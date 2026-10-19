param(
    [int]$Port=8765,
    [string]$AuthFile=(Join-Path $env:LOCALAPPDATA 'Memorybenchmark\web-auth.json'),
    [string]$TlsCert=$env:MEMORYBENCH_TLS_CERT,
    [string]$TlsKey=$env:MEMORYBENCH_TLS_KEY
)
$ErrorActionPreference='Stop'
$benchRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $benchRoot
$benchPython=(Get-Command python.exe -ErrorAction Stop).Source
$benchService=Join-Path $benchRoot '.runs\service'
New-Item -ItemType Directory -Force -Path $benchService | Out-Null
if (-not (Test-Path -LiteralPath $AuthFile -PathType Leaf)) { throw 'Web PIN verifier missing; refusing to start without authentication.' }
if (-not $TlsCert -or -not $TlsKey) { throw 'Native HTTPS requires both certificate paths; refusing plaintext startup.' }
if (-not (Test-Path -LiteralPath $TlsCert -PathType Leaf) -or -not (Test-Path -LiteralPath $TlsKey -PathType Leaf)) { throw 'HTTPS certificate or private key does not exist.' }
& $benchPython -u -m memorybenchmark --port $Port --log-dir .runs --auth-file $AuthFile --tls-cert $TlsCert --tls-key $TlsKey >> (Join-Path $benchService 'watch.log') 2>&1
exit $LASTEXITCODE
