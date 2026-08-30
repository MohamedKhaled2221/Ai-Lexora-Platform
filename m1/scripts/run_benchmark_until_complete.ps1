# Drive scripts/ocr_benchmark.py to completion across PaddleOCR's native crashes.
#
# PaddleOCR terminates the whole process on some pages -- an access violation in
# native code that no Python handler can catch. Across four attempts it killed
# the benchmark between fixtures 11 and 23 every time, discarding ~40 minutes of
# completed work on each occasion.
#
# The benchmark now checkpoints after every fixture and resumes by default, so
# a crash costs one fixture rather than the whole run. This driver simply
# relaunches until the JSON reports "complete", with an attempt cap so a
# genuinely stuck fixture cannot loop forever.
#
# Usage:  powershell -File scripts/run_benchmark_until_complete.ps1 [-MaxAttempts 12]

param(
    [int]$MaxAttempts = 12,
    [int]$MaxPages = 4
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:PYTHONIOENCODING = "utf-8"
$env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK = "True"

$json = Join-Path $root "reports\ocr_engine_comparison.json"
$log  = Join-Path $root "logs\ocr_benchmark.log"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null

for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
    Write-Host "=== attempt $attempt/$MaxAttempts ==="
    & .\.venv\Scripts\python.exe scripts\ocr_benchmark.py --max-pages $MaxPages *>> $log
    $code = $LASTEXITCODE

    if (Test-Path $json) {
        $done = (Get-Content $json -Raw | ConvertFrom-Json).complete
        $n    = (Get-Content $json -Raw | ConvertFrom-Json).runs.Count
        Write-Host "    exit=$code  runs recorded=$n  complete=$done"
        if ($done) {
            Write-Host "BENCHMARK COMPLETE after $attempt attempt(s)"
            exit 0
        }
    } else {
        Write-Host "    exit=$code  (no checkpoint yet)"
    }

    # A clean exit that did not reach completion means something other than a
    # crash stopped it; relaunching would spin.
    if ($code -eq 0) {
        Write-Host "clean exit without completion -- stopping to avoid a loop"
        exit 1
    }
}

Write-Host "gave up after $MaxAttempts attempts; partial results are in $json"
exit 1
