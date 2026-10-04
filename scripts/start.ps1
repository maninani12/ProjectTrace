$ErrorActionPreference = 'Stop'
$taskProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $taskProjectRoot
$taskPython = Join-Path $taskProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Run the setup instructions in README.md first.' }
New-Item -ItemType Directory -Force -Path data | Out-Null
& $taskPython -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
& $taskPython -m backend.seed
if ($LASTEXITCODE -ne 0) { throw 'Demo initialization failed.' }
$taskApiProcess = Start-Process -FilePath $taskPython -ArgumentList @('-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8011') -WorkingDirectory $taskProjectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput 'data\api.log' -RedirectStandardError 'data\api-error.log'
$taskUiProcess = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c','npm.cmd run dev') -WorkingDirectory (Join-Path $taskProjectRoot 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskProjectRoot 'data\ui.log') -RedirectStandardError (Join-Path $taskProjectRoot 'data\ui-error.log')
Write-Output "ProjectTrace: http://127.0.0.1:5181 (API PID $($taskApiProcess.Id), UI launcher PID $($taskUiProcess.Id)). Check data logs if ports are busy."
