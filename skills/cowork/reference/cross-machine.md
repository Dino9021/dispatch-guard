# Cross-machine: two machines, two trees, two accounts

Written after the first migration where one session on the source machine and one on the
destination machine had to coordinate through a shared file. It went badly, and the reason
is the first section below. Both sessions kept independent records; where they hit the same
pit from opposite ends, this file says so — two independent sources on one failure is
structural, not bad luck.

Everything in the rest of `cowork` still applies. What changes across machines is that the
mechanisms the rest of the skill assumes — a session directory both sides can see, a peer
heartbeat, `SendMessage` — **do not exist**, and the ones you build to replace them can fail
in a direction that produces no error on either side.

---

## Part 1 - The channel

### 1.1 There is no cross-machine messaging. The board is a file, and it is not free

`SendMessage` and `ListAgents` see sessions on **one machine, one account**. Across machines
they show nothing, and "nobody is there" and "I cannot see who is there" look identical.

So the channel becomes files in a shared directory, reached over whatever the two machines
have between them. That works, and it costs: polling instead of events, no delivery
confirmation, and no built-in notion of "the other side has gone quiet". Build those in
deliberately (1.4, 1.6) rather than discovering their absence mid-task.

⭐ **Two layers, and the rest of this file assumes both.** The **board** is ONE shared,
append-only file for claims, turns and short status — the same record `coordination.md` 3.1
describes — and it is usable across machines only once both sides have PROVED they can write
it (1.2). **Content**, and any message with substance, goes in **one author-named file per
writer** in the same shared directory (`coordination.md` 2.7, and 1.5 below); nobody writes
into another party's file. "Read the board" therefore means: read the shared file, then list
the WHOLE channel folder, recursively, for new or grown files — check-ins live in `checkin/`,
and a peer's message may sit in a folder you did not expect (1.3). When a side cannot write the
board, it does not go silent — it falls back to its own file (1.5).

### 1.2 ⛔ MEASURE THAT YOU CAN WRITE TO THE BOARD BEFORE YOU DEPEND ON IT

**This is the one that cost the most, and it is first because everything else in this file
is worthless when it is skipped.**

What happened: the board was created by the source machine, over an administrative share, so
the file's owner and its permissions belonged to *that* side's account. The destination
session could **read** it and could not **write** it. The protocol told that session to
append its report and flip a field — it could do neither. The source session polled every
20 seconds and saw no change, forever, and read that as "the other side has not started
yet".

**Neither side got an error.** One was waiting; one was unable to answer; nothing in the
system distinguished that from work in progress. The owner eventually fixed the permissions
by hand. A silent deadlock between two agents that are both behaving correctly is the worst
failure shape in this file, because every instinct says "give them more time".

⇒ **Before the first real message, both sides write a dated "channel test" line and each
confirms it can see the other's.** Two writes and two reads. It costs one round and it is
the only thing that proves the channel exists in the direction you need.

### 1.3 The board must not live inside the thing being moved or changed

The board was in the root of the tree being copied. So the operation that needed the channel
was the operation that broke it — and mirroring options on copy tools will also *delete* a
destination-only file, taking the board with them.

⇒ Put the board somewhere **stable on both sides and unrelated to the task**. If it has to
live in one machine's filesystem, put it outside the work area. Never inside the tree that
the task rewrites.

⚠ **This assumes you CAN reach a path outside the tree.** Measured: it was possible only because
the source side happened to have administrative reach to the whole destination disk. When the
only share opened is the target tree itself, "outside the tree" does not exist - then use a
dedicated subfolder the copy is explicitly told to exclude, and verify after the copy that it is
still there and unchanged; or have the owner open a separate share for the channel. Decide the
channel's location BEFORE the move, with the owner, whenever the reachable paths are restricted.
A share opened FOR the channel is not the target tree: use its root, no subfolder. A subfolder
you do use gets a one-line pointer file at the root naming it - the root is where the other side
looks first.

⛔ **Look for a channel before you create one, and when two exist the one at the root wins.**
Measured: two sessions, one per machine, built a channel within about a minute of each other in
the same share - one in a subfolder it chose (following the paragraph above, which named only the
subfolder), one at the root - and each watched only its own. Both answered within minutes; neither
saw the other for twelve; one told the owner the other "has not replied". One look before creating
would not have been enough: that side HAD listed the root, a minute before the other wrote there.
⇒ Before creating, list the shared location recursively and join any board already in it.
⇒ Create at the root, and point your watcher at the root, whole tree (1.8) - never at the folder
you expect the answer in. ⇒ Keep listing the whole tree until every party has written on ONE
board. ⇒ Two boards: the one nearer the root wins without negotiation (same depth: the earlier
first entry). The other side announces the move in its own location and retracts every signpost
it left pointing there (`coordination.md` 3.9).

### 1.4 A channel has two directions and you must measure them separately

Measured on the failing day: destination → board was refused, and **source-tree ← destination
was writable**. The two sides had asymmetric access to each other and neither had checked.
One side finding itself blocked concluded "there is no channel", which was false.

⇒ Test both directions, name them separately in the result, and if one is blocked, use the
one that is not. "I cannot write to you" does not mean "you cannot write to me".

### 1.5 Content goes one file per writer; the shared board carries claims, and only if both can write it

⛔ **The standing rule predates this file and comes from single-machine practice, where it was
measured:** several sessions coordinate on ONE append-only board (claims, turns, short status —
`coordination.md` 3.1), but **each writes its CONTENT into its own author-named file**
(`coordination.md` 2.7). The day that rule was written it was also tested by accident: the
shared deliverable was lost, and the per-author files lost nothing. "One file per writer"
is worth more than "no overwrites" — it means the work survives the shared artefact.

The first cross-machine job put everything — claims, turn-taking AND the substance — into one
shared file, with a "whose turn" field at the top and later a "last section header decides
the turn" variant. Both are two-party designs, and both need the constrained side to WRITE
the shared file, which is exactly what it could not do. That was the 1:1 **workaround**,
recorded so it is not mistaken for the protocol. The owner ruled on 2026-09-22: cross-machine
work ADDS the permission and channel lessons in this file; it does not replace the
single-machine rule.

⇒ **Two layers.** Board: one shared append-only file, used only after both sides pass the
write-test (1.2). Content and messages of substance: one author-named file per writer, new
section per message, never an edit to anyone else's file.

⇒ **When a side cannot write the board, it speaks through its own file** — created by itself,
so its permissions are its own — and the protocol must say that readers **list the whole
channel folder, recursively, for new or grown files**, not only `cat` the board. A reader that
watches one fixed name never sees the message that had to go elsewhere — nor does one that
watches one folder.

⇒ **Topology does not change this.** 1:1, 1:N, N:1 and N:N all reduce to "one board for
claims, every writer owns its content file, an aggregator reads everyone's and writes only its
own". An extra participant adds a file, not a failure mode.

⚠ Where a side can create new files but not modify existing ones — a common permission shape,
since a directory can allow creation while its files deny writes — the per-writer layer already
copes: the next message is a new numbered file.

### 1.6 Each side creates its own file in a shared directory, and silence means permissions

File permissions usually follow the creator. So a file created by one side over the network
is, by default, a file the other side can read and not write — and with per-writer files the
question moves one level up: **can each side CREATE a file in the shared directory?**

⇒ Each side creates its own file itself, so it owns what it writes. The directory is the
thing to test: both sides create their channel-test file there (1.2) and **nothing else
proceeds until both files are visible to both sides.** If only one side can create, that side
also creates the other's file and grants it — and says so on its own file.

⛔ **A file created over an administrative share is read-only to every other account, even when
the other side CAN create files.** Measured on a second migration, one day after the first: the
source side created the channel folder and the shared board over the admin share; both got
`Administrators` as owner and `Users: ReadAndExecute`; the folder allowed `Users: CreateFiles`.
So the destination sessions could create their own files and could not append one line to the
board. ⇒ **The creator of any file the other side must write grants that side's account, by
SID, in the same step as creating it** (`icacls <file> /grant *<SID>:(M)`), and says so on the
board. Same for the channel folder itself (`(OI)(CI)`), so later files inherit it.

⇒ **Waiting past a few minutes is a permissions hypothesis, not a patience problem.** The
default reading of silence on a cross-machine board is "it cannot write", not "it has not
started".

### 1.7 Declare the split in the board's first message

Two machines each with a full checkout and a live session means both can edit the same file
and neither will see the other do it. Say in the first message who owns which paths; anyone
else does not touch them. Waiting time is then spent on what the board already says is yours.

Also post, once, each side's clock (`date`, to the second) with the channel test, so an offset
is known; every later stamp is a full minute read from the clock and names which machine's -
never an estimate like `11:3x`. Measured: placeholder stamps made two messages impossible to
order, and one stamp named a minute that had not yet happened.

⛔ **A promise to read the clock does not hold - build the stamp instead.** Measured on a later job:
five estimated stamps from two sessions, three of them written AFTER their author had promised to read
the clock for every stamp, the worst nine minutes in the future - and on an append-only board a future
stamp puts entries out of order for good. ⇒ Produce the stamp in the same command that appends the
entry: the text carries a placeholder, the append substitutes the clock. ⚠ Use a placeholder that
occurs nowhere else in the text - measured, the substitution also rewrote the sentence that explained
the placeholder (4.4's shape).

### 1.8 ⛔ Waiting for a peer is not stopping - arm a wake-up before you end your turn

A session acts only inside a turn. Between turns it runs nothing, and **nothing wakes it when a
file changes.** So "I am waiting for the other side" at the end of a turn means *asleep*: it
sleeps until a human speaks to it. Measured: one side wrote "waiting" at 11:45 and did nothing
more until the owner relayed "go" at 13:31; the other side had finished long before. Everyone
was waiting; nobody was watching; the owner was the only thing moving.

⇒ **Before ending a turn to wait for a PEER, arm something that will wake you:**

- **Peer on the same machine:** send it a message with `notify_when_idle` (or a pure
  subscription) - one notice arrives when it next goes idle. No polling.
- **Peer on another machine, or reachable only through files:** run the shipped watcher in the
  background - `pwsh -NoProfile -WindowStyle Hidden -File <plugin>/skills/cowork/tools/watch-folder.ps1
  -Folder <channel root> -Ignore "<your file>,checkin/<your role>.md,<observer file>"` (Bash
  `run_in_background`). `-WindowStyle Hidden` keeps a console window from popping up on the owner's
  desktop, where a stray click on its close button would kill the watcher silently; output and exit code
  are still captured. It watches the WHOLE TREE under the folder and skips any `.claude` folder; an
  `-Ignore` entry is a relative path or a folder. It exits when any file changes, and its exit wakes you.
  Re-arm it after every wake; it also exits after 55 minutes with no change - re-arm then too.
  ⛔ Through 0.69.0 it listed only the top folder - so it never saw a check-in, and two sessions that
  each said "watcher armed, recursive" were both watching one folder (1.3). Its first output line names
  its version, "(whole tree)" and the file count: **read that line before telling anyone what you watch.**
- Post **one** line on the board: `[time, clock][you] WAITING for <who> to <what>. watcher armed.`

Measured after adoption: one side finished, and the other side's watcher woke it and it acted
**about fifty seconds later, with no human in between.**

⛔ **And a wake-up with nothing for you writes NOTHING.** The first version of this rule said
"before you end a turn, post a WAITING line" - read literally, every re-wake is a new stop, so
every party posted "woke, nothing for me, re-armed" on every wake, and each such line woke every
other watcher. Measured with nine parties: four or five such lines every two minutes, all
content-free. ⇒ Post to the board only to claim, to report a real change of state, to hand over,
or to ask. Your earlier WAITING line stays current; re-arm silently. Watchers ignore your own
files - content AND check-in - and any observer's file. A check-in is rewritten only when a field
in it changed (`coordination.md` 2.8): with the whole tree watched, a needless rewrite wakes every
peer, and a peer that rewrites its own wakes you back.

⚠ **Waiting on the OWNER is different** - the owner speaks in your window, so stopping cleanly is
right there, with a line saying what you wait for. A watcher is for peers. (`unattended-work`
§15 says the same from the other side: a peer-blocked item is not owner-blocked.)

---

## Part 2 - What arrives is not what you can use

### 2.1 After a copy, the first check is "can I write", not "is the hash right"

A hash proves the bytes arrived. It says nothing about whether the receiving account may
modify them, and a tree that is bit-perfect and unwritable fails **every** subsequent step —
each with a different error. One session saw a version-control fetch fail on permissions, a
package install fail on a lock file, and build caches fail to write, and began diagnosing
three unrelated problems.

⇒ **Sample N existing files, open each for writing, and create one file of your own as a
positive control.** Measured on the failing day: 0 of 40 existing files writable, own file
writable — so the instrument worked and the tree was the problem. That is a five-command
check that would have reframed the whole session.

⇒ Then report the result on the board as a number, not as "looks fine".

⚠ **A private key that arrives inherits its new folder's grants.** Measured: a key copied into the
user's key folder carried the parent's read grant for every local user, and the SSH client refused it
as an unprotected key file. Reset each key's ACL to the one account, and re-read it, before the first
connection.

### 2.2 A read-only tree does not look like a permissions problem, it looks like five bugs

Keep the list, because each of these reads as its own unrelated failure: version control
cannot write its own metadata · dependency installs cannot rewrite a lock file · compilers
and test runners cannot write caches · renames and deletes are refused while **creation
succeeds**, so the tree looks writable until you touch something that already exists.

⇒ When two or more tools fail differently right after a cross-machine copy, test permissions
before diagnosing any of them.

### 2.3 Copy tools do not carry permissions unless told to, and the destination's own
directory may be the source of the wrong ones

Two separate mechanisms, and confusing them sends the fix to the wrong machine:

- The copy tool may not be copying permissions at all (they are usually a distinct flag from
  data and timestamps).
- The destination directory may have been created by the *remote* side's connection, so it
  and everything under it inherits **that** identity — and a permission entry on the parent
  directory does not necessarily propagate downward.

⇒ Put the permission grant in the migration steps explicitly, run from whichever side has the
authority. **Refer to the destination account by its security identifier, not its name** — a
local account on one machine cannot be resolved by the other machine's name lookup. Have the
destination session read its own identifier and put it on the board.

⛔ **Do it BEFORE the first copy, at the root, and check the inheritance - not after, per
folder.** Measured: the same defect hit three times in two days (a first migration's tree, the
second migration's channel board, then its destination tree), and each time only the folder that
had failed was repaired. The root cause each time: the destination root was created over the admin
share, and the parent's grant for the destination account had no inheritance flags. ⇒ On the
destination, before anything is copied: list the destination root's ACL and owner, and the
inheritance flags of the parent's entry for the destination account; grant the account by SID with
`(OI)(CI)` on the destination root; then create one file there FROM THE SOURCE SIDE and confirm the
destination account can write it.

### 2.3b The destination's security software can remove files after a perfect copy

Measured: the copy was bit-perfect, the write-test read 40 of 40 writable, the attributes checked
out - and minutes later the destination's antivirus began quarantining tracked evidence files
(incident samples and decoded payloads) out of the working tree, silently, a few at a time. A later
sweep found thirty more files matching the same patterns still on disk, at risk.

⇒ Before copying anything an antivirus engine may flag - incident evidence, malware samples,
offensive tooling, packed binaries - compare the destination's exclusions with the source's and put
the exclusion in place first (the owner's decision: it is a machine-wide security setting).
⇒ After the copy, **re-count the tracked files some minutes later**, not once; and enumerate what
else matches the risky patterns, not only what is already gone. ⇒ Do not restore quarantined files
into a tree that is still being scanned - they are removed again; restore after the exclusion.

### 2.3c The destination agent must not start inside the destination tree

Measured: the destination session was started with its working directory in the copy target, and
its own tooling wrote a log into that tree on every tool call - so the target was no longer empty
before the copy, a mirror-mode copy would have deleted that file, and the agent then reasoned about
an obstacle that existed only because of where it had been started. ⇒ Start the destination agent
in a neutral folder - neither the copy target nor the channel - and move in after the last copy.
Anything a session start creates is destination-only content the copy must be told about.
⚠ Not the channel either (this line used to recommend it): measured, a session started in the channel
folder put its tool-call log and its task folders there, the other side had to be told which folders
were not messages, and with the whole tree watched (1.8) that log would wake every peer on every tool
call. Already running there: name those folders in the channel's standing text and pass them to every
watcher's `-Ignore` (`.claude` is skipped by the watcher itself).

### 2.4 Retry distinguishes a lock from a permission denial; the message does not

A file locked by a copy still in flight and a file the account may not write produce the
**same** denial text. The first assumption is usually "the transfer is still running", which
wastes the diagnosis.

⇒ Retry once. Same error → permissions; check the access control entries, and check the
*attribute* flags separately, since a read-only attribute and a denying entry are different
repairs. And the source side should post the explicit moment the transfer finished, so the
other side is not guessing.

### 2.5 Different accounts is the default assumption, not the exception

Two machines means two identities, and the local-account filtering that operating systems
apply to network logons can leave a session with **no self-repair path at all** — it cannot
grant itself access even over a loopback administrative share. Plan for the grant to come
from the other side or from the owner, and find that out in the first minutes, not the
fortieth.

⚠ **But read the OWNER before calling a refusal an elevation problem.** Measured: a directory that
every listing refused was owned by the session's own account; reading its ACL worked where listing
failed, and the owner of an object may always rewrite that object's ACL - one unprivileged grant
opened it. "Cannot read" and "needs elevation" are two different claims.

### 2.6 The source is not the authority. Diff both ways and look for the superset

A user-scope rules file arrived from the source machine and differed from the one already on
the destination. The instinct — source equals authority, overwrite — was **backwards**: the
destination's copy was a strict superset, carrying one rule the source lacked. Overwriting
would have deleted a rule and looked like a successful migration.

⇒ For any rules or configuration file that exists on both sides, **diff in both directions
and decide which is the superset**. Report the direction on the board, because the side that
is missing something has to be told.

⇒ **Timestamps are worthless here.** A copy stamps its own time, so the older content
routinely looks newer. Judge by content.

---

## Part 3 - Two live trees

### 3.1 The other machine's tree is read-only; version control runs only on your own

Once both sides can see each other's checkout, the temptation is to just fix things on the
far side. Two sessions running version-control operations against one checkout corrupts its
metadata, and simultaneous writes silently overwrite.

⇒ **The far tree is readable, never writable.** Version-control operations happen only on the
tree you are sitting on; synchronisation happens through the shared remote. To hand a file
over, write it to the board or to an agreed inbox directory — never edit the other side's
files in place.

### 3.2 Stop mirroring the moment the far side starts working

Re-running a whole-tree copy after the destination session has begun can overwrite its
version-control metadata and the files it has open.

⇒ Bulk copying happens **once, before the far side starts**. After that, changes travel
through the shared remote — the far side pulls. Say on the board which message was the last
copy.

### 3.3 A shared tree makes `rebase` unusable. Use `merge`

Measured: a push was rejected, the natural repair was a rebase, and the rebase refused —
because of uncommitted changes that belonged to **a different session** working in the same
tree. A merge succeeded: it requires the files it merges to be clean, not the whole tree.

⇒ **In a shared working tree, integrate with `merge`, never `rebase`.** Rebase's precondition
is a clean tree, and in a tree several sessions share, that is never reliably true.

⛔ And never reach for the option that stashes and restores the tree to get a rebase through.
The thing it stashes is someone else's unfinished work.

### 3.4 Machine-bound scheduled work must be cancelled before the machine changes

A scheduled resume registered with the operating system belongs to **that** machine. Left
armed while the work moves, it wakes up later and collides with the session that took over.

⇒ Cancel local scheduled work before handing over, and say on the board that none is armed.

⚠ **And a freeze stops the old side's standing work - say who covers the gap.** Measured: the old
side's security monitoring loops were stopped for the freeze and nothing covered the next hour and
a quarter; the gap was noticed only when a newly started monitoring role found it. ⇒ The migration
plan names which recurring work stops at the freeze, where and when it restarts, and who watches in
between.

⚠ **Verify a disabled task by its state, not by its next run time.** Measured: after a disable, the
scheduler still reported a next run time for the disabled task - and none for an enabled one. Read the
state (`Get-ScheduledTask` State, or `schtasks /query /v` "Scheduled Task State"), with a task you know
is enabled as the control.

### 3.5 Carry the two lists, not one

"Everything needed is in the work area" hides a split: what version control carries, and what
it does not — ignored-but-required configuration, credentials, another session's uncommitted
files, ignored evidence directories. A status check shows only some of that.

⇒ Build the manifest as **two columns: what a fresh checkout gives you, and what it does
not.** Verify the second column's arrival by hash and **never print its contents** — that
column is where the credentials are. Note another session's uncommitted files explicitly so
the destination knows not to touch them.

⛔ **Classify every entry, never a sample - and a size is not a class.** Measured: an inventory of
about thirty thousand ignored files was piped through `head -60`, and the "do not copy" verdicts written
from those sixty were wrong three times (hand-captured evidence, original design documents, a
tutorial) - each would have been destroyed with the source tree. A 140 MB folder judged "build output"
was one downloadable third-party tool beside 3 MB of irreplaceable evidence. ⇒ Classify the whole list,
by folder AND by content type. The "does not travel" column becomes a deletion list the moment the
source is to be removed (3.8).

⭐ **What worked for the credentials, measured on that job:** transport encryption switched on for the
share BEFORE any key travelled; keys in their own folder with inheritance removed, checked on the
FILES, not the folder (4.5); removed from the share as soon as the destination had proved them by
connecting; then the whole share swept BY CONTENT for private-key headers, with a positive control on a
key that still existed elsewhere.

### 3.6 Hard-coded absolute paths are first-class migration items

Paths change across machines. A script with an absolute path fails on the far side; a
*record* with one is history and must not be rewritten.

⇒ The source side greps for its own paths and hands over a table split into **"executed, must
change"** and **"historical, do not touch"**. Prefer replacing an absolute path with an
environment-relative one — that survives the *next* move too.

⇒ **One path has several spellings, and the scan needs every one:** `C:\`, `C:/`, the JSON-escaped
`C:\\`, a POSIX shell's `/c/`, the account's profile folder, and derived names such as a per-project
folder slug. Measured: a scan missed three executed config files because they held the JSON-escaped
form. A bracket expression (`C:[\/]+<dir>`) matches the first three; an alternation written with
`\|` in an extended regex matches NOTHING (4.5). Probe the pattern with one known file per spelling.
⇒ Classify per FILE: a scan view that set a whole folder aside as "history" missed an executed script
inside it. ⇒ Re-run the scan over every file added to the manifest after the scan ran - measured, a
late addition was the one executed hit nobody had scanned.

### 3.7 Re-verify the project's own tooling, not just the build

A different machine means a different console encoding, a different default locale, different
tool versions. A project's own pre-commit tooling can crash on the new machine while the build
and tests pass.

⇒ After a machine change, run the project's own checks too, and force explicit UTF-8 for
anything that emits non-ASCII. See 4.3 for why the crash is more dangerous than it looks.

### 3.8 Before the source is deleted, the "does not travel" column is a deletion list

When the owner decides the source tree goes, every "do not copy" verdict becomes permanent. Measured:
the re-audit that this decision forced found the three wrong verdicts of 3.5; nothing else would have.

⇒ Re-audit the whole source from scratch - not the manifest - until every entry is one of: on the
remote (asked of the SERVER, tags included, not of the local store), staged and verified, or named as
abandoned and regenerable. A directory you could not read is a hole in that count, not an entry in it
(2.5).
⇒ Look outside the tree for what belongs to it: per-project agent memory and transcripts, scheduled
tasks that point into it, certificate-store items, notes in a sibling folder. Measured: the project's
own notes named a sibling file outside the project folder, holding a secret, that no list had carried.
⇒ ⛔ **Check what the tree IS before anyone deletes it.** Raised on that job from the project's own
notes (not yet measured when this was written): the source path had once been a junction to a tree on
another host. If it still is one, a recursive delete can remove the TARGET's contents. Read the folder's
link type or reparse point, and its parent's, with a plain folder as the control; if it is a link,
remove only the link (`rmdir` without `/s`).

---

## Part 4 - Instruments that lie during a migration

These are three specific ways a check reported success or emptiness while measuring nothing.
Part 3 of `verification.md` is the general treatment; these are the cross-machine instances.

### 4.1 A search tool that respects ignore rules cannot see the files a migration must fix

Measured: a structured search over the tree returned 159 files. A plain recursive shell search
returned the same set **plus** the ignored directories — and the one-off scripts with
hard-coded paths, the files a migration most needs to find, live almost entirely in ignored
directories. The tool was silently blind to exactly the region that mattered.

⇒ For a migration scan, disable the ignore rules explicitly, or use a plain recursive search.

⇒ And **the migration document must name at least one file the scan is known to hit**, as a
positive control. On the failing day that single line is what exposed the gap. Make it a
required field of the migration manifest.

⚠ This narrows a general preference for structured search tools. Both are true: the
structured tool is better for an absence claim in tracked code; it is the wrong instrument
when the answer lives in ignored files. State which case you are in.

### 4.2 Writing a board message through a shell heredoc corrupted it invisibly

Backslashes were halved on the way to the file. Network paths lost a separator; what remained
became escape sequences the interpreter then executed, so the file received **invisible
control characters** — a carriage return and a backspace mid-word. The text looked correct in
a rendered view and a search for the affected line found nothing. The other side would have
read a message whose content had been altered.

⇒ Write a board message — anything containing platform paths, network paths or backslashes —
with the **file-writing tool**, never a shell heredoc. If a script is unavoidable, do not let
a literal backslash appear in it at all; build it from a character code.

⇒ Then **scan the written file for control characters by codepoint.** Not by reading it: the
damage is invisible in a rendered view, which is the entire problem.

⛔ **The control-character scan misses the second failure mode: double encoding.** Measured: the
owner's words, relayed verbatim onto a cross-machine board, arrived as a run of accented Latin
letters (bytes `c3 a6 c2 88 c2 91 …`) - UTF-8 bytes re-read as Latin-1 and encoded again. (Described,
not reproduced, so that the check below does not fire on this file - 4.4.) No control characters at all, and the ASCII around it was
intact, so a skim read "a few odd characters", not "the owner's words are gone". ⇒ After writing
text that contained non-ASCII, also look for runs of a character in U+00C0-U+00FF followed by one in
U+0080-U+00BF - the signature of double-encoded UTF-8; where the source was CJK, any such run is a
corruption (undo: encode Latin-1, decode UTF-8). ⇒ **Read back every owner quote you relay** - it is
the one text nobody can reconstruct from context.

### 4.3 The instrument crashed on its own positive control, after reporting a clean result

A scanner printed its clean result, then crashed — **on the line that injects a known-bad
sample to prove it can detect one.** Read the first half alone and you conclude "scanned,
nothing found", when nothing had demonstrated the scanner still works. The crash also made
the exit status non-zero, so a chained commit was blocked and read as "the scan found
something".

⇒ A clean result whose positive control did not run is **UNCONFIRMED, not clean.** Check that
the control printed, not only that the count was zero.

### 4.4 A checker that reads a character list measures the line that defines the list

A pre-commit check searching for a set of characters was blocked by **the handover document's
own line enumerating those characters**. It then, in the same minute, correctly caught real
instances elsewhere.

⇒ Any check driven by a list of markers must exclude the line that *defines* the list — and
records of such a finding should **describe** the offending character rather than reproduce
it, or the record itself trips the check for ever.

⚠ And a false positive is not grounds for distrusting the instrument. The same tool
misreported and correctly reported inside one minute. Read every hit and judge it.

### 4.5 A believable number from a tool used slightly wrong

Measured on one job, one session, three times in two hours, and none of them raised an error: (1) in an
extended regex `\|` is a literal pipe, so an alternation meant as "backslash or slash" matched nothing -
and the control beside it, run without `-E`, was dead the same way; (2) `du -ch <list> | tail -1`, after
`xargs` had split the list, printed the LAST batch's subtotal as the total (83 MB for 119 MiB); (3) a
codepoint check indexed `[0]` into what it took for an array and measured one character of a string,
reporting "0 control characters". A fourth, same session: protection claimed for files from a check run
on their FOLDER, after the files had been copied in.

⇒ **Run the control through the SAME invocation as the measurement** - same flags, same pipeline, same
object. A control built separately proves the separate thing. ⇒ Reconcile a total two independent ways
(the copier's count against a fresh count of the destination; a summed `stat` against the tool's total).
⇒ Measure the object the claim is about, not its parent. ⇒ Every one of these was caught by a control or
by the peer re-measuring (rule 8) - never by the number looking wrong.

---

## The checklist, in order

Before any cross-machine work:

1. A shared directory outside any tree the task touches, holding ONE append-only board for
   claims and turns plus one author-named content file per writer (1.5). Looked for before it is
   created, created at the root, watched whole-tree; two boards = the root one wins (1.3).
2. Each side appends a dated channel-test line to the board AND creates its own dated
   channel-test file; **neither proceeds until both sides can see both.** A side that cannot
   write the board says so in its own file, and from then on speaks there.
3. Both directions measured separately and named in the result; each side's clock posted once.
4. First message declares the split: who owns which paths.
5. Local machine-bound scheduled work cancelled, and said so; who covers stopped recurring work named.
6. Destination ROOT: owner, ACL and the parent's inheritance listed; destination account granted by SID
   with `(OI)(CI)`; a file created from the source side confirmed writable by the destination (2.3).
7. Destination antivirus exclusions compared with the source's and set first, if evidence, samples or
   tooling move (2.3b). The destination agent is started outside the destination tree (2.3c).

After anything arrives:

8. Write-test: sample existing files, plus one file of your own as a positive control.
9. Report the numbers on the board, not an impression. Re-count tracked files minutes later.
10. Rules and configuration files: diff both directions, find the superset, ignore timestamps.
11. Only then hashes, builds, tests, and the project's own tooling.

Throughout:

12. Far tree read-only; version control on your own tree only; `merge`, never `rebase`.
13. Board messages written with the file tool, then scanned for control characters AND for the
    double-encoding signature (4.2).
14. Migration scans run with ignore rules off, against a named known-hit control.
15. Waiting on a peer: a wake-up armed on the channel ROOT, whole tree, your own files and check-in
    ignored; ONE WAITING line, silent re-arms (1.8). List the whole tree before posting WAITING or
    saying who is present or who has (not) answered (`coordination.md` 3.14).
16. Moving the channel: announce it in the OLD place and keep watching there until all acknowledge
    (`coordination.md` 3.9). Rules adopted mid-run go into the channel's standing file (`coordination.md` 3.15).
17. Board stamps produced by the append command, never typed (1.7). Controls run through the same
    invocation as the measurement (4.5).

Before the source is deleted:

18. Re-audit the whole source, every entry classified; look outside the tree for what belongs to it;
    check the tree is not a link to somewhere else (3.8).
