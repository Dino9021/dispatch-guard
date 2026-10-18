#!/usr/bin/env python3
"""The Stop that ARMS an OS resume alarm asks the session, once, to schedule its own wake.

⛔ WHY. 2026-10-18 on the owner's Mac: a session's alarm was armed at Stop 00:41, its route-A
request (CronCreate for itself) went to the screen only, the session scheduled nothing, and the OS
alarm's relayed wake at 02:53 was never seen ("not yet read") - GAVE-UP 03:13, noticed at 05:38. A
sibling that HAD its own job woke at 02:51. ADR: Memory/tasks/20261018-161212-wake-held-and-route-a.

Drives the real dispatch_gate.on_stop with arm_from_handoff stubbed and NO resume record written -
the arming Stop runs before the detached arm writes one (ADR review B1).

    python Tools/Debug/test_route_a_stop.py     (or Tools/Debug/test_all.py for all of them)
"""

import contextlib
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import fresh_scratch, repo_path, scratch_dir   # noqa: E402

SID = "aaaa1111-2222-3333-4444-555566667777"


def main():
    fresh_scratch()
    os.environ["CLAUDE_DISPATCH_DIR"] = os.path.join(fresh_scratch(), "state-dir-for-the-log")
    sys.path.insert(0, repo_path("hooks"))
    import dispatch_gate as gate

    with scratch_dir("route-a-stop") as sdir:
        reset = time.time() + 3 * 3600
        ask = gate.route_a_line(sdir, None, {"at": reset + 180, "armed_for_reset": reset,
                                             "handoff": os.path.join(sdir, "HANDOFF.md")})
        assert ask.startswith(gate.ROUTE_A_LEAD), "route_a_line gave no wake sentence: %r" % ask
        cron = ask.split('with cron "')[1].split('"')[0]
        armed_line = " ⭐ dispatch-guard: a resume was ARMED for `t` (test)." + ask

        def stop(payload, line=armed_line, attended="1"):
            saved = gate.arm_from_handoff
            gate.arm_from_handoff = lambda *a, **k: line
            os.environ["CLAUDE_CODE_SESSION_ATTENDED"] = attended
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    gate.on_stop(dict({"hook_event_name": "Stop", "session_id": SID}, **payload),
                                 sdir, sdir, gate.gate_config(sdir, sdir))
            finally:
                gate.arm_from_handoff = saved
                os.environ.pop("CLAUDE_CODE_SESSION_ATTENDED", None)
            out = buf.getvalue().strip()
            assert out.count("\n") == 0, "more than one JSON object printed: %r" % out
            return json.loads(out) if out else None

        base = {"stop_hook_active": False, "session_crons": []}
        # it armed, a person is there, no wake job: ONE object, blocks, the reason carries the cron
        got = stop(base)
        assert got and got.get("decision") == "block" and cron in got.get("reason", ""), got
        assert "systemMessage" in got and gate.ROUTE_A_LEAD not in got["systemMessage"], got
        # nothing armed on this Stop (a later Stop for the same alarm): prints nothing at all
        assert stop(base, line=None) is None
        # the continued turn, a sub-agent, an older Claude Code, a headless session: no block
        for payload, attended in (({"stop_hook_active": True, "session_crons": []}, "1"),
                                  (dict(base, agent_id="a1"), "1"),
                                  ({"stop_hook_active": False}, "1"),
                                  (base, "0")):
            got = stop(payload, attended=attended)
            assert got and "decision" not in got, (payload, attended, got)
        # the same wake job already scheduled: no block; a wake job for ANOTHER time does not count
        same = {"id": "x", "schedule": cron, "recurring": False, "prompt": gate.WAKE_MARK + " ..."}
        assert "decision" not in stop(dict(base, session_crons=[same]))
        other = dict(same, schedule="0 0 1 1 *")
        assert stop(dict(base, session_crons=[other])).get("decision") == "block"
    print("ok - the Stop that arms blocks once for the in-session wake; never on a continued turn, "
          "a sub-agent, an older build, a headless run, or when the same wake job exists")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
