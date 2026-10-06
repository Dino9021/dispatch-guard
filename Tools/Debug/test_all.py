#!/usr/bin/env python3
"""Run every check this repository has, and fail if any of them does.

    python Tools/Debug/test_all.py

⛔ WHY A RUNNER. Because every command run by hand is one more chance to forget one, and this
project has already paid for that (the list is `CHECKS` below; no count is written here, since a
written count went stale twice): the gate's own selftest exercised
the clock's DECISION function and never called the clock, so a NameError that disabled the
entire gate shipped through five releases with every check green. The lesson was not "write
another check" - it was that a check nobody runs is the same as no check.

⚠ None of these touches ~/.claude, spends an API call, or creates a scheduled task.
⭐ EVERY FILE THEY PRODUCE GOES UNDER `Tools/Debug/scratch/`, which is gitignored and kept
after the run: if a check failed, what it wrote is still there to look at. A run that leaves
`git status` dirty is itself a defect - two of the checks here exist because a test wrote
outside its sandbox, once into the working tree and once into ~/.claude.
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import HERE as DEBUG_DIR, REPO, fresh_scratch, repo_path  # noqa: E402

# ⭐ Two kinds of check, and they live in different places on purpose: the `--selftest`
# entry points ship WITH the hooks, because a person diagnosing an install needs them
# available from the installed copy. The three scripts here never ship in a useful sense -
# they exercise install.py against scratch directories - so they live under Tools/Debug.
CHECKS = [
    ("dispatch gate", [repo_path("hooks", "dispatch_gate.py"), "--selftest"]),
    # ⚠ Parses the COMMITTED fixture, never the network. A check that quietly needs the
    # internet passes for the wrong reason on the day the page changes shape.
    ("model pricing", [repo_path("hooks", "model_pricing.py"), "--selftest"]),
    # ⚠ Runs the generated launcher for real, including its fallback. It says on its own
    # output when the fallback could not be exercised, rather than skipping quietly.
    ("shim", [repo_path("hooks", "shim.py"), "--selftest"]),
    ("usage",         [repo_path("hooks", "usage.py"), "--selftest"]),
    ("unattended",    [repo_path("hooks", "unattended.py"), "--selftest"]),
    ("install",       [os.path.join(DEBUG_DIR, "test_install.py")]),
    ("resume cancel", [os.path.join(DEBUG_DIR, "test_resume_cancel.py")]),
    ("resume launch", [os.path.join(DEBUG_DIR, "test_resume_launch.py")]),
    ("net zone",      [os.path.join(DEBUG_DIR, "test_net_zone.py")]),
    ("cmd guards",    [os.path.join(DEBUG_DIR, "test_guards.py")]),
    # ⛔ 0.64.0 shipped a cowork SKILL.md whose frontmatter was invalid YAML, and the skill
    # vanished from every session without a warning. This reads each SKILL.md the way the
    # loader does. See its docstring.
    ("skill frontmatter", [os.path.join(DEBUG_DIR, "test_skill_frontmatter.py")]),
    # ⚠ Drives the gate as a SUBPROCESS through allow / refuse / release. The defect it
    # covers lived in the event wiring, not in any function: every unit involved passed
    # while a failed dispatch held its slot for half an hour.
    ("slot lifecycle", [os.path.join(DEBUG_DIR, "test_slot_lifecycle.py")]),
    ("usage debug dump", [os.path.join(DEBUG_DIR, "test_usage_debug_dump.py")]),
    # ⚠ Runs the watch LOOP for a few seconds and counts what comes out. The defect it
    # covers - an idle watcher redrawing a too-wide line for ever - cannot be seen from a
    # pure function, only from the loop that never returns.
    ("usage watch", [os.path.join(DEBUG_DIR, "test_usage_watch.py")]),
    # ⚠ A diagnostic tool rots exactly like shipped code, and this one rots INTO A
    # LIE: a broken comparison prints "no difference", which is also the honest
    # answer on an idle machine. Its selftest plants a change and fails if it is
    # not reported. It touches no VS Code state - it diffs two fixtures in a temp
    # directory - so it is safe in the suite.
    ("vscode snapshot", [os.path.join(DEBUG_DIR, "vscode_snapshot.py"), "--selftest"]),
    # ⚠ The cowork nag's evidence reader. Its selftest parses a fixture log and judges GHOST /
    # LOADED for two firings; a parser that silently matched nothing would report "0 firings"
    # for ever and the owner's collect-first decision would rest on an empty page.
    ("cowork nag report", [os.path.join(DEBUG_DIR, "cowork_nag_report.py"), "--selftest"]),
    # ⚠ Runs the cowork folder watcher for real. Through 0.69.0 it listed only the top folder,
    # and two sessions answered each other in subfolders neither watcher could see.
    ("watch folder", [os.path.join(DEBUG_DIR, "test_watch_folder.py")]),
    # ⚠ The README's skill flowcharts (0.70.3) are a second description of the hook. This keeps
    # one chart per skill per language, the zh/en pairs identical in shape, and red meaning a
    # box that names the hook. It reads README.md only; it cannot render them or judge a label.
    ("readme charts", [os.path.join(DEBUG_DIR, "test_readme_charts.py")]),
]

# ⚠ Per check, not for the whole run. The slowest of these takes seconds; anything near this
# is a hang, and a hang has to become a legible FAILURE. See the call site.
CHECK_TIMEOUT = 180


def _resume_tasks():
    """Every `ClaudeDispatchGuardResume*` task registered on this machine; None if unknowable.

    ⛔ A CHECK MUST NOT LEAVE A REAL SCHEDULED TASK BEHIND. Found 2026-09-28: three
    `ClaudeDispatchGuardResume-<dir>-slot-lifecycle` entries, registered by a check whose gate
    auto-armed against the machine's real usage, pointing into temp folders that no longer
    existed. No single check can see that; only a count before and after the whole run can.
    """
    if os.name != "nt":
        return None
    try:
        r = subprocess.run(["schtasks", "/Query", "/FO", "CSV", "/NH"], capture_output=True,
                           timeout=120, stdin=subprocess.DEVNULL)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    text = (r.stdout or b"").decode("mbcs", "replace")
    return set(re.findall(r'"\\(ClaudeDispatchGuardResume[^"\\]*)"', text))


def _real_shims():
    """{path: bytes} of the USER'S launchers in ~/.claude/dispatch-guard (absent -> None).

    ⛔ Measured 2026-10-01: three checks re-pointed the real shim at this checkout through the
    gate's SessionStart statusline repair (install.py hard-codes the real state dir), so the
    machine's scheduled resumes and statusline ran uncommitted code. Bytes AND mtime before ==
    after, or the run fails - the same shape as `_resume_tasks`.
    ⚠ The mtime is what makes it hold: a live session's SessionStart (the installed copy) puts the
    shim BACK within minutes, so bytes alone read "unchanged" after a rewrite - measured, the first
    mutation of this guard survived that way. shim.write never rewrites identical content, so any
    mtime change is a real rewrite (a plugin update during the run would be one too).
    """
    d = os.path.join(os.path.expanduser("~"), ".claude", "dispatch-guard")
    out = {}
    for n in ("run.sh", "run.cmd"):
        p = os.path.join(d, n)
        try:
            with open(p, "rb") as f:
                out[n] = (f.read(), os.stat(p).st_mtime_ns)
        except OSError:
            out[n] = None
    return out


def main():
    # ⛔ THE RUNNER'S OWN CONSOLE, and it matters most when something FAILS. The children are
    # already read as UTF-8, but printing their ⭐ and ⚠ back out through a legacy codepage
    # raised UnicodeEncodeError - so the one run that needed its output printed nothing but a
    # traceback about printing. A reporter that dies while reporting is worse than no
    # reporter: the exit code says "failed" and the reason is gone.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    # ⭐ Prepared HERE, once, so the children inherit DG_SCRATCH_PREPARED and add to it
    # instead of each wiping the last one's files.
    fresh_scratch()
    tasks_before = _resume_tasks()
    shims_before = _real_shims()
    failed = []
    for name, argv in CHECKS:
        # ⚠ cwd is the REPOSITORY, not this folder: the hook selftests resolve sibling
        # modules from their own location, and install.py reads config.example.json beside
        # itself, so neither cares - but a check that shells out to git needs a repository.
        try:
            r = subprocess.run([sys.executable] + argv,
                               cwd=REPO, capture_output=True, text=True,
                               # ⛔ NEVER THE TERMINAL. A check that reads stdin blocks until
                               # end of file, and a terminal never sends one - `unattended.py`
                               # drains stdin because that is where a hook payload arrives, so
                               # inheriting it left two runs of this file sitting for over an
                               # hour with nothing on screen. DEVNULL gives every child an
                               # immediate EOF, whether this runs in a terminal or not.
                               stdin=subprocess.DEVNULL,
                               # ⚠ AND A CEILING, so the next hang is a FAILURE rather than a
                               # wait. A check that never returns is worse than one that fails:
                               # the exit code never arrives, so nothing reports anything.
                               timeout=CHECK_TIMEOUT,
                               # ⚠ The child prints ⭐ and ⛔; a legacy console codepage would
                               # raise UnicodeDecodeError here rather than in the child.
                               encoding="utf-8", errors="replace",
                               env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            ok = r.returncode == 0
        except subprocess.TimeoutExpired as exc:
            r = subprocess.CompletedProcess(
                argv, 1, stdout=(exc.stdout or ""),
                stderr="TIMED OUT after %ds - the check never returned.\n" % CHECK_TIMEOUT)
            ok = False
        print("%-16s %s" % (name, "PASS" if ok else "FAIL"))
        if not ok:
            failed.append((name, argv, r))
    total = len(CHECKS)
    tasks_after = _resume_tasks()
    if tasks_before is not None and tasks_after is not None:
        total += 1
        left = sorted(tasks_after - tasks_before)
        print("%-16s %s" % ("no tasks left", "FAIL" if left else "PASS"))
        if left:
            failed.append(("no tasks left", [os.path.join(DEBUG_DIR, "test_all.py")],
                           subprocess.CompletedProcess([], 1, stdout="", stderr=(
                               "the run left %d NEW scheduled task(s) - a check reached the real "
                               "scheduler (or a live session armed meanwhile; the name says "
                               "which): %s\n" % (len(left), ", ".join(left))))))
    else:
        print("%-16s %s" % ("no tasks left", "not checked (no Windows scheduler to ask)"))
    total += 1
    moved = sorted(n for n, b in _real_shims().items() if b != shims_before.get(n))
    print("%-16s %s" % ("real shim kept", "FAIL" if moved else "PASS"))
    if moved:
        failed.append(("real shim kept", [os.path.join(DEBUG_DIR, "test_all.py")],
                       subprocess.CompletedProcess([], 1, stdout="", stderr=(
                           "the run rewrote the USER'S %s in ~/.claude/dispatch-guard - a check "
                           "reached the real state dir. Put it back with the installed copy's "
                           "`python <plugin>/hooks/shim.py`.\n" % ", ".join(moved)))))
    for name, argv, r in failed:
        print("\n---- %s ----\n%s%s" % (name, r.stdout[-2000:], r.stderr[-2000:]))
        # ⭐ POINT AT WHAT IT WROTE. Every file a check produces is kept after the run, on
        # purpose - that is the whole reason the scratch directory lives in the repository
        # instead of the system temp directory. ⛔ But nothing said so, so the kept files were
        # only ever useful to somebody who already knew they existed, which is the person who
        # wrote them. A record nobody is told about is a record nobody reads.
        # ⚠ The directory is named after the SCRIPT, not after the label in CHECKS -
        # _debugpaths._owner() derives it from __main__. Guessing from the label gives
        # "cmd_guards" for a directory called "test_guards", a path that does not exist.
        stem = os.path.splitext(os.path.basename(argv[0]))[0]
        for cand in (os.path.join(DEBUG_DIR, "scratch", stem),
                     os.path.join(DEBUG_DIR, "scratch")):
            if os.path.isdir(cand):
                print("what it wrote is still here: %s" % cand)
                break
    print("\n%d/%d passed" % (total - len(failed), total))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
