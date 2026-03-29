param(
    [Parameter(Mandatory = $true)]
    [string]$InputCsv,

    [Parameter(Mandatory = $true)]
    [string]$OutDir,

    [string]$PythonExe = "python",

    [string]$ScriptPath = "",

    [int]$DebugPort = 9222,

    [int]$PageWaitSeconds = 8,

    [int]$InterItemSleepSeconds = 5,

    [int]$Limit = 0
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ScriptPath)) {
    $ScriptPath = Join-Path $PSScriptRoot "devtools_sciencedirect_serial_fetch.py"
}

if (-not (Test-Path -LiteralPath $InputCsv)) {
    throw "Input CSV not found: $InputCsv"
}

if (-not (Test-Path -LiteralPath $ScriptPath)) {
    throw "Script not found: $ScriptPath"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$args = @(
    $ScriptPath,
    "--input-csv", $InputCsv,
    "--out-dir", $OutDir,
    "--debug-port", $DebugPort,
    "--page-wait-seconds", $PageWaitSeconds,
    "--inter-item-sleep-seconds", $InterItemSleepSeconds
)

if ($Limit -gt 0) {
    $args += @("--limit", $Limit)
}

& $PythonExe @args

Write-Host "Done. Output directory: $OutDir"
