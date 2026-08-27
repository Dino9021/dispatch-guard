#!/usr/bin/env python3
"""Where the checks live, what they check, and the one place they may write.

⛔ EVERY FILE A CHECK PRODUCES GOES UNDER `Tools/Debug/scratch/`, and nowhere else. Two
failures paid for this rule, both of which looked like the plugin misbehaving rather than a
test misbehaving:

  - `test_resume_cancel.py` called `do_cancel()` with the REPOSITORY as the working
    directory, and `resume.log_line()` appends to `<cwd>/.claude/dispatch-gate.log`. Every
    run left the plugin's own log, in the plugin's own location, in the working tree - which
    is indistinguishable from the development copy being executed by a real session.
  - `test_install.py` patched `SETTINGS` but not `STATE_DIR`, so an uninstall case wrote
    `auto_statusline: false` into the real `~/.claude/dispatch-guard/config.json`.

⭐ A scratch directory INSIDE the repository, rather than the system temp directory, is the
deliberate choice: what a failing run left behind is still there to look at, one `git status`
proves the tree is clean, and one `.gitignore` line keeps it out of every commit.

⚠ Paths here are relative to this file, never to the working directory. A check may be run
from anywhere - `python Tools/Debug/test_all.py` from the root, or from inside this folder -
and both must reach the same repository.
"""

import contextlib
import os
import shutil
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# Tools/Debug -> Tools -> the repository root.
REPO = os.path.dirname(os.path.dirname(HERE))
SCRATCH = os.path.join(HERE, "scratch")


def repo_path(*parts):
    """A path inside the repository under test. `repo_path("install.py")`, etc."""
    return os.path.join(REPO, *parts)


# ⛔ SET BY WHICHEVER PROCESS PREPARED THE SCRATCH DIRECTORY, and inherited by the checks it
# spawns. Without it every child wiped the directory on startup and took the previous child's
# evidence with it - so after a full run only the LAST check's files were left, which is
# exactly backwards: the one that failed is the one whose files you want.
PREPARED = "DG_SCRATCH_PREPARED"


def fresh_scratch():
    """Empty `Tools/Debug/scratch/` once per RUN, and return it.

    ⚠ Once per run, not once per process and not once per case: a failing run's files must
    survive until the next run, which is the whole reason they live in the repository rather
    than in the system temp directory.
    """
    if os.environ.get(PREPARED):
        os.makedirs(SCRATCH, exist_ok=True)
        return SCRATCH
    if os.path.isdir(SCRATCH):
        shutil.rmtree(SCRATCH, ignore_errors=True)
    os.makedirs(SCRATCH, exist_ok=True)
    with open(os.path.join(SCRATCH, "README.txt"), "w", encoding="utf-8") as f:
        f.write("Written by the checks in Tools/Debug. Gitignored, and safe to delete.\n"
                "Kept after a run on purpose: if a check failed, what it wrote is here.\n")
    os.environ[PREPARED] = stamp()
    return SCRATCH


def _owner():
    """The running script's name, used to namespace its directories.

    ⚠ Two checks both numbering from 01 in one shared directory would overwrite each other's
    cases, and the numbers would say nothing about which check produced them.
    """
    import __main__
    name = os.path.basename(getattr(__main__, "__file__", "") or "check")
    return os.path.splitext(name)[0] or "check"


_n = [0]


@contextlib.contextmanager
def scratch_dir(name="case"):
    """`scratch/<check>/NN-name/` for one case. Never removed on exit.

    ⭐ Numbered so the order of cases is legible afterwards, namespaced by the check that
    produced them, and NOT deleted at the end - fresh_scratch() clears the lot at the start
    of the next RUN instead. A directory that deletes itself takes the evidence away exactly
    when a case has just failed.
    """
    _n[0] += 1
    d = os.path.join(SCRATCH, _owner(), "%02d-%s" % (_n[0], name))
    os.makedirs(d, exist_ok=True)
    yield d


def stamp():
    """A per-run marker, so two runs are distinguishable in the scratch directory."""
    return time.strftime("%Y%m%d-%H%M%S")
