# Automated Data Pulling

Windows-based Python download automation for eLIIS/MBLL, Vendor BCLDB, Alberta LiquorConnect, and Containerworld reports.

This repository contains Python downloaders, JSON configuration files, PowerShell wrappers, and Windows Task Scheduler commands for recurring data pulls. The scripts use Python's standard library for HTTP sessions, form submission, cookies, file handling, logging, ZIP extraction, and CSV/XLSX downloads.

> [!CAUTION]
> **Do not deploy the public repository as-is.** The current repository contains live-looking usernames/passwords in source code and JSON configuration files. Assume those credentials are compromised. Rotate them immediately, remove them from the current files, purge them from Git history, and keep real configuration files out of source control. This README intentionally does not reproduce any credential values.

## Table of contents

1. [What the repository downloads](#what-the-repository-downloads)
2. [Security actions required before use](#security-actions-required-before-use)
3. [Prerequisites](#prerequisites)
4. [Install the repository](#install-the-repository)
5. [Make the PowerShell wrappers portable](#make-the-powershell-wrappers-portable)
6. [Validate Python and JSON files](#validate-python-and-json-files)
7. [Configure and run each downloader](#configure-and-run-each-downloader)
8. [Create and manage scheduled tasks](#create-and-manage-scheduled-tasks)
9. [Task Scheduler GUI setup](#task-scheduler-gui-setup)
10. [Logs and output verification](#logs-and-output-verification)
11. [Troubleshooting](#troubleshooting)
12. [Known implementation limitations](#known-implementation-limitations)
13. [Recommended repository cleanup](#recommended-repository-cleanup)
14. [Maintenance checklist](#maintenance-checklist)
15. [Repository file map](#repository-file-map)

## What the repository downloads

| Job | Python script | Configuration | PowerShell wrapper | Main output |
|---|---|---|---|---|
| eLIIS MBLL daily files | `eliis_downloader.py` | `eliis_config.json` | `run_eliis_downloader.ps1` | Dated MBLL and common-file ZIPs |
| eLIIS Wednesday raw files | `eliis_downloader.py` | `eliis_wednesday_raw_data_config.json` | `run_eliis_wednesday_raw_data.ps1` | Fixed-name ZIPs plus extracted raw files |
| Vendor BCLDB product activity | `vendor_bcldb_downloader.py` | `vendor_bcldb_raw_config.json` | `vendor_bcldb_task_run.ps1` | Product Activity XLSX |
| Vendor BCLDB PO status | `vendor_po_status.py` | `vendor_bcldb_po_config.json` | `vendor_po_status_task_run.ps1` | PO Status XLSX |
| Alberta goods receipts | `AlbertaGR.py` | `AlbertaGR_raw.json` | `Run_AlbertaGR.ps1` | LiquorConnect receipts CSV |
| BC daily receipts | `BCGR.py` | `BCGR_raw.json` | `Run_BCGR.ps1` | Containerworld Daily Receipts CSV |
| Containerworld weekly queue | `RPO_Downloader.py`, `RPOSummary_Downloader.py`, `CW_Inventory_Downloader.py` | `BCGR_raw.json` for login credentials; output paths are currently in the Python files | `Run_CW_Weekly_Downloads.ps1` | Outstanding RPO, RPO Summary, and Inventory CSVs |

The repository is designed for Windows because it uses PowerShell wrappers, Windows-style paths, and Windows Task Scheduler (`schtasks.exe`).

## Security actions required before use

### 1. Rotate every exposed credential

Rotate credentials for all affected services before running the public copy:

- eLIIS/MBLL
- Vendor BCLDB
- Alberta LiquorConnect
- Containerworld

Changing or deleting the current file contents is not sufficient because old values remain in Git history.

### 2. Temporarily make the repository private

Make the repository private while credentials and history are being cleaned. If it must remain public, do not make it public again until secret scanning reports no active credentials.

### 3. Remove credentials from source code and tracked JSON

At minimum, inspect and clean these files:

- `eliis_downloader.py`
- `AlbertaGR.py`
- `AlbertaGR_raw.json`
- `BCGR_raw.json`
- `vendor_bcldb_raw_config.json`
- `vendor_bcldb_po_config.json`

Use placeholders in tracked examples, such as:

```json
{
  "username": "REPLACE_LOCALLY",
  "password": "REPLACE_LOCALLY"
}
```

A better pattern is to commit files named `*.example.json`, copy them locally to their operational names, and ignore the operational copies.

### 4. Purge secrets from Git history

Use a repository-history cleaning tool such as `git filter-repo` or the BFG Repo-Cleaner. Back up the repository first, coordinate the force-push with all users, and require every user to delete old clones and clone the cleaned repository again.

### 5. Add a `.gitignore`

A practical starting point is:

```gitignore
# Local credentials and operational configuration
AlbertaGR_raw.json
BCGR_raw.json
eliis_config.json
eliis_wednesday_raw_data_config.json
vendor_bcldb_raw_config.json
vendor_bcldb_po_config.json
*.local.json
secrets/

# Runtime logs and debug material
*.log
debug_*/
debug*/

# Python
__pycache__/
*.py[cod]

# Temporary and downloaded data
*.tmp
*.part
*.zip
*.csv
*.xlsx
downloads/

# Backups created by patch scripts
AlbertaGR_backup_*.py
```

Before adding these rules, rename the current sanitized JSON files to `*.example.json` so the repository still contains usable templates.

### 6. Protect local configuration files

Store operational configuration only on the machine that runs the task. Restrict the folder to the Windows account used by Task Scheduler. Do not place real credentials in a shared OneDrive/SharePoint folder, email, chat, or a public repository.

## Prerequisites

Install or confirm the following:

- Windows 10 or Windows 11
- Python 3; Python 3.10 or newer is recommended
- Windows PowerShell 5.1 or PowerShell 7
- Windows Task Scheduler access
- `git`, when cloning rather than downloading a ZIP
- Valid accounts for the relevant vendor websites
- Network/VPN access required by those websites
- Write access to every configured output directory
- An active OneDrive/SharePoint sync client when output paths point to synced folders

The inspected scripts use Python standard-library modules and do not require `pip install` for normal execution.

## Install the repository

### Option A: clone with Git

Open PowerShell and choose an installation folder:

```powershell
$InstallDir = "C:\Automated_Data_Pulling"
git clone https://github.com/liderrick616/Automated_Data_Pulling.git $InstallDir
Set-Location $InstallDir
```

### Option B: preserve the existing `.local\bin` layout

The current wrappers commonly expect this location:

```powershell
$InstallDir = "$env:USERPROFILE\.local\bin"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
```

Download or copy the repository files into `$InstallDir`, then confirm:

```powershell
Get-ChildItem $InstallDir
```

### Important layout rule

Keep each script beside the configuration file its wrapper expects unless you also update the wrapper/script:

```text
<InstallDir>\
  AlbertaGR.py
  AlbertaGR_raw.json
  BCGR.py
  BCGR_raw.json
  eliis_downloader.py
  eliis_config.json
  eliis_wednesday_raw_data_config.json
  vendor_bcldb_downloader.py
  vendor_bcldb_raw_config.json
  vendor_po_status.py
  vendor_bcldb_po_config.json
  *.ps1
```

## Make the PowerShell wrappers portable

Several wrappers contain a machine-specific line similar to:

```powershell
$ScriptFolder = "C:\Users\<WindowsUser>\.local\bin"
```

For a repository that can be moved safely, replace that line with:

```powershell
$ScriptFolder = Split-Path -Parent $MyInvocation.MyCommand.Path
```

Apply that change to these wrappers:

- `run_eliis_downloader.ps1`
- `run_eliis_wednesday_raw_data.ps1`
- `vendor_bcldb_task_run.ps1`
- `vendor_po_status_task_run.ps1`
- `Run_BCGR.ps1`
- `Run_CW_Weekly_Downloads.ps1`

`Run_AlbertaGR.ps1` already resolves its own script directory.

### Use a reliable Python executable

A scheduled task may not receive the same `PATH` as an interactive PowerShell window. If a wrapper reports that `python` is not recognized, either:

1. Use the Python launcher:

```powershell
& py -3 "<path-to-script.py>"
```

2. Or set an absolute interpreter path in the wrapper:

```powershell
$PythonExe = "C:\Program Files\Python313\python.exe"
& $PythonExe "<path-to-script.py>"
```

Find installed interpreters with:

```powershell
py -0p
Get-Command py -ErrorAction SilentlyContinue
Get-Command python -ErrorAction SilentlyContinue
```

## Validate Python and JSON files

Run these checks before testing a live download.

### Confirm Python

```powershell
py -3 --version
```

If `py` is unavailable:

```powershell
python --version
```

### Compile-check all operational Python scripts

```powershell
Set-Location $InstallDir

$Scripts = @(
    "eliis_downloader.py",
    "vendor_bcldb_downloader.py",
    "vendor_po_status.py",
    "AlbertaGR.py",
    "BCGR.py",
    "RPO_Downloader.py",
    "RPOSummary_Downloader.py",
    "CW_Inventory_Downloader.py"
)

foreach ($Script in $Scripts) {
    Write-Host "Checking $Script"
    py -3 -m py_compile (Join-Path $InstallDir $Script)
    if ($LASTEXITCODE -ne 0) {
        throw "Python compile check failed: $Script"
    }
}
```

The single-file Alberta check from the existing workflow is:

```powershell
py -3 -m py_compile .\AlbertaGR.py
```

### Validate JSON syntax

```powershell
$ConfigFiles = @(
    "eliis_config.json",
    "eliis_wednesday_raw_data_config.json",
    "vendor_bcldb_raw_config.json",
    "vendor_bcldb_po_config.json",
    "AlbertaGR_raw.json",
    "BCGR_raw.json"
)

foreach ($ConfigFile in $ConfigFiles) {
    $Path = Join-Path $InstallDir $ConfigFile
    Get-Content -Raw $Path | ConvertFrom-Json | Out-Null
    Write-Host "Valid JSON: $ConfigFile"
}
```

### JSON path rules

In JSON, either double each backslash:

```json
"output_dir": "C:\\Data\\BCLDB"
```

or use forward slashes:

```json
"output_dir": "C:/Data/BCLDB"
```

Absolute paths are recommended. The eLIIS downloader does not currently expand `%USERPROFILE%` in its download paths, so use a complete path in eLIIS JSON files.

## Configure and run each downloader

Always complete a successful manual run before creating a scheduled task.

---

## eLIIS / MBLL downloader

### Files

- Script: `eliis_downloader.py`
- Daily config: `eliis_config.json`
- Wednesday raw config: `eliis_wednesday_raw_data_config.json`
- Daily wrapper: `run_eliis_downloader.ps1`
- Wednesday wrapper: `run_eliis_wednesday_raw_data.ps1`

### What it does

The eLIIS downloader:

1. Opens the configured login page.
2. Parses the login form.
3. Maintains an authenticated cookie session.
4. Downloads every object in the `downloads` array.
5. Writes to a temporary `.tmp` file before replacing the final file.
6. Logs file size and SHA-256.
7. Retries a failed download up to three times.
8. Optionally extracts ZIP files with a path-safety check.

### Current credential limitation

The current `eliis_downloader.py` contains credentials directly in the login function. The `username_env` and `password_env` properties found in the Wednesday JSON are not consumed by the current script. Do not assume that setting `ELIIS_USER` and `ELIIS_PASSWORD` will work until the login function is refactored to read them.

A secure implementation should obtain credentials from environment variables, Windows Credential Manager, or another secret store, for example conceptually:

```python
username = os.environ[config.get("username_env", "ELIIS_USER")]
password = os.environ[config.get("password_env", "ELIIS_PASSWORD")]
```

Do not add actual values to this README or commit them to Python/JSON.

### Configure `eliis_config.json`

A sanitized structure is:

```json
{
  "login_url": "https://eliis.mbll.ca/liis/login/loginProxy.jsp",
  "username_field": "",
  "password_field": "",
  "download_dir": "C:/Data/eLIIS",
  "downloads": [
    {
      "name": "get_your_items",
      "url": "https://eliis.mbll.ca/liis/Downloads/FileDownloadsGetYourItems.do",
      "download_dir": "C:/Data/eLIIS/MBLL",
      "filename": "MBLL{mmddyyyy}.zip",
      "overwrite": true
    },
    {
      "name": "get_common_file",
      "url": "https://eliis.mbll.ca/liis/Downloads/FileDownloadsGetCommonFile.do",
      "download_dir": "C:/Data/eLIIS/CommonFile",
      "filename": "CSTVEND-{mm}-{dd}-{yyyy}.zip",
      "overwrite": true
    }
  ]
}
```

Supported filename placeholders include:

- `{date}` -> `yyyy-mm-dd`
- `{yyyymmdd}`
- `{mmddyyyy}`
- `{mm}`
- `{dd}`
- `{yyyy}`
- `{datetime}` -> timestamp

Optional ZIP settings per download:

```json
{
  "extract_zip": true,
  "extract_to": "C:/Data/eLIIS/Raw",
  "extract_overwrite": true
}
```

### Inspect the login form

Use this when the website changes or login field detection fails:

```powershell
Set-Location $InstallDir
py -3 .\eliis_downloader.py --config .\eliis_config.json --inspect-login
```

Copy the detected username/password field names into `username_field` and `password_field` only when auto-detection is incorrect.

### List candidate download links

```powershell
py -3 .\eliis_downloader.py --config .\eliis_config.json --list-download-links
```

### Run the daily download manually

```powershell
py -3 .\eliis_downloader.py --config .\eliis_config.json
```

Equivalent absolute-path form:

```powershell
py -3 "$InstallDir\eliis_downloader.py" --config "$InstallDir\eliis_config.json"
```

### Run the Wednesday raw download manually

```powershell
py -3 .\eliis_downloader.py --config .\eliis_wednesday_raw_data_config.json
```

The current Wednesday configuration uses fixed ZIP filenames and extracts them into a raw-data folder. With `overwrite` and `extract_overwrite` enabled, a new run replaces same-name files.

### Run through the wrappers

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$InstallDir\run_eliis_downloader.ps1"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$InstallDir\run_eliis_wednesday_raw_data.ps1"
```

### eLIIS logs

Look for:

- `eliis_downloader.log`
- `eliis_task_run.log`
- `eliis_wednesday_raw_data_task_run.log`

---

## Vendor BCLDB product-activity downloader

### Files

- Script: `vendor_bcldb_downloader.py`
- Config: `vendor_bcldb_raw_config.json`
- Wrapper: `vendor_bcldb_task_run.ps1`

### What it does

The script logs into the Vendor BCLDB site, opens the configured report page, submits the report/export form, validates that the response appears to be an Excel workbook, writes a `.part` file, and then replaces the final XLSX atomically.

### Configure `vendor_bcldb_raw_config.json`

The main settings are:

| Setting | Purpose |
|---|---|
| `username`, `password` | Current plaintext login fields; move these to a secure local source |
| `login_page_url` | Initial login page |
| `login_submit_url` | Login form target |
| `sales_info_url` | Authenticated landing/report area |
| `report_page_url` | Product Activity report page |
| `report_name` | Report identifier |
| `download_button_text` | Expected export control, currently Excel 2007 |
| `agent_numbers` | Supplier/agent numbers to include |
| `output_dir` | Destination directory |
| `filename_pattern` | Output filename with date placeholders |
| `skip_weekends` | Skip Saturday/Sunday unless `--force` is used |
| `http_timeout_seconds` | HTTP timeout |
| `debug` | Enable debug artifacts |
| `debug_dir` | Folder for debug HTML/form summaries |
| `form_field_overrides` | Optional site-specific form values |

The current filename pattern is date-based. Keep the report and agent-number settings aligned with the vendor account.

### Manual run

```powershell
Set-Location $InstallDir
py -3 .\vendor_bcldb_downloader.py --config .\vendor_bcldb_raw_config.json
```

### Force a weekend run

```powershell
py -3 .\vendor_bcldb_downloader.py --config .\vendor_bcldb_raw_config.json --force
```

### Wrapper run

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$InstallDir\vendor_bcldb_task_run.ps1"
```

### Debugging BCLDB

Set this in the local config:

```json
"debug": true
```

Then inspect the configured debug directory, especially files such as:

- `report_page.html`
- `report_forms.txt`
- request/response metadata files

Do not commit debug HTML because it may contain account/session information.

---

## Vendor BCLDB PO-status downloader

### Files

- Script: `vendor_po_status.py`
- Config: `vendor_bcldb_po_config.json`
- Wrapper: `vendor_po_status_task_run.ps1`

### Important manual-run rule

The script's default config argument currently points to the raw Product Activity config. Always provide the PO config explicitly:

```powershell
Set-Location $InstallDir
py -3 .\vendor_po_status.py --config .\vendor_bcldb_po_config.json
```

### Force a weekend run

```powershell
py -3 .\vendor_po_status.py --config .\vendor_bcldb_po_config.json --force
```

### Wrapper run

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$InstallDir\vendor_po_status_task_run.ps1"
```

### Output and debug settings

The current PO configuration selects the "Purchase Order Report - Past 90 days" report, writes a date-stamped XLSX, skips weekends by default, and enables a PO-specific debug folder. Update `output_dir`, filename rules, and report options for the deployment machine.

---

## Alberta LiquorConnect goods-receipts downloader

### Files

- Script: `AlbertaGR.py`
- Config: `AlbertaGR_raw.json`
- Wrapper: `Run_AlbertaGR.ps1`
- Backup wrapper: `Run_AlbertaGR_Backup.ps1`
- Historical patch utilities: `patch_export_by_error.py`, `patch_export_cultureoverrides.py`, `patch_skip_saturdays.py`

### What it does

The downloader authenticates to LiquorConnect, handles the report form and ReportViewer export workflow, selects a report date, and downloads a CSV. Debug mode writes timestamped diagnostics that can be used when the site changes.

### Configure `AlbertaGR_raw.json`

Review at least:

- Login/report URLs
- `username` and `password` placeholders
- Login field names and event targets, when needed
- Report date field names and formats
- `report_days_back`
- Saturday handling
- Output prefix and output date format
- `downloads_dir`
- `debug` and `debug_dir`
- HTTP timeout
- MFA field/event settings, when the site requires them

The script can override the JSON username/password with:

- `ALBERTAGR_USERNAME`
- `ALBERTAGR_PASSWORD`

It can read a six-digit MFA code from `ALBERTAGR_MFA_CODE`; otherwise it prompts interactively.

> [!WARNING]
> The current MFA submission path also contains a hardcoded password assignment. Remove it and use the configured/secure password before relying on environment overrides. A task running in the background cannot answer the interactive MFA prompt, so unattended execution may fail whenever a fresh MFA code is required.

### Compile check

```powershell
Set-Location $InstallDir
py -3 -m py_compile .\AlbertaGR.py
```

### Manual Python run

```powershell
py -3 .\AlbertaGR.py --config .\AlbertaGR_raw.json
```

### Test a specific report date

Use ISO format:

```powershell
py -3 .\AlbertaGR.py --config .\AlbertaGR_raw.json --date 2026-07-21
```

### Enable extra debug output

```powershell
py -3 .\AlbertaGR.py --config .\AlbertaGR_raw.json --debug
```

### Run the PowerShell wrapper

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\Run_AlbertaGR.ps1
```

The wrapper checks that the Python and JSON files exist, prefers `py -3`, falls back to `python`, captures output in a timestamped log under the user's Downloads folder, and treats a nonzero Python exit code as a failure.

### MFA scheduling guidance

For initial deployment:

1. Run the script interactively.
2. Confirm whether every run requires a new emailed code.
3. If MFA is always required, use a task configured to run only while the user is logged on and be prepared to supply the code, or redesign authentication with an approved unattended method.
4. Do not store a reusable MFA code in source control.

### Patch utilities

The `patch_*.py` files modify `AlbertaGR.py` in place and create backup copies. They are maintenance/migration tools, not normal downloader commands. Do not run them as scheduled tasks. Commit or back up the current working script before using one, inspect its diff afterward, and compile-test the result.

---

## BC daily receipts downloader (`BCGR.py`)

### Files

- Script: `BCGR.py`
- Config: `BCGR_raw.json`
- Wrapper: `Run_BCGR.ps1`

### What it does

The script logs into Containerworld, initializes the report session, requests Daily Receipts data, and saves a CSV. The current script selects a date range from four days before the run date through the run date.

### Configure `BCGR_raw.json`

The current config contains:

```json
{
  "username": "REPLACE_LOCALLY",
  "password": "REPLACE_LOCALLY",
  "download_dir": "%USERPROFILE%\\Downloads"
}
```

The script expands Windows environment variables in `download_dir`.

### Manual run

```powershell
Set-Location $InstallDir
py -3 .\BCGR.py
```

`BCGR.py` does not currently accept a `--config` argument. It always loads `BCGR_raw.json` from the script directory.

### Wrapper run

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$InstallDir\Run_BCGR.ps1"
```

### Output

The script uses the server-provided filename when available and otherwise generates a Daily Receipts CSV name. Verify the resulting file is a CSV rather than an HTML error page.

---

## Containerworld weekly inventory and RPO queue

### Files

- `RPO_Downloader.py`
- `RPOSummary_Downloader.py`
- `CW_Inventory_Downloader.py`
- `BCGR_raw.json` for the shared Containerworld login
- `Run_CW_Weekly_Downloads.ps1`

### What the queue downloads

The wrapper runs these scripts in order:

1. `RPO_Downloader.py` -> Outstanding RPO CSV
2. `RPOSummary_Downloader.py` -> RPO Summary CSV
3. `CW_Inventory_Downloader.py` -> Inventory CSV

### Required path edits

All three Python scripts currently read credentials from `BCGR_raw.json`, but their output directories are hardcoded in the Python source. Before running, edit the `DOWNLOAD_DIR` assignment in each script or refactor it into JSON configuration.

Recommended future JSON structure:

```json
{
  "username": "REPLACE_LOCALLY",
  "password": "REPLACE_LOCALLY",
  "daily_receipts_dir": "C:/Data/Containerworld/DailyReceipts",
  "outstanding_rpo_dir": "C:/Data/Containerworld/OutstandingRPO",
  "rpo_summary_dir": "C:/Data/Containerworld/RPOSummary",
  "inventory_dir": "C:/Data/Containerworld/Inventory"
}
```

### Run each script manually

```powershell
Set-Location $InstallDir

py -3 .\RPO_Downloader.py
py -3 .\RPOSummary_Downloader.py
py -3 .\CW_Inventory_Downloader.py
```

Check each output before using the combined wrapper.

### Run the weekly wrapper

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$InstallDir\Run_CW_Weekly_Downloads.ps1"
```

### Critical wrapper limitation

The current wrapper logs each Python exit code but ends with `exit 0`. Task Scheduler can therefore report success even when one or more downloads failed.

Replace it with failure propagation similar to this:

```powershell
$ErrorActionPreference = "Continue"
$ScriptFolder = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogFile = Join-Path $ScriptFolder "CW_Weekly_task_run.log"
$Failed = $false

$Scripts = @(
    "RPO_Downloader.py",
    "RPOSummary_Downloader.py",
    "CW_Inventory_Downloader.py"
)

foreach ($Script in $Scripts) {
    $ScriptPath = Join-Path $ScriptFolder $Script
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Running $Script" |
        Out-File $LogFile -Append

    & py -3 $ScriptPath *>> $LogFile
    $ExitCode = $LASTEXITCODE

    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Script exit code: $ExitCode" |
        Out-File $LogFile -Append

    if ($ExitCode -ne 0) {
        $Failed = $true
    }
}

if ($Failed) {
    exit 1
}

exit 0
```

## Create and manage scheduled tasks

Run task-creation commands from PowerShell. Set the install directory first:

```powershell
$InstallDir = "$env:USERPROFILE\.local\bin"
```

Change this value when the repository is installed elsewhere.

### eLIIS MBLL daily download: Monday-Friday at 11:00

Create or replace the task:

```powershell
schtasks.exe /Create `
  /TN "eLIIS MBLL Daily Download" `
  /SC WEEKLY `
  /D MON,TUE,WED,THU,FRI `
  /ST 11:00 `
  /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$InstallDir\run_eliis_downloader.ps1`"" `
  /F
```

Run immediately:

```powershell
schtasks.exe /Run /TN "eLIIS MBLL Daily Download"
```

Query details and last result:

```powershell
schtasks.exe /Query /TN "eLIIS MBLL Daily Download" /V /FO LIST
```

Delete:

```powershell
schtasks.exe /Delete /TN "eLIIS MBLL Daily Download" /F
```

### eLIIS Wednesday raw-data download

The supplied workflow references an existing task but does not specify its original creation time.

Run it:

```powershell
schtasks.exe /Run /TN "eLIIS MBLL Wednesday Raw Data Download"
```

Query it:

```powershell
schtasks.exe /Query /TN "eLIIS MBLL Wednesday Raw Data Download" /V /FO LIST
```

Example creation command; change `$WednesdayRawTime` before use:

```powershell
$WednesdayRawTime = "11:15"

schtasks.exe /Create `
  /TN "eLIIS MBLL Wednesday Raw Data Download" `
  /SC WEEKLY `
  /D WED `
  /ST $WednesdayRawTime `
  /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$InstallDir\run_eliis_wednesday_raw_data.ps1`"" `
  /F
```

### Vendor BCLDB daily downloader

Manual run:

```powershell
py -3 "$InstallDir\vendor_bcldb_downloader.py" --config "$InstallDir\vendor_bcldb_raw_config.json"
```

Run the existing task:

```powershell
schtasks.exe /Run /TN "Vendor BCLDB Daily Downloader"
```

Query it:

```powershell
schtasks.exe /Query /TN "Vendor BCLDB Daily Downloader" /V /FO LIST
```

The original schedule was not supplied. To recreate it, use Task Scheduler GUI or adapt the generic template below with the required days/time.

### BCLDB PO Status download

Manual run:

```powershell
py -3 "$InstallDir\vendor_po_status.py" --config "$InstallDir\vendor_bcldb_po_config.json"
```

Run the existing task:

```powershell
schtasks.exe /Run /TN "BCLDB PO Status Download"
```

Query it:

```powershell
schtasks.exe /Query /TN "BCLDB PO Status Download" /V /FO LIST
```

### AlbertaGR weekly downloader

Compile and test manually first:

```powershell
Set-Location $InstallDir
py -3 -m py_compile .\AlbertaGR.py
powershell.exe -ExecutionPolicy Bypass -File .\Run_AlbertaGR.ps1
```

Run the existing task:

```powershell
schtasks.exe /Run /TN "AlbertaGR Weekly Downloader"
```

Query details:

```powershell
schtasks.exe /Query /TN "AlbertaGR Weekly Downloader" /V /FO LIST
```

Because the original trigger was not supplied, inspect the query output before recreating the task.

### BCGR Daily Receipts: Tuesday and Friday at 10:55

Create or replace:

```powershell
schtasks.exe /Create `
  /TN "BCGR Daily Receipts Download" `
  /SC WEEKLY `
  /D TUE,FRI `
  /ST 10:55 `
  /TR "powershell.exe -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File `"$InstallDir\Run_BCGR.ps1`"" `
  /F
```

Run immediately:

```powershell
schtasks.exe /Run /TN "BCGR Daily Receipts Download"
```

Query:

```powershell
schtasks.exe /Query /TN "BCGR Daily Receipts Download" /V /FO LIST
```

Delete:

```powershell
schtasks.exe /Delete /TN "BCGR Daily Receipts Download" /F
```

### Containerworld weekly queue: Tuesday at 10:20

Create or replace:

```powershell
schtasks.exe /Create `
  /TN "CW Weekly Inventory Downloads" `
  /SC WEEKLY `
  /D TUE `
  /ST 10:20 `
  /TR "powershell.exe -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File `"$InstallDir\Run_CW_Weekly_Downloads.ps1`"" `
  /F
```

Run the matching task:

```powershell
schtasks.exe /Run /TN "CW Weekly Inventory Downloads"
```

Query:

```powershell
schtasks.exe /Query /TN "CW Weekly Inventory Downloads" /V /FO LIST
```

Delete:

```powershell
schtasks.exe /Delete /TN "CW Weekly Inventory Downloads" /F
```

> [!NOTE]
> A command supplied alongside the Containerworld notes ran `BCLDB PO Status Download`. That is a different task. Use `CW Weekly Inventory Downloads` to start the Containerworld queue and use `BCLDB PO Status Download` only for the PO-status job.

### Generic weekly task template

Use this for jobs whose original trigger was not supplied:

```powershell
$TaskName = "REPLACE WITH TASK NAME"
$Days = "MON,TUE,WED,THU,FRI"
$Time = "11:00"
$Wrapper = Join-Path $InstallDir "REPLACE_WITH_WRAPPER.ps1"
$TaskAction = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$Wrapper`""

schtasks.exe /Create `
  /TN $TaskName `
  /SC WEEKLY `
  /D $Days `
  /ST $Time `
  /TR $TaskAction `
  /F
```

### Common task lifecycle commands

```powershell
# Run now
schtasks.exe /Run /TN "<Task Name>"

# Detailed status and last result
schtasks.exe /Query /TN "<Task Name>" /V /FO LIST

# Export XML backup
schtasks.exe /Query /TN "<Task Name>" /XML > ".\TaskBackup.xml"

# Delete
schtasks.exe /Delete /TN "<Task Name>" /F
```

## Task Scheduler GUI setup

The GUI is preferable when you need credentials, network conditions, retry settings, or a schedule not shown above.

1. Open **Task Scheduler**.
2. Select **Create Task**, not only Basic Task.
3. On **General**:
   - Use a descriptive task name that exactly matches the commands in this README.
   - Select the same Windows account that owns the local configuration and destination folders.
   - For jobs using OneDrive/SharePoint paths, test both interactive and noninteractive access.
   - For Alberta MFA prompting, choose **Run only when user is logged on** unless authentication has been redesigned for unattended use.
4. On **Triggers**:
   - Add the required weekly days and start time.
   - Enable the trigger.
5. On **Actions**:
   - Program/script: `powershell.exe`
   - Arguments:

     ```text
     -NoProfile -ExecutionPolicy Bypass -File "C:\Path\To\Wrapper.ps1"
     ```

   - Start in: the repository/install directory.
6. On **Conditions**:
   - Enable the network requirement when appropriate.
   - Decide whether the task may wake the computer.
7. On **Settings**:
   - Enable **Run task as soon as possible after a scheduled start is missed**.
   - Prevent overlapping runs by selecting **Do not start a new instance** when the task is already running.
   - Set a reasonable stop timeout, such as one or two hours.
   - Consider retrying after a temporary network failure.
8. Save the task and provide the Windows password if requested.
9. Right-click the task and select **Run**.
10. Refresh and inspect **Last Run Result**, then check the wrapper and downloader logs.

## Logs and output verification

A task starting successfully does not prove the report was downloaded. Verify both logs and output files.

### Tail a log

```powershell
Get-Content "$InstallDir\eliis_task_run.log" -Tail 100
Get-Content "$InstallDir\CW_Weekly_task_run.log" -Tail 100
```

### Search logs for common errors

```powershell
Get-ChildItem $InstallDir -Filter *.log | ForEach-Object {
    Select-String -Path $_.FullName -Pattern "ERROR|Traceback|failed|exit code [1-9]|HTML instead" -CaseSensitive:$false
}
```

### Confirm recent output files

Replace the folder with the configured destination:

```powershell
$OutputDir = "C:\Data\Downloads"
Get-ChildItem $OutputDir -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 20 Name, Length, LastWriteTime
```

### Success checklist

For each job, confirm:

- The wrapper returned exit code 0.
- The Python log contains a final success message.
- A new file exists in the intended output directory.
- File size is greater than zero.
- A ZIP opens and extracts successfully.
- An XLSX opens in Excel and is not an HTML login page saved with an `.xlsx` extension.
- A CSV begins with expected report columns, not `<html>` or an error message.
- The filename date matches the intended reporting date.
- OneDrive/SharePoint reports the output as synced when applicable.

## Troubleshooting

### `python` or `py` is not recognized

Interactive PowerShell:

```powershell
py -0p
Get-Command py
Get-Command python
```

Task Scheduler can have a different environment. Use an absolute interpreter path or update the wrapper to use `py -3`.

### Task exists but does not start

```powershell
schtasks.exe /Query /TN "<Task Name>" /V /FO LIST
```

Check:

- Exact task name and folder
- Task enabled state
- Correct user account
- Stored account password still valid
- Trigger date/time
- Conditions such as AC power or network
- Whether another instance is already running

### Task says success but no file appears

1. Run the wrapper interactively.
2. Inspect the wrapper log.
3. Confirm the configured output directory exists.
4. Confirm the task account has write access.
5. Check OneDrive/SharePoint sync and path availability.
6. Check whether the script skipped a weekend.
7. Check whether the website returned a login page or report error.
8. For the CW weekly wrapper, apply the exit-code fix described above.

### BCLDB script skips a weekend

The BCLDB scripts respect `skip_weekends`. For a deliberate weekend test:

```powershell
py -3 .\vendor_bcldb_downloader.py --config .\vendor_bcldb_raw_config.json --force
```

or:

```powershell
py -3 .\vendor_po_status.py --config .\vendor_bcldb_po_config.json --force
```

### eLIIS cannot detect login fields

```powershell
py -3 .\eliis_downloader.py --config .\eliis_config.json --inspect-login
```

Update `username_field` and `password_field` with the current form names.

### eLIIS download URL changed

```powershell
py -3 .\eliis_downloader.py --config .\eliis_config.json --list-download-links
```

Compare the printed links with the configured URLs.

### Alberta task waits forever or fails around MFA

The script may be waiting for interactive input. Run it in a visible PowerShell window and complete MFA. Do not schedule an interactive MFA flow with `-WindowStyle Hidden` unless an approved unattended authentication solution is in place.

### Alberta export fails after website changes

1. Set `debug` to `true` or run with `--debug`.
2. Reproduce the failure manually.
3. Inspect the newest debug directory.
4. Review login, report form, ReportViewer, and export candidate files.
5. Do not immediately run old patch scripts against an uncommitted working copy.
6. Back up/commit, patch, review the diff, and compile-test.

### Containerworld returns HTML instead of CSV

This usually indicates an expired/failed login, changed form/session behavior, or an Oracle report error. Run the script interactively and inspect the printed HTTP/Oracle error. Confirm the account and report access in a browser.

### Output path works manually but not in Task Scheduler

Common causes:

- The task runs as a different Windows user.
- The task account has no access to the synced SharePoint library.
- OneDrive is not running in the noninteractive session.
- The path contains a user-specific folder name.
- A mapped drive is unavailable to the scheduled session.

Prefer local or UNC paths that are accessible to the task account, then let an approved sync process move files if needed.

## Known implementation limitations

These are important before production deployment:

1. **Credentials are exposed in the public repository.** Rotate and purge them.
2. **eLIIS environment-variable keys are not wired into the current login code.** The script must be refactored before `ELIIS_USER`/`ELIIS_PASSWORD` can be relied on.
3. **eLIIS retry accounting can still report failure after recovery.** The current script increments one shared failure counter for each unsuccessful attempt, so a later successful retry can still leave a final exit code of 1. Track the final status of each configured download instead.
4. **Alberta MFA has a hardcoded password assignment in one path.** Remove it.
5. **Alberta may require interactive MFA.** A hidden/unattended scheduled task may fail or wait for input.
6. **Most PowerShell wrappers contain a user-specific install path.** Replace it with the wrapper directory.
7. **The three Containerworld weekly Python files hardcode output directories.** Move those paths into config.
8. **The current CW weekly wrapper always returns 0.** Propagate failures so Task Scheduler reports them.
9. **`vendor_po_status.py` has an unsafe default config for manual use.** Always pass the PO config explicitly or correct the default.
10. **Logs, debug files, downloaded outputs, and backup files are tracked or easily trackable.** Add ignore rules.
11. **Patch scripts modify source files in place.** Treat them as one-time maintenance utilities.
12. **Website automation depends on vendor HTML/form/report behavior.** Vendor site changes can require code/config updates.
13. **No centralized alerting is present.** Failures are visible mainly through exit codes and local logs.

## Recommended repository cleanup

A safer long-term structure would be:

```text
Automated_Data_Pulling/
  README.md
  .gitignore
  src/
    eliis_downloader.py
    vendor_bcldb_downloader.py
    vendor_po_status.py
    AlbertaGR.py
    BCGR.py
    containerworld/
      RPO_Downloader.py
      RPOSummary_Downloader.py
      CW_Inventory_Downloader.py
  config/
    eliis_config.example.json
    eliis_wednesday_raw_data_config.example.json
    vendor_bcldb_raw_config.example.json
    vendor_bcldb_po_config.example.json
    AlbertaGR_raw.example.json
    BCGR_raw.example.json
  scripts/
    run_eliis_downloader.ps1
    run_eliis_wednesday_raw_data.ps1
    vendor_bcldb_task_run.ps1
    vendor_po_status_task_run.ps1
    Run_AlbertaGR.ps1
    Run_BCGR.ps1
    Run_CW_Weekly_Downloads.ps1
  maintenance/
    patch_export_by_error.py
    patch_export_cultureoverrides.py
    patch_skip_saturdays.py
  tests/
  logs/                 # ignored
  debug/                # ignored
```

Additional improvements:

- Add a shared configuration loader.
- Add a shared secret provider.
- Add `--config` to every Python entry point.
- Move every output path into JSON.
- Add structured rotating logs.
- Add email/Teams alerting for nonzero exit codes.
- Add file-content validation for every output type.
- Add unit tests for filename/date calculations and HTML parsing.
- Add a dry-run/config-check command that performs no download.
- Add a single installation script that creates all tasks from a documented schedule file.
- Remove unneeded binaries and historical logs from the repository after verifying they are not required.

## Maintenance checklist

### Weekly

- Review scheduled-task last results.
- Confirm expected files arrived.
- Review logs for warnings/retries.
- Confirm OneDrive/SharePoint sync completed.

### Monthly

- Test each wrapper interactively.
- Compile-check all Python files.
- Validate all JSON files.
- Confirm task account credentials are still valid.
- Confirm destination paths still exist.
- Review debug/log folder sizes.

### After a vendor website change

- Run the affected job manually.
- Enable debug output.
- Compare form fields, URLs, report names, and response content.
- Update only the affected parser/config.
- Test with a non-production output folder.
- Confirm output contents before restoring the schedule.

### After moving the repository

- Update or make portable every `$ScriptFolder` value.
- Update scheduled-task `/TR` actions.
- Update config output paths.
- Re-run manual tests.
- Query every task to confirm the action path.

### After changing credentials

- Update the secure local store/config.
- Run interactively.
- Confirm MFA behavior.
- Confirm the scheduled task runs under the account that can read the secret.
- Never commit the new values.

## Repository file map

### Operational Python scripts

- `eliis_downloader.py` - eLIIS login, download, retry, checksum logging, optional ZIP extraction
- `vendor_bcldb_downloader.py` - Vendor BCLDB Product Activity XLSX
- `vendor_po_status.py` - Vendor BCLDB PO Status XLSX
- `AlbertaGR.py` - Alberta LiquorConnect receipts CSV
- `BCGR.py` - Containerworld Daily Receipts CSV
- `RPO_Downloader.py` - Containerworld Outstanding RPO CSV
- `RPOSummary_Downloader.py` - Containerworld RPO Summary CSV
- `CW_Inventory_Downloader.py` - Containerworld Inventory CSV

### Operational configuration

- `eliis_config.json`
- `eliis_wednesday_raw_data_config.json`
- `vendor_bcldb_raw_config.json`
- `vendor_bcldb_po_config.json`
- `AlbertaGR_raw.json`
- `BCGR_raw.json`

### PowerShell wrappers

- `run_eliis_downloader.ps1`
- `run_eliis_wednesday_raw_data.ps1`
- `vendor_bcldb_task_run.ps1`
- `vendor_po_status_task_run.ps1`
- `Run_AlbertaGR.ps1`
- `Run_AlbertaGR_Backup.ps1`
- `Run_BCGR.ps1`
- `Run_CW_Weekly_Downloads.ps1`

### Maintenance/history files

- `patch_export_by_error.py`
- `patch_export_cultureoverrides.py`
- `patch_skip_saturdays.py`
- `*_backup_*.py` files created by patch operations
- `*.log` files from prior executions

These should not be confused with normal scheduled entry points.

## Quick deployment checklist

- [ ] Repository made private during cleanup
- [ ] All exposed vendor credentials rotated
- [ ] Secrets removed from code/config and Git history
- [ ] Real config files ignored by Git
- [ ] Installation directory selected
- [ ] Wrapper paths made portable or updated
- [ ] Python version confirmed
- [ ] All Python scripts compile
- [ ] All JSON files parse
- [ ] Every output path updated and writable
- [ ] eLIIS credential handling refactored
- [ ] eLIIS retry/final exit-code handling corrected
- [ ] Alberta hardcoded MFA password removed
- [ ] Alberta MFA behavior tested interactively
- [ ] Each Python script tested manually
- [ ] Each PowerShell wrapper tested manually
- [ ] CW wrapper fixed to return failure when a child script fails
- [ ] Scheduled tasks created with exact matching names
- [ ] Task actions, users, triggers, and conditions reviewed
- [ ] Immediate task runs verified through logs and output files
- [ ] Log/debug/output folders excluded from Git

---

For operational incidents, capture the task query output, wrapper log, downloader log, exact run date/time, and the newest output/debug filenames. Redact usernames, passwords, MFA codes, cookies, session IDs, and internal paths before sharing diagnostics externally.
