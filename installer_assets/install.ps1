param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\ContractLedgerTool",
    [switch]$NoDesktopShortcut,
    [switch]$EnableAutostart,
    [switch]$NoAutostart,
    [switch]$NoStart,
    [switch]$SkipSystemIntegrationCleanup,
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

function Write-Step($Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Assert-SafeInstallDirectory($Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "Install directory cannot be empty."
    }
    $Resolved = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    $Candidates = @(
        [System.IO.Path]::GetPathRoot($Resolved),
        $env:USERPROFILE,
        $env:LOCALAPPDATA,
        $env:APPDATA,
        $env:SystemRoot,
        $env:ProgramFiles,
        ${env:ProgramFiles(x86)},
        [Environment]::GetFolderPath("Desktop"),
        [Environment]::GetFolderPath("MyDocuments"),
        [System.IO.Path]::GetTempPath()
    )
    foreach ($Candidate in $Candidates) {
        if ([string]::IsNullOrWhiteSpace($Candidate)) {
            continue
        }
        $Forbidden = [System.IO.Path]::GetFullPath($Candidate).TrimEnd('\')
        if ($Resolved.Equals($Forbidden, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to install into unsafe directory: $Resolved"
        }
    }
    $DesktopRoot = [System.IO.Path]::GetFullPath(
        [Environment]::GetFolderPath("Desktop")
    ).TrimEnd('\')
    $DesktopPrefix = $DesktopRoot + '\'
    if ($Resolved.Equals($DesktopRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
        $Resolved.StartsWith($DesktopPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to install on the Desktop. Choose a dedicated application directory."
    }
    return $Resolved
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

function Get-Sha256Hex {
    param([Parameter(Mandatory = $true)][string]$Path)

    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        try {
            $hash = $sha256.ComputeHash($stream)
            return ([System.BitConverter]::ToString($hash)).Replace('-', '')
        }
        finally {
            $sha256.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
}

function Stage-AppExecutable($Source, $Destination) {
    $staged = "$Destination.new"
    if (Test-Path -LiteralPath $staged) {
        Set-WritableIfExists $staged
        Remove-Item -LiteralPath $staged -Force
    }

    Copy-Item -LiteralPath $Source -Destination $staged -Force
    $sourceHash = Get-Sha256Hex -Path $Source
    $stagedHash = Get-Sha256Hex -Path $staged
    if ($sourceHash -ne $stagedHash) {
        Remove-Item -LiteralPath $staged -Force -ErrorAction SilentlyContinue
        throw "Staged application verification failed."
    }
    return $staged
}

function Install-StagedExecutable($Staged, $Destination) {
    $previous = "$Destination.previous"
    if (Test-Path -LiteralPath $previous) {
        Set-WritableIfExists $previous
        Remove-Item -LiteralPath $previous -Force
    }

    $hadPrevious = Test-Path -LiteralPath $Destination
    if ($hadPrevious) {
        Set-WritableIfExists $Destination
        Move-Item -LiteralPath $Destination -Destination $previous -Force
    }

    try {
        Move-Item -LiteralPath $Staged -Destination $Destination -Force
    } catch {
        if ($hadPrevious -and (Test-Path -LiteralPath $previous)) {
            Move-Item -LiteralPath $previous -Destination $Destination -Force
        }
        throw
    }

    if (Test-Path -LiteralPath $previous) {
        Remove-Item -LiteralPath $previous -Force
    }
}

function New-InstallRollbackSnapshot($InstallDir, $ManagedFiles) {
    $snapshot = Join-Path ([System.IO.Path]::GetTempPath()) (
        "ContractLedgerTool-install-rollback-" + [guid]::NewGuid().ToString("N")
    )
    New-Item -ItemType Directory -Force -Path $snapshot | Out-Null
    foreach ($name in $ManagedFiles) {
        $source = Join-Path $InstallDir $name
        if (Test-Path -LiteralPath $source) {
            Copy-Item -LiteralPath $source -Destination (Join-Path $snapshot $name) -Force
        }
    }
    return $snapshot
}

function Restore-InstallRollbackSnapshot($Snapshot, $InstallDir, $ManagedFiles) {
    foreach ($name in $ManagedFiles) {
        $backup = Join-Path $Snapshot $name
        $destination = Join-Path $InstallDir $name
        Set-WritableIfExists $destination
        if (Test-Path -LiteralPath $backup) {
            Copy-Item -LiteralPath $backup -Destination $destination -Force
        } elseif (Test-Path -LiteralPath $destination) {
            Remove-Item -LiteralPath $destination -Force
        }
    }

    foreach ($suffix in @(".new", ".previous")) {
        $temporaryExe = (Join-Path $InstallDir "ContractLedgerTool.exe") + $suffix
        if (Test-Path -LiteralPath $temporaryExe) {
            Set-WritableIfExists $temporaryExe
            Remove-Item -LiteralPath $temporaryExe -Force
        }
    }
}

function Remove-InstallRollbackSnapshot($Snapshot) {
    if (Test-Path -LiteralPath $Snapshot) {
        try {
            Remove-Item -LiteralPath $Snapshot -Recurse -Force
        } catch {
            Write-Host "Could not remove rollback snapshot $Snapshot : $_" -ForegroundColor Yellow
        }
    }
}

function Invoke-InstalledAppSelfCheck($AppExe) {
    Write-Step "Verifying installed application"
    $reportPath = Join-Path ([System.IO.Path]::GetTempPath()) (
        "ContractLedgerTool-self-check-" + [guid]::NewGuid().ToString("N") + ".json"
    )
    try {
        $process = Start-Process -FilePath $AppExe `
            -ArgumentList @("--self-check", "--self-check-output", "`"$reportPath`"") `
            -WorkingDirectory (Split-Path -Parent $AppExe) `
            -WindowStyle Hidden `
            -Wait `
            -PassThru
        if ($process.ExitCode -ne 0) {
            throw "Installed application self-check failed (exit code: $($process.ExitCode))."
        }
        if (-not (Test-Path -LiteralPath $reportPath)) {
            throw "Installed application self-check did not create a report."
        }
        try {
            $result = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
        } catch {
            throw "Installed application self-check did not return valid JSON."
        }
        if (-not $result.ok -or $result.http_status -ne 200 -or $result.integrity_check -ne "ok") {
            throw "Installed application self-check reported an unhealthy runtime."
        }
    } finally {
        Remove-Item -LiteralPath $reportPath -Force -ErrorAction SilentlyContinue
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
    $installPrefix = $fullInstallDir + '\'
    $fullAppExe = [System.IO.Path]::GetFullPath($AppExe)

    Get-CimInstance Win32_Process |
        Where-Object {
            $path = [string]$_.ExecutablePath
            $cmd = [string]$_.CommandLine
            $isInstalledApp = $path -and $path.Equals($fullAppExe, [System.StringComparison]::OrdinalIgnoreCase)
            $isUnderInstallDir = $path -and $path.StartsWith($installPrefix, [System.StringComparison]::OrdinalIgnoreCase)
            $isLegacySourceCommand = (
                $cmd -and
                ($cmd.IndexOf($installPrefix, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) -and
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
    $WScriptExe = Join-Path $env:SystemRoot "System32\wscript.exe"
    $StartPs1 = Join-Path $InstallDir "start.ps1"
    $LaunchVbs = Join-Path $InstallDir "launch.vbs"

    foreach ($oldShortcut in @($ShortcutPath, $EnglishShortcutPath)) {
        if (Test-Path -LiteralPath $oldShortcut) {
            try {
                Remove-Item -LiteralPath $oldShortcut -Force
            } catch {
                Write-Host "Could not replace desktop launcher $oldShortcut : $_" -ForegroundColor Yellow
            }
        }
    }

    $EscapedStartPs1 = $StartPs1.Replace('"', '""')
    $LauncherScript = @"
Set shell = CreateObject("WScript.Shell")
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""$EscapedStartPs1"" -Port $Port", 0, False
"@
    Set-Content -LiteralPath $LaunchVbs -Value $LauncherScript -Encoding Unicode

    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $WScriptExe
    $Shortcut.Arguments = "`"$LaunchVbs`""
    $Shortcut.WorkingDirectory = $InstallDir
    $Shortcut.IconLocation = "$AppExe,0"
    $Shortcut.Save()
    return $ShortcutPath
}

function Register-Uninstaller($InstallDir, $AppExe, $Version) {
    $RegistryPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ContractLedgerTool"
    $UninstallScript = Join-Path $InstallDir "uninstall.ps1"
    $PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $UninstallCommand = "`"$PowerShellExe`" -NoProfile -ExecutionPolicy Bypass -File `"$UninstallScript`""
    $QuietUninstallCommand = "$UninstallCommand -NoPrompt"
    $EstimatedSize = [int][Math]::Ceiling((Get-Item -LiteralPath $AppExe).Length / 1KB)

    New-Item -Path $RegistryPath -Force | Out-Null
    New-ItemProperty -Path $RegistryPath -Name "DisplayName" -Value "采购业务平台" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $RegistryPath -Name "DisplayVersion" -Value $Version -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $RegistryPath -Name "Publisher" -Value "Shao" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $RegistryPath -Name "DisplayIcon" -Value "$AppExe,0" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $RegistryPath -Name "InstallLocation" -Value $InstallDir -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $RegistryPath -Name "UninstallString" -Value $UninstallCommand -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $RegistryPath -Name "QuietUninstallString" -Value $QuietUninstallCommand -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $RegistryPath -Name "EstimatedSize" -Value $EstimatedSize -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $RegistryPath -Name "NoModify" -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $RegistryPath -Name "NoRepair" -Value 1 -PropertyType DWord -Force | Out-Null
}

$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallDir = Assert-SafeInstallDirectory $InstallDir
$AppExeSource = Join-Path $PackageRoot "ContractLedgerTool.exe"
if (-not (Test-Path -LiteralPath $AppExeSource)) {
    throw "Package is incomplete: ContractLedgerTool.exe was not found."
}

Write-Step "Installing offline application files"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$AppExe = Join-Path $InstallDir "ContractLedgerTool.exe"
$ManagedFiles = @(
    "ContractLedgerTool.exe",
    "start.ps1",
    "launch.vbs",
    "stop.ps1",
    "setup_autostart.ps1",
    "setup_autostart_remove.ps1",
    "uninstall.ps1",
    "version.txt"
)
$RollbackSnapshot = New-InstallRollbackSnapshot $InstallDir $ManagedFiles

try {
    $StagedAppExe = Stage-AppExecutable $AppExeSource $AppExe
    Stop-PreviousVersions $InstallDir $AppExe $Port
    $ResolvedPort = Resolve-InstallPort $Port
    if ($ResolvedPort -ne $Port) {
        Write-Host "Port $Port is busy; using port $ResolvedPort instead." -ForegroundColor Yellow
        $Port = $ResolvedPort
    }
    Install-StagedExecutable $StagedAppExe $AppExe

    foreach ($script in @("start.ps1", "stop.ps1", "setup_autostart.ps1", "setup_autostart_remove.ps1", "uninstall.ps1", "version.txt")) {
        $src = Join-Path $PackageRoot $script
        if (Test-Path -LiteralPath $src) {
            $dst = Join-Path $InstallDir $script
            Set-WritableIfExists $dst
            Copy-Item -LiteralPath $src -Destination $dst -Force
        }
    }

    Invoke-InstalledAppSelfCheck $AppExe
    foreach ($dir in @("data", "output", "sessions", "uploads", "templates", "static", "logs")) {
        New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir $dir) | Out-Null
    }
} catch {
    $installError = $_
    Write-Step "Installation failed; restoring previous version"
    try {
        Restore-InstallRollbackSnapshot $RollbackSnapshot $InstallDir $ManagedFiles
        Write-Host "Previous application files were restored." -ForegroundColor Yellow
    } catch {
        Write-Host "Automatic rollback failed: $_" -ForegroundColor Red
    }
    throw $installError
} finally {
    Remove-InstallRollbackSnapshot $RollbackSnapshot
}

# Destructive cleanup and system integration changes happen only after the new
# executable passes its isolated HTTP and SQLite self-check.
Clear-LegacyProgramFiles $InstallDir

if (-not $SkipSystemIntegrationCleanup) {
    Clear-ExistingAutostart
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

if (-not $SkipSystemIntegrationCleanup) {
    try {
        $Version = "unknown"
        $VersionPath = Join-Path $InstallDir "version.txt"
        if (Test-Path -LiteralPath $VersionPath) {
            $Version = (Get-Content -LiteralPath $VersionPath -Raw -Encoding UTF8).Trim()
        }
        Register-Uninstaller $InstallDir $AppExe $Version
    } catch {
        Write-Host "Windows uninstall registration failed: $_" -ForegroundColor Yellow
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
} else {
    Write-Host "Auto-start:        disabled by -NoAutostart"
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
