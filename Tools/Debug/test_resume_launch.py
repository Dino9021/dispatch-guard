#!/usr/bin/env python3
"""A scheduled resume must be able to START, and must know whose record it is.

    python Tools/Debug/test_resume_launch.py

⛔ WHY. Measured 2026-09-28 on a Windows Server 2022 machine: every resume armed from 09-22 to
09-28 fired on time and never ran. The scheduler's line began with a bare `bash`, which was on
Claude Code's PATH but not on the PATH Task Scheduler uses, so each task failed with
0x80070002 before resume.py could log a word. And had it started, the line carried no
`--session`, so do_run() would have refused with `RUN-ABORT ... refusing to guess`. Eight
tasks, zero messages. The pins:

  1. the scheduler's line does not start with `bash` and names the record's session;
  2. that line ROUND-TRIPS: its own arguments, fed to main(), find the record (no RUN-ABORT);
  3. launch_probe passes the fixed line, FAILS a shim that exits 0 without reaching resume.py,
     and - where the registry PATH has no bash, as on the machine that lost the week - FAILS
     the old `bash` line;
  4. an arm whose probe fails is taken back down and ANNOUNCED (the auto-arm runs detached);
  5. --status translates Task Scheduler's 0x80070002 and flags an old-form line.

⚠ Nothing here registers a real task: every scheduler call is stubbed, and the probe runs
`--launch-check`, which changes nothing.
"""

import importlib.util
import io
import json
import os
import re
import sys
import time
import contextlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import fresh_scratch, repo_path, scratch_dir   # noqa: E402

SID = "aaaa1111-2222-3333-4444-555566667777"


class Result(object):
    def __init__(self, code, out=b"", err=b""):
        self.returncode, self.stdout, self.stderr = code, out, err


def load():
    sys.path.insert(0, repo_path("hooks"))
    spec = importlib.util.spec_from_file_location("dg_resume", repo_path("hooks", "resume.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    import shim
    return mod, shim


def case_line_names_the_session(mod):
    with scratch_dir("line") as sdir:
        line = mod.scheduled_line(sdir, "--run", SID)
    assert not line.lstrip().startswith("bash"), (
        "the scheduler's line starts with bash, which the OS scheduler may not find: %s" % line)
    assert "--session %s" % SID in line, "the scheduler's line names no session: %s" % line
    assert "--dir" in line, line
    # ⛔ THE CALLER'S STATE DIRECTORY, not whatever usage.state_dir() resolves: review 2 drove
    # do_arm(sdir=<scratch>) and it registered a task named for the REAL default directory.
    with scratch_dir("line-sdir") as sdir:
        cmd, _ = mod.schedule(time.localtime(time.time() + 3600), True, SID, sdir=sdir)
    assert mod.task_name(sdir, SID) in cmd and mod.dir8(sdir) in " ".join(cmd), (
        "schedule() did not use the state directory it was given: %s" % " ".join(cmd))
    print("ok - the scheduler's line is not `bash ...`, names the session and the caller's state dir")


def case_line_round_trips(mod):
    """The registered line's own arguments must find the record they were written for."""
    with scratch_dir("round-trip") as sdir:
        handoff = os.path.join(sdir, "HANDOFF.md")
        with open(handoff, "w", encoding="utf-8") as f:
            f.write("x" * 400)
        # armed for a reset that passed a minute ago; the heartbeat below is AFTER it, so the
        # found record stands down (ADR 20260929-152000 D3)
        mod.write_record(sdir, SID, {"task": sdir, "handoff": handoff, "session_id": SID,
                                     "at": time.time(), "armed_at": time.time() - 600,
                                     "armed_for_reset": time.time() - 60})
        # the arming session is live, so a found record stands down: no claude, no tokens
        alive = mod.dispatch_gate.state_path(sdir, SID, "alive")
        os.makedirs(os.path.dirname(alive), exist_ok=True)
        open(alive, "w").close()
        line = mod.scheduled_line(sdir, "--run", SID)
        argv = re.findall(r'"[^"]*"|\S+', line)
        argv = [a.strip('"') for a in argv[argv.index("resume.py") + 1:]]
        saved_run, mod.subprocess.run = mod.subprocess.run, lambda *a, **k: Result(1)
        saved_argv, here = sys.argv, os.getcwd()
        sys.argv = ["resume.py"] + argv
        os.chdir(sdir)
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                rc = mod.main()
        finally:
            os.chdir(here)
            sys.argv = saved_argv
            mod.subprocess.run = saved_run
        # log_line() writes <cwd>/.claude/dispatch_gate.log, and the cwd was sdir
        log = open(os.path.join(sdir, ".claude", "dispatch_gate.log"), encoding="utf-8").read()
    assert "RUN-ABORT" not in log, "the registered line did not find its record: %s" % log
    assert "RUN-SKIPPED" in log and rc == 0, "the round trip never reached do_run: %s" % log
    print("ok - the registered line's own arguments find the record it was armed for")


def _registry_path_has_bash():
    """Read the registry HERE, not through mod.scheduler_env(): a check that asks the function
    under test whether the function under test is right goes blind with it (mutation M4)."""
    if os.name != "nt":
        return None
    import winreg
    dirs = []
    for hive, key in ((winreg.HKEY_LOCAL_MACHINE,
                       r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                      (winreg.HKEY_CURRENT_USER, r"Environment")):
        try:
            with winreg.OpenKey(hive, key) as k:
                dirs += winreg.ExpandEnvironmentStrings(winreg.QueryValueEx(k, "Path")[0]).split(";")
        except OSError:
            continue
    if not dirs:
        return None
    return any(d and os.path.isfile(os.path.join(d, "bash.exe")) for d in dirs)


def case_probe(mod, shim):
    with scratch_dir("probe") as sdir:
        shim.write(sdir, repo_path())
        ok, detail = mod.launch_probe(sdir, SID)
        # ⚠ `claude` absent is a real answer on a machine without it - the launcher still worked.
        assert ok or "`claude` is not on the PATH" in detail, (
            "the fixed line did not reach resume.py under the scheduler's PATH: %s" % detail)
        assert mod.LAUNCH_MARK in detail, detail

        # ⛔ exit 0 WITHOUT the marker must FAIL: that is what both shims do on "no Python".
        name = shim.CMD if os.name == "nt" else shim.SH
        with open(os.path.join(sdir, name), "w", encoding="utf-8",
                  newline="\r\n" if os.name == "nt" else "\n") as f:
            f.write("@echo off\necho no working Python interpreter found\nexit /b 0\n"
                    if os.name == "nt" else "echo no working Python interpreter found\nexit 0\n")
        ok2, detail2 = mod.launch_probe(sdir, SID)
        assert ok2 is False, "a launcher that exits 0 without reaching resume.py passed: %s" % detail2

        # ⛔ THE INCIDENT ITSELF, where this machine can reproduce it.
        for p in shim.paths(sdir):                       # never clobbers a stranger, and skips
            os.remove(p)                                 # a rewrite run.sh says is current
        shim.write(sdir, repo_path())
        assert mod.launch_probe(sdir, SID)[0] is not False, "the real shim did not come back"
        if os.name == "nt":
            okh, dh = mod.launch_probe(sdir, SID, headless=True)
            print("  headless probe here: %s - %s" % (okh, dh[:80]))
            assert okh is not False or "did not reach" in dh, dh
        bash_there = _registry_path_has_bash()
        if bash_there is False:
            saved = shim.scheduled
            shim.scheduled = lambda d, script, *a, **k: shim.command(d, script, *a)
            try:
                ok3, detail3 = mod.launch_probe(sdir, SID)
            finally:
                shim.scheduled = saved
            assert ok3 is False, ("the old `bash` line PASSED the probe on a machine whose "
                                  "scheduler PATH has no bash - the probe is not using the "
                                  "scheduler's environment: %s" % detail3)
            print("ok - the probe passes the fixed line and fails the old bash line here")
        else:
            print("ok - the probe passes the fixed line; ⚠ the old-line half NOT exercised "
                  "(registry PATH %s)" % ("has bash" if bash_there else "unreadable / not Windows"))


def case_unlaunchable_arm_is_announced(mod):
    with scratch_dir("unlaunchable") as sdir:
        task = os.path.join(sdir, "Memory", "tasks", "20260101-000000-t")
        os.makedirs(task)
        with open(os.path.join(task, "HANDOFF.md"), "w", encoding="utf-8") as f:
            f.write("# handoff\n" + "the next step is written here in full. " * 12)
        saved = (mod.schedule, mod.launch_probe, mod.subprocess.run, mod.arming_session)
        mod.schedule = lambda when, dry, sid=None, headless=False, **k: (["schtasks"], Result(0))
        mod.launch_probe = lambda sdir_, sid_, env=None, headless=False: (False, "PROBE-SAID-NO")
        mod.subprocess.run = lambda *a, **k: Result(1)
        mod.arming_session = lambda sdir_, sid_: (SID, None)
        here = os.getcwd()
        os.chdir(sdir)
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out, \
                    contextlib.redirect_stderr(io.StringIO()):
                rc = mod.do_arm(["--arm", "--task", task, "--at", "03:00"], sdir, {})
        finally:
            os.chdir(here)
            mod.schedule, mod.launch_probe, mod.subprocess.run, mod.arming_session = saved
        assert rc == 1, "an arm the scheduler cannot start reported success: %s" % out.getvalue()
        assert not os.path.exists(mod.record_path(sdir, SID)), "its record was left armed"
        marker = mod.failed_path(sdir, SID)
        assert os.path.exists(marker), "nothing announces it - the auto-arm output is thrown away"
        assert "PROBE-SAID-NO" in json.load(open(marker, encoding="utf-8"))["why"]
    print("ok - an arm the scheduler cannot start is taken down and announced")

    if os.name != "nt":
        return
    # ⭐ HEADLESS FIRST, PLAIN AS THE FALLBACK: which one is registered follows the probe.
    # (probe says headless works?, scheduler accepts the headless line?, registrations, record)
    for headless_ok, reg_ok, want, final in ((True, True, [True], True),
                                             (False, True, [False], False),
                                             (True, False, [True, False], False)):
        with scratch_dir("headless-%s-%s" % (headless_ok, reg_ok)) as sdir:
            task = os.path.join(sdir, "Memory", "tasks", "20260101-000000-t")
            os.makedirs(task)
            with open(os.path.join(task, "HANDOFF.md"), "w", encoding="utf-8") as f:
                f.write("# handoff\n" + "the next step is written here in full. " * 12)
            got = []
            saved = (mod.schedule, mod.launch_probe, mod.subprocess.run, mod.arming_session)
            mod.schedule = lambda when, dry, sid=None, headless=False, **k: (
                got.append(headless), (["schtasks"], Result(0 if (reg_ok or not headless) else 1)))[1]
            mod.launch_probe = lambda sdir_, sid_, env=None, headless=False: (
                (headless_ok, "probe") if headless else (True, "probe"))
            mod.subprocess.run = lambda *a, **k: Result(1)
            mod.arming_session = lambda sdir_, sid_: (SID, None)
            here = os.getcwd()
            os.chdir(sdir)
            try:
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    rc = mod.do_arm(["--arm", "--task", task, "--at", "03:00"], sdir, {})
            finally:
                os.chdir(here)
                mod.schedule, mod.launch_probe, mod.subprocess.run, mod.arming_session = saved
            assert rc == 0 and got == want, (
                "headless probe %s, registration %s: registered %r, wanted %r"
                % (headless_ok, reg_ok, got, want))
            assert json.load(open(mod.record_path(sdir, SID), encoding="utf-8"))["headless"] is final
    print("ok - the headless line is registered when it launches, the plain one when it does not")


def case_status_reads_the_scheduler(mod):
    if os.name != "nt":
        print("ok - status read-back is Windows-only; not exercised here")
        return
    row = ('"HOST","\\X","N/A","Ready","Interactive only","9/27/2026 22:03:00","-2147024894",'
           '"HOST\\u","bash "C:/s/run.sh" resume.py --run --dir "C:/s"","N/A"\r\n')
    # ⛔ a comma in the state dir splits the unescaped Task To Run column (found by review)
    comma = ('"HOST","\\X","N/A","Ready","Interactive only","9/27/2026 22:03:00","-2147024894",'
             '"HOST\\u",""C:\\a,b\\run.cmd" resume.py --run --dir "C:/a,b" --session X","N/A"\r\n')
    saved = mod.subprocess.run
    try:
        mod.subprocess.run = lambda *a, **k: Result(0, row.encode("ascii"))
        line = mod.task_readback("C:/s", SID, {"session_id": SID})           # no launcher: old
        mod.subprocess.run = lambda *a, **k: Result(0, comma.encode("ascii"))
        line2 = mod.task_readback("C:/s", SID, {"session_id": SID, "launcher": mod.LAUNCHER})
    finally:
        mod.subprocess.run = saved
    assert "could NOT START" in line and "9/27/2026 22:03:00" in line, line
    assert "OLDER version" in line, "an alarm armed by an older version was not flagged: %s" % line
    assert "could NOT START" in line2 and "OLDER" not in line2, (
        "a current alarm was flagged as old (or its result lost) by a comma in the path: %s" % line2)
    print("ok - --status translates 0x80070002 and flags only an alarm an older version armed")


def case_upgrade_re_registers_old_alarms(mod):
    """An alarm armed by an older version and still ahead is registered again, once."""
    if os.name != "nt":
        print("ok - upgrade re-registration is Windows-only; not exercised here")
        return
    with scratch_dir("upgrade") as sdir:
        now = time.time()
        mod.write_record(sdir, "OLD", {"session_id": "OLD", "at": now + 3600})         # re-register
        mod.write_record(sdir, "NEW", {"session_id": "NEW", "at": now + 3600,
                                       "launcher": mod.LAUNCHER})                     # current
        mod.write_record(sdir, "PAST", {"session_id": "PAST", "at": now - 3600})      # fired
        mod.write_record(sdir, "GONE", {"session_id": "GONE", "at": now + 3600})      # task deleted
        calls = []
        saved = mod.schedule, mod._run
        mod.schedule = lambda when, dry, sid=None, **k: (calls.append(sid), (["x"], Result(0)))[1]
        mod._run = lambda cmd: not cmd[-1].endswith("-GONE")      # the scheduler holds all but GONE
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                n1 = mod.upgrade_records(sdir, now)
                n2 = mod.upgrade_records(sdir, now)
        finally:
            mod.schedule, mod._run = saved
        assert calls == ["OLD"], "re-registered the wrong alarms: %r" % calls
        assert (n1, n2) == (1, 0), "not exactly once: %r" % ((n1, n2),)
        assert json.load(open(mod.record_path(sdir, "OLD"), encoding="utf-8"))["launcher"] == mod.LAUNCHER
    print("ok - an alarm an older version armed is re-registered once, fired ones are left alone")


def case_missed_alarm_is_announced_once(mod):
    """An alarm whose time passed with no wake is announced once; a woken or future one is not."""
    with scratch_dir("missed") as sdir:
        now = time.time()
        mod.write_record(sdir, "MISSED", {"session_id": "MISSED", "task": "T-missed",
                                          "at": now - 3600})
        mod.write_record(sdir, "WOKE", {"session_id": "WOKE", "at": now - 3600,
                                        "woke_at": now - 3500})          # running or ran
        mod.write_record(sdir, "SOON", {"session_id": "SOON", "at": now - 60})   # inside grace
        mod.write_record(sdir, "AHEAD", {"session_id": "AHEAD", "at": now + 3600})
        with contextlib.redirect_stderr(io.StringIO()):
            n1 = mod.announce_missed(sdir, now)
            n2 = mod.announce_missed(sdir, now)
        markers = sorted(os.path.basename(p) for p in
                         __import__("glob").glob(os.path.join(sdir, "resume", "*.failed")))
        assert (n1, n2) == (1, 0), "not exactly once: %r" % ((n1, n2),)
        assert markers == ["MISSED.failed"], "wrong alarms announced: %r" % markers
        why = json.load(open(os.path.join(sdir, "resume", "MISSED.failed"), encoding="utf-8"))
        assert why["task"] == "T-missed" and "NEVER STARTED" in why["why"], why

        # ⛔ and do_run must mark the wake BEFORE it does anything long (claude -p can take hours)
        handoff = os.path.join(sdir, "HANDOFF.md")
        with open(handoff, "w", encoding="utf-8") as f:
            f.write("x" * 400)
        mod.write_record(sdir, "RUNNING", {"session_id": "RUNNING", "handoff": handoff,
                                           "task": sdir, "at": now - 3600,
                                           "armed_for_reset": now - 3780})
        seen = {}
        saved = mod.session_last_seen
        # the liveness read is do_run's FIRST decision; capture the record as it stands then,
        # and report activity after the reset so the run stands down (no claude, no tokens)
        mod.session_last_seen = lambda d, s: (
            seen.update(json.load(open(mod.record_path(d, "RUNNING"), encoding="utf-8"))), now)[1]
        saved_run = mod.subprocess.run
        mod.subprocess.run = lambda *a, **k: Result(1)
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                mod.do_run(sdir, {}, "RUNNING")
        finally:
            mod.session_last_seen, mod.subprocess.run = saved, saved_run
        assert (seen.get("woke_at") or 0) >= now - 3600, (
            "do_run had not recorded its wake when it started deciding - a long run would be "
            "announced as never started: %r" % seen)
    print("ok - a missed alarm is announced once; a woken, recent or future one is not")

    # ⭐ The prompt path reads only ITS OWN marker, leaving other sessions' for their session start.
    with scratch_dir("own-marker") as sdir:
        mod.announce_failure(sdir, "WHY-A", "SESSION-A", "T-A")
        mod.announce_failure(sdir, "WHY-B", "SESSION-B", "T-B")
        with contextlib.redirect_stderr(io.StringIO()):
            mine = mod.dispatch_gate.failed_resume_note(sdir, "SESSION-A")
        assert "WHY-A" in mine and "WHY-B" not in mine, mine
        assert os.path.exists(mod.failed_path(sdir, "SESSION-B")), "another session's marker was consumed"
        assert not os.path.exists(mod.failed_path(sdir, "SESSION-A")), "its own marker was not consumed"
        # ⛔ it runs on every prompt, so a malformed marker must not raise (that fails the hook open)
        with open(mod.failed_path(sdir, "SESSION-C"), "w", encoding="utf-8") as f:
            json.dump({"at": "not-a-time", "why": "WHY-C"}, f)
        got = mod.dispatch_gate.failed_resume_note(sdir, "SESSION-C")
        assert "WHY-C" in got, got
    print("ok - a session's prompt reads only its own failure marker, and a bad one cannot raise")


def main():
    fresh_scratch()
    os.environ["CLAUDE_DISPATCH_DIR"] = os.path.join(fresh_scratch(), "state-dir-for-the-log")
    mod, shim = load()
    case_line_names_the_session(mod)
    case_line_round_trips(mod)
    case_probe(mod, shim)
    case_unlaunchable_arm_is_announced(mod)
    case_status_reads_the_scheduler(mod)
    case_upgrade_re_registers_old_alarms(mod)
    case_missed_alarm_is_announced_once(mod)
    print("resume launch OK")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
