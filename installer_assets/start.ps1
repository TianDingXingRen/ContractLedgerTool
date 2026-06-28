param(
    [string]$HostAddr = "127.0.0.1",
    [int]$Port = 5000,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppExe = Join-Path $AppDir "ContractLedgerTool.exe"
$PythonExe = Join-Path $AppDir ".venv\Scripts\python.exe"
$Url = "http://${HostAddr}:${Port}/"
$ProbeUrl = "http://${HostAddr}:${Port}/static/style.css"
$OutLog = Join-Path $AppDir "server.log"
$ErrLog = Join-Path $AppDir "server_error.log"

function Test-ServiceReady {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $ProbeUrl -TimeoutSec 5 -ErrorAction Stop
        return $response.StatusCode -eq 200 -and $response.Content.Contains("Apple-style GUI Theme")
    } catch {
        return $false
    }
}

function Wait-ServiceReady {
    for ($i = 0; $i -lt 80; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-ServiceReady) {
            return $true
        }
    }
    return $false
}

function Complete-Launch {
    param([bool]$Ready)

    if ($NoBrowser) {
        if (-not $Ready) {
            Add-Content -LiteralPath $ErrLog -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Auto-start timed out while waiting for $Url"
        }
        exit 0
    }

    if ($Ready) {
        Start-Process $Url
        exit 0
    }

    Write-Host "Service startup failed. Check the log:" -ForegroundColor Red
    Write-Host $ErrLog
    Read-Host "Press Enter to exit"
    exit 1
}

# Reuse the running service and avoid duplicate processes.
if (Test-ServiceReady) {
    if (-not $NoBrowser) {
        Start-Process $Url
    }
    exit 0
}

# Prefer the bundled offline executable.
if (Test-Path -LiteralPath $AppExe) {
    Start-Process -FilePath $AppExe `
        -ArgumentList @("--host", $HostAddr, "--port", "$Port", "--no-browser") `
        -WorkingDirectory $AppDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput $OutLog `
        -RedirectStandardError $ErrLog

    Complete-Launch -Ready (Wait-ServiceReady)
}

# Compatibility fallback for legacy source installations.
if (-not (Test-Path -LiteralPath $PythonExe)) {
    if (-not $NoBrowser) {
        Write-Host "No runnable application was found. Run the installer first." -ForegroundColor Red
        Read-Host "Press Enter to exit"
    } else {
        Add-Content -LiteralPath $ErrLog -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Auto-start failed: missing $AppExe and $PythonExe"
    }
    exit 1
}

Start-Process -FilePath $PythonExe `
    -ArgumentList @("app.py", "--host", $HostAddr, "--port", "$Port", "--no-browser") `
    -WorkingDirectory $AppDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog

Complete-Launch -Ready (Wait-ServiceReady)
