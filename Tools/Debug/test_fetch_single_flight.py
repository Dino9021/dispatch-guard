#!/usr/bin/env python3
"""One usage fetch per machine, however many processes ask at the same instant (0.75.16).

    python Tools/Debug/test_fetch_single_flight.py

⛔ WHY IT EXISTS. Every VS Code window runs its own `usage.py --watch`, and every session's hook
can fork a refresh. They share one state directory, and _claim_attempt() is what lets only one
of them spend a call. Before 0.75.16 it read the last claim and wrote the new one as two steps,
so processes arriving together all passed: measured 2026-11-01, 42 of the 96 seconds that logged
a 429 had 2-3 requests in the same second.

⇒ Many processes, released at one instant, call _claim_attempt() on one state directory; exactly
one may be told to fetch, round after round. Then the lock's two edge cases: a fresh lock held by
someone else refuses, and a dead one (older than FETCH_LOCK_STALE_SECONDS) is cleared.
⚠ No network: _claim_attempt() only decides, it never fetches. Nothing outside a temp dir is touched.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import repo_path  # noqa: E402

HOOKS = repo_path("hooks")
WORKERS = 16
ROUNDS = 5
WORKER = ("import sys, time; sys.path.insert(0, sys.argv[1]); import usage; "
          "start = float(sys.argv[3])\n"
          "while time.time() < start: pass\n"
          "print(int(bool(usage._claim_attempt(sys.argv[2], 120))))")


def main():
    sys.path.insert(0, HOOKS)
    import usage
    sdir = tempfile.mkdtemp(prefix="dg-single-flight-")
    try:
        for n in range(ROUNDS):
            for name in ("fetch.claim", "fetch.429", "fetch.lock"):
                try:
                    os.remove(os.path.join(sdir, name))
                except OSError:
                    pass
            start = time.time() + 1.5            # every worker is started and spinning by then
            procs = [subprocess.Popen([sys.executable, "-c", WORKER, HOOKS, sdir, repr(start)],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for _ in range(WORKERS)]
            outs = [p.communicate(timeout=60) for p in procs]
            errs = [e.decode("utf-8", "replace").strip() for _o, e in outs if e.strip()]
            assert not errs, "a worker failed: %s" % errs[0]
            granted = sum(int(o.decode().strip() or 0) for o, _e in outs)
            assert granted == 1, "round %d: %d of %d processes were told to fetch" % (n, granted, WORKERS)
            assert not os.path.exists(os.path.join(sdir, "fetch.lock")), "the lock outlived its holder"

        # A lock someone else holds right now: refuse, and claim nothing.
        os.remove(os.path.join(sdir, "fetch.claim"))
        open(os.path.join(sdir, "fetch.lock"), "w").close()
        assert usage._claim_attempt(sdir, 120) is False, "claimed past a live lock"
        assert not os.path.exists(os.path.join(sdir, "fetch.claim")), "wrote a claim past a live lock"

        # A lock whose holder died: cleared, and the claim goes through.
        old = time.time() - usage.FETCH_LOCK_STALE_SECONDS - 5
        os.utime(os.path.join(sdir, "fetch.lock"), (old, old))
        assert usage._claim_attempt(sdir, 120) is True, "a dead lock blocked the fetch for good"
        assert not os.path.exists(os.path.join(sdir, "fetch.lock")), "the dead lock was not cleared"
        assert os.path.exists(os.path.join(sdir, "fetch.claim")), "no claim after clearing the dead lock"
    finally:
        shutil.rmtree(sdir, ignore_errors=True)
    print("ok - %d rounds x %d processes: exactly one fetch each; live lock refuses, dead lock clears"
          % (ROUNDS, WORKERS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
