---
description: Show the usage line on screen - the CLI statusline and the VS Code watcher task
allowed-tools: Bash(bash:*), AskUserQuestion
---

⭐ **This command exists so that nobody has to find the install path.** A marketplace
install lives under `~/.claude/plugins/cache/<market>/dispatch-guard/<version>/`, which
nobody can be expected to type. `${CLAUDE_PLUGIN_ROOT}` below always resolves to the copy
that is CURRENTLY loaded, so it is also right again after every `claude plugin update`.

⚠ It goes through `hooks/run.sh` rather than a bare `python`, because the obvious
interpreter name is wrong on both platforms - see the comment at the top of that file.

1. Run the dry run. It writes nothing:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" "${CLAUDE_PLUGIN_ROOT}/install.py" --all --check
```

2. Show that output to the user.

3. ⚠ ASK FIRST, with `AskUserQuestion`, exactly once. This edits their statusline setting
   and writes `.vscode/tasks.json` into this project, so it is their call. Put the install
   option first and suffix it `(Recommended)`:
   - `Install both halves (Recommended)` - statusline for the CLI, watcher task for the
     VS Code extension, which renders no statusline
   - `Statusline only` - no `.vscode/tasks.json` is written
   - `Cancel`

4. Run whichever they chose:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" "${CLAUDE_PLUGIN_ROOT}/install.py" --all
```

```bash
bash "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" "${CLAUDE_PLUGIN_ROOT}/install.py"
```

On `Cancel`, change nothing and say so.

5. Then say the two things that do NOT happen by themselves:
   - ⚠ Reopen the folder. The watcher task fires on folder open, not now.
   - ⭐ Hooks and the skill need nothing. They came with the plugin.
