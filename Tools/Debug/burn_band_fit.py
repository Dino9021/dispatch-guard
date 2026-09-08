"""Are the burn gauge's colour bands still calibrated? Measure, do not guess.

⭐ WHY THIS LIVES HERE AND NOT IN A TASK FOLDER. The ADR that chose the bands
(Memory/tasks/20260829-133237-burn-two-signals/) carries a reconsideration criterion - "after
a week of history, re-run the fit and reopen if red is over ~15% or has fallen to 0%". Its
first draft named a script inside that task folder, and the protocol archives a task folder as
a unit. ⛔ A reconsideration criterion that cannot be executed is not a criterion. So the
fitter ships beside the code it judges.

⭐ AND IT READS THE CONFIGURED EDGES, not a copy of them. A fitter that hard-coded 1.00 /
1.75 / 2.25 would report on a calibration the reader may no longer be running.

Usage:  python Tools/Debug/burn_band_fit.py [--dir <state dir>]

Reports, over every five-hour window in the local history:
  - the rate distribution, and the instrument's step
  - what share of live time each colour occupies under the CONFIGURED edges
  - the same under the alternatives the ADR recorded, for comparison
  - the closest achievable fit to the owner's target split
"""
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
USAGE = os.path.join(REPO, "hooks", "usage.py")
if not os.path.isfile(USAGE):                      # running from a checkout laid out oddly
    USAGE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "hooks", "usage.py")

spec = importlib.util.spec_from_file_location("_bbf_usage", USAGE)
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)

argv = sys.argv[1:]
SDIR = u.state_dir(argv)
CFG = u.config(SDIR)
LOGS = u.history_dir(SDIR, CFG)

# ⛔ THE OWNER'S TARGET, RECORDED SO THE COMPARISON MEANS SOMETHING. They did not pick edges,
# they picked shares and asked for the multiples that produce them.
TARGET = {"green": 50, "yellow": 25, "orange": 15, "red": 10}

rows = []
if os.path.isdir(LOGS):
    for name in sorted(os.listdir(LOGS)):
        if name.startswith(u.HISTORY_PREFIX) and name.endswith(".jsonl"):
            for line in io.open(os.path.join(LOGS, name), encoding="utf-8"):
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        continue
if not rows:
    print("no history under %s - nothing to measure." % LOGS)
    print("debug.token_usage must be ON (it is by default) and some time must have passed.")
    sys.exit(1)

norm = []
for r in rows:
    at, ra = u.unstamp(r.get("at", r.get("ts"))), u.unstamp(r.get("resets_at"))
    if at is not None and ra is not None and isinstance(r.get("pct"), (int, float)):
        norm.append({"ts": at, "pct": float(r["pct"]), "resets": ra})
norm.sort(key=lambda r: r["ts"])
if not norm:
    print("history exists but no row carries both a timestamp and a resets_at.")
    sys.exit(1)

# ⚠ A COPY, so nothing here can touch the live logs, and _burn_rate() reads a real directory
# rather than being reimplemented. Reimplementing it would measure the reimplementation.
tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, "logs"))
for name in os.listdir(LOGS):
    if name.startswith(u.HISTORY_PREFIX):
        shutil.copy(os.path.join(LOGS, name), os.path.join(tmp, "logs", name))
rcfg = dict(CFG)
rcfg["history_dir"] = os.path.join(tmp, "logs")

CLOCK = 100.0 / (u.FIVE_HOUR_SECONDS / 60.0)
WIN = rcfg.get("burn_window_min") or 0


def pct_at(t):
    seen = None
    for r in norm:
        if r["ts"] <= t:
            seen = r
        else:
            break
    return seen


# ⭐ A ONE-MINUTE GRID, NOT ONE POINT PER ROW. Rows are written only when a number MOVES, so a
# busy stretch writes many and a quiet one writes none; counting rows would measure "what
# happens while busy", and the question is what fraction of the WALL CLOCK each colour holds.
live, blind = [], 0
t = norm[0]["ts"]
while t <= norm[-1]["ts"]:
    row = pct_at(t)
    if row:
        r = u._burn_rate(tmp, rcfg, row["pct"], row["resets"], t)
        if r is None:
            blind += 1
        else:
            live.append(r * 60.0)
    t += 60
shutil.rmtree(tmp, ignore_errors=True)

if not live:
    print("no computable rate anywhere in %d minutes of history." % (blind,))
    sys.exit(1)
live.sort()
n = float(len(live))
windows = sorted(set(r["resets"] for r in norm))

print("state dir        : %s" % SDIR)
print("history          : %d rows, %d five-hour window(s)" % (len(norm), len(windows)))
print("span             : %s .. %s" % (u.stamp(norm[0]["ts"]), u.stamp(norm[-1]["ts"])))
print("burn_window_min  : %s" % WIN)
if WIN:
    print("instrument step  : %.4f %%/min = %.2fx clock  (a band edge finer than this is noise)"
          % (1.0 / WIN, (1.0 / WIN) / CLOCK))
print("clock speed      : %.3f %%/min  (spend the window exactly evenly)" % CLOCK)
print("live minutes     : %d with a rate, %d drawn as '--'" % (len(live), blind))
print()


def share(cuts):
    a, b, c = [x * CLOCK for x in cuts]
    return [100.0 * sum(1 for r in live if r < a) / n,
            100.0 * sum(1 for r in live if a <= r < b) / n,
            100.0 * sum(1 for r in live if b <= r < c) / n,
            100.0 * sum(1 for r in live if r >= c) / n]


def err(cuts):
    got = share(cuts)
    want = [TARGET["green"], TARGET["yellow"], TARGET["orange"], TARGET["red"]]
    return sum(abs(x - y) for x, y in zip(got, want))


CONFIGURED = (CFG["burn_x_yellow"], CFG["burn_x_orange"], CFG["burn_x_red"])
print("owner's target   : green %d%% / yellow %d%% / orange %d%% / red %d%%"
      % (TARGET["green"], TARGET["yellow"], TARGET["orange"], TARGET["red"]))
print()
print("%-34s %6s %7s %7s %6s %6s" % ("edges (x clock)", "green", "yellow", "orange", "red", "err"))
for label, cuts in [("CONFIGURED  %.2f / %.2f / %.2f" % CONFIGURED, CONFIGURED),
                    ("ADR default 1.00 / 1.75 / 2.25", (1.00, 1.75, 2.25)),
                    ("ADR 1st proposal 1.0 / 2.0 / 3.0", (1.0, 2.0, 3.0)),
                    ("ADR 2nd proposal 1.0 / 1.5 / 2.0", (1.0, 1.5, 2.0))]:
    g, y, o, rd = share(cuts)
    print("%-34s %5.0f%% %6.0f%% %6.0f%% %5.0f%% %6.0f" % (label, g, y, o, rd, err(cuts)))
print()

STEPS = [round(0.25 * i, 2) for i in range(2, 21)]
best = None
for a in STEPS:
    for b in STEPS:
        if b <= a:
            continue
        for c in STEPS:
            if c > b and (best is None or err((a, b, c)) < best[0]):
                best = (err((a, b, c)), (a, b, c))
g, y, o, rd = share(best[1])
print("closest achievable now (quarter-multiples): %.2f / %.2f / %.2f"
      % best[1] + "  ->  %.0f%% / %.0f%% / %.0f%% / %.0f%%" % (g, y, o, rd))
print()

red_now = share(CONFIGURED)[3]
print("VERDICT on the configured bands")
if red_now == 0:
    print("  ⛔ RED NEVER FIRES (0%% of live time). The warning colour is dead - reopen the ADR.")
elif red_now > 15:
    print("  ⛔ RED IS %.0f%% OF LIVE TIME, well over the ~15%% ceiling. A warning colour that"
          % red_now)
    print("     common stops being read - reopen the ADR.")
else:
    print("  ⭐ red is %.0f%% of live time - inside the band the ADR asked for (above 0, at or"
          % red_now)
    print("     under ~15%). No reason to reopen on this evidence.")
if len(windows) < 5:
    print("  ⚠ only %d window(s) of history. The criterion asks for a full week of MIXED use;"
          % len(windows))
    print("    treat this run as indicative, not as the reconsideration measurement.")
