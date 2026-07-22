# Run_AlbertaGR.ps1
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PyFile = Join-Path $ScriptDir "AlbertaGR.py"
$JsonFile = Join-Path $ScriptDir "AlbertaGR_raw.json"
$DownloadsDir = Join-Path $env:USERPROFILE "Downloads"
$WrapperLog = Join-Path $DownloadsDir ("AlbertaGR_wrapper_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

Write-Host "Starting AlbertaGR downloader..."
Write-Host "ScriptDir: $ScriptDir"
Write-Host "Python file: $PyFile"
Write-Host "JSON file: $JsonFile"
Write-Host "Wrapper log: $WrapperLog"

if (-not (Test-Path $PyFile)) {
    throw "Missing Python file: $PyFile"
}

if (-not (Test-Path $JsonFile)) {
    throw "Missing JSON config file: $JsonFile"
}

Write-Host ""
Write-Host "File timestamps:"
Get-Item $PyFile, $JsonFile | Select-Object FullName, LastWriteTime, Length | Format-List

Write-Host ""
Write-Host "Checking for newer debug markers inside AlbertaGR.py:"
Select-String -Path $PyFile -Pattern "Login start URL|02_login_attempts_summary|try_ajax_login" -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Running downloader..."
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue

if ($null -ne $pyLauncher) {
    & py -3 -u $PyFile --config $JsonFile 2>&1 | Tee-Object -FilePath $WrapperLog
    $ExitCode = $LASTEXITCODE
} else {
    & python -u $PyFile --config $JsonFile 2>&1 | Tee-Object -FilePath $WrapperLog
    $ExitCode = $LASTEXITCODE
}

Write-Host ""
Write-Host "Wrapper log saved to: $WrapperLog"

if ($ExitCode -ne 0) {
    throw "AlbertaGR downloader failed with exit code $ExitCode"
}