param(
    [ValidateRange(1,65535)][int]$Port=8765
)
$ErrorActionPreference='Stop'
$benchTask=Get-ScheduledTask -TaskName MemorybenchmarkWatch
if ($benchTask.State -eq 'Running') {
    Stop-ScheduledTask -TaskName MemorybenchmarkWatch
}

# Task Scheduler may stop the PowerShell launcher but leave its Python child.
# Only terminate a verified benchmark listener on the requested service port.
$benchListeners=@(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
foreach ($benchProcessId in @($benchListeners.OwningProcess | Select-Object -Unique)) {
    if (-not $benchProcessId) { continue }
    $benchProcess=Get-CimInstance Win32_Process -Filter ('ProcessId='+$benchProcessId)
    if (-not $benchProcess) { continue }
    if ($benchProcess.CommandLine -notmatch '(?:^|\s)-m\s+memorybenchmark(?:\s|$)' -or
        $benchProcess.CommandLine -notmatch ('--port\s+'+$Port+'(?:\s|$)')) {
        throw "Port $Port is occupied by a different program; no process was terminated."
    }
    Stop-Process -Id $benchProcessId -ErrorAction Stop
}

Start-ScheduledTask -TaskName MemorybenchmarkWatch
for ($benchAttempt=0; $benchAttempt -lt 40; $benchAttempt++) {
    $benchCurrent=@(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($benchCurrent.Count) {
        Get-ScheduledTask -TaskName MemorybenchmarkWatch | Select-Object TaskName,State
        exit 0
    }
    Start-Sleep -Milliseconds 250
}
throw "The watch service did not listen on port $Port within the startup window."
