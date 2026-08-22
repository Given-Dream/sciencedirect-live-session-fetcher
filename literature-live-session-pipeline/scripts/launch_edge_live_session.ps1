param(
    [ValidateSet("sciencedirect", "cnki", "wos", "custom")]
    [string]$Source = "sciencedirect",

    [ValidateSet("Edge", "Chrome")]
    [string]$Browser = "Edge",

    [string]$BrowserBinary = "",

    [string]$CloneUserDataDir = "",

    [string]$ProfileDirectory = "Default",

    [int]$RemoteDebuggingPort = 0,

    [string]$Url = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($BrowserBinary)) {
    if ($Browser -eq "Chrome") {
        $BrowserBinary = "C:\Program Files\Google\Chrome\Application\chrome.exe"
    } else {
        $BrowserBinary = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    }
}

if (-not (Test-Path -LiteralPath $BrowserBinary)) {
    throw "$Browser binary not found: $BrowserBinary"
}

$defaultPorts = @{
    sciencedirect = 9222
    cnki = 9223
    wos = 9224
    custom = 9225
}

$defaultUrls = @{
    sciencedirect = "https://www.sciencedirect.com/"
    cnki = "https://kns.cnki.net/"
    wos = "https://www.webofscience.com/wos/woscc/basic-search"
    custom = "about:blank"
}

if ($RemoteDebuggingPort -le 0) {
    $RemoteDebuggingPort = $defaultPorts[$Source]
}

if ([string]::IsNullOrWhiteSpace($Url)) {
    $Url = $defaultUrls[$Source]
}

if ([string]::IsNullOrWhiteSpace($CloneUserDataDir)) {
    $runtimeRoot = if ($Browser -eq "Chrome") { "runtime\\chrome_profiles" } else { "runtime\\edge_profiles" }
    $CloneUserDataDir = Join-Path (Join-Path $PSScriptRoot "..") "$runtimeRoot\$Source\User Data"
}

New-Item -ItemType Directory -Force -Path $CloneUserDataDir | Out-Null

Start-Process -FilePath $BrowserBinary -ArgumentList @(
    "--remote-debugging-port=$RemoteDebuggingPort",
    "--user-data-dir=$CloneUserDataDir",
    "--profile-directory=$ProfileDirectory",
    "--new-window",
    $Url
)

Write-Host "Opened $Browser session for source: $Source"
Write-Host "Remote debugging port: $RemoteDebuggingPort"
Write-Host "User data dir: $CloneUserDataDir"
Write-Host "Start URL: $Url"
