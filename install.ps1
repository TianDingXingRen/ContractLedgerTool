param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\ContractLedgerTool",
    [switch]$NoDesktopShortcut,
    [switch]$NoAutostart,
    [switch]$NoStart,
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

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

$InstallDir = Assert-SafeInstallDirectory $InstallDir
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppSource = Join-Path $PackageRoot "app"
if (-not (Test-Path -LiteralPath (Join-Path $AppSource "app.py"))) {
    $AppSource = $PackageRoot
}

function Find-Python {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        $candidate = (& py -3 -c "import sys; print(sys.executable)" 2>$null).Trim()
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
    }
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) {
        $candidate = (& python -c "import sys; print(sys.executable)" 2>$null).Trim()
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
    }
    throw "Python 3.10 or later is required. Use the offline installer on machines without Python."
}

function Copy-TreeContents($Source, $Destination) {
    if (-not (Test-Path -LiteralPath $Source)) { return }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Get-ChildItem -LiteralPath $Source -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $Destination -Recurse -Force
    }
}

Write-Host "Installing ContractLedgerTool source package to $InstallDir"
$PythonExe = Find-Python
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

foreach ($name in @(
    "app.py", "config.py", "docx_builder.py", "excel_bill_service.py",
    "field_eval.py", "payment_extractor.py", "pdf_exporter.py", "template_def.py",
    "xlsx_exporter.py", "requirements.txt", "requirements.lock", "pyproject.toml",
    "version.txt", "setup_autostart.ps1", "setup_autostart_remove.ps1"
)) {
    $source = Join-Path $AppSource $name
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $InstallDir $name) -Force
    }
}

foreach ($package in @("core", "runtime", "ledger_store", "procurement_store", "routes", "services", "utils", "static")) {
    Copy-TreeContents (Join-Path $AppSource $package) (Join-Path $InstallDir $package)
}

# HTML is application code and is updated. Contract templates and source
# documents are user-owned after installation and are only seeded when absent.
$sourceTemplates = Join-Path $AppSource "templates"
if (Test-Path -LiteralPath $sourceTemplates) {
    Get-ChildItem -LiteralPath $sourceTemplates -Recurse -File | ForEach-Object {
        $relative = $_.FullName.Substring($sourceTemplates.Length).TrimStart('\')
        $destination = Join-Path (Join-Path $InstallDir "templates") $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
        if ($_.Extension -eq ".html" -or -not (Test-Path -LiteralPath $destination)) {
            Copy-Item -LiteralPath $_.FullName -Destination $destination -Force
        }
    }
}

$sourceUploads = Join-Path $AppSource "uploads"
if (Test-Path -LiteralPath $sourceUploads) {
    Get-ChildItem -LiteralPath $sourceUploads -Recurse -File | ForEach-Object {
        $relative = $_.FullName.Substring($sourceUploads.Length).TrimStart('\')
        $destination = Join-Path (Join-Path $InstallDir "uploads") $relative
        if (-not (Test-Path -LiteralPath $destination)) {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $destination
        }
    }
}

foreach ($dir in @("data", "output", "sessions", "uploads", "templates", "logs")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir $dir) | Out-Null
}

foreach ($script in @("start.ps1", "stop.ps1")) {
    $source = Join-Path $AppSource $script
    if (-not (Test-Path -LiteralPath $source)) {
        $source = Join-Path (Join-Path $PackageRoot "installer_assets") $script
    }
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $InstallDir $script) -Force
    }
}

$VenvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    & $PythonExe -m venv (Join-Path $InstallDir ".venv")
}
$requirements = Join-Path $InstallDir "requirements.lock"
if (-not (Test-Path -LiteralPath $requirements)) {
    $requirements = Join-Path $InstallDir "requirements.txt"
}
& $VenvPython -m pip install -r $requirements
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed with exit code $LASTEXITCODE" }

if (-not $NoAutostart) {
    & (Join-Path $InstallDir "setup_autostart.ps1") -AppDir $InstallDir -NoPrompt -Port $Port
}

if (-not $NoDesktopShortcut) {
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $ShortcutPath = Join-Path $Desktop "合同管理工具.lnk"
    $PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $StartPs1 = Join-Path $InstallDir "start.ps1"
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $PowerShellExe
    $Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartPs1`" -Port $Port"
    $Shortcut.WorkingDirectory = $InstallDir
    $Shortcut.Save()
}

Write-Host "Installation complete. Existing data, templates, uploads, and outputs were preserved."
if (-not $NoStart) {
    & (Join-Path $InstallDir "start.ps1") -Port $Port
}
