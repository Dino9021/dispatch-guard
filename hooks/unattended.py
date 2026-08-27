#!/usr/bin/env python3
"""SessionStart: tell the agent to load the `unattended-work` skill - unless switched off.

⛔ WHY A SCRIPT RATHER THAN A CONDITIONAL HOOK. A plugin's hooks ALWAYS fire; the official
reference is explicit that they "cannot be conditionally enabled/disabled based on user
config". So the choice cannot live in `hooks.json` - it has to live here, in what the script
decides to PRINT. An empty stdout is a hook that did nothing, which is exactly what "off"
should look like.

⚠ SHELL-FORM HOOKS CANNOT SUBSTITUTE `${user_config.KEY}`, deliberately: it would let a
configured value reach a shell as a command. The value arrives as an environment variable
instead, `CLAUDE_PLUGIN_OPTION_<KEY UPPERCASED>`.

⛔ UNSET OR UNREADABLE MEANS ON, and that direction is not arbitrary. The default is true, and
a reminder that silently stops appearing is worse than one that appears when unwanted: the
owner would believe the working rules were in force while nothing had loaded them. Failing
towards "say it" is failing towards being noticed.

Standard library only, like everything else here.
"""

import json
import os
import sys

OPTION = "CLAUDE_PLUGIN_OPTION_ANNOUNCE_UNATTENDED_WORK"

# ⚠ Only these mean OFF. Anything else - including an empty string, a typo, or a value some
# future Claude Code spells differently - leaves the reminder on. See the docstring.
OFF = ("false", "0", "no", "off")

REMINDER = (
    "Invoke the unattended-work skill now. It governs review rounds, the stall test, "
    "mutation-checking fail-open guards, when you may proceed without the owner, and the "
    "exit bar before handing work back. Print its ACTIVE confirmation line as your first "
    "output."
)

# ⭐ THE LINE THE PERSON SEES, and it exists because the reminder above does not reach them.
# `additionalContext` goes to the MODEL and nowhere else, so "the skill loaded" and "the hook
# never ran" looked identical from a chair - the same channel confusion that cost this plugin
# four separate defects. `systemMessage` is displayed to the user on every hook event, per the
# shipped reference. => Two halves: this line proves the hook FIRED, and the skill's own ACTIVE
# line proves the agent ADOPTED it. Neither one alone answers the question.
SEEN = ("dispatch-guard: asked this session to load the unattended-work skill. "
        "Expect it to answer with a line beginning `unattended-work ACTIVE`; if that line "
        "does not appear, nothing loaded the rules. Turn this off with "
        "announce_unattended_work=false.")


def announcing(env=None):
    """Should the reminder be printed? The one decision this file makes, split out to check."""
    env = os.environ if env is None else env
    raw = env.get(OPTION)
    if raw is None:
        return True
    return str(raw).strip().lower() not in OFF


def main():
    # ⚠ The hook payload arrives on stdin and is not needed. It is drained anyway: leaving a
    # pipe unread can hand the writer a broken pipe on some platforms.
    try:
        sys.stdin.read()
    except Exception:
        pass
    if not announcing():
        return 0
    # ⭐ JSON RATHER THAN PLAIN TEXT, because plain stdout can only reach the model. The
    # SessionStart output schema accepts `hookSpecificOutput.additionalContext` - read out of
    # the shipped binary BEFORE changing this, since switching blind would have risked losing
    # the reminder altogether - and `systemMessage` is common to every hook event.
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": "SessionStart",
                               "additionalContext": REMINDER},
        "systemMessage": SEEN,
    }, ensure_ascii=False))
    return 0


def selftest():
    """`unattended.py --selftest` - the on/off branch, which is the whole feature.

    ⛔ A default-on option that has never been switched off is an untested branch, and it
    fails in the direction that looks fine: the reminder keeps appearing and nobody learns
    that "off" does nothing.
    """
    for value in ("false", "False", "FALSE", " off ", "0", "no", "No"):
        assert not announcing({OPTION: value}), "%r should switch it off" % value
    for value in ("true", "True", "1", "yes", "", "  ", "maybe", "ON", "enabled"):
        assert announcing({OPTION: value}), "%r must NOT switch it off" % value
    assert announcing({}), "unset must mean ON - see the docstring"
    assert announcing({"SOMETHING_ELSE": "false"}), "the wrong variable switched it off"
    # ⛔ AND IT MUST REACH THE PERSON, not only the model. Checked as JSON rather than by eye:
    # the reminder used to be plain text, which only ever reached the model, so "the skill
    # loaded" and "the hook never ran" were indistinguishable from outside.
    import contextlib
    import io as _io

    # ⛔ STDIN MUST BE REPLACED BEFORE CALLING main(), and this is not tidiness. main() drains
    # stdin - correctly, because a hook is handed a payload there and an unread pipe can break
    # the writer - so calling it with a TERMINAL on stdin blocks until end of file, which a
    # terminal never sends. Measured: two runs of Tools/Debug/test_all.py sat on this for over
    # an hour, and `python unattended.py --selftest` typed by hand hung the same way. ⚠ That is
    # the documented way to diagnose an install, so the hang was in the shipped product, not
    # only in the checks.
    def _run_main():
        buf = _io.StringIO()
        _saved_in = sys.stdin
        sys.stdin = _io.StringIO("")
        try:
            with contextlib.redirect_stdout(buf):
                main()
        finally:
            sys.stdin = _saved_in
        return buf

    buf = _run_main()
    out = json.loads(buf.getvalue())
    assert out["systemMessage"].startswith("dispatch-guard:"), out
    assert "unattended-work ACTIVE" in out["systemMessage"], "it does not name the answer"
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "SessionStart", hso
    assert hso["additionalContext"] == REMINDER, hso
    # ⚠ ...and off means silent on BOTH channels.
    _saved = os.environ.get(OPTION)
    os.environ[OPTION] = "false"
    try:
        assert _run_main().getvalue() == "", "off must print nothing"
    finally:
        if _saved is None:
            os.environ.pop(OPTION, None)
        else:
            os.environ[OPTION] = _saved
    print("selftest OK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())
