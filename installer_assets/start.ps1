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
$OutLog = Join-Path $AppDir "server.log"
$ErrLog = Join-Path $AppDir "server_error.log"

function Test-ServiceReady {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2 -ErrorAction Stop | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Wait-ServiceReady {
    for ($i = 0; $i -lt 20; $i++) {
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
            Add-Content -LiteralPath $ErrLog -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') 开机自启：服务启动超时，未能监听 $Url"
        }
        exit 0
    }

    if ($Ready) {
        Start-Process $Url
        exit 0
    }

    Write-Host "服务启动失败，请检查日志：" -ForegroundColor Red
    Write-Host $ErrLog
    Read-Host "按 Enter 退出"
    exit 1
}

# 服务已在运行时，只按需打开浏览器，避免重复启动。
if (Test-ServiceReady) {
    if (-not $NoBrowser) {
        Start-Process $Url
    }
    exit 0
}

# 离线安装模式：优先启动内置的独立 EXE，不依赖 Python 或网络。
if (Test-Path -LiteralPath $AppExe) {
    Start-Process -FilePath $AppExe `
        -ArgumentList @("--host", $HostAddr, "--port", "$Port", "--no-browser") `
        -WorkingDirectory $AppDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput $OutLog `
        -RedirectStandardError $ErrLog

    Complete-Launch -Ready (Wait-ServiceReady)
}

# 兼容旧的源码安装模式。
if (-not (Test-Path -LiteralPath $PythonExe)) {
    if (-not $NoBrowser) {
        Write-Host "Python 环境未找到，请先运行安装程序。" -ForegroundColor Red
        Read-Host "按 Enter 退出"
    } else {
        Add-Content -LiteralPath $ErrLog -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') 开机自启失败：未找到可运行程序 $AppExe 或 Python 环境 $PythonExe"
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
