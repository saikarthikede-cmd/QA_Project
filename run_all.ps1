param(
    [switch]$NoStop
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

$services = @(
    @{ Name = "Portal Dashboard"; Dir = "portal"; Port = 8000 },
    @{ Name = "App 1 - Resume Screener"; Dir = "app1_resume_screener"; Port = 8001 },
    @{ Name = "App 2 - Document Diff"; Dir = "app2_doc_diff"; Port = 8002 },
    @{ Name = "App 3 - FAQ Generator"; Dir = "app3_faq_generator"; Port = 8003 },
    @{ Name = "App 4 - Report Agent"; Dir = "app4_report_agent"; Port = 8004 },
    @{ Name = "App 5 - Policy Triage"; Dir = "app5_policy_triage"; Port = 8005 },
    @{ Name = "App 6 - Data Analyst"; Dir = "app6_data_analyst"; Port = 8006 }
)

New-Item -ItemType Directory -Force -Path (Join-Path $Root "logs") | Out-Null

if (-not $NoStop) {
    $ports = $services | ForEach-Object { $_.Port }
    $listeners = Get-NetTCPConnection -LocalPort $ports -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique

    foreach ($listenerPid in $listeners) {
        if ($listenerPid -and $listenerPid -ne 0) {
            Stop-Process -Id $listenerPid -Force -ErrorAction SilentlyContinue
        }
    }

    $existing = Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -like "*uvicorn*main:app*" -and $_.CommandLine -notlike "*Get-CimInstance*" }

    foreach ($proc in $existing) {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }

    Start-Sleep -Seconds 2
}

foreach ($svc in $services) {
    $workDir = Join-Path $Root $svc.Dir
    $outLog = Join-Path $Root ("logs\live{0}.out.log" -f $svc.Port)
    $errLog = Join-Path $Root ("logs\live{0}.err.log" -f $svc.Port)

    Start-Process `
        -FilePath "py" `
        -ArgumentList @("-3.11", "-m", "uvicorn", "main:app", "--port", "$($svc.Port)") `
        -WorkingDirectory $workDir `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden

    Write-Host ("Starting {0} on http://localhost:{1}" -f $svc.Name, $svc.Port) -ForegroundColor Cyan
}

Write-Host ""
Write-Host "Waiting for services..." -ForegroundColor Yellow
Start-Sleep -Seconds 8

foreach ($svc in $services) {
    try {
        $response = Invoke-WebRequest -Uri ("http://127.0.0.1:{0}/" -f $svc.Port) -UseBasicParsing -TimeoutSec 5
        Write-Host ("OK   http://localhost:{0}  {1}" -f $svc.Port, $svc.Name) -ForegroundColor Green
    }
    catch {
        Write-Host ("WAIT http://localhost:{0}  {1} - still starting, check logs/live{0}.err.log" -f $svc.Port, $svc.Name) -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Dashboard: http://localhost:8000" -ForegroundColor Green
Write-Host "Keep this terminal open only if you want to watch this message. The servers are running in the background."
