#!/usr/bin/env python3
"""do_cancel has three outcomes and used to have two. This pins all three.

⛔ WHY IT NEEDS A CHECK AT ALL. `schtasks /Delete` exits non-zero when it REFUSES and
equally when the task IS NOT THERE, and the correct handling is opposite in the two cases:
a job that is still registered must keep its record, a job that never existed must lose it.
Both wrong answers are silent, and both end with the gate telling the user something untrue
about whether work will be redone later.

⚠ The scheduler is never actually called: `subprocess.run` is replaced for the length of
each case. A test that registered real OS tasks would leave them behind.

    python Tools/Debug/test_resume_cancel.py

Standard library only, no framework, like everything else here.
"""

import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import fresh_scratch, repo_path, scratch_dir   # noqa: E402

HERE = repo_path()            # ⭐ the repository under test, not this folder


class Result(object):
    def __init__(self, code):
        self.returncode = code


def load_resume():
    sys.path.insert(0, repo_path("hooks"))
    spec = importlib.util.spec_from_file_location("dg_resume", repo_path("hooks", "resume.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def case(mod, name, codes, record=True):
    """Run do_cancel with schtasks answering `codes`. Returns (rc, record_still_there)."""
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        # /Query first, /Delete second - keyed by the flag so order cannot be assumed wrong
        return Result(codes["query"] if "/Query" in cmd else codes["delete"])

    with scratch_dir("cancel-" + name.replace(" ", "-").replace(",", "")) as sdir:
        if record:
            with open(os.path.join(sdir, "resume.json"), "w") as f:
                json.dump({"task": "x"}, f)
        saved, mod.subprocess.run = mod.subprocess.run, fake_run
        # ⛔ log_line() APPENDS TO `<cwd>/.claude/dispatch_gate.log`, so running this test
        # from the repository left RESUME lines - and a `.claude/` directory - in the working
        # tree on every run. It looked exactly like the plugin executing from the development
        # path, which is the one thing a person checking their install must be able to rule
        # out. ⇒ The whole case runs with the cwd inside its own temp directory.
        here = os.getcwd()
        os.chdir(sdir)
        try:
            rc = mod.do_cancel(sdir, quiet=True)
        finally:
            os.chdir(here)
            mod.subprocess.run = saved
        left = os.path.exists(os.path.join(sdir, "resume.json"))
    print("  %-28s rc=%d record_kept=%s" % (name, rc, left))
    return rc, left


def _tree_log():
    """The size of the repository's gate log, or None when it is absent.

    ⛔ THE QUESTION IS "DID I WRITE IT?", NOT "DOES IT EXIST?" - and the first version of this
    check asked the wrong one. `.claude/dispatch_gate.log` is where the plugin legitimately
    logs when a real session works in this repository, so asserting it is absent fails for a
    reason that has nothing to do with the test. Comparing before and after is the only form
    of the question that answers itself.
    """
    p = os.path.join(HERE, ".claude", "dispatch_gate.log")
    return os.path.getsize(p) if os.path.exists(p) else None


def case_chdir_never_raises():
    """⛔ A MISSING WORKING DIRECTORY MUST NOT SWALLOW THE WHOLE RESUME.

    `os.chdir` runs before every failure handler in do_run() - announce_failure, _rearm and
    do_cancel are all below it - so an unguarded call against a directory that no longer
    exists raises FileNotFoundError straight past them: exit 1, a traceback into the
    scheduler's void, no resume_failed.json, no retry, no cancellation. ⚠ The one mechanism
    whose entire purpose is to say "it failed at 03:40" is the one that does not run.
    Found by review 2026-09-01; this pins the guard.

    ⭐ The fallback ORDER is the point: the session's own cwd is where the work is, the task
    folder is where the handoff belongs, and the handoff's directory is the last resort.
    """
    import shutil
    import tempfile
    mod = load_resume()
    real_cwd = os.getcwd()
    live = tempfile.mkdtemp()
    gone = tempfile.mkdtemp()
    shutil.rmtree(gone)                      # recorded, then deleted before the alarm fires
    handoff_dir = tempfile.mkdtemp()
    handoff = os.path.join(handoff_dir, "HANDOFF.md")
    with open(handoff, "w", encoding="utf-8") as f:
        f.write("x")
    try:
        # 1. The recorded cwd is there: it wins, and nothing is logged as a fallback.
        got = mod._chdir_or_fall_back({"cwd": live, "task": handoff_dir}, handoff)
        assert os.path.samefile(got, live), (got, live)
        # 2. ⛔ The recorded cwd is GONE - the case that used to lose the resume. It must
        #    fall through to the task folder and RETURN, never raise.
        got = mod._chdir_or_fall_back({"cwd": gone, "task": handoff_dir}, handoff)
        assert os.path.samefile(got, handoff_dir), (got, handoff_dir)
        # 3. Everything recorded is gone: still no exception, and it says so.
        got = mod._chdir_or_fall_back({"cwd": gone, "task": gone}, os.path.join(gone, "H.md"))
        assert got is None, got
        # 4. Nothing recorded at all - a resume.json written before this shipped.
        got = mod._chdir_or_fall_back({}, handoff)
        assert os.path.samefile(got, handoff_dir), (got, handoff_dir)
    finally:
        os.chdir(real_cwd)
        shutil.rmtree(live, ignore_errors=True)
        shutil.rmtree(handoff_dir, ignore_errors=True)
    # ⛔ AND THE GUARD MUST BE THE ONLY WAY IN. The cases above drive the helper
    # DIRECTLY, so they stay green even if do_run() stops calling it - which is exactly how
    # this repository once shipped a decision function that was right while nothing invoked
    # it. ⇒ Assert the wiring structurally: one `os.chdir(` in the whole module, inside the
    # guard. ⚠ A second one anywhere else is a path that can still raise past every failure
    # handler.
    src = open(repo_path("hooks", "resume.py"), encoding="utf-8").read()
    calls = [l.strip() for l in src.splitlines()
             if "os.chdir(" in l and not l.strip().startswith("#")]
    assert calls == ["os.chdir(target)"], (
        "os.chdir must appear once, inside _chdir_or_fall_back - found %r" % (calls,))
    print("ok - a missing working directory falls back instead of losing the resume")


def case_log_reaches_the_state_dir():
    """⛔ A RESUME LINE MUST LAND WHERE SOMEBODY CAN FIND IT.

    `log_line()` writes to `<cwd>/.claude/dispatch_gate.log`, and `cwd` for a resume is
    wherever the scheduler happened to start it. The gate's own logger was given a second,
    unmovable destination in the state directory in 0.52.1; resume.py's was missed, so every
    ARMED and RESUME line was unfindable in the one place the rest of the record lives.
    Found by review 2026-09-01.

    ⚠ It writes to BOTH, not to the first that works. A copy that only appears when the other
    fails is not an audit trail.
    """
    import shutil
    import tempfile
    mod = load_resume()
    sdir = tempfile.mkdtemp()
    cwd = tempfile.mkdtemp()
    real_state, real_cwd = mod.usage.state_dir, os.getcwd()
    try:
        mod.usage.state_dir = lambda argv=None, _d=sdir: _d
        os.chdir(cwd)
        mod.log_line("PROBE-both-destinations")
    finally:
        mod.usage.state_dir = real_state
        os.chdir(real_cwd)
    # ⚠ READ DEFENSIVELY. The first version opened the file directly, so the failure it
    # produced was a FileNotFoundError traceback rather than a sentence - and a check whose
    # failure has to be decoded is one somebody misreads. Measured while mutation-checking
    # this very case: the mutation WAS caught and the grep looking for `AssertionError`
    # missed it.
    def _body(path):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    for where, path in (("state dir", os.path.join(sdir, "dispatch_gate.log")),
                        ("cwd", os.path.join(cwd, ".claude", "dispatch_gate.log"))):
        assert "PROBE-both-destinations" in _body(path), (
            "the resume log never reached the %s (%s) - it writes to the first destination "
            "that works instead of to both" % (where, path))
    shutil.rmtree(sdir, ignore_errors=True)
    shutil.rmtree(cwd, ignore_errors=True)
    print("ok - a resume line reaches the state directory as well as the working tree")


def case_arms_against_the_blocking_window():
    """⛔ THE RESUME MUST WAIT FOR THE WINDOW THAT IS ACTUALLY BLOCKING.

    It read `five_hour.resets_at` and nothing else, which was harmless while the brake could
    only ever STOP on the five-hour window. The moment it learned to STOP on the seven-day
    one, that became a trap: wrap up, arm against the FIVE-hour reset, wake three minutes
    later, still be at STOP because the WEEK is what is spent, retry every twenty minutes for
    two hours, announce failure. A scheduled resume that cannot succeed is worse than none -
    it looks armed the whole time.

    ⚠ AND THE RULE IS NOT "whichever resets later" either. The question is which window is
    BLOCKING, and verdict() already answers it. ⛔ Until 2026-09-01 a 7d window that reset
    before the current 5h window ended was dismissed as "not a constraint, its percentage is
    about to become zero" - and that was wrong whenever its HEADROOM ran out first. See
    _seven_day_binds() and Memory/notes/MEASURED-5h-and-7d-are-independent.md.
    """
    import json
    import time
    mod = load_resume()
    import usage
    now = time.time()
    r5, r7 = now + 2 * 3600, now + 3 * 86400

    def armed_for(p5, p7, seven_resets):
        with scratch_dir("arm-target-%d-%d" % (p5, p7)) as sdir:
            cfg = dict(usage.config(sdir))
            with open(cfg["token_usage_file"], "w", encoding="utf-8") as f:
                json.dump({"ts": int(now * 1000),
                           "five_hour": {"used_percentage": p5, "resets_at": int(r5)},
                           "seven_day": {"used_percentage": p7,
                                         "resets_at": int(seven_resets)}}, f)
            return mod.reset_time(sdir, cfg)

    when, which = armed_for(90, 10, r7)
    assert which == "5h" and abs(when - r5) < 2, (when, which)
    # ⭐ THE CASE THE FIX EXISTS FOR: the week is spent, the five hours are empty.
    when, which = armed_for(0, 99, r7)
    assert which == "7d" and abs(when - r7) < 2, (
        "the resume would wake at the 5h reset and find itself still blocked: %r"
        % ((when, which),))
    # ⛔ REVERSED 2026-09-01, and the old expectation cost the owner ninety minutes. A 7d
    # window that resets FIRST used to be dismissed as "not a constraint", so the resume was
    # armed for the five-hour reset two hours out - while the thing actually blocking the
    # work cleared in thirty minutes. ⚠ The blocker is the 7d at 99%; the moment it lifts is
    # the moment to wake. See _seven_day_binds() for the measurement that removed the rule.
    when, which = armed_for(0, 99, now + 1800)
    assert which == "7d" and abs(when - (now + 1800)) < 2, (
        "the resume slept through the reset that actually unblocked it: %r" % ((when, which),))
    # Nothing blocking at all still answers with the near window, so arming early works.
    when, which = armed_for(10, 10, r7)
    assert which == "5h" and abs(when - r5) < 2, (when, which)
    print("ok - the resume waits for the window that is actually blocking")


def main():
    fresh_scratch()
    before = _tree_log()
    mod = load_resume()
    if os.name != "nt":
        print("skipped - the three-way split is the Windows path; POSIX cannot ask `at`")
        return

    # Nothing registered. The record is an ORPHAN and this is the documented repair for it,
    # so it must be cleared and the caller must hear "nothing left to fire".
    rc, left = case(mod, "not registered", {"query": 1, "delete": 1})
    assert rc == 0 and not left, "an orphan record survived the command named to clear it"

    # Registered and deleted. The ordinary path.
    rc, left = case(mod, "registered, deleted", {"query": 0, "delete": 0})
    assert rc == 0 and not left, "a successful cancel left its record behind"

    # ⛔ Registered and REFUSED. The job will still fire, so the record must stay and the
    # caller must NOT be told that nothing will wake later.
    rc, left = case(mod, "registered, delete refused", {"query": 0, "delete": 1})
    assert rc == 1 and left, "a refused delete was reported as a cancellation"

    # ⛔ AND IT MUST LEAVE THE WORKING TREE ALONE. `log_line()` appends to
    # `<cwd>/.claude/dispatch_gate.log`, and this test used to run with the repository as its
    # working directory - so every run left the plugin's own log there, which is
    # indistinguishable from the development copy being executed by a real session.
    assert _tree_log() == before, (
        "the test changed %s/.claude/dispatch_gate.log (%r -> %r)"
        % (HERE, before, _tree_log()))
    case_arms_against_the_blocking_window()
    case_log_reaches_the_state_dir()
    case_chdir_never_raises()
    print("ok - not-there, deleted and refused are three different answers")


if __name__ == "__main__":
    main()
