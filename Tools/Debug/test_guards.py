#!/usr/bin/env python3
"""The silent-failure guards - driven through main(), the way the harness drives them.

    python Tools/Debug/test_guards.py

⛔ WHY EVERY CASE GOES THROUGH `main()` AND NOT THROUGH `cmd_guards.check()`. Releases 0.4.0
to 0.6.0 enforced NOTHING while every self-check stayed green, because the checks exercised
the decision functions and never the wiring: a `NameError` ahead of every event branch made
the hook print nothing, and a hook that prints nothing has APPROVED the call. So each case
here writes real payload bytes to the gate's stdin and asserts on the JSON that comes back
out. A guard that is correct but unreachable fails these checks.

⭐ EVERY GUARD IS MUTATION-CHECKED. `expect_deny` on its own only proves that SOMETHING
refused. So each guard is then removed from `cmd_guards.GUARDS` and the same payload is driven
through `main()` again: if the refusal survives, the case was not testing that guard, and if
the refusal was never there, the first assertion already failed. Three of these guards are
fail-open by nature, which is exactly the class that lies when tested naively.

⚠ Nothing here touches ~/.claude, spends an API call, or reaches a network. The state
directory is redirected, the clock's fork is stubbed out, and the git fixture is a bare
`git init` in `Tools/Debug/scratch/` with no commits - `symbolic-ref` names an unborn branch,
so the branch cases need no commit, no identity and no signing key.
"""

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import fresh_scratch, repo_path, scratch_dir  # noqa: E402

GIT_ID = ["-c", "user.name=dg check", "-c", "user.email=check@example.invalid",
          "-c", "commit.gpgsign=false"]


def load_gate(sdir):
    """Import the gate with its state directory redirected and its clock stubbed.

    ⛔ `usage.state_dir` is patched on the MODULE OBJECT the gate imported, not on a fresh
    copy. Patching a second import of the same file is a different object, the stub does
    nothing, and the check silently exercises the real paths - measured on this repository:
    a probe "verified" behaviour it had never reached and wrote into the real user settings.
    """
    sys.path.insert(0, repo_path("hooks"))
    import usage
    import dispatch_gate
    usage.state_dir = lambda argv=None: sdir
    # ⚠ Otherwise main() forks `usage.py --fetch-now` on the first payload, because an empty
    # state directory is always "due". That would spend an API call from a test.
    dispatch_gate.keep_clock_running = lambda _sdir: False
    return dispatch_gate


def run_gate(gate, payload):
    """Drive main() as the harness does: payload bytes on stdin, one JSON object on stdout."""
    raw = json.dumps(payload).encode("utf-8")

    class _Stdin(object):
        buffer = io.BytesIO(raw)

    out = io.StringIO()
    _in, _stdout = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = _Stdin(), out
    try:
        gate.main()
    finally:
        sys.stdin, sys.stdout = _in, _stdout
    text = out.getvalue().strip()
    return json.loads(text) if text.startswith("{") else text


def hso(result):
    return (result or {}).get("hookSpecificOutput", {}) if isinstance(result, dict) else {}


def decision(result):
    return hso(result).get("permissionDecision")


def reason(result):
    return hso(result).get("permissionDecisionReason") or ""


def bash(root, command, event="PreToolUse", sid="s1", tool="Bash", response=None):
    p = {"hook_event_name": event, "tool_name": tool, "cwd": root, "session_id": sid,
         "tool_input": {"command": command}}
    if response is not None:
        p["tool_response"] = response
    return p


def file_tool(root, tool, path, sid="s1", event="PreToolUse", **tool_input):
    """A Write / Edit / MultiEdit / NotebookEdit payload, the way the harness sends one."""
    return {"hook_event_name": event, "tool_name": tool, "cwd": root, "session_id": sid,
            "tool_input": dict(tool_input, file_path=path)}


def write_text(path, text):
    """A fixture file with its bytes exactly as given (no newline translation)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def band_pcts(gate):
    """Percentages a few points INSIDE the PACE and STOP bands, read from the thresholds.

    ⛔ NEVER A TYPED NUMBER. Four cases here called `usage_at(75)` to mean "a PACE", which was
    `soft_pct_5h` exactly - so raising the defaults to 80/90 on 2026-09-18 turned every one of
    them into a GO, and the cases failed with a bare `AssertionError: GO` on a verdict they
    were not testing. A fixture that encodes a threshold breaks the next time the owner moves
    it, and it breaks in the test rather than in whatever was actually wrong.

    ⚠ INSIDE, not ON, the edge: `soft_pct_5h` itself is PACE today, but a fixture sitting
    exactly on a boundary cannot survive the boundary moving by one.
    """
    d = gate.usage.DEFAULTS
    return d["soft_pct_5h"] + 2, d["hard_pct_5h"] + 5


def stamp_session(gate, sdir, sid="s1"):
    """Mark the session as started - without this every guard is advisory, by design."""
    os.makedirs(os.path.join(sdir, "state"), exist_ok=True)
    with open(gate.state_path(sdir, sid, "start"), "w", encoding="utf-8") as f:
        f.write("1")


def gitlog(root):
    p = os.path.join(root, ".claude", "dispatch_gate.log")
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def usage_state_dir():
    """The REAL state directory, resolved in a subprocess so no in-process stub reaches it.

    ⚠ `load_gate()` replaces `usage.state_dir` on the imported module, which is exactly
    what the other cases need and exactly what would hide the pollution this asks about.
    """
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, r'%s'); import usage; print(usage.state_dir([]))"
         % repo_path("hooks")],
        capture_output=True, text=True)
    return (out.stdout or "").strip()


def statelog(sdir):
    """The gate log's copy in the STATE directory - the one that cannot move.

    ⛔ `gitlog()` reads `<root>/.claude/dispatch_gate.log`, and `root` follows the payload's
    cwd in a project with no CLAUDE.md, AGENTS.md or .git. Measured 2026-09-01: one session's
    log arrived as four fragments in four directories. This copy is what makes "did the guard
    fire?" answerable in one place.
    """
    try:
        with open(os.path.join(sdir, "dispatch_gate.log"), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def git(root, *args):
    return subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True)


@contextlib.contextmanager
def project_cfg(root, **dispatch):
    """`<root>/.claude/dispatch-guard.json` for the duration of a block, then removed."""
    cfgdir = os.path.join(root, ".claude")
    os.makedirs(cfgdir, exist_ok=True)
    path = os.path.join(cfgdir, "dispatch-guard.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"dispatch": dispatch}, f)
    try:
        yield path
    finally:
        if os.path.exists(path):
            os.remove(path)


def load_skills(gate, root, sid, *names):
    """Invoke skills the way a session does - a real PostToolUse Skill payload each time.

    ⭐ Driven rather than written straight to disk. The mark's filename is an implementation
    detail; what these checks depend on is that a Skill CALL records it, and writing the file
    myself would test my own understanding of the name instead of the wiring.
    """
    for name in names:
        run_gate(gate, {"hook_event_name": "PostToolUse", "tool_name": "Skill",
                        "cwd": root, "session_id": sid, "tool_input": {"skill": name}})


def fixture_repo(d, branch="master"):
    """A real repository with a real branch and no commits. See the module docstring."""
    git(d, "init", "-q")
    # ⚠ `git init -b` needs git 2.28. symbolic-ref works everywhere and says the same thing.
    git(d, "symbolic-ref", "HEAD", "refs/heads/%s" % branch)
    return d


# --------------------------------------------------------------------------------- cases

def case_add_all(gate, sdir, root):
    """`git add -A`, and the mutation check that proves this case tests THAT guard."""
    import cmd_guards
    payload = bash(root, "git add -A")
    r = run_gate(gate, payload)
    assert decision(r) == "deny", r
    assert "by name" in reason(r).lower(), reason(r)
    assert "CMD-DENY(guard_add_all)" in gitlog(root), gitlog(root)[-400:]

    # ⭐ MUTATION: delete the guard, drive the same payload, the refusal must disappear.
    keep = cmd_guards.GUARDS
    cmd_guards.GUARDS = tuple(g for g in keep if g[0] != "guard_add_all")
    try:
        assert decision(run_gate(gate, payload)) is None, "removing the guard changed nothing"
    finally:
        cmd_guards.GUARDS = keep
    assert decision(run_gate(gate, payload)) == "deny", "the guard did not come back"

    # Other spellings of the same act.
    for cmd in ("git add .", "git add --all", "git -C . add -A", "git add -Av"):
        assert decision(run_gate(gate, bash(root, cmd))) == "deny", cmd
    # ...and a named path must NOT be refused. `./x.py` starts with a dot and is not `.`.
    for cmd in ("git add hooks/cmd_guards.py", "git add ./one.py", "git add -p"):
        assert decision(run_gate(gate, bash(root, cmd))) is None, cmd
    print("ok - git add -A refused, named paths allowed, mutation-checked")


def case_commit_m(gate, sdir, root):
    import cmd_guards
    payload = bash(root, 'git commit -m "hello (world)"')
    r = run_gate(gate, payload)
    assert decision(r) == "deny", r
    assert "-F" in reason(r), reason(r)
    keep = cmd_guards.GUARDS
    cmd_guards.GUARDS = tuple(g for g in keep if g[0] != "guard_commit_message_file")
    try:
        assert decision(run_gate(gate, payload)) is None, "mutation left the refusal standing"
    finally:
        cmd_guards.GUARDS = keep
    assert decision(run_gate(gate, bash(root, "git commit -am x"))) == "deny", "-am"
    # ⚠ `--amend` contains an m and must not match; `-F` is the form being asked for.
    for cmd in ("git commit -F msg.txt", "git commit --amend --no-edit", "git commit -F m --amend"):
        assert decision(run_gate(gate, bash(root, cmd))) is None, cmd
    print("ok - git commit -m refused, -F and --amend allowed, mutation-checked")


def case_branch(gate, sdir, root):
    """The one that caused real damage - including the CHAINED form that hid it."""
    import cmd_guards
    ctx = gate.guard_ctx(root, sdir, "s1", gate.gate_config(root, sdir))
    assert cmd_guards.record_branch(ctx) == "master", "the fixture is not on master"

    # Another session moves the shared working tree under this one.
    git(root, "symbolic-ref", "HEAD", "refs/heads/theirs")
    assert cmd_guards.current_branch(root) == "theirs", "the fixture did not switch"

    # ⛔ THE CHAINED FORM, which is how it actually happened: the branch name printed,
    # scrolled past, and `&&` carried on because the previous command had SUCCEEDED.
    chained = "git rev-parse --abbrev-ref HEAD && git commit -F m.txt"
    r = run_gate(gate, bash(root, chained))
    assert decision(r) == "deny", r
    assert "master" in reason(r) and "theirs" in reason(r), reason(r)
    assert "clone" in reason(r), "the refusal must name the repair"
    # ⛔ AND NOT THE OPPOSITE REPAIR. Until 0.62.0 this message ended "each one needs its own
    # worktree" - the reverse of the owner's rule ("no worktree workaround") and of the cowork
    # skill shipped beside it ("do not give each session its own copy of the work"). One
    # plugin, two right rules, is cowork's own catalogued failure. ADR 20260919-204317, D9.
    assert "own worktree" not in reason(r), "the refusal sends agents to worktrees again"
    assert r.get("systemMessage"), "this one has to reach the person too"
    # A bare commit is refused for the same reason.
    assert decision(run_gate(gate, bash(root, "git commit -F m.txt"))) == "deny"

    keep = cmd_guards.GUARDS
    cmd_guards.GUARDS = tuple(g for g in keep if g[0] != "guard_commit_branch")
    try:
        assert decision(run_gate(gate, bash(root, chained))) is None, "mutation left it standing"
    finally:
        cmd_guards.GUARDS = keep

    # ⭐ CRITERION 3: a branch THIS SESSION chose is legitimate. PostToolUse re-asks git
    # after a checkout, so the record follows the session's own decision.
    git(root, "symbolic-ref", "HEAD", "refs/heads/mine")
    run_gate(gate, bash(root, "git switch -c mine", event="PostToolUse"))
    assert cmd_guards._read(cmd_guards.branch_mark(ctx)) == "mine", "the record did not follow"
    assert decision(run_gate(gate, bash(root, "git commit -F m.txt"))) is None, \
        "refused a commit on the branch the session itself selected"
    print("ok - wrong branch refused (chained too), own checkout allowed, mutation-checked")


def case_silenced_search(gate, sdir, root):
    import cmd_guards
    payload = bash(root, "grep -rn needle . 2>/dev/null")
    r = run_gate(gate, payload)
    assert decision(r) == "deny", r
    assert "filter afterwards" in reason(r), reason(r)
    keep = cmd_guards.GUARDS
    cmd_guards.GUARDS = tuple(g for g in keep if g[0] != "guard_silenced_search")
    try:
        assert decision(run_gate(gate, payload)) is None, "mutation left the refusal standing"
    finally:
        cmd_guards.GUARDS = keep

    for cmd in ("timeout 40 grep -rn x . 2>/dev/null",     # a wrapper must not hide it
                "PYTHONIOENCODING=utf-8 grep x y 2>/dev/null",
                "find . -name '*.py' 2>/dev/null",
                "ls -la nosuch 2>$null",                   # the PowerShell spelling
                "git grep -q needle 2>/dev/null",
                "grep -s needle file",
                "rg --no-messages needle",
                "cat a | grep x 2>/dev/null"):
        assert decision(run_gate(gate, bash(root, cmd))) == "deny", cmd
    # ⚠ `rg -s` is --case-sensitive and silences NOTHING. Refusing it would be wrong, and a
    # guard that refuses correct commands is a guard the owner switches off.
    for cmd in ("rg -s needle", "grep -rn needle .", "curl -s http://x",
                "python x.py 2>/dev/null"):
        assert decision(run_gate(gate, bash(root, cmd))) is None, cmd
    print("ok - silenced searches refused, `rg -s` and non-searches allowed, mutation-checked")


def case_relative_cd(gate, sdir, root):
    """A warning, not a refusal - and it must carry NO permission decision at all."""
    import cmd_guards
    r = run_gate(gate, bash(root, "cd Tools && python Debug/test_all.py"))
    assert decision(r) is None, "a warning must not decide the permission: %r" % (r,)
    assert "RELATIVE" in hso(r).get("additionalContext", ""), r
    # ⚠ AND NO systemMessage, deliberately. `cd x && …` is ordinary, the agent is the one who
    # can act on the warning, and a screen line on every routine correction teaches the owner
    # to ignore the one channel a model cannot suppress. Only the branch refusal and the
    # unattended refusal earn that channel - each says something only a PERSON can fix.
    assert not r.get("systemMessage"), "a routine warning must not spend the screen channel"
    assert "CMD-WARN(guard_relative_cd)" in gitlog(root)
    keep = cmd_guards.GUARDS
    cmd_guards.GUARDS = tuple(g for g in keep if g[0] != "guard_relative_cd")
    try:
        r2 = run_gate(gate, bash(root, "cd Tools && python x.py"))
        assert not hso(r2).get("additionalContext"), "mutation left the warning standing"
    finally:
        cmd_guards.GUARDS = keep
    # A bare `cd`, an absolute path and a `cd -` are not the failure this describes.
    for cmd in ("cd Tools", "cd /tmp && ls", "cd C:/WorkSpace && ls", "cd ~ && ls",
                "cd - && ls"):
        assert not hso(run_gate(gate, bash(root, cmd))).get("additionalContext"), cmd
    print("ok - relative cd warns without deciding, mutation-checked")


def case_switches_and_logging(gate, sdir, root):
    """Criteria 4 and 6: every decision is logged, and one key turns each guard off."""
    cfgdir = os.path.join(root, ".claude")
    os.makedirs(cfgdir, exist_ok=True)
    cfgfile = os.path.join(cfgdir, "dispatch-guard.json")
    with open(cfgfile, "w", encoding="utf-8") as f:
        json.dump({"dispatch": {"guard_add_all": False}}, f)
    try:
        r = run_gate(gate, bash(root, "git add -A"))
        assert decision(r) is None, "the config key did not switch the guard off: %r" % (r,)
        # ⭐ RUN EVEN WHEN OFF, so the log says what the off switch cost. A disabled guard
        # that leaves no trace is indistinguishable from a guard that never ran.
        assert "CMD-DISABLED(guard_add_all)" in gitlog(root), gitlog(root)[-400:]
        # ...and the off-list is on the allow line, so a quiet disabled guard is visible too.
        run_gate(gate, bash(root, "echo hello"))
        assert "off=guard_add_all" in gitlog(root), gitlog(root)[-400:]
    finally:
        os.remove(cfgfile)
    # Criterion 4: an ordinary command leaves an allow line naming how many guards ran.
    before = len(gitlog(root))
    run_gate(gate, bash(root, "echo hello"))
    tail = gitlog(root)[before:]
    assert "CMD-ALLOW(checked=" in tail and "off=-" in tail, tail

    # ⛔ AND EVERY LINE ALSO REACHES THE STATE DIRECTORY, which never moves. `root` follows
    # the payload's cwd in a project with no CLAUDE.md, AGENTS.md or .git, so the per-repo
    # copy can scatter - measured 2026-09-01, four fragments from one session in OLD_Books,
    # and the hour that mattered looked empty in the one place anybody would look.
    sbefore = len(statelog(sdir))
    run_gate(gate, bash(root, "echo state-copy-probe"))
    stail = statelog(sdir)[sbefore:]
    assert "CMD-ALLOW(checked=" in stail, "the state copy missed the line: %r" % (stail[-200:],)
    # ⭐ A MOVED ROOT MUST NOT COST THE STATE COPY. This is the whole point: same session,
    # a cwd that resolves somewhere else, and the fixed copy still receives it.
    moved = os.path.join(root, "sub", "deeper")
    os.makedirs(moved, exist_ok=True)
    sbefore = len(statelog(sdir))
    run_gate(gate, bash(moved, "echo moved-root-probe"))
    assert "CMD-ALLOW(checked=" in statelog(sdir)[sbefore:], \
        "a moved root lost the state copy: %r" % (statelog(sdir)[-200:],)
    print("ok - each guard has its own switch, allow/deny/disabled log, and the state copy holds")


def case_fail_open(gate, sdir, root):
    """Criterion 5: a guard that RAISES blocks nothing, and still leaves a trace."""
    import cmd_guards

    def explode(payload, ctx, segs):
        raise RuntimeError("deliberate")

    keep = cmd_guards.GUARDS
    cmd_guards.GUARDS = (("guard_add_all", explode),) + tuple(
        g for g in keep if g[0] != "guard_add_all")
    try:
        before = len(gitlog(root))
        r = run_gate(gate, bash(root, "git add -A"))
        assert decision(r) is None, "a broken guard must not block work: %r" % (r,)
        tail = gitlog(root)[before:]
        assert "CMD-GUARD-ERROR(guard_add_all)" in tail, tail
        assert "deliberate" in tail, tail
    finally:
        cmd_guards.GUARDS = keep
    print("ok - a guard that raises allows the command and logs it")


def case_advisory_without_stamp(gate, sdir, root):
    """A session that began before this version was installed is advisory only."""
    before = len(gitlog(root))
    r = run_gate(gate, bash(root, "git add -A", sid="never-stamped"))
    assert decision(r) is None, "an unstamped session must not be policed: %r" % (r,)
    tail = gitlog(root)[before:]
    assert "CMD-ADVISORY(no-session-stamp)" in tail, tail
    print("ok - an unstamped session is advisory, and says so in the log")


def case_append_only(gate, sdir, root):
    """cowork rule 3 as a gate: a file that declares itself append-only may only GROW.

    ⭐ THE FILE DECLARES ITSELF - first heading or `<!-- append-only -->`, never body text: the
    loose rule marked the skill's own SKILL.md and the ADR that proposed it (measured over
    21 979 files, 2026-09-19). ⛔ MUTATION-CHECKED both ways: the guard is removed from BOTH
    tables and the same payloads are driven again; a refusal that survives was not this guard.
    """
    import cmd_guards
    sid = "s-append"
    stamp_session(gate, sdir, sid)
    d = os.path.join(root, "board")
    board = os.path.join(d, "BOARD.md")
    body = ("# Claims board (append-only)\n\nrules\n\n---\n[10:00][S1] took A\n---\n"
            "[10:05][S2] took B\n---\n")
    write_text(board, body)
    plain = os.path.join(d, "notes.md")
    write_text(plain, "# Notes\n\nThis body mentions an append-only board.\n\n---\nend\n")
    commented = os.path.join(d, "log.md")
    write_text(commented, "<!-- append-only -->\n# Log\nfirst\n")

    def ft(tool, path, s=sid, **ti):
        return run_gate(gate, file_tool(root, tool, path, sid=s, **ti))

    # -- the marker rule: a heading or the comment marks; body text does not.
    assert cmd_guards.append_only_marker(board) == "# Claims board (append-only)"
    assert cmd_guards.append_only_marker(commented) == "<!-- append-only -->"
    assert cmd_guards.append_only_marker(plain) is None, "body text must not mark a file"
    # ⛔ AND A DOCUMENT THAT MENTIONS THE COMMENT INLINE IS NOT MARKED. The installed 0.63.0 hook
    # refused an Edit of skills/cowork/SKILL.zh-TW.md because its rule 3 says `<!-- append-only -->`
    # in backticks inside the first 2 KB. The comment has to stand on a line of its own.
    doc = os.path.join(d, "doc.md")
    write_text(doc, "# How the marker works\n\nA record carries `<!-- append-only -->` on a line "
                    "of its own, or says append-only in its first heading.\n")
    assert cmd_guards.append_only_marker(doc) is None, \
        "a document describing the marker inline was marked: %r" % (cmd_guards.append_only_marker(doc),)
    write_text(doc, "# Notes\n  <!-- append-only -->  \nbody\n")
    assert cmd_guards.append_only_marker(doc) == "<!-- append-only -->", \
        "an own-line comment with surrounding spaces was not marked"
    assert cmd_guards.append_only_marker(os.path.join(d, "missing.md")) is None

    # -- Write: create, append (LF and CRLF) allowed; a rewrite refused; unmarked untouched.
    r = ft("Write", os.path.join(d, "fresh.md"), content="# Fresh (append-only)\n")
    assert decision(r) is None, "creating a file is an append: %r" % (r,)
    before = len(gitlog(root))
    r = ft("Write", board, content=body + "---\n[10:10][S3] took C\n")
    assert decision(r) is None, "Write-as-append refused: %r" % (reason(r),)
    assert "CMD-ALLOW(checked=2" in gitlog(root)[before:], \
        "the file-tool guards did not run: %r" % (gitlog(root)[-200:],)
    r = ft("Write", board, content=body.replace("\n", "\r\n") + "---\r\n[10:10][S3] took C\r\n")
    assert decision(r) is None, "a CRLF re-encoding refused a legitimate append: %r" % (reason(r),)
    r = ft("Write", board, content=body.replace("took A", "took A (fixed)"))
    assert decision(r) == "deny", "a Write that rewrites an earlier entry was allowed"
    assert "append-only" in reason(r) and "inherits the marker" in reason(r), reason(r)
    assert r.get("systemMessage"), "the person should see the refusal"
    r = ft("Write", plain, content="# Notes\nrewritten\n")
    assert decision(r) is None, "an unmarked file was policed: %r" % (reason(r),)

    # -- Edit: an append with or without the trailing newline; anything else refused.
    tail = "[10:05][S2] took B\n---\n"
    before = len(gitlog(root))
    r = ft("Edit", board, old_string=tail, new_string=tail + "[10:10][S3] took C\n---\n")
    assert decision(r) is None, "Edit-as-append refused: %r" % (reason(r),)
    assert "CMD-ALLOW(checked=2" in gitlog(root)[before:], "the Edit guards did not run"
    r = ft("Edit", board, old_string=tail.rstrip(), new_string=tail.rstrip() + "\n[10:10][S3] took C\n---")
    assert decision(r) is None, "Edit-as-append without its newline refused: %r" % (reason(r),)
    r = ft("Edit", board, old_string="took A", new_string="took A (fixed)")
    assert decision(r) == "deny", "an Edit in the middle was allowed"
    r = ft("Edit", board, old_string="---", new_string="---\n[10:10][S3] took C\n---",
           replace_all=True)
    assert decision(r) == "deny", "replace_all on a repeated anchor was allowed"
    assert "occurs" in reason(r) and "anchor" in reason(r), reason(r)
    # ⛔ AND WITHOUT replace_all. The Edit tool edits ONE occurrence and the guard cannot tell
    # which; the tool's own rule is that old_string must be unique, so refusing here can never
    # refuse an Edit the tool would perform. Review A (F3) measured the first version allowing it.
    r = ft("Edit", board, old_string="---", new_string="---\n[10:10][S3] took C\n---")
    assert decision(r) == "deny", "a repeated anchor without replace_all was allowed"
    r = ft("Edit", board, old_string=tail, new_string="[10:05][S2] took C\n---\n")
    assert decision(r) == "deny", "rewriting the anchor itself was allowed"
    # ⛔ THE RAW ANCHOR IS COUNTED, as the tool counts it (review C, c1): here `---\n` occurs
    # once raw although `---` occurs twice rstripped, and the tool WOULD perform this Edit.
    sub = os.path.join(d, "sub.md")
    write_text(sub, "# Sub (append-only)\nsee A---B\nfoo\n---\n")
    r = ft("Edit", sub, old_string="---\n", new_string="---\nnext\n---\n")
    assert decision(r) is None, "an anchor the tool finds once was refused: %r" % (reason(r),)
    # ⭐ A YAML frontmatter block is skipped: its `# comment` is not the file's first heading.
    fm = os.path.join(d, "fm.md")
    write_text(fm, "---\ntitle: x\n# a yaml comment, append-only in passing\n---\n# Notes\nbody\n")
    assert cmd_guards.append_only_marker(fm) is None, "a frontmatter comment marked the file"
    write_text(fm, "---\ntitle: x\n---\n# Log (append-only)\nbody\n")
    assert cmd_guards.append_only_marker(fm) == "# Log (append-only)", "H1 after frontmatter missed"
    # ⛔ ... but a Markdown horizontal rule on line 1 is NOT frontmatter (review C, e1): the
    # first version ate the rule, the marked H1 and the next `---` together.
    write_text(fm, "---\n# Board (append-only)\nentry\n---\nentry\n---\n")
    assert cmd_guards.append_only_marker(fm) == "# Board (append-only)", \
        "a leading horizontal rule hid the marked heading"
    # ⛔ ... and frontmatter that BEGINS with a `# comment` IS still frontmatter (review D, D7):
    # the key-on-line-2 rule read the comment as the file's first heading, both ways.
    write_text(fm, "---\n# generated, append-only in passing\ntitle: x\n---\n# Notes\nbody\n")
    assert cmd_guards.append_only_marker(fm) is None, "a comment-first frontmatter marked the file"
    write_text(fm, "---\n# generated\ntitle: x\n---\n# Log (append-only)\nbody\n")
    assert cmd_guards.append_only_marker(fm) == "# Log (append-only)", \
        "a comment-first frontmatter hid the marked heading"
    # ⛔ THE ONE RAW OCCURRENCE MUST BE AT THE END (review D, D2): the last line repeats an
    # earlier line's text but lacks its newline, so the raw count is 1 - for the EARLIER copy.
    mid = os.path.join(d, "mid.md")
    write_text(mid, "# Mid (append-only)\n[S1] took B\n---\n[S2] took B\n---")
    r = ft("Edit", mid, old_string="took B\n---\n", new_string="took B\n---\n[S3] took C\n---\n")
    assert decision(r) == "deny" and "not at the end" in reason(r), \
        "a mid-file insertion via a raw-unique anchor was allowed: %r" % (reason(r),)
    # -- MultiEdit: a single trailing append passes; an earlier edit anywhere does not.
    grow = {"old_string": "took B\n---", "new_string": "took B\n---\n[10:10][S3] took C\n---"}
    assert decision(ft("MultiEdit", board, edits=[grow])) is None
    assert decision(ft("MultiEdit", board,
                       edits=[grow, {"old_string": "took A", "new_string": "took Z"}])) == "deny"
    # -- a shape the rule cannot judge is allowed, and says so.
    before = len(gitlog(root))
    assert decision(ft("NotebookEdit", board, new_source="x")) is None
    assert "shape not judged" in gitlog(root)[before:], gitlog(root)[-300:]

    # -- the shell: every truncating / in-place / removing shape refused BY THIS GUARD. ⛔ The
    # reason is asserted too, not only the decision: review A (F8) measured that a `deny` alone
    # could come from any guard, and only one of these shapes was mutation-checked.
    rel = "board/BOARD.md"
    spaced = os.path.join(d, "board dir", "BOARD.md")
    write_text(spaced, body)
    for cmd in ("echo x > %s" % rel, "echo x >%s" % rel, "sed -i 's/a/b/' %s" % rel,
                "cat new.md | tee %s" % rel, "rm %s" % rel, "cp new.md %s" % rel,
                "mv new.md %s" % rel, "truncate -s 0 %s" % rel,
                "Set-Content -Path %s 'x'" % rel, "Out-File %s" % rel,
                "Clear-Content %s" % rel, "Remove-Item %s" % rel,
                "echo x > 'board/BOARD.md'", "echo x 2> %s" % rel,
                # review A: F1 (a quoted path WITH a space - the case quotes exist for), F2 (a
                # `cd` in the same command), F4 (-Value first), F5 (mv SOURCE is a removal)
                'echo x > "board/board dir/BOARD.md"', "echo x >'board/board dir/BOARD.md'",
                "cd board && echo x > BOARD.md", "Set-Content -Value x %s" % rel,
                "mv %s board/old.md" % rel,
                # review C: b1 (a QUOTED cd target WITH A SPACE - the F1 shape again; review D
                # measured the earlier fixture `cd "board"` passing under the OLD regex, so it
                # pinned nothing), d2 (PowerShell moves)
                'cd "board/board dir" && echo x > BOARD.md', "Move-Item %s board/old.md" % rel,
                "Rename-Item -Path %s -NewName old.md" % rel, "Copy-Item new.md %s" % rel,
                # review D: D1 (positional source + named parameter - the ordinary spelling),
                # D3 (two cds in sequence), D4 (uppercase and the PowerShell spellings)
                "Rename-Item %s -NewName old.md" % rel, "Move-Item %s -Destination board/old.md" % rel,
                "cd board && cd .. && echo x > %s" % rel, "CD board && echo x > BOARD.md",
                "Set-Location board && echo x > BOARD.md", "sl board && echo x > BOARD.md"):
        r = run_gate(gate, bash(root, cmd, sid=sid))
        assert decision(r) == "deny", "shell rewrite allowed: %r -> %r" % (cmd, reason(r))
        assert "declares itself append-only" in reason(r), \
            "refused, but not by guard_append_only: %r -> %r" % (cmd, reason(r))
    # ... and every append, read, copy-OUT, other-file or quoted-prose shape allowed - and the
    # guard RAN (the allow line names how many guards were checked).
    for cmd in ("echo x >> %s" % rel, "cat new.md | tee -a %s" % rel, "Add-Content %s 'x'" % rel,
                "Out-File -Append %s" % rel, "cp %s board/before.md" % rel,
                "grep append-only %s > count.txt" % rel, "sed -i 's/a/b/' board/notes.md",
                "echo x > board/notes.md", "cat %s" % rel,
                "echo 'use > BOARD.md to redirect' >> board/notes.md", "rm -rf board/tmpdir"):
        before = len(gitlog(root))
        r = run_gate(gate, bash(root, cmd, sid=sid))
        assert decision(r) is None, "innocent command refused: %r -> %r" % (cmd, reason(r))
        assert "CMD-ALLOW(checked=" in gitlog(root)[before:], "the guards did not run: %r" % (cmd,)
    # An append behind a `cd` is allowed too - but the relative-cd guard WARNS on it, so the
    # log line is CMD-WARN, not CMD-ALLOW; the assertion is that append-only stayed silent.
    r = run_gate(gate, bash(root, "cd board && echo x >> BOARD.md", sid=sid))
    assert decision(r) is None and "append-only" not in reason(r), reason(r)
    # ⛔ AND THE cd TARGET REPLACES THE BASE, it is not tried beside it (review C, b2): from
    # `sub`, BOARD.md is a file the command never touches, so no refusal.
    os.makedirs(os.path.join(root, "sub"), exist_ok=True)
    write_text(os.path.join(root, "BOARD.md"), body)
    r = run_gate(gate, bash(root, "cd sub && echo x > BOARD.md", sid=sid))
    assert decision(r) is None and "append-only" not in reason(r), \
        "refused on a file in the cwd that the command never touches: %r" % (reason(r),)
    os.remove(os.path.join(root, "BOARD.md"))
    # ⛔ AND TWO cds IN SEQUENCE (review D, D3): from `board` then `..`, BOARD.md is the cwd's,
    # which does not exist here - so no refusal on board/BOARD.md, a file never touched.
    r = run_gate(gate, bash(root, "cd board && cd .. && echo x > BOARD.md", sid=sid))
    assert decision(r) is None and "append-only" not in reason(r), \
        "the second cd was ignored and a file the command never touches was refused: %r" % (reason(r),)
    # Allowed controls for the PowerShell moves: copying or moving OUT, and a rename of a
    # different file, must pass (review D's fix-prototype controls).
    for cmd in ("Copy-Item %s -Destination board/before2.md" % rel,
                "Rename-Item board/notes.md -NewName notes2.md",
                "Move-Item new.md -Destination other.md -Force"):
        r = run_gate(gate, bash(root, cmd, sid=sid))
        assert decision(r) is None, "innocent PowerShell command refused: %r -> %r" % (cmd, reason(r))
    # -- a token the gate cannot expand is allowed and named as an allow in the log.
    before = len(gitlog(root))
    assert decision(run_gate(gate, bash(root, "echo x > $OUT/BOARD.md", sid=sid))) is None
    assert "CMD-ALLOW(guard_append_only unresolved)" in gitlog(root)[before:], gitlog(root)[-300:]

    # -- its own switch, both halves, leaves a trace.
    with project_cfg(root, guard_append_only=False):
        before = len(gitlog(root))
        assert decision(run_gate(gate, bash(root, "echo x > %s" % rel, sid=sid))) is None, \
            "the key did not switch the shell half off"
        assert "CMD-DISABLED(guard_append_only)" in gitlog(root)[before:], gitlog(root)[-300:]
        before = len(gitlog(root))
        assert decision(ft("Write", board, content="rewritten")) is None, \
            "the key did not switch the file-tool half off"
        assert "CMD-DISABLED(guard_append_only)" in gitlog(root)[before:], gitlog(root)[-300:]
    # -- advisory when unstamped, for the file tools too.
    before = len(gitlog(root))
    assert decision(ft("Write", board, s="never-stamped-2", content="rewritten")) is None
    assert "CMD-ADVISORY(no-session-stamp) Write" in gitlog(root)[before:], gitlog(root)[-300:]
    # -- fail open: a guard that raises allows the call and logs it.
    keep_marker = cmd_guards.append_only_marker

    def explode(_path):
        raise RuntimeError("deliberate")

    cmd_guards.append_only_marker = explode
    try:
        before = len(gitlog(root))
        assert decision(ft("Write", board, content="rewritten")) is None, "a broken guard blocked"
        assert "CMD-GUARD-ERROR(guard_append_only)" in gitlog(root)[before:], gitlog(root)[-300:]
    finally:
        cmd_guards.append_only_marker = keep_marker

    # ⛔ MUTATION: remove the guard from BOTH tables and the refusals must vanish.
    keep_g, keep_f = cmd_guards.GUARDS, cmd_guards.FILE_GUARDS
    cmd_guards.GUARDS = tuple(g for g in keep_g if g[0] != "guard_append_only")
    cmd_guards.FILE_GUARDS = tuple(g for g in keep_f if g[0] != "guard_append_only")
    try:
        assert decision(run_gate(gate, bash(root, "echo x > %s" % rel, sid=sid))) is None, \
            "mutation left the shell refusal standing - another guard refused it"
        assert decision(ft("Write", board, content="rewritten")) is None, \
            "mutation left the Write refusal standing - another guard refused it"
    finally:
        cmd_guards.GUARDS, cmd_guards.FILE_GUARDS = keep_g, keep_f
    assert decision(ft("Write", board, content="rewritten")) == "deny", "the guard did not come back"
    print("ok - an append-only file may only grow: Write/Edit/MultiEdit and 29 shell shapes "
          "refused, appends allowed, off switch and fail-open logged, mutation-checked")


def case_cowork_first(gate, sdir, root):
    """cowork rules 1-2 as a nag: a session that shares this tree with a LIVE peer loads the
    skill before its first write or commit - once per session.

    ⚠ THE HARNESS MARKS `s1` AS HAVING SEEN THE SKILL (see main()), because the fixture's own
    sessions are peers of one another and every other case assumes only the guard under test
    can refuse a commit. This case therefore uses its OWN session ids, and states the default
    (on) explicitly through a project config so the off-switch half reads beside it.
    ⛔ MUTATION: the live peer is removed and the same write must go through - proving the
    refusal came from the peer test and not from somewhere else.
    """
    import cmd_guards

    def peer(psid, cwd, age=0):
        """A peer: a JSON .start with that cwd, an .alive `age` seconds old."""
        with open(gate.state_path(sdir, psid, "start"), "w", encoding="utf-8") as f:
            json.dump({"at": time.time(), "cwd": cwd}, f)
        alive = gate.state_path(sdir, psid, "alive")
        with open(alive, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
        os.utime(alive, (time.time() - age, time.time() - age))

    sid = "s-cowork"
    stamp_session(gate, sdir, sid)
    target = os.path.join(root, "shared.md")

    def write(s=sid):
        return run_gate(gate, file_tool(root, "Write", target, sid=s, content="x\n"))

    with project_cfg(root, guard_cowork_first=True):
        assert decision(write()) is None, "no peer, yet it nagged: %r" % (reason(write()),)
        # a live peer in ANOTHER repository does not count (its root resolves elsewhere).
        peer("p-elsewhere", os.path.join(sdir, "other-root"))
        assert decision(write()) is None, "a peer in another repository counted"
        # a STALE peer in this repository does not count.
        peer("p-stale", root, age=cmd_guards.PEER_ALIVE_MIN * 60 + 60)
        assert decision(write()) is None, "a stale heartbeat counted as live"
        # ⭐ a live peer started in a SUBDIRECTORY, with the drive letter in the OTHER case -
        # 3 of 118 real .start files spell it differently (measured 2026-09-19).
        flipped = (root[0].swapcase() + root[1:]) if root[1:2] == ":" else root
        peer("p-live", os.path.join(flipped, "sub", "dir"))
        before = len(gitlog(root))
        r = write()
        assert decision(r) == "deny", "a live peer in this repository did not trigger: %r" % (r,)
        assert "cowork" in reason(r) and "1 other live session" in reason(r), reason(r)
        assert r.get("systemMessage"), "the person should know the first write was refused"
        assert "CMD-DENY(guard_cowork_first)" in gitlog(root)[before:], gitlog(root)[-300:]
        # ⭐ THE EVIDENCE LINE CARRIES THIS SESSION'S ID (0.63.2). Review 02 measured the first
        # draft of the fix passing this case with `sid=` removed from both log lines - the
        # behaviour was right and nothing pinned it. `cowork_nag_report.py` pairs a refusal with
        # the skill load that answered it BY THIS ID, so the id has to be on both lines.
        evidence = gitlog(root)[before:]
        assert "COWORK-PEERS sid=%s mine=" % sid[:8] in evidence, evidence[-400:]
        assert "p-live:alive=" in evidence, evidence[-400:]
        # ⚠ ONCE.
        assert decision(write()) is None, "it refused twice: %r" % (reason(write()),)
        # `git commit` is the shell trigger, for a fresh session.
        sid2 = "s-cowork-commit"
        stamp_session(gate, sdir, sid2)
        r = run_gate(gate, bash(root, "git commit -F m.txt", sid=sid2))
        assert decision(r) == "deny" and "cowork" in reason(r), reason(r)
        # the skill seen -> silent.
        # ⚠ its first 8 characters differ from `sid`'s, or the sid assertion below cannot tell
        # this session's SKILL-SEEN line from one written for the first session.
        sid3 = "s-loaded-cowork"
        assert sid3[:8] != sid[:8]
        stamp_session(gate, sdir, sid3)
        before = len(gitlog(root))
        load_skills(gate, root, sid3, "dispatch-guard:cowork")
        assert "SKILL-SEEN dispatch-guard:cowork sid=%s" % sid3[:8] in gitlog(root)[before:], \
            gitlog(root)[before:][-400:]
        assert decision(write(sid3)) is None, "the Skill call was ignored"
    # its off switch logs, and does NOT spend the one refusal.
    sid4 = "s-cowork-off"
    stamp_session(gate, sdir, sid4)
    with project_cfg(root, guard_cowork_first=False):
        before = len(gitlog(root))
        assert decision(write(sid4)) is None, "the key did not switch it off"
        assert "CMD-DISABLED(guard_cowork_first)" in gitlog(root)[before:], gitlog(root)[-300:]
        assert not os.path.exists(gate.state_path(sdir, sid4, "cowork-nagged")), \
            "it burned its one refusal while switched off"
    with project_cfg(root, guard_cowork_first=True):
        r = write(sid4)
        assert decision(r) == "deny" and "cowork" in reason(r), \
            "switching back on did not restore THIS guard's refusal: %r" % (reason(r),)
        # advisory when unstamped.
        before = len(gitlog(root))
        assert decision(write("never-stamped-3")) is None
        assert "CMD-ADVISORY(no-session-stamp)" in gitlog(root)[before:], gitlog(root)[-300:]
        # ⛔ MUTATION: take the live peer away; a fresh session must not be nagged.
        sid5 = "s-cowork-mut"
        stamp_session(gate, sdir, sid5)
        os.remove(gate.state_path(sdir, "p-live", "alive"))
        assert decision(write(sid5)) is None, "without a live peer the nag still fired"
        # cost, measured and printed - the ADR says milliseconds, so say the number.
        ctx = gate.guard_ctx(root, sdir, sid5, gate.gate_config(root, sdir))
        t0 = time.perf_counter()
        cmd_guards.peer_sessions(ctx)
        ms = (time.perf_counter() - t0) * 1000
        n_state = len(os.listdir(os.path.join(sdir, "state")))
        assert ms < 500, "peer_sessions() took %.0f ms over %d state files" % (ms, n_state)
        print("   peer_sessions() over %d state files: %.1f ms" % (n_state, ms))
    print("ok - a live peer in this repository nags once (drive-letter case ignored), another "
          "repository / a stale peer / the skill seen stay silent, commit triggers too, "
          "off switch keeps the mark, mutation-checked")


def case_unattended_first(gate, sdir, root):
    """Refuse ONE dispatch when `unattended-work` was never invoked - then stop.

    ⚠ THE WHOLE CASE RUNS WITH `require_dispatch_protocol: false`. By default the hard rule
    requires `dispatch-protocol`, so every dispatch here would be refused for THAT before the
    soft nag could ask for `unattended-work`. Switching the hard rule off is the only way to
    exercise the nag - and it is also the composition an owner sees when they do the same.
    """
    sid = "s-unattended"
    stamp_session(gate, sdir, sid)
    agent = {"hook_event_name": "PreToolUse", "tool_name": "Agent", "cwd": root,
             "session_id": sid, "tool_input": {"prompt": "do a thing", "description": "d"}}
    base = {"require_dispatch_protocol": False}
    cfgdir = os.path.join(root, ".claude")
    os.makedirs(cfgdir, exist_ok=True)
    cfgfile = os.path.join(cfgdir, "dispatch-guard.json")
    with open(cfgfile, "w", encoding="utf-8") as f:
        json.dump({"dispatch": base}, f)
    r = run_gate(gate, agent)
    assert decision(r) == "deny", r
    assert "unattended-work" in reason(r), reason(r)
    assert r.get("systemMessage"), "the person should know the first dispatch was refused"
    # ⚠ ONCE. A skill that fails to load must not deadlock the session, so the second
    # dispatch is judged by the other rules only - here, the plan check.
    r2 = run_gate(gate, agent)
    assert "unattended-work" not in reason(r2), "it refused twice: %r" % (reason(r2),)

    # Invoking the skill silences it for a fresh session.
    sid2 = "s-loaded"
    stamp_session(gate, sdir, sid2)
    run_gate(gate, {"hook_event_name": "PostToolUse", "tool_name": "Skill", "cwd": root,
                    "session_id": sid2,
                    "tool_input": {"skill": "dispatch-guard:unattended-work"}})
    agent2 = dict(agent, session_id=sid2)
    assert "unattended-work" not in reason(run_gate(gate, agent2)), "the Skill call was ignored"

    # ⛔ ITS OWN OFF SWITCH LEAVES A TRACE. `guard_unattended_first: false` used to gate the
    # CALL, so the one guard whose switch produced no log line was this one - and an off
    # switch that leaves no trace is indistinguishable from a guard that ran and found
    # nothing, which is the whole reason every decision here is written down.
    sid_off = "s-guard-off"
    stamp_session(gate, sdir, sid_off)
    with open(cfgfile, "w", encoding="utf-8") as f:
        json.dump({"dispatch": dict(base, guard_unattended_first=False)}, f)
    try:
        before = len(gitlog(root))
        r_off = run_gate(gate, dict(agent, session_id=sid_off))
        assert "unattended-work" not in reason(r_off), "the key did not switch it off"
        assert "CMD-DISABLED(guard_unattended_first)" in gitlog(root)[before:], \
            gitlog(root)[-300:]
        # ⚠ And the nag mark must NOT have been written: spending the one refusal while
        # nobody was listening would mean switching the guard back on never fires it.
        assert not os.path.exists(gate.state_path(sdir, sid_off, "unattended-nagged")), \
            "it burned its one refusal while switched off"
    finally:
        # ⚠ Back to the case's BASE config, not removed: the rest of the case still needs
        # the hard rule switched off, or it answers before the soft nag can.
        with open(cfgfile, "w", encoding="utf-8") as f:
            json.dump({"dispatch": base}, f)
    assert "unattended-work" in reason(run_gate(gate, dict(agent, session_id=sid_off))), \
        "switching the guard back on did not restore the refusal"

    # ⛔ AND IT IS SILENT WHEN THE OWNER TURNED THE REMINDER OFF. Refusing a dispatch for not
    # loading a skill the owner opted out of would be the plugin overruling its own switch.
    sid3 = "s-optout"
    stamp_session(gate, sdir, sid3)
    os.environ["CLAUDE_PLUGIN_OPTION_ANNOUNCE_UNATTENDED_WORK"] = "false"
    try:
        r3 = run_gate(gate, dict(agent, session_id=sid3))
        assert "unattended-work" not in reason(r3), "it ignored announce_unattended_work=false"
    finally:
        os.environ.pop("CLAUDE_PLUGIN_OPTION_ANNOUNCE_UNATTENDED_WORK", None)
    os.remove(cfgfile)
    print("ok - one refusal for a missing unattended-work, and it respects the off switch")


def case_require_skills(gate, sdir, root):
    """⛔ NOTHING DISPATCHES UNTIL `dispatch-protocol` IS LOADED, and it refuses EVERY time.

    ⭐ ONLY `dispatch-protocol` BY DEFAULT, and the split is the whole design. That skill is
    what this plugin IS: every mechanical part of it is what the gate enforces, so a session
    dispatching without it is being refused by rules it never read. `unattended-work` is a way
    of WORKING rather than a gate - somebody dispatching sub-tasks while watching the screen
    has no use for the review rounds or the exit bar - so whether the two must travel together
    is the owner's decision, in `require_unattended_work`.

    ⚠ Unlike guard_unattended_first it does NOT stand aside after one refusal. That is the
    point, and also the risk, so the escape hatch is checked as carefully as the refusal.
    """
    sid = "s-require"
    stamp_session(gate, sdir, sid)
    agent = {"hook_event_name": "PreToolUse", "tool_name": "Agent", "cwd": root,
             "session_id": sid, "tool_input": {"prompt": "do a thing", "description": "d"}}

    # Nothing loaded: refused, naming `dispatch-protocol` - and NOT `unattended-work`.
    r = run_gate(gate, agent)
    assert decision(r) == "deny", r
    assert "dispatch-protocol" in reason(r), reason(r)
    assert "unattended-work" not in reason(r), \
        "unattended-work must not be required by default: %r" % (reason(r),)
    assert "REPEATS" in reason(r), "it must say the refusal is not a one-off"
    assert r.get("systemMessage"), "only the person can release a broken skill loader"
    assert "DENY(require-skills)" in gitlog(root), gitlog(root)[-300:]

    # ⚠ AND IT REPEATS. guard_unattended_first refuses once; this must not.
    assert decision(run_gate(gate, agent)) == "deny", "the second dispatch was allowed"

    # ⛔ AND BY THE THIRD REFUSAL IT STOPS ASSUMING THE AGENT IS AT FAULT. The one assumption
    # under this rule that cannot be measured from outside is that the harness fires tool
    # hooks for the `Skill` tool at all. If it does not, this rule refuses every dispatch for
    # ever - so from the third refusal the message names that possibility, on BOTH channels.
    # An absent signal must never be indistinguishable from a working one.
    r_stuck = run_gate(gate, agent)
    assert "REFUSAL 3 IN THIS SESSION" in reason(r_stuck), reason(r_stuck)
    assert "not reporting `Skill` calls" in reason(r_stuck), reason(r_stuck)
    assert "SKILL-SEEN" in r_stuck.get("systemMessage", ""), r_stuck.get("systemMessage")
    assert "require_dispatch_protocol: false" in r_stuck.get("systemMessage", "")

    # ⭐ THE OWNER'S POINT 1: `dispatch-protocol` ALONE IS ENOUGH. `unattended-work` is not
    # loaded here and must not be asked for.
    load_skills(gate, root, sid, "dispatch-guard:dispatch-protocol")
    r2 = run_gate(gate, agent)
    assert "REPEATS" not in reason(r2), \
        "dispatch-protocol alone did not release the dispatch: %r" % (reason(r2),)

    # ⭐ THE OWNER'S POINT 2: one boolean makes them travel together.
    sid_pair = "s-require-pair"
    stamp_session(gate, sdir, sid_pair)
    with project_cfg(root, require_unattended_work=True):
        r3 = run_gate(gate, dict(agent, session_id=sid_pair))
        assert "dispatch-protocol" in reason(r3) and "unattended-work" in reason(r3), reason(r3)
        load_skills(gate, root, sid_pair, "dispatch-guard:dispatch-protocol")
        # Still refused - and now only the MISSING one is asked for.
        ask = reason(run_gate(gate, dict(agent, session_id=sid_pair)))
        assert "unattended-work" in ask, ask
        assert "Invoke `dispatch-guard:unattended-work` now" in ask, ask
        load_skills(gate, root, sid_pair, "dispatch-guard:unattended-work")
        assert "REPEATS" not in reason(run_gate(gate, dict(agent, session_id=sid_pair)))

    # ⭐ THE SAME SKILL UNDER EVERY SPELLING. A plugin prefix, a directory scope, a bare name
    # and a shouted one are ONE skill; as four marks, "loaded" would depend on how it was typed.
    for n, spelling in enumerate(("dispatch-protocol", "dispatch-guard:dispatch-protocol",
                                  "apps/web:dispatch-protocol", "DISPATCH-PROTOCOL")):
        sid_x = "s-spell-%d" % n
        stamp_session(gate, sdir, sid_x)
        load_skills(gate, root, sid_x, spelling)
        rx = run_gate(gate, dict(agent, session_id=sid_x))
        assert "REPEATS" not in reason(rx), "%r did not count as loaded" % spelling

    # The escape hatch: both switches off means the check is off, with a line saying so.
    sid_off = "s-require-off"
    stamp_session(gate, sdir, sid_off)
    with project_cfg(root, require_dispatch_protocol=False):
        before = len(gitlog(root))
        r_off = run_gate(gate, dict(agent, session_id=sid_off))
        assert "REPEATS" not in reason(r_off), "the off switch still refused"
        assert "REQUIRE-SKILLS-OFF" in gitlog(root)[before:], gitlog(root)[-300:]

    # ⚠ A BOOLEAN WRITTEN AS A STRING still means what it says. Config files are edited by
    # hand, and `"false"` is what a hand types; treating it as truthy would silently turn a
    # switch back on.
    sid_str = "s-require-str"
    stamp_session(gate, sdir, sid_str)
    with project_cfg(root, require_dispatch_protocol="false"):
        assert "REPEATS" not in reason(run_gate(gate, dict(agent, session_id=sid_str))), \
            '"false" was read as true'
    with project_cfg(root, require_dispatch_protocol="true"):
        assert "REPEATS" in reason(run_gate(gate, dict(agent, session_id=sid_str))), \
            '"true" was read as false'

    # ⛔ AND THE OTHER OFF SWITCH IS HONOURED. `announce_unattended_work=false` means "I do not
    # want that skill", so it wins even over `require_unattended_work: true` - otherwise the
    # plugin would overrule its own off switch. `dispatch-protocol` has no such switch.
    sid_opt = "s-require-optout"
    stamp_session(gate, sdir, sid_opt)
    load_skills(gate, root, sid_opt, "dispatch-guard:dispatch-protocol")
    os.environ["CLAUDE_PLUGIN_OPTION_ANNOUNCE_UNATTENDED_WORK"] = "false"
    try:
        with project_cfg(root, require_unattended_work=True):
            r_opt = run_gate(gate, dict(agent, session_id=sid_opt))
            assert "REPEATS" not in reason(r_opt), \
                "it ignored announce_unattended_work=false: %r" % (reason(r_opt),)
    finally:
        os.environ.pop("CLAUDE_PLUGIN_OPTION_ANNOUNCE_UNATTENDED_WORK", None)

    # ⚠ An unstamped session is advisory here too, like every other rule in this gate.
    r_un = run_gate(gate, dict(agent, session_id="s-require-nostamp"))
    assert decision(r_un) == "allow", "an unstamped session was policed: %r" % (r_un,)
    print("ok - dispatch-protocol alone suffices, one boolean pairs them, switches honoured")


def case_skill_price_table(gate):
    """⛔ THE SKILL AND THE PROMPT MUST CARRY NO PRICE LITERALS AT ALL.

    They used to carry a four-row table, and the check here asserted it matched
    `MODEL_PRICES` in the gate. That was the right check for a table typed into the code.
    It is the WRONG one now: the prices are refreshed in the background from Anthropic's
    published page, so any number frozen into a skill or a prompt template goes stale the
    moment a model is repriced - and it goes stale SILENTLY, which is the failure this whole
    change removed. ⇒ The rule lives in the skill; the numbers live in model_pricing.json and
    are interpolated at run time.

    ⚠ The old table was not hypothetical about drifting. It priced Claude Haiku 3.5 at $1;
    the published price is $0.80.
    """
    import re
    PRICE = re.compile(r"\$\s?\d+(?:\.\d+)?\b")
    # ⭐ The DEFAULT CEILING is not a price literal in this sense - it is the config value, and
    # the skill has to state it. Everything else that looks like money is drift.
    default = gate.DEFAULTS["max_model_price"]
    allowed = {"$%s" % default, "$%s" % float(default)}
    for name in ("SKILL.md", "SKILL.zh-TW.md"):
        path = repo_path("skills", "dispatch-protocol", name)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        found = [m for m in PRICE.findall(text) if m.replace(" ", "") not in allowed]
        assert not found, ("%s still hard-codes model prices %r - they belong in "
                           "model_pricing.json, which refreshes; a number here does not"
                           % (path, sorted(set(found))))
        # ...and the default limit in the prose must still be the default in the code.
        assert re.search(r"\*\*%s\*\*" % default, text), \
            "%s does not state the default limit (%r)" % (path, default)
        assert "max_model_price" in text, "%s does not name the config key" % path
        # ⭐ AND IT MUST SAY WHERE THE LIVE TABLE IS. A rule with no numbers that also does not
        # say where the numbers are is a rule the reader has to guess at.
        assert "model_pricing" in text, "%s does not say where the live table lives" % path

    # ⛔ THE PROMPT TEMPLATE TOO. PREPEND reaches every sub-agent at every depth, and it is
    # where the four numbers used to be typed. A literal there would have the gate refusing at
    # one price while the prompt promised another.
    assert not PRICE.search(gate.PREPEND), \
        "PREPEND hard-codes a price again: %r" % PRICE.findall(gate.PREPEND)
    assert "{price_list}" in gate.PREPEND, "rule 7 no longer interpolates the live table"

    # ⚠ MUTATION CHECK: the assertion must actually fire on a table that IS hard-coded.
    # Without it the regex could be wrong and every assertion above would pass on nothing.
    assert PRICE.search("haiku $1, sonnet $2, opus $5, fable $10"), \
        "the price detector does not detect prices"
    print("ok - the skill and the prompt carry the rule, not frozen prices")


def case_price_refresh(gate, sdir):
    """⛔ THE REFRESH MUST NEVER BLOCK, MUST NEVER ERASE, AND MUST NEVER GO SILENT.

    Three separate failures, one case:

    - a fetch inside a hook would stall every tool call, so the decision to refresh is split
      out from the fork and only the DECISION is tested here - nothing spawns a process;
    - a page that returns 200 with a reshaped table parses to nothing, and writing that would
      wipe every price the gate owns;
    - a fetch that has been failing for a month looks exactly like one that never needed to
      run, unless the attempt is recorded somewhere the gate can read.

    ⚠ NO NETWORK. Everything here runs against `file://` URLs over the committed fixture, so
    the check means the same thing on a machine with no route out. A test that quietly needs
    the internet passes for the wrong reason on the day the parser breaks.
    """
    import pathlib
    import model_pricing as mp

    root = repo_path("Tools", "Debug", "fixtures", "pricing.md")
    good = pathlib.Path(root).as_uri()
    live = os.path.join(sdir, mp.FILENAME)
    for junk in (live, os.path.join(sdir, mp.STATUS), os.path.join(sdir, gate.PRICE_MARK)):
        if os.path.exists(junk):
            os.remove(junk)

    # 1. A good fetch writes the table, stamps it, and records that it worked.
    reason = mp.update(sdir, good)
    assert reason.startswith("MODEL-PRICE-UPDATED"), reason
    doc = mp.read(live)
    assert doc and doc["models"]["claude-opus-5"]["input"] == 5, doc
    assert doc["source"] == good and doc["fetched_at"] > 0, doc
    # ⭐ The owner asked for a HUMAN-READABLE time as well as a timestamp. Both, exactly.
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC$", doc["fetched_at_utc"]), doc
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4}$",
                    doc["fetched_at_local"]), doc
    st = mp.status(sdir)
    assert st and st["ok"], st

    # 2. ⛔ A FETCH THAT FAILS KEEPS THE TABLE AND SAYS SO. This is the branch that would
    # otherwise leave a machine with no prices at all.
    before = mp.read(live)
    reason = mp.update(sdir, pathlib.Path(sdir).joinpath("no-such-page.md").as_uri())
    assert reason.startswith("MODEL-PRICE-FETCH-FAILED"), reason
    assert mp.read(live) == before, "a failed fetch overwrote the table"
    st = mp.status(sdir)
    assert st and not st["ok"] and "FETCH-FAILED" in st["reason"], st

    # 3. ⛔ AND SO DOES A FETCH THAT SUCCEEDS BUT PARSES TO NOTHING - the likelier future
    # failure, because the page will still return 200 on the day its table changes shape.
    empty = os.path.join(sdir, "reshaped.md")
    with open(empty, "w", encoding="utf-8") as f:
        f.write("# Pricing\n\nWe have moved this table.\n")
    reason = mp.update(sdir, pathlib.Path(empty).as_uri())
    assert reason.startswith("MODEL-PRICE-PARSE-FAILED"), reason
    assert mp.read(live) == before, "a reshaped page erased the table"

    # 4. The refresh DECISION. ⚠ prices_due() only decides; nothing here forks.
    cfg = dict(gate.DEFAULTS)
    now = time.time()
    os.remove(os.path.join(sdir, gate.PRICE_MARK)) if os.path.exists(
        os.path.join(sdir, gate.PRICE_MARK)) else None
    assert not gate.prices_due(sdir, cfg, now), "a table written seconds ago is not due"
    # ⚠ AGEING THE LIVE FILE IS NOT ENOUGH, and finding that out is worth a comment. load()
    # prefers whichever copy has the newer `fetched_at`, so a live copy back-dated by 25 h
    # loses to the seed that ships in the repository - and the seed is fresh, so nothing is
    # due. That is the CORRECT behaviour (the newest table wins), which is why the interval is
    # driven from the clock here instead of by falsifying the file.
    # ⛔ THE PREMISE HAS TO BE ESTABLISHED, NOT ASSUMED. The assertion below reads "a
    # back-dated live copy loses to a NEWER seed" - and the seed is a file committed to this
    # repository with a fixed `fetched_at`, so the premise expired exactly 24 hours after
    # that capture and the check then failed on the clock with nothing changed. Measured
    # 2026-08-29: the seed turned 24.09 h old and the suite went red.
    # ⇒ the instant is taken FROM THE SEED, so the case tests what it says for ever.
    # ⚠ AND IT IS A LOCAL INSTANT, NOT A CHANGE TO `now`. The assertions below measure
    # the 24 h interval FROM `now`, so moving it turns this red check into a different
    # one - which is what the first attempt at this did.
    _seed = mp.read(os.path.join(mp.PLUGIN_DIR, mp.FILENAME)) or {}
    _fresh = min(now, (_seed.get("fetched_at") or now) + 3600)
    old = dict(before)
    old["fetched_at"] = int(_fresh - 25 * 3600)
    mp.write(old, live)
    assert not gate.prices_due(sdir, cfg, _fresh), \
        "a back-dated live copy must lose to a newer seed, not trigger a refresh"
    mp.write(before, live)
    later = now + 25 * 3600
    assert gate.prices_due(sdir, cfg, later), "a 25 h old table must be due at 24 h"
    assert not gate.prices_due(sdir, cfg, now + 23 * 3600), "23 h must not be due"
    now = later
    # ⛔ MUTATION CHECK ON THE OFF SWITCH. It is the one thing that stops this plugin talking
    # to the internet, and an off switch that does not switch anything off is worse than none.
    off = dict(cfg)
    off["model_price_update"] = False
    assert not gate.prices_due(sdir, off, now), "model_price_update=false still refreshed"
    # ⛔ AND ON THE RETRY FLOOR. Without it, a page that 404s forks one child per session for
    # ever - and the table stays old, so the first clock never stops saying "due".
    # ⚠ The floor reads the mark's MTIME, not its contents, so the mtime is what has to move.
    # Writing `now` into the file and leaving the mtime at the real clock tests nothing.
    with open(os.path.join(sdir, gate.PRICE_MARK), "w") as f:
        f.write(str(now))
    os.utime(os.path.join(sdir, gate.PRICE_MARK), (now, now))
    assert not gate.prices_due(sdir, cfg, now), "the retry floor did not hold"
    assert gate.prices_due(sdir, cfg, now + gate.PRICE_RETRY + 1), "the floor never expires"
    # ⚠ 0 hours means the owner pinned the table. Not "refresh constantly".
    pinned = dict(cfg)
    pinned["model_price_hours"] = 0
    os.remove(os.path.join(sdir, gate.PRICE_MARK))
    assert not gate.prices_due(sdir, pinned, now), "0 hours must pin, not spin"

    # 5. ⭐ THE SESSION IS TOLD BEFORE IT DISPATCHES. That is the half a PreToolUse refusal
    # cannot do, and it is why this feature exists at all.
    note = gate.model_note({"max_model_price": 5}, sdir)
    assert "SUB-AGENT MODELS" in note and "`opus`" in note, note
    assert "`fable`" in note and "NOT" in note, "the note must name what is REFUSED too"
    # ⛔ AND IT MUST APPLY THE SAME availableModels CLAMP THE REFUSAL APPLIES. Announcing a
    # model the gate then refuses reproduces the exact refusal-first experience this line
    # exists to remove, and teaches the agent that the gate is unreliable.
    clamped = gate.model_note({"max_model_price": 5}, sdir, avail=["sonnet", "haiku"])
    assert "narrowed to `sonnet`" in clamped, clamped
    assert "`opus`" not in clamped, "the note offered a model availableModels forbids"
    assert "allows $2 per million" in clamped, clamped
    os.remove(live)
    print("ok - price refresh decides without fetching, keeps the table on failure, records why")


def case_handoff_past_soft(gate, sdir, root):
    """⛔ PAST THE SOFT THRESHOLD, A DISPATCH NEEDS A CURRENT HANDOFF ON DISK.

    The handoff used to be written when the agent hit STOP - which assumes it still gets a
    turn. A real cut-off, the server refusing, gives no turn at all, and then the resume
    wakes with nothing on disk saying what was being done and spends the new window
    rediscovering it. ⇒ The file has to exist BEFORE the interruption, and the room between
    soft and hard is exactly where it can be written.

    ⚠ FOUR STATES, NOT A BOOLEAN, because the remedies differ: missing means write one,
    stale means refresh the one that is there, thin means it is a placeholder. A check that
    only asked "does the file exist" would pass a handoff from three windows ago describing
    work that no longer exists - and a resume acting on wrong instructions is worse than one
    that knows it is reconstructing.
    """
    import json as _json
    import time as _time
    folder = "20260828-160000-handoff-case"
    tdir = os.path.join(root, "Memory", "tasks", folder)
    os.makedirs(tdir, exist_ok=True)
    hpath = os.path.join(tdir, "HANDOFF.md")
    started = _time.time() - 600
    cfg = dict(gate.DEFAULTS)
    cfg["task_root"] = "Memory/tasks"

    def usage_at(pct):
        """Put a five-hour reading on disk, so verdict() answers from data like the gate."""
        now = _time.time()
        with open(os.path.join(sdir, "token_usage.json"), "w", encoding="utf-8") as f:
            _json.dump({"ts": int(now * 1000),
                        "five_hour": {"used_percentage": pct,
                                      "resets_at": int(now) + 3 * 3600}}, f)

    def refusal():
        return gate.handoff_refusal(root, sdir, cfg, folder, started)

    def write(chars, age=0):
        with open(hpath, "w", encoding="utf-8") as f:
            f.write("x" * chars)
        if age:
            os.utime(hpath, (_time.time() - age, _time.time() - age))

    # ⭐ BELOW SOFT IT NEVER FIRES. The whole point is that it bites only when an
    # interruption is near; a gate that refused at 10% would be switched off in a day.
    usage_at(10)
    if os.path.exists(hpath):
        os.remove(hpath)
    assert refusal() is None, "it refused below the soft threshold"

    # ...and past it, with nothing on disk, it refuses and says which state.
    usage_at(90)
    r = refusal()
    assert r and "no HANDOFF.md in that task folder" in r, r
    assert hpath.replace(chr(92), "/") in r.replace(chr(92), "/"), (
        "the refusal must name the exact path to write: %r" % r)

    # ⚠ A PLACEHOLDER IS NOT A HANDOFF. resume.py refuses to arm against one for the same
    # measured reason: a resume that wakes with nothing to read burns a window for nothing.
    write(50)
    r = refusal()
    assert r and "placeholder rather than a work order" in r, r

    # ⛔ AND NEITHER IS ONE FROM AN EARLIER SESSION. This is the state a size check cannot
    # see, and the one that produces a resume acting on instructions that are wrong.
    write(500, age=3600)
    r = refusal()
    assert r and "older than this session" in r, r

    # A current, substantial handoff passes.
    write(500)
    assert refusal() is None, refusal()

    # ⚠ THE OFF SWITCH. The owner may want to dispatch without one and take the
    # reconstruction prompt instead.
    os.remove(hpath)
    assert refusal(), "the missing handoff stopped being refused"
    off = dict(cfg)
    off["require_handoff_past_soft"] = False
    assert gate.handoff_refusal(root, sdir, off, folder, started) is None, "the switch is dead"

    # ⚠ NO TASK FOLDER MEANS NO REFUSAL FROM HERE. The plan check has already refused that
    # case, and reporting it twice would name the wrong reason for it.
    assert gate.handoff_refusal(root, sdir, cfg, None, started) is None

    # ⛔ PUT THE USAGE READING BACK. These cases share one state directory, and leaving 90%
    # in it puts every LATER case past the soft threshold - where this new precondition
    # refuses their dispatches before the guard they are actually testing ever runs. Measured
    # the moment this case was added: the model-ceiling case started failing on a refusal
    # that had nothing to do with models.
    os.remove(os.path.join(sdir, "token_usage.json"))
    print("ok - past soft a dispatch needs a current handoff; four states, and an off switch")


def case_auto_arm(gate, sdir, root):
    """⭐ THE RESUME ARMS ITSELF once there is something worth resuming.

    Arming was the agent's job, and it is the one step whose omission cannot be recovered
    from: everything else leaves a trace to pick up later, but a run that ends with nothing
    armed simply never continues - the handoff sits on disk and nothing ever reads it.

    ⛔ NOTHING HERE REGISTERS AN OS TASK. `subprocess.Popen` is replaced with a recorder, so
    the check asserts WHAT WOULD BE SPAWNED. A check that scheduled real tasks on the machine
    it runs on is the class of defect this repository has already shipped twice.
    """
    import json as _json
    import time as _time
    folder = "20260828-170000-auto-arm-case"
    tdir = os.path.join(root, "Memory", "tasks", folder)
    os.makedirs(tdir, exist_ok=True)
    with open(os.path.join(tdir, "HANDOFF.md"), "w", encoding="utf-8") as f:
        f.write("y" * 500)
    started = _time.time() - 600
    cfg = dict(gate.DEFAULTS)
    cfg["task_root"] = "Memory/tasks"
    now = _time.time()
    r5, r7 = now + 2 * 3600, now + 3 * 86400

    spawned = []

    class _Rec(object):
        def __init__(self, argv, **kw):
            spawned.append(list(argv))

    def usage_at(p5, p7=10):
        with open(os.path.join(sdir, "token_usage.json"), "w", encoding="utf-8") as f:
            _json.dump({"ts": int(now * 1000),
                        "five_hour": {"used_percentage": p5, "resets_at": int(r5)},
                        "seven_day": {"used_percentage": p7, "resets_at": int(r7)}}, f)

    def armed(_sid=None, **state):
        # ⭐ ONE RECORD PER SESSION since 0.60: `<sdir>/resume/<session>.json`. The de-dup
        # below reads the ARMING session's own record, so seeding the old shared file would
        # test nothing. ADR 20260917-132015, D1.
        path = os.path.join(sdir, "resume", gate.safe_session(_sid) + ".json")
        if state:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(state, f)
        elif os.path.exists(path):
            os.remove(path)

    def try_arm(c=None, _sid=None):
        del spawned[:]
        mark = gate.state_path(sdir, _sid, gate.ARM_MARK)
        if os.path.exists(mark):
            os.remove(mark)                     # the spawn floor is tested on its own below
        keep = gate.subprocess.Popen
        gate.subprocess.Popen = _Rec
        try:
            return gate.maybe_auto_arm(root, sdir, c or cfg, folder, started, _sid)
        finally:
            gate.subprocess.Popen = keep

    armed()
    # ⭐ BELOW SOFT IT DOES NOTHING. Arming early would be harmless but noisy; the point is
    # the closing window.
    usage_at(10)
    assert try_arm() is False and not spawned, spawned

    # ...and past it, with a usable handoff and nothing armed, it arms for THIS folder.
    usage_at(90)
    assert try_arm() is True, "it did not arm with the window closing"
    argv = spawned[0]
    assert "--arm" in argv and folder in argv and "--dir" in argv, argv
    assert argv[-1] == sdir, argv

    # ⛔ ONCE. Armed for the same task and the same reset, it must not re-register on every
    # single dispatch for the rest of the window.
    armed(task=folder, armed_for_reset=r5)
    assert try_arm() is False and not spawned, spawned

    # ⛔ BUT AGAIN WHEN THE TARGET MOVES. The brake can flip from the five-hour window to the
    # seven-day one, and a resume aimed at the old reset would wake still blocked.
    usage_at(0, 99)                             # now the WEEK is what stops the work
    assert try_arm() is True, "the reset target moved and it did not re-arm"
    assert folder in spawned[0], spawned

    # ⚠ ...and for a DIFFERENT task it arms too - a record belongs to one task at a time.
    usage_at(90)
    armed(task="some-other-task", armed_for_reset=r5)
    assert try_arm() is True, spawned

    # ⛔ AND ANOTHER SESSION'S ARM IS NOT SUPPRESSED BY MINE. While there was one record per
    # MACHINE, this de-dup silently swallowed a second session's arm whenever the first had
    # armed for the same folder and reset - so on a machine with two sessions only one of
    # them ever got a resume. ADR 20260917-132015, D1; measured live 2026-09-17.
    armed("SESSION-A", task=folder, armed_for_reset=r5)
    assert try_arm(_sid="SESSION-A") is False, "A's own record must still de-duplicate"
    assert try_arm(_sid="SESSION-B") is True, (
        "session B's arm was suppressed by session A's record - the single-slot bug")
    assert "--session" in spawned[0] and "SESSION-B" in spawned[0], spawned
    armed("SESSION-A")                          # clean up A's record

    # ⛔ AND NEITHER IS IT SUPPRESSED BY THE SPAWN FLOOR. This is the SECOND half of the
    # single-slot bug and the one the ADR's own first draft missed: the 300-second floor was
    # machine-wide, so even with a record each, one session arming blocked every other
    # session's arm for five minutes. A floor is per session by nature - it exists to stop a
    # machine that CANNOT arm from spawning a subprocess per tool call. D3.
    del spawned[:]
    assert gate.maybe_auto_arm(root, sdir, cfg, folder, started, "FLOOR-A") is True, \
        "A could not arm at all"
    a_mark = gate.state_path(sdir, "FLOOR-A", gate.ARM_MARK)
    assert os.path.exists(a_mark), "A's arm left no floor, so the floor is not being set"
    del spawned[:]
    keep_popen = gate.subprocess.Popen
    gate.subprocess.Popen = _Rec
    try:
        # ⚠ NOTE: no floor is cleared here. That is the whole point.
        got = gate.maybe_auto_arm(root, sdir, cfg, folder, started, "FLOOR-B")
    finally:
        gate.subprocess.Popen = keep_popen
    assert got is True and spawned, (
        "session B was blocked by session A's spawn floor - arming is still serialised")
    for sid_ in ("FLOOR-A", "FLOOR-B"):
        for p_ in (gate.state_path(sdir, sid_, gate.ARM_MARK),
                   os.path.join(sdir, "resume", gate.safe_session(sid_) + ".json")):
            if os.path.exists(p_):
                os.remove(p_)

    # ⚠ NOTHING WORTH RESUMING, NOTHING ARMED. A placeholder handoff is refused by the
    # precondition above; arming for it would schedule a run with nothing to read.
    armed()
    with open(os.path.join(tdir, "HANDOFF.md"), "w", encoding="utf-8") as f:
        f.write("tiny")
    assert try_arm() is False and not spawned, spawned
    with open(os.path.join(tdir, "HANDOFF.md"), "w", encoding="utf-8") as f:
        f.write("y" * 500)

    # ⚠ THE OFF SWITCH.
    off = dict(cfg)
    off["auto_arm_resume"] = False
    assert try_arm(off) is False and not spawned, spawned

    # ⛔ AND THE SPAWN FLOOR, which try_arm() clears deliberately every other time. Without
    # it a run that cannot arm - no scheduler, no permission - starts a subprocess on every
    # tool call for the rest of the session.
    assert try_arm() is True, "the setup for the floor check did not arm"
    del spawned[:]
    os.makedirs(os.path.join(sdir, "state"), exist_ok=True)
    with open(gate.state_path(sdir, None, gate.ARM_MARK), "w") as f:
        f.write(str(_time.time()))
    keep = gate.subprocess.Popen
    gate.subprocess.Popen = _Rec
    try:
        assert gate.maybe_auto_arm(root, sdir, cfg, folder, started) is False, "no floor"
    finally:
        gate.subprocess.Popen = keep
    assert not spawned, spawned

    # ⛔ AND IT MUST FIRE ON THE STOP PATH, WHICH IS THE ONE THAT MATTERS MOST. The usage
    # brake refuses a dispatch at STOP and RETURNS - so the auto-arm further down the
    # function is unreachable there, and the feature would miss exactly the moment it exists
    # for. ⚠ Driven through main() with a real payload, because that unreachability is a
    # property of the WIRING and cannot be seen by calling the function directly.
    sid = "s-autoarm"
    stamp_session(gate, sdir, sid)
    load_skills(gate, root, sid, "dispatch-guard:dispatch-protocol",
                "dispatch-guard:unattended-work")
    plan = os.path.join(tdir, "prompts-auto-arm.md")
    with open(plan, "w", encoding="utf-8") as f:
        f.write("the sub-task prompt")
    # ⚠ REWRITTEN AFTER THE SESSION STAMP. handoff_state() calls anything older than the
    # session start STALE - correctly - and the copy written at the top of this case predates
    # the stamp taken two lines above.
    with open(os.path.join(tdir, "HANDOFF.md"), "w", encoding="utf-8") as f:
        f.write("y" * 500)
    armed()
    if os.path.exists(gate.state_path(sdir, None, gate.ARM_MARK)):
        os.remove(gate.state_path(sdir, None, gate.ARM_MARK))
    usage_at(99)                                    # well past hard_pct_5h
    del spawned[:]
    keep = gate.subprocess.Popen
    gate.subprocess.Popen = _Rec
    try:
        r = run_gate(gate, {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                            "cwd": root, "session_id": sid,
                            "tool_input": {"prompt": "write to Memory/tasks/%s/ now" % folder,
                                           "description": "d"}})
    finally:
        gate.subprocess.Popen = keep
    assert decision(r) == "deny" and "STOP" in reason(r), r
    assert spawned and folder in spawned[0], (
        "the brake refused at STOP and nothing was armed - the auto-arm is unreachable "
        "there: %r" % (spawned,))

    # ⛔ Put the usage reading back - these cases share a state directory. See the handoff
    # case for what leaving it behind did to every LATER case.
    os.remove(os.path.join(sdir, "token_usage.json"))
    armed()
    print("ok - the resume arms itself once, re-arms when the target moves, never twice, "
          "and fires on the STOP path")


def case_model_price_limit(gate, sdir, root):
    """The sub-agent model price limit, weighed with the catalog's published prices.

    ⛔ THE TWO CASES THAT MATTER MOST ARE THE ALIASES, not `fable` itself. `best` is a real
    accepted alias and the catalog resolves it to FABLE, and `claude-mythos-5` is a fifth
    family the harness's own weight function scores as 3 - sonnet's weight. A guard that
    refused the literal string "fable" would hand out Fable via `best` and Mythos via its
    full ID, and both would look like the guard working.
    """
    import cmd_guards
    sid = "s-model"
    stamp_session(gate, sdir, sid)
    # ⚠ Satisfy the skill rules first, so every assertion below is about the MODEL and nothing
    # else. Loading them for real beats switching them off: it also proves the two compose.
    load_skills(gate, root, sid, "dispatch-guard:dispatch-protocol",
                "dispatch-guard:unattended-work")

    def dispatch(model=None, ceiling=5):
        ti = {"prompt": "do a thing", "description": "d"}
        if model is not None:
            ti["model"] = model
        cfgdir = os.path.join(root, ".claude")
        os.makedirs(cfgdir, exist_ok=True)
        cfgfile = os.path.join(cfgdir, "dispatch-guard.json")
        with open(cfgfile, "w", encoding="utf-8") as f:
            json.dump({"dispatch": {"max_model_price": ceiling}}, f)
        try:
            return run_gate(gate, {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                                   "cwd": root, "session_id": sid, "tool_input": ti})
        finally:
            os.remove(cfgfile)

    def refused(model, ceiling=5):
        return "sub-agent model" in reason(dispatch(model, ceiling))

    # ⭐ Above the ceiling, in every spelling the harness accepts.
    for model in ("fable", "FABLE", "best", "fable[1m]", "claude-fable-5",
                  "claude-mythos-5", "claude-fable-5[1m]"):
        assert refused(model), "%s reached the sub-agent" % model
    r = dispatch("fable")
    assert decision(r) == "deny", r
    assert "`opus`" in reason(r), "the refusal must name the level below: %r" % (reason(r),)
    assert "$10" in reason(r) and "$5" in reason(r), "it should quote the published prices"
    assert r.get("systemMessage"), "only the owner can change the ceiling"
    assert "DENY(model 'fable')" in gitlog(root), gitlog(root)[-300:]

    # ⛔ THE CASE A FAMILY LADDER GOT WRONG, and the reason this is priced per MODEL now.
    # claude-opus-4-0 is tier_15_75 in the catalog; claude-opus-5 is tier_5_25. Same family,
    # three times the input price - so a family-level number called them equal and let the
    # expensive one through an `opus` ceiling untouched.
    for expensive in ("claude-opus-4-0", "claude-opus-4-1", "opus-4-0"):
        assert refused(expensive), "%s passed an opus ceiling" % expensive
    assert "$15" in reason(dispatch("claude-opus-4-0")), reason(dispatch("claude-opus-4-0"))
    for ok in ("claude-opus-4-8", "claude-opus-4-5", "claude-sonnet-4-6"):
        assert not refused(ok), "%s was refused and is at or below the ceiling" % ok

    # ⚠ A VERSION THIS TABLE HAS NEVER SEEN is priced through its family - the best answer
    # available - and the assumption is logged rather than hidden.
    before = len(gitlog(root))
    assert not refused("claude-opus-6"), "an unseen opus version was refused outright"
    assert "MODEL-PRICE-ASSUMED" in gitlog(root)[before:], gitlog(root)[-300:]

    # ⭐ At or below the ceiling, and the two forms that mean "the model the owner chose".
    for model in ("opus", "OPUS", "opus[1m]", "opusplan", "claude-opus-5", "sonnet",
                  "claude-sonnet-5", "haiku", "inherit", None):
        assert not refused(model), "%s was refused and should not be" % model

    # A lower ceiling moves the line, and the message follows it.
    assert refused("opus", ceiling=2), "an opus dispatch passed a $2 limit"
    assert "`sonnet`" in reason(dispatch("opus", ceiling=2))
    assert not refused("sonnet", ceiling=2)
    # ⚠ A model NAME is still accepted where a number was meant - it is what a hand types.
    assert refused("fable", ceiling="opus"), "the name form stopped working"
    assert not refused("opus", ceiling="opus"), "the name form refused its own model"

    # ⚠ An unrecognised family is refused - the safe direction for a cost guard, and the one
    # place this deliberately disagrees with the harness's own function.
    assert refused("gpt-5-turbo"), "an unknown model must not pass a cost ceiling"
    assert "does not recognise" in reason(dispatch("gpt-5-turbo"))

    # ⛔ ...but a ceiling the OWNER mistyped fails OPEN. Refusing every dispatch over a typo
    # in a config file is how a guard gets the whole plugin uninstalled.
    assert not refused("fable", ceiling="bananas"), "a mistyped limit refused a dispatch"
    assert "MODEL-PRICE-LIMIT-UNKNOWN" in gitlog(root), gitlog(root)[-300:]
    # null switches the check off entirely - and says so, like every other off switch here.
    before = len(gitlog(root))
    assert not refused("fable", ceiling=None), "the null limit still refused"
    assert "MODEL-PRICE-LIMIT-OFF" in gitlog(root)[before:], gitlog(root)[-300:]

    # ⛔ AND THE ALLOWLIST IS READ FROM A REAL FILE, not injected. The gate's own selftest
    # passes `avail=` straight into model_refusal, which tests the decision and NOT the
    # wiring - and a decision function that is right while nothing calls it is exactly how
    # 0.4.0 shipped enforcing nothing. `availableModels` is a settings key, so a settings
    # file is what has to make the ceiling move.
    settings = os.path.join(root, ".claude", "settings.json")
    with open(settings, "w", encoding="utf-8") as f:
        json.dump({"availableModels": ["sonnet", "haiku"]}, f)
    try:
        assert gate.available_models(root) == ["sonnet", "haiku"], gate.available_models(root)
        r = dispatch("opus")
        assert decision(r) == "deny", "an opus dispatch survived a sonnet-only allowlist"
        assert "Dispatch with `sonnet`" in reason(r), reason(r)
        assert "allows $2 per million" in reason(r), "it reported the configured limit"
        assert "MODEL-PRICE-LIMIT-CLAMPED" in gitlog(root), gitlog(root)[-300:]
        assert not refused("sonnet"), "sonnet is allowed and was refused"
    finally:
        os.remove(settings)
    print("ok - model ceiling holds; `best`, mythos, and a real availableModels file")


def case_wind_down_on_every_tool(gate, sdir, root):
    """⛔ THE INCIDENT'S OWN SHAPE: a Read, at STOP, with no dispatch and no user prompt.

    Measured 2026-08-31: 183 Read, 172 Write, 36 Bash, ZERO Agent, no user prompt in the burn
    window, 0% to 100% in 85 minutes, and not one `USAGE(` line in any gate log on the
    machine. The gate received every one of those calls and returned early. This pins that
    it no longer does.

    ⭐ COMPOSED, NOT INSERTED IN FRONT. The shell branch must keep doing what it did - a
    `CMD-ALLOW` line, `record_branch`, `note_skill` - and carry the note as well.
    """
    import json as _json
    sid = "s-wind"
    stamp_session(gate, sdir, sid)

    def usage_at(pct):
        """Plant a stored reading so verdict()/level() answer for real."""
        cfg = gate.usage.config(sdir)
        with open(cfg["token_usage_file"], "w", encoding="utf-8") as f:
            _json.dump({"ts": int(time.time() * 1000),
                        "five_hour": {"used_percentage": pct,
                                      "resets_at": int(time.time()) + 3 * 3600}}, f)

    def read_call(uid, agent=None):
        p = {"hook_event_name": "PreToolUse", "tool_name": "Read", "cwd": root,
             "session_id": sid, "tool_use_id": uid,
             "tool_input": {"file_path": os.path.join(root, "x.md")}}
        if agent:
            p["agent_id"] = agent
        return run_gate(gate, p)

    def note(r):
        return (hso(r).get("additionalContext") or "") if isinstance(r, dict) else ""

    # ⚠ GO first: the quiet case must stay quiet, or the note is noise on every tool call.
    usage_at(10)
    assert not note(read_call("w0")), "a GO session was warned: %r" % (note(read_call("w0")),)

    # ⛔ STOP on a plain Read - no dispatch, no user prompt. This is the incident.
    usage_at(99)
    r = read_call("w1")
    assert "STOP" in note(r), "the incident's own shape produced nothing: %r" % (r,)
    assert "HANDOFF.md" in note(r), note(r)
    assert decision(r) is None, "the wind-down must not carry a permission decision: %r" % (r,)
    assert "USAGE(STOP) tool-path" in gitlog(root), gitlog(root)[-300:]

    # ⭐ ONCE PER LEVEL. A note on every tool call is a note nobody reads.
    assert not note(read_call("w2")), "it warned twice at the same level"

    # ⚠ A SUB-AGENT MUST NOT SILENCE THE SUPERVISOR. Its payload carries the PARENT's
    # session_id - measured - so the marker is keyed by `agent_id` as well.
    sid2 = "s-wind2"
    stamp_session(gate, sdir, sid2)
    saved, globals()["_sid"] = sid, sid2
    p = {"hook_event_name": "PreToolUse", "tool_name": "Read", "cwd": root,
         "session_id": sid2, "tool_use_id": "w3",
         "tool_input": {"file_path": "x"}, "agent_id": "sub-1"}
    assert "STOP" in note(run_gate(gate, p)), "the sub-agent heard nothing"
    p2 = dict(p, tool_use_id="w4")
    p2.pop("agent_id")
    assert "STOP" in note(run_gate(gate, p2)), (
        "the sub-agent's note silenced the supervisor's own")

    # ⭐ COMPOSED: a shell call keeps its own log line AND carries the note.
    sid3 = "s-wind3"
    stamp_session(gate, sdir, sid3)
    before = len(gitlog(root))
    r = run_gate(gate, {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": root,
                        "session_id": sid3, "tool_input": {"command": "echo hi"}})
    assert "STOP" in note(r), "a plain shell call lost the note: %r" % (r,)
    assert "CMD-ALLOW(checked=" in gitlog(root)[before:], (
        "composing the note replaced the command guards instead of joining them")
    # ⛔ AND THE BRANCH THAT ALREADY EMITS SOMETHING MUST CARRY BOTH. `echo hi` fires no
    # guard, so it exercises the empty-handed path; a relative `cd` fires guard_relative_cd,
    # which returns its own text - and THAT is the case where composing rather than replacing
    # is the whole point. ⚠ Without this the mutation "stop carrying the note" passes.
    sid3b = "s-wind3b"
    stamp_session(gate, sdir, sid3b)
    r = run_gate(gate, {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": root,
                        "session_id": sid3b,
                        "tool_input": {"command": "cd build && make"}})
    got = note(r)
    assert "STOP" in got, "the note was dropped where a guard already spoke: %r" % (r,)
    assert "dispatch gate WARNING" in got, (
        "composing dropped the guard's OWN warning instead of joining it: %r" % (got,))

    # The switch silences it, and an unstamped session is advisory like everything else.
    sid4 = "s-wind4"
    stamp_session(gate, sdir, sid4)
    with project_cfg(root, guard_wind_down=False):
        r = run_gate(gate, {"hook_event_name": "PreToolUse", "tool_name": "Read", "cwd": root,
                            "session_id": sid4, "tool_input": {"file_path": "x"}})
        assert not note(r), "the switch did not silence the wind-down: %r" % (r,)
    r = run_gate(gate, {"hook_event_name": "PreToolUse", "tool_name": "Read", "cwd": root,
                        "session_id": "s-never-stamped", "tool_input": {"file_path": "x"}})
    assert not note(r), "an unstamped session was warned: %r" % (r,)
    # ⛔ PUT THE READING BACK. This case plants 99% to reach STOP, and the stored record is
    # shared with every case after it - leaving it high made the very next one fail with "the
    # warning must not refuse the dispatch", which is the usage brake doing its job on a
    # number this check invented. ⚠ A case that dirties shared state fails its neighbours.
    usage_at(0)
    print("ok - a Read at STOP now says something, once per level, per agent")


def case_session_cwd_is_recorded(gate, sdir, root):
    """⭐ THE SESSION'S START-TIME WORKING DIRECTORY, kept so a resume can find the work.

    ⛔ The START-time one, not the current one. A hook payload's `cwd` follows the Bash
    tool's own `cd`, which persists between calls - measured 2026-09-01, where that moving
    value scattered one session's gate log across four directories. A resume armed against
    the moved value would wake the work in the wrong tree, silently.

    ⚠ It rides in the `.start` file, whose content nothing else reads (session_start()
    takes the mtime), and a stamp written before this shipped must still parse as "no cwd".
    """
    sid = "s-cwd"
    run_gate(gate, {"hook_event_name": "SessionStart", "cwd": root, "session_id": sid})
    got = gate.session_cwd(sdir, sid)
    assert got and os.path.samefile(got, root), (got, root)
    # ⛔ THE STAMP STILL WORKS AS A STAMP. session_start() reads the mtime, and turning the
    # content into JSON must not have disturbed that - if it had, every guard would go
    # advisory and nothing would say so.
    assert gate.session_start(sdir, sid) is not None, "the start stamp stopped being a stamp"
    # ⚠ The pre-0.56 content is a bare timestamp: no cwd, and NOT a crash.
    with open(gate.state_path(sdir, "s-old", "start"), "w", encoding="utf-8") as f:
        f.write("1788000000.0")
    assert gate.session_cwd(sdir, "s-old") is None, "an old stamp must read as no cwd"
    assert gate.session_start(sdir, "s-old") is not None
    # ...and a session that was never stamped at all.
    assert gate.session_cwd(sdir, "s-never-seen") is None
    print("ok - the session's start-time cwd is recorded, and an old stamp still parses")


def case_agent_report_file(gate, sdir, root):
    """A prompt that demands a file, and whether that file ever appeared.

    ⛔ THE POST HALF IS THE LOAD-BEARING ONE and these checks are ordered to say so. It needs
    no knowledge of any agent's tool list, so it cannot rot, and it catches the case the PRE
    warning never can: an agent that COULD write and simply did not.

    ⛔ SILENCE IS ASSERTED, not assumed. A guard that fires on everything is a guard nobody
    reads, so the four no-alarm cases below are the ones that keep this one useful: a
    read-only type asked only to READ, a Bash-only type, an unknown type, and a path outside
    the task root.
    """
    sid = "s-agent-type"
    stamp_session(gate, sdir, sid)
    load_skills(gate, root, sid, "dispatch-guard:dispatch-protocol",
                "dispatch-guard:unattended-work")

    task = "20260831-091500-agent-type"
    folder = os.path.join(root, "Memory", "tasks", task)
    os.makedirs(folder, exist_ok=True)
    report = os.path.join(folder, "agent-01-review.md")
    rel = "Memory/tasks/%s/agent-01-review.md" % task
    # The plan on disk, or every dispatch below is refused before it reaches this guard.
    with open(os.path.join(folder, "prompts.md"), "w", encoding="utf-8") as f:
        f.write("the plan\n")

    def pre(prompt, stype=None, uid="u1"):
        ti = {"prompt": prompt, "description": "review"}
        if stype is not None:
            ti["subagent_type"] = stype
        return run_gate(gate, {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                               "cwd": root, "session_id": sid, "tool_use_id": uid,
                               "tool_input": ti})

    def post(uid="u1"):
        return run_gate(gate, {"hook_event_name": "PostToolUse", "tool_name": "Agent",
                               "cwd": root, "session_id": sid, "tool_use_id": uid,
                               "tool_input": {"prompt": "x"}, "tool_response": "done"})

    def warned(r):
        return "read-only" in (hso(r).get("additionalContext") or "")

    creating = ("Create %s as your FIRST action, then append every finding.\n"
                "Read Memory/tasks/%s/prompts.md for the plan." % (rel, task))

    # 1. The real case: a read-only type told to CREATE a file. A NOTE, never a refusal.
    r = pre(creating, "Explore")
    assert decision(r) == "allow", "the warning must not refuse the dispatch: %r" % (r,)
    assert warned(r), "no warning for an Explore agent told to create a file: %r" % (r,)
    assert r.get("systemMessage"), "the person must see it; only they can change the type"
    assert "AGENT-TYPE-WARN(Explore" in gitlog(root), gitlog(root)[-400:]

    # 2. PostToolUse, the file never appeared -> a note naming it.
    assert not os.path.exists(report)
    r = post()
    assert "was never created" in (hso(r).get("additionalContext") or ""), r
    assert rel.replace("/", os.sep) in (hso(r).get("additionalContext") or ""), r
    assert r.get("systemMessage"), "a lost report must reach the person"
    assert "AGENT-FILE-MISSING" in gitlog(root), gitlog(root)[-400:]

    # 3. ⛔ PostToolUse with the file PRESENT -> SILENCE, and the log says it checked.
    # This is the mutation that matters: drop the os.path.exists test in the gate and this
    # assertion is what fails.
    with open(report, "w", encoding="utf-8") as f:
        f.write("the report\n")
    pre(creating, "general-purpose", uid="u2")
    before = len(gitlog(root))
    r = post(uid="u2")
    assert not hso(r).get("additionalContext"), "it warned about a file that exists: %r" % (r,)
    assert "AGENT-FILE-OK n=1" in gitlog(root)[before:], gitlog(root)[-400:]
    os.remove(report)

    # 4. No false alarm: a read-only type whose prompt only tells it to READ.
    r = pre("Read %s and summarise it." % rel, "Explore", uid="u3")
    assert not warned(r), "a read-only agent told only to READ was warned: %r" % (r,)
    before = len(gitlog(root))
    r = post(uid="u3")
    assert not hso(r).get("additionalContext"), "nothing was demanded, so nothing is missing"
    assert "AGENT-FILE-MISSING" not in gitlog(root)[before:], gitlog(root)[-400:]

    # 5. No false alarm: Bash-only. `codex:codex-rescue` has no Write tool and writes
    # through the shell, so flagging it would be wrong.
    assert not warned(pre(creating, "codex:codex-rescue", uid="u4")), "Bash-only was flagged"
    post(uid="u4")

    # 6. An UNKNOWN type says nothing at PreToolUse - but the PostToolUse half still runs.
    r = pre(creating, "some-custom-agent", uid="u5")
    assert not warned(r), "an unknown type produced a guess: %r" % (r,)
    assert gate.agent_can_make_files(root, "some-custom-agent") is None
    r = post(uid="u5")
    assert "was never created" in (hso(r).get("additionalContext") or ""), \
        "the post check must not depend on knowing the type: %r" % (r,)

    # 7. A path OUTSIDE the task root is not this guard's business.
    r = pre("Create /etc/hosts.md and README.md as your first action.", "Explore", uid="u6")
    assert not warned(r), "a path outside the task root was picked up: %r" % (r,)
    before = len(gitlog(root))
    r = post(uid="u6")
    assert not hso(r).get("additionalContext"), r

    # ⭐ A PROJECT DEFINITION BEATS THE BUILT-IN SNAPSHOT, in both directions.
    adir = os.path.join(root, ".claude", "agents")
    os.makedirs(adir, exist_ok=True)
    with open(os.path.join(adir, "local-reader.md"), "w", encoding="utf-8") as f:
        f.write("---\nname: local-reader\ntools: Read, Grep, Glob\n---\nbody\n")
    with open(os.path.join(adir, "local-writer.md"), "w", encoding="utf-8") as f:
        f.write("---\nname: local-writer\ntools: Read, Write\n---\nbody\n")
    # ⛔ A YAML BLOCK LIST IS THE OTHER LEGAL SPELLING OF `tools:`, and reading it wrong
    # produced a FALSE WARNING - the pattern skipped the newline and captured only the first
    # item, so an agent holding Write was reported unable to write. Silence would have been
    # acceptable; a wrong answer about a perfectly good dispatch is not.
    with open(os.path.join(adir, "block-writer.md"), "w", encoding="utf-8") as f:
        f.write("---\nname: block-writer\ntools:\n  - Read\n  - Write\n---\nbody\n")
    with open(os.path.join(adir, "block-reader.md"), "w", encoding="utf-8") as f:
        f.write("---\nname: block-reader\ntools:\n  - Read\n  - Grep\n---\nbody\n")
    # ...and `tools:` with nothing under it declares nothing: UNKNOWN, so silent.
    with open(os.path.join(adir, "no-tools.md"), "w", encoding="utf-8") as f:
        f.write("---\nname: no-tools\ntools:\ndescription: x\n---\nbody\n")
    try:
        assert gate.agent_can_make_files(root, "block-writer") is True, \
            gate._project_agent_tools(root, "block-writer")
        assert gate.agent_can_make_files(root, "block-reader") is False
        assert gate.agent_can_make_files(root, "no-tools") is None
        assert gate.agent_can_make_files(root, "local-reader") is False
        assert gate.agent_can_make_files(root, "local-writer") is True
        assert warned(pre(creating, "local-reader", uid="u7"))
        post(uid="u7")
        assert not warned(pre(creating, "local-writer", uid="u8"))
        post(uid="u8")
    finally:
        shutil.rmtree(adir, ignore_errors=True)

    # ⛔ THE SHAPES THE FIRST VERSION COULD NOT SEE. Every row below is a REAL spelling taken
    # from this repository's own `Memory/tasks/*/prompts*.md`, and the line-by-line scan that
    # shipped first found two of eighteen work orders. The incident that motivated the whole
    # guard is the first row: verb at the end of one line, path on the next.
    cfg = {"task_root": "Memory/tasks"}

    def demanded(text, fold=task):
        return [os.path.basename(p) for p in gate.demanded_files(root, cfg, text, fold)[0]]

    assert demanded("**Your FIRST action:** create\n`Memory/tasks/%s/r.md`\nwith a heading."
                    % task) == ["r.md"], "the incident's own shape is still invisible"
    assert demanded("Create `agent-01-implement.md` in this same folder as your FIRST "
                    "action.") == ["agent-01-implement.md"], "a bare filename was missed"
    # ⚠ ...and a bare filename with NO task folder resolved has nowhere to go: silence.
    assert gate.demanded_files(root, cfg, "Create `x.md` now.", None)[0] == []

    # ⛔ THE COST OF REACHING ACROSS A LINE, BOUNDED. The window stops at the end of the
    # sentence, or after one line break - whichever comes first - so the NEXT instruction is
    # not swallowed. Without the cut, "Read <plan>" became a file the agent had to create.
    assert demanded("Create Memory/tasks/%s/r.md as your FIRST action.\n"
                    "Read Memory/tasks/%s/prompts.md for the plan." % (task, task)) \
        == ["r.md"], "the window ran on into the next instruction"

    # ⚠ WORK ORDERS ELIDE THE PREFIX. `...\\Memory\\tasks\\...` joined onto the repository
    # root gave `<root>\\...\\Memory\\...`, so a report that WAS written read as missing.
    got = gate.demanded_files(root, cfg, "create `...\\Memory\\tasks\\%s\\r.md`" % task, task)[0]
    assert got == [os.path.join(root, "Memory", "tasks", task, "r.md")], got

    # ⚠ A BARE `.md` WITH NO NAME is not a path. It used to produce `<folder>\\.md`, which can
    # never exist and would be reported as a lost report for ever.
    assert demanded("Create a file whose name ends in .md somewhere.") == []

    # ⛔ WHOLE WORDS. Stems matched inside `creative`, `appendix` and `rewritten`, and then
    # named whatever `.md` the sentence mentioned as the agent's lost report.
    for prose in ("Be creative about Memory/tasks/%s/r.md" % task,
                  "The appendix lists Memory/tasks/%s/r.md" % task,
                  "It was rewritten from Memory/tasks/%s/r.md" % task):
        assert demanded(prose) == [], "a verb stem fired inside a word: %r" % prose

    # An absolute path is used AS WRITTEN, never re-rooted into this repository.
    other = os.path.join(root, "elsewhere").replace("\\", "/")
    got = gate.demanded_files(root, cfg, "Create %s/Memory/tasks/%s/r.md" % (other, task))[0]
    assert got == [os.path.normpath("%s/Memory/tasks/%s/r.md" % (other, task))], got
    # ...and `..` is skipped: this cannot honestly be called scoped to the task root.
    assert demanded("Create Memory/tasks/../../escape.md") == []
    # A left boundary, so a directory merely ENDING in the task root is not one.
    assert demanded("Create MyMemory/tasks/%s/r.md" % task) == []

    # ⛔ A `.md` RIGHT AFTER A SHELL REDIRECT IS AN EXAMPLE, NOT A DEMAND (0.63.2). Measured
    # 2026-09-19: this exact prompt shape made the gate report `board.md` never created after
    # the round-2 ADR review returned - the real report was there. The control beside it is the
    # same filename as a genuine demand, which must still be seen.
    assert demanded("write three small files in your scratch directory - one with `append-only` "
                    "in its H1 - and work out on paper which the rule would refuse: (vi) `echo x "
                    ">> board.md`; (vii) `echo x > board.md`; (viii) `cat new.md | tee board.md`.") \
        == [], "a shell example's redirect target was read as a demanded report"
    assert demanded("Create `board.md` as your FIRST action.") == ["board.md"], \
        "the control - a genuine bare-filename demand - was lost"
    # ⛔ ... AND A MARKDOWN TABLE CELL IS NOT A REDIRECT. Review 01 measured the first draft
    # (bare `|` accepted) dropping a real deliverables row from this repository's work orders.
    assert demanded("| Create | Memory/tasks/%s/r.md | first action |" % task) == ["r.md"], \
        "a demand in a table cell was read as a pipe target"
    assert demanded("| write | `adr-review-01-adversarial.md` | round 1, adversarial |") \
        == ["adr-review-01-adversarial.md"], "a bare filename in a table cell was dropped"
    # ... and a prose arrow `->` is not a `>` redirect either.
    assert demanded("Write your report, as the last step -> Memory/tasks/%s/r.md" % task) == ["r.md"], \
        "the `>` of a prose arrow was read as a redirect"

    # ⭐ THE LOG SEPARATES "demanded nothing" FROM "demanded something, path not recognised".
    # Those are the same silence, and one line for both would hide the coverage gap.
    before = len(gitlog(root))
    pre("Summarise the repository. No files needed.", "Explore", uid="uA")
    post(uid="uA")
    assert "wants=0 verbs=0" in gitlog(root)[before:], gitlog(root)[-300:]
    before = len(gitlog(root))
    pre("Create that file as your FIRST action, then append.", "Explore", uid="uB")
    post(uid="uB")
    assert "wants=0 verbs=2" in gitlog(root)[before:], gitlog(root)[-300:]

    # ⚠ `Edit` ALONE IS NOT A WAY TO CREATE A FILE, which is why statusline-setup (Read,
    # Edit) is in the read-only snapshot. Asserted so a later "tidy-up" cannot quietly add
    # Edit to MAKES_FILES.
    assert "edit" not in gate.MAKES_FILES
    assert gate.agent_can_make_files(root, "statusline-setup") is False

    # The switch turns both halves off, and SAYS SO - an off switch that leaves no trace
    # looks exactly like a guard nobody broke.
    with project_cfg(root, guard_agent_report_file=False):
        before = len(gitlog(root))
        assert not warned(pre(creating, "Explore", uid="u9")), "the switch did not silence it"
        assert "AGENT-TYPE-DISABLED" in gitlog(root)[before:], gitlog(root)[-400:]
        r = post(uid="u9")
        assert not hso(r).get("additionalContext"), "the post half survived the switch: %r" % (r,)

    shutil.rmtree(folder, ignore_errors=True)
    print("ok - a demanded report file is checked on the way out, and silence is asserted")


def case_unpushed(gate, sdir, root):
    """PostToolUse advisory - and "no upstream" must stay silent rather than error."""
    before = len(gitlog(root))
    r = run_gate(gate, bash(root, "git commit -F m.txt", event="PostToolUse"))
    assert not hso(r).get("additionalContext"), "a branch with no upstream is normal: %r" % (r,)
    assert "CMD-ADVISORY(unpushed: no upstream" in gitlog(root)[before:], gitlog(root)[-300:]

    # Three commits with the upstream at the first: two unpushed, one of them older than the
    # commit just made - which is the condition the guard is for. ⚠ `--set-upstream-to` needs
    # the REMOTE to exist as well as the ref, and it never has to be reachable: nothing here
    # fetches, so `origin` points at a path that does not exist.
    with scratch_dir("unpushed-repo") as d:
        fixture_repo(d)
        for n in ("one", "two", "three"):
            subprocess.run(["git", "-C", d] + GIT_ID +
                           ["commit", "--allow-empty", "-q", "-F", "-"],
                           input="commit %s\n" % n, text=True, capture_output=True)
        first = git(d, "rev-parse", "HEAD~2").stdout.strip()
        git(d, "remote", "add", "origin", d + "-nowhere")
        git(d, "update-ref", "refs/remotes/origin/master", first)
        up = git(d, "branch", "--set-upstream-to=origin/master", "master")
        assert up.returncode == 0, up.stderr
        gate_root = gate.repo_root(d)
        assert gate_root == d, gate_root
        r2 = run_gate(gate, bash(d, "git commit -F m.txt", event="PostToolUse"))
        text = hso(r2).get("additionalContext", "")
        assert "not pushed" in text and "2 commits" in text, r2
        assert "CMD-NOTE(guard_unpushed n=2)" in gitlog(d), gitlog(d)[-300:]
    print("ok - unpushed commits reported, a missing upstream stays quiet")


def case_arm_on_stop(gate, sdir, root):
    """⛔ THE ARM RUNS WHEN THE TURN ENDS, not only when a dispatch is attempted.

    Measured 2026-09-02 on two machines: the session that dispatched a reviewer after writing
    its HANDOFF.md was armed (the arm lived on the Agent PreToolUse path); the session that
    obeyed PACE - no new wave - wrote its handoff, dispatched nothing more, and ended unarmed.
    Its agent confirmed the manual `resume.py --arm` was forgotten. ⇒ `Stop` and every
    PACE/STOP prompt now arm for the freshest HANDOFF.md THIS session wrote.

    ⛔ "THIS SESSION WROTE" IS RECORDED, NOT INFERRED FROM A CLOCK. The first version used
    mtime ≥ the session stamp, and the code review measured `git checkout` handing every
    tracked HANDOFF.md mtime=now: one Stop armed a FINISHED task's folder. Now the gate records
    the folder from the Write/Edit/Bash PostToolUse payload, and only recorded folders are
    candidates.

    ⛔ NOTHING HERE REGISTERS OR DELETES A REAL OS TASK: `subprocess.Popen` is a recorder and
    `resume.do_cancel` is replaced for the stand-down step. ADR: Memory/tasks/
    20260902-142400-auto-arm-on-stop/ADR.md.
    """
    import json as _json
    import time as _time
    sid = "s-stoparm"
    folder = "20260902-150000-stop-arm-case"
    older = "20260902-140000-stop-arm-older"
    pulled = "20260902-170000-pulled-finished-task"
    tdir = os.path.join(root, "Memory", "tasks", folder)
    odir = os.path.join(root, "Memory", "tasks", older)
    pdir = os.path.join(root, "Memory", "tasks", pulled)
    for d in (tdir, odir, pdir):
        os.makedirs(d, exist_ok=True)
    now = _time.time()
    r5, r7 = now + 2 * 3600, now + 3 * 86400
    spawned = []

    class _Rec(object):
        def __init__(self, argv, **kw):
            spawned.append(list(argv))

    def usage_at(p5, p7=10):
        with open(os.path.join(sdir, "token_usage.json"), "w", encoding="utf-8") as f:
            _json.dump({"ts": int(_time.time() * 1000),
                        "five_hour": {"used_percentage": p5, "resets_at": int(r5)},
                        "seven_day": {"used_percentage": p7, "resets_at": int(r7)}}, f)

    def level():
        return gate.usage.verdict(sdir, gate.usage.config(sdir))["verdict"]

    def armed(**state):
        # ⭐ This session's own record since 0.60 - the de-dup reads the arming session's.
        path = os.path.join(sdir, "resume", gate.safe_session(sid) + ".json")
        if state:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(state, f)
        elif os.path.exists(path):
            os.remove(path)

    def handoff(d, text, when=None):
        p = os.path.join(d, "HANDOFF.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        if when is not None:
            os.utime(p, (when, when))

    def gated(payload):
        keep = gate.subprocess.Popen
        gate.subprocess.Popen = _Rec
        try:
            return run_gate(gate, payload)
        finally:
            gate.subprocess.Popen = keep

    def fire(event, clear_floor=True, cwd=None):
        del spawned[:]
        mark = gate.state_path(sdir, sid, gate.ARM_MARK)
        if clear_floor and os.path.exists(mark):
            os.remove(mark)
        payload = {"hook_event_name": event, "cwd": cwd or root, "session_id": sid}
        if event == "Stop":
            payload["stop_hook_active"] = False
        else:
            payload["prompt"] = "hello"
        return gated(payload)

    def wrote(path, tool="Write"):
        """The PostToolUse the harness sends after the file tool wrote `path`."""
        del spawned[:]
        if tool == "Bash":
            ti = {"command": "printf 'x' > %s" % path.replace("\\", "/")}
        else:
            ti = {"file_path": path, "content": "..."}
        return gated({"hook_event_name": "PostToolUse", "tool_name": tool, "cwd": root,
                      "session_id": sid, "tool_input": ti, "tool_response": {}})

    def said(result):
        return (result or {}).get("systemMessage", "") if isinstance(result, dict) else ""

    seen = gate.state_path(sdir, sid, gate.HANDOFF_SEEN)
    if os.path.exists(seen):
        os.remove(seen)
    stamp_session(gate, sdir, sid)
    _time.sleep(1.1)
    armed()

    # ⛔ THE PULL. A HANDOFF.md that is fresh by mtime but that this session never wrote -
    # `git checkout` gives every tracked file mtime=now - is NOT a candidate. Nothing recorded,
    # nothing armed, and the log says what was missing.
    handoff(pdir, "p" * 500)
    usage_at(band_pcts(gate)[0])
    assert level() == "PACE", level()
    before = len(gitlog(root))
    r = fire("Stop")
    assert not spawned and r == "", (
        "a fresh-by-mtime HANDOFF.md nobody in this session wrote was armed: %r" % (spawned,))
    assert "AUTO-ARM-STOP-SKIPPED no HANDOFF.md write observed this session" in gitlog(root)[before:], (
        "the Stop payload did not reach the arm path at all - nothing was logged: %r"
        % (gitlog(root)[before:],))

    # ⭐ THE RECORD. The Write's PostToolUse names the file; the gate remembers the folder.
    handoff(tdir, "h" * 500)
    assert wrote(os.path.join(tdir, "HANDOFF.md")) == ""
    assert gate.handoffs_written(sdir, sid) == [folder], gate.handoffs_written(sdir, sid)
    # ...a second Write of the same file records nothing new; a Bash redirect records too.
    wrote(os.path.join(tdir, "HANDOFF.md"))
    assert gate.handoffs_written(sdir, sid) == [folder]
    handoff(odir, "o" * 500)
    wrote(os.path.join(odir, "HANDOFF.md"), tool="Bash")
    assert gate.handoffs_written(sdir, sid) == [folder, older], gate.handoffs_written(sdir, sid)
    # ...and an unrelated Write records nothing.
    wrote(os.path.join(root, "README.md"))
    assert gate.handoffs_written(sdir, sid) == [folder, older]
    # ⛔ A BASH COMMAND THAT ONLY READS OR MENTIONS THE FILE RECORDS NOTHING. The round-2 review
    # measured the first rule ("HANDOFF.md anywhere and a `>` anywhere") recording a folder from
    # each of these - and one Stop then armed a finished task. Only a path that immediately
    # follows `>` or `>>` is a write.
    ppath = os.path.join(pdir, "HANDOFF.md").replace("\\", "/")
    for cmd in ("cat %s 2>&1" % ppath,
                "cat %s > /dev/null" % ppath,
                "grep -n '>' %s" % ppath,
                "echo 'see %s' >> notes.txt" % ppath,
                "printf 'x' > %s.bak" % ppath,
                "T=%s; printf 'x' > \"$T/HANDOFF.md\"" % pdir.replace("\\", "/")):
        del spawned[:]
        gated({"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": root,
               "session_id": sid, "tool_input": {"command": cmd}, "tool_response": {}})
        assert gate.handoffs_written(sdir, sid) == [folder, older], (
            "a Bash command that does not write HANDOFF.md was recorded as writing it: %r -> %r"
            % (cmd, gate.handoffs_written(sdir, sid)))
    # ...while the quoted and heredoc write shapes still record.
    for cmd in ("cat <<EOF >> \"%s\"\nx\nEOF" % ppath, "printf 'x' >>%s" % ppath):
        gated({"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": root,
               "session_id": sid, "tool_input": {"command": cmd}, "tool_response": {}})
    assert gate.handoffs_written(sdir, sid) == [folder, older, pulled], gate.handoffs_written(sdir, sid)
    # put the record back to the two real writes: the pulled folder is the "never written" case
    with open(seen, "w", encoding="utf-8") as f:
        f.write(folder + "\n" + older + "\n")

    # ⭐ GO: nothing armed, nothing said.
    usage_at(10)
    assert level() == "GO"
    r = fire("Stop")
    assert not spawned and r == "", (spawned, r)

    # ⛔ PACE + this session's handoff + the turn ends => armed for the NEWEST of the recorded
    # folders (`folder` was written last), never the pulled one, and the person is told.
    handoff(tdir, "h" * 500)                                  # recorded
    _time.sleep(1.1)
    handoff(pdir, "p" * 500)                                  # NEWEST by mtime, never recorded
    usage_at(band_pcts(gate)[0])
    before = len(gitlog(root))
    r = fire("Stop")
    assert spawned and "--arm" in spawned[0], (
        "the turn ended at PACE with a fresh handoff and nothing was armed: %r" % (spawned,))
    assert pulled not in spawned[0], (
        "a folder this session never wrote was armed because its mtime was newest - time is "
        "not authorship: %r" % (spawned,))
    assert folder in spawned[0], spawned
    assert folder in said(r) and "ARMED" in said(r), r
    tail = gitlog(root)[before:]
    assert "AUTO-ARM-STOP %s (written=2 usable=2 session=%s)" % (folder, sid[:8]) in tail, tail

    # ⛔ ONCE: armed for this folder and this reset already => silent.
    armed(task=folder, armed_for_reset=r5)
    r = fire("Stop")
    assert not spawned and r == "", (spawned, r)
    armed()

    # ⛔ A RECORDED HANDOFF THAT IS STALE OR THIN IS NOT USABLE: skipped, and said.
    handoff(tdir, "h" * 500, when=now - 3600)
    handoff(odir, "tiny")
    before = len(gitlog(root))
    r = fire("Stop")
    assert not spawned and r == "", (spawned, r)
    assert "AUTO-ARM-STOP-SKIPPED the 2 HANDOFF.md this session wrote are missing, thin or older" \
        in gitlog(root)[before:], gitlog(root)[before:]
    handoff(tdir, "h" * 500)

    # ⛔ NO SESSION STAMP => no freshness test => NOTHING, and the log says why (ADR review B-2).
    stamp = gate.state_path(sdir, sid, "start")
    os.remove(stamp)
    before = len(gitlog(root))
    r = fire("Stop")
    assert not spawned and r == "", (spawned, r)
    assert "AUTO-ARM-STOP-SKIPPED no session stamp" in gitlog(root)[before:]
    stamp_session(gate, sdir, sid)
    _time.sleep(1.1)
    handoff(tdir, "h" * 500)

    # ⭐ THE SAME ON A PROMPT AT PACE: a handoff written after the warning still gets armed.
    armed()
    r = fire("UserPromptSubmit")
    assert spawned and folder in spawned[0], (
        "a PACE prompt with a fresh handoff armed nothing - the prompt path does not arm: %r"
        % (spawned,))
    assert "ARMED" in said(r) and folder in said(r), r

    # ⭐ THE SCAN ROOT IS THE START-TIME CWD, not the payload's. A stamp that recorded another
    # repository: the handoff recorded there is what gets armed, whatever cwd the payload says.
    root2 = os.path.join(sdir, "other-root")
    try:
        os.makedirs(os.path.join(root2, ".git"))
        f2 = "20260902-180000-other-root-task"
        d2 = os.path.join(root2, "Memory", "tasks", f2)
        os.makedirs(d2)
        with open(stamp, "w", encoding="utf-8") as f:
            _json.dump({"cwd": root2}, f)
        _time.sleep(1.1)
        handoff(d2, "z" * 500)
        wrote(os.path.join(d2, "HANDOFF.md"))
        armed()
        r = fire("Stop", cwd=root)
        assert spawned and f2 in spawned[0], (
            "the start-time cwd was recorded and the payload cwd won: %r" % (spawned,))
    finally:
        stamp_session(gate, sdir, sid)
        shutil.rmtree(root2, ignore_errors=True)
    _time.sleep(1.1)
    handoff(tdir, "h" * 500)

    # ⛔ THE STAND-DOWN TABLE, AMENDED (ADR decision 6 ⟨R2⟩): a PACE prompt KEEPS the alarm
    # (no cancel, no re-arm: the de-dup sees the same target) - measured before the change, 20
    # arms and 19 cancels in a 20-turn PACE session. A GO prompt cancels it AND clears the spawn
    # floor, so the next turn end at PACE re-arms without waiting out the 300 s.
    sys.path.insert(0, repo_path("hooks"))
    import resume as _resume
    cancelled = []

    def _fake_cancel(sdir_, quiet=False, all_jobs=False, session_id=None):
        cancelled.append(sdir_)
        try:
            os.remove(os.path.join(sdir_, "resume",
                                   gate.safe_session(session_id) + ".json"))
        except OSError:
            pass
        return 0

    mark = gate.state_path(sdir, sid, gate.ARM_MARK)
    keep_cancel = _resume.do_cancel
    _resume.do_cancel = _fake_cancel
    try:
        armed(task=folder, armed_for_reset=r5, at=now + 3600)
        with open(mark, "w") as f:
            f.write(str(_time.time()))                     # a fresh floor, as after an arm
        usage_at(band_pcts(gate)[0])
        r = fire("UserPromptSubmit", clear_floor=False)
        assert not cancelled, "a PACE prompt cancelled the alarm the turn end armed"
        assert os.path.exists(os.path.join(sdir, "resume",
                                           gate.safe_session(sid) + ".json")),             "the alarm went away at PACE"
        assert not spawned, "a PACE prompt re-armed an alarm that was already armed"
        usage_at(10)
        r = fire("UserPromptSubmit", clear_floor=False)
        assert cancelled, "a GO prompt did not stand the armed resume down"
        assert not os.path.exists(mark), (
            "the stand-down left the spawn floor in place - the next turn end cannot re-arm")
        assert "CANCELLED" in said(r) or "CANCELLED" in str(r), r
        # ...and the very next turn end at PACE arms again, floor or no floor.
        usage_at(band_pcts(gate)[0])
        r = fire("Stop", clear_floor=False)                # the cancel above removed the floor
        assert spawned and folder in spawned[0], spawned
    finally:
        _resume.do_cancel = keep_cancel

    os.remove(os.path.join(sdir, "token_usage.json"))
    armed()
    if os.path.exists(seen):
        os.remove(seen)
    for d in (tdir, odir, pdir):
        shutil.rmtree(d, ignore_errors=True)
    print("ok - the turn's end arms the resume for the handoff THIS session wrote (recorded, not "
          "mtime), once, said on screen; a pulled file, no stamp, stale, thin and GO stay silent "
          "and logged; PACE keeps the alarm, GO cancels it and clears the floor")


def case_selftests_never_read_the_terminal():
    """⛔ NO SHIPPED `--selftest` MAY BLOCK ON STDIN. Measured, and it cost two hours.

    `unattended.py`'s main() drains stdin - correctly, because that is where a hook payload
    arrives and an unread pipe can break the writer. Its selftest then CALLED main(), so with
    a terminal on stdin it waited for an end of file that a terminal never sends. Two runs of
    test_all.py sat on it for over an hour printing nothing, and `python unattended.py
    --selftest` typed by hand hung the same way - which is the documented way to diagnose an
    install, so the hang was in the shipped product and not only in the checks.

    ⚠ The condition is reproduced rather than described: the parent holds the write end of a
    pipe open and never writes to it, which is what an idle terminal looks like. A child that
    reads stdin never returns, so it is killed and the case FAILS instead of hanging too.
    """
    # ⚠ `resume.py` has no `--selftest` - it prints its usage and exits 2. It is checked
    # anyway, because the property being tested is "does not BLOCK", not "passes": it is a
    # shipped entry point a person may type, and if it ever grows a stdin read this catches it.
    # ⛔ AND NO SHIPPED --selftest MAY WRITE INTO THE REAL STATE DIRECTORY. From 0.52.1 the
    # gate log goes to `usage.state_dir()` as well as to the repository copy, and selftest()
    # runs the real decision paths - so every suite run filed 45 `DENY(ultracode)` lines into
    # the owner's own log until this was caught. ⚠ Measured 2026-09-01, and found by the OWNER
    # asking why their log was full of refusals for a mode no session had switched on. A check
    # that pollutes the evidence it exists to protect is worse than no check.
    # ⚠ This reads the real state directory deliberately - reading is the only way to know -
    # and never writes to it.
    # ⛔ LINES, NOT THE FILE SIZE, and the difference decides whether this check works at all.
    # It used to compare `len(f.read())` before and after. But EVERY live session on the
    # machine appends a `CMD-ALLOW` line here on EVERY Bash call, so any concurrent session
    # failed the assertion - with a message blaming the selftest. Measured 2026-09-18: three
    # consecutive whole-file runs failed twice (105 and 143 bytes) and reached the rest only
    # on the third. ⇒ It is not merely noisy: this case runs immediately BEFORE the prose pin,
    # so it ABORTED the run before later assertions executed, and a mutation check driven
    # through the whole file read as "caught" while the assertion under test never ran.
    # ⚠ THE RESIDUAL GAP, accepted on purpose: a selftest that wrote a `CMD-ALLOW` or
    # `CMD-DENY` line into the real directory slips past this filter. The alternative is the
    # size comparison, which failed on somebody else's traffic two runs in three and therefore
    # protected nothing. A check that is red for an unrelated reason is not a stricter check.
    LIVE_TRAFFIC = ("CMD-ALLOW", "CMD-DENY")

    def _real_state_lines():
        try:
            with open(os.path.join(usage_state_dir(), "dispatch_gate.log"),
                      encoding="utf-8") as f:
                return f.read().splitlines()
        except OSError:
            return []

    def _suspect(rows):
        """The new lines that a LIVE session's tool traffic cannot account for.

        ⛔ RECORDS, NOT LINES, and that distinction is the whole correctness of this filter.
        `log()` writes one record as `timestamp + message`, but the message is the COMMAND
        TEXT and it is truncated by character count, not at the first newline - so a heredoc
        or any multi-line command leaves continuation lines with NO timestamp prefix.
        Measured 2026-09-18 in the real log: 1383 such lines against 10145 timestamped ones.
        ⇒ A per-line filter flags every one of them, which is a red for an unrelated reason -
        the exact failure the size comparison was replaced to remove.

        ⚠ A leading continuation line belongs to a record that started BEFORE the window, so
        it is not new and is never flagged - hence `live` starts True.
        """
        out, live = [], True
        for row in rows:
            head = re.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d ", row)
            if head:
                msg = row[head.end():]
                live = (not msg) or msg.startswith(LIVE_TRAFFIC)
            if not live:
                out.append(row)
        return out

    # ⭐ THE FILTER GETS ITS CONTROLS IN THIS RUN. A `_suspect` that matched nothing - a typo
    # in the prefix, a regex that eats the whole line - would report a clean pass for ever;
    # one that matched everything would be red for ever. Both directions, and both of them
    # for a multi-line record too, because that is the case three green runs did not cover.
    assert _suspect(["2026-09-18 14:00:00 USAGE(STOP) pct=99"]), \
        "the filter no longer flags a line only a selftest could have written"
    assert not _suspect(["2026-09-18 14:00:00 CMD-ALLOW(checked=5 off=-) ls"]), \
        "the filter flags another live session's ordinary tool traffic"
    assert not _suspect(["2026-09-18 14:00:00 CMD-ALLOW(checked=5 off=-) python - <<'PY'",
                         "import io", "PY"]), \
        "the filter flags the continuation lines of a live session's multi-line command"
    assert _suspect(["2026-09-18 14:00:00 USAGE(STOP) pct=99", "and its second line"]) == \
        ["2026-09-18 14:00:00 USAGE(STOP) pct=99", "and its second line"], \
        "a suspect record must carry its continuation lines with it"
    assert not _suspect(["a continuation of a record that started before the window"]), \
        "a leading continuation line was flagged - its record is not new"

    _state_before = _real_state_lines()
    for script, expect_ok in (("dispatch_gate.py", True), ("usage.py", True),
                              ("unattended.py", True), ("resume.py", False)):
        path = repo_path("hooks", script)
        if not os.path.exists(path):
            continue
        p = subprocess.Popen([sys.executable, path, "--selftest"],
                             stdin=subprocess.PIPE,      # held open, never written, never closed
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             cwd=repo_path(),
                             env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        try:
            rc = p.wait(timeout=90)
        except subprocess.TimeoutExpired:
            p.kill()
            raise AssertionError(
                "%s --selftest blocked with an open stdin - it reads the terminal" % script)
        if expect_ok:
            assert rc == 0, "%s --selftest exited %s" % (script, rc)
    _state_after = _real_state_lines()
    # ⚠ PREFIX COMPARISON, with a set fallback: the log is append-only in practice, but a
    # rotation or a truncation during the window would make `len(before)` meaningless and
    # every old line read as new.
    if _state_after[:len(_state_before)] == _state_before:
        _new = _state_after[len(_state_before):]
    else:
        _old = set(_state_before)
        _new = [r for r in _state_after if r not in _old]
    _bad = _suspect(_new)
    assert not _bad, (
        "a shipped --selftest wrote into the REAL state directory (%s):\n   %s"
        % (os.path.join(usage_state_dir(), "dispatch_gate.log"),
           "\n   ".join(_bad[:5])))
    print("ok - no shipped --selftest blocks on stdin or writes to the real state dir")


def case_skill_copies():
    """⛔ ONE SKILL NAME, ONE FILE THAT REGISTERS IT. Frontmatter is what does the registering.

    Each skill directory holds `SKILL.md` - the skill - and `SKILL.zh-TW.md`, a reading copy
    for people. ⚠ THE READING COPY HAS NO FRONTMATTER, DELIBERATELY: a frontmatter block there
    would register a SECOND skill under the same base name, and which one a session loaded
    would be invisible from outside. That is precisely the duplicate 0.23.1 rewrote §19 to
    forbid, so it is asserted here rather than left to whoever edits the file next.

    ⭐ And the reading copy must keep SAYING it is only a reading copy. Without that line
    somebody reasonably concludes the translation is authoritative and edits it instead.
    """
    import glob
    import re
    frontmatter = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.S)
    paths = sorted(glob.glob(os.path.join(repo_path("skills"), "*", "SKILL*.md")))
    assert len(paths) >= 4, "expected two files per skill, found %r" % (paths,)
    for path in paths:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        with open(path, "rb") as f:
            assert f.read().count(b"\x00") == 0, "%s has NUL bytes" % path
        m = frontmatter.match(text)
        if ".zh-TW." in path:
            assert m is None, \
                "%s has frontmatter and would register as a second skill" % path
            assert "不是 skill 本身" in text, \
                "%s no longer declares itself a reading copy" % path
        else:
            assert m, "%s has no frontmatter, so nothing registers the skill" % path
            keys = dict(re.findall(r"^([a-z_]+):\s*(.*)$", m.group(1), re.M))
            assert keys.get("name"), (path, sorted(keys))
            assert keys.get("description"), (path, sorted(keys))
            assert keys["name"] == os.path.basename(os.path.dirname(path)), \
                "%s: frontmatter name %r does not match its directory" % (path, keys["name"])
        # ⛔ AND NO LIVE SKILL MAY TELL ANYBODY TO INSTALL A SECOND COPY. §19 said exactly
        # that until 0.23.1, inside a document its readers are required to follow.
        for line in text.splitlines():
            if "~/.claude/skills" not in line:
                continue
            assert ("Never create" in line or "絕對不要建立" in line), \
                "%s still points at a user-level skill copy: %r" % (path, line.strip())
    print("ok - one file registers each skill, and the reading copy stays a reading copy")


def case_cowork_restates_nothing():
    """⛔ ONE LIVE COPY PER RULE: `skills/cowork/` may point at `unattended-work` and
    `dispatch-protocol`, never restate them.

    Two instruments, because each misses what the other catches (ADR 20260919-204317, D7 and
    round 1's B3): a word-bag Jaccard over section BODIES at a floor calibrated on known
    restatements (0.25 - the pairs it was tuned on scored 0.29-0.31, a synthetic one 0.62), and
    an exact match on NORMALISED HEADINGS - because the restatement that shipped in the first
    merge had an identical heading and scored 0.167, under the floor.

    ⚠ The scope is printed in the pass line: zh-TW reading copies are out (their Latin word
    bags are empty by construction), and so are README.md and PROTOCOL.md (they describe the
    skills and restate them by design). A test that hides its exclusions is measuring a corpus
    nobody asked about.
    ⛔ MUTATION-CHECKED both ways on a temporary corpus: a copied section must produce a pair,
    a copied heading must fire the heading check.
    """
    import glob
    import re
    import shutil
    FLOOR = 0.25
    STOP = set(("the a an is are be it its this that of to in on for and or not you your they "
                "as with by at from what which when who how so if then than but do does did done "
                "one two more most less can cannot will would should must may might have has had "
                "was were been being there their them he she his her i we us our me my").split())

    def sections(path):
        with open(path, "rb") as f:
            text = f.read().decode("utf-8")
        parts = re.split(r"^(#{2,4} .+)$", text, flags=re.M)
        found = []
        for i in range(1, len(parts), 2):
            head = parts[i].strip("# ").strip()
            body = parts[i + 1] if i + 1 < len(parts) else ""
            if len(body.split()) >= 25:
                found.append((path, head, body))
        return found

    def bag(text):
        return set(w for w in re.findall(r"[a-z][a-z'-]{2,}", text.lower()) if w not in STOP)

    def sim(a, b):
        return len(a & b) / float(len(a | b)) if a and b else 0.0

    def norm_head(h):
        h = re.sub(r"^[\d.]+\s+", "", h)
        return re.sub(r"[^a-z0-9 ]", "", h.lower()).strip()

    def is_cowork(path):
        return os.sep + "cowork" + os.sep in path or "/cowork/" in path

    def measure(files):
        """(pairs involving cowork at or above FLOOR, heading overlaps involving cowork, n)."""
        secs = [s for p in files for s in sections(p)]
        bags = [bag(b) for _, _, b in secs]
        pairs = []
        for i in range(len(secs)):
            for j in range(i + 1, len(secs)):
                if is_cowork(secs[i][0]) == is_cowork(secs[j][0]):
                    continue                  # same side: cowork×cowork or skill×skill
                score = sim(bags[i], bags[j])
                if score >= FLOOR:
                    pairs.append((score, secs[i][1], secs[j][1]))
        other = {}
        for p in files:
            if is_cowork(p):
                continue
            for line in open(p, encoding="utf-8"):
                m = re.match(r"^#{2,4}\s+(.*)$", line.rstrip())
                if m and len(norm_head(m.group(1)).split()) >= 3:
                    other.setdefault(norm_head(m.group(1)), []).append(os.path.basename(p))
        heads = []
        for p in files:
            if not is_cowork(p):
                continue
            for line in open(p, encoding="utf-8"):
                m = re.match(r"^#{2,4}\s+(.*)$", line.rstrip())
                if m and norm_head(m.group(1)) in other:
                    heads.append((m.group(1).strip(), os.path.basename(p)))
        return pairs, heads, len(secs)

    # ⭐ CONTROLS FIRST, in this run. A floor that let the known restatement through, or that
    # flagged unrelated text, would make an empty result meaningless either way.
    p1 = ("When a budget is nearly spent, the remaining budget is for finishing the work and "
          "writing the handover, not for starting the next thing you wanted to do")
    p2 = ("A nearly spent budget is spent on finishing and on writing the handover; it is not "
          "spent starting another thing")
    pos = sim(bag(p1), bag(p2))
    assert pos >= FLOOR, "POSITIVE control: a deliberate restatement scored %.2f < %.2f" % (pos, FLOOR)
    neg = sim(bag("a scheduled wake-up prompt is written before you know what today teaches"),
              bag("print the version on the first line of the output so copies differ"))
    assert neg < FLOOR, "NEGATIVE control: unrelated texts scored %.2f >= %.2f" % (neg, FLOOR)

    files = sorted(p for p in glob.glob(os.path.join(repo_path("skills"), "*", "SKILL*.md"))
                   if ".zh-TW." not in p)
    files += sorted(glob.glob(os.path.join(repo_path("skills"), "cowork", "reference", "*.md")))
    assert any(is_cowork(p) for p in files) and any(not is_cowork(p) for p in files), files
    pairs, heads, n = measure(files)
    assert not pairs, "cowork restates another skill (Jaccard >= %.2f):\n  %s" % (
        FLOOR, "\n  ".join("%.2f  %s  <->  %s" % t for t in pairs))
    assert not heads, "a cowork heading is identical to another skill's: %r" % (heads,)

    # ⛔ MUTATION 1: a section copied from unattended-work into a cowork file -> a pair.
    with scratch_dir("restate-mutation") as d:
        mut = os.path.join(d, "skills")
        for p in files:
            rel = os.path.relpath(p, repo_path("skills"))
            dst = os.path.join(mut, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy(p, dst)
        uw = os.path.join(mut, "unattended-work", "SKILL.md")
        # ⚠ A section whose HEADING has three or more words, because the heading check ignores
        # shorter ones on purpose ("Install" would match everywhere). The first version of this
        # mutation copied "1. Dispatch" and read its own blindness as the check's.
        uw_secs = [s for s in sections(uw)
                   if len(s[2].split()) >= 40 and len(norm_head(s[1]).split()) >= 3]
        assert uw_secs, "no unattended-work section long enough, with a 3-word heading, to copy"
        _, head, body = uw_secs[0]
        planted = os.path.join(mut, "cowork", "reference", "planted.md")
        with open(planted, "w", encoding="utf-8") as f:
            f.write("# planted\n\n### Restated on purpose, under a different heading\n" + body)
        mfiles = [os.path.join(mut, os.path.relpath(p, repo_path("skills"))) for p in files] + [planted]
        mpairs, mheads, _ = measure(mfiles)
        assert mpairs, "MUTATION 1: a copied section produced no pair - the Jaccard check is blind"
        # ⛔ MUTATION 2: only the HEADING copied, body unrelated -> the heading check fires.
        with open(planted, "w", encoding="utf-8") as f:
            f.write("# planted\n\n### %s\n\n" % head +
                    "Entirely unrelated body text about pelicans and lighthouses, long enough to "
                    "count as a section but sharing no vocabulary with the source at all, so the "
                    "word-bag score stays under the floor while the heading is identical.\n")
        mpairs2, mheads2, _ = measure(mfiles)
        assert mheads2, "MUTATION 2: an identical heading was not caught - the heading check is blind"
        assert not mpairs2, "MUTATION 2 control: the unrelated body should not score >= floor"
    print("ok - cowork restates nothing in unattended-work/dispatch-protocol: %d sections, "
          "Jaccard floor %.2f (POSITIVE %.2f, NEGATIVE %.2f), 0 heading overlaps; excluded: "
          ".zh-TW copies, README.md, PROTOCOL.md; both mutations killed" % (n, FLOOR, pos, neg))


def case_burn_figure_never_winds_down():
    """⛔ THE `SPENT in ~N min` SENTENCE MAY NOT BE WRITTEN AS A REASON TO STOP.

    The brake reads the PERCENTAGE and never the burn figure - the owner's decision of
    2026-08-29 (`Memory/notes/SHELVED-burn-meter.md`: 「GO / PACE / STOP 派工或剎車都不參考
    這個值」), pinned in usage.py by a check that forces the figure and asserts the verdict
    does not move. ⚠ A skill that tells an agent to hand over on N enforces, in prose, exactly
    the rule the code refuses to enforce - and prose is the half that actually reaches the
    agent.

    ⛔ NOT HYPOTHETICAL. 0.56.2 to 0.58.1 said "N is your budget ... write the handover BEFORE
    it runs out" and "STOP for a new wave". Agents armed a resume and stopped at 20% of the
    five-hour window, because the line fires at the START of a window, not the end: the rate
    is anchored at the window's own open, so a young window makes any spend look steep.
    MEASURED 2026-09-14 - 10% used 10 minutes in prints `SPENT in ~90 min`; the same 10% at 45
    minutes in prints nothing at all.
    """
    import glob
    import re
    # ⭐ Each pattern is a phrasing that actually shipped, not a guess at one. A detector
    # written against imagined wording cannot fail on the wording that caused the incident.
    FORBIDDEN = (
        (r"N is (?:your|the) budget", "calls N a budget"),
        (r"handover inside N", "tells the agent to hand over inside N"),
        (r"handover BEFORE it runs out", "makes N the handover trigger"),
        (r"STOP for a new wave", "turns N into a dispatch verdict"),
        (r"N\s*(?:是|就是)[^\n]{0,12}預算", "calls N a budget (zh)"),
        (r"在\s*N\s*(?:之內|以內)[^\n]{0,8}(?:寫|交接)", "tells the agent to hand over inside N (zh)"),
        # ⛔ AND PACE IS NOT A HANDOVER EITHER - the same class of defect, one verdict over.
        # These two are the phrasings that SHIPPED in unattended-work §17 through 0.60.0,
        # beside a hook that agreed with them: the owner ruled on 2026-09-17 that PACE means
        # start no new batch, and STOP is the one that winds down. ⚠ The English one spanned a
        # line break in the file, so it needs [\s\S] and not [^\n].
        # ⛔ TIGHT ON PURPOSE - `says **PACE**` and `判定說 **PACE**`, not PACE anywhere
        # nearby. Round 2 measured the loose version going RED on the CORRECT rule written the
        # obvious way ("You hand over when the verdict is STOP, not PACE", "判定說 PACE 不是
        # 交接，STOP 才交接"). A detector that blocks the right edit is worse than one that
        # misses a paraphrase, because the REQUIRED sentence below already catches removal,
        # while a false red costs somebody an afternoon and teaches them to delete the check.
        (r"hand over when the verdict[\s\S]{0,6}says \*\*PACE\*\*",
         "makes PACE a handover trigger"),
        (r"判定說\s*\*\*PACE\*\*[^\n]{0,20}才交接", "makes PACE a handover trigger (zh)"),
    )
    # ⚠ WHICH PATTERNS ARE ABOUT PACE, so the failure does not blame the burn figure for a
    # finding that has nothing to do with it. Index into FORBIDDEN, kept beside it.
    PACE_PATS = (6, 7)
    # ⚠ The scoping sentence is REQUIRED, not merely the bad one absent. A file that says
    # nothing about N leaves the agent to infer, and inference is what this is fixing.
    REQUIRED = {"SKILL.md": "At GO you keep working",
                "SKILL.zh-TW.md": "判定是 GO 就繼續做"}
    paths = sorted(glob.glob(os.path.join(repo_path("skills"), "*", "SKILL*.md")))
    assert len(paths) >= 4, "expected two files per skill, found %r" % (paths,)
    seen = 0
    for path in paths:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for _i, (pat, why) in enumerate(FORBIDDEN):
            assert not re.search(pat, text), \
                "%s %s - %s" % (path, why,
                                "PACE means start no new batch; STOP is the verdict that "
                                "hands over (owner's ruling, 2026-09-17)" if _i in PACE_PATS
                                else "the burn figure sizes the NEXT block, it never winds "
                                     "anybody down")
        if "SPENT in" not in text:
            continue                      # this file does not carry the rule at all
        seen += 1
        want = REQUIRED["SKILL.zh-TW.md" if ".zh-TW." in path else "SKILL.md"]
        assert want in text, \
            "%s discusses the burn figure but never says %r" % (path, want)
    # ⛔ BOTH SKILLS, BOTH LANGUAGES. An English-only fix leaves the pair drifted, which is how
    # this defect survived: the zh-TW files never carried the bad rule, so a grep for the
    # English phrasing looked clean in half the repository.
    assert seen == 4, \
        "expected all four skill files to carry the burn rule, found %d" % seen
    # ⚠ MUTATION CHECK: the detector must fire on the text that actually shipped.
    for pat, _why in FORBIDDEN[:4]:
        assert re.search(pat, "That N is your budget ... write the handover inside N, and "
                              "write the handover BEFORE it runs out. GO with a small N is "
                              "still GO for the step you are on and STOP for a new wave."), \
            "the detector misses 0.58.1's own wording: %r" % pat
    assert re.search(FORBIDDEN[4][0], "N 是你的預算"), FORBIDDEN[4][0]
    assert re.search(FORBIDDEN[5][0], "在 N 之內寫好交接"), FORBIDDEN[5][0]
    # ⚠ AND THE SAME MUTATION CHECK for the two PACE patterns, against the lines that shipped
    # in unattended-work §17 through 0.60.0 - verbatim, line break included.
    assert re.search(FORBIDDEN[6][0], "You hand over when the verdict\nsays **PACE** or "
                                      "**STOP** - never because"), FORBIDDEN[6][0]
    assert re.search(FORBIDDEN[7][0], "判定說 **PACE** 或 **STOP** 才交接"), FORBIDDEN[7][0]
    # ⛔ AND THE FALSE-POSITIVE CONTROL, which is the half a detector normally lacks. Round 2
    # measured the loose first version going RED on the CORRECT rule written the obvious way,
    # so these two lines are the reason the patterns are tight. A detector that blocks the
    # right edit gets deleted by the next person who hits it.
    for ok in ("You hand over when the verdict is STOP, not PACE.",
               "判定說 PACE 不是交接，STOP 才交接。",
               "⛔ AND PACE IS NOT A HANDOVER. It means start no new batch.",
               "⛔ 而 PACE 不是交接。它的意思是不要開新的一批。"):
        for pat, why in (FORBIDDEN[i] for i in PACE_PATS):
            assert not re.search(pat, ok), \
                "the detector calls a CORRECT sentence %r: %r fires on %r" % (why, pat, ok)
    # ⛔ AND SAYING IT IS REQUIRED, not merely the bad line absent - the same argument as
    # REQUIRED above. A file that says nothing leaves the agent to infer from "the window is
    # closing", and inference is what put the hook and the skill on opposite sides.
    PACE_SAYS = {"SKILL.md": "PACE IS NOT A HANDOVER",
                 "SKILL.zh-TW.md": "PACE 不是交接"}
    pace_seen = 0
    for path in paths:
        if "unattended-work" not in path.replace("\\", "/"):
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        want = PACE_SAYS["SKILL.zh-TW.md" if ".zh-TW." in path else "SKILL.md"]
        assert want in text, "%s never says %r - PACE means start no new batch, and STOP is " \
                             "the verdict that hands over (owner's ruling, 2026-09-17)" \
                             % (path, want)
        pace_seen += 1
    # ⛔ AND THE FILTER MUST HAVE MATCHED SOMETHING. A loop that iterates zero times asserts
    # nothing and reports success - the same silent route the verdict-set check closes in
    # dispatch_gate.py's selftest. Rename the skill folder and this says so instead of
    # passing.
    assert pace_seen == 2, \
        "expected both unattended-work SKILL files, found %d in %r" % (pace_seen, paths)
    print("ok - the burn figure sizes the next block and winds nobody down, in both languages")


def main():
    fresh_scratch()
    case_selftests_never_read_the_terminal()
    case_skill_copies()
    case_cowork_restates_nothing()
    case_burn_figure_never_winds_down()
    with scratch_dir("state") as sdir, scratch_dir("repo") as root:
        fixture_repo(root)
        gate = load_gate(sdir)
        stamp_session(gate, sdir, "s1")
        # ⚠ `s1` HAS SEEN THE COWORK SKILL, from the start. `stamp_session()` writes a bare "1",
        # which carries no cwd and is never a peer - but case_session_cwd_is_recorded drives a
        # REAL SessionStart with cwd=root, and that session's JSON .start plus its fresh .alive
        # make it a live peer of s1 for every case that runs after it. Measured: without this
        # line the first `git commit` case_branch drives from s1 was refused by the cowork nag,
        # and its mutation ("remove the branch guard, the commit goes through") read as "left
        # standing". ⭐ Driven as a Skill call, not written to disk, and NOT switched off in
        # config: an off switch would put `off=guard_cowork_first` on every allow line, which
        # case_switches_and_logging asserts is `off=-`. case_cowork_first uses its own session
        # ids and is the one place the nag is exercised. (Review A, F8.5, corrected the earlier
        # comment, which said the fixture's stamps themselves were peers.)
        load_skills(gate, root, "s1", "dispatch-guard:cowork")
        case_add_all(gate, sdir, root)
        case_commit_m(gate, sdir, root)
        case_silenced_search(gate, sdir, root)
        case_relative_cd(gate, sdir, root)
        case_switches_and_logging(gate, sdir, root)
        case_fail_open(gate, sdir, root)
        case_advisory_without_stamp(gate, sdir, root)
        case_append_only(gate, sdir, root)
        case_cowork_first(gate, sdir, root)
        case_unattended_first(gate, sdir, root)
        case_require_skills(gate, sdir, root)
        case_skill_price_table(gate)
        case_price_refresh(gate, sdir)
        case_handoff_past_soft(gate, sdir, root)
        case_auto_arm(gate, sdir, root)
        case_arm_on_stop(gate, sdir, root)
        case_model_price_limit(gate, sdir, root)
        case_session_cwd_is_recorded(gate, sdir, root)
        case_wind_down_on_every_tool(gate, sdir, root)
        case_agent_report_file(gate, sdir, root)
        case_unpushed(gate, sdir, root)
        # ⚠ Last: it moves the fixture's branch, and the cases above assume `master`.
        case_branch(gate, sdir, root)
    print("all guard checks passed")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
