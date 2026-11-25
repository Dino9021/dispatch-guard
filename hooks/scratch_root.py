#!/usr/bin/env python3
"""Where a task's scratch lives: the machine's throwaway disk, or the repository (0.83.0).

The owner keeps caches on a non-system disk and wants task scratch there too (2026-11-25). The location is
`scratch_root` in the PER-MACHINE `<state dir>/config.json` only - a repository's own config is never read for
it, so nothing committed can redirect a machine. ADR Memory/tasks/20261125-203407-scratch-root-on-cache-disk.

    resolve(sdir, repo) -> {"mode": "repo" | "external" | "stop", "base", "root", "fallback", "reason"}

  repo      scratch_root unset, or set but its directory does not exist at all (volume not mounted - the
            owner's "fall back", with a note). Scratch is `<task_root>/<task>/scratch/`.
  external  `<root>/<repo-key>/<task>/scratch/<NN>/`. `base` is `<root>/<repo-key>`.
  stop      every other problem; the gate refuses dispatches until the owner fixes it (owner: 「在發現問題時
            在可以停下來的時候就停下來並提示要求處理」). `reason` says what and how.

⛔ The root and its marker are NEVER created here - the owner makes both once. The marker is what tells the
real volume from the empty mount-point directory left on the system disk when the volume is unmounted: a
root that exists without it is exactly the state where agents' writes have landed on the system disk.
⭐ `<repo-key>/` and its `.repo` ownership file ARE created here, under a valid root only, with an exclusive
create, so two checkouts can never both claim one key.
"""

import hashlib
import json
import os
import re
import stat
import sys

MARKER = ".dispatch-guard-scratch-root"
OWNER_FILE = ".repo"
_ANCHOR_NAMES = ("scratch", "scratchpad")
_REPARSE_POINT = 0x400


def state_dir():
    return os.environ.get("CLAUDE_DISPATCH_DIR") or os.path.join(os.path.expanduser("~"), ".claude",
                                                                 "dispatch-guard")


def configured(sdir):
    """The raw `scratch_root` from the machine config (top level, else its `dispatch` section), or None."""
    try:
        with open(os.path.join(sdir, "config.json"), encoding="utf-8") as fh:
            disk = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(disk, dict):
        return None
    if "scratch_root" in disk:
        return disk["scratch_root"]
    section = disk.get("dispatch")
    return section.get("scratch_root") if isinstance(section, dict) else None


def qualified(path, windows=None):
    """Fully qualified: POSIX `/...`; Windows a drive letter AND a root separator (`D:\\...`). Drive-relative
    `D:x`, current-drive `\\x` and UNC `\\\\server\\...` are not."""
    windows = (os.name == "nt") if windows is None else windows
    if windows:
        return bool(re.match(r"^[A-Za-z]:[\\/]", path))
    return path.startswith("/")


def is_link(path):
    st = os.lstat(path)
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & _REPARSE_POINT)


def repo_key(repo):
    real = os.path.realpath(repo)
    name = os.path.basename(real.rstrip("\\/")) or "repo"
    return "%s-%s" % (name, hashlib.sha256(os.path.normcase(real).encode("utf-8")).hexdigest()[:16])


def expanded(raw):
    return os.path.expanduser(raw) if isinstance(raw, str) else None


def check_root(raw, repo):
    """(realpath of a usable root or None, mode, reason) - before any key is claimed. `repo` None skips the
    inside-the-repository check (the cleaner has no repository)."""
    if raw is None:
        return None, "repo", ""
    fix = " Fix `scratch_root` in %s, or remove it to keep scratch in the repository." % os.path.join(
        state_dir(), "config.json")
    if not isinstance(raw, str) or not raw.strip():
        return None, "stop", "scratch_root %r is not a path string.%s" % (raw, fix)
    path = expanded(raw)
    if not qualified(path):
        return None, "stop", ("scratch_root %r is not a fully qualified path (Windows: a drive letter and a "
                              "backslash, D:\\...; UNC paths are not supported).%s" % (raw, fix))
    names = [n.lower() for n in re.split(r"[\\/]+", os.path.splitdrive(path)[1]) if n]
    if any(n in _ANCHOR_NAMES for n in names):
        return None, "stop", ("scratch_root %s has a folder named scratch or scratchpad, which would let the "
                              "cleaner delete a whole task's scratch at once.%s" % (path, fix))
    if not os.path.lexists(path):
        return None, "repo", ("scratch_root %s does not exist (disk not mounted?) - scratch falls back to the "
                              "repository's <task>/scratch/, still never committed." % path)
    try:
        if is_link(path):
            return None, "stop", "scratch_root %s is itself a link or junction.%s" % (path, fix)
    except OSError as exc:
        return None, "stop", "scratch_root %s could not be checked (%s).%s" % (path, exc.__class__.__name__, fix)
    real = os.path.realpath(path)
    if not os.path.isdir(real):
        return None, "stop", "scratch_root %s exists but is not a folder.%s" % (path, fix)
    if not os.path.isfile(os.path.join(real, MARKER)):
        return None, "stop", ("scratch_root %s exists but has no %s marker. Either the cache disk is NOT "
                              "MOUNTED and files were written onto the system disk at this path - move them "
                              "away, mount the disk, then retry - or the folder was never set up: create the "
                              "empty file %s in it." % (path, MARKER, os.path.join(path, MARKER)))
    if repo is None:
        return real, "external", ""
    repo_real = os.path.realpath(repo)
    try:
        inside = os.path.commonpath([os.path.normcase(real), os.path.normcase(repo_real)]) == \
            os.path.normcase(repo_real)
    except ValueError:                                   # different drives on Windows
        inside = False
    if inside:
        return None, "stop", "scratch_root %s is inside the repository %s.%s" % (path, repo_real, fix)
    return real, "external", ""


def resolve(sdir, repo):
    raw = configured(sdir)
    real, mode, reason = check_root(raw, repo)
    out = {"mode": mode, "root": real, "base": None, "reason": reason,
           "configured": expanded(raw) if isinstance(raw, str) else None}
    if mode != "external":
        return out
    base = os.path.join(real, repo_key(repo))
    want = os.path.realpath(repo)
    try:
        os.makedirs(base, exist_ok=True)
        if is_link(base):
            raise OSError("key folder is a link")
        owner = os.path.join(base, OWNER_FILE)
        try:
            fd = os.open(owner, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(want)
        except FileExistsError:
            pass
        with open(owner, encoding="utf-8") as fh:
            got = fh.read().strip()
        if os.path.normcase(got) != os.path.normcase(want):
            out.update(mode="stop", reason="scratch folder %s belongs to %s, not to %s. Move or delete that "
                       "folder, then retry." % (base, got, want))
            return out
    except OSError as exc:
        out.update(mode="stop", reason="scratch folder %s could not be prepared (%s). Check the disk, then "
                   "retry." % (base, exc.__class__.__name__))
        return out
    out["base"] = base
    return out


def where(res, task_root):
    """The scratch folder (ending in a separator) that `<NN>/` is appended to in rule 8 and the SessionStart note."""
    if res["mode"] == "external":
        return os.path.join(res["base"], "<task>", "scratch", "")
    return "%s/<task>/scratch/" % task_root


def where_note(res, task_root):
    """What follows that path: in external mode, the fallback and the never-create rule (ADR D4); else ""."""
    if res["mode"] != "external":
        return ""
    return (" (on this machine's cache disk; if %s is missing, use %s/<task>/scratch/ in the repository instead "
            "and NEVER create %s or anything above it)" % (res["base"], task_root, res["base"]))


def suggest(repo, windows=None):
    """A scratch_root to suggest for this machine, or None when no non-system disk is evident.

    Windows: the repository's drive when it is not the system drive (`D:\\Cache\\dg-scratch` - below the drive root,
    because the harness refuses to delete a drive root's children). POSIX: the first of ~/.cache, $XDG_CACHE_HOME,
    the parent of $TMPDIR / $CLAUDE_CODE_TMPDIR that sits on a different device from `/` - on the owner's Mac that is
    ~/.cache, the mount point of the cache volume.
    """
    windows = (os.name == "nt") if windows is None else windows
    if windows:
        system = (os.environ.get("SystemDrive") or "C:").upper()
        import ntpath                                    # Windows rules even when tested elsewhere
        drive = ntpath.splitdrive(os.path.realpath(repo))[0].upper()
        return drive + "\\Cache\\dg-scratch" if re.match(r"^[A-Z]:$", drive) and drive != system else None
    try:
        system_dev = os.stat("/").st_dev
    except OSError:
        return None
    candidates = [os.path.join(os.path.expanduser("~"), ".cache"), os.environ.get("XDG_CACHE_HOME")]
    candidates += [os.path.dirname(os.environ.get(v, "").rstrip("/")) for v in ("TMPDIR", "CLAUDE_CODE_TMPDIR")]
    for base in candidates:
        try:
            if base and os.path.isdir(base) and os.stat(base).st_dev != system_dev:
                return os.path.join(base, "dg-scratch")
        except OSError:
            continue
    return None


def advice(repo, suggestion=None):
    """What to tell the owner when scratch_root is unset (owner 2026-11-25: say why, and suggest a path)."""
    path = suggestion or suggest(repo)
    cfg = os.path.join(state_dir(), "config.json")
    where = ("Suggested for this machine: %s." % path) if path else \
        "Pick a folder on a disk that is not the system disk, below that disk's root."
    example = path or "<that folder>"
    return ("scratch_root is not set, so sub-task scratch (build copies, captures, downloads) is written inside "
            "the repository, on the repository's disk. Setting it moves that throwaway output to a disk meant for "
            "it: git and VS Code stop watching it (tens of thousands of scratch files once kept a Mac's CPU near "
            "full for two days) and the system disk does not fill. %s To set it: create the folder, put an empty "
            "file named %s in it, and add \"scratch_root\": %s to %s. Nothing else changes until you do." %
            (where, MARKER, json.dumps(example), cfg))


def under_configured(path, sdir=None):
    """(configured root, parts below it) when `path` lies under the configured scratch_root - valid or not -
    else None. Compared on the literal expanded value AND its realpath, case-folded where the OS folds."""
    raw = configured(sdir or state_dir())
    root = expanded(raw)
    if not root or not qualified(root):
        return None
    norm = os.path.normcase(os.path.abspath(path))
    for cand in {os.path.abspath(root), os.path.realpath(root)}:
        c = os.path.normcase(cand).rstrip("\\/")
        if norm == c or norm.startswith(c + os.sep):
            rest = os.path.abspath(path)[len(c):].lstrip("\\/")
            return cand, [p for p in re.split(r"[\\/]+", rest) if p]
    return None


def _selftest():
    import tempfile
    assert qualified("D:\\Cache\\x", True) and qualified("d:/Cache", True)
    for bad in ("D:Cache", "\\Cache", "\\\\server\\share", "Cache", ""):
        assert not qualified(bad, True), bad
    assert qualified("/Users/x", False) and not qualified("~/x", False) and not qualified("x", False)
    tmp = os.path.realpath(tempfile.mkdtemp())
    saved = os.environ.get("CLAUDE_DISPATCH_DIR")
    os.environ["CLAUDE_DISPATCH_DIR"] = sdir = os.path.join(tmp, "state")
    os.makedirs(sdir)
    repo = os.path.join(tmp, "WorkSpace", "proj")
    os.makedirs(repo)

    def setcfg(value, nested=False):
        with open(os.path.join(sdir, "config.json"), "w", encoding="utf-8") as fh:
            json.dump({"dispatch": {"scratch_root": value}} if nested else {"scratch_root": value}, fh)

    try:
        assert resolve(sdir, repo)["mode"] == "repo"                       # no config file at all
        root = os.path.join(tmp, "cache", "dg-scratch")
        setcfg(root)
        r = resolve(sdir, repo)
        assert r["mode"] == "repo" and "does not exist" in r["reason"], r  # unmounted: fall back
        os.makedirs(root)
        r = resolve(sdir, repo)
        assert r["mode"] == "stop" and MARKER in r["reason"], r            # stray writes / never set up: STOP
        open(os.path.join(root, MARKER), "w").close()
        r = resolve(sdir, repo)
        assert r["mode"] == "external", r
        key = repo_key(repo)
        assert r["base"] == os.path.join(root, key) and re.match(r"^proj-[0-9a-f]{16}$", key), r
        assert open(os.path.join(r["base"], OWNER_FILE)).read() == os.path.realpath(repo)
        assert where(r, "M").endswith(os.path.join("scratch", "")) and "NEVER create" in where_note(r, "M")
        assert where({"mode": "repo"}, "M") == "M/<task>/scratch/" and where_note({"mode": "repo"}, "M") == ""
        setcfg(root, nested=True)
        assert resolve(sdir, repo)["mode"] == "external"                   # the dispatch section works too
        # a second checkout with the same folder name gets its own key
        other = os.path.join(tmp, "E", "proj")
        os.makedirs(other)
        assert repo_key(other) != key and resolve(sdir, other)["mode"] == "external"
        # a key owned by another path stops
        with open(os.path.join(root, key, OWNER_FILE), "w") as fh:
            fh.write("/somewhere/else")
        r = resolve(sdir, repo)
        assert r["mode"] == "stop" and "belongs to" in r["reason"], r
        # unqualified, scratch component, not a string, inside the repo, a link: STOP
        for bad, word in (("rel/dir", "fully qualified"), (os.path.join(tmp, "Scratch", "x"), "scratch"),
                          (5, "not a path"), (os.path.join(repo, "sub"), "inside the repository")):
            if bad == os.path.join(repo, "sub"):
                os.makedirs(bad, exist_ok=True)
                open(os.path.join(bad, MARKER), "w").close()
            setcfg(bad)
            r = resolve(sdir, repo)
            assert r["mode"] == "stop" and word in r["reason"], (bad, r)
        if hasattr(os, "symlink"):
            link = os.path.join(tmp, "cache", "link-root")
            os.symlink(root, link)
            setcfg(link)
            r = resolve(sdir, repo)
            assert r["mode"] == "stop" and "link" in r["reason"], r
        setcfg(root)
        u = under_configured(os.path.join(root, "k", "t", "scratch", "01", "x"), sdir)
        assert u and u[1] == ["k", "t", "scratch", "01", "x"], u
        assert under_configured(os.path.join(tmp, "elsewhere", "x"), sdir) is None
        # suggestions: Windows uses the repo's drive unless it is the system drive
        saved_sd = os.environ.get("SystemDrive")
        os.environ["SystemDrive"] = "C:"
        try:
            real_rp = os.path.realpath
            os.path.realpath = lambda p: "D:\\WorkSpace\\proj"
            assert suggest("x", windows=True) == "D:\\Cache\\dg-scratch"
            os.path.realpath = lambda p: "C:\\Users\\u\\proj"
            assert suggest("x", windows=True) is None
        finally:
            os.path.realpath = real_rp
            if saved_sd is None:
                os.environ.pop("SystemDrive", None)
            else:
                os.environ["SystemDrive"] = saved_sd
        a = advice(repo, suggestion="/Volumes/cache/dg-scratch")
        assert "/Volumes/cache/dg-scratch" in a and MARKER in a and "config.json" in a and "system disk" in a, a
        assert "Pick a folder" in advice(repo, suggestion=None) or "Suggested" in advice(repo, suggestion=None)
    finally:
        if saved is None:
            os.environ.pop("CLAUDE_DISPATCH_DIR", None)
        else:
            os.environ["CLAUDE_DISPATCH_DIR"] = saved
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    print("scratch_root selftest OK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(_selftest())
    res = resolve(state_dir(), os.getcwd())
    print(json.dumps(res, ensure_ascii=False, indent=1))
