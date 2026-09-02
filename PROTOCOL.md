# Sub-task dispatch protocol

**The rules an agent must follow live in `skills/dispatch-protocol/SKILL.md` — one live
copy.** This file holds the mechanics around them: file conventions, what the hook
enforces, the honest gaps, and how resume works.

## 1. Files in a task folder

`<task_root>/<YYYYMMDD-HHMMSS-task-name>/` — `task_root` defaults to `Memory/tasks` under
the repository root; the gate creates it at `SessionStart`. Override with
`dispatch.task_root` in `config.json` or `<repo>/.claude/dispatch-guard.json` (`null` =
compatibility detection: first existing of `Memory/tasks`, `.agent-tasks`, `tasks`).

| file | contents |
|---|---|
| `progress.md` | one row per sub-task: agent, model, status (`pending`/`running`/`done`/`failed`/`delegated`), output path |
| `prompts*.md` | every sub-task's full prompt, written before any dispatch — each stating its `subagent_type` **and the capability that prompt needs from it** (`← needs Write: it must create its own report`) |
| `agent-NN-<subtask>.md` | one report per sub-task, numbered to match `progress.md` |
| `PARALLEL-APPROVED` | present only when the owner approved concurrency |
| `HANDOFF.md` | written on STOP; the resume's only input |

## 2. The approval file

Recognised forms only: `parallel <n>`, `N=<n>`, `平行<n>`. Anything else — including a bare
integer — approves nothing. **Do not relax the parser**: the first version took the first
integer anywhere in the file, so a record starting with a date (`2026-08-26 owner approved
平行2`) parsed as 2026 and nearly granted sixteen concurrent sub-tasks.

The file is not a barrier — an agent can always write one itself (it has). It makes the act
deliberate and leaves a trace: it **expires** (`approval_ttl_min`, default 60), it is
scoped to the named task folder, and each use logs one line
(`APPROVAL-USED n=… age=… says='…'`) — read that line to tell an owner-given approval from
an inferred one. Only a literal count in an owner message is an approval.

## 3. What the hook enforces

`hooks/dispatch_gate.py` runs on `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `Stop`,
`PostToolUse`, and binds sub-tasks at every depth (their dispatches hit the same hook).

| behaviour | mechanism |
|---|---|
| (N+1)th concurrent sub-task refused | N atomic `O_CREAT\|O_EXCL` slot claims, released on `PostToolUse` — **and on `PostToolUseFailure`**, which is the event a FAILED tool call fires instead (measured against Claude Code 2.1.251: same `tool_use_id`, and `PostToolUse` never arrives). ⚠ A dispatch that dies with no event at all keeps its slot until `slot_ttl_min` (default 30) reclaims it, and until then the refusal reads exactly like the rule working. Two such cases are known: the whole turn lost to an API error, and an `Agent` call with an invalid `subagent_type`, which fires **neither** terminal event while the turn carries on (measured 2026-09-02). ⭐ So the refusal names every holder, its age, and the minute it clears itself: the answer is to wait, never to delete a slot file. ⛔ And the refusal prints even when that note cannot be built — the note goes through `safe_held_slots_note()`, which logs `HELD-NOTE-FAILED` and returns blank, because a hook that crashes before it prints has ALLOWED the call (0.56.1 did exactly that with a huge `slot_ttl_min`). ⚠ Needs Claude Code **2.0.56** or later: an earlier build does not know `PostToolUseFailure`, and one unknown event name silences every hook of the plugin |
| background dispatch refused | `run_in_background` in the tool input |
| dispatch before a plan was written this session refused | newest `prompts*.md` vs session start stamp |
| mass-spawn tools refused | deny by tool name |
| dispatch refused at the hard usage threshold | the verdict |
| a resume is armed when a turn ENDS at PACE/STOP with a HANDOFF.md this session wrote | the `Stop` hook and every PACE/STOP `UserPromptSubmit` call `arm_from_handoff()`: the candidates are the task folders whose HANDOFF.md THIS session wrote — recorded on `PostToolUse` from the Write/Edit `file_path` or a Bash redirect (`state/<sid>.handoff-written`), never inferred from mtime (a `git checkout` gives every tracked file mtime=now; measured) — then `handoff_state()` must say "ok" (present, ≥ 200 chars, mtime ≥ the session stamp); no stamp or no recorded write → nothing, logged; the newest usable wins; `maybe_auto_arm()`'s guards (de-dup on `resume.json`, 300 s spawn floor, off switch) apply; one `systemMessage` names the folder and the wake time. ⚠ A PACE prompt KEEPS the alarm; a GO prompt cancels it (`stand_down_resume`) and clears the spawn floor so the next PACE turn end can re-arm. ADR `Memory/tasks/20260902-142400-auto-arm-on-stop/` |
| every dispatch refused until `dispatch-protocol` has been invoked | `require_dispatch_protocol`, default true; the `Skill` call is recorded on `PostToolUse`. `require_unattended_work` (default **false**) adds the second skill |
| a sub-agent's model costing more than the limit refused | `tool_input.model` priced with the catalog's published `pricing` tier, per MODEL — `max_model_price`, default **5** ($/M input), narrowed by the `availableModels` settings allowlist. ⭐ The same limit and table are in `dispatch-protocol` and in the injected block, so an agent reads them BEFORE choosing |
| a sub-agent returns without the file its prompt demanded → a note on screen and to the model | `guard_agent_report_file`, default true. The paths a prompt says to CREATE (a whole-word creation verb, then a `.md` path, within the same sentence **and** at most one line break) are resolved at `PreToolUse` and stashed in the slot; `PostToolUse` stats them. ⛔ **Advisory, never a refusal.** This half needs no knowledge of any agent's tool list, so it cannot go stale, and it catches an agent that COULD write and did not |
| a read-only `subagent_type` paired with a prompt that demands a file → a warning before it runs | same switch. A dated snapshot of the built-in read-only types, plus `tools:` read from `.claude/agents/<name>.md`; ⭐ **an unknown type says nothing at all**. ⚠ Names, not a rule derived from tool lists: `Explore` holds `Bash`, so a tool-list rule would have missed the incident this exists for |
| at PACE or STOP, one note on EVERY tool call — not only on a dispatch or a user prompt | `guard_wind_down`, default true. ⛔ **Advisory, never a refusal**, and once per level per agent (keyed by `agent_id`, because a sub-agent's payload carries the PARENT's `session_id`). It reads `usage.level()`, which is the verdict WORD without the burn projection — measured 0.471 ms against `verdict()`'s 28.99 ms. ⭐ It exists because the two places this used to fire from are both ABSENT from the kind of run that exhausts a window: measured 2026-08-31, 0% to 100% in 85 minutes with **zero** dispatches and no user prompt |
| a resume is armed even when the session never dispatched | the gate writes its own `HANDOFF.md` into `<state>/handoffs/<session>/` and arms against that absolute path. ⛔ **Into the plugin's state directory, never the repository** — `repo_root()` follows the shell's `cd` in a marker-less tree, so "one file" would have been N files in N directories. ⚠ It carries a banner saying no agent wrote it: measured, a 390-byte stub passes every mechanical check, so the banner is the only thing that tells a later session which kind it is |
| protocol reaches every sub-task prompt | the gate prepends it |
| every dispatch's outcome appended to `progress.md` | the gate writes it (append-only, never replacing the sub-task's own report) |

### Commands that fail silently

Same hook, same fail-open contract, **separate switches** — one key per guard, all defaulting
to `true`, read from the same places as the keys above (so `dispatch.*` in
`<repo>/.claude/dispatch-guard.json` sets them per project). Deliberately not one shared
switch: somebody will want the dispatch gate without the git gate.

| behaviour | key | mechanism |
|---|---|---|
| a `git commit` on a branch this session did not select is refused | `guard_commit_branch` | the branch recorded at `SessionStart` versus `git symbolic-ref` **now**, per commit — and matched anywhere in a compound command, because the measured failure was `A && git commit …` |
| `git add -A` / `.` / `--all` refused | `guard_add_all` | stage the paths you changed, by name |
| `git commit -m` refused | `guard_commit_message_file` | `-F <path>`; a message on the command line loses `()`, backticks and `::` to the shell |
| a search with its errors silenced is refused | `guard_silenced_search` | `2>/dev/null`, `2>$null`, `--no-messages`, and `-s` for grep only (for `rg`, `-s` means `--case-sensitive`) |
| the **first** dispatch is refused when `unattended-work` was never invoked | `guard_unattended_first` | the `Skill` call is recorded on `PostToolUse`; refused once, then allowed for the rest of the session |
| `cd <relative> && …` warned | `guard_relative_cd` | `additionalContext` with **no** permission decision — an `allow` from a hook would suppress the user's own permission prompt |
| unpushed commits older than the one just made are reported | `guard_unpushed` | `git rev-list --count @{u}..HEAD` on `PostToolUse`; advisory only |

State is **queried, never parsed out of the command**: the branch guard asks git which branch
HEAD is on, and the command string only decides which question to ask. Every decision is
logged — `CMD-DENY`, `CMD-WARN`, `CMD-ALLOW(checked=… off=…)`, `CMD-DISABLED`,
`CMD-GUARD-ERROR` — because "no denial appeared" and "no guard ever ran" must not look the
same.

The brake sits on the dispatch because a refused tool call is not advice a model can weigh
away. The gate never blocks because the gate itself broke: every failure path exits 0 and
logs to `.claude/dispatch_gate.log` (fallback `%TEMP%/dispatch_gate_error.log`).

## 4. NOT enforced — the honest gaps

| gap | what to do |
|---|---|
| no usage data = no brake | usually self-clears (the gate forks a background refresh); every session saying NO-DATA = the fetch is failing — run `usage.py --fetch-now` |
| a prompt naming no task folder gets only a loose plan check | name the output file in every prompt |
| a prompt naming several task folders passes if any has a fresh plan | a narrowing, not an exact test |
| the plan check is a timestamp, not a reading | it catches forgetting, not cheating |
| the gate is per session | deliberate; two sessions sharing one working tree is a separate hazard — give each a worktree |
| sessions started before the plugin was enabled are advisory only | self-heals next session |
| waking the live session (resume route A) can only be reminded, never enforced | act on the line `resume.py --arm` prints. ⭐ Route B (the OS task) IS enforced since 0.58.0: the `Stop` hook arms it for this session's fresh HANDOFF.md |
| the `Stop` hook does not fire on a user interrupt, and two sessions on one tree can each see the other's fresh HANDOFF.md | the next PACE/STOP prompt arms; two arms for one folder de-duplicate through `resume.json` |
| the alarm-cancel check runs only on `SessionStart`/`UserPromptSubmit` | an alarm can fire early inside a `PreToolUse`-only gap |
| the wind-down does not fire for a FAILED tool call | `PostToolUse` does not run for one. The gate does register `PostToolUseFailure` (since 0.56.1), but that branch only releases the dispatch's slot and records `FAILED:` in `progress.md`; it prints nothing, so the wind-down still does not fire there. ⚠ The note is on `PreToolUse` precisely so a failing loop still hears it, but a tool that fails after its `PreToolUse` produces no second chance |
| nothing prunes `<state>/handoffs/` | one small directory per session that reaches STOP without writing its own handoff |
| `NO-DATA` keeps the armed alarm | deliberate: not knowing is no reason to discard a backup |
| the full STOP→resume chain has never been staged end to end in one run | every stage measured individually |
| the command guards read a shell **string**, not a parsed shell | an operator or the words `git commit` inside a quoted heredoc can produce a false positive — the log names the command it refused |
| `git commit -a` / `-am` stages everything tracked and the add-all guard does not see it | `-am` is caught by the `-m` guard; a bare `-a` is not caught at all |
| `git -C <other-repo> commit` is judged against the branch of the session's OWN repository | the guard compares one checkout, the one the payload's `cwd` resolves to |
| the branch guard is satisfied by switching the shared tree | deliberate — a branch this session selects is legitimate; every switch is logged (`BRANCH-RECORDED`) |
| the relative-`cd` guard warns and never refuses | the shell's working directory persists between tool calls and the payload does not carry it, so the gate cannot test what the path will resolve against |
| the `unattended-work` check refuses ONE dispatch, then stops | otherwise a broken skill loader deadlocks the session; it is also silent when `announce_unattended_work=false`. ⚠ It is what asks for that skill by default, since `require_unattended_work` is false. Turn that on and this never fires — the hard rule answers first |
| the skill requirement CAN deadlock a session if the skill registry is broken | stated rather than hidden: that is what `require_dispatch_protocol: false` is for, and it belongs to the owner. The refusal does not name it, because a rule that names its own off switch gets switched off. ⭐ From the third refusal in a session the message names the other possibility — that the harness is not reporting `Skill` calls at all |
| the gate cannot tell an INVOKED skill from an ADOPTED one | the `Skill` tool call is recorded; whether the agent then followed the skill is not knowable from a hook. `unattended-work`'s own ACTIVE line is the second half of that answer |
| the demanded-file check reads a prompt with a REGEX, and a deliberately conservative one | a whole-word creation verb, then a `.md` path within 200 characters — the reach stops at the end of the sentence or after one line break, whichever comes first. A bare filename resolves against the dispatch's own task folder. ⭐ Measured against this repository's 18 real work orders: **19 paths, every one a genuine report file, no false positives**; the first version, which scanned line by line, saw two of eighteen. ⚠ Still missed: "Create **that file**" with the path named on an earlier line. That direction is chosen — a missed path costs nothing, a false alarm gets the guard switched off |
| an agent that writes its report SOMEWHERE ELSE is reported as missing | correct, and the note says the summary is unverified rather than that the agent failed |
| neither half ever refuses | deliberate. A read-only agent whose prompt merely names a path to READ is legitimate, and denying that would make the gate wrong more often than the dispatcher is |
| the read-only type table is a dated snapshot | `Explore`, `Plan`, `claude-code-guide`, `statusline-setup`, `feature-dev:code-{architect,explorer,reviewer}`, taken 2026-08-31. A type defined in `.claude/agents/` is read from its `tools:` line instead; anything else is UNKNOWN and warns about nothing. The `PostToolUse` half covers it regardless |
| the model ceiling sees only an EXPLICIT `tool_input.model` | a model pinned in an agent definition's frontmatter, or a `subagent_type` default, is invisible to the hook |
| an omitted model inherits the SESSION's model, whatever that is | deliberate — it is the model the owner chose; run the session below the ceiling if that matters |
| `subagent_type: "fork"` always inherits the parent model | a ceiling cannot lower it |
| a model this plugin has never heard of is refused, not ranked | the safe direction for a cost guard. ⚠ A model whose FAMILY is known but whose version is not is priced through its family, and the assumption is logged (`MODEL-PRICE-ASSUMED`) |
| a documented price table can drift from the enforced one | which is why `Tools/Debug/test_guards.py` asserts the skill's four rows against `model_price()` itself, including that each family's stated range tops out at its dearest model |
| the `[1m]` long-context suffix is stripped, not charged for | the catalog publishes one `pricing` tier per model and none for the long-context variant, and the harness's own accounting buckets a long-context request separately without multiplying its price — so there is no published number to use, and this gate invents none |
| a model the published page no longer lists is priced through its **family**, which can UNDERSTATE it | `claude-3-5-sonnet` and `claude-3-7-sonnet` were dropped from the pricing page when they retired. They price through `sonnet`, which is now $2, while their real price was $3. ⇒ Under a $2 ceiling they would pass. The assumption is logged (`MODEL-PRICE-ASSUMED`) rather than hidden, and the alternative — pricing an unseen version at the family's DEAREST ever — would refuse a genuinely new, cheaper model on its release day |
| the table records **base input only** | one model has many prices: batch is half, fast mode is $10/$50, `inference_geo:"us"` is ×1.1, Bedrock and Vertex bill separately, and prompt caching writes at 1.25×/2× and reads at 0.1×. The ceiling compares base input, and `model_pricing.json` says so in its own header |
| a model outside `availableModels` is NOT refused for that reason alone | Claude Code substitutes rather than failing, and every substitution is a step DOWN in cost — availability tightens the ceiling, it is not a second rule |
| the `model_access` entitlement from `GET /api/claude_cli/bootstrap` is not read | deliberate: a second endpoint with its own auth, for a list that `availableModels` already gives away for free |
| a command run in a session with no start stamp is advisory for these guards too | deliberate, and the same rule as for dispatch: installing an update must not start refusing commands inside a live session |

⭐ **THE LOG IS WRITTEN TWICE, AND THE SECOND COPY IS THE ONE TO READ.** `repo_root()`
walks up from the payload's `cwd` for `CLAUDE.md`, `AGENTS.md` or `.git`; a project with
none of the three falls through to the cwd itself, which the Bash tool's `cd` moves
between calls. Measured 2026-09-01: one session's log arrived as **four fragments in four
directories**, each with a stray `.claude/` beside it, and the hour that mattered looked
empty in the one place anybody would look. ⇒ Every line also goes to
`<state>/dispatch_gate.log`, which never moves.

**An absent denial is not proof the gate ran.** A log full of
`ADVISORY(no-session-stamp)` means it enforces nothing and looks identical to a log where
nobody broke a rule; `GATE-ERROR` lines mean it is failing open (a pre-branch `NameError`
once made it advisory in every session while all self-checks stayed green — the log was
the only trace; affected releases in [CHANGELOG.md](CHANGELOG.md)). When the answer
matters, read the log.

## 5. Resume after a STOP

Arm both routes; a heartbeat makes the OS-scheduled run stand down if any session was
active. On `SessionStart`/`UserPromptSubmit` the gate cancels an armed alarm when the
verdict is back to GO/PACE (early reset, or a changed account) and says so — repeat that
line to the user. If the account changed while an alarm is armed, its time is meaningless:
have the user run `resume.py --cancel` (`resume.py --status` shows `⛔ STALE`). The
transcript is a fallback, not a plan — the resumed run reads parts of it only when
`HANDOFF.md` leaves it unable to act.

## 6. Model choice and resuming a batch

Pick the cheapest capable model per sub-task; a cheaper model stretches the same allowance
across more sub-tasks. To resume an interrupted batch: read `progress.md` first — `done`
items are reused from their output files, `delegated` items checked for their file, only
`failed`/unfinished items re-dispatched, one at a time, no approval needed.

## 7. Fan-out skills

Some widely-installed skills and tool descriptions dispatch concurrently by design. This
protocol outranks them: the gate refuses the second dispatch and the skill stops part-way.
Recognise it — re-run sequentially or get a count — instead of debugging the gate.
