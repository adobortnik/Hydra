<#
.SYNOPSIS
    Phone Farm - Multi-device launcher (PowerShell)

.DESCRIPTION
    Opens a new console window for each device running run_device.py.

.PARAMETER Devices
    Comma-separated device serials. Default: ALL active devices from DB.
    Example: -Devices "10.1.11.4:5555,10.1.11.3:5555"

.PARAMETER DryRun
    Preview which devices would be launched without actually starting them.

.PARAMETER Once
    Pass --once to each runner (run one cycle then exit).

.PARAMETER Delay
    Seconds between launching windows (default: 2).

.EXAMPLE
    .\launch_farm.ps1
    .\launch_farm.ps1 -Devices "10.1.11.4:5555,10.1.11.3:5555"
    .\launch_farm.ps1 -DryRun
    .\launch_farm.ps1 -Once
#>

param(
    [string]$Devices = "",
    [switch]$DryRun,
    [switch]$Once,
    [int]$Delay = 2
)

$FarmDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DbPath  = Join-Path $FarmDir "db\phone_farm.db"
$Python  = Join-Path $FarmDir "venv\Scripts\python.exe"
$RunScript = Join-Path $FarmDir "run_device.py"

if (-not (Test-Path $Python)) {
    $Python = "python"
}

# ---------------------------------------------------------------------------
# Query DB for devices
# ---------------------------------------------------------------------------
function Get-FarmDevices {
    $query = @"
SELECT d.device_serial, d.device_name, COUNT(a.id) as account_count
FROM devices d
JOIN accounts a ON a.device_serial = d.device_serial AND a.status = 'active'
GROUP BY d.device_serial
ORDER BY d.device_serial
"@

    $results = @()
    $tempScript = Join-Path $env:TEMP "pf_query_devices.py"

    @"
import sqlite3, json, sys
conn = sqlite3.connect(r'$DbPath')
conn.row_factory = sqlite3.Row
rows = conn.execute('''$query''').fetchall()
conn.close()
print(json.dumps([dict(r) for r in rows]))
"@ | Set-Content -Path $tempScript -Encoding UTF8

    $raw = & $Python $tempScript 2>$null
    if ($raw) {
        $results = $raw | ConvertFrom-Json
    }
    Remove-Item $tempScript -ErrorAction SilentlyContinue
    return $results
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
$allDevices = Get-FarmDevices

if ($Devices -ne "") {
    $requestedSerials = $Devices -split "," | ForEach-Object { $_.Trim().Replace(":", "_") }
    $filteredDevices = $allDevices | Where-Object { $requestedSerials -contains $_.device_serial }

    # Warn about missing
    $foundSerials = $filteredDevices | ForEach-Object { $_.device_serial }
    $missing = $requestedSerials | Where-Object { $foundSerials -notcontains $_ }
    if ($missing) {
        Write-Host "  WARNING: Not found in DB: $($missing -join ', ')" -ForegroundColor Red
    }
    $deviceList = $filteredDevices
} else {
    $deviceList = $allDevices
}

if ($deviceList.Count -eq 0) {
    Write-Host "`n  No devices to launch.`n" -ForegroundColor Red
    exit 1
}

# Display plan
Write-Host ""
Write-Host ("=" * 65) -ForegroundColor Green
Write-Host "  Phone Farm - Multi-Device Launcher (PowerShell)" -ForegroundColor Green
Write-Host ("=" * 65) -ForegroundColor Green
Write-Host "  Python  : $Python" -ForegroundColor DarkGray
Write-Host "  Devices : $($deviceList.Count)" -ForegroundColor Cyan
Write-Host ""

foreach ($d in $deviceList) {
    $name   = $d.device_name.PadRight(25)
    $serial = $d.device_serial.PadRight(22)
    $count  = $d.account_count
    Write-Host "  $name  $serial  $count accounts" -ForegroundColor Cyan
}

Write-Host ""

if ($DryRun) {
    Write-Host "  --DryRun: would launch $($deviceList.Count) windows. Exiting.`n" -ForegroundColor Magenta
    exit 0
}

# Launch windows
$extraArgs = ""
if ($Once) { $extraArgs = " --once" }

Write-Host "Launching $($deviceList.Count) device windows...`n" -ForegroundColor Green

$launched = 0
foreach ($d in $deviceList) {
    $serial = $d.device_serial
    $name   = $d.device_name
    $adbSerial = $serial.Replace("_", ":")
    $title  = "Phone Farm - $name ($serial)"

    Write-Host -NoNewline "  Launching $name ($serial)... "

    try {
        $argList = "-NoExit -Command `"& { `$host.UI.RawUI.WindowTitle = '$title'; Set-Location '$FarmDir'; & '$Python' '$RunScript' $adbSerial$extraArgs }`""
        Start-Process powershell -ArgumentList $argList
        Write-Host "OK" -ForegroundColor Green
        $launched++
    } catch {
        Write-Host "FAILED: $_" -ForegroundColor Red
    }

    if ($Delay -gt 0 -and $launched -lt $deviceList.Count) {
        Start-Sleep -Seconds $Delay
    }
}

Write-Host "`n  Done. $launched/$($deviceList.Count) windows launched." -ForegroundColor Green
Write-Host "  Use stop_farm.ps1 to shut them all down.`n" -ForegroundColor DarkGray
