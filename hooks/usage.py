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
    "soft_pct": 70,          # PACE  - finish what is in flight, start nothing heavy
    "hard_pct": 85,          # STOP  - wrap up and schedule a resume
    "stale_min": 15,         # data older than this is not trusted
    "near_reset_min": 20,    # within this long of the reset, soften by one level
    "colour_warn_pct": 70,   # bar turns orange at or above this
    "colour_alarm_pct": 85,  # bar turns red at or above this
    "seven_day_binding_pct": 95,
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
# must not - and token_note(), which gets the same warning for free by READING the expiry.
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


TOKEN_WARN_SECONDS = 600         # warn a person this long before the token dies


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


def token_note():
    """A warning for a PERSON while the token still works, or None. Makes no request.

    ⭐ THIS IS THE POINT: a 401 tells you the token is already dead, which is too late to
    act on and costs one of the five calls to discover. The expiry is sitting in the
    credentials file, so it can be read for free and BEFORE the fact.

    ⚠ A warning that fixes itself is the expected case, not a bug. Whichever Claude client
    is running rotates the token roughly five minutes before it expires, so a warning that
    appears inside this window normally vanishes on its own. ⭐ One that PERSISTS is the
    real signal: nothing is running that will refresh it.
    """
    _, expires = _token_and_expiry()
    if expires is None:
        return None
    left = expires - time.time()
    if left <= 0:
        return "OAuth token EXPIRED - open a Claude session to refresh it"
    if left <= TOKEN_WARN_SECONDS:
        return ("OAuth token expires in %d min - open a Claude session to refresh it"
                % max(1, round(left / 60.0)))
    return None


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
        # ⚠ ROUNDED, not truncated. Observed live: the same window came back as
        # 11:00:00.203505Z once and 10:59:59.9xxZ later, and int() floors those to
        # 1787742000 and 1787741999 - so the reset appeared to move by a second and the
        # "did a number move?" check flapped. round() lands both on the same whole second.
        out["resets_at"] = int(round(resets))
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
                 and prev.get("seven_day") == record.get("seven_day"))
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
    # ⭐ Shown WHETHER OR NOT the data is stale, unlike a fetch failure. It is actionable
    # and it is early: by the time a 401 appears the numbers have already stopped.
    tnote = token_note()
    if tnote:
        note = "%s; %s" % (note, tnote) if note else tnote

    _note_render(sdir, payload, record.get("five_hour") or {})
    print(_line(record, note, cfg, payload))
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


def _visible_len(text):
    """Length as the terminal sees it: ANSI codes occupy no columns."""
    return len(re.sub(r"\x1b\[[0-9;]*m", "", text))


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


def _line(record, stale_note=None, cfg=None, payload=None):
    """One rendered line, trimmed from the right until it fits.

    ⛔ WRAPPING IS WHY THIS EXISTS. A status line that spills onto a second row does not
    merely look untidy - it pushes the prompt around and reads as a bug. claude-pacer
    solved it with three responsive layouts and width probing; that is the large half of
    that project. This does the small version: parts are ordered by how much they are
    worth, and the least valuable are dropped until the line fits.
    """
    rec = record or {}
    cfg = cfg or {}
    now = time.time()
    # ⛔ One decision, applied to both windows: is the stored value old enough that showing
    # it as a percentage would mislead? stale_note is set by the caller from the file's age.
    stale = bool(stale_note)
    parts = [_window("5h", rec.get("five_hour"), now, cfg, 5 * 3600, stale)]
    if isinstance(rec.get("seven_day"), dict):
        parts.append(_window("7d", rec["seven_day"], now, cfg, 7 * 86400, stale))
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
            parts.append("Ctx %s %s" % (BAR_EMPTY * (BAR_WIDTH + 1), "--"))
        else:
            on, off = _colour(cpct, cfg)
            parts.append("Ctx %s%s %d%%%s"
                         % (on, _bar(cpct, BAR_WIDTH + 1), round(cpct), off))
    if payload and cfg.get("show_model", True):
        mp = _model_part(payload)
        if mp:
            parts.append(mp)
    if stale_note:
        parts.append("(%s)" % stale_note)

    width = terminal_width(cfg)
    if not width:
        return "  ".join(parts)
    # Drop from the right - the rightmost parts are the least load-bearing - but never
    # drop the 5h window, which is the one the brake acts on.
    while len(parts) > 1 and _visible_len("  ".join(parts)) > width:
        parts.pop()
    return "  ".join(parts)


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

    # A window that has already turned over makes the stored percentage meaningless -
    # and it will read stale-HIGH, which is the dangerous direction.
    if now >= resets:
        return {"verdict": "GO", "exit": 0, "pct": pct, "age_min": age_min,
                "text": "GO - the 5h window already reset; treat usage as fresh. "
                        "Do not spend tokens re-verifying: the stored number stays "
                        "stale-high until the next statusline render."}

    remain_min = int((resets - now) / 60)
    clock = time.strftime("%H:%M", time.localtime(resets))
    sd = _seven_day_note(data.get("seven_day"), resets, now, cfg)
    proj = _projection(sdir, cfg, pct, resets, now)

    level = None
    if pct >= cfg["hard_pct"]:
        level = "STOP"
    elif pct >= cfg["soft_pct"] or (proj is not None and proj >= 100):
        level = "PACE"

    # ⭐ Near the reset the stakes shrink: hitting the cap costs a pause of a few
    # minutes, not lost work. Softening by one level here is deliberate, and it is why
    # a caller must act on the VERDICT and never on the percentage.
    if level and remain_min <= cfg["near_reset_min"]:
        level = "PACE" if level == "STOP" else None

    stale = " [data %d min old - may understate]" % age_min if age_min > cfg["stale_min"] else ""
    # ⭐ frozen_note() used to hang here. It detected the STATUSLINE REPLAYING an unchanged
    # value, which was a real defect and is now impossible: the number is fetched, so an
    # unchanged reading is the server confirming flat usage rather than a stale replay.
    # Worse, history is only appended when a number MOVES, so it could never again find the
    # three identical rows it needed - it could only have fired on pre-change files, as a
    # false alarm. Deleted rather than left inert.

    if level == "STOP":
        text = ("STOP - 5h at %d%% >= hard %d%%. Wrap up: finish the current step, commit or "
                "save state, start nothing new. Schedule a ONE-SHOT resume a few minutes after "
                "%s, then end the turn." % (round(pct), cfg["hard_pct"], clock))
    elif level == "PACE":
        why = ("projected %d%% by reset" % proj) if (proj is not None and proj >= 100
                                                     and pct < cfg["soft_pct"]) else \
              ("5h at %d%%" % round(pct))
        text = ("PACE - %s, %d min left (resets %s). Finish what is in flight; do not start "
                "new heavy work or another dispatch wave." % (why, remain_min, clock))
    else:
        text = ("GO - 5h at %d%%, %d min left (resets %s). Headroom available."
                % (round(pct), remain_min, clock))

    return {"verdict": level or "GO", "exit": {"STOP": 2, "PACE": 1}.get(level, 0),
            "pct": pct, "remain_min": remain_min, "resets_clock": clock,
            "age_min": age_min, "projected_pct": proj, "seven_day": sd,
            "text": text + stale + (" [%s]" % sd if sd else "")}


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
    if pct >= cfg["seven_day_binding_pct"]:
        return "7d %d%% - BINDING, near cap" % round(pct)
    return "7d %d%% - not near cap, ignore" % round(pct)


def _projection(sdir, cfg, pct, resets, now):
    """Where usage lands by reset at the recent burn rate, or None if unknowable.

    ⚠ A LOWER BOUND. Under bursty multi-agent dispatch the real burn runs ahead of it,
    so the hard stop still rules regardless of what this says.

    ⛔ Returns None when the token-usage history is off. ⚠ It is ON by default now - it
    used to be off, and this docstring used to say so. That is a real
    reduction in what PACE can catch, not a technicality - say so rather than letting a
    silently absent projection read as "nothing projected".
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
    if len(rows) < 2:
        return None
    first, last = rows[0], rows[-1]
    span = last["ts"] - first["ts"]
    if span < 300:                                   # under 5 minutes proves nothing
        return None
    rate = (last["pct"] - first["pct"]) / span       # percent per second
    if rate <= 0:
        return None
    return int(min(999, pct + rate * (resets - now)))


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
    return False, "no session active for %s; not fetching" % duration(idle)


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
            note = None
            if age is not None and age > cfg["stale_min"]:
                note = "%.0f min old" % age
            if reason and (note or age is None):
                note = "%s; %s" % (note, reason) if note else reason
            tnote = token_note()          # early warning; see collect()
            if tnote:
                note = "%s; %s" % (note, tnote) if note else tnote
            if idle_note:
                note = "%s; %s" % (note, idle_note) if note else idle_note
            # ⭐ THE VERDICT WORD CARRIES THE SAME COLOUR AS THE BARS: green below
            # colour_warn_pct, orange from there, red from colour_alarm_pct. It is the one
            # word a person reads when they are not reading anything else.
            # ⚠ AND IT ENDS WITH TWO SPACES. `--watch` rewrites the line in place, so the
            # terminal leaves its cursor at the end - directly on top of the last character,
            # which renders as a box over the "O" of GO. The trailing spaces park the cursor
            # somewhere harmless. ERASE_TO_EOL still clears whatever a longer previous line
            # left behind, so this costs nothing but two columns.
            von, voff = _colour(v.get("pct") if isinstance(v.get("pct"), (int, float))
                                else 0, cfg)
            text = "%s  %s  %s%s%s  " % (time.strftime("%H:%M:%S"),
                                         _line(data, note, cfg),
                                         von, v["verdict"], voff)
            if scroll:
                print(text)
            else:
                sys.stdout.write("\r" + text + ERASE_TO_EOL)
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

    # The token expiry is read, not discovered from a 401. A dead token must not cost one
    # of the five calls, and a warning must appear BEFORE it dies rather than after.
    _saved_env = os.environ.pop("ANTHROPIC_TOKEN", None)
    _saved_reader = read_json

    def _fake(now_offset_s):
        exp = (time.time() + now_offset_s) * 1000
        return lambda path, fallback=None: (
            {"claudeAiOauth": {"accessToken": "sk-x", "expiresAt": exp}}
            if path.endswith(".credentials.json") else _saved_reader(path, fallback))
    try:
        globals()["read_json"] = _fake(8 * 3600)
        assert token_note() is None, "a healthy token must not warn"
        globals()["read_json"] = _fake(TOKEN_WARN_SECONDS - 60)
        assert "expires in" in (token_note() or ""), "no warning inside the window"
        globals()["read_json"] = _fake(-60)
        assert "EXPIRED" in (token_note() or ""), "an expired token must say so"
        # ⛔ AND IT MUST NOT SPEND A CALL TO FIND THAT OUT. ⚠ Checked by counting requests,
        # NOT by reading the message: a real 401 reply also says "expired", so an assertion
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
