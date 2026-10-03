param([switch]$SmokeTest)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$localPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$preparedPython = Join-Path $PSScriptRoot '..\..\work\venv\Scripts\python.exe'
if (Test-Path -LiteralPath $preparedPython) {
    if ($SmokeTest) { & $preparedPython app.py --smoke-test }
    else { & $preparedPython app.py }
    exit $LASTEXITCODE
}
if (-not (Test-Path -LiteralPath $localPython)) {
    py -3.14 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw '建立環境失敗，需要 Python 3.14' }
    & $localPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw '安裝依賴失敗' }
}
if ($SmokeTest) { & $localPython app.py --smoke-test }
else { & $localPython app.py }
