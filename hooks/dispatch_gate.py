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
import model_pricing  # noqa: E402  - the published price table; see its docstring
import shim  # noqa: E402  - the version-free launcher; see its docstring
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
    # ⛔ HOW LONG A PER-SESSION STATE MARKER SURVIVES, in days. state/ holds one small file per
    # session per kind (.start, .branch-*, .skill-seen-*, .warned*, ...) and they are dead the
    # moment the session ends; prune_state() sweeps them by age at session start. ⚠ IT IS A
    # SAFETY margin, not a usefulness one: a live session's .start is the switch that keeps its
    # brake ON, so this must exceed the longest a single session can run - 7 days is that margin,
    # not a tuning knob to shrink casually. ⚠ DELETE-SAFE like history_keep_days: a bad value
    # (string, negative, 0) means KEEP EVERYTHING, never "fall back to 7 and start deleting" -
    # so it is coerced by usage._days(), NOT listed in NUMERIC_KEYS.
    "state_keep_days": 7,
    "brake_on_usage": True,             # deny a dispatch when the verdict is STOP
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
    # against the published base input price in model_pricing.json. 5 allows haiku, sonnet and
    # the current opus; it refuses fable and the retired opus 4/4.1. null switches the check
    # off.
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
    # ⛔ PAST THE SOFT THRESHOLD, A DISPATCH NEEDS A CURRENT HANDOFF ON DISK. Default ON,
    # and the reasoning is the owner's: the handoff is written when the agent hits STOP,
    # which assumes it still gets a turn - and a real cut-off, the server refusing, gives no
    # turn at all. ⇒ The file has to exist BEFORE the interruption, and the window between
    # soft and hard is exactly the room to write it in.
    # ⚠ Set false and a dispatch is allowed without one; the resume then wakes with the
    # RECONSTRUCTION prompt instead (see hooks/resume.py), which costs a chunk of the new
    # window rediscovering what the last one was doing.
    "require_handoff_past_soft": True,
    # ⭐ ARM THE RESUME AUTOMATICALLY once there is something worth resuming. Default ON.
    # The one thing the owner cannot recover from is a run that ends with nobody having
    # armed anything - the handoff is on disk and nothing ever reads it. ⚠ Arming is
    # REVERSIBLE (`resume.py --cancel`, and the run stands down by itself if a session is
    # alive); missing the moment is not. Set false to arm by hand only.
    "auto_arm_resume": True,
    # ⭐ HOW OLD THE PRICE TABLE MAY GET before the gate forks a background refresh, in hours.
    # ⚠ The refresh NEVER blocks anything: the session that notices the staleness keeps using
    # the file it has, and the new numbers land for the next one. So a longer interval costs
    # accuracy, never latency. 0 or null switches the refresh off and pins the table to
    # whatever is on disk.
    "model_price_hours": 24,
    # ⛔ THE ONE SWITCH THAT STOPS THIS PLUGIN TALKING TO THE INTERNET. It did not, before
    # this. Set false and nothing is ever fetched; the gate uses the seed that ships in the
    # repository, which is a real table taken from the published page on the day it was cut.
    "model_price_update": True,
    # The page the table is parsed from. Overridable so a mirror or a pinned copy can be used;
    # ⚠ whatever it points at must be that page's markdown, not an HTML rendering of it.
    "model_price_url": model_pricing.SOURCE_URL,
    # ⭐ DID THE FILE THE PROMPT DEMANDED ACTUALLY APPEAR? Default ON. Two halves, one
    # switch, because they answer one question: PreToolUse warns when a read-only
    # `subagent_type` is paired with a prompt telling it to CREATE a file, and PostToolUse
    # stats those files when the sub-agent returns. ⛔ NEITHER HALF EVER REFUSES - both are
    # advisory. A read-only agent whose prompt merely mentions a path it must READ is
    # perfectly legitimate, and refusing that would make this gate wrong more often than the
    # dispatcher is. Set false to silence both.
    "guard_agent_report_file": True,
    # ⭐ THE WIND-DOWN ON EVERY TOOL CALL. Default ON. At PACE or STOP the gate adds one
    # note - to the model and to the screen - from the path EVERY tool call crosses, at most
    # once per level per agent. ⛔ It never refuses anything: the STOP instruction is "write
    # a handoff, then stop", and writing needs the very tools a refusal would block.
    # ⚠ It exists because the two places this used to fire from - a dispatch and a user
    # prompt - are both ABSENT from the kind of run that exhausts a window. Measured
    # 2026-08-31: 0% to 100% in 85 minutes with zero dispatches, no user prompt, and not one
    # `USAGE(` line in any gate log on the machine. Set false to silence it.
    "guard_wind_down": True,
    # ⭐ HOW FRESH ANOTHER SESSION'S HEARTBEAT MUST BE for `guard_cowork_first` to call it a
    # live peer, in minutes. The gate touches `state/<sid>.alive` on every hook event. See
    # cmd_guards.PEER_ALIVE_MIN for the two fail-open directions. Coerced like the other
    # numeric keys: a bad value is logged and replaced by this default, never a crash.
    "peer_alive_min": cmd_guards.PEER_ALIVE_MIN,
    # ⭐ A PROMPT AFTER THIS MANY IDLE MINUTES IS A WAKE (0.68, ADR 20261001-085000 D8): a woken
    # session with a live peer is asked to re-check-in on the cowork board. See wake_reason().
    "wake_gap_min": 30,
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

# ⭐ THE PRICE TABLE IS A FILE NOW, NOT A LITERAL IN THIS MODULE. Every number comes from
# Anthropic's published pricing page, parsed by hooks/model_pricing.py into
# `model_pricing.json`, and refreshed in the background by keep_prices_fresh().
#
# ⛔ IT USED TO BE TYPED IN HERE, and the table that replaced it caught the typed one being
# wrong: this file priced Claude Haiku 3.5 at $1 when the published price is $0.80, because
# that one row was reasoned from the harness's own weight function instead of read from the
# page. ⇒ A table that cannot be checked against its source drifts silently, and it did.
#
# ⚠ THE `pricing` FIELD INSIDE THE INSTALLED BINARY WAS THE OTHER CANDIDATE AND IT LOST.
# Reading it means a machine that has not updated Claude Code prices models from an old
# catalog - stale in a different place, not fresher. The published page is the only source
# that does not depend on some local install being current.
#
# ⇒ WHAT `FAMILY_LATEST` BECAME. The page publishes no "latest" flag, so model_pricing.py
# derives it from the version in each display name and writes it into the file. `opus`
# therefore resolves to whatever the page currently calls the newest opus - which is the whole
# point, because `opus` meant $15 in 2025 and means $5 now.
_DOC = None


def price_doc():
    """(doc, where) for this process, loaded once. `(None, reason)` when nothing is readable.

    ⚠ LAZY, NOT AT IMPORT. The test suite and `--selftest` import this module with a state
    directory that is a temporary fixture and may not exist yet; loading at import time would
    bind the table to whatever the state directory looked like before the test set it up.
    """
    global _DOC
    if _DOC is None:
        _DOC = model_pricing.load(usage.state_dir())
    return _DOC


def prices():
    """model ID -> its row. `{}` when no table is readable; callers must fail OPEN on that."""
    doc, _where = price_doc()
    return (doc or {}).get("models") or {}


def price_of(mid):
    return (prices().get(mid) or {}).get("input")


def family_latest():
    """((family, newest model ID), ...) for the families a session may NAME, dearest first.

    ⛔ SORTED BY PRICE, NOT BY THE FILE'S ORDER. Two callers depend on the order: the refusal
    names `allowed[0]` as the best model still permitted, and the availableModels clamp takes
    the most expensive usable family. Insertion order would make both answers depend on how
    the page happened to be laid out that day.

    ⛔ `mythos` IS PRICED BUT IS NOT HERE - see model_pricing.ALIAS_FAMILIES. It is on the
    published page, so a full `claude-mythos-5` is priced correctly; but a bare `mythos` is not
    an alias any session can select, and offering it as one would invent a dispatch that
    cannot happen.
    """
    doc, _where = price_doc()
    fams = (doc or {}).get("families") or {}
    m = prices()
    rows = [(f, fams[f]) for f in model_pricing.ALIAS_FAMILIES if fams.get(f) in m]
    return tuple(sorted(rows, key=lambda r: -m[r[1]]["input"]))


def price_sentence():
    """`haiku $1, sonnet $2, opus $5, fable $10` - generated, for the sub-task prompt.

    ⛔ THIS USED TO BE FOUR NUMBERS TYPED INTO `PREPEND`. Removing the table from this module
    while leaving its numbers in the prompt template would have moved the drift rather than
    ended it: the gate would refuse at one price while the prompt promised another.
    """
    m = prices()
    rows = sorted(family_latest(), key=lambda r: m[r[1]]["input"])
    return ", ".join("%s $%g" % (f, m[mid]["input"]) for f, mid in rows)


def dearest():
    """(model ID, price) of the most expensive model on the table, or (None, None).

    ⭐ For the one example the sub-task prompt needs to carry: naming an old version can cost
    MORE than naming the family. Sorted first so ties resolve the same way every run.
    """
    m = prices()
    if not m:
        return None, None
    mid = max(sorted(m), key=lambda k: m[k]["input"])
    return mid, m[mid]["input"]

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
   cost at most ${max_model_price} per million INPUT tokens: {price_list} - and `best`
   means fable. Naming an old version can cost MORE than naming the family ({dear_example}).
   Omitting `model` is always allowed and inherits the model already in use, so there is
   always a legal dispatch. These prices are read from Anthropic's published pricing page,
   not from anybody's memory; the reasoning is in `dispatch-protocol`.
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


def _positive_number(value):
    """A number > 0 out of a config value, or None. Strings that parse are accepted; a whole
    number comes back as int, because `range()` and `%d` downstream need one.

    ⛔ A WRONG TYPE HERE IS A FAIL-OPEN, NOT A WRONG NUMBER. Measured 2026-09-02 by the review
    of 0.56.2: `"slot_ttl_min": "abc"` (or `null`, `"30"`, `[30]`) made `claim_slot()` raise
    TypeError at `cfg["slot_ttl_min"] * 60`; main()'s outer handler swallowed it, the process
    exited 0 with nothing on stdout, and the dispatch that should have been REFUSED went
    through. `false` and a negative number reclaimed every slot on every dispatch, which is
    the concurrency limit switched off. ⚠ bool is a subclass of int and is rejected on purpose.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    # ⚠ NaN and ±inf are floats too: "inf" and "1e999" parse, and range(inf) is the same
    # TypeError this function exists to keep out of the decision path.
    if not isinstance(value, (int, float)) or value != value or value in (float("inf"),
                                                                            float("-inf")):
        return None
    if value <= 0:
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


# The keys arithmetic or a comparison is done on. A string or null in any of them raised
# TypeError inside a decision path, and a decision path that raises prints nothing - an ALLOW.
# ⚠ NOT `max_model_price`: it has its own parsing in model_refusal() and three decisions of its
# own that this coercion would silently overturn - a model NAME is accepted where a number was
# meant, `null` switches the check off, and a mistyped ceiling fails OPEN with a
# MODEL-PRICE-LIMIT-UNKNOWN log line (test_guards.py case_model_price_limit pins all three).
NUMERIC_KEYS = ("slot_ttl_min", "approval_ttl_min", "max_slots", "peer_alive_min")
# ⛔ AND ONE OF THEM MUST BE A WHOLE NUMBER. `max_slots` reaches range() in claim_slot() and
# release_slot(); 1.5 passes "a number > 0" and range(1.5) is the same TypeError - measured
# 2026-09-02 by the round-2 review through the real process: with an approval for 2 and
# max_slots 1.5, the refusal printed nothing and the dispatch was ALLOWED, and no slot was
# ever released again.
INTEGER_KEYS = ("max_slots",)


def gate_config(root, sdir):
    cfg = dict(DEFAULTS)
    for path in (os.path.join(sdir, "config.json"),
                 os.path.join(root, ".claude", "dispatch-guard.json")):
        disk = usage.read_json(path, {}) or {}
        for source in (disk, disk.get("dispatch") or {}):
            for k in DEFAULTS:
                if k in source:
                    cfg[k] = source[k]
    for k in NUMERIC_KEYS:
        good = _positive_number(cfg[k])
        if k in INTEGER_KEYS and not isinstance(good, int):
            good = None
        if good is None:
            # ⚠ SAID IN THE LOG, on every read. A setting that is silently replaced by the
            # default is the same defect as a setting that silently crashes the gate - the
            # person who wrote it thinks it is in force. This fires once per hook call for
            # as long as the value stays wrong, which is the right volume for "your config
            # is being ignored".
            log(root, "CONFIG-IGNORED(%s=%r) using %r" % (k, cfg[k], DEFAULTS[k]))
            good = DEFAULTS[k]
        cfg[k] = good
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


def safe_session(session_id):
    """A session id as ONE filename component. The single definition of that rule.

    ⛔ IT IS NOT ONLY `state/`'s ANY MORE. resume.py names its per-session record and its OS
    task with the same key (ADR 20260917-132015, D1/D2), and two copies of a sanitising rule
    are two chances for a record and the task that fires it to disagree about their own name.
    ⚠ `"nosession"` on an empty id is deliberate and is the pre-existing behaviour: sessions
    without an id share one slot, exactly as they always did.
    """
    return "".join(c for c in str(session_id) if c.isalnum() or c in "-_")[:64] or "nosession"


def state_path(sdir, session_id, suffix):
    return os.path.join(sdir, "state", "%s.%s" % (safe_session(session_id), suffix))


def log(root, message):
    """⛔ Errors go here too. A compensating control nobody reads is not one.

    ⛔ TWO DESTINATIONS, AND THE SECOND ONE IS THE AUTHORITATIVE COPY. `root` comes from
    repo_root(), which walks up from the payload's `cwd` looking for CLAUDE.md, AGENTS.md or
    .git - and in a project carrying NONE of those it falls through to the cwd itself, which
    the Bash tool's `cd` moves between calls. Measured 2026-09-01 in `OLD_Books`: one
    session's log arrived as FOUR fragments in four directories, each with a stray `.claude/`
    beside it, and the hour that mattered looked empty in the one place anybody would look.
    ⇒ "No denial appeared" and "the log went somewhere else" must not be the same picture.

    ⭐ The state directory never moves, so the copy there is the one to read when the answer
    matters. The per-repository copy stays because it is where a person looks first, and
    because removing it would be a second change nobody asked for.
    """
    stamped = "%s %s%s" % (time.strftime("%Y-%m-%d %H:%M:%S"), message, "\n")
    # ⛔ A bare newline above, NEVER os.linesep. Text mode already translates it to the
    # platform's ending on Windows, so adding os.linesep on top produces a carriage return
    # too many, and every record is followed by a blank line. Measured 2026-08-26: every log
    # this plugin wrote was double-spaced - the gate log and the imported usage history alike.
    paths = []
    if root:
        paths.append(os.path.join(root, ".claude", "dispatch_gate.log"))
    try:
        # ⚠ IT CAN RETURN NOTHING, and joining None raises TypeError from inside the logger -
        # which would take out the one call every failure path in this module relies on.
        # Measured: the module's own --selftest reached here with no state directory.
        _sd = usage.state_dir([])
        if _sd:
            paths.append(os.path.join(_sd, "dispatch_gate.log"))
    except Exception:
        pass
    for path in paths:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(stamped)
        except Exception:
            # ⚠ ONE FAILING DESTINATION MUST NOT SILENCE THE OTHER. The whole point of the
            # second copy is that it survives whatever went wrong with the first.
            continue


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

    ⚠ Two clocks, not one. `token_usage.json` says when the DATA went stale; the mark says when
    a child was last STARTED. Only the second one moves when a fetch fails, so only the
    second one can stop a failing fetch from being retried forever.
    """
    def age(name):
        try:
            return now - os.stat(os.path.join(sdir, name)).st_mtime
        except OSError:
            return None

    data = age("token_usage.json")
    if data is not None and data < every:
        return False
    started = age(CLOCK_MARK)
    if started is not None and started < every:
        return False
    return True


def keep_clock_running(sdir):
    """Start a DETACHED refresh when token_usage.json has gone stale, and never wait for it.

    ⭐ THIS IS WHAT MAKES THE BRAKE WORK WITH NO STATUSLINE. The numbers only ever moved
    when something re-ran usage.py on a timer: the statusline, which Claude Code renders,
    or `--watch` in a terminal. The VS Code extension renders no statusline, so an
    extension-only user had a brake that read NO-DATA forever unless they wired a per-project
    task. ⇒ The statusline and `--watch` are now DISPLAY. This is the clock.

    ⛔ IT IS NOT THE SYNCHRONOUS FETCH ensure_fresh() REFUSES TO DO, and the difference is
    the whole design. A blocking HTTP call here would stall every dispatch that crossed the
    interval boundary. This forks and returns; the number lands in token_usage.json for a LATER
    call to read. A dispatch is never made to wait on the network.

    ⭐ Why the gate is the right place: dispatch happens inside a session, this hook already
    runs on every tool call of every session, so the sessions that need a fresh number are
    exactly the ones already executing this code. Nothing new has to be installed, and
    nothing is per-project - `token_usage.json` is per-ACCOUNT, like the usage it records.

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
    # every session where token_usage.json was stale. A clock is a convenience; it must never be
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


# ⚠ TWO CLOCKS AGAIN, for the same reason CLOCK_MARK has two. `model_pricing.json` says when
# the DATA was taken; this mark says when a child was last STARTED. A page that 404s or a
# proxy that eats the request leaves the data old for ever, so without the second clock a
# failing fetch would fork one process per session start until somebody noticed.
PRICE_MARK = "model_pricing.spawn"
PRICE_RETRY = 900


def prices_due(sdir, cfg, now=None):
    """Is a price refresh due AND has one not just been started? Pure decision, no side effects.

    ⛔ Split out from keep_prices_fresh() for the same reason clock_due() is split from
    keep_clock_running(): the decision can then be CHECKED without spawning a process or
    touching the network. ⚠ Two clocks, not one - `model_pricing.json` says when the DATA was
    taken, PRICE_MARK says when a child was last STARTED. Only the second moves when a fetch
    fails, so only the second can stop a failing fetch from being retried on every session.
    """
    now = time.time() if now is None else now
    if not cfg.get("model_price_update", DEFAULTS["model_price_update"]):
        return False
    doc, _where = model_pricing.load(sdir)
    if not model_pricing.due(doc, cfg.get("model_price_hours",
                                          DEFAULTS["model_price_hours"]), now):
        return False
    try:
        if now - os.path.getmtime(os.path.join(sdir, PRICE_MARK)) < PRICE_RETRY:
            return False
    except OSError:
        pass
    return True


def keep_prices_fresh(sdir, cfg, now=None):
    """Fork a detached price refresh when the table has aged past `model_price_hours`.

    ⛔ IT NEVER WAITS, AND THE HOOK NEVER FETCHES. This is the whole reason the update lives
    in a child: a synchronous HTTP call inside a hook would stall a tool call for as long as
    the network took, and a slow proxy would be indistinguishable from a hung plugin. The
    session that notices the staleness carries on with the table it already has; the new
    numbers land for the next session.

    ⚠ The child re-reads the file and decides for itself whether to fetch. This function
    decides whether to FORK. Neither is allowed to assume the other got it right.

    Returns True when it started a child.
    """
    now = time.time() if now is None else now
    if not prices_due(sdir, cfg, now):
        return False
    mark = os.path.join(sdir, PRICE_MARK)
    try:
        os.makedirs(sdir, exist_ok=True)
        with open(mark, "w") as f:
            f.write(str(now))
    # ⛔ NOT `except OSError`. A refresh is a convenience; nothing it can raise may be allowed
    # to escape into main() and take enforcement down with it. See keep_clock_running().
    except Exception:
        return False

    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
          "stderr": subprocess.DEVNULL, "cwd": sdir}
    if os.name == "nt":
        kw["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0x8)
                               | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200))
    else:
        kw["start_new_session"] = True
    try:
        # ⚠ --dir is not optional, for the same reason as the usage child: model_pricing.py
        # resolves its own state directory, so a child launched without it can write to a
        # different directory than the one this function just judged stale.
        subprocess.Popen([sys.executable, os.path.join(HERE, "model_pricing.py"),
                          "--update", "--dir", sdir,
                          "--url", cfg.get("model_price_url",
                                           DEFAULTS["model_price_url"])], **kw)
    except Exception:
        return False
    return True


def runnable(script):
    """A command the model can actually RUN, with NO VERSION NUMBER IN IT.

    ⛔ The messages used to hand over `.../usage.py --verdict`. The hook scripts are not
    executable and carry no shebang association on either platform, so the one command the
    gate named as the repair for a blind brake did not run when it was pasted. Everything
    goes through a launcher, which is also how the interpreter is found - see hooks/run.sh
    for why naming `python` directly is wrong on both platforms.

    ⛔ AND IT NAMES THE SHIM, NOT THIS DIRECTORY. `HERE` is inside
    `.../cache/dispatch-guard/dispatch-guard/<VERSION>/`, so a command built from it stops
    working - or worse, keeps working against an OLD copy - the next time the plugin
    updates. A model that pastes such a command into a script or a task carries the version
    with it. See hooks/shim.py.
    """
    return shim.command(usage.state_dir(), script)


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
            note = (" ⭐ The `Claude Usage Watcher` task was added to VS Code's USER tasks, so "
                    "EVERY project gets the usage line from now on - there is no per-project "
                    "file and nothing was written into this repository. ⚠ It starts by itself "
                    "on the next FOLDER OPEN; to start it in THIS window instead, the person "
                    "runs `Tasks: Run Task` from the command palette. Details: %s"
                    % "; ".join(lines))
            # ⛔ THE NO-RELOAD ROUTE COMES FIRST, and it is the whole of what a person can act
            # on right now. This used to offer only "reopen the folder", which reads as "shut
            # what you are doing" - and nothing outside VS Code can start the task for them:
            # the 1.135.0 CLI has no option that runs a task in a window already running, so
            # the palette is the only door. Measured 2026-08-27, the same day the user-level
            # task was chosen: it appears in Run Task and starts there.
            seen = ("added the `Claude Usage Watcher` task to VS Code's user tasks - it covers "
                    "every project. ⭐ To start it NOW without reloading: press F1, run "
                    "`Tasks: Run Task`, pick `Claude Usage Watcher`. Otherwise it starts by "
                    "itself the next time this folder opens.")
        else:
            note = seen = None
        # ⚠ A per-project file from an earlier version would now open a SECOND identical
        # terminal beside the user-level one. It is ours, so it goes - unless it is tracked
        # by git, where removing it would dirty somebody's tree.
        if install.vscode_task_present(root):
            if _git_tracked(root, ".vscode/tasks.json"):
                extra = ("this project also carries an OLDER per-project `Claude Usage Watcher` "
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


def touches_real_state(sdir):
    """May this gate touch install.py's paths (the real shim, ~/.claude/settings.json)? Never raises.

    ⛔ install.py hard-codes ~/.claude/dispatch-guard and writes its shim there pointed at the
    copy that IMPORTED it (`write_shim`). The statusline repairs below reach it from SessionStart,
    so every test driving a real SessionStart against a temporary state dir re-pointed the
    USER'S shim at the checkout under test - measured 2026-10-01: test_guards, test_net_zone and
    test_slot_lifecycle each rewrote it, and the scheduled resumes and the statusline then ran
    uncommitted code. ⇒ Only when this gate's state dir IS install's. ⚠ A user who set
    $CLAUDE_DISPATCH_DIR loses the automatic statusline repair; install.py never honoured that
    variable anyway (usage.state_dir's docstring).
    """
    if sdir is None:
        return True
    try:
        sys.path.insert(0, os.path.dirname(HERE))
        import install
        same = (os.path.normcase(os.path.realpath(sdir))
                == os.path.normcase(os.path.realpath(install.STATE_DIR)))
    except Exception:
        return False
    return same


def maybe_adopt_statusline(cfg, sdir=None):
    """Take an EMPTY statusline slot, so the CLI shows the line with nothing typed.

    ⛔ Only when the slot is empty. See install.adopt_statusline_if_empty() for why that
    boundary is the whole of the safety here.
    """
    if not cfg.get("auto_statusline") or not touches_real_state(sdir):
        return None, None
    try:
        sys.path.insert(0, os.path.dirname(HERE))
        import install
        # ⚠ KEPT AS A CALL THAT NOW DOES NOTHING, on purpose. seed_config() no longer
        # writes config.json at all - see its docstring - and the call stays so that the
        # decision lives in ONE place. A marketplace user may never run install.py, so if
        # seeding ever comes back, this is the path that has to do it too.
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


def maybe_repoint_statusline(sdir=None):
    """Repair a statusline left aimed at a version `claude plugin update` moved on from.

    ⛔ WHY IT IS SAFE TO DO WITHOUT ASKING, when writing .vscode/tasks.json is not. This
    touches one key in the user's OWN settings that this plugin already owns, and only ever
    aims it at the copy that is running anyway. Nothing new appears, nobody's repository
    changes, and a statusline belonging to another tool is never touched.

    ⚠ Cheap: one file read, and it returns immediately when the path is already right.
    """
    if not touches_real_state(sdir):
        return None, None
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


def session_cwd(sdir, session_id):
    """The working directory this session STARTED in, or None.

    ⛔ THE START-TIME ONE, NOT THE CURRENT ONE, and the difference is the whole reason this
    exists. A hook payload's `cwd` follows the Bash tool's own `cd`, which persists between
    calls - measured 2026-09-01 in a project with no repository marker, where one session's
    gate log arrived as FOUR fragments in four directories because `repo_root()` was reading
    a `cwd` that had moved. ⇒ A resume armed against the moved value would wake the work in
    the wrong tree, silently, which is worse than not waking at all.

    ⭐ IT LIVES IN THE `.start` FILE, which already exists per session and is already pruned
    by age. Its only other reader takes the mtime, so the content was free to use.
    ⚠ Tolerates the old plain-timestamp content: a session stamped before this shipped simply
    has no cwd, and the caller must treat None as "not recorded", never as "the root".
    """
    try:
        with open(state_path(sdir, session_id, "start"), encoding="utf-8") as f:
            raw = f.read().strip()
    except OSError:
        return None
    try:
        got = json.loads(raw)
    except ValueError:
        return None                   # the pre-0.56 form: a bare timestamp
    cwd = got.get("cwd") if isinstance(got, dict) else None
    return cwd if isinstance(cwd, str) and cwd else None


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
    table = prices()
    # ⛔ `mid in name` ONLY - never `name in mid`. The reverse would let the bare alias `opus`
    # match whichever opus ID happens to sort first, which after a longest-first sort is the
    # $15 one. A bare alias must fall through to the family branch below.
    #
    # ⭐ LONGEST ID FIRST is what makes the shortened IDs on the published page safe. The page
    # lists "Claude Opus 4" ($15) and "Claude Opus 4.5" ($5), which become `claude-opus-4` and
    # `claude-opus-4-5`; the first is a prefix of the second, so a shortest-first walk would
    # price every 4.x opus at $15 and refuse work that is perfectly legal.
    for mid in sorted(table, key=len, reverse=True):
        short = mid[7:] if mid.startswith("claude-") else mid
        if mid in name or short in name:
            return mid, table[mid]["input"], True
    latest_by_family = family_latest()
    for family, latest in latest_by_family:
        if name == family:
            return latest, table[latest]["input"], True
    for family, latest in latest_by_family:
        if family in name:
            return latest, table[latest]["input"], False
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
    # ⛔ NO TABLE MEANS NO CHECK, LOUDLY. Neither the shipped seed nor the live copy could be
    # read - a deleted file, a corrupted write, a state directory somebody chmod'd. Every
    # model would price as unrecognised and every dispatch with a `model` would be refused,
    # which is a cost guard bricking the work it exists to pace. ⇒ It fails OPEN and says so,
    # the same rule the misconfigured ceiling below follows.
    if not prices():
        if log_to:
            _doc, where = price_doc()
            log(log_to, "MODEL-PRICE-TABLE-MISSING (%s) - check not applied. Run `%s --update`"
                % (where, runnable("model_pricing.py")))
        return None
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
    usable = [(fam, price_of(latest)) for fam, latest in family_latest()
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
                "model. The table is `%s`, taken from %s - run `%s --show` to read it."
                % (raw, ", ".join(f for f, _l in family_latest()), best_allowed,
                   model_pricing.FILENAME, model_pricing.SOURCE_URL,
                   runnable("model_pricing.py")))
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


def model_note(cfg, sdir, avail=None):
    """One sentence naming the models this session may dispatch, for the OPENING context.

    ⭐ THIS IS THE HALF THE HOOK CANNOT DO. A PreToolUse refusal arrives after the agent has
    already chosen, written the prompt and spent the turn - and a rule an agent only ever
    meets as a refusal is a rule it starts trying to route around. Saying it once, up front,
    with the actual permitted families in it, costs one line and removes the retry loop.
    ⇒ The hook is still there. It is the backstop, not the announcement.

    ⚠ IT NAMES WHAT IS ALLOWED AND WHAT IS NOT. Listing only the permitted models reads as a
    suggestion; naming the refused ones and their prices is what makes it a limit.

    ⛔ AND IT APPLIES THE SAME `availableModels` CLAMP model_refusal() APPLIES. Without that
    this function announces a model the gate then refuses - on an account restricted to
    sonnet it would say "you may dispatch `opus`", the agent would dispatch opus, and the
    refusal it was written to prevent arrives anyway. ⇒ An announcement that disagrees with
    the enforcement is worse than no announcement: it teaches the agent the gate is unreliable.
    """
    doc, where = price_doc()
    m = prices()
    if not m:
        return (" ⛔ NO MODEL PRICE TABLE IS READABLE (%s), so the sub-agent model ceiling is "
                "NOT being enforced this session - do not report it as active. Run `%s "
                "--update`." % (where, runnable("model_pricing.py")))
    limit = cfg.get("max_model_price", DEFAULTS["max_model_price"])
    if limit is None or limit is False:
        return " ⚠ The sub-agent model ceiling is switched off (`max_model_price` is null)."
    if isinstance(limit, bool):
        cw = None
    elif isinstance(limit, (int, float)):
        cw = float(limit)
    else:
        cw = model_price(limit)[1]
    if not cw or cw <= 0:
        return ""
    rows = [(f, mid) for f, mid in family_latest() if family_available(f, avail)]
    narrowed = None
    if rows and max(m[mid]["input"] for _f, mid in rows) < cw:
        cw = max(m[mid]["input"] for _f, mid in rows)
        narrowed = next(f for f, mid in rows if m[mid]["input"] == cw)
    ok = ["`%s` $%g" % (f, m[mid]["input"]) for f, mid in reversed(rows)
          if m[mid]["input"] <= cw]
    no = ["`%s` $%g" % (f, m[mid]["input"]) for f, mid in rows if m[mid]["input"] > cw]
    st = model_pricing.status(sdir)
    # ⚠ A refresh that has been failing for a month looks exactly like one that never needed
    # to run. Said out loud, and only when it actually failed.
    warn = ("" if not st or st.get("ok") else
            " ⚠ The last price refresh FAILED: %s" % str(st.get("reason", ""))[:140])
    return (" ⭐ SUB-AGENT MODELS: `max_model_price` allows $%g per million input tokens%s, so "
            "you may dispatch %s%s. Omitting `model` inherits this session's model and is "
            "always allowed. Choose BEFORE you dispatch - the gate refuses the rest. Prices "
            "%s (%s).%s"
            % (cw,
               (" (narrowed to `%s` by your `availableModels` allowlist)" % narrowed)
               if narrowed else "",
               ", ".join(ok) or "nothing on this table",
               (" and NOT %s" % ", ".join(no)) if no else "",
               model_pricing.age_line(doc), where, warn))


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


def prepend_head(cfg):
    """The protocol block, with the live price table interpolated into rule 7.

    ⚠ THE FALLBACK WORDING MATTERS. With no readable table there are no numbers to promise,
    and inventing plausible ones here is exactly the failure this whole change removed. The
    rule still states the ceiling - which is the owner's setting and is always known - and
    points at the file instead of naming prices it cannot read.
    """
    mid, dear = dearest()
    return PREPEND.format(
        task_root=cfg["task_root"], plan_glob=cfg["plan_glob"],
        protocol_doc=cfg["protocol_doc"],
        max_model_price=cfg.get("max_model_price", DEFAULTS["max_model_price"]),
        price_list=price_sentence() or ("the table in %s" % model_pricing.FILENAME),
        dear_example=("%s is $%g" % (mid, dear)) if mid
        else "an old version can be several times the family's current price")


def allow_prepended(event, tool_input, cfg, note, warn=None):
    """Allow the dispatch with the protocol block prepended.

    ⛔ `note` AND `warn` GO TO DIFFERENT AUDIENCES, and mixing them up is this plugin's most
    repeated mistake - see context_note(). `note` is prepended to the SUB-AGENT's prompt, so
    it can only say things the sub-agent should act on. `warn` is about the dispatch itself
    and the DISPATCHER has to act on it, so it rides out as `additionalContext` (to the
    dispatching model) and `systemMessage` (onto the person's screen). Putting a dispatcher
    warning in `note` would send it to the one agent that cannot do anything about it.

    ⚠ `additionalContext` beside `permissionDecision: "allow"` is deliberate and permitted:
    the PreToolUse schema carries both, and the dispatcher attaches the context independently
    of the permission behaviour.
    """
    prompt = tool_input.get("prompt")
    if not isinstance(prompt, str):
        return
    head = prepend_head(cfg)
    if note:
        head += "!! %s\n\n" % note
    updated = dict(tool_input)
    updated["prompt"] = head + prompt
    out = {"hookSpecificOutput": {
        "hookEventName": event, "permissionDecision": "allow",
        "permissionDecisionReason": "dispatch gate: protocol prepended",
        "updatedInput": updated}}
    if warn:
        out["hookSpecificOutput"]["additionalContext"] = warn
        out["systemMessage"] = warn
    print(json.dumps(out, ensure_ascii=False))


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
        # ⭐ FOR THE PEER TEST (cmd_guards.peer_sessions): resolve another session's start cwd
        # to a repository root with THIS module's rule, without cmd_guards importing it.
        "repo_root": repo_root,
        "session_cwd": lambda other: session_cwd(sdir, other),
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


# ⛔ A BEST-EFFORT SNAPSHOT, TAKEN 2026-08-31, OF THE BUILT-IN AGENT TYPES THAT DO NOT
# PRODUCE FILES. ⚠ IT WILL ROT, WHICH IS WHY IT IS ONLY EVER USED TO WARN. Agent types are
# user- and plugin-defined (`.claude/agents/*.md` frontmatter, SDK `agents`), so no table
# compiled in here can stay correct. A type that is neither in this set nor defined under
# `.claude/agents/` is UNKNOWN and this guard says nothing at all about it - silence is the
# right answer for an unknown type, and a guess is not. The PostToolUse half covers it
# anyway, and covers it better.
#
# ⛔ NAMES, NOT A RULE DERIVED FROM TOOL LISTS, and that is the load-bearing choice here.
# `Explore` is declared as "all tools except Agent, Artifact, ExitPlanMode, Edit, Write,
# NotebookEdit" - which leaves it holding **Bash**. A tool-list rule would therefore call
# Explore able to write, and would have missed the exact incident this guard exists for:
# measured 2026-08-31, an `Explore` round-2 reviewer said in its first line that it could
# not create its report, returned the whole review as its final message, and its
# verification table and five findings were permanently lost. The type is read-only by
# INSTRUCTION, and an instruction is not visible in a tool list.
# ⚠ `codex:codex-rescue` holds only `Bash` and is deliberately ABSENT from this set: it
# writes files through the shell, so flagging it would be a false alarm.
READ_ONLY_AGENT_TYPES = frozenset((
    "explore", "plan", "claude-code-guide", "statusline-setup",
    "feature-dev:code-architect", "feature-dev:code-explorer", "feature-dev:code-reviewer",
))

# ⭐ WHAT COUNTS AS BEING ABLE TO PRODUCE A FILE, for a type defined under `.claude/agents/`.
# ⚠ `Edit` IS NOT IN HERE. Edit changes a file that already exists; it cannot bring one into
# being, and "create <path> as your FIRST action" is exactly the instruction it cannot obey.
# That is why `statusline-setup` (Read, Edit) is listed above as read-only.
MAKES_FILES = ("write", "notebookedit", "bash", "*")

# Words that turn a path in a prompt into a path the agent was told to CREATE.
#
# ⛔ WHOLE WORDS, NOT STEMS. `creat`/`writ`/`append` as bare stems also match inside
# `creative`, `rewritten` and `appendix`, and the path that then gets picked up is whatever
# `.md` file the sentence happened to mention - reported later as the agent's lost report.
# ⚠ `written` IS here and `rewritten` is not, which a stem cannot express.
_MAKE_VERB = re.compile(
    r"\b(?:creates?|creating|writes?|writing|written|appends?|appending"
    r"|saves?|saving|produces?|producing)\b|建立|寫入|寫到|寫成|產生", re.I)

# ⛔ HOW FAR PAST THE VERB A PATH STILL COUNTS AS THE THING BEING CREATED, in characters.
# ⚠ THE WINDOW CROSSES ONE LINE BREAK, AND THAT IS THE WHOLE POINT. This used to scan line
# by line, and measured 2026-08-31 against this repository's own 18 work orders that cost it
# almost everything: the incident that motivated the guard writes `**Your FIRST action:**
# create` on one line and the path on the NEXT, so the guard was silent on its own example.
# Two of eleven work orders demanding a report were seen.
VERB_WINDOW_CHARS = 200

# ⛔ ...AND THE WINDOW STOPS AT THE END OF THE SENTENCE, which is what keeps the reach above
# from becoming a false-alarm machine. Measured on this repository's own fixture: "Create
# <report> as your FIRST action, then append every finding." followed by "Read <plan> for the
# plan." - without this cut the window ran on into the next instruction and named the PLAN as
# a file the agent had been told to create. ⚠ A `.md` inside a path is NOT a sentence end,
# because the period there is not followed by whitespace.
_SENTENCE_END = re.compile(r"[.。！!?？]\s")
# The tail of the text just before a `.md` candidate, when that candidate is a shell
# redirect's target: `> x.md`, `>> x.md`, `| tee x.md`, with one optional quote or backtick.
# ⛔ `tee` is MANDATORY after the pipe, and `>` must not be the head of a `->` arrow. The first
# draft made `tee` optional, so a bare `|` matched - which is the text before a path in a
# MARKDOWN TABLE CELL, and the review measured a real deliverables row in this repository's own
# work orders (`| … | \`adr-review-01-adversarial.md\` |`) dropped. `cat a | b.md` runs b.md;
# no command writes the file after a bare pipe, so the alternative bought nothing.
_AFTER_REDIRECT = re.compile(r"(?:(?<!-)>>?|\|\s*tee(?:\s+-a)?)\s*[`'\"]?$")


def _in_shell_example(window, start, end):
    """Is the `.md` at window[start:end] inside an inline code span that carries a shell
    operator (`>`, `|`)? Then it is a command's operand - `cat new.md | tee board.md` reads
    one file and writes another - not a report the prompt asked the agent to produce.
    ⚠ Only spans with an operator: `Create `agent-01.md`` has none and stays a demand."""
    open_tick = window.rfind("`", 0, start)
    if open_tick < 0 or "\n" in window[open_tick:start]:
        return False
    close_tick = window.find("`", end)
    if close_tick < 0:
        return False
    span = window[open_tick + 1:close_tick]
    return (">" in span) or ("|" in span)


def _verb_window(text, start):
    """The span after a creation verb in which a path still belongs to that verb.

    ⛔ TWO LIMITS, AND THE FIRST ONE WINS - line count and sentence, each computed on its
    own. Folding them into one alternation is how this was wrong on its first attempt: a
    single pattern `[.?!]\\s|\\n[^\\n]*\\n` matched at offset ZERO whenever the verb ended
    its line, cutting the window to one character and hiding exactly the incident shape the
    window exists to catch. Measured against the incident's own work order.
    """
    window = text[start:start + VERB_WINDOW_CHARS]
    # The rest of the verb's line, plus ONE following line - no further.
    nl = window.find("\n")
    cut = len(window)
    if nl >= 0:
        nl2 = window.find("\n", nl + 1)
        if nl2 >= 0:
            cut = nl2
    end = _SENTENCE_END.search(window)
    if end:
        cut = min(cut, end.start() + 1)       # keep the `.md` that ends the sentence
    return window[:cut]

# A `.md` path, with a left boundary so `MyMemory/tasks/x.md` is not read as a task-root
# path. A leading drive letter or `/` is captured, so an absolute path stays absolute.
# ⚠ THE STEM MUST END IN A REAL CHARACTER. With `[...]*\.md` the stem may be EMPTY, so a
# bare `.md` written in prose ("name it `.md`") matched and produced `<task folder>\.md` -
# a path that can never exist, reported for ever as a lost report. Measured against this
# repository's own work orders.
_MD_PATH = re.compile(r"(?<![A-Za-z0-9._/-])((?:[A-Za-z]:)?[A-Za-z0-9._/-]*[A-Za-z0-9_-]\.md)\b")


def _project_agent_tools(root, name):
    """The `tools:` value from `<root>/.claude/agents/<name>.md`, lower-cased, or None.

    ⭐ A PROJECT DEFINITION BEATS THE SNAPSHOT ABOVE, because it is the live truth for that
    name in that repository and the snapshot is a guess from another day.
    """
    if not name or not re.match(r"^[A-Za-z0-9._-]+$", name):
        return None                    # a plugin-qualified name is not a project file
    path = os.path.join(root, ".claude", "agents", name + ".md")
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(4096)
    except OSError:
        return None
    m = re.search(r"^tools:[ \t]*(.*)$", head, re.M)
    if not m:
        return None
    inline = m.group(1).strip()
    if inline and not inline.startswith("-"):
        return inline.lower()          # `tools: Read, Write`
    # ⛔ A YAML BLOCK LIST IS THE OTHER LEGAL SPELLING, and reading it wrong is worse than
    # not reading it at all. `tools:` followed by indented `- Write` lines used to leave the
    # old pattern's `\s*(.+)` skipping the newline and capturing only `- Read` - so an agent
    # holding Write was reported as unable to write, which is a FALSE WARNING about a
    # perfectly good dispatch. Silence would have been acceptable; a wrong answer is not.
    items = []
    for line in head[m.end():].splitlines():
        if not line.strip():
            continue
        hit = re.match(r"^\s+-\s*(.+?)\s*$", line)
        if not hit:
            break                      # the list ended; anything after it is another key
        items.append(hit.group(1))
    # ⚠ NO ITEMS -> None, NOT an empty string. An empty string is a tool list containing
    # nothing, which reads as "cannot write" and warns; but a bare `tools:` with nothing
    # under it declares nothing, and the harness's own reading of that is inheritance.
    # Unknown, so silent.
    return ", ".join(items).lower() if items else None


def agent_can_make_files(root, subagent_type):
    """True / False / None. ⛔ None means UNKNOWN and must stay silent, not be read as False.

    ⚠ Three outcomes rather than a boolean on purpose. A boolean forces an unknown type into
    one of the two answers, and both are wrong: False invents a warning about a type nobody
    here has ever seen, True quietly promises a capability nobody checked.
    """
    if not isinstance(subagent_type, str) or not subagent_type.strip():
        return None                    # omitted -> the harness default; not this guard's call
    name = subagent_type.strip()
    tools = _project_agent_tools(root, name)
    if tools is not None:
        return any(t in tools for t in MAKES_FILES)
    if name.lower() in READ_ONLY_AGENT_TYPES:
        return False
    return None


# ⛔ BARE FILENAMES THIS REPOSITORY TALKS ABOUT IN PROSE, and therefore never a per-sub-task
# report. Measured 2026-09-01, on this guard's own dispatch: a review prompt containing the
# sentence "write a `HANDOFF.md` into the owner's repository, unasked" - prose ABOUT creating
# a file, not an instruction to create one - produced a warning on the owner's screen that
# the sub-agent had lost its report. ⚠ A false alarm costs trust, which is the whole budget
# this guard spends.
#
# ⭐ IT APPLIES ONLY TO THE BARE-FILENAME BRANCH. `Create Memory/tasks/x/HANDOFF.md` names a
# path and is a real instruction; a bare `HANDOFF.md` in a sentence has nothing to
# disambiguate it. ⚠ And dropping the bare branch altogether was measured and rejected: over
# this repository's own work orders it finds five genuine reports (`agent-01-implement.md`
# and friends) against this one false positive.
_NOT_A_REPORT = frozenset((
    "handoff.md", "protocol.md", "readme.md", "changelog.md", "claude.md", "agents.md",
))


def demanded_files(root, cfg, prompt_text, folder=None):
    """Paths this prompt tells its agent to CREATE. Returns (paths, verb_count).

    ⭐ CONSERVATIVE ON PURPOSE, and the asymmetry is the design: a path this misses costs
    nothing - the dispatch proceeds exactly as it does today - while a path it invents
    produces a warning about work that was never asked for, and a guard that cries wolf is
    a guard people switch off.

    ⛔ CONSERVATIVE IS NOT THE SAME AS BLIND, and the first version confused the two. It
    scanned line by line and so missed the shape of its own motivating incident - verb on
    one line, path on the next - along with a bare `agent-01-x.md` filename and every other
    real spelling in this repository except two. ⇒ The verb now carries forward
    VERB_WINDOW_CHARS, across lines, and a bare filename resolves against the dispatch's own
    task folder when one is known.

    ⚠ AN ABSOLUTE PATH IS USED AS WRITTEN, never re-rooted. A prompt naming another
    checkout's `Memory/tasks/...` was previously joined onto THIS repository's root and then
    reported missing from a folder nobody had mentioned.

    ⚠ A path containing `..` is skipped: this function cannot honestly claim such a path is
    inside the task root, and a guard that reports on a file outside its own scope is one
    nobody trusts.

    ⭐ `verb_count` is returned so the caller can log the difference between "this prompt
    demanded nothing" and "this prompt demanded something and no path was recognised". Those
    two are the same silence and must not be the same log line.
    """
    tr = str(cfg["task_root"]).replace("\\", "/").strip("/")
    text = str(prompt_text).replace("\\", "/")
    out, verbs = [], 0
    for verb in _MAKE_VERB.finditer(text):
        verbs += 1
        window = _verb_window(text, verb.end())
        for hit in _MD_PATH.finditer(window):
            cand = hit.group(1)
            if ".." in cand.split("/"):
                continue
            # ⛔ A PATH RIGHT AFTER A SHELL REDIRECT IS AN EXAMPLE, NOT A DEMAND. Measured
            # 2026-09-19: a review prompt said "write three small files … (vi) `echo x >>
            # board.md`" and the gate reported `board.md` never created when the agent
            # returned - the real report existed. The `.md` after `>`, `>>` or `|` (with an
            # optional quote or backtick between) is what a command WRITES, not what the
            # prompt asked the agent to produce. Measured against this repository's 33 work
            # orders before shipping: no genuine report starts that way.
            if _AFTER_REDIRECT.search(window[:hit.start()]) or \
                    _in_shell_example(window, hit.start(), hit.end()):
                continue
            at = ("/" + cand).find("/" + tr + "/")
            if at >= 0:
                if re.match(r"^([A-Za-z]:)?/", cand):
                    p = cand               # a real absolute path: used as written
                else:
                    # ⚠ FROM THE TASK ROOT ONWARD, not from the start of what matched. Work
                    # orders elide a long prefix as `...\Memory\tasks\...`, and joining that
                    # onto the repository root produced `<root>\...\Memory\...` - a path
                    # that never exists, so a report that WAS written read as missing.
                    p = os.path.join(root, ("/" + cand)[at + 1:])
            elif folder and "/" not in cand and cand.lower() not in _NOT_A_REPORT:
                # A bare filename - real, and previously invisible: "Create
                # `agent-01-implement.md` in this same folder as your FIRST action".
                p = os.path.join(root, tr, folder, cand)
            else:
                continue
            p = os.path.normpath(p.replace("/", os.sep))
            if p not in out:
                out.append(p)
    return out[:8], verbs              # bounded: this gets stashed in a slot file


# ⛔ THE SPAWN FLOOR IS PER SESSION, and until 0.60 it was not - which on its own kept
# arming serialised however many records existed. One session arming set a machine-wide
# 300-second floor, so a second session's arm inside that window returned False and got NO
# resume at all. ⇒ `state/<session>.auto-arm`, through state_path(). ADR 20260917-132015, D3.
# ⚠ It BELONGS in state/, unlike the record: losing it only permits an arm, so prune_state's
# age sweep is harmless to it.
ARM_MARK = "auto-arm"                  # suffix; state_path() builds the rest
HANDOFF = "HANDOFF.md"
# ⛔ Below this it is a placeholder, not a work order. ⚠ ONE definition, here rather than in
# resume.py, because resume.py imports this module and not the other way round - and two
# copies of a threshold are two chances for the gate to refuse what the resume would accept.
MIN_HANDOFF_CHARS = 200


def handoff_state(root, cfg, folder, started):
    """(state, path) for a task folder's handoff: "ok" / "missing" / "thin" / "stale".

    ⭐ "STALE" IS A STATE OF ITS OWN, and it is the one a size check cannot see. A handoff
    written three windows ago passes existence and length while describing work that no
    longer exists - and a resume then acts on instructions that are wrong, which is worse
    than the reconstruction prompt: that one at least KNOWS it is rebuilding. ⇒ Newer than
    this session's start stamp, or it does not count.

    ⚠ The remedies differ, which is why the states are named rather than collapsed into a
    boolean: missing means write one, stale means refresh the one that is there.
    """
    if not folder:
        return "unknown", None
    path = os.path.join(root, cfg["task_root"].replace("/", os.sep), folder, HANDOFF)
    try:
        st = os.stat(path)
    except OSError:
        return "missing", path
    if st.st_size < MIN_HANDOFF_CHARS:
        return "thin", path
    if started and st.st_mtime < started:
        return "stale", path
    return "ok", path


def handoff_refusal(root, sdir, cfg, folder, started, log_to=None):
    """Refuse this dispatch because the window is closing and nothing would survive it.

    ⛔ WHY THIS IS A GATE AND NOT ADVICE, which is this plugin's whole argument applied to
    its own worst gap. "Write a handoff before you run out" was already in the protocol, and
    an instruction an agent only meets as advice is one it can weigh against the task in
    front of it. The cost of it losing that weighing is a whole window: the run is cut off,
    the resume wakes, and there is nothing on disk saying what was being done.

    ⚠ IT ONLY BITES PAST THE SOFT THRESHOLD - when an interruption is genuinely near - and it
    gates DISPATCH only. The agent's own work is never blocked, and writing the file is one
    tool call it can always make.

    ⭐ THE VERDICT DECIDES "PAST SOFT", never a raw percentage. That is the rule everywhere
    else in this plugin: the verdict already folds in the seven-day window, the near-reset
    softening and the burn projection, and a second comparison here would eventually
    disagree with the one the brake acts on.
    """
    if not cfg.get("require_handoff_past_soft", DEFAULTS["require_handoff_past_soft"]):
        return None
    v = usage.verdict(sdir, usage.config(sdir))
    # ⭐ THE NET ZONE COUNTS AS PAST-SOFT. A relaxed STOP reads GO, but a new dispatch there
    # still needs a fresh handoff - the window can hit the cap mid-dispatch, and the net's
    # promise is that the handoff is current. `relaxed_stop` catches it whatever the word.
    # ⭐ AND THE RELAXED-PACE BAND (0.68, owner 2026-10-01 「要加」): the handoff and the alarm go
    # on first there too, so a dispatch waits for a current HANDOFF.md. ADR 20261001-085000 D4.
    if (v["verdict"] not in ("PACE", "STOP") and not v.get("relaxed_stop")
            and not v.get("relaxed_pace")):
        return None
    state, path = handoff_state(root, cfg, folder, started)
    if state in ("ok", "unknown"):
        # ⚠ "unknown" means the prompt named no task folder, so there is nowhere to look.
        # The plan check has already refused that case; refusing again here would report the
        # wrong reason for it.
        if state == "unknown" and log_to:
            log(log_to, "HANDOFF-CHECK-SKIPPED (no task folder in the prompt)")
        return None
    why = {"missing": "there is no %s in that task folder" % HANDOFF,
           "thin": "%s is under %d characters, which is a placeholder rather than a work "
                   "order" % (HANDOFF, MIN_HANDOFF_CHARS),
           "stale": "%s is older than this session, so it describes work that has already "
                    "moved on" % HANDOFF}[state]
    if log_to:
        log(log_to, "DENY(handoff-%s) %s" % (state, path))
    return ("dispatch gate: usage is at %s and %s. ⛔ Write it BEFORE dispatching again:\n"
            "  %s\n"
            "It must say what is done, what is in flight, what is next, and which files to "
            "read - enough that a fresh session can act without your context. ⚠ THIS IS THE "
            "POINT OF THE SOFT THRESHOLD: a hard cut-off gives you no turn to write it in, "
            "and then the next window is spent rediscovering what this one was doing. "
            "⭐ Set `require_handoff_past_soft: false` to dispatch without one - the resume "
            "then wakes with a reconstruction prompt instead, which costs tokens."
            % (relax_band_label(v), why, path))


# ⭐ THE BANNER THAT SAYS A HUMAN DID NOT WRITE THIS. Measured 2026-09-01: a 390-byte stub
# scores `handoff_state() == "ok"` and `check_handoff() == None`, so NOTHING MECHANICAL
# distinguishes a generated handoff from a real one. This line is the only thing that does,
# and a later session that trusts a stub as a real handoff acts on work nobody described.
GENERATED_BANNER = "GENERATED BY THE GATE - no agent wrote this"


def arm_trigger(v):
    """Should a resume be armed at this verdict? ⭐ THE ONE PLACE THAT DECIDES.

    ⛔ EXTRACTED SO IT CAN BE CHANGED IN ONE PLACE. The open question after this decision is
    whether arming should happen for every session that does substantial work rather than
    only when the window is closing - see the NO-DATA problem, where the guarantee is voided
    precisely because there is no verdict to act on. That change is one edit here and none
    anywhere else, which is the point of the function existing at all.

    ⭐ AND IT ARMS IN THE NET ZONE. A relaxed STOP reads GO, but the whole point of relaxing it
    was to keep working INTO a window that can still hit the cap - so the resume must be armed
    exactly then, or the safety the relaxation promised does not exist. `relaxed_stop` is true
    whenever a STOP was overridden in either window, independent of the display word.

    ⭐ AND IN THE RELAXED-PACE BAND (0.67). Measured 2026-10-01: a session wrote its HANDOFF at 86%
    with 23 minutes to the reset, the band read as plain GO, nothing armed - and the window then
    jumped to 95%. Owner: 「近重置放寬沒問題，但handoff跟鬧鐘還是要先上」; an alarm that rings after
    the session survived the reset is simply turned off. ADR 20261001-065500 D3.
    """
    return (v.get("verdict") in ("PACE", "STOP") or bool(v.get("relaxed_stop"))
            or bool(v.get("relaxed_pace")))


def generated_handoff(sdir, cfg, session_id, cwd, log_tail=""):
    """Write a machine-made handoff into the STATE directory and return its folder.

    ⛔ NOT INTO THE OWNER'S REPOSITORY, and that was reviewed twice to get here. The first
    design created a task folder under `task_root`; `repo_root()` falls back to the payload's
    cwd in a project with no `CLAUDE.md`, `AGENTS.md` or `.git`, and the Bash tool's own `cd`
    moves that - measured, one session produced THREE roots, one of them inside an existing
    task folder. ⇒ N files in N directories, per session, never pruned, in a tree under
    version control. Here it is one directory the plugin already owns.

    ⭐ `find_handoff()` and `handoff_state()` both accept an ABSOLUTE task, because
    `os.path.join` discards everything before one - so nothing in the resume path needed
    changing to point at this.

    ⚠ IT IS A FLOOR, NEVER A CEILING. A real handoff written by the agent into its own task
    folder is better in every way; this exists so that a session which never wrote one still
    comes back. The banner says which kind it is.

    Returns the folder, or None when it could not be written - in which case arming simply
    does not happen and the log says so.
    """
    if not session_id:
        return None
    folder = os.path.join(sdir, "handoffs", str(session_id))
    body = [
        "# HANDOFF - %s" % GENERATED_BANNER,
        "",
        "⚠ **The previous session hit the usage limit without writing a handoff of its own.**",
        "This file was assembled by the dispatch gate from what it could see. It is a",
        "STARTING POINT, not a plan: nothing here describes intent, only circumstance.",
        "",
        "## Where the work was",
        "",
        "- Working directory: `%s`" % (cwd or "not recorded"),
        "- Session id: `%s`" % session_id,
        "- Written: %s" % time.strftime("%Y-%m-%d %H:%M:%S"),
        "",
        "## Next step",
        "",
        "1. Change to the working directory above.",
        "2. Read `git status` and `git log --oneline -10` there to see what was in flight.",
        "3. Look for a task folder under `%s` newer than this file; if one exists, its"
        % cfg.get("task_root", TASK_ROOT),
        "   `progress.md` and reports say what was already done.",
        "4. ⛔ Do not redo finished work. Re-running it is the waste this file exists to avoid.",
        "",
        "## The gate's last lines before the window closed",
        "",
        "```",
        (log_tail or "(no log lines were available)").rstrip(),
        "```",
        "",
    ]
    try:
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, HANDOFF), "w", encoding="utf-8") as f:
            f.write("\n".join(body))
    except OSError:
        return None
    return folder


def gate_log_tail(sdir, lines=12):
    """The last few lines of the state-directory copy of the gate log, or ""."""
    try:
        with open(os.path.join(sdir, "dispatch_gate.log"), encoding="utf-8") as f:
            return "".join(f.readlines()[-lines:])
    except OSError:
        return ""


def wind_down_note(payload, root, sdir, cfg, now=None):
    """The PACE/STOP wind-down, at most once per level per agent. Text, or None.

    ⛔ THIS IS THE HALF THAT WAS UNREACHABLE. The plugin had two action points - a dispatch
    and a user prompt - and a session that neither dispatches nor is typed at crosses
    neither. Measured 2026-08-31: 183 Read, 172 Write, 36 Bash, ZERO Agent calls, no user
    prompt in the burn window, a five-hour window taken from 0% to 100%, and not one
    `USAGE(` line in any gate log on the machine. The gate received every one of those tool
    calls and returned early.

    ⭐ IT USES verdict(cheap=True), NOT the full verdict(). Measured: 28.99 ms against 0.471 ms,
    62x, same word. On a path that runs for every tool call, the full burn projection is not
    affordable - and the word does not depend on it. ⚠ cheap STILL carries `relaxed_stop` (the
    relaxation is in the shared path), so the net zone is visible here without the full cost.

    ⚠ ONE MARKER PER AGENT, not per session. A sub-agent's hook payload carries the PARENT's
    `session_id` - measured twice - and so does its `transcript_path`, so neither
    distinguishes them. The harness supplies `agent_id` for exactly this and says so:
    "Present only when the hook fires from within a subagent." ⇒ Without it the first
    sub-agent past a level would silence the supervisor's own warning.

    ⚠ AND ITS OWN MARKER, separate from on_user_prompt()'s. That function's behaviour is
    unchanged by this whole decision, whatever `agent_id` turns out to hold.
    """
    if not cfg.get("guard_wind_down", DEFAULTS["guard_wind_down"]):
        return None
    sid = payload.get("session_id")
    if session_start(sdir, sid) is None:
        return None            # an unstamped session is advisory for everything else too
    try:
        # ⚠ cheap=True keeps the per-tool-call cost at ~0.5 ms (it skips the burn projection),
        # but STILL carries `relaxed_stop` - that is computed in the shared path, so the net
        # zone is visible here without paying for the full verdict. See verdict()'s cheap path.
        v = usage.verdict(sdir, usage.config(sdir), cheap=True)
    except Exception as exc:
        # ⚠ FAIL OPEN AND SAY SO. A wind-down that raises must not take a tool call with it.
        log(root, "WIND-DOWN-FAILED %r" % (exc,))
        return None
    word = v["verdict"]
    relaxed_stop = v.get("relaxed_stop")
    # ⭐ THE RELAXED-PACE BAND (0.67) - only when nothing stricter speaks: STOP, then NET, then PACE.
    relaxed_pace = bool(v.get("relaxed_pace")) and word == "GO" and not relaxed_stop
    now = now if now is not None else time.time()
    # ⭐ WALL-HIT, checked on the path every session reaches (ADR 20260916's reconsideration
    # clause, never implemented until 0.66). Cheap: a glob, plus one history read per window.
    try:
        check_wall_hit(root, sdir, now)
    except Exception as exc:
        log(root, "WALL-HIT-CHECK-FAILED %r" % (exc,))
    # ⭐ THE NET ZONE. A STOP was relaxed near the reset, so the word is GO and the brake does
    # not fire - but the window can still hit the cap. ⚠ A BINDING STOP WINS: if the combined
    # word is still STOP (the OTHER window is a far STOP), that is the message, not the net.
    arm_state, arm_rec, reset = None, {}, None
    # ⚠ At relaxed PACE a sub-agent's tool call does nothing here: the arm skips it anyway (its
    # payload carries the PARENT's session id) and the note is about the session's own resume.
    if relaxed_pace and payload.get("agent_id"):
        return None
    if word == "STOP" or relaxed_stop or relaxed_pace:
        reset = window_reset(sdir, v)
        # ⭐ 0.68: the relaxed-PACE band too, so WALL-HIT covers it (owner 「要加」, ADR
        # 20261001-085000 D6); the marker keeps its `net-seen` name for upgrade compatibility.
        if (relaxed_stop or relaxed_pace) and reset:
            note_relaxed(sdir, reset, "7d" if v.get("relaxed_driver") == "7d" else "5h")
            # ⭐ THIS session worked in the net zone of this window - only such a session hears the
            # WALL-HIT afterwards (wall_hit_note); an idle one, a later one, a headless resume do not.
            seen = state_path(sdir, sid, "net-seen-%d" % reset)
            if not os.path.exists(seen):
                try:
                    with open(seen, "w", encoding="utf-8") as f:
                        f.write(str(now))
                except OSError:
                    pass
        # ⛔ ARM HERE, BECAUSE AN UNATTENDED SESSION REACHES NOTHING ELSE. Until 0.66 a resume was
        # armed on a dispatch, a prompt at PACE/STOP, or the end of a turn - and a session told
        # "keep working" in the net zone does none of those; when the cap cut it, the cut fired
        # no Stop hook either. Measured 2026-09-29 14:07: 3 of 4 net-zone sessions cut, only the
        # attended one armed. ADR 20260916 REVISION site 3 already said the net arms; this is the
        # path that was never wired. ADR 20260929-152000 item 2. Once per session per window.
        arm_state, arm_rec = own_resume(sdir, sid, now)
        # ⛔ Armed for ANOTHER reset is not armed for this one (0.67 review B, B1) - re-aim it.
        # ⚠ NOT AT A COMBINED PACE (0.67.1): this block sees a PACE only through a relaxed STOP in the
        # other window, and there reset_time() names the far PACE's window (the pended N-7 corner) -
        # re-aiming would move a 5h net-zone alarm to a 7d reset days away. Before 0.67 it was kept.
        if arm_state == "armed" and word != "PACE" and aims_elsewhere(sdir, v, arm_rec):
            # ⚠ ...unless that re-aim is already in flight: a spawn mark NEWER than the old record
            # and under 2 min old means the next tool call would otherwise say "NO resume" while
            # the new record is ~1 s from landing (fix review F1). An old mark is the old arm's.
            armed_at = arm_rec.get("armed_at")
            try:
                mark_at = os.path.getmtime(state_path(sdir, sid, ARM_MARK))
            except OSError:
                mark_at = None
            in_flight = (mark_at is not None and now - mark_at < 120
                         and isinstance(armed_at, (int, float)) and mark_at > armed_at + 1)
            arm_state, arm_rec = ("arming" if in_flight else "none"), {}
        # ⚠ never from a sub-agent's tool call: its payload carries the PARENT's session id
        if (arm_state == "none" and not payload.get("agent_id")
                and tool_path_arm(root, sdir, cfg, sid, v, reset,
                                  "rlx-" if relaxed_pace else "")):
            arm_state = "arming"
    if word == "STOP":
        level_key = "STOP-" + ("none" if arm_state == "none" else "armed")
    elif relaxed_stop:
        # ⭐ ONCE PER WINDOW, NOT EVERY 10 MINUTES (0.66). The 10-minute re-fire asked for a
        # HANDOFF rewrite each time; all four sessions interviewed on 2026-09-29 called that
        # noise. The note returns only when the session's resume state changes (none -> armed)
        # and once more inside the last 15 minutes. ADR 20260929-152000 item 6.
        late = reset is not None and (reset - now) < 15 * 60
        level_key = "NET-%s-%s%s" % (reset or "?", "none" if arm_state == "none" else "armed",
                                     "-late" if late else "")
    elif word == "PACE":
        level_key = "PACE"
    elif relaxed_pace:
        return relaxed_pace_note(root, sdir, cfg, sid, v, reset, now, arm_state, arm_rec)
    else:
        return None
    agent = payload.get("agent_id")
    mark = state_path(sdir, sid, "warned-tool" + ("-" + str(agent) if agent else ""))
    try:
        with open(mark, encoding="utf-8") as f:
            if f.read().strip() == level_key:
                return None                     # already said, at this level, to this agent
    except OSError:
        pass
    try:
        os.makedirs(os.path.dirname(mark), exist_ok=True)
        with open(mark, "w", encoding="utf-8") as f:
            f.write(level_key)
    except OSError:
        pass
    # ⚠ The logged level stays the bare word (STOP / NET / PACE): people and checks grep for
    # `USAGE(STOP) tool-path`. The resume state and the window ride along after it.
    log(root, "USAGE(%s) tool-path%s%s" % (
        level_key.split("-")[0], " agent=" + str(agent) if agent else "",
        (" resume=%s reset=%s" % (arm_state, reset)) if arm_state else ""))
    if level_key == "PACE":
        return ("dispatch-guard: usage is at PACE. Finish the step you are on and do not "
                "start anything new or expand scope. There is no need to stop working.")
    # ⛔ THE RESUME SENTENCE IS THIS SESSION'S REAL STATE. It used to say "a resume is armed" to
    # every session; on 2026-09-29 three of the four sessions told so had none. item 3.
    armed_line = resume_state_line(arm_state, arm_rec, now,
                                   cfg.get("auto_arm_resume", DEFAULTS["auto_arm_resume"]))
    # ⭐ AND ASK FOR THE WAKE THAT WAKES THIS SESSION (route A, 0.68): the OS alarm only starts a
    # new headless run. Appended - the resume sentence above is pinned as it is.
    if arm_state in ("armed", "arming"):
        armed_line += route_a_line(sdir, v, arm_rec, reset)
    if level_key.startswith("NET"):
        return net_facts_line(v, reset, now, armed_line, arm_state, arm_rec)
    return ("dispatch-guard: usage is at STOP - this window is nearly spent and the next "
            "tool call may be the last one that succeeds. \u26d4 Write a stand-alone HANDOFF.md "
            "into your task folder NOW, then end the turn. %s Nothing is being refused: writing "
            "and running commands still work, because those are how you get out." % armed_line)


def relaxed_pace_note(root, sdir, cfg, sid, v, reset, now, arm_state, arm_rec):
    """The relaxed-PACE note: once per window and resume state, on its OWN marker. Text or None.

    ⛔ NOT A WIND-DOWN, AND WORDED SO IT CANNOT READ AS ONE - no glyph, no capitals. On 2026-09-17
    sessions stopped early because a hook's capitals outranked the skill prose, and in 0.63.2 a
    glyph on a GO line did the same. The owner's ruling is "keep working, but the HANDOFF and the
    alarm go on first" (2026-10-01), so the note asks for exactly that and nothing more.

    ⚠ ITS OWN MARKER (`warned-rlx`), not `warned-tool`: that one holds a single key, so a window
    flickering between PACE and relaxed PACE would re-print both notes on every flip. The key
    carries the reset and the resume state, so it speaks again when the resume gets armed - that
    line carries the cancel command. ADR 20261001-065500 D4.
    """
    level_key = "RLX-%s-%s" % (reset or "?", "none" if arm_state == "none" else "armed")
    mark = state_path(sdir, sid, "warned-rlx")
    try:
        with open(mark, encoding="utf-8") as f:
            if f.read().strip() == level_key:
                return None
    except OSError:
        pass
    try:
        os.makedirs(os.path.dirname(mark), exist_ok=True)
        with open(mark, "w", encoding="utf-8") as f:
            f.write(level_key)
    except OSError:
        pass
    log(root, "USAGE(RLX) tool-path resume=%s reset=%s" % (arm_state, reset))
    seven = v.get("relaxed_driver") == "7d"
    pct = v.get("pct_7d") if seven else v.get("pct")
    clock = time.strftime("%H:%M", time.localtime(reset)) if reset else v.get(
        "resets_clock", "the reset")
    left = ("%d min left" % max(0, round((reset - now) / 60.0))) if reset else "soon"
    # ⚠ THE CANCEL COMMAND RIDES ON "ARMING" TOO. "arming" and "armed" share the key, so the note
    # printed while the arm is in flight is usually the only one this window - and the session
    # that finishes BEFORE the reset is the one that needs it (ADR T1: nothing alive after the
    # reset, so do_run's stand-down cannot fire).
    # ⚠ "ends", not "finish": the owner prefers carrying on over finishing early to stop (review B NB5)
    cancel = ("If this session fires a hook after the reset it stands itself down; if this session "
              "ends before the reset and you do not want it, cancel it with `%s --cancel --session %s` "
              "(this session's alarm only)." % (runnable("resume.py"), sid))
    if arm_state == "armed":
        at = arm_rec["at"]
        fmt = "%H:%M" if time.localtime(at)[:3] == time.localtime(now)[:3] else "%m-%d %H:%M"
        state = ("Your resume is armed for %s. %s%s" % (time.strftime(fmt, time.localtime(at)),
                                                         cancel, route_a_line(sdir, v, arm_rec, reset)))
    elif arm_state == "arming":
        state = ("Your resume is being armed from your HANDOFF.md. %s%s"
                 % (cancel, route_a_line(sdir, v, arm_rec, reset)))
    elif not cfg.get("auto_arm_resume", DEFAULTS["auto_arm_resume"]):
        state = ("You have no resume, and auto_arm_resume is off: after writing HANDOFF.md, run "
                 "`%s --arm --task <folder>`." % runnable("resume.py"))
    else:
        state = ("You have no resume yet; the gate arms one as soon as it sees a HANDOFF.md "
                 "written in your task folder.")
    return ("dispatch-guard: %s at %s%%, resets %s (%s) - a PACE is relaxed because the rest of "
            "the budget should last. This is not a wind-down: keep working. Keep a stand-alone "
            "HANDOFF.md current in your task folder so the gate can arm your resume first - a "
            "dispatch needs it too (0.68). %s"
            % ("7d" if seven else "5h", round(pct) if isinstance(pct, (int, float)) else "?",
               clock, left, state))


def own_resume(sdir, session_id, now=None):
    """(state, record) of THIS session's resume: "armed" / "arming" / "none". Never raises.

    "armed" = its record exists and fires in the future. "arming" = no record yet but the gate
    spawned `resume.py --arm` for it under two minutes ago (the record lands ~1 s later, or is
    taken back down by the launch probe - then this reads "none" again).
    """
    now = now if now is not None else time.time()
    rec = {}
    try:
        sys.path.insert(0, HERE)
        import resume as _resume
        rec = usage.read_json(_resume.record_path(sdir, session_id), {}) or {}
    except Exception:
        rec = {}
    if not isinstance(rec, dict):
        rec = {}
    at = rec.get("at")
    # ⚠ a real epoch only: a bool is an int in Python, and a huge value overflows localtime()
    if (isinstance(at, (int, float)) and not isinstance(at, bool)
            and now < at < now + 30 * 86400):
        return "armed", rec
    try:
        if now - os.path.getmtime(state_path(sdir, session_id, ARM_MARK)) < 120:
            return "arming", {}
    except OSError:
        pass
    return "none", {}


def aims_elsewhere(sdir, v, rec):
    """True when THIS session's armed record is for a different reset than the window closing now.

    ⛔ AN ALARM FOR THE WRONG RESET IS NO ALARM (code review B of 0.67, B1): a 7d relaxed PACE arms
    for the 7d reset; the 5h then reaches STOP with a LATER reset; a skip on "already armed" left
    the 7d alarm, which wakes into the 5h STOP and gives up after `retry_window_min`. maybe_auto_arm
    already re-arms on a different reset - this lets the tool path and the HANDOFF-write path reach
    it. Same comparison (resume.reset_time, 1 s tolerance). Never raises; unknown -> False.
    """
    try:
        sys.path.insert(0, HERE)
        import resume as _resume
        want = _resume.reset_time(sdir, usage.config(sdir), v)[0]
    except Exception:
        return False
    got = rec.get("armed_for_reset") if isinstance(rec, dict) else None
    return (isinstance(want, (int, float)) and isinstance(got, (int, float))
            and not isinstance(got, bool) and abs(got - want) > 1)


def tool_path_arm(root, sdir, cfg, session_id, v, reset, band=""):
    """Arm THIS session's resume from its own fresh HANDOFF.md - once per window. True if started.

    \u26a0 ONE ATTEMPT PER WINDOW HERE (marker `state/<sid>.tool-arm-<reset>`), so a session with no
    handoff does not re-scan and re-log on every tool call; a HANDOFF.md written LATER is armed
    from PostToolUse (arm_on_handoff_write). A real handoff only, under the unchanged freshness
    rule - no generated handoff (ADR 20260902 decision 4). Never raises.
    \u26a0 The relaxed-PACE band has its OWN attempt (`band="rlx-"`, 0.67): sharing the marker let a
    failed attempt at relaxed PACE use up the NET zone's one attempt later in the same window.
    """
    mark = state_path(sdir, session_id, "tool-arm-%s%s" % (band, reset or "unknown"))
    if os.path.exists(mark):
        return False
    try:
        os.makedirs(os.path.dirname(mark), exist_ok=True)
        with open(mark, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except OSError:
        return False
    try:
        return bool(arm_from_handoff(root, sdir, cfg, session_id, v))
    except Exception as exc:
        log(root, "TOOL-ARM-FAILED %r" % (exc,))
        return False


def arm_on_handoff_write(root, sdir, cfg, session_id):
    """A HANDOFF.md was just written: arm it at once at STOP, in the net zone or at relaxed PACE.

    \u2b50 THE NOTE SAID "write HANDOFF.md now - the gate arms it as soon as it sees the write", and
    this is that promise. Cheap verdict; skipped when this session already has a live resume or
    an arm is in flight. Never raises.
    """
    try:
        v = usage.verdict(sdir, usage.config(sdir), cheap=True)
        # ⚠ Not at a plain PACE: there the turn's end arms (on_stop), as since 0.58.0.
        if not (v["verdict"] == "STOP" or v.get("relaxed_stop") or v.get("relaxed_pace")):
            return ""
        state, rec = own_resume(sdir, session_id)
        # ⛔ a live resume for ANOTHER reset does not count (0.67 review B, B1) - except at a combined
        # PACE, for the reason in wind_down_note (0.67.1)
        if state == "arming" or (state == "armed" and (v["verdict"] == "PACE"
                                                       or not aims_elsewhere(sdir, v, rec))):
            return ""
        # ⭐ 0.68: the ARMED line itself, so the PostToolUse that saw the write can tell the model
        # (with route A) - it used to arm in silence. ADR 20261001-085000 D2.
        return arm_from_handoff(root, sdir, cfg, session_id, v) or ""
    except Exception as exc:
        log(root, "TOOL-ARM-FAILED %r" % (exc,))
        return ""


def resume_state_line(arm_state, arm_rec, now, auto=True):
    """The one sentence about THIS session's resume. See wind_down_note().

    \u26a0 The time carries the DATE when it is not today: a record armed for the 7d reset is armed,
    but not for this window, and "armed for 14:13" would claim coverage it does not give.
    """
    if arm_state == "armed":
        at = arm_rec["at"]
        fmt = "%H:%M" if time.localtime(at)[:3] == time.localtime(now)[:3] else "%m-%d %H:%M"
        return ("Your resume is armed for %s - if the cap cuts this turn, it continues from "
                "your HANDOFF.md." % time.strftime(fmt, time.localtime(at)))
    if arm_state == "arming":
        return "Your resume is being armed from your HANDOFF.md (started just now)."
    if not auto:
        return ("\u26d4 You have NO resume, and auto_arm_resume is off: write a stand-alone "
                "HANDOFF.md in your task folder and run `resume.py --arm --task <folder>`.")
    return ("\u26d4 You have NO resume: if the cap cuts this turn, nothing continues this work. "
            "Write a stand-alone HANDOFF.md in your task folder now - the gate arms it as soon "
            "as it sees the write.")


def safe_resume_line(sdir, session_id, cfg):
    """resume_state_line() for a caller that must never raise (the dispatch refusal)."""
    try:
        now = time.time()
        state, rec = own_resume(sdir, session_id, now)
        return resume_state_line(state, rec, now,
                                 cfg.get("auto_arm_resume", DEFAULTS["auto_arm_resume"]))
    except Exception:
        return "`resume.py --status` shows whether this session has a resume."


def net_facts_line(v, reset, now, armed_line, arm_state, arm_rec):
    """The net-zone note: facts, once per window. Decides nothing (the 2026-08-29 pin)."""
    seven = v.get("relaxed_driver") == "7d"
    pct = v.get("pct_7d") if seven else v.get("pct")
    clock = time.strftime("%H:%M", time.localtime(reset)) if reset else v.get(
        "resets_clock", "the reset")
    left = ("%d min left" % max(0, round((reset - now) / 60.0))) if reset else "soon"
    line = ("dispatch-guard: %s at %s%%, resets %s (%s) - a STOP is relaxed because the rest "
            "of the budget should last (the NET zone). Keep working in short, interruptible "
            "steps; start NO new sub-agent until %s. %s"
            % ("7d" if seven else "5h", round(pct) if isinstance(pct, (int, float)) else "?",
               clock, left, clock, armed_line))
    if arm_state == "armed" and reset and (reset - now) < 15 * 60:
        try:
            age = (now - os.path.getmtime(str(arm_rec.get("handoff") or ""))) / 60.0
        except (OSError, ValueError, TypeError):
            age = None
        if age is not None and age > 10:
            line += " Refresh HANDOFF.md once now (it is %d min old)." % age
    return line


def window_reset(sdir, v):
    """Epoch of the reset of the window this verdict is about, or None. A file read, no verdict.

    The relaxed window in the net zone; the 7d when a 7d STOP binds; otherwise the 5h.
    """
    try:
        d = usage.read_json(usage.config(sdir)["token_usage_file"], {}) or {}
    except Exception:
        return None
    seven = v.get("relaxed_driver") == "7d" or (v.get("verdict") == "STOP"
                                                and v.get("driver") == "7d")
    r = (d.get("seven_day" if seven else "five_hour") or {}).get("resets_at")
    return int(r) if isinstance(r, (int, float)) else None


WALL_DIR_MARKS = ("relaxed-", "wall-checked-", "wall-hit-")   # state/<mark><reset epoch>.json


def note_relaxed(sdir, reset, window="5h"):
    """Record, once, that a relaxation was shown in the window ending at `reset`."""
    p = os.path.join(sdir, "state", "relaxed-%d.json" % reset)
    if os.path.exists(p):
        return
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"reset": reset, "window": window, "acct": usage._current_account(),
                       "at": time.time()}, f)
    except Exception:
        pass


def check_wall_hit(root, sdir, now=None):
    """After a relaxed window has reset, ask ONCE whether it reached the cap first -> WALL-HIT.

    \u26d4 AFTER THE RESET, FROM THE HISTORY - NOT "SEEN AT >= 99% BEFORE THE RESET". On 2026-09-29
    the 100% sample landed at 14:07:12 and the next hook of any session came at 14:10:15, after
    the 14:10 reset: the sessions had been cut, so nothing was there to see the number live. The
    history kept the row. \u26a0 Rows of another account are ignored (acct recorded at relaxation).
    """
    now = now if now is not None else time.time()
    for p in glob.glob(os.path.join(sdir, "state", "relaxed-*.json")):
        # ⚠ DECIDED FROM THE NAME FIRST. This runs on every tool call, and reading each JSON cost
        # ~0.27 ms per file (review, 2026-09-29) while they live 7 days - skip the checked and the
        # not-yet-reset ones without opening them.
        name = os.path.basename(p)[len("relaxed-"):-len(".json")]
        if not name.isdigit() or now < int(name):
            continue
        reset = int(name)
        done = os.path.join(sdir, "state", "wall-checked-%d.json" % reset)
        if os.path.exists(done):
            continue
        d = usage.read_json(p, {})
        d = d if isinstance(d, dict) else {}
        hit = first_cap_row(sdir, reset, d.get("acct"), d.get("window") == "7d")
        try:
            with open(done, "w", encoding="utf-8") as f:
                json.dump({"reset": reset, "hit": hit}, f)
        except OSError:
            continue
        if hit is None:
            continue
        try:
            with open(os.path.join(sdir, "state", "wall-hit-%d.json" % reset), "w",
                      encoding="utf-8") as f:
                json.dump({"reset": reset, "hit": hit}, f)
        except OSError:
            pass
        log(root, "WALL-HIT %s (%d min before the %s reset, after a relaxation)"
            % (time.strftime("%H:%M", time.localtime(hit)), round((reset - hit) / 60.0),
               time.strftime("%H:%M", time.localtime(reset))))


def first_cap_row(sdir, reset, acct, seven=False):
    """Epoch of the first history row at >= 99% in the window ending at `reset`, or None.

    The 7d window reads the `sd_pct` / `sd_resets` columns of the same rows.
    """
    pct_key, reset_key = ("sd_pct", "sd_resets") if seven else ("pct", "resets_at")
    cfg_u = usage.config(sdir)
    rows = []
    for path in sorted(glob.glob(os.path.join(usage.history_dir(sdir, cfg_u),
                                              usage.HISTORY_PREFIX + "*.jsonl")))[-2:]:
        try:
            with open(path, encoding="utf-8") as f:
                rows += [json.loads(l) for l in f if l.strip()]
        except Exception:
            continue
    first = None
    for r in rows:
        if not isinstance(r, dict):
            continue
        at, ra, pct = usage.unstamp(r.get("at")), usage.unstamp(r.get(reset_key)), r.get(pct_key)
        if at is None or ra is None or abs(ra - reset) > 1 or not isinstance(pct, (int, float)):
            continue
        if acct and r.get("acct") and r.get("acct") != acct:
            continue
        if pct >= 99 and at < reset and (first is None or at < first):
            first = at
    return first


def wall_hit_note(sdir, session_id, now=None):
    """Once per session: the window hit the cap after a relaxation (within 6 h). Never raises."""
    now = now if now is not None else time.time()
    out = []
    try:
        for p in sorted(glob.glob(os.path.join(sdir, "state", "wall-hit-*.json"))):
            d = usage.read_json(p, {}) or {}
            reset, hit = d.get("reset"), d.get("hit")
            if not (isinstance(reset, (int, float)) and isinstance(hit, (int, float))):
                continue
            if now - reset > 6 * 3600:
                continue
            # ⚠ ONLY A SESSION THAT WAS IN THE NET ZONE OF THAT WINDOW (0.66.1). Broadcasting to
            # every session that prompts within 6 h told idle, later and headless sessions about a
            # cut they could not have suffered - the same line from every window the owner opens.
            if not os.path.exists(state_path(sdir, session_id, "net-seen-%d" % int(reset))):
                continue
            seen = state_path(sdir, session_id, "wall-hit-seen-%d" % reset)
            if os.path.exists(seen):
                continue
            with open(seen, "w", encoding="utf-8") as f:
                f.write(str(now))
            out.append(" \u26d4 TELL THE USER: the usage window hit the cap at %s, %d min before "
                       "its %s reset, after the gate had relaxed a PACE or STOP near the reset; "
                       "a turn that stopped "
                       "around then was cut by the cap - check that its last step finished."
                       % (time.strftime("%H:%M", time.localtime(hit)),
                          round((reset - hit) / 60.0),
                          time.strftime("%H:%M", time.localtime(reset))))
    except Exception:
        return "".join(out)
    return "".join(out)


def emit_with(event, own_text, wind, systemMessage=None):
    """One emission carrying a branch's own text AND the wind-down, or whichever exists.

    ⛔ COMPOSED, NOT INSERTED IN FRONT. A hook prints ONE object, and the branches above
    each `return` their own - so putting the wind-down before them would have skipped
    `cmd_guards.after_command` (which records the branch `guard_commit_branch` enforces
    against) and `note_skill` (which writes the marker `require_skills` refuses dispatches
    on). Review measured that it would falsify this decision's own promise that no tool call
    which succeeds today can fail afterwards.
    """
    parts = [t for t in (own_text, wind) if t]
    if not parts:
        return None
    return context_note(event, "\n\n".join(parts), systemMessage=systemMessage)


def maybe_auto_arm(root, sdir, cfg, folder, started, session_id=None, cwd=None):
    """Arm a resume, once, when the window is closing and there IS something to resume.

    ⭐ WHY AUTOMATIC. Arming was the agent's job and it is the one step whose omission
    cannot be recovered from: everything else leaves a trace to pick up later, but a run
    that ends with nothing armed simply never continues - the handoff sits on disk and
    nothing ever reads it. ⚠ And arming is REVERSIBLE (`--cancel`, and do_run() stands down
    on its own when a session is alive), while missing the moment is not.

    ⛔ IT ARMS FOR THE FOLDER OF THIS DISPATCH, never "the newest task folder". The gate can
    see several under task_root; arming for the wrong one plants a resume that continues
    work nobody asked to continue.

    ⛔ AND IT RE-ARMS WHEN THE TARGET MOVES. `resume.json` records the task and the reset it
    was armed for. Same task and same reset - do nothing. A DIFFERENT reset means the window
    that is blocking has changed, which really does happen: the brake can flip from the
    five-hour window to the seven-day one, and a resume aimed at the old reset would wake to
    find itself still blocked.

    ⚠ NEVER RAISES, and never waits. This runs inside a PreToolUse hook: `schtasks` is fast
    but it is still a subprocess, and nothing it can do may be allowed to take enforcement
    down with it. Returns True when it started one.
    """
    if not cfg.get("auto_arm_resume", DEFAULTS["auto_arm_resume"]):
        return False
    v = usage.verdict(sdir, usage.config(sdir))
    if not arm_trigger(v):
        return False
    # ⛔ NO DISPATCH MEANS NO TASK FOLDER, AND THAT USED TO MEAN NO RESUME. `folder` comes
    # from the dispatch prompt, so a session that never dispatched - which is exactly the
    # shape that burned a whole window on 2026-08-31 - reached here with nothing and returned.
    # ⇒ The gate writes its own handoff into its own state directory and arms against that.
    if not folder:
        folder = generated_handoff(sdir, cfg, session_id, cwd, gate_log_tail(sdir))
        if not folder:
            log(root, "AUTO-ARM-SKIPPED no task folder and no generated handoff")
            return False
        log(root, "AUTO-ARM-GENERATED %s" % folder)
    if handoff_state(root, cfg, folder, started)[0] != "ok":
        return False        # nothing worth waking up for; the refusal above says so
    # ⭐ THE TARGET IS THE WINDOW THAT IS BLOCKING, which resume.py already works out - and
    # asking it beats re-deriving it here, where the two could disagree about which reset a
    # resume was armed for.
    try:
        sys.path.insert(0, HERE)
        import resume as _resume
        want, _which = _resume.reset_time(sdir, usage.config(sdir))
    except Exception as exc:
        log(root, "AUTO-ARM-FAILED %r" % (exc,))
        return False
    if not want:
        return False
    # ⭐ THIS SESSION'S record, not "the" record. While there was one file per machine this
    # de-dup also silently suppressed a SECOND session's arm whenever the first had armed
    # for the same folder and reset. ADR 20260917-132015, D1.
    state = usage.read_json(_resume.record_path(sdir, session_id), {}) or {}
    if (state.get("task") == folder
            and isinstance(state.get("armed_for_reset"), (int, float))
            and abs(state["armed_for_reset"] - want) <= 1):
        return False                      # already armed for exactly this
    # ⚠ AND A SPAWN FLOOR, like every other fork in this file. Without it a run that cannot
    # arm - no scheduler, no permission - would start a subprocess on every tool call for
    # the rest of the session.
    mark = state_path(sdir, session_id, ARM_MARK)
    now = time.time()
    try:
        if now - os.path.getmtime(mark) < 300:
            return False
    except OSError:
        pass
    try:
        os.makedirs(os.path.dirname(mark), exist_ok=True)   # the mark lives in state/ now
        with open(mark, "w") as f:
            f.write(str(now))
        kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
              "stderr": subprocess.DEVNULL, "cwd": root}
        if os.name == "nt":
            kw["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0x8)
                                   | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200))
        else:
            kw["start_new_session"] = True
        # ⛔ THE SESSION ID IS PASSED, NEVER LEFT TO BE GUESSED. Without it do_arm falls back
        # to arming_session()'s "newest state/*.alive", whose own docstring says it picks the
        # WRONG id when two sessions are live - which is precisely when a per-session resume
        # matters. ADR 20260917-132015, D12.
        argv = ["--arm", "--task", folder, "--dir", sdir]
        if session_id:
            argv += ["--session", str(session_id)]
        subprocess.Popen([sys.executable, os.path.join(HERE, "resume.py")] + argv, **kw)
    except Exception as exc:
        log(root, "AUTO-ARM-FAILED %r" % (exc,))
        return False
    # ⭐ THE SESSION ID IS PART OF THE LINE, not decoration. "did two sessions arm inside one
    # window?" is the question that says whether per-session resume was worth building, and
    # this line - the auto-arm path, which is where the single-slot clobbering happened - could
    # not answer it. ADR 20260917-132015, D11.
    # ⭐ AND THE BAND (0.67), so ADR 20261001-065500's reconsideration criterion - how many
    # alarms armed at relaxed PACE ran for finished work - can be read off this log.
    band = (" band=net" if v.get("relaxed_stop") else
            " band=relaxed-pace" if v.get("relaxed_pace") else "")
    log(root, "AUTO-ARM %s for %s (session=%s)%s"
              % (folder, time.strftime("%Y-%m-%d %H:%M", time.localtime(want)),
                 str(session_id or "")[:8] or "?", band))
    return True


HANDOFF_SEEN = "handoff-written"      # state/<sid>.handoff-written: one task folder per line


def note_handoff_write(sdir, cfg, session_id, tool, tool_input):
    """Record that THIS session wrote <task_root>/<folder>/HANDOFF.md, from a PostToolUse payload.

    ⛔ TIME IS NOT AUTHORSHIP. The first version of arm_from_handoff() called a HANDOFF.md
    "written this session" when its mtime was newer than the session stamp - and `git pull`,
    `checkout`, `merge`, `stash pop` set mtime=now on every tracked file. Measured 2026-09-02 by
    the code review: one Stop at PACE after such a checkout armed a FINISHED task's folder
    (`fresh=3`, the newest-dated one - exactly the guess maybe_auto_arm() refuses). The gate
    already sees every Write/Edit `file_path` and every Bash command on PostToolUse, so a
    HANDOFF.md path that names a task folder in either is direct evidence of authorship.
    ⚠ A Bash write whose path is hidden in a shell variable is NOT seen (the file tool is the
    documented route); a session started before this shipped has no record and arms nothing -
    the safe direction.
    """
    text = ""
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        text = str((tool_input or {}).get("file_path") or "")
    elif tool == "Bash":
        # ⛔ ONLY A PATH THAT IMMEDIATELY FOLLOWS A REDIRECT COUNTS. The first rule was
        # "HANDOFF.md anywhere and a `>` anywhere", and the round-2 review measured it
        # recording a folder from `cat .../HANDOFF.md 2>&1`, from `> /dev/null`, from a `>`
        # inside a grep pattern and from prose in a heredoc - one Stop then armed a finished
        # task. `>` or `>>`, optional spaces and one quote, then the path, ending in HANDOFF.md.
        cmd = str((tool_input or {}).get("command") or "")
        text = " ".join(re.findall(r">>?\s*[\"']?(\S+?" + re.escape(HANDOFF) + r")(?=[\"'\s;&|)]|$)",
                                   cmd))
    if HANDOFF not in text:
        return []
    tr = str(cfg["task_root"]).replace("\\", "/")
    names = re.findall(re.escape(tr) + r"/([A-Za-z0-9._-]+)/" + re.escape(HANDOFF)
                       + r"(?=[\"'\s;&|)]|$)", text.replace("\\", "/"))
    have = handoffs_written(sdir, session_id)
    new = [n for n in dict.fromkeys(names) if n not in have]
    # ⭐ RETURNS every task folder this write names, new or not - a REWRITE of a known handoff is
    # still a fresh handoff, and the caller arms on it (arm_on_handoff_write, 0.66).
    if not new:
        return names
    path = state_path(sdir, session_id, HANDOFF_SEEN)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for n in new:
                f.write(n + "\n")
    except OSError:
        pass
    return names


def handoffs_written(sdir, session_id):
    """The task folders whose HANDOFF.md this session wrote, in the order first seen."""
    try:
        with open(state_path(sdir, session_id, HANDOFF_SEEN), encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip()]
    except OSError:
        return []


def arm_from_handoff(root, sdir, cfg, session_id, v=None):
    """Arm for the freshest HANDOFF.md THIS session wrote, when the window is closing.

    ⛔ THE ARM USED TO LIVE ONLY ON THE DISPATCH PATH, so a session that obeyed PACE - "finish
    what is in flight, no new wave" - wrote its handoff, dispatched nothing more, and ended
    unarmed. Measured 2026-09-02 on two machines the same afternoon: the session that dispatched
    a reviewer after its handoff was armed at 13:35; the one that stopped dispatching was not,
    and its agent confirmed the manual `resume.py --arm` was simply forgotten. A step that
    depends on an agent remembering is not a step. ⇒ This runs when the TURN ENDS (`Stop`) and
    on every prompt at PACE/STOP, and the agent is not asked. ADR:
    Memory/tasks/20260902-142400-auto-arm-on-stop/ADR.md.

    ⭐ A NARROWER RULE THAN "THE NEWEST TASK FOLDER", which maybe_auto_arm() refuses to guess for
    good reason: the candidates are the folders whose HANDOFF.md THIS SESSION WROTE - recorded
    by note_handoff_write() from the PostToolUse payloads, never inferred from a clock - and of
    those only the ones handoff_state() calls "ok" (present, ≥ 200 chars, mtime at or after the
    session stamp). No stamp → no freshness test → nothing, logged. No recorded write → nothing,
    logged. Several usable → the newest, and the log carries both counts and the session id so
    the ADR's reconsideration criteria can be read off it.

    ⚠ The scan root is the START-time cwd when the session recorded one (session_cwd), because
    the payload's cwd follows the Bash tool's `cd`; see the earlier resume ADR. Every log line
    here goes to that root too, so one event lands in one repository log. Returns the one-line
    screen message when it armed, else None. May raise: callers wrap it, like the two existing
    callers of maybe_auto_arm().
    """
    v = v if v is not None else usage.verdict(sdir, usage.config(sdir))
    if not arm_trigger(v):
        return None
    sid8 = str(session_id or "")[:8]
    start_cwd = session_cwd(sdir, session_id)
    scan_root = repo_root(start_cwd) if start_cwd else root
    started = session_start(sdir, session_id)
    if not started:
        log(scan_root, "AUTO-ARM-STOP-SKIPPED no session stamp session=%s" % sid8)
        return None
    written = handoffs_written(sdir, session_id)
    if not written:
        log(scan_root, "AUTO-ARM-STOP-SKIPPED no HANDOFF.md write observed this session "
                       "(root %s) session=%s" % (scan_root, sid8))
        return None
    usable = []
    for folder in dict.fromkeys(written):
        state, path = handoff_state(scan_root, cfg, folder, started)
        if state != "ok":
            continue
        try:
            usable.append((os.path.getmtime(path), folder))
        except OSError:
            continue
    if not usable:
        log(scan_root, "AUTO-ARM-STOP-SKIPPED the %d HANDOFF.md this session wrote are missing, "
                       "thin or older than the session stamp under %s session=%s"
                       % (len(written), scan_root, sid8))
        return None
    usable.sort()
    folder = usable[-1][1]
    if not maybe_auto_arm(scan_root, sdir, cfg, folder, started, session_id, start_cwd):
        return None                    # already armed for this target, floor, or off switch
    log(scan_root, "AUTO-ARM-STOP %s (written=%d usable=%d session=%s)"
                   % (folder, len(written), len(usable), sid8))
    # ⛔ THE CANCEL IS SCOPED TO THIS SESSION. A bare `--cancel` clears every session's record
    # (ADR 20260917-132015, D8); this line used to print the bare form to one session about its
    # own alarm, and measured 2026-09-25, a session following such advice retired every other
    # session's resume.
    # ⚠ AND IT SAYS THIS IS ROUTE (B). resume.py prints "arm route (A) as well" only on a hand-run
    # `--arm`; this path arms detached, so until 0.65.3 no agent that was auto-armed ever saw it
    # (both write-ups of the 2026-09-27 incident say so). Here the model reads it on a prompt;
    # on Stop only the person does, because the turn is already over.
    # ⭐ 0.68: the route-A sentence carries the exact cron and the check-first wake prompt
    # (ADR 20261001-085000 D1/D3) instead of "a one-shot CronCreate wake for then".
    hpath = os.path.join(scan_root, cfg["task_root"].replace("/", os.sep), folder, HANDOFF)
    return (" ⭐ dispatch-guard: a resume was ARMED for `%s` (the HANDOFF.md written this "
            "session) because the usage window is closing (%s); a few minutes after %s %s"
            " - nothing runs in the background (0.69). "
            "If the window is closed or the wake cannot be sent, the next session is told. Cancel it "
            "with `%s --cancel --session %s` if you do not want that (that cancels this "
            "session's alarm only).%s"
            % (folder, relax_band_label(v), v.get("resets_clock", "the reset"),
               ("it WAKES THIS window to continue from that handoff"
                if os.environ.get("CLAUDE_CODE_MESSAGING_SOCKET") and
                os.environ.get("CLAUDE_CODE_SESSION_ATTENDED") == "1" and
                os.environ.get("CLAUDE_CODE_SESSION_ID") == str(session_id)
                else "it fires, but this session has no window it can wake (no local messaging, or "
                     "not interactive), so it will only tell the next session"),
               runnable("resume.py"), session_id,
               # ⚠ LAST: for_screen() cuts here, and the cancel command is the person's (review B N1)
               route_a_line(sdir, v, {"handoff": hpath})))


def _epoch(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0


def wake_time(sdir, v, rec=None, reset=None):
    """(epoch, cron) for THIS session's own one-shot wake (route A), or None. Never raises.

    ⭐ THE ALARM SHOULD WAKE THE SESSION ITSELF (owner, 2026-10-01). The OS alarm (route B) cannot -
    it starts a NEW headless `claude -p`; only a CronCreate job the session schedules for itself
    can, and that wake arrives as a prompt at GO, where stand_down_resume() cancels this session's
    OS alarm. ⇒ The wake must land AFTER the reset and BEFORE the OS alarm: max(reset + 1 min,
    OS alarm - 2 min), one minute later if that is :00 or :30 (CronCreate fires a one-shot there
    up to 90 s early - its own tool description), and None if no such minute exists (a
    `resume_offset_min` under 2). The cron carries day and month, so a 7d reset is not "today".
    ADR 20261001-085000 D1.
    """
    try:
        rec = rec if isinstance(rec, dict) else {}
        sys.path.insert(0, HERE)
        import resume as _resume
        r = rec.get("armed_for_reset")
        if not _epoch(r):
            try:
                r = _resume.reset_time(sdir, usage.config(sdir), v)[0]
            except Exception:
                r = None
        if not _epoch(r):
            r = reset
        if not _epoch(r):
            return None
        b = rec.get("at")
        if not _epoch(b):
            b = r + _resume.rcfg(sdir)["resume_offset_min"] * 60
        t = max(r + 60, b - 120)
        t = (int(t) + 59) // 60 * 60     # a cron fires at :00 of its minute - that, not t, must be after the reset
        if time.localtime(t).tm_min in (0, 30):
            t += 60
        # ⚠ against the OS task's MINUTE (schtasks fires at its floored minute), and with 2 min of
        # lead: a one-shot cron scheduled after its minute passed waits a YEAR (fix review, 0.68).
        if t >= b // 60 * 60 or t <= time.time() + 120:
            return None              # no minute left, or a stale / too-near wake
        lt = time.localtime(t)
        return t, "%d %d %d %d *" % (lt.tm_min, lt.tm_hour, lt.tm_mday, lt.tm_mon)
    except Exception:
        return None


def wake_prompt(handoff=None):
    """What a woken session is told - check first, stop if nothing is left (owner, 2026-10-01).

    ⛔ MEASURED 2026-10-01 07:03: a headless resume found its handoff's next step already done and
    no new work - and then spent 8 minutes on checks it chose itself and edited a README. The owner:
    「被鬧鐘叫醒後應該去讀 handoff 或檢查未完成項目，如果真的沒有，就停下來就好」. ADR 20261001-085000 D3.
    ⚠ No double quote inside: the route-A line quotes this text whole.
    """
    # ⚠ THE ONE THING BEFORE THE CHECK (ADR 20261001-085000 D8, its review B1): this session stays
    # open, so its own cowork check-in is rewritten first - the stop rule applies after it.
    return ("dispatch-guard wake: the usage window has reset. If this project keeps a shared "
            "coordination board (cowork), first re-read it and rewrite your own check-in with this "
            "session's id. Then re-read %s and check, for this task "
            "only, what is still unfinished - its Next step against the commits since it was "
            "written that touch its task folder or the files it names, and that folder's "
            "RESULT.md / progress.md. Continue what is open. If nothing is left, or the handoff "
            "says the rest waits on the owner or on another session, add one line saying so to "
            "its Result section and stop - no other work, no looking for work elsewhere."
            % (handoff or "your HANDOFF.md"))


ROUTE_A_LEAD = " If this session stays open, also schedule ONE in-session wake"


def for_screen(text):
    """The person's copy of an arm line: without the route-A instructions, which are the MODEL'S
    (review A of 0.68: ~1000 characters of CronCreate syntax on the screen, and at Stop only the
    person reads it at all)."""
    return str(text or "").split(ROUTE_A_LEAD)[0].strip()


def route_a_line(sdir, v, rec=None, reset=None):
    """The sentence asking THIS session to schedule its own wake, or "" (ADR 20261001-085000 D1)."""
    w = wake_time(sdir, v, rec, reset)
    if not w:
        return ""
    t, cron = w
    return (ROUTE_A_LEAD + " so the alarm wakes "
            "THIS session: CronCreate (ToolSearch \"select:CronCreate\") with cron \"%s\" (%s), "
            "recurring false, prompt \"%s\" - skip it if you already scheduled one for this reset. "
            "When it fires, the gate cancels this session's OS alarm."
            % (cron, time.strftime("%m-%d %H:%M", time.localtime(t)),
               wake_prompt((rec or {}).get("handoff") if isinstance(rec, dict) else None)))


WAKE_MARK = "dispatch-guard wake:"     # the first words of every route-A wake prompt (wake_prompt)


def wake_reason(payload, cfg, now=None):
    """Why this event WAKES the session, or None (ADR 20261001-085000 D8).

    A route-A wake (its prompt carries WAKE_MARK); a prompt after this session's previous hook is
    older than `wake_gap_min` - read from `.alive` BEFORE main()'s heartbeat rewrote it, passed in
    as `_dg_prev_alive` (missing = unknown = no gap wake); a SessionStart from resume / clear /
    compact, after which the context that remembered the board may be gone.
    """
    now = now if now is not None else time.time()
    ev = payload.get("hook_event_name")
    if ev == "SessionStart":
        return {"resume": "resumed", "clear": "after /clear",
                "compact": "after a context compaction"}.get(payload.get("source"))
    if ev != "UserPromptSubmit":
        return None
    if WAKE_MARK in str(payload.get("prompt") or ""):
        return "by its alarm"
    prev = payload.get("_dg_prev_alive")
    gap = _positive_number(cfg.get("wake_gap_min")) or DEFAULTS["wake_gap_min"]
    if _epoch(prev) and now - prev >= gap * 60:
        return "after %d idle minutes" % int((now - prev) // 60)
    return None


def cowork_wake_note(payload, root, sdir, cfg, now=None):
    """(context, screen) asking a WOKEN session to re-check-in on the cowork board, or ("", None).

    ⛔ THE RULE EXISTED AND NOTHING SAID IT AT THE MOMENT IT APPLIES (owner, 2026-10-01: a woken
    session does not always re-check / re-register its session id on the board). cowork rule 2
    rewrites the check-in "on every restart" - and a wake is one: the runtime name and [ref] change
    while a session sleeps, and a headless resume or a compaction loses the memory of the board.
    The hook's only cowork enforcement (cmd_guards.cowork_first) is silent once the skill was
    loaded, so a woken session was never reminded. ⇒ One line at the wake, when the repository has
    a live peer or this session has worked under cowork. A reminder, not a refusal: the check-in
    path is the project's, and the first write after a wake is usually that check-in itself.
    ADR 20261001-085000 D8. Never raises.
    """
    try:
        why = wake_reason(payload, cfg, now)
        if not why:
            return "", None
        sid = payload.get("session_id")
        if not sid:
            return "", None          # no id to write into a check-in
        ctx = guard_ctx(root, sdir, sid, cfg)
        peers = cmd_guards.peer_sessions(ctx)
        seen = cmd_guards.skill_seen(ctx, "cowork")
        if not peers and not seen:
            return "", None
        log(root, "WAKE-CHECKIN-NUDGE why=%s peers=%d cowork=%s"
            % (why.replace(" ", "-"), len(peers), "seen" if seen else "not-seen"))
        who = (" while %d other session%s work%s in this repository"
               % (len(peers), "" if len(peers) == 1 else "s", "s" if len(peers) == 1 else "")
               if peers else "")
        load = ("" if seen else " Load `dispatch-guard:cowork` first - this session has not.")
        text = (" dispatch-guard: this session was just woken (%s)%s. If this project keeps a "
                "shared coordination board with check-in files (cowork), do this BEFORE any other "
                "work: re-read the board, then rewrite YOUR role's check-in with this session's id "
                "`%s`, its current runtime name and [ref] - they change while a session sleeps, "
                "and a peer that sends to the old name reaches somebody else (cowork rule 2; "
                "reference/coordination.md 2.8).%s" % (why, who, sid, load))
        screen = ("session woken (%s)%s - asked to re-check-in on the shared board first."
                  % (why, (" with %d live peer%s" % (len(peers), "" if len(peers) == 1 else "s"))
                   if peers else ""))
        return text, screen
    except Exception as exc:
        log(root, "WAKE-CHECKIN-FAILED %r" % (exc,))
        return "", None


def relax_band_label(v):
    """The word for the ARMED line: "GO" alone would read as "why arm at GO?" (0.67, D7)."""
    if v.get("relaxed_stop") and v.get("verdict") == "GO":
        return "GO, a STOP relaxed near the reset"
    if v.get("relaxed_pace"):
        return "GO, a PACE relaxed near the reset"
    return v.get("verdict")


def on_stop(payload, root, sdir, cfg):
    """The turn ended. Arm for this session's fresh handoff if the window is closing.

    ⚠ Prints ONLY when it armed - one `systemMessage` for the person - and nothing otherwise,
    because a Stop hook's empty stdout changes nothing about the turn (measured in the 2.0.56
    binary's hook-output schema, which also accepts systemMessage on every event). It never
    blocks the turn from ending.
    """
    line = None
    try:
        line = arm_from_handoff(root, sdir, cfg, payload.get("session_id"))
    except Exception as exc:
        log(root, "AUTO-ARM-FAILED %r" % (exc,))
    if line:
        print(json.dumps({"systemMessage": for_screen(line)}, ensure_ascii=False))


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


def claim_slot(root, sdir, cfg, session_id, slots, tool_use_id, folder=None, desc=None,
               wants=None):
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
            # ⭐ `wants` IS STASHED AT CLAIM TIME rather than re-derived on the way out. The
            # PostToolUse payload is not the place to go looking for the prompt again, and
            # the answer must be the one the PreToolUse branch actually computed - two reads
            # of the same prompt by two code paths is two chances to disagree.
            os.write(fd, json.dumps({"id": str(tool_use_id), "folder": folder,
                                     "desc": desc, "at": time.time(),
                                     "wants": list(wants or ())}).encode("utf-8"))
            os.close(fd)
            return True
        except FileExistsError:
            continue
        except OSError:
            return True                    # cannot claim; fail open rather than block
    return False


def held_slots_note(sdir, cfg, session_id, slots):
    """One line per held slot: what holds it, how old it is, and the minute it self-clears.

    ⛔ A REFUSAL THAT NAMES NOTHING GETS THE STATE FILE DELETED. Measured 2026-09-02 on
    another machine: the first dispatch died to an API 529 before its PostToolUse, so its
    slot was never released; every later dispatch was refused with "1 sub-task already in
    flight"; `ListAgents` showed ZERO agents alive; and the session - correctly reading the
    record as stale - removed this plugin's own enforcement state by hand. The slot would
    have been reclaimed on its own (claim_slot, slot_ttl_min), but the refusal never said
    so, and a wait nobody can see the end of looks like a broken gate.
    ⇒ Say who holds it and when the clock runs out, so the answer is "wait" and never "edit
    the enforcement state".
    """
    lines = []
    for i in range(slots):
        p = state_path(sdir, session_id, "slot%d" % i)
        try:
            started = os.path.getmtime(p)
            with open(p, encoding="utf-8") as f:
                raw = f.read().strip()
        except OSError:
            continue                       # free, or unreadable - either way not a holder
        try:
            held = json.loads(raw)
        except Exception:
            held = {}                      # an older version's slot: age still reads true
        lines.append("  slot%d: %s - dispatched %s (%.0f min ago), reclaimed automatically "
                     "at %s if it never returns"
                     % (i, held.get("desc") or "(unnamed)",
                        time.strftime("%H:%M", time.localtime(started)),
                        (time.time() - started) / 60.0,
                        time.strftime("%H:%M", time.localtime(
                            started + cfg["slot_ttl_min"] * 60))))
    return "\n".join(lines)


def safe_held_slots_note(root, sdir, cfg, session_id, slots):
    """held_slots_note(), and it NEVER raises. The refusal must print; the note is optional.

    ⛔ A CRASH INSIDE deny()'S ARGUMENT LIST APPROVES THE DISPATCH. main()'s outer handler
    swallows the exception and exits 0 with nothing on stdout - and a hook that prints
    nothing is an allow. Measured 2026-09-02 by the review of 0.56.1: `slot_ttl_min` set to a
    huge value made `time.localtime(started + ttl * 60)` raise OSError(22), so the log said
    DENY(slots-full) and the dispatch went through. The words added to make the refusal
    SAFER were the words that made it disappear.
    ⇒ One boundary, here, for every failure the note can have: the refusal goes out with
    the note replaced by "", and the log says why - a blank note and a note that was never
    attempted must not look the same afterwards.
    """
    try:
        return held_slots_note(sdir, cfg, session_id, slots)
    except Exception as exc:
        log(root, "HELD-NOTE-FAILED %r" % (exc,))
        return ""


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

def attended():
    """Is a person at this session? False only when Claude Code says so (`CLAUDE_CODE_SESSION_ATTENDED=0`:
    a headless `claude -p`, measured 2026-10-01). Unset (an older build) counts as attended.

    ⛔ WHY IT EXISTS (0.69, review A N4 / review B B1): the wake relay is a headless `claude -p`, and its
    SessionStart would READ AND CONSUME the owner's failure notices into a session nobody sees. A first
    fix switched the gate off by an environment variable - which any session could set for a child
    (review B measured it disabling the dispatch protocol). This one disables nothing: a headless
    session simply leaves the notices for a session a person will read.
    """
    return os.environ.get("CLAUDE_CODE_SESSION_ATTENDED") != "0"


def failed_resume_note(sdir, session_id=None):
    """If a scheduled resume gave up while nobody was watching, say so - once.

    ⭐ With `session_id`, only THAT session's marker: the prompt path uses it so the session that
    just auto-armed hears, on its next prompt, that the arm was taken back down - it had already
    been told "ARMED" by a message printed before the detached arm finished.

    ⛔ A scheduled task has no terminal and no window. Without this the outcome of an
    overnight resume is invisible: "it failed at 03:40" and "it was never armed" and
    "the work turned out not to be needed" all look identical the next morning. The
    marker is consumed here so it is announced exactly once.
    """
    # ⛔ EVERY MARKER, NOT ONE. There was a single `resume_failed.json`: two resumes failing
    # overnight left one announcement, because the second write overwrote the first and this
    # reader deleted it. The owner heard about one failure and never learnt of the other.
    # ⚠ The legacy path is still read, so an upgrade does not swallow a marker written by
    # the previous version. ADR 20260917-132015, D9.
    if session_id:
        paths = glob.glob(os.path.join(sdir, "resume", safe_session(session_id) + ".failed"))
    else:
        paths = sorted(glob.glob(os.path.join(sdir, "resume", "*.failed")))
        legacy = os.path.join(sdir, "resume_failed.json")
        if os.path.exists(legacy):
            paths.append(legacy)
    out = []
    for path in paths:
        data = usage.read_json(path, None)
        if not data:
            continue
        try:
            os.remove(path)             # consumed here, so it is announced exactly once
        except OSError:
            pass
        # ⭐ WHICH WORK STOPPED. The old message named neither the session nor the task, so
        # even the one announcement that survived did not say what had been abandoned.
        who = str(data.get("session_id") or "")[:8]
        what = data.get("task")
        # ⚠ A marker is a file anybody can write; this runs on EVERY prompt since 0.65.4, and a
        # TypeError here would take the whole hook down with it - which fails open (review).
        at = data.get("at") if isinstance(data, dict) else None
        at = at if isinstance(at, (int, float)) and 0 <= at < 4102444800 else 0
        out.append(" ⛔ TELL THE USER FIRST, BEFORE ANYTHING ELSE: a scheduled resume gave "
                   "up at %s and the work did NOT continue%s%s - %s"
                   % (time.strftime("%Y-%m-%d %H:%M", time.localtime(at)),
                      (" (task %s)" % what) if what else "",
                      (" (session %s)" % who) if who else "",
                      data.get("why", "no reason recorded")))
    return "".join(out)


# ⚠ THE TWO MARKER KINDS ARE PRUNED BY DIFFERENT RULES, AND THE ASYMMETRY IS THE POINT.
# The owner asked how few could be kept. For `.alive` the answer is one; for `.start` the
# question does not apply, because it is not a record - it is a switch.
STATE_KEEP_ALIVE = 20            # only the newest is READ; the rest are a count on screen
STATE_KEEP_DAYS_DEFAULT = 7      # ⛔ an age rule, and it is a SAFETY margin - see prune_state.
                                 # Overridable per install via cfg["state_keep_days"].


def prune_state(sdir, cfg=None):
    """Bound the state directory. Runs once per session start.

    ⛔ WITHOUT THIS IT GROWS FOREVER. Every session leaves one small file per KIND - a
    `.start`, an `.alive`, a `.branch-<repo>`, a `.skill-seen-<name>` for each skill, a
    `.warned`/`.warned-tool*`, a `.handoff-written` - and none was removed. Measured: 322
    files across 19 days, in a folder a person is expected to look inside. Found because the
    owner noticed it growing, not because anything failed.

    ⛔ ALL-BUT-EXCEPTIONS, NOT A SUFFIX LIST. An earlier version enumerated the kinds it knew
    (`.warned`, `.handoff-written`, `.start`) and missed every other - `.branch-*` alone was
    179 of those 322 files. A new marker kind added later would be missed again the same way.
    So this sweeps EVERYTHING in state/ by age, with only the two kinds that have a different
    rule carved out:
      - `.alive` - PRUNED BY COUNT, newest STATE_KEEP_ALIVE kept. A scheduled resume reads only
        the NEWEST ("has any session been alive since the window reopened?"); the rest are a
        count on `install.py --status`. Handled first, then skipped by the age sweep.
      - `.slot*` - NOT TOUCHED. Live concurrency state with its own minute-scale reclaim
        (slot_ttl_min); removing a held one hands out a slot twice.

    ⛔ TWO ENFORCEMENT MARKERS ARE SWEPT BY AGE WITH THE REST, and that age is a SAFETY margin,
    because BOTH fail OPEN when lost mid-session:
      - `.start` is the switch that decides whether a session is ENFORCED at all:
        `session_start()` returning None sends the gate down the ADVISORY branch, so deleting a
        still-running session's marker silently turns its brake off.
      - `.branch-<repo>` is the commit-branch guard's baseline (cmd_guards.g_commit_branch).
        With it gone, the next commit RE-RECORDS whatever branch is checked out and allows it -
        so a commit that has drifted onto another session's branch, the exact damage that guard
        exists to prevent, is waved through and re-blessed.
    ⚠ Liveness cannot be inferred - an open but IDLE session fires no hooks and looks exactly
    like a dead one - so the margin must EXCEED the longest a single session can run.
    `state_keep_days` (default 7) is that margin, not a tuning knob to shrink casually: set it
    below your sessions' length and you weaken those two guards, not just tidy the folder.

    ⚠ DELETE-SAFE like history_keep_days: `state_keep_days` is coerced by usage._days(), so a
    string / negative / 0 / null means KEEP EVERYTHING (skip the age sweep), never "fall back
    to 7 and start deleting". The `.alive` COUNT prune still runs - it is a fixed bound, not a
    retention setting, and deletes nothing a resume needs.
    """
    removed = 0
    state = os.path.join(sdir, "state")
    # .alive - by count, newest kept (a fixed bound, always applied)
    alive = []
    for path in glob.glob(os.path.join(state, "*.alive")):
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
    # everything else by age. ⛔ DELETE-SAFE: a bad state_keep_days keeps everything.
    days = usage._days((cfg or {}).get("state_keep_days"), STATE_KEEP_DAYS_DEFAULT)
    if days > 0:
        cutoff = time.time() - days * 86400
        for path in glob.glob(os.path.join(state, "*")):
            suffix = os.path.basename(path).rsplit(".", 1)[-1]
            if suffix == "alive" or suffix.startswith("slot"):
                continue             # .alive: by count above; .slot*: live, its own reclaim
            try:
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    removed += 1
            except OSError:
                pass                 # in use, or gone already; either way not our problem
    return removed


def stand_down_resume(root, sdir, v, session_id=None):
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
        PACE     KEEP (since 0.58.0; it used to CANCEL). The window has NOT reopened - PACE
                 is the closing window - and since the turn's end arms at PACE, cancelling
                 here made every prompt cancel and every turn end re-arm: measured by the
                 0.58.0 review, 20 arms and 19 cancels in a 20-turn PACE session, with a
                 screen line on every prompt. The alarm is inert while the session lives
                 (do_run stands down on a live session) and costs nothing to keep.
                 ADR 20260902-142400, decision 6 ⟨R2⟩.
        GO       CANCEL. There is MEASURED headroom, so the work can proceed now, in this
                 session, with its context. The alarm has nothing left to do.
        GO+relaxed_stop  KEEP. The word is GO only because a STOP was RELAXED near the reset -
                 the window is still closing and we are working into it on purpose. Cancelling
                 the backup here would strip the net exactly when it was armed. See usage._relax.
        GO+relaxed_pace  KEEP (0.67). The same for a relaxed PACE: the window is closing and the
                 alarm was armed first on purpose (owner 2026-10-01). It is cancelled by the first
                 plain GO - the reset, or an early reopen - and do_run stands it down if this
                 session fired a hook after the reset. ADR 20261001-065500 D3.

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
    if v["verdict"] != "GO":
        return ""
    # ⛔ THE NET ZONE KEEPS THE RESUME. A relaxed STOP reads GO, but it means the window is
    # still closing and we are knowingly working into it - cancelling the backup here would
    # strip the safety net exactly when it was armed on purpose. Same KEEP as STOP in the table.
    # ⭐ And the relaxed-PACE band, for the same reason (0.67).
    if v.get("relaxed_stop") or v.get("relaxed_pace"):
        return ""
    # ⛔ ONLY THIS SESSION'S ALARM. It used to cancel whatever the one shared record held,
    # so a session reaching GO retired a DIFFERENT session's still-needed resume.
    # ⚠ What this does NOT yet cover is the case the docstring above is about - the work
    # carried on in a different session from the one that armed. ADR 20260917-132015, D4
    # adds that half (cancel the alarms of task folders THIS session wrote a handoff to);
    # until it lands, `--cancel` is the bound.
    import resume as _resume_mod          # cycle-safe here, as below
    state = usage.read_json(_resume_mod.record_path(sdir, session_id), None)
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
        cancelled = resume.do_cancel(sdir, quiet=True, session_id=session_id) == 0
    except Exception as exc:
        log(root, "STAND-DOWN-FAILED %r" % (exc,))
        return (" ⚠ A scheduled resume is still armed for %s but the usage window has "
                "reopened (%s), and cancelling it just failed. TELL THE USER to run "
                "`resume.py --cancel --session %s` themselves (this session's alarm only - a "
                "bare `--cancel` would retire every session's) - otherwise it will wake later "
                "and redo work that is already done." % (when, v["verdict"], session_id))
    log(root, "STAND-DOWN %s the resume armed for %s (verdict %s)"
              % ("cancelled" if cancelled else "FAILED to cancel", when, v["verdict"]))
    if cancelled:
        # ⛔ AND THE SPAWN FLOOR GOES WITH IT. A GO prompt cancels the resume the last turn
        # end armed - the window reopened, the person is back - and without this the 300 s
        # floor blocked the re-arm at the next PACE turn end when the window closed again
        # inside five minutes. The floor exists for a machine that CANNOT arm; a cancel is
        # proof this one can. ADR 20260902-142400, decision 6 (PACE itself keeps the alarm).
        try:
            os.remove(state_path(sdir, session_id, ARM_MARK))
        except OSError:
            pass
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
        # ⭐ JSON NOW, AND THE `cwd` IS THE POINT. The stamp's own value has never been read -
        # `session_start()` takes the mtime - so the content was free, and the one thing the
        # gate knows here and can never recover later is where this session STARTED. A resume
        # armed hours afterwards needs it: the payload's `cwd` by then has followed whatever
        # `cd` the Bash tool last ran. See session_cwd().
        with open(state_path(sdir, payload.get("session_id"), "start"), "w",
                  encoding="utf-8") as f:
            json.dump({"at": time.time(), "cwd": payload.get("cwd") or ""}, f)
        prune_state(sdir, cfg)
    except OSError:
        pass
    # ⭐ AND THE RESUME RECORDS, which prune_state deliberately cannot see: they live OUTSIDE
    # `state/` so its age sweep can never delete a live alarm's record. Their own reaper asks
    # the scheduler about names it already holds, one probe per record. ⚠ Wrapped and
    # separate from the block above: housekeeping must never take enforcement down, and this
    # one spawns subprocesses. ADR 20260917-132015, D6.
    try:
        sys.path.insert(0, HERE)
        import resume as _resume_reap
        _resume_reap.migrate_legacy(sdir)
        _resume_reap.reap_records(sdir)
        _resume_reap.upgrade_records(sdir)     # an alarm an older version registered (0.65.3)
        _resume_reap.announce_missed(sdir)     # an alarm whose time passed and never woke
    except Exception as exc:
        log(root, "REAP-FAILED %r" % (exc,))
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
    # ⛔ THE VERSION-FREE LAUNCHER, WRITTEN BEFORE ANYTHING NAMES IT. Everything outside the
    # plugin - the statusline, the VS Code watcher task, every command in the text below -
    # points at this one path, and this is what keeps it aimed at the copy that is running.
    # ⚠ Cheap: it reads one line out of one file and returns when the path already matches.
    moved = shim.write(sdir, os.path.dirname(HERE))
    if moved and moved[0]:
        log(root, "SHIM-REPOINTED %s -> %s" % moved)
    # ⛔ FORKED, NEVER AWAITED. See keep_prices_fresh(): this session keeps the table it has.
    if keep_prices_fresh(sdir, cfg):
        log(root, "MODEL-PRICE-REFRESH-FORKED")
    model_line = model_note(cfg, sdir, avail=available_models(root))

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
             maybe_repoint_statusline(sdir),
             maybe_adopt_statusline(cfg, sdir),
             # ⭐ resumed / cleared / compacted: re-check-in on the cowork board (0.68, D8)
             cowork_wake_note(payload, root, sdir, cfg)]
    notes = [failed_resume_note(sdir) if attended() else "",
             stand_down_resume(root, sdir, v, payload.get("session_id"))]
    notes += [c or "" for c, _s in pairs]

    text = ("Sub-task dispatch is governed by %s and enforced by a hook: one sub-task at "
            "a time, no background dispatch, no Workflow, and the plan plus every "
            "sub-task prompt are written to %s/<YYYYMMDD-HHMMSS-task-name>/%s BEFORE any "
            "dispatch%s.%s %s Before "
            "dispatching a wave run `%s --verdict` for GO/PACE/STOP - never interpret the "
            "raw numbers yourself.%s%s"
            % (cfg["protocol_doc"], cfg["task_root"], cfg["plan_glob"],
               (" - that folder already exists, so create the task folder inside it rather "
                "than choosing a location") if task_root_ready else
               (" - and %s could NOT be created, so create it yourself before dispatching"
                % cfg["task_root"]), skills_line, brake,
               runnable("usage.py"), model_line, "".join(notes)))

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


def driving_pct(v):
    """The percentage of the window that DROVE this verdict, and a label saying which one.

    Returns `("7d ", 99)` or `("", 90)`. The empty label is the five-hour window - the common
    case - so a five-hour line reads exactly as it always did and nothing quoting its shape
    needed editing.

    ⛔ `v["pct"]` IS ALWAYS THE FIVE-HOUR FIGURE, and every message that took it directly was
    wrong whenever the WEEK was the constraint. At 5h 3% / 7d 99% `v["text"]` correctly said
    the week was nearly spent, and the next sentence ordered `STOP at 3% - winding down`: one
    screen, one half saying the brake is on and the other naming 3%, which reads as a false
    alarm. Measured 2026-09-18.

    ⛔ AND THE FIRST FIX WAS INCOMPLETE, which is why this is a function and not two lines
    inlined. 0.60.2 corrected only the acknowledgement line. FOUR other sites still took the
    five-hour figure - the `USAGE(...)` log, both `DENY(...)` logs, and the `systemMessage` of
    the DISPATCH REFUSAL, which is the strongest thing this plugin ever says and is quoted in
    the README. ⇒ One helper, every caller, and `selftest()` asserts that neither
    `on_user_prompt` nor `on_pre_agent` reads `v["pct"]` directly again.

    ⭐ `driver` is `None` only when the verdict is GO; every caller here has already returned
    on GO. ⚠ The `7d ` label is the owner's choice of 2026-09-18, taken over a bare
    `STOP at 99%`: the number alone cannot be told from a five-hour one, and the statusline is
    showing the five-hour figure at that same moment.
    """
    if v.get("driver") == "7d":
        return "7d ", round(v.get("pct_7d") or 0)
    return "", round(v.get("pct") or 0)


def on_user_prompt(payload, root, sdir, cfg):
    """The wind-down net, ported from claude-pacer's budget-guard.

    Fires once per level per session and re-arms when the level changes, so a long
    autonomous run hears it more than once without being nagged every turn.
    """
    v = usage.verdict(sdir, usage.config(sdir))
    sid = payload.get("session_id")
    # ⛔ BEFORE the early return, because GO is precisely the path a reopened window
    # arrives on. The old code returned silently here, which is why an alarm could outlive
    # the wait it was armed for. See stand_down_resume().
    # ⛔ THIS SESSION'S OWN FAILED ARM FIRST: the auto-arm told it "ARMED" before the detached arm
    # found the scheduler could not start it (resume.py launch_probe) - see failed_resume_note().
    try:
        mine = failed_resume_note(sdir, sid) if attended() else ""
    except Exception as exc:              # a notice must never take the brake down with it
        log(root, "FAILED-NOTE-ERROR %r" % (exc,))
        mine = ""
    # ⭐ AND "THE WINDOW HIT THE CAP": a turn cut by the cap ends silently on screen - two of the
    # three sessions cut on 2026-09-29 never knew. Checked here too, because the first hook after
    # a reset is often a prompt. ADR 20260929-152000 item 5.
    try:
        check_wall_hit(root, sdir)
        mine += wall_hit_note(sdir, sid)
    except Exception as exc:
        log(root, "WALL-HIT-CHECK-FAILED %r" % (exc,))
    note = mine + (stand_down_resume(root, sdir, v, sid) or "")
    # ⭐ WOKEN? Then the cowork check-in comes first (0.68, ADR 20261001-085000 D8) - to the
    # model in full (`wk`), to the screen in one short line (`ws`), in every branch below.
    wake_ctx, wake_screen = cowork_wake_note(payload, root, sdir, cfg)
    wk = wake_ctx or ""
    ws = (" dispatch-guard: " + wake_screen) if wake_screen else ""
    if v["verdict"] not in ("PACE", "STOP"):
        # ⭐ THE RELAXED BANDS ARM HERE TOO (0.68, owner 2026-10-01 「要加」): a GO that is only a
        # relaxed PACE/STOP is a closing window. No acknowledgement line - it is not a wind-down -
        # and a plain GO still only stands down (above). ADR 20261001-085000 D5.
        if v.get("relaxed_stop") or v.get("relaxed_pace"):
            try:
                note += arm_from_handoff(root, sdir, cfg, sid, v) or ""
            except Exception as exc:
                log(root, "AUTO-ARM-FAILED %r" % (exc,))
        if note or wk:
            # ⭐ ON THE SCREEN TOO. A cancelled alarm is a fact the PERSON needs - "nothing
            # will wake later" - and the round-2 review of 0.58.0 measured this branch putting
            # it into additionalContext only, where only the model could read it.
            context_note(payload.get("hook_event_name", "UserPromptSubmit"),
                         "[usage]" + note + wk, systemMessage=(for_screen(note) + ws).strip())
        return
    # ⭐ ARM HERE TOO, on every PACE/STOP prompt and BEFORE the once-per-level return: a handoff
    # written after the warning still gets its resume on the next prompt, and the arm runs after
    # stand_down_resume() so the two never race inside one hook. See arm_from_handoff().
    armed_line = ""
    try:
        armed_line = arm_from_handoff(root, sdir, cfg, sid, v) or ""
    except Exception as exc:
        log(root, "AUTO-ARM-FAILED %r" % (exc,))
    mark = state_path(sdir, sid, "warned")
    try:
        with open(mark, encoding="utf-8") as f:
            if f.read().strip() == v["verdict"]:
                if armed_line or note or wk:
                    context_note(payload.get("hook_event_name", "UserPromptSubmit"),
                                 "[usage]" + note + armed_line + wk,
                                 systemMessage=(for_screen(note + armed_line) + ws).strip())
                return
    except OSError:
        pass
    try:
        os.makedirs(os.path.dirname(mark), exist_ok=True)
        with open(mark, "w", encoding="utf-8") as f:
            f.write(v["verdict"])
    except OSError:
        pass
    log(root, "USAGE(%s) pct=%s%s" % ((v["verdict"],) + driving_pct(v)))
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
    # ⛔ AND THE TWO VERDICTS DO NOT SHARE ONE WORDING. Until 0.60.1 this was ONE format
    # string fed `v["verdict"]`, so a PACE session was ordered, in capitals, to announce a
    # wind-down and to name "what you are dropping" - the opposite of the ruling of
    # 2026-09-17 (PACE = start no new batch; STOP = wind down), and louder than the skill
    # prose it contradicted. Measured twice that day: sessions stopped early because the
    # hook's capitals outrank a skill's paragraph. Fix the LINE, not the text around it.
    # ⭐ ONE `ack_line` VARIABLE FEEDS BOTH FIELDS. The screen must expect exactly what the
    # transcript is ordered to print; two strings that merely agree today drift apart, and
    # that drift is unreadable from a chair - the person waits for a line nothing demands.
    window, pct = driving_pct(v)
    if v["verdict"] == "STOP":
        ack_line = "`STOP at %s%d%% - winding down`" % (window, pct)
        ack_tail = ("Then say in one sentence what you are finishing and what you are "
                    "dropping. If you will NOT wind down, print that line with `- NOT "
                    "winding down` instead and say why.")
        seen_why = "Sub-task dispatch is now REFUSED until the window resets."
    else:
        # ⚠ NO "WINDING DOWN" ANYWHERE IN THIS BRANCH, escape hatch included - the selftest
        # asserts its absence, and an escape phrase carrying the words would satisfy the
        # assertion while putting them back on the screen.
        ack_line = "`PACE at %s%d%% - no new batch`" % (window, pct)
        # ⚠ AND "BATCH" IS BOUND TO "WAVE" HERE, on purpose. `dispatch-protocol` gives batch a
        # narrower technical sense - an owner-approved CONCURRENT group - so a session about to
        # start one more ordinary sequential sub-task could read `no new batch` as not applying
        # to it, which is the same early-stop dressed as compliance.
        ack_tail = ("Then say in one sentence what is in flight that you will finish. ⛔ At "
                    "PACE you drop NOTHING and you hand nothing back: carry on with the work "
                    "already started. ⚠ A new batch here means a new dispatch wave or a new "
                    "heavy block - sequential ones included, not only an owner-approved "
                    "concurrent group. If you WILL start one anyway, print that line with "
                    "`- starting a new batch anyway` instead and say why.")
        seen_why = "Dispatch is still allowed; do not start a new wave."
    ack = (" ⛔ FIRST, IN YOUR NEXT MESSAGE, PRINT EXACTLY THIS LINE AND NOTHING BEFORE IT: "
           "%s. %s" % (ack_line, ack_tail))
    # ⭐ AND THE SAME FACT ON THE USER'S SCREEN, through the one channel a model cannot
    # swallow. The person then holds both halves: the brake fired (this line, guaranteed) and
    # whether the agent answered for it (the line above, in the transcript).
    seen = ("dispatch-guard: usage %s at %s%d%%. %s Expect the agent to acknowledge with %s; "
            "if that line does not appear, it did not act on it."
            % (v["verdict"], window, pct, seen_why, ack_line))
    context_note(payload.get("hook_event_name", "UserPromptSubmit"),
                 "[usage] " + v["text"] + extra + ack + note + armed_line + wk,
                 systemMessage=seen + " " + for_screen(note + armed_line) + ws)


def _wake_hint(v, sdir=None):
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
    but a short wait never reaches here: a STOP that is genuinely near its reset is RELAXED to
    GO by the near-reset projection (usage._relax), so a refusal that gets this far is one the
    projection did NOT relax - the window is either far from reset or projected to hit the cap,
    and in both the wait is far longer than a sleep can cover. A first version branched on the
    sleep case and the branch was unreachable by construction; measured, not reasoned.

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
    # ⭐ 0.68: the exact cron, before the OS alarm, and the check-first wake prompt (ADR
    # 20261001-085000 D1/D3) - "about N minutes out" left the minute, and the stop rule, to chance.
    w = wake_time(sdir, v) if sdir else None
    if w:
        when = "with cron \"%s\" (%s)" % (w[1], time.strftime("%m-%d %H:%M", time.localtime(w[0])))
    return (" ⭐ (A) IF THIS SESSION WILL STAY OPEN, this is the better route because it keeps "
            "all your context: schedule a one-shot wake %s (CronCreate via ToolSearch "
            "\"select:CronCreate\", recurring:false) with the prompt \"%s\", and end the turn. "
            "⚠ A background sleep cannot substitute: the harness caps a command at ten minutes, "
            "which never reaches the reset from here." % (when, wake_prompt()))


def on_pre_agent(payload, root, sdir, cfg, wind=None):
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
            # ⛔ ARM HERE TOO, BECAUSE THIS BRANCH RETURNS. The brake refuses first, so the
            # auto-arm further down is unreachable at STOP - which is the moment it matters
            # most. Measured by line order: the usage refusal returns before the plan check
            # ever resolves a task folder. ⇒ Resolve it here and arm, then refuse.
            # ⚠ It is a no-op unless there is a handoff worth waking up for; the refusal text
            # below already tells the agent to write one when there is not.
            try:
                maybe_auto_arm(root, sdir, cfg,
                               plan_for(root, cfg, tool_input.get("prompt") or "")[1],
                               started, sid, session_cwd(sdir, sid))
            except Exception as exc:
                log(root, "AUTO-ARM-FAILED %r" % (exc,))
            log(root, "DENY(usage-stop pct=%s%s) %s" % (driving_pct(v) + (desc,)))
            deny(event, "dispatch gate: %s Dispatching a sub-task is the most expensive "
                        "thing you can do right now, so it is refused until the window "
                        "resets. Finish and save the current step, then pick a resume:%s"
                        " ⭐ (B) ALWAYS, as the backup: write "
                        "%s/<task>/HANDOFF.md so it stands completely alone, then run "
                        "`%s --arm --task <task>` - that registers a one-shot OS task that "
                        "wakes this window after the reset when it can (0.69; a closed window "
                        "or one it cannot reach is told to the next session - nothing runs in "
                        "the background). Then end the turn."
                 % (v["text"], _wake_hint(v, sdir), cfg["task_root"],
                    runnable("resume.py")),
                 # ⭐ ON THE SCREEN TOO. This is the strongest thing the plugin ever does -
                 # a tool call refused outright - and until now a person could not tell it
                 # from the agent simply choosing something else. A refusal nobody sees is
                 # indistinguishable from a brake that was never installed.
                 systemMessage=("dispatch-guard: sub-task dispatch REFUSED - usage %s at "
                                "%s%d%%. Nothing was dispatched. The agent has been told to "
                                "save the current step and arm a resume."
                                % ((v["verdict"],) + driving_pct(v))))
            return
        if v.get("relaxed_stop") and cfg["brake_on_usage"]:
            # ⭐ THE NET ZONE, THE OWNER'S STRICT 甲. A STOP was relaxed so the MAIN session
            # keeps working - but a NEW sub-agent dispatch is the most expensive thing it can
            # do and is NOT covered by the armed resume, so it is refused here. The main
            # session's own sequential work never reaches this dispatch hook, so it is not
            # blocked. ⚠ Arm first, like the STOP branch, because this returns before the later
            # auto-arm.
            try:
                maybe_auto_arm(root, sdir, cfg,
                               plan_for(root, cfg, tool_input.get("prompt") or "")[1],
                               started, sid, session_cwd(sdir, sid))
            except Exception as exc:
                log(root, "AUTO-ARM-FAILED %r" % (exc,))
            log(root, "DENY(usage-net pct=%s%s) %s" % (driving_pct(v) + (desc,)))
            deny(event, "dispatch gate: %s ⛔ You are in the NET zone - a STOP was relaxed "
                        "because the window resets soon and the budget survives. Keep doing "
                        "your OWN work, but dispatching a NEW sub-agent is refused: it can burn "
                        "the budget the relaxation is counting on, and a resume does "
                        "not cover an in-flight sub-agent. Rewrite HANDOFF.md and continue "
                        "yourself." % v["text"],
                 systemMessage=("dispatch-guard: sub-task dispatch REFUSED - NET zone (a STOP "
                                "relaxed near the reset). Nothing was dispatched; the main "
                                "session keeps working. %s"
                                % safe_resume_line(sdir, sid, cfg)))
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

    # ⛔ AFTER the plan check, because that is what resolves `folder`, and before the slot
    # claim, because a refused dispatch must not consume one.
    try:
        h = handoff_refusal(root, sdir, cfg, folder, started, log_to=root)
    except Exception as exc:
        # ⚠ Fail OPEN and say so. A precondition that crashes must not become a gate nobody
        # can pass; the log line is what stops "no refusals" reading as "all clear".
        log(root, "HANDOFF-CHECK-FAILED %r" % (exc,))
        h = None
    if h:
        deny(event, h)
        return

    # ⭐ AFTER the handoff check, so it only ever arms for a handoff that would be usable,
    # and BEFORE the dispatch proceeds, so the arming happens even if this is the last
    # dispatch the window allows. ⚠ Forked and never awaited - see maybe_auto_arm().
    try:
        maybe_auto_arm(root, sdir, cfg, folder, started, sid, session_cwd(sdir, sid))
    except Exception as exc:
        log(root, "AUTO-ARM-FAILED %r" % (exc,))

    # ⭐ WHICH FILES THIS PROMPT DEMANDS, AND WHETHER THIS TYPE CAN MAKE THEM. Advisory
    # only - nothing below refuses. ⚠ Computed BEFORE claim_slot because the answer is
    # stashed in the slot for the PostToolUse half to read back.
    wants, warn = [], None
    if cfg.get("guard_agent_report_file", DEFAULTS["guard_agent_report_file"]):
        try:
            stype = tool_input.get("subagent_type")
            wants, verbs = demanded_files(root, cfg, tool_input.get("prompt") or "", folder)
            if wants and agent_can_make_files(root, stype) is False:
                warn = ("dispatch-guard: subagent_type %r is read-only, but this prompt "
                        "tells the agent to CREATE %s. It cannot, and the failure is "
                        "SILENT - a normal-looking summary still comes back while the "
                        "report is lost. Dispatch general-purpose or claude instead, or "
                        "drop the file requirement from the prompt. (Measured 2026-08-31: "
                        "an Explore reviewer's verification table and five findings were "
                        "lost exactly this way.)" % (stype, "; ".join(wants)))
                log(root, "AGENT-TYPE-WARN(%s wants=%d) %s" % (stype, len(wants), desc))
            else:
                # ⛔ `verbs` IS IN THE LINE ON PURPOSE. wants=0 with verbs=0 means the prompt
                # demanded nothing; wants=0 with verbs>0 means it demanded something and no
                # path was recognised - a coverage gap in this guard, not a clean dispatch.
                # One log line for both would hide the second behind the first.
                log(root, "AGENT-TYPE-OK(%s wants=%d verbs=%d writes=%r)"
                    % (stype, len(wants), verbs, agent_can_make_files(root, stype)))
        except Exception as exc:
            # ⚠ FAIL OPEN AND SAY SO. An advisory check that crashes must not stop a
            # dispatch, and the log line is what keeps "no warning" from reading as
            # "checked and clean".
            log(root, "AGENT-TYPE-CHECK-FAILED %r" % (exc,))
            wants, warn = [], None
    else:
        # ⛔ AN OFF SWITCH THAT LEAVES NO TRACE is the same defect as an absent denial that
        # proves nothing: "no warning appeared" and "this guard never ran" must not look
        # the same in the log.
        log(root, "AGENT-TYPE-DISABLED")

    slots = approved_slots(root, cfg, started, folder, log_to=root)
    if not claim_slot(root, sdir, cfg, sid, slots, payload.get("tool_use_id"),
                      folder, desc, wants=wants):
        log(root, "DENY(slots-full n=%d) %s" % (slots, desc))
        deny(event, "dispatch gate: %d sub-task(s) are already in flight, which is all "
                    "the owner approved. Dispatch one at a time - that needs no "
                    "permission. To raise the limit, ask the owner; when they answer with "
                    "a count, record it as %s/<task>/PARALLEL-APPROVED containing that "
                    "number in the form 'parallel N'.\n\n%s\n\n"
                    "⚠ If one of those dispatches DIED without returning - an API error, "
                    "an interrupt, a killed process - it still holds its slot, and this "
                    "refusal looks exactly like the rule working. It is not stuck: the "
                    "gate reclaims that slot by itself at the time shown above. Wait for "
                    "that minute and dispatch again, or do the work in this session "
                    "meanwhile. ⛔ Do NOT delete a slot file to get past this refusal. It "
                    "is this plugin's enforcement state, deleting a LIVE one hands the "
                    "same slot to two dispatches, and the wait it saves is minutes."
                    % (slots, cfg["task_root"],
                       # ⚠ A BLANK NOTE STILL SAYS SOMETHING. Without this the text above
                       # reads "at the time shown above" over three empty lines.
                       safe_held_slots_note(root, sdir, cfg, sid, slots)
                       or ("  (the holder could not be listed - the gate log has a "
                           "HELD-NOTE-FAILED line saying why. The slot still clears itself "
                           "%s minutes after it was claimed.)" % (cfg["slot_ttl_min"],))))
        return

    log(root, "ALLOW(slots=%d) %s" % (slots, desc))
    # ⚠ The wind-down rides in the same channel as the read-only-type warning: both are
    # about the DISPATCH and both are for the dispatcher, not for the sub-agent.
    allow_prepended(event, tool_input, cfg, note,
                    warn="\n\n".join([t for t in (warn, wind) if t]) or None)


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
    # ⭐ THIS SESSION'S PREVIOUS HOOK, read BEFORE the heartbeat rewrites it: a prompt after a long
    # gap is a wake, and the cowork check-in reminder needs to know (ADR 20261001-085000 D8).
    try:
        payload["_dg_prev_alive"] = os.path.getmtime(state_path(sdir, sid, "alive"))
    except (OSError, TypeError, ValueError):
        pass
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
    # ⛔ BEFORE the `tool != "Agent"` fall-through below: a Stop payload carries no tool name.
    if event == "Stop":
        return on_stop(payload, root, sdir, cfg)
    # ⭐ WHO WROTE WHICH HANDOFF.md - recorded here, before the Bash branch below returns, so a
    # Write, an Edit and a Bash redirect are all seen. Never decides anything; never returns.
    post_note = ""
    if event == "PostToolUse":
        try:
            if (note_handoff_write(sdir, cfg, sid, tool, payload.get("tool_input") or {})
                    and not payload.get("agent_id")):
                # ⭐ at STOP / in the net zone a fresh HANDOFF.md is armed the moment it lands.
                # ⚠ Not from a SUB-AGENT: its payload carries the PARENT's session id, so its
                # handoff would arm the parent's resume for the sub-agent's folder (review B N1).
                # ⭐ 0.68: what it says is CARRIED into this event's one print below (`wind`) -
                # never printed here: a return here would skip after_command / the slot release.
                post_note = arm_on_handoff_write(root, sdir, cfg, sid) or ""
        except Exception as exc:
            log(root, "HANDOFF-NOTE-FAILED %r" % (exc,))

    # ⛔ A TOOL CALL THAT FAILS FIRES PostToolUseFailure, AND PostToolUse NEVER RUNS. So
    # until this branch existed, EVERY failed dispatch kept its slot for the full
    # slot_ttl_min - not only the API-error case that was reported. Measured 2026-09-02
    # against Claude Code 2.1.251, one failing Bash call through a probe hook: PreToolUse
    # and PostToolUseFailure both arrived, carrying the SAME tool_use_id, and PostToolUse
    # did not arrive at all.
    # ⚠ IT RETURNS SILENTLY. Releasing the slot is all this event is used for; a hook that
    # prints on an event whose output contract is not needed here can only cost.
    if event == "PostToolUseFailure":
        if tool == "Agent":
            err = " ".join(str(payload.get("error") or "no error text").split())[:200]
            result = release_slot(sdir, cfg, sid, payload.get("tool_use_id"))
            if isinstance(result, dict):
                log(root, "RELEASE(dispatch failed) %s" % err)
                record_progress(root, cfg, result.get("folder"), result.get("desc"),
                                result.get("at"), "FAILED: %s" % err)
            else:
                # ⛔ SAID OUT LOUD. "No slot was held" and "the release did not run" must
                # not look the same in the log - that is the whole shape of this defect.
                log(root, "RELEASE-MISS(dispatch failed, no slot held) %s" % err)
        return

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
    # ⭐ COMPUTED ONCE, FOR EVERY TOOL, AND CARRIED INTO WHATEVER THIS EVENT ALREADY EMITS.
    # ⛔ PreToolUse and not PostToolUse: PostToolUse does not fire for a FAILED tool call -
    # the harness routes those elsewhere - so a session looping on failures would never hear
    # it. ⚠ It never carries a permission decision; see context_note().
    wind = None
    post_screen = None
    if event == "PreToolUse":
        try:
            wind = wind_down_note(payload, root, sdir, cfg)
        except Exception as exc:
            log(root, "WIND-DOWN-FAILED %r" % (exc,))
    elif post_note:
        # ⭐ the HANDOFF-write arm's ARMED line (0.68, ADR 20261001-085000 D2): to the model through
        # `wind`, and to the person's screen - composed into this event's ONE print.
        wind, post_screen = str(post_note).strip(), for_screen(post_note)

    if tool in cmd_guards.SHELL_TOOLS and event in ("PreToolUse", "PostToolUse"):
        try:
            ctx = guard_ctx(root, sdir, sid, cfg)
            if event == "PreToolUse":
                v = cmd_guards.check(payload, ctx)
                if v and v["kind"] == cmd_guards.DENY:
                    # ⚠ A refusal already tells the agent to stop; adding the wind-down to it
                    # would be two instructions in one breath. The refusal wins.
                    return deny(event, v["model"], systemMessage=v["screen"])
                if v:
                    # A warning: text for the model, a line for the person, and NO permission
                    # decision - see context_note() for why "allow" would be a free pass.
                    return emit_with(event, v["model"], wind, systemMessage=v["screen"])
                return emit_with(event, None, wind)
            else:
                text = cmd_guards.after_command(payload, ctx)
                if text or wind:
                    return emit_with(event, text, wind, systemMessage=post_screen)
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

    # ⭐ THE FILE-TOOL GUARDS (0.63.0): a Write/Edit that rewrites a file declaring itself
    # append-only, and the first write of a session that shares this tree with a live peer.
    # ⛔ WRAPPED like the shell-tool branch above, and for the same reason: a pre-branch
    # exception makes a hook print nothing, and a hook that prints nothing has APPROVED the
    # call. `wind` was computed once above; it is carried, never recomputed.
    if event == "PreToolUse" and tool in cmd_guards.FILE_TOOLS:
        try:
            v = cmd_guards.check_file_tool(payload, guard_ctx(root, sdir, sid, cfg))
            if v and v["kind"] == cmd_guards.DENY:
                return deny(event, v["model"], systemMessage=v["screen"])
            if v:
                return emit_with(event, v["model"], wind, systemMessage=v["screen"])
        except Exception as exc:
            log(root, "FILE-GUARDS-FAILED %r" % (exc,))
        return emit_with(event, None, wind)

    if tool != "Agent":
        # ⛔ THIS RETURN IS WHERE THE INCIDENT WENT. Every Read and every Write of that
        # session arrived here and left again. The gate saw all of them and said nothing.
        return emit_with(event, None, wind, systemMessage=post_screen)
    if event == "PreToolUse":
        # ⚠ PASSED IN, never recomputed here: wind_down_note() consumes a once-per-level
        # marker, so asking twice would answer once and swallow the note.
        return on_pre_agent(payload, root, sdir, cfg, wind)
    if event == "PostToolUse":
        result = release_slot(sdir, cfg, sid, payload.get("tool_use_id"))
        if isinstance(result, dict):
            log(root, "RELEASE")
            record_progress(root, cfg, result.get("folder"), result.get("desc"),
                            result.get("at"), payload.get("tool_response"))
            # ⭐ THE HALF THAT ACTUALLY HOLDS. It needs no knowledge of any agent's tool
            # list, so it cannot go stale, and it catches the case the PreToolUse warning
            # never can: an agent that COULD write and simply did not. ⚠ The failing agent
            # on 2026-08-31 did say in its first line that it could not write, and it was
            # still missed - because the summary looked normal. A missing file does not.
            try:
                missing = [p for p in (result.get("wants") or [])
                           if isinstance(p, str) and not os.path.exists(p)]
                if missing:
                    log(root, "AGENT-FILE-MISSING %s" % "; ".join(missing))
                    text = ("dispatch-guard: the sub-agent returned, but %s was never "
                            "created. Its prompt required that file. Treat the summary as "
                            "UNVERIFIED: either the agent could not write (check its "
                            "subagent_type's tool list) or it did not. If it returned "
                            "content that belonged on disk, transcribe it verbatim into "
                            "the task folder NOW - that content lives in a turn you will "
                            "not be able to reach again - and say in the file that it was "
                            "transcribed and what is missing."
                            % "; ".join(missing))
                    return context_note(
                        event, text,
                        systemMessage=("dispatch-guard: sub-agent returned without writing "
                                       "%s. Its report may be lost." % missing[0]))
                if result.get("wants"):
                    log(root, "AGENT-FILE-OK n=%d" % len(result["wants"]))
            except Exception as exc:
                log(root, "AGENT-FILE-CHECK-FAILED %r" % (exc,))
        elif result is not False:
            log(root, "RELEASE-FAILED %s" % result)


def selftest():
    """`dispatch_gate.py --selftest` - asserts where task folders resolve to and that the
    root is created. Touches no real repository: it builds its own temp tree.

    ⛔ Worth a check rather than a comment because a wrong answer here is SILENT. A gate
    that resolves task_root to the wrong folder finds no fresh plan, refuses every dispatch,
    and the refusal names a path without saying it looked in the wrong one.

    ⛔ AND IT MUST NOT WRITE INTO THE REAL STATE DIRECTORY. log() sends every line to
    `usage.state_dir()` as well as to the repository copy, and this function runs the real
    decision paths - so without the redirection below, `dispatch_gate.py --selftest` files
    45 `DENY(ultracode)` lines into the owner's own log every time the suite runs. Measured
    2026-09-01, from the owner noticing exactly that: a log full of refusals for a mode no
    session had switched on. ⚠ A check that pollutes the evidence it exists to protect is
    worse than no check.
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
        # ⛔ A NON-NUMBER IN A NUMERIC KEY IS THE DEFAULT, NEVER A TypeError LATER. Measured
        # 2026-09-02: "slot_ttl_min": "abc" crashed claim_slot() inside the refusal path, the
        # hook printed nothing, and the dispatch was ALLOWED. Strings that parse are kept;
        # bool, null, lists, zero and negatives fall back; and the log says so.
        sdir3 = tempfile.mkdtemp()
        with open(os.path.join(sdir3, "config.json"), "w", encoding="utf-8") as fh:
            json.dump({"slot_ttl_min": "abc", "max_slots": "4", "approval_ttl_min": None,
                       "dispatch": {"max_model_price": "opus"}}, fh)
        cfg3 = gate_config(root2, sdir3)
        assert cfg3["slot_ttl_min"] == DEFAULTS["slot_ttl_min"], cfg3["slot_ttl_min"]
        assert cfg3["max_slots"] == 4 and type(cfg3["max_slots"]) is int, cfg3["max_slots"]
        assert cfg3["approval_ttl_min"] == DEFAULTS["approval_ttl_min"], cfg3
        # ⚠ and max_model_price is NOT coerced: the name form is a documented input there.
        assert cfg3["max_model_price"] == "opus", cfg3["max_model_price"]
        for k in NUMERIC_KEYS:
            assert cfg3[k] * 60 > 0                    # the arithmetic the gate does on them
        list(range(cfg3["max_slots"]))                 # release_slot() iterates it: int only
        with open(os.path.join(root2, ".claude", "dispatch_gate.log"), encoding="utf-8") as fh:
            said = fh.read()
        assert "CONFIG-IGNORED(slot_ttl_min='abc')" in said, said
        assert "CONFIG-IGNORED(max_slots=" not in said, "a parseable string was reported"
        for bad in (True, False, -5, 0, [30], {"a": 1}, float("nan"), "", "1e", None,
                    "inf", "1e999", float("inf"), "-inf", "nan"):
            assert _positive_number(bad) is None, bad
        list(range(_positive_number("1e2")))           # 100: a parsed float is range()-safe
        assert _positive_number("60") == 60 and type(_positive_number("60")) is int
        assert _positive_number(2.5) == 2.5 and _positive_number(7) == 7
        # ⛔ max_slots must be WHOLE: 1.5 is a positive number and range(1.5) is a TypeError
        # in both the claim and the release path. A fraction there is the default, and said.
        for frac in (1.5, "1.5", 0.5):
            with open(os.path.join(sdir3, "config.json"), "w", encoding="utf-8") as fh:
                json.dump({"max_slots": frac}, fh)
            cfg4 = gate_config(root2, sdir3)
            assert cfg4["max_slots"] == DEFAULTS["max_slots"], (frac, cfg4["max_slots"])
            list(range(cfg4["max_slots"]))
        with open(os.path.join(root2, ".claude", "dispatch_gate.log"), encoding="utf-8") as fh:
            assert "CONFIG-IGNORED(max_slots=1.5)" in fh.read()
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
        for name, back, due in (("token_usage.json", 10, False),   # data still fresh
                                ("token_usage.json", 300, True),   # data stale, nothing started
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
        # ⚠ The published page names it "Claude Opus 4", so the ID is `claude-opus-4` and it
        # matches `claude-opus-4-0` as a prefix. Still $15, which is the number that matters.
        assert model_price("claude-opus-4-0") == ("claude-opus-4", 15, True), \
            model_price("claude-opus-4-0")
        # ...and an unseen version in a known family resolves, but is marked as an assumption.
        assert model_price("claude-opus-6") == ("claude-opus-5", 5, False)
        # ⭐ THE NUMBERS COME FROM THE FILE. Pinned against model_pricing directly, so a table
        # that silently stopped loading cannot leave these assertions passing on stale
        # constants somebody re-typed into this module.
        _doc, _where = price_doc()
        assert _doc and _doc.get("source"), "no price table loaded: %s" % (_where,)
        assert price_of("claude-opus-5") == _doc["models"]["claude-opus-5"]["input"]
        # ⚠ The one row the old hand-typed table had WRONG. It said $1; the page says $0.80.
        assert price_of("claude-3-5-haiku") == 0.8, price_of("claude-3-5-haiku")
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
        # ⛔ MUTATION CHECK ON THE FAIL-OPEN THAT MATTERS MOST. Take the table away and the
        # ceiling must stop refusing rather than refuse everything: with no prices every model
        # reads as unrecognised, and "unrecognised is refused" would brick every dispatch that
        # names a model. A cost guard that bricks the work is a cost guard people uninstall.
        global _DOC
        _keep = _DOC
        try:
            _DOC = (None, "selftest: table removed")
            assert not prices(), "the table did not actually go away"
            assert model_refusal({"model": "fable"}, ceil) is None, \
                "no table must fail OPEN, not refuse everything"
            assert "NOT being enforced" in model_note(ceil, tempfile.gettempdir())
            head = prepend_head({"task_root": "t", "plan_glob": "p", "protocol_doc": "d",
                                 "max_model_price": 5})
            assert "$1" not in head and "$10" not in head, \
                "with no table the prompt must not invent prices: %s" % head[:600]
        finally:
            _DOC = _keep
        assert prices(), "the table did not come back"

        # ⛔ THE WATCHER TASK, at VS Code's USER level. Isolated by pointing
        # vscode_user_dirs() at a temp directory: an earlier version of this block wrote to
        # the real %APPDATA%/Code/User/tasks.json while "testing", which is the same defect
        # it is here to prevent somebody else from shipping.
        sys.path.insert(0, os.path.dirname(HERE))
        import install as _install
        vsdir = tempfile.mkdtemp()
        _saved_dirs, _install.vscode_user_dirs = _install.vscode_user_dirs, lambda: [vsdir]
        _saved_grant, _install.allow_automatic_tasks = _install.allow_automatic_tasks, lambda: None
        # ⛔ AND write_shim(), WHICH WRITES INTO THE REAL ~/.claude/dispatch-guard. It is not
        # parameterised by a state directory - install.py owns exactly one - so the only
        # isolation available is to switch it off. Measured: without this line, running this
        # selftest from a development checkout repointed the LIVE statusline at the checkout.
        # The same defect the comment above describes, one function further along.
        _saved_shim, _install.write_shim = _install.write_shim, lambda: None
        _real_state = os.path.join(os.path.expanduser("~"), ".claude", "dispatch-guard")
        _shim_before = shim.recorded(_real_state)
        try:
            up = os.path.join(vsdir, "tasks.json")
            assert not _install.vscode_user_task_current(), "an empty dir cannot be current"
            note, seen = maybe_install_vscode_task(tempfile.mkdtemp(), dict(DEFAULTS))
            assert note and "USER tasks" in note, note
            # ⛔ AND A LINE FOR THE PERSON, not only for the model. With no usage left there
            # is no model turn at all, and installing on an empty budget is the case that
            # has to work - so a note that only reaches the model does not exist.
            # ⛔ AND IT NAMES THE ROUTE THAT NEEDS NO RELOAD. "Reopen the folder" was the only
            # instruction here, and it asks somebody to shut down what they are doing for a
            # terminal the command palette starts in place.
            assert seen and "Tasks: Run Task" in seen, seen
            assert _install.vscode_user_task_current(), "what it wrote does not read back"
            with open(up, encoding="utf-8") as fh:
                written = fh.read()
            assert _install.TASK_LABEL in written
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
            # ⚠ THE SHAPE OF THIS FIXTURE CHANGED WITH THE SHIM, and the old one stopped
            # meaning anything. It used to insert /OLDVERSION/ into a path containing
            # "/hooks/" - but the command names the shim now, which has no "/hooks/" in it,
            # so the replace matched nothing and the entry read as current. ⇒ It plants what
            # an OLDER VERSION would have written: a literal path into the plugin cache.
            book["tasks"][0]["command"] = (
                "C:/Users/x/.claude/plugins/cache/dispatch-guard/dispatch-guard/0.0.1"
                "/hooks/OLDVERSION_run.cmd")
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
            assert "my build" in labels and _install.TASK_LABEL in labels, labels

            # ⛔ A TASK UNDER AN OLD LABEL IS REPLACED, NOT JOINED. Both carry
            # `runOn: folderOpen`, so leaving the old one opens TWO watcher terminals on
            # every folder open - and nothing that removes tasks by the current label can
            # ever reach the old one again. Mutation-checked: drop LEGACY_TASK_LABELS from
            # ours() and this assertion fails with both labels present.
            with open(up, "w", encoding="utf-8") as fh:
                json.dump({"version": "2.0.0",
                           "tasks": [{"label": _install.LEGACY_TASK_LABELS[0]}]}, fh)
            assert not _install.vscode_user_task_current(), "an old label read as current"
            _install.vscode_user_task()
            with open(up, encoding="utf-8") as fh:
                labels = [t["label"] for t in json.load(fh)["tasks"]]
            assert labels == [_install.TASK_LABEL], labels

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

            # ⛔ JSONC IS THE ORDINARY SHAPE OF A USER settings.json, and reading it with
            # json.load reported every setting in it as unset. That bit the one line people
            # consult when the terminal did not open: allow_automatic_tasks() writes a `//`
            # comment as it grants, so from the moment this plugin allowed automatic tasks,
            # `--status` called them forbidden on that machine, for ever.
            # ⚠ Built by join, no escapes - see the note on the jsonc fixture above.
            sfile = os.path.join(vsdir, "settings.json")
            on = chr(10).join(["{", "  // added by dispatch-guard",
                               '  "task.allowAutomaticTasks": "on",',
                               '  "editor.fontSize": 13', "}"])
            with open(sfile, "w", encoding="utf-8") as fh:
                fh.write(on)
            assert _install.load(sfile, {}) == {}, "the fixture stopped being JSONC"
            assert _install.automatic_tasks_value(sfile) == "on", "JSONC read as unset"
            # ⛔ THE VALUE, NOT THE KEY. A substring test calls both of these allowed: "off",
            # and a line somebody commented OUT to withhold the permission on purpose.
            with open(sfile, "w", encoding="utf-8") as fh:
                fh.write(on.replace('"on"', '"off"'))
            assert _install.automatic_tasks_value(sfile) == "off", "off read as allowed"
            with open(sfile, "w", encoding="utf-8") as fh:
                fh.write(on.replace('  "task.', '  // "task.'))
            assert _install.automatic_tasks_value(sfile) is None, "a commented-out line counted"
            os.remove(sfile)
            assert _install.automatic_tasks_value(sfile) is None, "a missing file was not None"
        finally:
            _install.vscode_user_dirs = _saved_dirs
            _install.allow_automatic_tasks = _saved_grant
            _install.write_shim = _saved_shim
        # ⛔ PROVE IT. A patch that stops working is silent, and what it prevents here is a
        # selftest reaching out of its sandbox into the machine's live configuration.
        assert shim.recorded(_real_state) == _shim_before, \
            "the selftest changed the real state directory's shim"
        shutil.rmtree(vsdir, ignore_errors=True)
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(sdir, ignore_errors=True)
    # ⛔ THE BRAKE MUST REACH THE PERSON, not only the model. Every instruction this plugin
    # sends through additionalContext is invisible from a chair, and whether it was obeyed is
    # unknowable - measured three times today with three different messages. systemMessage is
    # the one channel a model cannot swallow, so the two loud events must carry one.
    import inspect
    # ⛔ NOBODY READS THE FIVE-HOUR FIGURE DIRECTLY AGAIN. This is the root-cause pin, and it
    # exists because the first fix was incomplete: 0.60.2 corrected the acknowledgement line
    # and left four sites taking `v["pct"]` whatever drove the verdict - including the
    # `systemMessage` of the dispatch REFUSAL, the strongest thing this plugin says. A
    # per-message check would have to be written once per message and would miss the fifth.
    assert driving_pct({"driver": "7d", "pct": 3, "pct_7d": 98.6}) == ("7d ", 99), \
        driving_pct({"driver": "7d", "pct": 3, "pct_7d": 98.6})
    assert driving_pct({"driver": "5h", "pct": 90.4, "pct_7d": 10}) == ("", 90), \
        driving_pct({"driver": "5h", "pct": 90.4, "pct_7d": 10})
    assert driving_pct({}) == ("", 0), driving_pct({})      # no driver, no crash
    for _fn in (on_user_prompt, on_pre_agent):
        assert 'v.get("pct") or 0' not in inspect.getsource(_fn), \
            ("%s takes the FIVE-HOUR percentage directly - it must use driving_pct(v), or it "
             "prints 3%% while the WEEK is at 99%%" % _fn.__name__)
    src = inspect.getsource(on_user_prompt)
    assert "systemMessage=" in src, "the wind-down no longer speaks to the user"
    assert "winding down" in src, "the acknowledgement line was dropped"
    # ⛔ AND PACE AND STOP MUST NOT SHARE ONE WORDING - DRIVEN, NOT READ. The assertion above
    # is satisfied by the STOP branch alone, so on its own it passes while a PACE session is
    # being told to wind down again; the defect WAS one format string serving two verdicts, so
    # the check has to see the two OUTPUTS. ⚠ Both directions per verdict, because an absence
    # test alone cannot tell a fixed branch from a branch that never ran - see the positive
    # control below, which is what actually guards the routes that emit nothing.
    import contextlib as _cl3, io as _io3
    def _prompt_out(pct5, sid, pct7=10):
        """Run on_user_prompt() on fabricated percentages; return (verdict, json)."""
        _sd, _rt = tempfile.mkdtemp(), tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(_sd, "state"), exist_ok=True)
            _now = time.time()
            # ⚠ THE RESET TWO HOURS OUT, deliberately: usage._relax turns a PACE or a STOP
            # near its reset back into GO, and on_user_prompt() then returns before it builds
            # a single word. `pct7` defaults LOW so the FIVE-HOUR window drives; raise it to
            # drive from the WEEK instead (soft_pct_7d 95, hard_pct_7d 97 - not 75/85).
            with open(os.path.join(_sd, "token_usage.json"), "w", encoding="utf-8") as fh:
                json.dump({"ts": int(_now * 1000),
                           "five_hour": {"used_percentage": pct5,
                                         "resets_at": int(_now + 2 * 3600)},
                           "seven_day": {"used_percentage": pct7,
                                         "resets_at": int(_now + 3 * 86400)}}, fh)
            _got = usage.verdict(_sd, usage.config(_sd))["verdict"]
            _buf = _io3.StringIO()
            with _cl3.redirect_stdout(_buf):
                on_user_prompt({"hook_event_name": "UserPromptSubmit",
                                "session_id": sid, "cwd": _rt}, _rt, _sd, dict(DEFAULTS))
            return _got, json.loads(_buf.getvalue())
        finally:
            shutil.rmtree(_sd, ignore_errors=True)
            shutil.rmtree(_rt, ignore_errors=True)
    # ⚠ A FRESH STATE DIRECTORY EACH TIME (_prompt_out makes one): the `warned` mark is
    # once-per-level-per-session, so a reused sdir returns early - and then `on_user_prompt()`
    # prints nothing, `json.loads("")` raises, and the failure names JSON instead of the
    # wording. Distinct session ids would separate the marks too; the fresh directory also
    # keeps `usage.config()` off this machine's real thresholds.
    # ⭐ THE WHOLE LINE, NOT THE PHRASE. Asserting `PACE at 78% - no new batch` pins the
    # verdict word and the percentage as well, and asserting the SAME string in both fields is
    # the only thing that pins the headline claim - that the screen cannot come to expect a
    # line the transcript is not ordered to print.
    # ⛔ AND THE SEVEN-DAY ROWS, because `pct` is the FIVE-HOUR figure and the line used to
    # print it whatever drove the verdict - `STOP at 3%` beside a text saying the WEEK was
    # spent. The 7d rows are what pin the `7d ` label; the 5h rows are what pin that the
    # label does NOT appear when the five-hour window drives.
    # ⚠ THE PERCENTAGES COME FROM THE THRESHOLDS, NOT FROM TYPED NUMBERS. This table read
    # 78 for PACE and 90 for STOP, which are the OLD 75/85 bands plus a margin - so raising
    # the defaults to 80/90 turned the PACE row into a GO and the positive control fired,
    # reading as a regression in the hook. Measured 2026-09-18. Each row now sits a few
    # points INSIDE its band, computed, so a future threshold change carries the fixture.
    _s5, _h5 = usage.DEFAULTS["soft_pct_5h"], usage.DEFAULTS["hard_pct_5h"]
    _s7, _h7 = usage.DEFAULTS["soft_pct_7d"], usage.DEFAULTS["hard_pct_7d"]
    _pace5, _stop5 = _s5 + 2, _h5 + 5          # inside PACE, and well past STOP
    _pace7, _stop7 = _s7 + 1, _h7 + 2
    _seen = set()
    for _pct, _p7, _want, _line, _not in (
            (_pace5, 10, "PACE", "`PACE at %d%% - no new batch`" % _pace5, "winding down"),
            (_stop5, 10, "STOP", "`STOP at %d%% - winding down`" % _stop5, "no new batch"),
            (3, _pace7, "PACE", "`PACE at 7d %d%% - no new batch`" % _pace7, "winding down"),
            (3, _stop7, "STOP", "`STOP at 7d %d%% - winding down`" % _stop7, "no new batch"),):
        _got, _out = _prompt_out(_pct, "wd-%s-%d" % (_want, _p7), _p7)
        # positive control: the fixture really did read as the verdict under test
        assert _got == _want, \
            "5h %d%% / 7d %d%% read as %s, not %s" % (_pct, _p7, _got, _want)
        _seen.add(_got)
        _ctx = _out.get("hookSpecificOutput", {}).get("additionalContext", "")
        for _where, _text in (("additionalContext", _ctx),
                              ("systemMessage", _out.get("systemMessage", ""))):
            assert _line in _text, \
                "%s %s lost %r - both fields must carry the one acknowledgement line: %r" \
                % (_want, _where, _line, _text)
            assert _not not in _text, \
                "%s %s says %r - the two verdicts share one wording again: %r" \
                % (_want, _where, _not, _text)
            # ⛔ AND THE WIND-DOWN INSTRUCTIONS THEMSELVES STAY STOP-ONLY, IN BOTH FIELDS.
            # The acknowledgement LINE is only the label; a PACE tail rewritten to demand a
            # handoff and the end of the turn satisfies every assertion above while doing the
            # exact damage this fixes. ⚠ And the SCREEN field needs its own row: a first
            # version checked `additionalContext` alone, and round 2 measured `seen_why`
            # rewritten to order a handover on the user's screen passing the whole suite.
            # ⭐ The rule is not the same for the two fields. `additionalContext` carries the
            # orders, so a cue belongs there at STOP and nowhere else; `systemMessage` is the
            # person's one-line expectation note and issues no orders at all, so a cue in it
            # is wrong at EVERY verdict.
            for _cue in ("END THE TURN", "dropping"):
                _may = _want == "STOP" and _where == "additionalContext"
                assert (_cue in _text) is _may, \
                    "%s %s must%s carry %r: %r" \
                    % (_want, _where, "" if _may else " NOT", _cue, _text)
    # ⛔ AND BOTH ROWS MUST HAVE RUN. Nothing above notices a table that lost its PACE row -
    # delete it and every assertion here passes while the hook orders a PACE session to wind
    # down. An unchecked fixture list is the third silent route, beside usage._relax and the
    # `warned` mark.
    assert _seen == set(["PACE", "STOP"]), \
        "the wording check stopped driving both verdicts: %r" % (sorted(_seen),)
    src2 = inspect.getsource(on_pre_agent)
    assert "systemMessage=" in src2, "a refused dispatch no longer speaks to the user"
    # ⛔ AND A FULL-SLOTS REFUSAL MUST CARRY THE HOLDER AND ITS CLOCK. The function exists
    # and passes its own check even when nothing calls it; this is the wiring.
    assert "held_slots_note(" in src2, "the full-slots refusal names nothing again"
    # ⛔ AND THROUGH THE WRAPPER THAT CANNOT RAISE. A crash inside deny()'s argument list is
    # an ALLOW (see safe_held_slots_note); the bare function at this call site is the 0.56.1
    # fail-open, verbatim.
    assert "safe_held_slots_note(" in src2, \
        "the full-slots refusal calls held_slots_note() bare - a crash there allows the dispatch"
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

    # ⛔ THE SLOT HOLDS, THE SLOT CLEARS ITSELF, AND THE REFUSAL SAYS BOTH. A dispatch that
    # dies before its PostToolUse keeps its slot, and the only thing between that and a
    # session editing this plugin's enforcement state by hand is a refusal that names the
    # holder and the minute the clock runs out. Measured 2026-09-02: another machine lost a
    # dispatch to an API 529 and deleted the slot file for want of those two facts.
    with tempfile.TemporaryDirectory() as sd:
        cfg_s = dict(DEFAULTS)
        held = state_path(sd, "s1", "slot0")
        assert claim_slot(sd, sd, cfg_s, "s1", 1, "tool_A", "F", "round 1 review")
        assert not claim_slot(sd, sd, cfg_s, "s1", 1, "tool_B", "F", "round 2"), \
            "one slot was handed to two dispatches"
        note = held_slots_note(sd, cfg_s, "s1", 1)
        assert "round 1 review" in note, note
        assert re.search(r"reclaimed automatically at \d\d:\d\d", note), note
        # ⛔ AND THE CLOCK MUST ACTUALLY TICK. Age the slot past slot_ttl_min: the next claim
        # takes it. Without this the refusal promises a reclaim that never happens, which is
        # the promise that makes waiting reasonable.
        old = time.time() - (cfg_s["slot_ttl_min"] * 60 + 60)
        os.utime(held, (old, old))
        assert claim_slot(sd, sd, cfg_s, "s1", 1, "tool_C", "F", "after the wait"), \
            "a slot older than slot_ttl_min was never reclaimed"
        assert "after the wait" in held_slots_note(sd, cfg_s, "s1", 1)
        assert release_slot(sd, cfg_s, "s1", "tool_C"), "release_slot found no slot"
        assert held_slots_note(sd, cfg_s, "s1", 1) == "", "a released slot still reads held"
        # ⛔ THE NOTE MUST NOT BE ABLE TO TAKE THE REFUSAL DOWN WITH IT. slot_ttl_min large
        # enough that started + ttl leaves the range time.localtime() accepts: the bare
        # function raises OSError(22), and inside deny()'s argument list that is an ALLOW.
        # The wrapper returns "" and logs HELD-NOTE-FAILED instead. ⚠ The bare function is
        # asserted to raise on purpose: if a future Python stops raising here, this check
        # stops proving anything and must find a different failure to inject.
        assert claim_slot(sd, sd, cfg_s, "s1", 1, "tool_D", "F", "huge ttl")
        huge = dict(cfg_s, slot_ttl_min=1000000000)
        try:
            held_slots_note(sd, huge, "s1", 1)
            raise AssertionError("the bare note no longer raises on a huge slot_ttl_min - "
                                 "this check needs a new failure to inject")
        except OSError:
            pass
        os.makedirs(os.path.join(sd, "repo"))
        note = safe_held_slots_note(os.path.join(sd, "repo"), sd, huge, "s1", 1)
        assert note == "", "the guarded note returned %r instead of blank" % (note,)
        with open(os.path.join(sd, "repo", ".claude", "dispatch_gate.log"),
                  encoding="utf-8") as fh:
            assert "HELD-NOTE-FAILED" in fh.read(), "the note failed and nothing said so"
        assert release_slot(sd, cfg_s, "s1", "tool_D")

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
    filled = prepend_head({"task_root": "Memory/tasks", "plan_glob": "prompts*.md",
                           "protocol_doc": "PROTOCOL.md", "max_model_price": 5})
    # ⛔ THE MODEL RULE MUST REACH EVERY DEPTH TOO. A sub-agent that dispatches further never
    # read `dispatch-protocol`; this block is the only channel that binds it, and a rule an
    # agent meets only as a refusal is a rule it tries to route around.
    assert "CHOOSE THE MODEL BEFORE YOU DISPATCH" in filled, filled[:400]
    assert "$5 per million INPUT tokens" in filled, "the limit did not interpolate"
    assert "Memory/tasks/<task>/scratch/" in filled, filled[-600:]
    # ⛔ AND THE PRICES IN IT MUST BE THE FILE'S, NOT FOUR NUMBERS TYPED INTO THE TEMPLATE.
    # That is exactly the drift this change removed everywhere else; leaving it in the prompt
    # would have the gate refusing at one price while the prompt promised another.
    assert "haiku $%g" % price_of(dict(family_latest())["haiku"]) in filled, filled[:900]
    assert "opus $%g" % price_of(dict(family_latest())["opus"]) in filled, filled[:900]
    assert not re.search(r"haiku \$1, sonnet \$2, opus \$5, fable \$10", PREPEND), \
        "the price list is hard-coded in PREPEND again"

    # ⛔ THE NET ZONE. A relaxed STOP reads GO but carries relaxed_stop=True; the resume must
    # ARM and must NOT be stood down. Both guards key off relaxed_stop, never the word.
    assert arm_trigger({"verdict": "GO", "relaxed_stop": True}) is True, "net zone must arm"
    assert arm_trigger({"verdict": "GO"}) is False, "a plain GO must not arm"
    # ⭐ 0.67: the relaxed-PACE band arms too (owner 2026-10-01, ADR 20261001-065500 D3).
    assert arm_trigger({"verdict": "GO", "relaxed_pace": True}) is True, "relaxed PACE must arm"
    assert arm_trigger({"verdict": "PACE"}) is True
    assert arm_trigger({"verdict": "STOP"}) is True
    # stand_down: a relaxed GO must return "" WITHOUT reaching do_cancel, a plain GO with a
    # future alarm must reach it. Inject a fake `resume` so no schtasks runs and the call is
    # observable. ⚠ stand_down imports `resume` inside the function, so sys.modules is the hook.
    import types as _types
    _ndir = tempfile.mkdtemp(prefix="dg-net-")
    # ⭐ Per-session record since 0.60: `<sdir>/resume/<session>.json`, not one shared file.
    _sid = "SELFTEST-SID"
    os.makedirs(os.path.join(_ndir, "resume"), exist_ok=True)
    with open(os.path.join(_ndir, "resume", _sid + ".json"), "w", encoding="utf-8") as _f:
        json.dump({"at": time.time() + 3600}, _f)          # a FUTURE alarm, ours to cancel
    _cc = []
    _fake = _types.ModuleType("resume")
    _fake.do_cancel = lambda sdir, quiet=True, session_id=None: (_cc.append(sdir), 0)[1]
    _fake.record_path = lambda sdir, session_id: os.path.join(
        sdir, "resume", safe_session(session_id) + ".json")
    _saved = sys.modules.get("resume")
    sys.modules["resume"] = _fake
    try:
        assert stand_down_resume(_ndir, _ndir, {"verdict": "GO", "relaxed_stop": True},
                                 _sid) == "", "net zone must not stand down"
        assert _cc == [], "the net zone reached do_cancel - the resume was cancelled"
        assert stand_down_resume(_ndir, _ndir, {"verdict": "GO", "relaxed_pace": True},
                                 _sid) == "", "relaxed PACE must not stand down"
        assert _cc == [], "relaxed PACE reached do_cancel - the resume was cancelled"
        _msg = stand_down_resume(_ndir, _ndir, {"verdict": "GO"}, _sid)
        assert _cc == [_ndir], "a plain GO with a future alarm must cancel: %r" % (_cc,)
        # ⛔ AND ANOTHER SESSION'S ALARM IS NOT TOUCHED. This is the whole point of the
        # per-session record: a session reaching GO used to cancel whatever the single
        # shared file held, which was often another session's still-needed resume.
        del _cc[:]
        assert stand_down_resume(_ndir, _ndir, {"verdict": "GO"}, "SOMEBODY-ELSE") == "", \
            "a GO cancelled another session's alarm"
        assert _cc == [], "another session's resume was cancelled: %r" % (_cc,)
    finally:
        if _saved is not None:
            sys.modules["resume"] = _saved
        else:
            sys.modules.pop("resume", None)
    shutil.rmtree(_ndir, ignore_errors=True)

    # ⛔ THE NET NOTE IS FACTS, ONCE PER WINDOW (0.66, ADR 20260929-152000 items 3 and 6) - no
    # longer every 10 minutes. It returns when THIS session's resume state changes (none ->
    # armed) and once inside the last 15 minutes, and it never claims a resume that does not
    # exist. Real relaxed-STOP scenario: 5h 90%, resets in 20 min.
    _wdir = tempfile.mkdtemp(prefix="dg-wind-")
    os.makedirs(os.path.join(_wdir, "state"), exist_ok=True)
    _wsid = "sess-net"
    with open(state_path(_wdir, _wsid, "start"), "w", encoding="utf-8") as _f:
        _f.write("x")                                       # stamp the session
    _rt = time.time()
    _reset = int(_rt + 20 * 60)
    with open(os.path.join(_wdir, "token_usage.json"), "w", encoding="utf-8") as _f:
        json.dump({"ts": int(_rt * 1000),
                   "five_hour": {"used_percentage": 90, "resets_at": _reset}}, _f)
    _wpayload = {"session_id": _wsid}
    _wv = usage.verdict(_wdir, usage.config(_wdir), now=_rt)
    assert _wv["verdict"] == "GO" and _wv["relaxed_stop"] is True, ("not the net zone: %r" % _wv)
    _m1 = wind_down_note(_wpayload, _wdir, _wdir, {}, now=_rt)
    assert _m1 and "NET zone" in _m1, ("the net note did not fire: %r" % (_m1,))
    assert "NO resume" in _m1 and "is armed" not in _m1, (
        "the net note claims a resume this session does not have: %r" % (_m1,))
    assert wind_down_note(_wpayload, _wdir, _wdir, {}, now=_rt + 60) is None, \
        "the net note repeated inside one window"
    # the session's resume lands -> the note says so, once
    os.makedirs(os.path.join(_wdir, "resume"), exist_ok=True)
    with open(os.path.join(_wdir, "resume", safe_session(_wsid) + ".json"), "w",
              encoding="utf-8") as _f:
        json.dump({"at": _reset + 180, "session_id": _wsid}, _f)
    _m4 = wind_down_note(_wpayload, _wdir, _wdir, {}, now=_rt + 2 * 60)
    assert _m4 and "resume is armed for" in _m4, ("the armed state was not reported: %r" % (_m4,))
    assert wind_down_note(_wpayload, _wdir, _wdir, {}, now=_rt + 3 * 60) is None, \
        "the net note re-fired without a change (the old 10-minute cadence is gone)"
    # ...and once more inside the last 15 minutes (13 min left here, clear of the boundary)
    _m6 = wind_down_note(_wpayload, _wdir, _wdir, {}, now=_rt + 7 * 60)
    assert _m6 and "NET zone" in _m6, ("no last-15-minutes note: %r" % (_m6,))
    assert wind_down_note(_wpayload, _wdir, _wdir, {}, now=_rt + 8 * 60) is None
    shutil.rmtree(_wdir, ignore_errors=True)

    # ⛔ prune_state SWEEPS EVERY PER-SESSION MARKER BY AGE (not a suffix list), keeps the recent
    # ones, keeps .slot* forever, bounds .alive by count, and is DELETE-SAFE on a bad setting.
    _psdir = tempfile.mkdtemp(prefix="dg-prune-")
    _pst = os.path.join(_psdir, "state")
    os.makedirs(_pst)
    _old = time.time() - 10 * 86400          # older than the 7-day margin
    _new = time.time() - 60                  # a minute ago
    def _plant(name, when):
        p = os.path.join(_pst, name)
        with open(p, "w", encoding="utf-8") as _f:
            _f.write("x")
        os.utime(p, (when, when))
        return p
    for _n in ("sidA.start", "sidA.branch-deadbeef", "sidA.skill-seen-unattended-work",
               "sidA.warned", "sidA.warned-tool", "sidA.warned-tool-agent7",
               "sidA.handoff-written", "sidA.require-skills-tries", "sidA.unattended-nagged"):
        _plant(_n, _old)
    _plant("sidB.start", _new)
    _plant("sidB.branch-cafe", _new)
    _plant("sidA.slot0", _old)               # live concurrency state - never age-pruned
    for _i in range(STATE_KEEP_ALIVE + 5):
        _plant("aliveS%d.alive" % _i, _new - _i)     # distinct mtimes for the count rule
    prune_state(_psdir, {"state_keep_days": 7})
    _left = set(os.listdir(_pst))
    assert not any(n.startswith("sidA.") and n != "sidA.slot0" for n in _left), (
        "an old per-session marker survived the age sweep: %r" % _left)
    assert "sidB.start" in _left and "sidB.branch-cafe" in _left, (
        "a recent marker was pruned: %r" % _left)
    assert "sidA.slot0" in _left, "a .slot file was pruned - that is live concurrency state"
    assert sum(1 for n in _left if n.endswith(".alive")) == STATE_KEEP_ALIVE, (
        "the .alive count bound is wrong: %r" % _left)
    # ⛔ DELETE-SAFE: a bad state_keep_days must KEEP EVERYTHING the age sweep would take.
    _plant("sidC.start", _old)
    prune_state(_psdir, {"state_keep_days": "abc"})
    assert "sidC.start" in set(os.listdir(_pst)), "a bad state_keep_days still deleted by age"
    shutil.rmtree(_psdir, ignore_errors=True)

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
        # ⛔ THE CHECK MUST NOT WRITE INTO THE REAL STATE DIRECTORY. log() sends every
        # line to usage.state_dir() as well as to the repository copy, and selftest()
        # runs the real decision paths - so without this, every suite run filed 45
        # `DENY(ultracode)` lines into the owner's own log. Measured 2026-09-01, from
        # the owner asking why their log was full of refusals for a mode no session had
        # switched on. ⚠ HERE, not inside selftest(): half that function runs after its
        # own try/finally, so a redirection scoped to the try would miss exactly the
        # ultracode block that produced the lines.
        import tempfile as _tf
        _quarantine = _tf.mkdtemp(prefix="dg-selftest-")
        usage.state_dir = lambda argv=None, _d=_quarantine: _d
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
            with open(os.path.join(tempfile.gettempdir(), "dispatch_gate_error.log"),
                      "a", encoding="utf-8") as f:
                f.write("%s %r%s" % (time.strftime("%Y-%m-%d %H:%M:%S"), exc, "\n"))
        except Exception:
            pass
    sys.exit(0)
