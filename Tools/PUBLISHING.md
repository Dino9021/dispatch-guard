# Updating the public repo

**"更新 public repo" means exactly this:**

```bash
python Tools/publish-public.py            # show the plan, change nothing
python Tools/publish-public.py --push     # sync, commit, push
```

Nothing else. No copying by hand, no working out what changed since the last version.

| | |
|---|---|
| private | `C:\WorkSpace\dispatch-guard` → `ssh://git@atlas.dino9021.com:2222/Dino9021/dispatch-guard.git` |
| public | `C:\WorkSpace\dispatch-guard_public` → `https://github.com/Dino9021/dispatch-guard` |

The private repository is the only working copy: full history, and `Memory/` tracked. The
public one is a **published snapshot** — one commit per publish, no `Memory/`, and every
commit names the private commit it came from, so the reasoning is one lookup away.

---

## What the script does, and why each part is the way it is

**1. It refuses while the private tree has uncommitted tracked changes.**
A snapshot must never contain work that exists nowhere else. ⚠ It caught its own author twice.

**2. It publishes `git archive HEAD`, not the working tree.**
Exactly what is committed: no untracked scratch, no ignored files, nothing half-finished.

**3. It MIRRORS the tree — it does not compute a delta.**
⛔ "Copy what changed since version X" is the obvious shape and it is wrong: a delta carries
additions and edits and silently misses **deletions** and renames, so a file removed privately
lives on in public for ever. A mirror cannot miss one, and it is idempotent — run it twice and
the second run publishes nothing.

**4. `Memory/` never leaves, by rule.**
⛔ Not by `.gitignore`: neither repository ignores it any more, because the private one
**tracks** it on purpose. The exclusion lives in the script, and the `Memory/` line in the
public `.gitignore` is the second lock.

**5. `.gitignore` belongs to the public repository and is never mirrored.**
Two reasons. It is the only thing keeping the work log out by hand, so no private edit may
remove it. And the private file's rules are written for a repository that tracks `Memory/` —
publishing them would carry a rule that contradicts its own purpose. ⚠ Because it is never
mirrored, a **new private ignore rule never arrives either** — so the script prints the
difference on every run. Silent drift is what is being avoided, not drift.

⚠ The `.gitignore` line inside the public `.gitignore` is **documentation of intent, not
enforcement**: that file is tracked there, and git's ignore rules do not apply to tracked
files. What actually stops the private one travelling is `PUBLIC_OWNED` in the script.

**6. After every sync it ensures these rules exist in the public `.gitignore`:**
`Memory/`, `.gitignore`, `Tools/Debug/scratch/`, `__pycache__/`, `*.pyc`.
⚠ Not theory: the first mirror found **78 stray files** in the public folder, every one of them
test scratch or byte-code, carried over when the folder was first copied.

**7. Every publish is secret-scanned, with a positive control.**
This is the one direction where a mistake cannot be taken back, so an empty result must be
distinguishable from a scan that never ran. ⛔ The only exemption is keyed on the **matched
string** — a match containing `FAKE`, `NOT-A-REAL`, `EXAMPLE`, `PLACEHOLDER`, `DUMMY` or
`REDACTED` is not a secret — never on a file or a path. A scanner taught to ignore *files*
ignores the wrong one the day a real key lands in a file somebody exempted last year.

**8. It checks the target can commit before it touches anything.**
⛔ The first real run copied 30 files, staged them, and only then found the public repository
had no git identity — leaving a half-applied tree that the mirror's own idempotence then read
as "nothing to publish". A step that mutates before it knows it can finish turns one clear
failure into two confusing ones.

---

## What it does NOT do

- It does not bump the version. Publish whatever the private `plugin.json` says.
- It does not touch the private repository at all.
- It does not delete `Memory/` from anywhere. It only declines to copy it.

## If it refuses

| it says | do |
|---|---|
| uncommitted changes to tracked files | commit them privately first |
| secret scan hits | look. If it is a fixture, put `FAKE` in the string — never widen the scanner |
| the public repository has no `user.name` / `user.email` | run the line it prints |
| nothing to publish | the snapshot already matches the private HEAD |
