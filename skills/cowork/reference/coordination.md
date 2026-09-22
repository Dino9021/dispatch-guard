# Coordination: splitting work, knowing who is who, the shared record

Open this when deciding whether to run several sessions at all, when you take over a role, when
you need to reach a specific peer, or when you write to the shared record.

---

## Part 1 - Deciding to run several sessions at all

### Parallel work is not free, and the cost is coordination

Several sessions on one body of work buy three things:

1. **Continuity beyond one context window.** Work that runs for days cannot live in one
   session; something must carry it, and separate sessions with separate roles carry it better
   than one session that keeps restarting.
2. **Different angles on the same material.** A reviewer whose responsibility lies outside the
   area being reviewed finds things the author does not. Measured on one engagement: most of
   the substantive corrections came from outside the responsible role, and **none was found by
   the author of the thing corrected.**
3. **Honest verification.** A second session can re-run a measurement without inheriting the
   first one's assumptions - which a second pass by the same session cannot do.

They cost one thing, and it grows faster than the number of participants:

- **every shared artefact needs an owner**, or it gets edited by everyone or by nobody;
- **every rule needs to exist in exactly one place**, or two correct rules quietly contradict;
- **every name needs to be current**, or messages go to addresses that no longer exist.

⇒ **Use several sessions when the work outlives one window, or when being checked by someone
outside the work is worth more than the coordination overhead. Otherwise use one.**

### The shapes that are worth splitting

| Shape | Why it splits well |
|---|---|
| Long-running observation vs. one-off analysis | Different cadence: one wakes on a schedule, the other runs to completion |
| Producing something vs. publishing it | The publisher screens what goes out; the producer does not review their own output |
| Building a tool vs. relying on it | The user of a tool finds defects its author cannot see |
| Gathering findings vs. reconciling them | Reconciling is a role, not a leftover task - unowned, it does not happen |

### The shapes that do not split

- **One linear task with one right answer.** Two sessions produce two answers and then a third
  problem: deciding which.
- **Anything needing one consistent voice** - a single document, a single interface. Split the
  research, not the writing.
- **Work whose parts all touch the same lines of the same file.** Splitting that buys nothing
  and costs merge conflicts.
- **A task shorter than the cost of explaining it.** Handing over a task has a fixed price: the
  brief has to stand alone. Below some size, doing it is cheaper than describing it.

### When one instruction reaches everyone at once

An owner who relays the same instruction to every session gets every session starting the same
work at the same minute. That is the single most reliable way to produce duplicated,
conflicting output.

⇒ **Claim before producing.** One shared, append-only claim record; you write a line saying
what you are taking; you take only what is unclaimed. It costs one round and it is the only
thing that stops four parallel drafts of the same section.

⇒ ⭐ **Claim the tools too, not only the pieces of the deliverable.** Measured: two people
independently built a screening tool for the same check, in the same hour. Neither collided
with the other on the claim record, because **a tool is not a section** - and nothing in the
process asked.
🔑 **The most expensive duplication between parallel workers is not two drafts of one
section - that collides visibly. It is two people building the same instrument**, which
collides nowhere.
⇒ Before building anything that measures, ask on the record whether somebody is already
measuring it.
⚠ **Tool duplication never shows up on the split of work**, because nobody writes "I am going
to build an instrument" as a task. That is exactly why it has to be asked for explicitly.

⇒ **The one who moves first proposes the split; everyone else may veto but must say so.**
Silent compliance is worse than disagreement here - if a split is wrong, the person who sees it
is usually not the one who proposed it.

⇒ ⭐ **When two people propose coordination schemes at the same moment, the coordination scheme
itself now needs coordinating.** The fix is not to argue about which is better. **Somebody
concedes immediately**, and the cost stops at one round. Whoever concedes should say so on the
shared record, so the third and fourth participants do not adopt the abandoned convention.

⇒ ⭐ **"I am not claiming it" is not coordination - it is handing the decision to the next
person.** Repeated by everyone in turn it is indistinguishable from silence, and the task
stops. Deferring is fine, but **attach an expiring default**: *if nobody has claimed this by
<time>, I do it*, and step aside immediately when somebody claims it. A deferral without a
default is a deadlock that everybody believes they are being helpful in.

⚠ **An expiring default looks unused when it works.** It is never reached, because somebody
claimed the work before the clock ran out - so the record shows a rule that never fired. Its
effect was to turn four people deferring to each other into one person starting, inside the
hour. **Whoever later trims this file for redundancy will reach for exactly this kind of rule
first.** It is doing its job precisely when nothing happened.

### Roles come from the owner, not from claiming them

- A **task** may be claimed. A **role** is assigned by the owner.
- ⛔ Never register somebody else as holding a role, however obvious it seems: an assignment is
  a fact about what the owner decided, not an inference from who is available.
- A session unsure which role it holds should ask, and should not act as owner of anything
  irreversible until it knows.

### Before you spend a round, check whether it is already done

The failure that wastes the most time is not conflict - it is **redoing something already
finished and filed by somebody else**. Filing does not notify anyone.

⇒ **Search the shared material before starting a piece of work, not only before asking a
question.** ⇒ If you finish something others are waiting on, say so on the shared record in the
same action - not only in a message to one of them.

### Know the budget before planning the work

Sessions run against a finite allowance. Plan against the number that says when it runs out,
not against when it resets: those are different, and the gap between them is exactly the period
where a half-finished task sits with nobody able to continue it.

⇒ **Write the handover before the budget is spent, not after it is gone.**

⇒ What to do once a budget is actually nearly spent - what the remainder is for, and saying
out loud what you are dropping - is in `longrunning.md`, 8.5.

---

## Part 2 - Identity: who is who

### 2.1 A roster tells you who claimed a role, never who holds it now

Session names are assigned by the runtime and change whenever the editor, the machine or the
session restarts. A table of names in a file therefore ages out - **and an aged-out table looks
exactly like a current one**. There is no visual difference between a name that is live and a
name that stopped existing an hour ago.

**Do:** to find who is running a role right now, query the live source (whatever lists running
sessions). Read the roster only to learn *who claimed what, when*.

**Otherwise:** you address work to a name that no longer exists, get a delivery failure, and
conclude that the role is vacant. It is not - you looked in the wrong place.

### 2.2 Register yourself; never register someone else

**Do:** when you take over a role, write your own row. Leave every other row alone, even when
you are certain a peer's row is stale.

**Otherwise:** a roster filled in by bystanders records guesses as facts. Role ownership comes
from the owner's assignment, not from a peer's observation. A row written by someone else is
indistinguishable from one written by the holder, and the next reader cannot tell which is which.

### 2.3 A half-updated roster is worse than a fully stale one

When some rows carry an "updated at HH:mm" marker and others do not, the unmarked rows **read
as current**. A reader who sees three fresh rows assumes the rest are fresh too.

**Do:** when you update part of a roster, also write down **which rows you did not check**.

**Otherwise:** partial freshness is read as total freshness, and the stale rows become more
dangerous than they were before anyone touched the file.

### 2.4 Re-registration decays within hours - so do not rely on memory for it

Even a correctly updated roster can be wrong again by the afternoon. Relying on people to
remember to re-register was observed to fail every single time.

**Do:** put the check in a gate that runs before something that matters - for example, refuse
the shared write until the registering session's live name matches the recorded one.

**Otherwise:** you get a rule that is written down, agreed by everyone, and still not followed,
because nothing forces the moment of checking.

⭐ The general form: **a lesson that keeps recurring needs a gate, not another written record.**
If the same mistake has been recorded three times and still happens, stop writing records.

### 2.5 "Message undeliverable" and "nobody holds that role" look identical

**Do:** when a message to a peer fails, query the live session list **and** re-read the roster
before drawing any conclusion. Say which of the two you found.

**Otherwise:** you report "the role is unstaffed" when the truth is "the name moved" - and the
person you failed to reach never learns you tried.

### 2.6 Role assignment is responsibility, not a permission boundary

**Do:** let any session measure anything, question anyone's conclusion, and demand a
correction, regardless of whose area it is.

**Otherwise:** defects survive because the only person allowed to look is the person who made
them. In practice a large share of the important corrections come from outside the area that
owns the topic - precisely because that session has no stake in the earlier answer.

### 2.7 Name files author-first

A filename is the only thing most searchers read. **Put the author at the front and the topic
after it.** A name that leads with section numbers, topics or dates is read *as* the author and
skipped - measured: a contribution named after the four sections it covered was reported
missing by two people while sitting in plain view, and was minutes away from being recorded in
the delivered artefact as an absence.

---

## Part 3 - The shared record

### 3.1 One append-only record that every session reads and writes

**Do:** keep a single shared file where every session appends its measurements, decisions and
corrections. Each entry starts with a timestamp and the author's role tag. Append only - never
edit an earlier entry, not even your own.

**Otherwise:** each session keeps its findings in its own conversation, and the only thing that
survives a restart is whatever happened to be written down. Conversations die; files do not.

⭐ **The record carries claims, measurements, decisions and corrections — NOT the work itself.
Content goes one file per author (2.7), and nobody writes into another author's file.** The
day this was written it was tested by accident: the shared deliverable everyone was merging
into was lost, and every per-author contribution file survived without losing a character.
"One file per writer" therefore buys more than "no overwrites": the work outlives the shared
artefact. Merging into the deliverable is done once, by one named person, announced on the
record first.

⛔ **Across MACHINES this file is also the only channel, and then "every session writes it"
becomes a claim to measure rather than a property to assume.** A record one side can read and
not write deadlocks both sides with no error on either. Write-test each direction before the
first real entry, and drop the in-place "whose turn" field: `cross-machine.md` Part 1.

### 3.2 Correct by appending, never by editing

**Do:** to correct something you wrote earlier, append a new entry stating what was wrong, what
is right, and how you measured it. Leave the original in place.

**Otherwise:** the record loses the fact that a wrong answer was once believed - and the
*reason* it was believed is usually the most useful part. It also becomes impossible to tell
whether a reader acted on the old version or the new one.

### 3.3 Paste the raw output line, not only the conclusion

**Do:** include the actual lines your tool printed, including the counts and the controls.

**Otherwise:** a conclusion with no output behind it cannot be challenged. The lines you paste
are the only thing another session can find a defect in - and they will, which is the point.

### 3.4 Measure the time; never estimate it

**Do:** read the clock and write the value. Same for any number: measure it at the moment of
writing.

**Otherwise:** an estimated timestamp quietly misplaces an event in a sequence, and sequences
are what people use to infer cause.

### 3.5 A written-down number goes stale because somebody changed something unrelated

Line numbers, counts, offsets and percentages are all snapshots. Someone inserting text
elsewhere invalidates every line reference, silently.

**Do:** prefer "here is how to compute it" over "here is the value". When you must record a
value, record the date, the tool and the version that produced it.

**Otherwise:** a number keeps being quoted long after it stopped being true, and nothing
anywhere reports that it changed.

### 3.6 A board is not a notification channel

A large shared file is read from the end. An entry written yesterday is, in practice, invisible.

**Do:** if something must reach a specific session, send it to them directly **and** append it
to the record. If it must reach the owner, it goes in the decisions register as well.

**Otherwise:** you satisfy the ritual of writing it down and still nobody acts on it.

⚠ **Across machines there is nothing to send it to directly** - no `SendMessage`, no roster -
so the board is all you have, and it has to be polled. Give it a fixed, machine-greppable
section header so a poll can recognise a new entry, and treat a quiet board as a permissions
hypothesis first: `cross-machine.md` Part 1.1, 1.5, 1.6.

### 3.7 The most dangerous artefact is the one with no owner

When several sessions are told to produce one thing, the first file to appear often has no
owner - somebody created it, nobody claimed it. Everyone then either avoids it (and it stays
half-finished) or edits it (and they overwrite each other).

⇒ **Whoever creates a shared artefact claims it in the same action.** If you find one with no
claim, do not adopt it silently and do not quietly work around it: **say on the record that it
has no owner and ask the creator to claim it.**

### 3.8 Two sets of rules can both be correct and still leave a hole

A coordination file said "do not edit the main artefact". The main artefact's own header said
"any session may claim a section and fill it in". Both were written in good faith, minutes
apart, by people solving the same problem.

🔑 **Two rule-sets coexisting unnoticed is worse than one being wrong.** A wrong rule gets
argued with. Two right ones get silently followed in opposite directions.

⇒ Before writing, **read the artefact you are contributing to, not only the instructions about
it.** If they disagree, that disagreement is the first thing to report.

⇒ The same shape hits section numbering: when one plan numbers sections `1..8` and the artefact
numbers them `A..H`, **build the mapping table before anyone merges.** One such pair had two
sections with no counterpart - following either scheme alone would have dropped them, and
nobody would have been notified. Nobody made a mistake; nobody had compared.

### 3.9 Removing or renaming a shared location is an announcement, not housekeeping

Somebody standardising on a new convention empties a directory others are still writing to. The
cleanup is harmless in itself; what it leaves behind is a **true-at-the-time observation that
outlives its truth**, and everyone who formed an explanation from it stops re-checking.

⇒ Say it where the others read. ⇒ Use an operation that cannot destroy, and say which one: a
command that refuses to act on a non-empty directory proves by its own semantics that nothing
was lost, which is worth more than remembering that it looked empty.


### 3.10 When you split a section, leave a pointer where it used to be whole

Merging often means one contribution's single section becomes two places in the product,
because half of it belongs with somebody else's material.

**Do:** at each half, name where the other half went - the file and the section, not the
directory.

**Otherwise:** a reader arriving at either half cannot tell whether the rest is elsewhere or
was dropped, and neither can the person who wrote it. Measured: the author of a section that
had been split this way said the pointer made both halves readable on their own, where their
original could only be read end to end.

⚠ This is the same reason a pointer is not a second copy. A pointer cannot drift into a
different answer; it can only reveal an absence.

⇒ And when the material you split was written by somebody else, the split itself needs their
review: see `verification.md`, *Verification has a third layer*.


### 3.11 A rule you just wrote has not been applied to what you already did

Adding a rule feels like the work is done. It is not: everything finished **before** the rule
existed is still in its old shape, and nothing will flag it.

Measured, in the writing of this file: a rule saying *"when you split a section, leave a
pointer where it used to be whole"* was added - and the split its own author had made an hour
earlier had no pointer. It was found by a reviewer, not by the author.

**Do:** when you add a rule, immediately sweep the work already done for places it applies,
and say which ones you checked.

**Otherwise:** the rule reads as though it has always been in force, and the exceptions that
predate it are indistinguishable from compliance.

⚠ The author is the person least able to spot this, because they believe the rule is now in
effect - they wrote it. Expect a reviewer to find it, and make that easy rather than treating
it as an oversight.

### 3.12 A habit you never wrote down is not a rule

The mirror of 3.11. A step you have always taken, reliably, for good reasons, **does not exist
for anybody else**. The next person does not inherit it, cannot follow it, and has no way to
know it was ever part of the process.

Measured: a reorganiser handed every rearranged section back to its author for review, every
time, all evening - and never wrote that step down. It reached the deliverable only because
somebody else noticed the habit and said so. Until then it was one person's practice, and it
would have ended with them.

**Do:** when you notice you have been doing something consistently that is not written
anywhere, write it down **then**, not at the end.

**Otherwise:** a good practice keeps working right up until the person who has it stops, and
nothing reports the gap - the process looks unchanged.

⭐ **A good habit that never becomes a rule is, for everyone downstream, the same as no habit
at all.**


### 3.13 Cross-file duplication is the kind nobody finds by reading

Two sections restating one rule inside **one** file get noticed: somebody reads the file
end to end and sees them. The same pair split across two files does not, because nobody holds
both files in their head at once - least of all the person who merged them.

⇒ **Before removing any duplicate, scan every file with a tool. Do not decide by reading.**
⇒ **Decide which copy to keep only after seeing all of them** - a rule that appears twice in
front of you may appear a third time somewhere you did not look.

Measured on one merged document:

```
by instrument   5 duplicated pairs, 3 of them spanning two different files
by reading      2 pairs, both inside a single file
```

⚠ The failure that produces this is subtler than missing a pair. Someone compared two copies
**inside one file**, chose which to keep, and gave advice - while a third copy of that same
rule sat in another file. Following the advice would have left two. **The error was treating
the range searched as the range that exists**, which is the same shape as declaring something
absent after looking in one directory.

⭐ The author of that advice found and withdrew it themselves. That is the useful pattern: the
person who narrowed the scope is the only one who knows how narrow it was.
