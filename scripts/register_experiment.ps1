param([Parameter(Mandatory=$true)][string]$JobFile,[int]$IntervalMinutes=5)
$ErrorActionPreference='Stop'
$job=Get-Content -LiteralPath $JobFile -Raw -Encoding UTF8|ConvertFrom-Json
if($job.schema -ne 'benchmark-job-1' -or $job.id -notmatch '^[0-9a-f]{32}$'){throw 'Invalid owned job specification'}
$root=[IO.Path]::GetFullPath((Split-Path -Parent $JobFile))
if($root -ne [IO.Path]::GetFullPath($job.root)){throw 'Job root mismatch'}
$entry=@'
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent/'runtime-hermes'))
from memorybenchmark.experiments.runner import main
main()
'@
[IO.File]::WriteAllText(($root+'/entry.py'),$entry,[Text.UTF8Encoding]::new($false))
$launch=@'
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$job=Get-Content -LiteralPath ($root+'/job.json') -Raw -Encoding UTF8|ConvertFrom-Json
if(Test-Path -LiteralPath ($root+'/result.json')){
 $result=Get-Content -LiteralPath ($root+'/result.json') -Raw -Encoding UTF8|ConvertFrom-Json
 $retention=$null
 if(Test-Path -LiteralPath ($root+'/retention.json')){$retention=Get-Content -LiteralPath ($root+'/retention.json') -Raw -Encoding UTF8|ConvertFrom-Json}
 $exit=$null
 if(Test-Path -LiteralPath ($root+'/driver-exit.json')){$exit=Get-Content -LiteralPath ($root+'/driver-exit.json') -Raw -Encoding UTF8|ConvertFrom-Json}
 if($result.archive.contents_verified -and $retention.phase -eq 'complete' -and $exit.exit_code -eq 0){
  $service=New-Object -ComObject Schedule.Service;$service.Connect()
  $service.GetFolder('\').GetTask('MemorybenchmarkExperiment_'+$job.id).Enabled=$false
  exit 0
 }
}
if(Test-Path -LiteralPath ($root+'/paused.json')){exit 0}
$registry=Get-Content -LiteralPath ($root+'/runtime-hermes/config/model-gateways.json') -Raw -Encoding UTF8|ConvertFrom-Json
$model=$registry.models.($job.model)
$gateway=$registry.gateways.($model.gateway)
$pointer=[IntPtr]::Zero;$plain=$null
try{
 if($model.gateway -eq 'google-gemini'){
  $connection=Get-Content -LiteralPath 'C:/Agents/GeminiGateway/data/connection-flash-lite.json' -Raw -Encoding UTF8|ConvertFrom-Json
  $env:MEMORYBENCH_GATEWAY_KEY=$connection.api_key
 }elseif($model.gateway -eq 'openai-subscription'){
  Add-Type -AssemblyName System.Security
  $taskStore=Join-Path $env:LOCALAPPDATA 'Memorybenchmark/gateway-task.dpapi'
  if(-not (Test-Path -LiteralPath $taskStore)){throw 'Run scripts/save_task_credential.ps1 on the server before dispatch'}
  $plain=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($taskStore),$null,[Security.Cryptography.DataProtectionScope]::LocalMachine)
  $env:MEMORYBENCH_GATEWAY_KEY=[Text.Encoding]::UTF8.GetString($plain)
 }else{throw 'Gateway credential provider is not configured'}
 $ErrorActionPreference='Continue'
 & $job.python -X utf8 -u ($root+'/entry.py') --job-file ($root+'/job.json') 1>> ($root+'/driver.stdout.log') 2>> ($root+'/driver.stderr.log')
 $code=$LASTEXITCODE
}finally{
 Remove-Item Env:MEMORYBENCH_GATEWAY_KEY -ErrorAction SilentlyContinue
 if($plain){[Array]::Clear($plain,0,$plain.Length)}
 if($pointer -ne [IntPtr]::Zero){[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)}
 $connection=$null;$secure=$null
}
exit $code
'@
[IO.File]::WriteAllText(($root+'/launch.ps1'),$launch,[Text.UTF8Encoding]::new($false))
$service=New-Object -ComObject Schedule.Service;$service.Connect();$folder=$service.GetFolder('\')
$taskName='MemorybenchmarkExperiment_'+$job.id
try{
 $existing=$folder.GetTask($taskName)
 # Stable job IDs make retrying the HTTP request idempotent.
 if($existing.Definition.Actions.Item(1).Arguments -notlike ('*'+$root+'/launch.ps1*')){throw 'Existing task belongs to a different root'}
 exit 0
}catch{
 if($_.Exception.Message -like '*different root*'){throw}
}
$definition=$service.NewTask(0)
$definition.RegistrationInfo.Description='Persistent paired Hermes experiment; only proven reboot boundaries resume automatically.'
$definition.Settings.ExecutionTimeLimit='PT0S';$definition.Settings.MultipleInstances=2
$definition.Settings.Hidden=$true;$definition.Settings.StartWhenAvailable=$true
$definition.Settings.DisallowStartIfOnBatteries=$false;$definition.Settings.StopIfGoingOnBatteries=$false
$definition.Settings.RunOnlyIfIdle=$false;$definition.Settings.IdleSettings.StopOnIdleEnd=$false
$definition.Settings.RestartInterval='PT1M';$definition.Settings.RestartCount=999
$boot=$definition.Triggers.Create(8);$boot.Enabled=$true;$boot.Delay='PT1M'
$trigger=$definition.Triggers.Create(1);$trigger.Enabled=$true
$trigger.StartBoundary=[DateTime]::Now.AddMinutes($IntervalMinutes).ToString('yyyy-MM-ddTHH:mm:ss')
$trigger.Repetition.Interval='PT'+$IntervalMinutes+'M'
$action=$definition.Actions.Create(0);$action.Path='powershell.exe'
$action.Arguments='-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$root+'/launch.ps1"'
$user=[Security.Principal.WindowsIdentity]::GetCurrent().Name
$definition.Principal.UserId=$user;$definition.Principal.LogonType=2
$registered=$folder.RegisterTaskDefinition($taskName,$definition,6,$user,$null,2,$null)
[IO.File]::WriteAllText(($root+'/task-definition.xml'),$registered.Xml,[Text.UTF8Encoding]::new($false))
$null=$registered.Run($null)
@{job=$job.id;task=$taskName;dispatched=$true;logon_type=2}|ConvertTo-Json -Compress
