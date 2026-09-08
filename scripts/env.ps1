# Dot-source this in PowerShell to get the native LEAN toolchain on PATH:
#   . .\scripts\env.ps1
$env:DOTNET_ROOT = "$env:LOCALAPPDATA\Microsoft\dotnet"
$env:PATH = "$env:DOTNET_ROOT;$env:LOCALAPPDATA\Programs\nodejs;$env:PATH"
$env:DOTNET_CLI_TELEMETRY_OPTOUT = "1"
$env:LEAN_PYTHON_HOME = "$env:LOCALAPPDATA\Python\pythoncore-3.11-64"
$env:PYTHONNET_PYDLL = "$env:LEAN_PYTHON_HOME\python311.dll"
$env:PYTHONHOME = $env:LEAN_PYTHON_HOME
$env:LEAN_ROOT = (Resolve-Path "$PSScriptRoot\..\..\Lean").Path
Write-Host "LEAN toolchain ready: dotnet=$(& "$env:DOTNET_ROOT\dotnet.exe" --version), LEAN_ROOT=$env:LEAN_ROOT"
