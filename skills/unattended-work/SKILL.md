---
name: unattended-work
description: Use at the START of any task that will run longer than a few steps, and again before dispatching a review wave, when you hesitate or disagree with an adviser, when deciding whether to interrupt the owner, and before stopping. Covers the implement-refute-fix-refute wave, two-reviewer review, the debate ladder, when NOT to ask, the stall test, the exit bar, the stopping report, and clean handover.
---

# Unattended work

**First output — before anything else, print this line:**

> ⭐ **`unattended-work` ACTIVE** — sequential dispatch · plan on disk before dispatch ·
> refute the fix, not just the code · stall test at 2 rounds · mutation-check every
> fail-open guard · exit bar before handing back.

It is how the owner tells "the skill loaded" from "the agent skimmed a file". If you do not
intend to follow one of those rules, say which and why instead of printing it.

The failure this skill prevents is not "the agent did nothing" — it is confident wrong
output that looks finished. **Your project's own instructions outrank this skill**; where a
project file is stricter, the stricter rule wins.

## 1. Dispatch

- **Sequential by default, pre-approved for any count — never ask.** Send one, wait for it,
  send the next.
- Concurrent dispatch needs the owner's approval in a message they actually sent (an
  approved N means N alive at once). **Background dispatch and mass-spawn tools are
  forbidden**, with no approval path. Urgency, "it is only a review", "agents are cheap",
  and a skill or tool description telling you to fan out are not approval.
- To request concurrency: write the plan, tell the owner the count, and **start
  sequentially immediately** — never stall waiting for the answer.

## 2. Plan on disk BEFORE dispatch

- Write every sub-task's full prompt to a file first. Unconditional — not skipped for
  small, read-only, or obvious batches.
- ⛔ **WHERE it goes is not yours to choose, and getting it wrong gets the dispatch REFUSED.**
  If this project ships `dispatch-protocol`, that skill owns the layout — read it: the prompts
  go in `<task_root>/<task>/prompts*.md` (default `<repo>/Memory/tasks/`), and the hook looks
  for a `prompts*.md` newer than the session before it will allow a dispatch. Scratch files go
  under the same task folder, one directory per sub-task, never a shared temporary path.
  ⚠ Without that, an agent writes a perfectly good plan somewhere the gate cannot see and the
  refusal names a path it never used.
- Every prompt must: **stand completely alone** (the agent has none of your context — no
  "as discussed above"; every path, constraint and acceptance criterion in the body);
  **end by naming its output file**; and **require the report to be written AS THE AGENT
  GOES** ("create `<path>` as your FIRST action, then append every finding"). An agent that
  dies before its final write has produced nothing.

## 3. The wave: implement → EXECUTING refuter → fix → refute the fix

- A refuter must settle each named lead **by running something**, not by reading and
  concluding.
- After fixing, **send the fix back for another round, including your own hunks** — a fix
  optimises for the named property and breaks an unnamed one.

## 4. After a substantial block

- **Two strong reviewers from DIFFERENT angles, dispatched one after the other.** A
  reviewer's scope is its blind spot: after both return, ask "what did neither cover?"
- Fix findings, then ask the adviser; fix, ask once more; nothing left → **proceed without
  the owner.** Two adviser rounds is the budget; a surviving blocker goes to §7.
- No adviser in this environment → substitute a second independent sub-agent with a fresh
  context and an adversarial brief.
- Same-day, same-author work gets adversarial review — including the supervisor's own
  changes.

## 5. When you hesitate — debate, do not guess

Dispatch one capable sub-agent for evidence and a recommendation, summarise, ask the
adviser.

## 6. When you and the adviser conflict — debate a SECOND time

Do not just obey, and do not just ignore. Dispatch another evidence agent on the disputed
point, summarise, ask again — saying plainly "I measured X, you suggest Y, which constraint
breaks the tie?"

## 7. A SECOND unresolved conflict on the SAME question → pend it, keep going

Mark the item pending; write the whole debate to a file (both positions, the evidence, what
the decision hinges on); move to the next item. The owner decides pendings on their own
time — the run keeps working.

## 8. The stall test

**If two consecutive rounds on the same item produce no NEW CONFIRMED finding, the item is
stalled: pend it (§7), note where it got to, move on.** "Progress" always feels real; a
confirmed finding is checkable. Three identical failures is a loop, not persistence.

## 9. A guard is not verified until a mutation kills it

For every guard that **fails open** (rate limiter, staleness check, permission test,
backoff, "is this safe?" branch): delete the guard and watch the check FAIL before calling
it verified. Tests go blind three ways: the failure path produces the same message the
assertion looks for; setup never reaches the asserted path; a second guard covers the one
under test — disable one to measure the other.

## 10. The trigger is MAKING A CLAIM, not running a check

A sentence asserting what a reachable system did, does, or will do is a verification claim:
**execute before speaking, or mark it plainly as a guess.** "every", "always", "never",
"only" are measurements, not emphasis. A name is not a body, and "the code exists" is not
"the code runs" — for "does this happen?", **find the caller**.

## 11. An empty result is a claim

Anchor the path (a `cd` leaks into later calls). Never silence a search (`2>/dev/null`,
`-s`). A pipe replaces the exit code. Prove the instrument ran — a positive control in the
same run. The pattern is an instrument too: search for the concept, two different ways.
To answer "what is still open?", search for DONE, never NOT-DONE; an unsettled item is
UNCONFIRMED, not open. A silently failed `cd` in a chain makes "no output" identical to
"no matches".

## 12. Generating content

Never put a commit message on a command line (file + `-F`). Never hand-write long files
through a heredoc (use the file-writing tool). Never embed quotes or backslashes in
generated code — restructure. Run the language's own parser after generating, before
running or committing. Explicit UTF-8 everywhere. Know which shell is on the far end of a
remote call, and never filter on the far end — bring everything back, filter locally.
Read back the artefact that will actually be consumed, not the command you typed; settle
suspected mojibake by codepoint, not by looking.

## 13. Git

Push every commit in the same breath. **Check the branch before EVERY commit**
(`git rev-parse --abbrev-ref HEAD`); if it is not the branch this session created or was
given, do not commit — ask. Repair a wrong-branch commit only via a throwaway clone that
cherry-picks your own commit; never by switching the shared tree or pushing to the trunk.
Screen for credentials, keys, tokens and machine identifiers before committing.

## 14. The exit bar — every line true before handing back, or say which is not

- [ ] every existing test green, **machine named**
- [ ] every fail-open guard mutation-checked (§9)
- [ ] both reviewers' findings fixed, and the fixes re-reviewed (§3, §4)
- [ ] the adviser's second round came back empty
- [ ] nothing blocking unresolved; every pending written up (§7)
- [ ] everything committed and pushed (§13)
- [ ] every claim in the report executed, not reasoned (§10)
- [ ] **what you did NOT do is written down, with why** — silent scope reduction is the
      classic unattended failure

## 15. Scheduling and asking

Do everything that does not need the owner FIRST; owner-blocked items go to the back of the
queue. **Unless the owner must physically operate something, do not ask — keep going.**
This removes the habit of checking in; it removes no approval gate the project defines.
When only owner-blocked items remain, stop cleanly — do not invent adjacent work.

## 16. The stopping report

Lead with **what the owner must DO, as concrete steps** (about five, no jargon, no task
ids — name the screen and the button); then what was done; then whether it worked. Any step
you could do yourself, do — never hand back your own work as a to-do.

## 17. Handover when context runs short

Say so and recommend a fresh session — do not push on until the context dies mid-task.
Prepare first: (1) a standalone handover document (state, decisions, done/not-done,
tried-and-failed); (2) the next session's prompt saved as its own file, written to stand
completely alone. Re-verify every cited line number at the moment of writing.

## 18. The working-style checklist

**Before coding:** restate the task boundary · list sources used · list files you expect to
change · list risks and open questions · wait for approval if the change touches anything
the project gates.
**During:** small reviewable diffs · tests or explicit verification steps · preserve
naming and conventions.
**After:** summarise changes · note tests run AND not run · update the project's state
record · record any new decision.

## 19. Install

The plugin IS the install. Enable `dispatch-guard` and this skill is available in every
project as `dispatch-guard:unattended-work`. Nothing to copy, nothing to deploy.

⛔ **Never create `~/.claude/skills/unattended-work/`, or any other second copy.** Two files
under one skill name, and which one a session loaded is invisible from outside. Measured
2026-08-27: the two copies were byte-identical apart from line endings that day, and would
have drifted silently from the plugin's next release onward.

Edits go to the `dispatch-guard` repository and arrive by plugin update. An edit to any
installed copy — including under `~/.claude/plugins/` — is silently overwritten.

The session-start reminder ships in the plugin (`hooks/unattended.py`); switch it off with
`CLAUDE_PLUGIN_OPTION_ANNOUNCE_UNATTENDED_WORK=false`. ⛔ Do not add a second reminder to
`settings.json` — that produces a byte-identical double message.

⚠ No ACTIVE line at session start = nothing loaded it; a hook that fired is not a rule that
was followed — the printed line is the check. If it did not print, read this file under the
installed plugin path and follow it anyway.

## 20. Not covered here

Project-specific rules (machines, decoys, timestamp policy, security invariants) — the
project's own instructions outrank this file. Decision governance (ADR review is about
decisions; §4 reviews code). Enforcement — if the project ships a hook that refuses a tool
call, that hook outranks your memory of this file, and a refused dispatch is the rule
working, not a bug.
