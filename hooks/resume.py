#!/usr/bin/env python3
"""Arm a one-shot resume for after the usage window resets.

    resume.py --arm --task <folder> [--at HH:MM] [--dry-run]
    resume.py --status
    resume.py --cancel [--all]     (--all: POSIX only, removes EVERY `at` job you have)
    resume.py --run                 (the scheduler calls this; not for humans)

⭐ WHAT THIS IS FOR, and why it is not the same as telling an agent to remember.

When usage hits the hard threshold the gate refuses further dispatches and the agent is
told to wrap up. That leaves a gap: the window resets an hour or two later, and unless
somebody is sitting there, nothing continues. This closes it with the operating system's
own scheduler, so the work resumes **even after the terminal and the editor are closed**.

⚠ NOT AFTER A LOGOFF, and the earlier wording here claimed otherwise. `schtasks /Create`
without `/RU` or `/IT` registers a task whose Logon Mode is **"Interactive only"** -
measured 2026-08-26 - so it runs only while the user is logged on interactively. Closing
the terminal and the editor is fine; logging out or switching user means it does not fire.

Adapted from claude-pacer's extras/schedule-resume + resume-runner, rewritten to fit this
protocol rather than ported as-is. Four deliberate differences:

 1. ⭐ **The handoff lives in the TASK FOLDER**, not in one global file. Everything a task
    produces belongs together, and a single shared handoff.md silently loses whichever
    task wrote it second.
 2. ⛔ **The handoff is REQUIRED and is checked for substance**, not merely for existence.
    An empty or placeholder file is refused, because a resume that wakes up with nothing
    to read burns an allowance to produce nothing - the exact waste this whole plugin
    exists to prevent.
 3. **One code path for Windows and Unix.** `schtasks` or `at`, chosen at run time.
 4. **It logs to the same gate log** as everything else, so one file answers "what
    happened while nobody was watching".

⚠ IT CANNOT VERIFY THAT THE RESUME WILL WORK. Scheduling succeeds long before the
scheduled moment, and whether `claude` is on PATH for the scheduler's user, whether the
machine is awake, and whether credentials are still valid are all unknown until it fires.
`--status` reports what was registered, never that it will succeed.
"""

import glob
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dispatch_gate  # noqa: E402  - for the ONE definition of where task folders live
import usage  # noqa: E402

TASK_NAME = "ClaudeDispatchGuardResume"
# ⭐ ONE definition, in the module this one already imports. The gate refuses a dispatch when
# the handoff is missing or thin, and this file refuses to ARM against the same bar - two
# copies of that number would be two chances for the two halves to disagree.
HANDOFF = dispatch_gate.HANDOFF
MIN_HANDOFF_CHARS = dispatch_gate.MIN_HANDOFF_CHARS
# All three are overridable in config.json. Retrying is bounded by TIME, not by a
# count: "keep trying for two hours, every twenty minutes" is a thing a person can
# reason about, whereas "three attempts" hides how long that actually covers.
RESUME_DEFAULTS = {
    "resume_offset_min": 3,      # how long AFTER the reset to fire
    "retry_window_min": 120,     # keep retrying for this long, then stop for good
    "retry_every_min": 20,       # how often to retry inside that window
}
FAILED_MARKER = "resume_failed.json"
# ⛔ ONE RECORD PER SESSION, AND DELIBERATELY NOT INSIDE `state/`. Every session used to
# write the SAME `<sdir>/resume.json`, so the second one to arm silently took the first
# one's slot - measured live on this machine, 2026-09-17, with one record carrying one
# session's task and another's working directory (see the ADR's MEASURED-live-clobber.md).
# ⚠ `state/` was the obvious home and is the WRONG one: prune_state() sweeps everything
# there by age with two carve-outs, and a resume can be armed against the SEVEN-day reset -
# so with `state_keep_days` set low the record would die while its OS task stayed
# registered, and the alarm would wake to `RUN-ABORT no handoff recorded`.
# ADR 20260917-132015, D1.
RESUME_DIR = "resume"
LEGACY_RECORD = "resume.json"           # pre-0.60 single slot; migrated by migrate_legacy()
# A session the gate touched within this many minutes counts as live, so the scheduled
# route stands down and lets the session-wake route do the work.
ALIVE_WITHIN_MIN = 30


def record_path(sdir, session_id):
    """Where THIS session's resume record lives: `<sdir>/resume/<session>.json`."""
    return os.path.join(sdir, RESUME_DIR,
                        dispatch_gate.safe_session(session_id) + ".json")


def record_paths(sdir):
    """Every resume record in this state directory, oldest name first.

    ⚠ `*.json` ONLY. The per-session failure markers live in the same folder and a sweep
    that matched everything would delete the announcements they exist to deliver.
    """
    return sorted(glob.glob(os.path.join(sdir, RESUME_DIR, "*.json")))


def dir8(sdir):
    """Eight hex characters naming this STATE DIRECTORY, for the OS task name.

    ⛔ WITHOUT IT TWO STATE DIRECTORIES COLLIDE ON ONE TASK NAME. A machine can have more
    than one (`--dir`, `$CLAUDE_DISPATCH_DIR`), and two of them that see the same session id
    would otherwise register the same task - the second `/Create /F` silently overwriting
    the first.

    ⚠ `normcase(realpath(...))` and not the raw path: `state_dir()` only calls `abspath`, so
    `C:\\Users\\X\\...` and `c:\\users\\x\\...` are the same directory spelled two ways, and
    hashing them apart would make a directory fail to recognise its own tasks. The failure
    would be silent and in the safe direction - nothing reaped - which is exactly the kind
    that survives for months.
    """
    import hashlib
    key = os.path.normcase(os.path.realpath(sdir))
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]


def task_name(sdir, session_id):
    """The OS task name for one session's resume in one state directory."""
    return "%s-%s-%s" % (TASK_NAME, dir8(sdir), dispatch_gate.safe_session(session_id))


def write_record(sdir, session_id, state):
    """Write one session's record, creating `<sdir>/resume/` on the way."""
    path = record_path(sdir, session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f)
    return path


def reap_records(sdir, now=None):
    """Remove spent records, and the OS task of each, for THIS state directory.

    ⛔ WITHOUT THIS, EVERY SESSION LEAVES A SCHEDULED TASK BEHIND FOR EVER. One record and
    one OS task per session is the whole point of 0.60, and it is also how a machine ends up
    with hundreds of them. ADR 20260917-132015, D6.

    ⭐ IT PROBES ONLY NAMES IT ALREADY HOLDS, and that is the design, not an optimisation.
    The obvious version enumerates `schtasks /Query /FO CSV` and deletes what looks like
    ours - but that listing costs SECONDS (measured by the ADR's round 2: 3.7-6.8 s against
    489 tasks, growing with a task count this plugin does not control), it runs under a 15 s
    hook timeout, and a hook that times out FAILS OPEN - so housekeeping would disable
    enforcement. It also cannot attribute a task to a state directory: the CSV carries a
    name, a next run time and a status, and nothing else. ⇒ One exact-name probe per record
    we wrote (~115 ms), which is both cheap and exactly attributable.

    ⚠ THE RESIDUE, NAMED: a task whose record somebody deleted by hand can no longer be
    found this way. `Tools/clean-dispatch-guard.ps1` enumerates by prefix, because an
    uninstall is interactive and has no hook timeout.

    ⛔ SPENT MEANS FIRED AND FINISHED, not "old". A record is removed only when its alarm
    time is further in the past than the whole retry window - so a resume that is still
    retrying is never swept out from under itself - AND its task is no longer registered,
    which is the scheduler agreeing the job is done. ⚠ Never on a scheduler ERROR: `_run`
    answers "did it exit 0?", and a `schtasks` that could not be launched at all answers no,
    which is indistinguishable from "not registered". So the delete needs the record to be
    old AS WELL, and that is what the two conditions together buy.

    ⚠ `*.json` only - `record_paths()` - or this deletes the per-session failure markers,
    which have no alarm time and no task and would match every condition by default.

    Returns how many records it removed. NEVER RAISES: it runs inside a hook.
    """
    now = time.time() if now is None else now
    keep_for = rcfg(sdir)["retry_window_min"] * 60
    removed = 0
    for rec in record_paths(sdir):
        try:
            state = usage.read_json(rec, None)
            if not isinstance(state, dict):
                continue
            at = state.get("at")
            if not isinstance(at, (int, float)) or (now - at) < keep_for:
                continue                       # in the future, or still inside its retries
            sid = state.get("session_id") or os.path.basename(rec)[:-len(".json")]
            if os.name == "nt" and _run(["schtasks", "/Query", "/TN", task_name(sdir, sid)]):
                continue                       # the scheduler still holds it; not spent
            os.remove(rec)
            removed += 1
            log_line("REAPED the spent record for session %s" % str(sid)[:8])
        except Exception:
            continue                           # housekeeping never breaks a hook
    return removed


def migrate_legacy(sdir):
    """Move a pre-0.60 `<sdir>/resume.json` to `resume/<its own session>.json`.

    ⛔ AN UPGRADE MUST NOT LOSE AN ARMED ALARM. The record and the OS task are BOTH renamed
    by this release, so without this an upgrade performed while a resume was armed leaves a
    task the plugin can no longer name and a record it no longer reads - the alarm fires,
    finds nothing, and the guarantee is gone with no message. ADR 20260917-132015, D8.

    ⭐ The old record already carries `session_id` (it has since the field was added), so the
    new name is derivable rather than guessed. ⛔ Without one it is LEFT ALONE and reported
    by --status: inventing a name for somebody's armed alarm is worse than saying "this one
    is yours to clear".

    ⚠ The OS task is re-registered under the new name by the next arm, not here. This
    function moves a FILE and nothing else, so it can run on every start without asking the
    scheduler anything.
    """
    old = os.path.join(sdir, LEGACY_RECORD)
    if not os.path.exists(old):
        return None
    state = usage.read_json(old, None)
    if not isinstance(state, dict) or not state.get("session_id"):
        return "unnamed"                  # --status explains; see the docstring
    new = record_path(sdir, state["session_id"])
    if os.path.exists(new):
        return "collision"                # this session already has one; leave both alone
    try:
        write_record(sdir, state["session_id"], state)
        os.remove(old)
    except OSError:
        return "failed"
    log_line("MIGRATED the single-slot record to %s" % os.path.basename(new))
    return new


def _chdir_or_fall_back(state, handoff_path):
    """Move to where the work lives, and NEVER raise doing it.

    ⛔ AN UNGUARDED `os.chdir` HERE LOSES THE WHOLE RESUME, SILENTLY. It sits upstream of
    every failure handler in do_run() - `announce_failure`, `_rearm`, `do_cancel` are all
    below it - so a target that no longer exists raises `FileNotFoundError` straight past
    them: exit 1, a traceback into the scheduler's void, no `resume_failed.json`, no retry,
    no cancellation. ⚠ The one mechanism whose entire purpose is to tell the owner "it failed
    at 03:40 while you were asleep" is the one that does not run. Measured as a real
    subprocess, found by review 2026-09-01.

    ⭐ THE CANDIDATES, IN ORDER, AND WHY THAT ORDER. `cwd` is where the session was working
    when it armed - the only one that is the actual work. `task` is the folder the handoff
    belongs to, which for a generated handoff is inside the plugin's own state directory and
    is therefore a poor place to run but a fine place to stand. The handoff's own directory
    is the last resort. ⚠ Whatever happens, we keep going: a resume that wakes in the wrong
    directory can still be told where to look, and a resume that never wakes cannot.
    """
    tried = []
    for label, target in (("cwd", state.get("cwd")),
                          ("task", state.get("task")),
                          ("handoff dir", os.path.dirname(handoff_path or "") or None)):
        if not target:
            continue
        try:
            os.chdir(target)
            if tried:
                log_line("RUN-CWD-FALLBACK used the %s (%s) after %s"
                         % (label, target, "; ".join(tried)))
            return target
        except OSError as exc:
            tried.append("%s %r failed (%s)" % (label, target, exc.__class__.__name__))
    # ⚠ EVERY candidate is gone. Say so and run from wherever the scheduler put us, rather
    # than raising past the handlers that exist to report exactly this.
    log_line("RUN-CWD-NONE %s - running from %s"
             % ("; ".join(tried) or "no directory was recorded", os.getcwd()))
    return None


def log_line(message):
    """Append to the gate log in the current repository AND to the state directory.

    ⛔ THE STATE COPY IS THE ONE THAT CAN BE FOUND. `os.getcwd()` is wherever the resume
    happened to be started from - a scheduled task's working directory, or whatever folder a
    shell was in - so this line lands somewhere nobody will look for it. The gate's own
    logger was given a second, unmovable destination in 0.52.1; this one was missed, which
    made every `ARMED`/`RESUME` line unfindable in the one place the rest of the record
    lives. Found by review, 2026-09-01.

    ⛔ AND IT WRITES TO BOTH, not to the first that works. The loop used to `return` on the
    first success, so the second destination was a FALLBACK rather than a copy - and the
    docstring said "and to a fallback" while the tuple held one element, so there was no
    fallback either. A copy that only appears when the other fails is not an audit trail.
    """
    line = "%s RESUME %s%s" % (time.strftime("%Y-%m-%d %H:%M:%S"), message, "\n")
    paths = [os.path.join(os.getcwd(), ".claude", "dispatch_gate.log")]
    try:
        _sd = usage.state_dir([])
        if _sd:
            paths.append(os.path.join(_sd, "dispatch_gate.log"))
    except Exception:
        pass
    for path in paths:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            continue
    sys.stderr.write(line)


def arg(argv, flag, default=None):
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def rcfg(sdir):
    """RESUME_DEFAULTS overlaid with config.json."""
    out = dict(RESUME_DEFAULTS)
    disk = usage.read_json(os.path.join(sdir, "config.json"), {}) or {}
    for src in (disk, disk.get("resume") or {}):
        for k in RESUME_DEFAULTS:
            if isinstance(src.get(k), (int, float)):
                out[k] = max(0, int(src[k]))
    return out


def failed_path(sdir, session_id):
    """Where ONE session's give-up marker lives: `<sdir>/resume/<session>.failed`."""
    return os.path.join(sdir, RESUME_DIR,
                        dispatch_gate.safe_session(session_id) + ".failed")


def announce_failure(sdir, why, session_id=None, task=None):
    """Leave a marker the next session will READ OUT LOUD.

    ⛔ A scheduled task has nowhere to put a message. It runs with no terminal, no
    window and nobody watching, so a resume that gives up would otherwise be
    indistinguishable from a resume that was never armed - and from the outside, from
    the work simply not having been needed. This marker is picked up by the plugin's
    SessionStart hook, which tells the agent, which tells the person. ⚠ That is the only
    path from "it failed at 03:40 while you were asleep" to somebody knowing.

    ⛔ ONE MARKER PER SESSION SINCE 0.60, AND IT IS NOT A TIDINESS CHANGE. There was a
    single `resume_failed.json`, written here and consumed-and-deleted by the gate, so two
    resumes failing overnight left ONE announcement: the second write overwrote the first,
    and the reader deleted it. The owner then heard about one failure and never learnt of
    the other. ⚠ The message also named no session and no task, so even the surviving one
    did not say WHICH work had stopped. ADR 20260917-132015, D9.
    """
    try:
        path = failed_path(sdir, session_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"at": time.time(), "why": why,
                       "session_id": session_id, "task": task}, f)
    except OSError:
        pass
    log_line("GAVE-UP %s" % why)


def session_alive_minutes(sdir, session_id=None):
    """How long ago was a session last active, in minutes? None if never seen.

    ⚠ WITHOUT `session_id` THIS MEANS "ANY SESSION". ⛔ do_run() USED TO CALL IT THAT WAY AND
    NO LONGER DOES (0.60). The old argument was that standing down because SOMEBODY is at the
    keyboard is the safe answer even when it is not the session that armed the resume. Two
    things killed it: the signal cannot carry that meaning - the gate stamps `.alive` before
    any branch on every hook event, including the headless `claude -p` a resume itself spawns
    - and with one resume per session the machine-wide answer vetoed every parallel resume,
    which is the whole feature. ADR 20260917-132015, D5.

    ⭐ WITH one, it answers the question both callers now ask: is the session that armed this
    resume still there? --status asks it to tell a person they can just carry on in that
    conversation; do_run() asks it to decide whether to run headless at all.

    ⛔ THIS IS THE CONFLICT RESOLUTION between the two resume routes, and both routes
    genuinely need to exist: waking the live session is better because it keeps all its
    context, but it depends on that session surviving - and the thing that ends a session
    is often the very limit being waited on. So the safe answer is to arm both, which
    means something has to stop them BOTH doing the work.

    The gate touches a per-session file on every hook event. If any of them is newer than
    the moment the window reopened, a session has been alive and working since then, and
    the scheduled run stands down.

    ⚠ It cannot tell "alive and continuing this task" from "alive doing something else
    entirely". Standing down is still the right call: a person is at the keyboard, and a
    headless run starting underneath them is worse than a resume they can trigger.
    """
    # ⭐ The filename is built by the ONE function that owns that format, sanitising
    # included - a second copy of the rule here is a second place for it to drift.
    paths = ([dispatch_gate.state_path(sdir, session_id, "alive")] if session_id
             else glob.glob(os.path.join(sdir, "state", "*.alive")))
    newest = None
    for p in paths:
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        if newest is None or m > newest:
            newest = m
    return None if newest is None else (time.time() - newest) / 60.0


def origin_session_note(sdir, state):
    """One line on the session this resume was armed from.

    ⛔ IT REPORTS "LAST SEEN", NEVER "ALIVE" OR "DEAD", and the distinction is the whole
    point. An open but IDLE session fires no hooks, so it refreshes nothing and looks
    exactly like a closed one. Printing "dead" from that would be a confident wrong answer
    about the one thing the reader is deciding on - whether they can go back to that
    window and carry on. So it reports the measurement and names the ambiguity.
    """
    sid = state.get("session_id")
    if not sid:
        return ("session  : not captured (armed before this was recorded, or no hook had "
                "fired yet)")
    mins = session_alive_minutes(sdir, sid)
    if mins is None:
        return ("session  : %s - ⛔ NEVER SEEN. Its heartbeat file is gone, so that "
                "conversation is almost certainly closed." % sid[:8])
    if mins < ALIVE_WITHIN_MIN:
        return ("session  : %s - last fired a hook %.0f min ago, so that conversation is "
                "still there. ⭐ Going back to it is the cheapest resume there is."
                % (sid[:8], mins))
    return ("session  : %s - no hook for %.0f min. ⚠ That does NOT mean it is gone: an "
            "open but IDLE session fires no hooks, so waiting and closed look identical "
            "from here. Check the window before assuming." % (sid[:8], mins))


def reset_time(sdir, cfg):
    """(epoch, which) - when the window that is ACTUALLY BLOCKING turns over, or (None, None).

    ⛔ IT USED TO READ `five_hour` AND NOTHING ELSE, and that became a trap the moment the
    brake learned to STOP on the seven-day window: the agent would be told to wrap up, arm a
    resume against the FIVE-hour reset, wake three minutes after it, still be at STOP because
    the WEEK is what is spent, retry every retry_every_min for retry_window_min, and then
    announce failure. Two hours of scheduled retries against a window that does not reset for
    days.

    ⭐ SO IT ASKS THE VERDICT WHICH WINDOW IS DRIVING. verdict() already decides that - it has
    to, to name the right one in its own text - and one answer to one question is the whole
    point of asking it rather than re-deriving it here.

    ⚠ AND THE ANSWER IS NOT "whichever resets later". A 7d window that resets BEFORE the
    current 5h window ends is not a constraint at all: its percentage is about to become
    zero, verdict() ignores it, and waiting days for it would be waiting for nothing. The
    question is which window is blocking, not which clock is longer.
    """
    data = usage.read_json(cfg["token_usage_file"], {}) or {}
    v = usage.verdict(sdir, usage.config(sdir), data=data)
    # ⛔ `relaxed_driver` COVERS THE RELAXED CASE. When a STOP is relaxed to GO near a reset the
    # combined word is GO, so `driver` is None; without this, a relaxed 7d STOP arms for the 5h
    # reset and wakes hours before the 7d window reopens - the days-away retry loop this function
    # exists to avoid. verdict() names which window was relaxed.
    key = ("seven_day" if v.get("driver") == "7d" or v.get("relaxed_driver") == "7d"
           else "five_hour")
    win = data.get(key) or {}
    r = win.get("resets_at")
    if isinstance(r, (int, float)):
        return r, ("7d" if key == "seven_day" else "5h")
    # ⚠ The driver's own reset is missing - fall back to the five-hour one rather than
    # refusing to arm at all, and say which was used. A resume at the wrong reset retries and
    # gives up; no resume at all just never happens.
    r = (data.get("five_hour") or {}).get("resets_at")
    return (r, "5h") if isinstance(r, (int, float)) else (None, None)


def find_handoff(task, sdir):
    """Locate the task folder's handoff, searching the task roots.

    ⚠ The CONFIGURED root is asked first, and this file no longer carries its own copy of
    the defaults. It used to, so a repository that had moved `dispatch.task_root` could not
    arm a resume at all: the handoff was named in config and looked for somewhere else,
    and the refusal read as "no HANDOFF.md" rather than "looked in the wrong place".

    ⚠ Relative to the REPOSITORY root, not to the current directory, so arming from a
    subdirectory finds the same folder the gate does.
    """
    if os.path.isabs(task) and os.path.isdir(task):
        return os.path.join(task, HANDOFF), task
    repo = dispatch_gate.repo_root(os.getcwd())
    for root in dispatch_gate.task_roots(repo, sdir):
        d = os.path.join(repo, root.replace("/", os.sep), task)
        if os.path.isdir(d):
            return os.path.join(d, HANDOFF), d
    return None, None


def arming_session(sdir, session_id=None):
    """(session_id, transcript path or None) for the session arming this resume.

    ⭐ **GIVEN A `session_id`, THERE IS NO GUESS** - and that is how the gate calls it. The
    gate holds the id on the hook payload that decided to arm, so it passes `--session`
    (dispatch_gate.maybe_auto_arm) and this function only has to find the transcript.
    ⛔ It used to have no such parameter, so EVERY automatic arm was keyed by the guess
    below - including the arms of two sessions racing each other, which is the one case the
    guess is documented to get wrong. ADR 20260917-132015, D12 ⟨R2 I-B1⟩.

    ⚠ THE GUESS REMAINS, for a `resume.py --arm` a person runs by hand. The gate stamps
    `<session-id>.alive` on every hook event, so the id is the FILENAME of the newest one,
    and a hand-run `--arm` is itself inside a session that just fired hooks.

    ⚠ "Newest", not "certainly ours". With two sessions live on one machine the wrong id
    could be picked. That is why the transcript is recorded as a POINTER the next run may
    consult, and never as something it must trust: a wrong pointer costs a wasted Read, a
    wrong --resume would cost a whole conversation.

    ⭐ The transcript is found by GLOB on the session id rather than by rebuilding Claude
    Code's project-folder name. That name is the cwd with separators replaced and its drive
    letter's case preserved from however the path was spelled - guessing it is exactly the
    kind of undocumented-internal-layout dependency this plugin refuses elsewhere. A UUID
    is unique, so one glob finds it with no guessing.
    """
    sid = session_id
    if not sid:
        newest = (None, None)
        for p in glob.glob(os.path.join(sdir, "state", "*.alive")):
            try:
                m = os.path.getmtime(p)
            except OSError:
                continue
            if newest[0] is None or m > newest[0]:
                newest = (m, os.path.basename(p)[:-len(".alive")])
        sid = newest[1]
    if not sid:
        return None, None
    hits = glob.glob(os.path.join(os.path.expanduser("~"), ".claude", "projects", "*",
                                  sid + ".jsonl"))
    return sid, (hits[0] if hits else None)


def check_handoff(path):
    """⛔ Substance, not existence. Returns None if usable, else the reason it is not."""
    if not path or not os.path.exists(path):
        return "no %s in that task folder" % HANDOFF
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        return "cannot read it: %r" % (exc,)
    body = " ".join(text.split())
    if len(body) < MIN_HANDOFF_CHARS:
        return ("only %d characters of content - that is a placeholder, not a work order. "
                "A resume that wakes with nothing to read spends an allowance to produce "
                "nothing." % len(body))
    return None


# ⛔ Phrases that point at context the reader does not have. A handoff carrying one of
# these does NOT stand alone, which is the single failure this file cannot recover from:
# the resumed run has the handoff and nothing else.
DANGLING = ("as discussed", "as above", "see above", "mentioned above", "the above",
            "as mentioned", "earlier in this", "如上所述", "如前所述", "前面提到",
            "上面提到", "剛才", "如上")


def handoff_warnings(path):
    """Structural smells in a handoff. WARNINGS ONLY - never a refusal.

    ⛔ WHY THESE WARN RATHER THAN BLOCK, unlike the length floor. Failing to arm removes
    the resume ENTIRELY, and an imperfect handoff is worth far more than no resume at all.
    The length floor stays hard because a 40-character placeholder really is worth nothing;
    everything below is a heuristic, and a heuristic must not be able to cost you the run.

    ⭐ WHY THIS EXISTS AT ALL - it is the measured leverage point. A resumed run pays for
    whatever it must re-read: measured 2026-08-26, resuming a 0.37 MB transcript cost 35,356
    input tokens on top of the 43,757 a fresh run pays anyway, with cache_read at ZERO
    because a wait long enough to need a resume is longer than the prompt cache TTL. A 3 KB
    handoff is about 800 tokens. ⇒ The handoff is a ~170x compression of the transcript, and
    it is the ONLY thing the next run gets. Its quality is the whole recovery.
    """
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    low = text.lower()
    out = []
    hit = [d for d in DANGLING if d in low]
    if hit:
        out.append("it says %r - the run that reads this has NONE of your context, so a "
                   "backward reference points at nothing. Spell the thing out."
                   % (hit[0],))
    # A context-free reader needs something it can open. Any path-shaped token will do.
    if not re.search(r"[\w.-]+[/\\][\w./\\-]+|\b[A-Za-z]:[/\\]", text):
        out.append("no file path appears anywhere - the next run has nothing to open. Name "
                   "the files it must read and the file it must write.")
    if not re.search(r"next step|next action|下一步|接下來|todo|TODO", text, re.I):
        out.append("no next step is marked - state the exact next action, concretely enough "
                   "to act on without deciding anything first.")
    # ⛔ WHO THIS SESSION IS. A resume wakes a FRESH `claude -p` with a NEW session id - never
    # `--resume`, because re-sending a transcript costs ~95k tokens/MB at zero cache read - so
    # the successor cannot know whose work it is continuing unless this file says. do_run
    # hands it the predecessor's id and tells it to keep the name it finds here; with no name
    # there is nothing to keep. ⚠ Sharpest with several sessions collaborating - a fleet keyed
    # on session ids sees one member vanish and a stranger arrive - but it is warned for EVERY
    # handoff, because a run does not know today whether it will be collaborating tomorrow.
    # ⭐ A session id OR a stated role satisfies it: the id is what the machine matches on,
    # the role is what a person reads.
    if not re.search(r"session[ _-]?id|session\s*[:：]|我是|call sign|role\s*[:：]|"
                     r"身分|代號|[0-9a-f]{8}-[0-9a-f]{4}", text, re.I):
        out.append("it does not say WHO this session is - name the role or call sign and the "
                   "session id. The resume wakes a NEW session, and it can only keep a name "
                   "that this file gives it.")
    return out


# ⛔ THE ONE FORM A TAKEOVER LINE MAY TAKE, and it is deliberately strict. A resume that
# refuses to run is a worse failure than one that redoes work - "the resume IS the
# guarantee" is this plugin's whole thesis - so anything this pattern does not match is
# ignored and the run proceeds. Prose, a missing timestamp, a date this cannot parse: all
# mean RUN. ADR 20260917-132015, D4.
TAKEOVER = re.compile(r"TAKEN\s+OVER\s+(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})", re.I)


def taken_over_since(path, armed_at):
    """The takeover line in `path` written AFTER `armed_at`, or None.

    ⛔ THE PROBLEM. A session dies mid-task with a resume armed. Somebody picks the work up
    in a DIFFERENT session - which is the normal way it happens, since the session that armed
    the alarm is the one that died - finishes it, and the alarm then fires and redoes work
    that is already done, spending a fresh window to produce a duplicate.

    ⭐ WHY THE EVIDENCE LIVES IN THE HANDOFF. do_run reads that file anyway: it is the
    resume's only input. So the successor writes one line into it at the moment it TAKES
    OVER, and no session ever touches another session's record or scheduled task. ⚠ An
    earlier design had the newcomer CANCEL the old alarm at its own wind-down; that fires
    hours too late, because a session writes its handoff when it stops, not when it starts.

    ⛔ THE TIMESTAMP IS COMPARED TO `armed_at`, NOT MERELY READ. A takeover line from a
    previous cycle would otherwise suppress every future resume for that folder, for ever -
    the file is not cleaned up by anybody. Older than the arm: ignored.

    ⛔ AND IT IS A TIMESTAMP IN THE TEXT, NEVER THE FILE'S mtime. `git checkout`, `pull`,
    `stash` and `merge` all set mtime=now on every tracked file - measured in this repository
    (ADR 20260902-142400, decision 4) - so an mtime rule would let one `git pull` convince
    every armed resume on the machine that somebody had taken over, and none of them would
    run. That failure is silent and it is in the direction that loses work.

    ⚠ FAILS TOWARD RUNNING, always: unreadable file, no line, unparsable date, no `armed_at`
    recorded - every one of them returns None and the resume proceeds.
    """
    if not isinstance(armed_at, (int, float)):
        return None                    # nothing to compare against; run
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    import datetime
    for m in TAKEOVER.finditer(text):
        try:
            # ⛔ `datetime`, NOT `time.mktime`. mktime NORMALISES out-of-range fields instead
            # of rejecting them - measured here: `2026-13-45T99:99` came back as a valid
            # moment in 2027, so a typo stood the resume DOWN for ever. datetime raises,
            # which sends this down the "cannot parse it, so run" path where it belongs.
            when = datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                     int(m.group(4)), int(m.group(5))).timestamp()
        except (ValueError, OverflowError, OSError):
            continue                   # a date that is not a date; run
        if when > armed_at:
            line = text[text.rfind("\n", 0, m.start()) + 1:]
            return line.split("\n")[0].strip()[:200]
    return None


def schedule(when, dry_run, session_id=None):
    """Register a ONE-SHOT task at `when` (a struct_time). Returns the command run.

    ⛔ THE COMMAND LINE GOES THROUGH THE SHIM, and of everything this plugin writes, this is
    the one where a versioned path hurts most. The task is registered with the OS NOW and
    fires HOURS later - across exactly the window in which somebody runs `claude plugin
    update`. A path into the plugin cache would then point at a version that is gone, the
    scheduler would run it, nothing would happen, and the whole point of arming a resume is
    that nobody is watching when it fires. ⇒ See hooks/shim.py.

    ⚠ The shim is WRITTEN here rather than assumed - arming is the one moment this code knows
    a command must still work at an unattended future time. ⛔ But AFTER the dry_run return,
    never before it: a caller asking what WOULD be registered must not change anything on
    disk. Measured the hard way elsewhere in this change - a builder with a side effect wrote
    into the real state directory from a test run.
    """
    import shim
    me = os.path.abspath(__file__)
    sdir = usage.state_dir()
    # ⛔ THE STATE DIRECTORY IS NAMED, or the alarm fires against the WRONG ONE. The task is
    # registered by a session whose `sdir` may come from `$CLAUDE_DISPATCH_DIR` or `--dir`,
    # but the scheduler starts `resume.py --run` with neither - so `state_dir()` at fire time
    # fell back to the DEFAULT directory, read a resume.json that was never written there,
    # and logged `RUN-ABORT no handoff recorded`. Silent, and only for the people who moved
    # their state directory. ADR 20260917-132015, D10.
    # ⚠ Quoted and forward-slashed: this string goes inside `schtasks /TR`, and a home
    # directory with a space in it is ordinary. `state_dir()` calls abspath on whatever it
    # receives, so either separator arrives correctly.
    inner = shim.command(sdir, "resume.py", "--run", "--dir",
                         '"%s"' % sdir.replace("\\", "/"))
    if os.name == "nt":
        cmd = ["schtasks", "/Create", "/TN", task_name(sdir, session_id), "/SC", "ONCE",
               "/ST", time.strftime("%H:%M", when), "/SD", time.strftime("%m/%d/%Y", when),
               "/TR", inner, "/F"]
    else:
        # `at` reads the command on stdin; keep it to one line for the same reason.
        cmd = ["at", time.strftime("%H:%M %Y-%m-%d", when)]
    if dry_run:
        return cmd, None
    shim.write(sdir, os.path.dirname(os.path.dirname(me)))
    try:
        if os.name == "nt":
            r = subprocess.run(cmd, capture_output=True, timeout=60)
        else:
            r = subprocess.run(cmd, input=(inner + "\n").encode(), capture_output=True,
                               timeout=60)
        return cmd, r
    except Exception as exc:
        return cmd, exc


def print_route_a_reminder(when):
    """⛔ THE OS TASK IS THE BACKUP. Say so, every single time, right after arming it.

    Two routes exist and only ONE of them has a command. This file arms the OS task;
    route (A) - waking this session - is an agent tool (CronCreate) that no Python can
    call. So arming was the only visible step, and an agent could reasonably finish its
    turn having armed the backup and nothing else.

    ⛔ THAT COMBINATION IS THE ONE HOLE WHERE NOTHING RESUMES. The OS task stands down
    when any session was active in the last ALIVE_WITHIN_MIN minutes, because it assumes
    the wake is handling it. If the wake was never armed, the stand-down hands the work to
    a route that does not exist, and both alarms stay silent.

    ⭐ Route (A) is also the one the person actually wants: the work carries on in the
    conversation already on their screen, so they can walk away and come back to it
    rather than to a headless run's summary.
    """
    stamp_ = time.strftime("%H:%M", when)
    print()
    print("⭐ NOW ARM ROUTE (A) AS WELL - the OS task above is the BACKUP, not the plan.")
    print("   (A) keeps THIS session and everything loaded in it. Schedule a one-shot wake")
    print("   for about %s with CronCreate (ToolSearch \"select:CronCreate\"," % stamp_)
    print("   recurring:false), then END THE TURN. When it fires you carry on in this same")
    print("   conversation, on screen, with nothing to reconstruct.")
    print("   ⛔ Arm ONLY the OS task and there is a hole: if anybody touched a session")
    print("   in the last %d minutes, the OS task stands down expecting a wake that was" % ALIVE_WITHIN_MIN)
    print("   never armed - and NOTHING resumes.")
    print("   ⚠ (A) dies with the session, which is exactly why (B) above is armed too.")


def do_arm(argv, sdir, cfg):
    task = arg(argv, "--task")
    if not task:
        print("⛔ --task <folder> is required: the handoff lives in the task folder, not")
        print("   in one shared file, so this needs to know which task is resuming.")
        return 2

    path, folder = find_handoff(task, sdir)
    problem = check_handoff(path)
    # ⛔ THE SAME SWITCH THE GATE READS. With `require_handoff_past_soft` on - the default -
    # a dispatch past the soft threshold is already refused without a handoff, so arming
    # without one would be arming for a session that could not have got here. With it OFF the
    # owner has said they accept the cost, and refusing to arm would leave them with the
    # worst of both: no handoff AND no resume.
    require = dispatch_gate.gate_config(dispatch_gate.repo_root(os.getcwd()), sdir).get(
        "require_handoff_past_soft", True)
    if problem and require:
        print("⛔ Cannot arm a resume: %s" % problem)
        print("   Expected: %s" % (path or "<task folder>/" + HANDOFF))
        print()
        print("   Write it FIRST, and write it to stand alone - the run that reads it has")
        print("   none of this session's context. State what is done, what is not, what")
        print("   was tried and failed, and the exact next step.")
        print()
        print("   ⚠ Or set require_handoff_past_soft: false, and the resume will wake with a")
        print("     RECONSTRUCTION prompt instead - it rebuilds the state from progress.md,")
        print("     git and the task folder, which costs a chunk of the new window.")
        return 2
    if problem:
        print("⚠ Arming WITHOUT a handoff: %s" % problem)
        print("  require_handoff_past_soft is false, so the resume will wake with the")
        print("  reconstruction prompt and rebuild the state from what is on disk.")

    for w in (handoff_warnings(path) if not problem else ()):
        print("⚠ handoff: %s" % w)

    at = arg(argv, "--at")
    armed_reset = None          # the reset this alarm was computed from, if any
    if at:
        try:
            hh, mm = [int(x) for x in at.split(":")]
        except Exception:
            print("⛔ --at must look like 14:05")
            return 2
        now = time.localtime()
        when_epoch = time.mktime((now.tm_year, now.tm_mon, now.tm_mday, hh, mm, 0, 0, 0, -1))
        if when_epoch <= time.time():
            when_epoch += 86400
    else:
        r, which = reset_time(sdir, cfg)
        if not r:
            print("⛔ No reset time available, so there is nothing to schedule against.")
            print("   Either usage data is missing (run install.py --status) or pass --at.")
            return 2
        armed_reset = r
        when_epoch = r + rcfg(sdir)["resume_offset_min"] * 60   # past the reset, not on it
        # ⛔ SAY WHICH WINDOW, because a seven-day reset is DAYS away and a person who
        # expected a three-hour wait needs to see that before they walk away from it.
        if which == "7d":
            print("⚠ Scheduling against the SEVEN-DAY reset, not the five-hour one: that is")
            print("  the window currently at STOP, and waking at the 5h reset would find it")
            print("  still blocked and retry until it gave up.")

    when = time.localtime(when_epoch)
    dry = "--dry-run" in argv
    # ⭐ `--session` when the gate armed this, the guess only for a hand-run --arm.
    sid, transcript = arming_session(sdir, arg(argv, "--session"))
    # ⛔ WHERE THE WORK LIVES, recorded here or lost for ever. do_run() `chdir`s before it
    # does anything, and until now the only thing it had to aim at was the TASK folder -
    # fine while every handoff sat inside the repository, wrong the moment one is generated
    # into the plugin's own state directory.
    # ⭐ THE SESSION-START cwd, NOT `os.getcwd()`. A hook payload's cwd follows the Bash
    # tool's own `cd`, so the value at arm time may be some scratch directory the session
    # wandered into. The gate stamps the start-time one; see dispatch_gate.session_cwd().
    # ⚠ `os.getcwd()` is the fallback for a session stamped before that shipped.
    work_cwd = dispatch_gate.session_cwd(sdir, sid) or os.getcwd()
    state = {"task": folder, "handoff": path, "at": when_epoch,
             "armed_at": time.time(), "session_id": sid, "cwd": work_cwd,
             "transcript": transcript, "armed_for_reset": armed_reset, "at_job": None}
    # ⛔ THE RECORD GOES DOWN BEFORE THE TASK IS REGISTERED, and the order is the point. The
    # reaper deletes a registered task that no record claims, so registering first leaves a
    # window in which a sibling session's start sweep can delete an alarm that was armed
    # one line ago - the same silent loss the record's placement was chosen to avoid.
    # ADR 20260917-132015, D6 ⟨round 2, I-N2⟩.
    if not dry:
        write_record(sdir, sid, state)
    cmd, result = schedule(when, dry, sid)

    print("task folder   : %s" % folder)
    print("handoff       : %s (%d chars)" % (path, os.path.getsize(path)))
    print("will fire at  : %s" % time.strftime("%Y-%m-%d %H:%M", when))
    print("command       : %s" % " ".join(cmd))
    if dry:
        print()
        print("--dry-run: nothing was registered.")
        print_route_a_reminder(when)
        return 0

    ok = hasattr(result, "returncode") and result.returncode == 0
    if ok:
        # ⭐ POSIX only: the job number `at` announced is the ONE handle that lets
        # do_cancel() remove this job without removing every other `at` job the user has.
        state["at_job"] = at_job_id(result)
        write_record(sdir, sid, state)
        print("status        : ARMED (this is the BACKUP route - see below)")
        log_line("ARMED task=%s at=%s session=%s"
                 % (folder, time.strftime("%Y-%m-%d %H:%M", when),
                    str(sid or "")[:8] or "?"))
    else:
        detail = getattr(result, "stderr", b"") or b""
        print("status        : ⛔ FAILED - %s" % (detail.decode("utf-8", "replace").strip()
                                                  or repr(result)))
        # ⛔ TAKE THE RECORD BACK DOWN. It was written BEFORE the scheduler was asked (see
        # above), so a refused registration would otherwise leave a record claiming an alarm
        # that does not exist - and `--status` would report a resume nothing will ever fire.
        try:
            os.remove(record_path(sdir, sid))
        except OSError:
            pass
        log_line("ARM-FAILED task=%s session=%s" % (folder, str(sid or "")[:8] or "?"))
    print()
    if ok:
        print_route_a_reminder(when)
    print()
    print("⚠ Armed is not the same as will-work. Whether `claude` is on PATH for the")
    print("  scheduler's user, whether the machine is awake, and whether credentials are")
    print("  still valid are all unknown until it fires.")
    return 0 if ok else 1


def do_run(sdir, cfg, session_id=None):
    """The scheduler's entry point. Runs headless Claude against the handoff.

    ⛔ IT DOES NOT DELETE ITSELF JUST BECAUSE IT WOKE UP. Two things can be true when the
    alarm goes off and neither is success: the window may not actually have reset (a
    clock that drifted, a reset that moved), and the run itself may fail (no network, an
    expired credential, `claude` not on the scheduler's PATH). A one-shot task that
    removes itself in either case has quietly cancelled the resume it existed to perform,
    and nothing says so until somebody notices the work never continued.

    So: verify the window first, run, and remove the schedule ONLY on a clean exit. On
    anything else, re-arm for RETRY_MINUTES later, up to MAX_ATTEMPTS.
    """
    # ⛔ THE ALARM SAYS WHOSE RECORD IT IS. The scheduler passes `--session` because the
    # task was registered with it; a task registered by an OLDER version passes none, and
    # then the only record it can mean is the pre-0.60 single slot. ⚠ With neither, this
    # REFUSES rather than picking one of several records - running somebody else's task is
    # the failure this whole change exists to stop. ADR 20260917-132015, D8.
    if session_id:
        state = usage.read_json(record_path(sdir, session_id), {}) or {}
    else:
        legacy = os.path.join(sdir, LEGACY_RECORD)
        state = usage.read_json(legacy, {}) or {}
        if not state and record_paths(sdir):
            log_line("RUN-ABORT no --session and no legacy record, but %d per-session "
                     "record(s) exist - refusing to guess which one this alarm is for"
                     % len(record_paths(sdir)))
            return 1
    path = state.get("handoff")
    if not path or not os.path.exists(path):
        log_line("RUN-ABORT no handoff recorded")
        return 1
    # ⭐ From here on every cancel and re-arm is about THIS record, so the id the record
    # carries is the one to use - not the argument, which is absent on the legacy path.
    my_sid = state.get("session_id", session_id)

    rc_ = rcfg(sdir)

    # ⭐ Stand down if THE SESSION THAT ARMED THIS has picked the work back up itself.
    # ⚠ "Recently active", NOT "active since the window reopened": resets_at names the
    # NEXT reset, so deriving the reopening from it is arithmetic that is easy to get
    # backwards - a first version did exactly that, compared against a future timestamp,
    # and the check never fired. Recency is what the question actually reduces to.
    #
    # ⛔ THIS ASKED "IS ANYBODY ALIVE?" UNTIL 0.60, AND THAT QUESTION CANNOT BE ANSWERED BY
    # THE SIGNAL IT USED. `session_alive_minutes(sdir)` globs every `state/*.alive`, and the
    # gate calls heartbeat() before ANY branch on every hook event - so the answer is "yes"
    # whenever any session exists at all, including the headless `claude -p` that a resume
    # itself spawns, for up to the three hours of its timeout. One resume would therefore
    # veto every other resume that fired after it.
    # ⇒ With per-session records (ADR 20260917-132015, D1) the machine-wide question also
    # stopped being the RIGHT one. This check exists to resolve the two resume routes
    # against each other - "will the session that armed me do this itself?" - and another
    # session being alive never answered that.
    #
    # ⛔ WHAT IS GIVEN UP, NAMED. The machine-wide test also happened to stop a headless run
    # starting while somebody was working in a DIFFERENT session. That protection is gone,
    # deliberately: keeping it costs the entire feature on a one-machine setup, which is the
    # owner's actual case. Approved by the owner 2026-09-17 (ADR §11, §9.3). The bounds are
    # the screen line the gate prints when it arms, `resume.py --cancel`, and the fact that a
    # resumed run works in ITS OWN recorded task folder and cwd.
    # ⚠ The 2026-08-30 reason for the second signal - our own `.alive` can go flat when the
    # hook is not wired - is narrowed rather than answered: a record only EXISTS because the
    # gate hook fired for that session at arm time. Not zero; recorded in the ADR as A2.
    alive = session_alive_minutes(sdir, my_sid)
    if alive is not None and alive < ALIVE_WITHIN_MIN:
        do_cancel(sdir, quiet=True, session_id=my_sid)
        log_line("RUN-SKIPPED the session that armed this (%s) was active %.0f min ago "
                 "(< %d), so it is awake and will carry the work on itself - standing down "
                 "rather than running it twice"
                 % (str(my_sid or "?")[:8], alive, ALIVE_WITHIN_MIN))
        return 0

    # ⭐ AND THE OTHER WAY THE WORK CAN ALREADY BE IN HAND: somebody picked it up in a
    # DIFFERENT session and said so in the handoff. That is the normal shape - the session
    # that armed this alarm is the one that died - and the check above cannot see it,
    # because it asks about a session that is gone either way. See taken_over_since().
    taken = taken_over_since(path, state.get("armed_at"))
    if taken:
        do_cancel(sdir, quiet=True, session_id=my_sid)
        log_line("RUN-SKIPPED the handoff says somebody took this over after it was armed, "
                 "so the work is already in hand: %s" % taken)
        return 0

    attempts = int(state.get("attempts", 0)) + 1
    state["attempts"] = attempts
    first = state.get("first_fire") or time.time()
    state["first_fire"] = first
    # ⭐ Bounded by elapsed time, not by attempt count.
    exhausted = (time.time() - first) > rc_["retry_window_min"] * 60

    # Has the window really turned over? Stored numbers read stale-HIGH after a reset,
    # so trust the verdict's reset arithmetic rather than the raw percentage.
    v = usage.verdict(sdir, cfg)
    # ⚠ FAIL-OPEN, AND IT IS NOW AUDIBLE. Only STOP defers, so NO-DATA proceeds - the
    # "has the window really reset?" check silently passes whenever nothing has ever
    # fetched. Running is still the right call (refusing would strand the work on a
    # missing statusline), but it must not look like a verified reset in the log.
    if v["verdict"] == "NO-DATA":
        log_line("RUN-UNVERIFIED no usage data, so the reset could NOT be confirmed - "
                 "proceeding anyway (fail-open). Install the statusline or leave "
                 "`usage.py --watch` running to make this check real.")
    if v["verdict"] == "STOP":
        if not exhausted:
            log_line("RUN-DEFERRED still STOP, retrying in %d min (attempt %d)"
                     % (rc_["retry_every_min"], attempts))
            _rearm(sdir, state, rc_["retry_every_min"])
            return 0
        do_cancel(sdir, quiet=True, session_id=my_sid)
        announce_failure(sdir, "usage still said STOP for the whole %d-minute retry "
                               "window after %d attempts, so the resume never ran"
                               % (rc_["retry_window_min"], attempts),
                         my_sid, state.get("task"))
        return 1

    _chdir_or_fall_back(state, path)
    # ⛔ A FRESH `claude -p`, deliberately NOT `--resume <session-id>`, and the reason is
    # measured. Resuming re-sends the whole transcript as input: 2026-08-26, a 0.37 MB
    # transcript cost 35,356 tokens on top of the 43,757 a fresh run pays anyway, and
    # cache_read was ZERO - a wait long enough to need a resume always outlives the prompt
    # cache. At ~95k tokens per MB that is most of a fresh window spent on re-reading.
    # ⭐ So the handoff is the payload and the transcript is a POINTER: named here so the
    # run can open the parts it needs, instead of paying for all of it or losing it forever.
    transcript = state.get("transcript")
    extra = ""
    if transcript and os.path.exists(transcript):
        extra = (" If and ONLY IF that file leaves you unable to act, the previous session's "
                 "full transcript is at %s - read the RELEVANT PARTS of it, never the whole "
                 "file: it is %.1f MB and reading it all would spend most of this window. "
                 "Say in your result that you had to fall back to it, and why the handoff "
                 "was not enough."
                 % (transcript, os.path.getsize(transcript) / 1048576.0))
    when = time.strftime("%Y-%m-%d %H:%M")
    # ⛔ THE WOKEN RUN IS A DIFFERENT SESSION, AND IT HAS TO BE TOLD SO. `claude -p` below
    # starts a FRESH conversation with a new session id - deliberately, see the measurement
    # there - so a run that wakes up believes it is somebody new. That is invisible on a
    # single task and expensive when several sessions collaborate: a fleet that identifies
    # its members by session id sees one member vanish and a stranger appear, and any
    # registry keyed on the id has a dead entry and an unknown one.
    # ⭐ The id cannot be preserved. The NAME can: this sentence hands the successor its
    # predecessor's id and tells it to keep whatever name the handoff gives it, so a
    # convention built on top of this plugin can re-register the same member.
    # ⚠ It cannot invent a name. If the handoff does not say who this session was, there is
    # nothing to carry - naming yourself is the handoff's job, not the scheduler's.
    who = str(state.get("session_id") or "")[:8]
    identity = (" ⚠ YOU ARE A CONTINUATION, NOT A NEW MEMBER: this work was armed by session "
                "%s, which is gone. Your own session id is different and that is expected. "
                "If %s gives this session a NAME or a role - a registry entry, a call sign, "
                "a domain - KEEP USING THAT NAME and say which session id now answers to it, "
                "rather than introducing yourself as somebody new."
                % (who, HANDOFF)) if who else ""
    # ⚠ `folder` is not in scope here - do_run() reads a recorded state, not the arm-time
    # locals - so the task folder comes from what was recorded, and the repository from
    # where os.chdir() has just put us.
    task_dir = state.get("task") or (os.path.dirname(path) if path else ".")
    repo = dispatch_gate.repo_root(os.getcwd())
    if check_handoff(path):
        # ⛔ NO HANDOFF, BECAUSE THE OWNER SWITCHED THE PRECONDITION OFF. So the run has to
        # rebuild the state itself, and what it is told to read - and NOT to read - is the
        # whole cost of this path.
        #
        # ⚠ THE OBVIOUS PROMPT IS THE EXPENSIVE ONE. "Check the progress and carry on" names
        # no path, so the cheapest thing to read is the session transcript, which is the most
        # expensive source there is - and it invites redoing work that is already committed.
        # ⇒ The sources are named in order of cost, the transcript is forbidden outright,
        # redoing finished work is forbidden, and writing the handoff is the FIRST action
        # rather than the last, so the next cut-off is not identical to this one.
        prompt = (
            "The usage window has reset, so treat usage as fresh. ⛔ There is NO handoff for "
            "this task: the previous session was cut off before it could write one, so "
            "nothing on disk states what it was doing.\n\n"
            "Reconstruct it from the CHEAPEST source that answers the question, and stop as "
            "soon as you can act:\n"
            "  1. %s - the gate records every dispatch and its outcome there.\n"
            "  2. `git -C %s log --oneline -15` and `git -C %s status --short` - what "
            "actually landed.\n"
            "  3. the task folder %s - its prompts and scratch files are what the sub-agents "
            "actually saw.\n"
            "⚠ Do NOT read the session transcript. It is the most expensive source there is "
            "and the last resort.\n\n"
            "⛔ Do NOT redo work that is already committed, or already recorded as done. "
            "Re-running finished work is the waste this reconstruction exists to avoid. When "
            "you cannot tell whether something finished, check the artefact it would have "
            "produced - never redo it to find out.\n\n"
            "⭐ WRITE %s AS YOUR FIRST ACTION, before continuing, and keep it current as you "
            "go. That file is the only thing that survives the next cut-off, and this prompt "
            "exists because it did not exist last time.\n\n"
            "Then continue the work. Append a '## Result %s' section to that file describing "
            "what you did and anything still open, and SAY IN IT that this run started from "
            "reconstruction rather than from a handoff. Do not re-verify usage limits before "
            "starting - the stored numbers read stale-high until a statusline renders.%s"
            % (os.path.join(task_dir, "progress.md"), repo, repo, task_dir,
               path or os.path.join(task_dir, HANDOFF), when, identity))
    else:
        prompt = ("The usage window has reset, so treat usage as fresh. Read %s and continue "
                  "that work, following its instructions exactly.%s%s Append a '## Result %s' "
                  "section to %s describing what you did and anything still open. "
                  "Do not re-verify usage limits before starting - the stored numbers read "
                  "stale-high until a statusline renders."
                  % (path, extra, identity, when, path))
    log_line("RUN starting for %s (attempt %d)" % (path, attempts))
    try:
        r = subprocess.run(["claude", "-p", prompt], capture_output=True, timeout=3 * 3600)
        rc = r.returncode
        log_line("RUN finished rc=%s" % rc)
    except Exception as exc:
        rc, r = -1, None
        log_line("RUN-FAILED %r" % (exc,))

    if rc == 0:
        do_cancel(sdir, quiet=True, session_id=my_sid)   # ⭐ only on a clean exit
        log_line("RUN-OK schedule removed")
        return 0
    detail = (getattr(r, "stderr", b"") or b"").decode("utf-8", "replace").strip()[:150]
    if not exhausted:
        log_line("RUN-RETRY rc=%s (attempt %d), again in %d min. %s"
                 % (rc, attempts, rc_["retry_every_min"], detail))
        _rearm(sdir, state, rc_["retry_every_min"])
        return 1
    do_cancel(sdir, quiet=True, session_id=my_sid)
    announce_failure(sdir, "the resume failed %d times over %d minutes and has stopped "
                           "trying - it is yours to handle now. Last error: %s"
                           % (attempts, rc_["retry_window_min"], detail or "rc=%s" % rc),
                     my_sid, state.get("task"))
    return 1


def at_job_id(result):
    """The job number `at` announced, or None. POSIX only; `schtasks` has names instead.

    ⛔ WHY IT IS WORTH PARSING AT ALL. `at` has no named jobs, so the only way to cancel ONE
    of them is by the number it prints when the job is registered. Without it the only
    instrument left is `atrm -a`, which deletes EVERY `at` job the user has - including jobs
    this plugin never created. That is what this file used to do on every cancel.

    ⚠ NOT VERIFIED AGAINST A REAL `at`: this plugin's development machine is Windows and has
    none (ADR 20260917-132015, A1). The format read is the one POSIX specifies for the
    announcement - `job <n> at <date>` - and BOTH streams are searched because
    implementations disagree about which one it goes to.

    ⭐ None is a supported answer everywhere this is used. It means an alarm this plugin
    cannot name, and do_cancel() then SAYS so instead of claiming the job is gone.
    """
    for stream in ("stderr", "stdout"):
        raw = getattr(result, stream, b"") or b""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        found = re.search(r"\bjob\s+(\d+)", raw)
        if found:
            return found.group(1)
    return None


def _rearm(sdir, state, minutes):
    """Push the one-shot schedule out by `minutes`, keeping the attempt count."""
    when_epoch = time.time() + minutes * 60
    _cmd, result = schedule(time.localtime(when_epoch), False, state.get("session_id"))
    # ⚠ A retry registers a NEW `at` job, so the id recorded at arm time is stale from here
    # on. Keep the old one only when the new registration announced none - a stale id is
    # still a better cancel target than nothing.
    state["at_job"] = at_job_id(result) or state.get("at_job")
    state["at"] = when_epoch
    try:
        write_record(sdir, state.get("session_id"), state)
    except OSError:
        pass


def _run(cmd):
    """Run `cmd` and answer only "did it exit 0?". A launch failure counts as no."""
    try:
        return subprocess.run(cmd, capture_output=True, timeout=60).returncode == 0
    except Exception:
        return False


def do_cancel(sdir, quiet=False, all_jobs=False, session_id=None):
    """Cancel the scheduled resume. 0 when nothing is left to fire, non-zero when it is.

    ⛔ THE THREE OUTCOMES, AND WHY TWO OF THEM MUST NOT BE MERGED. `schtasks /Delete` exits
    non-zero when it REFUSES and equally when the task IS NOT THERE, and the two demand
    opposite handling:

      not there  - there is nothing to fire, so the record must GO. This is also the
                   documented repair for an orphan record (`--status` says "re-arm it, or
                   `resume.py --cancel` to clear the record"), and treating it as a refusal
                   made that repair impossible: the record could never be cleared by the one
                   command named for clearing it.
      refused    - the job is still registered and WILL fire, so the record must STAY.
                   Removing it made the plugin forget a task the OS still holds, and the
                   gate then told the user nothing would wake later to redo the work.
      deleted    - the record goes, and the promise is true.

    ⭐ So Windows asks first. `schtasks /Query /TN` is the same probe --status already uses.

    ⛔ POSIX USED TO RUN `atrm -a` HERE, AND THAT DELETED JOBS THIS PLUGIN NEVER CREATED.
    `at` has no named jobs, so "cancel the resume" was implemented as "cancel everything the
    user has scheduled" - on every automatic stand-down, not only when somebody asked. ⇒ The
    job NUMBER is now recorded at arm time (at_job_id) and only that job is removed.

    ⚠ `atrm -a` is not gone, it is behind `--cancel --all`. Removing it outright would leave
    a state this docstring already rejects: an alarm armed before the number was recorded -
    or by an `at` that announced none - would be one NOBODY CAN EVER CLEAR, and
    stand_down_resume could never retire it. So the blunt instrument stays available to a
    person who asks for it by name, and never fires on an automatic path. ADR
    20260917-132015, D7 ⟨R2 I-N12⟩.

    ⇒ On POSIX with no recorded number the answer is the REFUSED outcome, not the deleted
    one: the record stays, the caller hears "something may still fire", and the message says
    which command clears it. Claiming success there would be the one lie this function's
    three outcomes exist to prevent.
    """
    legacy_at = False
    record = record_path(sdir, session_id)
    tname = task_name(sdir, session_id)
    if os.name == "nt":
        registered = _run(["schtasks", "/Query", "/TN", tname])
        if registered:
            gone = _run(["schtasks", "/Delete", "/TN", tname, "/F"])
        else:
            gone = True                       # nothing to fire; see the docstring
    elif all_jobs:
        _run(["atrm", "-a"])                  # asked for by name; see the docstring
        registered, gone = False, True
    else:
        state = usage.read_json(record, {}) or {}
        job = state.get("at_job")
        if job:
            registered = True
            gone = _run(["atrm", str(job)])
        else:
            registered, gone, legacy_at = True, False, True

    if gone:
        try:
            os.remove(record)
        except OSError:
            pass
    if not quiet:
        if legacy_at:
            print("⛔ this alarm carries no `at` job number, so it cannot be cancelled ONE")
            print("   job at a time, and the record was KEPT - it may still fire. It was")
            print("   armed before the number was recorded, or `at` announced none.")
            print("   ⚠ `resume.py --cancel --all` clears it, by removing EVERY `at` job")
            print("   this user has - including jobs this plugin never created.")
        elif not registered:
            print("nothing registered to cancel - any record was cleared")
        elif gone:
            print("cancelled")
        else:
            print("⛔ the task is registered and could NOT be deleted, so the record was KEPT.")
            print("   It may still fire. Check with `resume.py --status`; the task is")
            print("   named %s." % tname)
    log_line("CANCELLED" if gone else "CANCEL-REFUSED")
    # ⛔ 0 means nothing is left to fire. The gate says "nothing will wake later to redo it"
    # only on a 0, so this return value carries a promise and must be earned.
    return 0 if gone else 1


def stale_alarm_note(sdir, cfg, state):
    """One line: is this alarm still aimed at a reset that still exists?

    ⭐ WHAT THIS CATCHES, and it is the ONLY thing that catches it: THE ACCOUNT CHANGED
    DURING THE WAIT. Neither `~/.claude/.credentials.json` nor the usage endpoint carries
    any account identifier - measured 2026-08-26, both hold only tokens, scopes, plan type
    and numbers - so there is nothing to fingerprint. What IS visible is that the stored
    reset instant moved while the armed one had not yet arrived, and only a different
    account explains that.

    ⛔ WHY IT IS CONDITIONAL ON `now < armed_for_reset`. Past the reset the stored value
    moves on legitimately - the statusline re-fetches every 120-150 s, so by the time the
    alarm fires at reset+offset the record has usually advanced a whole window. Comparing
    then would warn on the healthy path, and a warning that fires when nothing is wrong is
    a warning nobody reads.

    ⚠ Deliberately NOT also checked inside do_run() for that same reason. do_run re-reads
    the verdict on every fire, so correctness does not depend on this line; it exists for a
    PERSON who is deciding whether their armed resume still means anything.
    """
    armed = state.get("armed_for_reset")
    if not isinstance(armed, (int, float)):
        return "reset     : not recorded (armed with --at, so there is nothing to compare)"
    if time.time() >= armed:
        return ("reset     : %s - already passed, so a moved stored value is normal now"
                % time.strftime("%H:%M", time.localtime(armed)))
    current, _which = reset_time(sdir, cfg)
    if current is None:
        return ("reset     : armed for %s; CANNOT COMPARE - no usage data on disk. Run "
                "`usage.py --fetch-now` if the answer matters."
                % time.strftime("%H:%M", time.localtime(armed)))
    if abs(current - armed) <= 1:
        return "reset     : armed for %s, still the current one" % time.strftime(
            "%H:%M", time.localtime(armed))
    # ⚠ chr(10) rather than an escape, matching the rest of this plugin: these files are
    # patched by scripts often enough that a literal backslash-n has been mangled before.
    return (chr(10).join([
        "reset     : ⛔ STALE - armed for %s but the stored reset is now %s,",
        "            and the armed one has NOT passed yet.",
        "            The usual cause is a DIFFERENT ACCOUNT signed in during the wait.",
        "            ⭐ If you already carried the work on yourself, run `--cancel`. The",
        "            alarm would otherwise fire at a moment that means nothing, find no",
        "            recent session, and redo work you have already done."])
            % (time.strftime("%H:%M", time.localtime(armed)),
               time.strftime("%H:%M", time.localtime(current))))


def do_status(sdir, cfg):
    """Report EVERY armed resume in this state directory, not just one.

    ⛔ ONE LINE PER SESSION, because there can now be several and a report that shows one
    is a report that hides the rest. ADR 20260917-132015, D8.
    """
    records = record_paths(sdir)
    legacy = os.path.join(sdir, LEGACY_RECORD)
    if os.path.exists(legacy):
        print("⚠ A pre-0.60 record is still at %s and carries no session id, so it could" % legacy)
        print("  not be renamed automatically. Its OS task is named %s." % TASK_NAME)
        print("  Re-arm the task it names, or `resume.py --cancel` to clear it.")
        print()
    if not records:
        print("no resume armed")
        return 1
    for i, rec in enumerate(records):
        if i:
            print()
        if len(records) > 1:
            print("== %s" % os.path.basename(rec))
        _status_one(sdir, cfg, usage.read_json(rec, {}) or {})
    return 0


def _status_one(sdir, cfg, state):
    print("task     : %s" % state.get("task"))
    print("handoff  : %s" % state.get("handoff"))
    print(origin_session_note(sdir, state))
    tr = state.get("transcript")
    print("transcript: %s" % (("%s (%.1f MB, a FALLBACK the run may read parts of)"
                               % (tr, os.path.getsize(tr) / 1048576.0))
                              if tr and os.path.exists(tr) else "none recorded"))
    print("fires at : %s" % time.strftime("%Y-%m-%d %H:%M", time.localtime(state.get("at", 0))))
    print("armed at : %s" % time.strftime("%Y-%m-%d %H:%M", time.localtime(state.get("armed_at", 0))))
    print(stale_alarm_note(sdir, cfg, state))
    rc_ = rcfg(sdir)
    print("attempts : %d so far" % state.get("attempts", 0))
    print("retrying : every %d min, for up to %d min from the first attempt"
          % (rc_["retry_every_min"], rc_["retry_window_min"]))
    print()
    print("⚠ This reports what was REGISTERED, not that it will succeed. The schedule is")
    print("  removed only after a run exits cleanly; a failure, or a window that had not")
    print("  actually reset, re-arms it. When the window above runs out it stops for good")
    print("  and leaves a marker the NEXT Claude session reads out loud, so a resume that")
    print("  gave up at 03:40 does not stay silent. RESUME lines in")
    print("  .claude/dispatch_gate.log say which happened.")
    return 0


def main():
    argv = sys.argv[1:]
    sdir = usage.state_dir(argv)
    cfg = usage.config(sdir)
    # ⛔ MIGRATION RUNS ONLY FOR A COMMAND THAT READS RECORDS, NEVER AT THE TOP OF main().
    # It was at the top for one revision, and that gave every invocation a side effect on
    # the REAL state directory - `--selftest`, a typo, `--help`, anything. Measured
    # immediately: `resume.py --selftest`, run by the checks with no `--dir`, migrated a
    # LIVE armed record of the person's and wrote a MIGRATED line into their log.
    # ⚠ A command that changes nothing must change nothing; this repository has the same
    # warning written on `schedule()`, about a builder with a side effect.
    def migrated():
        migrate_legacy(sdir)
        return True

    if "--run" in argv and migrated():
        return do_run(sdir, cfg, arg(argv, "--session"))
    if "--cancel" in argv and migrated():
        # ⚠ `--all` is the POSIX blunt instrument, and it is opt-in for that reason: it
        # removes every `at` job this user has. See do_cancel's docstring.
        # ⛔ A BARE `--cancel` STILL CLEARS EVERYTHING IN THIS DIRECTORY, and it has to:
        # it is the documented repair in `install.py --status`, in do_cancel's own
        # docstring and in the README, and quietly narrowing it to one session would leave
        # the other records with no command named for clearing them.
        # ADR 20260917-132015, D8 ⟨round 2, I-N3⟩.
        sid = arg(argv, "--session")
        if sid:
            return do_cancel(sdir, all_jobs="--all" in argv, session_id=sid)
        rc = 0
        records = record_paths(sdir)
        if not records:
            return do_cancel(sdir, all_jobs="--all" in argv)
        for rec in records:
            state = usage.read_json(rec, {}) or {}
            print("-- %s" % os.path.basename(rec))
            rc |= do_cancel(sdir, all_jobs="--all" in argv,
                            session_id=state.get("session_id") or
                            os.path.basename(rec)[:-len(".json")])
        return rc
    if "--status" in argv and migrated():
        return do_status(sdir, cfg)
    if "--arm" in argv and migrated():
        return do_arm(argv, sdir, cfg)
    print(__doc__.strip().splitlines()[0])
    print("Usage: resume.py --arm --task <folder> [--at HH:MM] [--dry-run] | --status"
          " | --cancel [--all]")
    return 2


def _utf8_console():
    """Make output survive a legacy console codepage.

    ⛔ Windows consoles default to a legacy codepage - cp950 on this machine - and a
    single non-ASCII character in a message then raises UnicodeEncodeError and kills the
    script. Measured 2026-08-26: install.py wrote its file and THEN crashed on the very
    warning explaining what to do next, so the user saw a traceback instead of the
    instruction. errors="replace" is deliberate: a mangled glyph is a cosmetic problem,
    a crash is not.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


if __name__ == "__main__":
    _utf8_console()
    sys.exit(main())
