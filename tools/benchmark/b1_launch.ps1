# B1 formal launcher; process-local execution policy only. Never changes power settings.
$ErrorActionPreference="Stop"
$b1Out=Join-Path (Get-Location) "revision_notes/B1_primary_logs"
if (Test-Path -LiteralPath (Join-Path $b1Out "windows_start.json")) { throw "B1 start already exists; no implicit rerun." }
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/benchmark/b1_windows_snapshot.ps1 -SnapshotName windows_start.json
if ($LASTEXITCODE -ne 0) { throw "Windows start snapshot failed." }
$b1Proc=Start-Process -FilePath wsl.exe -ArgumentList @("-d","Ubuntu","--","env","COLUMNS=120","LINES=40","PYTHONDONTWRITEBYTECODE=1","python3","tools/benchmark/b1_run.py") -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput (Join-Path $b1Out "launcher.stdout") -RedirectStandardError (Join-Path $b1Out "launcher.stderr")
$b1Code=$b1Proc.ExitCode
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/benchmark/b1_windows_snapshot.ps1 -SnapshotName windows_end.json
if ($LASTEXITCODE -ne 0) { throw "Windows end snapshot failed; final environment not verified." }
[ordered]@{exit_code=$b1Code;closed_utc=[DateTime]::UtcNow.ToString("o")} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $b1Out "launcher_exit.json") -Encoding UTF8
exit $b1Code
