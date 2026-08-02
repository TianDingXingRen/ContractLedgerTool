param(
    [string[]]$FilePath = @("$([Environment]::GetFolderPath('Desktop'))\合同管理工具_安装包.exe"),
    [string]$PfxPath = $env:CODESIGN_PFX,
    [string]$PfxPassword = $env:CODESIGN_PFX_PASSWORD,
    [string]$Thumbprint = $env:CODESIGN_CERT_THUMBPRINT,
    [string]$TimestampServer = $(if ($env:CODESIGN_TIMESTAMP_URL) { $env:CODESIGN_TIMESTAMP_URL } else { "http://timestamp.digicert.com" }),
    [string]$SignToolPath = $env:SIGNTOOL_PATH,
    [string]$Description = "合同管理工具",
    [switch]$NoTimestamp
)

$ErrorActionPreference = "Stop"

function Resolve-SignTool {
    if ($SignToolPath) {
        return (Resolve-Path -LiteralPath $SignToolPath).Path
    }

    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $kitsRoot = Join-Path "${env:ProgramFiles(x86)}" "Windows Kits\10\bin"
    if (Test-Path -LiteralPath $kitsRoot) {
        $candidate = Get-ChildItem -Path $kitsRoot -Filter signtool.exe -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($candidate) {
            return $candidate.FullName
        }
    }

    throw "SignTool.exe was not found. Install the Windows SDK or set SIGNTOOL_PATH."
}

function Resolve-CertificateArguments {
    if ($PfxPath -and $Thumbprint) {
        throw "Provide only one signing identity: PFX or certificate thumbprint."
    }

    if ($PfxPath) {
        $resolvedPfx = (Resolve-Path -LiteralPath $PfxPath).Path
        if (-not $PfxPassword) {
            throw "CODESIGN_PFX_PASSWORD is required when signing with a PFX file."
        }
        return @("/f", $resolvedPfx, "/p", $PfxPassword)
    }

    if ($Thumbprint) {
        $cleanThumbprint = ($Thumbprint -replace '\s', '').ToUpperInvariant()
        $currentUserCert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
            Where-Object { ($_.Thumbprint -replace '\s', '').ToUpperInvariant() -eq $cleanThumbprint } |
            Select-Object -First 1
        $localMachineCert = Get-ChildItem Cert:\LocalMachine\My -CodeSigningCert |
            Where-Object { ($_.Thumbprint -replace '\s', '').ToUpperInvariant() -eq $cleanThumbprint } |
            Select-Object -First 1
        $cert = if ($currentUserCert) { $currentUserCert } else { $localMachineCert }
        if (-not $cert) {
            throw "No code-signing certificate was found for thumbprint $Thumbprint."
        }
        if (-not $cert.HasPrivateKey) {
            throw "The code-signing certificate does not have an accessible private key."
        }

        $arguments = @("/sha1", $cleanThumbprint)
        if (-not $currentUserCert -and $localMachineCert) {
            $arguments += "/sm"
        }
        return $arguments
    }

    throw "Provide -PfxPath or -Thumbprint, or set CODESIGN_PFX / CODESIGN_CERT_THUMBPRINT."
}

$signTool = Resolve-SignTool
$certificateArguments = Resolve-CertificateArguments

foreach ($path in $FilePath) {
    $resolvedFile = (Resolve-Path -LiteralPath $path).Path
    $signArguments = @(
        "sign",
        "/fd", "SHA256",
        "/d", $Description
    )
    if (-not $NoTimestamp) {
        $signArguments += @("/tr", $TimestampServer, "/td", "SHA256")
    }
    $signArguments += $certificateArguments
    $signArguments += $resolvedFile

    & $signTool @signArguments
    if ($LASTEXITCODE -ne 0) {
        throw "SignTool failed to sign $resolvedFile (exit code $LASTEXITCODE)."
    }

    & $signTool verify /pa /all /v $resolvedFile
    if ($LASTEXITCODE -ne 0) {
        throw "SignTool verification failed for $resolvedFile (exit code $LASTEXITCODE)."
    }

    $signature = Get-AuthenticodeSignature -LiteralPath $resolvedFile
    if ($signature.Status -ne "Valid") {
        throw "Authenticode verification failed for $resolvedFile`: $($signature.Status) $($signature.StatusMessage)"
    }
    if (-not $NoTimestamp -and -not $signature.TimeStamperCertificate) {
        throw "The signature for $resolvedFile does not contain a trusted timestamp."
    }

    [PSCustomObject]@{
        File = $resolvedFile
        Status = $signature.Status
        Subject = $signature.SignerCertificate.Subject
        Thumbprint = $signature.SignerCertificate.Thumbprint
        TimestampSubject = if ($signature.TimeStamperCertificate) {
            $signature.TimeStamperCertificate.Subject
        } else {
            "Not requested"
        }
    } | Format-List
}
