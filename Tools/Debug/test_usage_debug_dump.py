#!/usr/bin/env python3
"""debug.API_response_usage keeps every usage API response. This pins that it does.

    python Tools/Debug/test_usage_debug_dump.py

⛔ WHY THIS SWITCH NEEDS A CHECK MORE THAN MOST. It is a fail-CLOSED diagnostic: with it
off, nothing happens - so "no file appeared" is what a working OFF and a completely broken
writer both look like. A test that only asserts the off case passes for the wrong reason,
and a test that only asserts "a line was written" passes against a writer that stored
`{"five_hour": ...}` and threw away the entire reason the feature exists. ⇒ Every case here
compares against the WHOLE input dict, and case 3 is the one that pins the call site's
POSITION rather than its existence.

⭐ NO NETWORK CALL, and not merely by accident: `urllib.request.urlopen` is replaced for the
length of each case and the replacement is COUNTED, so a case that somehow reached the real
endpoint fails on the count instead of quietly spending one of the roughly five calls per
access token that this endpoint allows.

⭐ THE TWO IDENTITY FILES ARE FAKED TOO - ~/.claude/.credentials.json and ~/.claude.json are
never opened. `read_json` is replaced, which is how usage.py's own --selftest does it. That
is what lets the check assert an exact organisation uuid on any machine, and it is also what
keeps a developer's real account id out of the scratch files.

⚠ Everything written goes under `Tools/Debug/scratch/`, kept after the run. See _debugpaths.
"""

import datetime
import glob
import importlib.util
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import fresh_scratch, repo_path, scratch_dir   # noqa: E402

# Fixed values, so the assertions can be exact. They are the SHAPE of the real ones.
ORG = "cb8c6fba-c115-4ce1-b615-3f1b0bcb08d3"
SEAT = "0e7d499f-4aff-49bd-8019-51f789f5e0a5"
OTHER_ORG = "11111111-2222-3333-4444-555555555555"
# ⛔ Planted in the fake profile ON PURPOSE. oauthAccount really does carry an email address
# beside the uuid, and the record must never contain one.
EMAIL = "must-never-be-written@example.invalid"
TOKEN = "sk-ant-oat-FAKE-NOT-A-REAL-TOKEN"

# ⭐ A response body carrying fields NOBODY VALUES, because that is the whole point: the
# field a later question needs is the one the current parser ignores. `nimbus_quill` and
# `seven_day_opus` are here to be compared byte for byte after the round trip.
RESPONSE = {
    "five_hour": {"utilization": 22.0, "resets_at": "2026-08-27T14:39:59.203505+00:00"},
    "seven_day": {"utilization": 8.0, "resets_at": "2026-09-01T04:39:59+00:00"},
    "seven_day_opus": {"utilization": 0.0, "resets_at": None},
    "nimbus_quill": {"tangelo": [1, 2, {"deep": True, "empty": None}], "unused": ""},
    "limits": [{"kind": "five_hour", "percent": 22},
               {"kind": "seven_day", "percent": 8}],
}

# ⛔ THE SHAPE THE PARSER REFUSES, and therefore the one worth capturing most. _api_window()
# returns None for this, so fetch() takes the `if not five: return` path - which is exactly
# why the dump has to happen BEFORE that line. Measured 2026-08-27: a real response arrived
# with five_hour.resets_at null, an unanticipated shape.
UNUSABLE = {
    "five_hour": {"resets_at": None},
    "seven_day": {"utilization": 8.0},
    "nimbus_quill": {"tangelo": "kept anyway"},
}


def load_usage():
    """usage.py as a module, from the repository under test."""
    sys.path.insert(0, repo_path("hooks"))
    spec = importlib.util.spec_from_file_location("dg_usage", repo_path("hooks", "usage.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Resp(object):
    """The two things urlopen()'s result is used for in fetch(): a context and a read()."""

    def __init__(self, body):
        self._body = body.encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def run_fetch(mod, sdir, cfg, body, org=ORG, seat=SEAT, seat_org=ORG, env_token=None):
    """One fetch() against a canned body. Returns (result, number of urlopen calls).

    ⛔ Nothing here touches the network or the real home directory: urlopen is replaced and
    so is read_json, and both are restored in a finally. `seat_org` is what the fake profile
    file claims - pass a different value to exercise the stale-profile cross-check.
    """
    home = os.path.expanduser("~")
    cred = os.path.abspath(os.path.join(home, ".claude", ".credentials.json"))
    prof = os.path.abspath(os.path.join(home, ".claude.json"))
    real_read = mod.read_json

    def fake_read(path, fallback=None):
        p = os.path.abspath(path)
        if p == cred:
            blob = {"claudeAiOauth": {"accessToken": TOKEN,
                                      "expiresAt": (time.time() + 3600) * 1000}}
            if org is not None:
                blob["organizationUuid"] = org
            return blob
        if p == prof:
            acct = {"emailAddress": EMAIL, "organizationName": "Altek Corp"}
            if seat is not None:
                acct["accountUuid"] = seat
            if seat_org is not None:
                acct["organizationUuid"] = seat_org
            return {"oauthAccount": acct}
        return real_read(path, fallback)

    calls = []

    def fake_open(*a, **k):
        calls.append(1)
        return _Resp(json.dumps(body))

    saved_open, saved_read = urllib.request.urlopen, mod.read_json
    # ⛔ THE ENVIRONMENT IS PINNED, not assumed. $ANTHROPIC_TOKEN makes _account_ids()
    # refuse to attribute the row at all - correctly, since on that path the credentials
    # file is not where the token came from - so a developer machine with it set would fail
    # the position-0 assertion for a reason that is not a defect. $CLAUDE_DISPATCH_DIR is
    # pointed AT THE SCRATCH DIRECTORY rather than merely cleared, so that even a code path
    # that fell back to state_dir() could only write inside this case's own folder.
    saved_env = {k: os.environ.get(k) for k in ("ANTHROPIC_TOKEN", "CLAUDE_DISPATCH_DIR")}
    try:
        if env_token is None:
            os.environ.pop("ANTHROPIC_TOKEN", None)
        else:
            os.environ["ANTHROPIC_TOKEN"] = env_token
        os.environ["CLAUDE_DISPATCH_DIR"] = sdir
        urllib.request.urlopen = fake_open
        mod.read_json = fake_read
        got = mod.fetch(cfg, sdir)
    finally:
        urllib.request.urlopen = saved_open
        mod.read_json = saved_read
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return got, len(calls)


def write_config(sdir, blob):
    with open(os.path.join(sdir, "config.json"), "w", encoding="utf-8") as f:
        json.dump(blob, f)


def dumped(sdir):
    """Every usage-response-*.jsonl line under sdir/logs, parsed. [] when there is none."""
    rows = []
    for path in sorted(glob.glob(os.path.join(sdir, "logs", "usage-response-*.jsonl"))):
        with open(path, encoding="utf-8") as f:
            rows += [json.loads(line) for line in f if line.strip()]
    return rows


def assert_no_dump_yet(sdir):
    """⛔ A FILE THAT WAS ALREADY THERE PROVES NOTHING ABOUT THE WRITER.

    Every case below asserts "a dump file exists" AFTER a fetch. That assertion also passes
    against a completely dead writer whenever a previous run left a file in the same
    directory - and it can, for two reasons that combine: fresh_scratch() deliberately does
    NOT clear between the processes of one suite run (DG_SCRATCH_PREPARED), and
    scratch_dir()'s case numbering restarts in each process, so run N+1 lands in run N's
    directories. ⚠ Found by a refuting pass, not imagined: with that variable in the ambient
    environment, a leftover file rescued a writer whose call had been deleted.

    ⇒ Calling this first turns "a file EXISTS" into "a file APPEARED", which is the claim
    the case is actually making.
    """
    stale = glob.glob(os.path.join(sdir, "logs", "usage-response-*.jsonl"))
    assert not stale, ("a dump file was present BEFORE the fetch, so this case could pass "
                       "with a dead writer: %r" % stale)


def raw(sdir):
    """The dump files' text, concatenated - for asserting what is NOT in them."""
    out = ""
    for path in sorted(glob.glob(os.path.join(sdir, "logs", "usage-response-*.jsonl"))):
        with open(path, encoding="utf-8") as f:
            out += f.read()
    return out


def case_off(mod):
    """Switch off: no file, and NO DIRECTORY EITHER. Necessary, and worthless on its own."""
    with scratch_dir("switch-off") as sdir:
        write_config(sdir, {"keep_history": False})
        cfg = mod.config(sdir)
        assert cfg["debug"] == {}, cfg["debug"]
        assert_no_dump_yet(sdir)
        got, calls = run_fetch(mod, sdir, cfg, RESPONSE)
        assert calls == 1, "urlopen was not the fake one: %r" % calls
        assert isinstance(got, dict), got
        # "no directory created, no file touched" - the directory is the stronger assertion.
        assert not os.path.exists(os.path.join(sdir, "logs")), (
            "the switch is OFF and %s/logs was created anyway" % sdir)
        print("  off              no logs/ directory, fetch still returned a record")


def case_on(mod):
    """Switch on: one COMPLETE record, in its own file, with the identity resolved."""
    with scratch_dir("switch-on") as sdir:
        write_config(sdir, {"debug": {"API_response_usage": True}})
        cfg = mod.config(sdir)
        assert cfg["debug"] == {"API_response_usage": True}, cfg["debug"]
        assert_no_dump_yet(sdir)
        got, calls = run_fetch(mod, sdir, cfg, RESPONSE)
        assert calls == 1, "urlopen was not the fake one: %r" % calls
        assert isinstance(got, dict), got

        files = sorted(glob.glob(os.path.join(sdir, "logs", "*.jsonl")))
        assert len(files) == 1, "expected one file, got %r" % files
        name = os.path.basename(files[0])
        assert name.startswith("usage-response-"), name
        # ⛔ SEPARATE FROM THE HISTORY FILE. A response body appended into
        # limits-history-*.jsonl would break _projection()'s reader.
        assert not glob.glob(os.path.join(sdir, "logs", "limits-history-*.jsonl")), (
            "the dump landed in the history file")

        rows = dumped(sdir)
        assert len(rows) == 1, "expected one line, got %d" % len(rows)
        row = rows[0]
        assert isinstance(row, list) and len(row) == 4, "not a 4-element array: %r" % (row,)
        assert row[0] == ORG, "position 0 is not the organisation uuid: %r" % (row[0],)
        assert row[1] == SEAT, "position 1 is not the account uuid: %r" % (row[1],)

        # Position 2: an ISO-8601 instant, UTC, and actually now rather than a constant.
        when = datetime.datetime.fromisoformat(row[2])
        assert when.tzinfo is not None, "position 2 has no timezone: %r" % (row[2],)
        assert when.utcoffset() == datetime.timedelta(0), "position 2 is not UTC: %r" % (row[2],)
        drift = abs(time.time() - when.timestamp())
        assert drift < 300, "position 2 is %.0fs from now: %r" % (drift, row[2])

        # ⛔ THE ASSERTION THE WHOLE FEATURE RESTS ON: the body is COMPLETE. A writer that
        # kept only the fields the parser understands would pass "a line was written" and
        # destroy the reason the switch exists.
        assert row[3] == RESPONSE, "position 3 is not the whole response: %r" % (row[3],)

        text = raw(sdir)
        assert EMAIL not in text, "an email address was written into the dump"
        assert TOKEN not in text, "the access token was written into the dump"
        print("  on               1 complete record in %s, org+seat resolved" % name)


def case_unusable_five_hour(mod):
    """⛔ THE CALL SITE'S POSITION, not its existence.

    `if not five: return` fires on this body, so a dump placed after _api_window() would
    lose exactly the responses a diagnostic exists to capture. This case fails if the call
    ever moves below that line, and it is the only case that can tell.
    """
    with scratch_dir("unusable-five-hour") as sdir:
        write_config(sdir, {"debug": {"API_response_usage": True}})
        cfg = mod.config(sdir)
        assert_no_dump_yet(sdir)
        got, calls = run_fetch(mod, sdir, cfg, UNUSABLE)
        assert calls == 1, calls
        # The parser really did refuse it - otherwise this case proves nothing.
        assert isinstance(got, str) and "five_hour" in got, (
            "expected the no-usable-five_hour reason, got %r" % (got,))
        rows = dumped(sdir)
        assert len(rows) == 1, (
            "a response the parser REFUSED was not dumped - the call site is below "
            "_api_window(), which loses the most interesting responses (got %d lines)"
            % len(rows))
        assert rows[0][3] == UNUSABLE, rows[0][3]
        print("  unusable 5h      refused by the parser, kept by the dump")


def case_list_alias(mod):
    """"debug": ["API_response_usage"] must mean the same as the object form."""
    with scratch_dir("list-alias") as sdir:
        write_config(sdir, {"debug": ["API_response_usage"]})
        cfg = mod.config(sdir)
        assert cfg["debug"] == {"API_response_usage": True}, cfg["debug"]
        assert_no_dump_yet(sdir)
        got, calls = run_fetch(mod, sdir, cfg, RESPONSE)
        assert calls == 1, calls
        rows = dumped(sdir)
        assert len(rows) == 1 and rows[0][3] == RESPONSE, rows
        print("  list alias       [\"API_response_usage\"] switched it on")


def case_stale_profile(mod):
    """⛔ A WRONG seat id is worse than a missing one, because it looks valid.

    The two identity files are written at different moments and can disagree after an
    account switch. On a mismatch the seat is dropped and the ROW IS STILL KEPT - a null
    there means "not attributable to a seat", which a statistics reader must exclude.
    """
    with scratch_dir("stale-profile") as sdir:
        write_config(sdir, {"debug": {"API_response_usage": True}})
        cfg = mod.config(sdir)
        assert_no_dump_yet(sdir)
        got, calls = run_fetch(mod, sdir, cfg, RESPONSE, seat_org=OTHER_ORG)
        assert calls == 1, calls
        rows = dumped(sdir)
        assert len(rows) == 1, "the record was DROPPED instead of kept: %r" % (rows,)
        assert rows[0][0] == ORG, rows[0][0]
        assert rows[0][1] is None, (
            "a stale profile's account uuid was attached anyway: %r" % (rows[0][1],))
        assert rows[0][3] == RESPONSE, rows[0][3]
        print("  stale profile    seat dropped to null, record kept")


def case_write_failure_does_not_break_the_fetch(mod):
    """⛔ THE FAIL-OPEN GUARD. A diagnostic that can break the brake is worse than none.

    The dump lives inside `try/except Exception` so a write failure ends as "no file",
    never as a crash. ⚠ Nothing pinned that: a refuting pass NARROWED the except clause and
    the whole suite stayed green, which means the suite was not protecting the one property
    that keeps a debug switch from costing the brake its reading.

    ⭐ The failure is REAL, not injected: `history_dir` points at an existing FILE, so
    creating the directory raises. That exercises the same path a full disk or a permission
    error would, without patching anything.
    """
    with scratch_dir("write-failure") as sdir:
        blocker = os.path.join(sdir, "not-a-directory")
        with open(blocker, "w", encoding="utf-8") as f:
            f.write("a FILE where the log directory must go\n")
        write_config(sdir, {"debug": {"API_response_usage": True},
                            "history_dir": blocker})
        cfg = mod.config(sdir)
        # ⛔ CAUGHT AND RE-RAISED AS AN ASSERTION, so the failure explains itself. Measured:
        # narrowing the dump's `except Exception` to `except ValueError` lets a real
        # FileExistsError propagate out of fetch(). The test did fail - but as a raw
        # traceback from inside usage.py, which reads as "the check is broken" rather than
        # "the brake just lost its reading". A legible failure is the whole difference.
        try:
            got, calls = run_fetch(mod, sdir, cfg, RESPONSE)
        except Exception as exc:            # noqa: BLE001 - catching everything IS the point
            raise AssertionError(
                "a failed DEBUG WRITE propagated out of fetch() and cost the fetch its "
                "result: %s: %s" % (type(exc).__name__, exc))
        assert calls == 1, calls
        # ⛔ THE WHOLE POINT: the fetch still produced its record.
        assert isinstance(got, dict), (
            "a failed DEBUG WRITE cost the fetch its result: %r" % (got,))
        assert got.get("five_hour", {}).get("used_percentage") == 22.0, got
        assert not dumped(sdir), "something was written to a path that cannot exist"
        print("  write failure    dump lost, fetch kept its number")


def case_env_token_refuses_to_attribute(mod):
    """$ANTHROPIC_TOKEN means the credentials file is NOT where the token came from.

    ⛔ So neither id may be attached. ⚠ A WRONG id is worse than a missing one, because it
    looks valid - and this path is reachable in normal use. A refuting pass deleted this
    guard and the suite stayed green, so it is pinned here.

    ⭐ The record is still KEPT, with two nulls. Losing the response would be the wrong
    trade: an unattributed sample is still a sample, as long as a reader can see it is
    unattributed.
    """
    with scratch_dir("env-token") as sdir:
        write_config(sdir, {"debug": {"API_response_usage": True}})
        cfg = mod.config(sdir)
        # ⛔ BOTH OF THESE WERE MISSING, and a refuting pass proved the case then passed with
        # the writer replaced by a no-op: it was the ONLY dump-asserting case with no
        # pre-check, and unlike case_on it had no age bound either, so a planted row dated
        # 2026-01-01 satisfied it. The hole this case was added alongside, reintroduced by
        # the same hand that closed it.
        assert_no_dump_yet(sdir)
        got, calls = run_fetch(mod, sdir, cfg, RESPONSE, env_token="sk-ant-FAKE-FROM-THE-ENV")
        assert calls == 1, calls
        rows = dumped(sdir)
        assert len(rows) == 1, "the record was DROPPED instead of kept: %r" % (rows,)
        drift = abs((datetime.datetime.now(datetime.timezone.utc)
                     - datetime.datetime.fromisoformat(rows[0][2])).total_seconds())
        assert drift < 300, "position 2 is %.0fs from now, so this row is not ours: %r" % (
            drift, rows[0][2])
        assert rows[0][0] is None, (
            "an organisation uuid was attached to a token the file did not supply: %r"
            % (rows[0][0],))
        assert rows[0][1] is None, rows[0][1]
        assert rows[0][3] == RESPONSE, rows[0][3]
        print("  env token        both ids null, record kept")


def case_config_coercion(mod):
    """⛔ THE SWITCH MUST NOT COME ON FOR SOMEBODY WHO WROTE THE WORD FOR OFF.

    ⚠ WHY THIS CASE EXISTS AND WHY IT IS NOT DECORATION. A refuting pass reverted `_truthy`
    to plain `bool()` - restoring the original trap verbatim - and the whole suite stayed at
    7/7, exit 0. Deleting the stderr warning did the same. So the trap was closed in the code
    and left wide open in the checks: the next edit that "simplifies" `_truthy` would ship
    green and the trap would come back. Nothing else here reads config values as strings.

    ⛔ `bool("false")` is True in Python. That is the whole hazard.
    """
    import io as _io                      # local: only this case captures stderr
    import contextlib as _ctx

    with scratch_dir("config-coercion") as sdir:
        def parsed(blob):
            write_config(sdir, blob)
            err = _io.StringIO()
            with _ctx.redirect_stderr(err):
                cfg = mod.config(sdir)
            return bool(cfg["debug"].get("API_response_usage")), err.getvalue()

        # (config blob, expected ON, expect a warning)
        table = [
            ({"debug": {"API_response_usage": False}}, False, False),
            ({"debug": {"API_response_usage": True}}, True, False),
            ({"debug": {"API_response_usage": "false"}}, False, False),
            ({"debug": {"API_response_usage": "0"}}, False, False),
            ({"debug": {"API_response_usage": "no"}}, False, False),
            ({"debug": {"API_response_usage": "off"}}, False, False),
            ({"debug": {"API_response_usage": ""}}, False, False),
            ({"debug": {"API_response_usage": "true"}}, True, False),
            ({"debug": {"API_response_usage": "1"}}, True, False),
            ({"debug": {"API_response_usage": "yes"}}, True, False),
            # ⛔ An unrecognised value leaves it OFF. A typo must not enable a writer.
            ({"debug": {"API_response_usage": "maybe"}}, False, False),
            ({"debug": ["API_response_usage"]}, True, False),
            # ⛔ Not an object and not a list: everything off, AND a warning says why. This
            # used to be a silent off, which is how a person waits all day for a file.
            ({"debug": True}, False, True),
            ({"debug": "yes"}, False, True),
            ({"debug": 3}, False, True),
            # No debug key at all: off, and NOT a warning - there is nothing to complain of.
            ({}, False, False),
        ]
        for blob, want_on, want_warn in table:
            on, warn = parsed(blob)
            assert on == want_on, (
                "debug=%r gave ON=%s, expected %s" % (blob.get("debug"), on, want_on))
            assert bool(warn.strip()) == want_warn, (
                "debug=%r gave warning=%r, expected warning=%s"
                % (blob.get("debug"), warn.strip()[:120], want_warn))
        print("  coercion         %d config shapes, strings read for meaning, "
              "bad shapes warn" % len(table))


def main():
    fresh_scratch()
    mod = load_usage()
    case_off(mod)
    case_on(mod)
    case_unusable_five_hour(mod)
    case_list_alias(mod)
    case_stale_profile(mod)
    case_write_failure_does_not_break_the_fetch(mod)
    case_env_token_refuses_to_attribute(mod)
    case_config_coercion(mod)
    print("ok - off writes nothing, on writes the WHOLE response, a refused response is "
          "still kept, and a failed write never costs the fetch its number")


if __name__ == "__main__":
    main()
