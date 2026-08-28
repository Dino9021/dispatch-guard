---
description: Is dispatch-guard live right now? Hooks, install path, usage data, armed resume
allowed-tools: Bash(bash:*)
---

!`bash "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" "${CLAUDE_PLUGIN_ROOT}/install.py" --status; echo "[--status exit code: $?]"`

Show that report to the user. ⭐ It is read-only and changes nothing.

⛔ **The `echo` is load-bearing; do not remove it.** `--status` exits 1 whenever anything is
not live, and a `!` command that exits non-zero makes the harness print "Shell command
failed" and route the whole report to stderr - so the report that is working exactly as
designed reads as a broken command, at the one moment somebody is using it to debug.
⚠ It hides nothing: the real code is printed, so `[--status exit code: 0]` means fully live,
`1` means see the ⛔ lines, and anything else means the script itself failed.

⚠ If it says the wired paths are WRONG, or that the brake has no data, the repair is one
command: `/dispatch-guard:install`.
