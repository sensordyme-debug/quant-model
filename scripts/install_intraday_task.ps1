# Registers the intraday sleeve launcher at 09:25 local (must be US Eastern) on weekdays.
#   .\scripts\install_intraday_task.ps1            # install / update
#   .\scripts\install_intraday_task.ps1 -Remove
param([switch]$Remove)

$taskName = "Quant Intraday Sleeve"
if ($Remove) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "removed $taskName"
    exit 0
}
$tz = [TimeZoneInfo]::Local.Id
if ($tz -notlike "*Eastern*") { Write-Warning "Local time zone is '$tz', not Eastern; 09:25 local is not 09:25 ET." }
$repo = (Resolve-Path "$PSScriptRoot\..").Path
$python = (& python -c "import sys; print(sys.executable)").Trim()
if (-not (Test-Path $python)) { throw "could not resolve python ($python)" }
$action = New-ScheduledTaskAction -Execute $python -Argument "`"$repo\scripts\intraday_launch.py`"" -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At 09:25
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 7) -StartWhenAvailable -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Intraday active sleeve on the IBKR paper account (scripts/intraday_launch.py -> intraday_trader.py)" -Force | Out-Null
Write-Host "registered '$taskName': $python $repo\scripts\intraday_launch.py at 09:25 Mon-Fri (runs until 15:42)"
