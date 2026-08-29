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


def case_no_version_in_wired_paths():
    """⛔ NOTHING THIS PLUGIN WRITES OUTSIDE ITSELF MAY NAME THE PLUGIN DIRECTORY.

    A marketplace install lives under `.../cache/dispatch-guard/dispatch-guard/<VERSION>/`.
    Hooks are immune - hooks.json uses ${CLAUDE_PLUGIN_ROOT}, re-expanded every session - but
    `statusLine.command` in settings.json and the `Claude Usage Watcher` task in tasks.json hold
    LITERAL paths, and so does every command the gate hands to the model. ⇒ The next
    `claude plugin update` moves the directory and each of them points at a version that is
    gone; worse, measured 2026-08-26, the old directory is LEFT BEHIND, so a stale path keeps
    working and keeps running old code while everything reports healthy.

    ⛔ AND IT ASSERTS THE POSITIVE PROPERTY, NOT THE ABSENCE OF A VERSION NUMBER. The first
    version of this check searched the wired paths for `/<n>.<n>.<n>/` - and PASSED with the
    bug put back, because in a development checkout the plugin lives at
    `C:/WorkSpace/dispatch-guard`, which has no version in it either. The check was blind in
    exactly the environment it runs in. ⇒ What is actually required is that every wired path
    goes through the SHIM, which is true, checkable and mutation-killed everywhere.
    """
    import importlib
    import time
    import sys
    sys.path.insert(0, HERE)
    sys.path.insert(0, os.path.join(HERE, "hooks"))
    inst = importlib.import_module("install")
    gate = importlib.import_module("dispatch_gate")
    resume = importlib.import_module("resume")

    # ⛔ AND THIS CHECK MUST NOT TOUCH THE REAL HOME DIRECTORY. It calls install.py's builders
    # to ask what they would produce, and for a while two of them WROTE the shim as a side
    # effect - which repointed the live statusline at a development checkout in the middle of
    # a test run. Same class as the cleaner that once uninstalled a working plugin, and the
    # only reason it was found is that somebody read the file afterwards. So it is recorded
    # before and asserted after.
    import shim as _shim
    real_state = os.path.join(os.path.expanduser("~"), ".claude", "dispatch-guard")
    before_shim = _shim.recorded(real_state)

    def norm(v):
        return str(v).replace(chr(92), "/")

    plugin_hooks = norm(os.path.join(HERE, "hooks"))
    shims = (norm(inst.SHIM_SH), norm(inst.SHIM_CMD))

    wired = {"statusLine.command": inst.COMMAND}
    cmd, args = inst._watch_command(os.getcwd())
    wired["the VS Code task command"] = cmd
    for i, a in enumerate(args):
        wired["the VS Code task arg %d" % i] = a
    # ⛔ THE USER-LEVEL TASK IS A SEPARATE BUILDER and it was missed the first time. It is
    # written ONCE and then read in every project on the machine, for as long as the editor
    # is installed - the worst place on this list for a path that goes stale.
    entry = inst.user_task_entry()
    wired["the user-level task command"] = entry.get("command")
    for i, a in enumerate(entry.get("args") or []):
        wired["the user-level task arg %d" % i] = a
    # ⛔ AND THE SCHEDULED RESUME, which is the worst case of all: registered with the OS NOW
    # and fired HOURS later, across the window in which somebody runs `plugin update`, with
    # nobody watching when it goes off. --dry-run returns the command without registering it.
    sched, _ = resume.schedule(time.localtime(time.time() + 3600), True)
    for i, part in enumerate(sched):
        wired["the scheduled resume argv[%d]" % i] = part
    for name in ("usage.py", "resume.py", "model_pricing.py"):
        wired["the gate's `%s` command" % name] = gate.runnable(name)

    named_shim = 0
    for what, value in wired.items():
        v = norm(value)
        assert plugin_hooks not in v, (
            "%s names the plugin directory, so it goes stale at the next update:%s  %s%s"
            "  it must go through %s" % (what, chr(10), value, chr(10), shims[0]))
        assert "plugins/cache" not in v, "%s points into the plugin cache: %s" % (what, value)
        if any(sh in v for sh in shims):
            named_shim += 1
    # ⚠ Some entries are bare arguments (`usage.py`, `--watch`), so not every one names the
    # shim - but if NONE do, the loop above is passing on strings that mention no path at all.
    assert named_shim >= 3, (
        "only %d wired value(s) name the shim - this check may be passing on nothing: %r"
        % (named_shim, wired))
    after_shim = _shim.recorded(real_state)
    assert after_shim == before_shim, (
        "asking install.py what it WOULD write changed the real state directory:%s"
        "  was: %s%s  now: %s" % (chr(10), before_shim, chr(10), after_shim))
    print("ok - every wired path goes through the shim, none names the plugin (%d checked, "
          "real home untouched)" % len(wired))


def main():
    fresh_scratch()
    case_no_version_in_wired_paths()
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
            f.write('{"version": "2.0.0", "tasks": [{"label": "Claude Usage Watcher"}]}')
        r = subprocess.run([sys.executable, os.path.join(HERE, "install.py"),
                            "--vscode-task", "--remove", "--check"],
                           cwd=tmp, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        assert r.returncode == 0, "--remove --check exited %d:\n%s" % (r.returncode, r.stderr)
        with open(tasks, encoding="utf-8") as f:
            assert "Claude Usage Watcher" in f.read(), "--check REMOVED the task for real"

        # ⭐ And without --check it has to actually go. Same file, so this also proves the
        # --check run above left something behind to remove.
        r = subprocess.run([sys.executable, os.path.join(HERE, "install.py"),
                            "--vscode-task", "--remove"],
                           cwd=tmp, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        assert r.returncode == 0, "--remove exited %d:\n%s" % (r.returncode, r.stderr)
        with open(tasks, encoding="utf-8") as f:
            assert "Claude Usage Watcher" not in f.read(), "--remove did not remove the task"

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
    with scratch_dir("install-writes-no-config") as tmp:
        inst3 = load_install_module(tmp)
        # ⛔ NOTHING IS CREATED, and that is the third design this has had. Copying the
        # example whole PINNED every value - a machine set up before a default moved kept
        # the old one silently, and it cost two reinstalls to find. Seeding only the
        # explanations fixed the pinning and left a 55 KB file that documented every setting
        # and showed not one of them. Writing nothing has neither problem: no file means no
        # pin, and a key that exists was typed on purpose.
        assert inst3.seed_config() is None, "seed_config created something"
        assert not os.path.exists(inst3.CONFIG_PATH), "config.json was written anyway"

        # ⛔ An existing file is still the user's. Nothing here may touch it.
        os.makedirs(os.path.dirname(inst3.CONFIG_PATH), exist_ok=True)
        with open(inst3.CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write('{"mine": true}')
        assert inst3.seed_config() is None
        with open(inst3.CONFIG_PATH, encoding="utf-8") as f:
            assert json.load(f) == {"mine": True}, "it overwrote the user's config"

        sys.path.insert(0, os.path.join(HERE, "hooks"))
        import dispatch_gate as _gate                                    # noqa: E402
        import usage as _usage                                           # noqa: E402
        with open(os.path.join(HERE, "config.example.json"), encoding="utf-8") as f:
            example = json.load(f)
        # ⛔ The example must not disagree with the code: --status compares a person's config
        # against the EXAMPLE, so a stale example would report drift that is not there and
        # miss drift that is.
        for k, v in _usage.DEFAULTS.items():
            if k in example:
                assert example[k] == v, "example %s=%r but code default is %r" % (
                    k, example[k], v)
        for k, v in _gate.DEFAULTS.items():
            block = example.get("dispatch") or {}
            if k in block:
                assert block[k] == v, "example dispatch.%s=%r but code says %r" % (
                    k, block[k], v)
        # ⛔ NO RETIRED KEY MAY APPEAR IN THE EXAMPLE. Nothing reads them, so anyone copying
        # the example by hand would pin a key that does nothing and then wonder why the
        # setting they wrote has no effect.
        for dead in ("keep_history", "token_usage_history", "limits_file", "model_ceiling",
                     "require_skills"):
            assert dead not in example, "the example still offers the retired key %r" % dead
            assert dead not in (example.get("dispatch") or {}), \
                "the example still offers the retired key dispatch.%r" % dead
        assert (example.get("debug") or {}).get("token_usage") is True, example.get("debug")

        # ⛔ THE DRIFT CHECK, RUN THROUGH `install.py --status` ITSELF, because it is what
        # makes a hand-written config survivable and it fails SILENTLY: a comparison that
        # stops comparing simply reports "all match" for ever.
        # ⚠ A FIRST VERSION CALLED _settable() AND COMPARED THE DICTS HERE - a
        # re-implementation, not the shipped code. Measured: breaking the real comparison
        # left the whole suite green.
        stale = {"soft_pct_5h": _usage.DEFAULTS["soft_pct_5h"] + 7,
                 "debug": {"token_usage": False}}
        with open(inst3.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(stale, f)
        out = _status_text(tmp)
        assert "NO LONGER MATCH THE DEFAULT" in out, out[:1500]
        assert "soft_pct_5h = %d" % stale["soft_pct_5h"] in out, out[:1500]
        assert "debug.token_usage = false" in out, out[:1500]

        # ⛔ AND EVERY RETIRED KEY, which the comparison above CANNOT see: they are gone from
        # the example, so a config carrying one matches nothing and would be reported as "all
        # still equal to the current default". ⚠ THAT MATTERS MORE NOW THAN IT USED TO. These
        # keys are no longer read at ALL - no compatibility path - so the setting its owner
        # wrote does nothing, silently, and this line is the only thing that ever says so.
        for dead in ("keep_history", "token_usage_history", "limits_file"):
            with open(inst3.CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({dead: False}, f)
            out = _status_text(tmp)
            assert "%s = false" % dead in out, (dead, out[:1500])
            assert "IGNORED" in out, (dead, out[:1500])
        # ⛔ MUTATION CHECK: the assertion must fail on a config that carries no retired key.
        with open(inst3.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"soft_pct_5h": _usage.DEFAULTS["soft_pct_5h"]}, f)
        assert "IGNORED" not in _status_text(tmp), "every config reports IGNORED"

        # ⚠ ...and a config that matches the defaults must report NOTHING, or it is noise.
        with open(inst3.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"soft_pct_5h": _usage.DEFAULTS["soft_pct_5h"]}, f)
        out = _status_text(tmp)
        assert "NO LONGER MATCH" not in out, out[:1500]
        assert "all still equal to the current default" in out, out[:1500]

        # ⛔ EVERY DEBUG SWITCH MUST BE NAMED, WITH ITS EFFECTIVE VALUE, ON EVERY RUN.
        # Two separate defects live here, and the second hid for weeks behind the first.
        #
        #   1. The values must come from usage.config(), never off the raw JSON. An untouched
        #      config carries no switch at all - both sit at their defaults, and one of those
        #      defaults is ON - so reading the file calls it off and sends somebody hunting
        #      for a file that is being written. Caught by a refuting pass.
        #   2. ⛔ THE LINE ONLY PRINTED WHEN THE LOG FOLDER DID NOT EXIST, which is to say on
        #      a machine that had never fetched. Everywhere else the switches were invisible -
        #      and `debug.API_response_usage` was then undiscoverable on any existing install,
        #      because seed_config() never overwrites a config.json and nothing else named the
        #      key. That was an open pending item. ⇒ Both states are asserted below.
        for logs_exist in (False, True):
            logs = os.path.join(inst3.STATE_DIR, "logs")
            if logs_exist:
                os.makedirs(logs, exist_ok=True)
            elif os.path.isdir(logs):
                os.rmdir(logs)
            with open(inst3.CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({}, f)               # empty: every switch at its default
            out = _status_text(tmp)
            where = "with a logs folder" if logs_exist else "without one"
            assert "debug switches" in out, "%s: the switches are not named%s%s" % (
                where, chr(10), out[:2000])
            assert "token_usage = ON" in out, "%s: %s" % (where, out[:2000])
            assert "API_response_usage = off" in out, "%s: %s" % (where, out[:2000])
            # ...and switching one off must READ as off, or the line is just a constant.
            with open(inst3.CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({"debug": {"token_usage": False}}, f)
            out = _status_text(tmp)
            assert "token_usage = ON" not in out, "%s: %s" % (where, out[:2000])
            assert "token_usage = off" in out, "%s: %s" % (where, out[:2000])

    print("ok - --check neither wrote nor removed anything, and said so")


def _status_text(tmp):
    """`install.py --status` output, captured, with every path pointed at `tmp`.

    ⛔ THE SHIPPED FUNCTION IS CALLED, not a copy of what it is believed to do. A check that
    re-implements the comparison it is checking passes while the real one is broken -
    measured on this very block, where breaking install.py's drift comparison left the whole
    suite green.
    ⚠ status() makes no network request: the verdict it shells out for reads token_usage.json and
    never fetches.
    """
    import contextlib
    import io as _io
    mod = load_install_module(tmp)
    buf = _io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            mod.status()
    except SystemExit:
        pass
    return buf.getvalue()


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
        # ⛔ AND THE SHIM, which is a fifth name and was the next hole in exactly the way this
        # docstring predicted. SHIM_SH, SHIM_CMD and COMMAND are all computed AT IMPORT from
        # the real STATE_DIR, so patching STATE_DIR alone leaves write_shim() aimed at the
        # machine's live launcher - measured, and it repointed a working statusline at a
        # development checkout mid-run.
        mod.SHIM_SH = os.path.join(mod.STATE_DIR, "run.sh").replace(chr(92), "/")
        mod.SHIM_CMD = os.path.join(mod.STATE_DIR, "run.cmd").replace(chr(92), "/")
        mod.COMMAND = 'bash "%s" usage.py --statusline' % mod.SHIM_SH
    return mod


def repoint():
    """A statusline that is ours but wired elsewhere must be re-pointed, not skipped.

    ⚠ In-process, with SETTINGS pointed at a temp file. A subprocess would read the real
    ~/.claude/settings.json, and a test that edits the machine it runs on is not a test.
    """
    with scratch_dir("stale-statusline-repointed") as tmp:
        # ⛔ WITH `tmp`, NOT WITHOUT IT. This used to load the module unpatched and then set
        # SETTINGS by hand - which left STATE_DIR pointing at the real ~/.claude, so
        # repoint_statusline() wrote the shim into the machine's live state directory.
        inst = load_install_module(tmp)
        # ⚠ install.py calls this from __main__, which importing skips - and then its own ⚠
        # characters raise UnicodeEncodeError on a cp950 console. Reuse its helper rather than
        # reinventing the fix, so the test prints exactly what a real run prints.
        inst._utf8_console()
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
    # ⛔ THE NET ROUND EVERYTHING BELOW. Several places in this file have now been found
    # writing into the real ~/.claude while "testing", each one patched individually after
    # somebody noticed. This asserts the property directly instead: whatever these checks
    # do, the machine's live launcher must read the same before and after.
    sys.path.insert(0, os.path.join(HERE, "hooks"))
    import shim as _shim
    _real_state = os.path.join(os.path.expanduser("~"), ".claude", "dispatch-guard")
    _shim_was = _shim.recorded(_real_state)
    main()
    repoint()
    selfheal()
    assert _shim.recorded(_real_state) == _shim_was, (
        "these checks changed the machine's live shim:%s  was: %s%s  now: %s"
        % (chr(10), _shim_was, chr(10), _shim.recorded(_real_state)))
    print("ok - nothing here touched the real state directory")
