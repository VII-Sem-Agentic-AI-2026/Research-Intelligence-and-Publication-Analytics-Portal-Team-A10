param(
    [ValidateRange(1024,65535)][int]$Port = 8001,
    [switch]$NoBrowser,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Python environment missing. Follow README setup first.' }
$instance = (& $python -B -c "from pathlib import Path; import hashlib; print(hashlib.sha256(str(Path.cwd().resolve()).encode()).hexdigest()[:16])").Trim()
if ($LASTEXITCODE -ne 0) { throw 'Unable to run the project Python environment.' }
$url = "http://127.0.0.1:$Port"
$health = $null
try { $health = Invoke-RestMethod -Uri "$url/api/health" -TimeoutSec 3 } catch {}
$compatible = $health -and $health.service -eq 'research-portal' -and $health.instance -eq $instance
if ($CheckOnly) {
    Write-Host "Python environment found. Dashboard already running: $compatible"
    Write-Host 'Check only: no server was started or stopped.'
    exit 0
}
if ($compatible) {
    Write-Host "Dashboard is already running: $url"
    if (-not $NoBrowser) { Start-Process $url }
    exit 0
}
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is occupied by another or older server. Stop it first or run start_server.bat -Port 8002."
}
Write-Host "Starting Research Portal: $url"
Write-Host 'Keep this window open. Press Ctrl+C to stop this server.'
Write-Host 'A Gemini key is optional at startup; configure AI inside the dashboard.'
if (-not $NoBrowser) {
    # Browser can retry if it opens before the server finishes initialization.
    Start-Process $url
}
& $python -B -m publication_agent.cli serve --port $Port
if ($LASTEXITCODE -ne 0) { throw 'Server exited with an error. Review the message above.' }
