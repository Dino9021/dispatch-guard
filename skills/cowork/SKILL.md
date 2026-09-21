---
name: cowork
description: Rules for several AI sessions working the same repository for one human owner over days or weeks - who is who, how work is claimed and reported, how the owner is protected from repeated questions and silent completions, and the failure shapes that make a wrong answer look finished. Use when more than one session shares a working tree, when a long task will outlive one context window, or when an owner is relaying the same thing to several sessions. Two of its rules are enforced by the dispatch-guard hook.
---

# Cowork: several sessions, one owner, one working tree

Written by sessions that shared one repository and one owner. Every line cost something to
learn. Nothing here names a project, machine, account, path, product or
person - if a rule cannot be applied elsewhere, it does not belong in this file.

Read this page in full. Open a reference file when you are about to do the thing it covers.
Every pointer in this skill targets a file that ships in this plugin - `skills/*/SKILL.md`,
`PROTOCOL.md` - never a file only one machine has.

---

## The twelve rules

If you read nothing else, these are the ones whose absence caused real damage.

1. **Claim before you produce.** One instruction reaching every session at once produces four
   drafts of the same section. Write a line on a shared, append-only record saying what you
   are taking; take only what is unclaimed. Claim the *tools* you build as well as the pieces
   of the deliverable - two people building the same instrument collides nowhere.
2. **Register yourself, never someone else.** Session names expire silently and an expired
   roster looks exactly like a current one. To find who holds a role *now*, query the live
   source. A roster records who claimed what when - it is history, not an address book.
3. **One append-only shared record, and correct it by appending.** Never edit an earlier
   entry, not even your own. The fact that a wrong answer was once believed is usually the
   most useful thing in the file. ⭐ **Enforced:** a file whose first heading says
   `append-only` (or that carries `<!-- append-only -->` on a line of its own) may only grow -
   see *What the hook enforces* below.
4. **Funnel questions to the owner through one session, and back the funnel with a file.**
   The funnel stops the owner answering the same thing three times. The file stops every
   pending question dying with that session.
5. **Never use a pronoun when asking the owner.** "Those five", "the broken one", "the old
   script" - replace each with its full name. If you cannot write the name, you have not
   finished investigating and the question is not ready.
6. **Search before you ask, and search before you start.** Filing, committing and writing a
   handover guarantee *findable*; none of them guarantees *read*. The most expensive failure
   is redoing something already finished by somebody else. *How* to search so that an empty
   result means something is `unattended-work` §11.
7. **Finished but not reported is not finished.** Land the result in the shared artefact
   before telling anyone it is done. Being right somewhere nobody can read is being silent.
8. **Execute the claim; never reason it.** One live copy: `unattended-work` §10. What this
   skill adds is that it binds a *peer's* claim as much as your own - re-measure a
   load-bearing report before you build on it (`owner-and-reporting.md` 2.9).
9. **An empty result is a claim - and one control is not enough.** The positive control, the
   anchored path, the unsilenced error and the two patterns are `unattended-work` §11. This
   skill adds the other three: a **pattern** probe with the target's shape that must fire, a
   **lookalike** that must NOT fire, and a fresh **negative** sentinel. "Most rules fired" is
   not a control.
10. **Verify a write by bytes, and then check the structure.** Appending: `after == before +
    body`. Replacing: the five steps in the verification reference. Bytes prove the write
    landed intact; a structural check (count the sections, the headings, the columns) proves
    it landed in the right place. They are complements.
11. **Before declaring anything missing, search by content, not by filename - and never relay
    an absence you did not check yourself.** Measured: three people in one hour each announced
    a piece of work missing; all three existed, under another name or in another directory.
    Passing on "X has not been done" turns one failed search into everyone's fact.
12. **Say which kind of "no answer" you have.** `UNKNOWN` (looked; the data cannot tell) /
    `NOT-ASKED` (a source exists; we chose not to look) / `UNCONFIRMED` (partly looked).
    Collapsing them is how a question stops being asked forever.

**Where each rule is worked out in full** - go to the named section, not to the directory:

| # | Section to open |
|---|---|
| 1 | `coordination.md` · Part 1 · *When one instruction reaches everyone at once* |
| 2 | `coordination.md` · Part 2.1, 2.2, 2.5 |
| 3 | `coordination.md` · Part 3.1, 3.2 · and *What the hook enforces*, below |
| 4 | `owner-and-reporting.md` · Part 1.1, 1.2, 1.3 |
| 5 | `owner-and-reporting.md` · Part 1.5 |
| 6 | `owner-and-reporting.md` · Part 1.6 · and `coordination.md` · Part 1 · *Before you spend a round* |
| 7 | `owner-and-reporting.md` · Part 2.1 |
| 8 | `unattended-work` §10 · then `owner-and-reporting.md` · Part 2.9 |
| 9 | `unattended-work` §11 · then `verification.md` · Part 3 · *Three controls, not one* |
| 10 | `verification.md` · Part 2 · and Part 3 · *A byte check proves the write, not the intent* |
| 11 | `ownership-and-production.md` · Part 4 · and `owner-and-reporting.md` · Part 2.12 |
| 12 | `verification.md` · Part 1.5 · and `owner-and-reporting.md` · Part 2.3 |

⭐ **And the rule about rules: a lesson that keeps recurring needs a gate, not another
record.** If the same mistake has been written down three times and still happens, stop
writing it down and make something refuse to continue. Every rule in this file was broken at
least once by the people writing it, in the hour they were writing it. Two of them are gates
now.

---

## What the hook enforces

The dispatch-guard hook sees every tool call of every session on the machine, and two of
these rules are cheap to refuse there. **A refused call is the rule working, not a bug.**
Both guards fail open (a broken guard logs and allows), stay advisory for a session that
started before the plugin was installed, log every decision, and have their own switch.

**`guard_append_only` (rule 3).** A file declares itself append-only when, inside its first
2 048 bytes, its first heading line contains `append-only` / `append only`, or an HTML comment
`<!-- append-only -->` stands on a line of its own. Body text - including this sentence, which
merely mentions the comment - does not count. For such a file the hook refuses:

- a `Write` whose content does not start with the file's current text;
- an `Edit` whose `old_string` is not the end of the file, or whose `new_string` does not start
  with it, or whose `old_string` occurs more than once in the file (with or without
  `replace_all` - the tool edits one occurrence and the guard cannot tell which; make the
  anchor the whole last entry, not its last line);
- a shell command that truncates, rewrites in place or removes it: `> path` (quoted paths
  included), `sed -i`, `tee` without `-a`, `rm`, `truncate`, `cp` *onto* it, `mv` *from or onto*
  it, `Set-Content`, `Out-File` without `-Append`, `Clear-Content`, `Remove-Item`, `Move-Item`,
  `Rename-Item`, `Copy-Item` *onto* it; a leading `cd x &&` (or `Set-Location`, `pushd`) in the
  same command *replaces* the directory the path is resolved against.

Allowed: creating the file; `>>`, `tee -a`, `Add-Content`; an `Edit` whose `old_string` is the
file's last *entry* (long enough to occur once, ending at the file's end) and whose
`new_string` starts with it; copying the file *out*. ⚠ A copy inherits the
marker - snapshot to a new name, and never copy back onto the record. ⚠ A program that rewrites
the file in place (`python fix.py board.md`), or removing the directory that holds it, is not
seen; the guard reads shell operators and file-tool inputs, not what a program does.

**`guard_cowork_first` (rules 1-2).** When another session's heartbeat in this repository is
younger than `peer_alive_min` (default 15 minutes) and this session has not invoked
`dispatch-guard:cowork`, the first `Write` / `Edit` (any file tool) / `git commit` is refused
**once**, naming the peer count. Invoke the skill and retry; the next call goes through either way. A session
idle at a prompt stops heartbeating, so an idle peer past 15 minutes is not counted; a peer
that just exited is counted for up to 15 minutes - once, then never again for that session.

Switches: `guard_append_only`, `guard_cowork_first`, `peer_alive_min` - in the plugin's
`config.json` or `<repo>/.claude/dispatch-guard.json` under `dispatch`. A switched-off guard
still logs what it would have refused.

---

## The failure shapes

A catalogue, so the next session names the shape instead of rediscovering it.

| Shape | What it looks like | What breaks it |
|---|---|---|
| Silent instrument | A check that cannot fail, reporting success | A positive control in the same run |
| False zero | Empty output from a wrong path, filter, or encoding | Anchor the path; never silence errors; two patterns |
| Rule too narrow | A believable zero from a rule that matches nothing at all | A synthetic probe with the target shape; every rule must fire |
| Rule too broad | Confident hits on innocent data that merely resembles the target | A lookalike probe that must NOT match, beside the one that must |
| True hit, wrong meaning | A real match, in another section or another day | Read the context of the hit, not the count |
| One-sided change | A classifier changed, and checked only where you were looking | Read every category it emits before quoting any of its numbers |
| Swapped comparison | Re-checking a flawed instrument; the question changed under you | Restate both sides, then confirm the new command still has them |
| Right bytes, wrong place | A write that verified perfectly against a wrong expectation | A structural check on the result, alongside the byte check |
| Half-verified guard | One mutation shows a guard is there, not that it is what stopped you | Break the protected thing; then remove the guard and confirm it slips |
| Stored number rot | A figure that quietly stopped being true | Recompute; or record when it was measured |
| Undated records | Timestamps without dates, compared as strings | Walk backwards from the end to a known marker; allow a day boundary only when the window truly crosses one |
| Claim before doing | Writing "done" and then finding it failed | Do, verify, then write. Never the other order |
| Fixed the one that bit me | One caller patched, the identical siblings left | Search for the same shape across the whole tree and fix the family |
| Alarm with no name | An alert that says how many, never which | Carry the identifier into the alert at the moment it is raised; a later lookup finds the state already gone |
| Anonymous tool | Two copies produce identical output, so a claimed fix cannot be tested | The version in the first output line; new content gets a new version |
| Relay single point | All communication funnelled through one session | Keep a durable written path alongside the relay |
| Collected is not read | The answer was filed somewhere nobody opened | Before asking anyone, search the record for it |
| Renamed reads as deleted | A shared artefact "vanishes" during a tidy-up | Search by content - size, headings, hash - and in more than the one directory you expect |
| Stale explanation | New evidence absorbed by an account that was true earlier | Check the timestamp on the check you are about to reuse |
| Tidy-up as a trap | A convention change leaves a location others are still using | Removing a shared location is an announcement, not housekeeping |
| Omission meets reorganisation | Nobody wrote it: one deferred to the other, the other moved | List what you relied on, one line each, beside your own work |
| Draft in the live slot | A half-written artefact loaded and followed as if finished | Work at a path nothing loads from; move to the live path last |
| Everyone defers | "I am not claiming it", four times, and the task stops | Deferrals carry an expiring default naming who does it otherwise |
| Two right rules | Two rule-sets coexist unnoticed and are followed in opposite directions | Read the artefact, not only the instructions about it; report the disagreement first |

---

## Where the detail lives

| Open this | When you are about to |
|---|---|
| `reference/coordination.md` | decide whether to split work across sessions at all; take over a role; work out who is who; write to the shared record |
| `reference/owner-and-reporting.md` | ask the owner anything; report a result; report that you are stuck; disagree with a peer |
| `reference/verification.md` | claim that something is true; write to a file others share; build or trust a checking tool |
| `reference/ownership-and-production.md` | share one working tree; change a live system; publish anything outward |
| `reference/longrunning.md` | hand over; run out of budget; start something that runs for hours or days |

Where a rule already lives in `unattended-work` or `dispatch-protocol`, these files point at it
and add only what several sessions change about it.

---

## How to use this file

1. New session joining a shared tree: read the twelve rules, register yourself, read the
   recent shared record. Then `reference/coordination.md`.
2. Before answering anything about a live system: `unattended-work` §10-§11, then
   `reference/verification.md`.
3. Before a long or unattended task: `unattended-work` and `dispatch-protocol` first;
   `reference/longrunning.md` for what several sessions add.
4. When something looks wrong: find the shape in the table above before theorising.
5. When this file is wrong, the fix goes to the dispatch-guard repository and arrives by
   plugin update - never to an installed copy, and never as a second file under this name.
   **One copy only** - two files under one name is a coin toss, even while they are
   momentarily identical.
