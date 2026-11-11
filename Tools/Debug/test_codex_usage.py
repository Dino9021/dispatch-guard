#!/usr/bin/env python3
"""The Codex usage verdict and the Codex gate (0.76.0).

    python Tools/Debug/test_codex_usage.py

ADR: Memory/tasks/20261110-164252-codex-usage-gate/ADR.md, D13 is this file's list.

⭐ A FAKE `codex` plays every server behaviour: a Python script reached through `codex.path` in
the scratch state dir's config.json. It records every method it was sent, so the check can
assert the probe sent the three allowed methods and nothing else - the account holds reset
credits and the owner's decision is never to use them.
⚠ Nothing here runs the real codex, touches ~/.claude or ~/.codex, or uses the network.
"""

import json
import os
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import fresh_scratch, repo_path, scratch_dir  # noqa: E402
from test_guards import (bash, decision, file_tool, fixture_repo, gitlog, load_gate,  # noqa: E402
                         load_skills, reason, run_gate, stamp_session)

WIN = os.name == "nt"
NOW = time.time()

# The method that spends a reset credit, built by concatenation like the source does, so this
# file itself never sends it and stays editable under its own guard.
RESET = "account/rateLimit" + "ResetCredit/consume"

FAKE = r'''
import json, os, sys, time
mode = os.environ.get("FAKE_MODE") or open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mode.txt")).read().strip()
log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "methods.log")
def out(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
now = time.time()
def win(pct, mins, reset):
    return {"usedPercent": pct, "windowDurationMins": mins, "resetsAt": reset}
for line in sys.stdin:
    msg = json.loads(line)
    with open(log, "a") as f:
        f.write(msg.get("method", "?") + "\n")
    if mode == "hang":
        time.sleep(60)
    if msg.get("id") == 1:
        out({"method": "remoteControl/status/changed", "params": {}})
        out({"id": 1, "result": {}})
    elif msg.get("id") == 2:
        if mode == "auth":
            out({"id": 2, "error": {"code": -32600, "message": "codex account authentication required to read rate limits"}})
        elif mode == "garbage":
            out({"id": 2, "result": {"something": "else"}})
        elif mode.startswith("map_"):
            top = {"limitId": "codex", "primary": win(12, 300, now + 3600), "secondary": win(30, 10080, now + 86400)}
            by = {"codex": top}
            if mode in ("map_two", "map_odd"):
                by["img"] = {"limitId": "img", "limitName": "Images" if mode == "map_two" else None,
                             "primary": win(100, 300, now + 7200), "secondary": None,
                             "rateLimitReachedType": "primary"}
            if mode == "map_odd":
                by["broken"] = "not a snapshot"
                by["pipe"] = {"limitName": "a|b\nc", "primary": win(5, 300, now + 3600)}
            res = {"ordinaryUsageAllowed": True, "rateLimitsByLimitId": by}
            if mode != "map_only":
                res["rateLimits"] = top
            out({"id": 2, "result": res})
        else:
            p, s, allowed, reached = {
                "go": (win(12, 300, now + 3600), win(30, 10080, now + 86400), True, None),
                "pace": (win(93, 300, now + 3600), win(30, 10080, now + 86400), True, None),
                "wait": (win(100, 300, now + 7200), win(40, 10080, now + 86400), False, "primary"),
                "wait_past": (win(100, 300, now - 60), None, False, "primary"),
                "null_secondary": (win(20, 300, now + 3600), None, True, None),
            }[mode]
            out({"id": 2, "result": {"ordinaryUsageAllowed": allowed,
                 "rateLimits": {"primary": p, "secondary": s, "rateLimitReachedType": reached}}})
'''


def setup_fake(d):
    """The fake codex in `d`; returns the path config.json names (a .cmd wrapper on Windows)."""
    py = os.path.join(d, "fakecodex.py")
    with open(py, "w", encoding="utf-8") as f:
        f.write(FAKE)
    if WIN:
        cmd = os.path.join(d, "codex.cmd")
        with open(cmd, "w", encoding="utf-8") as f:
            f.write('@"%s" "%s" %%*\r\n' % (sys.executable, py))
        return cmd
    return py


def set_mode(d, mode):
    with open(os.path.join(d, "mode.txt"), "w", encoding="utf-8") as f:
        f.write(mode)
    try:
        os.remove(os.path.join(d, "methods.log"))
    except OSError:
        pass


def methods(d):
    try:
        with open(os.path.join(d, "methods.log"), encoding="utf-8") as f:
            return [x.strip() for x in f if x.strip()]
    except OSError:
        return []


def write_cfg(sdir, **codex):
    with open(os.path.join(sdir, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"codex": codex}, f)


def clear_state(sdir):
    import codex_usage as c
    for n in (c.CACHE, c.LOCK, c.SPAWN, c.NOTICE, c.NOTICE_LOCK):
        try:
            os.remove(os.path.join(sdir, n))
        except OSError:
            pass


def put_cache(sdir, **rec):
    import codex_usage as c
    base = {"checked_at": time.time(), "source": "server", "path": "x", "reason": None,
            "until": None, "detail": ""}
    base.update(rec)
    c._write_json(os.path.join(sdir, c.CACHE), base)


# -------------------------------------------------------------------------------- verdict

def case_verdicts(sdir, fake_dir, fake):
    import codex_usage as c
    write_cfg(sdir, path=fake)
    expect = {"go": "GO", "pace": "PACE", "wait": "WAIT", "null_secondary": "GO",
              "wait_past": "WAIT"}
    for mode, word in expect.items():
        clear_state(sdir)
        set_mode(fake_dir, mode)
        rec = c.verdict(sdir)
        assert rec["word"] == word, (mode, rec)
        # ⛔ Only the three allowed methods, ever.
        assert methods(fake_dir) == ["initialize", "initialized", "account/rateLimits/read"], \
            (mode, methods(fake_dir))
        if mode == "wait":
            assert rec["until"] > time.time() + 3000 and not rec["unknown"], rec
        if mode == "wait_past":
            assert rec["unknown"] and rec["until"] <= time.time() + c.UNKNOWN_RESET + 1, rec
    clear_state(sdir)
    set_mode(fake_dir, "auth")
    rec = c.verdict(sdir)
    assert (rec["word"], rec["reason"]) == ("UNAVAILABLE", "not-logged-in"), rec
    clear_state(sdir)
    set_mode(fake_dir, "garbage")
    rec = c.verdict(sdir)
    assert (rec["word"], rec["reason"]) == ("UNAVAILABLE", "probe-failed"), rec
    # Not installed: a codex.path that does not exist.
    clear_state(sdir)
    write_cfg(sdir, path=os.path.join(fake_dir, "nope.exe"))
    rec = c.verdict(sdir)
    assert (rec["word"], rec["reason"]) == ("UNAVAILABLE", "not-installed"), rec
    # OFF, with no probe at all.
    clear_state(sdir)
    set_mode(fake_dir, "go")
    write_cfg(sdir, path=fake, enabled=False)
    rec = c.verdict(sdir)
    assert rec["word"] == "OFF" and methods(fake_dir) == [], (rec, methods(fake_dir))
    # The cache answers the next call without a probe.
    write_cfg(sdir, path=fake)
    clear_state(sdir)
    c.verdict(sdir)
    set_mode(fake_dir, "go")
    c.verdict(sdir)
    assert methods(fake_dir) == [], "a fresh cache probed again"
    print("ok - GO, PACE, WAIT, past reset, null window, auth, garbage, not installed, OFF, cache; "
          "only three methods sent")


def case_hang(sdir, fake_dir, fake):
    import codex_usage as c
    clear_state(sdir)
    write_cfg(sdir, path=fake)
    set_mode(fake_dir, "hang")
    t0 = time.time()
    rec = c.verdict(sdir)
    took = time.time() - t0
    assert took < 12, took
    assert (rec["word"], rec["reason"]) == ("UNAVAILABLE", "probe-failed"), rec
    time.sleep(0.5)
    # No fake codex may survive the kill (on Windows through the .cmd wrapper: a grandchild).
    if WIN:
        out = subprocess.run(["wmic", "process", "where", "name='python.exe'", "get",
                              "commandline"], capture_output=True, text=True,
                             stdin=subprocess.DEVNULL).stdout
        left = [ln for ln in out.splitlines() if "fakecodex.py" in ln and fake_dir in ln]
        # Positive control: the listing must show THIS python, or "no child left" proves nothing.
        assert "python" in out.lower(), "the process listing came back empty"
    else:
        out = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout
        left = [ln for ln in out.splitlines() if "fakecodex.py" in ln and fake_dir in ln]
    assert not left, left
    print("ok - a hanging server returns in %.1fs as probe-failed and leaves no child" % took)


def case_session_log_note(sdir, fake_dir, fake):
    import codex_usage as c
    home = os.path.join(fake_dir, "codexhome")
    d = os.path.join(home, "sessions", "2026", "11", "10")
    os.makedirs(d, exist_ok=True)
    keep = os.environ.get("CODEX_HOME")
    os.environ["CODEX_HOME"] = home
    try:
        for pct, want in ((100, True), (50, False)):
            with open(os.path.join(d, "rollout-x.jsonl"), "w", encoding="utf-8") as f:
                f.write(json.dumps({"payload": {"rate_limits": {
                    "primary": {"used_percent": pct, "resets_at": time.time() + 7200}}}}) + "\n")
            clear_state(sdir)
            set_mode(fake_dir, "garbage")
            write_cfg(sdir, path=fake)
            rec = c.verdict(sdir)
            assert (rec["word"], rec["reason"]) == ("UNAVAILABLE", "probe-failed"), rec
            assert ("last session log: limit until" in rec["detail"]) == want, rec
            # The gate allows a probe failure, whatever the session log says (ADR D5).
            assert c.gate(sdir) is None
    finally:
        if keep is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = keep
    print("ok - a failed probe is never WAIT; the session log only adds a note")


def case_discovery(tmp):
    import codex_usage as c
    ext = os.path.join(tmp, "ext")
    for ver in ("26.999.1", "26.1021.3"):
        for sub in ("macos-x86_64", "macos-aarch64"):
            b = os.path.join(ext, "openai.chatgpt-%s-darwin-arm64" % ver, "bin", sub)
            os.makedirs(b, exist_ok=True)
            open(os.path.join(b, "codex"), "w").close()
    got = c.extension_codex(ext, machine="arm64", plat="darwin")
    assert got and "26.1021.3" in got and "macos-aarch64" in got, got
    print("ok - newest extension by number (26.1021 after 26.999), architecture folder preferred")


# ---------------------------------------------------------------------------------- notice

def case_notice(sdir):
    import codex_usage as c
    clear_state(sdir)
    t = time.time()
    a = {"word": "UNAVAILABLE", "reason": "probe-failed", "detail": "x"}
    b = {"word": "UNAVAILABLE", "reason": "probe-failed", "detail": "y other cause"}
    go = {"word": "GO"}
    news = [c.announce(sdir, a, t), c.announce(sdir, b, t + 1)]
    c.recover(sdir, go, t + 2)
    news.append(c.announce(sdir, a, t + 600))       # a flap within the hour
    assert news.count("new") == 1, news
    # GO held an hour clears it.
    c.recover(sdir, go, t + 2 + 3600)
    assert c.announce(sdir, a, t + 3700) == "new"

    clear_state(sdir)
    w = {"word": "WAIT", "until": t + 300, "unknown": True}
    seq = []
    for k in range(4):                               # four re-probes, the synthetic until moves
        w2 = dict(w, until=t + 300 * (k + 1))
        c.recover(sdir, w2, t + 300 * k)
        seq.append(c.announce(sdir, w2, t + 300 * k))
    w5 = {"word": "WAIT", "until": t + 86400, "unknown": False}   # 5h window -> weekly
    c.recover(sdir, w5, t + 1300)
    seq.append(c.announce(sdir, w5, t + 1300))
    assert seq.count("new") == 1, seq
    c.recover(sdir, go, t + 2000)
    assert c.announce(sdir, w, t + 2100) == "new", "a new WAIT after GO was not news"

    clear_state(sdir)
    u = {"word": "UNAVAILABLE", "reason": "not-logged-in"}
    seq = [c.announce(sdir, w, t), c.announce(sdir, u, t + 1), c.announce(sdir, w, t + 2)]
    assert seq.count("new") == 2, seq

    # Two processes at once, same new key: one line, under the notice lock.
    clear_state(sdir)
    code = ("import sys,time; sys.path.insert(0, r'%s'); import codex_usage as c; "
            "t=float(sys.argv[1]); time.sleep(max(0,t-time.time())); "
            "print(c.announce(r'%s', {'word':'OFF'}))" % (repo_path("hooks"), sdir))
    start = time.time() + 1.0
    procs = [subprocess.Popen([sys.executable, "-c", code, str(start)], stdout=subprocess.PIPE,
                              text=True) for _ in range(4)]
    outs = [p.communicate(timeout=30)[0].strip() for p in procs]
    assert outs.count("new") == 1, outs
    print("ok - notices: one per episode, a moving WAIT stays one, flap is one, races are one")


# -------------------------------------------------------------------------------- scanner

FIRE = [
    ('C=$(ls -d ~/.vscode/extensions/openai.chatgpt-*-darwin-arm64 | sort -V | tail -1)'
     '/bin/macos-aarch64/codex; "$C" exec - < p', None),   # the macOS form (see below)
    ("codex exec -", "bash"), ('"C:/x/codex.exe" exec', "bash"), ("CODEX.EXE exec", "bash"),
    ('& "C:\\Program Files\\x\\codex.exe" exec -', "powershell"),
    ("$null | codex exec -", "powershell"), ("$null | codex exec -", "bash"),
    ("codex exec resume", "bash"), ("codex review", "bash"), ("codex exec help", "bash"),
    ("out=$(codex exec - < p)", "bash"), ("x=`codex exec hi`", "bash"),
    ("if codex exec -; then :; fi", "bash"), ("sleep 1 & codex exec -", "bash"),
    ("sleep 1&codex exec -", "bash"), ("cat <<EOF\n$(codex exec hi)\nEOF", "bash"),
    ("cat <<EOF\n'$(codex exec hi)'\nEOF", "bash"), ('echo "$(codex exec hi)"', "bash"),
    ("cd /x && codex exec -", "bash"),
    ("C:/Users/x/.vscode/extensions/openai.chatgpt-1/bin/windows-x86_64/codex.exe exec -", "bash"),
]
NO_FIRE = [
    "grep codex file", "git log --grep codex", "echo codex-notes.md", "codex --version",
    "codex -V", "codex login status", "codex app-server generate-json-schema",
    "cat <<EOF\ncodex exec hi\nEOF", "cat <<'EOF'\ncodex exec hi\nEOF",
    "cat <<'EOF'\n$(codex exec hi)\nEOF", 'cat <<"EOF"\n$(codex exec hi)\nEOF',
    "cat <<\\EOF\n$(codex exec hi)\nEOF",
    "echo ok # note; codex exec hi", "printf '%s\\n' '$(codex exec hi)'",
    "echo a 2>&1", "cmd &> f", "x >& y", "echo \\$(codex exec hi)",
]


def case_scanner():
    import codex_usage as c
    for cmd, shell in FIRE:
        if shell is None:
            # ⚠ The macOS form names codex through a variable, `"$C" exec`, which no string scan
            # can resolve - ADR D7 lists `$VAR exec` as an unseen limit. Its inline form is what
            # DESIGN tells agents to run, and that one IS seen:
            cmd = ('"$(ls -d ~/.vscode/extensions/openai.chatgpt-*-darwin-arm64 | sort -V | '
                   'tail -1)/bin/macos-aarch64/codex" exec - < p')
            shell = "bash"
        assert c.codex_calls(cmd, shell), ("must fire", shell, cmd)
    for cmd in NO_FIRE:
        assert not c.codex_calls(cmd, "bash"), ("must not fire", cmd, c.commands(cmd))
    # The `&` rules split only where the shell would.
    assert c.commands("echo a 2>&1") == [["echo", "a", "2>&1"]], c.commands("echo a 2>&1")
    assert [w[0] for w in c.commands("sleep 1&codex exec -")] == ["sleep", "codex"]
    # Linear enough for a hook: a pathological string stays cheap.
    t0 = time.time()
    c.codex_calls('echo "' + '\\"' * 50000)
    c.codex_calls("$(" * 2000 + "codex exec")
    assert time.time() - t0 < 2, time.time() - t0
    print("ok - scanner: %d must-fire and %d must-not-fire shapes" % (len(FIRE), len(NO_FIRE)))


def case_macos_inline_quoted():
    """The macOS path written into a quoted word with a substitution: its basename is codex."""
    import codex_usage as c
    cmd = '"$C/bin/macos-aarch64/codex" exec - < p'
    assert c.codex_calls(cmd), "a quoted path ending in /codex was not seen"
    print("ok - a quoted macOS path ending in /codex is a call")


# ------------------------------------------------------------------------------- the gate

def case_gate(gate, sdir, root, fake_dir, fake):
    import codex_usage as c
    import cmd_guards
    write_cfg(sdir, path=fake)
    # A fresh server WAIT refuses, names the time, says not to ask; the owner hears it once.
    clear_state(sdir)
    put_cache(sdir, word="WAIT", until=time.time() + 3600, unknown=False)
    r = run_gate(gate, bash(root, "codex exec - < p"))
    assert decision(r) == "deny", r
    assert "do NOT ask the owner" in reason(r) and "usable again after" in reason(r), reason(r)
    assert "usage limit until" in (r.get("systemMessage") or ""), r
    r2 = run_gate(gate, bash(root, "codex exec hi"))
    assert decision(r2) == "deny" and not r2.get("systemMessage"), r2
    # The allowlist passes at WAIT; a non-Codex command too.
    for cmd in ("codex --version", "codex login status", "grep codex f", "echo ok # x; codex exec"):
        assert decision(run_gate(gate, bash(root, cmd))) is None, cmd
    # PowerShell.
    r = run_gate(gate, bash(root, '& "C:\\x\\codex.exe" exec -', tool="PowerShell"))
    assert decision(r) == "deny", r
    # GO, PACE, UNAVAILABLE allow.
    for rec in ({"word": "GO"}, {"word": "PACE"},
                {"word": "UNAVAILABLE", "reason": "probe-failed", "source": "none"}):
        clear_state(sdir)
        put_cache(sdir, **rec)
        assert decision(run_gate(gate, bash(root, "codex exec -"))) is None, rec
    # A WAIT whose time has passed allows (and starts a refresher).
    clear_state(sdir)
    put_cache(sdir, word="WAIT", until=time.time() - 5, checked_at=time.time() - 400)
    set_mode(fake_dir, "go")
    assert decision(run_gate(gate, bash(root, "codex exec -"))) is None
    assert os.path.exists(os.path.join(sdir, c.SPAWN)), "a stale cache did not start a refresher"
    end = time.time() + 15
    while time.time() < end and (c.read_cache(sdir)[0] or {}).get("word") != "GO":
        time.sleep(0.3)
    assert (c.read_cache(sdir)[0] or {}).get("word") == "GO", "the detached refresher wrote nothing"
    # OFF refuses, read from config.json directly.
    clear_state(sdir)
    write_cfg(sdir, path=fake, enabled=False)
    r = run_gate(gate, bash(root, "codex exec -"))
    assert decision(r) == "deny" and "switched off by the owner" in reason(r), r
    write_cfg(sdir, path=fake)
    # A hanging probe and a stale cache: the guard returns at once (it never probes inline).
    clear_state(sdir)
    set_mode(fake_dir, "hang")
    t0 = time.time()
    assert decision(run_gate(gate, bash(root, "codex exec -"))) is None
    assert time.time() - t0 < 2, time.time() - t0
    # Switch off: no refusal, logged, and NO spawn.
    clear_state(sdir)
    put_cache(sdir, word="WAIT", until=time.time() + 3600, checked_at=time.time() - 400)
    cfgfile = os.path.join(root, ".claude", "dispatch-guard.json")
    with open(cfgfile, "w", encoding="utf-8") as f:
        json.dump({"dispatch": {"codex_gate": False}}, f)
    try:
        assert decision(run_gate(gate, bash(root, "codex exec -"))) is None
        assert "CMD-DISABLED(codex_gate)" in gitlog(root)
        assert not os.path.exists(os.path.join(sdir, c.SPAWN)), "a disabled gate spawned"
    finally:
        os.remove(cfgfile)
    # Unstamped: advisory.
    clear_state(sdir)
    put_cache(sdir, word="WAIT", until=time.time() + 3600)
    assert decision(run_gate(gate, bash(root, "codex exec -", sid="never-stamped"))) is None
    # Mutation: without the row the same payload passes.
    keep = cmd_guards.GUARDS
    cmd_guards.GUARDS = tuple(g for g in keep if g[0] != "codex_gate")
    try:
        assert decision(run_gate(gate, bash(root, "codex exec -"))) is None, "mutation stood"
    finally:
        cmd_guards.GUARDS = keep
    names = [k for k, _ in cmd_guards.GUARDS]
    assert names.index("codex_gate") < names.index("guard_relative_cd"), names
    assert decision(run_gate(gate, bash(root, "cd sub && codex exec -"))) == "deny"
    clear_state(sdir)
    print("ok - gate: WAIT/OFF refuse once-told, allowlist, PowerShell, GO/PACE/UNAVAILABLE "
          "allow, detached refresh, hang, switch, unstamped, mutation, order")


def case_end_to_end(sdir, root, fake_dir, fake):
    """ONE real hook process, hanging fake probe, stale cache: the hook must exit in < 5 s."""
    import codex_usage as c
    clear_state(sdir)
    write_cfg(sdir, path=fake)
    set_mode(fake_dir, "hang")
    put_cache(sdir, word="GO", checked_at=time.time() - 400)
    # ⛔ A fixed, low Claude usage reading, as test_slot_lifecycle.py does: without one the gate
    # process would fetch the machine's real usage.
    now = time.time()
    with open(os.path.join(sdir, "token_usage.json"), "w", encoding="utf-8") as f:
        json.dump({"ts": int(now * 1000),
                   "five_hour": {"used_percentage": 5, "resets_at": int(now) + 3 * 3600}}, f)
    payload = json.dumps(bash(root, "codex exec - < p")).encode("utf-8")
    env = dict(os.environ, CLAUDE_DISPATCH_DIR=sdir)
    t0 = time.time()
    p = subprocess.run([sys.executable, repo_path("hooks", "dispatch_gate.py")], input=payload,
                       capture_output=True, env=env, timeout=30)
    took = time.time() - t0
    assert took < 5, "the hook took %.1fs: a detached child is holding it" % took
    assert os.path.exists(os.path.join(sdir, c.SPAWN)), (p.stdout[-300:], p.stderr[-300:])
    # Let the detached refresher finish its 10 s deadline before the next case.
    end = time.time() + 20
    while time.time() < end and os.path.exists(os.path.join(sdir, c.LOCK)):
        time.sleep(0.3)
    print("ok - end to end: the hook exits in %.1fs with a hanging probe behind it" % took)


def case_reset_credit(gate, sdir, root):
    import codex_usage as c
    import cmd_guards
    assert c.sends_reset(json.dumps({"id": 3, "method": RESET}))
    assert c.sends_reset('{"method":"%s"}' % RESET)
    assert c.sends_reset("printf '{\\\"method\\\": \\\"%s\\\"}'" % RESET)
    assert not c.sends_reset("Never call %s, it spends a credit." % RESET)
    # Shell.
    for cmd in ("jq -n --arg m %s '{method:$m}' | codex app-server" % RESET,
                "python send.py %s" % RESET):
        r = run_gate(gate, bash(root, cmd))
        assert decision(r) == "deny" and "reset" in reason(r), (cmd, r)
    for cmd in ("grep -rn %s hooks" % RESET, "git log -S %s" % RESET, "cat x | grep %s" % RESET):
        assert decision(run_gate(gate, bash(root, cmd))) is None, cmd
    # Files.
    p = os.path.join(root, "probe.py")
    r = run_gate(gate, file_tool(root, "Write", p, content='send({"method": "%s"})' % RESET))
    assert decision(r) == "deny", r
    r = run_gate(gate, file_tool(root, "Edit", p, old_string="a", new_string='{"method":"%s"}' % RESET))
    assert decision(r) == "deny", r
    r = run_gate(gate, file_tool(root, "MultiEdit", p, edits=[{"old_string": "a",
                                                               "new_string": "method: '%s'" % RESET}]))
    assert decision(r) == "deny", r
    r = run_gate(gate, file_tool(root, "Write", os.path.join(root, "notes.md"),
                                 content="Never send %s." % RESET))
    assert decision(r) is None, r
    # On at GO, independent of codex_gate.
    cfgfile = os.path.join(root, ".claude", "dispatch-guard.json")
    with open(cfgfile, "w", encoding="utf-8") as f:
        json.dump({"dispatch": {"codex_gate": False}}, f)
    try:
        assert decision(run_gate(gate, bash(root, "python send.py %s" % RESET))) == "deny"
    finally:
        os.remove(cfgfile)
    # Mutation.
    keep, fkeep = cmd_guards.GUARDS, cmd_guards.FILE_GUARDS
    cmd_guards.GUARDS = tuple(g for g in keep if g[0] != "guard_reset_credit")
    cmd_guards.FILE_GUARDS = tuple(g for g in fkeep if g[0] != "guard_reset_credit")
    try:
        assert decision(run_gate(gate, bash(root, "python send.py %s" % RESET))) is None
        assert decision(run_gate(gate, file_tool(root, "Write", p,
                                                 content='{"method":"%s"}' % RESET))) is None
    finally:
        cmd_guards.GUARDS, cmd_guards.FILE_GUARDS = keep, fkeep
    # ⛔ The shipped sources never hold the method as one literal.
    for rel in (("hooks", "codex_usage.py"), ("hooks", "cmd_guards.py")):
        with open(repo_path(*rel), encoding="utf-8") as f:
            assert RESET not in f.read(), rel
    print("ok - reset credit: refused in shell and files, reads pass, on at GO, mutation")


def case_cli(sdir, fake_dir, fake):
    """usage.py --codex-verdict: the text, the exit code, the owner line once."""
    clear_state(sdir)
    write_cfg(sdir, path=fake)
    set_mode(fake_dir, "wait")
    env = dict(os.environ, PYTHONUTF8="1")
    args = [sys.executable, repo_path("hooks", "usage.py"), "--codex-verdict", "--dir", sdir]
    a = subprocess.run(args, capture_output=True, text=True, env=env, timeout=60)
    b = subprocess.run(args + ["--json"], capture_output=True, text=True, env=env, timeout=60)
    assert a.returncode == 2 and "Codex: WAIT until" in a.stdout, (a.returncode, a.stdout, a.stderr)
    assert "TELL THE OWNER:" in a.stdout, a.stdout
    j = json.loads(b.stdout)
    assert b.returncode == 2 and j["word"] == "WAIT" and "already told" in j["notice"], j
    clear_state(sdir)
    set_mode(fake_dir, "go")
    g = subprocess.run(args, capture_output=True, text=True, env=env, timeout=60)
    assert g.returncode == 0 and "Codex: GO" in g.stdout and "TELL" not in g.stdout, g.stdout
    print("ok - --codex-verdict prints the word, exits 2 at WAIT and 0 at GO, tells once")


def case_limits(gate, sdir, root, fake_dir, fake):
    """ADDENDUM-0.76.1: one word per limit id; only the main bucket decides."""
    import codex_usage as c
    write_cfg(sdir, path=fake)
    args = [sys.executable, repo_path("hooks", "usage.py"), "--codex-verdict", "--dir", sdir]
    env = dict(os.environ, PYTHONUTF8="1")

    def run(mode, *extra):
        clear_state(sdir)
        set_mode(fake_dir, mode)
        return subprocess.run(args + list(extra), capture_output=True, text=True, env=env, timeout=60)

    # Regression: no map, and a map holding only codex, give the 0.76.0 line exactly.
    go = run("go").stdout.splitlines()[0]
    only = run("map_codex_only").stdout.splitlines()[0]
    assert go.startswith("Codex: GO (5h 12%, weekly 30%; codex: ") and go.endswith(") - use Codex."), go
    assert only == go, (only, go)
    # A second bucket at its limit is reported, never decides.
    two = run("map_two")
    assert two.returncode == 0, two.stdout
    line = two.stdout.splitlines()[0]
    assert line.startswith("Codex: GO (") and " - use Codex. | limit Images: WAIT until " in line, line
    assert "do not ask the owner" in line and "TELL" not in two.stdout, two.stdout
    j = json.loads(run("map_two", "--json").stdout)
    assert j["word"] == "GO" and j["exit"] == 0, j
    assert [(x["limit_id"], x["word"], x["main"]) for x in j["limits"]] == \
        [("codex", "GO", True), ("img", "WAIT", False)], j["limits"]
    assert j["limits"][1]["until_text"] and j["limits"][1]["label"] == "Images", j["limits"]
    # The gate allows a plain call while only the other bucket is at WAIT.
    run("map_two")
    assert decision(run_gate(gate, bash(root, "codex exec -"))) is None
    # Unnamed -> its id; malformed -> UNAVAILABLE; a label cannot forge a segment.
    odd = run("map_odd").stdout.splitlines()[0]
    assert "| limit img: WAIT until" in odd and "| limit broken: UNAVAILABLE - unknown" in odd, odd
    assert "| limit a b c: GO - usable" in odd and odd.count(" | ") == 3, odd
    assert odd.startswith("Codex: GO ("), odd
    # A map with no top-level rateLimits stays probe-failed, exactly as 0.76.0 (no fallback).
    mo = run("map_only")
    assert mo.returncode == 3 and "UNAVAILABLE probe-failed" in mo.stdout, mo.stdout
    clear_state(sdir)
    print("ok - limits: 0.76.0 line unchanged, other buckets reported not refused, JSON list, "
          "labels sanitised, no map fallback")


def case_image_limit(gate, sdir, root, fake_dir, fake):
    """0.76.3: the image limit is read from image_gen's 429 in Codex's rollouts."""
    import codex_usage as c
    home = os.path.join(fake_dir, "imghome")
    d = os.path.join(home, "sessions", "2026", "11", "11")
    os.makedirs(d, exist_ok=True)
    now = time.time()
    iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))
    reset = int(now + 3 * 3600)
    # Shapes copied from real rollouts (compact JSON, one record per line).
    dump = lambda o: json.dumps(o, separators=(",", ":"))
    out = lambda t, items: dump({"timestamp": iso(t), "type": "response_item", "payload": {
        "type": "function_call_output", "call_id": "c", "output": items}})
    refusal = out(now - 120, [{"type": "input_text", "text":
        "image generation failed: http 429 Too Many Requests: Some(%s)" % json.dumps(dump(
            {"error": {"type": "usage_limit_reached", "resets_at": reset}}))}])
    # image_gen's result: JSON text, so the image_url key arrives escaped.
    gen_out = out(now - 50, [{"type": "input_text",
                              "text": dump({"image_url": "data:image/png;base64,AAAA"})}])
    # view_image: an input_image item, key not escaped.
    view_out = out(now - 50, [{"type": "input_image", "image_url": "data:image/png;base64,AAAA"}])

    def write(*lines):
        with open(os.path.join(d, "rollout-x.jsonl"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return c.image_limit(now, home)

    got = write(refusal)
    assert got and got["word"] == "WAIT" and got["until"] == reset and not got["main"], got
    # view_image output carries image data too: it must not read as a produced image.
    assert write(refusal, view_out), "a view_image output cleared the image limit"
    # An image_gen result after the refusal means images work again; one before it does not.
    assert write(refusal, gen_out) is None, "an image produced after the refusal"
    assert write(gen_out.replace(iso(now - 50), iso(now - 300)), refusal), "an older image cleared it"
    # A past reset time is no limit.
    assert write(refusal.replace(str(reset), str(int(now - 60)))) is None
    assert write() is None
    # End to end: GO stays GO, the image limit is appended, the gate allows a plain call.
    write(refusal)
    keep = os.environ["CODEX_HOME"]
    os.environ["CODEX_HOME"] = home
    try:
        clear_state(sdir)
        set_mode(fake_dir, "go")
        write_cfg(sdir, path=fake)
        rec = c.verdict(sdir)
        line = c.text_of(rec)
        assert line.startswith("Codex: GO (") and " | limit image generation: WAIT until " in line, line
        assert c.EXIT[rec["word"]] == 0, rec
        assert decision(run_gate(gate, bash(root, "codex exec -"))) is None
    finally:
        os.environ["CODEX_HOME"] = keep
        clear_state(sdir)
    print("ok - image limit: read from image_gen's 429, cleared only by image_gen output, reported not refused")


def main():
    fresh_scratch()
    with scratch_dir("state") as sdir, scratch_dir("repo") as root, \
            scratch_dir("fake") as fake_dir, scratch_dir("ext") as ext:
        # The real ~/.codex logs must never reach a case: an empty Codex home by default.
        os.environ["CODEX_HOME"] = os.path.join(fake_dir, "emptyhome")
        fixture_repo(root)
        os.makedirs(os.path.join(root, ".claude"), exist_ok=True)
        gate = load_gate(sdir)
        stamp_session(gate, sdir, "s1")
        load_skills(gate, root, "s1", "dispatch-guard:cowork")
        fake = setup_fake(fake_dir)
        case_scanner()
        case_macos_inline_quoted()
        case_discovery(ext)
        case_verdicts(sdir, fake_dir, fake)
        case_hang(sdir, fake_dir, fake)
        case_session_log_note(sdir, fake_dir, fake)
        case_notice(sdir)
        case_gate(gate, sdir, root, fake_dir, fake)
        case_reset_credit(gate, sdir, root)
        case_end_to_end(sdir, root, fake_dir, fake)
        case_cli(sdir, fake_dir, fake)
        case_limits(gate, sdir, root, fake_dir, fake)
        case_image_limit(gate, sdir, root, fake_dir, fake)
    print("ok - codex usage: all cases passed")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
