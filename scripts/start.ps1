<#
    One-click launcher for Windows.

    Double-click start.bat (or run: powershell -ExecutionPolicy Bypass -File scripts\start.ps1)

    What it does, in order:
      1. Checks Docker is installed and actually running.
      2. Picks a free host port for the UI (8080+) and the API (8000+).
      3. Starts the stack with demo data seeded, so the app is not empty.
      4. Waits for the backend to report healthy, then opens the browser.

    Everything is optional - no API keys, no database server, no manual config.
    Stop the stack again with stop.bat (or: docker compose down).
#>

[CmdletBinding()]
param(
    # Skip the browser launch at the end.
    [switch]$NoBrowser,
    # Rebuild images even if they already exist.
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

function Write-Step($message) { Write-Host "==> $message" -ForegroundColor Cyan }
function Write-Bad($message) { Write-Host "    $message" -ForegroundColor Red }
function Write-Good($message) { Write-Host "    $message" -ForegroundColor Green }

# --- 1. Docker must be installed and the engine must be up ------------------
Write-Step 'Checking Docker'

$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCmd) {
    Write-Bad 'Docker was not found on this machine.'
    Write-Host ''
    Write-Host '    Install Docker Desktop:  https://www.docker.com/products/docker-desktop'
    Write-Host '    Then start Docker Desktop and run this again.'
    Write-Host ''
    Read-Host 'Press Enter to close'
    exit 1
}

$dockerVersion = (& docker version --format '{{.Server.Version}}' 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $dockerVersion) {
    Write-Bad 'Docker is installed but the engine is not responding.'
    Write-Host ''
    Write-Host '    Start Docker Desktop (it can take a minute) and run this again.'
    Write-Host ''
    Read-Host 'Press Enter to close'
    exit 1
}
Write-Good "Docker engine $dockerVersion is running"

# Compose v2 is bundled with Docker Desktop. Fall back to the legacy binary.
$composeArgs = @('compose')
& docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
        $composeArgs = @('docker-compose')
    } else {
        Write-Bad 'Neither "docker compose" nor "docker-compose" is available.'
        Read-Host 'Press Enter to close'
        exit 1
    }
}

# --- 2. Find free host ports ------------------------------------------------
# Port 8080 is the documented default but is commonly taken (Oracle, other
# dev servers), so probe upward rather than failing with a cryptic bind error.
function Find-FreePort([int]$start, [int]$end) {
    foreach ($candidate in $start..$end) {
        # Docker publishes container ports on 0.0.0.0, so a Loopback-only probe
        # is not enough: .NET binds non-exclusively by default and will happily
        # take 127.0.0.1:8000 even when 0.0.0.0:8000 is already published by
        # another stack. Probe Any with ExclusiveAddressUse set, and cross-check
        # the current listener table.
        $existing = Get-NetTCPConnection -LocalPort $candidate -State Listen -ErrorAction SilentlyContinue
        if ($existing) { continue }

        $listener = New-Object System.Net.Sockets.TcpListener ([System.Net.IPAddress]::Any), $candidate
        $listener.ExclusiveAddressUse = $true
        try {
            $listener.Start()
            $listener.Stop()
            return $candidate
        } catch {
            # Port already bound - try the next one.
        }
    }
    throw "No free port available between $start and $end."
}

Write-Step 'Finding a free port'
$frontendPort = Find-FreePort 8080 8099
$backendPort = Find-FreePort 8000 8049

$env:FRONTEND_PORT = $frontendPort
$env:BACKEND_PORT = $backendPort
# Without this the container starts with an empty database, which makes the app
# look broken. Default in compose is "false"; a first-run demo wants "true".
$env:SEED_DEMO_DATA_ON_STARTUP = 'true'
$env:CORS_ORIGINS = "http://localhost:$frontendPort"

if ($frontendPort -ne 8080) {
    Write-Good "UI will use port $frontendPort (8080 was already in use)"
} else {
    Write-Good 'UI will use port 8080'
}
Write-Good "API will use port $backendPort"

# --- 3. Build and start -----------------------------------------------------
$buildArgs = @($composeArgs) + @('up', '-d')
if ($Force) { $buildArgs += '--build' }

Write-Step 'Building images (first run takes several minutes)'
Write-Host '    The backend image is ~1 GB: it bundles the RAG index and trained'
Write-Host '    ML models. Please do not close this window.'
Write-Host ''

& docker @($composeArgs) @('up', '-d', '--build')
if ($LASTEXITCODE -ne 0) {
    Write-Bad 'The stack failed to start. The output above should say why.'
    Write-Host ''
    Read-Host 'Press Enter to close'
    exit 1
}

# --- 4. Wait for the backend to be healthy ----------------------------------
Write-Step 'Waiting for the backend to become healthy'

$healthUrl = "http://127.0.0.1:$backendPort/api/v1/health/ready"
$deadline = (Get-Date).AddMinutes(5)
$ready = $false

while ((Get-Date) -lt $deadline) {
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 5
        if ($health.status -eq 'ready') { $ready = $true; break }
    } catch {
        # Not up yet - keep waiting.
    }
    Start-Sleep -Seconds 3
    Write-Host -NoNewline '.'
}
Write-Host ''

if (-not $ready) {
    Write-Bad 'The backend did not become healthy within 5 minutes.'
    Write-Host ''
    Write-Host '    See what the logs say:'
    Write-Host "      docker compose logs --tail 60 backend"
    Write-Host ''
    Read-Host 'Press Enter to close'
    exit 1
}

Write-Good "Backend ready (database=$($health.database) rag=$($health.rag) ml=$($health.ml))"

# The frontend is a static bundle behind nginx, so a successful response means
# it is serving. nginx starts before the backend is fully warmed.
Start-Sleep -Seconds 3

$uiUrl = "http://localhost:$frontendPort"
try {
    $ui = Invoke-WebRequest -Uri $uiUrl -TimeoutSec 10 -UseBasicParsing
    if ($ui.StatusCode -eq 200) {
        Write-Good 'Frontend is serving'
    } else {
        Write-Bad "Frontend answered HTTP $($ui.StatusCode)"
    }
} catch {
    Write-Bad "Frontend did not answer: $($_.Exception.Message)"
}

# --- 5. Open the browser ----------------------------------------------------
if (-not $NoBrowser) {
    Write-Step 'Opening your browser'
    try {
        Start-Process $uiUrl
    } catch {
        Write-Host "    Could not launch a browser automatically - open $uiUrl yourself."
    }
}

Write-Host ''
Write-Host '===========================================================' -ForegroundColor Green
Write-Host '  The system is running.' -ForegroundColor Green
Write-Host '===========================================================' -ForegroundColor Green
Write-Host "  App        $uiUrl"
Write-Host "  API docs   http://localhost:$backendPort/docs"
Write-Host "  Health     $healthUrl"
Write-Host ''
Write-Host '  Demo data is seeded: 3 farms, 6 fields, sensor telemetry, soil'
Write-Host '  tests and a pending approval to review.'
Write-Host ''
Write-Host '  To stop it later, run stop.bat in this folder.'
Write-Host ''
Write-Host '  Note: sensor readings are SIMULATED (there is no real probe'
Write-Host '  hardware attached). Weather uses the live keyless Open-Meteo API'
Write-Host '  when the field has coordinates, and falls back to clearly-labelled'
Write-Host '  offline climatology when it does not.'
Write-Host ''

if ($NoBrowser) { exit 0 }
Read-Host 'Press Enter to close this window (the app keeps running in Docker)'
exit 0
