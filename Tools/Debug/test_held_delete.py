#!/usr/bin/env python3
"""guard_held_delete (0.75.8) - the deletes Claude Code holds for the owner, refused first.

    python Tools/Debug/test_held_delete.py

⛔ EVERY SHAPE HERE WAS MEASURED, not imagined: headless `claude -p --permission-mode
bypassPermissions` on Claude Code 2.1.291 (Windows), first tool_result - and the BASH_REPARSE_* lists (0.75.9)
on 2.1.304 (macOS). HELD = Claude Code answered
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
import time

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


# 0.75.9: Bash tool, NO directory change - Claude Code parses a single-quoted string AGAIN when the
# command defines a function or runs eval, and holds an rm after a separator in it whose target can
# become `/`.
# Measured 2026-10-22 on 2.1.304 (macOS, headless, sonnet, the exact command checked); names are
# the probe case ids in Memory/tasks/20261021-105230-held-delete-guard/scratch/03-reparse-probes/.
BASH_REPARSE_HELD = [
    ('S=/tmp/dg-s/grmut && rm -rf $S && mkdir -p $S && f=graph-servers/graph-refresh.sh\nmut() { name=$1; shift; sed "$@" $f > $S/m.sh; if cmp -s $S/m.sh $f; then echo "$name: NOT APPLIED"; return; fi; o=$(REFRESH_UNDER_TEST=$S/m.sh sh graph-servers/test-graph-refresh.sh 2>&1); printf \'%s\\n\' "$o" | grep -q \'PASS .*FAIL$\' || { echo "$name: INVALID"; return; }; r=$(printf \'%s\\n\' "$o" | grep \'  FAIL\' | head -2 | tr \'\\n\' \';\'); if [ -n "$r" ]; then echo "$name: KILLED by:$r"; else echo "$name: SURVIVED"; fi; }\nmut L1-steal-live -e \'s/^        if lock_holder_alive "\\$lock"; then$/        if false; then/\'\nmut L2-no-pid-written -e \'s/^    echo \\$\\$ >"\\$lock\\/pid"$/    :/\'\nmut L3-no-recycle-check -e \'s/^    case \\$(ps -p "\\$_p" -o command= 2>\\/dev\\/null) in \\*graph-refresh\\*) return 0 ;; esac$/    return 0/\'\nmut L4-release-any -e \'s/^    \\[ "\\$({ tr -d . \\\\n\\\\r. <"\\$lock\\/pid"; } 2>\\/dev\\/null)" = "\\$\\$" \\] \\&\\& rm -rf "\\$lock"$/    rm -rf "$lock"/\'\nmut O1-output-dropped -e \'s/^            \\[ -s "\\$out_file" \\] \\&\\& tail -n 15 "\\$out_file" | sed .s\\/\\^\\/    | \\/. >>"\\$log_file"$/            :/\'\nmut O2-log-on-success -e \'s/^        if \\[ \\$rc -ne 0 \\]; then$/        if true; then/\'\nrm -rf $S', 'A-full'),
    ('mut() { echo "$1"; }\nmut L4-release-any -e \'s/^    \\[ "\\$({ tr -d . \\\\n\\\\r. <"\\$lock\\/pid"; } 2>\\/dev\\/null)" = "\\$\\$" \\] \\&\\& rm -rf "\\$lock"$/    rm -rf "$lock"/\'', 'C-L4-only'),
    ('mut() { echo "$1"; }\nmut L4-release-any -e \'s/^    \\[ "\\$({ tr -d . \\\\n\\\\r. <"\\$lock\\/pid"; } 2>\\/dev\\/null)" = "\\$\\$" \\] \\&\\& rm -rf "\\$lock"$/    rm -rf "$lock"/\'', 'H10-C-again'),
    ('mut() { echo "$1"; }; mut \'s/"\\$(x)" \\&\\& rm -rf "$lock"/\'', 'J01-func-subst-amp-escaped'),
    ('mut() { echo "$1"; }; mut \'"\\$(x)" && rm -rf "$lock"/\'', 'J02-func-subst-amp-plain'),
    ('mut() { echo "$1"; }; mut \'$(x) && rm -rf "$lock"/\'', 'J03-func-bare-subst'),
    ('mut() { echo "$1"; }; mut \'"\\$({ x; } 2>/dev/null)" = "\\$\\$" \\] \\&\\& rm -rf "$lock"/\'', 'J06-func-brace-subst'),
    ('mut() { echo "$1"; }\nsed -e \'s/^    \\[ "\\$({ tr -d . \\\\n\\\\r. <"\\$lock\\/pid"; } 2>\\/dev\\/null)" = "\\$\\$" \\] \\&\\& rm -rf "\\$lock"$/    rm -rf "$lock"/\' graph-servers/graph-refresh.sh > /dev/null', 'J08-funcdef-newline-sed-L4'),
    ('mut() { echo "$1"; }; mut L4-release-any -e \'s/^    \\[ "\\$({ tr -d . \\\\n\\\\r. <"\\$lock\\/pid"; } 2>\\/dev\\/null)" = "\\$\\$" \\] \\&\\& rm -rf "\\$lock"$/    rm -rf "$lock"/\'', 'J11-func-sameline-L4'),
    ('mut() { echo "$1"; }; mut \'$(x) && rm -rf $lock/*\'', 'K05-target-star'),
    ('mut() { echo "$1"; }; mut \'$(x) && rm -f "$lock"/\'', 'K08-rm-f-only'),
    ('function mut { echo "$1"; }; mut \'$(x) && rm -rf "$lock"/\'', 'K10-function-keyword'),
    ('mut() { echo "$1"; }; mut \'`x` && rm -rf "$lock"/\'', 'K12-backtick'),
    ('mut() { echo "$1"; }; mut \'$(x) && rm -rf "${lock}"/\'', 'K13-braced-var'),
    ('eval \'$(true) && rm -rf "$lock"/\'', 'L02-eval-subst'),
    ('mut() { echo "$1"; }; mut \'$(x); rm -rf "$lock"/\'', 'L04-func-semicolon'),
    ('mut() { echo "$1"; }; mut \'$(x) || rm -rf "$lock"/\'', 'L05-func-oror'),
    ('mut() { echo "$1"; }; mut \'$(x) | rm -rf "$lock"/\'', 'L06-func-pipe'),
    ('mut() { echo "$1"; }; mut \'$(x) && rm -rf "$lock"/*\'', 'L08-target-quoted-star'),
    ('mut() { echo "$1"; }; mut \'$(x) && rm -rf $lock/\'', 'L09-target-unquoted-slash'),
    ('mut() { echo "$1"; }; mut \'$(x) && rm "$lock"/\'', 'L10-rm-noflag-slash'),
    ('mut() { echo "$1"; }; mut \'$(x) && rm -r -f "$lock"/\'', 'L11-rm-split-flags'),
    ('mut() { echo "$1"; }; mut \'$(x) && rm -rf "$lock"/ more\'', 'L12-text-after-target'),
    ('eval true; echo \'$(x) && rm -rf "$lock"/\'', 'M02-eval-elsewhere'),
    ('mut () { echo "$1"; }; mut \'$(x) && rm -rf "$lock"/\'', 'M03-funcdef-space-paren'),
    ('mut() { echo "$1"; }; mut \'a && rm -rf "$lock"/\'', 'N01-func-no-subst-separator'),
    ('if true; then eval "$x"; fi\necho \'a && rm -rf "$v"/ x\'', 'P11-eval-after-then'),
    ('f(){ x; }\necho \'a && \'\\\'\'b && rm -rf "$v"/ x\'', 'U17-split-string-rm-in-second-piece'),
]
BASH_REPARSE_RAN = [
    ('S=/tmp/dg-s/grmut && rm -rf $S && mkdir -p $S && f=graph-servers/graph-refresh.sh\nrm -rf $S', 'B-setup-only'),
    ('S=/tmp/dg-s/grmut && rm -rf "$S" && mkdir -p "$S" && f=graph-servers/graph-refresh.sh\nrm -rf "$S"', 'D-quoted-S'),
    ('rm -rf /tmp/dg-s/grmut && mkdir -p /tmp/dg-s/grmut\nrm -rf /tmp/dg-s/grmut', 'E-literal-path'),
    ('rm -rf "$lock"', 'F01-real-unassigned'),
    ('rm -rf "${lock:?}"', 'F02-real-guarded'),
    ('rm -rf "$lock/dg-probe-nonexistent-1/x"', 'F03-real-deep'),
    ('rm -rf "$lock/dg-probe-nonexistent-2"', 'F04-real-toplevel'),
    ('lock=/tmp/dg-s/f05 && mkdir -p "$lock" && rm -rf "$lock"', 'F05-assigned-in-command'),
    ('echo \'rm -rf "$lock"\'', 'F06-echo-single-quoted'),
    ("grep -c 'rm -rf $lock' graph-servers/graph-refresh.sh", 'F07-grep-pattern'),
    ('echo \'rm -rf "${lock:?}"\'', 'F08-echo-guarded'),
    ("echo 'rm -rf /dg-probe-nonexistent-3'", 'F09-echo-literal'),
    ("echo 'rm -rf $HOME'", 'F10-echo-home'),
    ("sed -e 's/x/rm -f $f/' graph-servers/graph-refresh.sh > /dev/null", 'F11-sed-rm-f'),
    ('echo "rm -rf \\$lock"', 'F12-echo-escaped-dollar'),
    ("echo 'rm $x'", 'F13-echo-rm-noflag'),
    ('cat > /tmp/dg-s/f14.sh <<\'EOF\'\nrm -rf "$lock"\nEOF', 'F14-heredoc-body'),
    ('true # rm -rf "$lock"', 'F15-comment'),
    ("printf '%s\\n' 's/a/b/' > /tmp/dg-s/f16.sed && sed -f /tmp/dg-s/f16.sed graph-servers/graph-refresh.sh > /dev/null", 'F16-sed-file-instead'),
    ('echo \'rm -rf "$lock"/pid\'', 'F17-echo-rm-sub-relative'),
    ('mut() { echo "$1"; }; mut \'rm -rf "$lock"\'', 'G01-func-arg-plain'),
    ('dgprobe_unknown_cmd \'rm -rf "$lock"\'', 'G02-unknown-cmd-arg'),
    ('echo \'s/x $(y) && rm -rf "$lock"/\'', 'G03-echo-with-subst'),
    ('sed -e \'s/^    \\[ "\\$({ tr -d . \\\\n\\\\r. <"\\$lock\\/pid"; } 2>\\/dev\\/null)" = "\\$\\$" \\] \\&\\& rm -rf "\\$lock"$/    rm -rf "$lock"/\' graph-servers/graph-refresh.sh > /dev/null', 'G04-sed-L4-expr'),
    ('sh -c \'rm -rf "$lock"\'', 'G05-sh-c'),
    ('eval \'rm -rf "$lock"\'', 'G06-eval'),
    ('mut() { echo "$1"; }; mut \'rm -rf "${lock:?}"\'', 'G07-func-arg-guarded'),
    ('mut() { echo "$1"; }; mut \'rm -rf /dg-probe-nonexistent-4\'', 'G08-func-arg-literal'),
    ('mut() { echo "$1"; }; mut \'echo hi\'', 'G09-func-arg-control'),
    ('echo \'a; rm -rf "$lock"\'', 'G10-echo-semicolon-rm'),
    ('echo \'{ tr x; } && rm -rf "$lock"\'', 'G11-echo-brace-semicolon'),
    ('echo \'$(true) rm -rf "$lock"\'', 'G12-echo-subst-only'),
    ('sh -c \'rm -rf "${lock:?}"\'', 'G13-sh-c-guarded'),
    ('lock=/tmp/dg-s/g14 && mut() { echo "$1"; }; mut \'rm -rf "$lock"\'', 'G14-func-arg-assigned'),
    ('echo \'rm -rf "$lock"/\'', 'H01-echo-slash'),
    ("echo 'rm -rf $lock/*'", 'H02-echo-star'),
    ('mut() { echo "$1"; }; mut \'rm -rf "$lock"/\'', 'H03-func-slash'),
    ('mut() { echo "$1"; }; mut \'rm -rf $lock/*\'', 'H04-func-star'),
    ('sed -e \'s/a/rm -rf "$lock"\\//\' graph-servers/graph-refresh.sh > /dev/null', 'H05-sed-slash'),
    ('mut() { echo "$1"; }\nmut \'rm -rf "$lock"/\'', 'H06-func-newline-slash'),
    ('mut() { echo "$1"; }; mut -e \'s/x/    rm -rf "$lock"/\'', 'H07-func-unbalanced-tail'),
    ('echo -e \'s/x/    rm -rf "$lock"/\'', 'H08-echo-unbalanced-tail'),
    ('sed -e \'s/x/    rm -rf "$lock"/\' graph-servers/graph-refresh.sh > /dev/null', 'H09-sed-unbalanced-tail'),
    ('echo \'"\\$(x)" \\&\\& rm -rf "$lock"/\'', 'J04-echo-subst-amp-escaped'),
    ('printf \'%s\\n\' \'"\\$(x)" \\&\\& rm -rf "$lock"/\'', 'J05-printf-subst-amp-escaped'),
    ('sed -e \'"\\$({ x; } 2>/dev/null)" = "\\$\\$" \\] \\&\\& rm -rf "$lock"/\' graph-servers/graph-refresh.sh > /dev/null', 'J07-sed-brace-subst'),
    ('echo L4-release-any -e \'s/^    \\[ "\\$({ tr -d . \\\\n\\\\r. <"\\$lock\\/pid"; } 2>\\/dev\\/null)" = "\\$\\$" \\] \\&\\& rm -rf "\\$lock"$/    rm -rf "$lock"/\'', 'J09-echo-L4'),
    ('true\nsed -e \'s/^    \\[ "\\$({ tr -d . \\\\n\\\\r. <"\\$lock\\/pid"; } 2>\\/dev\\/null)" = "\\$\\$" \\] \\&\\& rm -rf "\\$lock"$/    rm -rf "$lock"/\' graph-servers/graph-refresh.sh > /dev/null', 'J10-true-newline-sed-L4'),
    ('mut() { o=$(true); echo "$1"; }; mut \'rm -rf "$lock"/\'', 'K01-subst-in-body-rm-in-arg'),
    ('x=$(true); mut() { echo "$1"; }; mut \'rm -rf "$lock"/\'', 'K02-subst-before-funcdef'),
    ('mut() { echo "$1"; }; mut \'$(x) && rm -rf "$lock"\'', 'K03-target-no-slash'),
    ('mut() { echo "$1"; }; mut \'$(x) && rm -rf "${lock:?}"/\'', 'K04-target-guarded'),
    ('mut() { echo "$1"; }; mut \'$(x) && rm -rf "$lock/sub"\'', 'K06-target-toplevel-quoted'),
    ('mut() { echo "$1"; }; mut \'$(x) && rm -rf "$lock/a/b"\'', 'K07-target-deep-quoted'),
    ('mut() { echo "$1"; }; mut \'$(x) && rm "$lock"/x\'', 'K09-rm-noflag'),
    ('mut() { echo "$1"; }; mut \'$(x)\' \'rm -rf "$lock"/\'', 'K11-subst-and-rm-separate-args'),
    ('mut() { echo "$1"; }; mut \'$(x) rm -rf "$lock"/\'', 'K14-no-ampersand'),
    ('mut() { echo "$1"; }; mut "\\$(x) && rm -rf \\"\\$lock\\"/"', 'L07-func-double-quoted'),
    ('echo \'mut() { x; }\'; echo \'$(x) && rm -rf "$lock"/\'', 'M01-funcdef-only-in-quotes'),
    ('mut() { echo "$1"; }; mut \'$(x) && ls "$lock"/\'', 'N02-func-subst-ls-not-rm'),
    ('echo \'a mut() { x; }\'; echo \'$(x) && rm -rf "$lock"/\'', 'N03-quoted-funcdef-after-space'),
    ('# f(){ x; }\necho \'a && rm -rf "$v"/ x\'', 'O16-funcdef-in-comment'),
    ('echo "a f(){ x; }"\necho \'a && rm -rf "$v"/ x\'', 'P01-funcdef-in-double-quotes'),
]

# 0.75.11: Bash tool, no cd, no function/eval - an rm target with two or more unchecked variables, any of
# them not set by this command before the rm (a `for` variable, an environment variable) or once a loop has
# run; followed through a same-command D=. Measured 2026-10-22 on 2.1.291 (Windows, headless, sonnet, the
# exact command checked); ids are the probe cases in
# Memory/tasks/20261021-105230-held-delete-guard/scratch/00-probes/permprobe_run10..run14.
_S = "S=/c/x/s"
BASH_UNRESOLVED_HELD = [
    (_S + ' && for k in a b c/App/node_modules; do test -e "$S/$k/App/node_modules" && echo "LINK $k"; done; '
     'test -e $S/c/App/node_modules && echo "LINK c"; for k in a b; do D=$S/$k; find "$D" -maxdepth 3 -type l | '
     'head -2; du -sh "$D" | cut -f1; rm -rf "${D:?}" && echo "deleted $k"; done', 'P0-owner-shape'),
    (_S + ' && for k in a b; do D=$S/$k; rm -rf "${D:?}" && echo "deleted $k"; done', 'P1-loop-checked-var'),
    (_S + ' && for k in a b; do rm -rf "$S/$k" && echo "deleted $k"; done', 'P3-loop-direct'),
    (_S + ' && for k in a b; do D=$S/$k; rm -rf "$D" && echo "deleted $k"; done', 'P4-loop-var-unchecked'),
    (_S + '; for k in a b; do D=$S/$k; rm -rf "${D:?}"; done', 'P6-loop-checked-semicolon'),
    (_S + ' && for k in a b; do D=$S/$k/App; rm -rf "${D:?}"; done', 'B1-assigned-var-plus-literal'),
    (_S + ' && k=a && for d in x y; do echo "$d"; done; rm -rf "$S/$k"', 'Q1-loop-then-two-plain-vars'),
    ('for d in x y; do echo "$d"; done; ' + _S + '; k=a; rm -rf "$S/$k"', 'Q4-assigned-after-loop'),
    ('rm -rf "$DG_PROBE_UNSET_A/$DG_PROBE_UNSET_B"', 'Q7-two-unassigned-env-vars'),
    # Seen held interactively (the owner's second screenshot, 2026-10-22, Windows Game session):
    (_S + ' && for k in dev-b1 b1-final; do D=$S/$k; test -e "$D/App/node_modules" && { echo "LINK in $k"; '
     'continue; }; rm -rf "${D:?}" && echo "deleted $k"; done', 'S2-owner-screenshot-continue'),
]
BASH_UNRESOLVED_RAN = [
    (_S + ' && D=$S/a && rm -rf "${D:?}" && echo deleted', 'P2-checked-var-no-loop'),
    ('for d in /c/x/s/a /c/x/s/b; do rm -rf "$d"; done', 'P5-loop-literal'),
    (_S + ' && for k in a b; do D=$S/$k; du -sh "$D" | cut -f1; done', 'P7-no-rm-control'),
    (_S + ' && for k in a b; do rm -rf "${S:?}/${k:?}" && echo "deleted $k"; done', 'R1-direct-both-checked'),
    (_S + ' && for k in a b; do D="${S:?}/${k:?}"; rm -rf "$D" && echo "deleted $k"; done', 'R2-assigned-both-checked'),
    (_S + ' && for k in a b; do D="${S:?}/${k:?}"; rm -rf "${D:?}" && echo "deleted $k"; done',
     'R3-assigned-checked-then-guard'),
    ('for d in /c/x/s/a /c/x/s/b; do rm -rf "${d:?}" && echo "deleted $d"; done', 'R4-literal-loop-paths'),
    (_S + ' && k=a && rm -rf "$S/$k"', 'B2-two-vars-no-loop'),
    ('S=/c/x/s/a && rm -rf "$S"', 'B3-one-var-only'),
    (_S + ' && k=a && for d in x y; do rm -rf "$S/$k"; done', 'Q2-two-plain-vars-inside-loop'),
    (_S + ' && for d in x y; do echo "$d"; done; rm -rf "$S/a"', 'Q5-one-var-plus-literal-after-loop'),
    ('rm -rf "$DG_PROBE_UNSET_VAR/a"', 'Q6-unassigned-env-var-plus-literal'),
    (_S + ' && k=a && for d in x y; do echo "$d"; done; rm -rf "${S:?}/${k:?}"', 'W1-after-loop-both-checked'),
    ('rm -rf "${DG_PROBE_UNSET_A:?}/${DG_PROBE_UNSET_B:?}"', 'W2-unassigned-both-checked'),
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
        # 0.75.9: the re-parsed rm - its own reason, naming the rewrites that measured RAN.
        for c, note in BASH_REPARSE_HELD:
            r = run_gate(gate, bash(root, c))
            assert decision(r) == "deny", (note, c, r)
            for token in ("parses this quoted text AGAIN", "sed -f <file>", '"${VAR:?}"/', "Never delete through a link"):
                assert token in reason(r), (note, token, reason(r))
        for c, note in BASH_REPARSE_RAN:
            r = run_gate(gate, bash(root, c))
            assert decision(r) is None, (note, c, r)
        # Linear time: an unclosed `"` before 50 000 `\"` took 12-16 s through the first version (review R2 B1),
        # and a hook that times out ALLOWS the call. The bound is loose on purpose; the bad version is 10x over it.
        slow = 'f(){ x; }; echo "' + '\\"' * 50000
        t0 = time.time()
        cmd_guards._reparsed_rm(slow, cmd_guards._shell_segments(slow))
        assert time.time() - t0 < 1.5, "the re-parse check is slow again: %.1fs" % (time.time() - t0)
        # 0.75.11: the unresolved-variable target - its own reason, naming the rewrites that measured RAN.
        for c, note in BASH_UNRESOLVED_HELD:
            r = run_gate(gate, bash(root, c))
            assert decision(r) == "deny", (note, c, r)
            for token in ("`for` loop variable", '"${S:?}/${k:?}"', "for d in /abs/a /abs/b",
                          "Never delete through a link"):
                assert token in reason(r), (note, token, reason(r))
        for c, note in BASH_UNRESOLVED_RAN:
            r = run_gate(gate, bash(root, c))
            assert decision(r) is None, (note, c, r)
        real_lv = cmd_guards._unresolved_rm
        cmd_guards._unresolved_rm = lambda *a: None
        try:
            assert decision(run_gate(gate, bash(root, BASH_UNRESOLVED_HELD[1][0]))) is None, "unresolved-var mutation stood"
        finally:
            cmd_guards._unresolved_rm = real_lv
        held_n = len(held) + len(BASH_REPARSE_HELD) + len(BASH_UNRESOLVED_HELD)
        ran_n = len(ran) + len(BASH_REPARSE_RAN) + len(BASH_UNRESOLVED_RAN)
        # Mutation: without the re-parse branch the DevWK-Mac shape is no longer refused.
        real_rp = cmd_guards._reparsed_rm
        cmd_guards._reparsed_rm = lambda *a: None
        try:
            assert decision(run_gate(gate, bash(root, BASH_REPARSE_HELD[0][0]))) is None, "re-parse mutation stood"
        finally:
            cmd_guards._reparsed_rm = real_rp

        # The Bash reason names forms that RUN, and forbids the split (review B2).
        r = run_gate(gate, bash(root, "cd h1 && rm -f out/*"))
        for token in ('"${D:?}"/*', "absolute path", "Do not split it into two tool calls"):
            assert token in reason(r), token
        # 0.75.12: the scratch tool is named with the refused rm's OWN path words, so it deletes the same entries
        # (ADR 20261022-212421-scratch-clean-script D2, review B2) - and not in the re-parse reason, whose rm is
        # usually text inside a sed string.
        assert 'run.sh" scratch_clean.py out/*` in the same command' in reason(r), reason(r)
        r11 = run_gate(gate, bash(root, BASH_UNRESOLVED_HELD[2][0]))
        assert 'run.sh" scratch_clean.py "$S/$k"` in the same place' in reason(r11), reason(r11)
        assert "scratch_clean" not in reason(run_gate(gate, bash(root, BASH_REPARSE_HELD[0][0])))
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
          "unstamped checked" % (held_n, ran_n))
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
