#!/usr/bin/env python3
"""Usage-limit awareness for the dispatch skill. Two entry points, one file.

    usage.py --statusline    Claude Code's statusLine command. Reads the payload on
                             stdin, PERSISTS the rate-limit numbers, prints one line.
    usage.py --verdict       Prints GO / PACE / STOP / NO-DATA and exits 0/1/2/3.
    usage.py --verdict --json    Same, as a JSON object.
    usage.py --fetch-now     Spend ONE API call, then print the verdict. ⭐ The answer to
                             a NO-DATA you want to confirm: --verdict never fetches, so
                             without this the only repair was piping `{}` into
                             --statusline, which nobody discovers. A diagnostic, not a
                             replacement for the statusline or --watch.
    usage.py --watch [--every N] Print the usage line every N seconds (default 30).
                             ⭐ For the VS Code extension, whose panel does NOT render a
                             statusline: measured on 2.1.246, `statusLine` appears 0 times
                             in the webview bundle while `hooks`, `permissions`, `plugins`
                             and `subagent` all appear - so the 0 is real, not minification.
                             The CLI binary mentions it 34 times and does render it.
                             ⭐ AND IT NOW FETCHES ITS OWN NUMBERS, so running this in a
                             VS Code terminal is a complete answer rather than a partial
                             one - it no longer needs a statusline to exist anywhere.

Adapted from claude-pacer (https://github.com/drpwchen/claude-pacer) - its reset
arithmetic, seven-day false-alarm rule, burn projection and near-reset exemption are
reproduced here in Python so the skill has no Node dependency and nothing to install.
The statusline RENDERING (bars, responsive tiers, width probing, topic/model display)
was deliberately not taken: it is the large half of that project and none of it is
needed to decide whether to dispatch.

WHERE THE NUMBERS COME FROM - a direct HTTP GET, as of 2026-08-26:

    GET https://api.anthropic.com/api/oauth/usage
        Authorization: Bearer <accessToken from ~/.claude/.credentials.json>
        anthropic-beta: oauth-2025-04-20

⛔ THIS REPLACED THE STATUSLINE PAYLOAD AS THE SOURCE, AND THE REASON IS A MEASUREMENT.
The payload route still works and is still the only thing a statusline receives - but a
session REPLAYS the `rate_limits` it last saw, and it advertises nothing when it does.
Measured 2026-08-26: one session reported 6% on twelve consecutive renders across eleven
minutes while the true figure climbed 15 -> 18 -> 22, and its `resets_at` was CORRECT the
whole time, so no staleness check on the reset could have caught it. Sixteen points low,
in the direction that keeps dispatching. Two sessions once read 97% and 74% at the same
moment for the same account, which is the same defect seen from the side.
⭐ The endpoint, by contrast, matched the extension's own `Account & Usage` panel to the
digit on both windows at 15:21 - the panel reaches it over an SDK channel a hook cannot
speak, which is why this file goes to HTTP instead.

⚠ It is UNDOCUMENTED. Anthropic's published Usage/Cost and Rate Limits Admin APIs are a
different quantity (tokens and dollars against a Console org, admin key required) and
carry no plan-window percentage at all. The client's own wrapper for the neighbouring
call is named `usage_EXPERIMENTAL_MAY_CHANGE_DO_NOT_RELY_ON_THIS_API_YET`. So every
failure here must end as "no number", never as a wrong number and never as a crash.

Standard library only, by design. No pip install, no npm install, nothing to vendor.
"""

import atexit
import datetime
import glob
import json
import os
import random
import re
import shutil
import sys
import time
import urllib.error
import urllib.request

DEFAULTS = {
    # The two the owner asked to keep: brake, then stop.
    # ⭐ ALIGNED WITH THE COLOUR THRESHOLDS BELOW, ON PURPOSE, and kept as separate keys.
    # The bar turning orange now means exactly "PACE has begun" and red means "STOP has
    # begun", so the line a person glances at and the decision the gate makes cannot drift
    # apart. ⚠ They stay four keys rather than two: colour is what a person reads, the
    # thresholds are what refuses a tool call, and somebody who wants a warning colour
    # earlier than the slow-down - or no colour at all - must not have to give up the brake
    # to get it.
    # ⛔ ONE PAIR PER WINDOW, because one pair could only ever watch one window. The brake
    # read the five-hour percentage and nothing else, so an account at 7d 99% and 5h 0% was
    # told GO and dispatched until the server refused - the 5h number was true and the
    # answer was wrong. ⚠ The 7d pair sits high on purpose: that window is usually NOT the
    # constraint, and pacing on it at 70% would throttle a week of work for nothing.
    "soft_pct_5h": 70,       # PACE  - finish what is in flight, start nothing heavy
    "hard_pct_5h": 85,       # STOP  - wrap up and schedule a resume
    "soft_pct_7d": 95,
    "hard_pct_7d": 97,
    # ⭐ HOW FAR BACK THE BURN GAUGE LOOKS. The gauge answers "how fast am I burning NOW",
    # so it reads the last `burn_window_min` minutes rather than the whole five-hour window.
    # ⚠ 0 means the WHOLE WINDOW - steady, and roughly `pct / minutes elapsed`, but it takes
    # over an hour to notice that the rate changed. See _burn_rate() for the trade this buys
    # and what it costs.
    "burn_window_min": 30,
    "stale_min": 15,         # data older than this is not trusted
    "near_reset_min": 20,    # within this long of the reset, soften by one level
    "colour_warn_pct": 70,   # bar turns orange at or above this
    "colour_alarm_pct": 85,  # bar turns red at or above this
    # How often the API may be asked. ⚠ THE REAL INTERVAL IS THIS PLUS UP TO
    # fetch_seconds_jitter of randomness - see _interval(). See FETCH_FLOOR_SECONDS:
    # values below that floor are clamped, and the reason is not a preference.
    "fetch_seconds": 120,
    # Randomness ADDED to every interval, never subtracted. 0 disables it. See _interval()
    # for why it is not merely politeness, and config() for the two things it is clamped
    # against.
    "fetch_seconds_jitter": 30,
    # ⚠ A DIFFERENT interval, and the two are easy to confuse. This one is how often
    # Claude Code RE-RUNS the statusline; install.py copies it into Claude Code's own
    # statusLine.refreshInterval. usage.py never acts on it. Each re-run consults the
    # cache and only reaches the network once fetch_seconds has elapsed, so leaving this
    # at 60 costs nothing: the display stays responsive while the API is asked at most
    # once every fetch_seconds.
    "refresh_seconds": 60,
    # ⛔ WHEN `--watch` STOPS ASKING THE API. That task is bound to the FOLDER being open,
    # not to a session being alive, so without this it polls all night against an endpoint
    # that allows about five calls per access token. The gate touches state/<id>.alive on
    # every hook event, so "is anyone working?" is already answered on disk.
    # ⚠ Conservative on purpose: a single long tool call fires no hook between its Pre and
    # Post, so a short value would pause the watcher during a build and unpause after it.
    # 15 minutes is longer than that and far shorter than a night.
    # ⚠ Only --watch is gated. --statusline is invoked BECAUSE a session is interacting, so
    # testing there would suppress the refresh exactly when it is due.
    "idle_after_min": 15,
}


def state_dir(argv=None):
    """Where token_usage.json and the logs/ folder live.

    `--dir` wins, then $CLAUDE_DISPATCH_DIR, then **~/.claude/dispatch-guard/**.

    ⛔ THAT LAST PATH USED TO BE WRITTEN HERE AS "~/.claude/", WHICH IS NOT WHERE ANYTHING
    GOES. It is the one sentence somebody reads when they are trying to find their files,
    so being one directory out made it worse than saying nothing.
    ⚠ install.py does NOT read $CLAUDE_DISPATCH_DIR - it hard-codes the default - so with
    that variable set, `install.py --status` reports paths the hooks are not using. It says
    so on its own 'log files' line rather than leaving the reader to find out.
    """
    argv = argv if argv is not None else sys.argv[1:]
    if "--dir" in argv:
        i = argv.index("--dir")
        if i + 1 < len(argv):
            return os.path.abspath(argv[i + 1])
    env = os.environ.get("CLAUDE_DISPATCH_DIR")
    if env:
        return os.path.abspath(env)
    home = os.path.expanduser("~")
    return os.path.join(home, ".claude", "dispatch-guard")


def read_json(path, fallback=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback


# ⭐ How long a file in history_dir survives, in days. 0 keeps everything for ever.
# ⚠ Thirty days of the debug dump is about 40 MB at the measured 1.2-1.4 MB a day, and
# thirty days of token_usage is well under 30 MB. Both are small enough to keep and
# enough to be worth bounding, which is why the default deletes rather than hoards.
HISTORY_KEEP_DAYS_DEFAULT = 30

# ⭐ EVERY DEBUG SWITCH AND ITS DEFAULT, in one place, because "what switches exist?" was
# otherwise answerable only by reading config.example.json.
# ⛔ The two defaults differ on purpose. token_usage writes two percentages a row -
# 82 KB a day, MEASURED (132 bytes a row, about 640 readings, and only when a number
# actually moved) - and it is what makes the burn PROJECTION work at all, so it is
# ON. API_response_usage writes whole response bodies at 1.2-1.4 MB a day to answer a
# question and then be switched off again, so it is OFF.
DEBUG_DEFAULTS = {
    "API_response_usage": False,
    "token_usage": True,
}


def _days(value, default):
    """A retention setting -> a number of days. ⛔ ANYTHING UNUSABLE KEEPS FILES FOR EVER.

    ⚠ THE DEFAULT DIRECTION MATTERS MORE HERE THAN ANYWHERE ELSE IN THIS FILE, because this
    is the one setting that DELETES. Every other bad value in config.json costs a wrong
    number on a line; a bad value here could cost a record that cannot be recovered. So a
    string, a null, a negative, a bool - anything this cannot read as a positive number -
    means KEEP EVERYTHING, never "fall back to 30 days and start deleting".
    ⭐ A hand-written "30" still works: the digits are read, because refusing them would be
    surprising in the other direction.
    """
    if value is None:
        return default
    if isinstance(value, bool):          # True is not 1 day, and False is not 0
        return 0
    try:
        days = float(value)
    except (TypeError, ValueError):
        return 0
    if days != days or days in (float("inf"), float("-inf")) or days <= 0:
        return 0
    return days


def _truthy(value, default=False):
    """A config value -> bool. ⛔ A STRING IS READ FOR ITS MEANING, NOT ITS LENGTH.

    ⚠ `bool("false")` is True, and so is `bool("0")` and `bool("no")`. JSON writes a real
    boolean, but config.json gets hand-edited, and somebody typing the word for OFF must not
    switch something ON. Measured by a refuting pass: `"API_response_usage": "false"` turned
    the dump on.

    ⛔ AN UNRECOGNISED STRING RETURNS `default`, NOT True. A first version returned True for
    anything it did not recognise, which switches a diagnostic ON for a typo - the same
    "reads as off, behaves as on" failure the function exists to remove.

    ⭐ THIS IS DELIBERATELY A SECOND COPY of `cmd_guards._truthy`, and the semantics are kept
    identical on purpose - including the `default` for an unrecognised value. It is not
    imported because the dependency runs the other way: dispatch_gate.py and resume.py both
    `import usage`, while usage.py imports nothing from its siblings, and cmd_guards is
    itself a dispatch_gate dependency. Reaching sideways from here would invert that and
    risk a cycle. ⚠ If you change one, change both.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("false", "0", "no", "off", ""):
        return False
    if text in ("true", "1", "yes", "on"):
        return True
    return default


def config(sdir):
    """DEFAULTS overlaid with config.json, if one exists. Unknown keys are ignored."""
    cfg = dict(DEFAULTS)
    disk = read_json(os.path.join(sdir, "config.json"), {}) or {}
    for source in (disk, disk.get("guard") or {}):
        for k in DEFAULTS:
            if isinstance(source.get(k), (int, float)):
                cfg[k] = source[k]
    # ⛔ The floor is ENFORCED, not merely documented, and the clamp SAYS SO when it
    # fires. A configured 30 silently becoming 120 is indistinguishable from a bug.
    if cfg["fetch_seconds"] < FETCH_FLOOR_SECONDS:
        sys.stderr.write(
            "usage.py: fetch_seconds=%s raised to the %d s floor - the usage endpoint "
            "allows only ~5 calls per token; see FETCH_FLOOR_SECONDS.\n"
            % (cfg["fetch_seconds"], FETCH_FLOOR_SECONDS))
        cfg["fetch_seconds"] = FETCH_FLOOR_SECONDS
    # ⛔ CLAMPED UP, NOT REJECTED, and it SAYS SO. Below BURN_WINDOW_FLOOR_MIN the span guard
    # in _burn_rate() refuses every sample, so a well-meant "burn_window_min": 2 would not
    # make the gauge twitchy - it would switch the gauge OFF, silently and for ever.
    # ⚠ 0 IS NOT CLAMPED: it is the documented way to ask for the whole window instead.
    if cfg["burn_window_min"] < 0:
        cfg["burn_window_min"] = DEFAULTS["burn_window_min"]
    if 0 < cfg["burn_window_min"] < BURN_WINDOW_FLOOR_MIN:
        sys.stderr.write(
            "usage.py: burn_window_min=%g raised to the %d min floor - a shorter baseline "
            "cannot resolve a rate from whole-percent readings; 0 asks for the whole "
            "window.%s" % (cfg["burn_window_min"], BURN_WINDOW_FLOOR_MIN, chr(10)))
        cfg["burn_window_min"] = BURN_WINDOW_FLOOR_MIN
    # ⛔ NEGATIVE JITTER IS REFUSED, and this is the load-bearing clamp. Jitter is added,
    # so a negative value would SUBTRACT and could push the real interval under the floor -
    # which is the one thing the floor exists to prevent.
    if cfg["fetch_seconds_jitter"] < 0:
        sys.stderr.write("usage.py: fetch_seconds_jitter=%s is negative and would subtract "
                         "from the interval; using 0.%s"
                         % (cfg["fetch_seconds_jitter"], chr(10)))
        cfg["fetch_seconds_jitter"] = 0
    # ⚠ A jitter big enough to push the longest interval past stale_min makes the data go
    # stale between fetches, which renders as -- and reads NO-DATA - a brake that fails
    # OPEN. Warned rather than clamped: the person may have raised stale_min on purpose,
    # and silently overriding a deliberate choice is its own trap.
    if cfg["fetch_seconds"] + cfg["fetch_seconds_jitter"] > cfg["stale_min"] * 60:
        sys.stderr.write(
            "usage.py: fetch_seconds+jitter (%ds) can exceed stale_min (%d min), so the "
            "number will intermittently read -- and the brake will not fire.%s"
            % (cfg["fetch_seconds"] + cfg["fetch_seconds_jitter"], cfg["stale_min"],
               chr(10)))
    # An explicit token_usage_file lets this skill read an EXISTING claude-pacer install
    # instead of collecting its own, so a machine that already has one is not broken
    # by installing this.
    cfg["token_usage_file"] = (disk.get("token_usage_file")
                          or os.path.join(sdir, "token_usage.json"))
    cfg["colour"] = disk.get("colour", disk.get("color", True))
    # ⭐ ON by default, and it did not use to be. token_usage_history_*.jsonl records how
    # much was used and when - two percentages a row, nothing else. It is on because burn
    # PROJECTION needs two samples of the same window, so with it off the "projected to
    # exceed before the reset" half of PACE has never fired for anybody who did not go and
    # switch it on. The soft and hard thresholds were always unaffected either way.
    # ⚠ THE COST IS NOW BOUNDED, which is what changed: roughly a megabyte a day, and
    # history_keep_days removes whole files after 30 days. Kept for ever, it was a record of
    # a person's usage that nobody had asked for; kept for a month, it is what makes the
    # projection work.
    # ⛔ THE SWITCH IS `debug.token_usage` NOW, and it is set further down, once the
    # debug block has been parsed. See the assignment there - putting it here would mean
    # parsing that block twice, and the second copy is the one that drifts.
    cfg["history_dir"] = disk.get("history_dir")     # None -> <state dir>/logs
    # ⛔ HOW LONG THE FILES IN history_dir SURVIVE, and it is the only setting here that
    # DELETES something. 0 - or any value that is not a positive number - keeps them for
    # ever, which is what this plugin did before the key existed.
    # ⚠ WHOLE FILES, BY AGE, AND NOTHING ELSE. See prune_logs(): a day's file is kept
    # entire or removed entire, so a record is never left half there. And only files
    # carrying one of this plugin's own two prefixes are touched, because history_dir can
    # be pointed at a folder that holds somebody else's files too.
    cfg["history_keep_days"] = _days(disk.get("history_keep_days"),
                                     HISTORY_KEEP_DAYS_DEFAULT)
    # ⛔ OFF by default, and it is meant to be switched back off. With
    # "debug": {"API_response_usage": true} every successful fetch appends the WHOLE
    # response body to <history_dir>/API_response_usage_<stamp>.jsonl, rotated rather than
    # trimmed. ⚠ COST, MEASURED: a whole line is 2006 bytes (the body alone 1887), and
    # fetch_seconds 120 with fetch_seconds_jitter 30 gives a MEAN interval of 135 s - about
    # 640 lines a day, where 720 would be the no-jitter ceiling. So AT MOST ABOUT
    # 1.2-1.4 MB A DAY, and only across a full day of continuous work: while nothing is
    # happening, idle_after_min stops the watcher asking at all.
    # ⛔ AN EARLIER VERSION OF THIS COMMENT SAID "2.9 KB a response, about 2 MB a day" AND
    # WAS WRONG BY ROUGHLY 60%. 2.9 KB was the size of a capture FILE - a wrapper around a
    # response - and 720 ignored the jitter. It exists to answer a question from disk
    # instead of by spending another API call, not to run forever.
    # ⭐ A NAMED BLOCK rather than a flat key, so the next debug switch needs no new schema.
    # ⚠ A LIST IS AN ALIAS for the same thing: "debug": ["API_response_usage"] means
    # {"API_response_usage": true}, because that is how the setting was described.
    # ⚠ Position 1 of a dumped row is the per-seat accountUuid and CAN BE null. A null
    # there does not mean "the same account as the row above" - it means the row could not
    # be attributed to a seat at all, so a reader computing statistics must EXCLUDE it
    # rather than average it in. See _account_ids().
    d = disk.get("debug") or {}
    if isinstance(d, list):
        d = {k: True for k in d}
    elif not isinstance(d, dict):
        # ⛔ WARNED, NOT SILENTLY DROPPED. `"debug": true` reads as "switch debugging on"
        # and used to mean the exact opposite - every switch off, with nothing anywhere
        # saying so. A person who wrote that would wait all day for a file that never
        # arrives, and the config would look right the whole time.
        # ⚠ "NO debug switch is on" WAS TRUE AND IS NOT ANY MORE. Once one switch defaults
        # to ON, an unusable block means "every switch keeps its default", not "everything
        # is off" - and saying the wrong one sends a person hunting for a file that is in
        # fact being written. Found by a refuting pass.
        sys.stderr.write('usage.py: debug=%r is not an object or a list, so it is IGNORED '
                         'and every switch keeps its default. Use '
                         '{"API_response_usage": true}.%s' % (d, chr(10)))
        d = {}
    # ⚠ VALUES ARE COERCED, and the string is the reason. JSON `false` arrives as a bool,
    # but a hand-edited config carries "false", "0" and "no" - every one of them TRUTHY in
    # Python, so the switch would come ON for somebody who wrote the word for off.
    # ⛔ EACH SWITCH HAS ITS OWN DEFAULT, from DEBUG_DEFAULTS, and an unrecognised value
    # falls back to that switch's default rather than to False. ⚠ A first version defaulted
    # every value to False, which is wrong the moment one switch is on by default: an absent
    # key then read as OFF and the default could never take effect.
    # ⚠ Every value here is coerced to a bool, so a future switch needing a STRING (a level,
    # a path) cannot live in this block as-is - it needs its own key.
    cfg["debug"] = dict(DEBUG_DEFAULTS)
    for key, value in d.items():
        cfg["debug"][key] = _truthy(value, DEBUG_DEFAULTS.get(key, False))

    # ⛔ `keep_history` IS NO LONGER READ AT ALL, and neither is anything else this switch has
    # been called. There is ONE name now - `debug.token_usage` - and cfg["debug"] is the only
    # place it lives; there is no second copy at the top level to drift from it.
    # ⚠ A config still carrying `"keep_history": false` therefore gets the DEFAULT, which is
    # ON. That is the owner's decision, taken deliberately: carrying a rename forward for ever
    # is how a settings file ends up with three names for one switch and nobody able to say
    # which one wins. `install.py --status` names every unrecognised key it finds.
    cfg["show_context"] = bool(disk.get("show_context", True))
    cfg["show_model"] = bool(disk.get("show_model", True))
    cfg["width"] = disk.get("width")        # None -> detect
    # ⭐ MAY THE DISPLAY SPEND A SECOND ROW when one will not hold everything? ON by default,
    # for both the statusline and `--watch`: the alternative is throwing information away,
    # and the context bar and the note are the parts that get thrown. ⚠ A second row costs a
    # row of the terminal above the input box, which on a narrow one is a row of
    # conversation - so it is switchable, and false packs one row exactly as before.
    cfg["two_rows"] = _truthy(disk.get("two_rows"), True)
    # ⚠ Reads as a gap in the bar until you know what it is, so it is switchable.
    cfg["show_time_marker"] = bool(disk.get("show_time_marker", True))
    # ⛔ Default is to REWRITE one line. A watcher that scrolls fills a panel with history
    # nobody asked for, and only the newest line means anything.
    cfg["watch_scroll"] = bool(disk.get("watch_scroll", False))
    # ⛔ A stale percentage is shown as dashes rather than as a number. See _window().
    cfg["stale_hides_numbers"] = bool(disk.get("stale_hides_numbers", True))
    SHOW_MARK[0] = cfg["show_time_marker"]
    return cfg


# ----------------------------------------------------------------------------- fetch

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_BETA = "oauth-2025-04-20"
# Seconds. The client itself budgets 5 for this same call, which is why 5 and not a number
# picked here. ⚠ MEASURED COST: against a non-routable address the request takes 5.05 s to
# give up, and collect() runs on the statusline's timer - so a dark network delays a render
# by five seconds. That is tolerable ONLY because _claim_attempt() bounds it to once per
# fetch_seconds instead of once per render: offline, one late line every three minutes
# rather than every sixty seconds. ⛔ Do not shorten it to shave that: cutting off a slow
# but working network loses the reading AND spends a call AND arms the same backoff, so a
# short timeout buys a cosmetic win with a blind brake.
FETCH_TIMEOUT = 5

# ⛔ NEVER LOWER THIS, AND IT IS NOT A TUNING PARAMETER.
#
# The endpoint allows only about FIVE CALLS PER ACCESS TOKEN. Source: onWatch, a Go quota
# monitor covering ten providers - https://github.com/onllm-dev/onwatch - which documents
# the endpoint as having "aggressive rate limits (~5 requests per token)" and whose OWN
# default poll interval is 120 s (ONWATCH_POLL_INTERVAL) while it serves its dashboard
# from a local SQLite cache rather than from the API.
#
# What goes wrong below ~120 s, in order:
#   1. `usage.py --statusline` re-runs on a timer and `--watch` loops, so a short interval
#      turns into a steady stream of calls rather than an occasional one.
#   2. The allowance is exhausted within minutes, and every later call in that session
#      returns HTTP 429. claude-code issue #31021 is exactly this, reported with a
#      persistent 429 that broke both the statusline and `/usage` - and CLOSED AS NOT
#      PLANNED, so there is no fix coming and no retry that recovers from it.
#   3. ⛔ The brake then goes BLIND for the rest of the window - during precisely the
#      heavy run it exists to govern, because that is what was burning the calls.
#   4. ⛔ Blind here means the LAST GOOD NUMBER goes stale and reads LOW. A too-fast poll
#      does not merely waste calls; it converts a working brake into one that FAILS OPEN.
#
# ⚠ And the recovery onWatch uses is not available here: it answers a 429 by refreshing
# the OAuth token to mint a fresh window. See _token_and_expiry() for why this file
# must not - and fetch(), which refuses to spend a call on a token that file shows is dead.
FETCH_FLOOR_SECONDS = 120

# ⭐ Randomness is ADDED to every interval - never subtracted, so the effective wait is
# always fetch_seconds..fetch_seconds+jitter and can never dip under the floor. The amount
# is `fetch_seconds_jitter` in config.json (default 30, 0 disables it); this constant is
# only the fallback for a caller that passes no config. Two reasons, and the second is why
# it is not merely tidiness:
#   1. It DE-SYNCHRONISES independent processes. Several sessions' statuslines all tick on
#      the same 60 s refresh, so without jitter they drift into lockstep and arrive at the
#      interval boundary together - which is precisely the burst _claim_attempt() has to
#      absorb. Jitter makes them stop arriving together in the first place; the claim then
#      only has to catch what is left.
#   2. It spreads the load rather than delivering it as a spike, which is the polite thing
#      to do to an endpoint that rate-limits at about five calls per token and whose
#      maintainers have already declined to fix a 429 report.
JITTER_SECONDS = 30


def _interval(cfg):
    """fetch_seconds plus 0..fetch_seconds_jitter seconds. Rolled ONCE per ensure_fresh().

    ⚠ Rolled once and passed down, not called twice: the freshness check and the claim
    check must agree on the same deadline, or a process can pass one and fail the other
    for no reason a reader could reconstruct.

    ⛔ The jitter is never negative - config() clamps it - because a negative one would
    subtract and could put the real interval under FETCH_FLOOR_SECONDS.
    """
    jitter = cfg.get("fetch_seconds_jitter", JITTER_SECONDS)
    return cfg["fetch_seconds"] + random.uniform(0, max(0, jitter))


def _token_and_expiry():
    """(token, expiry epoch seconds or None). READ ONLY - never written, never refreshed.

    ⛔ DO NOT ADD A REFRESH HERE, however tempting a 429 makes it. onWatch bypasses the
    rate limit by refreshing the token, and that works for onWatch because it is a
    standalone daemon that owns its own polling. This file runs as a hook inside the same
    account as the client that MAINTAINS that token: writing it would race whatever Claude
    process is running and rewriting the same file, and it would mean a hook writing
    credentials. Deliberately accepted trade: a 429 here reports no number and waits.

    ⚠ Only the JSON file and $ANTHROPIC_TOKEN are read. onWatch also reads the macOS
    keychain and the Linux keyring, neither of which is implemented here - so on a machine
    where the token lives only in a keychain this returns (None, None), and the caller
    degrades to "no data" rather than to a wrong number.

    ⭐ The file is re-read on EVERY call, deliberately. That is what makes a long-running
    `--watch` survive a token rotation with no restart: whichever Claude client is running
    refreshes the token and rewrites this file, and the next fetch picks up the new one.
    Measured 2026-08-26: rewritten at 15:29:40 with a new expiry of 23:29:40, about five
    minutes before the old one was due to die.

    ⚠ AN ACCESS TOKEN LASTS ABOUT EIGHT HOURS, not one. An earlier note here said "about an
    hour", which was a reading taken 45 minutes before an expiry and mistaken for the whole
    lifetime. The refresh token lasts about 30 days.
    """
    env = os.environ.get("ANTHROPIC_TOKEN")      # onWatch uses the same variable name
    if env and env.strip():
        return env.strip(), None                 # supplied by hand; no expiry to read
    blob = read_json(os.path.join(os.path.expanduser("~"), ".claude",
                                  ".credentials.json"), {}) or {}
    if not isinstance(blob, dict):
        return None, None
    inner = blob.get("claudeAiOauth")
    inner = inner if isinstance(inner, dict) else blob
    token = inner.get("accessToken")
    if not (isinstance(token, str) and token):
        return None, None
    expires = inner.get("expiresAt")
    if isinstance(expires, (int, float)) and not isinstance(expires, bool):
        expires = expires / 1000.0 if expires > 1e11 else float(expires)
    else:
        expires = None
    return token, expires


# ⛔ token_note() IS GONE, AND IT IS NOT COMING BACK BY ACCIDENT. The owner removed it in two
# steps on 2026-08-29 - first the ten-minute countdown ("OAuth 那行不要顯示"), then the
# expired form ("「已過期」也不顯示") - so nothing on the bar reports an OAuth token any more.
#
# ⚠ THE EXPIRY IS STILL READ, and that half must not be removed with it: fetch() refuses to
# spend one of the five calls on a token it can already see is dead, and returns that as its
# `reason`. See _token_and_expiry(), which fetch() calls for the token anyway.
# ⇒ So one OAuth sentence can still reach the display, by the ordinary failure-reason route
# and only once the stored number has gone stale. That is not this note returning; it is the
# line saying why the figures on it stopped, which is the one moment it must not stay quiet.


def _snap_minute(epoch):
    """A reset instant, snapped to the NEAREST whole minute.

    ⛔ MEASURED IN REAL DATA, on two machines. The API stamps microseconds and they differ on
    every response for the SAME window - and it does not even keep the same second: one
    machine's history holds `19:10:00`, `19:10:00`, `19:09:59`, `19:10:00` for ONE window.
    ⇒ Anything comparing reset instants for equality flaps, and every displayed clock is a
    second out half the time.

    ⚠ NEAREST, NOT ALWAYS UP. `19:09:59.7` and `19:10:00.2` are the same window and both must
    land on `19:10:00`; rounding up would push the second to 19:11 - a whole minute wrong, in
    the direction that makes the window look longer than it is.

    ⚠ It assumes resets fall on a whole minute, which is what both machines show. A window
    that genuinely reset at 19:10:30 would be reported half a minute early - the safe
    direction, because it under-states the time left.
    """
    return int(round(float(epoch) / 60.0)) * 60


def _iso_epoch(value):
    """ISO-8601 with an offset -> epoch seconds. Numbers pass through unstamp().

    ⚠ unstamp() cannot read what this API sends. It handles epochs and this file's own
    "YYYY-MM-DD HH:MM:SS", while the API sends "2026-08-26T11:00:00.203505+00:00" -
    fractional seconds and a UTC offset. Verified against a measured pair: that string
    parses to 1787742000, which is the exact epoch the stored file already held for the
    same window.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return unstamp(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


# Which row of the response's `limits` array describes the same window as which top-level
# key. Measured live 2026-08-27: `session` carries the five-hour figure, `weekly_all` the
# seven-day one, and both give `percent` as a WHOLE NUMBER.
_LIMIT_KIND = {"five_hour": "session", "seven_day": "weekly_all"}


# ⭐ A WINDOW SCOPED TO ONE MODEL. Measured on two accounts, 2026-08-27, captured in
# Memory/tasks/20260827-153945-usage-api-fable-window/: `limits[]` carries a third row whose
# `kind` is "weekly_scoped" and whose `scope.model.display_name` is the plain string "Fable".
_SCOPED_KIND = "weekly_scoped"


def _scoped_window(data):
    """The model-scoped window the account is actually using, or None.

    ⛔ THE RESPONSE CARRIES NO ENTITLEMENT FLAG, and that is measured rather than assumed.
    Two accounts were captured - one that may use Fable and one that may not - and the row
    EXISTS on both, `is_active` is false on both (it stayed false at 19% used), and
    `nimbus_quill` read 0.0 while the scoped row read 19%, which is evidence AGAINST that
    top-level codename being Fable's counterpart rather than for it. ⇒ Nothing in the
    payload says "this account may use Fable".

    ⇒ SO THIS ANSWERS A DIFFERENT QUESTION, and says so: is there a scoped window RUNNING?
    `percent > 0` or a non-null `resets_at`. On the two captures that is exactly the
    difference - the account that cannot use Fable had 0 and null, the one that can had 19
    and a timestamp. ⚠ An entitled account that used none this week therefore shows nothing
    until its first use. That is the acceptable direction: the owner asked for no extra text
    when it does not apply, and a bar that appears on first use is not a lie.

    ⭐ THE MODEL IS NOT HARD-CODED. The row names itself, so a scoped window for any other
    model works the same day it appears. ⚠ Only the first qualifying row is returned; the
    line has one column of room for this, and no account has yet shown two.

    ⛔ `percent` HERE NEEDS NO SCALE CHECK, unlike `utilization`. See _whole_percent(): the
    `limits[]` figure is a whole number by construction, which is the whole reason that
    function exists.
    """
    for row in (data or {}).get("limits") or []:
        if not isinstance(row, dict) or row.get("kind") != _SCOPED_KIND:
            continue
        scope = row.get("scope")
        model = (scope or {}).get("model") if isinstance(scope, dict) else None
        name = (model or {}).get("display_name") if isinstance(model, dict) else None
        if not isinstance(name, str) or not name.strip():
            continue
        pct = row.get("percent")
        if not isinstance(pct, (int, float)) or isinstance(pct, bool):
            continue
        if not 0 <= pct <= 100:
            continue
        resets = _iso_epoch(row.get("resets_at"))
        if not (pct > 0 or resets):
            continue                     # present but not running - see the docstring
        out = {"label": name.strip(), "used_percentage": float(pct)}
        if resets:
            out["resets_at"] = _snap_minute(resets)
        return out
    return None


def _whole_percent(data, name):
    """The same window's percent from the `limits` array, or None.

    ⭐ WHY THIS EXISTS: it is the response telling us its own scale. `utilization` is
    ambiguous in (0, 1] - 1% and 100% look identical - but `limits[].percent` is a whole
    number by construction, so the two together pin the scale down. Before this, a genuine
    1% window was thrown away and the segment vanished from the line entirely, which is how
    the seven-day bar disappeared the moment the week rolled over.
    """
    kind = _LIMIT_KIND.get(name)
    if not kind or not isinstance(data, dict):
        return None
    for row in data.get("limits") or []:
        if isinstance(row, dict) and row.get("kind") == kind:
            pct = row.get("percent")
            if isinstance(pct, (int, float)) and not isinstance(pct, bool):
                return float(pct)
    return None


def _api_window(win, whole=None):
    """One API window -> the {used_percentage, resets_at} shape token_usage.json stores.

    ⛔ THE SCALE IS ASSERTED, NOT ASSUMED, and a value that cannot be told apart is
    REJECTED. This endpoint returns WHOLE PERCENT - measured 2026-08-26 15:21,
    `utilization: 22.0` beside a UI reading 22%. But the VS Code webview's own meters
    receive the SAME FIELD NAME as a FRACTION and multiply it out
    (`Math.floor($.utilization * 100)`), so two scales for one name exist in this system.
    ⚠ A value in (0, 1] is therefore ambiguous: 1% and 100% are indistinguishable, and
    guessing wrong reads LOW - the direction that keeps dispatching. Refusing it costs a
    "no data" at under 1% used, where the brake has nothing to do anyway.
    """
    if not isinstance(win, dict):
        return None
    pct = win.get("utilization")
    if not isinstance(pct, (int, float)) or isinstance(pct, bool):
        return None
    if 0 < pct <= 1:
        # ⭐ Ask the response which scale it meant, instead of refusing the reading. `whole`
        # is the same window's percent from `limits[]`, a whole number, so exactly one of
        # the two readings can match it. ⚠ Still refused when there is nothing to compare
        # against: guessing here reads LOW, and low is the direction that keeps dispatching.
        if whole is None:
            return None
        if abs(whole - pct) < 0.5:            # 1.0 beside percent 1 -> already whole
            pass
        elif abs(whole - pct * 100) < 0.5:    # 0.01 beside percent 1 -> a fraction
            pct = pct * 100
        else:
            return None
    if not 0 <= pct <= 100:
        return None
    out = {"used_percentage": pct}
    resets = _iso_epoch(win.get("resets_at"))
    if resets:
        # ⛔ TRUNCATED TO WHOLE SECONDS ON PURPOSE. The API stamps microseconds and they
        # DIFFER ON EVERY RESPONSE for the same window (.203505, then .390781), so a
        # float here makes two identical readings compare unequal - which would defeat
        # _write_record()'s "did a number actually move?" check and append a history row
        # on every single fetch. The reset instant is a wall-clock minute; sub-second
        # precision on it is noise that carries a bug.
        # ⚠ SNAPPED TO THE WHOLE MINUTE, not merely rounded to the second. Rounding to the
        # second was the first fix and it was not enough: real history from another machine
        # holds 19:10:00 and 19:09:59 for ONE window, so the flap survived. See _snap_minute.
        out["resets_at"] = _snap_minute(resets)
    return out


def fetch(cfg=None, sdir=None):
    """One HTTP GET. Returns a record dict on success, or a STRING naming why not.

    ⚠ It returns a reason instead of raising, because every failure here must end as
    "no number" - in a statusline, in a watcher, and in a hook. A crash in any of those
    is worse than a dash, and a wrong number is worse than both.

    ⚠ `sdir` is used ONLY by the debug response dump below, which does nothing unless
    debug.API_response_usage is on. None disables it, so a caller that has no state
    directory (the selftest) simply gets the old behaviour. ⛔ It cannot be replaced by
    state_dir(): the state directory is a parameter everywhere else in this file, and the
    selftest drives ensure_fresh() against a temp directory state_dir() would never name.
    """
    token, expires = _token_and_expiry()
    if not token:
        return "no OAuth token (~/.claude/.credentials.json or $ANTHROPIC_TOKEN)"
    # ⭐ Do not spend one of the five calls on a token we can already see is dead. The
    # request would return 401, arm the same backoff, and tell us nothing the file did not.
    if expires is not None and expires <= time.time():
        return ("OAuth token expired %s - open a Claude session to refresh it"
                % (stamp(expires) or "recently"))
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": "Bearer " + token,
        "anthropic-beta": OAUTH_BETA,
        "Content-Type": "application/json",
        "User-Agent": "dispatch-guard/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            # ⛔ Not retried, and not worked around. See FETCH_FLOOR_SECONDS.
            return "HTTP 429 rate limited - backing off, NOT retrying"
        if exc.code in (401, 403):
            return "HTTP %d - token expired or rejected" % exc.code
        return "HTTP %d" % exc.code
    except Exception as exc:                      # timeout, DNS, TLS, offline
        return "%s" % (exc.__class__.__name__,)
    try:
        data = json.loads(body)
    except ValueError:
        return "unparseable response"
    if not isinstance(data, dict):
        return "unexpected response shape"
    # ⛔ THE DEBUG DUMP GOES HERE, AND THE POSITION IS THE WHOLE POINT - not style.
    # `if not five: return` a few lines below fires when a response's five_hour cannot be
    # used, and that is PRECISELY the shape a diagnostic exists to capture. Any later
    # position silently drops the most interesting responses. ⚠ Measured 2026-08-27: a
    # real response came back with five_hour.resets_at null beside utilization 0.0, an
    # unanticipated shape which happened to pass the check below. The next surprise may
    # not, and a diagnostic that only keeps the responses the parser already understood is
    # worth nothing.
    if sdir and ((cfg or {}).get("debug") or {}).get("API_response_usage"):
        _dump_response(sdir, cfg or {}, data)
    five = _api_window(data.get("five_hour"), _whole_percent(data, "five_hour"))
    if not five:
        # ⚠ A THIRD STATE, distinct from "no data" and from "stale data": the response
        # arrived and carried no usable window. Seen for real - a payload containing the
        # `rate_limits` key with no usable `five_hour` inside it. It must not overwrite a
        # good stored value with nulls.
        return "response carried no usable five_hour"
    record = {"ts": int(time.time() * 1000), "five_hour": five}
    seven = _api_window(data.get("seven_day"), _whole_percent(data, "seven_day"))
    if seven:
        record["seven_day"] = seven
    # ⭐ Only when one is RUNNING, so an account without it carries no extra key and its
    # display gains no extra text. See _scoped_window().
    scoped = _scoped_window(data)
    if scoped:
        record["scoped"] = scoped
    return record


def _write_record(sdir, cfg, record, prev):
    """Atomically replace token_usage.json, and append history only when a number moved.

    ⭐ ts IS ALWAYS STAMPED on a successful fetch, even when the numbers are identical -
    and that is the OPPOSITE of what the statusline path had to do. There, an unchanged
    payload was a REPLAY of an old reading, so stamping it made staleness invisible. Here
    an unchanged reading is the SERVER CONFIRMING the value right now, so the age of the
    file is honestly the age of the number, and stale_min means what it says again.
    """
    os.makedirs(sdir, exist_ok=True)
    tmp = cfg["token_usage_file"] + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(record, f)
        os.replace(tmp, cfg["token_usage_file"])      # atomic; never a half-written file
    except OSError:
        return
    moved = not (isinstance(prev, dict)
                 and prev.get("five_hour") == record.get("five_hour")
                 and prev.get("seven_day") == record.get("seven_day")
                 # ⭐ The model-scoped window counts as a number that can move. Left out, a
                 # session that spent only on the scoped model would look like a session
                 # where nothing happened, and the history would have no row for it.
                 and prev.get("scoped") == record.get("scoped"))
    if moved and cfg["debug"]["token_usage"]:
        # ⚠ model and session are no longer recorded, and that is accepted rather than
        # overlooked: they came off the statusline payload, which this path does not see.
        # Checked before accepting it - _projection() reads only `pct`, `at`/`ts` and
        # `resets_at`, so nothing computes on either field. They were context for a human
        # reading the log. If a per-model breakdown
        # is ever wanted, it has to come from the payload in collect(), not from here.
        _append_history(sdir, cfg, record.get("five_hour") or {},
                        record.get("seven_day") or {})


def _claim_attempt(sdir, due):
    """True if THIS process may spend one of the five calls. Written BEFORE the request.

    ⛔ WITHOUT THIS THE FLOOR PROTECTS NOTHING. fetch_seconds is enforced against the age
    of token_usage.json, and several processes share that one file: two sessions' statuslines,
    or a statusline and a `--watch`, crossing the interval boundary together all see the
    same stale timestamp and all fetch. At about five calls per token that is not a
    rounding error - it is most of the budget spent on one boundary. Several sessions open
    at once is the normal state on a working machine, not an edge case.

    ⭐ It doubles as the ONLY BACKOFF THERE IS, and that is the load-bearing half. Reaching
    this function means token_usage.json is NOT fresh, so any recent attempt recorded here must
    have FAILED. Refusing for `due` after a failure is therefore exactly the 429 backoff: a
    claim is not released on failure, deliberately, because releasing it would let the next
    caller retry at once and a persistent 429 is not something retrying cures.

    ⚠ `due` is fetch_seconds plus this caller's jitter, rolled by ensure_fresh() and passed
    in rather than re-rolled here - see _interval(). Jitter also reduces how often this
    function has to do anything, by stopping independent processes arriving together.

    # ponytail: mtime clock, not a real mutex. Two processes hitting the same instant
    # still get two calls; the cost is one wasted call, bounded and rare. A real lock
    # (O_EXCL plus stale-owner recovery plus release-on-crash) is a lot of machinery to
    # save an occasional single request. Upgrade only if fetch.log shows paired 429s.
    """
    path = os.path.join(sdir, "fetch.claim")
    try:
        if time.time() - os.path.getmtime(path) < due:
            return False
    except OSError:
        pass                                     # no claim yet, or unreadable
    try:
        os.makedirs(sdir, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
        os.replace(tmp, path)                    # atomic, and stamps a fresh mtime
    except OSError:
        return True     # cannot record the attempt; better to fetch than to go blind
    return True


def ensure_fresh(sdir, cfg):
    """Refresh token_usage.json when the stored number is older than fetch_seconds.

    Returns None when nothing needed doing or the fetch succeeded, else the reason string.

    ⛔ DELIBERATELY NOT CALLED FROM verdict(). verdict() runs inside the dispatch hook, on
    EVERY dispatch. A synchronous HTTP call there stalls the dispatch every time the
    interval boundary is crossed, and a hook that hangs is worse than a number a few
    minutes old. Fetching therefore belongs to the two callers already on a timer:
    --statusline, which Claude Code re-runs, and --watch.

    ⭐ THAT GAP IS CLOSED, and not by making verdict() fetch. dispatch_gate's
    keep_clock_running() FORKS this refresh, detached, when token_usage.json goes stale, on a
    hook event it was running anyway. The dispatch never waits on the network - the number
    lands for a later call to read - so the extension gets a working brake with no
    statusline, no watcher and nothing per-project. ⚠ Those two are now DISPLAY: they are
    how a person sees the line, not how the brake stays alive.

    ⚠ Freshness is judged from token_usage.json, which SEVERAL PROCESSES SHARE - so the age
    check alone does not bound the call count. _claim_attempt() does, and it is also the
    only backoff after a failure. Read its docstring before changing anything here.

    ⭐ The deadline is fetch_seconds PLUS UP TO 30 SECONDS OF JITTER, rolled once here and
    passed to both checks. See _interval() and JITTER_SECONDS.

    ⭐ RETURNS (record, reason) - the record IN MEMORY, so a caller never re-reads the file
    this function just read or wrote. Within one process the number is passed by value;
    token_usage.json exists for the CROSS-PROCESS hop only, which is the one that cannot be
    memory: the dispatch gate is a fresh process on every tool call and shares nothing with
    a long-running --watch.
    """
    due = _interval(cfg)                         # fetch_seconds + up to 30 s of jitter
    prev = read_json(cfg["token_usage_file"], None)
    if isinstance(prev, dict) and isinstance(prev.get("ts"), (int, float)):
        if (time.time() * 1000 - prev["ts"]) / 1000.0 < due:
            return prev, None                    # still fresh; spend no call
    if not _claim_attempt(sdir, due):
        return prev, None                        # someone else just tried; do not pile on
    got = fetch(cfg, sdir)
    if isinstance(got, str):
        _log_fetch(sdir, got)
        return prev, got                         # the OLD record survives a failure
    _write_record(sdir, cfg, got, prev)
    return got, None


def _log_fetch(sdir, reason):
    """One line per failed fetch. A silent instrument is the trap this plugin exists to
    avoid, and a persistent 429 with no record looks exactly like usage that stopped
    moving."""
    try:
        os.makedirs(sdir, exist_ok=True)
        with open(os.path.join(sdir, "fetch.log"), "a", encoding="utf-8") as f:
            f.write("%s %s%s" % (time.strftime("%Y-%m-%d %H:%M:%S"), reason, chr(10)))
    except OSError:
        pass


# --------------------------------------------------------------------------- collect

def _note_render(sdir, payload, five):
    """Record that a render happened, even when nothing changed.

    ⛔ Without this a repeated payload leaves no trace at all, and "which sessions are
    rendering?" becomes unanswerable exactly when it matters - when the number has stopped
    moving and you need to know whether the busy session is among them. One small rolling
    file, last 200 lines.
    """
    try:
        path = os.path.join(sdir, "renders.log")
        line = "%s %s %s%s" % (time.strftime("%Y-%m-%d %H:%M:%S"),
                               str(payload.get("session_id") or "?")[:8],
                               five.get("used_percentage"), chr(10))
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > 400:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines[-200:])
    except OSError:
        pass


def _age_note(record, cfg):
    """How stale the stored NUMBER is, or None while it is fresh enough to trust."""
    ts = (record or {}).get("ts")
    if not ts:
        return None
    age = (time.time() * 1000 - ts) / 60000.0
    return ("%d min old" % age) if age > cfg["stale_min"] else None


def _runnable(*args):
    """A command a model can actually RUN, with NO VERSION NUMBER IN IT.

    ⚠ A bare `usage.py --fetch-now` executes nowhere: the hook scripts are not executable and
    have no shebang association on either platform. ⛔ And a path built from this file's own
    location carries the plugin version, which stops being true at the next update - so it
    names the shim in the state directory instead. See hooks/shim.py.
    """
    import shim
    return shim.command(state_dir(), "usage.py", *args)


def collect(sdir, cfg):
    """statusLine mode: refresh the numbers if due, then print one short line.

    ⭐ THE USAGE NUMBERS NO LONGER COME FROM THE PAYLOAD. They are fetched from the API by
    ensure_fresh(), at most once per fetch_seconds however often Claude Code re-runs this.
    The payload is still read, but only for what the API does not carry and a person wants
    on the line anyway: the context window, the model and the effort.

    ⛔ WHY THE PAYLOAD WAS DROPPED AS A SOURCE rather than kept as a fallback. A session
    replays the `rate_limits` it last saw, so the payload can hold a value that is minutes
    or tens of minutes behind while looking current - measured at 6% against a true 22%,
    with a correct resets_at, so no staleness rule could have caught it. Falling back to it
    would let that stale number overwrite a fresh one, which is the whole defect this
    change removes. A missing number is safe; a confidently wrong low one is not.

    ⚠ The old guard against corruption by hand-run stdin is no longer needed here, because
    synthetic stdin can no longer influence a stored figure at all.
    """
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    # ⭐ The record comes back IN MEMORY - no second read of the file ensure_fresh just
    # touched. See its docstring for where a file is genuinely unavoidable.
    record, reason = ensure_fresh(sdir, cfg)
    record = record if isinstance(record, dict) else {}

    # ⚠ Surface a failure ONLY once the stored number has also gone stale. A single failed
    # fetch over a fresh cache is routine and saying so every minute trains the reader to
    # ignore the note that matters when the data really has stopped moving.
    note = _age_note(record, cfg)
    if note and reason:
        note = "%s; %s" % (note, reason)
    # ⛔ NO OAUTH NOTE HERE ANY MORE - the owner's instruction, 2026-08-29, first the
    # countdown and then the expired form: "「已過期」也不顯示". The bar carries numbers and
    # the reasons the numbers stopped; it is not where a token is reported.
    # ⚠ ONE OAUTH SENTENCE STILL REACHES THIS LINE, and deliberately. fetch() refuses to
    # spend a call on a token it can see is dead and returns that as its `reason`, which
    # arrives above - but only once the stored number has ALSO gone stale, which is the
    # moment the figures on screen are wrong. Suppressing it there would leave the display
    # confidently showing a number that stopped moving.

    _note_render(sdir, payload, record.get("five_hour") or {})
    # ⭐ ONE print PER ROW. Claude Code renders each line of this command's output as its own
    # row, so a second row needs nothing but a second print.
    for _row in line_rows(record, note, cfg, payload, burn=burn_triple(sdir, cfg, record)):
        print(_row)
    return 0


HISTORY_PREFIX = "token_usage_history_"

# ⭐ The debug response dump's prefix - same directory, same rotation, different file.
# ⛔ DELIBERATELY NOT the history file. History holds two percentages per row and is PARSED
# by _projection(); this holds whole response bodies for questions nobody has asked yet. One
# reader would choke on the other's lines, so they never share a file.
DEBUG_RESPONSE_PREFIX = "API_response_usage_"


def history_dir(sdir, cfg):
    """Where usage records live. Configurable; defaults to <state dir>/logs.

    ⭐ A directory of its own, because these files accumulate one per day - mixed in with
    config.json and the state folder they would bury the two files a person actually edits.
    Set `history_dir` in config.json to put them somewhere else entirely, such as a synced
    folder or a drive with room.

    ⚠ NO LONGER "FOREVER": `history_keep_days` removes whole files older than 30 days by
    default, and 0 restores the old keep-everything behaviour. ⛔ If you point this at a
    folder holding anything else, note that prune_logs() only ever deletes files carrying
    this plugin's own two prefixes - but check that before pointing it at a shared drive.
    """
    d = cfg.get("history_dir") or os.path.join(sdir, "logs")
    return os.path.abspath(os.path.expanduser(d))


def history_path(sdir, cfg, now=None, prefix=HISTORY_PREFIX):
    """Today's history file: token_usage_history_<YYYYMMDD-HHMMSS>.jsonl

    The stamp is when the FILE was started, in the same YYYYMMDD-HHMMSS form the task
    folders use, so one convention covers both. A new file begins at each local midnight:
    today's file is whichever existing one carries today's date, and a fresh stamp is
    minted when there is none.

    ⚠ Local midnight, not UTC. These are a person's usage records and they get read
    against a person's day.

    ⛔ A FILE IS NEVER TRIMMED. Dropping the early part of a day to satisfy a line count
    would quietly destroy the record it exists to keep, so a day's file is kept entire.
    ⚠ WHOLE FILES ARE DELETED BY AGE, THOUGH - see history_keep_days and prune_logs(). The
    two are not the same decision: trimming leaves a record that LOOKS complete and is not,
    while removing a whole day leaves nothing to misread.

    ⛔ AND THIS FUNCTION IS WHERE THAT DELETING HAPPENS, which is the one surprising thing
    about it: minting a new day's name is the only moment that occurs at most once a day
    per process, and it is exactly the moment every older file became a day older. Pruning
    on every append would stat the whole directory 640 times a day to remove nothing.

    ⭐ `prefix` is the ONLY thing the debug response dump (DEBUG_RESPONSE_PREFIX) changes
    about any of this, so this file has ONE rotation rule rather than two that can drift.
    """
    now = now if now is not None else time.time()
    d = history_dir(sdir, cfg)
    today = time.strftime("%Y%m%d", time.localtime(now))
    existing = sorted(glob.glob(os.path.join(d, prefix + today + "-*.jsonl")))
    if existing:
        return existing[-1]
    prune_logs(sdir, cfg, now)
    return os.path.join(d, prefix
                        + time.strftime("%Y%m%d-%H%M%S", time.localtime(now)) + ".jsonl")


def _history_stamp(path):
    """The YYYYMMDD-HHMMSS part of a history file name, whichever prefix it carries.

    ⛔ THE PREFIX IS STRIPPED BY NAME, NOT BY SPLITTING ON A SEPARATOR. The prefix carries the
    same separator the stamp does, so `split("_", 1)` would leave "usage_history_20260828-..."
    and sort by the word instead of by the date - an order with nothing to do with when the
    files were written, while _projection() reads the last two.
    """
    name = os.path.basename(path)
    if name.startswith(HISTORY_PREFIX):
        return name[len(HISTORY_PREFIX):]
    return name


def prune_logs(sdir, cfg, now=None):
    """Remove whole log files older than history_keep_days. Returns how many went.

    ⛔ ONLY THIS PLUGIN'S OWN FILES, matched on the two prefixes it writes. `history_dir`
    is configurable and the docs suggest pointing it at a synced folder or another drive,
    so a blanket sweep of *.jsonl there could delete somebody else's data. The prefixes are
    the whole safety argument for this function.

    ⛔ 0 KEEPS EVERYTHING, and so does any value _days() cannot read. A retention setting
    that guesses is a retention setting that deletes something nobody meant to lose.

    ⚠ AGE IS MTIME, not the stamp in the name. The name records when the file was STARTED;
    mtime records when it was last written, which is what a person means by "old". They
    differ by up to a day, and mtime is the later of the two - so this errs towards keeping.

    ⚠ Every failure is swallowed. A file that cannot be removed - open elsewhere, read-only,
    on a disconnected drive - must cost nothing: this runs inside the path that is about to
    write a usage record, and losing that record to a housekeeping error would be a bad
    trade.
    """
    # ⛔ COERCED HERE TOO, not only in config(). This function DELETES, so it must not
    # depend on somebody else having sanitised its input first: `cfg` reaches it through
    # history_path() from two writers, one of which passes `cfg or {}`, and a project-level
    # config or a hand-built dict can carry a raw string. Found by a check that passed
    # "abc" straight in and got a TypeError out of `days <= 0`.
    days = _days(cfg.get("history_keep_days"), HISTORY_KEEP_DAYS_DEFAULT)
    if days <= 0:
        return 0
    cutoff = (time.time() if now is None else now) - days * 86400
    d = history_dir(sdir, cfg)
    removed = 0
    # ⛔ ONLY THE TWO PREFIXES THIS PLUGIN WRITES. Never a sweep by extension: `history_dir`
    # is configurable and the docs suggest pointing it at a synced folder, where a blanket
    # *.jsonl delete would take somebody else's data with it.
    for pref in (HISTORY_PREFIX, DEBUG_RESPONSE_PREFIX):
        for path in glob.glob(os.path.join(d, pref + "*.jsonl")):
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    removed += 1
            except OSError:
                pass
    return removed


TIME_FMT = "%Y-%m-%d %H:%M:%S"


def stamp(epoch):
    """Epoch seconds -> "YYYY-MM-DD HH:MM:SS" in LOCAL time, or None.

    ⭐ The history is read by people, and an epoch integer is not readable. Local time,
    not UTC, for the same reason the files roll at local midnight: these are a person's
    records and get read against a person's day.

    ⚠ Tolerates milliseconds. claude-pacer stamps in milliseconds and this plugin in
    seconds; a row imported from there would otherwise land in the year 58000.
    """
    if not isinstance(epoch, (int, float)):
        return None
    if epoch > 1e12:
        epoch = epoch / 1000.0
    try:
        return time.strftime(TIME_FMT, time.localtime(epoch))
    except (ValueError, OSError):
        return None


def unstamp(value):
    """The inverse, tolerant of the numeric rows older files still contain."""
    if isinstance(value, (int, float)):
        return value / 1000.0 if value > 1e12 else value
    if isinstance(value, str):
        try:
            return time.mktime(time.strptime(value, TIME_FMT))
        except ValueError:
            return None
    return None


def _append_history(sdir, cfg, five, seven, model=None, session=None):
    """One sample per render, into today's file.

    Every time is written as a readable local timestamp rather than an epoch integer,
    and the seven-day window's reset is kept as well as its percentage - without it a
    row cannot be attributed to a particular weekly window when read back later.
    """
    sample = {"at": stamp(time.time()),
              "pct": five.get("used_percentage"),
              "resets_at": stamp(five.get("resets_at"))}
    if isinstance(seven, dict):
        sample["sd_pct"] = seven.get("used_percentage")
        sample["sd_resets"] = stamp(seven.get("resets_at"))
    # ⭐ Which model wrote this row. Every session renders its own statusline, so with
    # several sessions open the file interleaves rows from all of them - without this
    # there is no way to tell whose usage a row belongs to when reading it back.
    if model:
        sample["model"] = model
    # ⭐ WHICH session rendered this. Several sessions each render on their own timer, so
    # without it there is no way to tell whether the session actually burning the
    # allowance is among them - which is the whole question when the number stops moving.
    if session:
        sample["session"] = session
    try:
        os.makedirs(history_dir(sdir, cfg), exist_ok=True)
        with open(history_path(sdir, cfg), "a", encoding="utf-8") as f:
            f.write(json.dumps(sample, ensure_ascii=False) + chr(10))
    except OSError:
        pass


def _account_ids():
    """(organizationUuid, accountUuid) for a debug row. Either may be None.

    ⭐ POSITION 0 COMES FROM ~/.claude/.credentials.json, the file the access token itself
    came from, so it is authoritative about which account made the call. Measured
    2026-08-27: `organizationUuid` sits at the TOP LEVEL there, beside the `claudeAiOauth`
    block _token_and_expiry() already reads. One dictionary lookup, no new API call.

    ⛔ organizationUuid IDENTIFIES THE ORGANISATION, NOT THE SEAT. Two accounts inside one
    team share it - measured here organizationType `claude_team`, seatTier `team_tier_1` -
    and the owner switches BOTH between organisations AND between seats inside one, so the
    org id alone provably cannot answer "did these two rows come from the same account?".
    The per-seat `accountUuid` is in ~/.claude.json under `oauthAccount`.

    ⚠ THE TWO FILES ARE WRITTEN AT DIFFERENT MOMENTS. .credentials.json is rewritten when
    the token refreshes; ~/.claude.json's oauthAccount when the profile is fetched. After an
    account switch they can disagree, and a stale profile would attach the WRONG seat id to
    a response - worse than a missing one, because it looks valid. Both files carry
    organizationUuid, so they are cross-checked and the seat id is DROPPED on a mismatch.

    ⛔ A None in position 1 therefore means "this row cannot be tied to a seat". The row is
    still KEPT - never lose data - but a reader computing statistics must EXCLUDE it rather
    than average it in.

    ⚠ ~/.claude.json is about 55 KB and is read only from here, which runs only while the
    debug switch is on. Nothing extra is read when it is off.

    ⛔ NO emailAddress AND NO TOKEN EVER LEAVES THIS FUNCTION. oauthAccount carries an email
    address beside the uuid; accountUuid identifies the seat without putting a personal
    address into a log file that gets copied around.
    """
    # ⚠ $ANTHROPIC_TOKEN WINS IN _token_and_expiry(), and on that path the credentials file
    # is never opened - so it is not the source of the token in hand and its organizationUuid
    # may describe a different account entirely. That is the same "looks valid but is wrong"
    # failure the cross-check below exists to prevent, so it gets the same answer: nothing.
    env = os.environ.get("ANTHROPIC_TOKEN")
    if env and env.strip():
        return None, None
    home = os.path.expanduser("~")
    cred = read_json(os.path.join(home, ".claude", ".credentials.json"), {}) or {}
    org = cred.get("organizationUuid") if isinstance(cred, dict) else None
    org = org if isinstance(org, str) and org else None
    prof = read_json(os.path.join(home, ".claude.json"), {}) or {}
    acct = prof.get("oauthAccount") if isinstance(prof, dict) else None
    acct = acct if isinstance(acct, dict) else {}
    seat = acct.get("accountUuid")
    seat = seat if isinstance(seat, str) and seat else None
    # ⛔ Including the case where the credentials file carries no org id at all: with
    # nothing to confirm the profile file against, the seat it names cannot be trusted.
    if org is None or acct.get("organizationUuid") != org:
        seat = None
    return org, seat


def _dump_response(sdir, cfg, data):
    """debug.API_response_usage: keep the WHOLE response body, and never break a fetch.

    One JSON array per line, appended to <history_dir>/API_response_usage_<YYYYMMDD-HHMMSS>.jsonl:

        [organizationUuid, accountUuid, "2026-08-27T09:45:00+00:00", {...the response...}]

    ⛔ POSITION 3 IS THE RAW PARSED BODY - not trimmed, not reshaped, no key dropped for
    looking useless. The entire point is that a field nobody valued turns out to be the
    evidence later: `resets_at: null` beside `utilization: 0.0` was measured on 2026-08-27
    and is what says "no usage YET in this window", which is the only way to find when work
    actually began inside one. ⚠ That is a property of a SEQUENCE of responses, which no
    single response and nothing else this plugin stores can answer.

    ⚠ POSITION 2 IS NOT OPTIONAL. The filename records when the FILE was started, not when
    each call happened, and statistics need a per-line instant.

    ⛔ EVERY FAILURE IS SWALLOWED. This file's rule is that every failure ends as "no
    number", never as a wrong number and never as a crash - so a full disk or a permission
    error while writing a DIAGNOSTIC must not cost the brake its reading.
    """
    try:
        org, seat = _account_ids()
        row = [org, seat,
               datetime.datetime.now(datetime.timezone.utc).isoformat(), data]
        os.makedirs(history_dir(sdir, cfg), exist_ok=True)
        with open(history_path(sdir, cfg, prefix=DEBUG_RESPONSE_PREFIX), "a",
                  encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + chr(10))
    except Exception:
        pass


BAR_FULL, BAR_EMPTY = "▓", "░"      # single-width blocks; CJK would misalign

# ⛔ ONE WIDTH FOR ALL THREE SEGMENTS. The 5h and 7d bars were 6 cells and Ctx was 4,
# written as separate literals, which is how they drifted apart in the first place. A bar
# exists to be compared at a glance, and two bars of different lengths cannot be: the same
# fill ratio does not look like the same length.
BAR_WIDTH = 9

# ⚠ Colour thresholds are about ATTENTION and are deliberately NOT soft_pct/hard_pct.
# Those decide what the gate DOES; a person wants a warning colour a little before
# anything starts being refused. Override with colour_warn_pct / colour_alarm_pct, or set
# colour:false - a terminal that does not understand ANSI would otherwise print the
# escape codes as visible rubbish.
ANSI = {"reset": "\033[0m",
        "ok": "\033[32m",          # green
        "warn": "\033[38;5;208m",  # orange, 256-colour
        "alarm": "\033[31m"}       # red


def _colour(pct, cfg):
    if not cfg.get("colour", True):
        return "", ""
    if pct >= cfg.get("colour_alarm_pct", 90):
        key = "alarm"
    elif pct >= cfg.get("colour_warn_pct", 70):
        key = "warn"
    else:
        key = "ok"
    return ANSI[key], ANSI["reset"]


BAR_MARK = "┃"    # the elapsed-time marker
# Module-level because _bar is called from several places and threading a flag through
# all of them for one boolean is noise. Set from config once, at entry.
SHOW_MARK = [True]


def _bar(pct, width=None, time_pct=None):
    """A proportional bar, optionally carrying an elapsed-time marker.

    ⭐ The marker is the cleverest thing in claude-pacer and is worth having: it shows how
    far through the WINDOW you are, beside how much you have SPENT. Fill ahead of the
    marker means burning faster than the clock; behind it means there is slack. A bare
    percentage cannot say that.

    ⚠ It is inserted BETWEEN cells, so the bar renders one column wider rather than
    replacing a cell. Replacing one was a real bug in that project (v0.1.1): the filled
    proportion then reads a cell short and the number beside it disagrees with the bar.

    ⚠ Single-width glyphs only. A CJK block counts as two terminal columns and the bar
    drifts out of alignment with everything beside it.
    """
    width = BAR_WIDTH if width is None else width
    filled = int(round(max(0.0, min(100.0, pct)) / 100.0 * width))
    cells = [BAR_FULL] * filled + [BAR_EMPTY] * (width - filled)
    if isinstance(time_pct, (int, float)) and SHOW_MARK[0]:
        at = int(round(max(0.0, min(100.0, time_pct)) / 100.0 * width))
        cells.insert(at, BAR_MARK)
    return "".join(cells)


def duration(mins):
    """Minutes as the largest units that fit, hyphenated: 9m, 3h-5m, 4d-4h-7m.

    ⚠ Hours alone stop being readable past a day - the seven-day window routinely shows a
    three-digit hour count, and "100h24m" is arithmetic the reader has to do. Hyphens and
    no zero padding, because "4d04h07m" reads as one long number and "4d-4h-7m" reads as
    three separate quantities, which is what it is.
    """
    mins = max(0, int(mins))
    if mins < 60:
        return "%dm" % mins
    if mins < 1440:
        return "%dh-%dm" % (mins // 60, mins % 60)
    return "%dd-%dh-%dm" % (mins // 1440, (mins % 1440) // 60, mins % 60)


def _window(label, win, now, cfg=None, window_secs=None, stale=False):
    """One window's bar, percentage and time remaining - or dashes.

    ⛔ A STALE NUMBER IS NOT SHOWN AS A NUMBER. Measured 2026-08-26: the display read 74%
    while the account page read 93%, because the only session rendering the statusline was
    an idle one replaying the rate_limits it last received. A percentage on screen is read
    as the current percentage - nobody reads it as "the last value some session happened to
    see" - so showing it is worse than showing nothing. Under-reading is the dangerous
    direction: it is exactly when the brake should fire that a frozen number holds it off.

    ⚠ This cannot be fixed here, only reported. Nothing but Claude Code's own statusline
    invocation delivers the numbers, and it delivers whatever that session last saw.

    Set stale_hides_numbers:false to show the old value anyway; the age is always printed.
    """
    cfg = cfg or {}
    have = isinstance(win, dict) and isinstance(win.get("used_percentage"), (int, float))
    resets = win.get("resets_at") if isinstance(win, dict) else None

    # ⛔ A WINDOW THAT HAS ALREADY TURNED OVER makes its stored percentage meaningless,
    # and meaningless in the worst direction: it reads HIGH. Measured 2026-08-26 - the
    # window reset at 14:00, the account page went to 0%, and the display still showed
    # 97% because nothing had rendered since. The verdict already knew (it returns GO past
    # a reset); the display did not, so the two disagreed with each other.
    # ⇒ Past the reset, show dashes until a render brings a real number for the new window.
    reset_passed = bool(resets) and now >= resets
    if not have or reset_passed or (stale and cfg.get("stale_hides_numbers", True)):
        # ⚠ One cell wider than BAR_WIDTH, to stand where the time marker would: a bar that
        # changed length when it lost its number would make the line jump.
        return "%s %s %s" % (label, BAR_EMPTY * (BAR_WIDTH + 1), "--")

    pct = win["used_percentage"]
    time_pct = None
    if resets and window_secs:
        time_pct = 100.0 * (1.0 - (resets - now) / float(window_secs))
    on, off = _colour(pct, cfg)
    out = "%s %s%s %d%%%s" % (label, on, _bar(pct, BAR_WIDTH, time_pct), round(pct), off)
    if resets:
        out += " " + duration((resets - now) / 60)
    return out


# ⭐ THE WORD THAT REPLACES THE VERDICT WHILE NOTHING IS HAPPENING. Display only - see
# _watch_line() for why it must never reach verdict(). Upper case like GO, PACE and STOP:
# it stands in the same column and means the same kind of thing.
SLEEP_WORD = "SLEEP"


def _watch_open(scroll):
    """The bytes to emit once, before the first draw. Empty when scrolling.

    ⛔ THE RESIDUE THIS REMOVES IS NOT THIS PROCESS'S. A rewriting watcher overwrites its own
    row for ever, so the row it starts on is the only one it can reach - and the line left
    behind by the PREVIOUS run sits above that, out of reach, for the life of the terminal.
    Seen in a screenshot: a one-row draw from the old version stranded above a two-row draw
    from the new one, which reads as the two-row layout being broken when it is not.

    ⭐ CLEARING IS SAFE HERE PRECISELY BECAUSE IT REWRITES. A surface that rewrites one row
    has no scrollback worth keeping; anybody who wants the history passes `--scroll`, and
    that path emits nothing from here. ⚠ It also takes the task's "Executing task" header
    with it, which is the cost, and the reason this is tied to rewriting rather than done
    unconditionally.
    """
    # ⛔ AND AUTO-WRAP OFF (DECAWM, `?7l`), which is the fix for the residue that survived
    # both the clear and the fixed row count. A row as wide as the panel - or wider - is
    # wrapped by the TERMINAL onto a second visual row, and `\033[1A` then climbs one VISUAL
    # row rather than one logical one: it lands mid-line, `\r` returns to the start of the
    # wrong row, and the top half is left on screen for ever. ⚠ Fitting cannot rule this out,
    # because the width may be wrong (a resize between measuring and writing) or unknowable
    # (COLUMNS unset and no tty size). With wrapping off the terminal truncates at the margin
    # instead and the cursor stays on the row it was on, so the climb cannot be wrong.
    return "" if scroll else "\033[2J\033[H\033[?7l"


def _watch_close(scroll):
    """The bytes that hand the terminal back. Empty when scrolling.

    ⛔ AUTO-WRAP IS THE TERMINAL'S MODE, NOT THIS PROCESS'S. Left off it stays off for
    whatever runs next there - a shell whose own commands then vanish at the right margin.
    Restoring it is giving back something borrowed, not tidiness.
    """
    return "" if scroll else "\033[?7h"


def _redraw(lines, erase="\033[K"):
    """Every row, drawn from the top-left of the screen the watcher cleared and owns.

    ⛔ WHY THIS REPLACED A RELATIVE CLIMB, after three attempts that did not. `\033[1A` moves
    up one row from WHEREVER THE CURSOR IS, so it is only correct while nothing else has moved
    it - and inside a VS Code panel that is not something this process controls. Measured
    2026-08-29: with the row count fixed at two and wrapping disabled, the FIRST draw was
    still stranded, every later draw overwriting the second row cleanly. ⇒ The cursor was one
    row lower than the arithmetic believed before the second draw ever ran, and no amount of
    fixing the arithmetic reaches that.

    ⭐ AN ABSOLUTE HOME CANNOT BE WRONG. `\033[H` is row 1, column 1 of the screen - not a
    displacement from anywhere - so it does not matter what moved the cursor, how wide the
    rows were, or how many were drawn last time. ⚠ It is legitimate ONLY because the watcher
    cleared the screen at startup and redraws all of it every time; a program sharing a
    terminal must never do this.

    ⭐ `\033[J` AT THE END erases from the cursor to the bottom of the screen, which is what
    makes a shrinking draw safe without counting anything. The old code padded with blank
    rows to do this, and the padding had to know the previous height.
    """
    body = "\n".join("\r" + one + erase for one in lines)
    return "\033[H" + body + "\033[J"


def _watch_line(stamp, data, v, note, cfg, idle=False, burn=None):
    """The row(s) `--watch` prints, fitted to the terminal ONCE. A list; pure, no I/O.

    ⛔ THE BUG THIS FUNCTION EXISTS FOR. `_line()` fits ITSELF to the terminal width - and
    the watcher then prepended a timestamp and appended the verdict word, sixteen columns
    nobody had subtracted. MEASURED at width 150: `_line` returned 149 characters and the
    line that reached the terminal was 165. ⇒ It wrapped; `\r` returns to the start of the
    LAST VISUAL ROW and `\033[K` clears only that row, so every render stranded its first
    row on screen for ever. That is the residue in the owner's screenshot, and it is why the
    whole thing is assembled in one place that owns the width.

    ⭐ AND WHY IT RETURNS A LIST. When everything will not fit on one row, the answer used to
    be to DROP the least valuable parts. A terminal has more rows, so the second one is spent
    instead: the usage bars and the verdict stay together on the first, the context bar, the
    model and the note move to the second. ⚠ Each row is fitted separately - two rows that
    can each wrap is the original defect twice over.

    ⭐ IDLE KEEPS THE FIGURES AND DROPS THE COLOUR. A frozen percentage is dangerous when a
    FETCH is failing; while nobody is working nobody is spending, so it cannot drift. The
    exposure is the moment work resumes, and should_fetch() starts fetching at that same
    moment. `SLEEP` is what says the row is not live. ⚠ watch() also stops redrawing while
    idle - see there - so this is called ONCE per quiet spell.

    ⛔ AND `SLEEP` NEVER REACHES verdict(). The gate reads verdict() for GO/PACE/STOP; a
    fourth word arriving from the display side would be a word the dispatch logic does not
    know. This substitution is local to the watcher's screen.
    """
    word = SLEEP_WORD if idle else v["verdict"]
    lcfg = dict(cfg)
    if idle:
        # ⭐ ONE key carries the whole idle appearance: _colour() already honours it, so "no
        # colour anywhere" costs a setting rather than a second code path.
        lcfg["colour"] = False
    von, voff = _colour(v.get("pct") if isinstance(v.get("pct"), (int, float)) else 0, lcfg)
    head = "%s  " % stamp
    tail = "  %s%s%s  " % (von, word, voff)
    windows, extras = _line_parts(data, note, lcfg, None,
                                  stale=False if idle else None, burn=burn)
    # ⭐ THE WATCHER BREAKS AFTER THE LAST USAGE WINDOW, and Burn opens the second row.
    # The owner's instruction, and it fixes the defect measured in 0.40.7: on a panel under
    # 141 columns the gauge was silently dropped, so "no Burn" meant either "no data" or
    # "too narrow" and the screen could not tell you which. Given a row of its own it is
    # always there.
    # ⛔ AND THE ROW COUNT NEVER CHANGES, which is the whole point rather than a detail.
    # Before a burn rate exists the gauge was omitted and the watcher drew ONE row; the first
    # draw after it appeared drew TWO, and that 1-to-2 transition is where a stranded line
    # comes from - twice in the owner's screenshots. The cursor arithmetic for growth is
    # correct and pinned, but it depends on the terminal not having moved the cursor in
    # between, and in a VS Code panel that is not something this process controls.
    # ⇒ REMOVE THE TRANSITION. `_burn_part(None, ...)` already draws "no data yet" as dashes,
    # exactly as the statusline does, so there is always a segment to move and always two
    # rows. ⚠ This also makes the gauge's absence impossible to misread: it is either a rate
    # or dashes, never a missing row.
    # ⚠ WATCHER ONLY, by the owner's instruction - not because the statusline cannot do it.
    # line_rows() measured that Claude Code splits the command's output on newlines and
    # counts them, so a statusline may be two rows; it simply is not asked to spend one.
    if not (windows and windows[-1].startswith("Burn")):
        windows.append(_burn_part(None, None, None, lcfg))
    extras.insert(0, windows.pop())
    return _rows(windows, extras, terminal_width(cfg), head, tail,
                 cfg.get("two_rows", True), always_split=True)


# The payload key that carries context usage. ⭐ Named once because Part B turns its
# PRESENCE into the difference between "zero" and "unknown".
CONTEXT_KEY = "context_window"


def _context_pct(payload):
    """Context-window usage as a percentage, or None when it cannot be read.

    ⛔ ZERO AND UNKNOWN ARE DIFFERENT ANSWERS, and the difference is decided by whether the
    KEY IS THERE - never by whether the value is falsy. Rendering "I cannot read this" as 0%
    is a confident wrong answer, and it errs LOW, the same direction _api_window() refuses a
    reading whose scale it cannot establish.

    ⭐ MEASURED, NOT ASSUMED (Claude Code 2.1.246, read out of the shipped binary). The
    statusline payload is built as `context_window: a6e(w, I)`, an UNCONDITIONAL field -
    unlike `rate_limits`, which is spread in only when a window exists. And a6e() always
    emits `used_percentage`, with `current_usage: null` and `total_input_tokens: 0` when
    there are no messages yet. The binary's own documentation of the field says
    `Context: $used% used`, so the scale is whole percent, not a fraction. ⇒ So:

      key absent            -> not a statusline payload at all, or the field was renamed.
                               Unknown. Draw dashes.
      key present, no work  -> `current_usage` is null. A real zero. Draw an empty bar.
      key present, a value  -> draw it.
      key present, garbage  -> unknown again. The shape changed under us, and guessing zero
                               would hide that behind a plausible-looking bar.
    """
    if not isinstance(payload, dict) or CONTEXT_KEY not in payload:
        return None
    cw = payload.get(CONTEXT_KEY)
    if not isinstance(cw, dict):
        return None
    pct = cw.get("used_percentage")
    if isinstance(pct, (int, float)) and not isinstance(pct, bool):
        return float(pct)
    # ⚠ The fallback matters: all three token counts have to be added, or the number reads
    # far too low. It is kept for payloads that carry the counts but not the percentage.
    u, size = cw.get("current_usage"), cw.get("context_window_size")
    if isinstance(u, dict) and isinstance(size, (int, float)) and size:
        used = (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) \
               + (u.get("cache_creation_input_tokens") or 0)
        return 100.0 * used / size
    if u is None:
        return 0.0        # ⭐ "no messages yet" - a known answer, and its value is zero
    return None


def _model_part(payload):
    m = payload.get("model") or {}
    name = m.get("display_name") or m.get("id")
    if not name:
        return None
    eff = (payload.get("effort") or {}).get("level")
    return "%s%s" % (name, "·" + eff if eff else "")


# ⛔ ONE definition. A second copy of this pattern is a second chance to get it wrong, and
# getting it wrong means truncating INSIDE an escape sequence - which garbles a terminal
# rather than tidying it.
_STRIP_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _visible_len(text):
    """Length as the terminal sees it: ANSI codes occupy no columns."""
    return len(_STRIP_ANSI.sub("", text))


def terminal_width(cfg):
    """Columns available, or None if unknowable.

    ⚠ Claude Code sets $COLUMNS for the statusline; a plain terminal may not. An unknown
    width must never shrink the line - guessing narrow and dropping information would be
    worse than a wrap, so None means render everything.
    """
    w = cfg.get("width")
    if isinstance(w, int) and w > 10:
        return w
    for src in (os.environ.get("COLUMNS"),):
        try:
            n = int(src)
            if n > 10:
                return n
        except (TypeError, ValueError):
            pass
    try:
        n = shutil.get_terminal_size(fallback=(0, 0)).columns
        return n if n > 10 else None
    except Exception:
        return None


def _rows(windows, extras, width, head="", tail="", two_rows=True, always_split=False):
    """The row(s) to draw: one when everything fits, two when it does not and `two_rows`.

    ⭐ ONE SPLITTER FOR BOTH SURFACES. The watcher and the statusline had different ideas
    about what to do with a line that will not fit - the watcher spent a second row, the
    statusline threw the least valuable parts away - and two answers to one question drift.
    `head` and `tail` are what the caller wraps around the middle (a timestamp and a verdict
    word, for the watcher; nothing, for the statusline).

    ⛔ THE BUDGETS ARE PER ROW, and each subtracts what surrounds it. Fitting the middle and
    then adding the wrapper around it is the measured defect this whole area came from: at
    width 150 the middle came back 149 characters and the line was 165.

    ⚠ `two_rows` false keeps the old behaviour exactly - one row, packed, and whatever does
    not fit is dropped from the right. A second row costs a row of the terminal, and on a
    narrow one that is a row of conversation; the owner decides.

    ⭐ `always_split` spends the second row even when everything WOULD fit. The watcher asks
    for it so the burn gauge has a fixed home instead of appearing and vanishing with the
    terminal width - a segment that moves is a segment nobody trusts. ⚠ The statusline does
    NOT ask for it, and the reason is the owner's instruction rather than a platform limit:
    a statusline CAN be two rows - see line_rows(), where that was measured out of the
    shipped binary - it simply is not made to spend one it does not need.
    """
    if not width:
        # ⚠ A forced split has to survive here too, or the second row would appear only on
        # terminals whose width could be detected - which is the machines, not the intent.
        if always_split and two_rows and extras:
            return [head + _fit(windows, None) + tail,
                    " " * _second_row_indent(head, windows, extras) + _fit(extras, None)]
        return [head + _fit(windows + extras, None) + tail]
    one = head + _fit(windows + extras, None) + tail
    if not always_split and _visible_len(one) <= width:
        return [one]
    # ⚠ With nothing to move to a second row there is nothing to split, so the single row is
    # cut instead. Dropping the only content would leave an empty display.
    if not two_rows or not extras:
        return [_cut(head + _fit(windows + extras, width - _visible_len(head)
                                 - _visible_len(tail)) + tail, width)]
    room = width - _visible_len(head) - _visible_len(tail)
    first = _cut(head + _fit(windows, room) + tail, width)
    pad = " " * _second_row_indent(head, windows, extras)
    second = _cut(pad + _fit(extras, width - len(pad)), width)
    return [first, second] if second.strip() else [first]


def _bar_col(part):
    """Which column a segment's bar starts in, or None if it has no bar.

    ⚠ ANSI first. A coloured segment carries escape bytes before the bar, and counting those
    as columns puts the answer several places to the right of where the eye sees it.
    """
    plain = _STRIP_ANSI.sub("", part or "")
    for i, ch in enumerate(plain):
        if ch in (BAR_FULL, BAR_EMPTY, BAR_MARK, "─"):
            return i
    return None


def _second_row_indent(head, windows, extras):
    """Columns of padding that put the second row's bar under the first row's bar.

    ⛔ THE OLD RULE WAS "indent by the head", and it does not align anything: the labels are
    different lengths (`5h` against `Burn`), so the bars landed two columns apart and the
    two rows read as two unrelated lines. ⭐ Measured from the STRINGS rather than from a
    table of label widths, so a new label needs nothing added here.

    ⚠ Never negative, and never less than nothing: a second row pulled left of column zero
    would collide with the timestamp above it rather than line up with it.
    """
    base = _visible_len(head)
    top, bottom = _bar_col(windows[0] if windows else None), _bar_col(extras[0] if extras
                                                                     else None)
    if top is None or bottom is None:
        return base
    return max(0, base + top - bottom)


def _cut(text, width):
    """`text` shortened to `width` COLUMNS, never mid-escape-sequence.

    ⛔ THE LAST GUARD, AND IT IS NOT REDUNDANT WITH _fit(). That function drops whole parts
    and never drops the last one, so a single part wider than the terminal - a long note on
    a narrow window - survives and overflows. One column too many wraps the row, and a
    wrapped row is what `\r` can never repair.

    ⚠ IT CUTS THE PLAIN TEXT AND RE-CLOSES THE COLOUR. Slicing a string full of `\033[32m`
    by length would eventually land INSIDE an escape sequence, and a half-written escape
    garbles a terminal rather than tidying it.
    """
    if not width or _visible_len(text) <= width:
        return text
    plain = _STRIP_ANSI.sub("", text)[:width]
    return plain + (ANSI["reset"] if _STRIP_ANSI.search(text) else "")


def _burn_part(burn, remain, rate, cfg, stale=False):
    """`Burn ▓▓▓▓░░░░░░ 1.20%/m · 44m left` - how long the budget lasts, and how fast.

    ⭐ IT ANSWERS ONE FORWARD-LOOKING QUESTION: can I keep spending? The bar is the budget's
    life measured against the TIME LEFT IN THE WINDOW, so a full bar means "this window
    resets before you run dry" and half a bar means "you get halfway". ⚠ It is a RATIO, not
    a stock - unlike a health bar it goes back UP when the burn slows, because the thing it
    measures is whether the two clocks cross, not how much is left in a tank.
    ⛔ Deliberately NOT the historical rate profile, which was the first design. A sparkline
    of past samples answers "how fast was I going", and the question is "how long have I
    got" - and worse, history rows are written only when a number MOVES, so a quiet hour
    does not draw a low bar, it draws nothing at all. The axis looked like time and was not.

    ⛔ UNKNOWABLE IS NEVER DRAWN AS ZERO OR AS EMPTY. No history, one sample, under five
    minutes of span, a flat or falling rate - all of them mean the rate cannot be computed,
    and an empty bar in a column where empty means DANGER would read as the opposite. It
    gets its own glyph and its own words.

    ⚠ COLOUR IS INVERTED HERE and does not use _colour(). Everywhere else a HIGH percentage
    is bad; here a high ratio is good, so the same thresholds would paint safety red.
    """
    if not cfg.get("colour", True):
        on = off = ""
    else:
        on = off = None                        # decided below, once the state is known
    if stale or burn is None or not remain:
        # ⚠ `--` matches every other segment's "no usable number", and the dashes are a
        # different glyph from an empty bar on purpose.
        return "Burn %s %s" % ("─" * (BAR_WIDTH + 1), "--")
    ratio = burn / float(remain)
    # ⚠ BAR_WIDTH + 1, exactly like the Ctx segment. The three usage bars carry the elapsed
    # marker, which sits BETWEEN cells and so costs them one extra column; a bar without one
    # is a column narrower and will not line up under them. Widening here is what lets the
    # watcher's second row sit squarely beneath the first.
    width = BAR_WIDTH + 1
    filled = min(width, int(round(min(ratio, 1.0) * width)))
    bar = BAR_FULL * filled + BAR_EMPTY * (width - filled)
    if on is None:
        key = "ok" if ratio >= 1 else ("alarm" if ratio < 0.5 else "warn")
        on, off = ANSI[key], ANSI["reset"]
    # ⛔ ALWAYS A TIME, NEVER WORDS. The owner's instruction: "outlasts reset" cost
    # fourteen columns to say something the BAR already says - a full bar IS "the reset
    # arrives first" - and it made the reader translate a phrase into a number anyway.
    # ⚠ So this can now print a time LONGER than the window has left, and that is the
    # honest reading: it is when the burn-out lands, not a promise you will get there.
    tail = "%s left" % duration(burn)
    rate_s = "%.2f%%/m " % rate if rate else ""
    return "Burn %s%s%s %s· %s" % (on, bar, off, rate_s, tail)


def _fit(parts, width, keep=1):
    """Join `parts` with two spaces, dropping from the RIGHT until it fits `width`.

    ⭐ The rightmost parts are the least load-bearing, and `keep` is how many may never be
    dropped - one, normally, because the five-hour window is what the brake acts on and a
    line without it says nothing.
    """
    parts = [p for p in parts if p]
    if not width:
        return "  ".join(parts)
    while len(parts) > keep and _visible_len("  ".join(parts)) > width:
        parts.pop()
    return "  ".join(parts)


def _line_parts(record, stale_note=None, cfg=None, payload=None, stale=None, burn=None):
    """(windows, extras) - every segment of the line, in falling order of worth.

    ⭐ SPLIT OUT SO A CALLER CAN PUT THEM ON TWO ROWS. `_line()` joins them into one and
    drops what does not fit, which is right for a statusline that owns a single row; the
    watcher owns a terminal and can spend a second one rather than throw information away.
    ⇒ `windows` are the usage bars and must stay together; `extras` are the context bar, the
    model and the note, which are the ones worth moving.
    """
    rec = record or {}
    cfg = cfg or {}
    now = time.time()
    # ⛔ One decision, applied to both windows: is the stored value old enough that showing
    # it as a percentage would mislead? By default that is "there is a note", which the
    # caller sets from the file's age; a caller that knows better says so explicitly.
    stale = bool(stale_note) if stale is None else bool(stale)
    parts = [_window("5h", rec.get("five_hour"), now, cfg, 5 * 3600, stale)]
    if isinstance(rec.get("seven_day"), dict):
        parts.append(_window("7d", rec["seven_day"], now, cfg, 7 * 86400, stale))
    # ⭐ THE MODEL-SCOPED WINDOW, when the account has one running. It goes THROUGH _window()
    # like the other two, so staleness, the idle rule and the past-a-reset rule all apply to
    # it identically - a bar that degraded differently would be the one bar that lies.
    # ⚠ Its window length is the WEEKLY one: measured, the scoped reset lands one second
    # before the same account's weekly_all reset, so it rides that boundary rather than
    # running a clock of its own.
    sc = rec.get("scoped")
    if isinstance(sc, dict) and isinstance(sc.get("label"), str):
        parts.append(_window(sc["label"], sc, now, cfg, 7 * 86400, stale))
    # ⭐ ON THE FIRST ROW, after the windows: it is a decision input like they are, not
    # context like the model name. ⚠ Last of the four, so a narrow terminal drops it before
    # any usage bar - the five-hour window is what the brake acts on.
    if burn is not None and cfg.get("show_burn", True):
        parts.append(_burn_part(burn[0], burn[1], burn[2], cfg, stale))
    extras = []
    if payload and cfg.get("show_context", True):
        # ⛔ ALWAYS DRAWN, from the first moment of a session. It used to appear only once
        # work had begun, so the line changed width partway through and the reader could
        # not tell "this interface has no such thing" from "this session has not started".
        # A bar growing from zero says the second; a missing segment says neither.
        # ⚠ The trailing space is deliberate: 5h and 7d carry the time marker, which sits
        # BETWEEN cells and so costs them one extra column. Padding here keeps all three
        # bars occupying the same columns, which is the entire point of giving them one
        # width. The marker is NOT given a cell to even this up - see _bar().
        # ⚠ ONE space before the number, exactly like 5h and 7d. Two used to sit there as a
        # pad, to make up the column the time marker costs the other two segments - but two
        # spaces is the separator BETWEEN segments in this line, so using it inside one made
        # `Ctx` read as two items. The bar carries the extra cell instead: BAR_WIDTH + 1 is
        # the same width the marker'd bars occupy, so the columns still line up.
        cpct = _context_pct(payload)
        if cpct is None:
            extras.append("Ctx %s %s" % (BAR_EMPTY * (BAR_WIDTH + 1), "--"))
        else:
            on, off = _colour(cpct, cfg)
            extras.append("Ctx %s%s %d%%%s"
                          % (on, _bar(cpct, BAR_WIDTH + 1), round(cpct), off))
    # ⛔ THE NOTE OUTRANKS THE MODEL NAME, and it used to be the other way round. Parts are
    # dropped from the RIGHT when they do not fit, so with the model last a narrow display
    # kept the label "Opus 5" and threw away "OAuth token EXPIRED" - that particular note is
    # gone now, but "12 min old" and a fetch failure still arrive here. ⇒ A warning beats a
    # caption: the note says something is wrong, the model name says what was already known.
    if stale_note:
        extras.append("(%s)" % stale_note)
    if payload and cfg.get("show_model", True):
        mp = _model_part(payload)
        if mp:
            extras.append(mp)
    return parts, extras


def line_rows(record, stale_note=None, cfg=None, payload=None, stale=None, burn=None):
    """The statusline's row(s). ⭐ Claude Code prints one row per line of output.

    ⛔ MEASURED, not assumed, because this used to be capped at one row on a belief. The
    documentation says "each `echo` or `print` statement displays as a separate row", and the
    shipped binary splits the command's output on newlines and counts them
    (`line_count: ge.length`). ⇒ A statusline may be two rows, and throwing information away
    to fit one was this plugin's limitation rather than the platform's.

    ⚠ `two_rows: false` returns to one packed row. A second row costs a row of the terminal
    above the input box, which on a narrow one is a row of conversation.
    """
    windows, extras = _line_parts(record, stale_note, cfg, payload, stale, burn)
    cfg = cfg or {}
    return _rows(windows, extras, terminal_width(cfg),
                 two_rows=cfg.get("two_rows", True))


def _line(record, stale_note=None, cfg=None, payload=None, stale=None, burn=None):
    """One rendered line, trimmed from the right until it fits.

    ⛔ WRAPPING IS WHY THIS EXISTS. A status line that spills onto a second row does not
    merely look untidy - it pushes the prompt around and reads as a bug. claude-pacer solved
    it with three responsive layouts and width probing; that is the large half of that
    project. This does the small version: parts are ordered by how much they are worth, and
    the least valuable are dropped until the line fits.

    ⭐ `stale` SEPARATES THE NOTE FROM THE JUDGEMENT, for one caller. A note used to MEAN
    stale - and while the watcher is idle there is a note to show with nothing stale about
    it: nobody is spending, so the number cannot drift. ⛔ Left coupled, the idle line threw
    its percentages away and printed `--`, which is how the owner found it.
    """
    windows, extras = _line_parts(record, stale_note, cfg, payload, stale, burn)
    return _fit(windows + extras, terminal_width(cfg))


# --------------------------------------------------------------------------- verdict

def verdict(sdir, cfg, now=None, data=None):
    """GO / PACE / STOP / NO-DATA, with the reasoning that makes each one correct.

    ⛔ This is the ONLY sanctioned way to interpret the numbers. Three things are got
    wrong when an agent reads token_usage.json directly, and all three are handled here:
    reset arithmetic, seven-day false alarms, and burn projection.
    """
    now = now if now is not None else time.time()
    # ⚠ `data` is an INTERNAL shortcut for a caller in this file that has just read or
    # written the record - it saves re-reading a file whose contents it already holds. An
    # outside caller must omit it: the point of this function is that it reads the stored
    # record itself, and letting a stranger supply one would let a stranger supply a wrong
    # one. dispatch_gate.py deliberately does not pass it.
    # ⚠ An EMPTY dict falls through to the file, not to NO-DATA. `{}` is a dict, so an
    # isinstance test alone would accept it as "the caller supplied a record" and answer
    # NO-DATA while a perfectly good token_usage.json sat on disk - a brake reading unknown
    # because of a bookkeeping slip. A caller with nothing to offer must be indistinguish-
    # able from one that offered nothing.
    data = data if (isinstance(data, dict) and data) else read_json(cfg["token_usage_file"])
    if not data or not isinstance(data.get("five_hour"), dict):
        return {"verdict": "NO-DATA", "exit": 3,
                "text": "NO-DATA: no five_hour block. Nothing has fetched YET - the "
                        "dispatch gate starts a background refresh when it sees this, so "
                        "it normally clears by itself within seconds. If it never clears, "
                        "the fetch is failing rather than pending: run `%s` "
                        "for the reason in one line, and check fetch.log in "
                        "the state directory. Report usage as UNKNOWN - never a number."
                        % _runnable("--fetch-now")}

    five = data["five_hour"]
    pct, resets = five.get("used_percentage"), five.get("resets_at")
    if not isinstance(pct, (int, float)) or not resets:
        return {"verdict": "NO-DATA", "exit": 3,
                "text": "NO-DATA: five_hour present but incomplete. Report usage as UNKNOWN."}

    age_min = (now * 1000 - data.get("ts", 0)) / 60000.0

    seven = data.get("seven_day") if isinstance(data.get("seven_day"), dict) else None
    pct7 = (seven or {}).get("used_percentage")
    resets7 = (seven or {}).get("resets_at")

    # ⚠ A window that has already turned over makes its stored percentage meaningless, and
    # meaningless in the dangerous direction: it reads stale-HIGH. ⛔ But it used to return
    # GO on the spot, which threw the SEVEN-DAY window away with it - an account whose week
    # was spent got told GO the moment its five-hour window rolled over.
    five_over = now >= resets
    remain_min = 0 if five_over else int((resets - now) / 60)
    clock = time.strftime("%H:%M", time.localtime(resets))
    sd = _seven_day_note(seven, resets, now, cfg)

    # --------------------------------------------------------------- the five-hour window
    proj = burn = None
    early = False
    five_level = None
    if not five_over:
        proj = _projection(sdir, cfg, pct, resets, now)
        # ⭐ WHEN, not only WHETHER. "Projected 140% by reset" says the window will be
        # exhausted and leaves the reader to work out whether there is room for one more
        # wave. ⚠ None means unknowable, never safe - see burnout_min().
        burn = burnout_min(sdir, cfg, pct, resets, now)
        early = burn is not None and burn < remain_min
        five_level = _window_level(pct, cfg["soft_pct_5h"], cfg["hard_pct_5h"])
        # ⛔ THE PROJECTION IS DISPLAY-ONLY FOR NOW. Switched off deliberately, kept here so
        # turning it back on is uncommenting one line rather than reconstructing an argument.
        #
        # ⚠ WHY, MEASURED on a second machine's real history (12 rows, 2026-08-28): the
        # verdict flipped GO→PACE→GO→PACE→GO in twelve minutes while the PERCENTAGE climbed
        # smoothly from 40% to 52% - never within twenty points of soft_pct_5h. The boundary
        # is `(100 - pct) / minutes_left`, so at 47% with 114 minutes left a swing of ONE
        # HUNDREDTH of a percent per minute crosses it. Under bursty dispatch the rate swings
        # far more than that between two samples.
        #
        # ⛔ AND SINCE 0.35.0 A PACE COSTS SOMETHING: it makes a current HANDOFF.md a
        # precondition of dispatching. So a PACE that flickers for one sample blocks a
        # dispatch that should have gone through, and the plugin's own rule - act on the
        # WORD, never on raw percentages - is undermined by a word that is itself twitching.
        #
        # ⇒ WHAT TO ADD BEFORE RE-ENABLING, not just this line back:
        #    1. HYSTERESIS. Enter PACE at proj >= 100, leave it only below 90. A single
        #       threshold on a noisy input can only chatter.
        #    2. A MINIMUM HISTORY. The rate is computed from whatever rows exist in this
        #       window, and logging does not start when the window does - on that machine the
        #       window opened at 14:10 and the first row is 16:49 at 35% already used. The
        #       unlogged head can only ever be an average, and ignoring it made the logged
        #       (busier) stretch stand for the whole window: 0.48 %/min against a
        #       whole-window average of 0.22.
        #
        # if five_level is None and proj is not None and proj >= 100:
        #     five_level = "PACE"
        five_level = _soften_near_reset(five_level, remain_min, cfg)
    burn_note = ("" if not early else
                 " ⛔ At the current rate the 5h window is SPENT in ~%d min - %d min BEFORE "
                 "it resets. Plan for the gap, not for the reset."
                 % (burn, remain_min - burn))

    # --------------------------------------------------------------- the seven-day window
    # ⛔ THE BRAKE USED TO IGNORE THIS ENTIRELY. The 7d figure produced a NOTE and nothing
    # else, so 7d 99% beside 5h 0% read as GO - both numbers true, the answer wrong, and the
    # only thing that stopped the work was the server refusing.
    seven_level = None
    remain7 = None
    if _seven_day_binds(seven, resets, now):
        remain7 = int((resets7 - now) / 60)
        seven_level = _window_level(pct7, cfg["soft_pct_7d"], cfg["hard_pct_7d"])
        seven_level = _soften_near_reset(seven_level, remain7, cfg)

    # ⭐ THE STRICTER OF THE TWO WINS, and ties go to the five-hour window because it is the
    # nearer and more actionable one to name.
    if _STRICTNESS[seven_level] > _STRICTNESS[five_level]:
        level, driver = seven_level, "7d"
    else:
        level, driver = five_level, "5h"

    stale = " [data %d min old - may understate]" % age_min if age_min > cfg["stale_min"] else ""

    if level == "STOP" and driver == "7d":
        text = ("STOP - 7d at %d%% >= hard_pct_7d %d%%. ⛔ The 5h window is NOT the "
                "constraint here (5h %d%%): the WEEK is nearly spent, and it does not reset "
                "for %s. Wrap up: finish the current step, commit or save state, start "
                "nothing new. A resume must be scheduled after the SEVEN-DAY reset, not "
                "after the five-hour one."
                % (round(pct7), cfg["hard_pct_7d"], round(pct), duration(remain7)))
    elif level == "STOP":
        text = ("STOP - 5h at %d%% >= hard_pct_5h %d%%. Wrap up: finish the current step, "
                "commit or save state, start nothing new. Schedule a ONE-SHOT resume a few "
                "minutes after %s, then end the turn."
                % (round(pct), cfg["hard_pct_5h"], clock))
    elif level == "PACE" and driver == "7d":
        text = ("PACE - 7d at %d%%, and it does not reset for %s. ⚠ The 5h window has room "
                "(5h %d%%) - that is not the one to watch. Finish what is in flight; do not "
                "start new heavy work or another dispatch wave."
                % (round(pct7), duration(remain7), round(pct)))
    elif level == "PACE":
        # ⚠ `proj` can no longer be the REASON for a PACE - see the block above - so the
        # wording is the percentage's. The projection is still reported, as a figure to read
        # rather than a verdict to obey.
        why = "5h at %d%%" % round(pct)
        text = ("PACE - %s, %d min left (resets %s). Finish what is in flight; do not start "
                "new heavy work or another dispatch wave." % (why, remain_min, clock))
    elif five_over:
        text = ("GO - the 5h window already reset; treat usage as fresh. Do not spend tokens "
                "re-verifying: the stored number stays stale-high until the next statusline "
                "render.")
    else:
        text = ("GO - 5h at %d%%, %d min left (resets %s). Headroom available."
                % (round(pct), remain_min, clock))

    return {"verdict": level or "GO", "exit": {"STOP": 2, "PACE": 1}.get(level, 0),
            "pct": pct, "pct_7d": pct7, "driver": driver if level else None,
            "remain_min": remain_min, "resets_clock": clock,
            "age_min": age_min, "projected_pct": proj, "seven_day": sd,
            "burnout_min": burn, "burns_out_early": early,
            "text": text + burn_note + stale + (" [%s]" % sd if sd else "")}


_STRICTNESS = {None: 0, "PACE": 1, "STOP": 2}


def _window_level(pct, soft, hard):
    """None / PACE / STOP for one window, from its own pair of thresholds."""
    if not isinstance(pct, (int, float)):
        return None
    if pct >= hard:
        return "STOP"
    if pct >= soft:
        return "PACE"
    return None


def _soften_near_reset(level, remain_min, cfg):
    """⭐ Near a reset the stakes shrink: hitting the cap costs a pause of a few minutes,
    not lost work. Softening by one level is deliberate, and it is why a caller must act on
    the VERDICT and never on the percentage.

    ⚠ It is applied PER WINDOW. A 5h STOP twelve minutes from its reset is worth softening; a
    7d STOP three days from its reset is not, and one shared test would have softened both.
    """
    if not level or remain_min > cfg["near_reset_min"]:
        return level
    return "PACE" if level == "STOP" else None


def _seven_day_binds(seven, five_resets, now):
    """Can the 7-day window actually stop work inside THIS five-hour window?

    ⛔ THE ANSWER IS NOT ALWAYS YES, AND THAT PREDATES THE FOUR THRESHOLDS. If the 7d window
    resets before the 5h one ends, its percentage cannot be what stops you here - it is about
    to become zero. Counting it anyway would brake on a number that is on its way out.

    ⚠ It is also not "is it high": how high is the threshold's business. This answers only
    whether the window is a live constraint at all.
    """
    if not isinstance(seven, dict):
        return False
    pct, resets = seven.get("used_percentage"), seven.get("resets_at")
    if not isinstance(pct, (int, float)) or not resets:
        return False
    if now >= resets:
        return False                      # already reset; the stored number reads stale-high
    return resets > five_resets


def _seven_day_note(seven, five_resets, now, cfg):
    """⛔ A high 7-day percentage is usually NOT a constraint. Say which it is."""
    if not isinstance(seven, dict):
        return None
    pct, resets = seven.get("used_percentage"), seven.get("resets_at")
    if not isinstance(pct, (int, float)) or not resets:
        return None
    if now >= resets:
        return "7d already reset - ignore"
    if resets <= five_resets:
        return ("7d %d%% but it resets before this 5h window ends - IGNORE, not a constraint"
                % round(pct))
    if pct >= cfg["soft_pct_7d"]:
        return "7d %d%% - BINDING, near cap" % round(pct)
    return "7d %d%% - not near cap, ignore" % round(pct)


def burn_triple(sdir, cfg, record, now=None):
    """(minutes to 100%, minutes to reset, percent per minute), or None when unknowable.

    ⭐ ONE call site for the display, so the bar and the verdict cannot disagree - they read
    the same history through the same functions.
    ⚠ MEASURED 2.47 ms on real history, against a statusline that renders once per
    refresh_seconds (60 s by default). It reads at most the last two history files, which
    history_keep_days bounds; a `--watch` at `--every 2` pays it every two seconds and that
    is still nothing next to the render itself.
    """
    now = time.time() if now is None else now
    five = (record or {}).get("five_hour") or {}
    pct, resets = five.get("used_percentage"), five.get("resets_at")
    if not isinstance(pct, (int, float)) or not resets or now >= resets:
        return None
    burn = burnout_min(sdir, cfg, pct, resets, now)
    rate = _burn_rate(sdir, cfg, pct, resets, now)
    return burn, int((resets - now) / 60), (rate * 60 if rate else 0)


BURN_WINDOW_FLOOR_MIN = 5           # under this, a 1% reading cannot resolve a rate


def _burn_rate(sdir, cfg, pct, resets, now, window_secs=5 * 3600):
    """Percent per SECOND over the last `burn_window_min` minutes, or None if unknowable.

    ⭐ Split out so the projection and the burn-out time are computed from ONE sampling of
    one history. Two samplings would disagree at the edges and put a contradiction on one
    line - "projected 140% by reset" beside "runs out after the reset".

    ⛔ Returns None when the token-usage history is off. ⚠ It is ON by default now - it used
    to be off, and this docstring used to say so. That is a real reduction in what PACE can
    catch, not a technicality - say so rather than letting a silently absent projection read
    as "nothing projected".
    """
    # Read the last two files: a 5h window can straddle midnight, and therefore two.
    # ⛔ ONE PREFIX, AND NO PATH FOR THE NAMES THIS FILE USED TO HAVE. A projection quietly
    # assembled from files two renames old is worth less than one that says it has no data
    # yet, and there is now exactly one name to look for.
    rows = []
    hdir = history_dir(sdir, cfg)
    paths = glob.glob(os.path.join(hdir, HISTORY_PREFIX + "*.jsonl"))
    for path in sorted(paths, key=_history_stamp)[-2:]:
        try:
            with open(path, encoding="utf-8") as f:
                rows += [json.loads(l) for l in f if l.strip()]
        except Exception:
            continue
    if not rows:
        return None
    # ⭐ THIS FILTER IS ALSO WHAT MAKES HISTORY ACCOUNT-SAFE, by accident rather than by
    # design - worth writing down so nobody "tidies" it away. History rows carry no account
    # field, and ⚠ NOT for the reason this comment used to give. It said neither the
    # credentials file nor the endpoint carries an account identifier (measured 2026-08-26)
    # and that is WRONG: measured 2026-08-27, ~/.claude/.credentials.json carries
    # `organizationUuid` at its top level, and ~/.claude.json carries the per-seat
    # `accountUuid` under `oauthAccount`. Both are what _account_ids() reads for the debug
    # response dump. ⚠ Whether a history row SHOULD carry one is an open decision nobody has
    # made - and the safety below is what makes the current answer harmless either way. If
    # the signed-in account changes, rows from the old one would otherwise be mixed into the
    # new one's burn rate. They are not, because a row is kept only when its resets_at
    # matches the window being projected to the second, and two accounts' windows do not
    # share an instant.
    # Rows carry readable timestamps now and epochs in older files; unstamp() reads both.
    norm = []
    for r in rows:
        if not isinstance(r.get("pct"), (int, float)):
            continue
        at, ra = unstamp(r.get("at", r.get("ts"))), unstamp(r.get("resets_at"))
        if at is None or ra is None or abs(ra - resets) > 1:
            continue
        norm.append({"ts": at, "pct": r["pct"]})
    rows = norm
    rows.sort(key=lambda r: r["ts"])
    if not isinstance(pct, (int, float)):
        return None
    opened = resets - window_secs

    # ⭐ THE END POINT IS `now` AND THE LIVE `pct`, NOT THE LAST LOGGED ROW. History rows are
    # written only when a number MOVES (see the `moved` gate before _append_history), so an
    # idle stretch writes nothing at all - and reading the last row as "now" froze BOTH ends
    # of the measurement. ⛔ MEASURED on a real idle window: after 84 quiet minutes the rate
    # read 39% HIGH and the burn-out time 78 minutes too soon, and it was not being recomputed
    # at all - the same number was redrawn. ⚠ `now` was in this signature and unread; that is
    # what the bug looked like from outside.
    #
    # ⭐ THE START POINT IS WHAT WAS SPENT `burn_window_min` MINUTES AGO. The gauge answers
    # "how fast am I burning NOW", so it must not average in an hour that is over.
    # ⚠ A ROW'S VALUE STANDS UNTIL THE NEXT ROW, which is exactly why the newest row at or
    # before the cut can be read AS the value at the cut: nothing changed in between, or a
    # row would have been written. So the baseline is a true `burn_window_min` minutes, not
    # "however long ago the last row happens to sit".
    #
    # ⛔ AND THAT HOLDS ONLY WHILE THE RECORDER WAS RUNNING. A gap in the history has two
    # causes and the timestamps cannot tell them apart: nothing was spent (the reading is
    # right), or nothing was WATCHING - Claude Code closed, the machine off, the watcher never
    # started - and the quota is account-wide, so another seat may have spent through the gap.
    # ⇒ In the second case this under-states the rate, which is the dangerous direction.
    # ⚠ A "went to sleep" marker does not fix it: the shutdown that matters is the one that
    # does not get to write anything. What fixes it is a HEARTBEAT row - write one when the
    # value moves OR when the newest row is older than some age - because then the absence of
    # a heartbeat is itself the evidence, recorded by the passage of time rather than by an
    # event somebody had to catch. Not built; see Memory/notes/SHELVED-burn-meter.md.
    #
    # ⭐ AND THE WINDOW'S OWN START IS STILL A DATA POINT, AND STILL FREE. Inside the first
    # `burn_window_min` minutes the cut reaches back past the open, and a window opens at zero
    # by definition - so `(opened, 0)` is a reading nobody had to record. ⛔ WITHOUT IT THE
    # BUSY TAIL STOOD FOR THE WHOLE WINDOW: measured on a second machine, a window that opened
    # at 14:10 whose first row is 16:49 with 35% ALREADY SPENT read 0.48 %/min against a true
    # average of 0.22. That is why the anchor survives here rather than being replaced.
    #
    # ⛔ WHAT THIS COSTS, AND IT IS NOT SMALL. `used_percentage` is reported in WHOLE percent,
    # so over a 30-minute baseline one step is 0.033 %/min - the gauge cannot resolve finer,
    # and on a quiet window that quantum is most of the signal. MEASURED on real history, a
    # 25-minute baseline swung 0.407 -> 0.040 %/min across half an hour in which the
    # whole-window figure moved 0.150 -> 0.137. ⇒ THE NUMBER IS DELIBERATELY TWITCHY, because
    # what was asked of it is "react", and it is safe to be twitchy for exactly one reason:
    # NO BURN FIGURE REACHES GO/PACE/STOP. That is pinned by a check that forces both figures
    # to their worst and asserts the word does not move. Set burn_window_min to 0 for the
    # steady whole-window figure instead.
    span_want = cfg.get("burn_window_min") or 0
    cut = now - span_want * 60 if span_want else opened
    if cut <= opened:
        start_ts, start_pct = opened, 0.0
    else:
        older = [r for r in rows if r["ts"] <= cut]
        if older:
            start_ts, start_pct = cut, older[-1]["pct"]
        elif rows:
            # ⚠ Nothing that old exists: the baseline is SHORTER than asked, and saying so
            # with a number is better than saying nothing. The span guard below still applies.
            start_ts, start_pct = rows[0]["ts"], rows[0]["pct"]
        else:
            return None
    span = now - start_ts
    if span < 300:                                   # under 5 minutes proves nothing
        return None
    rate = (pct - start_pct) / span                  # percent per second
    if rate <= 0:
        # ⚠ NOT ZERO, AND NOT "SAFE". Nothing was spent in the baseline, so there is no rate
        # to draw - and _burn_part() renders that as its own glyph rather than as an empty
        # bar, because empty means DANGER in that column.
        return None
    return rate


def _projection(sdir, cfg, pct, resets, now):
    """Where usage lands by reset at the recent burn rate, or None if unknowable.

    ⚠ A LOWER BOUND. Under bursty multi-agent dispatch the real burn runs ahead of it, so
    the hard stop still rules regardless of what this says.
    """
    rate = _burn_rate(sdir, cfg, pct, resets, now)
    if rate is None:
        return None
    return int(min(999, pct + rate * (resets - now)))


def burnout_min(sdir, cfg, pct, resets, now):
    """Minutes until this window reaches 100% at the recent burn rate, or None.

    ⭐ THE INVERSE OF _projection(), AND THE OWNER ASKED FOR IT BECAUSE THE TWO ANSWER
    DIFFERENT QUESTIONS. "Projected 140% by reset" says the window will be exhausted; it
    does not say WHEN, and when is what decides whether there is time for one more wave.

    ⛔ IT SHARES _burn_rate() WITH THE PROJECTION ON PURPOSE. Two samplings of the same
    history would disagree at the edges, and then the line would say "projected 140%" beside
    "runs out after the reset" - a contradiction on one screen, which is worse than either
    number alone.

    ⚠ None means "cannot be known", never "safe". No history (debug.token_usage off), under
    five minutes of baseline, or nothing spent within it all return None, and every caller
    must print something that says so rather than nothing. ⭐ Inside the first
    `burn_window_min` minutes of a window no logged row is needed at all, because the
    window's own start is the second point.
    """
    rate = _burn_rate(sdir, cfg, pct, resets, now)
    if rate is None or not isinstance(pct, (int, float)):
        return None
    if pct >= 100:
        return 0
    return int((100.0 - pct) / rate / 60.0)


# --------------------------------------------------------------------------- main

def last_heartbeat_min(sdir, now=None):
    """Minutes since any session last fired a hook, or None if none ever has.

    ⭐ The gate writes `state/<session-id>.alive` on EVERY hook event, so the newest of
    those files is the answer to "is anybody actually working?" - no new bookkeeping, no
    new file, and it already survives pruning: prune_state() keeps the .alive files by
    COUNT, newest first, so a live session's own file can never be the one dropped.
    """
    now = time.time() if now is None else now
    newest = None
    for path in glob.glob(os.path.join(sdir, "state", "*.alive")):
        try:
            m = os.path.getmtime(path)
        except OSError:
            continue
        if newest is None or m > newest:
            newest = m
    return None if newest is None else max(0.0, (now - newest) / 60.0)


def should_fetch(sdir, cfg, now=None):
    """`--watch` only: may the API be asked, and if not, why not? Returns (bool, note).

    ⛔ SPLIT OUT SO IT CAN BE CHECKED WITHOUT HTTP. The decision it makes is invisible when
    it is right and expensive when it is wrong - a watcher that never pauses burns the five
    calls per token overnight, and one that pauses too eagerly shows a frozen number during
    real work. Neither failure announces itself, so both need a check.

    ⚠ Zero or a negative idle_after_min disables the pause entirely. Somebody who wants the
    old always-poll behaviour should be able to say so without editing code.
    """
    limit = cfg.get("idle_after_min", 15)
    if not isinstance(limit, (int, float)) or limit <= 0:
        return True, None
    idle = last_heartbeat_min(sdir, now)
    if idle is None:
        # ⚠ Nothing has EVER fired a hook here. That is a fresh state directory, not an
        # idle machine, and refusing to fetch would leave the first render empty forever.
        return True, None
    if idle <= limit:
        return True, None
    # ⚠ Short on purpose: it is appended inside a status line, and a sentence here is what
    # pushed that line past the terminal width - which wrapped it, which stranded a row `\r`
    # could never reach.
    return False, "idle %s" % duration(idle)


WATCH_MARK = "watch.alive"


def _note_watch(sdir):
    """Touch a file on every redraw, so somebody can ask whether the watcher is running.

    ⛔ WHY THIS IS NOT `renders.log`. That file records STATUSLINE renders, keyed by session
    id, and a `--watch` process has no session - so the one question people actually ask,
    "is the VS Code usage terminal alive?", had no answer anywhere. Measured 2026-08-28: a
    second machine's terminal did not appear, and every diagnostic could report the task was
    installed while none could report whether it had ever run.

    ⭐ ON REDRAW, NOT ON FETCH. The watcher deliberately stops calling the API when nobody is
    working and keeps REDRAWING, so a fetch-based heartbeat would read as dead during exactly
    the idle stretch it is designed for. What is being proved here is that the process is
    alive, and the redraw is that proof.
    """
    try:
        with open(os.path.join(sdir, WATCH_MARK), "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except OSError:
        pass                              # a read-only state dir must not kill the watcher


def watch(sdir, cfg, argv):
    """Reprint the usage line on an interval, for a terminal that stays open.

    ⭐ By default it REWRITES ONE LINE rather than scrolling. A watcher that adds a row
    every thirty seconds fills the panel with history nobody asked for, and the only line
    that means anything is the newest one. Set `watch_scroll: true`, or pass `--scroll`,
    to keep every line instead.

    ⚠ Rewriting needs a real terminal. Redirected to a file or a pipe there is no cursor
    to move, and a carriage return would collapse the whole run onto one unreadable line -
    so it falls back to scrolling automatically when stdout is not a tty.

    ⭐ IT NOW FETCHES, so it is self-sufficient: no statusline has to exist anywhere for
    this to show a real number. That is what makes it the answer for the VS Code
    extension, whose panel renders no statusline at all.

    ⚠ It fetches at most once per fetch_seconds regardless of --every, so a two-second
    --every costs nothing extra at the API. A line that stops advancing now means the
    fetch is failing rather than that usage stopped moving, and fetch.log says which.
    """
    every = 30
    if "--every" in argv:
        i = argv.index("--every")
        if i + 1 < len(argv):
            try:
                every = max(2, int(argv[i + 1]))
            except ValueError:
                pass

    scroll = bool(cfg.get("watch_scroll", False)) or "--scroll" in argv
    try:
        if not sys.stdout.isatty():
            scroll = True          # no cursor to rewrite; see the docstring
    except Exception:
        scroll = True

    ERASE_TO_EOL = "\033[K"        # so a shorter line cannot leave the old tail behind
    drawn_idle = False             # has this quiet spell's SLEEP line been drawn already?
    # ⛔ ONCE, BEFORE ANYTHING IS DRAWN. See _watch_open(): the line the previous run left
    # behind is above the row this one can reach, so nothing later can remove it.
    opening = _watch_open(scroll)
    if opening:
        sys.stdout.write(opening)
        sys.stdout.flush()
        # ⭐ atexit RATHER THAN A finally AROUND THE LOOP, deliberately: the loop is a
        # `while True` with several ways out, and this runs on all of them - a clean return,
        # Ctrl-C, an unhandled error - without reindenting a body whose cursor arithmetic is
        # the thing being protected. ⚠ Wrapped in try/except: a closed pipe at shutdown must
        # not turn a clean stop into a traceback.
        def _restore(_bytes=_watch_close(scroll)):
            try:
                sys.stdout.write(_bytes)
                sys.stdout.flush()
            except Exception:
                pass
        atexit.register(_restore)
    try:
        while True:
            # ⭐ Pause the FETCH when nobody is working - never the redraw. A frozen
            # line would read as a current number, which is the confident wrong answer
            # this plugin refuses everywhere else, so the note below says both that
            # nothing is being fetched and how old the figure is.
            # ⚠ No catch-up on resume: this simply starts calling ensure_fresh() again,
            # and that honours fetch_seconds, so waking costs one call and not a burst.
            may_fetch, idle_note = should_fetch(sdir, cfg)
            if may_fetch:
                data, reason = ensure_fresh(sdir, cfg)  # in memory; no re-read
            else:
                data, reason = read_json(cfg["token_usage_file"]), None
            data = data if isinstance(data, dict) else {}
            age = None
            if data.get("ts"):
                age = (time.time() * 1000 - data["ts"]) / 60000.0
            v = verdict(sdir, cfg, data=data)           # same record, passed by value
            idle = bool(idle_note)
            # ⛔ WHILE IDLE THIS LINE CARRIES NO NOTE AT ALL. `2 min old` and `idle 15m` both
            # restate what SLEEP already says - the line stopped moving because nobody is
            # working - and a note that repeats the word beside it is a note people stop
            # reading. The OAuth warning used to be the one exception; the owner removed it
            # (2026-08-29), so nothing survives here now.
            # ⚠ `reason` cannot appear while idle either: idle means no fetch was attempted,
            # so there is no failure to report.
            note = None
            if not idle:
                if age is not None and age > cfg["stale_min"]:
                    note = "%.0f min old" % age
                if reason and (note or age is None):
                    note = "%s; %s" % (note, reason) if note else reason
            # ⭐ ONE FUNCTION OWNS THE WHOLE LINE, INCLUDING ITS WIDTH. This used to assemble
            # the stamp, the body and the verdict word here - and _line() fitted only the
            # BODY, so the sixteen columns added around it overflowed the terminal and the
            # line wrapped. See _watch_line() for what that cost.
            # ⚠ AND THE LINE STILL ENDS WITH TWO SPACES. `--watch` rewrites in place, so the
            # terminal parks its cursor on the last character - which renders as a box over
            # the "O" of GO. Those two spaces put it somewhere harmless; ERASE_TO_EOL still
            # clears whatever a longer previous line left behind.
            # ⛔ WHILE IDLE, DRAW ONCE AND THEN STOP - the owner's instruction, and it removes
            # the reported defect at its source instead of mitigating it. A line nothing is
            # rewriting cannot strand a row whatever its width, and an idle machine stops
            # scrolling a terminal full of identical lines all night.
            # ⇒ ONE render marks the transition: the same figures, no colour, the word SLEEP.
            # After that nothing is printed until work resumes. ⚠ `drawn_idle` is cleared on
            # the way back, so the NEXT quiet spell marks itself too - without that, a machine
            # that went idle, woke and went idle again would never say so a second time.
            if idle and drawn_idle:
                _note_watch(sdir)
                time.sleep(every)
                continue
            drawn_idle = idle
            lines = _watch_line(time.strftime("%H:%M:%S"), data, v, note, cfg, idle=idle,
                                burn=burn_triple(sdir, cfg, data))
            # ⛔ NO CLIMBING. See _redraw(): the watcher cleared the screen at startup and
            # redraws all of it from an absolute home, because a relative move is only right
            # while nothing else has touched the cursor - and in a VS Code panel it does.
            if scroll:
                for one in lines:
                    print(one)
            else:
                sys.stdout.write(_redraw(lines, ERASE_TO_EOL))
            sys.stdout.flush()
            _note_watch(sdir)
            time.sleep(every)
    except KeyboardInterrupt:
        if not scroll:
            sys.stdout.write("\n")
        return 0


def selftest():
    """`usage.py --selftest` - asserts the fetch layer's two dangerous decisions.

    Both are dangerous in the same direction: a wrong answer here reads LOW and holds the
    brake off. Neither is exercised by simply running the tool, because both only matter
    on inputs the API does not normally send - which is exactly why they need a check that
    fails loudly instead of a comment that hopes.

    Touches no real state: it builds its own temp directory and makes no HTTP request.
    """
    import tempfile

    # Scale. (0, 1] is ambiguous - 1% and 100% cannot be told apart - so it is refused.
    assert _api_window({"utilization": 22.0})["used_percentage"] == 22.0
    assert _api_window({"utilization": 0.0})["used_percentage"] == 0.0
    for bad in (0.22, 1.0, 101, -1, None, True, "22"):
        assert _api_window({"utilization": bad}) is None, bad
    assert _api_window(None) is None and _api_window("x") is None

    # ⭐ ...unless the response says which scale it meant. `limits[].percent` is a whole
    # number, so exactly one reading of an ambiguous `utilization` can match it. Measured
    # 2026-08-27: a week that had just rolled over returned utilization 1.0 beside
    # percent 1, and refusing it made the 7d segment vanish from the line entirely.
    assert _api_window({"utilization": 1.0}, 1.0)["used_percentage"] == 1.0
    assert _api_window({"utilization": 0.01}, 1.0)["used_percentage"] == 1.0
    assert _api_window({"utilization": 1.0}, 100.0)["used_percentage"] == 100.0
    # ⛔ A hint that matches NEITHER reading proves nothing, so the value is still refused.
    assert _api_window({"utilization": 1.0}, 47.0) is None
    raw = {"five_hour": {"utilization": 8.0}, "seven_day": {"utilization": 1.0},
           "limits": [{"kind": "session", "percent": 8},
                      {"kind": "weekly_all", "percent": 1}]}
    assert _whole_percent(raw, "seven_day") == 1.0
    assert _whole_percent(raw, "five_hour") == 8.0
    assert _whole_percent({"limits": []}, "seven_day") is None
    assert _whole_percent(raw, "nonexistent") is None

    # Timestamps. The API sends fractional seconds and an offset; the stored value must be
    # whole seconds, or two identical readings compare unequal. 1787742000 is a measured
    # pair: that ISO string and the epoch the file already held for the same window.
    got = _api_window({"utilization": 5,
                       "resets_at": "2026-08-26T11:00:00.203505+00:00"})["resets_at"]
    assert got == 1787742000 and isinstance(got, int), got
    assert _api_window({"utilization": 5, "resets_at": "2026-08-26T11:00:00+00:00"}
                       )["resets_at"] == 1787742000
    assert _api_window({"utilization": 5, "resets_at": "nonsense"}).get("resets_at") is None
    a = _api_window({"utilization": 5, "resets_at": "2026-08-26T11:00:00.203505+00:00"})
    b = _api_window({"utilization": 5, "resets_at": "2026-08-26T11:00:00.390781+00:00"})
    assert a == b, "microseconds must not make two identical readings differ"
    # ⚠ Observed live: the SAME window came back on either side of the second boundary.
    # Truncating made the reset appear to move; rounding lands both on the same second.
    c = _api_window({"utilization": 5, "resets_at": "2026-08-26T10:59:59.912345+00:00"})
    assert c == a, "a sub-second wobble across the boundary must not move the reset"

    # ⛔ THE WATCHER'S IDLE PAUSE, both directions. It is invisible when right and expensive
    # when wrong: never pausing burns the five calls per token overnight, pausing too
    # eagerly freezes the number during real work. Neither failure announces itself.
    with tempfile.TemporaryDirectory() as sdir:
        os.makedirs(os.path.join(sdir, "state"))
        cfg_i = {"idle_after_min": 15}
        now = time.time()
        # A fresh state directory has never seen a hook. That is not idleness, and refusing
        # to fetch there would leave the very first render empty for ever.
        assert should_fetch(sdir, cfg_i, now)[0] is True, "an empty state dir must fetch"

        beat = os.path.join(sdir, "state", "abc.alive")
        for back_min, expect in ((0, True), (14, True), (16, False), (600, False)):
            with open(beat, "w") as f:
                f.write("x")
            os.utime(beat, (now - back_min * 60, now - back_min * 60))
            got, note = should_fetch(sdir, cfg_i, now)
            assert got is expect, "%d min idle -> %s" % (back_min, got)
            assert (note is None) is expect, note
        # ⚠ The NEWEST heartbeat wins: one live session among twenty dead ones is activity.
        with open(os.path.join(sdir, "state", "live.alive"), "w") as f:
            f.write("x")
        assert should_fetch(sdir, cfg_i, now)[0] is True, "a live session was ignored"
        # 0 or negative switches the pause off entirely.
        assert should_fetch(sdir, {"idle_after_min": 0}, now)[0] is True

    # ⛔ Ctx: zero and unknown are different answers, decided by whether the KEY is there.
    # Rendering "cannot read" as 0% would be a confident wrong answer erring LOW.
    assert _context_pct({"model": {}}) is None, "an absent key must be unknown"
    assert _context_pct({CONTEXT_KEY: {"used_percentage": 41.0}}) == 41.0
    assert _context_pct({CONTEXT_KEY: {"used_percentage": 0}}) == 0.0
    assert _context_pct({CONTEXT_KEY: {"current_usage": None,
                                       "context_window_size": 200000}}) == 0.0
    assert _context_pct({CONTEXT_KEY: {"renamed": 1, "current_usage": {"x": 1}}}) is None
    assert _context_pct({CONTEXT_KEY: "not a dict"}) is None
    # ...and the three render differently, which is the point of the whole exercise.
    _rec = {"five_hour": {"used_percentage": 5.0, "resets_at": time.time() + 3600}}
    _zero = _line(_rec, None, {"width": None}, {CONTEXT_KEY: {"used_percentage": 0}})
    _absent = _line(_rec, None, {"width": None}, {"model": {}})
    _real = _line(_rec, None, {"width": None}, {CONTEXT_KEY: {"used_percentage": 41.0}})
    assert "Ctx" in _zero and " 0%" in _zero, _zero
    assert "Ctx" in _absent and "--" in _absent and "0%" not in _absent, _absent
    assert _zero != _absent, "a real zero and an unreadable one rendered the same"
    assert "41%" in _real, _real

    # Jitter is ADDED, never subtracted, so the effective wait can never dip under the
    # floor - which is the whole point, since the floor is what protects the five calls.
    for width in (JITTER_SECONDS, 5, 300):
        _cfg = {"fetch_seconds": FETCH_FLOOR_SECONDS, "fetch_seconds_jitter": width}
        seen = [_interval(_cfg) for _ in range(500)]
        assert min(seen) >= FETCH_FLOOR_SECONDS, "went BELOW the floor: %r" % min(seen)
        assert max(seen) <= FETCH_FLOOR_SECONDS + width, (width, max(seen))
        assert max(seen) - min(seen) > width / 2, "not jittering at %r: %r" % (width, seen[:3])
    # 0 disables it, and a negative value must not be able to subtract.
    _cfg = {"fetch_seconds": FETCH_FLOOR_SECONDS, "fetch_seconds_jitter": 0}
    assert _interval(_cfg) == FETCH_FLOOR_SECONDS
    _cfg["fetch_seconds_jitter"] = -60
    assert _interval(_cfg) >= FETCH_FLOOR_SECONDS, "a negative jitter subtracted"

    # The token expiry is read, not discovered from a 401: a dead token must not cost one of
    # the five calls. ⛔ AND IT REACHES NO DISPLAY. The owner removed the OAuth note from the
    # bar in two steps on 2026-08-29 - the countdown, then the expired form.
    _saved_env = os.environ.pop("ANTHROPIC_TOKEN", None)
    _saved_reader = read_json

    def _fake(now_offset_s):
        exp = (time.time() + now_offset_s) * 1000
        return lambda path, fallback=None: (
            {"claudeAiOauth": {"accessToken": "sk-x", "expiresAt": exp}}
            if path.endswith(".credentials.json") else _saved_reader(path, fallback))
    try:
        # ⛔ NO OAUTH NOTE ON THE BAR, IN ANY TOKEN STATE. ⚠ Pinned by the SYMBOL, not by
        # rendering one line: the note is re-added under its own name whenever somebody puts
        # it back, and a text assertion on one rendered line cannot see the other display -
        # the statusline and the watcher build their notes separately.
        assert "token_note" not in globals(), \
            "token_note() is back - the bar must not report an OAuth token"
        globals()["read_json"] = _fake(-60)
        # ⛔ THE EXPIRY IS STILL READ, AND MUST NOT SPEND A CALL TO FIND OUT. ⚠ Checked by
        # counting requests, NOT by reading the message: a real 401 reply also says
        # "expired", so an assertion
        # on the text alone cannot tell "never asked" from "asked and was refused" - it
        # passed against a build with this guard removed, and made a live request doing it.
        called = []
        _saved_open = urllib.request.urlopen
        urllib.request.urlopen = lambda *a, **k: called.append(1)
        try:
            got = fetch({})
            assert "expired" in str(got).lower(), got
            assert not called, "fetch asked anyway on a token it could see was dead"
        finally:
            urllib.request.urlopen = _saved_open
    finally:
        globals()["read_json"] = _saved_reader
        if _saved_env is not None:
            os.environ["ANTHROPIC_TOKEN"] = _saved_env

    # The floor is enforced, not merely documented.
    tmp = tempfile.mkdtemp()
    with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"fetch_seconds": 30}, f)
    assert config(tmp)["fetch_seconds"] == FETCH_FLOOR_SECONDS
    with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"fetch_seconds": 600, "stale_min": 60}, f)
    assert config(tmp)["fetch_seconds"] == 600
    # jitter comes from config, defaults to 30, and a negative one is refused
    assert config(tmp)["fetch_seconds_jitter"] == 30
    for value, want in ((5, 5), (0, 0), (-1, 0)):
        with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"fetch_seconds_jitter": value, "stale_min": 60}, f)
        assert config(tmp)["fetch_seconds_jitter"] == want, (value, want)

    # A failed fetch must leave a good stored value alone. fetch() returns a reason string
    # for every failure, and ensure_fresh() must not write on one.
    cfg = config(tmp)
    good = {"ts": int(time.time() * 1000) - 3600_000,
            "five_hour": {"used_percentage": 6, "resets_at": 1787742000}}
    with open(cfg["token_usage_file"], "w", encoding="utf-8") as f:
        json.dump(good, f)
    calls = []
    saved = fetch
    globals()["fetch"] = (
        lambda cfg=None, sdir=None: (calls.append(1), "HTTP 429 rate limited")[1])
    try:
        rec, why = ensure_fresh(tmp, cfg)
        assert "429" in (why or ""), why
        # ⛔ The record must come back BY VALUE on every path, including the common one
        # where nothing needed doing - callers rely on it instead of re-reading the file,
        # so a path that returns None makes them render -- with good data on disk.
        assert rec, "ensure_fresh returned no record on the failure path"
        assert rec == good, "the old record must survive a failed fetch, in memory too"
        assert read_json(cfg["token_usage_file"]) == good, "a 429 must not touch the cache"
        # ⛔ The claim is NOT released on failure, so the next caller must not retry. This
        # is the only backoff there is, and without it a persistent 429 becomes a loop
        # that spends the whole five-call budget. It is also what stops several sessions'
        # statuslines from all fetching on the same interval boundary.
        again = ensure_fresh(tmp, cfg)
        assert again[1] is None, "a second call must be refused by the claim"
        assert again[0] == good, "the fresh/refused path must still hand back the record"
        assert len(calls) == 1, "the claim did not prevent the second request: %r" % calls
        # ⛔ And an empty record from a caller must NOT be mistaken for "no data exists".
        assert verdict(tmp, cfg, data={})["verdict"] != "NO-DATA", (
            "an empty dict was accepted as a record instead of falling back to the file")
        # ⛔ THE COMMON PATH, tested separately because the two above do not reach it. With
        # a FRESH record nothing needs doing, and that is the path taken on almost every
        # tick - so it is the one whose return value matters most. ⚠ The earlier assertions
        # went down the claim-refused branch instead, and a mutation that emptied this
        # branch passed them: every tick would have rendered -- with good data on disk.
        fresh = {"ts": int(time.time() * 1000),
                 "five_hour": {"used_percentage": 11, "resets_at": 1787742000}}
        with open(cfg["token_usage_file"], "w", encoding="utf-8") as f:
            json.dump(fresh, f)
        del calls[:]                       # count only what THIS path does
        # ⚠ THE CLAIM IS CLEARED FIRST, deliberately. Leaving it would let the claim check
        # refuse the fetch, so this assertion would pass even with the freshness check gone
        # - the two guards cover each other and the test would be measuring the wrong one.
        # Removing it makes freshness the ONLY thing that can prevent the request.
        try:
            os.remove(os.path.join(tmp, "fetch.claim"))
        except OSError:
            pass
        rec2, why2 = ensure_fresh(tmp, cfg)
        assert why2 is None and rec2 == fresh, (
            "the FRESH path must hand the record back by value: %r %r" % (rec2, why2))
        assert not calls, "the fresh path made a request"
    finally:
        globals()["fetch"] = saved

    # ⛔ RETENTION - the only setting in this file that DELETES, so it is checked hardest.
    # Two properties, and the second one is the safety argument for the whole feature.
    assert _days(None, HISTORY_KEEP_DAYS_DEFAULT) == HISTORY_KEEP_DAYS_DEFAULT
    assert _days(30, 30) == 30 and _days("30", 30) == 30      # a hand-typed "30" still works
    # ⛔ EVERY UNUSABLE VALUE MEANS KEEP FOR EVER, never "fall back to 30 and start
    # deleting". A wrong number elsewhere in this file costs a wrong reading on a line; a
    # wrong number here costs a record nobody can get back.
    for bad in (0, -1, True, False, "abc", "", [], {}, float("nan"), float("inf")):
        assert _days(bad, 30) == 0, bad

    tmp2 = tempfile.mkdtemp(prefix="dg-prune-")
    logs = os.path.join(tmp2, "logs")
    os.makedirs(logs)
    now2 = time.time()
    planted = {"token_usage_history_20200101-000000.jsonl": 60,   # ours, old
               "API_response_usage_20200101-000000.jsonl": 60,     # ours, old
               "token_usage_history_20990101-000000.jsonl": 1,     # ours, fresh
               "limits-history-20200101-000000.jsonl": 400,        # RETIRED name, ancient
               "not-ours.jsonl": 400,                              # NOT ours, old
               "notes.txt": 400}                                   # NOT ours, old

    def replant():
        for fname, age in planted.items():
            p = os.path.join(logs, fname)
            with open(p, "w", encoding="utf-8") as f:
                f.write("x" + chr(10))
            os.utime(p, (now2 - age * 86400, now2 - age * 86400))

    replant()
    cfg2 = {"history_dir": logs, "history_keep_days": 30}
    # ⚠ TWO: the history file and the response dump, one old file each.
    assert prune_logs(tmp2, cfg2, now2) == 2, "expected exactly the two old OURS"
    left = set(os.listdir(logs))
    # ⛔ THE SAFETY ARGUMENT: history_dir is configurable and the docs suggest pointing it
    # at a synced folder, so anything without one of this plugin's two prefixes must
    # survive no matter how old it is. A blanket *.jsonl sweep would delete a stranger's
    # data, and nothing would ever report it.
    assert "not-ours.jsonl" in left and "notes.txt" in left, left
    assert "token_usage_history_20990101-000000.jsonl" in left, left
    assert "token_usage_history_20200101-000000.jsonl" not in left, left
    # ⛔ A NAME THIS PLUGIN NO LONGER WRITES IS NOT TOUCHED, however old it is. There is one
    # set of names now and prune_logs() knows only that set - so a file from a retired naming
    # scheme is a stranger's file as far as this function is concerned, and strangers' files
    # are never deleted. ⚠ Anyone updating is expected to run Tools/clean-dispatch-guard.ps1,
    # which removes the whole state directory including these.
    assert "limits-history-20200101-000000.jsonl" in left, left

    # 0 and every unreadable value keep everything - checked through prune_logs itself,
    # not only through _days(), because this function is reached with a cfg that never
    # passed through config().
    for keep in (0, "abc", True, -5, [], ""):
        replant()
        c = {"history_dir": logs, "history_keep_days": keep}
        assert prune_logs(tmp2, c, now2) == 0, keep
        assert len(os.listdir(logs)) == len(planted), keep

    # ⚠ AN EXPLICIT null IS *NOT* "FOR EVER" - it means "use the default", the same as
    # history_dir: null and the same as leaving the key out. ⛔ 0 is the value that keeps
    # everything, and config.example.json says so where somebody editing the file will
    # read it. Pinned here because the two readings are easy to confuse and one of them
    # deletes.
    replant()
    assert prune_logs(tmp2, {"history_dir": logs, "history_keep_days": None}, now2) == 2

    # ⭐ And the trigger: history_path() prunes ONLY when it mints a new day's name.
    replant()
    minted = history_path(tmp2, cfg2, now2)
    assert not os.path.exists(minted), "history_path must not create the file"
    assert len(os.listdir(logs)) == len(planted) - 2, "minting a new name must prune"
    replant()
    with open(minted, "w", encoding="utf-8") as f:
        f.write("x" + chr(10))
    same = history_path(tmp2, cfg2, now2)
    assert same == minted, (same, minted)
    assert len(os.listdir(logs)) == len(planted) + 1, "an existing day's file must NOT prune"

    # ⛔ THERE IS EXACTLY ONE FILE NAME NOW, and this checks that the reader and the writer
    # agree on it. They are built from the same constant, so the risk is not that they differ
    # - it is that BOTH are wrong and _projection() answers None, which looks exactly like
    # "not enough samples yet". There is no error to notice, which is why it is asserted.
    tmp3 = tempfile.mkdtemp(prefix="dg-history-")
    logs3 = os.path.join(tmp3, "logs")
    os.makedirs(logs3)
    resets3 = int(time.time()) + 3600
    rows3 = [{"at": stamp(time.time() - 1800), "pct": 10, "resets_at": stamp(resets3)},
             {"at": stamp(time.time() - 60), "pct": 40, "resets_at": stamp(resets3)}]
    cfg3 = {"history_dir": logs3, "debug": {"token_usage": True}}
    written = history_path(tmp3, cfg3)
    assert os.path.basename(written).startswith("token_usage_history_"), written
    with open(written, "w", encoding="utf-8") as f:
        for row in rows3:
            f.write(json.dumps(row) + chr(10))
    proj = _projection(tmp3, cfg3, 40, resets3, time.time())
    assert proj is not None and proj > 40, (
        "the writer's own file name was not read back: %r (%s)" % (proj, written))
    # ⛔ AND A NAME THIS PLUGIN NO LONGER USES IS NOT READ. The owner asked for one name with
    # no compatibility path; a projection quietly assembled from files two renames old is
    # worth less than one that says it has no data yet. Mutation-checked: put the rows under
    # a retired name and the projection must go away.
    os.rename(written, os.path.join(logs3, "limits-history-20200101-000000.jsonl"))
    assert _projection(tmp3, cfg3, 40, resets3, time.time()) is None, \
        "a retired file name is still being read"

    # ⛔ ONE SWITCH, ONE NAME, AND EVERY OLD NAME IGNORED. `keep_history` was what this used
    # to be called; it is not read any more, so a config still carrying it gets the DEFAULT.
    # ⚠ That is the owner's decision and it is asserted rather than assumed, because the
    # opposite - a name that quietly still works - is how a settings file ends up with three
    # spellings of one switch and nobody able to say which wins.
    tmp4 = tempfile.mkdtemp(prefix="dg-switch-")
    for blob, want, why in (
            ({}, True, "absent -> ON, the default"),
            ({"debug": {"token_usage": False}}, False, "the one name, OFF"),
            ({"debug": {"token_usage": True}}, True, "the one name, ON"),
            ({"keep_history": False}, True, "a retired name must be IGNORED, not obeyed"),
            ({"token_usage_history": False}, True, "and so must the other retired name")):
        with open(os.path.join(tmp4, "config.json"), "w", encoding="utf-8") as f:
            json.dump(blob, f)
        assert config(tmp4)["debug"]["token_usage"] is want, "%s: %r" % (why, blob)

    # ⛔ THE WATCHER'S LINE MUST NEVER BE WIDER THAN THE TERMINAL. It was, and the way it
    # failed is the reason this check exists at all: _line() fitted the BODY, watch() then
    # added a timestamp and a verdict word around it, and the sixteen columns nobody had
    # subtracted pushed the line into a wrap. `\r` returns to the start of the LAST VISUAL
    # ROW and `\033[K` clears only that row, so every render stranded its first row on
    # screen for ever. MEASURED at width 150: body 149, line 165.
    _now = time.time()
    _live = {"ts": int(_now * 1000),
             "five_hour": {"used_percentage": 55, "resets_at": int(_now) + 1600},
             "seven_day": {"used_percentage": 32, "resets_at": int(_now) + 300000}}
    _v = {"verdict": "GO", "pct": 55}
    _note = "idle 7h-35m; OAuth token expires in 10m - open a session"
    # ⚠ EVERY ROW, not the joined text: the point of a second row is that each one fits.
    for _w in (200, 150, 120, 100, 80, 60, 40, 25):
        for _idle in (True, False):
            _rows = _watch_line("07:26:12", _live, _v, _note, {"width": _w}, idle=_idle)
            assert 1 <= len(_rows) <= 2, _rows
            for _r in _rows:
                assert _visible_len(_r) <= _w, (
                    "width %d, idle=%s: a row is %d columns and WILL wrap: %r"
                    % (_w, _idle, _visible_len(_r), _r))

    # ⛔ THE WATCHER BREAKS AFTER THE LAST USAGE WINDOW WHEN THERE IS A BURN GAUGE, and the
    # gauge opens the second row. The owner's instruction, and it closes the hole measured in
    # 0.40.7: below 141 columns the gauge was silently dropped, so an absent Burn meant either
    # "no data yet" or "your panel is narrow" and nothing on screen told the two apart.
    # ⚠ EVEN AT WIDTH 200, where it would fit on one row. A segment that appears and vanishes
    # with the terminal is a segment nobody can rely on.
    _burn3 = (188, 106, 0.38)
    _two = _watch_line("07:26:12", _live, _v, None, {"width": 200}, burn=_burn3)
    assert len(_two) == 2, _two
    assert "Burn" not in _two[0] and "Burn" in _two[1], _two
    assert "5h" in _two[0] and "GO" in _two[0], _two[0]
    # ⛔ AND THE TWO BARS SIT IN THE SAME COLUMN. Indenting the second row by the timestamp
    # was the old rule and it aligned nothing: `5h` and `Burn` are different lengths, so the
    # bars landed two columns apart and the rows read as two unrelated lines. ⚠ The widths
    # have to match too - the usage bars carry the elapsed marker, which costs them a column
    # a plain bar does not have, so _burn_part draws BAR_WIDTH + 1.
    assert _bar_col(_two[0]) == _bar_col(_two[1]), (
        "the bars are not in one column: %r vs %r"
        % (_bar_col(_two[0]), _bar_col(_two[1])))
    # ...and both rows still fit, at every width, which is the defect this area exists for.
    for _w in (200, 150, 120, 100, 80, 60, 40, 25):
        for _idle in (True, False):
            _rr = _watch_line("07:26:12", _live, _v, _note, {"width": _w},
                              idle=_idle, burn=_burn3)
            for _r in _rr:
                assert _visible_len(_r) <= _w, (
                    "width %d idle=%s: %d columns WILL wrap: %r"
                    % (_w, _idle, _visible_len(_r), _r))

    # ⛔ THE ROW COUNT IS CONSTANT, WITH OR WITHOUT A BURN RATE. This is the fix for the
    # stranded line in the owner's screenshots: the watcher drew one row until a rate existed
    # and two afterwards, and that single 1-to-2 growth left the older row on screen. With no
    # transition there is nothing to get wrong. ⚠ And the gauge says "no data" in words
    # rather than by vanishing, which is the same rule the statusline already follows.
    _none = _watch_line("07:26:12", _live, _v, None, {"width": 200})
    assert len(_none) == 2, _none
    assert "Burn" in _none[1] and "--" in _none[1], _none
    assert _bar_col(_none[0]) == _bar_col(_none[1]), (_none, "dashes must align too")
    # ...at every width, including ones where the second row has to be cut.
    for _w in (200, 120, 80, 40, 25):
        _rr = _watch_line("07:26:12", _live, _v, _note, {"width": _w})
        assert len(_rr) == 2, (_w, _rr)
        for _r in _rr:
            assert _visible_len(_r) <= _w, (_w, _visible_len(_r), _r)

    # ⛔ AND THE CLI STATUSLINE IS UNTOUCHED - it gets ONE row from Claude Code, so a second
    # would be thrown away. The forced split is the watcher's, not a property of _line_parts.
    _sl = _line(_live, None, {"width": 200, "colour": True}, None, burn=_burn3)
    assert isinstance(_sl, str) and chr(10) not in _sl, _sl
    assert "Burn" in _sl and "5h" in _sl, _sl

    # ⭐ IDLE KEEPS THE NUMBERS, DROPS EVERY COLOUR, AND SAYS Sleep. The owner's rule: while
    # nobody is working nobody is spending, so a frozen figure cannot drift - and hiding it
    # threw away information for a danger that is not there. `Sleep` is what says the line
    # is not live.
    _idle_line = chr(10).join(
        _watch_line("07:26:12", _live, _v, _note, {"width": 200}, idle=True))
    assert SLEEP_WORD in _idle_line, _idle_line
    assert "55%" in _idle_line, "idle threw the percentage away: %r" % _idle_line
    assert _STRIP_ANSI.sub("", _idle_line) == _idle_line, (
        "the idle line is coloured: %r" % _idle_line)
    # ...and the active line is the opposite on all three counts, or the test proves nothing.
    _live_line = chr(10).join(
        _watch_line("07:26:12", _live, _v, _note, {"width": 200}, idle=False))
    assert SLEEP_WORD not in _live_line and "GO" in _live_line, _live_line
    assert _STRIP_ANSI.sub("", _live_line) != _live_line, (
        "the active line lost its colour: %r" % _live_line)

    # ⛔ AND A WINDOW THAT ALREADY RESET STILL SHOWS DASHES, EVEN IDLE. This is the one place
    # the owner's rule collides with an existing invariant, and the invariant wins: overnight
    # idle crosses the five-hour reset by construction, and a percentage stored before a
    # reset reads HIGH. Measured 2026-08-26: the display said 97% while the account page
    # said 0%.
    _past = dict(_live)
    _past["five_hour"] = {"used_percentage": 97, "resets_at": int(_now) - 60}
    _reset_line = chr(10).join(
        _watch_line("07:26:12", _past, _v, _note, {"width": 200}, idle=True))
    assert "97%" not in _reset_line, (
        "a percentage from before the reset was shown: %r" % _reset_line)
    assert SLEEP_WORD in _reset_line, _reset_line

    # ⚠ MUTATION CHECK on the width guard: a line built WITHOUT the overhead subtraction must
    # actually exceed the terminal. Without this the loop above could be passing because
    # _line() happens to be short, not because anything subtracts.
    # ⚠ The note here is the ORIGINAL 110-character one, from the owner's screenshot, because
    # that is the input that actually filled a 150-column terminal. A short note leaves _line
    # well under its budget and the control passes for the wrong reason.
    _long = ("OAuth token expires in 10 min - open a Claude session to refresh it; "
             "no session active for 7h-35m; not fetching")
    _body = _line(_live, _long, {"width": 150})
    _unfitted = "%s  %s  %s  " % ("07:26:12", _body, "GO")
    assert _visible_len(_body) <= 150, _visible_len(_body)
    assert _visible_len(_unfitted) > 150, (
        "the unfitted line is only %d columns - this check no longer proves anything"
        % _visible_len(_unfitted))
    # ...and the same input, through the function under test, must FIT - on every row.
    for _r in _watch_line("07:26:12", _live, _v, _long, {"width": 150}):
        assert _visible_len(_r) <= 150, _r

    # ⭐ TWO ROWS RATHER THAN DROPPING WHAT WILL NOT FIT. Narrow enough, and the context bar,
    # the model and the note move to a second row instead of being thrown away.
    _wide = {"ts": int(time.time() * 1000),
             "five_hour": {"used_percentage": 55, "resets_at": int(time.time()) + 1600},
             "seven_day": {"used_percentage": 32, "resets_at": int(time.time()) + 300000}}
    _two = _watch_line("07:26:12", _wide, _v, _long, {"width": 160})
    assert len(_two) == 2, "it dropped the note instead of using a second row: %r" % (_two,)
    assert "5h" in _two[0] and "GO" in _two[0], _two
    # ⚠ THE BURN GAUGE OPENS ROW TWO AND THE NOTE FOLLOWS IT. The gauge goes first because it
    # is the segment with a BAR, and the bar is what row two is aligned by; a note in front of
    # it would leave the two rows looking unrelated again. ⇒ On a row too narrow for both, the
    # note is what goes - the same right-to-left rule every other row here follows.
    assert _two[1].lstrip().startswith("Burn"), _two
    assert "OAuth" in _two[1], _two
    # ⛔ AND A LINE THAT FITS STILL SPENDS THE SECOND ROW. The old rule was the opposite -
    # "or every watcher grows a blank second one" - and that reason is gone: row two is never
    # blank now, it always carries the gauge. ⚠ The rule it replaces is what produced the
    # stranded line: one row before a burn rate existed, two after, and the single growth in
    # between left the older row on screen.
    assert len(_watch_line("07:26:12", _wide, _v, None, {"width": 200})) == 2

    # ⛔ THE MODEL-SCOPED WINDOW, against BOTH measured accounts. The rows below are the real
    # `limits[]` entries captured 2026-08-27 from an account that may NOT use Fable and one
    # that may, in Memory/tasks/20260827-153945-usage-api-fable-window/. They are inlined
    # rather than read from that folder because Memory/ is not part of the published
    # repository - a check that cannot run where the code runs is not a check.
    #
    # ⚠ WHAT SEPARATES THEM IS NOT AN ENTITLEMENT FLAG, because the response has none. The
    # row exists on both, `is_active` is false on both - it stayed false at 19% used - and
    # `nimbus_quill` read 0.0 while the scoped row read 19%, which argues against that
    # codename being Fable's counterpart. Only `percent` and `resets_at` differ.
    _cannot = {"limits": [
        {"kind": "session", "percent": 9, "is_active": False},
        {"kind": "weekly_all", "percent": 12, "is_active": True},
        {"kind": "weekly_scoped", "percent": 0, "resets_at": None, "is_active": False,
         "scope": {"model": {"id": None, "display_name": "Fable"}, "surface": None}}]}
    _can = {"limits": [
        {"kind": "session", "percent": 59, "is_active": True},
        {"kind": "weekly_all", "percent": 21, "is_active": False},
        {"kind": "weekly_scoped", "percent": 19, "is_active": False,
         "resets_at": "2026-09-02T02:59:59.602732+00:00",
         "scope": {"model": {"id": None, "display_name": "Fable"}, "surface": None}}]}
    assert _scoped_window(_cannot) is None, _scoped_window(_cannot)
    _got = _scoped_window(_can)
    assert _got and _got["label"] == "Fable" and _got["used_percentage"] == 19.0, _got
    assert isinstance(_got.get("resets_at"), int), _got

    # ⭐ THE MODEL IS NOT HARD-CODED: the row names itself, so another scoped model works.
    _other = {"limits": [{"kind": "weekly_scoped", "percent": 4, "is_active": False,
                          "resets_at": None,
                          "scope": {"model": {"display_name": "Mythos"}}}]}
    assert (_scoped_window(_other) or {}).get("label") == "Mythos", _scoped_window(_other)

    # ⛔ AND NOTHING ELSE IN limits[] MAY BE MISTAKEN FOR ONE. `session` and `weekly_all` are
    # not scoped, and a scoped row with no model name is not usable.
    assert _scoped_window({"limits": [{"kind": "session", "percent": 99}]}) is None
    assert _scoped_window({"limits": [{"kind": "weekly_scoped", "percent": 9,
                                       "scope": {}}]}) is None
    assert _scoped_window({}) is None and _scoped_window(None) is None

    # ⭐ It reaches the line, and ONLY when there is one. The owner asked for no extra text
    # on an account that has none - not "cannot use Fable", nothing at all.
    _with = {"ts": int(time.time() * 1000),
             "five_hour": {"used_percentage": 55, "resets_at": int(time.time()) + 1600},
             "scoped": _got}
    _shown = _line(_with, None, {"width": 200})
    assert "Fable" in _shown, _shown
    _without = dict(_with)
    del _without["scoped"]
    _plain = _line(_without, None, {"width": 200})
    assert "Fable" not in _plain and "annot" not in _plain, _plain

    # ⛔ AND IT DEGRADES LIKE THE OTHER BARS, or it is the one bar that lies. Past its reset,
    # dashes - not a percentage stored before the window turned over.
    _old = dict(_with)
    _old["scoped"] = dict(_got, resets_at=int(time.time()) - 60)
    assert "19%" not in _line(_old, None, {"width": 200}), _line(_old, None, {"width": 200})

    # ⛔ WHEN THE WINDOW RUNS OUT, NOT ONLY WHETHER. "Projected 175% by reset" says it will
    # be exhausted and leaves the reader to work out whether there is room for another wave.
    # ⚠ AND None MEANS UNKNOWABLE, NEVER SAFE - three ways to get there, each checked, because
    # a missing warning and a warning that says "fine" look identical on a screen.
    _bt = tempfile.mkdtemp(prefix="dg-burn-")
    _blogs = os.path.join(_bt, "logs")
    os.makedirs(_blogs)
    # ⚠ burn_window_min 0 = the WHOLE window, which is what these fixtures were written
    # against. The trailing baseline gets its own block below rather than silently changing
    # what every case here means.
    _bcfg = {"history_dir": _blogs, "soft_pct_5h": 70, "hard_pct_5h": 85, "stale_min": 15,
             "near_reset_min": 10, "soft_pct_7d": 95, "hard_pct_7d": 97,
             "burn_window_min": 0, "debug": {"token_usage": True}}
    _bnow = time.time()

    def _plant(rows, resets):
        for _f in glob.glob(os.path.join(_blogs, "*.jsonl")):
            os.remove(_f)
        with open(os.path.join(_blogs, HISTORY_PREFIX + "20200101-000000.jsonl"),
                  "w", encoding="utf-8") as _f:
            for _at, _pct in rows:
                _f.write(json.dumps({"at": stamp(_at), "pct": _pct,
                                     "resets_at": stamp(resets)}) + chr(10))

    # ⚠ THE FIXTURE OPENS ITS WINDOW WHERE ITS FIRST ROW IS, at zero used, so the anchor is a
    # no-op here and the arithmetic stays readable: 55 points in 55 minutes is 1 %/min, and
    # from 55% there are 45 points left, so ~45 minutes. A fixture logged LATE would be
    # measuring the anchor instead of the burn-out; the anchor gets its own check below.
    _far = _bnow + 245 * 60                          # ⇒ the window opened 55 minutes ago
    _rows = [(_far - 5 * 3600, 0), (_bnow - 1, 55)]
    _plant(_rows, _far)
    _b = burnout_min(_bt, _bcfg, 55, _far, _bnow)
    assert _b is not None and 40 <= _b <= 50, _b
    # ⭐ The projection and the burn-out must agree, because they share one sampling. A window
    # projected past 100% MUST have a burn-out inside it, or the line contradicts itself.
    _pj = _projection(_bt, _bcfg, 55, _far, _bnow)
    assert _pj is not None and _pj >= 100 and _b < (_far - _bnow) / 60, (_pj, _b)

    _v = verdict(_bt, _bcfg, data={"ts": int(_bnow * 1000),
                                   "five_hour": {"used_percentage": 55,
                                                 "resets_at": int(_far)}})
    assert _v["burns_out_early"] is True, _v
    assert "SPENT in ~" in _v["text"] and "BEFORE it resets" in _v["text"], _v["text"]

    # ⛔ AND IT MUST STAY QUIET when the window resets first - the same rate, a nearer reset.
    _near = _bnow + 20 * 60
    _plant([(_near - 5 * 3600, 0), (_bnow - 1, 55)], _near)
    _vn = verdict(_bt, _bcfg, data={"ts": int(_bnow * 1000),
                                    "five_hour": {"used_percentage": 55,
                                                  "resets_at": int(_near)}})
    assert _vn["burns_out_early"] is False, _vn
    assert "SPENT in ~" not in _vn["text"], _vn["text"]

    # ⚠ THE UNKNOWABLE CASES. Each returns None and none of them warns.
    # ⛔ "Flat" MEANS FLAT FROM THE WINDOW'S OPEN, not flat across the logged rows: two equal
    # rows late in a window still describe a climb from zero, which is a rate.
    _plant([(_bnow - 1800, 0), (_bnow - 1, 0)], _far)            # flat: no rate
    assert burnout_min(_bt, _bcfg, 0, _far, _bnow) is None
    _short = _bnow + 5 * 3600 - 60                               # opened 60 seconds ago
    _plant([(_bnow - 1, 55)], _short)                            # under 5 min of span
    assert burnout_min(_bt, _bcfg, 55, _short, _bnow) is None
    for _f in glob.glob(os.path.join(_blogs, "*.jsonl")):        # no history at all
        os.remove(_f)
    assert burnout_min(_bt, _bcfg, 55, _far, _bnow) is None
    # ...and a window already at 100% is not "unknowable", it is spent NOW.
    _plant(_rows, _far)
    assert burnout_min(_bt, _bcfg, 100, _far, _bnow) == 0

    # ⭐ THE WINDOW'S OWN START AS THE ANCHOR: THE WINDOW'S OWN START COUNTS. Logging does not begin when the window
    # does - a reinstall, a first run, a machine that was off - and reading only the logged
    # rows lets a busy tail stand for the whole window. MEASURED on a second machine: the
    # window opened at 14:10, the first row is 16:49 with 35% ALREADY SPENT, and those rows
    # gave 0.48 %/min for a window whose true average was 0.22.
    # ⇒ Same last reading, logged late: the anchored rate must come out well UNDER what the
    # logged segment alone says.
    _aw = _bnow + 60 * 60                                        # opened 4 hours ago
    _open = _aw - 5 * 3600
    _plant([(_bnow - 1800, 35), (_bnow - 1, 52)], _aw)           # 17 points in 30 min
    _ar = _burn_rate(_bt, _bcfg, 52, _aw, _bnow) * 60
    _seg = (52 - 35) / 30.0                                      # 0.567 %/min
    assert _ar < _seg / 2, "the unlogged head was ignored: %.3f vs %.3f %%/min" % (_ar, _seg)
    # ...and what it lands on is the whole-window average, the only thing knowable about a
    # stretch nobody recorded.
    assert abs(_ar - 52.0 / ((_bnow - _open) / 60.0)) < 0.01, _ar
    # ⚠ AND A NO-OP WHERE LOGGING DID COVER THE WINDOW: the first row already sits at the
    # open with nothing used, so the anchor lands on top of it.
    _plant([(_open, 0), (_bnow - 1, 52)], _aw)
    assert abs(_burn_rate(_bt, _bcfg, 52, _aw, _bnow) * 60 - _ar) < 0.01
    # ⭐ ONE LOGGED ROW IS NOW ENOUGH, which is the whole point: a machine that has just
    # started logging still gets a rate, where before it got None.
    _plant([(_bnow - 1, 52)], _aw)
    assert abs(_burn_rate(_bt, _bcfg, 52, _aw, _bnow) * 60 - _ar) < 0.01

    # ⭐⭐ THE TRAILING BASELINE - what the gauge actually uses. The owner asked for a gauge
    # that reacts to the last half hour rather than to the whole window, and the two answers
    # differ by an order of magnitude on the same history. Every case below plants ONE history
    # and reads it two ways, so what is being checked is the baseline and nothing else.
    _tt = tempfile.mkdtemp(prefix="dg-trail-")
    _tlogs = os.path.join(_tt, "logs")
    os.makedirs(_tlogs)
    _t30 = {"history_dir": _tlogs, "burn_window_min": 30, "debug": {"token_usage": True}}
    _tall = dict(_t30, burn_window_min=0)
    _tnow = time.time()

    def _rate(cfgd, pct, resets, why):
        """The rate as %/min, refusing to be None - a None here is the defect, not a case."""
        _r = _burn_rate(_tt, cfgd, pct, resets, _tnow)
        assert _r is not None, "no rate where one is measurable: %s" % why
        return _r * 60

    def _tplant(rows, resets):
        for _f in glob.glob(os.path.join(_tlogs, "*.jsonl")):
            os.remove(_f)
        with open(os.path.join(_tlogs, HISTORY_PREFIX + "20200101-000000.jsonl"),
                  "w", encoding="utf-8") as _f:
            for _at, _pct in rows:
                _f.write(json.dumps({"at": stamp(_at), "pct": _pct,
                                     "resets_at": stamp(resets)}) + chr(10))

    # A window that opened 200 minutes ago, so the cut at 30 minutes is well inside it.
    _tres = _tnow + 100 * 60
    _topen = _tres - 5 * 3600

    # ⛔ BURNED HARD EARLY, QUIET NOW. The whole-window figure still reports the morning; the
    # trailing one reports the last half hour, which is the question the gauge is asked.
    _tplant([(_topen + 60, 0), (_topen + 30 * 60, 40), (_tnow - 40 * 60, 40)], _tres)
    _slow = _rate(_t30, 41, _tres, "quiet tail, 30 min baseline")
    _whole = _rate(_tall, 41, _tres, "quiet tail, whole window")
    assert abs(_slow - 1.0 / 30.0) < 0.001, (
        "the baseline is not the last 30 minutes: %.4f, expected %.4f %%/min - the whole "
        "window reads %.4f" % (_slow, 1.0 / 30.0, _whole))
    assert _whole > 5 * _slow, (_whole, _slow)

    # ⭐ AND THE REVERSE, which is the whole point: quiet early, busy now. The whole-window
    # figure is still reporting the quiet hours while the machine is spending fast.
    _tplant([(_topen + 60, 0), (_tnow - 40 * 60, 5)], _tres)
    _fast = _rate(_t30, 25, _tres, "busy tail, 30 min baseline")
    _whole = _rate(_tall, 25, _tres, "busy tail, whole window")
    assert abs(_fast - 20.0 / 30.0) < 0.001, (
        "the baseline is not the last 30 minutes: %.4f, expected %.4f %%/min - the whole "
        "window reads %.4f" % (_fast, 20.0 / 30.0, _whole))
    assert _fast > 5 * _whole, (_fast, _whole)

    # ⛔ THE END POINT IS `now`, NOT THE LAST LOGGED ROW - the bug this replaces. Rows are
    # written only when a number MOVES, so an idle stretch writes nothing and reading the last
    # row as "now" froze both ends: the same number was redrawn while time passed.
    # ⚠ Asked over the WHOLE window so the last row is the only candidate endpoint.
    _tplant([(_topen + 60, 0), (_tnow - 90 * 60, 30)], _tres)
    _live = _rate(_tall, 30, _tres,
                  "the end point is the last logged row again, so the span ran backwards")
    assert abs(_live - 30.0 / 200.0) < 0.001, (
        "the rate does not end at `now`: %.5f, expected %.5f %%/min" % (_live, 30.0 / 200.0))
    _frozen = 30.0 / ((_tnow - 90 * 60 - _topen) / 60.0)   # what the last row alone gives
    assert _live < _frozen * 0.6, (_live, _frozen)

    # ⚠ AND IDLE READS AS UNKNOWABLE, NOT AS SAFE. Nothing was spent inside the baseline, so
    # there is no rate to draw - and _burn_part() gives that its own glyph rather than an
    # empty bar, because empty means DANGER in that column.
    _tplant([(_topen + 60, 0), (_tnow - 90 * 60, 30)], _tres)
    assert _burn_rate(_tt, _t30, 30, _tres, _tnow) is None
    assert "─" in _burn_part(None, 100, None, {"colour": False})

    # ⭐ INSIDE THE FIRST burn_window_min MINUTES THE ANCHOR STILL CARRIES IT, with no logged
    # row at all: the cut reaches back past the open, and a window opens at zero by definition.
    _young = _tnow + 5 * 3600 - 20 * 60                    # opened 20 minutes ago
    _tplant([], _young)
    assert _burn_rate(_tt, _t30, 10, _young, _tnow) is None      # no history file: unknowable
    _tplant([(_tnow - 60, 10)], _young)
    _anch = _rate(_t30, 10, _young, "young window, anchor at the open")
    assert abs(_anch - 10.0 / 20.0) < 0.001, _anch
    shutil.rmtree(_tt, ignore_errors=True)

    # ⛔ AND THE FLOOR IS CLAMPED UP RATHER THAN SILENTLY DISABLING THE GAUGE. Under five
    # minutes the span guard refuses every sample, so a well-meant 2 would switch the gauge
    # off for ever instead of making it twitchy. ⚠ 0 is NOT clamped - it asks for the whole
    # window - and that distinction is the whole reason this check exists.
    _cdir = tempfile.mkdtemp(prefix="dg-bwcfg-")
    assert config(_cdir)["burn_window_min"] == DEFAULTS["burn_window_min"]
    for _v, _want in ((2, BURN_WINDOW_FLOOR_MIN), (0, 0), (-1, DEFAULTS["burn_window_min"]),
                      (45, 45)):
        with open(os.path.join(_cdir, "config.json"), "w", encoding="utf-8") as _f:
            json.dump({"burn_window_min": _v}, _f)
        assert config(_cdir)["burn_window_min"] == _want, (_v, config(_cdir))
    shutil.rmtree(_cdir, ignore_errors=True)
    shutil.rmtree(_bt, ignore_errors=True)

    # ⛔ THE REDRAW IS ABSOLUTE, AND THAT IS THE WHOLE POINT. A relative climb (`\033[1A`)
    # moves up from wherever the cursor IS, so it is correct only while nothing else has moved
    # it - and in a VS Code panel that is not this process's to control. Measured 2026-08-29,
    # after both the fixed row count and wrapping-off: the FIRST draw was still stranded, so
    # the cursor was already a row lower than any arithmetic believed. ⇒ No climb at all.
    # ⚠ The bytes are asserted rather than the intent: "homed" and "homed one row too far"
    # produce the same shape and different screens.
    assert _redraw(["a"], "<K>") == "\033[H\ra<K>\033[J", _redraw(["a"], "<K>")
    assert _redraw(["a", "b"], "<K>") == "\033[H\ra<K>\n\rb<K>\033[J", _redraw(["a", "b"], "<K>")
    # ⛔ NO RELATIVE MOVE MAY SURVIVE ANYWHERE IN IT. One `\033[1A` left behind is the whole
    # defect back, and it would look like a cosmetic difference in a diff.
    for _n_rows in (1, 2, 3):
        assert "\033[1A" not in _redraw(["x"] * _n_rows, "<K>"), _n_rows
    # ⚠ SHRINKING NEEDS NO COUNTING. `\033[J` clears from the cursor to the bottom, so a draw
    # with fewer rows than the last cannot leave one behind - the old code padded with blanks
    # instead, and the padding had to know the previous height.
    assert _redraw(["a", "b"], "<K>").endswith("\033[J")

    # ⭐ TWO ROWS ARE A SETTING, AND BOTH SURFACES OBEY IT. The statusline was capped at one
    # row on a BELIEF, not a limit: the documentation says "each `echo` or `print` statement
    # displays as a separate row", and the shipped binary splits the command's output on
    # newlines and counts them. ⇒ Throwing the context bar and the note away to fit one row
    # was this plugin's choice, and it is now the owner's.
    _tr = {"ts": int(time.time() * 1000),
           "five_hour": {"used_percentage": 55, "resets_at": int(time.time()) + 1600},
           "seven_day": {"used_percentage": 32, "resets_at": int(time.time()) + 300000}}
    # ⚠ A REALISTIC note, not an absurd one. The real ones are this shape - the age, the idle
    # reason, the token warning - and a 150-character fixture would prove only that _fit()
    # drops parts it cannot fit, which is not the behaviour under test.
    _tnote = "12 min old; idle 7h-35m; OAuth token expires in 10m - open a session"
    for _pay in (None, {"model": {"display_name": "Opus 5"},
                        CONTEXT_KEY: {"used_percentage": 41}}):
        _on = line_rows(_tr, _tnote, {"width": 100, "two_rows": True}, _pay)
        _off = line_rows(_tr, _tnote, {"width": 100, "two_rows": False}, _pay)
        assert len(_on) == 2, "two_rows:true did not use a second row: %r" % (_on,)
        assert len(_off) == 1, "two_rows:false used %d rows: %r" % (len(_off), _off)
        for _r in _on + _off:
            assert _visible_len(_r) <= 100, (_visible_len(_r), _r)
        # ⛔ THE SECOND ROW MUST CARRY WHAT THE ONE-ROW FORM THREW AWAY, or it costs a row of
        # the terminal and buys nothing. ⚠ A note this long still gets CUT on the second row
        # at width 100 - what matters is that its opening survives there and nowhere in the
        # one-row form.
        assert "OAuth token expires" in _on[1], _on
        assert "OAuth token expires" not in _off[0], _off
        # ...and the five-hour window is on the FIRST row either way - it is what the brake
        # acts on, and a display that can hide it is worse than a narrower one.
        assert "5h" in _on[0] and "5h" in _off[0], (_on, _off)

    # ⚠ AND THE WATCHER READS THE SAME KEY. One question, one answer: they had different ones
    # for a while and that is how two surfaces drift.
    _v2 = {"verdict": "GO", "pct": 55}
    assert len(_watch_line("07:26:12", _tr, _v2, _tnote,
                           {"width": 100, "two_rows": True})) == 2
    assert len(_watch_line("07:26:12", _tr, _v2, _tnote,
                           {"width": 100, "two_rows": False})) == 1

    # ⚠ A line that FITS stays on one row whatever the setting, or every display grows a
    # blank second row it does not need.
    assert len(line_rows(_tr, None, {"width": 200, "two_rows": True})) == 1

    # ⛔ THE BRAKE WEIGHS BOTH WINDOWS. It used to read the five-hour percentage and nothing
    # else: the seven-day figure produced a NOTE and never a level, so an account at 7d 99%
    # beside 5h 0% was told GO and kept dispatching until the SERVER refused. Both numbers
    # were true and the answer was wrong, which is the shape of every defect in this file.
    _bnow2 = time.time()
    _bc = {"soft_pct_5h": 70, "hard_pct_5h": 85, "soft_pct_7d": 95, "hard_pct_7d": 97,
           "near_reset_min": 20, "stale_min": 15, "debug": {"token_usage": False}}
    _bdir = tempfile.mkdtemp(prefix="dg-brake-")

    def _verdict(p5, p7, r5=None, r7=None):
        return verdict(_bdir, _bc, data={
            "ts": int(_bnow2 * 1000),
            "five_hour": {"used_percentage": p5,
                          "resets_at": int(r5 if r5 else _bnow2 + 3 * 3600)},
            "seven_day": {"used_percentage": p7,
                          "resets_at": int(r7 if r7 else _bnow2 + 3 * 86400)}})

    _v = _verdict(0, 99)
    assert (_v["verdict"], _v["driver"]) == ("STOP", "7d"), _v
    # ⭐ AND IT SAYS WHICH WINDOW, or the reader looks at 5h 0% and concludes the brake is
    # broken - which is how a guard gets switched off.
    assert "7d at 99%" in _v["text"] and "5h window is NOT the constraint" in _v["text"], _v
    assert _verdict(0, 96)["verdict"] == "PACE", _verdict(0, 96)
    assert _verdict(0, 90)["verdict"] == "GO", _verdict(0, 90)
    # ...and the five-hour thresholds still do their own job, unchanged.
    assert (_verdict(90, 10)["verdict"], _verdict(90, 10)["driver"]) == ("STOP", "5h")
    assert _verdict(75, 10)["verdict"] == "PACE"
    # ⚠ TIES GO TO THE FIVE-HOUR WINDOW, because it is the nearer and more actionable one.
    assert _verdict(90, 99)["driver"] == "5h", _verdict(90, 99)

    # ⛔ A SEVEN-DAY WINDOW THAT RESETS FIRST IS NOT A CONSTRAINT, and that judgement predates
    # the four thresholds. Its percentage is about to become zero; braking on it would brake
    # on a number on its way out.
    _v = _verdict(0, 99, r7=_bnow2 + 1800)
    assert _v["verdict"] == "GO", _v
    assert "IGNORE, not a constraint" in _v["text"], _v

    # ⛔ AND THE EARLY RETURN THAT THREW THE WEEK AWAY. A five-hour window that has already
    # turned over used to return GO on the spot - so an account whose WEEK was spent was told
    # GO the moment its five-hour window rolled over.
    _v = _verdict(0, 99, r5=_bnow2 - 60)
    assert (_v["verdict"], _v["driver"]) == ("STOP", "7d"), _v
    # ...while the same reset with a quiet week is still the plain "treat usage as fresh".
    _v = _verdict(0, 10, r5=_bnow2 - 60)
    assert _v["verdict"] == "GO" and "already reset" in _v["text"], _v

    # ⚠ NEAR-RESET SOFTENING IS PER WINDOW. A 5h STOP twelve minutes from its reset softens;
    # a 7d STOP three days out does not, and one shared test would have softened both.
    assert _verdict(90, 10, r5=_bnow2 + 12 * 60)["verdict"] == "PACE"
    assert _verdict(0, 99)["verdict"] == "STOP"
    assert _verdict(0, 99, r7=_bnow2 + 12 * 60)["verdict"] == "GO", "7d resets first"
    shutil.rmtree(_bdir, ignore_errors=True)

    # ⛔ THE BURN GAUGE. It answers ONE forward-looking question - can I keep spending - by
    # measuring the budget's life against the TIME LEFT IN THE WINDOW. Full bar means the
    # window resets before you run dry.
    _bcfg2 = {"colour": True, "width": 200}
    _full = _burn_part(188, 106, 0.38, _bcfg2)          # outlasts the reset
    _half = _burn_part(80, 119, 0.60, _bcfg2)           # 67% of the time left
    _dry = _burn_part(12, 130, 3.40, _bcfg2)            # 9%
    # ⛔ THE TAIL IS A TIME IN EVERY CASE NOW, including this one where the burn-out lands
    # AFTER the reset. The owner's instruction: the words cost fourteen columns to repeat
    # what the full bar already says. ⚠ 188 minutes with 106 left, so the number printed is
    # deliberately LONGER than the window has - that is when burn-out lands, not a promise.
    assert "3h-8m left" in _full and BAR_EMPTY not in _STRIP_ANSI.sub("", _full), _full
    # ⛔ AND IT IS BAR_WIDTH + 1 WIDE, like the Ctx segment and unlike a bare bar. The three
    # usage bars carry the elapsed marker, which sits between cells and costs them a column;
    # a burn bar one narrower cannot line up beneath them however the row is indented.
    # ⚠ Column equality alone does NOT catch this - both start in the same place and end in
    # different ones - so it is asserted separately. Mutation-checked: BAR_WIDTH here and the
    # alignment check still passes while the rows visibly disagree.
    _glyphs = [c for c in _STRIP_ANSI.sub("", _full) if c in (BAR_FULL, BAR_EMPTY, BAR_MARK)]
    assert len(_glyphs) == BAR_WIDTH + 1, (len(_glyphs), _full)
    assert "outlasts" not in _full and ANSI["ok"] in _full, _full
    assert "left" in _half and ANSI["warn"] in _half, _half
    assert ANSI["alarm"] in _dry, _dry
    # ⚠ COLOUR IS INVERTED HERE, and _colour() must not be used: everywhere else a HIGH
    # number is bad, so the shared thresholds would paint safety red. Pinned by asserting
    # the FULL bar is ok-coloured, which _colour() would never do for a large value.
    assert ANSI["alarm"] not in _full and ANSI["warn"] not in _full, _full

    # ⛔ UNKNOWABLE IS NEVER AN EMPTY BAR AND NEVER A ZERO. In a column where empty means
    # DANGER, drawing "no data" as empty says the opposite of the truth.
    for _u in (_burn_part(None, 119, 0, _bcfg2),
               _burn_part(188, 0, 0.38, _bcfg2),
               _burn_part(188, 106, 0.38, _bcfg2, stale=True)):
        assert BAR_EMPTY not in _u and BAR_FULL not in _u, _u
        assert "0.00%/m" not in _u and "0m left" not in _u, _u
        assert "--" in _u and _STRIP_ANSI.sub("", _u) == _u, _u

    # ⭐ IT REACHES THE LINE, on the FIRST row, after the windows - it is a decision input
    # like they are, not context like the model name.
    _brec = {"ts": int(time.time() * 1000),
             "five_hour": {"used_percentage": 29, "resets_at": int(time.time()) + 5900}}
    _wins, _extras = _line_parts(_brec, None, _bcfg2, None, burn=(188, 106, 0.38))
    assert any(w.startswith("Burn") for w in _wins), _wins
    assert not any(x.startswith("Burn") for x in _extras), _extras
    assert _wins[0].startswith("5h"), "the burn segment displaced the five-hour window"
    # ...and it is the LAST of them, so a narrow terminal drops it before any usage bar.
    assert _wins[-1].startswith("Burn"), _wins

    # ⚠ Absent when there is nothing to show, and switchable.
    assert not any(w.startswith("Burn")
                   for w in _line_parts(_brec, None, _bcfg2, None, burn=None)[0])
    assert not any(w.startswith("Burn") for w in _line_parts(
        _brec, None, dict(_bcfg2, show_burn=False), None, burn=(188, 106, 0.38))[0])

    # ⛔ AND burn_triple() MUST REFUSE A WINDOW THAT HAS ALREADY RESET, where the stored
    # percentage reads stale-high and any rate computed from it is meaningless.
    _past = {"five_hour": {"used_percentage": 97, "resets_at": int(time.time()) - 60}}
    assert burn_triple(tempfile.gettempdir(), {}, _past) is None
    assert burn_triple(tempfile.gettempdir(), {}, {}) is None

    # ⛔ THE PROJECTION MUST NOT SET THE VERDICT. Switched off deliberately, and pinned here
    # so switching it back on is a decision somebody makes on purpose rather than a line that
    # creeps back.
    #
    # ⚠ WHAT IT DID, measured on a second machine's real history: the verdict flipped
    # GO→PACE→GO→PACE→GO in twelve minutes while the PERCENTAGE climbed smoothly from 40% to
    # 52%, never within twenty points of soft_pct_5h. The boundary is
    # (100 - pct) / minutes_left, so at 47% with 114 minutes left a swing of one HUNDREDTH of
    # a percent per minute crosses it - and under bursty dispatch the rate swings far more
    # than that between two samples. Since 0.35.0 a PACE also makes a handoff a precondition
    # of dispatching, so one flickering sample blocked a dispatch that should have gone
    # through.
    _pdir = tempfile.mkdtemp(prefix="dg-proj-")
    _plogs = os.path.join(_pdir, "logs")
    os.makedirs(_plogs)
    _pcfg = {"history_dir": _plogs, "soft_pct_5h": 70, "hard_pct_5h": 85,
             "soft_pct_7d": 95, "hard_pct_7d": 97, "near_reset_min": 20, "stale_min": 15,
             "burn_window_min": 0, "debug": {"token_usage": True}}
    _pnow = time.time()
    # ⚠ 47% SPENT IN THE FIRST HOUR OF THE WINDOW, which is what a projection over 100% takes
    # once the rate is anchored at the window's open (0.38.0). The incident above happened at
    # 114 minutes left, and that shape can no longer project over the line at all: 47% with
    # 186 of 300 minutes gone is 0.25 %/min, and it projects to 76%. ⇒ Anchoring removed the
    # exact reading that flipped the verdict; the pin stays anyway, because it guards the
    # decision - display-only - and not that one reading.
    _presets = _pnow + 240 * 60                      # ⇒ the window opened 60 minutes ago
    with open(os.path.join(_plogs, HISTORY_PREFIX + "20200101-000000.jsonl"),
              "w", encoding="utf-8") as _f:
        for _t, _p in ((_pnow - 1800, 23.5), (_pnow - 1, 47)):
            _f.write(json.dumps({"at": stamp(_t), "pct": _p,
                                 "resets_at": stamp(_presets)}) + chr(10))
    _pv = verdict(_pdir, _pcfg, data={"ts": int(_pnow * 1000),
                                      "five_hour": {"used_percentage": 47,
                                                    "resets_at": int(_presets)}})
    assert _pv["projected_pct"] is not None and _pv["projected_pct"] >= 100, _pv
    assert _pv["verdict"] == "GO", (
        "the projection is setting the verdict again - it is display-only, and re-enabling "
        "it needs hysteresis and a minimum history first. See the block in verdict(): %r"
        % (_pv,))
    # ⭐ ...but it is still REPORTED, or switching it off would have hidden the figure the
    # owner wants to watch.
    assert _pv["burnout_min"] is not None, _pv

    # ⛔ AND NEITHER BURN FIGURE MAY REACH THE WORD - the owner's instruction, 2026-08-29:
    # "GO / PACE / STOP 派工或剎車都不參考這個值". The pin above covers the projection only,
    # and burnout_min is a second way in: it is computed in verdict(), it is returned, and it
    # writes a sentence into the text. One `if` on `early` would silently make it a brake.
    # ⚠ FORCED, NOT READ. Both figures are driven to their worst - "spent in one minute" and
    # "projected 999%" - at a percentage twenty-three points under soft_pct_5h. Reading the
    # code proves what it says; forcing proves what it does.
    _fb, _fp = burnout_min, _projection
    globals()["burnout_min"] = lambda *a, **k: 1
    globals()["_projection"] = lambda *a, **k: 999
    try:
        _forced = verdict(_pdir, _pcfg, data={"ts": int(_pnow * 1000),
                                              "five_hour": {"used_percentage": 47,
                                                            "resets_at": int(_presets)}})
    finally:
        globals()["burnout_min"], globals()["_projection"] = _fb, _fp
    # The forcing must REACH the figures, or the check passes by never running the path.
    assert _forced["burnout_min"] == 1 and _forced["projected_pct"] == 999, _forced
    assert _forced["verdict"] == "GO" and _forced["exit"] == 0, (
        "a burn figure moved the verdict - the brake must not read it. See the owner's "
        "instruction in Memory/notes/SHELVED-burn-meter.md: %r" % (_forced,))
    # ⭐ ...and it still WARNS, which is the whole design: a sentence, never a decision.
    assert "SPENT in ~1 min" in _forced["text"], _forced["text"]
    shutil.rmtree(_pdir, ignore_errors=True)

    print("selftest OK")
    return 0


def fetch_now(sdir, cfg):
    """`usage.py --fetch-now` - spend one call, then print the verdict. Exit code is it.

    ⛔ WHY THIS EXISTS AS A NAMED MODE. The capability was already here but unreachable by
    anyone who had not read the source: only --statusline and --watch fetch, so the way to
    turn a NO-DATA into a number was to pipe an empty JSON object into STATUSLINE mode -
    `echo {} | usage.py --statusline`. Nobody guesses that. A brake whose one repair is
    undiscoverable is a brake that stays broken.

    ⚠ It spends one of about five calls per access token, so it is a DIAGNOSTIC, not a
    substitute for the statusline or for `--watch`. Those two are what keep the number
    fresh; this answers "is the instrument broken, or is the number real?" once.

    ⭐ It is also the honest answer to "should I probe usage by dispatching a cheap agent?"
    No: an agent that replies proves only that nothing is hard-blocked right now, carries no
    percentage and no reset time, costs the most expensive action in the protocol, and pays
    for it out of the very allowance being measured. This costs one HTTP GET and returns the
    real number.
    """
    record, reason = ensure_fresh(sdir, cfg)
    if reason:
        print("fetch FAILED: %s" % reason)
    v = verdict(sdir, cfg)
    print(v["text"])
    return v["exit"]


def main():
    argv = sys.argv[1:]
    if "--selftest" in argv:
        return selftest()
    sdir = state_dir(argv)
    cfg = config(sdir)
    if "--fetch-now" in argv:
        return fetch_now(sdir, cfg)
    if "--statusline" in argv:
        return collect(sdir, cfg)
    if "--watch" in argv:
        return watch(sdir, cfg, argv)
    result = verdict(sdir, cfg)
    if "--json" in argv:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(result["text"])
    return result["exit"]


def _utf8_console():
    """Make output survive a legacy console codepage.

    ⛔ Windows consoles default to a legacy codepage - cp950 on this machine - and a
    single non-ASCII character in a message then raises UnicodeEncodeError and kills the
    script. Measured 2026-08-26: install.py wrote its file and THEN crashed on the very
    warning explaining what to do next, so the user saw a traceback instead of the
    instruction. errors="replace" is deliberate: a mangled glyph is a cosmetic problem,
    a crash is not.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


if __name__ == "__main__":
    _utf8_console()
    try:
        sys.exit(main())
    except Exception as exc:
        # ⛔ Never take the statusline or a hook down. A broken usage check must look
        # like "unknown", not like a crash the caller has to interpret.
        sys.stderr.write("usage.py: %r\n" % (exc,))
        sys.exit(3)
