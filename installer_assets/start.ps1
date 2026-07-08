param(
    [string]$HostAddr = "127.0.0.1",
    [int]$Port = 5000,
    [switch]$NoBrowser,
    [switch]$NoPrompt,
    [int]$StartupTimeoutSeconds = 120,
    [int]$PortSearchCount = 20
)

$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppExe = Join-Path $AppDir "ContractLedgerTool.exe"
$PythonExe = Join-Path $AppDir ".venv\Scripts\python.exe"
$LogStamp = Get-Date -Format "yyyyMMdd_HHmmss"

function Prepare-LogFile {
    param([string]$Path, [string]$FallbackPrefix)

    try {
        if (Test-Path -LiteralPath $Path) {
            Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
        }
        return $Path
    } catch {
        return (Join-Path $AppDir ("{0}_{1}.log" -f $FallbackPrefix, $LogStamp))
    }
}

$OutLog = Prepare-LogFile (Join-Path $AppDir "server.log") "server"
$ErrLog = Prepare-LogFile (Join-Path $AppDir "server_error.log") "server_error"

function Get-ServiceUrl {
    param([int]$ProbePort)
    return "http://${HostAddr}:${ProbePort}/"
}

function Get-ProbeUrl {
    param([int]$ProbePort)
    return "http://${HostAddr}:${ProbePort}/static/style.css"
}

function Test-ServiceReady {
    param([int]$ProbePort)

    try {
        $probeUrl = Get-ProbeUrl -ProbePort $ProbePort
        $response = Invoke-WebRequest -UseBasicParsing -Uri $ProbeUrl -TimeoutSec 5 -ErrorAction Stop
        return $response.StatusCode -eq 200 -and $response.Content.Contains("Apple-style GUI Theme")
    } catch {
        return $false
    }
}

function Test-PortListening {
    param([int]$ProbePort)

    try {
        $listeners = Get-NetTCPConnection -LocalPort $ProbePort -State Listen -ErrorAction SilentlyContinue
        return [bool]$listeners
    } catch {
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $connect = $client.BeginConnect($HostAddr, $ProbePort, $null, $null)
            $connected = $connect.AsyncWaitHandle.WaitOne(200, $false)
            if ($connected) {
                $client.EndConnect($connect)
            }
            $client.Close()
            return [bool]$connected
        } catch {
            return $false
        }
    }
}

function Resolve-LaunchPort {
    param([int]$PreferredPort)

    for ($i = 0; $i -lt $PortSearchCount; $i++) {
        $candidate = $PreferredPort + $i
        if ($candidate -gt 65535) {
            break
        }
        if (Test-ServiceReady -ProbePort $candidate) {
            return $candidate
        }
        if (-not (Test-PortListening -ProbePort $candidate)) {
            return $candidate
        }
    }
    return $PreferredPort
}

function Wait-ServiceReady {
    param([int]$ProbePort, $Process)

    $iterations = [Math]::Max(1, [int]($StartupTimeoutSeconds * 2))
    Write-Host ("Waiting for service at {0}" -f (Get-ServiceUrl -ProbePort $ProbePort))
    for ($i = 0; $i -lt $iterations; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-ServiceReady -ProbePort $ProbePort) {
            return $true
        }
        if ($Process -and $Process.HasExited) {
            Write-Host ("Application process exited early (exit code: {0})." -f $Process.ExitCode) -ForegroundColor Yellow
            return $false
        }
        if ((($i + 1) % 10) -eq 0) {
            Write-Host "Still waiting for the local service..."
        }
    }
    return $false
}

function Show-StartupLog {
    foreach ($path in @($ErrLog, $OutLog)) {
        if (Test-Path -LiteralPath $path) {
            Write-Host ""
            Write-Host "Last log lines from $path"
            try {
                Get-Content -LiteralPath $path -Tail 40 | ForEach-Object { Write-Host $_ }
            } catch {
                Write-Host "Could not read log: $_" -ForegroundColor Yellow
            }
        }
    }
}

function Complete-Launch {
    param([bool]$Ready, [int]$LaunchPort)

    $url = Get-ServiceUrl -ProbePort $LaunchPort

    if ($NoBrowser) {
        if (-not $Ready) {
            Add-Content -LiteralPath $ErrLog -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Auto-start timed out while waiting for $url"
        }
        exit 0
    }

    if ($Ready) {
        Start-Process $url
        exit 0
    }

    Write-Host "Service startup failed. Check the log:" -ForegroundColor Red
    Write-Host $ErrLog
    Show-StartupLog
    if (-not $NoPrompt) {
        Read-Host "Press Enter to exit"
    }
    exit 1
}

$LaunchPort = Resolve-LaunchPort -PreferredPort $Port
if ($LaunchPort -ne $Port) {
    Write-Host "Port $Port is busy; using port $LaunchPort instead." -ForegroundColor Yellow
}

# Reuse the running service and avoid duplicate processes.
if (Test-ServiceReady -ProbePort $LaunchPort) {
    if (-not $NoBrowser) {
        Start-Process (Get-ServiceUrl -ProbePort $LaunchPort)
    }
    exit 0
}

# Prefer the bundled offline executable.
if (Test-Path -LiteralPath $AppExe) {
    $process = Start-Process -FilePath $AppExe `
        -ArgumentList @("--host", $HostAddr, "--port", "$LaunchPort", "--no-browser") `
        -WorkingDirectory $AppDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput $OutLog `
        -RedirectStandardError $ErrLog `
        -PassThru

    Complete-Launch -Ready (Wait-ServiceReady -ProbePort $LaunchPort -Process $process) -LaunchPort $LaunchPort
}

# Compatibility fallback for legacy source installations.
if (-not (Test-Path -LiteralPath $PythonExe)) {
    if (-not $NoBrowser) {
        Write-Host "No runnable application was found. Run the installer first." -ForegroundColor Red
        if (-not $NoPrompt) {
            Read-Host "Press Enter to exit"
        }
    } else {
        Add-Content -LiteralPath $ErrLog -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Auto-start failed: missing $AppExe and $PythonExe"
    }
    exit 1
}

$process = Start-Process -FilePath $PythonExe `
    -ArgumentList @("app.py", "--host", $HostAddr, "--port", "$LaunchPort", "--no-browser") `
    -WorkingDirectory $AppDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -PassThru

Complete-Launch -Ready (Wait-ServiceReady -ProbePort $LaunchPort -Process $process) -LaunchPort $LaunchPort
