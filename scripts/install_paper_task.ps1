# Registers a Windows scheduled task that runs the paper rebalance at 15:45 local time on
# weekdays. The machine clock must be US Eastern for that to be 15:45 ET; the script warns if not.
#   .\scripts\install_paper_task.ps1            # install / update
#   .\scripts\install_paper_task.ps1 -Remove    # remove
param([switch]$Remove)

$taskName = "Quant Paper Rebalance"
if ($Remove) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "removed $taskName"
    exit 0
}
$tz = [TimeZoneInfo]::Local.Id
if ($tz -notlike "*Eastern*") {
    Write-Warning "Local time zone is '$tz', not Eastern. 15:45 local will not be 15:45 ET; adjust -At below."
}
$repo = (Resolve-Path "$PSScriptRoot\..").Path
$python = (Get-Command python).Source
$action = New-ScheduledTaskAction -Execute $python -Argument "`"$repo\scripts\paper_trade.py`"" -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At 15:45
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -StartWhenAvailable
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Rebalance the IBKR paper account with the champion strategy (scripts/paper_trade.py)" -Force | Out-Null
Write-Host "registered '$taskName': $python $repo\scripts\paper_trade.py at 15:45 Mon-Fri"
Write-Host "It only sends orders when live\APPROVED_PAPER.md exists; create live\HALT to flatten and stop."
