# Verification: what counts as knowing

Open this before claiming that something is true, before writing to a file others share, and
before building or trusting a checking tool.

A session that reports "done" without evidence is worse than one that reports nothing, because
the owner then stops checking.

**A broken instrument reports good news.** Fast and successful-looking is not proof. If a tool
cannot fail visibly, its silence means nothing.

---

## Part 1 - The baseline

### 1.1 Every claim about a live system is executed, not reasoned

One live copy: **`unattended-work` §10**. Not restated here - a pointer cannot drift into a
second answer. What several sessions add: it binds a **peer's** claim too - see
`owner-and-reporting.md` 2.9.

### 1.2 An empty result is a claim, so prove the instrument was alive

One live copy: **`unattended-work` §11**. Two items that are not there, so they stay here:

- A substring match is not a token match. Anchor on the real token, or settle it by
  codepoint.
- Before writing "there is no X", list the container first. Confirming existence costs one
  command; concluding absence needs the stronger instrument.

And the positive control is only the first of four - see Part 3, *Three controls, not one*.

### 1.3 A real hit can mislead as badly as a false zero

Two opposite shapes, both of which look normal:

```
a false ZERO   the filter, the encoding, or a truncation hid the hits   -> reads as "clean"
a true N       the hits are in another section, or from another day     -> reads as "done" or "on fire"
```

Never act on a count alone - look at *where* the hits are. A count without its context is a
number in search of a story.

### 1.4 A number you wrote down expires; a number you can recompute does not

Any figure copied into a document - a line number, a size, a threshold, a count - can be
falsified later by an unrelated change, and nothing will report it. Prefer a command that
recomputes it. Where a figure must be recorded, record **when and how it was measured** and
mark it as a measurement of that moment, not a current value.

### 1.5 Say which kind of "no answer" you have

```
UNKNOWN      you looked; the data does not exist or cannot distinguish
NOT-ASKED    a source exists; a decision was made not to look
UNCONFIRMED  partly looked; no conclusion yet
```

Collapsing these is how a question stops being asked: a later reader assumes it was settled.
This applies to numbers too - "no upper bound measured" is not "at least N".

---

## Part 2 - Writes that do not silently overwrite each other

**Verifying your own write by searching for a string is fail-open.** The string may be present
because of somebody else, another day, another reason. Measured against four scenarios (write
succeeded / failed, with and without older copies of similar text present):

| check | wrong in |
|---|---|
| whole-file count of the string | 1 of 4 |
| looking only at the tail you just wrote | 1 of 4 - **and it passes when the write failed**, the worst case |
| byte equality | 0 of 4 |

⇒ **Appending: `after == before + body`.** Read the bytes before, append, read the bytes after,
assert. It is short, and it is the only one of the three that never lied.

🔑 **It works because `before` is inside the equation** - one assertion proves both "the old
content was untouched" and "the new bytes are correct". Reading back and comparing against what
you *intended* proves only the second: whether the intention itself was right is not checked.

⇒ **Replacing needs five steps, no fewer:**

```
1. read the whole file as bytes                        -> before
2. assert the anchor text occurs exactly once          <- if not unique, stop; do not guess which
3. expected = derived from `before` by replacing it    <- derived, not assembled separately
4. read the file again; assert it still equals before  <- this is what stops another session's
                                                          edit between your read and your write
5. write; read back; assert bytes equal expected
```

⚠ **Step 4 shrinks the race window; it does not remove it.** This is not atomic.

⛔ **Do not "fix" that with a lock file.** A lock introduces a new failure mode: the holder gets
interrupted, the lock remains, and everyone else believes a write is in progress that is not.
Trading a mechanism that can overwrite for one that can wedge is not obviously a good trade.
Write the boundary down so the next person knows what the check covers - do not add a layer.
If a real overwrite is ever measured, reopen it **with that evidence**, not with this argument.

### Anchors: byte checks cannot catch a wrong intention

**Use a whole line or a whole block as the anchor, never the opening fragment of one.** Anchor
on an opening fragment and the new text lands inside the old line, splitting it - and the byte
check still passes, because the bytes really are what you asked for. What was wrong was the
request.

⇒ **After any structured edit, run a structural check** - count the sections, count the columns
in every table row, count the headings. **Byte checks catch a broken write; structure checks
catch a wrong target. They are complements, not duplicates.**

### Proving you did not overwrite someone

Two directions, and you need both:

1. **From the version history** - a commit that only adds lines deleted nothing. If you had
   overwritten someone's line it would appear as a deletion.
2. **Ask the person who could have been overwritten** whether what they wrote is still there.

📌 **One direction alone is not enough to say "no harm done".**

⚠ And state the part neither direction covers: if somebody's edit was overwritten *before* it
ever reached version control, no history shows it. That gap is exactly what step 4 exists for.

---

## Part 3 - Controls, guards, and instruments that can lie

⚠ **The cross-machine instances of this Part live in `cross-machine.md` Part 4**, because they
only arise during a migration: a structured search that is blind to every ignored file, a
generated message silently corrupted into invisible control characters, a clean count whose
positive control crashed *after* printing it, and a marker-list check that measures the line
defining its own list. That file narrows one general preference stated elsewhere; it says
which case you are in.

### Three ways a mutation test lies

That a guard is not verified until a mutation kills it, and the three ways a test goes blind,
is **`unattended-work` §9** - one live copy, not restated here. Three things it does not say:

- **Mutate one token, not a block.** Deleting a block usually produces a syntax error, and a
  test killed by a syntax error has proved nothing about the guard.
- Extract the logic **from the written file** when testing it. Re-typing the logic into the
  test means the test checks the copy.
- If a test fails, suspect the test first. A harness that misuses control flow will report a
  correct file as broken - and that looks exactly like a real defect.

### Three controls, not one: each catches a different lie

A positive control proves the instrument is **alive**. It does not prove your rule matches the
thing you are hunting — and a rule aimed at nearly-the-right-shape returns a believable zero
while the positive control passes. Run all three in the same invocation:

```
POSITIVE   something you already know is present must be found
PATTERN    a synthetic probe built to have the TARGET SHAPE must trigger the rule you rely on
LOOKALIKE  innocent data shaped ALMOST like the target must NOT trigger it
NEGATIVE   a value that cannot legitimately exist must NOT be found
```

**The lookalike probe is the one that no other control can stand in for.** A positive control
asks only *does the rule catch the real thing*; it never asks *what else does it catch*. So a
rule can pass every other check and still be wrong in either direction:

```
too narrow   matches nothing at all          -> reports CLEAN     -> false calm
too broad    also matches innocent lookalikes -> reports problems  -> false alarm
```

Both survive the same positive control, because both catch the real thing — the second one
just catches more. ⇒ **Give every rule two probe fragments: one that must match, one that must
not.** Measured while writing this: a rule for identifiers written as "seven or more characters
from this set" also matched dates and byte counts, and passed its positive control throughout.

- **The pattern control is the one people skip**, and it is the only one that catches a rule
  looking for the wrong shape. "My search tool works" and "my search finds this" are different
  claims, and only the second one is the reason you ran it.
- **Build the probe out of fabricated strings, never out of real data.** A probe taken from
  real content only proves *this content contains the shape*; it cannot prove the rule
  recognises the shape, because the rule and the sample came from the same place.
- **Require every rule to fire, and read the result.** A control that reports "most rules
  fired" and is accepted as good enough is not a control. Measured, in the writing of this
  very section: a screening tool reported *seven of eight* and the seven was accepted. The
  silent rule was broken — it could not match anything at all — and two other people had
  already screened documents "clean" through it. **Keep each rule's probe fragment beside the
  rule**, so a rule cannot be added without one, and so the control fails loudly when a rule
  goes blind.
- **A control reports a binary, not a score.** "Seven of eight fired" reads like *nearly all*,
  and it is the wrong reading: the one that stayed silent is a rule that returns zero forever.
  Either every rule fires and the run continues, or it stops. Moving that from *somebody
  remembers to ask which one* to *the tool refuses to continue* is worth more than adding
  another rule.
- A verdict reached while one rule was blind is not wrong, but it is **unfounded** — re-run it
  after the fix and tell everyone who acted on the earlier verdict.
- **Before relying on somebody else's tool for your own conclusion, kill it once.** Change one
  rule so it can never match, keeping the syntax valid, and confirm the tool refuses to issue
  a verdict. This is not distrust: *will it stay quiet when it breaks?* is a question only a
  mutation can answer, and once your result hangs on that tool, its silence is your problem.
- **A guard needs two mutations, not one.** Break the thing it protects and watch the guard
  stop the run; then **remove the guard** and confirm the same breakage now slips through. The
  first shows a guard is present, the second shows it is what stopped you — without it, the
  run may have halted for an unrelated reason and the first mutation proved nothing. Two people
  each doing one half is enough, provided somebody says which half is missing.
- **Generate the negative sentinel fresh each run, and never publish its value.** A fixed
  sentinel is poisoned the moment it lands in an audit log, or in a write-up describing your
  own method. After that it matches, and the control fails for a reason that has nothing to do
  with the data you were checking.
- When a control fails, the correct outcome is **instrument suspect**, reported as its own
  result — distinct from both "clean" and "problems found". Collapsing it into either one is
  how a broken instrument gets quoted.

### A change to a classifier has collateral in the categories you were not watching

When you fix how something is judged, **every category it can emit moves**, not only the one
you were fixing.

- **Look at every output category before quoting any of them.** A suite of checks that all
  assert the same category will pass in full while a different category silently fills with
  items nobody has read. If your controls only ever assert one side, they are not checking the
  change — they are checking your intention. Publishing the other categories' numbers under
  the words "all checks pass" is then literally true and completely misleading.
- **Score a candidate fix over the whole corpus, as recovered versus newly misjudged.** A fix
  is perfect on the examples that made you notice it — that is *why* you noticed it. A fix that
  recovers two items and misjudges two is not an improvement, and nothing in the examples in
  front of you can tell you which it is.
- **When you loosen a rule to catch more, name the new direction it can now be wrong in, and
  add a probe for that direction specifically.** Widening a detector always creates a way to
  fail that the narrow version did not have, and it is usually the fail-open way.
- A sound general lesson can still produce a wrong specific conclusion. Keep the lesson;
  re-run the measurement. **Never let a lesson overturn a result on its own authority.**

### Re-checking a suspect instrument must not change what is being compared

On finding that a measurement used a flawed instrument, the instinct is to go and examine the
instrument — and in doing so the question quietly changes, most often from *A versus B* into
*B versus B′*. The new question gets answered correctly, and the original finding is overturned
by something that never addressed it.

- **Write the two sides down again before re-measuring, then check that your new command still
  has those two sides.** It costs one line and it is the whole defence.
- Beware the shape where the flaw you found turns out not to matter: discovering that two
  candidate sources are identical proves the choice between them was irrelevant — that is not
  evidence about the original comparison at all.
- When the thing under test is itself a tool, **exercise that file**, not a re-typed copy of
  its logic (see the item about extracting logic from the written file). A copy is a different
  instrument, so agreeing or disagreeing with it proves nothing about the one in use.

### A byte check proves the write, not the intent

Comparing bytes catches a write that went wrong. It cannot catch a write that went exactly as
instructed to **the wrong place** — when the anchor or target was chosen wrongly, the bytes
match the expectation perfectly, because the expectation was itself wrong.

- Pair the byte check with a **structural check on the result**: the count of sections, the
  presence of each expected heading, the total still parsing as its own format.
- The two are complementary, not redundant. One asks *did my write land intact*, the other
  asks *is the thing I produced still the shape it is supposed to be*.
- The format's own parser is the cheapest structural check - `unattended-work` §12 already
  says to run it after generating, before anything consumes the result.

### A tool's output must answer "which copy am I, and how wrong might I be?"

Two copies of a tool that produce identical output **cannot be told apart by anyone running
them**. A fix present in only one of them can then be claimed and never disproved — not because
anyone lied, but because no observation distinguishes the copies.

- **Print the tool's version, and the size of whatever it just measured, on the first line of
  its output.** Not only in a header comment: the header is read by whoever edits the tool, and
  the problem belongs to whoever *runs* it.
- **If the content changes, the version changes — even when the behaviour does not.** Two
  different contents under one version number is exactly the defect this rule prevents.
- **Print the known error bar beside the number, not in the documentation.** A figure leaves
  its source immediately and then travels alone; whatever qualifies it has to travel inside the
  output.
- Where you measured a limit and decided not to fix it, record *measured — tried — why not*, in
  the tool. That is the only thing that lets a later reader tell a **bounded** instrument from
  an **unexamined** one, and that difference decides whether they re-check it.
- **A verdict carries the state of the instrument that produced it.** Which version, and which
  controls were actually passing, are part of the result, not background. So re-running a
  check after fixing the instrument is a **new measurement** — it does not retroactively found
  the old verdict, even when the answer is identical. Say that plainly rather than letting
  "same result" be heard as "no harm done".
- ⚠ **A rule of this kind, written down for one artefact type, silently fails to reach the
  others.** Where a rule is filed determines who thinks to apply it. If the rule is "the thing
  must say which version it is", it governs anything whose output somebody acts on — and
  somebody has to go and say so, because nobody re-reads a rule to check its scope.


### Make the categories check each other: a partition control

When a check sorts things into buckets - found / mapped / missing, pass / fail / skipped,
clean / hits / instrument-suspect - **assert that the buckets add up to the number of items
read.** One line, and it is a different question from any of the per-bucket assertions.

- Reading each bucket tells you whether that bucket looks sensible. It cannot tell you that
  an item was counted **twice**, or that one fell through every branch and was counted
  **never**. Only the total can.
- Measured, while merging the document you are reading: a checker's `if / elif` chain was
  edited into two independent `if` statements. Every item it had already matched fell through
  the second chain as well and was reported missing - **63 false alarms, from a correct
  merge.** The buckets summed to 177 out of 100 items read. The partition control would have
  printed that on the first run.
- ⭐ The general form: **the relationship between a classifier's outputs is a control, not
  just each output on its own.** Where the outputs are supposed to partition the input, say
  so in an assertion rather than in a comment.
- ⚠ And when a check fails, suspect the check before the subject. In that incident the merge
  was never wrong; the instrument was.


### Checking that nothing was dropped: your own query is an instrument too

When you search a merged or rewritten document to confirm a particular point survived, **a
query that does not match and a point that is genuinely missing produce the same output.**

- **Search with at least two different patterns**, worded differently, before concluding that
  something is absent.
- **Run a positive control in the same pass**: a string you are certain is present, with its
  hit count printed. Measured while checking this very document: a searcher looked for a
  phrase as they remembered writing it, got zero, and was about to report the point as lost -
  the text said something slightly different. The second pattern found it.
- ⭐ The general form: **the person verifying a merge is running an instrument, and it can be
  wrong in exactly the way the merge is being checked for.** Treat your own search the way
  you would treat any other measurement.


### How bad a defective check is depends on which way it pushes you

A broken instrument reports good news - but not always. The same defect can be harmless or
dangerous depending only on what it outputs when it misfires.

Measured: two people checked the same merged document within an hour, and both made the same
mistake - searching for a point using the wording they remembered writing, rather than the
wording on the page.

```
one  remembered wording -> zero hits    -> "that point was dropped"   sends you AWAY from the file
one  remembered wording -> reports MISSING, which they then go and read   sends you TO the file
```

Neither was more careful than the other. **One design turns the mistake into a false
conclusion; the other turns it into a trip to the source.**

⇒ **When you build a check, ask what it prints when it is wrong, and prefer the version that
makes someone open the thing.** ⚠ This is not licence to make checks noisy - a check that
cries often trains people to ignore it, and that costs more than it saves. The aim is a check
whose *failure mode* points inward, not a check that fails more.


### A wrapped line turns a whole-sentence search into a false zero

Searching a document for an entire sentence fails whenever that sentence is **wrapped across
lines** in the file - the text is there, the pattern spans a newline, the count is zero, and
zero reads exactly like deleted.

Measured, while someone was checking that nothing had been lost from a rewritten document: two
points were about to be reported as deleted. Both were present; both sentences wrapped.

⇒ **Search for a fragment short enough that it cannot be broken by wrapping.**
⇒ **Before acting on a zero, check whether the phrase you searched for spans a line in the
original.**
⚠ This is the same family as any other false zero, with one difference worth knowing: the
document being checked is usually the one that was just reformatted, so wrapping is more
likely here than anywhere else.


### A threshold is calibrated against a known case, never chosen by feel

Any check with a cut-off - a similarity score, a size limit, a staleness window, a confidence
level - silently defines what it will never report. **A threshold picked because it sounded
reasonable has never been tested against anything.**

⇒ **Feed it a case you already know it must catch, and require that case to come back.** When
it does not, do not lower the threshold by feel: **measure what that known case actually
scores**, and set the cut-off from the measurement.

Measured: a duplicate-detector was set to a cut-off that felt right, and its positive control
failed - the known duplicate did not come back. Measuring it showed the known case scored well
below the cut-off. With the threshold corrected, the tool found **three more duplicates than
anyone had found by reading**. Without the control, it would have reported "no others", and
that answer would have looked complete.

⭐ Same family as the partition control above: **both make the instrument prove its own
settings, instead of asking people to trust them.**


### Verification has a third layer, and only the original author can do it

```
layer 1   bytes equal            catches a write that went wrong
layer 2   structure              catches a write that went to the wrong place
                                 (section count, every heading present, tables still square)
layer 3   the original author    catches "every word is present, but which rule is now the
                                 reason for which has changed"
```

**Layers 1 and 2 both pass on a layer-3 defect.** Rearranging somebody's material can keep
every byte and every heading and still break what a sentence was *for* - the reason attached
to a rule, the ordering that made one clause the justification of the next.

⇒ **After reorganising material somebody else wrote, hand it back to them and mark it
`UNCONFIRMED` until they say it survived.**

⚠ Nobody does this layer by default, and the reason is symmetrical:

- **the person who reorganised cannot do it** - they hold the text, not the intent behind it;
- **the author will not do it unprompted** - they assume the reorganiser already verified,
  and the reorganiser *did* verify, just not this layer.

⇒ **So handing it back is the reorganiser's job, not a favour the author is owed.** It is a
step in the process, not something to do if there is time.

⭐ Measured, in the making of this file: the only defect that survived every other check was
found this way. A cross-reference between two halves of a split section had been lost; bytes
matched, structure matched, screening was clean, and it was invisible to everyone except the
person who had written the two halves as one.


### A measurement states what it did NOT cover, in its own output

Saying what you measured is not the same as saying what you left out, and a reader cannot
derive the second from the first. "Compared 93 sections" gives no way to tell whether the
working notes, the drafts or the tools were among them.

⇒ **Print the exclusions beside the result**, every run, in the output itself - not in the
documentation, which travels separately.

Measured: a duplicate detector was pointed at a whole directory and reported 35 pairs. Thirty
four came from the shared working record, which **restates things by design - that is what it
is for**. The count was correct; the question it answered was one nobody had asked; and the
single pair that mattered was buried in it.

🔑 Same family as an instrument that is right about the wrong subject, with a different
remedy: **narrowing the scope is only half the fix - the other half is saying out loud what
the narrowed scope now excludes.** Otherwise the next reader inherits your scoping decision
without knowing it was made.


### Checking conformance to a convention: measure the convention first

A tool that asks *"does this document follow convention X?"* encodes your belief about what X
looks like. If the document uses a different-but-equally-valid form, the tool measures a shape
that is not there and **reports confident, specific defects that do not exist**.

⇒ **First measure which form the document actually uses. Then write the rule.** Not the other
way round.

Measured: a checker for cross-references assumed they would name a bare filename. The document
wrote them as a path. The checker reported that one whole file was never referenced, and that
four references were malformed. Both were false: the file was referenced twice, and the four
"malformed" ones were a table of contents, where naming the file alone is correct.

🔴 **Where the probe must come from is the opposite of the leak-detector case, and the reason
is worth holding onto:**

```
detecting a SHAPE that must not appear     probe FABRICATED
   (a leaked identifier, a forbidden form)  a probe cut from the real text only proves the
                                            text contains the shape, not that the rule knows it

checking CONFORMANCE to a convention       probe TAKEN FROM THE DOCUMENT
   (do the references look like X?)         a fabricated probe proves only that the tool
                                            agrees with the author's assumption about X
```

⚠ These two look like a contradiction and are not. **Ask what the control is protecting you
from**: in the first case, from a rule that cannot see a real instance; in the second, from a
rule that is looking for something the subject never does. Do not cite either one to skip the
other.

⭐ And the hardest case to catch: **a tool that has just succeeded is the one you are least
likely to doubt.** The checker above had, minutes earlier, found three real duplicates that no
human reading had found. Its next two findings were both false, and its record made them
believable.
