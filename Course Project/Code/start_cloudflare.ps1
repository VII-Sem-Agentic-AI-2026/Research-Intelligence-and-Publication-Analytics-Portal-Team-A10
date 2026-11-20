param(
    [ValidateRange(1024,65535)][int]$Port = 8001,
    [switch]$CheckOnly,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Python environment missing. Follow README setup first.' }
$cloudCommand = Get-Command cloudflared.exe -ErrorAction SilentlyContinue
$cloudflared = if ($cloudCommand) { $cloudCommand.Source } else { $null }
if (-not $cloudflared) {
    foreach ($candidate in @((Join-Path $projectRoot 'cloudflared.exe'),(Join-Path $projectRoot 'tools\cloudflared.exe'),"${env:ProgramFiles}\cloudflared\cloudflared.exe","${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe")) {
        if (Test-Path -LiteralPath $candidate) { $cloudflared = $candidate; break }
    }
}
if (-not $cloudflared) { throw 'Install cloudflared first: winget install --id Cloudflare.cloudflared -e, then reopen this launcher.' }
$instance = (& $python -B -c "from pathlib import Path; import hashlib; print(hashlib.sha256(str(Path.cwd().resolve()).encode()).hexdigest()[:16])").Trim()
if ($LASTEXITCODE -ne 0) { throw 'Unable to run the project Python environment.' }
$localUrl = "http://127.0.0.1:$Port"
function Get-PortalHealth {
    try { return Invoke-RestMethod -Uri "$localUrl/api/health" -TimeoutSec 3 } catch { return $null }
}
function Test-PortalHealth($health) {
    return $health -and $health.service -eq 'research-portal' -and $health.tunnel_support -and $health.instance -eq $instance
}
$health = Get-PortalHealth
Write-Host "Project: $projectRoot"
Write-Host "Cloudflared: $cloudflared"
Write-Host "Local dashboard: $localUrl"
if ($CheckOnly) {
    Write-Host "Dependencies found. Compatible running dashboard: $(Test-PortalHealth $health)"
    Write-Host 'Check only: no server or public tunnel was started.'
    exit 0
}
$mutex = New-Object System.Threading.Mutex($false, "Local\ResearchPortalCloudflare-$instance")
$acquired = $false
$tunnel = $null
$owner = [guid]::NewGuid().ToString('N')
$runtime = Join-Path $projectRoot 'runtime'
$originFile = Join-Path $runtime 'cloudflare_origin.json'
$linkFile = Join-Path $runtime 'cloudflare-link.txt'
$utf8 = New-Object System.Text.UTF8Encoding($false)
function Write-Registration($url) {
    $registration = @{ origin=$url; expires_at=([DateTimeOffset]::UtcNow.ToUnixTimeSeconds()+300); owner=$owner } | ConvertTo-Json -Compress
    $temporary = "$originFile.$owner.tmp"
    [IO.File]::WriteAllText($temporary,$registration,$utf8)
    Move-Item -LiteralPath $temporary -Destination $originFile -Force
}
try {
    $acquired = $mutex.WaitOne(0)
    if (-not $acquired) { throw 'A Cloudflare launcher is already running for this project.' }
    New-Item -ItemType Directory -Path $runtime -Force | Out-Null
    if (-not (Test-PortalHealth $health)) {
        if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
            throw "Port $Port is already occupied by an older or different server. Stop that server and rerun this file; no unrelated process was stopped."
        }
        Write-Host 'Starting dashboard...'
        $server = Start-Process -FilePath $python -ArgumentList '-B','-m','publication_agent.cli','serve','--port',$Port -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'cloudflare-server.out.log') -RedirectStandardError (Join-Path $runtime 'cloudflare-server.err.log') -PassThru
        for ($attempt=0; $attempt -lt 30; $attempt++) {
            Start-Sleep -Seconds 1
            $health = Get-PortalHealth
            if (Test-PortalHealth $health) { break }
            if ($server.HasExited) { throw 'Dashboard failed to start. See runtime\cloudflare-server.err.log.' }
        }
        if (-not (Test-PortalHealth $health)) { throw 'Dashboard startup timed out. See runtime\cloudflare-server.err.log.' }
    } else { Write-Host 'Using the dashboard already running for this project.' }
    $setup = Invoke-RestMethod -Uri "$localUrl/api/setup-status" -TimeoutSec 5
    if ($setup.needs_setup) { throw "Create your administrator locally at $localUrl before sharing the portal." }
    Remove-Item -LiteralPath $linkFile -ErrorAction SilentlyContinue
    $stdout = Join-Path $runtime 'cloudflare-tunnel.out.log'
    $stderr = Join-Path $runtime 'cloudflare-tunnel.err.log'
    Write-Host 'Requesting a temporary Cloudflare link...'
    $tunnel = Start-Process -FilePath $cloudflared -ArgumentList 'tunnel','--no-autoupdate','--url',$localUrl,'--http-host-header',"127.0.0.1:$Port" -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $publicUrl = $null
    for ($attempt=0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Seconds 1
        $logs = (Get-Content -LiteralPath $stderr -Raw -ErrorAction SilentlyContinue) + (Get-Content -LiteralPath $stdout -Raw -ErrorAction SilentlyContinue)
        $found = [regex]::Matches([string]$logs,'https://[a-z0-9-]+\.trycloudflare\.com') | Where-Object { $_.Value -ne 'https://api.trycloudflare.com' } | Select-Object -First 1
        if ($found) { $publicUrl=$found.Value; break }
        if ($tunnel.HasExited) { throw 'Cloudflared exited. See runtime\cloudflare-tunnel.err.log.' }
    }
    if (-not $publicUrl) { throw 'No tunnel URL received within 60 seconds. Check runtime\cloudflare-tunnel.err.log and your Internet connection.' }
    Write-Registration $publicUrl
    [IO.File]::WriteAllText($linkFile,$publicUrl+[Environment]::NewLine,$utf8)
    Write-Host ''
    Write-Host "Temporary public link: $publicUrl" -ForegroundColor Green
    Write-Host 'Sign in with your normal portal account. Share the link with intended users.'
    Write-Host 'Keep this window and computer running. Press Ctrl+C to stop sharing.'
    Write-Host 'The local dashboard remains running when sharing stops.'
    if (-not $NoBrowser) { Start-Process $publicUrl }
    $heartbeat = 0
    while (-not $tunnel.HasExited) {
        Start-Sleep -Seconds 1
        $heartbeat++
        if ($heartbeat -ge 30) { Write-Registration $publicUrl; $heartbeat=0 }
    }
    throw 'Cloudflared stopped. Rerun the batch file for a new temporary link.'
} finally {
    if ($tunnel -and -not $tunnel.HasExited) { Stop-Process -Id $tunnel.Id -ErrorAction SilentlyContinue }
    if ($acquired) {
        if (Test-Path -LiteralPath $originFile) {
            try {
                $registration = Get-Content -LiteralPath $originFile -Raw | ConvertFrom-Json
                if ($registration.owner -eq $owner) { Remove-Item -LiteralPath $originFile -ErrorAction SilentlyContinue; Remove-Item -LiteralPath $linkFile -ErrorAction SilentlyContinue }
            } catch {}
        }
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
