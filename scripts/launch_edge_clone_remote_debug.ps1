param(
    [string]$EdgeBinary = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    [string]$CloneUserDataDir = "",
    [string]$ProfileDirectory = "Default",
    [int]$RemoteDebuggingPort = 9222,
    [string]$Url = "https://www.sciencedirect.com/"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $EdgeBinary)) {
    throw "Edge binary not found: $EdgeBinary"
}

if ([string]::IsNullOrWhiteSpace($CloneUserDataDir)) {
    $CloneUserDataDir = Join-Path (Join-Path $PSScriptRoot "..") "runtime\edge_profile_clone\User Data"
}

New-Item -ItemType Directory -Force -Path $CloneUserDataDir | Out-Null

Start-Process -FilePath $EdgeBinary -ArgumentList @(
    "--remote-debugging-port=$RemoteDebuggingPort",
    "--user-data-dir=$CloneUserDataDir",
    "--profile-directory=$ProfileDirectory",
    "--new-window",
    $Url
)

Write-Host "Opened Edge window with remote debugging on port $RemoteDebuggingPort."
Write-Host "User data dir: $CloneUserDataDir"
