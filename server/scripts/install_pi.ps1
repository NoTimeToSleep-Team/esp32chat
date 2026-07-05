param(
    [Parameter(Mandatory = $true)]
    [string]$Host,

    [string]$User = "pi",

    [int]$Port = 22,

    [string]$SourcePath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,

    [string]$RemotePath = "/tmp/local-chat-server-deploy",

    [string]$IdentityFile = "",

    [switch]$SkipSudo
)

$ErrorActionPreference = "Stop"

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' is not available in PATH."
    }
}

Assert-Command "ssh"
Assert-Command "scp"
Assert-Command "tar"

if (-not (Test-Path $SourcePath)) {
    throw "SourcePath does not exist: $SourcePath"
}

$target = "$User@$Host"
$timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
$archive = Join-Path $env:TEMP ("local-chat-server-{0}.tar.gz" -f $timestamp)
$remoteArchive = "$RemotePath.tar.gz"

Write-Host "[install_pi.ps1] Building archive: $archive"
& tar -czf $archive -C $SourcePath .
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create archive"
}

$sshArgs = @("-p", $Port.ToString())
$scpArgs = @("-P", $Port.ToString())
if ($IdentityFile) {
    $sshArgs += @("-i", $IdentityFile)
    $scpArgs += @("-i", $IdentityFile)
}

Write-Host "[install_pi.ps1] Uploading archive to $target"
& scp @scpArgs $archive ("{0}:{1}" -f $target, $remoteArchive)
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upload archive"
}

$installCommand = if ($SkipSudo) {
    "bash '$RemotePath/scripts/install_pi.sh'"
} else {
    "sudo bash '$RemotePath/scripts/install_pi.sh'"
}

$remoteCommand = @(
    "set -euo pipefail",
    "rm -rf '$RemotePath'",
    "mkdir -p '$RemotePath'",
    "tar -xzf '$remoteArchive' -C '$RemotePath'",
    $installCommand
) -join "; "

Write-Host "[install_pi.ps1] Running remote install script"
& ssh @sshArgs $target $remoteCommand
if ($LASTEXITCODE -ne 0) {
    throw "Remote install failed"
}

Write-Host "[install_pi.ps1] Verifying remote health"
& ssh @sshArgs $target "curl -fsS http://127.0.0.1/health"
if ($LASTEXITCODE -ne 0) {
    throw "Remote health check failed"
}

Remove-Item -Force $archive
Write-Host "[install_pi.ps1] Done"
