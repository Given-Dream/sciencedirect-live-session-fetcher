param(
    [Parameter(Mandatory = $true)]
    [string]$InputCsv,

    [Parameter(Mandatory = $true)]
    [string]$OutDir,

    [int]$DebugPort = 9223,
    [int]$PageWaitSeconds = 8,
    [int]$DownloadTimeoutSeconds = 90,
    [int]$InterItemSleepSeconds = 7,
    [string]$SystemDownloadDir = (Join-Path $HOME "Downloads"),
    [switch]$ReuseExistingPage,
    [switch]$UseCurrentPageFirst
)

$ErrorActionPreference = "Stop"

$arguments = @(
    (Join-Path $PSScriptRoot "cnki_pdf_live_fetch.py"),
    "--input-csv", $InputCsv,
    "--out-dir", $OutDir,
    "--debug-port", $DebugPort,
    "--page-wait-seconds", $PageWaitSeconds,
    "--download-timeout-seconds", $DownloadTimeoutSeconds,
    "--inter-item-sleep-seconds", $InterItemSleepSeconds,
    "--system-download-dir", $SystemDownloadDir
)

if ($ReuseExistingPage) {
    $arguments += "--reuse-existing-page"
}
if ($UseCurrentPageFirst) {
    $arguments += "--use-current-page-first"
}

python @arguments
exit $LASTEXITCODE
