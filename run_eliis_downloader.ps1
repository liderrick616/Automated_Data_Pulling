$ErrorActionPreference = "Stop"

$ScriptFolder = "C:\Users\DLI\.local\bin"
$LogFile = "$ScriptFolder\eliis_task_run.log"

Set-Location $ScriptFolder

"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Starting eLIIS download..." | Out-File $LogFile -Append

& python "$ScriptFolder\eliis_downloader.py" --config "$ScriptFolder\eliis_config.json" *>> $LogFile

$ExitCode = $LASTEXITCODE

"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Finished with exit code $ExitCode" | Out-File $LogFile -Append
"" | Out-File $LogFile -Append

exit $ExitCode
