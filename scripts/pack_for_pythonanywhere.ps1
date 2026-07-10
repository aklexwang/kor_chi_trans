# PythonAnywhere 업로드용 ZIP 생성 (api 키·.env 제외)
# 사용: PowerShell에서 프로젝트 루트로 cd 후  .\scripts\pack_for_pythonanywhere.ps1

$ErrorActionPreference = "Stop"
# PSScriptRoot = .../interpreting/scripts
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not (Test-Path (Join-Path $root "main.py"))) {
  throw "main.py not found next to scripts/. Expected: interpreting/main.py"
}

$outDir = Join-Path $root "dist"
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$zip = Join-Path $outDir "interpreting_pa_$stamp.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }

$files = @(
  "main.py",
  "requirements.txt",
  ".env.example",
  ".gitignore",
  "README.md"
)

$toPack = @()
foreach ($f in $files) {
  $p = Join-Path $root $f
  if (Test-Path $p) { $toPack += (Resolve-Path $p).Path }
  else { Write-Warning "Skip (missing): $f" }
}
# 한글 파일명은 인코딩 이슈 방지: 와일드카드로 추가
Get-ChildItem -Path $root -Filter "PythonAnywhere*.md" -File -ErrorAction SilentlyContinue | ForEach-Object { $toPack += $_.FullName }
Get-ChildItem -Path $root -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "*할_일.txt" } | ForEach-Object { $toPack += $_.FullName }

if ($toPack.Count -eq 0) { throw "No files to pack." }

# 동일 경로가 두 번 들어가면 Compress-Archive가 실패할 수 있음
$toPack = $toPack | Sort-Object -Unique

# Compress-Archive: 여러 파일을 루트에 평면으로 넣음
Compress-Archive -Path $toPack -DestinationPath $zip -Force

Write-Host "OK: $zip"
Write-Host "PythonAnywhere Files -> Upload a file -> 이 zip 을 interpreting 폴더에 풀거나, zip 안의 main.py / requirements.txt 만 골라 올리기."
