#!/usr/bin/env python3
"""Install dispatch-guard's statusline. Idempotent; safe to re-run.

⭐ INSIDE A CLAUDE SESSION, NOBODY SHOULD BE READING THIS. `/dispatch-guard:install` runs
this script for you, and `commands/install.md` spells the path as `${CLAUDE_PLUGIN_ROOT}`,
which Claude Code expands - so no human has to find a marketplace cache directory with a
version number in it, and the command does not go stale after `claude plugin update`.
Everything below is the manual form, for a plain terminal.

    python install.py --all      ⭐ EVERYTHING the plugin cannot do for itself, in one
                                 command: the statusline (for the CLI) and the VS Code
                                 watcher task (for the extension, which renders no
                                 statusline). Hooks and the skill install themselves.
    python install.py            the statusline only
    python install.py --check    report only, change nothing (works with --all too, so
                                 `--all --check` writes neither half)
    python install.py --status       ⭐ is it actually working right now?
    python install.py --enable-auto-task   let the hook wire the VS Code watcher task into
                                     every project by itself (--disable-auto-task undoes it)
    python install.py --take-statusline  ⚠ replace an existing statusline with this
                                     plugin's (the old one is backed up first)
    python install.py --vscode-user-task   ⭐ the watcher task in VS Code's USER tasks file:
                                     written once, applies to EVERY project, no per-project
                                     file (--remove to take it out again)
    python install.py --vscode-task  the old per-PROJECT form, for one repository only
                                     (--remove to take it out again)
    python install.py --all --uninstall  ⭐ remove BOTH halves: the statusline and this
                                 project's `Claude usage watch` task. It then lists what
                                 it did not touch. Add --check to see it change nothing.
    python install.py --uninstall    the statusline only

⛔ WHY AN INSTALLER EXISTS FOR A ONE-LINE EDIT

Everything else in this plugin installs itself: `hooks/hooks.json` is picked up when
the plugin is enabled, and `${CLAUDE_PLUGIN_ROOT}` resolves without anybody editing a
path. **The statusline cannot work that way.** Measured against the 26 plugin manifests
installed on the machine this was written on: not one declares a `statusLine`, and the
key lives in `settings.json`, not in a plugin. So one manual edit is unavoidable.

⭐ IT IS OPTIONAL NOW, AND IT WAS NOT ALWAYS. The statusline used to be the only thing
that re-ran usage.py on a timer, so skipping it left the brake blind. Since 0.4.0 the
dispatch gate forks its own refresh when the numbers go stale, on a hook event it was
running anyway - so the brake works with nothing installed at all. ⇒ What the statusline
adds is a line a PERSON can see, and one more clock for the CLI. Install it if you want
the numbers in front of you; the brake no longer depends on it.

⭐ It does NOT clobber an existing statusline. If one is already configured, this
points the plugin at whatever data that statusline already writes where it can, and
otherwise says plainly what it did not do.
"""

import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "dispatch-guard")
COMMAND = 'bash "%s" "%s" --statusline' % (
    os.path.join(HERE, "hooks", "run.sh").replace("\\", "/"),
    os.path.join(HERE, "hooks", "usage.py").replace("\\", "/"))

def load(path, fallback):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback


def readable(path):
    """True when `path` is absent or parses as JSON. False when it EXISTS and does not.

    ⛔ THE DIFFERENCE load() THROWS AWAY, AND IT IS THE DIFFERENCE BETWEEN CREATING A FILE
    AND DESTROYING ONE. load() maps every failure to its fallback, so a `.vscode/tasks.json`
    carrying comments - JSONC, which VS Code accepts and json.load does not - or a
    settings.json with a trailing comma reads back as "empty", and the next save() writes
    that emptiness over everything the person had. Measured by review, 2026-08-27: a tasks
    file with two of the user's own tasks and a comment was replaced by ours, with no
    backup and nothing said.

    ⚠ Callers must refuse to write when this is False. A missing file is safe to create; an
    unreadable one belongs to somebody and must be left exactly as it is.
    """
    if not os.path.exists(path):
        return True
    try:
        with open(path, encoding="utf-8") as f:
            json.load(f)
        return True
    except Exception:
        return False


def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def statusline_is_ours(current):
    """Is the configured statusLine this plugin's? One definition, three callers."""
    if not isinstance(current, dict):
        return False
    cmd = str(current.get("command", ""))
    # ⛔ BOTH, NOT EITHER. It used to be `"dispatch-guard" in cmd or ...`, so ANY statusline
    # whose command merely mentioned this plugin's folder - somebody's own script living
    # under it, or one that read our limits.json - was declared ours and silently replaced,
    # with no backup. Ownership now needs the two things only our own command has together.
    return "usage.py" in cmd and "--statusline" in cmd


def repoint_statusline():
    """Aim an already-ours statusline at THIS copy. Returns (from, to), or None.

    ⭐ SEPARATED SO THE GATE CAN CALL IT ON EVERY SESSION START. The watcher task learned to
    repair its own stale path; the statusline had not, and that asymmetry was the last thing
    left needing a command after `claude plugin update`. The stale path still EXISTS - update
    leaves the old directory behind - so it runs, renders, and silently executes old code.

    ⛔ It only ever rewrites a slot this plugin ALREADY owns, and only to the copy currently
    running. A statusline belonging to something else is never touched; taking that slot is
    a deliberate act and stays behind --take-statusline.
    """
    if not readable(SETTINGS):
        return None                       # ⛔ see readable(): unreadable belongs to somebody
    settings = load(SETTINGS, {})
    current = settings.get("statusLine")
    if not statusline_is_ours(current):
        return None
    wired = str(current.get("command", ""))
    if wired == COMMAND:
        return None
    settings["statusLine"] = {"type": "command", "command": COMMAND}
    ensure_refresh(settings, [])
    save(SETTINGS, settings)
    return (wired, COMMAND)


def adopt_statusline_if_empty():
    """Install the statusline when NOTHING owns that slot. Returns the command, or None.

    ⭐ WHY THE HOOK MAY DO THIS UNASKED. The slot is empty, so nothing is displaced and
    nothing is lost; the line is this plugin's entire visible purpose; and `--uninstall`
    takes it straight back out. ⛔ An occupied slot is never touched, whoever owns it -
    silently replacing somebody's statusline would delete work they chose to do, which is
    why taking it over stays a named, deliberate act behind --take-statusline.
    """
    if not readable(SETTINGS):
        return None                       # ⛔ never write over a settings file we cannot read
    settings = load(SETTINGS, {})
    if settings.get("statusLine"):
        return None
    settings["statusLine"] = {"type": "command", "command": COMMAND}
    ensure_refresh(settings, [])
    save(SETTINGS, settings)
    return COMMAND


_SEED_NOTE = (
    "Every setting is explained below, and NONE of them is set. That is deliberate: a value "
    "written here PINS it, so a later version's new default would never reach you. Add only "
    "the keys you actually want to fix, and delete a key to go back to following the "
    "plugin's default. Run install.py --status to see which keys you have pinned."
)
_SEED_NOTE_ZH = (
    "下面每一個設定都有說明，而且一個都沒有被設定 —— 這是刻意的。寫在這裡的值會被「釘住」，"
    "以後版本改了預設值也到不了你這裡。只加你真的想固定的那幾個；把一個 key 刪掉就回到跟隨"
    "外掛預設值。想看自己釘住了哪些，跑 install.py --status。"
)


def _docs_only(data):
    """Keep the `_`-prefixed explanations, drop every real setting. Recurses one level.

    ⚠ Nested blocks (`dispatch`, `resume`) get the same treatment. A block emptied of values
    is kept rather than removed, because its explanations are the reason the file is worth
    opening at all.
    """
    out = {"_README": _SEED_NOTE, "_README_zh": _SEED_NOTE_ZH}
    for k, v in data.items():
        if isinstance(v, dict):
            out[k] = _docs_only(v) if not k.startswith("_") else v
        elif k.startswith("_"):
            out[k] = v
    return out


def set_dispatch_config(key, value):
    """Set one `dispatch` key in the state directory's config.json. Returns the path.

    ⚠ It MERGES. The file is the user's, and it holds their thresholds, colours and paths;
    rewriting it wholesale to set one flag would be a data-loss bug wearing a convenience's
    clothes.
    """
    path = os.path.join(STATE_DIR, "config.json")
    if not readable(path):
        raise ValueError("%s does not parse as JSON; refusing to overwrite it" % path)
    data = load(path, {}) or {}
    block = data.get("dispatch")
    data["dispatch"] = block if isinstance(block, dict) else {}
    data["dispatch"][key] = value
    save(path, data)
    return path


CONFIG_PATH = os.path.join(STATE_DIR, "config.json")


def seed_config():
    """Put a documented config.json where the code READS it. Returns the path, or None.

    ⭐ WHY IT IS CREATED RATHER THAN LEFT TO A COPY-PASTE STEP. Every setting was documented
    in `config.example.json`, which sits inside the plugin - a marketplace cache directory
    with a version number in it, that the next update moves. So the file a person was told
    to copy lived somewhere they could not find, and the file they were told to create did
    not exist to be opened. Creating it removes both halves of that.

    ⭐ It is seeded FROM the example, comments and all, because an empty file with the right
    name teaches nobody which keys exist. The `_key` entries beside each value are the whole
    reason it is worth writing.

    ⛔ NEVER OVERWRITES. The file is the user's the moment it exists, and a re-run of the
    installer - which is a routine thing after an update - must not discard their settings.
    ⚠ Nor is it written when it cannot be read: see readable().

    ⛔ IT SEEDS THE DOCUMENTATION, NEVER THE VALUES, and that is the whole of the design.
    A written-out value PINS that setting for ever: the first version of this copied the
    example verbatim, and when `auto_vscode_task` later changed default from false to true,
    every machine seeded before that day kept the false - the update landed, the code default
    moved, and nothing happened. Measured twice on one machine, and it cost two reinstalls to
    find, because "the setting is in my config file" is invisible next to "the plugin has a
    new default".

    ⇒ So every real key is stripped and only the `_`-prefixed explanations remain. The file
    still tells a person what exists and what each thing does; ⭐ adding a key becomes a
    DELIBERATE pin rather than an accident of when they happened to install.
    """
    if os.path.exists(CONFIG_PATH):
        return None
    example = os.path.join(HERE, "config.example.json")
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        if os.path.exists(example):
            with open(example, encoding="utf-8") as f:
                data = json.load(f)               # a broken example must not be copied out
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(_docs_only(data), f, indent=2, ensure_ascii=False)
                f.write("\n")
        else:
            # ⚠ A copied folder may not carry the example. A bare defaults file is still
            # better than nothing: it is at the right path, and it is valid.
            save(CONFIG_PATH, {"_note": "defaults; see config.example.json in the plugin"})
    except Exception:
        return None
    return CONFIG_PATH


def check_python():
    """Report the interpreter hooks/run.sh will actually pick.

    ⛔ It must EXECUTE each candidate, not merely locate it. On Windows `python3`
    resolves to the Microsoft Store alias stub, so `shutil.which("python3")` returns a
    path and looks like success - but running it prints "Python was not found" and
    exits 49. An earlier version of this function used `which` alone and cheerfully
    reported that stub as the interpreter, which is the same confident-wrong-answer
    this plugin exists to prevent elsewhere.
    """
    for c in ("python3", "python", "py"):
        p = shutil.which(c)
        if not p:
            continue
        try:
            r = subprocess.run([c, "-c", "import sys"], capture_output=True, timeout=15)
        except Exception:
            continue
        if r.returncode == 0:
            return c, p
    return None, None


REFRESH_SECONDS = 60


def ensure_refresh(settings, changed):
    """Make the statusline re-run on a timer, whoever's statusline it is.

    ⛔ WITHOUT THIS THE NUMBERS GO STALE AND NOBODY IS TOLD. A statusline renders on
    interactive events, so between turns nothing refreshes. Measured 2026-08-26: the
    file was 27 minutes old and read 52% while the account page read 60% - the reset
    times matched exactly, so it was the same window, merely frozen. ⚠ A frozen
    percentage is the dangerous direction: it reads LOW, so the brake holds off.

    `statusLine.refreshInterval` re-runs the command every N seconds in addition to the
    event-driven updates. ⭐ It is added to whatever statusline is already configured -
    the command is not touched - so this works even when another tool owns that slot.
    """
    sl = settings.get("statusLine")
    if not isinstance(sl, dict) or not sl.get("command"):
        return False
    if sl.get("refreshInterval"):
        return False
    seconds = REFRESH_SECONDS
    disk = load(os.path.join(STATE_DIR, "config.json"), {}) or {}
    if isinstance(disk.get("refresh_seconds"), (int, float)):
        seconds = max(1, int(disk["refresh_seconds"]))
    sl["refreshInterval"] = seconds
    changed.append("added statusLine.refreshInterval = %ds (it was unset, so the numbers "
                   "only moved on interactive turns). Change it with refresh_seconds in "
                   "%s" % (seconds, os.path.join(STATE_DIR, "config.json")))
    return True


def wired_paths_health(settings):
    """Do the paths baked into settings.json and tasks.json still EXIST?

    ⛔ THIS IS THE ONE FAILURE A MARKETPLACE INSTALL CREATES AND NOTHING ELSE CATCHES.
    A marketplace install COPIES the plugin to
    `~/.claude/plugins/cache/<marketplace>/<plugin>/<VERSION>/`, and that path carries the
    version number. Hooks are immune - `${CLAUDE_PLUGIN_ROOT}` is re-expanded every session
    - but the statusline command and `.vscode/tasks.json` hold a LITERAL absolute path,
    because neither file gets that variable. ⇒ The next `claude plugin update` moves the
    directory, both keep pointing at a version that is gone, and they fail SILENTLY: no
    statusline renders, no watcher starts, every verdict reads NO-DATA, and the brake is
    off while everything still looks installed.

    ⛔ AND "THE PATH STILL EXISTS" IS NOT ENOUGH, which was this check's first mistake.
    Measured 2026-08-26: after `plugin update` from 0.1.0 to 0.1.1 the OLD directory was
    LEFT IN PLACE. So the wired path still resolved, still ran, and quietly executed the
    PREVIOUS VERSION - while --status reported "everything is live". A missing path is at
    least loud. A stale one that works is the exact failure mode this plugin exists to
    catch, so the test is: does the wired path match the CURRENTLY INSTALLED one?
    """
    import re
    installed = load(os.path.join(os.path.expanduser("~"), ".claude", "plugins",
                                  "installed_plugins.json"), {}).get("plugins", {})
    current = None
    for key, entries in installed.items():
        if key.startswith("dispatch-guard@") and entries:
            current = (entries[0].get("installPath") or "").replace("\\", "/").rstrip("/")
    problems = []

    def judge(what, path):
        norm = path.replace("\\", "/")
        if not os.path.exists(path):
            problems.append("%s points at a path that is GONE:%s  %s" % (what, chr(10), path))
        elif current and "/cache/" in norm and not norm.startswith(current + "/"):
            problems.append("%s runs a STALE COPY - the path exists, so nothing complains, "
                            "but it is not the installed version:%s  wired  : %s%s  current: %s"
                            % (what, chr(10), path, chr(10), current))

    sl = (settings.get("statusLine") or {}).get("command") or ""
    if "dispatch-guard" in sl:
        for quoted in re.findall(r'"([^"]+)"', sl):
            if "/" in quoted or "\\" in quoted:
                judge("statusline", quoted)
    tasks = load(os.path.join(os.getcwd(), ".vscode", "tasks.json"), {})
    for t in (tasks.get("tasks") or []):
        if t.get("label") != "Claude usage watch":
            continue
        for cand in [t.get("command")] + list(t.get("args") or []):
            if (isinstance(cand, str) and not cand.startswith("$")
                    and not cand.startswith("--") and ("/" in cand or "\\" in cand)):
                judge("the VS Code task", cand)
    if not problems:
        return False
    print("wired paths         : ⛔ WRONG - and this fails SILENTLY")
    for pr in problems:
        print("                      %s" % pr)
    print("                      The cache path carries the VERSION, and `plugin update`")
    print("                      LEAVES THE OLD DIRECTORY BEHIND - so a stale path keeps")
    print("                      working and keeps running old code. Fix by re-running")
    print("                      `python install.py --all` from the CURRENT install path.")
    return True


RESUME_TASK_NAME = "ClaudeDispatchGuardResume"


def resume_status():
    """Is a resume armed, and does the OS actually still hold the task?

    ⛔ IT ASKS THE SCHEDULER, not just the JSON, and that is the point of putting it in
    --status at all. `resume.json` records what this plugin BELIEVES it armed. The task can
    be gone anyway - deleted by hand, cleared by a cleanup tool, or never created because
    schtasks failed after the file was written. A record with no task behind it is the same
    trap as a brake with no data: it reads as protection that is not there.

    ⚠ The opposite mismatch matters too. A task with no record is an ORPHAN: nothing will
    cancel it, and when it fires, do_run finds no handoff and aborts - so it is harmless but
    permanent, and worth naming so somebody removes it.
    """
    import time
    state = load(os.path.join(STATE_DIR, "resume.json"), None)
    if os.name == "nt":
        probe = subprocess.run(["schtasks", "/Query", "/TN", RESUME_TASK_NAME],
                               capture_output=True, timeout=30)
        registered = probe.returncode == 0
    else:
        # `at` has no named jobs, so presence cannot be probed the same way. Say so rather
        # than reporting a guess as a measurement.
        registered = None

    if not state:
        if registered:
            print("resume armed        : ⚠ NO record, but the OS still holds a task named")
            print("                      %s - an ORPHAN. It will" % RESUME_TASK_NAME)
            print("                      abort harmlessly when it fires, but nothing will")
            print("                      ever remove it. Run `resume.py --cancel`.")
        else:
            print("resume armed        : no (nothing pending, which is the normal state)")
        return

    at = state.get("at")
    when = (time.strftime("%Y-%m-%d %H:%M", time.localtime(at))
            if isinstance(at, (int, float)) else "unknown")
    print("resume armed        : yes - fires %s" % when)
    print("                      task: %s" % state.get("task"))
    if registered is None:
        print("                      ⚠ cannot probe `at` for a named job; check with `atq`")
    elif registered:
        print("                      ⭐ the OS task IS registered")
    else:
        print("                      ⛔ the OS task is NOT registered. The record says armed")
        print("                         and the scheduler disagrees, so NOTHING will fire.")
        print("                         Re-arm it, or `resume.py --cancel` to clear the record.")
    if isinstance(at, (int, float)) and at > time.time():
        print("                      ⚠ This is the BACKUP route. If the window has already")
        print("                         reopened and you are carrying the work on yourself,")
        print("                         the gate cancels it on the next prompt - or run")
        print("                         `resume.py --cancel` now.")


def status():
    """Answer "is this actually working?" in one human-readable screen.

    ⛔ This exists because the plugin's own liveness message is spoken to the MODEL, not
    to the person - a SessionStart hook's stdout enters the agent's context and is never
    rendered on screen. So "I don't see anything" is the expected experience whether the
    plugin is working perfectly or not running at all, and those two must be
    distinguishable by something a person can run.

    Every line below is a measurement, not a claim: a stamp file that exists, a log with
    a timestamp, a verdict the interpreter actually returned.
    """
    import glob
    import time
    ok = True

    installed = load(os.path.join(os.path.expanduser("~"), ".claude", "plugins",
                                  "installed_plugins.json"), {}).get("plugins", {})
    enabled = load(SETTINGS, {}).get("enabledPlugins", {})
    found = next((k for k in installed if k.startswith("dispatch-guard@")), None)
    print("plugin installed    : %s" % (found or "NO - install it first"))
    print("plugin enabled      : %s" % (enabled.get(found) if found else False))
    # ⭐ THE ANSWER TO "so where IS it installed?", printed every time - not only when
    # something is already wrong. There is no fixed path to put in a document: the cache
    # path carries the VERSION, and `plugin update` leaves the old directory behind, so
    # listing the cache shows several. ⚠ And inside the VS Code extension there is no
    # session opening line to read it off, because a hook's stdout goes to Claude.
    # installed_plugins.json IS at a fixed path, so this is the one place that always knows.
    print("install path        : %s" % HERE)
    # ⭐ WHICH SETTINGS ARE PINNED, and why a new default may not have reached you. A value
    # in config.json always beats the code default, and there is no other way to see that
    # from outside: the plugin updates, the default moves, and nothing appears to happen.
    pinned = []
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.join(HERE, "hooks"))
        import usage as _u, dispatch_gate as _g          # noqa: E402
        disk = load(CONFIG_PATH, {}) or {}
        for k, v in sorted(_u.DEFAULTS.items()):
            if k in disk and disk[k] != v:
                pinned.append("%s = %r (default %r)" % (k, disk[k], v))
        for k, v in sorted(_g.DEFAULTS.items()):
            block = disk.get("dispatch") or {}
            if k in block and block[k] != v:
                pinned.append("dispatch.%s = %r (default %r)" % (k, block[k], v))
    except Exception:
        pinned = None
    if pinned is None:
        print("pinned settings     : could not be read")
    elif not pinned:
        print("pinned settings     : none - every setting follows the plugin's default")
    else:
        print("pinned settings     : ⚠ %d, and these OVERRIDE any new default" % len(pinned))
        for line in pinned:
            print("                      %s" % line)
    elsewhere = False
    if found and installed.get(found):
        rec = (installed[found][0].get("installPath") or "").replace("\\", "/").rstrip("/")
        if rec and rec != HERE.replace("\\", "/").rstrip("/"):
            elsewhere = True
            print("                      ⚠ that is NOT the installed copy. This script was")
            print("                        run from somewhere else; the installed one is:")
            print("                        %s" % rec)
    ok = ok and bool(found) and bool(enabled.get(found))

    stamps = sorted(glob.glob(os.path.join(STATE_DIR, "state", "*.start")),
                    key=lambda p: os.path.getmtime(p), reverse=True)
    if stamps:
        age = (time.time() - os.path.getmtime(stamps[0])) / 60.0
        print("SessionStart hook   : RAN - %d session(s) stamped, newest %.0f min ago"
              % (len(stamps), age))
        print("                      ⭐ this is the proof the hooks are live; the message")
        print("                         it prints goes to Claude, never to your screen")
    else:
        ok = False
        print("SessionStart hook   : ⛔ NEVER RAN - no session has been stamped.")
        print("                      A plugin's hooks load at SESSION START, so open a")
        print("                      new session after installing, then re-run this.")

    sl = load(SETTINGS, {}).get("statusLine") or {}
    print("statusline refresh  : %s" % (("every %ds" % sl["refreshInterval"])
                                        if sl.get("refreshInterval") else
                                        "⛔ NOT SET - numbers only move on interactive "
                                        "turns and go stale between them"))
    if wired_paths_health(load(SETTINGS, {})):
        ok = False
    cfg = load(os.path.join(STATE_DIR, "config.json"), {})
    limits = cfg.get("limits_file") or os.path.join(STATE_DIR, "limits.json")
    print("usage data file     : %s" % limits)
    data = load(limits, None)
    if data:
        age = (time.time() * 1000 - data.get("ts", 0)) / 60000.0
        flag = "  ⚠ STALE - a frozen percentage reads LOW, so the brake holds off"                if age > 15 else ""
        print("                      last written %.0f min ago%s" % (age, flag))

    # ⛔ WHERE THE LOG FILES ACTUALLY ARE, printed rather than described. config.json calls
    # this "a logs/ folder under the state directory", which is true and gives a person
    # nothing they can paste into a file manager. A sentence in the documentation can only
    # ever name the default; this resolves `history_dir` and prints the result.
    # ⚠ It usually does not exist, and that is not a fault: both switches that write here
    # are off by default. "Not created yet, and here is which switch is off" is the honest
    # answer to "where are my files?" - a path with no explanation is not.
    logs = cfg.get("history_dir") or os.path.join(STATE_DIR, "logs")
    logs = os.path.abspath(os.path.expanduser(logs))
    print("log files           : %s" % logs)
    # ⛔ AND THE ONE CASE WHERE THIS WHOLE BLOCK IS LOOKING IN THE WRONG PLACE. STATE_DIR is
    # a constant here, but usage.py's state_dir() reads $CLAUDE_DISPATCH_DIR first - so with
    # that variable set, the hooks write somewhere this script never looks, and every path
    # printed above it is the wrong one too. ⚠ NOT introduced by this line and NOT fixed by
    # it: making install.py follow the variable would move where it installs things, which
    # is a different decision. Saying so is the part that cannot wait.
    env_dir = os.environ.get("CLAUDE_DISPATCH_DIR")
    if env_dir and os.path.abspath(os.path.expanduser(env_dir)) != os.path.abspath(STATE_DIR):
        print("                      ⚠ $CLAUDE_DISPATCH_DIR is set to %s"
              % os.path.abspath(os.path.expanduser(env_dir)))
        print("                        The HOOKS use that; this script does not, so the")
        print("                        paths above are not where your files are.")
    if os.path.isdir(logs):
        kept = [f for f in os.listdir(logs)
                if f.startswith(("limits-history-", "usage-response-"))]
        total = 0
        for f in kept:
            try:
                total += os.path.getsize(os.path.join(logs, f))
            except OSError:
                pass
        days = cfg.get("history_keep_days", 30)
        forever = (not isinstance(days, (int, float)) or isinstance(days, bool)
                   or days <= 0)
        print("                      %d file%s, %.1f MB, kept %s"
              % (len(kept), "" if len(kept) == 1 else "s", total / 1048576.0,
                 "FOR EVER (history_keep_days is %r)" % (days,) if forever
                 else "%g days (history_keep_days)" % days))
    else:
        on = []
        if cfg.get("keep_history"):
            on.append("keep_history")
        dbg = cfg.get("debug") or {}
        if isinstance(dbg, list):
            dbg = {k: True for k in dbg}
        if isinstance(dbg, dict) and dbg.get("API_response_usage"):
            on.append("debug.API_response_usage")
        print("                      not created yet - %s"
              % ("nothing written since %s was switched on" % " and ".join(on) if on
                 else "keep_history and debug.API_response_usage are both off"))

    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "hooks", "usage.py"),
                            "--verdict"], capture_output=True, timeout=30,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        line = r.stdout.decode("utf-8", "replace").strip().splitlines()
        line = line[0] if line else "(no output)"
    except Exception as exc:
        r, line = None, "could not run: %r" % (exc,)
    print("usage verdict       : %s" % line)
    if line.startswith("NO-DATA"):
        ok = False
        print("                      ⛔ USAGE BRAKING IS INACTIVE. Nothing will refuse a")
        print("                         dispatch when the window runs out, and usage must")
        print("                         be reported as UNKNOWN, never as a number.")
        print("                         Fix: run this script with no arguments.")

    # ⛔ THE HALF --status COULD NOT ANSWER. It reported the statusline and said nothing at
    # all about the VS Code watcher - so "the usage terminal did not appear" had no diagnosis
    # and turned into a hunt. Measured 2026-08-28 on a second machine, where the task was
    # present and correct the whole time and the report could not say so.
    #
    # ⭐ IT ALSO NAMES WHAT THIS CANNOT SEE. Whether the task actually STARTED is not
    # knowable from here: VS Code runs folder-open tasks after enumerating every task
    # provider in that workspace, and any extension that asks a question during enumeration -
    # CMake Tools picking a CMakeLists.txt is the measured case - delays or pre-empts it.
    # That is somebody else's extension and not fixable from this plugin. What IS fixable is
    # it being invisible, so the two ordinary reasons are printed rather than left to guess.
    dirs = vscode_user_dirs()
    if not dirs:
        print("VS Code task        : no VS Code user directory on this machine - nothing to do")
    else:
        entry = user_task_entry()
        for d in dirs:
            path = os.path.join(d, "tasks.json")
            found = [t for t in ((load(path, {}) or {}).get("tasks") or [])
                     if isinstance(t, dict) and t.get("label") == TASK_LABEL]
            if not found:
                print("VS Code task        : ⛔ NOT in %s" % path)
                print("                      No usage terminal will open. Run this script")
                print("                      with --all, or start a session INSIDE VS Code")
                print("                      and the hook writes it.")
                ok = False
            elif found[0] != entry:
                # ⛔ ONLY THE INSTALLED COPY MAY CALL A TASK STALE. `user_task_entry()` builds
                # the entry from THIS script's own location, so running --status out of a
                # checkout compares the task against the checkout and reports a perfectly good
                # task as broken. Caught on the first run of this check, against a task that
                # was correct - which is the same false alarm the line above already exists to
                # prevent, and would have sent somebody to re-run --all for nothing.
                if elsewhere:
                    print("VS Code task        : present in %s" % path)
                    print("                      ⚠ cannot say whether it is CURRENT: this")
                    print("                        script is not the installed copy, so there")
                    print("                        is nothing valid to compare its path with.")
                else:
                    print("VS Code task        : ⚠ STALE in %s" % path)
                    print("                      it points at a different install path, so it")
                    print("                      fails silently. Re-run with --all.")
                    ok = False
            else:
                print("VS Code task        : present and current in %s" % path)
        auto = None
        for d in dirs:
            auto = (load(os.path.join(d, "settings.json"), {}) or {}).get("task.allowAutomaticTasks")
            if auto:
                break
        if auto == "on":
            print("automatic tasks     : allowed (task.allowAutomaticTasks = on)")
        else:
            print("automatic tasks     : ⛔ %s - VS Code will NOT start the task on folder"
                  % ("not set" if auto is None else auto))
            print("                      open, and says nothing about it. Fix: Ctrl+Shift+P")
            print("                      -> Tasks: Manage Automatic Tasks -> Allow.")
            ok = False
        # ⭐ AND NOW IT CAN SAY WHETHER THE TASK ACTUALLY RAN. `--watch` touches this on every
        # redraw - on the REDRAW rather than the fetch, because it deliberately stops calling
        # the API while nobody works and keeps drawing, so a fetch-based signal would read as
        # dead during exactly the idle stretch it is built for.
        mark = os.path.join(STATE_DIR, "watch.alive")
        if os.path.exists(mark):
            age = (time.time() - os.path.getmtime(mark)) / 60.0
            if age <= 2:
                print("usage watcher       : RUNNING - last drew %.0f min ago" % age)
            else:
                print("usage watcher       : ⚠ last drew %.0f min ago, so it is not running now"
                      % age)
                print("                      Reopen the FOLDER - the task fires on folder open.")
        else:
            print("usage watcher       : ⛔ HAS NEVER RUN on this machine.")
            print("                      The task above is only a definition; this is the")
            print("                      proof it started. Reopen the FOLDER (a task written")
            print("                      during a session starts on the NEXT one), and if it")
            print("                      still does not: check whether another extension")
            print("                      prompts you at folder open - VS Code runs the")
            print("                      folder-open tasks only after every task provider")
            print("                      has answered.")
            ok = False

    resume_status()

    logs = glob.glob(os.path.join(os.getcwd(), ".claude", "dispatch-gate.log"))
    if logs:
        try:
            with open(logs[0], encoding="utf-8") as f:
                tail = [l.rstrip() for l in f if l.strip()][-3:]
            print("gate log (last 3)   :")
            for l in tail:
                print("                      %s" % l)
        except OSError:
            pass
    else:
        print("gate log            : none yet in this directory - written on the first")
        print("                      dispatch decision, so an empty one is normal")

    print()
    print("OVERALL             : %s" % ("everything is live" if ok
                                        else "⛔ NOT fully live - see the lines above"))
    return 0 if ok else 1


def _watch_command(repo):
    """(command, args) for the task, expressed so it survives being committed.

    ⚠ `.vscode/tasks.json` is often TRACKED - it is in this repository - so an absolute
    path baked in here breaks for the next person who clones. When the plugin lives
    inside the repository, address it through `${workspaceFolder}`; only fall back to an
    absolute path when it genuinely lives elsewhere, and say so.

    ⛔ It goes through `run.sh` rather than naming an interpreter, because `python3` on
    Windows is a Microsoft Store stub that resolves and then exits 49.
    """
    # ⛔ On Windows the launcher is run.cmd, NOT bash run.sh. Measured 2026-08-26: from
    # PowerShell, `bash` resolves to the WSL launcher stub in WindowsApps and fails with
    # "no installed distributions". Claude Code invokes its own bash and is fine; a VS
    # Code task goes through the user's default shell and is not. The command resolving
    # is exactly what makes this invisible until it runs.
    win = os.name == "nt"
    launcher = os.path.join(HERE, "hooks", "run.cmd" if win else "run.sh")
    script = os.path.join(HERE, "hooks", "usage.py")
    base = "${workspaceFolder}/"
    try:
        rel_l = os.path.relpath(launcher, repo).replace("\\", "/")
        rel_s = os.path.relpath(script, repo).replace("\\", "/")
        if not rel_l.startswith(".."):
            return base + rel_l, [base + rel_s, "--watch"]
    except ValueError:
        pass                      # different drive; no relative path exists
    return launcher.replace("\\", "/"), [script.replace("\\", "/"), "--watch"]


def allow_automatic_tasks():
    """Grant VS Code permission to run a folderOpen task, in USER settings. Returns a line.

    ⭐ IT RETURNS ITS SUMMARY as well as printing it, because vscode_user_task() collects
    lines instead of printing - and a grant nobody reports is a grant nobody can check. That
    matters here more than usual: VS Code asks for this permission with a NOTIFICATION, and a
    notification that fades unanswered leaves the task installed, listed, and never running.

    ⛔ IT CANNOT BE A WORKSPACE SETTING, and that is a security property rather than an
    oversight: if a repository could set `task.allowAutomaticTasks` in its own
    `.vscode/settings.json`, cloning any repository would let it run commands the moment
    the folder opened. VS Code therefore honours it only from user scope. Measured
    2026-08-26 - written to the workspace, the task never fired and nothing said why.

    ⚠ The palette command usually quoted for this ("Tasks: Manage Automatic Tasks") does
    not exist in every build; it is absent from the one measured here. Writing the setting
    is the reliable route.

    ⭐ The edit is TEXTUAL, not a parse-and-rewrite. A user settings.json is JSONC: it
    carries comments, and a json.load/json.dump round trip would silently delete every one
    of them - somebody else's configuration destroyed to add one key. Line endings are
    preserved for the same reason: rewriting 222 CRLFs as LF turns a two-line change into
    a whole-file diff nobody can review.
    """
    CRLF = chr(13) + chr(10)
    LF = chr(10)
    candidates = [
        os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Code", "User",
                     "settings.json"),
        os.path.join(os.path.expanduser("~"), ".config", "Code", "User", "settings.json"),
        os.path.join(os.path.expanduser("~"), "Library", "Application Support", "Code",
                     "User", "settings.json"),
    ]
    path = next((p for p in candidates if os.path.exists(p)), None)
    if not path:
        print("automatic tasks     : could not find VS Code's user settings.json.")
        print("                      Add this to it by hand or the task will never run:")
        print('                        "task.allowAutomaticTasks": "on"')
        return "⚠ could not find VS Code user settings - allow automatic tasks by hand"
    try:
        raw = open(path, "rb").read().decode("utf-8-sig")
    except OSError as exc:
        print("automatic tasks     : could not read %s (%r)" % (path, exc))
        return "⚠ could not read VS Code user settings (%r)" % (exc,)
    if "allowAutomaticTasks" in raw:
        print("automatic tasks     : already allowed in user settings")
        return None                       # nothing changed, so nothing to report upward
    brace = raw.find("{")
    if brace < 0:
        print("automatic tasks     : %s does not look like JSON; add the key by hand" % path)
        return "⚠ VS Code user settings does not look like JSON - add the key by hand"
    was_crlf = CRLF in raw
    ins = (LF + "  // added by dispatch-guard: lets .vscode/tasks.json runOn:folderOpen run"
           + LF + '  "task.allowAutomaticTasks": "on",')
    out = raw[:brace + 1] + ins + raw[brace + 1:]
    if was_crlf:
        out = out.replace(CRLF, LF).replace(LF, CRLF)
    try:
        with open(path + ".bak-dispatch-guard", "wb") as f:
            f.write(raw.encode("utf-8"))
        with open(path, "wb") as f:
            f.write(out.encode("utf-8"))
        print("automatic tasks     : allowed in %s" % path)
        print("                      previous file kept as .bak-dispatch-guard")
        return "allowed automatic tasks in VS Code user settings"
    except OSError as exc:
        print("automatic tasks     : could not write %s (%r)" % (path, exc))
        return "⚠ could not grant automatic tasks (%r)" % (exc,)


# ⭐ MEASURED 2026-08-27, and it is the fact this whole design rests on: a USER-LEVEL task
# does honour `runOn: folderOpen`. The documentation says only that user tasks are limited to
# `shell` and `process` types and says nothing about folderOpen, so it was tested: a task
# placed in %APPDATA%/Code/User/tasks.json opened its terminal on the next folder open, and
# appeared in Run Task. ⇒ One file, written once, covers every project for ever.
#
# ⛔ WHY THAT MATTERS MORE THAN THE CONVENIENCE. The per-project file could not exist before
# the session that created it, so the FIRST open of every new project never had the task -
# not once per machine, once per PROJECT. And it put a file into somebody's repository, which
# needed a tracked-file guard, a JSONC guard, and a setting to switch the whole thing off.
# The user-level file needs none of that: it is the person's own editor configuration.
#
# ⚠ Variants keep their own directory. Only ones that already EXIST are written to - creating
# a configuration directory for an editor that is not installed would be litter.
VSCODE_USER_DIRS = ("Code", "Code - Insiders", "VSCodium")

TASK_LABEL = "Claude usage watch"


def vscode_user_dirs():
    """Every VS Code-family User directory that exists on this machine.

    ⚠ Portable installations put this under $VSCODE_PORTABLE/user-data instead, and that is
    honoured when the variable is set. A person running two variants gets the task in both,
    which is what they would expect.
    """
    out = []
    portable = os.environ.get("VSCODE_PORTABLE")
    if portable:
        d = os.path.join(portable, "user-data", "User")
        if os.path.isdir(d):
            out.append(d)
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData",
                                                         "Roaming")
        roots = [os.path.join(base, n, "User") for n in VSCODE_USER_DIRS]
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
        roots = [os.path.join(base, n, "User") for n in VSCODE_USER_DIRS]
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"),
                                                                 ".config")
        roots = [os.path.join(base, n, "User") for n in VSCODE_USER_DIRS]
    out.extend(d for d in roots if os.path.isdir(d) and d not in out)
    return out


def user_task_entry():
    """The task dict for the USER-level file. Absolute paths, always.

    ⛔ IT MUST NOT GO THROUGH _watch_command(). That function shortens the path to
    `${workspaceFolder}/...` whenever the plugin happens to sit inside the folder it is given
    - which is right for a per-PROJECT task that may be committed, and wrong here in a way
    that looks fine. Measured 2026-08-27: called with the home directory, and the plugin
    cache living under it, it produced
    `${workspaceFolder}/.claude/plugins/cache/.../run.cmd`. A user-level task has no
    workspace of its own, so VS Code would resolve that variable against WHATEVER project is
    open and look for the plugin inside it - failing in every project, including the one
    where it was written.
    """
    win = os.name == "nt"
    launcher = os.path.join(HERE, "hooks", "run.cmd" if win else "run.sh")
    script = os.path.join(HERE, "hooks", "usage.py")
    entry = dict(vscode_task_entry(os.path.expanduser("~")))
    entry["command"] = launcher.replace("\\", "/")
    entry["args"] = [script.replace("\\", "/"), "--watch"]
    return entry


def vscode_user_task(remove=False, check_only=False):
    """Put the watcher task in VS Code's USER tasks file. Returns a list of what it did.

    ⛔ MERGES, and refuses a file it cannot read. This is the person's own editor
    configuration and may hold their own tasks - and VS Code allows comments in it, which
    json.load does not. See readable(): an unreadable file is left exactly as it is.
    """
    done = []
    for d in vscode_user_dirs():
        path = os.path.join(d, "tasks.json")
        if not readable(path):
            done.append("⛔ %s exists but does not parse as JSON - NOT touched" % path)
            continue
        data = load(path, {"version": "2.0.0", "tasks": []})
        data.setdefault("version", "2.0.0")
        tasks = [t for t in data.get("tasks") or []
                 if not (isinstance(t, dict) and t.get("label") == TASK_LABEL)]
        if remove:
            if len(tasks) == len(data.get("tasks") or []):
                done.append("nothing to remove in %s" % path)
                continue
            data["tasks"] = tasks
            if not check_only:
                save(path, data)
            done.append("%s from %s" % ("would remove" if check_only else "removed", path))
            continue
        entry = user_task_entry()
        if entry in (data.get("tasks") or []):
            done.append("already current in %s" % path)
            continue
        tasks.append(entry)
        data["tasks"] = tasks
        if not check_only:
            save(path, data)
            # ⛔ THE PERMISSION HAS TO TRAVEL WITH THE TASK. VS Code refuses to run an
            # automatic task until `task.allowAutomaticTasks` is on, and it asks with a
            # NOTIFICATION - which fades. Measured 2026-08-27: a fresh install wrote the task,
            # the notification appeared and vanished before it could be read, the setting
            # stayed unset, and the terminal never opened. The task existed and Run Task
            # listed it, which is exactly the shape of failure that looks like nothing.
            # ⚠ This grant lived only on the old per-PROJECT path and was left behind when
            # the task moved to the user level in 0.13.0.
            grant = allow_automatic_tasks()
            if grant:
                done.append(grant)
        done.append("%s %s" % ("would write" if check_only else "wrote", path))
    if not done:
        done.append("no VS Code user directory found - nothing to do")
    return done


def vscode_user_task_current():
    """Is our task already correct in every user directory that exists?"""
    dirs = vscode_user_dirs()
    if not dirs:
        return True                       # nothing to keep current
    entry = user_task_entry()
    for d in dirs:
        path = os.path.join(d, "tasks.json")
        if not readable(path):
            return True                   # cannot read: pretend current, never rewrite
        if entry not in ((load(path, {}) or {}).get("tasks") or []):
            return False
    return True


def vscode_task_entry(repo):
    """The exact task dict this copy would write for `repo`. One definition, three callers.

    ⭐ Split out so that "is the task already correct?" and "write the task" cannot drift
    apart. The gate asks the first question on every session start; if it answered from its
    own idea of the shape, a change here would leave it rewriting a file that was already
    right, or leaving one that was already wrong.
    """
    cmd, args = _watch_command(repo)
    return {
        "label": "Claude usage watch",
        # ⛔ "process", NOT "shell". A shell task is handed to the user's default shell,
        # which on Windows is PowerShell - and in PowerShell a quoted path at the start of
        # a line is a STRING LITERAL, not a command. Measured 2026-08-26: the task failed
        # with "Unexpected token", so nothing ever appeared and nothing said why. "process"
        # execs the program directly with an argument list, so no shell parses anything.
        "type": "process",
        "command": cmd,
        "args": args,
        "presentation": {"reveal": "always", "panel": "dedicated", "echo": False,
                         "focus": False, "showReuseMessage": False},
        "runOptions": {"runOn": "folderOpen"},
        "problemMatcher": [],
    }


def vscode_task_present(repo):
    """Does this project already carry a task with our label, right or wrong?

    ⭐ The distinction that decides whether consent is needed. CREATING this file puts
    something into a repository that was not there before, so it is opt-in. REPAIRING one
    that is already there, and already ours, adds nothing - it only stops it running the
    version `claude plugin update` moved on from.
    """
    path = os.path.join(repo, ".vscode", "tasks.json")
    return any(isinstance(t, dict) and t.get("label") == "Claude usage watch"
               for t in (load(path, {}) or {}).get("tasks") or [])


def vscode_task_current(repo):
    """Does repo/.vscode/tasks.json ALREADY hold exactly the task this copy would write?

    ⚠ Compared field by field, not just by label. A task left behind by an older version
    carries that version's absolute path: it still exists, still runs, and still reports
    itself as installed - the stale-copy failure this plugin exists to catch.
    """
    path = os.path.join(repo, ".vscode", "tasks.json")
    for t in (load(path, {}) or {}).get("tasks") or []:
        if isinstance(t, dict) and t.get("label") == "Claude usage watch":
            return t == vscode_task_entry(repo)
    return False


def vscode_task(repo, remove=False, check_only=False, grant=True):
    """Write a VS Code task that opens the usage watcher automatically.

    ⛔ THE HONEST ANSWER to "can the plugin open a terminal itself?" is: not a VS Code
    one. A hook is a plain process; it has no access to the editor's API, so it cannot
    create an integrated terminal. It *could* spawn a bare OS console window, but that
    lands outside the editor, steals focus, and reappears on every session - worse than
    the problem.

    ⭐ VS Code's own mechanism does exactly what was wanted: a task with
    `runOptions.runOn = "folderOpen"` starts in the integrated panel when the folder is
    opened, with no command typed. That is a per-PROJECT file, which is why the plugin
    cannot ship it and this writes it on request instead.

    ⚠ VS Code asks for permission the first time an automatic task runs (Allow Automatic
    Tasks). Until that is granted it silently does nothing - so if no panel appears, that
    prompt is the first thing to check.
    """
    path = os.path.join(repo, ".vscode", "tasks.json")
    if not readable(path):
        # ⛔ VS Code accepts comments in tasks.json; json.load does not. Rewriting from an
        # empty fallback here deleted the person's own tasks. See readable().
        print("VS Code task        : ⛔ %s exists but does not parse as JSON" % path)
        print("                      (VS Code allows comments here and this reader does")
        print("                      not). NOTHING was written - fixing it by hand is the")
        print("                      only safe move, since anything else loses your tasks.")
        return 1
    data = load(path, {"version": "2.0.0", "tasks": []})
    data.setdefault("version", "2.0.0")
    tasks = [t for t in data.get("tasks", []) if t.get("label") != "Claude usage watch"]
    if remove:
        # ⛔ AN UNINSTALL MUST NOT CREATE A FILE. load() falls back to an empty task list, so
        # removing from a project that never had a tasks.json wrote a new empty one - seen
        # for real while clearing a machine down: `--all --uninstall` left behind a .vscode
        # directory in a repository that had none.
        if not os.path.exists(path):
            print("VS Code task        : nothing to remove - %s does not exist" % path)
            return 0
        # --check has to gate the DELETE too, not only the write. This branch returns
        # before the check_only guard below, so without this `--vscode-task --remove
        # --check` removed the task for real.
        if check_only:
            print("VS Code task        : would remove the task from %s" % path)
            print("                      (--check: not removed)")
            return 0
        data["tasks"] = tasks
        save(path, data)
        print("removed the watcher task from %s" % path)
        return 0
    entry = vscode_task_entry(repo)
    cmd, args = entry["command"], entry["args"]
    # ⛔ --check has to stop HERE, before save(). It used to be honoured by the statusline
    # half only, so `--all --check` printed "not written" about the statusline and then
    # wrote .vscode/tasks.json anyway - a dry run that was not dry is worse than no dry
    # run, because it is the one thing a cautious user trusts.
    if check_only:
        print("VS Code task        : would write %s" % path)
        print("                      command: %s %s" % (cmd, " ".join(args)))
        print("                      (--check: not written, and automatic tasks not")
        print("                      allowed either)")
        return 0
    tasks.append(entry)
    data["tasks"] = tasks
    save(path, data)
    print("wrote %s" % path)
    if "${workspaceFolder}" not in cmd:
        print("                      ⚠ that is an ABSOLUTE path, because the plugin")
        print("                      lives outside this workspace. If it is a marketplace")
        print("                      install the path carries the VERSION, so the next")
        print("                      `claude plugin update` breaks this task SILENTLY.")
        print("                      Re-run this command after any update; `--status`")
        print("                      checks the path and says so if it has gone.")

    # ⚠ Only when this call is the one that INSTALLED the task. Repairing a stale path is
    # not an occasion to edit VS Code's user settings: the permission was either granted
    # when it was installed or deliberately withheld, and re-granting it silently, from a
    # hook, is exactly the surprise this plugin is careful about everywhere else.
    if grant:
        allow_automatic_tasks()

    print()
    print("It opens a dedicated terminal showing the usage line, on every folder open.")
    print("⚠ REOPEN THE FOLDER for it to start - the task fires on folder open, not now.")
    print("  Nothing appearing? Terminal -> Run Task -> 'Claude usage watch' runs it by")
    print("  hand: if that works the task is fine and only the automatic trigger is not,")
    print("  which separates two failures that otherwise look identical.")
    return 0


def statusline_install(argv):
    """The statusline half. Split out so --all can run it and then the task half."""
    check_only = "--check" in argv
    # ⛔ THE SAME HOLE readable() WAS WRITTEN FOR, ON THE MANUAL PATH. An unparseable
    # settings.json read back as {} here, so `current` was None, `ours` was False, and the
    # MISSING branch wrote a file containing nothing but statusLine over everything the
    # person had. Guarding only the hook's writers left the one a human runs by hand.
    if not readable(SETTINGS):
        print("settings.json       : ⛔ %s exists but does not parse as JSON." % SETTINGS)
        print("                      NOTHING was written. Fix it by hand first - anything")
        print("                      else here would replace the whole file.")
        return 1
    settings = load(SETTINGS, {})
    current = settings.get("statusLine")
    ours = statusline_is_ours(current)

    changed = []
    if ensure_refresh(settings, changed) and not check_only:
        save(SETTINGS, settings)

    name, path = check_python()
    print("Python found        : %s" % (("%s -> %s" % (name, path)) if name else "NONE"))
    for c in changed:
        print("refresh             : %s%s" % (c, "" if not check_only else "  (--check: not written)"))
    print("settings.json       : %s" % SETTINGS)
    print("state directory     : %s" % STATE_DIR)
    if check_only:
        print("config.json         : %s" % ("already there" if os.path.exists(CONFIG_PATH)
                                            else "would be created (--check: not written)"))
    else:
        made = seed_config()
        print("config.json         : %s" % (("created %s - every setting is explained "
                                             "inside it" % made) if made
                                            else "already there, not touched"))

    if "--uninstall" in argv:
        if not ours:
            print("statusLine          : nothing to remove - it is not this plugin's")
        elif check_only:
            print("statusLine          : would REMOVE this entry (--check: kept)")
            print("                      %s" % str(current.get("command", "")))
        else:
            settings.pop("statusLine", None)
            save(SETTINGS, settings)
            print("statusLine          : REMOVED (refreshInterval went with it)")
            # ⛔ AND IT HAS TO STAY REMOVED. auto_statusline defaults to true, so the very
            # next SessionStart hook found an empty slot and put the line straight back -
            # an uninstall that undoes itself before the person has finished reading its
            # output. Turning the two automatic behaviours off is part of removing them.
            try:
                set_dispatch_config("auto_statusline", False)
                done = "auto_statusline"
                # ⚠ Only when the task half is going too. Somebody removing the statusline
                # alone did not ask for their VS Code tasks to stop being maintained.
                if "--all" in argv:
                    set_dispatch_config("auto_vscode_task", False)
                    done += " and auto_vscode_task"
                print("                      %s set to false," % done)
                print("                      so the hook does not put it back")
            except Exception as exc:
                print("                      ⚠ could not switch off auto_statusline (%r)." % exc)
                print("                      The hook WILL reinstall the line next session.")
        # ⛔ CANCEL AN ARMED RESUME, and do it here rather than in a document. Every other
        # leftover just sits on disk; this one is an OS scheduled task that WAKES UP and
        # runs a script the uninstall may have taken away. A leftover that executes is not
        # the same class of mess as a leftover that waits to be deleted.
        if not check_only:
            try:
                subprocess.run([sys.executable, os.path.join(HERE, "hooks", "resume.py"),
                                "--cancel"], timeout=30)
            except Exception as exc:
                print("armed resume        : could not run resume.py --cancel (%r)" % exc)
                print("                      Check it by hand: resume.py --status")
        print()
        print("⚠ STILL ON DISK, because this script did not create it and will not guess:")
        print("  - the state directory, which holds your usage history and config:")
        print("      %s" % STATE_DIR)
        print("  - the plugin itself (hooks and the skill):")
        print("      claude plugin uninstall dispatch-guard@dispatch-guard")
        print("      claude plugin marketplace remove dispatch-guard")
        print("  - Memory/tasks in each project. That is YOUR work log, never touched here.")
        print("  - `task.allowAutomaticTasks` in VS Code user settings, and any")
        print("    .bak-dispatch-guard beside it. Other tasks may rely on that switch now.")
        if "--all" not in argv:
            print("  - the `Claude usage watch` task in this project. Use --all --uninstall,")
            print("    or --vscode-task --remove, to take that out too.")
        return 0

    if "--take-statusline" in argv and current and not ours:
        # ⭐ The deliberate switch. Reading another tool's data works for the BRAKE, but
        # this plugin's own bar, colours and daily history files stay dark until it owns
        # that slot - the statusline Claude Code invokes is what re-runs usage.py on a
        # timer, and `usage.py --watch` is the only other thing that does. Never done implicitly: the slot holds exactly one command, and taking
        # it silently would remove whatever the person chose to put there.
        backup = SETTINGS + ".statusline-backup.json"
        settings["statusLine"] = {"type": "command", "command": COMMAND}
        ensure_refresh(settings, [])
        if not check_only:
            save(backup, {"statusLine": current})   # ⚠ --check must write NOTHING at all
            save(SETTINGS, settings)
        print("statusLine          : TAKEN OVER by this plugin%s"
              % ("  (--check: not written)" if check_only else ""))
        print("                      previous command saved to %s" % backup)
        print("                      %s" % current.get("command"))
        print()
        print("⚠ The numbers appear on the NEXT interactive turn. Until then the verdict")
        print("  is whatever the old data said, and history starts from the first render.")
        return 0

    if ours:
        # ⛔ "OURS" IS NOT THE SAME AS "CURRENT", and treating them as the same made the
        # repair command fail to repair. A marketplace path carries the VERSION, so after
        # `claude plugin update` the slot still holds OUR command - pointing at the copy
        # update left behind. It exists, so it runs, so nothing complains. Measured
        # 2026-08-26: --status called the statusline a STALE COPY while --all said
        # "nothing to do" in the same minute. A tool that detects a fault and then
        # declines to fix it is worse than one that does neither, because the report
        # reads like the repair already happened.
        wired = str(current.get("command", ""))
        if wired == COMMAND:
            print("statusLine          : already ours - nothing to do")
        elif check_only:
            print("statusLine          : ours, but wired to another path - would RE-POINT")
            print("                      from: %s" % wired)
            print("                      to  : %s" % COMMAND)
        else:
            repoint_statusline()          # one implementation; see its docstring
            print("statusLine          : RE-POINTED at this copy - it was ours, but wired")
            print("                      to a different path, which keeps working and keeps")
            print("                      running old code")
            print("                      from: %s" % wired)
            print("                      to  : %s" % COMMAND)
    elif current:
        print("statusLine          : ALREADY SET by something else, and NOT overwritten:")
        print("                      %s" % current.get("command"))
        print("                      ⛔ USAGE BRAKING WILL NOT WORK until one of these is true:")
        print("                         (a) replace it with the command below, or")
        print("                         (b) set limits_file in %s"
              % os.path.join(STATE_DIR, "config.json"))
        print("                         %s" % COMMAND)
        return 0

    else:
        if check_only:
            print("statusLine          : MISSING - would install")
        else:
            settings["statusLine"] = {"type": "command", "command": COMMAND}
            save(SETTINGS, settings)
            print("statusLine          : installed")
        print("                      %s" % COMMAND)
        if os.sep + "cache" + os.sep in HERE:
            print("                      ⚠ a marketplace install, so that path carries the")
            print("                        VERSION. `claude plugin update` moves it and the")
            print("                        statusline then fails SILENTLY - re-run this from")
            print("                        the new path, and use --status to check.")

    print()
    print("Hooks are NOT installed by this script - enable the plugin and Claude Code")
    print("reads hooks/hooks.json itself. This script only handles the one thing a")
    print("plugin cannot do for itself.")
    print()
    print("⚠ The LINE appears on the next interactive turn, not immediately - a")
    print("  statusline renders on a turn, not on every tool call.")
    print("⭐ The BRAKE does not wait for it: the dispatch gate forks its own refresh")
    print("  when the numbers go stale, so it works with or without this.")
    return 0


def main():
    """One entry point. ⭐ `--all` is the whole manual half in a single command.

    ⛔ WHY TWO COMMANDS IS THE FLOOR, and it cannot be one. A plugin has no install-time
    hook, `statusLine` is not a key a plugin manifest can set, and `.vscode/tasks.json` is
    per-PROJECT so a plugin could not know which project to write it into. Hooks and skills
    DO install themselves - `claude plugin install` is all they need. What is left is this
    script, and --all collapses it to one run.

    ⚠ --all is not the DEFAULT, deliberately. The task half writes `.vscode/tasks.json`
    into the current project - a file most repositories track - and edits VS Code's user
    settings. Doing that to somebody who only wanted a statusline is an overreach, so it is
    opt-in and named.
    """
    argv = sys.argv[1:]
    if "--status" in argv:
        return status()
    for flag, value in (("--enable-auto-task", True), ("--disable-auto-task", False)):
        if flag in argv:
            # ⭐ A NAMED FLAG rather than "edit this JSON by hand". It is what the agent runs
            # when somebody answers yes to the offer, and set_dispatch_config() merges, so a
            # one-word answer cannot cost them the rest of their configuration.
            path = set_dispatch_config("auto_vscode_task", value)
            print("auto_vscode_task    : %s in %s" % (value, path))
            # ⭐ AN ANSWER, EITHER WAY, RETIRES THE OFFER. Turning it off is a decision, and
            # a decision must not be re-litigated at the next session start - while a
            # question nobody ever answered has to survive, which is why the gate counts
            # misses instead of assuming the first message was seen.
            try:
                with open(os.path.join(STATE_DIR, "asked-vscode-task"), "w",
                          encoding="utf-8") as f:
                    json.dump({"answered": True, "value": value}, f)
            except OSError:
                pass
            if value:
                print("                      New projects opened in VS Code now get the")
                print("                      `Claude usage watch` task by themselves.")
                print("                      ⚠ REOPEN THE FOLDER for it to start.")
            return 0
    if "--all" in argv:
        # ⚠ argv goes through WHOLE, --all included. It used to be filtered out, so the
        # statusline half could not tell `--all --uninstall` from a bare --uninstall and
        # told the reader to remove the task they were already removing.
        rc = statusline_install(argv)
        print()
        print("=" * 62)
        print()
        # ⭐ --uninstall implies removal of the task half. Without this, `--all
        # --uninstall` removed the statusline and then WROTE the task back - the opposite
        # of what one word in the command line asked for.
        # ⭐ THE USER-LEVEL FILE IS THE DEFAULT NOW - one write, every project, no reopen
        # cycle per project and nothing placed in anybody's repository.
        for line in vscode_user_task(remove="--uninstall" in argv or "--remove" in argv,
                                     check_only="--check" in argv):
            print("VS Code task        : %s" % line)
        rc2 = 0
        # ⚠ A per-project file from an earlier version is still REMOVED by an uninstall, and
        # still repaired if somebody asks for one explicitly with --vscode-task.
        if "--uninstall" in argv or "--remove" in argv:
            rc2 = vscode_task(os.getcwd(), remove=True, check_only="--check" in argv)
        print()
        if "--check" in argv:
            print("⭐ --check: NOTHING was changed. Re-run without --check to apply it.")
        elif "--uninstall" in argv:
            print("⭐ Both halves removed. See the list above for what is still on disk.")
        else:
            print("⭐ Both halves done. Hooks and the skill needed nothing - they came with")
            print("   the plugin. ⚠ REOPEN THE FOLDER for the watcher task to start.")
        return rc or rc2
    if "--vscode-user-task" in argv:
        for line in vscode_user_task(remove="--remove" in argv,
                                     check_only="--check" in argv):
            print("VS Code task        : %s" % line)
        return 0
    if "--vscode-task" in argv:
        return vscode_task(os.getcwd(), remove="--remove" in argv,
                           check_only="--check" in argv)
    return statusline_install(argv)


def _utf8_console():
    """Make output survive a legacy console codepage.

    ⛔ Windows consoles default to a legacy codepage - cp950 on this machine - and a
    single non-ASCII character in a message then raises UnicodeEncodeError and kills the
    script. Measured 2026-08-26: install.py wrote its file and THEN crashed on the very
    warning explaining what to do next, so the user saw a traceback instead of the
    instruction. errors="replace" is deliberate: a mangled glyph is a cosmetic problem,
    a crash is not.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


if __name__ == "__main__":
    _utf8_console()
    sys.exit(main())
