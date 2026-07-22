$ErrorActionPreference = "Continue"

$ScriptFolder = "C:\Users\DLI\.local\bin"
$LogFile = "$ScriptFolder\CW_Weekly_task_run.log"

Set-Location $ScriptFolder

"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') --- Starting Weekly CW Downloads Queue ---" | Out-File $LogFile -Append

# --- 1. Outstanding RPO ---
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Running RPO_Downloader.py..." | Out-File $LogFile -Append
& python "$ScriptFolder\RPO_Downloader.py" *>> $LogFile
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Finished RPO_Downloader.py with exit code $LASTEXITCODE" | Out-File $LogFile -Append

# --- 2. RPO Summary ---
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Running RPOSummary_Downloader.py..." | Out-File $LogFile -Append
& python "$ScriptFolder\RPOSummary_Downloader.py" *>> $LogFile
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Finished RPOSummary_Downloader.py with exit code $LASTEXITCODE" | Out-File $LogFile -Append

# --- 3. CW Inventory ---
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Running CW_Inventory_Downloader.py..." | Out-File $LogFile -Append
& python "$ScriptFolder\CW_Inventory_Downloader.py" *>> $LogFile
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Finished CW_Inventory_Downloader.py with exit code $LASTEXITCODE" | Out-File $LogFile -Append

"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') --- All Weekly CW Downloads Completed ---" | Out-File $LogFile -Append
"" | Out-File $LogFile -Append

exit 0