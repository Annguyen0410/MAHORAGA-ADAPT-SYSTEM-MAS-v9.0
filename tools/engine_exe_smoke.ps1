# Packaged-app smoke, using disposable data and TEMP inside the workspace.
# Only processes descended from the launched PID are stopped.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File tools/engine_exe_smoke.ps1 -ExePaths build/current-release/Mei.exe
param(
    [Parameter(Mandatory = $true)][string[]]$ExePaths,
    [int]$SettleSeconds = 35
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$testRoot = Join-Path $root ('build/exe-smoke-' + [guid]::NewGuid().ToString('N'))
$variables = @('LITEBROWSER_DATA_DIR', 'LITEBROWSER_UPDATE_METADATA_URL', 'LOCALAPPDATA', 'TEMP', 'TMP', 'QT_QPA_PLATFORM')
$previous = @{}
foreach ($name in $variables) { $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
$failed = $false

function Get-Descendants([int]$ParentId) {
    $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $byParent = @{}
    foreach ($proc in $all) {
        $key = [int]$proc.ParentProcessId
        if (-not $byParent.ContainsKey($key)) { $byParent[$key] = @() }
        $byParent[$key] += $proc
    }
    $tree = @()
    $queue = @($ParentId)
    $seen = @{}
    while ($queue.Count -gt 0) {
        $next = @()
        foreach ($q in $queue) {
            if ($seen.ContainsKey([int]$q)) { continue }
            $seen[[int]$q] = $true
            if ($byParent.ContainsKey([int]$q)) {
                foreach ($kid in $byParent[[int]$q]) {
                    $tree += $kid
                    $next += $kid.ProcessId
                }
            }
        }
        $queue = $next
    }
    return $tree
}

try {
    New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
    $index = 0
    foreach ($candidate in $ExePaths) {
        $index++
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            "$candidate RESULT missing exe"
            $failed = $true
            continue
        }
        $exe = (Resolve-Path -LiteralPath $candidate).Path
        $dir = Split-Path -Parent $exe
        $runRoot = Join-Path $testRoot ([string]$index)
        $tempRoot = Join-Path $runRoot 'temp'
        $dataRoot = Join-Path $runRoot 'data'
        $profile = Join-Path $dataRoot 'profiles/Default'
        New-Item -ItemType Directory -Path $tempRoot, $profile, (Join-Path $runRoot 'localappdata') -Force | Out-Null
        # Seed only synthetic settings, never copy an existing profile.
        [IO.File]::WriteAllText((Join-Path $profile 'prefs.json'), '{"onboarding_done":true}')
        [IO.File]::WriteAllText((Join-Path $dataRoot 'last_profile.txt'), 'Default')
        $env:LITEBROWSER_DATA_DIR = $dataRoot
        $env:LOCALAPPDATA = Join-Path $runRoot 'localappdata'
        $env:TEMP = $tempRoot
        $env:TMP = $tempRoot
        $env:QT_QPA_PLATFORM = 'windows'
        # Missing local metadata reports an error without using any network/key.
        $env:LITEBROWSER_UPDATE_METADATA_URL = ([uri](Join-Path $runRoot 'no-update.json')).AbsoluteUri
        $p = $null
        try {
            $p = Start-Process -FilePath $exe -WorkingDirectory $dir -PassThru
            Start-Sleep -Seconds $SettleSeconds
            $tree = @(Get-Descendants $p.Id)
            $engine = @($tree | Where-Object { $_.Name -like 'QtWebEngineProcess*' })
            $shape = @()
            $windows = @()
            foreach ($id in @($p.Id) + @($tree | Select-Object -ExpandProperty ProcessId)) {
                $live = Get-Process -Id $id -ErrorAction SilentlyContinue
                if ($live) {
                    $shape += ('{0}#{1}(threads={2},mem={3}MB)' -f $live.Name, $live.Id, $live.Threads.Count, [int]($live.WorkingSet64 / 1MB))
                    if ($live.MainWindowTitle) { $windows += $live.MainWindowTitle }
                }
            }
            $ok = -not $p.HasExited -and $engine.Count -gt 0 -and @($windows | Where-Object { $_ -like 'Mei - Workspace*' }).Count -gt 0
            "$candidate RESULT passed=$ok bootloader-exited=$($p.HasExited) engine-procs=$($engine.Count)"
            "$candidate WINDOWS $($windows -join ' | ')"
            "$candidate SHAPE $($shape -join ' | ')"
            if (-not $ok) { $failed = $true }
        } finally {
            if ($p) {
                $tree = @(Get-Descendants $p.Id)
                for ($i = $tree.Count - 1; $i -ge 0; $i--) { Stop-Process -Id $tree[$i].ProcessId -Force -ErrorAction SilentlyContinue }
                Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 3
            }
        }
    }
} catch {
    Write-Output ('SMOKE FAILED: ' + $_.Exception.Message)
    $failed = $true
} finally {
    foreach ($name in $variables) { [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process') }
    # All test files are generated under this unique workspace directory.
    if (Test-Path -LiteralPath $testRoot) { Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
if ($failed) { exit 1 }
exit 0
