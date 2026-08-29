#!/usr/bin/env python3
"""Snapshot the VS Code state that decides whether the folder-open task runs, and diff two.

⛔ WHY THIS EXISTS. "The first open after installing does nothing; the second one works" is
a claim about a DIFFERENCE, and no single reading can answer it - the question is which
byte changed between the two launches. VS Code keeps that state in five places, three of
them SQLite databases nobody can read with an editor, so "look at the files" is not
actionable advice until something lists them.

⭐ WHAT IT CAPTURES, and why each one is here:

  - `User/settings.json`   - `task.allowAutomaticTasks` lives here, and nowhere else counts:
                             VS Code honours it at USER scope only.
  - `User/tasks.json`      - the task itself. A first launch that never had it explains
                             everything, and Settings Sync can rewrite this file at startup.
  - `globalStorage/storage.json` and `globalStorage/state.vscdb`
                           - WORKSPACE TRUST lives in here. Measured 2026-08-29 on 1.135.0:
                             with trust at its default, a fresh folder produced NOT ONE
                             `RunAutomaticTasks` line in a trace log - the runner returns
                             before its first trace call. ⇒ An untrusted folder and a broken
                             task look exactly alike, and only this file tells them apart.
  - `workspaceStorage/<id>/` - per-folder memory, including `workbench.tasks.recentlyUsedTasks2`.
                             A folder VS Code has never run a task in is a different folder
                             from one it has, and that is precisely the first-vs-second
                             difference being hunted.
  - the plugin's own state directory listing, for `watch.alive` - the proof the watcher
                             actually drew, as opposed to the task merely being defined.

⚠ TAKE THE SNAPSHOT WITH VS CODE CLOSED. A running VS Code holds these databases open and
flushes them on exit, so a snapshot taken while it runs captures a half-written state and
the diff fills with noise that means nothing.

Usage:
    python vscode_snapshot.py before          # VS Code CLOSED, right after installing
    python vscode_snapshot.py after-first     # open VS Code, watch it fail, CLOSE it
    python vscode_snapshot.py after-second    # open it again (it works), CLOSE it
    python vscode_snapshot.py --diff before after-first
"""

import difflib
import glob
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vscode-snapshots")


def user_dir():
    """VS Code's User directory on this platform, or None."""
    home = os.path.expanduser("~")
    for p in (os.path.join(os.environ.get("APPDATA", ""), "Code", "User"),
              os.path.join(home, ".config", "Code", "User"),
              os.path.join(home, "Library", "Application Support", "Code", "User")):
        if p and os.path.isdir(p):
            return p
    return None


def dump_db(path):
    """Every key/value in a state.vscdb, sorted, as text.

    ⛔ COPIED BEFORE READING. VS Code keeps these open, and sqlite refuses a locked database
    rather than returning stale rows - which would turn a real reading into an exception in
    the middle of a snapshot. The -wal file comes along or the copy is missing whatever has
    not been checkpointed yet, which is exactly the recent activity being measured.
    """
    if not os.path.exists(path):
        return "(no such file)"
    tmp = tempfile.mkdtemp()
    try:
        copy = os.path.join(tmp, "db")
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(path + suffix):
                shutil.copy2(path + suffix, copy + suffix)
        rows = []
        con = sqlite3.connect(copy)
        try:
            for k, v in con.execute("select key, value from ItemTable"):
                rows.append("%s = %s" % (k, v))
        finally:
            con.close()
        return "\n".join(sorted(rows))
    except Exception as exc:                  # a locked or absent db is a READING, not a crash
        return "(could not read: %r)" % (exc,)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def read_text(path):
    if not os.path.exists(path):
        return "(no such file)"
    try:
        with open(path, "rb") as f:
            return f.read().decode("utf-8-sig", "replace")
    except OSError as exc:
        return "(could not read: %r)" % (exc,)


def listing(root):
    """Every file under `root` with its size and mtime - a directory as comparable text."""
    if not os.path.isdir(root):
        return "(no such directory)"
    out = []
    for base, _dirs, files in os.walk(root):
        for name in sorted(files):
            p = os.path.join(base, name)
            try:
                st = os.stat(p)
            except OSError:
                continue
            out.append("%s  %8d  %s" % (
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
                st.st_size, os.path.relpath(p, root).replace("\\", "/")))
    return "\n".join(sorted(out, key=lambda line: line.split("  ", 2)[2]))


def snapshot(label):
    u = user_dir()
    if not u:
        print("⛔ no VS Code User directory found - nothing to snapshot")
        return 1
    dest = os.path.join(OUT, label)
    os.makedirs(dest, exist_ok=True)
    parts = {
        "settings.json": read_text(os.path.join(u, "settings.json")),
        "tasks.json": read_text(os.path.join(u, "tasks.json")),
        "globalStorage-storage.json": read_text(
            os.path.join(u, "globalStorage", "storage.json")),
        "globalStorage-state.vscdb.txt": dump_db(
            os.path.join(u, "globalStorage", "state.vscdb")),
        "dispatch-guard-state.txt": listing(
            os.path.join(os.path.expanduser("~"), ".claude", "dispatch-guard")),
    }
    # ⚠ ONE FILE PER WORKSPACE, keyed by the FOLDER it describes rather than by the opaque
    # hash directory. The hash is stable, but a diff nobody can read back to a folder is a
    # diff nobody acts on.
    for d in sorted(glob.glob(os.path.join(u, "workspaceStorage", "*"))):
        meta = os.path.join(d, "workspace.json")
        if not os.path.exists(meta):
            continue
        try:
            who = json.load(open(meta, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        name = (who.get("folder") or who.get("workspace") or "unknown")
        safe = "".join(c if c.isalnum() else "-" for c in name)[-90:]
        parts["ws-%s.txt" % safe] = ("# %s\n# %s\n%s"
                                     % (name, os.path.basename(d),
                                        dump_db(os.path.join(d, "state.vscdb"))))
    for name, text in parts.items():
        with open(os.path.join(dest, name), "w", encoding="utf-8") as f:
            f.write(text)
    print("snapshot '%s' written to %s (%d files)" % (label, dest, len(parts)))
    print("⚠ take it with VS Code CLOSED, or the databases are caught mid-write.")
    return 0


def diff(a, b):
    da, db = os.path.join(OUT, a), os.path.join(OUT, b)
    for d in (da, db):
        if not os.path.isdir(d):
            print("⛔ no snapshot called '%s' (looked in %s)" % (os.path.basename(d), OUT))
            return 1
    names = sorted(set(os.listdir(da)) | set(os.listdir(db)))
    changed = 0
    for name in names:
        left = read_text(os.path.join(da, name)).splitlines()
        right = read_text(os.path.join(db, name)).splitlines()
        if left == right:
            continue
        changed += 1
        print("\n===== %s" % name)
        for line in difflib.unified_diff(left, right, a, b, lineterm="", n=0):
            # ⚠ Truncated per line: a single storage value can be tens of kilobytes of JSON,
            # and one of those scrolls the answer off the screen.
            print(line[:400])
    if not changed:
        print("no difference between '%s' and '%s'" % (a, b))
    else:
        print("\n%d file(s) differ" % changed)
    return 0


def selftest():
    """⛔ The one thing that must not silently pass: a diff that reports NO DIFFERENCE.

    Two snapshots of an idle machine legitimately come out identical, so "no difference"
    is also exactly what a broken comparison prints - and there is no way to tell them
    apart by looking. This plants a known change and fails if it is not reported.
    """
    global OUT
    keep, OUT = OUT, tempfile.mkdtemp()
    try:
        # ⚠ Joined with chr(10) rather than written as an escape: an escaped newline inside
        # generated code is how this very block first arrived as a syntax error.
        nl = chr(10)
        for label, second in (("a", "y = 2"), ("b", "y = 99")):
            os.makedirs(os.path.join(OUT, label))
            with open(os.path.join(OUT, label, "one.txt"), "w", encoding="utf-8") as f:
                f.write(nl.join(["x = 1", second, ""]))
        import contextlib
        import io as _io
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            diff("a", "b")
        out = buf.getvalue()
        assert "no difference" not in out, "a REAL change read as no difference:" + nl + out
        assert "y = 99" in out, "the changed line is not in the diff:" + nl + out
        # ...and identical snapshots must still say so, or every run cries wolf.
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            diff("a", "a")
        assert "no difference" in buf.getvalue(), buf.getvalue()
        print("ok - the diff reports a real change and stays quiet on none")
        return 0
    finally:
        shutil.rmtree(OUT, ignore_errors=True)
        OUT = keep


def main(argv):
    if argv == ["--selftest"]:
        return selftest()
    if len(argv) == 3 and argv[0] == "--diff":
        return diff(argv[1], argv[2])
    if len(argv) == 1 and not argv[0].startswith("-"):
        return snapshot(argv[0])
    print(__doc__)
    return 2


if __name__ == "__main__":
    # ⛔ Same trap install.py documents, and it bites here for the same reason: a Windows
    # console is cp950 on this machine, so one ⚠ in a message kills the script AFTER it has
    # already written the snapshot - a traceback in place of the instruction.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main(sys.argv[1:]))
