param(
    [string]$InstallDir = $PSScriptRoot,
    [switch]$RemoveData,
    [switch]$NoPrompt,
    [switch]$SkipSystemIntegrationCleanup
)

$ErrorActionPreference = "Stop"
$InstallMarkerName = ".contract-ledger-tool-install"

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
            throw "Refusing to uninstall from unsafe directory: $Resolved"
        }
    }
    return $Resolved
}

function Test-SameDirectory($Left, $Right) {
    if ([string]::IsNullOrWhiteSpace($Left) -or [string]::IsNullOrWhiteSpace($Right)) {
        return $false
    }
    $LeftPath = [System.IO.Path]::GetFullPath($Left).TrimEnd('\')
    $RightPath = [System.IO.Path]::GetFullPath($Right).TrimEnd('\')
    return $LeftPath.Equals($RightPath, [System.StringComparison]::OrdinalIgnoreCase)
}

function Test-InstallDirectoryOwnership($Path) {
    $DirectoryInfo = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (-not $DirectoryInfo.PSIsContainer) {
        return $false
    }
    if ($DirectoryInfo.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        throw "Install directory cannot be a symbolic link or junction: $Path"
    }

    $MarkerPath = Join-Path $Path $InstallMarkerName
    if (Test-Path -LiteralPath $MarkerPath -PathType Leaf) {
        try {
            $MarkerInfo = Get-Item -LiteralPath $MarkerPath -ErrorAction Stop
            if ($MarkerInfo.Length -le 128) {
                $MarkerValue = (Get-Content -LiteralPath $MarkerPath -Raw -ErrorAction Stop).Trim()
                if ($MarkerValue -ceq "ContractLedgerTool") {
                    return $true
                }
            }
        } catch {
            # A malformed or unreadable marker is not ownership evidence.
        }
    }

    $RegistryPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ContractLedgerTool"
    try {
        $RegisteredPath = (Get-ItemProperty -LiteralPath $RegistryPath `
            -Name InstallLocation -ErrorAction Stop).InstallLocation
        if (Test-SameDirectory $Path $RegisteredPath) {
            return $true
        }
    } catch {
        # Missing registration is expected for legacy source installations.
    }

    $LegacyBundledDefault = Join-Path $env:LOCALAPPDATA "Programs\ContractLedgerTool"
    if (Test-SameDirectory $Path $LegacyBundledDefault) {
        $BundledFiles = @("ContractLedgerTool.exe", "start.ps1", "version.txt")
        $BundledMatch = $true
        foreach ($Name in $BundledFiles) {
            if (-not (Test-Path -LiteralPath (Join-Path $Path $Name) -PathType Leaf)) {
                $BundledMatch = $false
                break
            }
        }
        if ($BundledMatch) {
            return $true
        }
    }

    $LegacySourceDefault = Join-Path $env:LOCALAPPDATA "ContractLedgerTool"
    if (Test-SameDirectory $Path $LegacySourceDefault) {
        $LegacyFiles = @("app.py", "start.ps1", "setup_autostart.ps1", "version.txt")
        foreach ($Name in $LegacyFiles) {
            if (-not (Test-Path -LiteralPath (Join-Path $Path $Name) -PathType Leaf)) {
                return $false
            }
        }
        return (
            (Test-Path -LiteralPath (Join-Path $Path ".venv") -PathType Container) -and
            (Test-Path -LiteralPath (Join-Path $Path "data") -PathType Container)
        )
    }
    return $false
}

function Remove-IfPresent($Path, [switch]$Recurse) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    if ($Recurse) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    } else {
        Remove-Item -LiteralPath $Path -Force
    }
}

$InstallDir = Assert-SafeInstallDirectory $InstallDir
$AppExe = Join-Path $InstallDir "ContractLedgerTool.exe"
if (-not (Test-Path -LiteralPath $AppExe)) {
    throw "ContractLedgerTool.exe was not found in the requested install directory."
}
if (-not (Test-InstallDirectoryOwnership $InstallDir)) {
    throw "Refusing to uninstall an unrecognized ContractLedgerTool directory: $InstallDir"
}

if (-not $NoPrompt) {
    $Action = if ($RemoveData) { "Uninstall the app and permanently delete all local data" } else { "Uninstall the app and keep local data" }
    $Answer = Read-Host "$Action. Enter Y to continue"
    if ($Answer -notmatch '^[Yy]$') {
        Write-Host "Uninstall cancelled."
        exit 0
    }
}

$StopScript = Join-Path $InstallDir "stop.ps1"
if (Test-Path -LiteralPath $StopScript) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $StopScript 2>&1 |
        ForEach-Object { Write-Host $_ }
}

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $ExecutablePath = [string]$_.ExecutablePath
        $ExecutablePath -and $ExecutablePath.Equals($AppExe, [System.StringComparison]::OrdinalIgnoreCase)
    } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

if (-not $SkipSystemIntegrationCleanup) {
    $RemoveAutostartScript = Join-Path $InstallDir "setup_autostart_remove.ps1"
    if (Test-Path -LiteralPath $RemoveAutostartScript) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $RemoveAutostartScript -NoPrompt 2>&1 |
            ForEach-Object { Write-Host $_ }
    }

    $Desktop = [Environment]::GetFolderPath("Desktop")
    foreach ($ShortcutName in @("合同管理工具.lnk", "ContractLedgerTool.lnk")) {
        Remove-IfPresent (Join-Path $Desktop $ShortcutName)
    }

    $RegistryPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ContractLedgerTool"
    Remove-IfPresent $RegistryPath -Recurse
}

if ($RemoveData) {
    Set-Location ([System.IO.Path]::GetTempPath())
    Remove-Item -LiteralPath $InstallDir -Recurse -Force
    Write-Host "Uninstall complete. The app and all local data were deleted."
    exit 0
}

$ManagedFiles = @(
    "ContractLedgerTool.exe",
    "start.ps1",
    "launch.vbs",
    "stop.ps1",
    "setup_autostart.ps1",
    "setup_autostart_remove.ps1",
    "version.txt",
    ".installed_version",
    ".contract-ledger-tool-install"
)
foreach ($Name in $ManagedFiles) {
    Remove-IfPresent (Join-Path $InstallDir $Name)
}

Write-Host "Uninstall complete. Contracts, ledger, templates, settings, and backups were kept in: $InstallDir"
Write-Host "After confirming your backup, delete that directory manually to remove all data."

# Keep this statement last: Windows PowerShell has already loaded the script.
Remove-IfPresent (Join-Path $InstallDir "uninstall.ps1")
