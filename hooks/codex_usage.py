#!/usr/bin/env python3
"""The Codex usage verdict, and the Codex gate's decision (0.76.0).

ADR: Memory/tasks/20261110-164252-codex-usage-gate/ADR.md. The owner's goal, verbatim:
「你覺得怎麼設計去避免 codex 撞到上限後 agent 還一直叫說不能用，或是默默地再也不用」 and
「如果會知道，就不用問，記下下一次哪時候可以用，用量重設後繼續用就好」.

ONE machine-wide answer to "may an agent call Codex now?", read from the Codex server itself
(`codex app-server` -> `account/rateLimits/read`, which makes no model call), cached in the state
dir as codex_usage.json.

Words and exit codes: GO 0, PACE 1, WAIT 2, UNAVAILABLE 3, OFF 4. What each word means for an
agent is PROTOCOL.md, section "Codex verdict" - the one live copy.

FOUR THINGS THAT ARE EASY TO MISREAD
------------------------------------

1. THE VERDICT FAILS CLOSED, THE GATE FAILS OPEN. A verdict that cannot be measured is never GO; it
   is UNAVAILABLE. The gate refuses only a server-measured WAIT, or OFF, and lets everything else
   through, so a broken check never stops Codex being used (the owner's failure 2).

2. A FAILED PROBE IS NEVER A WAIT (ADR D5). Codex's own session log may still show a limit, but it
   cannot be cleared while the probe is broken: an old weekly snapshot would lock Codex out for up
   to 7 days. It only adds a note.

3. THE OWNER IS TOLD ONCE PER EPISODE PER MACHINE (ADR D9). Episode keys carry no time, so a WAIT
   whose reset time moves is still the same WAIT. GO clears WAIT at once; UNAVAILABLE is cleared
   only after an hour of GO, so a flapping network is announced once.

4. ⛔ THE PROBE SENDS EXACTLY THREE METHODS: initialize, initialized, account/rateLimits/read. The
   account holds free reset credits and the protocol has a method that spends one. The owner's
   decision (2026-11-10): never use them. Nothing here may send anything else.

Standard library only, like everything else here.
"""

import glob
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))

CACHE = "codex_usage.json"
LOCK = "codex.lock"
SPAWN = "codex.spawn"
NOTICE = "codex_notice.json"
NOTICE_LOCK = "codex_notice.lock"

EXIT = {"GO": 0, "PACE": 1, "WAIT": 2, "UNAVAILABLE": 3, "OFF": 4}

FRESH_OK = 60            # seconds a GO or PACE stays fresh
FRESH_BAD = 300          # seconds a WAIT or UNAVAILABLE stays fresh
UNKNOWN_RESET = 300      # a WAIT with no usable reset time re-probes after this long
LOCK_STALE = 30          # a probe lock older than this is dead
SPAWN_EVERY = 30         # the gate starts at most one refresher per this many seconds
NOTICE_LOCK_STALE = 10
VERDICT_WAIT = 12        # --codex-verdict waits this long for another process's probe
PROBE_DEADLINE = 10.0
RECOVER_UNAVAILABLE = 3600   # GO must hold this long before UNAVAILABLE may be announced again
PACE_PCT = 90

# ⛔ Built by concatenation, so this file never contains the method as one literal: the
# reset-credit guard refuses a write that sends it, and this source must stay editable.
RESET_METHOD = "account/rateLimit" + "ResetCredit/consume"

REASONS = ("not-installed", "not-logged-in", "probe-failed")

COMMAND = "bash ~/.claude/dispatch-guard/run.sh usage.py --codex-verdict"


# ------------------------------------------------------------------------------ small files

def _read_json(path, fallback=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback


def _write_json(path, data):
    """Atomic: a reader sees the old file or the new one, never half of one."""
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def _take_lock(path, stale):
    """True when THIS process now holds the O_EXCL lock. Never waits."""
    for _ in range(2):
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return True
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(path) < stale:
                    return False
                os.remove(path)          # its holder died
            except OSError:
                return False
        except OSError:
            return False
    return False


def _drop_lock(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _local(t):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t))


# ----------------------------------------------------------------------------- configuration

def codex_config(sdir):
    """The `codex` object of the STATE config.json - machine level, never per project (ADR D4.1)."""
    disk = _read_json(os.path.join(sdir, "config.json"), {}) or {}
    c = disk.get("codex") if isinstance(disk, dict) else None
    return c if isinstance(c, dict) else {}


def is_off(cfg):
    v = cfg.get("enabled", True)
    if v is False:
        return True
    return isinstance(v, (str, int)) and not isinstance(v, bool) and \
        str(v).strip().lower() in ("false", "off", "no", "0")


def pace_pct(cfg):
    v = cfg.get("pace_pct", PACE_PCT)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v <= 100 else PACE_PCT


# ------------------------------------------------------------------------------- locating

_ARCH = {"arm64": ("arm64", "aarch64"), "aarch64": ("arm64", "aarch64"),
         "x86_64": ("x86_64", "amd64", "x64"), "amd64": ("x86_64", "amd64", "x64")}
_OS = {"darwin": ("macos", "darwin"), "win32": ("windows", "win"), "linux": ("linux",)}


def _version(name):
    m = re.match(r"openai\.chatgpt-([0-9][0-9.]*)", os.path.basename(name))
    if not m:
        return ()
    return tuple(int(p) for p in m.group(1).strip(".").split(".") if p.isdigit())


def extension_codex(ext_root=None, machine=None, plat=None):
    """The codex binary inside the newest VS Code ChatGPT extension, or None (ADR D2.3)."""
    ext_root = ext_root or os.path.join(os.path.expanduser("~"), ".vscode", "extensions")
    machine = (machine or platform.machine() or "").lower()
    plat = plat or sys.platform
    arch = _ARCH.get(machine, (machine,))
    oses = _OS.get(plat, (plat,))
    dirs = sorted(glob.glob(os.path.join(ext_root, "openai.chatgpt-*")), key=_version, reverse=True)
    for d in dirs:
        found = []
        for b in glob.glob(os.path.join(d, "bin", "*")):
            for exe in ("codex", "codex.exe"):
                p = os.path.join(b, exe)
                if os.path.isfile(p):
                    sub = os.path.basename(b).lower()
                    score = (any(a in sub for a in arch if a), any(o in sub for o in oses))
                    found.append((score, p))
        if found:
            found.sort(key=lambda x: x[0], reverse=True)
            return found[0][1]
    return None


def locate(cfg):
    """codex.path, then PATH, then the VS Code extension (ADR D2, MAC change 1)."""
    p = cfg.get("path")
    if isinstance(p, str) and p.strip():
        p = os.path.expanduser(p.strip())
        return p if os.path.isfile(p) else None
    return shutil.which("codex") or extension_codex()


# --------------------------------------------------------------------------------- probing

def _kill_tree(proc):
    """Kill the app-server and anything it started. Returns a note when the kill failed."""
    note = None
    try:
        if os.name == "nt":
            if proc.poll() is None:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=5,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
        else:
            import signal
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    except Exception as exc:
        note = "kill failed: %r" % (exc,)
    try:
        proc.wait(2)
    except Exception:
        try:
            proc.kill()
            proc.wait(1)
        except Exception as exc:
            note = "child not reaped: %r" % (exc,)
    return note


def probe(path, deadline=PROBE_DEADLINE):
    """("ok", result) | ("auth", message) | ("fail", reason), within `deadline` seconds."""
    cmd = [sys.executable, path] if path.lower().endswith(".py") else [path]
    cmd.append("app-server")
    kw = {"stdin": subprocess.PIPE, "stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    else:
        kw["start_new_session"] = True
    try:
        proc = subprocess.Popen(cmd, **kw)
    except Exception as exc:
        return "fail", "cannot start: %s" % (exc.__class__.__name__,)
    end = time.time() + deadline
    lines = queue.Queue()

    def reader():
        try:
            for line in proc.stdout:
                lines.put(line)
        except Exception:
            pass
        lines.put(None)

    threading.Thread(target=reader, daemon=True).start()

    def send(obj):
        proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
        proc.stdin.flush()

    def wait_id(want):
        while True:
            left = end - time.time()
            if left <= 0:
                return "timeout"
            try:
                line = lines.get(timeout=left)
            except queue.Empty:
                return "timeout"
            if line is None:
                return "closed"
            try:
                msg = json.loads(line.decode("utf-8", "replace"))
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("id") == want and "method" not in msg:
                return msg

    try:
        send({"id": 1, "method": "initialize",
              "params": {"clientInfo": {"name": "dispatch-guard", "version": "0"}}})
        msg = wait_id(1)
        if not isinstance(msg, dict):
            return "fail", "no reply to initialize (%s)" % msg
        if "error" in msg:
            return "fail", "initialize error"
        send({"method": "initialized"})
        send({"id": 2, "method": "account/rateLimits/read"})
        msg = wait_id(2)
        if not isinstance(msg, dict):
            return "fail", "no reply to rateLimits/read (%s)" % msg
        err = msg.get("error")
        if err is not None:
            text = str(err.get("message", "")) if isinstance(err, dict) else str(err)
            if "auth" in text.lower() or "login" in text.lower():
                return "auth", text[:120]
            return "fail", "rateLimits/read error %s" % (
                err.get("code") if isinstance(err, dict) else "?")
        res = msg.get("result")
        if not isinstance(res, dict):
            return "fail", "reply has no result"
        return "ok", res
    except Exception as exc:
        return "fail", "probe error: %s" % (exc.__class__.__name__,)
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        _kill_tree(proc)


# ---------------------------------------------------------------------------- classifying

def _label(mins):
    if mins == 300:
        return "5h"
    if mins == 10080:
        return "weekly"
    return "%sm" % mins if isinstance(mins, (int, float)) else "window"


def classify(result, cfg, now):
    """A probe result -> a record, or None when the shape is not recognised (ADR D4.3-6).

    The word is the top-level `rateLimits` only, exactly as in 0.76.0; every OTHER bucket of
    `rateLimitsByLimitId` is reported in `limits`, never used to refuse (ADDENDUM-0.76.1 A2-A4)."""
    rl = result.get("rateLimits")
    allowed = result.get("ordinaryUsageAllowed")
    if not isinstance(rl, dict) or not isinstance(allowed, bool):
        return None
    rec = _snapshot(rl, allowed, cfg, now)
    if rec is None:
        return None
    main_id = rl.get("limitId") if isinstance(rl.get("limitId"), str) else "codex"
    rec["limits"] = [_limit(main_id, rl, rec, True)]
    by = result.get("rateLimitsByLimitId")
    for key, snap in (by.items() if isinstance(by, dict) else ()):
        if key == main_id:
            continue
        got = _snapshot(snap, None, cfg, now) if isinstance(snap, dict) else None
        rec["limits"].append(_limit(str(key), snap if isinstance(snap, dict) else {},
                                    got or {"word": "UNAVAILABLE", "detail": "unrecognised"},
                                    False))
    return rec


def _limit(limit_id, snap, rec, main):
    name = snap.get("limitName")
    label = name if isinstance(name, str) and name.strip() else limit_id
    label = " ".join(label.replace("|", " ").split())   # a label cannot forge a ` | ` segment
    until = rec.get("until") if rec.get("word") == "WAIT" else None
    return {"limit_id": limit_id, "label": label, "word": rec["word"], "until": until,
            "until_text": None if until is None or rec.get("unknown") else _local(until),
            "detail": rec.get("detail", ""), "main": main}


def _snapshot(rl, allowed, cfg, now):
    """One RateLimitSnapshot -> {word, detail, until?, unknown?}, or None if unrecognised.
    `allowed` is ordinaryUsageAllowed for the main bucket, None for the others."""
    wins = []
    for name in ("primary", "secondary"):
        w = rl.get(name)
        if isinstance(w, dict) and isinstance(w.get("usedPercent"), (int, float)) \
                and not isinstance(w.get("usedPercent"), bool):
            r = w.get("resetsAt")
            wins.append({"name": name, "pct": float(w["usedPercent"]),
                         "label": _label(w.get("windowDurationMins")),
                         "resets": r if isinstance(r, (int, float)) and not isinstance(r, bool)
                         else None})
    if not wins:
        return None
    detail = ", ".join("%s %d%%" % (w["label"], round(w["pct"])) for w in wins)
    full = [w for w in wins if w["pct"] >= 100]
    if allowed is False or rl.get("rateLimitReachedType") or full:
        times = [w["resets"] for w in full if w["resets"]]
        if not times:
            p = [w["resets"] for w in wins if w["name"] == "primary" and w["resets"]]
            times = p
        t = max(times) if times else None
        if t and t > now:
            return {"word": "WAIT", "until": float(t), "unknown": False, "detail": detail}
        return {"word": "WAIT", "until": now + UNKNOWN_RESET, "unknown": True, "detail": detail}
    if any(w["pct"] >= pace_pct(cfg) for w in wins):
        return {"word": "PACE", "detail": detail}
    return {"word": "GO", "detail": detail}


def _find_rate_limits(obj, depth=0):
    if depth > 6:
        return None
    if isinstance(obj, dict):
        if isinstance(obj.get("rate_limits"), dict):
            return obj["rate_limits"]
        for v in obj.values():
            r = _find_rate_limits(v, depth + 1)
            if r is not None:
                return r
    return None


def session_log_note(now):
    """'(last session log: limit until <t>)' from Codex's newest rollout, or "" (ADR D5)."""
    try:
        home = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
        files = glob.glob(os.path.join(home, "sessions", "*", "*", "*", "rollout-*.jsonl"))
        if not files:
            return ""
        newest = max(files, key=os.path.getmtime)
        with open(newest, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 262144))
            tail = f.read().decode("utf-8", "replace").splitlines()
        for line in reversed(tail):
            if "rate_limits" not in line:
                continue
            try:
                rl = _find_rate_limits(json.loads(line))
            except ValueError:
                continue
            if rl is None:
                continue
            ts = []
            for w in (rl.get("primary"), rl.get("secondary")):
                if isinstance(w, dict) and isinstance(w.get("used_percent"), (int, float)) \
                        and w["used_percent"] >= 100 and isinstance(w.get("resets_at"), (int, float)) \
                        and w["resets_at"] > now:
                    ts.append(w["resets_at"])
            return "(last session log: limit until %s)" % _local(max(ts)) if ts else ""
    except Exception:
        return ""
    return ""


def compute(sdir, now=None):
    """Probe and classify. Always returns a record; never raises."""
    now = now or time.time()
    cfg = codex_config(sdir)
    rec = {"checked_at": now, "source": "server", "path": None, "reason": None,
           "until": None, "detail": ""}
    if is_off(cfg):
        rec.update(word="OFF", source="config")
        return rec
    try:
        path = locate(cfg)
    except Exception:
        path = None
    rec["path"] = path
    if not path:
        rec.update(word="UNAVAILABLE", reason="not-installed", source="none",
                   detail="not found via codex.path, PATH or the VS Code extension")
        return rec
    status, data = probe(path)
    if status == "auth":
        rec.update(word="UNAVAILABLE", reason="not-logged-in", detail=data)
        return rec
    got = classify(data, cfg, now) if status == "ok" else None
    if got is None:
        why = data if status == "fail" else "unrecognised reply shape"
        note = session_log_note(now)
        rec.update(word="UNAVAILABLE", reason="probe-failed", source="none",
                   detail=(why + (" " + note if note else "")))
        return rec
    rec.update(got)
    return rec


# -------------------------------------------------------------------------- cache, refresh

def read_cache(sdir, now=None):
    """(record or None, fresh?)"""
    now = now or time.time()
    rec = _read_json(os.path.join(sdir, CACHE))
    if not isinstance(rec, dict) or rec.get("word") not in EXIT:
        return None, False
    age = now - float(rec.get("checked_at") or 0)
    word = rec["word"]
    if word == "OFF":
        return rec, False                 # OFF is read from config.json, every time
    if word == "WAIT" and float(rec.get("until") or 0) <= now:
        return rec, False
    limit = FRESH_OK if word in ("GO", "PACE") else FRESH_BAD
    return rec, 0 <= age < limit


def refresh(sdir, now=None):
    """Probe once under the single-flight lock and write the cache. None when another holds it."""
    os.makedirs(sdir, exist_ok=True)
    lock = os.path.join(sdir, LOCK)
    if not _take_lock(lock, LOCK_STALE):
        return None
    try:
        rec = compute(sdir, now)
        _write_json(os.path.join(sdir, CACHE), rec)
        try:
            recover(sdir, rec)
        except Exception:
            pass
        return rec
    finally:
        _drop_lock(lock)


def spawn_refresh(sdir, now=None):
    """Start `usage.py --codex-refresh --dir <sdir>` detached; at most once per SPAWN_EVERY s."""
    now = now or time.time()
    mark = os.path.join(sdir, SPAWN)
    try:
        if now - os.path.getmtime(mark) < SPAWN_EVERY:
            return False
    except OSError:
        pass
    try:
        os.makedirs(sdir, exist_ok=True)
        with open(mark, "w") as f:
            f.write(str(now))
    except OSError:
        return False
    # ⛔ Every handle to DEVNULL: a hook's stdout is a pipe Claude Code reads, and a child that
    # inherits it holds the hook open. --dir so the child writes THIS state dir.
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
          "stderr": subprocess.DEVNULL, "cwd": sdir}
    if os.name == "nt":
        kw["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0x8)
                               | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
                               | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
    else:
        kw["start_new_session"] = True
    try:
        subprocess.Popen([sys.executable, os.path.join(HERE, "usage.py"),
                          "--codex-refresh", "--dir", sdir], **kw)
    except Exception:
        return False
    return True


# ------------------------------------------------------------------------------ the notice

def episode(rec):
    """The notice key: a fixed vocabulary, never a time (ADR D9, R2-B2)."""
    w = rec.get("word")
    if w == "WAIT":
        return "WAIT"
    if w == "OFF":
        return "OFF"
    if w == "UNAVAILABLE":
        r = rec.get("reason")
        return "UNAVAILABLE|%s" % (r if r in REASONS else "probe-failed")
    return None


def _marker(sdir):
    m = _read_json(os.path.join(sdir, NOTICE), {})
    if not isinstance(m, dict):
        m = {}
    if not isinstance(m.get("keys"), dict):
        m["keys"] = {}
    return m


def announce(sdir, rec, now=None):
    """'new' when THIS call must tell the owner, 'told' when it must not, None at GO/PACE."""
    key = episode(rec)
    if key is None:
        return None
    now = now or time.time()
    lock = os.path.join(sdir, NOTICE_LOCK)
    if not _take_lock(lock, NOTICE_LOCK_STALE):
        return "told"                     # another process is telling the owner right now
    try:
        m = _marker(sdir)
        if key in m["keys"]:
            return "told"
        m["keys"][key] = now
        m["first_go_at"] = None
        _write_json(os.path.join(sdir, NOTICE), m)
        return "new"
    finally:
        _drop_lock(lock)


def recover(sdir, rec, now=None):
    """After a probe: GO/PACE clears WAIT and OFF at once, UNAVAILABLE after an hour of GO."""
    now = now or time.time()
    lock = os.path.join(sdir, NOTICE_LOCK)
    if not _take_lock(lock, NOTICE_LOCK_STALE):
        return
    try:
        m = _marker(sdir)
        before = json.dumps(m, sort_keys=True)
        if rec.get("word") in ("GO", "PACE"):
            m["keys"].pop("WAIT", None)
            m["keys"].pop("OFF", None)
            first = m.get("first_go_at")
            if not isinstance(first, (int, float)):
                m["first_go_at"] = first = now
            if now - first >= RECOVER_UNAVAILABLE:
                for k in [k for k in m["keys"] if k.startswith("UNAVAILABLE|")]:
                    del m["keys"][k]
        else:
            m["first_go_at"] = None
        if json.dumps(m, sort_keys=True) != before:
            _write_json(os.path.join(sdir, NOTICE), m)
    finally:
        _drop_lock(lock)


def owner_line(rec):
    """The one line the owner hears, once per episode per machine."""
    w, r = rec.get("word"), rec.get("reason")
    if w == "WAIT":
        when = "an unknown time (re-checked every 5 minutes)" if rec.get("unknown") \
            else _local(rec["until"])
        return ("Codex is at its usage limit until %s. Sessions carry on without it and use it "
                "again after the reset - nobody needs to do anything." % when)
    if w == "OFF":
        return "Codex is switched off in dispatch-guard's config.json (codex.enabled false)."
    if r == "not-installed":
        return ("Codex CLI was not found on this machine (codex.path, PATH, VS Code extension). "
                "Sessions carry on without it.")
    if r == "not-logged-in":
        return "Codex CLI is not logged in on this machine. Sessions carry on without it."
    return ("The Codex usage check failed (%s). Sessions keep using Codex anyway."
            % (rec.get("detail") or "unknown reason"))


# ------------------------------------------------------------------------------ the verdict

def action(rec):
    """The action for the current word only - PROTOCOL.md 'Codex verdict' holds all of them."""
    w, r = rec.get("word"), rec.get("reason")
    if w == "GO":
        return "use Codex."
    if w == "PACE":
        return "small Codex calls only, no large job - the account is shared by every session."
    if w == "WAIT":
        when = "the next check" if rec.get("unknown") else _local(rec["until"])
        return ("carry on without Codex, do not ask the owner, use it again after %s." % when)
    if w == "OFF":
        return "do not use Codex until the owner switches it back on."
    if r == "probe-failed":
        return "the usage check is broken, not Codex: use Codex anyway."
    return "carry on without Codex; tell the owner once and ask whether to keep trying."


def text_of(rec):
    w = rec.get("word")
    head = "Codex: %s" % w
    if w == "WAIT":
        head += " (reset time unknown)" if rec.get("unknown") else " until %s" % _local(rec["until"])
    elif w == "UNAVAILABLE":
        head += " %s" % rec.get("reason")
    bits = [b for b in (rec.get("detail"), rec.get("path") and "codex: %s" % rec["path"]) if b]
    if bits:
        head += " (%s)" % "; ".join(bits)
    line = "%s - %s" % (head, action(rec))
    for lim in rec.get("limits") or ():
        if not lim.get("main"):
            line += " | " + _limit_text(lim)
    return line


_LIMIT_ACTION = {"GO": "usable", "PACE": "small use only", "UNAVAILABLE": "unknown"}


def _limit_text(lim):
    """` | limit <label>: <WORD>[ until <t>] - <action>` (ADDENDUM-0.76.1 A5)."""
    w = lim["word"]
    when = lim.get("until_text") or ("the next check" if w == "WAIT" else None)
    s = "limit %s: %s" % (lim["label"], w)
    if w == "WAIT":
        s += " until %s" % when if lim.get("until_text") else " (reset time unknown)"
        return s + " - do not use what this limit covers until %s; do not ask the owner" % when
    return s + " - " + _LIMIT_ACTION.get(w, "unknown")


def verdict(sdir, now=None):
    """The record --codex-verdict prints: from a fresh cache, or one probe, or the holder's."""
    now = now or time.time()
    if is_off(codex_config(sdir)):
        return {"word": "OFF", "source": "config", "checked_at": now, "until": None,
                "reason": None, "detail": "", "path": None}
    rec, fresh = read_cache(sdir, now)
    if fresh:
        return rec
    got = refresh(sdir, now)
    if got is not None:
        return got
    end = time.time() + VERDICT_WAIT       # another process is probing: wait for its answer
    while time.time() < end:
        time.sleep(0.25)
        rec, fresh = read_cache(sdir)
        if fresh:
            return rec
    got = refresh(sdir)                    # its lock may have gone stale meanwhile
    if got is not None:
        return got
    # ⚠ "slow" is not a state change: this answer is never announced to the owner (see main()).
    return {"word": "UNAVAILABLE", "reason": "probe-failed", "source": "none", "checked_at": now,
            "until": None, "path": None, "slow": True,
            "detail": "another usage check did not finish in %d s" % VERDICT_WAIT}


def main(argv, sdir):
    if "--codex-refresh" in argv:
        refresh(sdir)
        return 0
    rec = verdict(sdir)
    told = None if rec.get("slow") else announce(sdir, rec)
    out = dict(rec)
    out["exit"] = EXIT[rec["word"]]
    out["text"] = text_of(rec)
    out["until_text"] = _local(rec["until"]) if rec.get("until") else None
    out["limits"] = rec.get("limits") or []
    if told == "new":
        out["notice"] = "TELL THE OWNER: " + owner_line(rec)
    elif told == "told":
        out["notice"] = "(already told on this machine - say nothing)"
    else:
        out["notice"] = None
    if "--json" in argv:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(out["text"])
        if out["notice"]:
            print(out["notice"])
    return out["exit"]


# ------------------------------------------------------------------ finding Codex calls (D7)

_CODEX_NAMES = frozenset(("codex", "codex.exe", "codex.cmd", "codex.ps1"))
_SAFE_FIRST = frozenset(("--version", "-V", "-h", "--help", "help"))
_SAFE_TWO = (("login", "status"), ("app-server", "generate-json-schema"))
_HEREDOC_OP = re.compile(r"<<(-?)[ \t]*(?:'([^'\n]*)'|\"([^\"\n]*)\"|(\\)?([A-Za-z_0-9.-]+))")
MAX_DEPTH = 3


def _sub_end(text, i):
    """Index of the `)` closing a `$(` whose body starts at i (quote-aware), or len(text)."""
    depth, q, n = 1, None, len(text)
    while i < n:
        c = text[i]
        if q == "'":
            if c == "'":
                q = None
        elif q == '"':
            if c == "\\":
                i += 1
            elif c == '"':
                q = None
        elif c == "\\":
            i += 1
        elif c in "'\"":
            q = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def _tick_end(text, i):
    """Index of the backtick closing a span whose body starts at i, or len(text)."""
    n = len(text)
    while i < n:
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == "`":
            return i
        i += 1
    return n


def _body_subs(body, ps, depth, out):
    """Substitutions in an UNQUOTED heredoc body. Quotes there are data (codex-03 follow-up)."""
    i, n = 0, len(body)
    while i < n:
        c = body[i]
        if c == "\\":
            i += 2
            continue
        if c == "$" and body[i + 1:i + 2] == "(":
            e = _sub_end(body, i + 2)
            _scan(body[i + 2:e], ps, depth + 1, out)
            i = e + 1
            continue
        if c == "`" and not ps:
            e = _tick_end(body, i + 1)
            _scan(body[i + 1:e], ps, depth + 1, out)
            i = e + 1
            continue
        i += 1


def _scan(text, ps, depth, out):
    """Append every simple command in `text`, as a list of quote-stripped words, to `out`."""
    if depth > MAX_DEPTH:
        return
    esc = "`" if ps else "\\"
    words, cur, has = [], [], False
    pending = []                     # heredocs opened on this line: (delimiter, quoted)
    i, n = 0, len(text)

    def end_word():
        nonlocal cur, has
        if has:
            words.append("".join(cur))
        cur, has = [], False

    def end_cmd():
        end_word()
        if words:
            out.append(list(words))
        del words[:]

    while i < n:
        c = text[i]
        if c == "#" and not has:
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == esc and i + 1 < n:
            if text[i + 1] != "\n":
                cur.append(text[i + 1])
                has = True
            i += 2
            continue
        if c == "'":
            e = text.find("'", i + 1)
            e = n if e < 0 else e
            cur.append(text[i + 1:e])
            has = True
            i = e + 1
            continue
        if c == '"':
            i += 1
            has = True
            while i < n and text[i] != '"':
                d = text[i]
                if d == esc and i + 1 < n:
                    nxt = text[i + 1]
                    if ps or nxt in '$`"\\\n':
                        cur.append(nxt)
                    else:
                        cur.append(d + nxt)
                    i += 2
                    continue
                if d == "$" and text[i + 1:i + 2] == "(":
                    e = _sub_end(text, i + 2)
                    _scan(text[i + 2:e], ps, depth + 1, out)
                    cur.append("$()")
                    i = e + 1
                    continue
                if d == "`" and not ps:
                    e = _tick_end(text, i + 1)
                    _scan(text[i + 1:e], ps, depth + 1, out)
                    cur.append("``")
                    i = e + 1
                    continue
                cur.append(d)
                i += 1
            i += 1
            continue
        if c == "$" and text[i + 1:i + 2] == "(":
            e = _sub_end(text, i + 2)
            _scan(text[i + 2:e], ps, depth + 1, out)
            cur.append("$()")
            has = True
            i = e + 1
            continue
        if c == "`" and not ps:
            e = _tick_end(text, i + 1)
            _scan(text[i + 1:e], ps, depth + 1, out)
            cur.append("``")
            has = True
            i = e + 1
            continue
        if c == "<" and not ps and text.startswith("<<", i) and not text.startswith("<<<", i):
            m = _HEREDOC_OP.match(text, i)
            if m:
                quoted = m.group(2) is not None or m.group(3) is not None or bool(m.group(4))
                delim = m.group(2) if m.group(2) is not None else \
                    m.group(3) if m.group(3) is not None else m.group(5)
                pending.append((delim, quoted))
                end_word()
                i = m.end()
                continue
        if c == "\n":
            end_cmd()
            i += 1
            for delim, quoted in pending:
                start = i
                while i < n:
                    j = text.find("\n", i)
                    j = n if j < 0 else j
                    if text[i:j].strip() == delim:
                        body, i = text[start:i], min(j + 1, n)
                        break
                    i = j + 1
                else:
                    body = text[start:]
                if not quoted:
                    _body_subs(body, ps, depth, out)
            pending = []
            continue
        if text.startswith(("&&", "||"), i):
            end_cmd()
            i += 2
            continue
        if c in ";|)\r" or (c == "(" and not has):
            end_cmd()
            i += 1
            continue
        if c == "&" and not ps:
            prev = text[i - 1] if i else ""
            nxt = text[i + 1:i + 2]
            if prev in "><" or nxt == ">":
                cur.append(c)
                has = True
            else:
                end_cmd()
            i += 1
            continue
        if c in " \t":
            end_word()
            i += 1
            continue
        cur.append(c)
        has = True
        i += 1
    end_cmd()


def commands(command, shell="bash"):
    """Every simple command in a shell string, recursing into substitutions (ADR D7)."""
    out = []
    try:
        _scan(command or "", shell == "powershell", 0, out)
    except Exception:
        return []
    return out


def head(words, ps=False):
    """The command words from the command word on (wrappers, VAR=, keywords, PS `&`/`.` skipped)."""
    import cmd_guards
    w = list(words)
    for _ in range(8):
        w = cmd_guards._head_words(w)
        if w and (w[0] in cmd_guards._KEYWORDS or (ps and w[0] in ("&", "."))):
            w = w[1:]
            continue
        break
    return w


def _base(word):
    return re.split(r"[\\/]", word)[-1].casefold()


def codex_calls(command, shell="bash"):
    """The argument lists of every Codex call that is NOT on the positional allowlist."""
    ps = shell == "powershell"
    found = []
    for words in commands(command, shell):
        w = head(words, ps)
        if not w or _base(w[0]) not in _CODEX_NAMES:
            continue
        args = w[1:]
        if args and args[0] in _SAFE_FIRST:
            continue
        if tuple(args[:2]) in _SAFE_TWO:
            continue
        found.append(args)
    return found


# ---------------------------------------------------------------------- the gate's decision

def gate(sdir, enabled=True, now=None):
    """(model text, screen line or None) to refuse this Codex call, or None to allow it.

    Reads the cache only, never probes inline (MAC change 2). A stale cache starts a detached
    refresher, unless the switch is off (R1-N6)."""
    now = now or time.time()
    if is_off(codex_config(sdir)):
        rec = {"word": "OFF"}
    else:
        rec, fresh = read_cache(sdir, now)
        if not fresh and enabled:
            spawn_refresh(sdir, now)
        if not rec or rec.get("word") != "WAIT" or rec.get("source") != "server" \
                or float(rec.get("until") or 0) <= now:
            return None
    screen = None
    if enabled and announce(sdir, rec, now) == "new":
        screen = "dispatch-guard: " + owner_line(rec)
    if rec["word"] == "OFF":
        why = "Codex is switched off by the owner (codex.enabled false in config.json)"
        after = "Do not use it until the owner switches it back on."
    else:
        when = _local(rec["until"])
        why = "Codex is at its usage limit (measured from the Codex server)"
        after = ("It is usable again after %s%s; run `%s` then." %
                 (when, " (reset time unknown, re-checked every 5 minutes)" if rec.get("unknown")
                  else "", COMMAND))
    return ("dispatch gate: this Codex call is REFUSED. %s. Carry on without Codex and do NOT "
            "ask the owner about it. %s" % (why, after)), screen


# ------------------------------------------------------------------ reset credits (D8)

_RESET_RE = re.compile(r"method\\?[\"']?\s*[:=]\s*\\?[\"']?\s*" + re.escape(RESET_METHOD), re.I)
_READ_TOOLS = frozenset(("grep", "egrep", "fgrep", "rg", "cat", "head", "tail", "less", "more",
                         "wc", "ls", "echo", "printf", "type", "select-string", "get-content"))
_GIT_READS = frozenset(("grep", "log", "show", "diff"))


def sends_reset(text):
    """True when file content sends the reset-credit method as a JSON-RPC method value."""
    return isinstance(text, str) and bool(_RESET_RE.search(text))


def shell_sends_reset(command, shell="bash"):
    """True when a shell command names the method and is not purely reads (ADR D8)."""
    if not isinstance(command, str) or RESET_METHOD.lower() not in command.lower():
        return False
    ps = shell == "powershell"
    cmds = commands(command, shell)
    if not cmds:
        return True
    for words in cmds:
        w = head(words, ps)
        if not w:
            continue
        b = _base(w[0])
        b = b[:-4] if b.endswith(".exe") else b
        if b in _READ_TOOLS:
            continue
        if b == "git" and len(w) > 1 and w[1] in _GIT_READS:
            continue
        return True
    return False
