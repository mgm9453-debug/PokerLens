param(
    [Parameter(Mandatory=$true)][string]$Version,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$Project = Split-Path $PSScriptRoot -Parent
$RepositoryRoot = Split-Path (Split-Path $Project -Parent) -Parent
Set-Location $RepositoryRoot
if ($Version -notmatch '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$') { throw '請提供例如 1.0.2 的正式版本' }
$ProductPath = Join-Path $Project 'release/product.json'
$Original = [IO.File]::ReadAllText($ProductPath)
$Product = $Original | ConvertFrom-Json
if ([version]$Version -le [version]$Product.version) { throw '新版本必須高於目前版本；已發布版本不可覆寫' }
$Tag = "v$Version"
$Origin = git remote get-url origin
if ($LASTEXITCODE -or $Origin -notmatch '^https://github\.com/mgm9453-debug/PokerLens(?:\.git)?$') { throw '遠端儲存庫不符' }
git fetch origin --tags
if ($LASTEXITCODE) { throw '無法取得遠端狀態' }
$Existing = git tag --list $Tag
if ($Existing) { throw '版本標籤已存在，不可覆寫' }
$Branch = git branch --show-current
if (-not $Branch) { throw '請先切換到開發分支' }
$Changed = @(git diff --name-only; git ls-files --others --exclude-standard)
foreach ($Path in $Changed) {
    if ($Path -notmatch '^(outputs/poker_live_analyzer/|\.github/|README\.md$|\.gitignore$)') { throw "發現專案以外的修改，請先處理：$Path" }
}
if (-not (Test-Path (Join-Path $Project 'release/notes.md'))) { throw '缺少本次更新說明' }
$Product.version = $Version
[IO.File]::WriteAllText($ProductPath, ($Product | ConvertTo-Json -Depth 10) + "`n", [Text.UTF8Encoding]::new($false))
try {
    Set-Location $Project
    & $Python -m pytest tests packaging/tests -q
    if ($LASTEXITCODE) { throw '測試失敗' }
    & (Join-Path $PSScriptRoot 'build.ps1') -Python $Python
    Set-Location $RepositoryRoot
    git add -- .github .gitignore README.md outputs/poker_live_analyzer
    if ($LASTEXITCODE) { throw '準備提交失敗' }
    git commit -m "發布 $Tag"
    if ($LASTEXITCODE) { throw '提交失敗' }
    git push origin HEAD:main
    if ($LASTEXITCODE) { throw '推送失敗，保留本機提交；請處理遠端差異後重試，勿強制推送' }
    git tag -a $Tag -m "PokerLens $Tag"
    if ($LASTEXITCODE) { throw '建立標籤失敗' }
    git push origin $Tag
    if ($LASTEXITCODE) { throw '推送標籤失敗，可直接重試 git push origin 此版本標籤' }
    Write-Host "已送出 $Tag，請到 GitHub Actions 確認建置與發布結果。"
} finally {
    Set-Location $RepositoryRoot
}
