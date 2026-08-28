#!/usr/bin/env python3
"""The one path with no version number in it.

⛔ THE PROBLEM THIS EXISTS FOR. A marketplace install copies the plugin to

    ~/.claude/plugins/cache/dispatch-guard/dispatch-guard/<VERSION>/

and that path carries the version. Hooks are immune - `hooks.json` uses
`${CLAUDE_PLUGIN_ROOT}`, re-expanded every session - but everything else that names this
plugin holds a LITERAL path: `statusLine.command` in settings.json, the `Claude usage watch`
task in tasks.json, and every command the gate hands to the model. ⇒ The next
`claude plugin update` moves the directory and all of them point at a version that is gone.

⚠ AND "THE PATH STILL EXISTS" IS NOT SAFE EITHER. Measured 2026-08-26: after an update the
OLD directory was LEFT IN PLACE, so a wired path still resolved, still ran, and quietly
executed the PREVIOUS version while everything reported healthy.

⇒ So nothing outside the plugin names a versioned path any more. They all name

    ~/.claude/dispatch-guard/run.sh     (or run.cmd)

which never changes, and which forwards into whichever copy is current.

⭐ TWO THINGS KEEP IT CURRENT, AND THE SECOND IS WHY THIS WORKS AT ALL:

  1. The gate rewrites it at session start whenever the recorded path is not the copy that
     is running. That covers every update, with nothing in anybody's settings touched.
  2. ⛔ THE SHIM ITSELF FALLS BACK. Between an update and the next session start there is a
     window where the recorded path is gone - and a VS Code watcher task opened at that
     moment would sit dead for hours, because nothing starts a Claude session to repair it.
     So the shim looks for the NEWEST installed copy on its own. That window is exactly
     where the silent failure used to live.

⛔ WHY IT IS TWO FILES. `bash` on a Windows PATH is usually NOT Git Bash - measured, it
resolves to the WSL launcher stub, which fails. Claude Code invokes its own bash and is fine;
a VS Code task goes through the user's default shell and is not. Same split as hooks/run.sh
and hooks/run.cmd, and for the same measured reason.
"""

import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(HERE)

SH = "run.sh"
CMD = "run.cmd"
# ⚠ The marker is what tells "a shim this plugin wrote" from "a file somebody put here".
# Nothing is ever overwritten without it.
MARK = "dispatch-guard shim - generated, do not edit"

_SH = """#!/bin/sh
# %(mark)s
# Forwards into the installed plugin, whatever version that is today.
#   %(usage)s
DG="%(plugin)s"
if [ ! -f "$DG/hooks/run.sh" ]; then
  # ⛔ The recorded copy is gone - an update moved it and no session has run since. Take the
  # NEWEST installed one rather than failing: a dead watcher task is silent for hours.
  for c in "$HOME"/.claude/plugins/cache/dispatch-guard/dispatch-guard/*/hooks/run.sh; do
    [ -f "$c" ] || continue
    if [ -z "$best" ] || [ "$c" -nt "$best" ]; then best="$c"; fi
  done
  [ -n "$best" ] && DG=$(dirname "$(dirname "$best")")
fi
if [ ! -f "$DG/hooks/run.sh" ]; then
  echo "dispatch-guard: no installed copy found. Reinstall, or run install.py --all." >&2
  exit 0
fi
script="$1"
shift
exec sh "$DG/hooks/run.sh" "$DG/hooks/$script" "$@"
"""

_CMD = """@echo off
setlocal enabledelayedexpansion
rem %(mark)s
rem Forwards into the installed plugin, whatever version that is today.
rem   %(usage)s
set "DG=%(plugin_win)s"
if not exist "%%DG%%\\hooks\\run.cmd" (
  rem The recorded copy is gone. /o-d is newest first, so the first hit is the current one.
  set "CACHE=%%USERPROFILE%%\\.claude\\plugins\\cache\\dispatch-guard\\dispatch-guard"
  if exist "!CACHE!" (
    for /f "delims=" %%%%D in ('dir /b /ad /o-d "!CACHE!"') do (
      if not defined FOUND if exist "!CACHE!\\%%%%D\\hooks\\run.cmd" set "FOUND=!CACHE!\\%%%%D"
    )
  )
  if defined FOUND set "DG=!FOUND!"
)
if not exist "%%DG%%\\hooks\\run.cmd" (
  echo dispatch-guard: no installed copy found. Reinstall, or run install.py --all. 1>&2
  exit /b 0
)
set "SCRIPT=%%~1"
shift
set "REST="
:collect
if "%%~1"=="" goto go
set "REST=!REST! %%1"
shift
goto collect
:go
call "%%DG%%\\hooks\\run.cmd" "%%DG%%\\hooks\\!SCRIPT!"!REST!
"""

USAGE = 'bash "<state>/run.sh" usage.py --statusline'


def paths(sdir):
    return os.path.join(sdir, SH), os.path.join(sdir, CMD)


def recorded(sdir):
    """The plugin directory the shim currently forwards to, or None.

    ⚠ Read out of the FILE rather than remembered, because the question this answers is
    "does the shim on disk point at the copy that is running?" - and only the file knows.
    """
    try:
        with io.open(paths(sdir)[0], encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    if MARK not in text:
        return None
    for line in text.splitlines():
        if line.startswith('DG="') and line.endswith('"'):
            return line[4:-1]
    return None


def write(sdir, plugin_dir=PLUGIN_DIR):
    """Write both shims, pointed at `plugin_dir`. Returns (previous, now), or None.

    ⛔ RETURNS None WHEN NOTHING CHANGED, so a caller can report a repair without reporting
    a no-op every session. ⚠ And it refuses to overwrite a file that is not ours - the state
    directory is the user's, and a `run.sh` somebody else put there is not this plugin's to
    replace.
    """
    plugin = plugin_dir.replace("\\", "/").rstrip("/")
    before = recorded(sdir)
    sh_path, cmd_path = paths(sdir)
    for path in (sh_path, cmd_path):
        if os.path.exists(path):
            try:
                with io.open(path, encoding="utf-8") as f:
                    if MARK not in f.read():
                        return None      # somebody else's file; never clobbered
            except OSError:
                return None
    if before == plugin:
        return None
    fields = {"mark": MARK, "usage": USAGE, "plugin": plugin,
              "plugin_win": plugin.replace("/", "\\")}
    try:
        os.makedirs(sdir, exist_ok=True)
        # ⭐ Newlines pinned per file. A .cmd with LF endings fails on cmd.exe in ways that
        # read as a syntax error in the user's own script, and a .sh with CRLF fails with
        # "bad interpreter: /bin/sh^M". Both are measured classics, neither is obvious.
        with io.open(sh_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(_SH % fields)
        with io.open(cmd_path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(_CMD % fields)
        try:
            os.chmod(sh_path, 0o755)
        except OSError:
            pass
    except OSError:
        return None
    return before, plugin


def command(sdir, script, *args):
    """The command line a MESSAGE should name, with no version number in it."""
    sh = paths(sdir)[0].replace("\\", "/")
    return 'bash "%s" %s' % (sh, " ".join([script] + list(args)))


def _selftest():
    import shutil
    import subprocess
    import sys
    import tempfile

    tmp = tempfile.mkdtemp(prefix="dg-shim-")
    try:
        assert recorded(tmp) is None, "an empty directory must record nothing"
        got = write(tmp, PLUGIN_DIR)
        assert got == (None, PLUGIN_DIR.replace("\\", "/").rstrip("/")), got
        sh_path, cmd_path = paths(tmp)
        assert os.path.isfile(sh_path) and os.path.isfile(cmd_path)
        assert recorded(tmp) == PLUGIN_DIR.replace("\\", "/").rstrip("/")
        # ⭐ NOTHING CHANGED MEANS None, so a caller can report a repair without announcing a
        # no-op every session.
        assert write(tmp, PLUGIN_DIR) is None, "an unchanged shim must report no change"

        # ⛔ LINE ENDINGS ARE NOT COSMETIC HERE. A .cmd with LF fails on cmd.exe in ways that
        # read as a syntax error in the user's own script; a .sh with CRLF fails with
        # "bad interpreter: /bin/sh^M". Read as BYTES, because text mode hides exactly this.
        sh_bytes = io.open(sh_path, "rb").read()
        cmd_bytes = io.open(cmd_path, "rb").read()
        assert b"\r\n" not in sh_bytes, "run.sh must not carry CRLF"
        assert b"\r\n" in cmd_bytes, "run.cmd must carry CRLF"

        # ⛔ AND IT MUST ACTUALLY FORWARD. Everything above checks a file was written; this
        # is the only line that checks the file WORKS. Measured against the real plugin.
        out = subprocess.run(["bash", sh_path, "usage.py", "--verdict", "--dir", tmp],
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, timeout=90)
        text = (out.stdout or b"").decode("utf-8", "replace")
        assert "NO-DATA" in text or "GO" in text or "PACE" in text or "STOP" in text, \
            "the shim did not forward: %r / %r" % (text[:200],
                                                   (out.stderr or b"")[:200])

        # ⛔ THE FALLBACK IS THE POINT OF THE WHOLE FILE, so it is executed rather than read.
        # Aim the shim at a directory that does not exist - which is exactly what an update
        # leaves behind - and it must still find an installed copy and run.
        write(tmp, os.path.join(tmp, "gone-0.0.0"))
        cache = os.path.join(os.path.expanduser("~"), ".claude", "plugins", "cache",
                             "dispatch-guard", "dispatch-guard")
        if os.path.isdir(cache) and os.listdir(cache):
            out2 = subprocess.run(["bash", sh_path, "usage.py", "--verdict", "--dir", tmp],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=90)
            t2 = (out2.stdout or b"").decode("utf-8", "replace")
            assert "NO-DATA" in t2 or "GO" in t2 or "PACE" in t2 or "STOP" in t2, \
                "the fallback did not find an installed copy: %r / %r" % (
                    t2[:200], (out2.stderr or b"")[:200])
            print("  fallback: exercised against %s" % cache)
        else:
            # ⛔ SAID OUT LOUD. A check that skips quietly reports the same "OK" as one that
            # ran, and this is the branch that only matters on somebody else's machine.
            print("  ⚠ fallback NOT exercised - no marketplace install at %s" % cache)

        # ⛔ A FILE THIS PLUGIN DID NOT WRITE IS NEVER CLOBBERED. The state directory is the
        # user's. Mutation-checked: without the marker test, this overwrites their file.
        other = tempfile.mkdtemp(prefix="dg-shim-other-")
        with io.open(os.path.join(other, SH), "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\necho somebody else's launcher\n")
        assert write(other, PLUGIN_DIR) is None, "it overwrote a file it did not write"
        with io.open(os.path.join(other, SH), encoding="utf-8") as f:
            assert "somebody else" in f.read(), "the other file was replaced"
        shutil.rmtree(other, ignore_errors=True)

        assert "run.sh" in command(tmp, "usage.py", "--verdict")
        assert "usage.py --verdict" in command(tmp, "usage.py", "--verdict")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("shim selftest OK")
    return 0


if __name__ == "__main__":
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if "--selftest" in sys.argv[1:]:
        sys.exit(_selftest())
    sys.path.insert(0, HERE)
    import usage
    d = usage.state_dir(sys.argv[1:])
    got = write(d, PLUGIN_DIR)
    print("shim: %s" % paths(d)[0])
    print("cmd : %s" % paths(d)[1])
    print("-> %s" % (recorded(d) or "(not written)"))
    print("changed" if got else "already current")
