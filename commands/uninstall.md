---
description: Remove the statusline and this project's Claude Usage Watcher task, and say what is left
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
   - `Remove both (Recommended)` - the statusline and this project's `Claude Usage Watcher`
     task. It also sets `auto_statusline` and `auto_vscode_task` to false, WITHOUT WHICH THE
     UNINSTALL UNDOES ITSELF - the hook refills an empty statusline slot on the next session
     start - and cancels an armed resume, because that one is a scheduled OS task that would
     otherwise wake up and run a script that is gone
   - `Statusline only` - the task stays, and it keeps opening a terminal on folder open
   - `Task only` - the statusline stays, so the usage brake keeps working
   - `Cancel`

4. Run whichever they chose:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" "${CLAUDE_PLUGIN_ROOT}/install.py" --all --uninstall
```

```bash
bash "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" "${CLAUDE_PLUGIN_ROOT}/install.py" --uninstall
```

```bash
bash "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" "${CLAUDE_PLUGIN_ROOT}/install.py" --vscode-task --remove
```

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

7. ⚠ Say plainly that only THIS project's task was removed. If `auto_vscode_task` was on,
   every project opened in VS Code may carry one, and nothing records which. The flag is off
   now, so no new ones appear; existing ones come out one project at a time.
