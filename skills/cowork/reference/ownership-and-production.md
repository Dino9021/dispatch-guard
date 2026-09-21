# Shared trees, ownership, and changing something real

Open this before sharing one working directory with other sessions, before changing anything a
real system depends on, and before publishing anything outward.

---

## Part 1 - One shared tree, one owner of the irreversible operations

**Do not give each session its own copy of the work.** When sessions coordinate through files
in a shared directory — a running record, each other's outputs, tools one session writes and
another fixes — a per-session copy destroys the only channel they have. One session's note
becomes invisible to the others until somebody merges. The shared directory is the design, not
a defect to be fixed.

**Split who may perform irreversible operations, not who may see the files.** Everyone reads
and writes ordinary files. Exactly one session at a time may run the operations that rewrite
shared state or publish it outward — in a version-controlled tree that means commit, branch,
checkout, reset, and anything that pushes.

- Record the current owner in a file, not in anybody's memory.
- A session that is not the owner has two honest routes: **ask the owner to publish for them**,
  or **work in a throwaway copy** that nobody else is working in, publish from there, delete it.
- ⛔ A throwaway copy is for producing one publication. The moment someone continues *working*
  in it, its writes diverge from the shared tree and the others stop seeing them.

⇒ **How to write to a shared file without silently overwriting anyone**, including inside a
throwaway copy, is in `verification.md`, Part 2.

**The owner's job is not "being right about the content".** It is: the thing that gets
published is the thing that was reviewed, and nothing of anybody else's goes missing on the
way. Content correctness stays with whoever measured it.


⇒ The two artefact rules that belong with this - *the most dangerous artefact is the one with
no owner* and *two rule-sets can both be correct and still leave a hole* - are in
`coordination.md`, Part 3.

---

## Part 2 - Changing something real

**Having approval is not having understanding.** When an owner approves a change, the last step
before making it is to find out **why the thing is in its current state**. More than once the
answer changed what the correct change was — something had been disabled after a rebuild rather
than as part of the original response, and that difference mattered.

**Tools that touch real systems should be fail-closed:**

- default to reporting; require an explicit flag to act;
- refuse, rather than proceed, when a precondition is not what was assumed — for instance when
  the setting about to be edited is currently live rather than dormant;
- never touch the neighbouring setting that would change behaviour immediately, even if it is
  right there;
- read the value back after writing it, on every target, and print the comparison.

**Check whether the setting is managed from a layer above before editing it locally.** A value
pushed down by central policy will be restored on the next refresh **with no message at all**:
the change appears to work, then quietly stops being true. Measure where it comes from first;
if it comes from above, the edit belongs up there.

**Apply to every target in one operation and verify each one separately.** A setting that is
only correct on some members of a group is the state that produced the problem to begin with,
and it is invisible until someone enumerates all of them.


---

## Part 3 - Where an artefact lives is what switches it on

### A draft sitting at the delivery path is already live

Where an artefact lives is what switches it on. Anything placed at the path the system loads
from is loaded — not when it is finished, but immediately.

- Measured independently by two people in the same hour: a half-written guidance document
  placed at its final path was listed as available to every participant the moment it existed,
  and would have been followed as if complete.
- **A half-finished artefact in the live position is worse than no artefact at all.** When it
  is absent people ask; when a plausible draft is present, people comply with it.
- So keep work-in-progress at a path that nothing loads from, and move it to the delivery path
  as the **last** step. If you cannot tell which paths are live, find out before writing, not
  after: the difference is invisible from inside the file.


---

## Part 4 - When you leave something out because somebody else has it

### Omitting what someone else has, when their copy can move

Deciding *"I will not write this, the other contribution covers it"* is correct, and it pairs
badly with a second correct action: someone reorganising, renaming or withdrawing that other
contribution. Neither person has erred; together they produce a topic nobody wrote.

- **The person who made the omission is the one who cannot notice it**, because they will not
  look at that topic again. So state the omission where it will be read: alongside your own
  work, listing what you relied on, **one line per item**.
- This does not conflict with the rule against keeping a second copy of anything. The rule
  forbids **two full copies that drift into two different answers**. A one-line pointer cannot
  drift into an answer; it can only reveal an absence. Keep the distinction explicit, or
  somebody will cite the no-duplication rule to justify writing nothing.
- **Before declaring a shared artefact missing, search by content — size, headings, a hash —
  not only by filename, and not only in the one directory you expect.** From the searcher's
  side, *deleted*, *renamed* and *filed somewhere else* look exactly the same, and the latter
  two are far more likely while several people are reorganising. Measured while writing this
  section: three different people, inside one hour, each announced a piece of work missing;
  in all three cases it existed, under another name or in another directory. **A naming scheme
  that encodes something other than the author** — section numbers, topics, dates — makes this
  worse, because the searcher reads the name as an author and skips the file.
  Related trap: the tidy, rigorous-looking classifications for "no answer" make it easy to
  file a moved artefact as *unrecoverable* and stop looking.
- **This is the one absence claim you must not relay unchecked.** Passing on "X has not been
  done" turns one person's failed search into a shared fact, and the next reader has no way to
  tell it was never verified. Search for it yourself before repeating it — and if you were
  asked to relay it, say that you checked and what you found. **Timestamp the check when you
  report it**, because an absence expires faster than a presence: the thing can arrive one
  minute later, and nothing will tell you.
- **An explanation that used to be true will stop you re-checking the thing it explained.**
  The sharper version of the failure above, diagnosed by the person who made it: the evidence
  *was* in front of them — a directory they had been told was empty had reappeared in their own
  output minutes earlier — and a ready-made account of it ("empty, something recreated it"),
  correct when they formed it, consumed the new observation instead of being revised by it.
  ⇒ **When you are about to skip a check because you checked before, look at the timestamp on
  that earlier check.** In a shared working area the answer changes in minutes, and the
  explanation you are reusing has no expiry date written on it.
- **The stale explanation usually has an author, and it is often the tidy one.** In this case
  the location had been emptied by somebody standardising on a different convention — a
  harmless-looking cleanup that made a true-at-the-time observation, which then outlived its
  truth. **Removing or renaming a shared location is an announcement, not housekeeping**: say
  it where the others read, because somebody is still writing there. (Use an operation that
  cannot destroy, and say which: a command that refuses to act on a non-empty directory proves
  by its own semantics that nothing was lost, and that is worth more than remembering that it
  looked empty.)

⚠ The reporting side of the last two points - *never relay an absence you did not check* and
*a stale explanation stops you re-checking* - is in `owner-and-reporting.md`, Part 2.
