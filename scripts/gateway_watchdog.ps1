# Thin shim. The watchdog logic lives in scripts/gateway_watchdog.py so it can be unit
# tested; this file stays as the scheduled task's action so the registered task
# ("OpenClaw Gateway Watchdog", every 5 minutes + at logon) does not have to be re-registered.
# AGENTS.md: do not change schedulers without inspecting and preserving existing state.
#
# The previous sleep-45s-then-probe-once implementation is kept beside this file as
# gateway_watchdog.ps1.pre-statemachine.bak for reference. Its verdict conflated "dead" with
# "slow": four of its six restarts on 2026-09-12 were logged as failures purely because the
# machine was at 98% commit charge and the gateway took longer than 45 s to bind.
$ErrorActionPreference = 'Continue'
$repo = Split-Path $PSScriptRoot -Parent
$py = "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe"
if (-not (Test-Path $py)) { $py = 'python' }
& $py (Join-Path $PSScriptRoot 'gateway_watchdog.py') @args
exit $LASTEXITCODE
