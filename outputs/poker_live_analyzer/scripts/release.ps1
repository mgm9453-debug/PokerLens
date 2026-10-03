param([string]$Python = 'python', [string]$SigningKeyFile = '', [switch]$UploadDraft, [switch]$Publish)
$ErrorActionPreference = 'Stop'
$Project = Split-Path $PSScriptRoot -Parent
$PythonCommand = Get-Command $Python -ErrorAction SilentlyContinue
if ($PythonCommand) { $Python = $PythonCommand.Source }
elseif (Test-Path -LiteralPath $Python) { $Python = (Resolve-Path -LiteralPath $Python).Path }
else { throw '找不到指定 Python 執行檔' }
$Product = Get-Content (Join-Path $Project 'release/product.json') -Raw | ConvertFrom-Json
$Repository = $Product.github_repository
if (($UploadDraft -or $Publish) -and -not $Repository) {
    throw '尚未設定 GitHub 儲存庫，請先將 owner/repository 填入 release/product.json；本機建置不需遠端網址'
}
if ($Publish -and -not $UploadDraft) { throw '公開發布必須同時指定 -UploadDraft，先完成草稿與資產驗證' }
Set-Location $Project
& $Python -m pytest tests packaging/tests -q
if ($LASTEXITCODE) { throw '測試失敗，停止建置與發布' }
& (Join-Path $PSScriptRoot 'build.ps1') -Python $Python
if ($Repository) { $BaseUrl = "https://github.com/$Repository/releases/download/v$($Product.version)" } else { $BaseUrl = '' }
& (Join-Path $PSScriptRoot 'publish.ps1') -Python $Python -SigningKeyFile $SigningKeyFile -BaseUrl $BaseUrl
if ($UploadDraft) {
    Set-Location $Project
    gh release create "v$($Product.version)" --repo $Repository --draft --title "PokerLens $($Product.version)" --notes-file release/notes.md
    if ($LASTEXITCODE) { throw '草稿建立失敗' }
    gh release upload "v$($Product.version)" dist/release/* --repo $Repository
    if ($LASTEXITCODE) { throw '發布資產上傳失敗，草稿保持未公開' }
    if ($Publish) {
        gh release edit "v$($Product.version)" --repo $Repository --draft=false
        if ($LASTEXITCODE) { throw '公開發布失敗' }
    }
}
