#!/usr/bin/env python3
"""Run every check this repository has, and fail if any of them does.

    python Tools/Debug/test_all.py

⛔ WHY A RUNNER FOR SEVEN COMMANDS. Because seven commands run by hand is six chances to
forget one, and this project has already paid for that: the gate's own selftest exercised
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
    ("usage",         [repo_path("hooks", "usage.py"), "--selftest"]),
    ("unattended",    [repo_path("hooks", "unattended.py"), "--selftest"]),
    ("install",       [os.path.join(DEBUG_DIR, "test_install.py")]),
    ("resume cancel", [os.path.join(DEBUG_DIR, "test_resume_cancel.py")]),
    ("cmd guards",    [os.path.join(DEBUG_DIR, "test_guards.py")]),
    ("usage debug dump", [os.path.join(DEBUG_DIR, "test_usage_debug_dump.py")]),
]

# ⚠ Per check, not for the whole run. The slowest of these takes seconds; anything near this
# is a hang, and a hang has to become a legible FAILURE. See the call site.
CHECK_TIMEOUT = 180


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
    print("\n%d/%d passed" % (len(CHECKS) - len(failed), len(CHECKS)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
