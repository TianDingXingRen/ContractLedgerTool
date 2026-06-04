$ErrorActionPreference = "Continue"

$TaskName = "ContractLedgerTool"
$StartupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$LauncherPaths = @(
    (Join-Path $StartupDir "ContractLedgerTool_Autostart.vbs"),
    (Join-Path $StartupDir "ContractLedgerTool.vbs")
)
$Removed = $false

try {
    foreach ($LauncherPath in $LauncherPaths) {
        if (Test-Path -LiteralPath $LauncherPath) {
            Remove-Item -LiteralPath $LauncherPath -Force
            $Removed = $true
        }
    }
} catch {
    Write-Host "Failed to remove startup launcher: $_" -ForegroundColor Red
}

try {
    $Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($Existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        $Removed = $true
    }
} catch {
    Write-Host "Scheduled task removal skipped: $_" -ForegroundColor Yellow
}

if ($Removed) {
    Write-Host "Auto-start is disabled." -ForegroundColor Green
} else {
    Write-Host "Auto-start entry was not found." -ForegroundColor Yellow
}

Read-Host "Press Enter to close"
