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
     and ignores another account's rows;
  5. (0.67, ADR 20261001-065500) the relaxed-PACE band arms first - tool path, HANDOFF write, turn
     end - keeps the alarm at GO, says so once per window without reading as a wind-down, never
     refuses a dispatch, and aims the resume at the relaxed window only when the word is GO.

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


PROMPTS = []        # every `claude -p` argv do_run would have started (run_do_run captures it)


def run_do_run(mod, sdir, state, alive_at=None, session_id=SID, other_alive=False, body=None):
    """Drive the real do_run against one record. Returns the RESUME log text."""
    handoff = os.path.join(sdir, "HANDOFF.md")
    with open(handoff, "w", encoding="utf-8") as f:
        f.write(body if body is not None
                else "# handoff\n" + "the next step is written here in full. " * 12)
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
    mod.subprocess.run = lambda *a, **k: (PROMPTS.append(list(a[0]) if a else []), Result(1))[1]
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
            assert os.path.exists(gate.state_path(sdir, SID, "net-seen-%d" % reset)), \
                "a session in the net zone was not marked, so it would never hear a WALL-HIT"
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
        # only sessions that worked in the net zone of that window hear it (0.66.1)
        for s in (SID, "OTHER-NET-SESSION", "LATE-SESSION"):
            touch(gate.state_path(sdir, s, "net-seen-%d" % reset), reset - 900)
        n1 = gate.wall_hit_note(sdir, SID, now)
        n2 = gate.wall_hit_note(sdir, SID, now + 60)
        n3 = gate.wall_hit_note(sdir, "OTHER-NET-SESSION", now)
        n4 = gate.wall_hit_note(sdir, "NEVER-IN-THE-NET-ZONE", now)
        assert "hit the cap" in n1 and n2 == "" and "hit the cap" in n3, (n1, n2, n3)
        assert n4 == "", ("a session that was never in the net zone was told about a cap cut it "
                          "could not have suffered: %r" % n4)
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


def write_usage(sdir, pct, reset, pct7=None, reset7=None):
    """token_usage.json with a FIXED reset, so two readings can share one window."""
    d = {"ts": int(time.time() * 1000), "five_hour": {"used_percentage": pct, "resets_at": reset}}
    if pct7 is not None:
        d["seven_day"] = {"used_percentage": pct7, "resets_at": reset7}
    with open(os.path.join(sdir, "token_usage.json"), "w", encoding="utf-8") as f:
        json.dump(d, f)


def case_relaxed_pace_arms_first(gate, resume):
    """⭐ 0.67 - THE RELAXED-PACE BAND ARMS, KEEPS AND TELLS (ADR 20261001-065500).

    2026-10-01: a session wrote its HANDOFF.md at 86% with 23 min to the reset; the band read as
    plain GO, nothing armed, and the window then jumped to 95%. Owner: 「handoff跟鬧鐘還是要先上」.
    """
    usage = gate.usage
    calls = []
    saved = gate.arm_from_handoff

    def fake_arm(root, sdir, cfg, sid, v=None):
        # like the real maybe_auto_arm: the spawn mark is what own_resume() reads as "arming"
        calls.append(sid)
        touch(gate.state_path(sdir, sid, gate.ARM_MARK), time.time())
        return "armed"
    gate.arm_from_handoff = fake_arm
    try:
        with scratch_dir("rlx-note") as sdir:
            now, reset = net_dir(gate, sdir, pct=85, minutes=20)
            for cheap in (True, False):
                v = usage.verdict(sdir, usage.config(sdir), cheap=cheap)
                assert v["verdict"] == "GO" and v["relaxed_pace"] and not v["relaxed_stop"], v
            note = gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now)
            assert calls == [SID], "the first relaxed-PACE note did not try to arm: %r" % calls
            assert note and "not a wind-down" in note and "HANDOFF.md" in note, note
            assert "being armed" in note and "--cancel --session %s" % SID in note, (
                "the note printed while the arm is in flight lacks the cancel command: %r" % note)
            assert "⛔" not in note and "NET" not in note and "STOP" not in note, (
                "the relaxed-PACE note reads like a wind-down or a net zone: %r" % note)
            # ⭐ 0.68 (owner 「要加」): WALL-HIT covers the relaxed-PACE band too
            assert os.path.exists(gate.state_path(sdir, SID, "net-seen-%d" % reset)), \
                "a session at relaxed PACE was not marked, so it would never hear a WALL-HIT"
            assert os.path.exists(os.path.join(sdir, "state", "relaxed-%d.json" % reset)), \
                "a relaxed-PACE window was not recorded for the WALL-HIT check"
            assert gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now + 60) is None, \
                "the relaxed-PACE note repeated inside one window with the same resume state"
            assert calls == [SID], "the tool path re-armed inside one window: %r" % calls
            # the record lands: "arming" -> "armed" is the same key, so no second note
            os.makedirs(os.path.join(sdir, "resume"), exist_ok=True)
            with open(os.path.join(sdir, "resume", gate.safe_session(SID) + ".json"), "w",
                      encoding="utf-8") as f:
                json.dump({"at": reset + 180, "session_id": SID}, f)
            assert gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now + 120) is None
        with scratch_dir("rlx-armed") as sdir:
            # already armed when the band starts: the note says for when, and how to cancel
            now, reset = net_dir(gate, sdir, pct=85, minutes=20)
            os.makedirs(os.path.join(sdir, "resume"), exist_ok=True)
            with open(os.path.join(sdir, "resume", gate.safe_session(SID) + ".json"), "w",
                      encoding="utf-8") as f:
                json.dump({"at": reset + 180, "session_id": SID}, f)
            del calls[:]
            note = gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now)
            assert calls == [], "a session with a live resume was armed again: %r" % calls
            assert note and "armed for" in note and "--cancel --session %s" % SID in note, note
        with scratch_dir("rlx-flicker") as sdir:
            # ⚠ A PACE <-> relaxed-PACE flicker inside ONE window must not re-print either note.
            now, reset = net_dir(gate, sdir, pct=85, minutes=25)
            out = []
            for pct in (85, 89, 85, 89):           # 85 relaxes 25 min out, 89 does not
                write_usage(sdir, pct, reset)
                out.append(gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now))
            assert out[0] and "not a wind-down" in out[0], out
            assert out[1] and "usage is at PACE" in out[1], out
            assert out[2] is None and out[3] is None, ("a PACE / relaxed-PACE flicker re-printed "
                                                       "the notes: %r" % out)
        with scratch_dir("rlx-subagent") as sdir:
            now, reset = net_dir(gate, sdir, pct=85, minutes=20)
            del calls[:]
            got = gate.wind_down_note({"session_id": SID, "agent_id": "agent-7"}, sdir, sdir, {},
                                      now=now)
            assert got is None and calls == [], ("a SUB-AGENT at relaxed PACE was told, or armed "
                                                 "its parent's resume: %r %r" % (got, calls))
        with scratch_dir("rlx-and-net") as sdir:
            # ⚠ PRECEDENCE: a relaxed STOP in one window and a relaxed PACE in the other is the NET
            # zone - its note still reaches a sub-agent (it says "start NO new sub-agent").
            now, reset = net_dir(gate, sdir, pct=90, minutes=20)
            write_usage(sdir, 90, reset, pct7=95, reset7=int(now + 30 * 60))
            v = usage.verdict(sdir, usage.config(sdir), cheap=True)
            assert v["relaxed_stop"] and v["relaxed_pace"], v
            got = gate.wind_down_note({"session_id": SID, "agent_id": "agent-7"}, sdir, sdir, {},
                                      now=now)
            assert got and "NET zone" in got, "relaxed PACE hid the NET note: %r" % got
        with scratch_dir("rlx-write") as sdir:
            now, reset = net_dir(gate, sdir, pct=85, minutes=20)
            del calls[:]
            gate.arm_on_handoff_write(sdir, sdir, {}, SID)
            assert calls == [SID], "a HANDOFF.md written at relaxed PACE was not armed: %r" % calls
        with scratch_dir("rlx-plain-pace") as sdir:
            net_dir(gate, sdir, pct=85, minutes=180)          # a PACE far from the reset
            del calls[:]
            gate.arm_on_handoff_write(sdir, sdir, {}, SID)
            assert calls == [], "a HANDOFF.md written at a plain PACE armed on the write: %r" % calls
    finally:
        gate.arm_from_handoff = saved

    # ⭐ THE STOP-HOOK / PROMPT ARM (arm_from_handoff -> arm_trigger) and its ARMED line (D7)
    armed = []
    saved_auto = gate.maybe_auto_arm
    gate.maybe_auto_arm = lambda root, sdir, cfg, folder, *a, **k: (armed.append(folder), True)[1]
    try:
        with scratch_dir("rlx-stop-hook") as sdir:
            net_dir(gate, sdir, pct=85, minutes=20)
            folder = "20261001-000000-rlx"
            os.makedirs(os.path.join(sdir, "Memory", "tasks", folder))
            time.sleep(0.05)
            with open(os.path.join(sdir, "Memory", "tasks", folder, "HANDOFF.md"), "w",
                      encoding="utf-8") as f:
                f.write("# handoff\n" + "the next step is written here in full. " * 12)
            with open(gate.state_path(sdir, SID, gate.HANDOFF_SEEN), "w", encoding="utf-8") as f:
                f.write(folder + "\n")
            line = gate.arm_from_handoff(sdir, sdir, {"task_root": "Memory/tasks"}, SID)
            assert armed == [folder], "the turn's end at relaxed PACE did not arm: %r" % armed
            assert line and "a PACE relaxed near the reset" in line, line
            assert "--cancel --session %s" % SID in line, line
    finally:
        gate.maybe_auto_arm = saved_auto

    # ⭐ A GO THAT IS A RELAXED PACE KEEPS THE ALARM - through the REAL verdict, not a typed dict.
    import types
    cancelled = []
    fake = types.ModuleType("resume")
    fake.record_path = resume.record_path
    fake.do_cancel = lambda sdir, quiet=False, session_id=None: (cancelled.append(session_id), 0)[1]
    saved_mod = sys.modules.get("resume")
    sys.modules["resume"] = fake
    try:
        with scratch_dir("rlx-keep") as sdir:
            now, reset = net_dir(gate, sdir, pct=85, minutes=20)
            os.makedirs(os.path.join(sdir, "resume"), exist_ok=True)
            with open(os.path.join(sdir, "resume", gate.safe_session(SID) + ".json"), "w",
                      encoding="utf-8") as f:
                json.dump({"at": reset + 180, "session_id": SID}, f)
            v = usage.verdict(sdir, usage.config(sdir))
            assert gate.stand_down_resume(sdir, sdir, v, SID) == "" and cancelled == [], (
                "a GO at relaxed PACE cancelled the alarm it had armed first: %r" % cancelled)
            write_usage(sdir, 3, reset)                        # the window reopened early
            v = usage.verdict(sdir, usage.config(sdir))
            gate.stand_down_resume(sdir, sdir, v, SID)
            assert cancelled == [SID], "a plain GO no longer cancels the alarm: %r" % cancelled
    finally:
        if saved_mod is not None:
            sys.modules["resume"] = saved_mod
        else:
            sys.modules.pop("resume", None)

    # ⛔ THE RESUME TARGET (D2): a relaxed 7d PACE names the 7d reset only when the word is GO.
    with scratch_dir("rlx-target") as sdir:
        now = time.time()
        r5, r7 = int(now + 180 * 60), int(now + 30 * 60)
        write_usage(sdir, 95, r5, pct7=95, reset7=r7)          # 5h far STOP + 7d relaxed PACE
        assert resume.reset_time(sdir, usage.config(sdir)) == (r5, "5h"), \
            "a 7d relaxed PACE pulled a 5h STOP's resume to the 7d reset"
        write_usage(sdir, 10, r5, pct7=95, reset7=r7)          # the 7d relaxed PACE alone
        assert resume.reset_time(sdir, usage.config(sdir)) == (r7, "7d")
    print("ok - relaxed PACE arms first, keeps the alarm at GO, tells once, and aims at its window")


def case_relaxed_pace_edges(gate):
    """The branches code review A mutated and found unpinned (agent-02-code-review-a.md, N1 + N5)."""
    usage = gate.usage
    calls = []
    saved = gate.arm_from_handoff
    # an arm that does NOT start (no handoff yet): no spawn mark, so the state stays "none"
    gate.arm_from_handoff = lambda root, sdir, cfg, sid, v=None: (calls.append(sid), None)[1]
    try:
        with scratch_dir("rlx-key") as sdir:
            now, reset = net_dir(gate, sdir, pct=85, minutes=20)
            n1 = gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now)
            assert n1 and "no resume yet" in n1, n1
            # the resume state changes -> the note speaks again (the key carries it)
            os.makedirs(os.path.join(sdir, "resume"), exist_ok=True)
            with open(os.path.join(sdir, "resume", gate.safe_session(SID) + ".json"), "w",
                      encoding="utf-8") as f:
                json.dump({"at": reset + 180, "session_id": SID}, f)
            n2 = gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now + 60)
            assert n2 and "armed for" in n2, "none -> armed did not speak again: %r" % n2
            # a NEW window -> it speaks again (the key carries the reset)
            write_usage(sdir, 85, reset + 60)
            n3 = gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now + 120)
            assert n3 and "not a wind-down" in n3, "a new window's relaxed PACE was silent: %r" % n3
        with scratch_dir("rlx-then-net") as sdir:
            # N1: a failed attempt at relaxed PACE must not use up the NET zone's attempt
            now, reset = net_dir(gate, sdir, pct=85, minutes=20)
            del calls[:]
            gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now)
            write_usage(sdir, 90, reset)
            gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now + 60)
            assert calls == [SID, SID], ("the NET zone lost its tool-path arm to the relaxed-PACE "
                                         "attempt of the same window: %r" % calls)
        with scratch_dir("rlx-7d") as sdir:
            now, _r = net_dir(gate, sdir, pct=10, minutes=180)
            write_usage(sdir, 10, int(now + 180 * 60), pct7=95, reset7=int(now + 30 * 60))
            n = gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now)
            assert n and "7d at 95%" in n and time.strftime(
                "%H:%M", time.localtime(int(now + 30 * 60))) in n, (
                "a 7d relaxed PACE note shows the wrong window: %r" % n)
        with scratch_dir("rlx-7d-then-5h-stop") as sdir:
            # ⛔ review B, B1: armed for the 7d reset at a 7d relaxed PACE, then the 5h reaches a far
            # STOP. The 7d alarm would wake into the 5h STOP and give up - it must be re-aimed.
            now, _r = net_dir(gate, sdir, pct=10, minutes=180)
            r5, r7 = int(now + 180 * 60), int(now + 30 * 60)
            write_usage(sdir, 10, r5, pct7=95, reset7=r7)
            os.makedirs(os.path.join(sdir, "resume"), exist_ok=True)
            with open(os.path.join(sdir, "resume", gate.safe_session(SID) + ".json"), "w",
                      encoding="utf-8") as f:
                json.dump({"at": r7 + 180, "armed_for_reset": r7, "session_id": SID}, f)
            del calls[:]
            n = gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now)
            gate.arm_on_handoff_write(sdir, sdir, {}, SID)
            assert calls == [] and n and "armed for" in n, (
                "a resume aimed at the relaxed 7d reset was re-armed at that same band: %r %r"
                % (calls, n))
            write_usage(sdir, 95, r5, pct7=95, reset7=r7)
            n = gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now + 60)
            assert calls == [SID], ("the tool path kept a resume aimed at the 7d reset when the 5h "
                                    "STOP needs the 5h one: %r" % calls)
            assert n and "usage is at STOP" in n and "is armed" not in n, (
                "the STOP note claimed the 7d-aimed alarm covers this window: %r" % n)
            del calls[:]
            gate.arm_on_handoff_write(sdir, sdir, {}, SID)
            assert calls == [SID], ("a HANDOFF.md written at the 5h STOP was not armed because a "
                                    "resume for ANOTHER reset exists: %r" % calls)
        with scratch_dir("net-pace-keeps-5h") as sdir:
            # ⛔ 0.67.1: 5h relaxed STOP + 7d far PACE reads PACE with driver 7d, and reset_time()
            # names the 7d reset (pended N-7). A 5h-aimed net-zone alarm must NOT be moved days away.
            now, _r = net_dir(gate, sdir, pct=90, minutes=20)
            r5, r7 = int(now + 20 * 60), int(now + 3 * 86400)
            write_usage(sdir, 90, r5, pct7=95, reset7=r7)
            v = usage.verdict(sdir, usage.config(sdir), cheap=True)
            assert v["verdict"] == "PACE" and v["relaxed_stop"] and v["driver"] == "7d", v
            os.makedirs(os.path.join(sdir, "resume"), exist_ok=True)
            with open(os.path.join(sdir, "resume", gate.safe_session(SID) + ".json"), "w",
                      encoding="utf-8") as f:
                json.dump({"at": r5 + 180, "armed_for_reset": r5, "session_id": SID}, f)
            del calls[:]
            gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now)
            assert calls == [], ("the tool path re-aimed a 5h net-zone alarm at the far 7d PACE's "
                                 "reset: %r" % calls)
            gate.arm_on_handoff_write(sdir, sdir, {}, SID)
            assert calls == [], ("a HANDOFF write re-aimed a 5h net-zone alarm at the far 7d PACE's "
                                 "reset: %r" % calls)
        with scratch_dir("re-aim-in-flight") as sdir:
            # fix review F1: once the re-aim has started, the next tool call must not say "NO resume"
            now, _r = net_dir(gate, sdir, pct=10, minutes=180)
            r5, r7 = int(now + 180 * 60), int(now + 30 * 60)
            write_usage(sdir, 95, r5, pct7=95, reset7=r7)
            os.makedirs(os.path.join(sdir, "resume"), exist_ok=True)
            with open(os.path.join(sdir, "resume", gate.safe_session(SID) + ".json"), "w",
                      encoding="utf-8") as f:
                json.dump({"at": r7 + 180, "armed_for_reset": r7, "armed_at": now - 600,
                           "session_id": SID}, f)
            touch(gate.state_path(sdir, SID, gate.ARM_MARK), now - 600)    # the OLD arm's mark

            def spawn(root, sdir_, cfg, sid, v=None):
                calls.append(sid)
                touch(gate.state_path(sdir_, sid, gate.ARM_MARK), time.time())
                return "armed"
            gate.arm_from_handoff = spawn
            del calls[:]
            n1 = gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=time.time())
            n2 = gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=time.time())
            assert calls == [SID] and n1 and "being armed" in n1, (calls, n1)
            assert n2 is None, ("the call after a re-aim started said the session has no resume: %r"
                                % n2)
            gate.arm_from_handoff = lambda root, sdir, cfg, sid, v=None: (calls.append(sid), None)[1]
        with scratch_dir("re-aim-old-mark") as sdir:
            # ...but the OLD arm's own fresh mark is not a re-aim in flight: it must still try
            now, _r = net_dir(gate, sdir, pct=10, minutes=180)
            r5, r7 = int(now + 180 * 60), int(now + 30 * 60)
            write_usage(sdir, 95, r5, pct7=95, reset7=r7)
            os.makedirs(os.path.join(sdir, "resume"), exist_ok=True)
            with open(os.path.join(sdir, "resume", gate.safe_session(SID) + ".json"), "w",
                      encoding="utf-8") as f:
                json.dump({"at": r7 + 180, "armed_for_reset": r7, "armed_at": now - 30,
                           "session_id": SID}, f)
            touch(gate.state_path(sdir, SID, gate.ARM_MARK), now - 31)     # spawned, then recorded
            del calls[:]
            gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now)
            assert calls == [SID], ("the old arm's spawn mark was taken for a re-aim in flight, so "
                                    "nothing re-aimed: %r" % calls)
        with scratch_dir("rlx-auto-off") as sdir:
            now, reset = net_dir(gate, sdir, pct=85, minutes=20)
            n = gate.wind_down_note({"session_id": SID}, sdir, sdir, {"auto_arm_resume": False},
                                    now=now)
            assert n and "auto_arm_resume is off" in n and "--arm --task" in n, n
    finally:
        gate.arm_from_handoff = saved

    # the ARMED line names a relaxed STOP too
    saved_auto = gate.maybe_auto_arm
    gate.maybe_auto_arm = lambda *a, **k: True
    try:
        with scratch_dir("net-armed-label") as sdir:
            net_dir(gate, sdir, pct=90, minutes=20)
            folder = "20261001-000000-net"
            os.makedirs(os.path.join(sdir, "Memory", "tasks", folder))
            time.sleep(0.05)
            with open(os.path.join(sdir, "Memory", "tasks", folder, "HANDOFF.md"), "w",
                      encoding="utf-8") as f:
                f.write("# handoff\n" + "the next step is written here in full. " * 12)
            with open(gate.state_path(sdir, SID, gate.HANDOFF_SEEN), "w", encoding="utf-8") as f:
                f.write(folder + "\n")
            line = gate.arm_from_handoff(sdir, sdir, {"task_root": "Memory/tasks"}, SID)
            assert line and "a STOP relaxed near the reset" in line, line
    finally:
        gate.maybe_auto_arm = saved_auto

    # the AUTO-ARM log line carries the band - the real maybe_auto_arm, with Popen stubbed so
    # nothing reaches a scheduler
    import subprocess as _sp
    spawned = []
    saved_popen = _sp.Popen
    _sp.Popen = lambda argv, **kw: spawned.append(argv)
    try:
        with scratch_dir("rlx-band-log") as sdir:
            now, reset = net_dir(gate, sdir, pct=85, minutes=20)
            folder = "20261001-000000-band"
            os.makedirs(os.path.join(sdir, "Memory", "tasks", folder))
            with open(os.path.join(sdir, "Memory", "tasks", folder, "HANDOFF.md"), "w",
                      encoding="utf-8") as f:
                f.write("# handoff\n" + "the next step is written here in full. " * 12)
            assert gate.maybe_auto_arm(sdir, sdir, {"task_root": "Memory/tasks"}, folder,
                                       now - 60, SID) is True
            log = open(os.path.join(sdir, ".claude", "dispatch_gate.log"), encoding="utf-8").read()
            assert "band=relaxed-pace" in log and len(spawned) == 1, (log[-300:], spawned)
            assert "--session" in spawned[0], spawned
    finally:
        _sp.Popen = saved_popen
    print("ok - relaxed PACE re-speaks on a state or window change, keeps the NET zone's arm, "
          "names its window, and logs its band")


def run_main(gate, payload, sdir):
    """The real main() in-process (so stubs hold), its one print captured as parsed JSON or None."""
    saved_in, saved_env = sys.stdin, os.environ.get("CLAUDE_DISPATCH_DIR")
    sys.stdin = io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode("utf-8")), encoding="utf-8")
    os.environ["CLAUDE_DISPATCH_DIR"] = sdir
    try:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            gate.main()
    finally:
        sys.stdin = saved_in
        if saved_env is None:
            os.environ.pop("CLAUDE_DISPATCH_DIR", None)
        else:
            os.environ["CLAUDE_DISPATCH_DIR"] = saved_env
    text = out.getvalue().strip()
    return json.loads(text) if text else None


def case_the_alarm_wakes_the_session(gate, resume):
    """⭐ 0.68 (owner 2026-10-01, ADR 20261001-085000): the alarm should wake THE SESSION, and a
    woken run checks first and stops when nothing is left.

    The OS alarm can only start a NEW headless run; what wakes the session itself is a one-shot
    CronCreate it schedules - so every arm text the model reads asks for it, at a minute after the
    reset and BEFORE the OS alarm, and every wake / headless prompt carries the check-first rule.
    """
    usage = gate.usage
    # --- wake_time: after the reset, before the OS alarm, never on :00 / :30, day and month pinned
    with scratch_dir("wake-time") as sdir:
        hour = int(time.time() // 3600 * 3600) + 7200            # an on-the-hour reset
        r = int(time.mktime(time.localtime(hour)))
        t, cron = gate.wake_time(sdir, None, {"at": r + 180, "armed_for_reset": r})
        lt = time.localtime(r + 60)
        assert t == r + 60 and cron == "%d %d %d %d *" % (lt.tm_min, lt.tm_hour, lt.tm_mday,
                                                        lt.tm_mon), (t, cron, r)
        t2, _c = gate.wake_time(sdir, None, {"at": r + 120, "armed_for_reset": r - 60})
        assert time.localtime(t2).tm_min not in (0, 30) and r - 60 < t2 < r + 120, (
            "a wake landing on :00 fires up to 90 s early - it must move off the mark: %r" % t2)
        assert gate.wake_time(sdir, None, {"at": r + 60, "armed_for_reset": r}) is None, \
            "with the OS alarm 1 min after the reset there is no minute between - offer nothing"
        far = r + 3 * 86400
        _t, cron7 = gate.wake_time(sdir, None, {"at": far + 180, "armed_for_reset": far})
        lf = time.localtime(far + 60)
        assert cron7.endswith("%d %d *" % (lf.tm_mday, lf.tm_mon)), (
            "a 7d reset days away must not read as today: %r" % cron7)
    # --- every arm text the model reads asks for the session's own wake
    calls = []
    saved = gate.arm_from_handoff

    def spawn(root, sdir_, cfg, sid, v=None):
        calls.append(sid)
        touch(gate.state_path(sdir_, sid, gate.ARM_MARK), time.time())
        return "armed"
    gate.arm_from_handoff = spawn
    try:
        for name, pct in (("wake-rlx", 85), ("wake-net", 90), ("wake-stop", 95)):
            with scratch_dir(name) as sdir:
                now, reset = net_dir(gate, sdir, pct=pct, minutes=20 if pct < 95 else 180)
                n = gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now)
                assert n and "CronCreate" in n and 'cron "' in n and "dispatch-guard wake" in n, (
                    "the %s note does not ask for the wake that wakes this session: %r" % (name, n))
                assert "stop - no other work" in n, n
    finally:
        gate.arm_from_handoff = saved
    # --- the HANDOFF-write arm is told on the SAME PostToolUse, composed into its one print
    saved_w, saved_after = gate.arm_on_handoff_write, gate.cmd_guards.after_command
    after = []
    gate.arm_on_handoff_write = lambda *a, **k: " ⭐ dispatch-guard: a resume was ARMED TEST-LINE"
    gate.cmd_guards.after_command = lambda payload, ctx: (after.append(1), "AFTER-TEXT")[1]
    try:
        with scratch_dir("post-write") as work:
            sdir, repo = os.path.join(work, "state"), os.path.join(work, "repo")
            os.makedirs(os.path.join(sdir, "state"))
            os.makedirs(os.path.join(repo, ".git"))
            hp = os.path.join(repo, "Memory", "tasks", "20260101-000000-t", "HANDOFF.md")
            base = {"hook_event_name": "PostToolUse", "session_id": SID, "cwd": repo,
                    "tool_response": {}}
            got = run_main(gate, dict(base, tool_name="Write", tool_input={"file_path": hp}), sdir)
            assert got and "ARMED TEST-LINE" in json.dumps(got) and "ARMED TEST-LINE" in str(
                got.get("systemMessage")), ("a HANDOFF.md armed on its write was not told: %r" % got)
            got = run_main(gate, dict(base, tool_name="Bash", tool_input={
                "command": "echo x > Memory/tasks/20260101-000000-t/HANDOFF.md"}), sdir)
            assert after, "the shell-guard after_command did not run - an early return skipped it"
            blob = json.dumps(got)
            assert "AFTER-TEXT" in blob and "ARMED TEST-LINE" in blob, (
                "the ARMED line and the shell guard's text were not composed into one print: %r"
                % got)
            gate.arm_on_handoff_write = lambda *a, **k: ""
            assert run_main(gate, dict(base, tool_name="Write", tool_input={"file_path": hp}),
                            sdir) is None, "a PostToolUse with nothing to say printed something"
    finally:
        gate.arm_on_handoff_write, gate.cmd_guards.after_command = saved_w, saved_after
    # --- the prompt path arms in the relaxed bands, without an acknowledgement line
    armed = []
    gate.arm_from_handoff = lambda root, sdir_, cfg, sid, v=None: (armed.append(sid), " ARMED-LINE")[1]
    try:
        with scratch_dir("prompt-rlx") as sdir:
            net_dir(gate, sdir, pct=85, minutes=20)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                gate.on_user_prompt({"session_id": SID, "hook_event_name": "UserPromptSubmit"},
                                    sdir, sdir, {})
            o = out.getvalue()
            assert armed == [SID] and "ARMED-LINE" in o, ("a prompt at relaxed PACE did not arm: "
                                                          "%r %r" % (armed, o))
            assert "FIRST, IN YOUR NEXT MESSAGE" not in o, "relaxed PACE demanded a wind-down line"
        with scratch_dir("prompt-go") as sdir:
            net_dir(gate, sdir, pct=10, minutes=20)
            del armed[:]
            with contextlib.redirect_stdout(io.StringIO()):
                gate.on_user_prompt({"session_id": SID, "hook_event_name": "UserPromptSubmit"},
                                    sdir, sdir, {})
            assert armed == [], "a plain GO prompt armed a resume: %r" % armed
    finally:
        gate.arm_from_handoff = saved
    # --- every woken run checks first and stops when nothing is left
    now = time.time()
    with scratch_dir("check-first") as sdir:
        del PROMPTS[:]
        run_do_run(resume, sdir, {"at": now, "armed_for_reset": now - 180,
                                  "armed_at": now - 3600})
        p = PROMPTS[-1][-1] if PROMPTS else ""
        assert "FIRST CHECK WHETHER ITS WORK IS STILL UNFINISHED" in p and "--since=" in p, p[:300]
        assert "STOP: no other work, no looking for work in boards" in p, p[:600]
        assert '"' not in p.split("--since=")[1].split(" ")[0], "a quote reached the argv"
    with scratch_dir("check-first-recon") as sdir:
        del PROMPTS[:]
        run_do_run(resume, sdir, {"at": now, "armed_for_reset": now - 180}, body="x")
        p = PROMPTS[-1][-1] if PROMPTS else ""
        assert "NO handoff" in p and "THEN CHECK BEFORE YOU CONTINUE" in p, p[:300]
    # --- the hand-run `--arm` reminder gives the same minute and the same wake prompt
    with scratch_dir("reminder") as sdir:
        r = int(time.time() // 3600 * 3600) + 7200
        with contextlib.redirect_stdout(io.StringIO()) as out:
            resume.print_route_a_reminder(time.localtime(r + 180), sdir, r, "X/HANDOFF.md")
        o = out.getvalue()
        lt = time.localtime(r + 60)
        assert ('cron "%d %d %d %d *"' % (lt.tm_min, lt.tm_hour, lt.tm_mday, lt.tm_mon)) in o, o
        assert "dispatch-guard wake" in o and "X/HANDOFF.md" in o, o
    print("ok - every arm asks for the wake that wakes this session, before the OS alarm; the "
          "HANDOFF-write arm is told on its PostToolUse; woken runs check first and stop")


def case_cowork_wake_checks_in_first(gate, resume):
    """⭐ 0.68 (owner 2026-10-01, ADR 20261001-085000 D8): a session woken by its alarm, by the
    owner after an idle stretch, or after a resume / clear / compaction is told - when a peer is
    live or it worked under cowork - to re-read the board and rewrite its own check-in first."""
    now = time.time()
    # --- what counts as a wake
    wr = gate.wake_reason
    assert wr({"hook_event_name": "SessionStart", "source": "compact"}, {}) == \
        "after a context compaction"
    assert wr({"hook_event_name": "SessionStart", "source": "clear"}, {}) == "after /clear"
    assert wr({"hook_event_name": "SessionStart", "source": "startup"}, {}) is None
    up = {"hook_event_name": "UserPromptSubmit"}
    assert wr(dict(up, prompt=gate.wake_prompt("H.md")), {}) == "by its alarm"
    assert wr(dict(up, prompt="hi", _dg_prev_alive=now - 31 * 60), {}, now) == "after 31 idle minutes"
    assert wr(dict(up, prompt="hi", _dg_prev_alive=now - 5 * 60), {}, now) is None
    assert wr(dict(up, prompt="hi"), {}, now) is None, "no previous heartbeat must not be a wake"
    assert wr(dict(up, prompt="hi", _dg_prev_alive=now - 45 * 60), {"wake_gap_min": 60}, now) is None
    assert gate.wake_prompt("H.md").index("check-in") < gate.wake_prompt("H.md").index("H.md"), \
        "the route-A wake must check in BEFORE its check-first step (ADR D8, review B1)"

    def tree(work, peer=True, seen=False):
        sdir, repo = os.path.join(work, "state"), os.path.join(work, "repo")
        os.makedirs(os.path.join(sdir, "state"))
        os.makedirs(os.path.join(repo, ".git"))
        with open(gate.state_path(sdir, SID, "start"), "w", encoding="utf-8") as f:
            json.dump({"at": now - 3600, "cwd": repo}, f)
        if peer:
            with open(gate.state_path(sdir, "PEER-SESSION", "start"), "w", encoding="utf-8") as f:
                json.dump({"at": now - 3600, "cwd": repo}, f)
            touch(gate.state_path(sdir, "PEER-SESSION", "alive"), time.time())
        if seen:
            touch(gate.state_path(sdir, SID, "skill-seen-cowork"), now)
        write_usage(sdir, 10, int(now + 3 * 3600))
        return sdir, repo
    # --- the note: only with a live peer or cowork in use; with this session's id
    with scratch_dir("cw-peer") as work:
        sdir, repo = tree(work)
        text, screen = gate.cowork_wake_note(dict(up, session_id=SID, prompt=gate.wake_prompt()),
                                             repo, sdir, {})
        assert "rewrite YOUR role's check-in" in text and SID in text and "Load" in text, text
        assert screen and "re-check-in" in screen and "1 live peer" in screen, screen
        log = open(os.path.join(repo, ".claude", "dispatch_gate.log"), encoding="utf-8").read()
        assert "WAKE-CHECKIN-NUDGE why=by-its-alarm peers=1" in log, log[-300:]
    with scratch_dir("cw-alone") as work:
        sdir, repo = tree(work, peer=False)
        assert gate.cowork_wake_note(dict(up, session_id=SID, prompt=gate.wake_prompt()),
                                     repo, sdir, {}) == ("", None), \
            "a lone session that never used cowork was told about a board"
    with scratch_dir("cw-seen") as work:
        sdir, repo = tree(work, peer=False, seen=True)
        text, _s = gate.cowork_wake_note(dict(up, session_id=SID, prompt=gate.wake_prompt()),
                                         repo, sdir, {})
        assert text and "Load" not in text, text
    # --- through the REAL main(): the idle gap is read BEFORE the heartbeat rewrites `.alive`
    with scratch_dir("cw-main-gap") as work:
        sdir, repo = tree(work)
        touch(gate.state_path(sdir, SID, "alive"), now - 40 * 60)
        got = run_main(gate, dict(up, session_id=SID, cwd=repo, prompt="are you there?"), sdir)
        blob = json.dumps(got, ensure_ascii=False)
        assert got and "idle minutes" in blob and "rewrite YOUR role's check-in" in blob, (
            "a prompt after 40 idle minutes with a live peer did not get the check-in line: %r"
            % got)
        assert "re-check-in" in str(got.get("systemMessage")), got
        got = run_main(gate, dict(up, session_id=SID, cwd=repo, prompt="and now?"), sdir)
        assert "check-in" not in json.dumps(got or {}), "the very next prompt was called a wake"
    with scratch_dir("cw-main-compact") as work:
        sdir, repo = tree(work)
        got = run_main(gate, {"hook_event_name": "SessionStart", "source": "compact",
                              "session_id": SID, "cwd": repo}, sdir)
        assert "after a context compaction" in json.dumps(got or {}), got
    # --- the headless run checks in only when it continues
    with scratch_dir("cw-headless") as sdir:
        del PROMPTS[:]
        run_do_run(resume, sdir, {"at": now, "armed_for_reset": now - 180})
        p = PROMPTS[-1][-1] if PROMPTS else ""
        assert "rewrite your role's check-in with YOUR session id (a run that stops does not)" in p, \
            p[:500]
    print("ok - a woken session (alarm, idle gap read before the heartbeat, compaction) is told "
          "to re-check-in on the board first; a lone one is not; a headless run checks in only "
          "when it continues")


def case_review_a_gaps(gate, resume):
    """The 0.68 branches code review A mutated and found unpinned (agent-03-code-review-a.md), and
    its three fixes: no past wake, no `None` session id, no route-A text on the person's screen."""
    now = time.time()
    r = int(now // 3600 * 3600) + 7200
    with scratch_dir("gap-wake-time") as sdir:
        # M8 a record without `at` -> reset + resume_offset_min; M17 the `reset` argument is used
        assert gate.wake_time(sdir, None, {"armed_for_reset": r})[0] == r + 60
        assert gate.wake_time(sdir, None, {}, reset=r)[0] == r + 60, "the reset argument was ignored"
        # fix: a stale record never yields a wake in the past
        assert gate.wake_time(sdir, None, {"armed_for_reset": now - 7200, "at": now - 7000}) is None
        # review B N3: whole minutes - a reset at :mm:59 must not wake at :mm+1:00, one second on
        t, _c = gate.wake_time(sdir, None, {"armed_for_reset": r + 59, "at": r + 59 + 600})
        assert t % 60 == 0 and t >= r + 59 + 60, (t - r)
        # fix review: never in the OS task's own minute (it fires at its floored minute)
        assert gate.wake_time(sdir, None, {"armed_for_reset": r + 30, "at": r + 150}) is None, \
            "a wake in the same minute as the OS task"
        # ...and never with under 2 minutes of lead: a one-shot cron that is late waits a YEAR
        # (reset 30 s ago, OS task in 170 s: the wake rounds to <= now + 110, before the task's
        # minute - so only the lead rule can refuse it)
        assert gate.wake_time(sdir, None, {"armed_for_reset": now - 30, "at": now + 170}) is None
    # review B N2: with no minute between the reset and the OS task the hand-run reminder names no
    # time at or before the reset
    with scratch_dir("gap-reminder-offset") as sdir:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            resume.print_route_a_reminder(time.localtime(r + 60), sdir, r, "X/HANDOFF.md")
        o = out.getvalue()
        assert "first minute AFTER the reset" in o and "shortly before" not in o, o
    # M19 a resumed session is a wake
    assert gate.wake_reason({"hook_event_name": "SessionStart", "source": "resume"}, {}) == "resumed"
    # fix: no session id, nothing to check in with - WITH a live peer, so "no peer" cannot be
    # what returns early (the first version of this pin was blind that way; mutation AF2)
    with scratch_dir("gap-no-sid") as work:
        sdir, repo = os.path.join(work, "state"), os.path.join(work, "repo")
        os.makedirs(os.path.join(sdir, "state"))
        os.makedirs(os.path.join(repo, ".git"))
        with open(gate.state_path(sdir, "PEER-SESSION", "start"), "w", encoding="utf-8") as f:
            json.dump({"at": now - 3600, "cwd": repo}, f)
        touch(gate.state_path(sdir, "PEER-SESSION", "alive"), time.time())
        assert gate.cowork_wake_note({"hook_event_name": "UserPromptSubmit",
                                      "prompt": gate.wake_prompt()}, repo, sdir, {}) == ("", None)
        assert gate.cowork_wake_note({"hook_event_name": "UserPromptSubmit", "session_id": SID,
                                      "prompt": gate.wake_prompt()}, repo, sdir, {})[0], \
            "control: with an id and the same live peer the line must appear"
    # M7 the STOP refusal's route-A hint carries the exact cron
    with scratch_dir("gap-wake-hint") as sdir:
        net_dir(gate, sdir, pct=95, minutes=180)
        v = gate.usage.verdict(sdir, gate.usage.config(sdir))
        assert 'cron "' in gate._wake_hint(v, sdir) and "dispatch-guard wake" in gate._wake_hint(v, sdir)
    # M5 the REAL arm_from_handoff line carries route A; fix: the screen copy does not
    saved_auto = gate.maybe_auto_arm
    gate.maybe_auto_arm = lambda *a, **k: True
    try:
        with scratch_dir("gap-armed-line") as sdir:
            net_dir(gate, sdir, pct=95, minutes=180)
            folder = "20261001-000000-gap"
            os.makedirs(os.path.join(sdir, "Memory", "tasks", folder))
            time.sleep(0.05)
            with open(os.path.join(sdir, "Memory", "tasks", folder, "HANDOFF.md"), "w",
                      encoding="utf-8") as f:
                f.write("# handoff\n" + "the next step is written here in full. " * 12)
            with open(gate.state_path(sdir, SID, gate.HANDOFF_SEEN), "w", encoding="utf-8") as f:
                f.write(folder + "\n")
            line = gate.arm_from_handoff(sdir, sdir, {"task_root": "Memory/tasks"}, SID)
            assert line and "CronCreate" in line and 'cron "' in line, line
            assert "CronCreate" not in gate.for_screen(line) and "ARMED" in gate.for_screen(line)
            # review B N1: the person's copy keeps the cancel command (route A comes LAST)
            assert "--cancel --session %s" % SID in gate.for_screen(line), gate.for_screen(line)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                gate.on_stop({"session_id": SID}, sdir, sdir, {"task_root": "Memory/tasks"})
            o = out.getvalue()
            assert "ARMED" in o and "CronCreate" not in o, ("the Stop line (the person's) carries "
                                                            "the model's route-A text: %r" % o)
    finally:
        gate.maybe_auto_arm = saved_auto
    # M6 the relaxed-PACE note in the "armed" state carries route A
    with scratch_dir("gap-rlx-armed") as sdir:
        _n, reset = net_dir(gate, sdir, pct=85, minutes=20)
        os.makedirs(os.path.join(sdir, "resume"), exist_ok=True)
        with open(os.path.join(sdir, "resume", gate.safe_session(SID) + ".json"), "w",
                  encoding="utf-8") as f:
            json.dump({"at": reset + 180, "armed_for_reset": reset, "session_id": SID}, f)
        n = gate.wind_down_note({"session_id": SID}, sdir, sdir, {}, now=now)
        assert n and "armed for" in n and "CronCreate" in n, n
    # M1 a Bash PostToolUse whose shell guard says NOTHING still tells the ARMED line; fix: the
    # screen copy drops the route-A text, the model's copy keeps it
    saved_w, saved_after = gate.arm_on_handoff_write, gate.cmd_guards.after_command
    gate.arm_on_handoff_write = lambda *a, **k: " ARMED-X." + gate.ROUTE_A_LEAD + " CRON-X"
    gate.cmd_guards.after_command = lambda payload, ctx: None
    try:
        with scratch_dir("gap-post-bash") as work:
            sdir, repo = os.path.join(work, "state"), os.path.join(work, "repo")
            os.makedirs(os.path.join(sdir, "state"))
            os.makedirs(os.path.join(repo, ".git"))
            got = run_main(gate, {"hook_event_name": "PostToolUse", "session_id": SID, "cwd": repo,
                                  "tool_name": "Bash", "tool_response": {}, "tool_input": {
                                      "command": "echo x > Memory/tasks/20260101-000000-t/HANDOFF.md"}},
                           sdir)
            assert got and "CRON-X" in json.dumps(got.get("hookSpecificOutput")), got
            assert "ARMED-X" in str(got.get("systemMessage")) and "CRON-X" not in str(
                got.get("systemMessage")), got
    finally:
        gate.arm_on_handoff_write, gate.cmd_guards.after_command = saved_w, saved_after
    # M2/M3/M3b the cowork wake line at a PACE prompt - the first time and once already warned
    with scratch_dir("gap-pace-wake") as work:
        sdir, repo = os.path.join(work, "state"), os.path.join(work, "repo")
        os.makedirs(os.path.join(sdir, "state"))
        os.makedirs(os.path.join(repo, ".git"))
        for s in (SID, "PEER-SESSION"):
            with open(gate.state_path(sdir, s, "start"), "w", encoding="utf-8") as f:
                json.dump({"at": now - 3600, "cwd": repo}, f)
        touch(gate.state_path(sdir, "PEER-SESSION", "alive"), time.time())
        write_usage(sdir, 85, int(now + 180 * 60))                     # a plain PACE
        for _i in (1, 2):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                gate.on_user_prompt({"session_id": SID, "hook_event_name": "UserPromptSubmit",
                                     "prompt": gate.wake_prompt()}, repo, sdir, {})
            o = out.getvalue()
            assert "rewrite YOUR role's check-in" in o and "re-check-in" in o, (
                "a PACE prompt (call %d) dropped the cowork wake line: %r" % (_i, o[:400]))
    print("ok - review A's unpinned branches are pinned; no past wake, no None id, the screen "
          "copy of an arm line has no route-A text")


def case_relaxed_pace_dispatch_needs_a_handoff_for_real():
    """⭐ 0.68 (owner 「要加」, ADR 20261001-085000 D4): at relaxed PACE a dispatch needs a current
    HANDOFF.md - refused without one, allowed with one. Through the real hook process."""
    import subprocess
    gate_py = repo_path("hooks", "dispatch_gate.py")
    with scratch_dir("rlx-dispatch") as work:
        sdir, repo = os.path.join(work, "state-root"), os.path.join(work, "repo")
        os.makedirs(os.path.join(sdir, "state"))
        os.makedirs(os.path.join(repo, ".git"))
        task = os.path.join(repo, "Memory", "tasks", "20260101-000000-t")
        os.makedirs(task)
        now = time.time()
        write_usage(sdir, 85, int(now + 20 * 60))
        # ⛔ AUTO-ARM OFF, as in the net-zone case: never register a real scheduled task.
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
        time.sleep(1.1)
        with open(os.path.join(task, "prompts.md"), "w", encoding="utf-8") as f:
            f.write("# plan\n## sub-task 1\nthe full prompt\n")
        for skill in ("dispatch-protocol", "unattended-work"):
            with open(os.path.join(sdir, "state", "%s.skill-seen-%s" % (SID, skill)), "w",
                      encoding="utf-8") as f:
                f.write(skill)
        # ⚠ the task folder in the form the plan check resolves (task_root/<folder>/...)
        agent = {"subagent_type": "general-purpose", "description": "x",
                 "prompt": "Work in Memory/tasks/20260101-000000-t and write your report to "
                           "Memory/tasks/20260101-000000-t/agent-01.md."}
        denied = fire(dict(base, hook_event_name="PreToolUse", tool_name="Agent", tool_use_id="t1",
                           tool_input=agent))
        with open(os.path.join(task, "HANDOFF.md"), "w", encoding="utf-8") as f:
            f.write("# handoff\n" + "the next step is written here in full. " * 12)
        allowed = fire(dict(base, hook_event_name="PreToolUse", tool_name="Agent", tool_use_id="t2",
                            tool_input=agent))
        log = ""
        for p in (os.path.join(sdir, "dispatch_gate.log"),
                  os.path.join(repo, ".claude", "dispatch_gate.log")):
            if os.path.exists(p):
                log += open(p, encoding="utf-8").read()
    assert denied is not None, "the gate printed nothing for a relaxed-PACE dispatch. Log: %s" % log[-600:]
    dh = denied.get("hookSpecificOutput", {})
    assert dh.get("permissionDecision") == "deny" and "HANDOFF.md" in json.dumps(denied), denied
    assert "a PACE relaxed near the reset" in json.dumps(denied), (
        "the refusal names a bare GO instead of the relaxed band: %r" % denied)
    assert "DENY(handoff-missing)" in log, log[-600:]
    assert allowed is not None, log[-600:]
    assert allowed.get("hookSpecificOutput", {}).get("permissionDecision") != "deny", (
        "a relaxed-PACE dispatch WITH a current HANDOFF.md was refused: %r" % allowed)
    assert "GATE-ERROR" not in log, log[-600:]
    print("ok - at relaxed PACE the real hook refuses a dispatch without a HANDOFF.md, "
          "allows it with one")


def main():
    fresh_scratch()
    os.environ["CLAUDE_DISPATCH_DIR"] = os.path.join(fresh_scratch(), "state-dir-for-the-log")
    resume, gate = load()
    case_d3_stand_down_only_after_the_reset(resume)
    case_tool_path_arms_once_per_window(gate)
    case_notes_never_claim_a_missing_resume(gate)
    case_net_zone_refuses_a_dispatch_for_real()
    case_wall_hit(gate)
    case_relaxed_pace_arms_first(gate, resume)
    case_relaxed_pace_edges(gate)
    case_the_alarm_wakes_the_session(gate, resume)
    case_cowork_wake_checks_in_first(gate, resume)
    case_review_a_gaps(gate, resume)
    case_relaxed_pace_dispatch_needs_a_handoff_for_real()
    print("net zone OK")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
