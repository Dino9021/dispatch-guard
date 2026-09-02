#!/usr/bin/env python3
"""The concurrency slot's whole life, driven through the REAL hook process.

    python Tools/Debug/test_slot_lifecycle.py

⛔ WHY A SECOND CHECK WHEN `--selftest` ALREADY CALLS claim_slot(). Because the defect this
exists for was never in claim_slot. It was in the WIRING: a dispatch that fails fires
`PostToolUseFailure`, and the plugin only ever registered `PostToolUse`, so a failed dispatch
kept its slot for the full `slot_ttl_min` and every later dispatch was refused. Measured
2026-09-02 on another machine: a session read the refusal as a broken gate and deleted the
plugin's own state file by hand. Every function involved passed its own unit check that day.

⇒ This runs `dispatch_gate.py` as a subprocess, the way the harness does, and asserts the
sequence a person would see: allow, held, refused BY NAME, released on failure, allow again.

⚠ It writes nothing outside its own temp tree. $CLAUDE_DISPATCH_DIR sends the state
directory into that tree, which is also what keeps the real log clean.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import repo_path  # noqa: E402

GATE = repo_path("hooks", "dispatch_gate.py")
SID = "slot-lifecycle"


def fire(env, payload):
    """One hook process, one payload. Returns the parsed decision or None."""
    p = subprocess.run([sys.executable, GATE],
                       input=json.dumps(payload).encode("utf-8"),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    err = p.stderr.decode("utf-8", "replace").strip()
    assert not err, "the gate wrote to stderr: %s" % err
    out = p.stdout.decode("utf-8", "replace").strip()
    if not out:
        return None
    return json.loads(out).get("hookSpecificOutput", {})


def main():
    work = tempfile.mkdtemp(prefix="dg-slots-")
    try:
        sdir = os.path.join(work, "state-root")
        repo = os.path.join(work, "repo")
        os.makedirs(os.path.join(sdir, "state"))
        os.makedirs(os.path.join(repo, ".git"))     # a repo marker, so root resolves here
        task = os.path.join(repo, "Memory", "tasks", "20260101-000000-t")
        os.makedirs(task)
        env = dict(os.environ, CLAUDE_DISPATCH_DIR=sdir)
        base = {"session_id": SID, "cwd": repo}

        fire(env, dict(base, hook_event_name="SessionStart"))
        # ⚠ AFTER the session stamp, and a second later: the plan check compares mtimes, and
        # a plan written in the same second as the stamp is not provably newer than it.
        time.sleep(1.1)
        with open(os.path.join(task, "prompts.md"), "w", encoding="utf-8") as f:
            f.write("# plan" + chr(10) + "## sub-task 1" + chr(10) + "the full prompt")
        for skill in ("dispatch-protocol", "unattended-work"):
            with open(os.path.join(sdir, "state", "%s.skill-seen-%s" % (SID, skill)),
                      "w", encoding="utf-8") as f:
                f.write(skill)

        def dispatch(tool_use_id, desc):
            return fire(env, dict(base, hook_event_name="PreToolUse", tool_name="Agent",
                                  tool_use_id=tool_use_id,
                                  tool_input={"subagent_type": "general-purpose",
                                              "description": desc,
                                              "prompt": "Work in %s and report." % task}))

        slot0 = os.path.join(sdir, "state", "%s.slot0" % SID)
        first = dispatch("toolu_FIRST", "round 1 adversarial review")
        assert first.get("permissionDecision") == "allow", first
        assert os.path.exists(slot0), "the allowed dispatch claimed no slot"

        # ⛔ THE REFUSAL MUST NAME THE HOLDER AND ITS CLOCK. Without both, a session whose
        # dispatch died cannot tell this from a permanently broken gate - and the repair it
        # invents is to delete the file this check just found.
        second = dispatch("toolu_SECOND", "round 2 review")
        assert second.get("permissionDecision") == "deny", second
        why = second.get("permissionDecisionReason", "")
        assert "round 1 adversarial review" in why, why
        assert re.search(r"reclaimed automatically at \d\d:\d\d", why), why
        assert "Do NOT delete a slot file" in why, why

        # ⛔ THE EVENT THE PLUGIN USED TO MISS. A failed dispatch fires PostToolUseFailure,
        # never PostToolUse. Measured against Claude Code 2.1.251: same tool_use_id, and no
        # PostToolUse at all.
        fire(env, dict(base, hook_event_name="PostToolUseFailure", tool_name="Agent",
                       tool_use_id="toolu_FIRST", error="API Error: 529 Overloaded",
                       is_interrupt=False,
                       tool_input={"subagent_type": "general-purpose"}))
        assert not os.path.exists(slot0), \
            "a failed dispatch still holds its slot - PostToolUseFailure is not wired"

        third = dispatch("toolu_THIRD", "round 2 review, retried")
        assert third.get("permissionDecision") == "allow", third

        # ⚠ AND THE HARNESS MUST ACTUALLY SEND THAT EVENT. main() handling it is half the
        # fix; hooks.json subscribing to it is the half that delivers it.
        with open(repo_path("hooks", "hooks.json"), encoding="utf-8") as f:
            assert "PostToolUseFailure" in json.load(f)["hooks"], \
                "hooks.json does not subscribe to PostToolUseFailure"

        print("slot lifecycle OK")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
