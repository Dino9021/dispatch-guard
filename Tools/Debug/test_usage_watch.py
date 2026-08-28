#!/usr/bin/env python3
"""What `usage.py --watch` puts on a screen, checked by running it.

⛔ WHY THIS IS A SEPARATE CHECK AND NOT A SELFTEST. The two defects it covers only exist in
the LOOP, and the loop never returns:

  1. An idle watcher redrew every tick. Each render was wider than the terminal, so it
     wrapped - and `\\r` returns to the start of the LAST VISUAL ROW while `\\033[K` clears
     only that row, so every render stranded its first row. Overnight that is a screen full
     of half-lines, which is how the owner reported it.
  2. The line itself was assembled in the loop, where `_line()` fitted only the middle and
     the timestamp and verdict word were added around it afterwards - sixteen columns nobody
     had subtracted.

⇒ (2) is pinned by usage.py's own selftest, on the pure function. (1) can only be seen by
running the loop and counting what comes out, which is what this does.

    python Tools/Debug/test_usage_watch.py     (or Tools/Debug/test_all.py for all of them)

Standard library only, no framework, like everything else here.
"""

import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import fresh_scratch, repo_path, scratch_dir   # noqa: E402

HERE = repo_path()
RUN_SECONDS = 6
# ⛔ A DRAW IS NOT A LINE. Since 0.33.0 the watcher spends a SECOND ROW when one will not
# hold everything, so "how many lines came out" answers the wrong question - and it answers
# it differently depending on how long the note happens to be, which made this check depend
# on whether an OAuth token was near expiry. Only the first row of a draw carries the clock.
DRAW = re.compile(r"^\d\d:\d\d:\d\d\s")


def _fixture(sdir, idle_minutes):
    """A state directory holding one usage record and a heartbeat of a chosen age."""
    os.makedirs(os.path.join(sdir, "state"), exist_ok=True)
    now = time.time()
    with open(os.path.join(sdir, "token_usage.json"), "w", encoding="utf-8") as f:
        json.dump({"ts": int(now * 1000),
                   "five_hour": {"used_percentage": 55, "resets_at": int(now) + 3000},
                   "seven_day": {"used_percentage": 32, "resets_at": int(now) + 300000}}, f)
    # ⭐ The heartbeat IS the idle clock: should_fetch() reads the newest state/*.alive.
    beat = os.path.join(sdir, "state", "fixture.alive")
    with open(beat, "w", encoding="utf-8") as f:
        f.write("x")
    old = now - idle_minutes * 60
    os.utime(beat, (old, old))
    with open(os.path.join(sdir, "config.json"), "w", encoding="utf-8") as f:
        # ⚠ Colour off so the assertions compare text rather than escape sequences, and a
        # FIXED width so "did it fit?" means the same thing wherever this runs.
        json.dump({"colour": False, "idle_after_min": 15, "width": 120}, f)


def _run(sdir):
    """`--watch --scroll` for a few seconds. Returns its lines.

    ⚠ --scroll, because the rewriting form puts everything on one line with carriage returns
    and "how many times did it draw?" is exactly the question. The decision under test is the
    same in both forms.
    """
    p = subprocess.Popen(
        [sys.executable, os.path.join(HERE, "hooks", "usage.py"), "--watch", "--scroll",
         # ⚠ `--every`, NOT `refresh_seconds`. That key belongs to the statusline; the
         # watcher reads this flag, defaults to 30 seconds and floors at 2 - so a check
         # written against refresh_seconds waits half a minute and then concludes that an
         # active watcher drew only once, which is the opposite of what it measured.
         "--every", "2", "--dir", sdir],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1"))
    try:
        out, err = p.communicate(timeout=RUN_SECONDS)
    except subprocess.TimeoutExpired:
        p.kill()
        out, err = p.communicate()
    text = (out or b"").decode("utf-8", "replace")
    return [l for l in text.splitlines() if l.strip()], (err or b"").decode("utf-8", "replace")


def draws(lines):
    """How many times it DREW, counting first rows rather than lines. See DRAW."""
    return [l for l in lines if DRAW.match(l)]


def case_idle_draws_once():
    """⛔ AN IDLE WATCHER DRAWS ONCE AND THEN STAYS SILENT."""
    with scratch_dir("idle-draws-once") as sdir:
        _fixture(sdir, idle_minutes=480)        # eight hours - well past idle_after_min
        lines, err = _run(sdir)
        assert lines, "the idle watcher printed nothing at all: %r" % err[:400]
        drew = draws(lines)
        assert len(drew) == 1, (
            "an idle watcher drew %d times in %d seconds - it must draw ONCE:%s%s"
            % (len(drew), RUN_SECONDS, chr(10), chr(10).join(lines[:6])))
        assert "SLEEP" in lines[0], lines[0]
        # ⭐ The figures are KEPT, not replaced by dashes. That was the owner's point: while
        # nobody is working nobody is spending, so the last number is still worth reading.
        assert "55%" in lines[0], "idle threw the percentage away: %r" % lines[0]
        # ...and no colour, which is what says the line is not live.
        assert "\033[" not in lines[0], "the idle line is coloured: %r" % lines[0]
        print("ok - idle draws one uncoloured SLEEP line, keeps the numbers, then stops")


def case_active_keeps_drawing():
    """⚠ THE CONTROL. Without it, "drew once" would also pass on a watcher that crashed
    after its first line - which is the same output and a completely different fault."""
    with scratch_dir("active-keeps-drawing") as sdir:
        _fixture(sdir, idle_minutes=0)          # a heartbeat from just now
        lines, err = _run(sdir)
        drew = draws(lines)
        assert len(drew) >= 3, (
            "an ACTIVE watcher drew only %d time(s) in %d seconds - so 'idle draws once' "
            "proves nothing:%s%s" % (len(drew), RUN_SECONDS, chr(10), err[:400]))
        assert "SLEEP" not in lines[0], lines[0]
        print("ok - an active watcher keeps drawing (%d draws), so the idle case means "
              "something" % len(drew))


def case_line_never_wraps():
    """⛔ AND NOTHING IT DRAWS MAY EXCEED THE TERMINAL. The stranded rows came from a line
    sixteen columns wider than the width `_line()` had been given."""
    with scratch_dir("line-fits") as sdir:
        _fixture(sdir, idle_minutes=0)
        lines, _err = _run(sdir)
        for line in lines:
            assert len(line) <= 120, (
                "a drawn line is %d columns against a width of 120 and WILL wrap: %r"
                % (len(line), line))
        print("ok - every drawn line fits the terminal (%d checked)" % len(lines))


def main():
    fresh_scratch()
    case_idle_draws_once()
    case_active_keeps_drawing()
    case_line_never_wraps()
    print("all watch checks passed")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
