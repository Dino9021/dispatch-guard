<#
.SYNOPSIS
  Remove every trace of an older dispatch-guard install, so a reinstall starts clean.

.DESCRIPTION
  Run it with no arguments:

      .\clean-dispatch-guard.ps1

  It asks whether to include project files, prints everything it intends to do, and then waits
  for you to type `confirm`. ⭐ Anything else aborts, and the default is to do nothing.

  ⛔ THE LIST COMES BEFORE THE QUESTION. An earlier version asked first and discovered second,
  which is consent for something you have not seen. The same code produces the list and carries
  it out, so what you approve is exactly what runs.

  ⚠ THE `.claude` FOLDER ITSELF IS NEVER DELETED. It is where this looks. Everything it removes
  is named individually, and every one of those names contains `dispatch-guard`.

  ⛔ WHY A CLEANER IS NEEDED WHEN THE PLUGIN SELF-HEALS. A stale statusline and a stale VS Code
  task repair themselves from 0.13.0 onward, so most upgrades need nothing. What never
  self-heals is everything the plugin was once told to REMEMBER:

    - a config.json written before 0.11.0 PINNED every value, so a later default never reaches
      that machine. `auto_vscode_task: false` frozen in there means the watcher task silently
      never appears, for ever, with nothing saying why.
    - renamed keys are IGNORED, not warned about: `model_ceiling` became `max_model_price` in
      0.24.0, `require_skills` became two booleans in 0.23.0.
    - a one-shot resume registered as `ClaudeDispatchGuardResume` outlives every uninstall.

.NOTES
  PowerShell 7+ (uses -EscapeHandling so JSON edits do not mangle non-ASCII text).
  Never touches Memory/ or Memory/tasks - that is your work log, not this plugin's state.

  ⚠ DG_CLEAN_HOME and DG_CLEAN_VSCODE are TEST HOOKS, not options. They exist so the checks can
  aim this at a fixture directory, and they exist because relying on `$HOME` once let a test run
  against a real install and uninstall a working plugin. Leave them unset.
#>

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) {
    Write-Host "⛔ Needs PowerShell 7+. You are on $($PSVersionTable.PSVersion)." -ForegroundColor Red
    exit 2
}

$MARKER  = 'dispatch-guard'
$TASKDEF = 'Claude usage watch'
$SCHED   = 'ClaudeDispatchGuardResume'
$plan     = [System.Collections.Generic.List[hashtable]]::new()
$skipped  = [System.Collections.Generic.List[string]]::new()
$backedUp = @{}

$claude = if ($env:DG_CLEAN_HOME) { $env:DG_CLEAN_HOME } else { Join-Path $HOME '.claude' }

# ------------------------------------------------------------------------------- reporting

# ⭐ ONE DEFINITION OF THE INSTALL COMMANDS. Both endings need them - after a clean, and when
# there was nothing to clean - and two copies of a command line drift the first time one
# changes. ⚠ Whoever finds nothing here is usually one step from installing: a cleaner that
# says "nothing to do" and stops has answered the question they asked and not the one they
# have.
function Show-Install {
    Write-Host "Install (or reinstall) with:" -ForegroundColor White
    Write-Host "  claude plugin marketplace add Dino9021/dispatch-guard"
    Write-Host "  claude plugin install dispatch-guard@dispatch-guard"
    Write-Host "  ⚠ then open a NEW session - a plugin's hooks load at session start." -ForegroundColor DarkGray
    Write-Host ""
}

function Note([string]$verb, [string]$what, [string]$why = '') {
    $colour = switch ($verb) {
        'DELETE' { 'Red' } 'MODIFY' { 'Yellow' } 'KEEP' { 'DarkGray' }
        'deleted' { 'Green' } 'modified' { 'Green' } 'FAILED' { 'Red' } default { 'Gray' }
    }
    Write-Host ("  {0,-8} {1}" -f $verb, $what) -ForegroundColor $colour
    if ($why) { Write-Host ("           {0}" -f $why) -ForegroundColor DarkGray }
}

# ⛔ JSONC IS NOT JSON, AND PowerShell 7 HIDES THAT. VS Code allows comments in tasks.json and
# settings.json; `ConvertFrom-Json` in PS7 ACCEPTS them, and `ConvertTo-Json` then writes the
# file back without them. So "refuse what will not parse" catches nothing - the file parses and
# the comments are gone. Measured on a fixture. ⇒ Comments are found in the RAW TEXT instead.
$COMMENTED = [regex]'(?m)^\s*(//|/\*)|\s//\s'

function Read-JsonFile([string]$path, [switch]$Quiet) {
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    $raw = Get-Content -LiteralPath $path -Raw -Encoding utf8
    if ($COMMENTED.IsMatch($raw)) {
        if (-not $Quiet) {
            Note 'KEEP' $path 'it has comments (JSONC) - rewriting would delete them. Edit this one by hand'
            $skipped.Add($path)
        }
        return 'UNPARSEABLE'
    }
    try { return ($raw | ConvertFrom-Json -AsHashtable) }
    catch {
        if (-not $Quiet) { Note 'KEEP' $path 'cannot parse it - edit by hand'; $skipped.Add($path) }
        return 'UNPARSEABLE'
    }
}

function Get-JsonNode($data, [string[]]$keyPath) {
    $node = $data
    for ($i = 0; $i -lt $keyPath.Count - 1; $i++) {
        if ($node -isnot [hashtable] -or -not $node.ContainsKey($keyPath[$i])) { return $null }
        $node = $node[$keyPath[$i]]
    }
    if ($node -isnot [hashtable] -or -not $node.ContainsKey($keyPath[-1])) { return $null }
    return $node
}

# ⭐ TWO VERBS, AND THE DIFFERENCE IS THE POINT. DELETE means the file or folder goes away.
# MODIFY means the file STAYS and one setting inside it is taken out. An earlier version said
# "remove" for both, and "remove <path-to-settings.json>" reads as "delete your settings" -
# which is how a cleaner frightens someone into approving what they misread.
function Plan-Delete([string]$path, [string]$why = '') {
    if (-not (Test-Path -LiteralPath $path)) { return }
    $plan.Add(@{ Kind = 'delete'; Path = $path })
    Note 'DELETE' $path $why
}

function Plan-Modify([string]$path, [string[]]$keyPath, [string]$why = '') {
    $data = Read-JsonFile $path
    if ($null -eq $data -or $data -eq 'UNPARSEABLE') { return }
    if (-not (Get-JsonNode $data $keyPath)) { return }
    $plan.Add(@{ Kind = 'jsonkey'; Path = $path; KeyPath = $keyPath })
    Note 'MODIFY' $path "the file stays. Setting taken out: $($keyPath -join ' > ')   ($why)"
}

function Plan-VsTask([string]$path) {
    $t = Read-JsonFile $path
    if ($null -eq $t -or $t -eq 'UNPARSEABLE' -or -not $t.ContainsKey('tasks')) { return }
    $all  = @($t['tasks'])
    $keep = @($all | Where-Object { [string]$_.label -ne $TASKDEF })
    if ($keep.Count -eq $all.Count) { return }
    if ($keep.Count -eq 0) {
        # ⚠ Only our task is in there, so the file is ours to take. An empty shell left behind
        # is litter that looks like configuration.
        $plan.Add(@{ Kind = 'delete'; Path = $path })
        Note 'DELETE' $path "it holds the `"$TASKDEF`" task and nothing else"
    } else {
        $plan.Add(@{ Kind = 'vstask'; Path = $path })
        Note 'MODIFY' $path "the file stays. Task taken out: `"$TASKDEF`"   ($($keep.Count) other task(s) stay)"
    }
}

# --------------------------------------------------------------- ask about project files

Write-Host ""
Write-Host "dispatch-guard cleaner" -ForegroundColor White
Write-Host "  it will look in : $claude" -ForegroundColor White
Write-Host "                    ⚠ that folder is NOT deleted - only the items listed below" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Also clean PROJECT files (.vscode/tasks.json entries, .claude/dispatch-gate.log," -ForegroundColor White
Write-Host "  .claude/dispatch-guard.json)? Type a folder to search, or press Enter to skip." -ForegroundColor White
$projectRoot = (Read-Host "  project folder").Trim().Trim('"')
if ($projectRoot -and -not (Test-Path -LiteralPath $projectRoot)) {
    Write-Host "  ⛔ no such folder: $projectRoot - aborting rather than guessing." -ForegroundColor Red
    exit 2
}

# --------------------------------------------------------------------------- find and list

Write-Host ""
Write-Host "1. folders to delete" -ForegroundColor White
Plan-Delete (Join-Path $claude 'plugins\cache\dispatch-guard')        'the installed copies, one folder per version'
Plan-Delete (Join-Path $claude 'plugins\marketplaces\dispatch-guard') 'the marketplace git clone (the SOURCE, never runs)'
Plan-Delete (Join-Path $claude 'dispatch-guard') @'
usage history, config.json, session stamps, clock.spawn, fetch.claim, renders.log,
           resume.json, asked-vscode-task, model_pricing.json + .status + model_prices.spawn.
           ⛔ config.json is the one that matters: a version before 0.11.0 pinned every value
           here, so new defaults never reach this machine
'@

Write-Host ""
Write-Host "2. files to delete" -ForegroundColor White
$settings = Join-Path $claude 'settings.json'
Plan-Delete "$settings.statusline-backup.json" 'only exists if --take-statusline was used'
if ($env:TEMP) { Plan-Delete (Join-Path $env:TEMP 'dispatch-gate-error.log') 'the fallback log for hook errors' }
if (Test-Path -LiteralPath $claude) {
    Get-ChildItem -LiteralPath $claude -Filter '*.bak-dispatch-guard' -ErrorAction SilentlyContinue |
        ForEach-Object { Plan-Delete $_.FullName 'a backup this plugin made before editing' }
}

Write-Host ""
Write-Host "3. files to MODIFY - the file stays, one setting comes out" -ForegroundColor White

# ⭐ THE STATUSLINE COMES OUT ONLY IF IT IS OURS. Somebody else's line in that slot must survive
# a clean of this plugin - taking it would be the rudest possible bug.
$s = Read-JsonFile $settings
if ($s -and $s -ne 'UNPARSEABLE') {
    $cmd = ''
    if ($s.ContainsKey('statusLine') -and $s['statusLine'] -is [hashtable]) { $cmd = [string]$s['statusLine']['command'] }
    if ($cmd -like "*$MARKER*") {
        Plan-Modify $settings @('statusLine') 'this plugin''s usage line; refreshInterval goes with it'
    } elseif ($cmd) {
        Note 'KEEP' "$settings > statusLine" 'that slot belongs to something else - not touching it'
    }
}
Plan-Modify $settings @('enabledPlugins', 'dispatch-guard@dispatch-guard') 'the enable flag'
Plan-Modify $settings @('marketplaces', 'dispatch-guard')                  'a marketplace declaration, if one was added here'
Plan-Modify (Join-Path $claude 'plugins\known_marketplaces.json') @('dispatch-guard')                          'the marketplace record'
Plan-Modify (Join-Path $claude 'plugins\installed_plugins.json') @('plugins', 'dispatch-guard@dispatch-guard') 'the install record'
Plan-Modify (Join-Path $claude 'plugins\installed_plugins.json') @('dispatch-guard@dispatch-guard')            'the install record, pre-v2 layout'

Write-Host ""
Write-Host "4. VS Code, user level" -ForegroundColor White
$userDirs = @()
if ($env:DG_CLEAN_VSCODE) { $userDirs = @($env:DG_CLEAN_VSCODE) }
else {
    foreach ($base in @($env:APPDATA, (Join-Path $HOME 'Library/Application Support'), (Join-Path $HOME '.config'))) {
        if (-not $base) { continue }
        foreach ($flavour in 'Code', 'Code - Insiders', 'VSCodium') {
            $userDirs += (Join-Path (Join-Path $base $flavour) 'User')
        }
    }
}
foreach ($userDir in $userDirs) {
    if (-not (Test-Path -LiteralPath $userDir)) { continue }
    Plan-VsTask (Join-Path $userDir 'tasks.json')
    $vs = Read-JsonFile (Join-Path $userDir 'settings.json') -Quiet
    if ($vs -and $vs -ne 'UNPARSEABLE' -and $vs.ContainsKey('task.allowAutomaticTasks')) {
        Note 'KEEP' "$(Join-Path $userDir 'settings.json') > task.allowAutomaticTasks = $($vs['task.allowAutomaticTasks'])" `
            'not plugin-specific - your other projects'' automatic tasks may rely on it'
    }
}

Write-Host ""
Write-Host "5. the OS scheduled task - an armed resume outlives every uninstall" -ForegroundColor White
if ($IsWindows -or $env:OS -eq 'Windows_NT') {
    & schtasks /Query /TN $SCHED *> $null
    if ($LASTEXITCODE -eq 0) { $plan.Add(@{ Kind = 'schtask'; Path = $SCHED }); Note 'DELETE' "scheduled task $SCHED" }
} else {
    Note 'INFO' 'on macOS/Linux the resume uses `at`' 'list with `atq`, remove with `atrm <id>`'
}

Write-Host ""
Write-Host "6. project level" -ForegroundColor White
if (-not $projectRoot) {
    Note 'INFO' 'skipped - you pressed Enter' 'run again and give a folder to include project files'
} else {
    foreach ($f in Get-ChildItem -LiteralPath $projectRoot -Recurse -Depth 3 -Force -Filter 'dispatch-gate.log' -ErrorAction SilentlyContinue) {
        Plan-Delete $f.FullName 'a log this plugin wrote'
    }
    foreach ($f in Get-ChildItem -LiteralPath $projectRoot -Recurse -Depth 3 -Force -Filter 'dispatch-guard.json' -ErrorAction SilentlyContinue) {
        if ($f.DirectoryName -like '*\.claude') { Plan-Delete $f.FullName 'a per-project config override' }
    }
    foreach ($f in Get-ChildItem -LiteralPath $projectRoot -Recurse -Depth 3 -Force -Filter 'tasks.json' -ErrorAction SilentlyContinue) {
        if ($f.DirectoryName -like '*\.vscode') { Plan-VsTask $f.FullName }
    }
}

Write-Host ""
Write-Host "7. never touched" -ForegroundColor White
Note 'KEEP' 'Memory/ and Memory/tasks/ in every project' 'your work log - plans, sub-task prompts, agent reports. Never this plugin''s to delete'
Note 'KEEP' "$claude itself" 'only the items listed above come out of it'

# ------------------------------------------------------------------------------ confirm

$deletes = @($plan | Where-Object { $_.Kind -in 'delete', 'schtask' }).Count
$edits   = @($plan | Where-Object { $_.Kind -in 'jsonkey', 'vstask' }).Count

Write-Host ""
if ($plan.Count -eq 0) {
    # ⛔ "NOTHING FOUND" MUST NOT READ AS "CLEANED". An empty result and a wrong search folder
    # look identical from a chair, so the empty case says which one it is.
    Write-Host "Nothing found - there is no dispatch-guard install under $claude." -ForegroundColor Cyan
    Write-Host "  ⚠ If you expected one, check that path: a wrong folder looks exactly like a clean machine." -ForegroundColor DarkGray
    Write-Host ""
    Show-Install
    exit 0
}

Write-Host "$deletes to delete, $edits file(s) to modify." -ForegroundColor White
Write-Host "Type  confirm  to carry out exactly that list. Anything else stops here." -ForegroundColor Yellow
if ((Read-Host "  ").Trim() -inotmatch '^confirm$') {
    Write-Host ""
    Write-Host "stopped - nothing was changed." -ForegroundColor Cyan
    Write-Host ""
    exit 3
}

# ------------------------------------------------------------------------------ carry out

# ⚠ ONE BACKUP PER FILE PER RUN. An early version copied before every edit, so a second change
# to the same file overwrote the backup with the already-half-edited version - destroying the
# one state worth keeping.
function Backup-Once([string]$path) {
    if ($backedUp.ContainsKey($path)) { return }
    Copy-Item -LiteralPath $path -Destination "$path.bak-dg-clean" -Force
    $backedUp[$path] = $true
}

function Write-JsonFile([string]$path, $obj) {
    Backup-Once $path
    ($obj | ConvertTo-Json -Depth 32 -EscapeHandling Default) + "`n" |
        Set-Content -LiteralPath $path -Encoding utf8 -NoNewline
}

Write-Host ""
$done = 0
foreach ($item in $plan) {
    switch ($item.Kind) {
        'delete' {
            Remove-Item -LiteralPath $item.Path -Recurse -Force -ErrorAction SilentlyContinue
            if (Test-Path -LiteralPath $item.Path) {
                # ⚠ A live session's hooks rewrite state files within seconds. One retry, then
                # report - silently leaving it is the failure this whole plugin is about.
                Start-Sleep -Milliseconds 500
                Remove-Item -LiteralPath $item.Path -Recurse -Force -ErrorAction SilentlyContinue
            }
            if (Test-Path -LiteralPath $item.Path) {
                Note 'FAILED' $item.Path 'still there - close Claude Code and run this again'
                $skipped.Add($item.Path)
            } else { $done++; Note 'deleted' $item.Path }
        }
        'jsonkey' {
            $data = Read-JsonFile $item.Path -Quiet
            if ($null -eq $data -or $data -eq 'UNPARSEABLE') { $skipped.Add($item.Path); break }
            $node = Get-JsonNode $data $item.KeyPath
            if (-not $node) { break }
            $node.Remove($item.KeyPath[-1]) | Out-Null
            Write-JsonFile $item.Path $data
            $done++; Note 'modified' "$($item.Path)   -   $($item.KeyPath -join ' > ') taken out"
        }
        'vstask' {
            $t = Read-JsonFile $item.Path -Quiet
            if ($null -eq $t -or $t -eq 'UNPARSEABLE') { $skipped.Add($item.Path); break }
            $t['tasks'] = @($t['tasks'] | Where-Object { [string]$_.label -ne $TASKDEF })
            Write-JsonFile $item.Path $t
            $done++; Note 'modified' "$($item.Path)   -   `"$TASKDEF`" taken out"
        }
        'schtask' {
            & schtasks /Delete /TN $item.Path /F *> $null
            if ($LASTEXITCODE -eq 0) { $done++; Note 'deleted' "scheduled task $($item.Path)" }
            else { Note 'FAILED' "scheduled task $($item.Path)" 'try an elevated shell'; $skipped.Add($item.Path) }
        }
    }
}

Write-Host ""
Write-Host "$done of $($plan.Count) done. Edited files keep a .bak-dg-clean copy beside them." -ForegroundColor Green
if ($skipped.Count) {
    Write-Host "⚠ left behind:" -ForegroundColor Yellow
    $skipped | Select-Object -Unique | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
}
Write-Host ""
Write-Host "⚠ A RUNNING Claude Code session rewrites $claude\dispatch-guard within seconds." -ForegroundColor Yellow
Write-Host "  Close every session first, or run this again until it finds nothing." -ForegroundColor Yellow
Write-Host ""
Show-Install
exit ($skipped.Count ? 1 : 0)
