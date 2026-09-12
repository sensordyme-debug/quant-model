# Registers "OpenClaw Gateway Watchdog": runs scripts/gateway_watchdog.ps1 every 5 minutes and at
# logon, on battery too. Re-run to update. Remove with:
#   Unregister-ScheduledTask -TaskName 'OpenClaw Gateway Watchdog' -Confirm:$false
$repo = Split-Path $PSScriptRoot -Parent
$script = Join-Path $repo 'scripts\gateway_watchdog.ps1'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $script)
$t1 = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$t2 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName 'OpenClaw Gateway Watchdog' -Action $action -Trigger @($t1, $t2) -Settings $settings -Force | Out-Null
Get-ScheduledTask -TaskName 'OpenClaw Gateway Watchdog' | Select-Object TaskName, State
