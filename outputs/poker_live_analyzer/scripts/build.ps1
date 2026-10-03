param([string]$Python = 'python', [switch]$SkipInstaller, [string]$ISCC = '')
$ErrorActionPreference = 'Stop'
$Project = Split-Path $PSScriptRoot -Parent
$PythonCommand = Get-Command $Python -ErrorAction SilentlyContinue
if ($PythonCommand) { $Python = $PythonCommand.Source }
elseif (Test-Path -LiteralPath $Python) { $Python = (Resolve-Path -LiteralPath $Python).Path }
else { throw '找不到指定 Python 執行檔' }
Set-Location $Project
$Product = Get-Content release/product.json -Raw | ConvertFrom-Json
$Version = $Product.version
& $Python packaging/prepare_build.py
if ($LASTEXITCODE) { throw '準備版本資訊失敗' }
foreach ($Entry in @('app', 'launcher', 'updater')) {
    $env:POKERLENS_ENTRY = $Entry
    & $Python -m PyInstaller --noconfirm --clean --distpath dist/frozen --workpath "build/$Entry" packaging/PokerLens.spec
    if ($LASTEXITCODE) { throw "打包失敗：$Entry" }
}
& $Python packaging/prepare_build.py --assemble
if ($LASTEXITCODE) { throw '組裝安裝目錄失敗' }
if (-not $SkipInstaller) {
    if (-not $ISCC) {
        $Candidates = @("${env:ProgramFiles(x86)}/Inno Setup 6/ISCC.exe", "$env:LOCALAPPDATA/Programs/Inno Setup 6/ISCC.exe")
        $ISCC = $Candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (-not $ISCC) { throw '找不到 Inno Setup 編譯器；請提供 -ISCC 路徑' }
    & $ISCC "/DProductVersion=$Version" "/DProductPublisher=$($Product.publisher)" "/DProductAppId=$($Product.app_id)" packaging/PokerLens.iss
    if ($LASTEXITCODE) { throw '安裝程式編譯失敗' }
}
