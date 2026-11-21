param([Parameter(Mandatory = $true)][string]$RootName)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$private = 'C:/Codes/memorybenchmark-private'
$scope = @{
    'dingo-normal-retain' = @('dingo-normal', 'retain', 16, '4fc7d7915f2b28af10c14d6041f1b1d732c7572cc681fd211289303bef5827f2', '129c2bb92664')
    'dingo-normal-clear' = @('dingo-normal', 'clear', 16, '970390ab062ab65f01babc21234e4c1d5e194536c07bfb257bbd03263f21c826', 'ad9ce7b10d12')
    'boar-normal-clear' = @('boar-normal', 'clear', 8, 'd4e9d791dbf3f32f51b6f30b97d080b4769fdf55644881dad652db9d316bec9f', 'e848eaae679e')
}
if (-not $scope.ContainsKey($RootName)) { throw 'This job is outside the diagnosed import repair.' }
$map, $condition, $index, $beforeHash, $token = $scope[$RootName]
$model = 'gemini-3.1-flash-lite'
$root = "$private/easy20-gemini-$model-$RootName-20261111"
$name = ('{0:D2}-T{0}-{1}' -f $index, $condition)
$recovery = "$root/bootstrap-history/reboot-recovery-v1"
$run = "$root/runtime-hermes/.runs/pilot-hermes-$condition-$map-$model-20261111"
$intentRoot = "$root/bootstrap-history/lease-expired-operator-v1/$name-$token"
$repair = "$root/bootstrap-history/owned-recovery-imports-v1"
$launcher = "$recovery/run.ps1"
$pause = "$recovery/paused.json"
$python = 'C:/Codes/memorybenchmark/.venv/Scripts/python.exe'

function Read-Receipt($path) {
    Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
}
function Get-Sha($path) {
    (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$scheduler = New-Object -ComObject Schedule.Service
$scheduler.Connect()
$task = $scheduler.GetFolder('\').GetTask("MemorybenchmarkGeminiEasyNormalHermes_${model}_${map}_${condition}_20261111")
$arguments = $task.Definition.Actions.Item(1).Arguments
$currentLauncher = [regex]::Match($arguments, '(?i)-File\s+"([^"]+\.ps1)"').Groups[1].Value
if (-not $task.Enabled -or $task.State -ne 3 -or
    [IO.Path]::GetFullPath($currentLauncher) -ne [IO.Path]::GetFullPath($launcher)) {
    throw 'Existing registered task is not at the owned, inactive boundary.'
}
if ((Get-Sha $launcher) -ne $beforeHash -or (Read-Receipt $pause).type -ne 'ModuleNotFoundError') {
    throw 'The diagnosed original import failure and launcher must both be present.'
}
if ((Get-Sha "$root/driver-started.json") -ne (Get-Sha "$intentRoot/driver-started.before.json")) {
    throw 'The driver identity changed after recovery staging.'
}
$pilot = Read-Receipt "$run/pilot.json"
$intent = Read-Receipt "$intentRoot/intent.json"
if (@($pilot.sessions).Count -ne ($index - 1) -or
    (Test-Path -LiteralPath "$run/sessions/$name") -or
    -not (Test-Path -LiteralPath "$intentRoot/paused-cleared.json") -or
    $intent.recovery_kind -ne 'operator') {
    throw 'The previously staged checkpoint is no longer the next task.'
}

$probe = @'
import importlib
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "runtime-hermes"))
for name in ("storage_guard", "gemini_transport", "chat_accounting"):
    source = Path(importlib.import_module(name).__file__).resolve()
    if source != root / (name + ".py"):
        raise ValueError("Unexpected owned adapter resolution: " + name)
for name in ("memorybenchmark.ga_runtime", "scripts.report_station_experiment"):
    source = Path(importlib.import_module(name).__file__).resolve()
    if not source.is_relative_to(root / "runtime-hermes"):
        raise ValueError("Unexpected frozen module resolution: " + name)
print("owned_imports_passed")
'@
$priorPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = $root
    $checked = $probe | & $python -X utf8 - $root
    if ($LASTEXITCODE -ne 0 -or $checked -ne 'owned_imports_passed') {
        throw 'Zero-model import preflight failed.'
    }
} finally {
    $env:PYTHONPATH = $priorPythonPath
}

$original = Get-Content -LiteralPath $launcher -Raw -Encoding UTF8
$prefix = '$env:PYTHONPATH = ' + [char]39 + $root + [char]39 + [Environment]::NewLine
$patched = $prefix + $original
$tokens = $null
$parseErrors = $null
$null = [System.Management.Automation.Language.Parser]::ParseInput($patched, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'Patched launcher syntax failed.' }

New-Item -Path $repair -ItemType Directory | Out-Null
$encoding = [Text.UTF8Encoding]::new($false)
$temporary = "$recovery/run.owned-imports.tmp"
[IO.File]::WriteAllText($temporary, $patched, $encoding)
[IO.File]::Replace($temporary, $launcher, "$repair/run.before.ps1")
$receipt = [ordered]@{
    utc = [DateTime]::UtcNow.ToString('o')
    map = $map
    condition = $condition
    task = $name
    zero_model_imports_passed = $true
    before_sha256 = Get-Sha "$repair/run.before.ps1"
    after_sha256 = Get-Sha $launcher
    committed_sessions = @($pilot.sessions).Count
    extra_task_retries = 0
}
[IO.File]::WriteAllText("$repair/receipt.json", ($receipt | ConvertTo-Json), $encoding)
Move-Item -LiteralPath $pause -Destination "$repair/import-pause.before.json"
if ($task.State -eq 3 -and $task.Definition.Settings.MultipleInstances -eq 2) {
    $null = $task.Run($null)
}
$receipt | ConvertTo-Json -Compress
