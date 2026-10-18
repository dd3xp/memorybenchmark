param(
    [int]$Port=8765,
    [string]$AuthFile=(Join-Path $env:LOCALAPPDATA 'Memorybenchmark\web-auth.json')
)
$ErrorActionPreference='Stop'
$benchRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $benchRoot
$benchPython=(Get-Command python.exe -ErrorAction Stop).Source
$benchService=Join-Path $benchRoot '.runs\service'
New-Item -ItemType Directory -Force -Path $benchService | Out-Null
if (-not (Test-Path -LiteralPath $AuthFile -PathType Leaf)) { throw 'Web PIN verifier missing; refusing to start without authentication.' }
& $benchPython -u -m memorybenchmark --port $Port --log-dir .runs --watch-dir .runs/ga-cross-session --auth-file $AuthFile >> (Join-Path $benchService 'watch.log') 2>&1
exit $LASTEXITCODE
