#!/usr/bin/env python3
"""Promises of install.py that failed silently once, so each gets a check.

⛔ WHY THESE AND NOT A SUITE. Every one is the same shape of bug: the script SAID the right
thing and did the wrong thing, and no amount of running it normally would show that.
  1. `--check` was honoured by the statusline half only, so `--all --check` printed "not
     written" and then wrote `.vscode/tasks.json` anyway. A dry run that is not dry is
     worse than no dry run - it is what somebody runs BEFORE deciding to trust this.
  2. Re-running the installer did not re-point a statusline that was already ours but
     wired to an older version's path. --status called it a STALE COPY while --all said
     "nothing to do", in the same minute.
  3. A file that EXISTS but does not parse - a commented tasks.json, a settings.json with a
     trailing comma - read back as empty and was written over, losing what was in it.
  4. Ownership was a loose substring, so a statusline merely mentioning this plugin's folder
     was claimed and replaced.

    python Tools/Debug/test_install.py      (or Tools/Debug/test_all.py for all of them)

Standard library only, no framework, like everything else here.
"""

import importlib.util
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import fresh_scratch, repo_path, scratch_dir   # noqa: E402

HERE = repo_path()            # ⭐ the repository under test, not this folder


def main():
    fresh_scratch()
    with scratch_dir("all-check-writes-nothing") as tmp:
        r = subprocess.run([sys.executable, os.path.join(HERE, "install.py"), "--all", "--check"],
                           cwd=tmp, capture_output=True, text=True,
                           # ⛔ encoding= is not optional. text=True alone decodes with the
                           # console codepage - cp950 on the machine this was written on -
                           # and install.py's ⭐ characters then raise UnicodeDecodeError
                           # INSIDE subprocess, leaving r.stdout as None. Same trap the
                           # script itself documents; it bites the test too.
                           encoding="utf-8", errors="replace",
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        # ⚠ cwd is what --all uses to place .vscode/tasks.json, so a temp cwd is the whole
        # isolation. Nothing else it touches is written under --check.
        left = os.listdir(tmp)
        assert r.returncode == 0, "install.py --all --check exited %d:\n%s" % (r.returncode, r.stderr)
        assert left == [], "--check WROTE something into the project: %r" % (left,)
        assert "NOTHING was changed" in r.stdout, "--check no longer says it changed nothing:\n%s" % r.stdout

    # ⛔ And --check has to gate the DELETE, not only the write. The remove branch returns
    # early, so it is a second door out of the same function and needs its own guard.
    with scratch_dir("remove-check-then-remove") as tmp:
        os.mkdir(os.path.join(tmp, ".vscode"))
        tasks = os.path.join(tmp, ".vscode", "tasks.json")
        with open(tasks, "w", encoding="utf-8") as f:
            f.write('{"version": "2.0.0", "tasks": [{"label": "Claude usage watch"}]}')
        r = subprocess.run([sys.executable, os.path.join(HERE, "install.py"),
                            "--vscode-task", "--remove", "--check"],
                           cwd=tmp, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        assert r.returncode == 0, "--remove --check exited %d:\n%s" % (r.returncode, r.stderr)
        with open(tasks, encoding="utf-8") as f:
            assert "Claude usage watch" in f.read(), "--check REMOVED the task for real"

        # ⭐ And without --check it has to actually go. Same file, so this also proves the
        # --check run above left something behind to remove.
        r = subprocess.run([sys.executable, os.path.join(HERE, "install.py"),
                            "--vscode-task", "--remove"],
                           cwd=tmp, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        assert r.returncode == 0, "--remove exited %d:\n%s" % (r.returncode, r.stderr)
        with open(tasks, encoding="utf-8") as f:
            assert "Claude usage watch" not in f.read(), "--remove did not remove the task"

    # ⛔ The uninstall path is a third door out, and it deletes from the USER's settings.
    # `--uninstall --check` used to remove the statusline entry for real, so this one is
    # checked in-process against a temp settings file rather than the real one.
    with scratch_dir("uninstall-check-then-uninstall") as tmp:
        inst = load_install_module(tmp)
        inst._utf8_console()
        with open(inst.SETTINGS, "w", encoding="utf-8") as f:
            json.dump({"statusLine": {"type": "command", "command": inst.COMMAND}}, f)
        inst.statusline_install(["--uninstall", "--check"])
        with open(inst.SETTINGS, encoding="utf-8") as f:
            assert "statusLine" in json.load(f), "--uninstall --check REMOVED it for real"
        # ⚠ Point HERE at the temp dir so the resume.py the uninstall path shells out to is
        # not there. Otherwise this test would cancel a REAL armed resume on the machine it
        # runs on. install.py catches that failure and prints a line about it, which is the
        # expected noise below.
        inst.HERE = tmp
        inst.statusline_install(["--uninstall"])
        with open(inst.SETTINGS, encoding="utf-8") as f:
            assert "statusLine" not in json.load(f), "--uninstall did not remove it"

    # ⛔ An UNINSTALL must not CREATE anything. Removing the task from a project that never
    # had a tasks.json used to write a new empty one, so clearing a machine down left a
    # .vscode directory in every repository it touched.
    with scratch_dir("remove-creates-nothing") as tmp:
        r = subprocess.run([sys.executable, os.path.join(HERE, "install.py"),
                            "--vscode-task", "--remove"],
                           cwd=tmp, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        assert r.returncode == 0, r.stderr
        assert os.listdir(tmp) == [], "removing created %r" % (os.listdir(tmp),)
        assert "nothing to remove" in r.stdout, r.stdout

    # ⛔ THE MOST DESTRUCTIVE THING THIS SCRIPT COULD DO. VS Code accepts comments in
    # tasks.json; json.load does not. The old reader mapped that to "empty" and wrote over
    # the person's own tasks with no backup and nothing said.
    with scratch_dir("jsonc-tasks-not-overwritten") as tmp:
        os.mkdir(os.path.join(tmp, ".vscode"))
        tasks = os.path.join(tmp, ".vscode", "tasks.json")
        jsonc = '{\n  // my own tasks\n  "version": "2.0.0",\n  "tasks": [{"label": "build"}]\n}'
        with open(tasks, "w", encoding="utf-8") as f:
            f.write(jsonc)
        r = subprocess.run([sys.executable, os.path.join(HERE, "install.py"), "--vscode-task"],
                           cwd=tmp, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        with open(tasks, encoding="utf-8") as f:
            assert f.read() == jsonc, "an unparseable tasks.json was overwritten"
        assert "does not parse" in r.stdout, r.stdout

    # ⛔ And the same for the settings file, on the path a HUMAN runs. Guarding only the
    # hook's writers left `install.py` with no arguments still able to replace the lot.
    with scratch_dir("unreadable-settings-refused") as tmp:
        inst2 = load_install_module(tmp)
        inst2._utf8_console()
        broken = '{"statusLine": {"command": "mine"},}'      # trailing comma: VS Code no, us no
        with open(inst2.SETTINGS, "w", encoding="utf-8") as f:
            f.write(broken)
        assert inst2.statusline_install([]) == 1, "an unparseable settings.json was accepted"
        with open(inst2.SETTINGS, encoding="utf-8") as f:
            assert f.read() == broken, "an unparseable settings.json was overwritten"

    # ⛔ The seeded config must not change a single effective default. It ships the example
    # verbatim, and the example once pinned dispatch.task_root to a path while the code
    # default was null - "choose the one this repository already uses". Writing that out
    # would have moved every repository that keeps task folders somewhere else.
    with scratch_dir("seeded-config-pins-nothing") as tmp:
        inst3 = load_install_module(tmp)
        assert inst3.seed_config() == inst3.CONFIG_PATH, "config.json was not created"
        with open(inst3.CONFIG_PATH, encoding="utf-8") as f:
            seeded = json.load(f)
        # ⛔ NOT ONE REAL KEY. A value written here PINS it: the first version copied the
        # example verbatim, and when auto_vscode_task later changed default, every machine
        # seeded before that day kept the old value and the update appeared to do nothing.
        assert any(k.startswith("_") for k in seeded), "seeded without its explanations"
        sys.path.insert(0, os.path.join(HERE, "hooks"))
        import dispatch_gate as _gate                                    # noqa: E402
        import usage as _usage                                           # noqa: E402
        for k in _usage.DEFAULTS:
            assert k not in seeded, "seeded PINS %s" % k
        for k in _gate.DEFAULTS:
            assert k not in (seeded.get("dispatch") or {}), "seeded PINS dispatch.%s" % k
        # ⚠ ...while every explanation survives, or the file is not worth opening.
        assert sum(1 for k in seeded if k.startswith("_")) > 20, "explanations were lost"
        assert any(k.startswith("_") for k in (seeded.get("dispatch") or {})), "block emptied"
        # ⛔ And it never overwrites: the file is the user's the moment it exists.
        with open(inst3.CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write('{"mine": true}')
        assert inst3.seed_config() is None, "seed_config offered to overwrite"
        with open(inst3.CONFIG_PATH, encoding="utf-8") as f:
            assert json.load(f) == {"mine": True}, "it overwrote the user's config"

    print("ok - --check neither wrote nor removed anything, and said so")


def load_install_module(tmp=None):
    """Load install.py, optionally with EVERY path it writes through pointed at `tmp`.

    ⛔ PATCHING SETTINGS ALONE WAS NOT ENOUGH, and the gap was not theoretical: the
    uninstall test patched SETTINGS and HERE but not STATE_DIR, so `--uninstall` wrote
    `auto_statusline: false` into the REAL ~/.claude/dispatch-guard/config.json, and
    seed_config() - finding no config.example.json beside the patched HERE - replaced it
    with a stub. A test that edits the machine it runs on is not a test, and every future
    block must get this for free rather than having to remember four names.
    """
    spec = importlib.util.spec_from_file_location("dg_install", os.path.join(HERE, "install.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if tmp is not None:
        mod.SETTINGS = os.path.join(tmp, "settings.json")
        mod.STATE_DIR = os.path.join(tmp, "state")
        mod.CONFIG_PATH = os.path.join(tmp, "state", "config.json")
    return mod


def repoint():
    """A statusline that is ours but wired elsewhere must be re-pointed, not skipped.

    ⚠ In-process, with SETTINGS pointed at a temp file. A subprocess would read the real
    ~/.claude/settings.json, and a test that edits the machine it runs on is not a test.
    """
    inst = load_install_module()
    # ⚠ install.py calls this from __main__, which importing skips - and then its own ⚠
    # characters raise UnicodeEncodeError on a cp950 console. Reuse its helper rather than
    # reinventing the fix, so the test prints exactly what a real run prints.
    inst._utf8_console()
    with scratch_dir("stale-statusline-repointed") as tmp:
        inst.SETTINGS = os.path.join(tmp, "settings.json")
        stale = ('bash "/somewhere/dispatch-guard/0.0.1/hooks/run.sh" '
                 '"/somewhere/dispatch-guard/0.0.1/hooks/usage.py" --statusline')
        with open(inst.SETTINGS, "w", encoding="utf-8") as f:
            json.dump({"statusLine": {"type": "command", "command": stale}}, f)

        inst.statusline_install([])
        with open(inst.SETTINGS, encoding="utf-8") as f:
            got = json.load(f)["statusLine"]["command"]
        assert got == inst.COMMAND, "stale statusline not re-pointed:\n  %s" % got

        # ⭐ And --check must NOT re-point. Same file, now correct: put the stale one back.
        with open(inst.SETTINGS, "w", encoding="utf-8") as f:
            json.dump({"statusLine": {"type": "command", "command": stale}}, f)
        inst.statusline_install(["--check"])
        with open(inst.SETTINGS, encoding="utf-8") as f:
            assert json.load(f)["statusLine"]["command"] == stale, "--check re-pointed for real"

    print("ok - a stale statusline is re-pointed, and --check only says it would")


def selfheal():
    """The GATE must repair a stale statusline by itself, and leave a correct one alone.

    ⛔ Checked through the gate rather than through install.py, because the point of the
    feature is that nobody runs install.py. A silent no-op here would restore the exact
    defect it was written to remove: after `claude plugin update` the old directory is still
    there, so the stale command still runs and nothing ever complains.
    """
    sys.path.insert(0, os.path.join(HERE, "hooks"))
    sys.path.insert(0, HERE)
    import dispatch_gate                     # noqa: E402
    import install                           # noqa: E402  the copy the gate itself imports

    with scratch_dir("gate-repairs-statusline") as tmp:
        # ⚠ The REAL module object here, because dispatch_gate imports `install` by name -
        # so every path it writes through has to be redirected, not just SETTINGS. See
        # load_install_module() for what forgetting one of them cost.
        saved = (install.SETTINGS, install.STATE_DIR, install.CONFIG_PATH)
        install.SETTINGS = os.path.join(tmp, "settings.json")
        install.STATE_DIR = os.path.join(tmp, "state")
        install.CONFIG_PATH = os.path.join(tmp, "state", "config.json")
        try:
            stale = ('bash "/gone/dispatch-guard/0.0.1/hooks/run.sh" '
                     '"/gone/dispatch-guard/0.0.1/hooks/usage.py" --statusline')
            with open(install.SETTINGS, "w", encoding="utf-8") as f:
                json.dump({"statusLine": {"type": "command", "command": stale}}, f)
            note, seen = dispatch_gate.maybe_repoint_statusline()
            assert note and "re-pointed" in note, note
            with open(install.SETTINGS, encoding="utf-8") as f:
                assert json.load(f)["statusLine"]["command"] == install.COMMAND
            assert dispatch_gate.maybe_repoint_statusline() == (None, None), "must not repeat"

            # ⛔ Somebody else's statusline is never touched. Taking that slot is a
            # deliberate act and stays behind --take-statusline.
            # ⛔ INCLUDING one that names this plugin's folder. Ownership used to be
            # "dispatch-guard" OR "usage.py --statusline", so somebody's own script living
            # under our directory was declared ours and replaced with no backup. This line
            # is the pin for that: it must still read as FOREIGN.
            theirs = {"type": "command",
                      "command": "python ~/.claude/plugins/dispatch-guard/my-own-prompt.py"}
            assert not install.statusline_is_ours(theirs), "a foreign command was claimed"
            with open(install.SETTINGS, "w", encoding="utf-8") as f:
                json.dump({"statusLine": theirs}, f)
            assert dispatch_gate.maybe_repoint_statusline() == (None, None)
            with open(install.SETTINGS, encoding="utf-8") as f:
                assert json.load(f)["statusLine"] == theirs, "it took a foreign statusline"

            # ⛔ And the same slot must be left alone by the ADOPT path too. Adopting is
            # only ever allowed into an empty slot; silently replacing somebody's statusline
            # would delete work they chose to do.
            assert dispatch_gate.maybe_adopt_statusline({"auto_statusline": True}) == (None, None)
            with open(install.SETTINGS, encoding="utf-8") as f:
                assert json.load(f)["statusLine"] == theirs, "adopt overwrote a foreign one"

            # ⭐ An EMPTY slot is taken, so the CLI shows the line with nothing typed.
            with open(install.SETTINGS, "w", encoding="utf-8") as f:
                json.dump({}, f)
            note, seen = dispatch_gate.maybe_adopt_statusline({"auto_statusline": True})
            # ⛔ AND A LINE FOR THE PERSON. With no usage left there is no model turn to
            # relay anything, and installing on an empty budget is the case that must work.
            assert seen and "statusline" in seen, seen
            assert note and "othing owned the statusline" in note, note
            with open(install.SETTINGS, encoding="utf-8") as f:
                assert json.load(f)["statusLine"]["command"] == install.COMMAND
            assert dispatch_gate.maybe_adopt_statusline({"auto_statusline": True}) == (None, None)

            # ⚠ Off means off, even with the slot empty.
            with open(install.SETTINGS, "w", encoding="utf-8") as f:
                json.dump({}, f)
            assert dispatch_gate.maybe_adopt_statusline({"auto_statusline": False}) == (None, None)
            with open(install.SETTINGS, encoding="utf-8") as f:
                assert "statusLine" not in json.load(f), "adopted while switched off"
        finally:
            install.SETTINGS, install.STATE_DIR, install.CONFIG_PATH = saved

    print("ok - the gate repairs a stale statusline and leaves a foreign one alone")


if __name__ == "__main__":
    main()
    repoint()
    selfheal()
