param(
    [string[]]$FilePath = @("$([Environment]::GetFolderPath('Desktop'))\合同管理工具_安装包.exe"),
    [string]$PfxPath = $env:CODESIGN_PFX,
    [string]$PfxPassword = $env:CODESIGN_PFX_PASSWORD,
    [string]$Thumbprint = $env:CODESIGN_CERT_THUMBPRINT,
    [string]$TimestampServer = $(if ($env:CODESIGN_TIMESTAMP_URL) { $env:CODESIGN_TIMESTAMP_URL } else { "http://timestamp.digicert.com" }),
    [switch]$NoTimestamp
)

$ErrorActionPreference = "Stop"

function Resolve-SigningCert {
    if ($PfxPath) {
        $resolvedPfx = (Resolve-Path -LiteralPath $PfxPath).Path
        $flags = [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::Exportable -bor
                 [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::PersistKeySet
        if ($PfxPassword) {
            return [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($resolvedPfx, $PfxPassword, $flags)
        }
        $securePassword = Read-Host "PFX password" -AsSecureString
        return [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($resolvedPfx, $securePassword, $flags)
    }

    if ($Thumbprint) {
        $cleanThumbprint = ($Thumbprint -replace '\s', '').ToUpperInvariant()
        $cert = Get-ChildItem Cert:\CurrentUser\My, Cert:\LocalMachine\My -CodeSigningCert |
            Where-Object { ($_.Thumbprint -replace '\s', '').ToUpperInvariant() -eq $cleanThumbprint } |
            Select-Object -First 1
        if (-not $cert) {
            throw "No code-signing certificate was found for thumbprint $Thumbprint."
        }
        return $cert
    }

    throw "Provide -PfxPath or -Thumbprint, or set CODESIGN_PFX / CODESIGN_CERT_THUMBPRINT."
}

function Assert-CodeSigningCert($Certificate) {
    if (-not $Certificate.HasPrivateKey) {
        throw "The certificate does not have an accessible private key."
    }

    $hasCodeSigningEku = $false
    if ($Certificate.EnhancedKeyUsageList) {
        foreach ($eku in $Certificate.EnhancedKeyUsageList) {
            if ($eku.ObjectId -eq "1.3.6.1.5.5.7.3.3" -or $eku.FriendlyName -eq "Code Signing") {
                $hasCodeSigningEku = $true
                break
            }
        }
    }

    if (-not $hasCodeSigningEku) {
        foreach ($extension in $Certificate.Extensions) {
            if ($extension.Oid.Value -eq "2.5.29.37") {
                $ekuExtension = [System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]::new($extension, $false)
                foreach ($oid in $ekuExtension.EnhancedKeyUsages) {
                    if ($oid.Value -eq "1.3.6.1.5.5.7.3.3" -or $oid.FriendlyName -eq "Code Signing") {
                        $hasCodeSigningEku = $true
                        break
                    }
                }
            }
        }
    }

    if (-not $hasCodeSigningEku) {
        throw "The certificate is not marked for Code Signing EKU."
    }
}

$cert = Resolve-SigningCert
Assert-CodeSigningCert $cert

foreach ($path in $FilePath) {
    $resolvedFile = (Resolve-Path -LiteralPath $path).Path
    $params = @{
        FilePath = $resolvedFile
        Certificate = $cert
        HashAlgorithm = "SHA256"
    }
    if (-not $NoTimestamp) {
        $params.TimestampServer = $TimestampServer
    }

    $signature = Set-AuthenticodeSignature @params
    if ($signature.Status -notin @("Valid", "UnknownError")) {
        throw ("Signing failed for {0}: {1} {2}" -f $resolvedFile, $signature.Status, $signature.StatusMessage)
    }

    $verify = Get-AuthenticodeSignature -LiteralPath $resolvedFile
    [PSCustomObject]@{
        File = $resolvedFile
        Status = $verify.Status
        Subject = $verify.SignerCertificate.Subject
        Thumbprint = $verify.SignerCertificate.Thumbprint
    } | Format-List
}
