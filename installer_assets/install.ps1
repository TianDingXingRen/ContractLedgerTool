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
            $path = [string]$_.ExecutablePath
            $cmd = [string]$_.CommandLine
            $isInstalledApp = $path -and $path.Equals($fullAppExe, [System.StringComparison]::OrdinalIgnoreCase)
            $isUnderInstallDir = $path -and $path.StartsWith($fullInstallDir, [System.StringComparison]::OrdinalIgnoreCase)
            $isLegacySourceCommand = (
                $cmd -and
                ($cmd.IndexOf($fullInstallDir, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) -and
                ($cmd.IndexOf("app.py", [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
            )
            $_.ProcessId -ne $PID -and ($isInstalledApp -or $isUnderInstallDir -or $isLegacySourceCommand)
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
                (($name -eq "python.exe" -or $name -eq "pythonw.exe") -and $cmd -and ($cmd -like "*app.py*" -or $cmd -like "*ContractLedgerTool*")) -or
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

function Test-PortListening($Port) {
    try {
        $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        return [bool]$listeners
    } catch {
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $connect = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
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

function Resolve-InstallPort($PreferredPort) {
    for ($i = 0; $i -lt 20; $i++) {
        $candidate = $PreferredPort + $i
        if ($candidate -gt 65535) {
            break
        }
        if (-not (Test-PortListening $candidate)) {
            return $candidate
        }
    }
    return $PreferredPort
}

function Invoke-PowerShellFile($ScriptPath, $Arguments) {
    $PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    & $PowerShellExe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath @Arguments 2>&1 |
        ForEach-Object { Write-Host $_ }
    $exitCode = $LASTEXITCODE

    return $exitCode
}

function Invoke-OptionalPowerShellFile($Description, $ScriptPath, $Arguments) {
    try {
        if (-not (Test-Path -LiteralPath $ScriptPath)) {
            throw "Script was not found: $ScriptPath"
        }

        $exitCode = Invoke-PowerShellFile $ScriptPath $Arguments
        if ($exitCode -ne 0) {
            Write-Host "$Description failed (exit code: $exitCode). Installation files are already in place." -ForegroundColor Yellow
            return $false
        }
        return $true
    } catch {
        Write-Host "$Description failed: $_" -ForegroundColor Yellow
        Write-Host "Installation files are already in place; you can run start.ps1 manually from the install directory." -ForegroundColor Yellow
        return $false
    }
}

function Start-OptionalPowerShellFile($Description, $ScriptPath, $Arguments) {
    try {
        if (-not (Test-Path -LiteralPath $ScriptPath)) {
            throw "Script was not found: $ScriptPath"
        }

        $PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
        $argList = @(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "`"$ScriptPath`""
        ) + $Arguments
        Start-Process -FilePath $PowerShellExe `
            -ArgumentList $argList `
            -WorkingDirectory (Split-Path -Parent $ScriptPath) `
            -WindowStyle Hidden | Out-Null
        return $true
    } catch {
        Write-Host "$Description could not be started: $_" -ForegroundColor Yellow
        Write-Host "Installation files are already in place; you can run start.ps1 manually from the install directory." -ForegroundColor Yellow
        return $false
    }
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
$ResolvedPort = Resolve-InstallPort $Port
if ($ResolvedPort -ne $Port) {
    Write-Host "Port $Port is busy; using port $ResolvedPort instead." -ForegroundColor Yellow
    $Port = $ResolvedPort
}
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
    $AutostartEnabled = Invoke-OptionalPowerShellFile "Auto-start setup" $SetupScript @("-AppDir", $InstallDir, "-NoPrompt", "-Port", "$Port")
}

if (-not $NoDesktopShortcut) {
    Write-Step "Creating desktop launcher"
    try {
        $Launcher = New-DesktopLauncher $InstallDir $AppExe $Port
    } catch {
        Write-Host "Desktop launcher creation failed: $_" -ForegroundColor Yellow
        Write-Host "Installation files are already in place; you can run start.ps1 manually from the install directory." -ForegroundColor Yellow
    }
}

Write-Step "Installation complete"
Write-Host "Install directory: $InstallDir"
Write-Host "Offline app:       $AppExe"
Write-Host "Local URL:         http://127.0.0.1:$Port/"
if (-not $NoDesktopShortcut) {
    if ($Launcher) {
        Write-Host "Desktop launcher:  $Launcher"
    } else {
        Write-Host "Desktop launcher:  skipped"
    }
}
if (-not $NoAutostart) {
    if ($AutostartEnabled) {
        Write-Host "Auto-start:        enabled"
    } else {
        Write-Host "Auto-start:        skipped"
    }
}
Write-Host ""

if (-not $NoStart) {
    Write-Host "Starting the contract management tool in the background..."
    $StartScript = Join-Path $InstallDir "start.ps1"
    $StartRequested = Start-OptionalPowerShellFile "Application startup" $StartScript @("-Port", "$Port", "-NoPrompt")
    if ($StartRequested) {
        Write-Host "If the browser does not open shortly, use the desktop launcher or open http://127.0.0.1:$Port/."
    } else {
        Write-Host "Installation completed, but automatic startup could not be requested." -ForegroundColor Yellow
    }
}
