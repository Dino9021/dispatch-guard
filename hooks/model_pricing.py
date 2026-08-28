#!/usr/bin/env python3
"""The model price table, taken from Anthropic's published pricing page.

    python hooks/model_pricing.py --show      # print the table and where it came from
    python hooks/model_pricing.py --update    # fetch now and rewrite the live copy
    python hooks/model_pricing.py --seed      # rewrite the SHIPPED seed (maintainers only)

⭐ WHY THIS FILE EXISTS. The prices used to be a table typed into dispatch_gate.py. It was
correct on the day it was typed and it drifted the day a model was repriced, with nothing to
say so. Two other sources were considered and rejected:

  - `GET /v1/models` publishes id, capabilities, created_at, display_name, max_input_tokens,
    max_tokens and type. ⛔ It has NO pricing field. Measured 2026-08-28 against the API
    reference; this is not a gap in the search, it is a gap in the API.
  - Scraping the installed Claude Code binary's own catalog. ⛔ Rejected by the owner, and
    correctly: a user who has not updated Claude Code gets prices from an old binary. That is
    not fresher than a typed table, it is stale in a different place.

⇒ The published page is the only authoritative source, and it serves raw markdown at a public
URL with no key and no model turn involved.

⚠ AND THE PAGE ITSELF SAYS IT IS NOT THE LAST WORD - its first line reads "For the most
current pricing information, visit claude.com/pricing". So the URL is recorded in the file and
nobody gets to call the number authoritative beyond that.

⚠ ONE MODEL HAS MANY PRICES. Batch is half. Fast mode is $10/$50. `inference_geo:"us"` is
1.1x. Bedrock and Vertex are billed separately. Prompt caching writes at 1.25x/2x and reads at
0.1x. THIS FILE RECORDS BASE INPUT AND BASE OUTPUT ONLY, and the gate compares base input.

⛔ NOTHING HERE IS EVER CALLED SYNCHRONOUSLY FROM A HOOK. `load()` reads a file. The fetch
runs in a detached child that the gate forks and never waits for - see keep_prices_fresh() in
dispatch_gate.py. A blocking HTTP call inside a PreToolUse hook would stall every tool call in
the session, and a slow network would be indistinguishable from a hung plugin.

Standard library only, like everything else here.
"""

import io
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(HERE)

SOURCE_URL = "https://platform.claude.com/docs/en/about-claude/pricing.md"
FILENAME = "model_pricing.json"
FETCH_TIMEOUT = 10

# ⛔ THE PARSE MUST BE ABLE TO FAIL. A page whose table changed shape returns HTTP 200 and
# parses to nothing, and writing that would erase every price the gate owns. So a table is
# only accepted when it has at least this many models AND every family the gate resolves
# aliases through. ⚠ Being strict is the safe direction here: a refused update keeps the last
# good file, while an accepted empty one refuses every dispatch until somebody notices.
MIN_MODELS = 6
REQUIRED_FAMILIES = ("opus", "sonnet", "haiku")

# ⭐ THE FAMILIES A SESSION CAN ACTUALLY NAME, which is a fact about the harness and not about
# pricing - so it does NOT come from the page. The accepted alias list in Claude Code is
# ["sonnet","opus","haiku","fable","best","sonnet[1m]","opus[1m]","fable[1m]","opusplan"].
# ⛔ `mythos` is priced (it is on the page) but is NOT here: a bare `mythos` is not something a
# session can ask for, so treating it as an alias would invent a dispatch that cannot happen.
ALIAS_FAMILIES = ("fable", "opus", "sonnet", "haiku")

_ROW = re.compile(r"^\|(.+)\|\s*$")
_MTOK = re.compile(r"^\$([\d.]+)\s*/\s*MTok$")


# --------------------------------------------------------------------------- parsing

def model_id(display):
    """`Claude Opus 4.8` -> `claude-opus-4-8`. None when the name is not shaped like a model.

    ⚠ THE 3.x GENERATION REVERSES THE ORDER and that is not a typo in this function: the
    published ID for "Claude Haiku 3.5" is `claude-3-5-haiku`, while "Claude Haiku 4.5" is
    `claude-haiku-4-5`. One special case, because there is exactly one exception.
    """
    m = re.match(r"^Claude\s+([A-Za-z]+)\s+(\d+)(?:\.(\d+))?$", (display or "").strip())
    if not m:
        return None
    family = m.group(1).lower()
    ver = m.group(2) if m.group(3) is None else "%s-%s" % (m.group(2), m.group(3))
    if m.group(2) == "3":
        return "claude-%s-%s" % (ver, family)
    return "claude-%s-%s" % (family, ver)


def _version(display):
    m = re.match(r"^Claude\s+[A-Za-z]+\s+(\d+)(?:\.(\d+))?$", (display or "").strip())
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (-1, -1)


def parse(markdown):
    """(models, families) from the page's raw markdown, or ({}, {}) when it does not match.

    `models` maps model ID -> {"display", "family", "input", "output"}, in US dollars per
    million tokens. `families` maps a family name to its newest model ID.

    ⛔ ONLY THE `## Model pricing` SECTION. The same page carries a batch table (half price)
    and a fast-mode table ($10/$50), and both have the same column shape. A parser that walked
    the whole document would silently take whichever it met last.
    """
    if "## Model pricing" not in markdown:
        return {}, {}
    sec = markdown.split("## Model pricing", 1)[1]
    # The next H2 ends the section. ⚠ Not "the next heading": the table is preceded by H3s in
    # some renderings and cutting at those would take an empty slice.
    nxt = re.search(r"^## ", sec[3:], re.M)
    if nxt:
        sec = sec[:nxt.start() + 3]

    models = {}
    for line in sec.splitlines():
        m = _ROW.match(line.strip())
        if not m:
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if len(cells) < 3:
            continue
        # The name cell carries footnote links - "Claude Opus 4.1 ([retired, ...](url))".
        display = re.split(r"\s*[(\[]", cells[0])[0].strip()
        mid = model_id(display)
        if not mid:
            continue
        pin, pout = _MTOK.match(cells[1]), _MTOK.match(cells[-1])
        if not (pin and pout):
            continue
        models[mid] = {"display": display, "family": display.split()[1].lower(),
                       "input": float(pin.group(1)), "output": float(pout.group(1))}

    families = {}
    for mid, row in models.items():
        cur = families.get(row["family"])
        if cur is None or _version(row["display"]) > _version(models[cur]["display"]):
            families[row["family"]] = mid
    return models, families


def valid(models, families):
    """Is this table safe to write over the last good one? ⛔ See MIN_MODELS."""
    return (len(models) >= MIN_MODELS
            and all(f in families for f in REQUIRED_FAMILIES))


# --------------------------------------------------------------------------- the file

def stamps(now):
    """The three time fields. ⭐ The owner asked for a timestamp AND a human-readable form;
    the staleness maths only ever uses the epoch one."""
    lt = time.localtime(now)
    off = -(time.altzone if lt.tm_isdst else time.timezone)
    return {
        "fetched_at": int(now),
        "fetched_at_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now)) + " UTC",
        "fetched_at_local": "%s %+03d%02d" % (time.strftime("%Y-%m-%d %H:%M:%S", lt),
                                              off // 3600, abs(off) // 60 % 60),
    }


def build(markdown, url=SOURCE_URL, now=None):
    """A complete document, or None when the markdown does not parse into a usable table."""
    models, families = parse(markdown)
    if not valid(models, families):
        return None
    doc = {
        "_": "Base input and output price in US dollars per million tokens, taken from the "
             "page named in `source`. Batch, fast mode, prompt caching, data residency and "
             "the partner clouds all price differently and are NOT here. Generated by "
             "hooks/model_pricing.py - do not hand-edit.",
        "source": url,
    }
    doc.update(stamps(time.time() if now is None else now))
    doc["models"] = models
    doc["families"] = families
    return doc


def write(doc, path):
    """⭐ ATOMIC. The gate reads this file on hook events while a forked child writes it, so a
    plain open-and-write would let a hook read half a file and fall back to the seed for one
    tool call."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp%d" % os.getpid()
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1, sort_keys=False)
        f.write("\n")
    os.replace(tmp, path)


def read(path):
    try:
        with io.open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception:
        return None
    if isinstance(doc, dict) and doc.get("models") and doc.get("families"):
        return doc
    return None


def load(sdir=None, plugin_dir=PLUGIN_DIR):
    """(doc, where) - the live copy when it is usable, otherwise the shipped seed.

    ⛔ TWO COPIES ON PURPOSE. `claude plugin update` replaces everything under the plugin
    directory, so a fetched table written there is destroyed on every update - and on some
    installs that directory is not writable at all. ⇒ The seed is committed and read-only in
    practice; the live copy lives in the state directory beside limits.json.

    ⚠ NEWER IS DECIDED BY `fetched_at`, NOT BY MTIME. A plugin update rewrites the seed's
    mtime without changing a single price, which would make a stale seed look newest.

    ⇒ (None, reason) when neither is readable. The caller must fail OPEN on that; see
    dispatch_gate.model_refusal().
    """
    seed = read(os.path.join(plugin_dir, FILENAME))
    live = read(os.path.join(sdir, FILENAME)) if sdir else None
    if live and seed and seed.get("fetched_at", 0) > live.get("fetched_at", 0):
        return seed, "seed (newer than the live copy)"
    if live:
        return live, "live copy"
    if seed:
        return seed, "shipped seed"
    return None, "no price table found"


def due(doc, hours, now=None):
    """Is the table older than the configured interval? ⚠ A missing or unparsable timestamp
    counts as due - the alternative is a file that never refreshes because it never said when
    it was written."""
    if not hours or hours <= 0:
        return False                     # the owner switched the refresh off
    try:
        age = (time.time() if now is None else now) - float((doc or {}).get("fetched_at", 0))
    except (TypeError, ValueError):
        return True
    return age >= float(hours) * 3600


def age_line(doc):
    """`fetched 2026-08-28 11:30:00 UTC (3.2 h ago)` - for logs and for the session note."""
    if not doc:
        return "no price table"
    try:
        h = (time.time() - float(doc.get("fetched_at", 0))) / 3600.0
    except (TypeError, ValueError):
        return "fetched at an unreadable time"
    return "fetched %s (%.1f h ago)" % (doc.get("fetched_at_utc", "?"), h)


# --------------------------------------------------------------------------- fetching

def fetch(url=SOURCE_URL, timeout=FETCH_TIMEOUT):
    """The page's raw markdown, or None. ⚠ Never raises: this runs in a detached child whose
    only failure mode should be "the file was not updated"."""
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "dispatch-guard/model_pricing (+https://github.com/Dino9021/dispatch-guard)",
            "Accept": "text/markdown, text/plain, */*"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


STATUS = "model_pricing.status"


def _record(sdir, reason, ok):
    """⭐ WHY THE CHILD WRITES A FILE INSTEAD OF LOGGING. The refresh runs detached with every
    handle on DEVNULL, and the gate's log lives in the REPOSITORY - which a child launched
    with only a state directory has no way to find. Without this file a fetch that fails for
    a month is completely invisible: the table just quietly stops moving. The gate reads it
    at session start and can then tell "the refresh has not run yet" from "the refresh is
    failing", which are different problems with different answers."""
    try:
        write({"ok": bool(ok), "reason": reason, "at": int(time.time()),
               "at_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()) + " UTC"},
              os.path.join(sdir, STATUS))
    except Exception:
        pass


def status(sdir):
    """The last refresh attempt, or None. ⚠ read() insists on a price table, so not that."""
    try:
        with io.open(os.path.join(sdir, STATUS), encoding="utf-8") as f:
            got = json.load(f)
        return got if isinstance(got, dict) else None
    except Exception:
        return None


def update(sdir, url=SOURCE_URL, timeout=FETCH_TIMEOUT):
    """Fetch and rewrite the live copy. Returns a one-line reason, always, and records it.

    ⛔ A FAILED PARSE KEEPS THE OLD FILE. The page returning 200 with a reshaped table is the
    likeliest future failure, and it is the one that would otherwise erase every price.
    """
    reason, ok = _update(sdir, url, timeout)
    _record(sdir, reason, ok)
    return reason


def _update(sdir, url, timeout):
    md = fetch(url, timeout)
    if md is None:
        return "MODEL-PRICE-FETCH-FAILED %s (kept the previous table)" % url, False
    doc = build(md, url)
    if doc is None:
        return ("MODEL-PRICE-PARSE-FAILED %s - the table did not match; kept the previous "
                "table. Run `python hooks/model_pricing.py --show` and re-check the parser."
                % url), False
    path = os.path.join(sdir, FILENAME)
    old = read(path)
    try:
        write(doc, path)
    except OSError as exc:
        return "MODEL-PRICE-WRITE-FAILED %s (%r)" % (path, exc), False
    changed = [k for k in sorted(set(doc["models"]) | set((old or {}).get("models", {})))
               if (doc["models"].get(k) or {}).get("input")
               != ((old or {}).get("models", {}).get(k) or {}).get("input")]
    return ("MODEL-PRICE-UPDATED %d models, %s%s"
            % (len(doc["models"]), doc["fetched_at_utc"],
               (" - CHANGED: %s" % ", ".join(changed)) if changed and old else "")), True


# --------------------------------------------------------------------------- cli

def _selftest():
    fixture = os.path.join(HERE, "..", "Tools", "Debug", "fixtures", "pricing.md")
    md = io.open(os.path.abspath(fixture), encoding="utf-8").read()
    models, families = parse(md)
    assert valid(models, families), "the committed fixture must parse"
    assert models["claude-opus-5"]["input"] == 5, models.get("claude-opus-5")
    assert models["claude-sonnet-5"]["input"] == 2, models.get("claude-sonnet-5")
    assert models["claude-fable-5"]["input"] == 10
    # ⚠ The one row the old hand-typed table got wrong: it said 1, the page says 0.80.
    assert models["claude-3-5-haiku"]["input"] == 0.8, models.get("claude-3-5-haiku")
    assert models["claude-opus-4-1"]["input"] == 15
    assert families["opus"] == "claude-opus-5", families
    assert families["sonnet"] == "claude-sonnet-5", families
    assert families["haiku"] == "claude-haiku-4-5", families

    assert model_id("Claude Haiku 3.5") == "claude-3-5-haiku"
    assert model_id("Claude Opus 4.8") == "claude-opus-4-8"
    assert model_id("Claude Opus 4") == "claude-opus-4"
    assert model_id("Claude Something") is None

    # ⛔ MUTATION CHECKS on the two branches that decide whether a bad table is written.
    assert not valid({}, {}), "an empty table must be refused"
    assert not valid(models, {k: v for k, v in families.items() if k != "opus"}), \
        "a table missing a required family must be refused"
    assert build("no table here at all") is None, "unparsable markdown must build to None"
    assert build(md.replace("## Model pricing", "## Something else")) is None, \
        "the section heading is what anchors the parse"

    s = stamps(0)
    assert s["fetched_at_utc"] == "1970-01-01 00:00:00 UTC", s
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4}$", s["fetched_at_local"])

    now = 1000000.0
    assert due({"fetched_at": now - 25 * 3600}, 24, now), "25 h must be due at 24 h"
    assert not due({"fetched_at": now - 23 * 3600}, 24, now), "23 h must not be due"
    assert not due({"fetched_at": 0}, 0, now), "0 hours means the refresh is off"
    assert due({}, 24, now), "a table with no timestamp must be due"
    print("model_pricing selftest OK (%d models)" % len(models))
    return 0


def main(argv):
    sys.path.insert(0, HERE)
    if "--selftest" in argv:
        return _selftest()
    import usage
    sdir = usage.state_dir(argv)
    url = SOURCE_URL
    if "--url" in argv:
        url = argv[argv.index("--url") + 1]

    if "--seed" in argv:
        md = fetch(url)
        if md is None:
            print("fetch failed: %s" % url)
            return 1
        doc = build(md, url)
        if doc is None:
            print("parse failed: %s" % url)
            return 1
        write(doc, os.path.join(PLUGIN_DIR, FILENAME))
        print("wrote the seed: %s (%d models, %s)"
              % (os.path.join(PLUGIN_DIR, FILENAME), len(doc["models"]),
                 doc["fetched_at_utc"]))
        return 0

    if "--update" in argv:
        print(update(sdir, url))

    doc, where = load(sdir)
    if not doc:
        print("no price table: %s" % where)
        return 1
    print("source : %s" % doc.get("source"))
    print("from   : %s" % where)
    print("time   : %s / %s (epoch %s)"
          % (doc.get("fetched_at_utc"), doc.get("fetched_at_local"), doc.get("fetched_at")))
    print()
    print("%-22s %-8s %8s %8s" % ("model", "family", "in $/M", "out $/M"))
    for mid in sorted(doc["models"], key=lambda k: (doc["models"][k]["family"], k)):
        r = doc["models"][mid]
        print("%-22s %-8s %8g %8g" % (mid, r["family"], r["input"], r["output"]))
    print()
    print("newest per family: %s"
          % ", ".join("%s=%s" % kv for kv in sorted(doc["families"].items())))
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main(sys.argv[1:]))
