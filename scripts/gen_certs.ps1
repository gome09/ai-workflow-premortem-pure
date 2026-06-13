param(
    [string]$CertDir = (Join-Path $PSScriptRoot "..\nginx\certs")
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $CertDir | Out-Null
$resolvedDir = (Resolve-Path $CertDir).Path
$certPath = Join-Path $resolvedDir "server.crt"
$keyPath = Join-Path $resolvedDir "server.key"

if ((Test-Path $certPath) -and (Test-Path $keyPath)) {
    Write-Host "[skip] Certificates already exist at $resolvedDir"
    exit 0
}
if (Get-Command openssl -ErrorAction SilentlyContinue) {
    & openssl req -x509 -newkey rsa:2048 -nodes `
        -keyout $keyPath `
        -out $certPath `
        -days 3650 `
        -subj "/CN=localhost" `
        -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
    Write-Host "[gen] server.crt + server.key written to $resolvedDir"
    Write-Host "      Self-signed cert valid for 3650 days."
    Write-Host "      Import server.crt into your browser/OS trust store to remove warnings."
    exit 0
}

throw "OpenSSL is required to generate nginx/certs/server.crt and server.key. Install Git for Windows or another OpenSSL distribution, then rerun scripts/gen_certs.ps1."
