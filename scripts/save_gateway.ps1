param([string]$CredentialPath=(Join-Path $env:LOCALAPPDATA 'Memorybenchmark\gateway.dpapi'))
$ErrorActionPreference='Stop'
# Read through stdin so the key is never part of a process command line.
$benchRaw=[Console]::ReadLine()
if ([string]::IsNullOrWhiteSpace($benchRaw)) { throw 'Gateway credential was not supplied on stdin' }
$benchSecure=ConvertTo-SecureString $benchRaw -AsPlainText -Force
try {
    $benchEncrypted=ConvertFrom-SecureString $benchSecure
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $CredentialPath) | Out-Null
    [IO.File]::WriteAllText($CredentialPath,$benchEncrypted)
    Write-Output 'Gateway credential stored using Windows user encryption.'
} finally { $benchRaw=$null; $benchSecure.Dispose() }
