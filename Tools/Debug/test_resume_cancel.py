#!/usr/bin/env python3
"""do_cancel has three outcomes and used to have two. This pins all three.

⛔ WHY IT NEEDS A CHECK AT ALL. `schtasks /Delete` exits non-zero when it REFUSES and
equally when the task IS NOT THERE, and the correct handling is opposite in the two cases:
a job that is still registered must keep its record, a job that never existed must lose it.
Both wrong answers are silent, and both end with the gate telling the user something untrue
about whether work will be redone later.

⚠ The scheduler is never actually called: `subprocess.run` is replaced for the length of
each case. A test that registered real OS tasks would leave them behind.

    python Tools/Debug/test_resume_cancel.py

Standard library only, no framework, like everything else here.
"""

import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import fresh_scratch, repo_path, scratch_dir   # noqa: E402

HERE = repo_path()            # ⭐ the repository under test, not this folder


class Result(object):
    def __init__(self, code):
        self.returncode = code


def load_resume():
    sys.path.insert(0, repo_path("hooks"))
    spec = importlib.util.spec_from_file_location("dg_resume", repo_path("hooks", "resume.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def case(mod, name, codes, record=True):
    """Run do_cancel with schtasks answering `codes`. Returns (rc, record_still_there)."""
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        # /Query first, /Delete second - keyed by the flag so order cannot be assumed wrong
        return Result(codes["query"] if "/Query" in cmd else codes["delete"])

    with scratch_dir("cancel-" + name.replace(" ", "-").replace(",", "")) as sdir:
        if record:
            with open(os.path.join(sdir, "resume.json"), "w") as f:
                json.dump({"task": "x"}, f)
        saved, mod.subprocess.run = mod.subprocess.run, fake_run
        # ⛔ log_line() APPENDS TO `<cwd>/.claude/dispatch_gate.log`, so running this test
        # from the repository left RESUME lines - and a `.claude/` directory - in the working
        # tree on every run. It looked exactly like the plugin executing from the development
        # path, which is the one thing a person checking their install must be able to rule
        # out. ⇒ The whole case runs with the cwd inside its own temp directory.
        here = os.getcwd()
        os.chdir(sdir)
        try:
            rc = mod.do_cancel(sdir, quiet=True)
        finally:
            os.chdir(here)
            mod.subprocess.run = saved
        left = os.path.exists(os.path.join(sdir, "resume.json"))
    print("  %-28s rc=%d record_kept=%s" % (name, rc, left))
    return rc, left


def _tree_log():
    """The size of the repository's gate log, or None when it is absent.

    ⛔ THE QUESTION IS "DID I WRITE IT?", NOT "DOES IT EXIST?" - and the first version of this
    check asked the wrong one. `.claude/dispatch_gate.log` is where the plugin legitimately
    logs when a real session works in this repository, so asserting it is absent fails for a
    reason that has nothing to do with the test. Comparing before and after is the only form
    of the question that answers itself.
    """
    p = os.path.join(HERE, ".claude", "dispatch_gate.log")
    return os.path.getsize(p) if os.path.exists(p) else None


def main():
    fresh_scratch()
    before = _tree_log()
    mod = load_resume()
    if os.name != "nt":
        print("skipped - the three-way split is the Windows path; POSIX cannot ask `at`")
        return

    # Nothing registered. The record is an ORPHAN and this is the documented repair for it,
    # so it must be cleared and the caller must hear "nothing left to fire".
    rc, left = case(mod, "not registered", {"query": 1, "delete": 1})
    assert rc == 0 and not left, "an orphan record survived the command named to clear it"

    # Registered and deleted. The ordinary path.
    rc, left = case(mod, "registered, deleted", {"query": 0, "delete": 0})
    assert rc == 0 and not left, "a successful cancel left its record behind"

    # ⛔ Registered and REFUSED. The job will still fire, so the record must stay and the
    # caller must NOT be told that nothing will wake later.
    rc, left = case(mod, "registered, delete refused", {"query": 0, "delete": 1})
    assert rc == 1 and left, "a refused delete was reported as a cancellation"

    # ⛔ AND IT MUST LEAVE THE WORKING TREE ALONE. `log_line()` appends to
    # `<cwd>/.claude/dispatch_gate.log`, and this test used to run with the repository as its
    # working directory - so every run left the plugin's own log there, which is
    # indistinguishable from the development copy being executed by a real session.
    assert _tree_log() == before, (
        "the test changed %s/.claude/dispatch_gate.log (%r -> %r)"
        % (HERE, before, _tree_log()))
    print("ok - not-there, deleted and refused are three different answers")


if __name__ == "__main__":
    main()
