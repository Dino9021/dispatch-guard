# Work that outlives one context window

Open this before a handover, when a budget is running out, and before starting anything that
runs for hours or days.

---

## Part 1 - Handover

### Handover: when to write it, and why "it is findable" is not "it was handed over"

### 8.1 The handover is written before it is needed

A session can end without warning. **Keep the handover in a state where someone else could
continue from it alone** - not written at the end, because a forced stop gives you no turn in
which to write it. (The plugin's gate makes this a refusal: from PACE onward a dispatch needs a
current `HANDOFF.md` on disk - the `require_handoff_past_soft` switch in the plugin's config.
When your *context* is what is running out, `unattended-work` §17.)

### 8.2 What a usable handover contains

One live copy: **`dispatch-protocol`, "HANDOFF.md after a STOP"** - seven sections, WHO YOU ARE
first, and the `TAKEN OVER` line when you pick up somebody else's task. Three things its seven
sections do not name, so they stay here:

- ⚠ **Say what was deliberately NOT done, and why.** A handover that lists only state,
  decisions and done makes the next person read "deliberately not done" as "not yet done" -
  and then do it.
- For each thing done, **how it was verified** - a command or test the next person can re-run,
  not a sentence saying it works.
- For each decision, **who made it and on what basis** - a decision with no source reads as a
  suggestion, and gets re-opened.

### 8.3 What you schedule for your future self was written before today's lesson

Any "run this later" prompt, schedule, or to-do was written by the past you.
⇒ Each time you re-issue it, **correct the parts today disproved** instead of only appending.
📌 Measured cost: an instruction that misstated which file a defect lived in was re-issued four
rounds running; each round restarted from the same wrong place. Appending does not cancel an
error, it extends it.

### 8.4 "Findable" is not "read"

Filing something in the shared area, writing it on the board, putting it in the handover - all
of that guarantees **findable**, not **read**. A handover is no exception.

⇒ In practice: search the shared record for each waiting item before asking anyone.
⇒ The rule in full, and what it costs when it is missed, is in `owner-and-reporting.md`, 1.6.

### 8.5 Say out loud what you are dropping

When the verdict is STOP (what STOP, PACE and the burn figure each mean - and that PACE is *not*
a handover - is `dispatch-protocol`, one live copy), the remainder goes to the handover, and one
thing the handover must carry is **what you are dropping, said out loud**. **Work silently
dropped and work forgotten look identical from the outside.**

### 8.6 A deferral is a decision, and it has to be visible

"Next round" is acceptable, but say it each time, with the reason.
**When the same item defers a third time the problem is the ordering, not the budget** - put it
first next round, ahead of the routine work that keeps crowding it out.


### The written handover is the backup; a scheduled wake-up is not

A scheduled continuation is convenient and fragile: ordinary events - a new message, the
account changing, the budget window reopening early - cancelled it repeatedly, and **each time,
nothing announced that the schedule was gone.** ⇒ **What survives all of that is the file on
disk**, so the file is the thing that must be complete. The re-arming rule that follows from
this - at every turn's end, verified with `resume.py --status`, never assumed - is
`dispatch-protocol`'s, and since 0.58.0 the gate does it itself.

### A handover written for a future condition becomes a wrong instruction when the condition changes

A handover that says "paused until <date>, resume then" is correct when written and becomes a
false instruction the moment the reason evaporates — **and it reads perfectly normally.** Ours
went stale inside ten minutes.

⇒ **Mark it void in place; keep the original text.** Deleting it makes it look as though the
decision was never taken, and the decision was right when it was made.
⇒ **Read a running handover bottom-up, newest first**, and say so in the file itself.
⇒ After changing any rule about process, **sweep the open items for lines that describe the
old process.** A status line written minutes before a rule change can contradict it — we
produced exactly that inside a single commit: the rule and the now-false status went in
together.

### If somebody else will rely on it, put it where they can check it

When you do something others depend on, record it in the shared material, not only in a message
to one session. Otherwise the next person can only write "reported by X, I could not verify" —
and that is not them being cautious, it is you not having left anything checkable.

⚠ The mirror of this: **when a message fails to deliver, that is not evidence nobody took the
role.** An address that changed and a role nobody holds look identical from the sender's side.
Check the live roster before concluding the second.

---

## Part 2 - Background work that runs for hours or days

### Long-running background work: is it still alive, and who notices when it stops

Applies when a session starts something that runs for hours or days - a periodic check, a
polling loop, a long collection - and everyone else, including the owner, sees only its output.

### 9.1 "No alarms" is not a conclusion until you prove the instrument was still writing

The deadly property of this work: **a broken instrument reports good news.** A dead watcher and
a quiet system produce the same thing - no new messages.

⇒ Rule: before reporting "quiet", measure **whether the expected volume was written**.
```
every background job must know its own period (one pass per N seconds, M lines per pass)
 -> expected lines for this window = window length / period x lines per pass
 -> only if the actual count is the same order of magnitude is it "alive"
 -> a process still listed is NOT the same as a process still working: read the output, not the process table
```
📌 Counting processes is not enough. Measured case: the process was up, but the source it read
had been moved elsewhere, so every pass succeeded and every pass read nothing. It was quiet for
hours. **It was not broken - it was correctly answering the wrong question.**

### 9.2 An alarm must carry what makes it actionable at the moment it fires

An alarm that says "N things are wrong right now" without saying **which** is unusable: by the
time anyone looks, the state has often cleared itself, and the identity is gone for good.
Measured shape: a condition that released itself within the hour; two later queries both
returned zero; the alarm had been firing for two days and not one instance could be acted on.

⇒ Rule: **the identifier goes into the alarm text at the moment the alarm is raised**, never
"look it up afterwards".
⇒ Corollary: if the data was already in hand at sampling time and was not carried through, that
is an **actionability defect**, not a false alarm. Fixing it outranks adding new checks.

### 9.3 Three outcomes, and only one of them is "normal"

```
measured, value normal                          -> normal
measured, value abnormal                        -> alarm
NOT measured (timeout, refusal, source absent)  -> UNMEASURED, never counted as normal
```
"Could not reach it" and "it is broken" are separate buckets, and neither is clean. The output
must make clear which one happened.
⇒ The verification section has the general form of this: **"instrument suspect" is its own
verdict**, never folded into "clean" or "problem found". Long-running work is where it appears
most, because nobody is watching whether a given pass measured anything at all.

### 9.4 A threshold is measured, not imagined - and it expires

- Measure the steady state before setting a threshold. Alarming on "greater than zero" for a
  metric whose steady state is non-zero puts the noise straight back in.
- Baselines move with working hours, seasons, and equipment changes. **When quoting a baseline,
  state when it was measured and over how large a sample.**
- ⚠ Too short a sample manufactures false anomalies: the same data can give averages differing
  several-fold between a short and a long sample. Low-activity periods - nights, holidays - are
  the easiest to be fooled about. For "is this outside normal", **the historical maximum is a
  steadier test than the average**.

### 9.5 Reading undated output: never compare timestamps as strings

Much long-running output carries only a time of day. To take a subset of it:
```
⛔ do not filter with "time >= value" - across midnight or across days it silently returns another day's data
✅ walk backwards from the end of the file, stopping at the marker left by the previous check
✅ allow crossing one day boundary ONLY when the cutoff time is later than the current time
✅ do not start from "the clock now": the file may have been written a second after you read the
   clock, and that looks like a day boundary and ends the walk at zero
```
📌 This family of error occurred five times in practice, in both directions: sometimes it made a
problem appear that did not exist (another day's alarms read as new), sometimes it hid a real
one - and once it nearly caused a non-existent outage to be reported.
⇒ Worth writing the correct read as a fixed snippet and reusing it, rather than improvising it
each time.

### 9.6 Restart and survival: measure, do not assume

- Which artefacts survive an editor restart, a machine restart, and the end of your own session
  - **measure it; do not write it from memory**.
- The recovery procedure (how to bring each piece back, how to verify it came back) is written
  **before** it is needed, not during the incident.
- Until it has actually been used, label the recovery procedure **untested**. A written
  procedure is not a working procedure.
- Single-instance protection: count before restarting and count after. Two copies of the same
  job writing one output make that output **permanently unreadable as a sequence**.

### 9.7 Output that other people have to read

- Every line carries a full timestamp including the date, or the order cannot be rebuilt across
  a day boundary.
- The tool prints its own version on its first line of output. Otherwise nobody can tell which
  copy they are running, and the sentence "I already fixed that" cannot be disproved by anyone.
- An alarm carries its own next step (where to look, what to run), not just a status code for
  the next person to decode.

---

## Part 3 - Where the related rules are

This file's own budget and survival rules are 8.5 and 9.6 above. The rules about **planning**
against a budget before the work starts are in `coordination.md`, *Know the budget before
planning the work*.
