param([int]$Port=8765)
$ErrorActionPreference='Stop'
$benchRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $benchRoot
$benchPython=(Get-Command python.exe -ErrorAction Stop).Source
$benchService=Join-Path $benchRoot '.runs\service'
New-Item -ItemType Directory -Force -Path $benchService | Out-Null
& $benchPython -u -m memorybenchmark --port $Port --log-dir .runs --watch-dir .runs/ga-cross-session >> (Join-Path $benchService 'watch.log') 2>&1
exit $LASTEXITCODE
