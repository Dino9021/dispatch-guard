# watch-folder.ps1 - wake a waiting agent when anything in a shared channel folder changes.
#
# Part of the dispatch-guard `cowork` skill, reference/cross-machine.md 1.8. For peers on the SAME
# machine prefer SendMessage's `notify_when_idle`; this is for peers you can only reach through files.
#
# Usage - run it IN THE BACKGROUND (Bash tool `run_in_background`), then end your turn. When it exits
# you are woken: read what changed, act or stay silent, and re-arm it.
#   pwsh -NoProfile -WindowStyle Hidden -File <plugin>/skills/cowork/tools/watch-folder.ps1 -Folder <dir> [-Every 30] [-MaxMinutes 55] [-Ignore "a.md,b.md"]
# -WindowStyle Hidden: no console window pops up on the owner's desktop (a stray click on its close button would
#   kill the watcher). Output and exit code are still captured.
#
# Exit 0 = something changed (prints what). Exit 3 = timed out with no change - re-arm it.
# -Ignore takes ONE value; separate several names with commas. Ignore your own file and the observer's,
#   or every write you or an observer make wakes you (and you then wake everyone else).
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

# Under `pwsh -File`, "-Ignore a.md,b.md" arrives as ONE string - split it here.
$Ignore = @($Ignore | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })

if (-not (Test-Path -LiteralPath $Folder -PathType Container)) {
    Write-Host "watch-folder.ps1: folder not found or not readable: $Folder"
    exit 2
}

function Get-Snapshot {
    Get-ChildItem -LiteralPath $Folder -File |
        Where-Object { $Ignore -notcontains $_.Name } |
        ForEach-Object { "{0}|{1}|{2}" -f $_.Name, $_.Length, $_.LastWriteTimeUtc.Ticks }
}

$start = Get-Date
$base = @(Get-Snapshot)
"watching $Folder every ${Every}s for up to $MaxMinutes min; $($base.Count) files (ignoring: $($Ignore -join ', ')); started $($start.ToString('yyyy-MM-dd HH:mm:ss'))"
while (((Get-Date) - $start).TotalMinutes -lt $MaxMinutes) {
    Start-Sleep -Seconds $Every
    $now = @(Get-Snapshot)
    $diff = Compare-Object -ReferenceObject $base -DifferenceObject $now
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
