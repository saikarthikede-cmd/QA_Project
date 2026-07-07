# Run any of the 6 QA demo apps with Python 3.11
# Usage: .\run.ps1 1   (runs app 1 on port 8001)

param([int]$App = 1)

$apps = @{
    1 = @{ dir = "app1_resume_screener";  port = 8001; name = "Resume Screener" }
    2 = @{ dir = "app2_doc_diff";         port = 8002; name = "Document Diff Analyzer" }
    3 = @{ dir = "app3_faq_generator";    port = 8003; name = "FAQ Generator" }
    4 = @{ dir = "app4_report_agent";     port = 8004; name = "Report Summarizer Agent" }
    5 = @{ dir = "app5_policy_triage";    port = 8005; name = "Policy Triage Agent" }
    6 = @{ dir = "app6_data_analyst";     port = 8006; name = "Data Analyst Agent" }
}

if (-not $apps.ContainsKey($App)) {
    Write-Host "Usage: .\run.ps1 <1-6>"
    exit 1
}

$cfg = $apps[$App]
Write-Host "Starting App $App — $($cfg.name) on http://localhost:$($cfg.port)" -ForegroundColor Cyan
Set-Location (Join-Path $PSScriptRoot $cfg.dir)
py -3.11 -m uvicorn main:app --reload --port $cfg.port
