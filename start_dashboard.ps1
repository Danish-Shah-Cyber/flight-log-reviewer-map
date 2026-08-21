$ErrorActionPreference = "Stop"
$BundledPython = "C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Vendor = Join-Path $PSScriptRoot "work\vendor"

Set-Location $PSScriptRoot

if (Test-Path $Vendor) {
    $env:PYTHONPATH = $Vendor
}

if (Test-Path $BundledPython) {
    & $BundledPython -m flightrecorder dashboard
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    python -m flightrecorder dashboard
} else {
    throw "Python was not found. Install Python 3.11+ and pymavlink."
}
