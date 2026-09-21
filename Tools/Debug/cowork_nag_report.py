#!/usr/bin/env python3
"""Every firing of `guard_cowork_first`, with what it saw and what happened next.

    python Tools/Debug/cowork_nag_report.py            # the real state-directory log
    python Tools/Debug/cowork_nag_report.py <log>      # any gate log
    python Tools/Debug/cowork_nag_report.py --selftest

⭐ WHY THIS EXISTS. The nag refuses one write per session when another session is live in the
same repository. Its first real firing (2026-09-21) counted a peer that was most likely the
ghost of the same session before a restart - a `.alive` file nobody clears. The owner ruled:
collect data first, decide later - and the owner works in other projects most days, so the
collection has to happen without anybody watching. The gate already writes everything needed
into the authoritative log (`~/.claude/dispatch-guard/dispatch_gate.log`): since 0.63.2 a
`COWORK-PEERS sid=… mine=…` line right before each `CMD-DENY(guard_cowork_first)`, and a
`SKILL-SEEN … sid=…` line when the skill is then invoked. This script only reads them back.

Two questions per firing, and the answers decide two open items:
  GHOST?    a peer whose heartbeat is OLDER than this session's age has not moved since this
            session began - the shape of a session that exited before this one started
            (ADR R2: tighten the peer test if the nag fires with no real peer)
  LOADED?   was `cowork` invoked BY THE SAME SESSION within the next few minutes of the refusal
            (ADR R5: promote the nag to repeat-until-loaded if fewer than half do)

⛔ PAIRED BY SESSION ID, NOT BY TIME. The state log is one file for every session on the
machine; review 01 measured two firings a second apart and one skill load read as "2/2 loaded"
when the pairing was by time alone. Lines without a sid (pre-0.63.2) fall back to the time
window and the row says so.

exit 0 always for a report; --selftest exits 1 on a wrong answer.
"""
import io
import os
import re
import sys
import time

out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
VERSION = "v1.1"
LOADED_WITHIN_S = 300

_STAMP = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) (.*)$")
_PEERS = re.compile(r"^COWORK-PEERS (?:sid=(\S+) )?mine=(-?\d+)s ?(.*)$")
_PEER = re.compile(r"^([^:\s]+):alive=(-?\d+)s,start=(-?\d+)s$")
_SEEN = re.compile(r"^SKILL-SEEN (\S+)(?: sid=(\S+))?")


def _epoch(stamp):
    return time.mktime(time.strptime(stamp, "%Y-%m-%d %H:%M:%S"))


def _is_cowork(skill_name):
    """The skill NAMED cowork, under any spelling - `cowork`, `dispatch-guard:cowork`,
    `x/cowork` - and not `my-coworker-skill`."""
    bare = skill_name.strip().lower().replace("\\", "/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    return bare == "cowork"


def firings(lines):
    """[(stamp, sid, mine_s, peers, unparsed_tokens, loaded)] where
    peers = [(sid8, alive_s, start_s, ghost)] with ghost in (True, False, None=unknown),
    loaded = (seconds, how) with how in ("sid", "time") or None."""
    recs = []
    for line in lines:
        m = _STAMP.match(line.rstrip("\r\n"))
        if m:
            recs.append((m.group(1), m.group(2)))
    rows = []
    for i, (stamp, msg) in enumerate(recs):
        pm = _PEERS.match(msg)
        if not pm:
            continue
        sid, mine = pm.group(1), int(pm.group(2))
        if sid == "?":
            sid = None                        # the gate's "no id" spelling: pair by time, never by "?"
        peers, unparsed = [], 0
        for tok in pm.group(3).split():
            t = _PEER.match(tok)
            if not t:
                unparsed += 1
                continue
            psid, alive, start = t.group(1), int(t.group(2)), int(t.group(3))
            ghost = None if mine < 0 else (alive > mine)
            peers.append((psid, alive, start, ghost))
        t0 = _epoch(stamp)
        loaded = None
        for stamp2, msg2 in recs[i + 1:]:
            dt = _epoch(stamp2) - t0
            if dt > LOADED_WITHIN_S:
                break
            sm = _SEEN.match(msg2)
            if not sm or not _is_cowork(sm.group(1)):
                continue
            sid2 = None if sm.group(2) == "?" else sm.group(2)
            if sid and sid2:
                if sid2 == sid:
                    loaded = (int(dt), "sid")
                    break
                continue                      # another session's load: not ours
            loaded = (int(dt), "time")        # pre-0.63.2 line(s): time is all there is
            break
        rows.append((stamp, sid, mine, peers, unparsed, loaded))
    return rows


def report(lines, source):
    rows = firings(lines)
    print("  cowork_nag_report %s   %d firing(s)   source %s" % (VERSION, len(rows), source), file=out)
    print("  GHOST = the peer's heartbeat is older than this session (it has not moved since "
          "this session began); ? = this session's own age unknown", file=out)
    print("  LOADED = `cowork` invoked by the SAME session within %d s of the refusal; "
          "(by time) = a pre-0.63.2 line without a sid, paired by time only" % LOADED_WITHIN_S,
          file=out)
    if not rows:
        print("  nothing to report: no COWORK-PEERS line in this log (0.63.2 writes one per firing)",
              file=out)
        out.flush()
        return
    ghosts_only = judged = loaded_n = 0
    for stamp, sid, mine, peers, unparsed, loaded in rows:
        def mark(g):
            return " GHOST" if g is True else (" ?" if g is None else "")
        desc = ", ".join("%s alive %ds%s" % (p, a, mark(g)) for p, a, _s, g in peers) or "(no peer parsed)"
        if unparsed:
            desc += "  (%d token(s) not parsed)" % unparsed
        if peers and all(g is not None for _p, _a, _s, g in peers):
            judged += 1
            ghosts_only += all(g for _p, _a, _s, g in peers)
        loaded_n += loaded is not None
        how = "" if loaded is None else (" (by time)" if loaded[1] == "time" else "")
        print("  %s  sid %-8s  mine %5ds  peers: %s  ->  %s" % (
            stamp, sid or "?", mine, desc,
            "LOADED after %ds%s" % (loaded[0], how) if loaded is not None else "not loaded"),
            file=out)
    print("  summary: %d/%d judged firings saw ONLY ghosts (R2; %d firing(s) unjudged - own age "
          "unknown or no peer parsed);  %d/%d were followed by the skill (R5)"
          % (ghosts_only, judged, len(rows) - judged, loaded_n, len(rows)), file=out)
    print("  scope: firings are read from COWORK-PEERS lines only; a DENY without one (pre-0.63.2) "
          "is not counted", file=out)
    out.flush()


def selftest():
    lines = [
        # 1: a ghost peer, the same session loads 23 s later
        "2026-09-21 16:44:03 COWORK-PEERS sid=ccb45ef4 mine=120s 9aee7131:alive=554s,start=9000s",
        "2026-09-21 16:44:03 CMD-DENY(guard_cowork_first) Edit x.md",
        "2026-09-21 16:44:26 SKILL-SEEN dispatch-guard:cowork sid=ccb45ef4",
        # 2 and 3: two sessions fire a second apart; ONE of them loads - by sid, only one is LOADED
        "2026-09-21 17:00:00 COWORK-PEERS sid=aaaa0001 mine=3600s bbbb0002:alive=20s,start=7200s",
        "2026-09-21 17:00:00 CMD-DENY(guard_cowork_first) Write y.md",
        "2026-09-21 17:00:01 COWORK-PEERS sid=bbbb0002 mine=7200s aaaa0001:alive=1s,start=3600s",
        "2026-09-21 17:00:01 CMD-DENY(guard_cowork_first) Write z.md",
        "2026-09-21 17:00:27 SKILL-SEEN cowork sid=bbbb0002",
        # 4: a look-alike skill name must not count
        "2026-09-21 17:10:00 COWORK-PEERS sid=cccc0003 mine=50s dddd0004:alive=10s,start=99s",
        "2026-09-21 17:10:07 SKILL-SEEN my-coworker-skill sid=cccc0003",
        # 5: own age unknown -> ghost unjudged; a non-hex peer id parses; pre-0.63.2 lines by time
        "2026-09-21 17:20:00 COWORK-PEERS mine=-1s s-nonhex-peer:alive=30s,start=100s",
        "2026-09-21 17:20:10 SKILL-SEEN dispatch-guard:cowork",
        # 6: across midnight
        "2026-09-21 23:59:50 COWORK-PEERS sid=eeee0005 mine=10s ffff0006:alive=5s,start=8s",
        "2026-09-22 00:00:10 SKILL-SEEN cowork sid=eeee0005",
        "junk line without a stamp",
        # 7: the gate's "?" is NOT an id - two "?" sessions must not pair with each other by it
        "2026-09-22 01:00:00 COWORK-PEERS sid=? mine=5s gggg0007:alive=1s,start=2s",
        "2026-09-22 01:00:05 SKILL-SEEN cowork sid=?",
    ]
    rows = firings(lines)
    assert len(rows) == 7, len(rows)
    assert rows[6][1] is None and rows[6][5] == (5, "time"), rows[6]
    assert rows[0][1] == "ccb45ef4" and rows[0][3] == [("9aee7131", 554, 9000, True)], rows[0]
    assert rows[0][5] == (23, "sid"), rows[0][5]
    assert rows[1][5] is None, "session aaaa0001 never loaded, but was credited: %r" % (rows[1][5],)
    assert rows[2][5] == (26, "sid"), rows[2][5]
    assert rows[3][5] is None, "a look-alike skill name was counted: %r" % (rows[3][5],)
    assert rows[4][1] is None and rows[4][3] == [("s-nonhex-peer", 30, 100, None)], rows[4]
    assert rows[4][5] == (10, "time"), rows[4][5]
    assert rows[5][5] == (20, "sid"), rows[5][5]
    # controls: an empty log and a DENY without a PEERS line report zero firings
    assert firings([]) == []
    assert firings(["2026-09-21 16:44:03 CMD-DENY(guard_cowork_first) Edit x.md"]) == []
    report(lines, "selftest fixture")
    print("ok - cowork_nag_report: seven firings parsed; LOADED paired by sid (two sessions a second "
          "apart -> one credited), look-alike skill ignored, unknown own age unjudged, midnight "
          "and non-hex ids parse, '?' is not an id, controls hold", file=out)
    out.flush()
    return 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    if len(argv) > 1 and not argv[1].startswith("--"):
        path = argv[1]
    else:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), "hooks"))
        import usage
        path = os.path.join(usage.state_dir([]), "dispatch_gate.log")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as exc:
        print("  cannot read %s: %s" % (path, exc), file=out)
        out.flush()
        return 0
    report(lines, path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
