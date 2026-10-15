#!/usr/bin/env python3
"""`Tools/clean-dispatch-guard.ps1`, run for real against a fixture install.

⛔ WHY. The cleaner had no check at all, and on macOS it missed three things (measured 2026-10-15,
MAC / WIN finding 2): the `*\\.claude` / `*\\.vscode` project patterns never match a `/` path; the
hook's fallback log was looked for in $env:TEMP only, which is unset on macOS; and the 0.75 launchd
resume jobs were not looked for at all. (Its backslash-joined paths were NOT a problem: pwsh's
Join-Path turns `\\` into `/` on macOS - measured, after a mutant that put them back survived.)

Three runs against one fixture under DG_CLEAN_HOME / DG_CLEAN_VSCODE (/ DG_CLEAN_TMP):
  0. DG_CLEAN_TMP UNSET, a log planted in the real temp folder only if none is there, answer `no`:
     the plan must name it - the default temp lookup, which run 1-2's test hook bypasses;
  1. answer the project question with a fixture project and the confirm question with `no`: exit 3,
     the PLAN must name every planted item (project `.claude`/`.vscode` files included), nothing may change;
  2. (not on Windows) answer `confirm`: everything planned is gone, and on macOS a FAKE `launchctl`
     put first on PATH must have been asked to boot out the spent job and NOT the running one.
⚠ Step 2 is skipped on Windows: there the cleaner queries and deletes the REAL Task Scheduler, and a
test must never delete a real armed resume.

    python Tools/Debug/test_clean.py     (or Tools/Debug/test_all.py for all of them)

Needs PowerShell 7 (`pwsh`), like the script itself; a missing pwsh is a FAILURE, never a skip.
"""

import json
import os
import shutil
import stat
import subprocess
import tempfile
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import fresh_scratch, repo_path, scratch_dir   # noqa: E402

CLEANER = repo_path("Tools", "clean-dispatch-guard.ps1")
SPENT = "com.dispatch-guard.resume.abcd1234.s1.1792000000.0a0b0c0d"
RUNNING = "com.dispatch-guard.resume.abcd1234.s2.1792000600.0e0f1011"


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def plant(root):
    """A fixture install. Returns (home, vscode, tmp, fakebin, bootout_log)."""
    home = os.path.join(root, "home", ".claude")
    vscode = os.path.join(root, "vscode", "User")
    tmp = os.path.join(root, "tmp")
    fakebin = os.path.join(root, "bin")
    _write(os.path.join(home, "plugins", "cache", "dispatch-guard", "dispatch-guard", "0.75.1", "x"), "x")
    _write(os.path.join(home, "plugins", "marketplaces", "dispatch-guard", "x"), "x")
    _write(os.path.join(home, "dispatch-guard", "resume", "launchd", SPENT + ".plist"), "x")
    _write(os.path.join(home, "settings.json"), json.dumps({
        "statusLine": {"type": "command", "command": 'bash "~/.claude/dispatch-guard/run.sh" usage.py'},
        "enabledPlugins": {"dispatch-guard@dispatch-guard": True, "other@x": True}}))
    _write(os.path.join(home, "plugins", "installed_plugins.json"),
           json.dumps({"plugins": {"dispatch-guard@dispatch-guard": [{}], "other@x": [{}]}}))
    _write(os.path.join(vscode, "tasks.json"),
           json.dumps({"version": "2.0.0", "tasks": [{"label": "Claude Usage Watcher"}]}))
    _write(os.path.join(tmp, "dispatch_gate_error.log"), "x")
    proj = os.path.join(root, "proj")
    _write(os.path.join(proj, ".claude", "dispatch-guard.json"), "{}")
    _write(os.path.join(proj, ".vscode", "tasks.json"),
           json.dumps({"version": "2.0.0", "tasks": [{"label": "Claude Usage Watcher"}, {"label": "mine"}]}))
    log = os.path.join(root, "bootout.log")
    # (no %-formatting: the shell's own printf would collide with it)
    _write(os.path.join(fakebin, "launchctl"),
           "#!/bin/sh\n"
           'if [ "$1" = list ]; then\n'
           '  printf "PID\\tStatus\\tLabel\\n-\\t0\\t' + SPENT + '\\n4242\\t0\\t' + RUNNING
           + '\\n-\\t0\\tcom.apple.other\\n"\n'
           "  exit 0\nfi\n"
           'echo "$*" >> "' + log + '"\nexit 0\n')
    os.chmod(os.path.join(fakebin, "launchctl"), stat.S_IRWXU)
    return home, vscode, tmp, fakebin, log


def run(pwsh, home, vscode, tmp, fakebin, answers):
    env = dict(os.environ, DG_CLEAN_HOME=home, DG_CLEAN_VSCODE=vscode,
               PATH=fakebin + os.pathsep + os.environ.get("PATH", ""))
    env.pop("DG_CLEAN_TMP", None)
    if tmp:
        env["DG_CLEAN_TMP"] = tmp
    r = subprocess.run([pwsh, "-NoProfile", "-File", CLEANER], input=answers, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    return r.returncode, r.stdout + r.stderr


def main():
    fresh_scratch()
    pwsh = shutil.which("pwsh")
    if not pwsh:
        print("FAIL  pwsh (PowerShell 7) not found - clean-dispatch-guard.ps1 cannot be exercised.")
        return 1
    with scratch_dir("cleaner") as root:
        home, vscode, tmp, fakebin, log = plant(root)
        proj = os.path.join(root, "proj")
        # 0. the DEFAULT temp folder (no DG_CLEAN_TMP), plan only. ⚠ A log is planted there only if
        #    none exists, and removed again only if planted here - the real one is never touched.
        real_log = os.path.join(tempfile.gettempdir(), "dispatch_gate_error.log")
        planted = not os.path.exists(real_log)
        if planted:
            _write(real_log, "planted by test_clean.py")
        try:
            rc, out = run(pwsh, home, vscode, None, fakebin, "\nno\n")
        finally:
            if planted:
                os.remove(real_log)
        assert rc == 3 and real_log.replace("\\", "/") in out.replace("\\", "/"), (
            "the hook's fallback log in the real temp folder is not in the plan (rc %s):\n%s" % (rc, out))
        # 1. the plan, with project files, then "no"
        rc, out = run(pwsh, home, vscode, tmp, fakebin, proj + "\nno\n")
        assert rc == 3, "answering no did not stop (rc %s):\n%s" % (rc, out)
        cache = os.path.join(home, "plugins", "cache", "dispatch-guard")
        for must in ("plugins/cache/dispatch-guard", "plugins/marketplaces/dispatch-guard",
                     "dispatch_gate_error.log", "statusLine", "tasks.json", "installed_plugins.json",
                     "proj/.claude/dispatch-guard.json", "proj/.vscode/tasks.json"):
            assert must in out.replace("\\", "/"), "the plan does not name %s:\n%s" % (must, out)
        assert "nothing was changed" in out and os.path.isdir(cache), out
        if sys.platform == "darwin":
            assert "launchd job " + SPENT in out, "the spent launchd job is not in the plan:\n%s" % out
            assert "RUNNING now" in out and RUNNING in out, "the running job is not reported as KEEP:\n%s" % out
        if os.name == "nt":
            print("ok - the cleaner plans every planted item (confirm run skipped on Windows: real Task Scheduler)")
            return 0
        # 2. confirm
        rc, out = run(pwsh, home, vscode, tmp, fakebin, proj + "\nconfirm\n")
        assert rc == 0, "the confirmed clean failed (rc %s):\n%s" % (rc, out)
        for gone in (cache, os.path.join(home, "plugins", "marketplaces", "dispatch-guard"),
                     os.path.join(home, "dispatch-guard"), os.path.join(tmp, "dispatch_gate_error.log"),
                     os.path.join(vscode, "tasks.json"), os.path.join(proj, ".claude", "dispatch-guard.json")):
            assert not os.path.exists(gone), "still there after confirm: %s\n%s" % (gone, out)
        kept = json.load(open(os.path.join(proj, ".vscode", "tasks.json"), encoding="utf-8"))["tasks"]
        assert kept == [{"label": "mine"}], "the project tasks.json lost the wrong task: %r" % (kept,)
        settings = json.load(open(os.path.join(home, "settings.json"), encoding="utf-8"))
        assert "statusLine" not in settings and settings["enabledPlugins"] == {"other@x": True}, settings
        if sys.platform == "darwin":
            booted = open(log, encoding="utf-8").read() if os.path.exists(log) else ""
            assert SPENT in booted, "the spent launchd job was not booted out:\n%s" % out
            assert RUNNING not in booted, "a RUNNING launchd job was booted out - that kills it:\n%s" % booted
    print("ok - the cleaner finds and removes a fixture install on this platform%s"
          % (", and boots out only the spent launchd job" if sys.platform == "darwin" else ""))
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
