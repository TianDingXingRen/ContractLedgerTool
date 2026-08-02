param(
    [string]$AppDir = $PSScriptRoot,
    [switch]$NoPrompt,
    [string]$HostAddr = "127.0.0.1",
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

$AppDir = [System.IO.Path]::GetFullPath($AppDir)
$TaskName = "ContractLedgerTool"
$LauncherName = "ContractLedgerTool_Autostart.vbs"
$StartupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$LauncherPath = Join-Path $StartupDir $LauncherName
$LegacyLauncherPaths = @(
    (Join-Path $StartupDir "ContractLedgerTool.vbs")
)

# 使用 start.ps1 -NoBrowser 来后台启动服务，不弹浏览器
$StartPs1 = Join-Path $AppDir "start.ps1"
if (-not (Test-Path -LiteralPath $StartPs1)) {
    throw "未找到 start.ps1: $StartPs1"
}
$PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

# 构建命令行：powershell -File start.ps1 -HostAddr 127.0.0.1 -Port 5000 -NoBrowser
$Command = "`"$PowerShellExe`" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartPs1`" -HostAddr $HostAddr -Port $Port -NoBrowser"

try {
    New-Item -ItemType Directory -Force -Path $StartupDir | Out-Null
    try {
        $ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($ExistingTask) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        }
    } catch {
        Write-Host "旧计划任务清理跳过: $_" -ForegroundColor Yellow
    }
    foreach ($LegacyPath in $LegacyLauncherPaths) {
        if (Test-Path -LiteralPath $LegacyPath) {
            Remove-Item -LiteralPath $LegacyPath -Force
        }
    }
    $EscapedAppDir = $AppDir.Replace('"', '""')
    $EscapedCommand = $Command.Replace('"', '""')
    $VbsContent = @"
' 合同管理工具 - 开机后台启动服务（静默，不弹出浏览器）
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = "$EscapedAppDir"
shell.Run "$EscapedCommand", 0, False
"@
    Set-Content -LiteralPath $LauncherPath -Value $VbsContent -Encoding Unicode
    Write-Host "开机自启已启用（后台静默启动服务）" -ForegroundColor Green
    Write-Host "应用目录: $AppDir"
    Write-Host "启动项: $LauncherPath"
} catch {
    Write-Host "启用开机自启失败: $_" -ForegroundColor Red
    exit 1
}

if (-not $NoPrompt) {
    Read-Host "按 Enter 关闭"
}
