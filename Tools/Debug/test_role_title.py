#!/usr/bin/env python3
"""Naming a cowork session after its role (0.77.0, hooks/role_title.py).

    python Tools/Debug/test_role_title.py

ADR: Memory/tasks/20261111-213912-auto-role-identity/ADR.md (rev 4). Cases: off without both keys; role
found by session id; title returned only when it differs; SessionStart only on resume; ambiguity;
D5 line; bad names; collision guard (live vs dead holder, unreadable registry); headless; and one end
to end run of the hook as Claude Code runs it.
⚠ Uses fixture directories and a fixture registry only; never ~/.claude.
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import fresh_scratch, repo_path, scratch_dir  # noqa: E402

sys.path.insert(0, repo_path("hooks"))
import role_title as rt  # noqa: E402

SID = "11111111-2222-3333-4444-555555555555"
CFG = {"cowork_checkin_dir": "Memory/checkin", "cowork_name_format": "Game-{role}"}
DEAD_PID = 999999


def repo_with(d, files):
    cdir = os.path.join(d, "Memory", "checkin")
    os.makedirs(cdir, exist_ok=True)
    for name, text in files.items():
        with open(os.path.join(cdir, name), "w", encoding="utf-8") as f:
            f.write(text)
    return d


def registry(d, entries):
    reg = os.path.join(d, "cfg")
    os.makedirs(os.path.join(reg, "sessions"), exist_ok=True)
    for i, e in enumerate(entries):
        with open(os.path.join(reg, "sessions", "%d.json" % i), "w", encoding="utf-8") as f:
            json.dump(e, f)
    return reg


def ups(title=None, sid=SID):
    p = {"hook_event_name": "UserPromptSubmit", "session_id": sid}
    if title is not None:
        p["session_title"] = title
    return p


def start(source, title=None):
    p = {"hook_event_name": "SessionStart", "session_id": SID, "source": source}
    if title is not None:
        p["session_title"] = title
    return p


def main():
    fresh_scratch()
    n = 0
    with scratch_dir("decide") as d:
        root = repo_with(d, {"G1.md": "- session id: `%s`\n" % SID, "G2.md": "- session id: `other`\n"})
        reg = registry(d, [{"sessionId": "zzz", "name": "Game-G2", "pid": os.getpid()}])
        t = lambda p, cfg=CFG, att=True, r=reg: rt.decide(p, root, cfg, attended=att, config_dir=r)

        # off unless both keys, and only when the format names {role}
        for cfg in ({}, {"cowork_checkin_dir": "Memory/checkin"}, {"cowork_name_format": "Game-{role}"},
                    {"cowork_checkin_dir": "Memory/checkin", "cowork_name_format": "Game"}):
            assert t(ups("x"), cfg) == (None, "", None), cfg
        n += 1
        # UPS: differs -> set; equal -> nothing at all
        title, line, _ = t(ups("title-probe-c2"))
        assert title == "Game-G1" and "role G1" in line, (title, line)
        assert t(ups("Game-G1")) == (None, "", None)
        assert t(ups())[0] == "Game-G1", "an absent title differs"
        n += 1
        # SessionStart: resume sets when differing; startup never sets; compact/clear say nothing
        assert t(start("resume", "Old-Name"))[0] == "Game-G1"
        title, line, _ = t(start("resume", "Game-G1"))
        assert title is None and "its name is Game-G1" in line
        assert t(start("startup"))[0] is None and "role G1" in t(start("startup"))[1]
        assert t(start("compact", "x")) == (None, "", None) and t(start("clear", "x")) == (None, "", None)
        n += 1
        # headless: nothing, ever
        assert t(ups("x"), att=False) == (None, "", None) and t(start("resume", "x"), att=False) == (None, "", None)
        n += 1
        # no check-in: D5 at SessionStart only
        title, line, _ = t(start("startup", None) | {"session_id": "nobody"})
        assert title is None and "no cowork check-in" in line and "nobody" in line, line
        assert t(ups("x", sid="nobody")) == (None, "", None)
        n += 1
        # collision: a live holder blocks; a dead one does not; own entry ignored; unreadable fails closed
        reg2 = registry(os.path.join(d, "r2"), [{"sessionId": "zzz", "name": "Game-G1", "pid": os.getpid()}])
        title, line, once = t(ups("x"), r=reg2)
        assert title is None and "already holds the name Game-G1" in line and once == "role-taken", line
        reg3 = registry(os.path.join(d, "r3"), [{"sessionId": "zzz", "name": "Game-G1", "pid": DEAD_PID},
                                                {"sessionId": SID, "name": "Game-G1", "pid": os.getpid()}])
        assert t(ups("x"), r=reg3)[0] == "Game-G1", "a dead holder or this session's own entry must not block"
        title, line, once = t(ups("x"), r=os.path.join(d, "missing"))
        assert title is None and "could not be read" in line and once == "role-noregistry"
        n += 1
    with scratch_dir("ambiguous") as d:
        root = repo_with(d, {"G1.md": SID, "G3.md": "previous holder " + SID, "bad role.md": "x"})
        title, line, _ = rt.decide(ups("x"), root, CFG, config_dir=registry(d, []))
        assert title is None and "G1.md" in line and "G3.md" in line, line
        assert rt.find_role(os.path.join(root, "Memory", "checkin"), SID) == ("", ["G1.md", "G3.md"])
        root2 = repo_with(os.path.join(d, "b"), {"bad role.md": SID})
        title, line, _ = rt.decide(ups("x"), root2, CFG, config_dir=registry(d, []))
        assert title is None and "letters, digits" in line, line
        n += 1
    with scratch_dir("end-to-end") as d:
        root = repo_with(d, {"G1.md": SID})
        os.makedirs(os.path.join(root, ".claude"), exist_ok=True)
        with open(os.path.join(root, ".claude", "dispatch-guard.json"), "w", encoding="utf-8") as f:
            json.dump(CFG, f)
        open(os.path.join(root, ".git"), "w").close()        # a repo marker for repo_root()
        env = dict(os.environ, CLAUDE_CONFIG_DIR=registry(d, []), CLAUDE_CODE_SESSION_ATTENDED="1",
                   CLAUDE_DISPATCH_DIR=os.path.join(d, "state"))
        payload = dict(ups("title-probe-c2"), cwd=root)
        r = subprocess.run([sys.executable, repo_path("hooks", "role_title.py")], input=json.dumps(payload),
                           capture_output=True, text=True, env=env, timeout=60)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)["hookSpecificOutput"]
        assert out == {"hookEventName": "UserPromptSubmit", "sessionTitle": "Game-G1",
                       "additionalContext": out.get("additionalContext")} and "role G1" in out["additionalContext"], out
        payload = dict(ups("Game-G1"), cwd=root)
        r = subprocess.run([sys.executable, repo_path("hooks", "role_title.py")], input=json.dumps(payload),
                           capture_output=True, text=True, env=env, timeout=60)
        assert r.returncode == 0 and r.stdout.strip() == "", "an equal title must print nothing: %r" % r.stdout
        n += 1
    print("role title: %d groups passed" % n)


if __name__ == "__main__":
    main()
