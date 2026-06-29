param(
    [string]$InstallDir = "$env:LOCALAPPDATA\ContractLedgerTool",
    [switch]$NoDesktopShortcut,
    [switch]$NoAutostart,
    [switch]$NoStart,
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

function Write-Step($Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Set-WritableIfExists($Path) {
    if (Test-Path -LiteralPath $Path) {
        try {
            Set-ItemProperty -LiteralPath $Path -Name IsReadOnly -Value $false -ErrorAction SilentlyContinue
        } catch {
            Write-Host "Could not clear read-only flag on $Path : $_" -ForegroundColor Yellow
        }
    }
}

function Stop-ProcessIfRunning($ProcessId, $Reason) {
    if (-not $ProcessId -or $ProcessId -eq $PID) {
        return
    }
    try {
        Stop-Process -Id $ProcessId -Force -ErrorAction Stop
        Write-Host "Stopped previous process $ProcessId ($Reason)"
    } catch {
        Write-Host "Could not stop process $ProcessId ($Reason): $_" -ForegroundColor Yellow
    }
}

function Stop-PreviousVersions($InstallDir, $AppExe, $Port) {
    $fullInstallDir = [System.IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
    $fullAppExe = [System.IO.Path]::GetFullPath($AppExe)

    Get-CimInstance Win32_Process |
        Where-Object {
            $name = $_.Name
            $path = [string]$_.ExecutablePath
            $cmd = [string]$_.CommandLine
            $isInstalledApp = $path -and $path.Equals($fullAppExe, [System.StringComparison]::OrdinalIgnoreCase)
            $isToolExe = $name -eq "ContractLedgerTool.exe"
            $isUnderInstallDir = (
                ($path -and $path.StartsWith($fullInstallDir, [System.StringComparison]::OrdinalIgnoreCase)) -or
                ($cmd -and ($cmd.IndexOf($fullInstallDir, [System.StringComparison]::OrdinalIgnoreCase) -ge 0))
            )
            $_.ProcessId -ne $PID -and ($isInstalledApp -or $isToolExe -or $isUnderInstallDir)
        } |
        ForEach-Object { Stop-ProcessIfRunning $_.ProcessId "installed tool" }

    try {
        $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($ownerProcessId in $listeners) {
            if (-not $ownerProcessId -or $ownerProcessId -eq $PID) {
                continue
            }
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$ownerProcessId" -ErrorAction SilentlyContinue
            if (-not $proc) {
                continue
            }
            $name = [string]$proc.Name
            $cmd = [string]$proc.CommandLine
            $looksLikeOldTool = (
                $name -eq "ContractLedgerTool.exe" -or
                $name -eq "python.exe" -or
                $name -eq "pythonw.exe" -or
                ($cmd -and ($cmd -like "*app.py*" -or $cmd -like "*ContractLedgerTool*"))
            )
            if ($looksLikeOldTool) {
                Stop-ProcessIfRunning $ownerProcessId "port $Port"
            }
        }
    } catch {
        Write-Host "Port cleanup skipped: $_" -ForegroundColor Yellow
    }

    Start-Sleep -Milliseconds 500
}

function Clear-ExistingAutostart {
    $TaskName = "ContractLedgerTool"
    $StartupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
    $LauncherNames = @(
        "ContractLedgerTool_Autostart.vbs",
        "ContractLedgerTool.vbs"
    )

    foreach ($name in $LauncherNames) {
        $path = Join-Path $StartupDir $name
        if (Test-Path -LiteralPath $path) {
            try {
                Remove-Item -LiteralPath $path -Force
                Write-Host "Removed old auto-start launcher: $path"
            } catch {
                Write-Host "Could not remove old auto-start launcher $path : $_" -ForegroundColor Yellow
            }
        }
    }

    try {
        $ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($ExistingTask) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
            Write-Host "Removed old scheduled task: $TaskName"
        }
    } catch {
        Write-Host "Scheduled task cleanup skipped: $_" -ForegroundColor Yellow
    }
}

function Clear-LegacyProgramFiles($InstallDir) {
    $LegacyDirs = @(
        ".venv",
        "__pycache__",
        "core",
        "routes",
        "utils",
        "services",
        "runtime",
        "ledger_store",
        "procurement_store"
    )
    $LegacyFiles = @(
        "app.py",
        "config.py",
        "doc_processor.py",
        "docx_builder.py",
        "excel_bill_service.py",
        "field_eval.py",
        "ledger_store.py",
        "payment_extractor.py",
        "pdf_exporter.py",
        "template_def.py",
        "xlsx_exporter.py",
        "requirements.txt",
        "requirements.lock",
        "pyproject.toml",
        "install.bat",
        "setup.bat",
        "start.bat"
    )

    foreach ($dir in $LegacyDirs) {
        $path = Join-Path $InstallDir $dir
        if (Test-Path -LiteralPath $path) {
            try {
                Remove-Item -LiteralPath $path -Recurse -Force
                Write-Host "Removed legacy directory: $dir"
            } catch {
                Write-Host "Could not remove legacy directory $dir : $_" -ForegroundColor Yellow
            }
        }
    }

    foreach ($file in $LegacyFiles) {
        $path = Join-Path $InstallDir $file
        if (Test-Path -LiteralPath $path) {
            try {
                Set-WritableIfExists $path
                Remove-Item -LiteralPath $path -Force
                Write-Host "Removed legacy file: $file"
            } catch {
                Write-Host "Could not remove legacy file $file : $_" -ForegroundColor Yellow
            }
        }
    }
}

function New-DesktopLauncher($InstallDir, $AppExe, $Port) {
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $ShortcutPath = Join-Path $Desktop "合同管理工具.lnk"
    $EnglishShortcutPath = Join-Path $Desktop "ContractLedgerTool.lnk"
    $PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $StartPs1 = Join-Path $InstallDir "start.ps1"

    foreach ($oldShortcut in @($ShortcutPath, $EnglishShortcutPath)) {
        if (Test-Path -LiteralPath $oldShortcut) {
            try {
                Remove-Item -LiteralPath $oldShortcut -Force
            } catch {
                Write-Host "Could not replace desktop launcher $oldShortcut : $_" -ForegroundColor Yellow
            }
        }
    }

    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $PowerShellExe
    $Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartPs1`" -Port $Port"
    $Shortcut.WorkingDirectory = $InstallDir
    $Shortcut.IconLocation = "$AppExe,0"
    $Shortcut.Save()
    return $ShortcutPath
}

$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppExeSource = Join-Path $PackageRoot "ContractLedgerTool.exe"
if (-not (Test-Path -LiteralPath $AppExeSource)) {
    throw "Package is incomplete: ContractLedgerTool.exe was not found."
}

Write-Step "Installing offline application files"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$AppExe = Join-Path $InstallDir "ContractLedgerTool.exe"
Stop-PreviousVersions $InstallDir $AppExe $Port
Clear-ExistingAutostart
Clear-LegacyProgramFiles $InstallDir
Set-WritableIfExists $AppExe
Copy-Item -LiteralPath $AppExeSource -Destination $AppExe -Force

foreach ($script in @("start.ps1", "stop.ps1", "setup_autostart.ps1", "setup_autostart_remove.ps1")) {
    $src = Join-Path $PackageRoot $script
    if (Test-Path -LiteralPath $src) {
        $dst = Join-Path $InstallDir $script
        Set-WritableIfExists $dst
        Copy-Item -LiteralPath $src -Destination $dst -Force
    }
}

foreach ($dir in @("data", "output", "sessions", "uploads", "templates", "static", "logs")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir $dir) | Out-Null
}

if (-not $NoAutostart) {
    Write-Step "Enabling auto-start"
    $SetupScript = Join-Path $InstallDir "setup_autostart.ps1"
    & $SetupScript -AppDir $InstallDir -NoPrompt -Port $Port
}

if (-not $NoDesktopShortcut) {
    Write-Step "Creating desktop launcher"
    $Launcher = New-DesktopLauncher $InstallDir $AppExe $Port
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
    & (Join-Path $InstallDir "start.ps1") -Port $Port
}
