$ErrorActionPreference = "Stop"

$ScriptFolder = "C:\Users\DLI\.local\bin"
$LogFile = "$ScriptFolder\vendor_bcldb_task_run.log"

Set-Location $ScriptFolder

"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Starting BCLDB PAR download..." | Out-File $LogFile -Append

try {
    & python "$ScriptFolder\vendor_bcldb_downloader.py" --config "$ScriptFolder\vendor_bcldb_raw_config.json" *>> $LogFile

    $ExitCode = $LASTEXITCODE

    if ($null -eq $ExitCode) {
        $ExitCode = 0
    }

    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Finished with exit code $ExitCode" | Out-File $LogFile -Append
    "" | Out-File $LogFile -Append

    exit $ExitCode
}
catch {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ERROR: $($_.Exception.Message)" | Out-File $LogFile -Append
    "" | Out-File $LogFile -Append

    exit 1
}
