# Register weekday 09:05 task. Runs only if this user is logged on. Does not wake the PC.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot "run_fq002_simnow.ps1"
$task = "FQ002-SimNow"
$tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$script`""
schtasks /Create /TN $task /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 09:05 /TR $tr /F /RL LIMITED | Out-Host
Write-Host "Registered $task -> $script (weekdays 09:05 dry-run, skipped if the PC is off)."
Write-Host "Step 2 (Aliyun SimNow auto) is required before --send. Remove: schtasks /Delete /TN $task /F"
