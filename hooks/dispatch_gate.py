#!/usr/bin/env python3
"""Dispatch gate - enforces the sub-task dispatch protocol, and brakes on usage.

Registered in settings.json for SessionStart, UserPromptSubmit, PreToolUse and
PostToolUse. Reads one hook payload as JSON on stdin, writes a hook response on stdout.

  SessionStart     stamp the session; print the protocol pointer into context.
  UserPromptSubmit inject a wind-down instruction once usage crosses soft/hard.
  PreToolUse
      Workflow     deny - it spawns many agents at once by construction.
      Agent        deny if usage says STOP;
                   deny a background dispatch;
                   deny if no dispatch plan was written in this session;
                   deny once the concurrency slots are full;
                   otherwise PREPEND the protocol to the sub-task's prompt.
  PostToolUse
      Agent        release this dispatch's slot.

⭐ WHY THE USAGE BRAKE LIVES ON THE DISPATCH, not only in an advisory message:
dispatching a sub-task is the single most expensive thing an agent does - a sub-agent
reads its own context and its report is read back, so one dispatch can cost more than
a long stretch of ordinary work. Refusing THAT at the hard threshold is a real brake.
An injected "please wind down" is advice the model may weigh against its task; a
refused tool call is not.

PORTABLE BY DESIGN. Nothing here names a particular project. Paths, thresholds and the
protocol document all come from config.json, and every one has a default that works in
a repository that has never seen this skill. Copy the folder, run install.py, done.

Standard library only. No pip install, no npm install, nothing to vendor.

THREE DESIGN DECISIONS THAT ARE EASY TO MISREAD
-----------------------------------------------

1. A session with no start stamp is ADVISORY ONLY - logged and prepended, never
   denied. A session that began before this gate was installed has no stamp, and
   policing it would refuse dispatches for a plan file it had no way to know it
   needed. Enforcement begins with the NEXT session, never mid-flight in one already
   running - which also means installing this cannot disrupt a colleague's live work.

2. A background dispatch is REFUSED rather than counted. PostToolUse fires when the
   tool call RETURNS, which for a background dispatch is at launch, so its slot would
   free while the sub-task was still alive and any number could pile up behind it. No
   hook event fires when a background sub-task finishes, so counting is not merely
   hard - it is impossible. The cost, stated plainly: an approved concurrency runs as
   BATCHES of N rather than as a rolling window that refills as each finishes.

3. The gate FAILS OPEN on its own errors. A broken gate that refused every dispatch
   would be worse than the rule it enforces. ⚠ The price is that an absent denial is
   not proof the gate ran - which is why every decision is logged and every error is
   written to the log the documentation points at.
"""

import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmd_guards  # noqa: E402  - the silent-failure guards; see its docstring
import usage  # noqa: E402  - same folder, stdlib-only, no install step

# Candidate markers for "this is the repository root", tried in order.
REPO_MARKERS = ("CLAUDE.md", "AGENTS.md", ".git")

# ⭐ THE DECLARED TASK ROOT. Task folders live in <repo>/Memory/tasks, and the gate
# CREATES it at SessionStart - see ensure_task_root() for why creating beats waiting.
# Override it with `dispatch.task_root` in config.json or in
# <repo>/.claude/dispatch-guard.json; it is relative to the repository root.
TASK_ROOT = "Memory/tasks"
# ⚠ COMPATIBILITY ONLY, and consulted only while task_root is unset: a repository that
# ALREADY keeps task folders in one of these keeps using it, so installing this plugin
# does not strand work already on disk under a second convention. First that exists wins;
# a repository with none of them gets TASK_ROOT.
TASK_ROOTS = (TASK_ROOT, ".agent-tasks", "tasks")

DEFAULTS = {
    "task_root": None,                  # unset -> an existing TASK_ROOTS entry, else TASK_ROOT
    "plan_glob": "prompts*.md",
    "approval_glob": "PARALLEL-APPROVED*",
    "protocol_doc": "PROTOCOL.md",
    "max_slots": 16,
    "slot_ttl_min": 30,
    "approval_ttl_min": 60,             # a concurrency approval expires; see approved_slots
    "brake_on_usage": True,             # deny a dispatch when the verdict is STOP
    "warn_on_usage": True,              # attach a note when the verdict is PACE
    # ⭐ ON BY DEFAULT: write the watcher task unless doing so would CONFLICT with something.
    # ⛔ It used to be off, and being off made the feature undiscoverable. The hook's only way
    # in was a SessionStart message - and that goes into a MODEL's context, not onto a screen
    # - so on a clean install the task simply never appeared and nothing said why. Measured
    # twice, on two clean installs.
    # ⇒ The protection lives in the CONFLICT TESTS now, not in a default that hides the
    # feature: auto_task_reason() refuses outside VS Code, and maybe_install_vscode_task()
    # refuses on a tracked tasks.json or one that exists but cannot be parsed. Both are
    # REPORTED rather than overwritten. Set false to keep it out of your projects entirely.
    "auto_vscode_task": True,
    # ⭐ ON by default, and only ever into an EMPTY slot. The line is what this plugin is
    # for, an empty statusLine means nothing is displaced, and --uninstall takes it back
    # out. A slot somebody else owns is never touched. Set false to keep the slot empty.
    "auto_statusline": True,
    # ⭐ THE MOST A SUB-AGENT'S MODEL MAY COST: US dollars per million INPUT tokens, compared
    # against the catalog's published `pricing` tier (see MODEL_PRICES). 5 allows haiku ($1),
    # sonnet ($2-3) and the current opus ($5); it refuses fable ($10) and the retired
    # opus-4-0/4-1 ($15). null switches the check off.
    #
    # ⛔ A NUMBER RATHER THAN A MODEL NAME, and the reason is that a name goes stale while a
    # number does not. `"opus"` meant $15 in 2025 and means $5 now - so a ceiling written as a
    # name silently changes what it permits when a family is repriced, which is the one thing a
    # cost limit must never do. A name is still ACCEPTED and priced, because it is what a hand
    # reaches for, but the documented form is the number.
    #
    # ⇒ AND THE SAME LIMIT IS WRITTEN INTO `dispatch-protocol`, so an agent reads it BEFORE
    # choosing a model rather than meeting it as a refusal afterwards. A rule an agent only
    # ever meets as a refusal is a rule it tries to route around; Tools/Debug/test_guards.py
    # asserts the skill's table and this table have not drifted apart.
    "max_model_price": 5,
}

# ⭐ ONE CONFIG READER, TWO FAMILIES. Merging the guard switches into DEFAULTS gives them
# gate_config()'s whole resolution chain for nothing: the state config.json, the per-project
# .claude/dispatch-guard.json, and the `dispatch` sub-block. ⛔ They stay SEPARATE KEYS
# rather than one `guards: true` - somebody will want the dispatch gate without the git gate,
# and a switch that turns off seven things at once is a switch nobody dares touch.
DEFAULTS.update(cmd_guards.GUARD_DEFAULTS)

# The ONLY forms that state a concurrency count. ⛔ Do NOT relax this to "the first
# integer you find": records are conventionally written starting with a date, so
# "2026-08-26 approved 2" would parse as 2026 and be clamped UP to max_slots - the
# owner would have said two and been given sixteen. Measured defect, 2026-08-26.
APPROVAL_FORMS = (r"平行\s*(\d{1,2})\b", r"\bN\s*=\s*(\d{1,2})\b",
                  r"\bparallel\s*[:=]?\s*(\d{1,2})\b")

# ⭐ EVERY NUMBER HERE IS PUBLISHED DATA: the `pricing` field on each entry of the shipped
# model catalog, which reads `tier_<input>_<output>` in US dollars per million tokens. Copied
# verbatim, one row per model.
#
# ⛔ WHY PER MODEL AND NOT PER FAMILY, which is what this used to do. Because a family is not
# one price. `claude-opus-4-0` is tier_15_75 and `claude-opus-5` is tier_5_25 - the same family,
# THREE TIMES the input price - and `claude-sonnet-5` (tier_2_10) is CHEAPER than
# `claude-sonnet-4-6` (tier_3_15). A family-level ladder calls those equal and is simply wrong
# about the thing it claims to measure.
#
# ⛔ AND WHY IT IS COPIED RATHER THAN INFERRED. The previous version gave `mythos` a weight of
# 10 by reasoning from `advisor_rank`, in a file whose own comments said not to invent numbers.
# The catalog's `pricing` field was there the whole time and needed no reasoning at all. The
# number turned out to be right - claude-mythos-5 IS tier_10_50 - which is exactly what makes
# the method the problem rather than the value.
#
# ⚠ HAIKU IS THE ONE EXCEPTION AND IT IS MARKED. Its catalog `pricing` is the opaque label
# `haiku_45` / `haiku_35`, not a `tier_x_y` string, so those two rows come from the harness's
# own weight function instead (`if(n.includes("haiku")) return 1`). Same source as before, and
# the only rows here that are not the published tier.
#
# ⇒ To refresh: Memory/tasks/.../scratch/07-model-facts/probe_pricing.py prints this table.
MODEL_PRICES = (
    ("claude-opus-4-0", 15), ("claude-opus-4-1", 15),          # tier_15_75
    ("claude-opus-4-5", 5), ("claude-opus-4-6", 5),            # tier_5_25
    ("claude-opus-4-7", 5), ("claude-opus-4-8", 5),
    ("claude-opus-5", 5),
    ("claude-3-5-sonnet", 3), ("claude-3-7-sonnet", 3),        # tier_3_15
    ("claude-sonnet-4-0", 3), ("claude-sonnet-4-5", 3),
    ("claude-sonnet-4-6", 3),
    ("claude-sonnet-5", 2),                                    # tier_2_10
    ("claude-fable-5", 10), ("claude-mythos-5", 10),            # tier_10_50
    ("claude-haiku-4-5", 1), ("claude-3-5-haiku", 1),          # ⚠ not tier_; see above
)

# ⭐ WHAT A BARE FAMILY ALIAS ACTUALLY GETS, from the catalog's `latest_per_family`. `opus`
# resolves to claude-opus-5, so it is priced as claude-opus-5 - not as the most expensive opus
# that ever existed. ⛔ `mythos` IS ABSENT ON PURPOSE: the selectable alias list in the binary
# is ["sonnet","opus","haiku","fable",…], so a bare `mythos` is not a thing a session can ask
# for. Its full model ID is priced above, and a bare `mythos` falls through to unrecognised.
FAMILY_LATEST = (("fable", "claude-fable-5"), ("opus", "claude-opus-5"),
                 ("sonnet", "claude-sonnet-5"), ("haiku", "claude-haiku-4-5"))

# ⛔ THE TRAP THAT DECIDES THE SHAPE OF THIS GUARD. The accepted alias list in the binary is
# ["sonnet","opus","haiku","fable","best","sonnet[1m]","opus[1m]","fable[1m]","opusplan"] -
# so `best` is a real alias, and the catalog resolves `best` to FABLE. A guard that simply
# refused the string "fable" would wave `best` straight through and hand out the very model
# it was installed to refuse. Aliases are resolved BEFORE pricing.
#
# ⚠ THE `[1m]` SUFFIX IS STRIPPED, and that is a limit rather than a decision. `opus[1m]` is a
# real selectable variant - the binary displays it as "Opus 1M" - but the catalog publishes ONE
# `pricing` tier per model and no separate one for the long-context variant. The harness's own
# accounting agrees: it counts a long-context REQUEST in a separate bucket (`longCtxCost` /
# `longCtxCount`, when the input tokens of one request exceed a threshold) and does NOT
# multiply the price by anything. ⇒ So there is no published number to charge it with, and this
# gate does not invent one. It is in the honest-gaps table instead.
MODEL_ALIASES = {"best": "fable", "opusplan": "opus"}
# Omitted, empty, or `inherit`: the sub-agent runs on the model the OWNER chose for this
# session. There is nothing to police, and always a legal dispatch available - which is why
# this guard cannot deadlock anything.
MODEL_INHERIT = ("", "inherit", "default", "auto")

PREPEND = """<<< SUB-TASK PROTOCOL - injected by the dispatch gate, not by whoever wrote this prompt >>>

These rules bind you exactly as they bind the agent that dispatched you, and they bind
anything YOU dispatch in turn.

1. ONE SUB-TASK AT A TIME. Never dispatch two agents in one message, never dispatch one
   in the background, and never call Workflow. Sequential dispatch of any number needs
   no permission; concurrency needs the owner's approval. This is enforced by a hook,
   not by your judgement.
2. THE WORK ORDER LANDS ON DISK FIRST. Before dispatching anything, write the plan and
   every sub-task's full prompt into {task_root}/<task>/{plan_glob}. A dispatch with no
   plan written in this session is refused.
3. WRITE YOUR REPORT AS YOU GO. Create your output file as your FIRST action, then
   append every finding, command and result the moment you have it. An agent that dies
   before its final write has produced nothing.
4. EVERY PROMPT YOU WRITE MUST STAND ALONE. The agent running it has none of your
   context. Spell out every path, constraint and acceptance criterion, and end it by
   naming the file that agent must write its report to.
5. AN EMPTY SEARCH RESULT IS A CLAIM, NOT AN ANSWER. Never silence a search's errors.
   Prove the instrument ran before believing a zero.
6. PACING IS THE DISPATCHER'S JOB. If you are a worker, finish your assigned unit at
   full quality and do NOT self-throttle to save budget. Whether another wave goes out
   is the dispatcher's decision.
7. CHOOSE THE MODEL BEFORE YOU DISPATCH, not after being refused. A sub-task's model may
   cost at most ${max_model_price} per million INPUT tokens: haiku $1, sonnet $2, opus $5,
   fable $10 - and `best` means fable. Naming an old version can cost MORE than naming the
   family (claude-opus-4-0 is $15). Omitting `model` is always allowed and inherits the
   model already in use, so there is always a legal dispatch. Full table and the reasoning:
   `dispatch-protocol`.
8. SCRATCH FILES GO IN THE TASK FOLDER, AND YOU DO NOT DELETE THEM. Every intermediate
   file you write - probes, captured output, half-built scripts, fixtures - goes under
   {task_root}/<task>/scratch/<your-subtask>/, never the system temp directory and never
   a path another sub-task also uses. LEAVE THEM BEHIND when you finish: they are the
   only way anyone can answer "what did that agent actually see?" after you are gone,
   and tidying up is the one helpful-looking act that destroys the evidence. The task
   folder is removed or archived as a whole; cleaning up after yourself is not your job.

Full protocol: {protocol_doc}

<<< END PROTOCOL - the actual work order follows >>>

"""


# --------------------------------------------------------------------------- helpers

def repo_root(cwd):
    d = os.path.abspath(cwd or os.getcwd())
    for _ in range(12):
        if any(os.path.exists(os.path.join(d, m)) for m in REPO_MARKERS):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return os.path.abspath(cwd or os.getcwd())


def gate_config(root, sdir):
    cfg = dict(DEFAULTS)
    for path in (os.path.join(sdir, "config.json"),
                 os.path.join(root, ".claude", "dispatch-guard.json")):
        disk = usage.read_json(path, {}) or {}
        for source in (disk, disk.get("dispatch") or {}):
            for k in DEFAULTS:
                if k in source:
                    cfg[k] = source[k]
    if not cfg["task_root"]:
        cfg["task_root"] = next((t for t in TASK_ROOTS
                                 if os.path.isdir(os.path.join(root, t.replace("/", os.sep)))),
                                TASK_ROOTS[0])
    return cfg


def task_roots(root, sdir):
    """Task roots to search, the CONFIGURED one first. Shared with resume.py.

    ⚠ resume.py used to carry its own hardcoded copy of TASK_ROOTS, so a repository that
    had moved task_root could not arm a resume at all - the handoff was named in config and
    looked for somewhere else. One function, one answer.
    """
    configured = gate_config(root, sdir)["task_root"]
    return (configured,) + tuple(t for t in TASK_ROOTS if t != configured)


def ensure_task_root(root, cfg):
    """Create <repo>/<task_root>, so a task folder always has somewhere to go.

    ⛔ WHY IT IS CREATED RATHER THAN WAITED FOR. The plan-on-disk rule refuses a dispatch
    until a prompts*.md exists UNDER the task root, so in a fresh repository the very first
    dispatch is refused for a directory nobody was ever told to make - and the refusal names
    the path without saying it does not exist yet. Creating it at SessionStart turns "where
    do task files go?" into a question whose answer is already on disk.

    ⚠ It is empty and inert until a task folder is made inside it, and it is created under
    the REPOSITORY root, never under the state directory: these are the project's work
    products, and they belong with the project.
    """
    path = os.path.join(root, cfg["task_root"].replace("/", os.sep))
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except OSError:
        return None                     # read-only tree; the gate must not break over it


def state_path(sdir, session_id, suffix):
    safe = "".join(c for c in str(session_id) if c.isalnum() or c in "-_")[:64] or "nosession"
    return os.path.join(sdir, "state", "%s.%s" % (safe, suffix))


def log(root, message):
    """⛔ Errors go here too. A compensating control nobody reads is not one."""
    try:
        path = os.path.join(root, ".claude", "dispatch-gate.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # ⛔ A bare newline here, NEVER os.linesep. Text mode already translates it
        # to the platform's ending on Windows, so adding os.linesep on top produces a
        # carriage return too many, and every record is followed by a blank line.
        # Measured 2026-08-26: every log this plugin wrote was double-spaced - the gate
        # log and the imported usage history alike.
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s %s%s" % (time.strftime("%Y-%m-%d %H:%M:%S"), message, "\n"))
    except Exception:
        pass


def newest(pattern):
    best = (None, None)
    for p in glob.glob(pattern):
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        if best[0] is None or m > best[0]:
            best = (m, p)
    return best


HERE = os.path.dirname(os.path.abspath(__file__))

# ⛔ HOW OFTEN THE GATE MAY FORK - a different question from how often the API may be
# called. usage.py's own claim bounds the CALLS. This bounds the PROCESSES, so a spell
# where every fetch fails - an expired token, a 429 - cannot start one child per tool call
# for the rest of the window.
CLOCK_MARK = "clock.spawn"


def clock_due(sdir, every, now):
    """Is a refresh due AND has one not just been started? Pure decision, no side effects.

    ⛔ Split out from keep_clock_running() so it can be CHECKED without spending an API
    call. The failure it guards against is silent and expensive: forget the second test and
    the gate forks a process per tool call for as long as the fetch keeps failing, which is
    exactly when it fails most - an expired token, or the 429 the fetch floor exists to
    avoid.

    ⚠ Two clocks, not one. `limits.json` says when the DATA went stale; the mark says when
    a child was last STARTED. Only the second one moves when a fetch fails, so only the
    second one can stop a failing fetch from being retried forever.
    """
    def age(name):
        try:
            return now - os.stat(os.path.join(sdir, name)).st_mtime
        except OSError:
            return None

    data = age("limits.json")
    if data is not None and data < every:
        return False
    started = age(CLOCK_MARK)
    if started is not None and started < every:
        return False
    return True


def keep_clock_running(sdir):
    """Start a DETACHED refresh when limits.json has gone stale, and never wait for it.

    ⭐ THIS IS WHAT MAKES THE BRAKE WORK WITH NO STATUSLINE. The numbers only ever moved
    when something re-ran usage.py on a timer: the statusline, which Claude Code renders,
    or `--watch` in a terminal. The VS Code extension renders no statusline, so an
    extension-only user had a brake that read NO-DATA forever unless they wired a per-project
    task. ⇒ The statusline and `--watch` are now DISPLAY. This is the clock.

    ⛔ IT IS NOT THE SYNCHRONOUS FETCH ensure_fresh() REFUSES TO DO, and the difference is
    the whole design. A blocking HTTP call here would stall every dispatch that crossed the
    interval boundary. This forks and returns; the number lands in limits.json for a LATER
    call to read. A dispatch is never made to wait on the network.

    ⭐ Why the gate is the right place: dispatch happens inside a session, this hook already
    runs on every tool call of every session, so the sessions that need a fresh number are
    exactly the ones already executing this code. Nothing new has to be installed, and
    nothing is per-project - `limits.json` is per-ACCOUNT, like the usage it records.

    ⚠ The child re-checks freshness itself and usually does nothing. That is deliberate:
    this function decides whether to FORK, usage.py decides whether to FETCH, and neither
    is allowed to assume the other got it right.

    Returns True when it started a child.
    """
    now = time.time()
    if not clock_due(sdir, usage.config(sdir)["fetch_seconds"], now):
        return False
    try:
        os.makedirs(sdir, exist_ok=True)
        with open(os.path.join(sdir, CLOCK_MARK), "w") as f:
            f.write(str(now))
    # ⛔ NOT `except OSError`. It was, and `now` was left unbound when the timestamp moved
    # into clock_due() - so every call raised NameError, which OSError does not catch. That
    # escaped into main() BEFORE the event branches, the top-level handler exited 0 with no
    # output, and a hook that prints nothing is a hook that APPROVED the call. The gate did
    # not brake, did not refuse a background dispatch, and did not check for a plan, in
    # every session where limits.json was stale. A clock is a convenience; it must never be
    # able to switch enforcement off, so nothing it can raise leaves this function.
    except Exception:
        return False

    # ⛔ Every handle goes to DEVNULL. A hook's stdout is a pipe Claude Code READS, and a
    # child that inherits it can hold the hook open long after the hook is done.
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
          "stderr": subprocess.DEVNULL, "cwd": sdir}
    if os.name == "nt":
        kw["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0x8)
                               | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200))
    else:
        kw["start_new_session"] = True
    try:
        # ⚠ --dir is not optional. usage.py resolves its own state directory from argv,
        # $CLAUDE_DISPATCH_DIR, then ~/.claude - so a child launched without it can write
        # to a DIFFERENT directory than the one this function just judged stale, and the
        # gate would fork forever while the data landed somewhere else.
        subprocess.Popen([sys.executable, os.path.join(HERE, "usage.py"),
                          "--fetch-now", "--dir", sdir], **kw)
    except Exception:
        return False
    return True


def runnable(script, root=False):
    """A command the model can actually RUN, not a bare path to a .py file.

    ⛔ The messages used to hand over `.../usage.py --verdict`. The hook scripts are not
    executable and carry no shebang association on either platform, so the one command the
    gate names as the repair for a blind brake did not run when it was pasted. Everything
    goes through run.sh, which is also how the interpreter is found - see the comment at the
    top of that file for why naming `python` directly is wrong on both platforms.
    """
    base = os.path.dirname(HERE) if root else HERE
    return 'bash "%s" "%s"' % (os.path.join(HERE, "run.sh").replace("\\", "/"),
                               os.path.join(base, script).replace("\\", "/"))


def _git_tracked(root, rel):
    """Is `rel` a file git already tracks in `root`? None when the question cannot be asked.

    ⛔ This is the one check that stops an opt-in convenience from becoming somebody else's
    problem. `.vscode/tasks.json` is commonly COMMITTED, and the task inside it names an
    absolute path on this machine, carrying this machine's plugin version. Rewriting a
    tracked file leaves the repository dirty and invites that path into a commit, where it
    hands the next person a task pointing at a directory they do not have.
    """
    try:
        r = subprocess.run(["git", "-C", root, "ls-files", "--error-unmatch", rel],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=10)
    except Exception:
        return None
    return r.returncode == 0


def auto_task_reason(root, cfg, env=None):
    """Why the watcher task must NOT be auto-installed here, or None to go ahead.

    ⭐ A REASON RATHER THAN A BOOLEAN, because every one of these is worth saying out loud
    once. Silent inaction and silent action are both wrong for something that writes into
    somebody's repository.

    ⚠ The VS Code test matters more than it looks. Without it, a plain CLI session in any
    project would drop a `.vscode/` directory into a repository that may never be opened in
    VS Code at all - a per-project file created for an editor nobody used here.
    """
    env = os.environ if env is None else env
    if not cfg.get("auto_vscode_task"):
        return "off"
    if not (env.get("CLAUDE_CODE_ENTRYPOINT", "").find("vscode") >= 0 or env.get("VSCODE_PID")):
        return "not running in VS Code"
    if not root or not os.path.isdir(root):
        return "no project directory"
    return None




def maybe_install_vscode_task(root, cfg, sdir=None):
    """Keep the watcher task correct - in VS Code's USER tasks file.

    Returns (context, screen): the first for the model, the second for the person. ⛔ A note
    that only reaches the model is a note that does not exist when the person has no usage
    left - and installing with an empty budget is the case that has to work.

    ⭐ ONE FILE, WRITTEN ONCE, FOR EVERY PROJECT. It used to be per-project, and that could
    never work on a first open: the file is created by a session, and a session starts after
    the folder is already open. So the first open of every NEW project had no task - not once
    per machine, once per project - and the file landed inside somebody's repository.

    ⚠ The environment test that the per-project form needed does not apply here. This is the
    person's own editor configuration, not their repository, and vscode_user_dirs() finds
    nothing at all unless a VS Code family editor is actually installed. `auto_vscode_task:
    false` is still honoured, because that is a decision somebody made.
    """
    if not cfg.get("auto_vscode_task"):
        return None, None
    try:
        sys.path.insert(0, os.path.dirname(HERE))
        import install                                  # the plugin root, beside hooks/
        # ⭐ THE USER-LEVEL TASK FIRST, and it is the whole feature now: one file, written
        # once, and every project has the watcher from its FIRST open. The per-project file
        # could never manage that - it is created by a session, and a session starts after
        # the folder is already open, so the first open of every new project missed it.
        if not install.vscode_user_task_current():
            lines = install.vscode_user_task()
            note = (" ⭐ The `Claude usage watch` task was added to VS Code's USER tasks, so "
                    "EVERY project gets the usage line from now on - there is no per-project "
                    "file and nothing was written into this repository. ⚠ It starts on the "
                    "next FOLDER OPEN. Details: %s" % "; ".join(lines))
            seen = ("added the `Claude usage watch` task to VS Code's user tasks - it covers "
                    "every project. ⚠ Reopen the folder (or run `Developer: Reload Window`) "
                    "for the usage terminal to start.")
        else:
            note = seen = None
        # ⚠ A per-project file from an earlier version would now open a SECOND identical
        # terminal beside the user-level one. It is ours, so it goes - unless it is tracked
        # by git, where removing it would dirty somebody's tree.
        if install.vscode_task_present(root):
            if _git_tracked(root, ".vscode/tasks.json"):
                extra = ("this project also carries an OLDER per-project `Claude usage watch` "
                         "task, which opens a SECOND identical terminal. It is tracked by git "
                         "here, so it was not removed - take it out yourself, or run "
                         "install.py --vscode-task --remove.")
                return (note or "") + " ⚠ " + extra, " ".join(x for x in (seen, extra) if x)
            import io as _io
            buf, saved = _io.StringIO(), sys.stdout
            sys.stdout = buf
            try:
                install.vscode_task(root, remove=True)
            finally:
                sys.stdout = saved
            extra = ("the older per-project task in this repository was removed, because "
                     "the user-level one now covers every project and two would open two "
                     "identical terminals.")
            return (note or "") + " ⭐ " + extra, " ".join(x for x in (seen, extra) if x)
        return note, seen
    except Exception as exc:
        broke = "the watcher task could NOT be written (%r)." % (exc,)
        return " ⚠ " + broke, broke


def maybe_adopt_statusline(cfg):
    """Take an EMPTY statusline slot, so the CLI shows the line with nothing typed.

    ⛔ Only when the slot is empty. See install.adopt_statusline_if_empty() for why that
    boundary is the whole of the safety here.
    """
    if not cfg.get("auto_statusline"):
        return None, None
    try:
        sys.path.insert(0, os.path.dirname(HERE))
        import install
        # ⭐ Seeded here as well as in install.py, because a marketplace user may never run
        # install.py at all - the hook is the whole installation now. It creates nothing
        # when the file is already there.
        install.seed_config()
        cmd = install.adopt_statusline_if_empty()
    except Exception:
        return None, None                               # never break a session over a line
    if not cmd:
        return None, None
    return (" ⭐ Nothing owned the statusline slot, so the usage line was installed into it - "
            "that is where the CLI shows the numbers, and it appears on the next interactive "
            "turn. To undo it, `/dispatch-guard:uninstall` removes the line AND switches this "
            "behaviour off; removing the entry alone is not enough, because an empty slot is "
            "exactly what this refills.",
            "nothing owned the statusline slot, so the usage line went into it. It appears on "
            "your next turn. `/dispatch-guard:uninstall` takes it back out.")


def maybe_repoint_statusline():
    """Repair a statusline left aimed at a version `claude plugin update` moved on from.

    ⛔ WHY IT IS SAFE TO DO WITHOUT ASKING, when writing .vscode/tasks.json is not. This
    touches one key in the user's OWN settings that this plugin already owns, and only ever
    aims it at the copy that is running anyway. Nothing new appears, nobody's repository
    changes, and a statusline belonging to another tool is never touched.

    ⚠ Cheap: one file read, and it returns immediately when the path is already right.
    """
    try:
        sys.path.insert(0, os.path.dirname(HERE))
        import install                                  # the plugin root, beside hooks/
        moved = install.repoint_statusline()
    except Exception:
        return None, None                               # never break a session over a statusline
    if not moved:
        return None, None
    return (" ⭐ The statusline was still aimed at %s - a copy left behind by an earlier "
            "version, which keeps working and keeps running OLD code - and it has been "
            "re-pointed at the running one. Nothing else was changed, and no command is "
            "needed after a plugin update any more." % moved[0],
            "your statusline still pointed at an old version (%s) and was re-pointed at the "
            "running one." % moved[0])


def effort_level(payload):
    """The reasoning effort for this turn, lowercased, or "".

    ⭐ MEASURED, from the hook input schema inside the shipped binary: "Reasoning effort
    applied to the current turn. Same shape as StatusLineCommandInput.effort. Present for
    hooks that fire within a tool-use context (PreToolUse, PostToolUse, Stop, SubagentStop,
    etc.) ... absent for session-lifecycle hooks and models without effort support."
    ⇒ So SessionStart and UserPromptSubmit cannot see it, and PreToolUse can. That is why the
    check below lives on the tool path rather than in the opening line.

    ⚠ The same reference says it also reaches Bash as CLAUDE_EFFORT, so that is read as a
    fallback for harnesses that fill one and not the other.
    """
    v = payload.get("effort")
    if isinstance(v, dict):
        v = v.get("level")
    if not isinstance(v, str) or not v.strip():
        v = os.environ.get("CLAUDE_EFFORT") or ""
    return v.strip().lower()


ULTRACODE_REASON = (
    "dispatch gate: ultracode is ON, and every tool call is refused until it is turned off. "
    "⛔ TELL THE USER, NOW, IN PLAIN WORDS: ultracode is xhigh effort PLUS dynamic workflow "
    "orchestration, and this gate refuses Workflow outright and refuses a second concurrent "
    "sub-task - so under ultracode every turn plans something that will be denied, and those "
    "tokens buy nothing. ⇒ Ask them to run `/effort` and choose `max` (or lower). max keeps "
    "the reasoning depth and drops the workflow orchestration. ⚠ There is no way around this "
    "from your side: no tool call will be permitted until the effort changes, so do not try "
    "another tool - say it and end the turn.")


def ultracode_refusal(payload, root, sdir):
    """Is ultracode on? Returns (reason, systemMessage or None) - or None when it is not.

    ⛔ REFUSED OUTRIGHT, EVERY TOOL CALL, and that is a deliberate escalation from the first
    version of this check, which warned once and let the session continue. Warning once is
    the wrong shape here: ultracode does not merely SUGGEST a workflow, it re-states the
    instruction every turn - so a session that was told once goes on burning planning tokens
    on something the gate will deny, for as long as it runs. The owner asked for the harder
    rule, and the harder rule is the honest one: max or below may proceed, ultracode may not.

    ⚠ THE REFUSAL REPEATS; THE SCREEN MESSAGE DOES NOT. The denial reaches the MODEL on every
    call, which is what makes it a rule rather than advice. A systemMessage on every call
    would bury the screen, so the person is told once - see the .warned mark for the same
    reasoning about repetition.

    ⭐ Nothing here can be fixed by the agent, which is why the reason tells it to stop rather
    than to try something else: only a person can run /effort.
    """
    if effort_level(payload) != "ultracode":
        return None
    sid = payload.get("session_id")
    mark = state_path(sdir, sid, "ultracode")
    seen = os.path.exists(mark)
    if not seen:
        try:
            os.makedirs(os.path.dirname(mark), exist_ok=True)
            with open(mark, "w", encoding="utf-8") as f:
                f.write(str(time.time()))
        except OSError:
            pass
    log(root, "DENY(ultracode)")
    msg = None if seen else (
        "dispatch-guard: ultracode is ON, and EVERY tool call is refused until you change it. "
        "It asks for dynamic workflows, which this gate refuses outright. Run /effort and pick "
        "`max` or lower - max keeps the same reasoning depth without the workflow "
        "orchestration.")
    return ULTRACODE_REASON, msg


def heartbeat(sdir, session_id):
    """Touch a per-session liveness file on every hook event.

    ⭐ This is what lets a SCHEDULED resume tell whether it is still needed. Both resume
    routes can legitimately be armed at once - waking this session is better when it
    survives, and the OS task is the only one that works when it does not - but if both
    fire, the same work runs twice. A live session touches this file constantly, so the
    scheduled task can ask "has anything been alive since the window reopened?" and stand
    down if so. Costs one file write per hook; that is the whole mechanism.
    """
    try:
        p = state_path(sdir, session_id, "alive")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except OSError:
        pass


def session_start(sdir, session_id):
    try:
        return os.path.getmtime(state_path(sdir, session_id, "start"))
    except OSError:
        return None


# ⭐ WHERE CLAUDE CODE KEEPS ITS OWN MODEL ALLOWLIST. `availableModels` is a SETTINGS key,
# not an API call - so this costs a file read rather than a request against an endpoint whose
# call budget this plugin already documents as tiny. Its schema, verbatim from the shipped
# binary: "Allowlist of models that users can select. Accepts family aliases (\"opus\" allows
# any opus version), version prefixes (\"opus-4-5\" allows only that version), and full model
# IDs. If undefined, all models are available".
#
# ⚠ Precedence, highest first, and the paths are measured rather than guessed: the managed
# file wins over everything, then this checkout's local and project settings, then the user's.
# ⛔ Best effort by design. An unreadable or absent file means "no allowlist", which means
# every model is available - the same answer Claude Code gives, and the one that cannot
# refuse a dispatch over a file this plugin failed to parse.
def settings_files(root):
    home = os.path.expanduser("~")
    files = [
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "ClaudeCode",
                     "managed-settings.json"),
        "/Library/Application Support/ClaudeCode/managed-settings.json",
        "/etc/claude-code/managed-settings.json",
    ]
    if root:
        files += [os.path.join(root, ".claude", "settings.local.json"),
                  os.path.join(root, ".claude", "settings.json")]
    files.append(os.path.join(home, ".claude", "settings.json"))
    return files


def available_models(root):
    """The `availableModels` allowlist, lowercased - or None when nothing sets one."""
    for path in settings_files(root):
        data = usage.read_json(path, None)
        if isinstance(data, dict):
            raw = data.get("availableModels")
            if isinstance(raw, list):
                names = [str(x).strip().lower() for x in raw if str(x).strip()]
                if names:
                    return names
    return None


def family_available(family, avail):
    """Is this family represented in the allowlist at all?

    ⚠ A SUBSTRING TEST, and deliberately loose. All three documented forms name the family -
    the alias `opus`, the version prefix `opus-4-5`, the full ID `claude-opus-5` - so asking
    "does any entry mention this family" answers every one of them. ⛔ Being loose is the safe
    direction here: too strict would refuse a dispatch Claude Code would have accepted, and a
    guard that refuses correct work is a guard the owner switches off.
    """
    if not avail:
        return True
    return any(family in entry for entry in avail)


def model_price(raw):
    """(label, dollars per million input tokens, exact) for a model alias or ID.

    `(None, None, False)` when nothing recognises it. ⚠ `inherit` and friends come back as
    ("inherit", 0, True): a price of zero passes every ceiling, which is the right answer for
    "whatever the owner picked for this session".

    ⭐ A MODEL ID IS MATCHED BEFORE A FAMILY, so `claude-opus-4-0` is priced at its own $15
    rather than at the family's $5. Longest ID first, and the `claude-` prefix is optional so
    `opus-4-0` resolves too.

    ⚠ `exact` IS FALSE WHEN A VERSION THIS TABLE HAS NEVER SEEN resolved through its family -
    `claude-opus-6`, the day it ships. The family's current price is the best available answer
    and it is a guess, so the caller logs it rather than pretending otherwise. A BARE alias is
    exact: `opus` genuinely gets the family's latest model.
    """
    name = str(raw or "").strip().lower()
    name = re.sub(r"\[[12]m\]$", "", name).strip()
    if name in MODEL_INHERIT:
        return "inherit", 0, True
    name = MODEL_ALIASES.get(name, name)
    prices = dict(MODEL_PRICES)
    # ⛔ `mid in name` ONLY - never `name in mid`. The reverse would let the bare alias `opus`
    # match whichever opus ID happens to sort first, which after a longest-first sort is the
    # $15 one. A bare alias must fall through to the family branch below.
    for mid, price in sorted(MODEL_PRICES, key=lambda row: -len(row[0])):
        short = mid[7:] if mid.startswith("claude-") else mid
        if mid in name or short in name:
            return mid, price, True
    for family, latest in FAMILY_LATEST:
        if name == family:
            return latest, prices[latest], True
    for family, latest in FAMILY_LATEST:
        if family in name:
            return latest, prices[latest], False
    return None, None, False


def model_refusal(tool_input, cfg, avail=None, log_to=None):
    """Is this dispatch's model above the ceiling? Returns a reason, or None.

    `avail` is the `availableModels` allowlist, or None for "everything". ⭐ It NARROWS two
    things and decides neither: the ceiling is clamped to the best family the account can
    actually use, and the replacement named in the refusal is chosen from that same set - so
    the gate never answers "use `opus`" on an account where opus was never available.

    ⛔ WHAT IT DELIBERATELY DOES NOT DO IS REFUSE ON AVAILABILITY BY ITSELF, and the reason is
    worth stating because the opposite looks more thorough. When a model is outside the
    allowlist, Claude Code substitutes rather than failing - "using the newest allowed model in
    its family", or "inheriting the parent model". Every one of those substitutions is a step
    DOWN in cost, so a cost guard has nothing to protect there, while a refusal built on the
    alias-and-version-prefix matching above would eventually refuse work that was perfectly
    legal. ⇒ Availability tightens the ceiling; it is not a second rule.

    ⛔ AN UNRECOGNISED MODEL IS REFUSED, and that is the one place this deliberately differs
    from the harness's own weight function, which scores an unknown model 3 - sonnet's number.
    Scoring an unknown as mid-range is right for ACCOUNTING and wrong for a GUARD: a new, more
    expensive model would come in under an `opus` ceiling and spend the window this plugin
    exists to protect, silently. ⇒ The refusal says the name was not recognised, so the answer
    is to name a known model rather than to go hunting for a bug. ⚠ A model whose FAMILY is
    known but whose version is not - `claude-opus-6`, the day it ships - is priced through its
    family instead of refused, and that assumption is logged (`MODEL-PRICE-ASSUMED`).

    ⚠ A MISCONFIGURED CEILING FAILS OPEN. A ceiling this code cannot resolve is the owner's
    typo, not the agent's fault, and refusing every dispatch over a typo is exactly the kind
    of guard that gets the whole plugin uninstalled. It is logged instead.
    """
    limit = cfg.get("max_model_price", DEFAULTS["max_model_price"])
    if limit is None or limit is False:
        # ⚠ Logged rather than silent, for the same reason as every other off switch: an
        # absent refusal must not be indistinguishable from a check that never ran.
        if log_to:
            log(log_to, "MODEL-PRICE-LIMIT-OFF (max_model_price is %r)" % (limit,))
        return None
    if isinstance(limit, bool):
        cw = None                       # `true` names no price; fall through to unknown
    elif isinstance(limit, (int, float)):
        cw = float(limit)
    else:
        # ⭐ A MODEL NAME IS ACCEPTED TOO, and priced. The documented form is a NUMBER, because
        # that is the thing being compared and it does not go stale when a family's price
        # changes - but `"opus"` is what a hand reaches for, and silently ignoring it would be
        # a footgun that reads as the check being off.
        _lbl, cw, _cx = model_price(limit)
    if not cw or cw <= 0:
        if log_to:
            log(log_to, "MODEL-PRICE-LIMIT-UNKNOWN %r - check not applied" % (limit,))
        return None
    # ⭐ CLAMP THE CEILING TO WHAT THE ACCOUNT CAN ACTUALLY USE. An `opus` ceiling on an
    # account restricted to sonnet is really a sonnet ceiling, and saying so out loud is the
    # difference between a limit the owner set and a limit they merely believe they set.
    prices = dict(MODEL_PRICES)
    usable = [(fam, prices[latest]) for fam, latest in FAMILY_LATEST
              if family_available(fam, avail)]
    narrowed = None
    if usable and max(p for _f, p in usable) < cw:
        cw = max(p for _f, p in usable)
        narrowed = next(f for f, p in usable if p == cw)
        if log_to:
            log(log_to, "MODEL-PRICE-LIMIT-CLAMPED %r -> %s ($%g/M) by availableModels %r"
                % (limit, narrowed, cw, avail))
    raw = tool_input.get("model")
    if not isinstance(raw, str) or not raw.strip():
        return None                     # omitted: inherit the session's model
    label, price, exact = model_price(raw)
    if label == "inherit":
        return None
    if label is not None and not exact and log_to:
        # ⚠ A version this table has never seen, priced through its family. Said out loud,
        # because it is the one number in this check that is an assumption rather than a
        # reading - and the log line is what tells somebody the table needs refreshing.
        log(log_to, "MODEL-PRICE-ASSUMED %r -> %s ($%g/M)" % (raw, label, price))
    # The best model still allowed, for the message. The owner asked that a refusal name the
    # level below rather than only listing what is permitted - and it is picked from the models
    # that are actually AVAILABLE, so the advice is one the agent can act on.
    allowed = [f for f, p in usable if p <= cw]
    best_allowed = allowed[0] if allowed else "haiku"
    if label is None:
        return ("dispatch gate: sub-agent model %r is refused - this gate does not recognise "
                "it, and an unrecognised model is treated as ABOVE the limit rather than "
                "below it (a new, more expensive model must not slip through silently). Known "
                "families: %s. Dispatch with `%s`, or omit `model` to inherit this session's "
                "model. The table is in `%s` (MODEL_PRICES) and in config.example.json."
                % (raw, ", ".join(f for f, _l in FAMILY_LATEST), best_allowed,
                   os.path.join("hooks", "dispatch_gate.py")))
    if price <= cw:
        return None
    # ⛔ REPORT THE EFFECTIVE LIMIT, NOT THE CONFIGURED ONE. Naming $5 while advising `sonnet`
    # reads as a bug in the gate rather than as a restriction on the account, and an agent that
    # thinks the gate is broken works around it instead of complying.
    return ("dispatch gate: sub-agent model `%s` is refused. `max_model_price` allows $%g per "
            "million input tokens%s, and %s is published at $%g - about %.1fx as much of the "
            "same window. Dispatch with `%s` instead, or omit `model` to inherit this "
            "session's model. ⚠ Do not raise the limit yourself: `max_model_price` is the "
            "owner's setting. ⭐ This is in `dispatch-protocol` too - read it BEFORE choosing a "
            "model rather than after being refused."
            % (label,
               cw,
               (" (narrowed to `%s` by your `availableModels` allowlist)" % narrowed)
               if narrowed else "",
               label, price, float(price) / cw, best_allowed))


def deny(event, reason, systemMessage=None):
    """Refuse the tool call. ⭐ Optionally say so on the USER's screen as well.

    ⚠ The refusal reason reaches the MODEL. A person watching sees only that the agent did
    something else instead - so a brake that fires and a brake that was never installed look
    the same from a chair. systemMessage closes that gap; see context_note().
    """
    out = {"hookSpecificOutput": {
        "hookEventName": event, "permissionDecision": "deny",
        "permissionDecisionReason": reason}}
    if systemMessage:
        out["systemMessage"] = systemMessage
    print(json.dumps(out, ensure_ascii=False))


def allow_prepended(event, tool_input, cfg, note):
    prompt = tool_input.get("prompt")
    if not isinstance(prompt, str):
        return
    head = PREPEND.format(task_root=cfg["task_root"], plan_glob=cfg["plan_glob"],
                          protocol_doc=cfg["protocol_doc"],
                          max_model_price=cfg.get("max_model_price",
                                                  DEFAULTS["max_model_price"]))
    if note:
        head += "!! %s\n\n" % note
    updated = dict(tool_input)
    updated["prompt"] = head + prompt
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": event, "permissionDecision": "allow",
        "permissionDecisionReason": "dispatch gate: protocol prepended",
        "updatedInput": updated}}, ensure_ascii=False))


def context_note(event, text, systemMessage=None):
    """Emit a hook result: text into the MODEL, and optionally a line onto the USER's screen.

    ⛔ TWO DIFFERENT AUDIENCES, and confusing them was this plugin's most repeated mistake.
    `additionalContext` reaches the model and nobody else - so every instruction sent that way
    is invisible to the person, and whether it was obeyed is unknowable from outside. Measured
    three separate times today: an install offer, a reopen instruction and a task-written note
    all "reported" and none reached a human.

    ⭐ `systemMessage` is displayed to the USER, on every hook event - quoted from the shipped
    reference: "systemMessage - Display a message to the user (all hooks)". It is the only
    channel here that cannot be ignored by a model, so anything the person must KNOW - rather
    than anything the agent must DO - belongs in it.

    ⭐ THIS WORKS ON PreToolUse TOO, and that is measured rather than assumed - the shipped
    binary's schema for the PreToolUse branch is `{hookEventName, permissionDecision?,
    permissionDecisionReason?, updatedInput?, additionalContext?}`, and the dispatcher attaches
    additionalContext independently of the permission behaviour. ⛔ THAT IS WHY A WARNING USES
    THIS AND NOT `permissionDecision: "allow"`: an "allow" from a hook suppresses the user's own
    permission prompt, so warning that way would hand every guarded command a free pass.
    """
    out = {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}
    if systemMessage:
        out["systemMessage"] = systemMessage
    print(json.dumps(out, ensure_ascii=False))


def guard_ctx(root, sdir, sid, cfg):
    """The little context cmd_guards runs against - paths, config, and a logger.

    ⭐ PASSED IN RATHER THAN IMPORTED. cmd_guards must not import this module: the gate
    imports cmd_guards, and a cycle would make the import order decide whether the guards
    exist. It also makes every guard drivable from a check with three temp directories.
    """
    return {
        "root": root,
        "sdir": sdir,
        "sid": sid,
        "cfg": cfg,
        "log": lambda m: log(root, m),
        "state": lambda suffix: state_path(sdir, sid, suffix),
        # See cmd_guards' docstring, point 2: an unstamped session is advisory only.
        "stamped": session_start(sdir, sid) is not None,
    }


# ----------------------------------------------------------------------- plan & slots

def plan_for(root, cfg, prompt_text):
    """(mtime, folder) of the plan governing THIS dispatch.

    ⚠ Checking the newest plan anywhere under the task root is too weak: more than one
    session can be live on one working tree, so another session writing ITS plan would
    satisfy this one's check. The protocol already requires every prompt to name the
    file its agent must write its report to, so when a prompt names a task folder, only
    folders it names are considered.

    ⚠ It considers EVERY folder the prompt names, because the gate cannot tell which
    mention is the output path and which is a file the sub-task was told to read. That
    is a narrowing, not an exact test - a prompt quoting another task's path inherits
    that task's plan.
    """
    tr = cfg["task_root"].replace("\\", "/")
    names = re.findall(re.escape(tr) + r"/([A-Za-z0-9._-]+)/", str(prompt_text).replace("\\", "/"))
    best = (None, None)
    for folder in dict.fromkeys(names):
        m = newest(os.path.join(root, tr.replace("/", os.sep), folder, cfg["plan_glob"]))[0]
        if m is not None and (best[0] is None or m > best[0]):
            best = (m, folder)
    if best[0] is not None:
        return best
    if names:
        return None, names[0]
    return newest(os.path.join(root, tr.replace("/", os.sep), "*", cfg["plan_glob"]))[0], None


def approved_slots(root, cfg, cutoff, folder, log_to=None):
    """How many sub-tasks the owner approved running at once. 1 unless they said more.

    ⚠ Scoped to the task folder this dispatch names. An approval granted for one task
    must not silently raise the limit for another, nor for another session.
    """
    if not folder:
        return 1
    tr = cfg["task_root"].replace("/", os.sep)
    mtime, path = newest(os.path.join(root, tr, folder, cfg["approval_glob"]))
    if mtime is None or mtime < cutoff:
        return 1
    # ⚠ An approval EXPIRES. Measured 2026-08-26: an agent that had been refused twice
    # wrote its own PARALLEL-APPROVED, quoting the owner's "dispatch two at once" as the
    # approval, and got through. The file then sat in the task folder, silently granting
    # concurrency to every later session that touched it. Nothing can stop an agent
    # writing that file - it can always reason its way to one - so the honest defences
    # are that it does not outlive the moment, and that its provenance is one log line
    # instead of a forensic dig.
    age_min = (time.time() - mtime) / 60.0
    if age_min > cfg["approval_ttl_min"]:
        if log_to:
            log(log_to, "APPROVAL-EXPIRED(%.0f min old) %s" % (age_min, os.path.basename(path)))
        return 1
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read(400)
    except OSError:
        return 1
    for form in APPROVAL_FORMS:
        found = re.search(form, text)
        if found:
            n = max(1, min(cfg["max_slots"], int(found.group(1))))
            if log_to:
                # ⭐ Provenance in ONE line: what granted it, how old, and what it says.
                # Whoever reads the log later must be able to see whether a human really
                # approved this, without reconstructing the session.
                log(log_to, "APPROVAL-USED n=%d age=%.0fmin file=%s says=%r"
                    % (n, age_min, os.path.basename(path),
                       " ".join(text.split())[:100]))
            return n
    return 1


def record_progress(root, cfg, folder, desc, started_at, response):
    """Append this dispatch's outcome to the task folder's progress.md.

    ⛔ THE GATE WRITES THIS, not the agent, and that is the whole point. The protocol
    requires results on disk; nothing could enforce it, so an agent answering a small
    question reasonably reported inline and wrote nothing. Measured 2026-08-26: a
    session dispatched two sub-tasks, wrote only prompts.md, and the NEXT session could
    not tell the work had been done - so it did all of it again. Redoing finished work
    is the exact cost the plan-on-disk rule exists to prevent, arriving through the
    other end of the same task folder.

    ⭐ The gate already knows everything needed - which folder, which sub-task, when it
    started, when it returned - so recording it costs nothing and removes the agent's
    memory from the loop entirely.

    ⚠ It APPENDS and never rewrites: a human-written progress.md must survive intact.
    """
    if not folder:
        return
    d = os.path.join(root, cfg["task_root"].replace("/", os.sep), folder)
    if not os.path.isdir(d):
        return
    path = os.path.join(d, "progress.md")
    excerpt = ""
    if isinstance(response, str):
        excerpt = " ".join(response.split())[:120]
    elif isinstance(response, dict):
        excerpt = " ".join(json.dumps(response, ensure_ascii=False).split())[:120]
    took = int(time.time() - started_at) if started_at else 0
    try:
        new = not os.path.exists(path)
        with open(path, "a", encoding="utf-8") as f:
            if new:
                f.write("# progress\n\n"
                        "Rows below this line are appended by the dispatch gate, not by an\n"
                        "agent - they are what actually happened, so a later session can tell\n"
                        "finished work from work that only looks finished.\n\n"
                        "| returned | sub-task | took | result |\n|---|---|---|---|\n")
            f.write("| %s | %s | %ds | %s |\n"
                    % (time.strftime("%Y-%m-%d %H:%M:%S"), desc or "(unnamed)", took,
                       excerpt.replace("|", "\\|") or "(no text returned)"))
    except OSError:
        pass


def claim_slot(root, sdir, cfg, session_id, slots, tool_use_id, folder=None, desc=None):
    """Atomically take one of `slots` numbered slots. True if one was free.

    O_CREAT|O_EXCL is atomic - 20 threads racing it produce exactly one winner - so two
    hooks firing at the same instant cannot both take the same slot.

    A slot older than slot_ttl_min is reclaimed first. A dispatch that dies without its
    PostToolUse - an interrupt, an API error, a killed process - would otherwise hold
    its slot forever and every later dispatch would be refused, ⛔ which reads exactly
    like the rule working.
    """
    os.makedirs(os.path.join(sdir, "state"), exist_ok=True)
    for i in range(slots):
        p = state_path(sdir, session_id, "slot%d" % i)
        try:
            if time.time() - os.path.getmtime(p) > cfg["slot_ttl_min"] * 60:
                os.remove(p)
                log(root, "RECLAIM(stale slot%d)" % i)
        except OSError:
            pass
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps({"id": str(tool_use_id), "folder": folder,
                                     "desc": desc, "at": time.time()}).encode("utf-8"))
            os.close(fd)
            return True
        except FileExistsError:
            continue
        except OSError:
            return True                    # cannot claim; fail open rather than block
    return False


def release_slot(sdir, cfg, session_id, tool_use_id):
    """Free this dispatch's slot.

    ⚠ The read is CLOSED before the remove. Windows refuses to delete an open file and
    the resulting PermissionError IS an OSError, so removing inside the `with` block
    failed silently and every slot leaked until the gate refused everything. Measured
    2026-08-26; do not fold these back together.
    """
    want = str(tool_use_id)
    for i in range(cfg["max_slots"]):
        p = state_path(sdir, session_id, "slot%d" % i)
        try:
            with open(p, encoding="utf-8") as f:
                raw = f.read().strip()
        except OSError:
            continue
        try:
            held = json.loads(raw)
        except Exception:
            held = {"id": raw}          # tolerate a slot written by an older version
        if held.get("id") != want:
            continue
        try:
            os.remove(p)
            return held
        except OSError as exc:
            return "error: %r" % (exc,)
    return False


# ---------------------------------------------------------------------------- events

def failed_resume_note(sdir):
    """If a scheduled resume gave up while nobody was watching, say so - once.

    ⛔ A scheduled task has no terminal and no window. Without this the outcome of an
    overnight resume is invisible: "it failed at 03:40" and "it was never armed" and
    "the work turned out not to be needed" all look identical the next morning. The
    marker is consumed here so it is announced exactly once.
    """
    path = os.path.join(sdir, "resume-failed.json")
    data = usage.read_json(path, None)
    if not data:
        return ""
    try:
        os.remove(path)
    except OSError:
        pass
    return (" ⛔ TELL THE USER FIRST, BEFORE ANYTHING ELSE: a scheduled resume gave up at "
            "%s and the work did NOT continue - %s"
            % (time.strftime("%Y-%m-%d %H:%M", time.localtime(data.get("at", 0))),
               data.get("why", "no reason recorded")))


# ⚠ THE TWO MARKER KINDS ARE PRUNED BY DIFFERENT RULES, AND THE ASYMMETRY IS THE POINT.
# The owner asked how few could be kept. For `.alive` the answer is one; for `.start` the
# question does not apply, because it is not a record - it is a switch.
STATE_KEEP_ALIVE = 20            # only the newest is READ; the rest are a count on screen
STATE_KEEP_START_DAYS = 7        # ⛔ an age rule, and it is a SAFETY margin - see below


def prune_state(sdir):
    """Bound the state directory. Runs once per session start.

    ⛔ WITHOUT THIS IT GROWS FOREVER. Every session leaves a `.start` and a `.alive` and
    neither was ever removed - 63 files after one day of ordinary work, so a year is
    thousands of tiny files in a folder a person is expected to look inside. Found because
    the owner noticed it growing, not because anything failed.

    ⭐ `.alive` IS PRUNED BY COUNT, and one would do. It exists so a scheduled resume can
    ask "has any session been alive since the window reopened?", which only ever reads the
    NEWEST. The others contribute a count to `install.py --status` and nothing else, so 20
    is a generous round number rather than a requirement.

    ⛔ `.start` IS PRUNED BY AGE ONLY, and NEVER BY COUNT. It is not data - it is the switch
    that decides whether this session is ENFORCED. `session_start()` returning None sends
    the gate down the ADVISORY branch, so deleting the marker of a session that is still
    running silently turns its brake off. ⚠ And liveness cannot be inferred: an open but
    IDLE session fires no hooks, so it refreshes nothing and looks exactly like a dead one.
    A week is therefore a safety margin, not a usefulness one - the file is worthless the
    moment its session ends, and the margin is there because we cannot tell when that was.
    ⇒ If this ever needs to shrink, the thing to change is the FAIL-OPEN, not the margin.

    ⚠ `.slotN` files are not touched at all. They are live concurrency state with their own
    reclaim rule in minutes (slot_ttl_min), and removing a held one hands out a slot twice.
    """
    removed = 0
    # .alive - by count, newest kept
    alive = []
    for path in glob.glob(os.path.join(sdir, "state", "*.alive")):
        try:
            alive.append((os.path.getmtime(path), path))
        except OSError:
            pass
    for _, path in sorted(alive, reverse=True)[STATE_KEEP_ALIVE:]:
        try:
            os.remove(path)
            removed += 1
        except OSError:
            pass
    # .start - by age only, never by count
    cutoff = time.time() - STATE_KEEP_START_DAYS * 86400
    for path in glob.glob(os.path.join(sdir, "state", "*.start")):
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1
        except OSError:
            pass                 # in use, or gone already; either way not our problem
    return removed


def stand_down_resume(root, sdir, v):
    """Kill a pending OS alarm as soon as the wait it was armed for is demonstrably over.

    ⛔ THE PROBLEM THIS SOLVES, and it is not only about switching accounts. A window can
    reopen EARLIER than the reset time the alarm was computed from - the reset moves, or a
    different account is signed in - and the developer then carries the work on themselves,
    hours before the alarm is due. The alarm knows none of that. It fires at its old time,
    finds nobody active because they finished and left, and REDOES WORK THAT IS ALREADY
    DONE - spending a fresh allowance to produce a duplicate.

    ⭐ THE FIX IS TO CANCEL AT THE MOMENT WORK RESUMES, not at the moment the alarm fires.
    do_run()'s own stand-down already covers "somebody is active RIGHT NOW", but it only
    gets to ask at fire time, which is exactly too late when the person came back early and
    then left again.

    ⛔ THE VERDICT TABLE IS THE WHOLE SAFETY ARGUMENT. Read it before changing anything:

        STOP     KEEP. The wait is still on; this is why the alarm exists. ⭐ It is also
                 what stops a cancel firing seconds after the arm - a dispatch is refused
                 at STOP, so STOP is necessarily still true when the alarm is armed.
        NO-DATA  KEEP. We do not know whether the window reopened. ⛔ Never discard a
                 backup on the strength of ignorance - that is the fail-open direction
                 turned into data loss.
        GO/PACE  CANCEL. There is MEASURED headroom, so the work can proceed now, in this
                 session, with its context. The alarm has nothing left to do.

    ⭐ A route (A) wake lands here too - the cron wake arrives as a UserPromptSubmit - so
    the backup is retired the moment the preferred route actually works.

    ⚠ `import resume` is deliberately INSIDE the function. resume.py imports this module at
    its top level, so a module-level import here would be a cycle; by the time this runs,
    this module is already in sys.modules and the import is free.

    ⚠ It also means a hook now spawns `schtasks /Delete`. That happens AT MOST ONCE per
    armed resume, because a successful cancel removes resume.json and the condition below
    can never match again. If schtasks were to hang past the hook's timeout the gate is
    killed and fails open, which is the same outcome as any other gate failure.
    """
    if v["verdict"] not in ("GO", "PACE"):
        return ""
    state = usage.read_json(os.path.join(sdir, "resume.json"), None)
    if not isinstance(state, dict):
        return ""
    at = state.get("at")
    # ⚠ Only a FUTURE alarm is ours to cancel. One whose time has passed is either mid-run
    # or mid-retry, and do_run owns that lifecycle - reaching into it from here would
    # cancel a resume while it was working.
    if not isinstance(at, (int, float)) or at <= time.time():
        return ""
    when = time.strftime("%H:%M", time.localtime(at))
    try:
        import resume                      # see the docstring: cycle-safe here, not above
        cancelled = resume.do_cancel(sdir, quiet=True) == 0
    except Exception as exc:
        log(root, "STAND-DOWN-FAILED %r" % (exc,))
        return (" ⚠ A scheduled resume is still armed for %s but the usage window has "
                "reopened (%s), and cancelling it just failed. TELL THE USER to run "
                "`resume.py --cancel` themselves - otherwise it will wake later and redo "
                "work that is already done." % (when, v["verdict"]))
    log(root, "STAND-DOWN %s the resume armed for %s (verdict %s)"
              % ("cancelled" if cancelled else "FAILED to cancel", when, v["verdict"]))
    if not cancelled:
        # ⛔ do_cancel() returns non-zero when the SCHEDULER refused, and the record is kept
        # on purpose so the orphan can still be chased. Announcing "nothing will wake later"
        # here would be the plugin asserting an outcome it was just denied.
        return (" ⚠ TELL THE USER: the usage window reopened early, so the scheduled resume "
                "armed for %s should have been cancelled - but the SCHEDULER REFUSED, and "
                "the job may still fire and redo work this session is about to do. The "
                "record was kept so it can be found: run `%s --status`, and on Windows the "
                "task is named ClaudeDispatchGuardResume."
                % (when, runnable("resume.py")))
    return (" ⭐ TELL THE USER: the usage window has reopened early, so the scheduled "
            "resume that was armed for %s has been CANCELLED - this session is continuing "
            "the work instead. Nothing will wake later to redo it." % when)


def on_session_start(payload, root, sdir, cfg):
    try:
        os.makedirs(os.path.join(sdir, "state"), exist_ok=True)
        with open(state_path(sdir, payload.get("session_id"), "start"), "w",
                  encoding="utf-8") as f:
            f.write(str(time.time()))
        prune_state(sdir)
    except OSError:
        pass
    # ⚠ The message below tells the agent the task root "already exists". Say that only
    # when it is TRUE - a read-only tree makes this None, and asserting a folder that is
    # not there is the same class of lie as a brake that reports active while dead.
    task_root_ready = ensure_task_root(root, cfg) is not None
    # ⭐ THE BRANCH THIS SESSION SELECTED, asked of git and written down now. Everything the
    # commit guard does is a comparison against this one value, so it is recorded before the
    # session can do anything - and never inferred from a command later.
    try:
        b = cmd_guards.record_branch(guard_ctx(root, sdir, payload.get("session_id"), cfg))
        log(root, "BRANCH-AT-START %s" % (b or "unknown"))
    except Exception as exc:
        log(root, "BRANCH-RECORD-FAILED %r" % (exc,))
    # ⛔ Say whether the usage brake is actually ALIVE. Without a statusline there are
    # no numbers, the brake never fires, and nothing distinguishes that from a session
    # that simply stayed under the threshold. An inactive safety net that looks active
    # is worse than no safety net, so it is reported every single session.
    v = usage.verdict(sdir, usage.config(sdir))
    if v["verdict"] == "NO-DATA":
        # ⛔ NO-DATA NO LONGER MEANS "NOTHING WILL EVER REFRESH". keep_clock_running()
        # forks a fetch on every hook event once the number goes stale, so at session start
        # the honest reading is "not here YET", and the old message - which announced a dead
        # brake and demanded an install - would now be alarming and wrong. ⚠ The two cases
        # still have to be distinguishable, which is what the third sentence is for: pending
        # clears by itself, failing does not.
        brake = ("⚠ NO USAGE NUMBERS YET, so report usage as UNKNOWN - never as a number - "
                 "and do not claim the brake either fired or held. ⭐ The gate has already "
                 "started a fetch in the background; it normally lands within seconds and "
                 "later checks in this session will have it. ⛔ If EVERY session says this, "
                 "the fetch is FAILING rather than pending - an expired token and a 429 look "
                 "identical from here, so run `%s --fetch-now`, which prints the reason in "
                 "one line. ⭐ Nothing has to be installed for the brake itself. A "
                 "statusline, or `usage.py --watch` in a terminal, only adds a line a PERSON "
                 "can see - `/dispatch-guard:install` sets those up if they want them."
                 % runnable("usage.py"))
    else:
        brake = "Usage braking is active (%s)." % v["verdict"]

    # ⭐ SAY IT UP FRONT. A rule an agent only meets as a refusal costs a wasted turn every
    # session, and this one refuses EVERY dispatch rather than nagging once - so stating it in
    # the opening line is the difference between one Skill call and a confused retry loop.
    need = cmd_guards.required_skills(cfg)
    skills_line = ("" if not need else
                   " ⛔ BEFORE YOUR FIRST DISPATCH you must invoke %s - every dispatch is "
                   "refused until you do."
                   % " and ".join("`dispatch-guard:%s`" % cmd_guards.skill_slug(n)
                                  for n in need))

    # ⚠ Reported, never silent. These write into the user's settings or repository, and a
    # change nobody is told about is the wrong kind of convenience however small the file.
    # ⭐ (context, screen) FROM EACH, rather than one string the caller has to parse. The
    # first version scraped a "TELL THE USER:" marker out of the prose, which would have
    # dropped the screen line silently the first time somebody reworded a note.
    pairs = [maybe_install_vscode_task(root, cfg, sdir),
             maybe_repoint_statusline(),
             maybe_adopt_statusline(cfg)]
    notes = [failed_resume_note(sdir), stand_down_resume(root, sdir, v)]
    notes += [c or "" for c, _s in pairs]

    text = ("Sub-task dispatch is governed by %s and enforced by a hook: one sub-task at "
            "a time, no background dispatch, no Workflow, and the plan plus every "
            "sub-task prompt are written to %s/<YYYYMMDD-HHMMSS-task-name>/%s BEFORE any "
            "dispatch%s.%s %s Before "
            "dispatching a wave run `%s --verdict` for GO/PACE/STOP - never interpret the "
            "raw numbers yourself.%s"
            % (cfg["protocol_doc"], cfg["task_root"], cfg["plan_glob"],
               (" - that folder already exists, so create the task folder inside it rather "
                "than choosing a location") if task_root_ready else
               (" - and %s could NOT be created, so create it yourself before dispatching"
                % cfg["task_root"]), skills_line, brake,
               runnable("usage.py"), "".join(notes)))

    # ⛔ THE ONES MARKED "TELL THE USER" NOW REACH THE USER. They were asking the MODEL to
    # relay them - which is advice a model weighs against its task, and this plugin's whole
    # argument is that advice is not a mechanism. Every one of these notes describes something
    # written into somebody's settings or repository, and the one channel that could tell them
    # was the one channel a model can decline to use.
    #
    # ⭐ ONLY WHEN SOMETHING CHANGED. A line on every session start is a line people stop
    # reading, so the screen channel carries only what a PERSON must act on, the once it
    # becomes true. Everything else stays in the model's context where it belongs.
    screen = [s for _c, s in pairs if s]
    out = {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                  "additionalContext": text}}
    if screen:
        out["systemMessage"] = "dispatch-guard: " + " ".join(screen)
    # ⚠ JSON RATHER THAN PLAIN TEXT, and the shape is the one hooks/unattended.py already
    # proves on this event: plain stdout can only ever become model context, so it had no way
    # to reach a screen at all.
    print(json.dumps(out, ensure_ascii=False))


def on_user_prompt(payload, root, sdir, cfg):
    """The wind-down net, ported from claude-pacer's budget-guard.

    Fires once per level per session and re-arms when the level changes, so a long
    autonomous run hears it more than once without being nagged every turn.
    """
    v = usage.verdict(sdir, usage.config(sdir))
    # ⛔ BEFORE the early return, because GO is precisely the path a reopened window
    # arrives on. The old code returned silently here, which is why an alarm could outlive
    # the wait it was armed for. See stand_down_resume().
    note = stand_down_resume(root, sdir, v)
    if v["verdict"] not in ("PACE", "STOP"):
        if note:
            context_note(payload.get("hook_event_name", "UserPromptSubmit"),
                         "[usage]" + note)
        return
    sid = payload.get("session_id")
    mark = state_path(sdir, sid, "warned")
    try:
        with open(mark, encoding="utf-8") as f:
            if f.read().strip() == v["verdict"]:
                return
    except OSError:
        pass
    try:
        os.makedirs(os.path.dirname(mark), exist_ok=True)
        with open(mark, "w", encoding="utf-8") as f:
            f.write(v["verdict"])
    except OSError:
        pass
    log(root, "USAGE(%s) pct=%s" % (v["verdict"], round(v.get("pct") or 0)))
    extra = ""
    if v["verdict"] == "STOP":
        extra = (" Arm the resume so this survives the window: write a stand-alone "
                 "HANDOFF.md into the task folder, then run `%s --arm --task <task>` - it "
                 "registers a one-shot OS scheduled task for a few minutes after %s and "
                 "will refuse a handoff that is only a placeholder. Then END THE TURN. New "
                 "sub-task dispatches are refused by the gate until the window resets."
                 % (runnable("resume.py"),
                    v.get("resets_clock", "the reset")))
    # ⭐ THE ACKNOWLEDGEMENT LINE. A wind-down instruction is advice a model weighs against
    # its task, and "it kept working" is indistinguishable from "it never heard". Demanding
    # one exact line makes the difference visible on the screen: no line, no wind-down.
    # ⚠ It is not proof of obedience - nothing in a prompt can be - but it separates
    # "acknowledged and continued anyway" from "never received", which are different faults
    # with different fixes.
    ack = (" ⛔ FIRST, IN YOUR NEXT MESSAGE, PRINT EXACTLY THIS LINE AND NOTHING BEFORE IT: "
           "`%s at %d%% - winding down`. Then say in one sentence what you are finishing and "
           "what you are dropping. If you will NOT wind down, print that line with `- NOT "
           "winding down` instead and say why."
           % (v["verdict"], round(v.get("pct") or 0)))
    # ⭐ AND THE SAME FACT ON THE USER'S SCREEN, through the one channel a model cannot
    # swallow. The person then holds both halves: the brake fired (this line, guaranteed) and
    # whether the agent answered for it (the line above, in the transcript).
    seen = ("dispatch-guard: usage %s at %d%%. %s Expect the agent to acknowledge with "
            "`%s at %d%% - winding down`; if that line does not appear, it did not act on it."
            % (v["verdict"], round(v.get("pct") or 0),
               "Sub-task dispatch is now REFUSED until the window resets."
               if v["verdict"] == "STOP" else "Dispatch is still allowed; scope should shrink.",
               v["verdict"], round(v.get("pct") or 0)))
    context_note(payload.get("hook_event_name", "UserPromptSubmit"),
                 "[usage] " + v["text"] + extra + ack + note, systemMessage=seen)


def _wake_hint(v):
    """Route (A): wake THIS session when the window turns over, keeping all its context.

    ⭐ Better than a scheduled task when the session survives - the work continues with
    everything already loaded, instead of a fresh headless run reading a handoff.

    ⭐ MEASURED IN BOTH HARNESSES, 2026-08-26, and the long gap is the part worth knowing:
    a one-shot CronCreate job fired after a 32-minute idle gap in the VS Code extension and
    after a 33-minute gap in the CLI, and in both the session could still account for what
    it had been doing beforehand. A 4.5-minute gap was measured first. ⇒ The ten-minute cap
    below is a COMMAND cap and does not bound this route.

    ⛔ It does NOT offer a plain background sleep, and the reason is worth writing down.
    The harness caps a command at ten minutes, so a sleep can only cover a short wait -
    but a short wait never reaches here: the near-reset exemption softens STOP to PACE
    within near_reset_min (20 minutes by default) of the reset, so any refusal that gets
    this far has at least that long to wait. A first version branched on the sleep case
    and the branch was unreachable by construction; measured, not reasoned.

    ⚠ THE CRON JOB DIES WITH THE SESSION. It is held in the session's memory and is never
    written to disk, so "the session did not survive" does not make this route fail - it
    makes it cease to exist, with nothing left behind to notice. That is why route (B) is
    offered alongside it rather than as a fallback.

    ⚠ AND IT IS NOT THE CHEAPER ROUTE, which is the natural misreading. Keeping the session
    does not keep the tokens: a wait long enough to need a resume outlives the prompt cache,
    so the first request after the wake re-sends the whole conversation at full price.
    Measured: cache_read was ZERO on a resumed conversation. What this route buys is
    CORRECTNESS - nothing has to be reconstructed from a handoff - not a smaller bill.
    """
    mins = v.get("remain_min")
    when = ("about %d minutes out" % (mins + 1)) if isinstance(mins, int) else "after the reset"
    return (" ⭐ (A) IF THIS SESSION WILL STAY OPEN, this is the better route because it keeps "
            "all your context: schedule a one-shot wake %s (CronCreate via ToolSearch "
            "\"select:CronCreate\", recurring:false) and end the turn - when it fires, carry "
            "on from here. ⚠ A background sleep cannot substitute: the harness caps a command "
            "at ten minutes, which never reaches the reset from here." % when)


def on_pre_agent(payload, root, sdir, cfg):
    tool_input = payload.get("tool_input") or {}
    event = payload.get("hook_event_name", "PreToolUse")
    desc = str(tool_input.get("description", ""))[:40]
    sid = payload.get("session_id")
    started = session_start(sdir, sid)

    if started is None:
        log(root, "ADVISORY(no-session-stamp) %s" % desc)
        allow_prepended(event, tool_input, cfg, None)
        return

    # ---- the usage brake, before anything else: this is the expensive call ----
    note = None
    if cfg["brake_on_usage"] or cfg["warn_on_usage"]:
        v = usage.verdict(sdir, usage.config(sdir))
        if v["verdict"] == "STOP" and cfg["brake_on_usage"]:
            log(root, "DENY(usage-stop pct=%s) %s" % (round(v.get("pct") or 0), desc))
            deny(event, "dispatch gate: %s Dispatching a sub-task is the most expensive "
                        "thing you can do right now, so it is refused until the window "
                        "resets. Finish and save the current step, then pick a resume:%s"
                        " ⭐ (B) IF THE SESSION MIGHT NOT SURVIVE, or you are unsure: write "
                        "%s/<task>/HANDOFF.md so it stands completely alone, then run "
                        "`%s --arm --task <task>` - that registers a one-shot OS task and "
                        "survives closing everything. Then end the turn."
                 % (v["text"], _wake_hint(v), cfg["task_root"],
                    runnable("resume.py")),
                 # ⭐ ON THE SCREEN TOO. This is the strongest thing the plugin ever does -
                 # a tool call refused outright - and until now a person could not tell it
                 # from the agent simply choosing something else. A refusal nobody sees is
                 # indistinguishable from a brake that was never installed.
                 systemMessage=("dispatch-guard: sub-task dispatch REFUSED - usage %s at "
                                "%d%%. Nothing was dispatched. The agent has been told to "
                                "save the current step and arm a resume."
                                % (v["verdict"], round(v.get("pct") or 0))))
            return
        if v["verdict"] == "PACE" and cfg["warn_on_usage"]:
            note = ("Usage is high (%s). Do this unit and report; do NOT expand scope, "
                    "and do not dispatch anything yourself." % v["text"])

    # ⭐ THE MODEL CEILING, read straight off tool_input as the owner asked. ⚠ AFTER the
    # usage brake on purpose: at STOP nothing should be dispatched at all, and a "use a
    # cheaper model" refusal invites an immediate retry - which is the wrong thing to invite
    # when the answer is "dispatch nothing until the window resets".
    why = model_refusal(tool_input, cfg, avail=available_models(root), log_to=root)
    if why:
        log(root, "DENY(model %r) %s" % (tool_input.get("model"), desc))
        deny(event, why,
             # ⭐ ON THE SCREEN, because only the owner can change the ceiling - and because
             # a sub-agent quietly running on a model they did not choose is the thing they
             # asked to be able to see.
             systemMessage=("dispatch-guard: dispatch REFUSED - sub-agent model %r costs more "
                            "than `max_model_price` (%r $/M input). Nothing was dispatched."
                            % (tool_input.get("model"),
                               cfg.get("max_model_price", DEFAULTS["max_model_price"]))))
        return

    # ⭐ AFTER THE USAGE BRAKE, BEFORE EVERYTHING ELSE. `unattended-work` is the skill that
    # would have told this agent to write the plan first, so asking for it ahead of the plan
    # check means the next refusal is one it already understands.
    # ⭐ THE REQUIRED SKILLS, OR NOTHING DISPATCHES. Placed after the usage brake and the model
    # ceiling, and before the soft nag below. ⚠ By default only `dispatch-protocol` is
    # required, so the nag below still has a job: it is what asks for `unattended-work` when
    # the owner has not made it mandatory. Turn `require_unattended_work` on and the nag never
    # fires, because a missing `unattended-work` becomes a refusal here instead.
    try:
        need = cmd_guards.skills_refusal(payload, guard_ctx(root, sdir, sid, cfg), cfg)
    except Exception as exc:
        log(root, "CMD-GUARDS-FAILED %r" % (exc,))
        need = None
    if need:
        log(root, "DENY(require-skills) %s" % desc)
        deny(event, need["model"], systemMessage=need["screen"])
        return

    # ⭐ CALLED UNCONDITIONALLY, with the switch passed IN. Gating the call on the key
    # here was the one off switch in this plugin that left no trace, which is the same defect
    # as an absent denial that proves nothing - see criterion 6 in the guard's own prompt.
    try:
        u = cmd_guards.unattended_first(
            payload, guard_ctx(root, sdir, sid, cfg),
            enabled=cfg.get("guard_unattended_first", True))
    except Exception as exc:
        log(root, "CMD-GUARDS-FAILED %r" % (exc,))
        u = None
    if u:
        log(root, "DENY(unattended-not-loaded) %s" % desc)
        deny(event, u["model"], systemMessage=u["screen"])
        return

    if tool_input.get("run_in_background"):
        log(root, "DENY(background) %s" % desc)
        deny(event, "dispatch gate: background dispatch is refused. The harness treats a "
                    "background sub-task as finished the moment it is launched, so it "
                    "escapes the one-at-a-time accounting entirely and any number can "
                    "pile up behind it. Dispatch in the foreground and wait. See %s."
             % cfg["protocol_doc"])
        return

    plan_mtime, folder = plan_for(root, cfg, tool_input.get("prompt") or "")
    if plan_mtime is None or plan_mtime < started:
        log(root, "DENY(no-plan in %s) %s" % (folder or "any task folder", desc))
        deny(event, "dispatch gate: no dispatch plan was written in this session. Per %s, "
                    "write the plan and EVERY sub-task's full prompt into "
                    "%s/<YYYYMMDD-HHMMSS-task-name>/%s first, then dispatch. This is what "
                    "lets an interrupted run resume instead of restart, and what lets the "
                    "prompts be handed to another account."
             % (cfg["protocol_doc"], cfg["task_root"], cfg["plan_glob"]))
        return

    slots = approved_slots(root, cfg, started, folder, log_to=root)
    if not claim_slot(root, sdir, cfg, sid, slots, payload.get("tool_use_id"),
                      folder, desc):
        log(root, "DENY(slots-full n=%d) %s" % (slots, desc))
        deny(event, "dispatch gate: %d sub-task(s) are already in flight, which is all "
                    "the owner approved. Dispatch one at a time - that needs no "
                    "permission. To raise the limit, ask the owner; when they answer with "
                    "a count, record it as %s/<task>/PARALLEL-APPROVED containing that "
                    "number in the form 'parallel N'." % (slots, cfg["task_root"]))
        return

    log(root, "ALLOW(slots=%d) %s" % (slots, desc))
    allow_prepended(event, tool_input, cfg, note)


# ------------------------------------------------------------------------------ main

def main():
    try:
        # ⛔ NOT json.load(sys.stdin). Python opens stdin in the console codepage - cp950
        # on some Windows machines - so any non-ASCII byte in a prompt is mangled before
        # the gate sees it, and a double-byte codepage swallows the following byte too.
        # Measured: a prompt containing Chinese made the task-folder regex miss entirely,
        # silently downgrading the plan check AND discarding that task's approval.
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("unparseable hook payload: %r" % (exc,))

    root = repo_root(payload.get("cwd"))
    sdir = usage.state_dir([])
    cfg = gate_config(root, sdir)
    event = payload.get("hook_event_name")
    tool = payload.get("tool_name")
    sid = payload.get("session_id")
    heartbeat(sdir, sid)
    # ⭐ Before any branch, because this is what keeps the numbers moving for every route -
    # CLI, extension, sub-agent, every depth. It forks at most once per fetch_seconds.
    # ⛔ AND BELTED AS WELL AS BRACED. keep_clock_running() already swallows its own
    # failures; this second guard exists because the first one was wrong once and cost the
    # entire gate. Enforcement must not depend on a refresh succeeding, or even on the
    # refresh code being correct.
    try:
        keep_clock_running(sdir)
    except Exception as exc:
        log(root, "CLOCK-FAILED %r" % (exc,))

    if event == "SessionStart":
        return on_session_start(payload, root, sdir, cfg)
    if event == "UserPromptSubmit":
        return on_user_prompt(payload, root, sdir, cfg)

    # ⛔ ULTRACODE IS REFUSED BEFORE ANY OTHER CHECK, and for every tool - not only Agent.
    # `effort` rides on the tool-use payload and nowhere else (see effort_level), so this is
    # the only place it can be seen, and PreToolUse is the only place a call can be denied.
    if event == "PreToolUse":
        ultra = ultracode_refusal(payload, root, sdir)
        if ultra:
            reason, msg = ultra
            return deny(event, reason, systemMessage=msg)

    if event == "PreToolUse" and tool == "Workflow":
        if session_start(sdir, sid) is None:
            log(root, "ADVISORY(no-session-stamp) Workflow")
            return
        log(root, "DENY(workflow)")
        return deny(event, "dispatch gate: Workflow is forbidden - it spawns many agents "
                           "concurrently by construction. Dispatch sequentially with the "
                           "Agent tool instead; that needs no permission. See %s."
                    % cfg["protocol_doc"])

    # ⭐ THE SILENT-FAILURE GUARDS. A shell command is the other place where the wrong
    # outcome and the right one look identical, and unlike a dispatch it happens constantly.
    # ⛔ WRAPPED, like keep_clock_running above: belt as well as braces. cmd_guards fails open
    # inside itself, and this second net exists because the first one was wrong once and cost
    # the entire gate - a pre-branch exception makes a hook print nothing, and a hook that
    # prints nothing has APPROVED the call.
    if tool in cmd_guards.SHELL_TOOLS and event in ("PreToolUse", "PostToolUse"):
        try:
            ctx = guard_ctx(root, sdir, sid, cfg)
            if event == "PreToolUse":
                v = cmd_guards.check(payload, ctx)
                if v and v["kind"] == cmd_guards.DENY:
                    return deny(event, v["model"], systemMessage=v["screen"])
                if v:
                    # A warning: text for the model, a line for the person, and NO permission
                    # decision - see context_note() for why "allow" would be a free pass.
                    return context_note(event, v["model"], systemMessage=v["screen"])
            else:
                text = cmd_guards.after_command(payload, ctx)
                if text:
                    return context_note(event, text)
        except Exception as exc:
            log(root, "CMD-GUARDS-FAILED %r" % (exc,))
        return

    # ⚠ POST, NOT PRE: a Skill call the user declined never became an invocation.
    if event == "PostToolUse" and tool == "Skill":
        try:
            cmd_guards.note_skill(payload, guard_ctx(root, sdir, sid, cfg))
        except Exception as exc:
            log(root, "SKILL-NOTE-FAILED %r" % (exc,))
        return

    if tool != "Agent":
        return
    if event == "PreToolUse":
        return on_pre_agent(payload, root, sdir, cfg)
    if event == "PostToolUse":
        result = release_slot(sdir, cfg, sid, payload.get("tool_use_id"))
        if isinstance(result, dict):
            log(root, "RELEASE")
            record_progress(root, cfg, result.get("folder"), result.get("desc"),
                            result.get("at"), payload.get("tool_response"))
        elif result is not False:
            log(root, "RELEASE-FAILED %s" % result)


def selftest():
    """`dispatch_gate.py --selftest` - asserts where task folders resolve to and that the
    root is created. Touches no real repository: it builds its own temp tree.

    ⛔ Worth a check rather than a comment because a wrong answer here is SILENT. A gate
    that resolves task_root to the wrong folder finds no fresh plan, refuses every dispatch,
    and the refusal names a path without saying it looked in the wrong one.
    """
    import shutil
    import tempfile
    root = tempfile.mkdtemp()
    sdir = tempfile.mkdtemp()
    try:
        # Unset in config -> the DECLARED default, and it gets created.
        cfg = gate_config(root, sdir)
        assert cfg["task_root"] == TASK_ROOT, cfg["task_root"]
        made = ensure_task_root(root, cfg)
        assert made and os.path.isdir(made), made
        assert os.path.isdir(os.path.join(root, "Memory", "tasks"))
        # Compatibility detection: an EXISTING other root wins over the default.
        root2 = tempfile.mkdtemp()
        os.makedirs(os.path.join(root2, "tasks"))
        assert gate_config(root2, sdir)["task_root"] == "tasks"
        # An explicit project setting beats both, and task_roots() puts it first.
        os.makedirs(os.path.join(root2, ".claude"), exist_ok=True)
        with open(os.path.join(root2, ".claude", "dispatch-guard.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"dispatch": {"task_root": "work/jobs"}}, f)
        assert gate_config(root2, sdir)["task_root"] == "work/jobs"
        order = task_roots(root2, sdir)
        assert order[0] == "work/jobs", order
        assert len(set(order)) == len(order), "task_roots repeated a root: %r" % (order,)
        # ⛔ A nested path must become a real directory, not a literal "work/jobs" name.
        ensure_task_root(root2, gate_config(root2, sdir))
        assert os.path.isdir(os.path.join(root2, "work", "jobs"))
        shutil.rmtree(root2, ignore_errors=True)

        # ⛔ The clock's fork decision, checked without spending an API call. Both False
        # cases matter more than the True one: get either wrong and the gate forks a process
        # on every tool call, which is worst exactly when the fetch is already failing.
        clock = tempfile.mkdtemp()
        now = time.time()
        assert clock_due(clock, 120, now), "empty state dir must be due"
        for name, back, due in (("limits.json", 10, False),   # data still fresh
                                ("limits.json", 300, True),   # data stale, nothing started
                                (CLOCK_MARK, 10, False),      # a child was just started
                                (CLOCK_MARK, 300, True)):     # that child never landed data
            f = os.path.join(clock, name)
            with open(f, "w") as fh:
                fh.write("{}")
            os.utime(f, (now - back, now - back))
            assert clock_due(clock, 120, now) is due, "%s aged %ds" % (name, back)
            os.remove(f)
        # ⛔ CALL THE REAL FUNCTION, not only its decision. Checking clock_due() alone is
        # what let `now` go unbound in keep_clock_running() for a whole release: every call
        # raised NameError, the exception escaped into main() ahead of every event branch,
        # the gate exited silently - and a hook that prints nothing has APPROVED the call.
        # The selftest passed the entire time. Popen is stubbed so nothing is spawned and no
        # API call is spent; what is asserted is that the body RUNS and asks for the right
        # command.
        spawned = []
        _popen, subprocess.Popen = subprocess.Popen, lambda *a, **k: spawned.append((a, k))
        try:
            assert keep_clock_running(clock) is True, "a state dir with no data is due"
            assert len(spawned) == 1, spawned
            argv = spawned[0][0][0]
            assert argv[1].endswith("usage.py") and "--fetch-now" in argv, argv
            assert argv[argv.index("--dir") + 1] == clock, "the child must be told where"
            assert os.path.getsize(os.path.join(clock, CLOCK_MARK)) > 0, "mark left empty"
            assert keep_clock_running(clock) is False, "the young mark must stop a second fork"
            assert len(spawned) == 1, "forked twice"
        finally:
            subprocess.Popen = _popen
        shutil.rmtree(clock, ignore_errors=True)

        # ⛔ THE MODEL CEILING'S ALIAS TRAP, pinned here as well as in Tools/Debug because
        # this selftest ships with the plugin and a person diagnosing an install can run it.
        # `best` is a real accepted alias and it resolves to FABLE, and `claude-mythos-5` is a
        # fifth family the harness's own weight function scores as 3 - sonnet's price. Drop
        # either line and the guard hands out the exact model it was installed to refuse.
        ceil = {"max_model_price": 5}
        for over in ("fable", "best", "FABLE[1m]", "claude-fable-5", "claude-mythos-5",
                     "gpt-5", "mythos",
                     # ⛔ AND THE ONE A FAMILY LADDER GOT WRONG. claude-opus-4-0 is tier_15_75:
                     # three times claude-opus-5's tier_5_25, in the same family. Priced per
                     # family it read as "opus" and passed a $5 limit untouched.
                     "claude-opus-4-0", "claude-opus-4-1", "opus-4-0"):
            assert model_refusal({"model": over}, ceil), "%s passed a $5 limit" % over
        for under in ("opus", "opusplan", "opus[1m]", "claude-opus-5", "claude-opus-4-8",
                      "sonnet", "claude-sonnet-4-6", "haiku", "inherit", "", None):
            assert not model_refusal({"model": under}, ceil), "%r was refused" % (under,)
        # ⭐ THE LIMIT IS A NUMBER, so it moves without renaming anything.
        assert model_refusal({"model": "opus"}, {"max_model_price": 3}), "$3 must refuse opus"
        assert not model_refusal({"model": "sonnet"}, {"max_model_price": 2}), "sonnet is $2"
        assert model_refusal({"model": "sonnet"}, {"max_model_price": 1}), "$1 is haiku only"
        # ⚠ ...and a model NAME is still accepted, because it is what a hand reaches for.
        assert model_refusal({"model": "fable"}, {"max_model_price": "opus"}), "name form"
        assert not model_refusal({"model": "opus"}, {"max_model_price": "opus"}), "name form"
        # ⚠ A bare family alias is priced as the model it actually resolves to, so `opus` is
        # claude-opus-5 at $5 - not as the most expensive opus that ever existed.
        assert model_price("opus") == ("claude-opus-5", 5, True), model_price("opus")
        assert model_price("claude-opus-4-0") == ("claude-opus-4-0", 15, True)
        # ...and an unseen version in a known family resolves, but is marked as an assumption.
        assert model_price("claude-opus-6") == ("claude-opus-5", 5, False)
        assert not model_refusal({"model": "fable"}, {"max_model_price": None}), "null must be off"
        assert not model_refusal({"model": "fable"}, {"max_model_price": "typo"}), "typo opens"
        assert not model_refusal({"model": "fable"}, {"max_model_price": 0}), "0 must be off"
        # ⭐ availableModels NARROWS the limit and the advice. On an account restricted to
        # sonnet, a $5 limit is really a $2 limit - and the refusal must not tell the agent to
        # use a model the account cannot select.
        only_sonnet = ["sonnet", "haiku"]
        assert model_refusal({"model": "opus"}, ceil, avail=only_sonnet), "the clamp did nothing"
        msg = model_refusal({"model": "fable"}, ceil, avail=only_sonnet)
        assert "Dispatch with `sonnet`" in msg, msg
        # ⛔ AND IT REPORTS THE EFFECTIVE LIMIT. Quoting the configured $5 while advising
        # `sonnet` reads as a bug in the gate rather than as a restriction on the account, and
        # an agent that believes the gate is broken works around it instead of complying.
        assert "allows $2 per million" in msg, msg
        assert "narrowed to `sonnet` by your `availableModels`" in msg, msg
        assert not model_refusal({"model": "sonnet"}, ceil, avail=only_sonnet)
        # A prefix or a full ID names its family just as an alias does.
        for entry in (["opus-4-5"], ["claude-opus-5"], ["opus"]):
            assert not model_refusal({"model": "opus"}, ceil, avail=entry), entry
        assert not model_refusal({"model": "opus"}, ceil, avail=None), "None means everything"

        # ⛔ THE WATCHER TASK, at VS Code's USER level. Isolated by pointing
        # vscode_user_dirs() at a temp directory: an earlier version of this block wrote to
        # the real %APPDATA%/Code/User/tasks.json while "testing", which is the same defect
        # it is here to prevent somebody else from shipping.
        sys.path.insert(0, os.path.dirname(HERE))
        import install as _install
        vsdir = tempfile.mkdtemp()
        _saved_dirs, _install.vscode_user_dirs = _install.vscode_user_dirs, lambda: [vsdir]
        _saved_grant, _install.allow_automatic_tasks = _install.allow_automatic_tasks, lambda: None
        try:
            up = os.path.join(vsdir, "tasks.json")
            assert not _install.vscode_user_task_current(), "an empty dir cannot be current"
            note, seen = maybe_install_vscode_task(tempfile.mkdtemp(), dict(DEFAULTS))
            assert note and "USER tasks" in note, note
            # ⛔ AND A LINE FOR THE PERSON, not only for the model. With no usage left there
            # is no model turn at all, and installing on an empty budget is the case that
            # has to work - so a note that only reaches the model does not exist.
            assert seen and "Reopen the folder" in seen, seen
            assert _install.vscode_user_task_current(), "what it wrote does not read back"
            with open(up, encoding="utf-8") as fh:
                written = fh.read()
            assert "Claude usage watch" in written
            # ⛔ NEVER ${workspaceFolder} IN A USER-LEVEL TASK. It has no workspace of its
            # own, so VS Code resolves that variable against whatever project happens to be
            # open and looks for the plugin inside it - wrong in every project, including the
            # one it was written from. Measured: the path shortener produced exactly that.
            assert "workspaceFolder" not in written, written
            # ⭐ ...and it does not rewrite a file that is already correct, every session.
            assert maybe_install_vscode_task(tempfile.mkdtemp(), dict(DEFAULTS)) == (None, None)

            # ⭐ AFTER `claude plugin update` THE STORED PATH IS STALE, and repairing it is
            # the whole reason nobody has to re-run anything. The cache directory carries the
            # VERSION, so the absolute path inside the task names a copy the update moved on
            # from - and the old directory is left behind, so it still RUNS and runs old code.
            import json as _json
            with open(up, encoding="utf-8") as fh:
                book = _json.load(fh)
            book["tasks"][0]["command"] = book["tasks"][0]["command"].replace(
                "/hooks/", "/OLDVERSION/hooks/")
            with open(up, "w", encoding="utf-8") as fh:
                _json.dump(book, fh)
            assert not _install.vscode_user_task_current(), "a stale path read as current"
            assert maybe_install_vscode_task(tempfile.mkdtemp(), dict(DEFAULTS))[0] is not None
            with open(up, encoding="utf-8") as fh:
                assert "OLDVERSION" not in fh.read(), "an update did NOT repair the path"

            # ⛔ MERGES, never clobbers: somebody's own tasks survive.
            with open(up, "w", encoding="utf-8") as fh:
                json.dump({"version": "2.0.0", "tasks": [{"label": "my build"}]}, fh)
            _install.vscode_user_task()
            with open(up, encoding="utf-8") as fh:
                labels = [t["label"] for t in json.load(fh)["tasks"]]
            assert "my build" in labels and "Claude usage watch" in labels, labels

            # ⛔ ...and refuses a file it cannot read. VS Code allows comments here.
            # ⚠ Built by join rather than written with escapes: a generated "\n" inside
            # generated code is how this very block first arrived as a syntax error.
            jsonc = chr(10).join(["{", "  // mine", '  "version": "2.0.0", "tasks": []', "}"])
            with open(up, "w", encoding="utf-8") as fh:
                fh.write(jsonc)
            out = _install.vscode_user_task()
            assert any("does not parse" in x for x in out), out
            with open(up, encoding="utf-8") as fh:
                assert fh.read() == jsonc, "an unparseable user tasks file was overwritten"

            # ⚠ An explicit false keeps it out entirely; that is a decision, not a question.
            os.remove(up)
            assert maybe_install_vscode_task(tempfile.mkdtemp(),
                                             {"auto_vscode_task": False}) == (None, None)
            assert not os.path.exists(up), "false still wrote the user task"
        finally:
            _install.vscode_user_dirs = _saved_dirs
            _install.allow_automatic_tasks = _saved_grant
        shutil.rmtree(vsdir, ignore_errors=True)
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(sdir, ignore_errors=True)
    # ⛔ THE BRAKE MUST REACH THE PERSON, not only the model. Every instruction this plugin
    # sends through additionalContext is invisible from a chair, and whether it was obeyed is
    # unknowable - measured three times today with three different messages. systemMessage is
    # the one channel a model cannot swallow, so the two loud events must carry one.
    import inspect
    src = inspect.getsource(on_user_prompt)
    assert "systemMessage=" in src, "the wind-down no longer speaks to the user"
    assert "winding down" in src, "the acknowledgement line was dropped"
    src2 = inspect.getsource(on_pre_agent)
    assert "systemMessage=" in src2, "a refused dispatch no longer speaks to the user"
    # ⚠ And the emitters must actually put it in the JSON, or the calls above are decoration.
    import io as _io2, json as _json2, contextlib
    for fn, kw in ((context_note, {"systemMessage": "SEEN"}),
                   (deny, {"systemMessage": "SEEN"})):
        buf = _io2.StringIO()
        with contextlib.redirect_stdout(buf):
            fn("UserPromptSubmit", "to the model", **kw)
        out = _json2.loads(buf.getvalue())
        assert out.get("systemMessage") == "SEEN", out
        assert "to the model" in _json2.dumps(out), out

    # ⛔ ONCE PER LEVEL, PER SESSION - and re-armed when the level CHANGES. Without the mark
    # every message would carry the same warning, which trains a reader to skip the very line
    # that says whether the brake is alive. Without the re-arm, crossing from PACE into STOP
    # would say nothing at all, which is the more dangerous half.
    with tempfile.TemporaryDirectory() as sd:
        os.makedirs(os.path.join(sd, "state"))
        mark = state_path(sd, "s1", "warned")
        os.makedirs(os.path.dirname(mark), exist_ok=True)
        with open(mark, "w", encoding="utf-8") as fh:
            fh.write("PACE")
        with open(mark, encoding="utf-8") as fh:
            assert fh.read().strip() == "PACE"
        # the same level is silent, a different level is not - the read the gate performs
        for verdict, speaks in (("PACE", False), ("STOP", True)):
            with open(mark, encoding="utf-8") as fh:
                same = fh.read().strip() == verdict
            assert (not same) is speaks, verdict
        # ⚠ and it is keyed by SESSION: another session has no mark and must be told.
        assert not os.path.exists(state_path(sd, "s2", "warned"))

    # ⛔ ULTRACODE IS REFUSED, EVERY TOOL, EVERY CALL. max and below proceed. This is the
    # rule the owner asked to be hard rather than advisory: ultracode re-states its workflow
    # instruction every turn, so warning once leaves a session burning planning tokens on
    # something that will be denied for as long as it runs.
    with tempfile.TemporaryDirectory() as sd:
        os.makedirs(os.path.join(sd, "state"))
        base = {"session_id": "u", "hook_event_name": "PreToolUse"}
        assert effort_level(dict(base, effort={"level": "ULTRACODE"})) == "ultracode"
        assert effort_level(dict(base, effort={"level": " Max "})) == "max"
        assert effort_level(dict(base)) == (os.environ.get("CLAUDE_EFFORT") or "").lower()
        # every tool, and it keeps refusing
        seen_screen = 0
        for _ in range(3):
            got = ultracode_refusal(dict(base, effort={"level": "ultracode"}), None, sd)
            assert got is not None, "ultracode was allowed through"
            reason, msg = got
            assert "refused" in reason and "/effort" in reason, reason
            seen_screen += 1 if msg else 0
        assert seen_screen == 1, "the screen message repeated (%d times)" % seen_screen
        # ⭐ ...and anything else is left alone entirely.
        for level in ("max", "xhigh", "high", "medium", "low", ""):
            assert ultracode_refusal(dict(base, effort={"level": level}), None, sd) is None, level

    # ⛔ RULE 8 MUST SURVIVE IN THE PREPEND. It is the only channel that reaches every
    # sub-agent at every depth without the dispatcher remembering to say it - and "tidy up
    # after yourself" is trained behaviour, so the instruction not to is load-bearing.
    for token in ("SCRATCH FILES GO IN THE TASK FOLDER", "YOU DO NOT DELETE THEM",
                  "{task_root}/<task>/scratch/"):
        assert token in PREPEND, token
    filled = PREPEND.format(task_root="Memory/tasks", plan_glob="prompts*.md",
                            protocol_doc="PROTOCOL.md", max_model_price=5)
    # ⛔ THE MODEL RULE MUST REACH EVERY DEPTH TOO. A sub-agent that dispatches further never
    # read `dispatch-protocol`; this block is the only channel that binds it, and a rule an
    # agent meets only as a refusal is a rule it tries to route around.
    assert "CHOOSE THE MODEL BEFORE YOU DISPATCH" in filled, filled[:400]
    assert "$5 per million INPUT tokens" in filled, "the limit did not interpolate"
    assert "Memory/tasks/<task>/scratch/" in filled, filled[-600:]

    print("selftest OK")
    return 0


def _utf8_console():
    """Make output survive a legacy console codepage.

    ⛔ THE MESSAGE THIS GATE PRINTS CONTAINS ⚠ AND ⭐, and a Windows console defaults to a
    legacy codepage - cp950 on this machine - where a single one of those raises
    UnicodeEncodeError. Measured: run directly, the SessionStart line died on encode and the
    session was told NOTHING - not the protocol pointer, not that the usage brake was
    inactive. run.sh and run.cmd both set PYTHONIOENCODING=utf-8, so the hook path was
    safe; every other way of invoking this file was not, and the failure is silent because
    the gate fails open by design.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


if __name__ == "__main__":
    _utf8_console()
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    try:
        main()
    except Exception as exc:            # never block a dispatch because the gate broke
        try:
            r = repo_root(os.getcwd())
            if any(os.path.exists(os.path.join(r, m)) for m in REPO_MARKERS):
                log(r, "GATE-ERROR %r" % (exc,))
        except Exception:
            pass
        try:
            with open(os.path.join(tempfile.gettempdir(), "dispatch-gate-error.log"),
                      "a", encoding="utf-8") as f:
                f.write("%s %r%s" % (time.strftime("%Y-%m-%d %H:%M:%S"), exc, "\n"))
        except Exception:
            pass
    sys.exit(0)
