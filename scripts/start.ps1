param([string]$Config, [switch]$FullDevelopment, [switch]$DockerRedis)
$ErrorActionPreference = 'Stop'
$taskProjectRoot = Split-Path $PSScriptRoot -Parent
$taskPython = Join-Path $taskProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Follow README setup first.' }
$taskArguments = @((Join-Path $PSScriptRoot 'dev_runtime.py'), 'start')
if ($Config) { $taskArguments += @('--config', $Config) }
if ($FullDevelopment) { $taskArguments += '--full-development' }
if ($DockerRedis) { $taskArguments += '--docker-redis' }
& $taskPython @taskArguments
if ($LASTEXITCODE -ne 0) { throw 'ProjectTrace startup failed; see the specific message above.' }
