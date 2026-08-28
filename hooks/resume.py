#!/usr/bin/env python3
"""Arm a one-shot resume for after the usage window resets.

    resume.py --arm --task <folder> [--at HH:MM] [--dry-run]
    resume.py --status
    resume.py --cancel
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
HANDOFF = "HANDOFF.md"
MIN_HANDOFF_CHARS = 200          # below this it is a placeholder, not a work order
# All three are overridable in config.json. Retrying is bounded by TIME, not by a
# count: "keep trying for two hours, every twenty minutes" is a thing a person can
# reason about, whereas "three attempts" hides how long that actually covers.
RESUME_DEFAULTS = {
    "resume_offset_min": 3,      # how long AFTER the reset to fire
    "retry_window_min": 120,     # keep retrying for this long, then stop for good
    "retry_every_min": 20,       # how often to retry inside that window
}
FAILED_MARKER = "resume_failed.json"
# A session the gate touched within this many minutes counts as live, so the scheduled
# route stands down and lets the session-wake route do the work.
ALIVE_WITHIN_MIN = 30


def log_line(message):
    """Append to the gate log in the current repository, and to a fallback."""
    line = "%s RESUME %s%s" % (time.strftime("%Y-%m-%d %H:%M:%S"), message, "\n")
    for path in (os.path.join(os.getcwd(), ".claude", "dispatch_gate.log"),):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
            return
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


def announce_failure(sdir, why):
    """Leave a marker the next session will READ OUT LOUD.

    ⛔ A scheduled task has nowhere to put a message. It runs with no terminal, no
    window and nobody watching, so a resume that gives up would otherwise be
    indistinguishable from a resume that was never armed - and from the outside, from
    the work simply not having been needed. This marker is picked up by the plugin's
    SessionStart hook, which tells the agent, which tells the person. ⚠ That is the only
    path from "it failed at 03:40 while you were asleep" to somebody knowing.
    """
    try:
        with open(os.path.join(sdir, FAILED_MARKER), "w", encoding="utf-8") as f:
            json.dump({"at": time.time(), "why": why}, f)
    except OSError:
        pass
    log_line("GAVE-UP %s" % why)


def session_alive_minutes(sdir, session_id=None):
    """How long ago was a session last active, in minutes? None if never seen.

    ⚠ WITHOUT `session_id` THIS MEANS "ANY SESSION", and do_run() deliberately keeps it
    that way. Standing down because SOMEBODY is at the keyboard is the safe answer even
    when it is not the session that armed the resume - a headless run starting underneath
    a working person is worse than a resume they can trigger themselves.

    ⭐ WITH one, it answers the narrower question a PERSON asks: is the session I armed
    this from still there, so can I just carry on in it? Only --status asks that.

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
    """When the current window turns over, as epoch seconds, or None."""
    data = usage.read_json(cfg["token_usage_file"], {}) or {}
    five = data.get("five_hour") or {}
    r = five.get("resets_at")
    return r if isinstance(r, (int, float)) else None


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


def arming_session(sdir):
    """(session_id, transcript path or None) for the session arming this resume.

    ⭐ NOTHING NEW IS PLUMBED FOR THIS. The gate already stamps `<session-id>.alive` on
    every hook event, so the session id is the FILENAME of the newest one - and `--arm` is
    itself run from inside a session that just fired hooks, so the newest is this one.

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
    return out


def schedule(when, dry_run):
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
    inner = shim.command(sdir, "resume.py", "--run")
    if os.name == "nt":
        cmd = ["schtasks", "/Create", "/TN", TASK_NAME, "/SC", "ONCE",
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
    if problem:
        print("⛔ Cannot arm a resume: %s" % problem)
        print("   Expected: %s" % (path or "<task folder>/" + HANDOFF))
        print()
        print("   Write it FIRST, and write it to stand alone - the run that reads it has")
        print("   none of this session's context. State what is done, what is not, what")
        print("   was tried and failed, and the exact next step.")
        return 2

    for w in handoff_warnings(path):
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
        r = reset_time(sdir, cfg)
        if not r:
            print("⛔ No reset time available, so there is nothing to schedule against.")
            print("   Either usage data is missing (run install.py --status) or pass --at.")
            return 2
        armed_reset = r
        when_epoch = r + rcfg(sdir)["resume_offset_min"] * 60   # past the reset, not on it

    when = time.localtime(when_epoch)
    dry = "--dry-run" in argv
    cmd, result = schedule(when, dry)

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
        with open(os.path.join(sdir, "resume.json"), "w", encoding="utf-8") as f:
            sid, transcript = arming_session(sdir)
            json.dump({"task": folder, "handoff": path, "at": when_epoch,
                       "armed_at": time.time(), "session_id": sid,
                       "transcript": transcript, "armed_for_reset": armed_reset}, f)
        print("status        : ARMED (this is the BACKUP route - see below)")
        log_line("ARMED task=%s at=%s" % (folder, time.strftime("%Y-%m-%d %H:%M", when)))
    else:
        detail = getattr(result, "stderr", b"") or b""
        print("status        : ⛔ FAILED - %s" % (detail.decode("utf-8", "replace").strip()
                                                  or repr(result)))
        log_line("ARM-FAILED task=%s" % folder)
    print()
    if ok:
        print_route_a_reminder(when)
    print()
    print("⚠ Armed is not the same as will-work. Whether `claude` is on PATH for the")
    print("  scheduler's user, whether the machine is awake, and whether credentials are")
    print("  still valid are all unknown until it fires.")
    return 0 if ok else 1


def do_run(sdir, cfg):
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
    state = usage.read_json(os.path.join(sdir, "resume.json"), {}) or {}
    path = state.get("handoff")
    if not path or not os.path.exists(path):
        log_line("RUN-ABORT no handoff recorded")
        return 1

    rc_ = rcfg(sdir)

    # ⭐ Stand down if a live session already picked the work back up.
    # ⚠ "Recently active", NOT "active since the window reopened": resets_at names the
    # NEXT reset, so deriving the reopening from it is arithmetic that is easy to get
    # backwards - a first version did exactly that, compared against a future timestamp,
    # and the check never fired. Recency is what the question actually reduces to.
    alive = session_alive_minutes(sdir)
    if alive is not None and alive < ALIVE_WITHIN_MIN:
        do_cancel(sdir, quiet=True)
        log_line("RUN-SKIPPED a Claude session was active %.0f min ago (< %d), so somebody "
                 "is already awake - standing down rather than running the work twice"
                 % (alive, ALIVE_WITHIN_MIN))
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
        do_cancel(sdir, quiet=True)
        announce_failure(sdir, "usage still said STOP for the whole %d-minute retry "
                               "window after %d attempts, so the resume never ran"
                               % (rc_["retry_window_min"], attempts))
        return 1

    os.chdir(state.get("task") or os.path.dirname(path))
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
    prompt = ("The usage window has reset, so treat usage as fresh. Read %s and continue "
              "that work, following its instructions exactly.%s Append a '## Result %s' "
              "section to %s describing what you did and anything still open. "
              "Do not re-verify usage limits before starting - the stored numbers read "
              "stale-high until a statusline renders."
              % (path, extra, time.strftime("%Y-%m-%d %H:%M"), path))
    log_line("RUN starting for %s (attempt %d)" % (path, attempts))
    try:
        r = subprocess.run(["claude", "-p", prompt], capture_output=True, timeout=3 * 3600)
        rc = r.returncode
        log_line("RUN finished rc=%s" % rc)
    except Exception as exc:
        rc, r = -1, None
        log_line("RUN-FAILED %r" % (exc,))

    if rc == 0:
        do_cancel(sdir, quiet=True)   # ⭐ removed only on a clean exit
        log_line("RUN-OK schedule removed")
        return 0
    detail = (getattr(r, "stderr", b"") or b"").decode("utf-8", "replace").strip()[:150]
    if not exhausted:
        log_line("RUN-RETRY rc=%s (attempt %d), again in %d min. %s"
                 % (rc, attempts, rc_["retry_every_min"], detail))
        _rearm(sdir, state, rc_["retry_every_min"])
        return 1
    do_cancel(sdir, quiet=True)
    announce_failure(sdir, "the resume failed %d times over %d minutes and has stopped "
                           "trying - it is yours to handle now. Last error: %s"
                           % (attempts, rc_["retry_window_min"], detail or "rc=%s" % rc))
    return 1


def _rearm(sdir, state, minutes):
    """Push the one-shot schedule out by `minutes`, keeping the attempt count."""
    when_epoch = time.time() + minutes * 60
    schedule(time.localtime(when_epoch), False)
    state["at"] = when_epoch
    try:
        with open(os.path.join(sdir, "resume.json"), "w", encoding="utf-8") as f:
            json.dump(state, f)
    except OSError:
        pass


def _run(cmd):
    """Run `cmd` and answer only "did it exit 0?". A launch failure counts as no."""
    try:
        return subprocess.run(cmd, capture_output=True, timeout=60).returncode == 0
    except Exception:
        return False


def do_cancel(sdir, quiet=False):
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

    ⚠ POSIX cannot make the distinction and does not pretend to: `at` has no named jobs, so
    `atrm -a` cannot be asked about one. There, a failure is treated as "nothing there" -
    the old behaviour - because the alternative is a record nobody can ever clear.
    """
    if os.name == "nt":
        registered = _run(["schtasks", "/Query", "/TN", TASK_NAME])
        if registered:
            gone = _run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
        else:
            gone = True                       # nothing to fire; see the docstring
    else:
        _run(["atrm", "-a"])                  # best effort; see the docstring
        registered, gone = False, True

    if gone:
        try:
            os.remove(os.path.join(sdir, "resume.json"))
        except OSError:
            pass
    if not quiet:
        if not registered:
            print("nothing registered to cancel - any record was cleared")
        elif gone:
            print("cancelled")
        else:
            print("⛔ the task is registered and could NOT be deleted, so the record was KEPT.")
            print("   It may still fire. Check with `resume.py --status`; the task is")
            print("   named %s." % TASK_NAME)
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
    current = reset_time(sdir, cfg)
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
    state = usage.read_json(os.path.join(sdir, "resume.json"), None)
    if not state:
        print("no resume armed")
        return 1
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
    if "--run" in argv:
        return do_run(sdir, cfg)
    if "--cancel" in argv:
        return do_cancel(sdir)
    if "--status" in argv:
        return do_status(sdir, cfg)
    if "--arm" in argv:
        return do_arm(argv, sdir, cfg)
    print(__doc__.strip().splitlines()[0])
    print("Usage: resume.py --arm --task <folder> [--at HH:MM] [--dry-run] | --status | --cancel")
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
