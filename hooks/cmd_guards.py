#!/usr/bin/env python3
"""Guards for commands that fail SILENTLY - where the wrong outcome and the right one
are byte-identical on screen.

The dispatch gate refuses concurrent, background, mass-spawn, plan-less and over-budget
DISPATCHES. This file is the second family: a `git commit` that lands on another session's
branch, a `git add -A` that sweeps somebody else's files in, a search whose errors were
silenced so "you looked in the wrong place" reads as "there is nothing there".

⭐ WHY THESE AND NOT A DOCUMENT. Every rule here was already written down, read, and broken
anyway - four of them in ONE session by the agent that had read them, two of them by the
agent that had WRITTEN them that morning. The sharpest case: the branch rule said "check
which branch you are on before every commit", and the agent DID run the command - chained as
`git rev-parse --abbrev-ref HEAD && git add -A && git commit …`. ⛔ `&&` asks only whether
the previous command SUCCEEDED, never whether its answer was ACCEPTABLE. The branch name
printed, scrolled past, and the commit landed on another session's branch.
⇒ An injected message is advice a model weighs against its task. A refused tool call is not.

FIVE THINGS THAT ARE EASY TO MISREAD
------------------------------------

1. EVERY PATH FAILS OPEN. A guard that raises is logged and skipped; the command runs. The
   gate's whole claim is that a broken gate never stops work, and this family does not get
   to weaken it. ⚠ The price is the same as before: an absent denial is not proof a guard
   ran, which is why every decision is logged - allow, deny, disabled and error alike.

2. AN UNSTAMPED SESSION IS ADVISORY ONLY, exactly as for the dispatch guards. A session that
   began before this version was installed gets logged and allowed. ⛔ Otherwise installing
   an update starts refusing `git add -A` in the middle of somebody's live session, which is
   the one thing the gate has always promised not to do.

3. STATE IS QUERIED, NEVER PARSED OUT OF THE COMMAND. The branch guard asks git which branch
   HEAD is on. The command string is used only as a cheap filter for WHICH question to ask -
   never as the answer.

4. NEVER `permissionDecision: "allow"` FOR A SHELL COMMAND. An "allow" from a hook suppresses
   the user's own permission prompt, so a warning that used it would silently hand every
   guarded command a free pass. Warnings therefore carry no decision at all - see warn().

5. THE BRANCH RECORD IS KEYED PER (SESSION, REPOSITORY). One session can work in two
   checkouts; a single record would report the first repository's branch as the "selected"
   one and refuse the first commit in the second. Measured in review, not in production -
   which is the only reason it is not in CHANGELOG.md as a defect.

Standard library only, like everything else here.
"""

import hashlib
import os
import re
import subprocess

# ⭐ EVERY GUARD HAS ITS OWN SWITCH, defaulting to on. A guard that cannot be turned off gets
# the whole plugin uninstalled the first time it is wrong, and these are heuristics over
# shell strings - they WILL be wrong sometimes. ⛔ Deliberately NOT one switch shared with
# the dispatch guards: somebody will want the dispatch gate without the git gate.
GUARD_DEFAULTS = {
    "guard_commit_branch": True,        # deny: commit on a branch this session did not pick
    "guard_add_all": True,              # deny: git add -A / . / --all
    "guard_commit_message_file": True,  # deny: git commit -m, name -F instead
    "guard_silenced_search": True,      # deny: a search with its errors silenced
    "guard_relative_cd": True,          # warn: `cd <relative> && …`
    "guard_unattended_first": True,     # deny once: dispatch before unattended-work loaded
    "guard_unpushed": True,             # note: older unpushed commits on this branch
}

# ⭐ WHICH SKILLS A SESSION MUST HAVE INVOKED BEFORE IT MAY DISPATCH ANYTHING - two booleans,
# and the split between them is the point.
#
# `dispatch-protocol` is what this plugin IS. It says how a wave is planned, laid out on disk
# and paced, and every mechanical part of it is what the gate enforces - so a session that
# dispatches without it is being refused by rules it never read. Required by default.
#
# ⛔ `unattended-work` IS NOT REQUIRED BY DEFAULT, and that is a correction. It shipped as a
# requirement in 0.22.0 and the owner reversed it for a good reason: a skill exists to give an
# agent a WAY OF WORKING, not to gate it, and this plugin's job is dispatch discipline rather
# than unattended operation. Someone who dispatches sub-tasks while watching the screen needs
# `dispatch-protocol` and has no use for the review rounds, the stall test or the exit bar.
# ⇒ Whether the two must travel together is now the owner's decision, in one switch.
#
# ⚠ THE REQUIREMENT REFUSES EVERY TIME, not once - unlike guard_unattended_first, which nags
# once and stands aside. It is defensible because the fix is always available to the agent:
# invoking a skill is a tool call it can make. ⛔ The residual risk is stated rather than
# hidden - if the skill registry itself is broken, that session cannot dispatch at all. The
# switches are the escape hatch and they belong to the OWNER: the refusal deliberately does
# NOT tell the agent to edit config, because a rule that names its own off switch is a rule
# that gets switched off. See the branch guard for the same decision.
GUARD_DEFAULTS["require_dispatch_protocol"] = True
GUARD_DEFAULTS["require_unattended_work"] = False

# The tools that run a shell. ⚠ BOTH, not just Bash: this harness also exposes a PowerShell
# tool, and `git add -A` through it does exactly the same damage.
SHELL_TOOLS = ("Bash", "PowerShell")

# ⚠ 3 SECONDS, and fail open past it. The hook's whole budget is 15s, and git blocks on
# `index.lock` for as long as another process holds it - so an unlucky moment must cost a
# skipped guard, never a stalled tool call.
GIT_TIMEOUT = 3

DETACHED = "(detached HEAD)"


# ------------------------------------------------------------------- shell string handling

# ⚠ NOT A SHELL PARSER, and it does not need to be. Splitting on the operators is enough to
# find "is there a `git commit` in here", which is the question the chained failure turned
# into. Quoting is not honoured; the cost is a possible false positive from an operator
# inside a quoted string, and the log is what makes that visible. `2>&1` is why a lone `&`
# is NOT a separator here.
_SPLIT = re.compile(r"&&|\|\||;|\||\n|\r")

# Wrappers to strip before asking "what is this segment's command?". ⛔ Without this a
# silenced `timeout 40 grep … 2>/dev/null` walks straight past a starts-with-grep test, and
# `timeout`-prefixed commands are not exotic - this repository's own checks are full of them.
_WRAPPER = re.compile(
    r"^(?:"
    r"[A-Za-z_][A-Za-z_0-9]*=(?:\"[^\"]*\"|'[^']*'|\S*)"     # VAR=value
    r"|timeout\s+-?-?\w*\s*[0-9.]+[smhd]?"
    r"|time|nohup|command|exec|sudo|env|builtin|\\"
    r")\s+")


def segments(command):
    """The command split on shell operators, stripped, empties dropped."""
    return [s.strip() for s in _SPLIT.split(command or "") if s.strip()]


def bare(segment):
    """A segment with leading wrappers, brackets and redirections-before-command removed."""
    s = (segment or "").lstrip("({ \t")
    for _ in range(6):                      # bounded: a pathological string must not loop
        m = _WRAPPER.match(s)
        if not m:
            break
        s = s[m.end():]
    return s


def command_of(payload):
    """The shell command in this payload, or "" when the tool does not run one."""
    if payload.get("tool_name") not in SHELL_TOOLS:
        return ""
    c = (payload.get("tool_input") or {}).get("command")
    return c if isinstance(c, str) else ""


# `git`, optionally with global options, then the subcommand. `-C <path>` and `-c k=v` take a
# value; anything else global is a flag. Written out rather than "git.*commit" because the
# loose form matches a commit message that merely MENTIONS git commit.
_GIT = r"^git(?:\.exe)?\s+(?:(?:-C|-c|--git-dir|--work-tree|--namespace)(?:\s+|=)\S+\s+|-\S+\s+)*"
_COMMIT = re.compile(_GIT + r"commit\b(?P<rest>.*)$", re.S)
_ADD = re.compile(_GIT + r"add\b(?P<rest>.*)$", re.S)
_GIT_GREP = re.compile(_GIT + r"grep\b", re.S)
# Branch-changing commands. ⚠ Used ONLY to decide whether to re-ask git; never as the answer.
_MOVED = re.compile(_GIT + r"(?:checkout|switch|worktree\s+add|restore\s+--source)\b", re.S)

# `-A`, `--all`, or a lone `.` as a whole argument. `git add ./one.py` is a named path and
# must NOT match, which is why the dot form is anchored on both sides.
_ADD_ALL = re.compile(r"(?:^|\s)(?:-[A-Za-z]*A[A-Za-z]*|--all|\.)(?:\s|$)")
# `-m`, `-am`, `--message`. ⚠ `--amend` must not match: the second dash is not preceded by
# whitespace, so the lead-in `(?:^|\s)-` cannot start there.
_DASH_M = re.compile(r"(?:^|\s)(?:-[A-Za-z]*m[A-Za-z]*|--message)(?:\s|=|$)")

# Errors thrown away. `$null` and `NUL` are the PowerShell and cmd spellings of the same act.
_SILENCED = re.compile(r"2\s*>\s*(?:/dev/null|\$null|NUL|nul)(?:\s|$)")
# ⚠ `-s` MEANS DIFFERENT THINGS, and the long flag does not. For grep `-s` is
# --no-messages; for ripgrep `-s` is --case-sensitive and silences nothing at all. Getting
# that backwards would refuse a correct command and teach the owner to switch the guard off,
# so `-s` is checked for grep only - while `--no-messages`, which means the same thing in
# both, is checked for both.
_S_FLAG_TOOLS = ("grep", "egrep", "fgrep")
_S_FLAG = re.compile(r"(?:^|\s)-[A-Za-z]*s[A-Za-z]*(?:\s|$)")
_LONG_QUIET = re.compile(r"(?:^|\s)--no-messages(?:\s|$)")
SEARCH_TOOLS = ("grep", "egrep", "fgrep", "rg", "find", "ls")


def _head(seg):
    """The command word of a bare segment, lowercased, extension dropped."""
    m = re.match(r"^([^\s]+)", seg)
    if not m:
        return ""
    w = m.group(1).replace("\\", "/").rsplit("/", 1)[-1].lower()
    return w[:-4] if w.endswith(".exe") else w


# ------------------------------------------------------------------------------- git state

def _git(root, args, timeout=GIT_TIMEOUT):
    """(returncode, stdout) - or (None, "") when git could not be run at all."""
    try:
        p = subprocess.Popen(["git", "-C", root] + list(args),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, _err = p.communicate(timeout=timeout)
    except Exception:
        return None, ""
    return p.returncode, (out or b"").decode("utf-8", "replace")


def current_branch(root):
    """The branch HEAD is on, DETACHED when there is none, or None when git cannot say.

    ⭐ `symbolic-ref` rather than `rev-parse --abbrev-ref`: in a repository with no commit
    yet, symbolic-ref still names the unborn branch and rev-parse fails outright - and a
    first commit is exactly when a wrong answer here is least welcome.

    ⚠ `-q` EXITS 1 FOR DETACHED HEAD AND FOR "NOT A REPOSITORY" ALIKE, so the two are told
    apart with a second question rather than guessed at. Detached HEAD is a real state a
    session can sit in; reporting it as "git is unusable" would silently disable the guard.
    """
    rc, out = _git(root, ["symbolic-ref", "--short", "-q", "HEAD"])
    if rc == 0:
        return out.strip() or DETACHED
    if rc is None:
        return None
    rc2, _ = _git(root, ["rev-parse", "--git-dir"])
    return DETACHED if rc2 == 0 else None


def _repo_key(root):
    """A short, stable id for a checkout. ⭐ The branch record is per (session, repository):
    one session can work in two checkouts, and a single record would call the first one's
    branch "selected" and refuse the first commit in the second."""
    norm = os.path.normcase(os.path.abspath(root or "."))
    return hashlib.md5(norm.encode("utf-8", "replace")).hexdigest()[:8]


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def _write(path, text):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return True
    except OSError:
        return False


def branch_mark(ctx, root=None):
    return ctx["state"]("branch-%s" % _repo_key(root or ctx["root"]))


def record_branch(ctx, root=None, branch=None):
    """Record the branch this session is working on. Returns what was recorded, or None."""
    root = root or ctx["root"]
    b = branch if branch is not None else current_branch(root)
    if b is None:
        return None
    _write(branch_mark(ctx, root), b)
    return b


# ------------------------------------------------------------------------------- verdicts

DENY = "deny"
WARN = "warn"


def _v(kind, key, model, screen=None):
    return {"kind": kind, "key": key, "model": model, "screen": screen}


# --------------------------------------------------------------------------------- guards
# Every guard: (payload, ctx, segs) -> a verdict, or None to say nothing. `segs` is the list
# of BARE segments. Guards must not raise, but check() assumes they might.

def g_commit_branch(payload, ctx, segs):
    """A commit on a branch this session did not select.

    ⛔ THIS IS THE ONE THAT CAUSED REAL DAMAGE, and it is a PER-COMMIT condition, not a
    per-session one: in a shared working tree another session can `checkout` under you
    between two of your commits. Asking once at session start would have caught nothing.
    """
    if not any(_COMMIT.match(s) for s in segs):
        return None
    root = ctx["root"]
    actual = current_branch(root)
    if actual is None:
        # Not a git repository, or git is unusable right now. Nothing to compare against.
        ctx["log"]("CMD-ADVISORY(commit-branch: git cannot name a branch in %s)" % root)
        return None
    mark = branch_mark(ctx, root)
    recorded = _read(mark)
    if recorded is None:
        # ⭐ FIRST COMMIT IN THIS REPOSITORY FOR THIS SESSION: record and allow. Refusing
        # here would refuse a commit for a record nobody was ever told to create - the same
        # shape as the unstamped-session rule.
        _write(mark, actual)
        ctx["log"]("CMD-ADVISORY(commit-branch: recorded %s for %s)" % (actual, root))
        return None
    if recorded == actual:
        return None
    return _v(DENY, "guard_commit_branch",
              "dispatch gate: `git commit` REFUSED. This session selected branch `%s`; HEAD "
              "is on `%s` now, so another session moved this shared working tree under you. "
              "⛔ Do NOT switch it back - that breaks their work in flight. Commit from a "
              "throwaway clone instead: `git clone . ../dg-tmp`, commit and push there, then "
              "delete it. ⚠ Say this to the user before doing anything else: two sessions are "
              "sharing one working tree, and each one needs its own worktree."
              % (recorded, actual),
              # ⭐ ON THE SCREEN TOO: this one means somebody else's branch nearly received
              # a commit, and only a person can decide to give the sessions separate trees.
              "dispatch-guard: `git commit` REFUSED - this session picked `%s`, the tree is "
              "on `%s`. Another session moved it. Nothing was committed." % (recorded, actual))


def g_add_all(payload, ctx, segs):
    """`git add -A` / `git add .` / `git add --all` in a tree somebody else may be editing."""
    for s in segs:
        m = _ADD.match(s)
        if m and _ADD_ALL.search(m.group("rest")):
            return _v(DENY, "guard_add_all",
                      "dispatch gate: `git add -A` (or `.` / `--all`) is refused. Stage the "
                      "paths you changed, BY NAME. In a shared working tree this stages "
                      "whatever every other session has been editing - that is how two "
                      "unrelated files entered someone else's commit. It costs one flag.")
    return None


def g_commit_message_file(payload, ctx, segs):
    """`git commit -m` - the message loses characters to the shell, silently."""
    for s in segs:
        m = _COMMIT.match(s)
        if m and _DASH_M.search(m.group("rest")):
            return _v(DENY, "guard_commit_message_file",
                      "dispatch gate: `git commit -m` is refused. Write the message to a file "
                      "and use `git commit -F <path>`. A message on the command line loses "
                      "parentheses, backticks and `::` to the shell, and the damage is only "
                      "visible in `git log` afterwards - when it is already history.")
    return None


def g_silenced_search(payload, ctx, segs):
    """A search whose errors were thrown away.

    ⛔ That flag is exactly what converts "you searched the wrong place" into "there is
    nothing there". The two outputs are identical, and the second one is a conclusion.
    """
    for s in segs:
        head = _head(s)
        is_git_grep = bool(_GIT_GREP.match(s))
        if head not in SEARCH_TOOLS and not is_git_grep:
            continue
        why = None
        if _SILENCED.search(s):
            why = "its errors are redirected away"
        elif _LONG_QUIET.search(s):
            why = "`--no-messages` silences them"
        elif (head in _S_FLAG_TOOLS or is_git_grep) and _S_FLAG.search(s):
            why = "`-s` silences them"
        if why:
            return _v(DENY, "guard_silenced_search",
                      "dispatch gate: this search is refused because %s. Run it bare, READ the "
                      "error, and filter afterwards if the noise is real. A silenced search "
                      "returns the same empty output whether the path was wrong or the match "
                      "was absent - and only one of those is an answer." % why)
    return None


def g_relative_cd(payload, ctx, segs):
    """`cd <relative path> && …` - when the `cd` fails, the rest silently does not run.

    ⚠ WARN, NOT REFUSE, and the reason is a limit rather than a preference. The prompt for
    this guard allowed a refusal if the target's existence could be tested - it cannot. The
    shell's working directory PERSISTS between tool calls and the hook payload does not carry
    it, so the gate does not know what the relative path will be resolved against. Refusing
    on "not found under the payload cwd" would refuse correct commands. The existence test is
    still reported, as a hint, when it fails.
    """
    if len(segs) < 2:
        return None
    m = re.match(r"^cd\s+(?P<t>\"[^\"]+\"|'[^']+'|[^\s;&|]+)", segs[0])
    if not m:
        return None
    target = m.group("t").strip("\"'")
    if (target.startswith(("/", "~", "\\", "-", "$")) or re.match(r"^[A-Za-z]:", target)):
        return None                     # absolute, home, `cd -`, or a variable
    here = payload.get("cwd") or ctx.get("root") or "."
    seen = os.path.isdir(os.path.join(here, target.replace("/", os.sep)))
    return _v(WARN, "guard_relative_cd",
              "dispatch gate WARNING: `cd %s && …` uses a RELATIVE path. The shell's working "
              "directory persists between calls, so this can resolve somewhere else than last "
              "time - and when the `cd` fails, every later command in the chain does not run "
              "and prints a clean-looking nothing. %s Use an absolute path, or `cd … || exit 1`."
              % (target,
                 "⛔ It does not exist under %s right now." % here if not seen
                 else "(It does exist under %s.)" % here))


# ⭐ THE TABLE IS THE GUARD LIST. Ordered most-damaging first, and the first verdict wins:
# one refusal an agent can act on beats four it has to unpick. Deleting an entry disables
# that guard completely, which is how the checks in Tools/Debug/test_guards.py mutation-test
# each one - remove the row, drive the same payload through main(), watch the check fail.
GUARDS = (
    ("guard_commit_branch", g_commit_branch),
    ("guard_add_all", g_add_all),
    ("guard_commit_message_file", g_commit_message_file),
    ("guard_silenced_search", g_silenced_search),
    ("guard_relative_cd", g_relative_cd),
)


# ---------------------------------------------------------------------------- entry points

def check(payload, ctx):
    """Run the command guards over a PreToolUse payload. Returns a verdict or None.

    ⛔ LOGS EVERY DECISION - allow, deny, disabled and error alike. "No denial appeared" and
    "no guard ever ran" must not look the same in the log, because that is precisely how this
    plugin was silently advisory for five releases.
    """
    cmd = command_of(payload)
    if not cmd:
        return None
    if not ctx.get("stamped"):
        # See point 2 in the module docstring: never mid-flight in a session already running.
        ctx["log"]("CMD-ADVISORY(no-session-stamp) %s" % cmd[:60])
        return None
    cfg = ctx.get("cfg") or {}
    segs = [bare(s) for s in segments(cmd)]
    off = []
    for key, fn in GUARDS:
        enabled = cfg.get(key, GUARD_DEFAULTS.get(key, True))
        if not enabled:
            off.append(key)
        try:
            v = fn(payload, ctx, segs)
        except Exception as exc:
            # ⛔ FAIL OPEN, LOUDLY IN THE LOG AND SILENTLY ON SCREEN. A guard that breaks
            # must not block work; a guard that breaks unnoticed must not happen either.
            ctx["log"]("CMD-GUARD-ERROR(%s) %r" % (key, exc))
            continue
        if not v:
            continue
        if not enabled:
            # ⭐ RUN EVEN WHEN OFF, so the log says what the off switch actually cost. A
            # disabled guard that stays quiet is invisible; this one at least leaves a trace.
            ctx["log"]("CMD-DISABLED(%s) would have refused: %s" % (key, cmd[:60]))
            continue
        ctx["log"]("CMD-%s(%s) %s" % (v["kind"].upper(), key, cmd[:60]))
        return v
    ctx["log"]("CMD-ALLOW(checked=%d off=%s) %s"
               % (len(GUARDS), ",".join(off) or "-", cmd[:60]))
    return None


def skill_slug(name):
    """The bare skill name, lowercased and safe to use in a filename.

    ⚠ THE SAME SKILL ARRIVES UNDER SEVERAL NAMES. A plugin skill is invoked as
    `dispatch-guard:unattended-work`, a directory-scoped one as `apps/web:deploy`, and a plain
    one as `unattended-work`. Stripping the plugin and directory prefixes makes all three the
    same mark - otherwise "the skill is loaded" depends on how it was spelled.
    """
    bare = str(name or "").strip().lower().replace("\\", "/")
    bare = bare.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    return "".join(c if (c.isalnum() or c in "-_") else "-" for c in bare)[:48].strip("-")


def skill_seen(ctx, name):
    """Did this session invoke that skill?"""
    slug = skill_slug(name)
    return bool(slug) and os.path.exists(ctx["state"]("skill-seen-%s" % slug))


def note_skill(payload, ctx):
    """Record that this session invoked a skill. PostToolUse only.

    ⚠ POST, NOT PRE: a Skill call the user denied is not an invocation, and PreToolUse fires
    before anyone has agreed to anything.

    ⭐ EVERY skill, not only `unattended-work`. One mark per skill costs nothing, prune_state
    clears them with the rest of the session's state, and it means `require_skills` can name
    anything without a second recording path.
    """
    if payload.get("tool_name") != "Skill":
        return False
    name = str((payload.get("tool_input") or {}).get("skill") or "")
    slug = skill_slug(name)
    if not slug:
        return False
    _write(ctx["state"]("skill-seen-%s" % slug), name)
    ctx["log"]("SKILL-SEEN %s" % name)
    return True


def _truthy(value, default):
    """A config boolean that survives being written as a string. `"false"` means false."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("false", "0", "no", "off", ""):
        return False
    if text in ("true", "1", "yes", "on"):
        return True
    return default


def required_skills(cfg):
    """The skills this session must have invoked before dispatching. [] = the check is off.

    ⛔ `announce_unattended_work=false` REMOVES `unattended-work`, and that is a conflict
    resolved rather than ignored. That switch means "I do not want this skill"; a check that
    then refused every dispatch until it loaded would be the plugin overruling its own off
    switch, and the owner would face two settings that contradict. ⇒ One meaning per switch.
    `dispatch-protocol` is unaffected: it has no such switch, and it is the one this plugin
    cannot sensibly work without.
    """
    names = []
    if _truthy(cfg.get("require_dispatch_protocol"), True):
        names.append("dispatch-protocol")
    if _truthy(cfg.get("require_unattended_work"), False):
        names.append("unattended-work")
    if "unattended-work" in names:
        try:
            import unattended
            if not unattended.announcing():
                names.remove("unattended-work")
        except Exception:
            pass                        # cannot read the switch: keep the stricter list
    return names


def skills_refusal(payload, ctx, cfg):
    """Refuse this dispatch while any required skill has not been invoked. Returns a verdict.

    ⚠ Repeats for as long as one is missing - see GUARD_DEFAULTS' comment on
    `require_dispatch_protocol` for why that is the point rather than an oversight, and where
    the escape hatch lives.
    """
    need = required_skills(cfg)
    if not need:
        ctx["log"]("REQUIRE-SKILLS-OFF")
        return None
    missing = [n for n in need if not skill_seen(ctx, n)]
    if not missing:
        return None
    calls = ", ".join("`dispatch-guard:%s`" % skill_slug(n) for n in missing)
    ctx["log"]("REQUIRE-SKILLS missing=%s" % ",".join(skill_slug(n) for n in missing))

    # ⛔ THE ONE ASSUMPTION UNDER THIS RULE THAT CANNOT BE MEASURED FROM OUTSIDE: that the
    # harness fires PreToolUse/PostToolUse for the `Skill` tool at all. The shipped binary has
    # no exemption list, no special case for Skill, and a dispatch generic over the tool name -
    # but "no evidence against" is not proof, and if it were wrong this rule would refuse every
    # dispatch in every session for ever. ⇒ So the failure is made to REPORT ITSELF rather than
    # look like the rule working: after a few refusals in one session the message stops
    # assuming the agent is at fault and names the other possibility. An absent signal must
    # never be indistinguishable from a working one - that is this whole plugin's thesis.
    tries_path = ctx["state"]("require-skills-tries")
    prior = _read(tries_path) or "0"
    tries = (int(prior) if prior.isdigit() else 0) + 1
    _write(tries_path, str(tries))
    stuck = ("" if tries < 3 else
             " ⛔ THIS IS REFUSAL %d IN THIS SESSION. If you HAVE invoked those skills and this "
             "keeps repeating, then this harness is not reporting `Skill` calls to the hook, and "
             "no amount of retrying will clear it. STOP and tell the user exactly that, in plain "
             "words, so they can release it." % tries)
    stuck_screen = ("" if tries < 3 else
                    " ⛔ %d refusals in this session. If the agent says it DID load them, the "
                    "harness is not reporting `Skill` calls to the hook - look for a "
                    "`SKILL-SEEN` line in .claude/dispatch_gate.log, and if there is none, set "
                    "`require_dispatch_protocol: false`." % tries)
    # ⚠ WHY EACH SKILL IS NEEDED, but only for the ones actually missing. Naming a skill the
    # session already loaded reads as the gate not knowing what it has, and an agent that
    # believes the gate is confused works around it instead of complying.
    WHY = {
        "dispatch-protocol": "`dispatch-protocol` is how a wave is planned, laid out on disk "
                             "and paced - and every mechanical part of it is what this gate "
                             "enforces, so without it you are being refused by rules you "
                             "never read",
        "unattended-work": "`unattended-work` is how the work is reviewed, when you may "
                           "proceed without the owner, and the exit bar before handing back",
    }
    why = ". ".join(WHY[s] for s in (skill_slug(n) for n in missing) if s in WHY)
    return _v(DENY, "require_skills",
              "dispatch gate: dispatch REFUSED - this session has not invoked %s. Invoke %s "
              "now, then dispatch again. ⚠ This refusal REPEATS until it is loaded; it is not "
              "a one-off, so do not retry the dispatch unchanged. %s. ⛔ If it will not load, "
              "STOP and tell the user in plain words - only they can change what this gate "
              "requires, and you must not work around it.%s"
              % (calls.replace(", ", " and "), calls, why or "They are not optional extras",
                 stuck),
              "dispatch-guard: dispatch REFUSED - %s not loaded in this session. Nothing was "
              "dispatched. The agent is being asked to invoke %s. ⚠ Every dispatch is refused "
              "until it does; if the skill cannot load, set `require_dispatch_protocol: false` "
              "in config.json to release it.%s"
              % (", ".join(skill_slug(s) for s in missing), calls, stuck_screen))


def unattended_first(payload, ctx, enabled=True):
    """Refuse ONE dispatch when this session never invoked `unattended-work`.

    ⭐ RUNS EVEN WHEN `enabled` IS FALSE, and logs instead of refusing - the same rule the
    five command guards follow. A guard that switches off silently is indistinguishable in the
    log from a guard that ran and found nothing, which defeats the reason every decision here
    is written down. ⚠ And when it is off the nag mark is NOT written: leaving the mark would
    spend the one refusal while nobody was listening, so switching the guard back on later
    would find it already used.

    ⭐ WHY IT EXISTS. The plugin already prints a SessionStart reminder naming the skill and
    asking for its ACTIVE line. Measured 2026-08-27: the reminder was ignored for an entire
    session and nothing noticed. The dispatch is where it starts to matter, and PreToolUse is
    the only place a call can be refused.

    ⚠ ONCE, then allow for the rest of the session. A skill that fails to load - a renamed
    plugin, a broken registry - would otherwise deadlock the session at its first dispatch,
    and a guard that can brick a session is a guard people remove.

    ⛔ SILENT WHEN THE OWNER TURNED THE REMINDER OFF. `announce_unattended_work=false` is a
    decision that the rules do not apply here; refusing a dispatch for not loading a skill
    the owner opted out of would be the plugin overruling its own off switch. One source of
    truth for that switch - unattended.announcing().
    """
    if skill_seen(ctx, "unattended-work"):
        return None
    try:
        import unattended
        if not unattended.announcing():
            return None
    except Exception as exc:
        ctx["log"]("CMD-GUARD-ERROR(guard_unattended_first) %r" % (exc,))
        return None
    mark = ctx["state"]("unattended-nagged")
    if os.path.exists(mark):
        return None
    if not enabled:
        ctx["log"]("CMD-DISABLED(guard_unattended_first) would have refused this dispatch")
        return None
    _write(mark, "1")
    return _v(DENY, "guard_unattended_first",
              "dispatch gate: dispatch refused ONCE - this session never invoked the "
              "`unattended-work` skill. Invoke `dispatch-guard:unattended-work` now, print its "
              "ACTIVE line, then dispatch again; the next dispatch is allowed either way. It "
              "governs review rounds, the stall test, when you may proceed without the owner, "
              "and the exit bar - all of which apply to what you are about to dispatch.",
              "dispatch-guard: first dispatch refused - the agent had not loaded the "
              "unattended-work skill. It is being asked to load it now. This happens at most "
              "once per session.")


def after_command(payload, ctx):
    """PostToolUse for a shell command: keep the branch record honest, and flag unpushed work.

    Returns advisory text for the model, or None. Never refuses - PostToolUse cannot.
    """
    cmd = command_of(payload)
    if not cmd:
        return None
    segs = [bare(s) for s in segments(cmd)]
    cfg = ctx.get("cfg") or {}
    out = []

    # ⭐ A BRANCH THIS SESSION CHOSE ITSELF IS LEGITIMATE, so the record follows it. The
    # command string only decides whether to ASK; the recorded value comes from git.
    if any(_MOVED.match(s) for s in segs):
        b = record_branch(ctx)
        ctx["log"]("BRANCH-RECORDED %s" % b if b else "BRANCH-RECORD-FAILED")

    if any(_COMMIT.match(s) for s in segs):
        enabled = cfg.get("guard_unpushed", GUARD_DEFAULTS["guard_unpushed"])
        rc, txt = _git(ctx["root"], ["rev-list", "--count", "@{u}..HEAD"])
        if rc != 0:
            # ⚠ NO UPSTREAM IS A NORMAL STATE - a new branch before its first push. Saying
            # nothing is right; letting it reach the generic error handler would spam
            # CMD-GUARD-ERROR on every commit and poison the log the guards exist to protect.
            ctx["log"]("CMD-ADVISORY(unpushed: no upstream for HEAD)")
        else:
            try:
                n = int(txt.strip() or "0")
            except ValueError:
                n = 0
            if n >= 2:
                msg = ("dispatch gate: %d commits on this branch are NOT pushed, including "
                       "ones older than the one you just made. Push now - a fix that is not "
                       "pushed never reaches anybody." % n)
                if enabled:
                    ctx["log"]("CMD-NOTE(guard_unpushed n=%d)" % n)
                    out.append(msg)
                else:
                    ctx["log"]("CMD-DISABLED(guard_unpushed) would have noted n=%d" % n)
            else:
                ctx["log"]("CMD-ALLOW(guard_unpushed n=%d)" % n)
    return " ".join(out) or None
