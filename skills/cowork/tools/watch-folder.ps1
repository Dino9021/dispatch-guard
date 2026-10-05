# watch-folder.ps1 - wake a waiting agent when anything in a shared channel folder changes.
#
# Part of the dispatch-guard `cowork` skill, reference/cross-machine.md 1.8. For peers on the SAME
# machine prefer SendMessage's `notify_when_idle`; this is for peers you can only reach through files.
#
# Usage - run it IN THE BACKGROUND (Bash tool `run_in_background`), then end your turn. When it exits
# you are woken: read what changed, act or stay silent, and re-arm it.
#   pwsh -NoProfile -WindowStyle Hidden -File <plugin>/skills/cowork/tools/watch-folder.ps1 -Folder <dir> [-Every 30] [-MaxMinutes 55] [-Ignore "OLD.md,checkin/OLD.md"]
# -WindowStyle Hidden: no console window pops up on the owner's desktop (a stray click on its close button would
#   kill the watcher). Output and exit code are still captured.
#
# Exit 0 = something changed (prints what). Exit 3 = timed out with no change - re-arm it.
# It watches the WHOLE TREE under -Folder (0.69.1). Point it at the channel's ROOT, never at the subfolder you
#   expect the answer in: check-ins live in checkin/, and a peer may build its channel in a folder you did not
#   expect. Measured: through 0.69.0 it listed only the top folder, and two sessions each wrote to the other in
#   a place the other's watcher could not see.
# Any `.claude` folder is always skipped: a session started in the channel writes its log there on every tool call.
# -Ignore takes ONE value; separate several entries with commas. An entry is a path relative to -Folder
#   (`OLD.md`, `checkin/OLD.md`) or a folder (`Memory`), which skips everything under it - no wildcards; the
#   first output line prints every entry as it will be matched, so a dead one is visible. Ignore your own files -
#   content AND check-in - and the observer's, or every write you or an observer make wakes you (and you then
#   wake everyone else).
# Read-only: it lists names, sizes and write times. It never opens a file's content.
param(
    [string]$Folder = $PSScriptRoot,
    [int]$Every = 30,
    [int]$MaxMinutes = 55,
    [string[]]$Ignore = @()
)

# --- Settle which PowerShell is running this (5.1 and 7 differ silently). Re-exec under pwsh 7, arguments
# serialised rather than rebuilt as a command line; refuse when pwsh 7 is not installed.
if ($PSVersionTable.PSVersion.Major -lt 7) {
    $exe = (Get-Command pwsh -CommandType Application -ErrorAction SilentlyContinue |
            Where-Object {
                try { [int] (& $_.Source -NoProfile -Command '$PSVersionTable.PSVersion.Major') -ge 7 }
                catch { $false }
            } | Select-Object -First 1).Source
    if (-not $exe) {
        foreach ($p in @((Join-Path $env:ProgramFiles 'PowerShell\7\pwsh.exe'),
                         (Join-Path ${env:ProgramFiles(x86)} 'PowerShell\7\pwsh.exe'))) {
            if ($p -and (Test-Path -LiteralPath $p)) { $exe = $p; break }
        }
    }
    if (-not $exe) {
        Write-Host "watch-folder.ps1 needs PowerShell 7 (pwsh). Install it: winget install --id Microsoft.PowerShell -e"
        Write-Host "or from https://github.com/PowerShell/PowerShell/releases - then run this with pwsh."
        exit 2
    }
    $bound = @{}
    foreach ($kv in $PSBoundParameters.GetEnumerator()) {
        $bound[$kv.Key] = if ($kv.Value -is [switch]) { [bool] $kv.Value.IsPresent } else { $kv.Value }
    }
    $encode = {
        param($obj)
        [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes(
            (ConvertTo-Json -InputObject $obj -Depth 8 -Compress)))
    }
    $boundB64 = & $encode $bound
    $rest = [string[]] @($args)
    if ($null -eq $rest) { $rest = [string[]] @() }
    $restB64  = & $encode $rest
    $selfQ    = $PSCommandPath.Replace("'", "''")
    $child = @"
`$h = @{}
`$j = ConvertFrom-Json ([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('$boundB64')))
if (`$j) { `$j.PSObject.Properties | ForEach-Object { `$h[`$_.Name] = `$_.Value } }
`$rest = [string[]] @(ConvertFrom-Json ([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('$restB64'))))
& '$selfQ' @h @rest
exit `$LASTEXITCODE
"@
    & $exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command $child
    if ($null -eq $LASTEXITCODE) { exit 1 } else { exit $LASTEXITCODE }
}

# UTF-8 out: a CJK folder or file name printed in the console code page reaches the agent as mojibake.
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

if (-not (Test-Path -LiteralPath $Folder -PathType Container)) {
    Write-Host "watch-folder.ps1: folder not found or not readable: $Folder"
    exit 2
}
# ProviderPath, not Path: for a UNC folder .Path carries a provider prefix the children's FullName lacks. Never
# trim it: `W:\` trimmed is `W:`, which PowerShell reads as the CURRENT directory on W: (measured).
$root = (Resolve-Path -LiteralPath $Folder).ProviderPath
try { [void](Get-ChildItem -LiteralPath $root -Force -ErrorAction Stop | Select-Object -First 1) }
catch {
    Write-Host "watch-folder.ps1: cannot list $root - a watcher that cannot list it can never wake you: $_"
    exit 2
}
function Get-Rel([string]$path) { [IO.Path]::GetRelativePath($root, $path).Replace('\', '/') }

# Under `pwsh -File`, "-Ignore a.md,b.md" arrives as ONE string - split it here. Entries are compared as
# relative paths with forward slashes, case-insensitively; `./x`, `x//y` and an absolute path under -Folder
# are normalised, so an entry that is printed as ignored really is.
$Ignore = @($Ignore | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ } |
            ForEach-Object {
                # FullyQualified, not Rooted: `/checkin/x.md` is rooted on Windows (the drive's root) but means the channel's.
                $e = if ([IO.Path]::IsPathFullyQualified($_)) { Get-Rel $_ } else { $_.Replace('\', '/') }
                (($e -replace '/{2,}', '/') -replace '^(\./)+', '').Trim('/')
            } | Where-Object { $_ -and $_ -ne '.' })

function Test-Ignored([string]$rel) {
    if ($rel.Split('/') -contains '.claude') { return $true }
    foreach ($e in $Ignore) {
        if ($rel -eq $e -or $rel.StartsWith("$e/", [StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    $false
}

# Enumeration errors (an unreadable subfolder) are printed, never silenced: a folder the watcher cannot list
# is a folder it cannot wake you for. They are also collected, so the files under a folder that failed to list
# in THIS poll are not reported as deleted (measured: a transient denial read as "the peer deleted x.md").
function Get-Snapshot {
    Get-ChildItem -LiteralPath $root -File -Recurse -Force -ErrorVariable +script:snapErr |
        ForEach-Object {
            $rel = Get-Rel $_.FullName
            if (-not (Test-Ignored $rel)) { "{0}|{1}|{2}" -f $rel, $_.Length, $_.LastWriteTimeUtc.Ticks }
        }
}

$start = Get-Date
$base = @(Get-Snapshot)
"watch-folder.ps1 0.69.1 (whole tree): watching $root every ${Every}s for up to $MaxMinutes min; $($base.Count) files (ignoring: .claude, $($Ignore -join ', ')); started $($start.ToString('yyyy-MM-dd HH:mm:ss'))"
while (((Get-Date) - $start).TotalMinutes -lt $MaxMinutes) {
    Start-Sleep -Seconds $Every
    $script:snapErr = @()
    $now = @(Get-Snapshot)
    $bad = @($script:snapErr | Where-Object { "$($_.TargetObject)" } | ForEach-Object { Get-Rel "$($_.TargetObject)" })
    $diff = Compare-Object -ReferenceObject $base -DifferenceObject $now | Where-Object {
        $r = $_.InputObject.Split('|')[0]
        -not ($_.SideIndicator -eq '<=' -and
              @($bad | Where-Object { $_ -eq '.' -or $r.StartsWith("$_/", [StringComparison]::OrdinalIgnoreCase) }).Count)
    }
    if ($diff) {
        "CHANGED at $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss')):"
        $diff | ForEach-Object {
            $side = if ($_.SideIndicator -eq '=>') { 'now ' } else { 'was ' }
            "  $side $($_.InputObject)"
        }
        exit 0
    }
}
"NO CHANGE for $MaxMinutes min (until $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))) - re-arm"
exit 3
