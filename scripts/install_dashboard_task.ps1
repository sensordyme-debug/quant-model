# Registers the local Quant dashboard (scripts/dashboard.py) as a scheduled task that starts
# at logon for the current user and stays up: no execution time limit, restarted up to three
# times one minute apart if it dies, and a second start is ignored while an instance runs.
# The dashboard serves http://127.0.0.1:8787 only, is read-only apart from appending
# live/state/nav_history.jsonl, and holds IB Gateway clientId 81 - never run two of them.
#   .\scripts\install_dashboard_task.ps1            # install / update
#   .\scripts\install_dashboard_task.ps1 -Remove    # remove
param([switch]$Remove)

$taskName = "Quant Dashboard"
if ($Remove) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "removed $taskName"
    exit 0
}
$repo = (Resolve-Path "$PSScriptRoot\..").Path
# Resolve through any Store/App-Execution alias to the real interpreter; Task Scheduler does
# not reliably launch the WindowsApps alias files.
$python = (& python -c "import sys; print(sys.executable)").Trim()
if (-not (Test-Path $python)) { throw "could not resolve the python executable (got '$python')" }
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
# No --open: a logon task has no terminal to hand a browser to. The launcher installs
# fastapi/uvicorn on first start if they are missing.
$action = New-ScheduledTaskAction -Execute $python -Argument "`"$repo\scripts\dashboard.py`"" -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Days 365) -StartWhenAvailable `
    -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
# "PT0S" is Task Scheduler's "no time limit"; New-ScheduledTaskSettingsSet cannot express it as
# a TimeSpan, so the 365-day limit above stays as the fallback if this assignment is rejected.
try { $settings.ExecutionTimeLimit = "PT0S" } catch { Write-Warning "could not clear the execution time limit; keeping 365 days" }
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Local read-only Quant dashboard on http://127.0.0.1:8787 (scripts/dashboard.py, IB clientId 81)" -Force | Out-Null
Write-Host "registered '$taskName': $python $repo\scripts\dashboard.py at logon for $user -> http://127.0.0.1:8787"
Write-Host "start now:   Start-ScheduledTask -TaskName '$taskName'"
Write-Host "unregister:  .\scripts\install_dashboard_task.ps1 -Remove   (Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false)"
