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
# Windows PowerShell promotes native stderr to a terminating error under Stop.
# Give the web child real log handles so a disconnected browser request cannot
# terminate the supervising launcher. Each launch keeps its own complete logs.
$benchLaunch=(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8)
$benchStdout=Join-Path $benchService ('watch-'+$benchLaunch+'.stdout.log')
$benchStderr=Join-Path $benchService ('watch-'+$benchLaunch+'.stderr.log')
$benchArguments=@('-X','utf8','-u','-m','memorybenchmark','--port',[string]$Port,'--log-dir','.runs','--auth-file',$AuthFile,'--tls-cert',$TlsCert,'--tls-key',$TlsKey)
$benchArgumentLine=($benchArguments | ForEach-Object { '"'+$_.Replace('"','\"')+'"' }) -join ' '
[pscustomobject]@{started_at=$benchLaunch;stdout=$benchStdout;stderr=$benchStderr} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $benchService 'watch-process.json') -Encoding UTF8
$benchChild=Start-Process -FilePath $benchPython -ArgumentList $benchArgumentLine -WorkingDirectory $benchRoot -WindowStyle Hidden -RedirectStandardOutput $benchStdout -RedirectStandardError $benchStderr -Wait -PassThru
exit $benchChild.ExitCode
