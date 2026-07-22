$ErrorActionPreference = "Stop"

$ScriptFolder = "C:\Users\DLI\.local\bin"

$LogFile = "$ScriptFolder\BCGR_task_run.log"

Set-Location $ScriptFolder

"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Starting BCGR download..." | Out-File $LogFile -Append

& python "$ScriptFolder\BCGR.py" *>> $LogFile

$ExitCode = $LASTEXITCODE

"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Finished with exit code $ExitCode" | Out-File $LogFile -Append

"" | Out-File $LogFile -Append

exit $ExitCode