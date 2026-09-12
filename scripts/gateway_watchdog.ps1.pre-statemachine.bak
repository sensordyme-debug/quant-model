# Restart the "OpenClaw Gateway" scheduled task when nothing is listening on its port.
# Registered by scripts/install_gateway_watchdog.ps1 to run every 5 minutes. The gateway died
# silently twice on 2026-09-12 (no log line, no crash event) while the task still reported
# "Running" because its wscript/cmd wrappers outlived the node process, so Task Scheduler's own
# restart-on-failure never fired. This closes that gap. Log: live/log/gateway_watchdog.log.
$port = 18789
$task = 'OpenClaw Gateway'
$logDir = Join-Path (Split-Path $PSScriptRoot -Parent) 'live\log'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir 'gateway_watchdog.log'
function Write-Log($m) { Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m) }
function Test-Listening { (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Measure-Object).Count -gt 0 }

if (Test-Listening) { exit 0 }
$info = Get-ScheduledTaskInfo -TaskName $task -ErrorAction SilentlyContinue
if ($info -and $info.LastRunTime -gt (Get-Date).AddMinutes(-3)) {
    Write-Log "port $port down but task started $($info.LastRunTime); giving it time"
    exit 0
}
Write-Log "port $port not listening; restarting task '$task'"
Stop-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process | Where-Object {
    ($_.CommandLine -match 'gateway\.(vbs|cmd)') -or ($_.Name -eq 'node.exe' -and $_.CommandLine -match 'openclaw')
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 3
Start-ScheduledTask -TaskName $task
Start-Sleep -Seconds 45
Write-Log ("restart result: listening={0}" -f (Test-Listening))
