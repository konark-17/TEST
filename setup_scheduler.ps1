# Windows PowerShell script to manage daily GitHub Uploader scheduled task
param (
    [string]$Action = "menu", # "install", "run", "status", "remove", "menu"
    [string]$Time = "10:00"   # Default run time: 10:00 AM
)

$TaskName = "GitHubDailyUploader"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = (Get-Command python.exe -ErrorAction SilentlyContinue).Source

if (-not $PythonExe) {
    Write-Host "[ERROR] python.exe was not found in PATH." -ForegroundColor Red
    exit 1
}

$ScriptPath = Join-Path $ScriptDir "uploader.py"
$LogPath = Join-Path $ScriptDir "logs\scheduler.log"

function Install-Task {
    param([string]$RunTime)

    Write-Host "`nRegistering Scheduled Task: $TaskName..." -ForegroundColor Cyan
    Write-Host "Trigger: Daily at $RunTime"
    Write-Host "Script: $ScriptPath"

    $ActionCmd = New-ScheduledTaskAction `
        -Execute $PythonExe `
        -Argument "`"$ScriptPath`" --upload-one" `
        -WorkingDirectory $ScriptDir

    # Trigger: Daily at specified time
    $Trigger = New-ScheduledTaskTrigger -Daily -At $RunTime

    # Settings: Start when available if missed, wake if needed
    $Settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

    try {
        # Unregister previous task if exists
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

        Register-ScheduledTask `
            -TaskName $TaskName `
            -Action $ActionCmd `
            -Trigger $Trigger `
            -Settings $Settings `
            -Description "Automated GitHub Uploader - Commits and pushes 1 file daily" | Out-Null

        Write-Host "`n[SUCCESS] Scheduled task '$TaskName' registered successfully!" -ForegroundColor Green
        Write-Host "It will run automatically every day at $RunTime." -ForegroundColor Green
    }
    catch {
        Write-Host "`n[ERROR] Failed to register task: $_" -ForegroundColor Red
    }
}

function Run-TaskNow {
    Write-Host "`nTriggering scheduled task '$TaskName' now..." -ForegroundColor Cyan
    try {
        Start-ScheduledTask -TaskName $TaskName
        Write-Host "[SUCCESS] Task triggered! Check logs\uploader.log for execution details." -ForegroundColor Green
    }
    catch {
        Write-Host "[ERROR] Could not start task '$TaskName'. Make sure it is installed first." -ForegroundColor Red
    }
}

function Show-TaskStatus {
    Write-Host "`n--- Scheduled Task Status ---" -ForegroundColor Cyan
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        $taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName
        Write-Host "Task Name    : $($task.TaskName)"
        Write-Host "State        : $($task.State)"
        Write-Host "Last Run     : $($taskInfo.LastRunTime)"
        Write-Host "Last Result  : $($taskInfo.LastTaskResult)"
        Write-Host "Next Run     : $($taskInfo.NextRunTime)"
    } else {
        Write-Host "Task '$TaskName' is NOT installed." -ForegroundColor Yellow
        Write-Host "Run this script with -Action install to schedule daily uploads."
    }
}

function Remove-Task {
    Write-Host "`nRemoving scheduled task '$TaskName'..." -ForegroundColor Yellow
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-Host "[SUCCESS] Task '$TaskName' removed successfully." -ForegroundColor Green
    }
    catch {
        Write-Host "[INFO] Task '$TaskName' was not found or already removed." -ForegroundColor Gray
    }
}

switch ($Action.ToLower()) {
    "install" { Install-Task -RunTime $Time }
    "run"     { Run-TaskNow }
    "status"  { Show-TaskStatus }
    "remove"  { Remove-Task }
    "menu"    {
        while ($true) {
            Clear-Host
            Write-Host "==========================================================" -ForegroundColor Cyan
            Write-Host "    GitHub Daily Uploader - Windows Scheduler Manager      " -ForegroundColor White
            Write-Host "==========================================================" -ForegroundColor Cyan
            Write-Host " 1. Install / Update Daily Schedule (Default: 10:00 AM)"
            Write-Host " 2. Install with Custom Daily Time"
            Write-Host " 3. Check Scheduled Task Status"
            Write-Host " 4. Run Task Now (Test 1 upload)"
            Write-Host " 5. Remove Scheduled Task"
            Write-Host " 6. Exit"
            Write-Host "----------------------------------------------------------"
            $choice = Read-Host "Select an option (1-6)"

            switch ($choice) {
                "1" { Install-Task -RunTime "10:00"; Read-Host "`nPress Enter to continue..." }
                "2" {
                    $customTime = Read-Host "Enter daily time in 24h format (e.g. 09:30 or 18:00)"
                    if ($customTime) { Install-Task -RunTime $customTime }
                    Read-Host "`nPress Enter to continue..."
                }
                "3" { Show-TaskStatus; Read-Host "`nPress Enter to continue..." }
                "4" { Run-TaskNow; Read-Host "`nPress Enter to continue..." }
                "5" { Remove-Task; Read-Host "`nPress Enter to continue..." }
                "6" { exit 0 }
            }
        }
    }
    default {
        Write-Host "Unknown action: $Action. Valid actions: install, run, status, remove, menu"
    }
}

