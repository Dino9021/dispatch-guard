#!/usr/bin/env python3
"""The near-reset net zone, as shipped in 0.66 (ADR 20260929-152000 v3, reduced scope).

    python Tools/Debug/test_net_zone.py

⛔ WHY. 2026-09-29 14:00-14:10: the relaxation said GO at 91-94%, the meter read 100% at 14:07:12
and three of four sessions in the net zone were refused by the provider. Only the ATTENDED session
had a resume (its turn ended normally, so the Stop hook armed it); a turn cut by the cap fires no
Stop hook, and the tool-path note never armed. And had the alarm fired, the stand-down rule
("the arming session was active in the last 30 minutes") would have cancelled it - a session cut
by the cap still has a fresh heartbeat. The pins:

  1. D3: a resume stands down only on the arming session's activity AFTER the reset it was armed
     for (`armed_for_reset`, else the original `first_at`); before-only → RUN; no threshold → RUN;
     no session id → RUN, never a machine-wide glob; `_rearm` never moves `first_at`;
  2. the tool path arms once per window, and a HANDOFF.md written at STOP / in the net zone is
     armed from PostToolUse;
  3. no note claims a resume the session does not have;
  4. WALL-HIT is found after the reset from the history, logged once, announced once per session,
     and ignores another account's rows.

⚠ Nothing is registered with a real scheduler: `arm_from_handoff` / `schedule` / `subprocess.run`
are stubbed wherever they would reach one.
"""

import contextlib
import importlib.util
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import fresh_scratch, repo_path, scratch_dir   # noqa: E402

SID = "net-zone-sid"


class Result(object):
    def __init__(self, code, out=b"", err=b""):
        self.returncode, self.stdout, self.stderr = code, out, err


def load():
    sys.path.insert(0, repo_path("hooks"))
    spec = importlib.util.spec_from_file_location("dg_resume_nz", repo_path("hooks", "resume.py"))
    resume = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(resume)
    import dispatch_gate
    return resume, dispatch_gate


def touch(path, when):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("x")
    os.utime(path, (when, when))


def run_do_run(mod, sdir, state, alive_at=None, session_id=SID, other_alive=False):
    """Drive the real do_run against one record. Returns the RESUME log text."""
    handoff = os.path.join(sdir, "HANDOFF.md")
    with open(handoff, "w", encoding="utf-8") as f:
        f.write("# handoff\n" + "the next step is written here in full. " * 12)
    state = dict(state, handoff=handoff, task=sdir, cwd=sdir)
    if session_id:
        mod.write_record(sdir, session_id, dict(state, session_id=session_id))
    else:
        with open(os.path.join(sdir, "resume.json"), "w", encoding="utf-8") as f:
            json.dump(state, f)
    if alive_at is not None and session_id:
        touch(mod.dispatch_gate.state_path(sdir, session_id, "alive"), alive_at)
    if other_alive:
        touch(mod.dispatch_gate.state_path(sdir, "SOMEBODY-ELSE", "alive"), time.time())
    saved = (mod.subprocess.run, mod.schedule)
    mod.subprocess.run = lambda *a, **k: Result(1)
    mod.schedule = lambda *a, **k: (["x"], Result(0))
    here = os.getcwd()
    os.chdir(sdir)
    try:
        with contextlib.redirect_stderr(io.StringIO()) as err:
            mod.do_run(sdir, mod.usage.config(sdir), session_id)
    finally:
        os.chdir(here)
        mod.subprocess.run, mod.schedule = saved
    return err.getvalue()


def case_d3_stand_down_only_after_the_reset(mod):
    now = time.time()
    reset = now - 180                                   # the alarm fired 3 min after this reset
    with scratch_dir("d3-after") as sdir:
        log = run_do_run(mod, sdir, {"at": now, "armed_for_reset": reset}, alive_at=reset + 60)
    assert "RUN-SKIPPED the session that armed this" in log, (
        "activity AFTER the reset did not stand the resume down: %s" % log)
    with scratch_dir("d3-before") as sdir:
        log = run_do_run(mod, sdir, {"at": now, "armed_for_reset": reset}, alive_at=reset - 120)
    assert "RUN-SKIPPED" not in log and "RUN starting" in log, (
        "a heartbeat from BEFORE the reset stood the resume down - a session cut by the cap "
        "looks exactly like this: %s" % log)
    # `--at` alarm: the ORIGINAL fire time, less the offset, is the threshold
    offset = mod.rcfg("/nonexistent")["resume_offset_min"] * 60
    with scratch_dir("d3-at-after") as sdir:
        log = run_do_run(mod, sdir, {"at": now, "first_at": now - 60},
                         alive_at=now - 60 - offset + 30)
    assert "RUN-SKIPPED the session that armed this" in log, log
    with scratch_dir("d3-at-before") as sdir:
        log = run_do_run(mod, sdir, {"at": now, "first_at": now - 60},
                         alive_at=now - 60 - offset - 30)
    assert "RUN-SKIPPED" not in log, log
    # no threshold (a record from before 0.66) -> RUN, however fresh the heartbeat
    with scratch_dir("d3-none") as sdir:
        log = run_do_run(mod, sdir, {"at": now}, alive_at=now)
    assert "RUN-SKIPPED" not in log and "RUN starting" in log, (
        "a record with no threshold stood down on liveness: %s" % log)
    # no session id -> RUN, and ANOTHER session's fresh heartbeat must not count (no glob)
    with scratch_dir("d3-nosid") as sdir:
        log = run_do_run(mod, sdir, {"at": now, "armed_for_reset": reset}, session_id=None,
                         other_alive=True)
    assert "RUN-SKIPPED" not in log, "a machine-wide heartbeat stood the resume down: %s" % log
    # _rearm moves `at`, never `first_at`
    with scratch_dir("d3-rearm") as sdir:
        st = {"session_id": SID, "at": now, "first_at": now - 60}
        mod.write_record(sdir, SID, st)
        saved = mod.schedule
        mod.schedule = lambda *a, **k: (["x"], Result(0))
        try:
            mod._rearm(sdir, dict(st), 20)
        finally:
            mod.schedule = saved
        after = json.load(open(mod.record_path(sdir, SID), encoding="utf-8"))
    assert after["first_at"] == now - 60 and after["at"] > now, after
    print("ok - a resume stands down only on the arming session's activity after its reset")


def net_dir(gate, sdir, pct=90, minutes=20):
    os.makedirs(os.path.join(sdir, "state"), exist_ok=True)
    with open(gate.state_path(sdir, SID, "start"), "w", encoding="utf-8") as f:
        f.write("x")
    now = time.time()
    reset = int(now + minutes * 60)
    with open(os.path.join(sdir, "token_usage.json"), "w", encoding="utf-8") as f:
        json.dump({"ts": int(now * 1000),
                   "five_hour": {"used_percentage": pct, "resets_at": reset}}, f)
    return now, reset


def case_tool_path_arms_once_per_window(gate):
    calls = []
    saved = gate.arm_from_handoff
    gate.arm_from_handoff = lambda root, sdir, cfg, sid, v=None: (calls.append(sid), "armed")[1]
    try:
        with scratch_dir("tool-arm") as sdir:
            now, reset = net_dir(gate, sdir)
            note = gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now)
            assert calls == [SID], "the first net note did not try to arm: %r" % calls
            assert note and "being armed" in note, note
            gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now + 60)
            gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now + 120)
            assert calls == [SID], "the tool path re-armed inside one window: %r" % calls
        with scratch_dir("tool-arm-subagent") as sdir:
            now, reset = net_dir(gate, sdir)
            del calls[:]
            gate.wind_down_note({"session_id": SID, "agent_id": "agent-7"}, sdir, sdir, {}, now=now)
            assert calls == [], ("a SUB-AGENT's tool call armed the parent's resume (its payload "
                                 "carries the parent's session id): %r" % calls)
        with scratch_dir("tool-arm") as sdir:
            now, reset = net_dir(gate, sdir)
            gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now)
            # a HANDOFF.md written now arms at once (PostToolUse) - unless a resume is live
            del calls[:]
            os.remove(gate.state_path(sdir, SID, gate.ARM_MARK)) if os.path.exists(
                gate.state_path(sdir, SID, gate.ARM_MARK)) else None
            gate.arm_on_handoff_write(sdir, sdir, {}, SID)
            assert calls == [SID], "a fresh HANDOFF.md in the net zone was not armed: %r" % calls
            os.makedirs(os.path.join(sdir, "resume"), exist_ok=True)
            with open(os.path.join(sdir, "resume", gate.safe_session(SID) + ".json"), "w",
                      encoding="utf-8") as f:
                json.dump({"at": reset + 180, "session_id": SID}, f)
            del calls[:]
            gate.arm_on_handoff_write(sdir, sdir, {}, SID)
            assert calls == [], "a session with a live resume was armed again: %r" % calls
        with scratch_dir("tool-arm-go") as sdir:
            net_dir(gate, sdir, pct=10)
            del calls[:]
            gate.arm_on_handoff_write(sdir, sdir, {}, SID)
            assert calls == [], "a HANDOFF.md written at GO armed a resume: %r" % calls
    finally:
        gate.arm_from_handoff = saved
    # ⛔ AND THE POSTTOOLUSE BRANCH MUST CALL IT - the cases above drive the function directly and
    # stay green while nothing calls it. Code lines only (comments quote the name).
    src = open(repo_path("hooks", "dispatch_gate.py"), encoding="utf-8").read()
    body = src[src.index('if event == "PostToolUse":'):]
    body = body[:body.index("except Exception")]
    code = "\n".join(l for l in body.splitlines() if not l.strip().startswith("#"))
    assert "arm_on_handoff_write(" in code, (
        "PostToolUse no longer arms a HANDOFF.md written at STOP / in the net zone")
    print("ok - the tool path arms once per window; a HANDOFF.md written in the net zone arms at once")


def case_notes_never_claim_a_missing_resume(gate):
    with scratch_dir("notes") as sdir:
        now, reset = net_dir(gate, sdir, pct=95, minutes=180)      # a real STOP, far from reset
        note = gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now)
    assert note and "usage is at STOP" in note, note
    assert "NO resume" in note and "is armed" not in note, (
        "the STOP note claims a resume this session does not have: %r" % note)
    src = open(repo_path("hooks", "usage.py"), encoding="utf-8").read()
    assert "A resume is armed" not in src, "usage.py tells every session its resume is armed again"
    print("ok - no note claims a resume the session does not have")


def case_net_zone_refuses_a_dispatch_for_real():
    """⛔ THE NET-ZONE REFUSAL MUST PRINT - through the real hook process.

    Found by code review A: the refusal's screen line called resume_state_line() with one argument
    short, raised TypeError inside the hook, and main() logged GATE-ERROR and printed nothing -
    and a hook that prints nothing ALLOWS the dispatch. Every in-process case stayed green.
    """
    import subprocess
    gate_py = repo_path("hooks", "dispatch_gate.py")
    with scratch_dir("net-deny") as work:
        sdir, repo = os.path.join(work, "state-root"), os.path.join(work, "repo")
        os.makedirs(os.path.join(sdir, "state"))
        os.makedirs(os.path.join(repo, ".git"))
        task = os.path.join(repo, "Memory", "tasks", "20260101-000000-t")
        os.makedirs(task)
        now = time.time()
        with open(os.path.join(sdir, "token_usage.json"), "w", encoding="utf-8") as f:
            json.dump({"ts": int(now * 1000),
                       "five_hour": {"used_percentage": 90, "resets_at": int(now + 20 * 60)}}, f)
        # ⛔ AUTO-ARM OFF: the real hook's dispatch path would spawn `resume.py --arm` from a
        # generated handoff and register a REAL scheduled task (measured - it did, and was deleted).
        with open(os.path.join(sdir, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"auto_arm_resume": False}, f)
        env = dict(os.environ, CLAUDE_DISPATCH_DIR=sdir)
        base = {"session_id": SID, "cwd": repo}

        def fire(payload):
            p = subprocess.run([sys.executable, gate_py], input=json.dumps(payload).encode("utf-8"),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=120)
            out = p.stdout.decode("utf-8", "replace").strip()
            return json.loads(out) if out else None

        fire(dict(base, hook_event_name="SessionStart"))
        time.sleep(1.1)                      # the plan must be provably newer than the stamp
        with open(os.path.join(task, "prompts.md"), "w", encoding="utf-8") as f:
            f.write("# plan\n## sub-task 1\nthe full prompt\n")
        for skill in ("dispatch-protocol", "unattended-work"):
            with open(os.path.join(sdir, "state", "%s.skill-seen-%s" % (SID, skill)), "w",
                      encoding="utf-8") as f:
                f.write(skill)
        got = fire(dict(base, hook_event_name="PreToolUse", tool_name="Agent", tool_use_id="t1",
                        tool_input={"subagent_type": "general-purpose", "description": "x",
                                    "prompt": "Work in %s and report." % task}))
        log = ""
        for p in (os.path.join(sdir, "dispatch_gate.log"),
                  os.path.join(repo, ".claude", "dispatch_gate.log")):
            if os.path.exists(p):
                log += open(p, encoding="utf-8").read()
    assert got is not None, ("FAIL-OPEN: the gate printed nothing for a net-zone dispatch - it is "
                             "ALLOWED. Log: %s" % log[-600:])
    hso = got.get("hookSpecificOutput", {})
    assert hso.get("permissionDecision") == "deny", got
    assert "NET zone" in got.get("systemMessage", ""), got
    assert "NO resume" in got.get("systemMessage", "") and "GATE-ERROR" not in log, (got, log[-400:])
    print("ok - a net-zone dispatch is refused by the real hook, and says the session has no resume")


def history_row(when, pct, reset, acct):
    fmt = "%Y-%m-%d %H:%M:%S"
    return json.dumps({"at": time.strftime(fmt, time.localtime(when)), "pct": pct,
                       "resets_at": time.strftime(fmt, time.localtime(reset)), "acct": acct})


def case_wall_hit(gate):
    now = time.time()
    reset = int(now - 600)                                  # the relaxed window reset 10 min ago
    with scratch_dir("wall-hit") as sdir:
        os.makedirs(os.path.join(sdir, "state"), exist_ok=True)
        os.makedirs(os.path.join(sdir, "logs"), exist_ok=True)
        with open(os.path.join(sdir, "state", "relaxed-%d.json" % reset), "w",
                  encoding="utf-8") as f:
            json.dump({"reset": reset, "acct": "ACCT-A"}, f)
        with open(os.path.join(sdir, "logs", "token_usage_history_%s.jsonl"
                               % time.strftime("%Y%m%d-000000")), "w", encoding="utf-8") as f:
            f.write(history_row(reset - 600, 94, reset, "ACCT-A") + "\n")
            f.write(history_row(reset - 400, 100, reset, "ACCT-B") + "\n")   # another account
            f.write(history_row(reset - 180, 100, reset, "ACCT-A") + "\n")   # THE hit
            f.write(history_row(reset + 60, 2, reset + 5 * 3600, "ACCT-A") + "\n")
        with contextlib.redirect_stderr(io.StringIO()):
            gate.check_wall_hit(sdir, sdir, now)
            gate.check_wall_hit(sdir, sdir, now + 60)
        hitf = os.path.join(sdir, "state", "wall-hit-%d.json" % reset)
        assert os.path.exists(hitf), "a window that reached 100% before its reset was not recorded"
        d = json.load(open(hitf, encoding="utf-8"))
        assert abs(d["hit"] - (reset - 180)) <= 1, ("the other account's row was taken: %r" % d)
        log = open(os.path.join(sdir, ".claude", "dispatch_gate.log"), encoding="utf-8").read()
        assert log.count("WALL-HIT") == 1, "WALL-HIT not logged exactly once: %r" % log
        n1 = gate.wall_hit_note(sdir, SID, now)
        n2 = gate.wall_hit_note(sdir, SID, now + 60)
        n3 = gate.wall_hit_note(sdir, "ANOTHER-SESSION", now)
        assert "hit the cap" in n1 and n2 == "" and "hit the cap" in n3, (n1, n2, n3)
        assert gate.wall_hit_note(sdir, "LATE-SESSION", reset + 7 * 3600) == "", \
            "a wall hit was announced more than 6 hours later"
    with scratch_dir("wall-clear") as sdir:
        os.makedirs(os.path.join(sdir, "state"), exist_ok=True)
        os.makedirs(os.path.join(sdir, "logs"), exist_ok=True)
        with open(os.path.join(sdir, "state", "relaxed-%d.json" % reset), "w",
                  encoding="utf-8") as f:
            json.dump({"reset": reset, "acct": "ACCT-A"}, f)
        with open(os.path.join(sdir, "logs", "token_usage_history_%s.jsonl"
                               % time.strftime("%Y%m%d-000000")), "w", encoding="utf-8") as f:
            f.write(history_row(reset - 180, 95, reset, "ACCT-A") + "\n")
        gate.check_wall_hit(sdir, sdir, now)
        assert not os.path.exists(os.path.join(sdir, "state", "wall-hit-%d.json" % reset)), \
            "a window that never reached the cap was recorded as a wall hit"
        assert os.path.exists(os.path.join(sdir, "state", "wall-checked-%d.json" % reset))
    print("ok - WALL-HIT is found from the history after the reset, logged once, told once each")


def main():
    fresh_scratch()
    os.environ["CLAUDE_DISPATCH_DIR"] = os.path.join(fresh_scratch(), "state-dir-for-the-log")
    resume, gate = load()
    case_d3_stand_down_only_after_the_reset(resume)
    case_tool_path_arms_once_per_window(gate)
    case_notes_never_claim_a_missing_resume(gate)
    case_net_zone_refuses_a_dispatch_for_real()
    case_wall_hit(gate)
    print("net zone OK")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
