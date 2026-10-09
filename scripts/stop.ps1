$ErrorActionPreference = 'Stop'
$taskProjectRoot = Split-Path $PSScriptRoot -Parent
& (Join-Path $taskProjectRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'dev_runtime.py') stop
if ($LASTEXITCODE -ne 0) { throw 'ProjectTrace shutdown did not complete; see the message above.' }
