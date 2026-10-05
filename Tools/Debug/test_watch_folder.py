#!/usr/bin/env python3
"""What `skills/cowork/tools/watch-folder.ps1` wakes on, checked by running it.

⛔ WHY. Through 0.69.0 the watcher listed only the TOP folder of the channel. The skill's own
layout puts check-ins in `checkin/`, so the shipped watcher could never see one - and on
2026-10-05 two sessions on two machines each built a channel in a different folder of the same
share, each watched only its own, and each answered the other in a place the other's watcher
could not see. The fix (0.69.1) watches the whole tree; recursion then needs two exclusions to
stay quiet: any `.claude` folder (a session started in the channel logs there on every tool
call) and the `-Ignore` entries, which are now relative paths or folders.

One case, two phases, one watcher process, `-Folder` given WITH a trailing separator:
  A. changes the watcher must NOT wake on - `.claude/`, your own root file (ignored as `./OWN.md`),
     your own check-in (ignored with a LEADING backslash, another case and backslashes), a file deep
     under an ignored folder (ignored as `memory/` for `Memory/`);
  B. a change to a HIDDEN file two folders deep that it MUST wake on, named by its relative path.
Mutation-checked (scratch of task 20261005-122013): removing `-Recurse` or `-Force` fails B;
removing the `.claude` skip, the folder-prefix match, its case-insensitivity, the exact match's
case-insensitivity, the separator normalisation or the `./` normalisation fails A. Not covered
here: a drive root (`W:` and its separator) and a UNC folder - both need a mapping this check
will not create; the task's refuter measured both (scratch/01-refuter, l2 and l11h).

    python Tools/Debug/test_watch_folder.py     (or Tools/Debug/test_all.py for all of them)

Standard library only. Needs PowerShell 7 (`pwsh`) - the tool itself refuses without it, so a
missing pwsh is a FAILURE here, never a quiet skip.
"""

import os
import shutil
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import fresh_scratch, repo_path, scratch_dir   # noqa: E402

WATCHER = repo_path("skills", "cowork", "tools", "watch-folder.ps1")
QUIET_SECONDS = 4      # phase A: four polls at -Every 1 with nothing it may wake on
WAKE_SECONDS = 15      # phase B: generous - pwsh start-up is the slow part, and it is already done


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


def _hide(path):
    """Set the Windows hidden attribute; refuse to run the case without it."""
    import ctypes
    FILE_ATTRIBUTE_HIDDEN = 0x2
    assert ctypes.windll.kernel32.SetFileAttributesW(path, FILE_ATTRIBUTE_HIDDEN), "cannot hide %s" % path


def case_whole_tree_with_exclusions(pwsh):
    with scratch_dir("whole-tree") as d:
        chan = os.path.join(d, "chan")
        for rel in ("BOARD.md", "OWN.md", os.path.join("checkin", "OWN.md"),
                    os.path.join("sub", "deep", "b.txt"), os.path.join(".claude", "x.log"),
                    os.path.join("Memory", "t.md")):
            _write(os.path.join(chan, rel), "seed\n")

        deep = os.path.join(chan, "sub", "deep", "b.txt")
        _hide(deep)
        cmd = [pwsh, "-NoProfile", "-WindowStyle", "Hidden", "-File", WATCHER,
               "-Folder", chan + os.sep, "-Every", "1", "-MaxMinutes", "1",
               "-Ignore", "./OWN.md, \\CHECKIN\\own.md ,memory/"]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", creationflags=flags)
        lines = []
        reader = threading.Thread(target=lambda: lines.extend(proc.stdout), daemon=True)
        reader.start()
        try:
            deadline = time.time() + 30
            while not any("watching" in ln for ln in lines) and time.time() < deadline:
                if proc.poll() is not None:
                    break
                time.sleep(0.2)
            head = "".join(lines)
            assert "watching" in head, "watcher never started: %r" % head
            assert "0.69.1" in head and "whole tree" in head, "first line carries no version: %r" % head

            # A - none of these may wake it.
            _write(os.path.join(chan, ".claude", "x.log"), "tool call\n")
            _write(os.path.join(chan, "OWN.md"), "my own entry\n")
            _write(os.path.join(chan, "checkin", "OWN.md"), "my own check-in\n")
            _write(os.path.join(chan, "Memory", "new", "deep.md"), "tooling\n")
            time.sleep(QUIET_SECONDS)
            assert proc.poll() is None, (
                "woke on an excluded change (exit %s): %r" % (proc.returncode, "".join(lines)))

            # B - this must wake it, and be named. The file is hidden: `-Force` is what lists it.
            _write(deep, "peer answer\n")
            try:
                rc = proc.wait(timeout=WAKE_SECONDS)
            except subprocess.TimeoutExpired:
                rc = None
            reader.join(timeout=5)
            out = "".join(lines)
            assert rc == 0, "a change two folders deep did not wake it (exit %r): %r" % (rc, out)
            changed = out.split("CHANGED", 1)[-1]
            assert "sub/deep/b.txt" in changed, "the wake does not name the file: %r" % out
            for quiet in (".claude", "OWN.md", "Memory"):
                assert quiet not in changed, "excluded %s reported: %r" % (quiet, out)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    print("OK  whole tree: a hidden file two folders deep wakes it and is named; .claude, own files "
          "(./, other case, backslash) and an ignored folder (other case) do not")


def main():
    fresh_scratch()
    pwsh = shutil.which("pwsh")
    if not pwsh:
        print("FAIL  pwsh (PowerShell 7) not found - watch-folder.ps1 cannot be exercised. "
              "Install: winget install --id Microsoft.PowerShell -e")
        return 1
    case_whole_tree_with_exclusions(pwsh)
    return 0


if __name__ == "__main__":
    sys.exit(main())
