$ErrorActionPreference = "Stop"

$ScriptFolder = "C:\Users\DLI\.local\bin"
$LogFile = "$ScriptFolder\vendor_po_status_task_run.log"

Set-Location $ScriptFolder

"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Starting BCLDB PO Status download..." | Out-File $LogFile -Append

try {
    # UPDATED: Now points to your newly created Python file
    & python "$ScriptFolder\vendor_po_status.py" --config "$ScriptFolder\vendor_bcldb_po_config.json" *>> $LogFile

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