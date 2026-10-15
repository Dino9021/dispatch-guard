#!/usr/bin/env python3
"""The macOS resume alarm on launchd (0.75), checked against a FAKE launchctl.

    python Tools/Debug/test_resume_launchd.py     (or Tools/Debug/test_all.py for all of them)

⛔ WHY. On macOS `at` never runs (com.apple.atrun is not loaded), so every macOS alarm was dead
until 0.75 moved it to launchd. ADR: Memory/tasks/20261014-225156-mac-resume-and-tests/ADR.md.
Two launchd facts drive most of what is pinned here, both measured on the owner's Mac:
  - a job booted out while it RUNS is killed on the spot, its own process included;
  - launchd refuses a label already loaded, with the same rc as a missing file.

⚠ NOTHING HERE TOUCHES THE REAL launchd. resume._launchctl is replaced by FakeLaunchd for every
case, and the scheduler is pinned with scheduler_kind(), so this runs the same on Windows.
"""

import contextlib
import importlib.util
import io
import json
import os
import plistlib
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import fresh_scratch, repo_path, scratch_dir   # noqa: E402

SID = "aaaa1111-2222-3333-4444-555566667777"
OTHER = "bbbb1111-2222-3333-4444-555566667777"


class Result(object):
    def __init__(self, code, out=b"", err=b""):
        self.returncode, self.stdout, self.stderr = code, out, err


class FakeLaunchd(object):
    """A gui domain in memory: {label: pid column}. Records every call it gets."""

    def __init__(self):
        self.jobs, self.calls, self.prints = {}, [], {}
        self.bootstrap_rc, self.bootout_rc, self.on_bootstrap = 0, None, None

    def __call__(self, args):
        args = list(args)
        self.calls.append(args)
        verb = args[0]
        if verb == "list":
            rows = "".join("%s\t0\t%s\n" % (pid, label) for label, pid in self.jobs.items())
            return 0, "PID\tStatus\tLabel\n" + rows, ""
        if verb == "bootstrap":
            with open(args[2], "rb") as f:
                label = plistlib.load(f)["Label"]
            if self.on_bootstrap:
                self.on_bootstrap(label, args[2])
            if self.bootstrap_rc or label in self.jobs:
                return self.bootstrap_rc or 5, "", "Bootstrap failed: 5: Input/output error"
            self.jobs[label] = "-"
            return 0, "", ""
        label = args[1].split("/", 2)[2]
        if verb == "bootout":
            if self.bootout_rc is not None:
                return self.bootout_rc, "", "Boot-out failed"
            if label not in self.jobs:
                return 3, "", "Boot-out failed: 3: No such process"
            del self.jobs[label]
            return 0, "", ""
        if verb == "print":
            if label not in self.jobs:
                return 113, "", 'Could not find service "%s"' % label
            state, runs, code = self.prints.get(label, ("not running", "0", "(never exited)"))
            return 0, "%s = {\n\tstate = %s\n\truns = %s\n\tlast exit code = %s\n}\n" % (
                label, state, runs, code), ""
        raise AssertionError("unexpected launchctl call %r" % args)

    def verbs(self, verb):
        return [c for c in self.calls if c[0] == verb]


def load():
    sys.path.insert(0, repo_path("hooks"))
    spec = importlib.util.spec_from_file_location("dg_resume_ld", repo_path("hooks", "resume.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.scheduler_kind = lambda: "launchd"
    # Windows has no os.getuid; the launchd branch only ever runs for real on macOS, which does.
    if not hasattr(os, "getuid"):
        mod._gui_domain = lambda: "gui/501"
    return mod


@contextlib.contextmanager
def launchd(mod, sdir):
    """A fresh fake launchd, the cwd in `sdir` (log_line writes there), output swallowed."""
    fake = FakeLaunchd()
    saved, mod._launchctl = mod._launchctl, fake
    here = os.getcwd()
    os.chdir(sdir)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            yield fake
    finally:
        os.chdir(here)
        mod._launchctl = saved


def label_at(mod, sdir, sid, epoch):
    return mod.launchd_label(sdir, sid, epoch)


def case_kind_follows_the_platform():
    # the module's OWN scheduler_kind(), not the one load() pins
    mod = importlib.util.module_from_spec(importlib.util.spec_from_file_location(
        "dg_resume_kind", repo_path("hooks", "resume.py")))
    mod.__spec__.loader.exec_module(mod)
    saved = (mod.os.name, mod.sys.platform)
    try:
        for name, platform, want in (("nt", "win32", "schtasks"), ("posix", "darwin", "launchd"),
                                     ("posix", "linux", "at")):
            mod.os.name, mod.sys.platform = name, platform
            assert mod.scheduler_kind() == want, (name, platform, mod.scheduler_kind())
    finally:
        mod.os.name, mod.sys.platform = saved
    print("ok - Windows -> schtasks, macOS -> launchd, other POSIX -> at, decided at run time")


def case_labels_are_unique_and_attributable(mod):
    with scratch_dir("labels") as sdir:
        when = int(time.time()) + 3600
        a, b = label_at(mod, sdir, SID, when), label_at(mod, sdir, SID, when)
        assert a != b, "two arms for the same session and second got ONE label: %s" % a
        assert a.startswith("%s%s.%s.%d." % (mod.LAUNCHD_PREFIX, mod.dir8(sdir), SID, when)), a
        assert mod.launchd_epoch(a) == when, (a, mod.launchd_epoch(a))
        assert mod.launchd_epoch("application.com.microsoft.VSCode.1.2") is None
        assert mod.launchd_epoch(mod.LAUNCHD_PREFIX + "x.y.notanumber.ab") is None
    print("ok - a label carries directory, session and fire time, and two for one second differ")


def case_schedule_writes_and_registers(mod):
    with scratch_dir("schedule") as sdir:
        when = time.localtime(time.time() + 3600)
        with launchd(mod, sdir) as fake:
            cmd, plist = mod.schedule(when, True, SID, sdir=sdir)
            assert not os.path.exists(cmd[-1]), "a DRY RUN wrote a plist: %s" % cmd[-1]
            assert plist and plist["Label"] in cmd[-1] and not fake.calls, (cmd, fake.calls)
            label = mod.launchd_label(sdir, SID, time.mktime(when))
            cmd, r = mod.schedule(when, False, SID, sdir=sdir, label=label)
            assert r.returncode == 0 and fake.jobs.get(label) == "-", (r.returncode, fake.jobs)
            with open(mod.launchd_plist_path(sdir, label), "rb") as f:
                pl = plistlib.load(f)
            assert pl["Label"] == label and pl["ProgramArguments"][:2] == ["/bin/sh", "-c"], pl
            line = pl["ProgramArguments"][2]
            assert "--run" in line and "--session %s" % SID in line and "--dir" in line, line
            assert pl["StartCalendarInterval"] == {"Month": when.tm_mon, "Day": when.tm_mday,
                                                   "Hour": when.tm_hour, "Minute": when.tm_min}, pl
            assert pl["EnvironmentVariables"].get("PATH"), "the job would get launchd's PATH (no claude)"
            assert "RunAtLoad" not in pl and "KeepAlive" not in pl, pl
            # a refused registration leaves no plist behind
            fake.bootstrap_rc = 5
            label2 = mod.launchd_label(sdir, SID, time.mktime(when))
            _cmd, r2 = mod.schedule(when, False, SID, sdir=sdir, label=label2)
            assert r2.returncode == 5 and not os.path.exists(mod.launchd_plist_path(sdir, label2))
    print("ok - schedule() writes the plist beside the records, registers it, and cleans up a refusal")


def case_arm_records_the_label_first_and_replaces_the_old_job(mod):
    with scratch_dir("arm") as sdir:
        task = os.path.join(sdir, "Memory", "tasks", "20260101-000000-t")
        os.makedirs(task)
        with open(os.path.join(task, "HANDOFF.md"), "w", encoding="utf-8") as f:
            f.write("# handoff\n" + "the next step is written here in full. " * 12)
        seen = []

        def record_named(label, _path):
            rec = json.load(open(mod.record_path(sdir, SID), encoding="utf-8"))
            seen.append(rec.get("launchd_label") == label)

        saved = (mod.launch_probe, mod.arming_session)
        mod.launch_probe = lambda sdir_, sid_, env=None, headless=False: (True, "probe ok")
        mod.arming_session = lambda sdir_, sid_: (SID, None)
        try:
            with launchd(mod, sdir) as fake:
                fake.on_bootstrap = record_named
                argv = ["--arm", "--task", task, "--at", "03:00"]
                assert mod.do_arm(argv, sdir, {}) == 0
                first = json.load(open(mod.record_path(sdir, SID), encoding="utf-8"))["launchd_label"]
                # ⛔ the same session, the same minute: launchd would refuse a repeated label (rc 5)
                assert mod.do_arm(argv, sdir, {}) == 0, "a second arm for the same minute failed"
                second = json.load(open(mod.record_path(sdir, SID), encoding="utf-8"))["launchd_label"]
        finally:
            mod.launch_probe, mod.arming_session = saved
        assert seen == [True, True], "a label was registered before its record named it: %r" % seen
        assert first != second and second in fake.jobs, (first, second, fake.jobs)
        assert first not in fake.jobs, "the replaced alarm is still loaded and would fire: %r" % fake.jobs
        assert not os.path.exists(mod.launchd_plist_path(sdir, first))
    print("ok - the record names a label before it is registered; a re-arm replaces the old job")


def case_remove_never_boots_out_a_running_job(mod):
    with scratch_dir("remove") as sdir:
        with launchd(mod, sdir) as fake:
            idle, running, refused = (label_at(mod, sdir, SID, 1), label_at(mod, sdir, SID, 2),
                                      label_at(mod, sdir, SID, 3))
            fake.jobs.update({idle: "-", running: "4242"})
            assert mod._launchd_remove(sdir, label_at(mod, sdir, SID, 9)) == "not there"
            assert mod._launchd_remove(sdir, running) == "running"
            assert running in fake.jobs and not [c for c in fake.verbs("bootout") if running in c[1]], (
                "a RUNNING job was booted out - inside the job that kills the caller itself")
            assert mod._launchd_remove(sdir, idle) == "deleted" and idle not in fake.jobs
            fake.jobs[refused] = "-"
            fake.bootout_rc = 37
            assert mod._launchd_remove(sdir, refused) == "refused" and refused in fake.jobs
            del fake.jobs[refused]                       # gone meanwhile: print says 113
            assert mod._launchd_remove(sdir, refused) == "not there"
    print("ok - _launchd_remove: not there / running (never booted out) / deleted / refused")


def case_cancel_outcomes(mod):
    with scratch_dir("cancel") as sdir:
        with launchd(mod, sdir) as fake:
            lab = label_at(mod, sdir, SID, time.time() + 600)
            for pid, want_rc, kept, loaded in (("-", 0, False, False), ("77", 0, False, True)):
                fake.jobs = {lab: pid}
                mod.write_record(sdir, SID, {"task": "x", "launchd_label": lab})
                rc = mod.do_cancel(sdir, quiet=False, session_id=SID)
                assert rc == want_rc and os.path.exists(mod.record_path(sdir, SID)) is kept, (pid, rc)
                assert (lab in fake.jobs) is loaded, (pid, fake.jobs)
            fake.jobs, fake.bootout_rc = {lab: "-"}, 37
            mod.write_record(sdir, SID, {"task": "x", "launchd_label": lab})
            assert mod.do_cancel(sdir, quiet=True, session_id=SID) == 1, "a refused cancel claimed success"
            assert os.path.exists(mod.record_path(sdir, SID)), "a refused cancel dropped the record"
            # armed by <=0.74 with `at`: nothing can fire; its at job is removed by number
            fake.bootout_rc = None
            ran = []
            saved = mod.subprocess.run
            mod.subprocess.run = lambda cmd, **k: (ran.append(list(cmd)), Result(0))[1]
            try:
                mod.write_record(sdir, SID, {"task": "x", "at_job": "12"})
                assert mod.do_cancel(sdir, quiet=True, session_id=SID) == 0
            finally:
                mod.subprocess.run = saved
            assert ran == [["atrm", "12"]] and not os.path.exists(mod.record_path(sdir, SID)), ran
    print("ok - cancel: idle job unloaded, running job left to finish, refusal keeps the record, "
          "an old `at` record is cleared")


def case_a_fire_its_record_does_not_name_is_a_noop(mod):
    with scratch_dir("stale") as sdir:
        named = label_at(mod, sdir, SID, time.time())
        stale = label_at(mod, sdir, SID, time.time() - 365 * 86400)
        mod.write_record(sdir, SID, {"task": "x", "launchd_label": named})
        saved = os.environ.get("XPC_SERVICE_NAME")
        try:
            with launchd(mod, sdir):
                os.environ["XPC_SERVICE_NAME"] = stale
                assert mod.do_run(sdir, mod.usage.config(sdir), SID) == 0
                os.environ["XPC_SERVICE_NAME"] = named           # the armed one: not stale
                mod.do_run(sdir, mod.usage.config(sdir), SID)
                os.environ["XPC_SERVICE_NAME"] = "application.com.microsoft.VSCode.1.2"
                mod.do_run(sdir, mod.usage.config(sdir), SID)
        finally:
            if saved is None:
                os.environ.pop("XPC_SERVICE_NAME", None)
            else:
                os.environ["XPC_SERVICE_NAME"] = saved
        log = open(os.path.join(sdir, ".claude", "dispatch_gate.log"), encoding="utf-8").read()
        assert log.count("RUN-STALE") == 1 and stale in log, log
        assert "RUN-ABORT no handoff" in log, "the armed label did not get past the stale guard: %s" % log
    print("ok - a fire the record does not name (next year, replaced, orphaned) exits untouched")


def case_sweep(mod):
    with scratch_dir("sweep") as sdir:
        now = time.time()
        with launchd(mod, sdir) as fake:
            due = label_at(mod, sdir, OTHER, now + 60)           # armed a moment ago, no record yet
            spent = label_at(mod, sdir, SID, now - 3 * 3600)
            running = label_at(mod, sdir, SID, now - 4 * 3600)
            foreign = "%s%s.%s.%d.%s" % (mod.LAUNCHD_PREFIX, "ffffffff", SID, int(now - 5 * 3600), "00000000")
            fake.jobs = {due: "-", spent: "-", running: "999", foreign: "-"}
            stray_old = mod.launchd_plist_path(sdir, label_at(mod, sdir, SID, now - 3 * 3600))
            stray_due = mod.launchd_plist_path(sdir, label_at(mod, sdir, SID, now + 600))
            for p in (stray_old, stray_due):
                os.makedirs(os.path.dirname(p), exist_ok=True)
                open(p, "w").close()
            mod.reap_records(sdir, now=now)
            assert due in fake.jobs, "the reaper removed an alarm armed a moment ago (I-N2's race)"
            assert spent not in fake.jobs, "a spent job stayed loaded - it would fire next year"
            assert running in fake.jobs and foreign in fake.jobs, fake.jobs
            assert not os.path.exists(stray_old) and os.path.exists(stray_due)
            # --cancel --session X: only X's jobs, even future ones
            mine = label_at(mod, sdir, SID, now + 600)
            fake.jobs[mine] = "-"
            mod.launchd_sweep(sdir, "cancel", session_id=SID, now=now)
            assert mine not in fake.jobs and due in fake.jobs, fake.jobs
            # a bare --cancel: everything of this directory that is not running
            mod.launchd_sweep(sdir, "cancel", now=now)
            assert due not in fake.jobs and running in fake.jobs and foreign in fake.jobs, fake.jobs
    print("ok - the sweep spares what is due, running or another directory's, and clears the rest")


def case_rearm_from_inside_the_job(mod):
    with scratch_dir("rearm") as sdir:
        with launchd(mod, sdir) as fake:
            old = label_at(mod, sdir, SID, time.time() - 60)
            fake.jobs[old] = "555"                                 # it is the job running this
            old_plist = mod.launchd_plist_path(sdir, old)
            os.makedirs(os.path.dirname(old_plist), exist_ok=True)
            open(old_plist, "w").close()
            state = {"task": "t", "session_id": SID, "launchd_label": old, "at": time.time() - 60}
            mod.write_record(sdir, SID, state)
            seen = []
            fake.on_bootstrap = lambda label, _p: seen.append(
                json.load(open(mod.record_path(sdir, SID), encoding="utf-8"))["launchd_label"] == label)
            mod._rearm(sdir, state, 20)
            new = json.load(open(mod.record_path(sdir, SID), encoding="utf-8"))["launchd_label"]
            assert seen == [True] and new != old and new in fake.jobs, (seen, new, fake.jobs)
            assert old in fake.jobs and not fake.verbs("bootout"), "the re-arm booted out its own job"
            assert not os.path.exists(old_plist), "the replaced job's plist was kept"
            # a refused re-registration is restored and ANNOUNCED
            fake.bootstrap_rc = 5
            mod._rearm(sdir, state, 20)
            rec = json.load(open(mod.record_path(sdir, SID), encoding="utf-8"))
            assert rec["launchd_label"] == new, "a failed re-arm left the record naming nothing loaded"
            assert os.path.exists(mod.failed_path(sdir, SID)), "a failed re-arm was not announced"
    print("ok - a re-arm records first, never boots out the job it runs in, and announces a refusal")


def case_status_reads_launchd(mod):
    with scratch_dir("status") as sdir:
        with launchd(mod, sdir) as fake:
            lab = label_at(mod, sdir, SID, time.time())
            st = {"launchd_label": lab}
            assert "NO JOB loaded" in mod.task_readback(sdir, SID, st)
            fake.jobs[lab] = "-"
            for prints, want in ((("not running", "0", "(never exited)"), "has not fired yet"),
                                 (("running", "1", "(never exited)"), "RUNNING now"),
                                 (("not running", "1", "0"), "exited 0"),
                                 (("not running", "1", "1"), "FIRED and exited 1")):
                fake.prints[lab] = prints
                got = mod.task_readback(sdir, SID, st)
                assert want in got, (prints, got)
            assert "`at`" in mod.task_readback(sdir, SID, {"at_job": "3"})
    print("ok - --status reads launchd's own answer for the record's job")


def main():
    fresh_scratch()
    # ⛔ log_line() also appends to the DEFAULT state directory's log; without this the cases'
    # RESUME lines land in the owner's real ~/.claude/dispatch-guard/dispatch_gate.log (measured
    # on the first run of this file). Same remedy as test_net_zone.
    os.environ["CLAUDE_DISPATCH_DIR"] = os.path.join(fresh_scratch(), "state-dir-for-the-log")
    case_kind_follows_the_platform()
    mod = load()
    case_labels_are_unique_and_attributable(mod)
    case_schedule_writes_and_registers(mod)
    case_arm_records_the_label_first_and_replaces_the_old_job(mod)
    case_remove_never_boots_out_a_running_job(mod)
    case_cancel_outcomes(mod)
    case_a_fire_its_record_does_not_name_is_a_noop(mod)
    case_sweep(mod)
    case_rearm_from_inside_the_job(mod)
    case_status_reads_launchd(mod)
    print("resume launchd OK")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
