$ErrorActionPreference = "SilentlyContinue"

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppExe = Join-Path $AppDir "ContractLedgerTool.exe"
$AppPath = Join-Path $AppDir "app.py"
$escapedAppPath = $AppPath.Replace("\", "\\")

$procs = Get-CimInstance Win32_Process |
    Where-Object {
        ($_.ExecutablePath -eq $AppExe) -or
        (
            $_.ExecutablePath -like "*python*" -and
            ($_.CommandLine -like "*$AppPath*" -or $_.CommandLine -like "*$escapedAppPath*")
        )
    }

foreach ($proc in $procs) {
    Stop-Process -Id $proc.ProcessId -Force
}

Write-Host "Contract tool service stopped."
