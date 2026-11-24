# Rebuild the published dashboard data from the newest PubTracker export in "PubTracker Export/".
# Does not commit or push; review the summary and `git status`, then push manually.
#   .\refresh.ps1                      # rebuild from existing data\varr_baseline_FY26.csv
#   .\refresh.ps1 -Db "<path>\vadaily.db"   # re-export the VARR baseline first
param([string]$Db, [string]$Fy)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
# Fiscal year defaults to the current one (Oct-Sep); -Fy 26 rebuilds a past year.
if ($Fy) { $env:VARR_FY = $Fy }
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

if ($Db) {
    & $py export_varr_baseline.py --db $Db
    if ($LASTEXITCODE) { throw "export_varr_baseline.py failed" }
}

& $py build_static_dashboard_data.py
if ($LASTEXITCODE) { throw "build_static_dashboard_data.py failed" }
& $py build_unattributed_funding_data.py
if ($LASTEXITCODE) { throw "build_unattributed_funding_data.py failed" }

& $py -c "import json,fiscal_year as f; m=json.load(open(f.OUTPUT_DIR/'meta.json')); print('meta:', m)"
Write-Host "`nBuild finished. Review with 'git status' and 'git diff --stat docs', then commit and push to publish."
