#!/usr/bin/env python3
"""A sub-agent the harness runs in the BACKGROUND, driven through the real hook process.

    python Tools/Debug/test_background_agent.py

⛔ WHY IT EXISTS. Claude Code 2.1.299 / 2.1.304 runs an `Agent` call in the background by
default: its PostToolUse arrives AT LAUNCH with
`{"isAsync": true, "status": "async_launched", "agentId": ...}`. Until 0.75.7 the gate read that
as "the agent returned". It freed the one-at-a-time slot at launch, and it reported the agent's
report file "never created" - 9 times out of 9 in one project on 2026-10-21, and on every
dispatch of this repository's own review that morning.
⇒ Every payload below has a measured shape: ADR and MEASUREMENTS.md in
Memory/tasks/20261021-094254-harness-background-agents/ (M1-M11).

⚠ It writes nothing outside its own temp tree. $CLAUDE_DISPATCH_DIR sends the state directory
into that tree, which is also what keeps the real log clean.
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
SID = "background-agent"


def fire(env, payload):
    """One hook process, one payload. Returns the WHOLE printed object, or None."""
    p = subprocess.run([sys.executable, GATE],
                       input=json.dumps(payload).encode("utf-8"),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    err = p.stderr.decode("utf-8", "replace").strip()
    assert not err, "the gate wrote to stderr: %s" % err
    out = p.stdout.decode("utf-8", "replace").strip()
    return json.loads(out) if out else None


def launched(agent_id, desc):
    """The PostToolUse tool_response of a background launch (M1)."""
    return {"isAsync": True, "status": "async_launched", "agentId": agent_id,
            "description": desc, "resolvedModel": "claude-haiku-5-5", "prompt": "...",
            "outputFile": "/tmp/tasks/%s.output" % agent_id, "canReadOutputFile": True,
            "canContinueAgent": True}


def main():
    work = tempfile.mkdtemp(prefix="dg-bg-")
    try:
        sdir = os.path.join(work, "state-root")
        state = os.path.join(sdir, "state")
        repo = os.path.join(work, "repo")
        os.makedirs(state)
        os.makedirs(os.path.join(repo, ".git"))     # a repo marker, so root resolves here
        task = os.path.join(repo, "Memory", "tasks", "20260101-000000-t")
        os.makedirs(task)
        env = dict(os.environ, CLAUDE_DISPATCH_DIR=sdir)
        base = {"session_id": SID, "cwd": repo}
        # ⛔ A FIXED, LOW USAGE READING, as in test_slot_lifecycle.py: without one the gate reads
        # the machine's real usage, and at PACE/STOP it would arm a real resume.
        now = time.time()
        with open(os.path.join(sdir, "token_usage.json"), "w", encoding="utf-8") as f:
            json.dump({"ts": int(now * 1000),
                       "five_hour": {"used_percentage": 5, "resets_at": int(now) + 3 * 3600}}, f)

        fire(env, dict(base, hook_event_name="SessionStart"))
        time.sleep(1.1)       # the plan must be provably newer than the session stamp
        with open(os.path.join(task, "prompts.md"), "w", encoding="utf-8") as f:
            f.write("# plan" + chr(10) + "## sub-task 1" + chr(10) + "the full prompt")
        for skill in ("dispatch-protocol", "unattended-work"):
            with open(os.path.join(state, "%s.skill-seen-%s" % (SID, skill)),
                      "w", encoding="utf-8") as f:
                f.write(skill)

        slot0 = os.path.join(state, "%s.slot0" % SID)
        slot1 = os.path.join(state, "%s.slot1" % SID)

        def sfile(suffix):
            return os.path.join(state, "%s.%s" % (SID, suffix))

        def report(n):
            return os.path.join(task, "agent-%02d-review.md" % n)

        def dispatch(tool_use_id, desc, n, env_=env, model=None):
            ti = {"subagent_type": "general-purpose", "description": desc,
                  "prompt": "Review the code. Write the report to %s" % report(n)}
            if model:
                ti["model"] = model
            got = fire(env_, dict(base, hook_event_name="PreToolUse", tool_name="Agent",
                                  tool_use_id=tool_use_id, tool_input=ti))
            return (got or {}).get("hookSpecificOutput", {})

        def post(tool_use_id, response):
            return fire(env, dict(base, hook_event_name="PostToolUse", tool_name="Agent",
                                  tool_use_id=tool_use_id, tool_response=response,
                                  tool_input={"subagent_type": "general-purpose"}))

        def stop(agent_id, also=(), text="done"):
            """SubagentStop as measured: background_tasks lists the agent itself, running."""
            bg = [{"id": agent_id, "type": "subagent", "status": "running"}]
            bg += [{"id": k, "type": "shell", "status": "running"} for k in also]
            out = fire(env, dict(base, hook_event_name="SubagentStop", agent_id=agent_id,
                                 agent_type="general-purpose", stop_hook_active=False,
                                 last_assistant_message=text, background_tasks=bg))
            # ⛔ On SubagentStop, `block` keeps the sub-agent running. Never, on any path.
            assert out is None or "decision" not in out, out
            return out

        def agent_event(agent_id, event="PreToolUse", tool="Read", response=None):
            p = dict(base, hook_event_name=event, tool_name=tool, agent_id=agent_id,
                     tool_use_id="toolu_%s_%s" % (agent_id, time.time()),
                     tool_input={"file_path": report(9)})
            if response is not None:
                p["tool_response"] = response
            return fire(env, p)

        def held(p=slot0):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except OSError:
                return None

        def age(p, minutes):
            t = time.time() - minutes * 60
            os.utime(p, (t, t))

        def gate_log():
            with open(os.path.join(sdir, "dispatch_gate.log"), encoding="utf-8") as f:
                return f.read()

        def progress():
            with open(os.path.join(task, "progress.md"), encoding="utf-8") as f:
                return f.read()

        # 1. THE LAUNCH: allowed, then PostToolUse says async_launched. The slot STAYS, marked,
        # with its pointer and the repository root (ADR D1).
        assert dispatch("toolu_BG1", "background review", 1) \
            .get("permissionDecision") == "allow"
        out = post("toolu_BG1", launched("aBG1", "background review"))
        assert held() is not None, "a background launch freed its slot AT LAUNCH (the 0.75.6 defect)"
        h = held()
        assert h.get("agent") == "aBG1" and h.get("asked") is False, h
        assert os.path.realpath(h.get("root", "")) == os.path.realpath(repo), h
        with open(sfile("bgslot-aBG1"), encoding="utf-8") as f:
            assert f.read().strip() == "0"
        ctx = ((out or {}).get("hookSpecificOutput") or {}).get("additionalContext", "")
        # 2. ... and NO false alarm: the report cannot exist yet. The model is told which file to
        # check itself when the agent finishes (ADR r2 N6).
        assert "never created" not in json.dumps(out), out
        assert "AGENT-FILE-MISSING" not in gate_log(), "the launch ran the missing-file check"
        assert "BACKGROUND" in ctx and "task-notification" in ctx and report(1) in ctx, out
        assert "runs in the background" in (out or {}).get("systemMessage", ""), out
        assert "LAUNCHED IN THE BACKGROUND by the harness (agent aBG1)" in progress()

        # 3. ONE AT A TIME STILL HOLDS while it runs, and the refusal names a background holder.
        second = dispatch("toolu_NEXT", "next review", 2)
        why = second.get("permissionDecisionReason", "")
        assert second.get("permissionDecision") == "deny", second
        assert "running in the BACKGROUND as agent aBG1" in why, why
        assert re.search(r"reclaimed automatically at \d\d:\d\d", why), why
        assert "wait for its task-notification" in why, why

        # 4. ITS OWN HOOKS KEEP THE SLOT ALIVE past slot_ttl_min (M4); another agent's do not.
        h = held()
        h["at"] = time.time() - 40 * 60
        with open(slot0, "w", encoding="utf-8") as f:
            json.dump(h, f)
        age(slot0, 31)
        agent_event("aOTHER")
        assert os.path.getmtime(slot0) < time.time() - 30 * 60, \
            "another agent's hook refreshed this agent's slot"
        agent_event("aBG1")
        assert os.path.getmtime(slot0) > time.time() - 60, \
            "the background agent's own hook did not refresh its slot"
        third = dispatch("toolu_NEXT2", "next review", 2)
        assert third.get("permissionDecision") == "deny", \
            "a LIVE background agent's slot was reclaimed by age: %r" % (third,)
        assert "(40 min ago)" in third.get("permissionDecisionReason", ""), third

        # 5. A STOP WITH ITS OWN BACKGROUND WORK RUNNING IS NOT THE FINISH (M10). The Bash child
        # is recorded from the agent's own PostToolUse; while it is `running` the slot stays.
        agent_event("aBG1", event="PostToolUse", tool="Bash",
                    response={"stdout": "", "stderr": "", "interrupted": False,
                              "backgroundTaskId": "bkid1"})
        assert os.path.exists(sfile("bgkid-aBG1-bkid1")), "the background child was not recorded"
        assert stop("aBG1", also=["bkid1"]) is None
        assert held() is not None, "an INTERIM stop released the slot"
        assert "BG-STOP-INTERIM agent=aBG1 waiting=bkid1" in gate_log()
        assert "WAITING on its own background work (bkid1)" in progress()
        assert "AGENT-FILE-MISSING" not in gate_log(), "an interim stop ran the file check"
        # ANOTHER AGENT'S STOP RELEASES NOTHING.
        assert stop("aOTHER") is None and held() is not None

        # 6. THE REAL FINISH (the child is gone): released, FINISHED row, and the missing report
        # goes to the screen - never as a `decision`.
        out = stop("aBG1", text="review finished")
        assert held() is None, "the final SubagentStop did not release the slot"
        assert report(1) in (out or {}).get("systemMessage", ""), out
        assert "AGENT-FILE-MISSING %s" % report(1) in gate_log()
        assert "RELEASE(background finished) agent=aBG1" in gate_log()
        assert "FINISHED in the background: review finished" in progress(), progress()
        assert not os.path.exists(sfile("bgslot-aBG1")), "the pointer outlived its slot"
        assert not os.path.exists(sfile("bgkid-aBG1-bkid1")), "a child record outlived its slot"
        assert stop("aBG1") is None, "a second stop for a released agent printed something"

        # 7. THE DETECTOR (ADR D4): a released agent active again is logged ONCE. (The second
        # stop above already consumed the marker the release wrote - re-arm it.)
        open(sfile("bgdone-aBG1"), "w").close()
        agent_event("aBG1")
        agent_event("aBG1")
        assert gate_log().count("BG-AGENT-ACTIVE-AFTER-RELEASE agent=aBG1") == 2, \
            "the detector did not log exactly once per marker"

        # 8. A NESTED BACKGROUND AGENT THAT IS ITSELF WAITING drops out of background_tasks
        # (M11); its own slot pointer still marks it running (ADR r2 N2). Then a report that
        # WAS written: released, nothing printed.
        assert dispatch("toolu_BG2", "second background review", 2) \
            .get("permissionDecision") == "allow"
        post("toolu_BG2", launched("aBG2", "second background review"))
        agent_event("aBG2", event="PostToolUse", tool="Agent",
                    response=launched("aNEST", "nested"))
        assert os.path.exists(sfile("bgkid-aBG2-aNEST"))
        open(sfile("bgslot-aNEST"), "w").write("5")
        assert stop("aBG2") is None
        assert held() is not None, "a stop with a nested agent still holding its slot released"
        os.remove(sfile("bgslot-aNEST"))
        with open(report(2), "w", encoding="utf-8") as f:
            f.write("report")
        assert stop("aBG2") is None
        assert held() is None
        assert "AGENT-FILE-OK n=1" in gate_log()

        # 9. FOREGROUND IS UNCHANGED (M5): its own events never touch its unmarked slot; its
        # SubagentStop comes FIRST and must not release; PostToolUse does, with the file check.
        assert dispatch("toolu_FG", "foreground review", 3).get("permissionDecision") == "allow"
        age(slot0, 5)
        agent_event("aFG")
        assert os.path.getmtime(slot0) < time.time() - 4 * 60, \
            "a FOREGROUND agent's own event touched its unmarked slot"
        assert stop("aFG") is None
        assert held() is not None, "a FOREGROUND agent's SubagentStop released its slot"
        out = post("toolu_FG", {"status": "completed", "agentId": "aFG",
                                "content": [{"type": "text", "text": "done"}]})
        assert held() is None, "PostToolUse did not release the foreground dispatch"
        assert "never created" in json.dumps(out), "the foreground missing-file check is gone"

        # 10. AN APPROVED OVER-PRICE ASK THAT WENT TO THE BACKGROUND keeps its slot: the next
        # parent-level dispatch must not release it as an "unresolved ask".
        env_ask = dict(env, CLAUDE_CODE_SESSION_ATTENDED="1")
        asked = dispatch("toolu_ASK", "price probe", 4, env_=env_ask, model="fable")
        assert asked.get("permissionDecision") == "ask", asked
        assert held().get("asked") is True, held()
        post("toolu_ASK", launched("aASK", "price probe"))
        h = held()
        assert h.get("asked") is False and h.get("agent") == "aASK", h
        h["at"] = time.time() - 30
        with open(slot0, "w", encoding="utf-8") as f:
            json.dump(h, f)
        later = dispatch("toolu_LATER", "later", 5, env_=env_ask, model="opus")
        assert later.get("permissionDecision") == "deny", \
            "a background ask was released as unresolved: %r" % (later,)
        assert "RELEASE(ask unresolved) id=toolu_ASK" not in gate_log()
        stop("aASK")
        assert held() is None, "SubagentStop did not release the background ask's slot"

        # 11. THE REWRITE FALLS BACK TO IN PLACE when its temp file cannot be written (ADR D1).
        os.makedirs(sfile("tmp-slot0"))
        assert dispatch("toolu_BG3", "third background review", 6) \
            .get("permissionDecision") == "allow"
        post("toolu_BG3", launched("aBG3", "third background review"))
        assert (held() or {}).get("agent") == "aBG3", "the in-place fallback did not mark the slot"
        os.rmdir(sfile("tmp-slot0"))

        # 12. A STALE POINTER IS CHECKED, NOT TRUSTED (ADR r2 N11): it names slot0, which aBG3
        # holds - aSTALE's stop must not free it.
        open(sfile("bgslot-aSTALE"), "w").write("0")
        assert stop("aSTALE") is None
        assert (held() or {}).get("agent") == "aBG3", "a stale pointer released another's slot"
        assert not os.path.exists(sfile("bgslot-aSTALE")), "the stale pointer was kept"
        stop("aBG3")
        assert held() is None

        # 13. A HOLDER OUTSIDE THE APPROVED RANGE STILL COUNTS (ADR r2 N12): a background agent
        # left in slot1 by an approval that expired. slot0 is free, N is 1 - refused.
        with open(slot1, "w", encoding="utf-8") as f:
            json.dump({"id": "toolu_HIGH", "desc": "high holder", "at": time.time(),
                       "agent": "aHIGH", "asked": False}, f)
        high = dispatch("toolu_AFTER", "after expiry", 7)
        assert high.get("permissionDecision") == "deny", \
            "a holder in slot1 was not counted under N=1: %r" % (high,)
        assert "slot1: high holder" in high.get("permissionDecisionReason", ""), high
        os.remove(slot1)

        # 14. A CRASH IN THE SUB-AGENT-EVENT HANDLING IS CONTAINED (ADR r2): it runs before every
        # branch of main(), and an escape would make the gate print nothing - an allow - and skip
        # the rest of the event. A child record whose path is a directory makes it raise; the
        # nested launch on the same event must still be handled.
        os.makedirs(sfile("bgkid-aX-aKID"))
        fire(env, dict(base, hook_event_name="PostToolUse", tool_name="Agent", agent_id="aX",
                       tool_use_id="toolu_NESTED", tool_response=launched("aKID", "kid"),
                       tool_input={"subagent_type": "general-purpose"}))
        log_now = gate_log()
        assert "BG-ACTIVITY-FAILED" in log_now, "the injected failure did not happen"
        assert "BG-LAUNCH(no slot held) agent=aKID id=toolu_NESTED" in log_now, \
            "a failure in the sub-agent-event handling took the rest of the event with it"
        os.rmdir(sfile("bgkid-aX-aKID"))

        # 15. THE HARNESS MUST ACTUALLY SEND THE EVENT.
        with open(repo_path("hooks", "hooks.json"), encoding="utf-8") as f:
            assert "SubagentStop" in json.load(f)["hooks"], \
                "hooks.json does not subscribe to SubagentStop"

        print("background agent OK")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
