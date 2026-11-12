#!/usr/bin/env python3
"""guard_wake_checkin (0.78.0) - a resumed session's first write is refused once until it re-checks-in.

    python Tools/Debug/test_wake_checkin.py

ADR: Memory/tasks/20261112-074900-wake-checkin-enforced/ADR.md (its "Tests" list is this file's list).
⭐ Driven through main(), like test_guards.py: the SessionStart resume writes the mark, and real Write /
Bash payloads meet the guard. A real git repository with one commit, so `git diff HEAD` works.
⚠ Nothing here touches ~/.claude, a network, or a scheduler.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import fresh_scratch, scratch_dir  # noqa: E402
from test_guards import (GIT_ID, bash, decision, file_tool, fixture_repo, git, gitlog,  # noqa: E402
                         load_gate, load_skills, reason, run_gate, stamp_session)

SID = "s1-0000-wake-checkin"


def resume(gate, root, sid=SID, source="resume", **extra):
    p = {"hook_event_name": "SessionStart", "source": source, "cwd": root, "session_id": sid}
    p.update(extra)
    return run_gate(gate, p)


def mark(gate, sdir, sid=SID):
    return gate.state_path(sdir, sid, "wake-checkin-due")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def main():
    fresh_scratch()
    with scratch_dir("state") as sdir, scratch_dir("repo") as root:
        fixture_repo(root)
        write(os.path.join(root, "Memory", "cowork", "WIN.md"), "# WIN board\n")
        write(os.path.join(root, "README.md"), "x\n")
        git(root, *GIT_ID, "add", ".")
        git(root, *GIT_ID, "commit", "-q", "-m", "init")
        gate = load_gate(sdir)
        import cmd_guards
        stamp_session(gate, sdir, SID)
        load_skills(gate, root, SID, "dispatch-guard:cowork")    # cowork used -> the wake note fires
        board = os.path.join(root, "Memory", "cowork", "WIN.md")

        # No mark: a write is allowed.
        assert decision(run_gate(gate, file_tool(root, "Write", os.path.join(root, "a.py"), sid=SID,
                                                 content="x"))) is None

        # E1: which wakes write the mark.
        os.environ["CLAUDE_CODE_SESSION_ATTENDED"] = "0"
        resume(gate, root)
        assert not os.path.exists(mark(gate, sdir)), "a headless resume wrote the mark"
        os.environ.pop("CLAUDE_CODE_SESSION_ATTENDED")
        for src in ("compact", "clear"):
            resume(gate, root, source=src)
            assert not os.path.exists(mark(gate, sdir)), src
        resume(gate, root, agent_id="sub-1")
        assert not os.path.exists(mark(gate, sdir)), "a sub-agent payload wrote the mark"
        other = "s9-no-cowork"
        stamp_session(gate, sdir, other)
        resume(gate, root, sid=other)       # no cowork use, but SID's heartbeat is a live peer here
        assert os.path.exists(mark(gate, sdir, other)), "a live peer: the mark is due"
        os.remove(mark(gate, sdir, other))
        with scratch_dir("lonely") as lonely:
            fixture_repo(lonely)
            resume(gate, lonely, sid=other)  # another repository: no peer there, no cowork use
            assert not os.path.exists(mark(gate, sdir, other)), "no peer, no cowork: no mark"
        resume(gate, root)
        assert os.path.exists(mark(gate, sdir)), "an attended resume with cowork used wrote no mark"

        # A sub-agent's write passes and leaves the mark.
        p = file_tool(root, "Write", os.path.join(root, "a.py"), sid=SID, content="x")
        p["agent_id"] = "sub-1"
        assert decision(run_gate(gate, p)) is None and os.path.exists(mark(gate, sdir))

        # A board Write WITH the id: allowed, mark cleared.
        r = run_gate(gate, file_tool(root, "Write", os.path.join(root, "Memory", "cowork", "X.md"), sid=SID,
                                     content="check-in: session %s\n" % SID))
        assert decision(r) is None and not os.path.exists(mark(gate, sdir)), r
        assert "WAKE-CHECKIN-DONE" in gitlog(root)

        # A board Write WITHOUT the id: refused once; the same call again is allowed.
        resume(gate, root)
        r = run_gate(gate, file_tool(root, "Write", board, sid=SID, content="0.77.0 published\n"))
        assert decision(r) == "deny" and SID in reason(r) and "retry this call" in reason(r), r
        assert decision(run_gate(gate, file_tool(root, "Write", board, sid=SID,
                                                 content="0.77.0 published\n"))) is None

        # A non-board write: refused once, then allowed.
        resume(gate, root)
        src = os.path.join(root, "src", "a.py")
        assert decision(run_gate(gate, file_tool(root, "Write", src, sid=SID, content="x"))) == "deny"
        assert decision(run_gate(gate, file_tool(root, "Write", src, sid=SID, content="x"))) is None

        # skills/ is excluded even with the id.
        resume(gate, root)
        sk = os.path.join(root, "skills", "cowork", "x.md")
        assert decision(run_gate(gate, file_tool(root, "Write", sk, sid=SID, content=SID))) == "deny"

        # R1-B1's exact shape: board appended in the working tree, not staged, then a chained commit.
        resume(gate, root)
        with open(board, "a", encoding="utf-8") as f:
            f.write("- Check-in: session %s\n" % SID)
        cmd = "printf x > msg && git add Memory/cowork/WIN.md && git commit -F msg"
        r = run_gate(gate, bash(root, cmd, sid=SID))
        assert decision(r) is None and not os.path.exists(mark(gate, sdir)), r
        git(root, *GIT_ID, "checkout", "--", "Memory/cowork/WIN.md")
        # ... an added board line without the id: refused once.
        resume(gate, root)
        with open(board, "a", encoding="utf-8") as f:
            f.write("- another session's note\n")
        assert decision(run_gate(gate, bash(root, cmd, sid=SID))) == "deny"
        assert decision(run_gate(gate, bash(root, cmd, sid=SID))) is None
        git(root, *GIT_ID, "checkout", "--", "Memory/cowork/WIN.md")
        # ... a staged check-in: allowed.
        resume(gate, root)
        with open(board, "a", encoding="utf-8") as f:
            f.write("- Check-in: session %s\n" % SID)
        git(root, "add", "Memory/cowork/WIN.md")
        assert decision(run_gate(gate, bash(root, "git commit -F msg", sid=SID))) is None
        git(root, "reset", "-q", "--", "Memory/cowork/WIN.md")
        git(root, *GIT_ID, "checkout", "--", "Memory/cowork/WIN.md")
        # ... a NEW untracked check-in file with the id: allowed.
        resume(gate, root)
        write(os.path.join(root, "Memory", "cowork", "checkin-new.md"), "session %s\n" % SID)
        assert decision(run_gate(gate, bash(root, cmd, sid=SID))) is None
        os.remove(os.path.join(root, "Memory", "cowork", "checkin-new.md"))

        # cowork_checkin_dir narrows the path rule.
        cfgfile = os.path.join(root, ".claude", "dispatch-guard.json")
        write(cfgfile, '{"dispatch": {"cowork_checkin_dir": "board"}}')
        try:
            resume(gate, root)
            assert decision(run_gate(gate, file_tool(root, "Write", board, sid=SID, content=SID))) == "deny"
            resume(gate, root)
            assert decision(run_gate(gate, file_tool(root, "Write", os.path.join(root, "board", "R.md"),
                                                     sid=SID, content=SID))) is None
        finally:
            os.remove(cfgfile)

        # Switch off: no refusal, logged, mark kept.
        write(cfgfile, '{"dispatch": {"guard_wake_checkin": false}}')
        try:
            resume(gate, root)
            assert decision(run_gate(gate, file_tool(root, "Write", src, sid=SID, content="x"))) is None
            assert "CMD-DISABLED(guard_wake_checkin)" in gitlog(root)
            assert os.path.exists(mark(gate, sdir)), "a disabled guard touched the mark"
        finally:
            os.remove(cfgfile)

        # Unstamped: advisory.
        un = "s8-unstamped"
        os.makedirs(os.path.dirname(mark(gate, sdir, un)), exist_ok=True)
        write(mark(gate, sdir, un), "resumed")
        assert decision(run_gate(gate, file_tool(root, "Write", src, sid=un, content="x"))) is None

        # Fail open: a raising guard allows.
        keep, fkeep = cmd_guards.GUARDS, cmd_guards.FILE_GUARDS
        boom = lambda *a: 1 / 0  # noqa: E731
        cmd_guards.FILE_GUARDS = tuple((k, boom if k == "guard_wake_checkin" else f) for k, f in fkeep)
        try:
            assert decision(run_gate(gate, file_tool(root, "Write", src, sid=SID, content="x"))) is None
        finally:
            cmd_guards.FILE_GUARDS = fkeep

        # Mutation: without the rows the refused cases pass.
        resume(gate, root)
        cmd_guards.FILE_GUARDS = tuple(g for g in fkeep if g[0] != "guard_wake_checkin")
        cmd_guards.GUARDS = tuple(g for g in keep if g[0] != "guard_wake_checkin")
        try:
            assert decision(run_gate(gate, file_tool(root, "Write", src, sid=SID, content="x"))) is None
            assert decision(run_gate(gate, bash(root, "git commit -F msg", sid=SID))) is None
        finally:
            cmd_guards.GUARDS, cmd_guards.FILE_GUARDS = keep, fkeep
        names = [k for k, _ in cmd_guards.GUARDS]
        assert names.index("guard_cowork_first") < names.index("guard_wake_checkin") \
            < names.index("guard_relative_cd"), names

    print("ok - wake check-in: marks only at attended resumes, check-in by session id (file tool, "
          "chained commit, staged, untracked), refuse once, checkin dir, skills excluded, switch, "
          "unstamped, fail-open, mutation, order")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
