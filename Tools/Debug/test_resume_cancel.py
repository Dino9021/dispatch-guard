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
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import fresh_scratch, repo_path, scratch_dir   # noqa: E402

HERE = repo_path()            # ⭐ the repository under test, not this folder
SID = "SID-under-test"        # every case names its own session; records are per-session


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
        # ⭐ One record per session since 0.60, under `<sdir>/resume/`.
        if record:
            mod.write_record(sdir, SID, {"task": "x", "session_id": SID})
        saved, mod.subprocess.run = mod.subprocess.run, fake_run
        # ⛔ log_line() APPENDS TO `<cwd>/.claude/dispatch_gate.log`, so running this test
        # from the repository left RESUME lines - and a `.claude/` directory - in the working
        # tree on every run. It looked exactly like the plugin executing from the development
        # path, which is the one thing a person checking their install must be able to rule
        # out. ⇒ The whole case runs with the cwd inside its own temp directory.
        here = os.getcwd()
        os.chdir(sdir)
        try:
            rc = mod.do_cancel(sdir, quiet=True, session_id=SID)
        finally:
            os.chdir(here)
            mod.subprocess.run = saved
        left = os.path.exists(mod.record_path(sdir, SID))
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
    # ⛔ A RELAXED 7d STOP MUST ARM FOR THE 7d RESET (0.59.0). 7d 98% within half an hour of its
    # reset RELAXES to GO, so the combined verdict word is GO and `driver` is None - but the
    # window that can still hit the cap is the 7d one, in thirty minutes, not the 5h one two
    # hours out. reset_time reads `relaxed_driver` for exactly this. Without it the resume wakes
    # at the 5h reset and finds the 7d still the blocker - the failure this whole case guards.
    when, which = armed_for(0, 98, now + 1800)
    assert which == "7d" and abs(when - (now + 1800)) < 2, (
        "a relaxed 7d STOP armed for the wrong (5h) reset: %r" % ((when, which),))
    # Nothing blocking at all still answers with the near window, so arming early works.
    when, which = armed_for(10, 10, r7)
    assert which == "5h" and abs(when - r5) < 2, (when, which)
    print("ok - the resume waits for the window that is actually blocking")


def case_posix_cancels_one_job_not_all():
    """⛔ A PLAIN CANCEL MUST NOT RUN `atrm -a` - IT DELETES JOBS THIS PLUGIN NEVER CREATED.

    `at` has no named jobs, so "cancel the resume" was implemented as "remove EVERY `at` job
    this user has", on every automatic stand-down and not only when somebody asked for it.
    A person with a backup or a batch job scheduled lost it to a resume being tidied up.
    ⇒ The job NUMBER is recorded at arm time and only that job is removed. ADR
    20260917-132015, D7.

    ⚠ THIS RUNS ON WINDOWS, by replacing `os.name` inside the module under test. The real
    `at` is never called on either platform - there is none on this machine (ADR A1) - so
    what is pinned is the DECISION (which command, and which of the three outcomes), never
    that `at` behaves as documented.

    ⛔ AND THE NO-NUMBER CASE IS THE REFUSED OUTCOME, not the deleted one. An alarm armed
    before the number was recorded cannot be named, so claiming it is gone would be the one
    lie do_cancel's three outcomes exist to prevent: the record stays and the caller hears
    that something may still fire.
    """
    mod = load_resume()

    def run_posix(record, all_jobs):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(list(cmd))
            return Result(0)

        with scratch_dir("posix-%s-%s" % (record.get("at_job"), all_jobs)) as sdir:
            mod.write_record(sdir, SID, record)
            saved_run, mod.subprocess.run = mod.subprocess.run, fake_run
            saved_name, mod.os.name = mod.os.name, "posix"
            here = os.getcwd()
            os.chdir(sdir)
            try:
                rc = mod.do_cancel(sdir, quiet=True, all_jobs=all_jobs, session_id=SID)
            finally:
                os.chdir(here)
                mod.os.name = saved_name
                mod.subprocess.run = saved_run
            left = os.path.exists(mod.record_path(sdir, SID))
        return rc, left, calls

    # 1. A recorded job number: exactly that job goes, and `-a` is never passed.
    rc, left, calls = run_posix({"task": "x", "at_job": "42"}, False)
    assert calls == [["atrm", "42"]], (
        "a plain cancel must remove ONE job by number - it ran %r" % (calls,))
    assert rc == 0 and not left, (rc, left)

    # 2. ⛔ No recorded number: nothing is removed, the record STAYS, and the caller is told
    #    something may still fire.
    rc, left, calls = run_posix({"task": "x"}, False)
    assert calls == [], "an alarm with no job number was cancelled by guesswork: %r" % (calls,)
    assert rc == 1 and left, (
        "an uncancellable alarm was reported as cancelled (rc=%r, record_kept=%r)" % (rc, left))

    # 3. `--all` is the blunt instrument, and it is the ONLY way to reach it.
    rc, left, calls = run_posix({"task": "x"}, True)
    assert calls == [["atrm", "-a"]], calls
    assert rc == 0 and not left, (rc, left)

    # 4. The number is read from either stream, and its absence is not an error.
    class R(object):
        def __init__(self, out=b"", err=b""):
            self.stdout, self.stderr = out, err

    assert mod.at_job_id(R(err=b"job 7 at Wed Sep 17 18:30:00 2026")) == "7"
    assert mod.at_job_id(R(out="job 1234 at Thu Sep 18 09:00:00 2026")) == "1234"
    assert mod.at_job_id(R(err=b"warning: commands will be executed using /bin/sh")) is None
    assert mod.at_job_id(None) is None
    print("ok - a plain POSIX cancel removes ONE job; `atrm -a` needs --all")


def case_only_the_owner_session_stands_a_resume_down():
    """⛔ ANOTHER SESSION BEING ALIVE MUST NOT STOP THIS RESUME FIRING.

    Until 0.60 do_run() asked `session_alive_minutes(sdir)` - ANY session - and cancelled
    itself if one had been active in the last 30 minutes. On a machine running several
    sessions that is always true, so NONE of the parallel resumes ever ran: the records and
    the task names were per session and the firing was not. Worse, the headless `claude -p`
    a resume spawns is itself a session, so one running resume vetoed every other for up to
    its three-hour timeout.

    ⇒ The question is now "is the session that armed ME awake?". ADR 20260917-132015, D5.

    ⚠ This drives the decision through `session_alive_minutes`, which is where do_run() reads
    it, and ALSO pins the call shape - a `session_alive_minutes(sdir)` anywhere in do_run is
    the old behaviour returning. Measured on this change: matching the flag name alone let a
    mutation survive in a comment, so the assertion is on the CALL.
    """
    mod = load_resume()
    with scratch_dir("owner-standdown") as sdir:
        state = os.path.join(sdir, "state")
        os.makedirs(state, exist_ok=True)
        now = time.time()

        def mark(sid, minutes_ago):
            p = mod.dispatch_gate.state_path(sdir, sid, "alive")
            with open(p, "w") as f:
                f.write("x")
            os.utime(p, (now - minutes_ago * 60, now - minutes_ago * 60))

        # A is at the keyboard right now. B armed a resume and then died.
        mark("SESSION-A", 0)
        mark("SESSION-B", 999)
        assert mod.session_alive_minutes(sdir, "SESSION-B") > mod.ALIVE_WITHIN_MIN, (
            "B must read as dead for this case to mean anything")
        assert mod.session_alive_minutes(sdir, "SESSION-A") < mod.ALIVE_WITHIN_MIN
        # ⛔ The old machine-wide question answers "somebody is awake" - which is exactly
        # the answer that used to cancel B's resume.
        assert mod.session_alive_minutes(sdir) < mod.ALIVE_WITHIN_MIN, (
            "the any-session form no longer reports A - this case would pass vacuously")

    # ⛔ AND do_run MUST ASK THE NARROW ONE. A bare `session_alive_minutes(sdir)` in that
    # function is the old behaviour, whatever the comments around it say.
    src = open(repo_path("hooks", "resume.py"), encoding="utf-8").read()
    body = src[src.index("def do_run"):]
    body = body[:body.index("\ndef ", 1)]
    # ⛔ CODE ONLY. The comments in do_run QUOTE the old call while explaining why it went,
    # so a plain substring search over the whole body reports the defect it is looking for.
    # Measured on this very change: the first version of this assertion failed against
    # correct code. A check that matches prose is not checking the code.
    code = "\n".join(l for l in body.splitlines() if not l.strip().startswith("#"))
    assert "session_alive_minutes(sdir)" not in code, (
        "do_run stands down on ANY live session again - on a machine with one session open, "
        "no parallel resume will ever fire")
    assert "session_alive_minutes(sdir, my_sid)" in code, (
        "do_run does not ask about the session that armed the resume")
    assert "usage._user_activity_min()" not in code, (
        "the machine-wide keyboard signal is back in do_run; it reports every session too, "
        "including the headless run a resume spawns")
    print("ok - only the arming session's own liveness stands its resume down")


def case_a_takeover_line_stands_the_resume_down():
    """⛔ WORK PICKED UP IN ANOTHER SESSION MUST NOT BE REDONE AT 03:40.

    A session dies mid-task with a resume armed. Somebody continues it in a DIFFERENT session
    - the normal shape, since the session that armed the alarm is the one that died - and the
    alarm then fires and spends a fresh window producing a duplicate. The successor says so in
    the handoff, which is the file do_run reads anyway. ADR 20260917-132015, D4.

    ⛔ EVERY AMBIGUOUS CASE MUST RUN. "The resume IS the guarantee": redoing work wastes a
    window, refusing to run loses it entirely, so only a well-formed line NEWER than the arm
    may stand a resume down.

    ⚠ THE IMPOSSIBLE-DATE CASE IS NOT DECORATION. The first version used `time.mktime`, which
    NORMALISES out-of-range fields instead of rejecting them: `2026-13-45T99:99` came back as
    a valid moment in 2027, so one typo in a handoff would have stood that resume down for
    ever. Measured here; the parser uses `datetime`, which raises.
    """
    import tempfile
    mod = load_resume()
    armed = time.mktime((2026, 9, 18, 10, 0, 0, 0, 0, -1))

    def stands_down(body):
        p = os.path.join(tempfile.mkdtemp(), "HANDOFF.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
        return mod.taken_over_since(p, armed) is not None

    base = "# HANDOFF\nGoal: x\n"
    for body, why in (
            (base, "no takeover line"),
            (base + "TAKEN OVER 2026-09-18T09:30 by x\n", "a takeover OLDER than the arm - a "
             "stale line from a previous cycle must not suppress every future resume"),
            (base + "TAKEN OVER by x, this morning\n", "no timestamp"),
            (base + "TAKEN OVER 2026-13-45T99:99 by x\n", "an impossible date"),
            ("we discussed taking over the module\n", "prose that merely mentions taking over"),
    ):
        assert not stands_down(body), "the resume refused to run on %s" % why
    for body, why in (
            (base + "TAKEN OVER 2026-09-18T11:30 by domain-42\n", "ISO with T"),
            (base + "TAKEN OVER 2026-09-18 11:30 by domain-42\n", "a space instead of T"),
            (base + "taken over 2026-09-18T11:30 by x\n", "lower case"),
            (base + "TAKEN OVER 2026-13-45T99:99 by x\nTAKEN OVER 2026-09-18T11:30 by y\n",
             "a bad line followed by a good one"),
    ):
        assert stands_down(body), "a real takeover (%s) did not stand the resume down" % why

    # ⛔ With no `armed_at` recorded there is nothing to compare against - run.
    p = os.path.join(tempfile.mkdtemp(), "HANDOFF.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(base + "TAKEN OVER 2026-09-18T11:30 by x\n")
    assert mod.taken_over_since(p, None) is None, (
        "a record with no armed_at stood its resume down on an uncomparable line")

    # ⛔ AND do_run MUST ACTUALLY CONSULT IT. The cases above drive the parser directly and
    # stay green while nothing calls it - the shape this repository has shipped before.
    src = open(repo_path("hooks", "resume.py"), encoding="utf-8").read()
    body = src[src.index("def do_run"):]
    body = body[:body.index("\ndef ", 1)]
    code = "\n".join(l for l in body.splitlines() if not l.strip().startswith("#"))
    assert "taken_over_since(" in code, (
        "do_run never asks whether the work was taken over, so the handoff line does nothing")
    print("ok - a fresh takeover line stands the resume down; everything ambiguous runs")


def case_a_handoff_must_say_who_wrote_it():
    """⛔ A HANDOFF THAT NAMES NOBODY CANNOT PASS A NAME ON.

    The resume wakes a FRESH session with a new id, and do_run tells it to keep whatever name
    the handoff gives it. With no name there is nothing to keep, and a fleet that identifies
    its members by session id loses one and gains a stranger.

    ⚠ WARNING, NOT REFUSAL - like every other entry here. Failing to arm removes the resume
    entirely, and a handoff with no name is still worth far more than no resume at all.

    ⭐ Either form satisfies it: a session id, which is what a machine matches on, or a stated
    role, which is what a person reads. ⚠ Both are checked, because a rule that only accepted
    the machine form would push people to paste a UUID and call it identity.
    """
    import tempfile
    mod = load_resume()

    def warned(text):
        p = os.path.join(tempfile.mkdtemp(), "HANDOFF.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return any("WHO this session" in w for w in mod.handoff_warnings(p))

    base = "Goal: x. Next step: run `python a/b.py`. Path: C:/x/y.md\n"
    assert warned(base), "a handoff naming nobody was not warned about"
    for named in ("Session id: `ba6b78ef`\n", "Role: domain-42\n", "我是 domain-42\n",
                  "ba6b78ef-89ab-4392\n"):
        assert not warned(base + named), (
            "a handoff that DOES name its session was warned about anyway: %r" % named)

    # ⛔ AND THE GATE'S OWN GENERATED HANDOFF MUST PASS ITS OWN RULE. It is written when a
    # session never wrote one, which is exactly the run most likely to be resumed.
    gate_src = open(repo_path("hooks", "dispatch_gate.py"), encoding="utf-8").read()
    assert "Session id:" in gate_src, (
        "generated_handoff no longer names the session, so the handoff the GATE writes "
        "would fail the rule the gate enforces")
    print("ok - a handoff that names nobody is warned about; either form satisfies it")


def case_the_woken_run_is_told_it_is_a_continuation():
    """⛔ THE RESUME STARTS A NEW SESSION, AND SILENCE ABOUT THAT COSTS AN IDENTITY.

    `do_run` spawns a FRESH `claude -p` - deliberately, because `--resume <id>` re-sends the
    whole transcript (measured: 35,356 tokens for 0.37 MB, zero cache read; one real
    transcript was 239 MB). So the woken run ALWAYS has a different session id. That is
    invisible on a single task and expensive when several sessions collaborate: a fleet that
    identifies its members by session id sees one member vanish and a stranger appear.

    ⭐ The id cannot be preserved. The NAME can - so both prompts hand the successor its
    predecessor's id and tell it to keep whatever name the handoff gives it.
    ⚠ This pins the SENTENCE, not the outcome. Whether a model obeys a prompt is not
    something a check can assert; what it can assert is that the instruction is still there.
    """
    mod = load_resume()
    src = open(repo_path("hooks", "resume.py"), encoding="utf-8").read()
    body = src[src.index("def do_run"):]
    body = body[:body.index("\ndef ", 1)]
    code = "\n".join(l for l in body.splitlines() if not l.strip().startswith("#"))
    assert "identity = (" in code, "the continuation notice is gone from do_run"
    # ⛔ BOTH prompts, and this is the half that rots: the reconstruction branch is the one
    # nobody exercises by hand, so an edit that drops it there is invisible.
    used = code.count("identity")
    assert used >= 3, (
        "the continuation notice is built but reaches %d prompt(s) - it must reach BOTH the "
        "handoff prompt and the reconstruction prompt" % (used - 1))
    # ⚠ And it must carry the predecessor, or it says nothing a successor can act on.
    assert 'state.get("session_id")' in code, (
        "the notice does not name the session that armed the work")
    print("ok - a woken run is told whose continuation it is")


def case_reaper_takes_only_spent_records():
    """⛔ ONE OS TASK PER SESSION IS ALSO HOW A MACHINE COLLECTS HUNDREDS OF THEM.

    The reaper removes a record, and the task behind it, once the alarm has fired and the
    scheduler no longer holds the job. ADR 20260917-132015, D6.

    ⛔ AND WHAT IT MUST NOT TAKE IS THE POINT:
      - a FUTURE alarm - somebody's armed resume;
      - one still inside its retry window - a resume that is mid-retry would be swept out
        from under itself;
      - a per-session `.failed` marker - those have no alarm time and no task, so a sweep
        that matched "everything with no task" would delete exactly the announcements the
        owner is meant to read in the morning.
    """
    mod = load_resume()
    with scratch_dir("reaper") as sdir:
        now = time.time()
        window = mod.rcfg(sdir)["retry_window_min"] * 60
        # Nothing is registered with the scheduler in this directory, so "no task" is true
        # for all of them - the ages are what separates them.
        mod.write_record(sdir, "SPENT", {"session_id": "SPENT", "at": now - window - 60})
        mod.write_record(sdir, "FUTURE", {"session_id": "FUTURE", "at": now + 3600})
        mod.write_record(sdir, "RETRYING", {"session_id": "RETRYING", "at": now - 60})
        failed = os.path.join(sdir, mod.RESUME_DIR, "SOMEBODY.failed")
        with open(failed, "w", encoding="utf-8") as f:
            json.dump({"at": now - window - 999, "why": "it failed at 03:40"}, f)

        here = os.getcwd()
        os.chdir(sdir)
        try:
            removed = mod.reap_records(sdir)
        finally:
            os.chdir(here)

        left = sorted(os.path.basename(p) for p in mod.record_paths(sdir))
        assert removed == 1, "the reaper took %d records, expected 1: %r" % (removed, left)
        assert left == ["FUTURE.json", "RETRYING.json"], left
        assert os.path.exists(failed), (
            "the reaper deleted a failure announcement - the owner would never see that the "
            "resume gave up overnight")
    print("ok - the reaper takes spent records only, and leaves .failed markers alone")


def case_two_failures_produce_two_announcements():
    """⛔ TWO RESUMES FAILING OVERNIGHT MUST NOT LEAVE ONE MESSAGE.

    There was a single `resume_failed.json`: the second failure overwrote the first, and the
    gate's reader deleted the file after announcing it. The owner heard about one failure and
    never learnt of the other. The message also named neither the session nor the task, so
    even the survivor did not say WHICH work had stopped. ADR 20260917-132015, D9.

    ⚠ The legacy single file is still read, so upgrading does not swallow a marker the
    previous version wrote.
    """
    import importlib.util as _il
    mod = load_resume()
    spec = _il.spec_from_file_location("dg_gate_d9", repo_path("hooks", "dispatch_gate.py"))
    gate = _il.module_from_spec(spec)
    spec.loader.exec_module(gate)

    with scratch_dir("two-failures") as sdir:
        here = os.getcwd()
        os.chdir(sdir)
        try:
            # ⚠ REALISTIC IDS. The note truncates a session id to 8 characters, the same
            # prefix the gate log uses, so two ids that share their first 8 would be
            # indistinguishable on screen - and a check using such a pair measures nothing.
            # A real session id is a UUID.
            mod.announce_failure(sdir, "the window never reopened",
                                 "aaaa1111-0000-4000-8000-000000000001", "task-A")
            mod.announce_failure(sdir, "claude was not on PATH",
                                 "bbbb2222-0000-4000-8000-000000000002", "task-B")
        finally:
            os.chdir(here)
        # A marker written by the previous version, with no session and no task.
        with open(os.path.join(sdir, "resume_failed.json"), "w", encoding="utf-8") as f:
            json.dump({"at": 1, "why": "an older version gave up"}, f)

        note = gate.failed_resume_note(sdir)
        for want in ("the window never reopened", "claude was not on PATH",
                     "an older version gave up", "task-A", "task-B",
                     "aaaa1111", "bbbb2222"):
            assert want in note, (
                "the morning announcement lost %r - a failure the owner never hears about "
                "is the same as no resume at all:\n%s" % (want, note))
        # ⭐ Consumed exactly once: a second call must be silent.
        assert gate.failed_resume_note(sdir) == "", "a failure was announced twice"
    print("ok - every failed resume is announced, and each names its own task")


def case_upgrade_keeps_an_armed_alarm():
    """⛔ AN UPGRADE MUST NOT LOSE A RESUME THAT IS ALREADY ARMED.

    0.60 renamed BOTH the record and the OS task. Without a migration, upgrading while a
    resume was armed leaves a task the plugin can no longer name and a record it no longer
    reads: the alarm fires, finds nothing, and the guarantee is gone with no message.
    ADR 20260917-132015, D8.

    ⛔ AND IT NEVER INVENTS A NAME. A pre-0.60 record without a `session_id` is LEFT WHERE
    IT IS and reported by --status. Renaming somebody's armed alarm to a guess is worse
    than telling them it is theirs to clear.
    """
    mod = load_resume()
    with scratch_dir("migrate-named") as sdir:
        with open(os.path.join(sdir, "resume.json"), "w", encoding="utf-8") as f:
            json.dump({"task": "T", "session_id": "OLD-SESSION", "at": 1}, f)
        here = os.getcwd()
        os.chdir(sdir)
        try:
            mod.migrate_legacy(sdir)
        finally:
            os.chdir(here)
        assert not os.path.exists(os.path.join(sdir, "resume.json")), \
            "the legacy record was left behind as well as copied"
        moved = mod.record_path(sdir, "OLD-SESSION")
        assert os.path.exists(moved), "an armed alarm was lost by the upgrade"
        assert json.load(open(moved, encoding="utf-8"))["task"] == "T"

    with scratch_dir("migrate-unnamed") as sdir:
        with open(os.path.join(sdir, "resume.json"), "w", encoding="utf-8") as f:
            json.dump({"task": "T", "at": 1}, f)
        here = os.getcwd()
        os.chdir(sdir)
        try:
            out = mod.migrate_legacy(sdir)
        finally:
            os.chdir(here)
        assert out == "unnamed", out
        assert os.path.exists(os.path.join(sdir, "resume.json")), \
            "a record that could not be named was removed anyway"
        assert not mod.record_paths(sdir), "an unnamed record was renamed to a guess"
    print("ok - an upgrade keeps an armed alarm, and never invents a name for one")


def case_the_arming_session_is_told_not_guessed():
    """⛔ THE RECORD MUST BE KEYED BY THE SESSION THAT ARMED, NOT BY THE NEWEST ONE.

    `arming_session()` had no way to be told: it took the FILENAME of the newest
    `state/*.alive` and called that the arming session. Its own docstring admits the guess
    picks the wrong id when two sessions are live - and two sessions live is exactly the
    case a per-session resume exists for, so every automatic arm was keyed by a coin toss in
    the one situation that matters. The gate holds the id on the payload that decided to
    arm; it now passes it. ADR 20260917-132015, D12 ⟨round 2, I-B1⟩.

    ⚠ The guess is NOT removed - a `resume.py --arm` run by hand has nothing to be told -
    so both branches are pinned here.
    """
    import time
    mod = load_resume()
    with scratch_dir("arming-session") as sdir:
        state = os.path.join(sdir, "state")
        os.makedirs(state, exist_ok=True)
        # Two live sessions. OLDER is the one that "armed"; NEWER is the decoy the guess
        # would pick.
        for name, age in (("SID-OLDER", 60), ("SID-NEWER", 1)):
            p = os.path.join(state, name + ".alive")
            with open(p, "w") as f:
                f.write("x")
            os.utime(p, (time.time() - age, time.time() - age))

        told, _ = mod.arming_session(sdir, "SID-OLDER")
        assert told == "SID-OLDER", (
            "the id the gate passed was ignored and the newest .alive was used instead: %r"
            % (told,))
        guessed, _ = mod.arming_session(sdir)
        assert guessed == "SID-NEWER", (
            "the hand-run fallback stopped picking the newest .alive: %r" % (guessed,))

    # ⛔ AND BOTH ENDS OF THE WIRE MUST BE PINNED, because the cases above drive
    # `arming_session` DIRECTLY and stay green while nothing passes it anything. Measured
    # while mutation-checking this very case: deleting the argument from do_arm's call left
    # all seven checks passing. ⚠ A decision function that is right while nothing invokes it
    # is a shape this repository has shipped before - see case_chdir_never_raises.
    def body(path, marker):
        src = open(repo_path(*path), encoding="utf-8").read()
        cut = src[src.index(marker):]
        return cut[:cut.index("\ndef ", 1)]

    # ⚠ THE ASSERTION IS ON THE CALL SHAPE, NOT ON THE FLAG NAME - measured: the first
    # version looked for "--session" anywhere in do_arm, and the flag also appears in a
    # COMMENT there, so deleting the argument from the call left the check green. A check
    # that matches prose is not checking the code.
    arm = body(("hooks", "resume.py"), "def do_arm")
    assert "arming_session(sdir)" not in arm, (
        "do_arm calls arming_session with no session id, so every automatic arm is keyed by "
        "the newest-.alive guess no matter what the gate passes")
    assert "--session" in arm, "do_arm never reads --session"
    spawn = body(("hooks", "dispatch_gate.py"), "def maybe_auto_arm")
    assert '"--session"' in spawn, (
        "maybe_auto_arm spawns the armer without --session, so do_arm falls back to the "
        "newest-.alive guess for every automatic arm")
    print("ok - the arming session is passed in; the newest-.alive guess is the fallback")


def case_scheduled_command_names_its_state_dir():
    """⛔ THE ALARM MUST FIRE AGAINST THE DIRECTORY IT WAS ARMED IN.

    The scheduler starts `resume.py --run` with no arguments of its own, so `state_dir()` at
    fire time took its DEFAULT - `~/.claude/dispatch-guard` - however the arming session had
    resolved it. Anybody using `$CLAUDE_DISPATCH_DIR` or `--dir` therefore had an alarm that
    woke, read a `resume.json` that was never written there, and logged `RUN-ABORT no handoff
    recorded`. Silent, and only for them. ADR 20260917-132015, D10.

    ⚠ `--dry-run` returns the command WITHOUT registering anything, so this leaves no task
    behind on the machine running the checks.
    """
    import time as _t
    mod = load_resume()
    with scratch_dir("scheduled-dir") as sdir:
        saved, mod.usage.state_dir = mod.usage.state_dir, lambda argv=None, _d=sdir: _d
        try:
            cmd, _ = mod.schedule(_t.localtime(_t.time() + 3600), True)
        finally:
            mod.usage.state_dir = saved
        line = " ".join(cmd)
        assert "--dir" in line, (
            "the scheduled command names no state directory, so it will fire against the "
            "default one: %s" % line)
        # ⭐ The VALUE matters, not just the flag: a `--dir` naming the wrong directory is
        # the same failure with more characters.
        assert sdir.replace("\\", "/") in line, (
            "the scheduled command names a state directory that is not the one it was armed "
            "in (%s): %s" % (sdir, line))
    print("ok - the scheduled resume names the state directory it was armed in")


def main():
    fresh_scratch()
    before = _tree_log()
    mod = load_resume()
    case_posix_cancels_one_job_not_all()
    case_only_the_owner_session_stands_a_resume_down()
    case_a_takeover_line_stands_the_resume_down()
    case_a_handoff_must_say_who_wrote_it()
    case_the_woken_run_is_told_it_is_a_continuation()
    case_reaper_takes_only_spent_records()
    case_two_failures_produce_two_announcements()
    case_upgrade_keeps_an_armed_alarm()
    case_the_arming_session_is_told_not_guessed()
    case_scheduled_command_names_its_state_dir()
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
