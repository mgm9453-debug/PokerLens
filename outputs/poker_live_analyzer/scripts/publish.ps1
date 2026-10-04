param([string]$Python = 'python', [string]$BaseUrl = '', [string]$PreviousManifest = '', [string]$SigningKeyFile = '', [switch]$Unsigned)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$Project = Split-Path $PSScriptRoot -Parent
$PythonCommand = Get-Command $Python -ErrorAction SilentlyContinue
if ($PythonCommand) { $Python = $PythonCommand.Source }
elseif (Test-Path -LiteralPath $Python) { $Python = (Resolve-Path -LiteralPath $Python).Path }
else { throw '找不到指定 Python 執行檔' }
Set-Location $Project
if (-not $BaseUrl -and -not $Unsigned) {
    $Product = Get-Content release/product.json -Raw | ConvertFrom-Json
    if (-not $Product.github_repository) { throw '正式簽章需設定 GitHub 儲存庫或提供 -BaseUrl；未簽署測試可用 -Unsigned' }
    $BaseUrl = "https://github.com/$($Product.github_repository)/releases/download/v$($Product.version)"
}
$Arguments = @('scripts/package_updates.py', '--base-url', $BaseUrl)
if ($PreviousManifest) { $Arguments += @('--previous-manifest', $PreviousManifest) }
& $Python @Arguments
if ($LASTEXITCODE) { throw '更新元件封裝失敗' }
if (-not $Unsigned) {
    $SigningArguments = @('scripts/sign_release.py', '--manifest', 'dist/release/manifest.json')
    if (-not $env:POKERLENS_SIGNING_KEY) {
        if (-not $SigningKeyFile) { $SigningKeyFile = "$env:LOCALAPPDATA/PokerLensRelease/signing.key" }
        if (Test-Path -LiteralPath $SigningKeyFile) { $SigningArguments += @('--key-file', $SigningKeyFile) }
    }
    & $Python @SigningArguments
    if ($LASTEXITCODE) { throw '發布簽章失敗' }
    & $Python scripts/verify_release.py --manifest dist/release/manifest.json
    if ($LASTEXITCODE) { throw '發布驗證失敗' }
}
$Checksums = Get-ChildItem dist/release -File | Where-Object { $_.Name -ne 'SHA256SUMS.txt' } | Sort-Object Name | ForEach-Object {
    "$((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower())  $($_.Name)"
}
[System.IO.File]::WriteAllLines((Join-Path $Project 'dist/release/SHA256SUMS.txt'), [string[]]$Checksums, [System.Text.UTF8Encoding]::new($false))
