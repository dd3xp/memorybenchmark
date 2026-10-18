param(
    [Parameter(Mandatory=$true)][string]$BaseUrl,
    [string]$Archive,
    [string]$CredentialPath=(Join-Path $env:LOCALAPPDATA 'Memorybenchmark\gateway.dpapi'),
    [string]$Distro='Ubuntu',
    [string]$Model='gpt-5.6-luna',
    [ValidateSet('valley','lake-easy','loch-ness')][string]$Scenario='lake-easy',
    [string]$Resume
)
$ErrorActionPreference='Stop'
$benchRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $benchRoot
if (-not $Archive) { $Archive=Join-Path (Split-Path -Parent $benchRoot) 'memorybenchmark-private\GenericAgent_src.tar.xz' }
$benchPython=(Get-Command python.exe -ErrorAction Stop).Source
$benchEncrypted=(Get-Content -LiteralPath $CredentialPath -Raw).Trim()
$benchSecret=ConvertTo-SecureString $benchEncrypted
$benchPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($benchSecret)
try {
    $env:MEMORYBENCH_GATEWAY_KEY=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($benchPointer)
    $benchArguments=@('-u','-m','memorybenchmark.ga_experiment','--base-url',$BaseUrl,'--distro',$Distro)
    if ($Resume) { $benchArguments+=@('--resume',$Resume) }
    else {
        $benchArguments+=@($Archive,'--model',$Model,'--scenario',$Scenario,'--tasks','T1','T2','T3','T4')
        if ($Scenario -eq 'valley') { $benchArguments+=@('T5','T6') }
        $benchArguments+=@('--max-turns','48','--final-turns','6','--max-output-tokens','0')
    }
    $benchService=Join-Path $benchRoot '.runs\service'
    New-Item -ItemType Directory -Force -Path $benchService | Out-Null
    & $benchPython @benchArguments >> (Join-Path $benchService 'ga.log') 2>&1
    $benchExit=$LASTEXITCODE
} finally {
    Remove-Item Env:MEMORYBENCH_GATEWAY_KEY -ErrorAction SilentlyContinue
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($benchPointer)
    $benchSecret.Dispose()
}
exit $benchExit
