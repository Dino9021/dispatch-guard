#!/usr/bin/env python3
"""Name a cowork session after its role (0.77.0, ADR Memory/tasks/20261111-213912-auto-role-identity rev 4).

The project opts in with two keys (`cowork_checkin_dir`, `cowork_name_format`). The role R is the stem
of the ONE check-in file that holds this session's id; its name is N = format(R). When the session's
current title differs from N, the hook returns N as `sessionTitle`:
- SessionStart, `source: resume` only (a startup title does not reach the peer name; a resume already
  restores the stored one, so this fires only when the stored title is not N);
- UserPromptSubmit (a fresh tab after its check-in is written, or a title changed by hand).
Attended sessions only. It never takes a name another live session holds (the runtime would make one
of the two yield and rename it). Read-only: it writes nothing but its own once-only state markers.
Remote Control's name is out of scope (hook titles do not reach an existing bridge).

0.79.0 (ADR Memory/tasks/20261112-144435-owner-name-restore): with NO setting, in every project, an
attended resume of a session that has a stored title N (the owner's name, or the 0.77.0 role name)
becomes `N_` at SessionStart and `N` again at its first prompt - a title the hook sets in this run, so
a Remote Control bridge opened after that prompt takes N too. State: `<sid>.name-restore` holds N.
"""

import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dispatch_gate as dg  # noqa: E402
import usage  # noqa: E402

NAME_OK = re.compile(r"^[A-Za-z0-9-]+$")      # 0.72.1: a name with spaces was dropped by the runtime
# 0.79.0: an owner's name may hold `_` (measured 2026-11-12: a hook title `Probe-Under_` was stored as
# customTitle and agentName). Spaces stay excluded (0.72.1); CJK and `.` are not restored.
RESTORE_OK = re.compile(r"^[A-Za-z0-9_-]+$")
TEMP = "_"                                     # the owner's choice: 「最後面加一個底線 _」
MAX_CHECKIN_BYTES = 256 * 1024


def find_role(checkin_dir, sid):
    """(role or "", [matching file names]). The role only when exactly one file holds the id."""
    hits = []
    for p in sorted(glob.glob(os.path.join(checkin_dir, "*.md"))):
        try:
            with open(p, "rb") as f:
                text = f.read(MAX_CHECKIN_BYTES).decode("utf-8", "replace")
        except OSError:
            continue
        if sid in text:
            hits.append(os.path.basename(p))
    if len(hits) == 1:
        return os.path.splitext(hits[0])[0], hits
    return "", hits


def _alive(pid):
    """Is this process running? Unknown counts as alive (the caller then refuses: fail closed)."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        # ⛔ NOT os.kill(pid, 0): on Windows any signal value other than CTRL events TERMINATES it.
        try:
            import ctypes
            k = ctypes.windll.kernel32
            h = k.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return False
            code = ctypes.c_ulong()
            ok = k.GetExitCodeProcess(h, ctypes.byref(code))
            k.CloseHandle(h)
            return (not ok) or code.value == 259         # STILL_ACTIVE
        except Exception:
            return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def name_holder(name, sid, config_dir=None):
    """Another live session holding `name`: its session id; "" if none; None if the registry is
    unreadable. The registry is `<config dir>/sessions/<pid>.json` (undocumented; see
    dispatch_gate.current_session_name)."""
    root = config_dir or os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    folder = os.path.join(root, "sessions")
    if not os.path.isdir(folder):
        return None
    for p in glob.glob(os.path.join(folder, "*.json")):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict) or d.get("sessionId") in (None, sid):
            continue
        if (d.get("name") or "").strip() == name and _alive(d.get("pid")):
            return d.get("sessionId")
    return ""


def decide(payload, root, cfg, attended=True, config_dir=None):
    """(title to set or None, context line or "", marker name for a once-only line or None)."""
    folder, fmt = (cfg.get("cowork_checkin_dir") or "").strip(), (cfg.get("cowork_name_format") or "").strip()
    sid = payload.get("session_id") or ""
    event = payload.get("hook_event_name")
    if not folder or not fmt or "{role}" not in fmt or not sid or not attended:
        return None, "", None
    start = event == "SessionStart"
    if start and payload.get("source") != "resume" and payload.get("source") != "startup":
        return None, "", None                       # compact / clear keep the name
    cdir = os.path.join(root, folder)
    role, hits = find_role(cdir, sid)
    if len(hits) > 1:
        return None, (" dispatch-guard: more than one cowork check-in in %s holds this session's id (%s), so "
                      "no role name was set. Settle with the owner which role this session holds."
                      % (folder, ", ".join(hits))), ("role-ambiguous" if not start else None)
    if not role:
        if not start:
            return None, "", None
        return None, (" dispatch-guard: no cowork check-in in %s holds this session's id `%s`. If the owner "
                      "has not told you your role, ask in one sentence; then write the check-in (with this "
                      "session id) as %s/<role>.md. This session is then named %s on the next prompt."
                      % (folder, sid, folder, fmt)), None
    name = fmt.replace("{role}", role)
    if not NAME_OK.match(role) or not NAME_OK.match(name):
        return None, (" dispatch-guard: the cowork role `%s` gives the name `%s`, which is not letters, digits "
                      "and hyphens only, so it was not set." % (role, name)), "role-badname"
    cur = (payload.get("session_title") or "").strip()
    if cur == name or (start and payload.get("source") == "startup"):
        line = (" dispatch-guard: this session holds cowork role %s (check-in %s/%s.md); its name is %s."
                % (role, folder, role, name)) if start else ""
        return None, line, None
    holder = name_holder(name, sid, config_dir)
    if holder is None:
        return None, (" dispatch-guard: cowork role %s, but the session registry could not be read, so the "
                      "name %s was not set (it must never take a name another live session holds)."
                      % (role, name)), "role-noregistry"
    if holder:
        return None, (" dispatch-guard: cowork role %s, but another live session (%s) already holds the name %s, "
                      "so it was not set. Tell the owner: two sessions claim one role." % (role, holder, name)), \
            "role-taken"
    return name, (" dispatch-guard: this session holds cowork role %s (check-in %s/%s.md); its name is set "
                  "to %s." % (role, folder, role, name)), None


def role_name(payload, root, cfg):
    """The 0.77.0 role name for this session, or "" when that path does not apply."""
    folder, fmt = (cfg.get("cowork_checkin_dir") or "").strip(), (cfg.get("cowork_name_format") or "").strip()
    sid = payload.get("session_id") or ""
    if not folder or not fmt or "{role}" not in fmt or not sid:
        return ""
    role, _hits = find_role(os.path.join(root, folder), sid)
    name = fmt.replace("{role}", role) if role else ""
    return name if role and NAME_OK.match(role) and NAME_OK.match(name) else ""


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def restore_start(payload, prev, role=""):
    """SessionStart of an attended resume: (temporary title or None, name to remember or "").

    ⭐ 0.79.0 (ADR Memory/tasks/20261112-144435-owner-name-restore), owner 2026-11-12: 「只要擁有者命名了就要
    成功」, for every project, no setting. A resume RESTORES the stored title, and a restored title never
    reaches a Remote Control bridge opened later - only a title a hook sets in this run does (FINDINGS
    2026-11-11). A hook title equal to the current one is a no-op, and two SessionStart titles in one
    event do not both apply (measured), so: `N_` now, `N` at the first prompt (restore_prompt).
    `prev` is the name this session remembered last run: a stored `N_` is stripped back to `N` only then,
    so an owner's own name ending in `_` is kept as it is.
    """
    stored = (payload.get("session_title") or "").strip()
    name = role or stored
    if not role and prev and stored == prev + TEMP:
        name = prev
    if not name or not RESTORE_OK.match(name):
        return None, ""
    return name + TEMP, name


def restore_prompt(payload, name, sid, config_dir=None):
    """UserPromptSubmit while a restore is pending: (title or None, line, once-marker or None)."""
    cur = (payload.get("session_title") or "").strip()
    if cur != name + TEMP:
        return None, "", None                    # the owner renamed it meanwhile: theirs wins
    holder = name_holder(name, sid, config_dir)
    if holder is None:
        return None, (" dispatch-guard: the session registry could not be read, so this session's name "
                      "was not set back to %s (it must never take a name another live session holds). "
                      "It is reachable as %s meanwhile." % (name, name)), "restore-noregistry"
    if holder:
        return None, (" dispatch-guard: another live session (%s) already holds the name %s, so this "
                      "session keeps %s%s. Tell the owner: two sessions have one name."
                      % (holder, name, name, TEMP)), "restore-taken"
    return name, "", None


def main():
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception:
        return
    event = payload.get("hook_event_name")
    if event not in ("SessionStart", "UserPromptSubmit"):
        return
    root = dg.repo_root(payload.get("cwd"))
    sdir = usage.state_dir([])
    cfg = dg.gate_config(root, sdir)
    sid = payload.get("session_id") or ""
    pending = dg.state_path(sdir, sid, "name-restore") if sid else ""
    restoring = (sid and dg.attended() and not payload.get("agent_id")
                 and event == "SessionStart" and payload.get("source") == "resume")
    title, line, once = None, "", None
    if restoring:
        title, name = restore_start(payload, _read(pending), role_name(payload, root, cfg))
        if title:
            try:
                os.makedirs(os.path.dirname(pending), exist_ok=True)
                with open(pending, "w", encoding="utf-8") as f:
                    f.write(name)
            except OSError:
                title = None                     # no memory of N: never leave the session on N_
        if not title:
            title, line, once = decide(payload, root, cfg, attended=dg.attended())
    elif event == "UserPromptSubmit" and pending and os.path.exists(pending):
        name = _read(pending)
        try:
            os.remove(pending)
        except OSError:
            pass
        if name:
            title, line, once = restore_prompt(payload, name, sid)
    else:
        title, line, once = decide(payload, root, cfg, attended=dg.attended())
    if once:
        mark = dg.state_path(sdir, payload.get("session_id"), once)
        if os.path.exists(mark):
            line = ""
        else:
            try:
                os.makedirs(os.path.dirname(mark), exist_ok=True)
                open(mark, "w").close()
            except OSError:
                pass
    if not title and not line:
        return
    out = {"hookEventName": event}
    if title:
        out["sessionTitle"] = title
        dg.log(root, "ROLE-TITLE %s" % title)
    if line:
        out["additionalContext"] = line
    print(json.dumps({"hookSpecificOutput": out}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass                                        # a naming helper must never block a session
    sys.exit(0)
