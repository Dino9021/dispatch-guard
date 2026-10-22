#!/usr/bin/env python3
"""hooks/scratch_clean.py (0.75.12) - the one way an agent deletes scratch.

    python Tools/Debug/test_scratch_clean.py

⛔ A DELETE TOOL IS TESTED FOR WHAT IT MUST NOT DELETE FIRST. Every refusal case runs with --dry-run, so a broken
check prints WOULD-DELETE and fails the case instead of deleting anything. The positive cases delete fixtures under
Tools/Debug/scratch only. ADR: Memory/tasks/20261022-212421-scratch-clean-script (review B1: a `..` path and a
junction between two scratch folders; N1 depth; N2/N4 git asked from the outer scratch, case-insensitively; N9 a
read-only hard link; F4 a junction is not islink).

⚠ Every fixture lives below Tools/Debug/scratch, which is itself a folder named `scratch` - so the OUTERMOST anchor
for all of them is that folder, and its repository (this one, where it is ignored) is the one git is asked. The
git-tracked refusal is therefore driven in-process with the anchor pointed at a fixture repository.
"""

import os
import stat
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import fresh_scratch, repo_path, scratch_dir  # noqa: E402

SCRIPT = repo_path("hooks", "scratch_clean.py")
WIN = os.name == "nt"


def run(*args):
    r = subprocess.run([sys.executable, SCRIPT] + list(args), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=repo_path(), env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    lines = r.stdout.strip().splitlines()
    assert lines and lines[-1].startswith("scratch_clean: "), "no last line - it did not run:\n%s%s" % (r.stdout, r.stderr)
    return r.returncode, r.stdout


def put(path, text="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def link_dir(link, target):
    """A junction on Windows (what bit the Game project), a symlink elsewhere."""
    if WIN:
        subprocess.run(["cmd", "/c", "mklink", "/J", link, target], check=True, capture_output=True)
    else:
        os.symlink(target, link)


def git(d, *args):
    subprocess.run(["git", "-C", d, "-c", "user.name=dg", "-c", "user.email=dg@example.invalid",
                    "-c", "commit.gpgsign=false"] + list(args), check=True, capture_output=True)


def main():
    fresh_scratch()
    with scratch_dir("cases") as f:
        # 1. a whole copy, hidden files and subfolders included
        for p in ("copy/a.txt", "copy/.hidden", "copy/deep/b.txt"):
            put(os.path.join(f, p))
        rc, out = run(os.path.join(f, "copy"))
        assert rc == 0 and not os.path.exists(os.path.join(f, "copy")), out
        assert "DELETED " + os.path.join(f, "copy") in out and "scratch_clean: 1 deleted" in out, out

        # 2. --build removes only the rule-8 build folders; evidence stays
        for p in ("sub/node_modules/x.js", "sub/build/out.o", "sub/nested/dist/y.js", "sub/report.md",
                  "sub/logs/run.log"):
            put(os.path.join(f, p))
        rc, out = run("--build", os.path.join(f, "sub"))
        assert rc == 0, out
        for gone in ("node_modules", "build", "nested/dist"):
            assert not os.path.exists(os.path.join(f, "sub", gone)), (gone, out)
        for kept in ("report.md", "logs/run.log", "nested"):
            assert os.path.exists(os.path.join(f, "sub", kept)), (kept, out)
        assert "scratch_clean: 3 deleted" in out, out

        # 3. refusals - all --dry-run, so a broken check fails the case instead of deleting
        put(os.path.join(f, "keep/sentinel.txt"))
        outside = repo_path("no-such-dir-for-scratch-clean")          # no scratch component at all
        rc, out = run("--dry-run", outside)
        assert rc == 1 and "REFUSED" in out and "not below a folder named scratch" in out, out
        anchor_child = os.path.dirname(f)                             # Tools/Debug/scratch/test_scratch_clean: depth 1
        rc, out = run("--dry-run", anchor_child)
        assert rc == 1 and "only 1 level(s) below `scratch`" in out, out
        rc, out = run("--dry-run", os.path.join(f, "keep", "..", "keep"))
        assert rc == 1 and "`..` component" in out, out
        # a junction between two scratch folders (review B1): the link check starts at the OUTERMOST one
        put(os.path.join(f, "realrepo/Memory/tasks/U/scratch/02/evidence/e.txt"))
        link_dir(os.path.join(f, "proj"), os.path.join(f, "realrepo"))
        victim = os.path.join(f, "proj", "Memory", "tasks", "U", "scratch", "02", "evidence")
        rc, out = run("--dry-run", victim)
        assert rc == 1 and "is a link or junction" in out, out
        assert os.path.exists(os.path.join(f, "realrepo/Memory/tasks/U/scratch/02/evidence/e.txt"))

        # 4. a link INSIDE a deleted tree is removed as a link; its target survives
        put(os.path.join(f, "target/sentinel.txt"))
        put(os.path.join(f, "tree/file.txt"))
        link_dir(os.path.join(f, "tree", "link"), os.path.join(f, "target"))
        rc, out = run(os.path.join(f, "tree"))
        assert rc == 0 and not os.path.lexists(os.path.join(f, "tree")), out
        assert os.path.exists(os.path.join(f, "target/sentinel.txt")), "the delete followed the link"
        assert "links-removed=1" in out, out

        # 5. the path ITSELF a link: the link goes, the target stays
        put(os.path.join(f, "target2/sentinel.txt"))
        link_dir(os.path.join(f, "linkpath"), os.path.join(f, "target2"))
        rc, out = run(os.path.join(f, "linkpath"))
        assert rc == 0 and not os.path.lexists(os.path.join(f, "linkpath")), out
        assert os.path.exists(os.path.join(f, "target2/sentinel.txt")), "the delete followed the link"

        # 6. a project copy with its own .git (read-only objects on Windows) is deletable (review N2)
        put(os.path.join(f, "gitcopy/src.txt"))
        git(os.path.join(f, "gitcopy"), "init", "-q")
        git(os.path.join(f, "gitcopy"), "add", "src.txt")
        git(os.path.join(f, "gitcopy"), "commit", "-q", "-m", "x")
        rc, out = run(os.path.join(f, "gitcopy"))
        assert rc == 0 and not os.path.exists(os.path.join(f, "gitcopy")), out

        # 6b. VERY deep trees (owner, 2026-10-22: "scratch 有時候會有非常多層"): past Python's ~1000 recursion limit
        # and past 260 characters, both for a whole path and for --build finding a build folder at the bottom.
        # Windows only for the >1000 case - macOS refuses an absolute path past PATH_MAX (1024).
        levels = 1100 if WIN else 300
        top_deep = os.path.join(f, "deep")
        lp = ("\\\\?\\" + top_deep) if WIN else top_deep
        os.mkdir(lp)
        for _ in range(levels):                       # one level at a time: os.makedirs itself recurses
            lp = os.path.join(lp, "d")
            os.mkdir(lp)
        for d in ("node_modules", os.path.join("node_modules", "pkg")):
            os.mkdir(os.path.join(lp, d))
        for name in (os.path.join("node_modules", "pkg", "m.js"), "keep.txt"):
            with open(os.path.join(lp, name), "w") as fh:
                fh.write("x")
        try:
            rc, out = run("--build", top_deep)
            assert rc == 0 and "scratch_clean: 1 deleted" in out, out[-400:]
            assert not os.path.exists(os.path.join(lp, "node_modules")) and os.path.exists(os.path.join(lp, "keep.txt"))
            rc, out = run(top_deep)
            assert rc == 0 and not os.path.exists(top_deep), out[-400:]
        finally:
            if os.path.lexists(top_deep):             # never leave a tree the next run's cleanup cannot recurse into
                sys.path.insert(0, repo_path("hooks"))
                import scratch_clean as _sc
                _sc.delete(_sc._long(top_deep), False, {"bytes": 0, "files": 0, "links": 0, "kept": 0, "notes": []})

        # 7. --dry-run changes nothing; 8. ABSENT is not a failure
        put(os.path.join(f, "dry/x.txt"))
        rc, out = run("--dry-run", os.path.join(f, "dry"))
        assert rc == 0 and os.path.exists(os.path.join(f, "dry/x.txt")) and "WOULD-DELETE" in out, out
        assert "scratch_clean: 1 would be deleted" in out, out
        rc, out = run(os.path.join(f, "never-there"))
        assert rc == 0 and "ABSENT" in out, out

        # 9. a read-only hard link: the original's read-only bit must not be cleared through it (review N9)
        orig = os.path.join(f, "hlsrc", "orig.txt")
        put(orig)
        os.makedirs(os.path.join(f, "hl"))
        os.link(orig, os.path.join(f, "hl", "link.txt"))
        os.chmod(orig, stat.S_IREAD)
        rc, out = run(os.path.join(f, "hl"))
        assert not os.access(orig, os.W_OK), "the original lost its read-only bit through the hard link"
        if WIN:
            assert rc == 1 and "read-only hard-linked file left" in out, out
        os.chmod(orig, stat.S_IWRITE | stat.S_IREAD)

    # 10. git-tracked: refused, case-insensitively, asked from the anchor (in-process, see the docstring)
    sys.path.insert(0, repo_path("hooks"))
    import scratch_clean as sc
    with scratch_dir("git") as g:
        repo = os.path.join(g, "repo")
        put(os.path.join(repo, "scratch", "sub", "x", "f.txt"))
        git(repo, "init", "-q")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "x")
        top = os.path.join(repo, "scratch")
        assert sc._tracked(top, os.path.join("sub", "x")) == 1
        assert sc._tracked(top, os.path.join("SUB", "X")) == 1, "a path in another case slipped past (review N4)"
        assert sc._tracked(top, os.path.join("sub", "y")) == 0
        real_anchor = sc.anchor
        sc.anchor = lambda path, depth_needed=True: (top, os.path.relpath(path, top).split(os.sep))
        try:
            try:
                sc.check(os.path.join(top, "sub", "x"))
                raise AssertionError("a git-tracked path was not refused")
            except sc.Refused as why:
                assert "git tracks 1 file(s)" in str(why), why
        finally:
            sc.anchor = real_anchor
        # fail closed: a git that cannot answer refuses
        real_run = sc.subprocess.run
        sc.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("git"))
        try:
            try:
                sc.check(os.path.join(top, "sub", "x"))         # exists: an absent path never asks git
                raise AssertionError("a check that could not be answered did not refuse")
            except sc.Refused as why:
                assert "could not be answered" in str(why), why
        finally:
            sc.subprocess.run = real_run

    print("ok - scratch_clean deletes copies and build output only below scratch, never through a link, refuses "
          "`..`, depth, git-tracked and unanswerable checks, keeps a read-only hard link's original")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
