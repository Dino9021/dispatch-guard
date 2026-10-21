#!/usr/bin/env python3
"""guard_held_delete (0.75.8) - the deletes Claude Code holds for the owner, refused first.

    python Tools/Debug/test_held_delete.py

⛔ EVERY SHAPE HERE WAS MEASURED, not imagined: headless `claude -p --permission-mode
bypassPermissions` on Claude Code 2.1.291 (Windows), first tool_result. HELD = Claude Code answered
"Dangerous rm operation detected" / "Remove-Item on system path … is blocked"; RAN = it ran. The guard
must deny every HELD shape and pass every RAN shape - an over-match costs the agent a pointless
rewrite, an under-match leaves the dialog that stalls a run for hours. Probe scripts and outputs:
Memory/tasks/20261021-105230-held-delete-guard/scratch/00-probes/ (and the reviewer's P1-P6 in
scratch/01-adr-review/). A Claude Code update can move the boundary: re-probe, then edit BOTH lists.

⭐ DRIVEN THROUGH main(), like test_guards.py - the wiring and the table order are part of what is
tested (the relative-cd WARNING sits after this guard and would otherwise answer first). Then the
guard is removed from cmd_guards.GUARDS and one HELD shape must stop being denied (mutation check),
the switch must turn it off, and a guard that raises must allow.
⚠ Nothing here touches ~/.claude, a network, or a scheduler; no command is executed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import fresh_scratch, scratch_dir  # noqa: E402
from test_guards import (bash, decision, fixture_repo, load_gate, load_skills, reason,  # noqa: E402
                         run_gate, stamp_session)

WIN = os.name == "nt"

# (command, note) - Bash tool, Claude Code HELD these on the first call.
BASH_HELD = [
    ("cd h1 && rm -f out/*", "F1 relative cd"),
    ("cd h6; rm -f out/*", "F1 cd then ;"),
    ("(cd h4 && rm -f out/*)", "F1 subshell"),
    ('(cd "C:\\x\\h4" && rm -f out/*)', "F2 subshell, quoted drive target"),
    ("pushd h5 >/dev/null && rm -f out/*", "F1 pushd"),
    ("rm -f h7/out/* && cd h7", "F1 rm BEFORE the cd"),
    ("cd n5/out && rm -f *", "run7 bare *"),
    ("cd r2 && rm -rf ./out/*", "run8 dot-relative"),
    ('cd k6 && D=out && rm -rf "$D"/*', "F2 plain variable"),
    ('cd k8 && rm -rf "$(cygpath -u \'C:/x\')/k8/out"/*', "F2 command substitution"),
    ('cd g5 && SIM=$(cat id.txt) && echo "$SIM" | head -1; rm -f out/*; echo done', "the owner's screenshot shape"),
]
# Windows only: Claude Code cannot resolve an MSYS target there (P1, run7 n4, the wii 7.3 h wait).
BASH_HELD_WIN = [
    ("cd /d/WorkSpace/x/q1 && rm -f out/*", "P1 MSYS cd"),
    ("cd /d/WorkSpace/wii/Build/Wii/app && php -l x && mkdir -p contract && rm -rf contract/* && cp -r a b",
     "the wii 7.3 h wait"),
]
# Bash tool, Claude Code RAN these on the first call - the guard must stay out of the way.
BASH_RAN = [
    ("cd n1 && rm -f out/*.log", "run7 pattern"),
    ("cd n2 && rm -f out/a*", "run7 prefix glob"),
    ("cd n6 && rm -f out/?.log", "run7 ? glob"),
    ('cd "D:\\x\\q2" && rm -f out/*', "P2 quoted drive cd (review B1)"),
    ('cd "C:\\x\\g7" && rm -f out/*', "g7 quoted drive cd (review B1)"),
    ("cd h3 && rm -f C:/x/h3/out/*", "F3 absolute glob"),
    ("cd m4 && rm -f D:/x/m4/out/*.log", "run6 absolute pattern"),
    ('cd r1 && D=out && rm -rf "${D:?}"/*', "run8 checked variable"),
    ('D=r3/out && cd r3 && rm -rf "${D:?}"/*', "run8 checked variable, set first"),
    ("cd h2 && rm -rf out", "F3 no glob"),
    ('cd h8 && D=out && rm -rf "$D"', "F3 variable, no glob"),
    ("cd h9 && rm -rf out/{a.txt,deep}", "F3 brace list"),
    ("cd h10 && find out -name '*.txt' -delete", "F3 find -delete"),
    ("cd k7 && find out -mindepth 1 -delete", "F3 find -mindepth"),
    ("cd k10 && rm -rf out && mkdir out", "F3 rm dir and recreate"),
    ("cd m2 && find out -maxdepth 1 -type f -name '*.log' -delete", "run6 find pattern"),
    ("rm -f g1/*", "F3 no directory change"),
    ("rm -rf g2/*", "F3 no directory change"),
    ('D=k9/out && rm -rf "$D"/*', "F3 variable glob, no directory change"),
    ("S=v1; rm -rf $S/sub", "F3 variable, no glob"),
    ("cat > q6/s.sh <<'EOF'\ncd build\nrm -f out/*\nEOF\nwc -l q6/s.sh", "P6 heredoc body (review N2)"),
    ('grep -n "cd x && rm -f out/*" notes.txt', "a quoted pattern is data (review N2)"),
]
# PowerShell tool.
PS_HELD = [
    ("Set-Location k1; Remove-Item -Recurse -Force out\\*", "F4 Set-Location"),
    ("Push-Location k2; Remove-Item -Recurse -Force out\\*; Pop-Location", "F4 Push-Location"),
    ("cd k3; Remove-Item -Recurse -Force out/*", "F4 cd alias, forward slash"),
    ("Remove-Item -Recurse -Force k4\\out\\*", "F4 no location change"),
    ("Remove-Item -Recurse -Force 'D:\\x\\q4\\out\\*'", "P4 absolute"),
    ("rm -Recurse -Force p1\\out\\*", "F4 alias rm"),
    ("del -Recurse -Force p2\\out\\*", "F4 alias del"),
    ("ri -Recurse -Force p3\\out\\*", "F4 alias ri"),
    ("Remove-Item -LiteralPath 'p4\\out\\*' -Recurse -Force -ErrorAction SilentlyContinue; 'done'", "F4 -LiteralPath"),
    ("Remove-Item -Path p6\\out\\* -Recurse -Force", "F4 -Path"),
]
PS_RAN = [
    ("Remove-Item n7\\out\\*.log", "run7 pattern"),
    ("Remove-Item n8\\out\\a*", "run7 prefix glob"),
    ("Remove-Item -LiteralPath p7\\out -Recurse -Force", "F5 literal directory"),
    ("Remove-Item -Recurse -Force t2", "F5 literal directory"),
    ("Get-ChildItem p5\\out | Remove-Item -Recurse -Force", "F5 pipeline"),
    ("Get-ChildItem q3\\out -Filter *.txt | Remove-Item -Force", "P3 filtered pipeline"),
]


def ps(root, command, sid="s1"):
    return bash(root, command, sid=sid, tool="PowerShell")


def main():
    fresh_scratch()
    with scratch_dir("state") as sdir, scratch_dir("repo") as root:
        fixture_repo(root)
        gate = load_gate(sdir)
        import cmd_guards                       # importable once load_gate() put hooks/ on the path
        stamp_session(gate, sdir, "s1")
        load_skills(gate, root, "s1", "dispatch-guard:cowork")    # no cowork nag in the way
        held = [(bash, c, n) for c, n in BASH_HELD + (BASH_HELD_WIN if WIN else [])] + \
               [(ps, c, n) for c, n in PS_HELD]
        ran = [(bash, c, n) for c, n in BASH_RAN] + [(ps, c, n) for c, n in PS_RAN]
        if not WIN:
            ran += [(bash, c, n + " (not Windows: an MSYS path is a real path here)") for c, n in BASH_HELD_WIN]
        for mk, c, note in held:
            r = run_gate(gate, mk(root, c))
            assert decision(r) == "deny", (note, c, r)
            assert "SAME entries in ONE command" in reason(r), (note, reason(r))
            assert "never delete through a link" in reason(r), (note, reason(r))
        for mk, c, note in ran:
            r = run_gate(gate, mk(root, c))
            assert decision(r) is None, (note, c, r)

        # The Bash reason names forms that RUN, and forbids the split (review B2).
        r = run_gate(gate, bash(root, "cd h1 && rm -f out/*"))
        for token in ('"${D:?}"/*', "absolute path", "Do not split it into two tool calls"):
            assert token in reason(r), token
        assert "Get-ChildItem <dir> | Remove-Item -Recurse -Force" in reason(run_gate(gate, ps(root, "Remove-Item k4\\out\\*")))

        # Mutation: without the row the same payload is no longer refused - it falls to the relative-cd
        # WARNING, which carries no permission decision.
        keep = cmd_guards.GUARDS
        cmd_guards.GUARDS = tuple(g for g in keep if g[0] != "guard_held_delete")
        try:
            assert decision(run_gate(gate, bash(root, "cd h1 && rm -f out/*"))) is None, "mutation left it standing"
            assert decision(run_gate(gate, ps(root, "Remove-Item k4\\out\\*"))) is None
        finally:
            cmd_guards.GUARDS = keep
        # Order: the guard must answer BEFORE the relative-cd warning (review N4).
        names = [k for k, _ in cmd_guards.GUARDS]
        assert names.index("guard_held_delete") < names.index("guard_relative_cd"), names

        # The switch turns it off and logs what it would have refused.
        with open(os.path.join(root, ".claude", "dispatch-guard.json"), "w", encoding="utf-8") as f:
            f.write('{"dispatch": {"guard_held_delete": false}}')
        try:
            assert decision(run_gate(gate, bash(root, "cd h1 && rm -f out/*"))) is None, "switch off ignored"
            with open(os.path.join(root, ".claude", "dispatch_gate.log"), encoding="utf-8") as f:
                assert "CMD-DISABLED(guard_held_delete)" in f.read(), "the off switch left no trace"
        finally:
            os.remove(os.path.join(root, ".claude", "dispatch-guard.json"))

        # Fail open: a guard that raises allows, and says so in the log.
        real = cmd_guards.g_held_delete
        boom = lambda *a: 1 / 0  # noqa: E731
        cmd_guards.GUARDS = tuple((k, boom if k == "guard_held_delete" else f) for k, f in keep)
        try:
            assert decision(run_gate(gate, bash(root, "cd h1 && rm -f out/*"))) is None
        finally:
            cmd_guards.GUARDS = keep
        assert cmd_guards.g_held_delete is real

        # An unstamped session stays advisory (cmd_guards invariant 2).
        assert decision(run_gate(gate, bash(root, "cd h1 && rm -f out/*", sid="never-stamped"))) is None

    print("ok - %d held shapes refused, %d ran shapes passed, mutation, order, switch, fail-open and "
          "unstamped checked" % (len(held), len(ran)))
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
