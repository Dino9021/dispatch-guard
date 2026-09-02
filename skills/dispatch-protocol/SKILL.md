---
name: dispatch-protocol
description: Use BEFORE dispatching any sub-agent, planning a multi-agent wave, opening a task folder, or deciding whether there is enough usage budget left to continue. Covers task layout on disk, how many sub-tasks may run at once, what every prompt must contain, and how to read GO/PACE/STOP.
---

# Dispatching sub-tasks

A hook enforces the load-bearing parts and refuses the tool call — a refused dispatch is
the rule working, not a bug. Full mechanics and the honest enforcement gaps:
`../../PROTOCOL.md`.

## Task layout

Make your task folder inside the declared `task_root` (default `<repo>/Memory/tasks/`,
created by the gate at session start — do not pick another location or ask): 
`<YYYYMMDD-HHMMSS-task-name>/`, timestamp with hours-minutes-seconds. Everything the task
produces goes there: `prompts*.md` (every prompt, BEFORE any dispatch), `progress.md`
(written by the gate), `agent-NN-<subtask>.md` reports, external-model captures, handoffs.
The filesystem is the handoff — chat output dies with the session. Never write a
credential, key, token or machine identifier into a folder that gets committed.

## Scratch files

**Every intermediate file a sub-task writes goes under its own directory in the task folder:
`<task_root>/<task>/scratch/<NN-agent-or-purpose>/`.** Probes, captured command output, half-
built scripts, downloaded pages, generated fixtures — all of it, and named for the sub-task
or the question it belongs to.

⛔ **Not the system temp directory, not the repository root, and never a path two sub-tasks
share.** Two agents given "somewhere temporary" pick the same place, and the second one wipes
the first one's evidence — so the run that failed is the one whose files are gone. Measured in
this repository's own checks, where every child process cleared a shared scratch directory on
startup and only the LAST one's files survived a full run.

⭐ **Leave them after the sub-task finishes.** They cost nothing and they are the only way to
answer "what did that agent actually see?" after it is gone. The task folder is deleted or
archived as a unit; scratch does not need its own cleanup.

⚠ **Say the path in the prompt.** A sub-task cannot infer it, and an agent told only "write
your report to X" will put everything else wherever it likes. Gitignore the scratch path if
the task folder is committed.

## Choose the model BEFORE you dispatch

Pick the cheapest model that can do the unit. `max_model_price` (default **5**) is the most a
sub-agent's model may cost in US dollars per million **input** tokens, and a dispatch above it
is refused — so decide here, not after a refusal.

⭐ **The prices are deliberately NOT written into this file.** A table typed into a skill goes
stale until somebody ships a plugin update, and this repository shipped exactly that defect —
its typed-in table overcharged Claude Haiku 3.5 against the published price for months. The
live table is parsed from Anthropic's published pricing page into `model_pricing.json` and
refreshed in the background.

⇒ **It reaches you before you choose, two ways, with no lookup:**

- the **session's opening context** names the families you may dispatch and the ones you may
  not, with their current prices;
- **rule 7 of the block prepended to every sub-task prompt** carries the same list, so an
  agent that dispatches further is bound by the same numbers.

To read the whole table yourself:
`bash <plugin>/hooks/run.sh <plugin>/hooks/model_pricing.py --show`

⚠ A family is not one price. Naming an **old version** can cost several times what naming the
family costs — the retired opus is three times the current one. Prefer the bare family alias.

⛔ `best` resolves to **fable**, the dearest selectable family. `opusplan` resolves to opus. An
`[1m]` suffix does not change the price. `mythos` is priced but no session can select it by
alias. **Omitting `model` is always allowed** and inherits the session's model — that is the
safe default, and it means there is always a legal dispatch.

⚠ If the opening context says no price table is readable, the ceiling is **not being enforced**
that session. Do not report it as active.

## The six refusals

1. **Two dispatches at once.** Sequential needs no permission and is the default;
   concurrency needs the owner's approval recorded as `PARALLEL-APPROVED` in the task
   folder, stating the count as `parallel N`, `N=<n>` or `平行N` (bare integers are not
   accepted).
2. **Background dispatch** — it escapes the accounting entirely.
3. **Dispatching before the plan is on disk** (`prompts*.md` newer than session start).
4. **Any mass-spawn tool.** No approval path.
5. **Dispatching when usage says STOP.**
6. **A model above `max_model_price`** — see the table above. Do not raise the limit; it is
   the owner's setting.

Three ways agents talk themselves past rule 1 — none is an exception: "it is only a
review" (**two reviewers is two dispatches** — the second reviewer waits); "this case is
special" (only a literal count in an owner message is approval; "do them together" is a
request, not an approval); "I'll background it and collect later" (refusal 2).

**An approved N means N ALIVE AT ONCE, run as batches of N** (dispatch N, wait for all N,
next batch — not a rolling window). Approvals expire (60 min default) and are scoped to the
named task folder.

**Asking for a count:** write the plan and prompts, tell the owner the total and that they
can approve a count, then **start sequentially immediately** — never stall waiting.

## Every prompt

1. **Stands completely alone** — the agent has none of your context; every path,
   constraint, and acceptance criterion in the body.
2. **Ends by naming its output file** under the task folder (also how the gate finds the
   right plan).
3. **Requires the report to be written AS THE AGENT GOES** — create the file first, append
   each finding. An agent that dies before its final write produced nothing.
4. **Names the `subagent_type` AND the capability this prompt needs from it** —
   `type: general-purpose  ← needs Write: this prompt requires it to create its own report`.
   The type name alone carries no information; the capability clause cannot be written
   without checking that type's tool list first.

⛔ **Rule 3 is only a rule for an agent that HAS a way to write.** Measured 2026-08-31: a
round-2 ADR review was dispatched as `Explore`, a read-only type. It could not create its
report, so it returned the whole review as its final message — and its verification table and
five of its findings were **permanently lost**, because they sat in an intermediate turn the
dispatcher never received. The dispatch named the model and never the type, so the mismatch
had nowhere to become visible.

⚠ **Do not trust a list of read-only types typed into a file** — agent types are user- and
plugin-defined (`.claude/agents/*.md` frontmatter, SDK `agents`), so any snapshot here rots
and then lies. Read the tool list the session declares for that type. A type carrying only
`Bash` writes through the shell and is fine.

⭐ **The gate now checks this for you, and it is the half that holds.** When a sub-agent
returns, the gate stats the files its prompt told it to create and says so if one is missing —
it needs no knowledge of any agent's tool list, and it also catches an agent that *could*
write and did not. ⚠ **Advisory, not a refusal**, and its prompt-reading is a conservative
regex: a phrasing it does not recognise is silently missed, so `ls` the file yourself when the
answer matters. If an agent returns content that belonged on disk, transcribe it verbatim into
the task folder in the next turn, and say **in the file** that it was transcribed and what is
missing.

## Usage: act on the word, never the numbers

Run `<plugin>/hooks/usage.py --verdict` before a wave. **GO** = dispatch freely. **PACE** =
finish what is in flight, no new wave. **STOP** = wrap up, write `HANDOFF.md`, arm a resume
(both routes the gate prints), end the turn. **NO-DATA** = report usage as UNKNOWN, never a
number. Never compute headroom from raw percentages.

⭐ **The same line also says WHEN the window is spent at the current rate** — `⛔ At the
current rate the 5h window is SPENT in ~N min - M min BEFORE it resets. Plan for the gap, not
for the reset.` That N is your budget, not a forecast to note and move past: fit the remaining
work into it, and write the handover BEFORE it runs out, because the reset is M minutes further
away than the money. GO with a small N is still GO for the step you are on and STOP for a new
wave. Do not compute N yourself; act on the number the line prints.

## HANDOFF.md after a STOP

The only thing the next run gets (a transcript re-read costs ~95k tokens/MB with zero
cache; a 3 KB handoff ~800). Six sections: Goal (standalone) · Done (with every output
path) · Next step (nothing left to decide) · Tried and failed (with reasons) · Decided
(not to be re-litigated) · Every path, command and branch. No backward references; never
"continue the previous work". Then `resume.py --arm --task <task>`. The 200-character floor
catches EMPTY, not BAD — quality is yours.

## External model runs

The gate cannot see them, so this rule is kept by you: capture the prompt, the log, and the
output **verbatim** into the task folder (the supervisor captures — the tool cannot).
Record the verdict in `progress.md`, never by editing the output file.

## If you are the one who was dispatched

Do your unit at full quality — pacing is the dispatcher's decision, never self-throttle.
These rules bind anything YOU dispatch, at every depth; the same hook fires.
