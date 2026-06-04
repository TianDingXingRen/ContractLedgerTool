param(
    [string]$InstallDir = "$env:LOCALAPPDATA\ContractLedgerTool",
    [switch]$NoDesktopShortcut,
    [switch]$NoAutostart,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"

function Write-Step($Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppExeSource = Join-Path $PackageRoot "ContractLedgerTool.exe"
if (-not (Test-Path -LiteralPath $AppExeSource)) {
    throw "Package is incomplete: ContractLedgerTool.exe was not found."
}

Write-Step "Installing offline application files"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$AppExe = Join-Path $InstallDir "ContractLedgerTool.exe"
if (Test-Path -LiteralPath $AppExe) {
    Get-CimInstance Win32_Process |
        Where-Object { $_.ExecutablePath -eq $AppExe } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
}
Copy-Item -LiteralPath $AppExeSource -Destination $AppExe -Force

foreach ($script in @("start.ps1", "stop.ps1", "setup_autostart.ps1", "setup_autostart_remove.ps1")) {
    $src = Join-Path $PackageRoot $script
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $InstallDir $script) -Force
    }
}

foreach ($dir in @("data", "output", "sessions", "uploads", "templates", "static", "logs")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir $dir) | Out-Null
}

if (-not $NoAutostart) {
    Write-Step "Enabling auto-start"
    $SetupScript = Join-Path $InstallDir "setup_autostart.ps1"
    & $SetupScript -AppDir $InstallDir -NoPrompt
}

if (-not $NoDesktopShortcut) {
    Write-Step "Creating desktop launcher"
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $Launcher = Join-Path $Desktop "合同管理工具.lnk"
    $PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $StartPs1 = Join-Path $InstallDir "start.ps1"
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($Launcher)
    $Shortcut.TargetPath = $PowerShellExe
    $Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartPs1`""
    $Shortcut.WorkingDirectory = $InstallDir
    $Shortcut.IconLocation = "$AppExe,0"
    $Shortcut.Save()
}

Write-Step "Installation complete"
Write-Host "Install directory: $InstallDir"
Write-Host "Offline app:       $AppExe"
if (-not $NoDesktopShortcut) {
    Write-Host "Desktop launcher:  $Launcher"
}
if (-not $NoAutostart) {
    Write-Host "Auto-start:        enabled"
}
Write-Host ""

if (-not $NoStart) {
    Write-Host "Starting the contract management tool..."
    & (Join-Path $InstallDir "start.ps1")
}
