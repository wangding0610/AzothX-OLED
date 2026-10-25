param(
    [ValidateSet('start', 'stop', 'status', 'run')][string]$Action = 'start',
    [string]$PythonPath = ''
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $projectRoot '.runtime'
$pidFile = Join-Path $runtimeDir 'beijing-clock.pid'
# Supervisors started before the Beijing rename wrote this name.
$legacyPidFile = Join-Path $runtimeDir 'taipei-clock.pid'
$showPath = Join-Path $PSScriptRoot 'show.py'
$servicePath = Join-Path $PSScriptRoot 'clock_service.py'
$taskName = 'AzothX-BeijingClock'
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null

function Get-ClockProcess {
    foreach ($file in @($pidFile, $legacyPidFile)) {
        if (-not (Test-Path -LiteralPath $file)) { continue }
        $clockPid = 0
        if ([int]::TryParse(([string](Get-Content -LiteralPath $file -Raw)).Trim(), [ref]$clockPid)) {
            $candidate = Get-CimInstance Win32_Process -Filter "ProcessId = $clockPid"
            if ($candidate -and $candidate.CommandLine -like "*$showPath*" -and
                $candidate.CommandLine -match '\sclock\s.*--quiet') { return $candidate }
        }
    }
    return $null
}

$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task -and ($task.Actions.Arguments -join ' ') -notlike "*$PSCommandPath*" -and
    ($task.Actions.Arguments -join ' ') -notlike "*$servicePath*") {
    throw "A task named $taskName belongs to another project. It has not been changed."
}
$existing = Get-ClockProcess

if ($Action -eq 'stop') {
    if ($task) {
        Disable-ScheduledTask -TaskName $taskName | Out-Null
        Stop-ScheduledTask -TaskName $taskName
    }
    $existing = Get-ClockProcess
    if ($existing) { Stop-Process -Id $existing.ProcessId }
    foreach ($file in @($pidFile, $legacyPidFile)) {
        if (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file }
    }
    Add-Content -LiteralPath (Join-Path $runtimeDir 'clock-supervisor.log') -Encoding UTF8 -Value "[$([DateTimeOffset]::UtcNow.ToString('o'))] Stopped by user; login startup disabled."
    Write-Output 'Beijing clock stopped. Login startup and recovery disabled.'
    exit 0
}

if ($Action -eq 'status') {
    if ($existing) { Write-Output "Beijing clock is running. PID=$($existing.ProcessId)" }
    else { Write-Output 'Beijing clock is not running.' }
    if ($task) {
        Write-Output "Windows task: $($task.State); startup enabled=$($task.Settings.Enabled); host=$($task.Actions.Execute)"
        if ($existing -and $task.State -ne 'Running') {
            Write-Output 'Clock worker is alive, but its supervisor is not running.'
        }
    } else { Write-Output 'Windows task is not installed.' }
    exit 0
}

# Retain the interpreter selected when the task was originally installed.
if (-not $PythonPath -and $task) {
    $oldArguments = $task.Actions.Arguments -join ' '
    if ($oldArguments -match '(?:-PythonPath|--python)\s+"([^"]+)"') { $PythonPath = $Matches[1] }
}
if (-not $PythonPath) {
    $PythonPath = (Get-Command python -CommandType Application | Select-Object -First 1).Source
}
$pythonwPath = Join-Path (Split-Path -Parent $PythonPath) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf) -or
    -not (Test-Path -LiteralPath $pythonwPath -PathType Leaf)) {
    throw 'Both python.exe and pythonw.exe are required for windowless operation.'
}
$pythonwPath | Set-Content -LiteralPath (Join-Path $runtimeDir 'clock-pythonw.txt') -Encoding Unicode
$arguments = '"' + $servicePath + '" run --python "' + $PythonPath + '"'

# Compatibility for explicit old -Action run calls; the scheduled task no
# longer starts PowerShell. pythonw itself is a GUI-subsystem executable.
if ($Action -eq 'run') {
    $service = Start-Process -FilePath $pythonwPath -ArgumentList $arguments -WorkingDirectory $runtimeDir -WindowStyle Hidden -PassThru
    $null = $service.Handle
    $service.WaitForExit()
    exit $service.ExitCode
}

$taskAction = New-ScheduledTaskAction -Execute $pythonwPath -Argument $arguments -WorkingDirectory $runtimeDir
if (-not $task) {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
    $principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
    $settingsArgs = @{
        MultipleInstances = 'IgnoreNew'
        ExecutionTimeLimit = [TimeSpan]::Zero
        RestartCount = 3
        RestartInterval = New-TimeSpan -Minutes 1
        AllowStartIfOnBatteries = $true
        DontStopIfGoingOnBatteries = $true
        StartWhenAvailable = $true
    }
    $registration = @{
        TaskName = $taskName
        Action = $taskAction
        Trigger = $trigger
        Principal = $principal
        Settings = New-ScheduledTaskSettingsSet @settingsArgs
        Description = "Windowless custom Beijing OLED clock in $projectRoot."
    }
    $task = Register-ScheduledTask @registration
} elseif ($task.Actions.Execute -ne $pythonwPath -or ($task.Actions.Arguments -join ' ') -ne $arguments) {
    # Register the valid replacement before stopping the old console host.
    Set-ScheduledTask -TaskName $taskName -Action $taskAction | Out-Null
    Stop-ScheduledTask -TaskName $taskName
    $existing = Get-ClockProcess
    if ($existing) { Stop-Process -Id $existing.ProcessId }
    $task = Get-ScheduledTask -TaskName $taskName
}

if (-not @($task.Triggers | Where-Object { $_.Repetition.Interval -eq 'PT1M' }).Count) {
    $recoveryTrigger = New-ScheduledTaskTrigger -Once -At ([DateTime]::Now.AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes 1)
    Set-ScheduledTask -TaskName $taskName -Trigger (@($task.Triggers) + @($recoveryTrigger)) | Out-Null
}
if ($task.State -eq 'Running') {
    Write-Output 'Windowless Beijing clock supervisor is already running.'
    exit 0
}
$existing = Get-ClockProcess
if ($existing) { Stop-Process -Id $existing.ProcessId }
Enable-ScheduledTask -TaskName $taskName | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Output 'Windowless Beijing clock started. Login startup and automatic recovery enabled.'
