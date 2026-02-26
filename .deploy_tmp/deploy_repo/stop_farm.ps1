<#
.SYNOPSIS
    Phone Farm - Stop all running bot processes.

.DESCRIPTION
    Finds and terminates all python processes running run_device.py,
    plus their hosting console windows.

.PARAMETER Force
    Force kill processes (taskkill /F).

.PARAMETER DryRun
    Show which processes would be stopped without actually stopping them.

.EXAMPLE
    .\stop_farm.ps1
    .\stop_farm.ps1 -Force
    .\stop_farm.ps1 -DryRun
#>

param(
    [switch]$Force,
    [switch]$DryRun
)

Write-Host ""
Write-Host "Phone Farm - Process Stopper" -ForegroundColor White
Write-Host ""

# Find python processes running run_device.py
$botProcesses = Get-WmiObject Win32_Process -Filter "Name like '%python%'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "run_device\.py" } |
    Select-Object ProcessId, CommandLine

if (-not $botProcesses -or $botProcesses.Count -eq 0) {
    Write-Host "  No run_device.py processes found. Farm is already stopped." -ForegroundColor Green
    Write-Host ""
    exit 0
}

Write-Host "  Found $($botProcesses.Count) bot process(es):" -ForegroundColor Yellow
Write-Host ""

foreach ($p in $botProcesses) {
    $serial = "?"
    if ($p.CommandLine -match "run_device\.py\s+(\S+)") {
        $serial = $matches[1]
    }
    Write-Host "  PID $($p.ProcessId.ToString().PadRight(8))  serial=$serial" -ForegroundColor Cyan
}

if ($DryRun) {
    Write-Host ""
    Write-Host "  --DryRun: would stop the above processes." -ForegroundColor DarkGray
    Write-Host ""
    exit 0
}

# Stop processes
$mode = if ($Force) { "FORCE" } else { "GRACEFUL" }
Write-Host ""
Write-Host "  Stopping ($mode)..." -ForegroundColor White
Write-Host ""

$stopped = 0
foreach ($p in $botProcesses) {
    $serial = "?"
    if ($p.CommandLine -match "run_device\.py\s+(\S+)") {
        $serial = $matches[1]
    }

    Write-Host -NoNewline "  Stopping PID $($p.ProcessId) ($serial)... "

    try {
        if ($Force) {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
        } else {
            Stop-Process -Id $p.ProcessId -ErrorAction Stop
        }
        Write-Host "OK" -ForegroundColor Green
        $stopped++
    } catch {
        Write-Host "FAILED: $_" -ForegroundColor Red
    }
}

# Clean up hosting windows (cmd/powershell with run_device.py in cmdline)
$hostWindows = Get-WmiObject Win32_Process -Filter "Name like '%cmd%' or Name like '%powershell%'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "run_device\.py" }

if ($hostWindows -and $hostWindows.Count -gt 0) {
    Write-Host ""
    Write-Host "  Cleaning up $($hostWindows.Count) hosting window(s)..." -ForegroundColor DarkGray

    foreach ($w in $hostWindows) {
        try {
            Stop-Process -Id $w.ProcessId -Force -ErrorAction SilentlyContinue
        } catch { }
    }
}

Write-Host ""
Write-Host "  Stopped $stopped/$($botProcesses.Count) bot processes." -ForegroundColor Green
Write-Host ""
