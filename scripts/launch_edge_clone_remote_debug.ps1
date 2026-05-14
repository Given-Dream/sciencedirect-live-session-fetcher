param(
    [string]$EdgeBinary = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    [string]$CloneUserDataDir = "",
    [string]$ProfileDirectory = "Default",
    [int]$RemoteDebuggingPort = 9222,
    [string]$Url = "https://www.sciencedirect.com/",
    [switch]$DirectConnection,
    [switch]$DisableExtensions,
    [switch]$OneShotProfile
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $EdgeBinary)) {
    throw "Edge binary not found: $EdgeBinary"
}

if ($OneShotProfile -and [string]::IsNullOrWhiteSpace($CloneUserDataDir)) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $CloneUserDataDir = Join-Path (Join-Path $PSScriptRoot "..") "runtime\edge_profile_once_$stamp\User Data"
} elseif ([string]::IsNullOrWhiteSpace($CloneUserDataDir)) {
    $CloneUserDataDir = Join-Path (Join-Path $PSScriptRoot "..") "runtime\edge_profile_clone\User Data"
}

New-Item -ItemType Directory -Force -Path $CloneUserDataDir | Out-Null

$edgeArgs = @(
    "--remote-debugging-port=$RemoteDebuggingPort",
    "--user-data-dir=$CloneUserDataDir",
    "--profile-directory=$ProfileDirectory",
    "--new-window"
)

if ($DirectConnection) {
    $edgeArgs += @(
        "--no-proxy-server",
        "--proxy-bypass-list=*"
    )
}

if ($DisableExtensions) {
    $edgeArgs += "--disable-extensions"
}

$edgeArgs += $Url

Start-Process -FilePath $EdgeBinary -ArgumentList $edgeArgs

Write-Host "Opened Edge window with remote debugging on port $RemoteDebuggingPort."
Write-Host "User data dir: $CloneUserDataDir"
if ($DirectConnection) {
    Write-Host "Proxy mode: direct connection for this Edge process only (--no-proxy-server)."
}
if ($DisableExtensions) {
    Write-Host "Extensions: disabled."
}
if ($OneShotProfile) {
    Write-Host "Profile mode: one-shot profile. Close this Edge window to end the session."
}
