---
description: Remove the statusline and the Claude Usage Watcher task, and say what is left
allowed-tools: Bash(bash:*), AskUserQuestion
---

⭐ This removes the two things `install.py` wired up. ⚠ It does NOT remove the plugin, and it
never deletes the user's usage history or their `Memory/tasks` work log - the script lists
those instead, and step 5 below hands the removal to the user.

1. Run the dry run. It changes nothing:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" "${CLAUDE_PLUGIN_ROOT}/install.py" --all --uninstall --check
```

2. Show that output to the user.

3. ⚠ ASK FIRST, with `AskUserQuestion`, exactly once:
   - `Remove both (Recommended)` - the statusline and the `Claude Usage Watcher` task in
     VS Code's user-level `tasks.json` (plus a per-project `.vscode/tasks.json` copy in this
     project, if an earlier version left one). It also sets `auto_statusline` and
     `auto_vscode_task` to false, WITHOUT WHICH THE
     UNINSTALL UNDOES ITSELF - the hook refills an empty statusline slot on the next session
     start - and cancels an armed resume, because that one is a scheduled OS task that would
     otherwise wake up and run a script that is gone
   - `Statusline only` - the task stays, and it keeps opening a terminal on folder open
   - `Task only` - the statusline stays, so the usage brake keeps working. This also sets
     `auto_vscode_task` to false, WITHOUT WHICH the hook puts the user-level task back at
     the next session start
   - `Cancel`

4. Run whichever they chose:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" "${CLAUDE_PLUGIN_ROOT}/install.py" --all --uninstall
```

```bash
bash "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" "${CLAUDE_PLUGIN_ROOT}/install.py" --uninstall
```

```bash
bash "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" "${CLAUDE_PLUGIN_ROOT}/install.py" --disable-auto-task
bash "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" "${CLAUDE_PLUGIN_ROOT}/install.py" --vscode-user-task --remove
bash "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" "${CLAUDE_PLUGIN_ROOT}/install.py" --vscode-task --remove
```

(Three commands for `Task only`, in that order: `--disable-auto-task` returns before any
other flag is read, so it cannot share a line; the last one only removes a per-project copy
an earlier version may have left.)

On `Cancel`, change nothing and say so.

5. Then repeat the script's own "STILL ON DISK" list to the user, and offer these two
   commands. ⛔ Do NOT run them yourself: they remove the plugin, which removes this command
   and the hooks mid-turn.

```bash
claude plugin uninstall dispatch-guard@dispatch-guard
claude plugin marketplace remove dispatch-guard
```

6. ⚠ Say that VS Code keeps its own leftovers, and that the user has to decide on them:
   - `task.allowAutomaticTasks` in **user** settings stays on. Other tasks may rely on it now.
   - A dedicated terminal from the removed task keeps running until the folder is reopened.

7. ⚠ Say that the user-level task covered every project, so it is gone everywhere. Only
   projects where an EARLIER version wrote a per-project `.vscode/tasks.json` still carry one,
   and nothing records which: those come out one project at a time, with
   `--vscode-task --remove` run in that project.
