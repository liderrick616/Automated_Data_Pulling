$ErrorActionPreference = "Stop"

$ScriptFolder = "C:\Users\DLI\.local\bin"
$LogFile = "$ScriptFolder\eliis_wednesday_raw_data_task_run.log"

Set-Location $ScriptFolder

"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Starting Wednesday eLIIS raw data download..." | Out-File $LogFile -Append

& python "$ScriptFolder\eliis_downloader.py" --config "$ScriptFolder\eliis_wednesday_raw_data_config.json" *>> $LogFile

$ExitCode = $LASTEXITCODE

"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Finished with exit code $ExitCode" | Out-File $LogFile -Append
"" | Out-File $LogFile -Append

exit $ExitCode
