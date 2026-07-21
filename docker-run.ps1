$ErrorActionPreference = "Stop"

$services = @(
    @{ Name = "Portal Dashboard";        Port = 8000 },
    @{ Name = "App 1 - Resume Screener"; Port = 8001 },
    @{ Name = "App 2 - Document Diff";   Port = 8002 },
    @{ Name = "App 3 - FAQ Generator";   Port = 8003 },
    @{ Name = "App 4 - Report Agent";    Port = 8004 },
    @{ Name = "App 5 - Policy Triage";   Port = 8005 },
    @{ Name = "App 6 - Data Analyst";    Port = 8006 }
)

docker compose up -d --build

Write-Host ""
Write-Host "Waiting for containers to become reachable..." -ForegroundColor Yellow

function Wait-ForService($svc) {
    for ($i = 0; $i -lt 15; $i++) {
        try {
            Invoke-WebRequest -Uri ("http://127.0.0.1:{0}/" -f $svc.Port) -UseBasicParsing -TimeoutSec 3 | Out-Null
            Write-Host ("OK   http://localhost:{0}  {1}" -f $svc.Port, $svc.Name) -ForegroundColor Green
            return
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }
    Write-Host ("WAIT http://localhost:{0}  {1} - still starting after 30s, check: docker compose logs" -f $svc.Port, $svc.Name) -ForegroundColor Yellow
}

foreach ($svc in $services) {
    Wait-ForService $svc
}

Write-Host ""
Write-Host "Dashboard: http://localhost:8000" -ForegroundColor Green
Write-Host "Stop everything with: docker compose down"
