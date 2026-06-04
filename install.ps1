param(
    [string]$InstallDir = "$env:LOCALAPPDATA\ContractLedgerTool"
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "合同管理工具 - 安装程序"

$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppSource = Join-Path $PackageRoot "app"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "    合同管理工具 - 安装程序"                   -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. 检查 Python ──
Write-Host "[1/5] 检查 Python 环境..." -ForegroundColor Yellow
$PythonExe = $null
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
    try { $PythonExe = (& py -3 -c "import sys; print(sys.executable)" 2>$null).Trim() } catch {}
}
if (-not $PythonExe) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        try { $PythonExe = (& python -c "import sys; print(sys.executable)" 2>$null).Trim() } catch {}
    }
}
if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "未找到 Python，尝试通过 winget 安装 Python 3.12..."
        winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
        $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "User") + ";" + [Environment]::GetEnvironmentVariable("PATH", "Machine")
        try { $PythonExe = (& py -3 -c "import sys; print(sys.executable)" 2>$null).Trim() } catch {}
    }
    if (-not $PythonExe) {
        Write-Host "请先安装 Python 3.11+，然后重新运行安装程序。" -ForegroundColor Red
        Write-Host "下载: https://www.python.org/downloads/" -ForegroundColor Yellow
        Read-Host "按 Enter 退出"
        exit 1
    }
}
Write-Host "  Python 路径: $PythonExe" -ForegroundColor Green

# ── 2. 复制应用文件 ──
Write-Host "[2/5] 复制应用文件到 $InstallDir ..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

Get-ChildItem -LiteralPath $AppSource -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $InstallDir -Force
}

foreach ($assetDir in @("static", "templates", "uploads", "routes", "utils")) {
    $srcDir = Join-Path $AppSource $assetDir
    $dstDir = Join-Path $InstallDir $assetDir
    New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
    if (Test-Path $srcDir) {
        $items = Get-ChildItem -LiteralPath $srcDir -Force -ErrorAction SilentlyContinue
        if ($items) {
            Copy-Item -LiteralPath $items.FullName -Destination $dstDir -Recurse -Force
        }
    }
}

foreach ($dir in @("data", "output", "sessions", "logs")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir $dir) | Out-Null
}
Write-Host "  文件复制完成" -ForegroundColor Green

# ── 3. 创建虚拟环境并安装依赖 ──
Write-Host "[3/5] 创建虚拟环境并安装 Python 依赖..." -ForegroundColor Yellow
$VenvDir = Join-Path $InstallDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    & $PythonExe -m venv $VenvDir
    if (-not (Test-Path $VenvPython)) {
        Write-Host "  虚拟环境创建失败，请检查 Python 安装" -ForegroundColor Red
        Read-Host "按 Enter 退出"
        exit 1
    }
}
& $VenvPython -m pip install --upgrade pip --quiet 2>&1 | Out-Null
& $VenvPython -m pip install -r (Join-Path $InstallDir "requirements.txt") --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "  pip 安装依赖失败（退出码: $LASTEXITCODE），请检查网络连接" -ForegroundColor Red
    Read-Host "按 Enter 退出"
    exit 1
}
Write-Host "  依赖安装完成" -ForegroundColor Green

# ── 4. 配置开机自启 ──
Write-Host "[4/5] 配置开机自启（后台静默启动服务）..." -ForegroundColor Yellow
$SetupScript = Join-Path $InstallDir "setup_autostart.ps1"
if (Test-Path $SetupScript) {
    try {
        & $SetupScript -AppDir $InstallDir -NoPrompt
    } catch {
        Write-Host "  开机自启配置失败: $_" -ForegroundColor Yellow
        Write-Host "  您可以稍后在应用内手动开启自启" -ForegroundColor Yellow
    }
}
Write-Host "  开机自启配置完成" -ForegroundColor Green

# ── 5. 创建桌面快捷方式 ──
Write-Host "[5/5] 创建桌面快捷方式..." -ForegroundColor Yellow
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "合同管理工具.lnk"
$PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$StartPs1 = Join-Path $InstallDir "start.ps1"
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $PowerShellExe
$Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartPs1`""
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.IconLocation = "$PowerShellExe,0"
$Shortcut.Save()
Write-Host "  快捷方式: $ShortcutPath" -ForegroundColor Green

# ── 完成 ──
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "    安装完成！"                              -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  安装目录:       $InstallDir"
Write-Host "  桌面快捷方式:   $ShortcutPath"
Write-Host "  开机自启:       已启用（开机后后台启动服务）"
Write-Host ""

# ── 启动应用 ──
Write-Host "正在启动合同管理工具，浏览器将自动打开..."
Start-Sleep -Seconds 1
& $StartPs1
