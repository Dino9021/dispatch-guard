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


def stamp_session(gate, sdir, sid="s1"):
    """Mark the session as started - without this every guard is advisory, by design."""
    os.makedirs(os.path.join(sdir, "state"), exist_ok=True)
    with open(gate.state_path(sdir, sid, "start"), "w", encoding="utf-8") as f:
        f.write("1")


def gitlog(root):
    p = os.path.join(root, ".claude", "dispatch-gate.log")
    try:
        with open(p, encoding="utf-8") as f:
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
    print("ok - each guard has its own switch, and allow/deny/disabled all log")


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
    old = dict(before)
    old["fetched_at"] = int(now - 25 * 3600)
    mp.write(old, live)
    assert not gate.prices_due(sdir, cfg, now), \
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
    print("ok - no shipped --selftest blocks on an open stdin")


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


def main():
    fresh_scratch()
    case_selftests_never_read_the_terminal()
    case_skill_copies()
    with scratch_dir("state") as sdir, scratch_dir("repo") as root:
        fixture_repo(root)
        gate = load_gate(sdir)
        stamp_session(gate, sdir, "s1")
        case_add_all(gate, sdir, root)
        case_commit_m(gate, sdir, root)
        case_silenced_search(gate, sdir, root)
        case_relative_cd(gate, sdir, root)
        case_switches_and_logging(gate, sdir, root)
        case_fail_open(gate, sdir, root)
        case_advisory_without_stamp(gate, sdir, root)
        case_unattended_first(gate, sdir, root)
        case_require_skills(gate, sdir, root)
        case_skill_price_table(gate)
        case_price_refresh(gate, sdir)
        case_model_price_limit(gate, sdir, root)
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
