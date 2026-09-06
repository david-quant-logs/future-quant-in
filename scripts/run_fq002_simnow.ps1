# FQ-002 SimNow daily job. Clears HTTP proxy so CTP TCP is not sent through Clash.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
foreach ($name in @("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "CTP_CONFIG")) {
    Remove-Item "Env:$name" -ErrorAction SilentlyContinue
}
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) {
    Write-Error "python not on PATH"
    exit 3
}
& $py "$Root\run_fq002_ctp.py" --refresh --wait 18
exit $LASTEXITCODE
