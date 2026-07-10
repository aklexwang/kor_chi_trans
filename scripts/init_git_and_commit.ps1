# Git이 설치된 뒤 한 번만: 저장소 생성 + 첫 커밋(비밀 제외)
# .env 는 .gitignore에 있으므로 커밋되지 않습니다.

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) {
  throw "git 이 PATH에 없습니다. https://git-scm.com/download/win 설치 후 PowerShell을 다시 열고 이 스크립트를 다시 실행하세요."
}

if (-not (Test-Path ".git")) {
  git init
  git add main.py requirements.txt .gitignore .env.example README.md scripts/
  Get-ChildItem -Filter "PythonAnywhere*.md" -File | ForEach-Object { git add -- "$($_.Name)" }
  Get-ChildItem -File | Where-Object { $_.Name -like "*할_일.txt" } | ForEach-Object { git add -- "$($_.Name)" }
  if (Test-Path "GIT_초보자_가이드.md") { git add -- "GIT_초보자_가이드.md" }
  if (Test-Path "관련정보.txt") { git add -- "관련정보.txt" }
  git commit -m "Initial import: 텔레그램 한중 통역 봇"
} else {
  Write-Host "이미 .git이 있습니다. 수동으로 git add / commit 하세요."
}

Write-Host "다음(선택): GitHub에 새 repo 만들고: git remote add origin ... / git push -u origin main"
