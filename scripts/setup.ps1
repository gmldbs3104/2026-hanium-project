<#
.SYNOPSIS
    한이음 프로젝트 개발 환경 한 번에 세팅 (Windows).

.DESCRIPTION
    Docker 컨테이너(Postgres/Redis), 백엔드 venv + 의존성(AI 포함) + DB 마이그레이션,
    프론트 의존성까지 순서대로 설정한다. Firebase 연동(flutterfire configure)처럼
    브라우저 로그인이 필요한 대화형 단계는 자동화하지 않고 안내만 출력한다.

.USAGE
    저장소 루트에서 실행:
        powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#>

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Test-Cmd($name) {
    return $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}

Write-Host "`n=== 1. 필수 도구 확인 ===" -ForegroundColor Cyan
$missing = @()
foreach ($cmd in @("python", "flutter", "docker", "git")) {
    if (Test-Cmd $cmd) {
        Write-Host "  [OK] $cmd" -ForegroundColor Green
    } else {
        Write-Host "  [없음] $cmd" -ForegroundColor Red
        $missing += $cmd
    }
}
if ($missing.Count -gt 0) {
    Write-Host "`n먼저 아래를 설치하고 새 터미널에서 다시 실행하세요:" -ForegroundColor Yellow
    if ($missing -contains "python") { Write-Host "  Python 3.13+: https://www.python.org/downloads/" }
    if ($missing -contains "flutter") { Write-Host "  Flutter: git clone https://github.com/flutter/flutter.git -b stable C:\src\flutter (PATH에 C:\src\flutter\bin 추가)" }
    if ($missing -contains "docker") { Write-Host "  Docker Desktop: https://www.docker.com/products/docker-desktop/" }
    if ($missing -contains "git") { Write-Host "  Git: https://git-scm.com/downloads" }
    exit 1
}

Write-Host "`n=== 2. Docker 컨테이너 (Postgres, Redis) ===" -ForegroundColor Cyan
$existing = docker ps -a --format "{{.Names}}"
if ($existing -notcontains "hanium-postgres") {
    docker run --name hanium-postgres -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=password -e POSTGRES_DB=hanium_db -p 5432:5432 -d postgres:16 | Out-Null
    Write-Host "  hanium-postgres 새로 생성" -ForegroundColor Green
} else {
    docker start hanium-postgres | Out-Null
    Write-Host "  hanium-postgres 기동" -ForegroundColor Green
}
if ($existing -notcontains "hanium-redis") {
    docker run --name hanium-redis -p 6379:6379 -d redis:7 | Out-Null
    Write-Host "  hanium-redis 새로 생성" -ForegroundColor Green
} else {
    docker start hanium-redis | Out-Null
    Write-Host "  hanium-redis 기동" -ForegroundColor Green
}

Write-Host "`n=== 3. 백엔드: venv + 의존성 ===" -ForegroundColor Cyan
Set-Location "$RepoRoot\backend"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "  .env 생성됨 — FIREBASE_CREDENTIALS_PATH, SECRET_KEY 등 직접 채워야 합니다!" -ForegroundColor Yellow
}

if (-not (Test-Path "venv")) {
    python -m venv venv
}
$py = ".\venv\Scripts\python.exe"
& $py -m pip install --upgrade pip | Out-Null
& $py -m pip install -r requirements.txt

Write-Host "  craft-text-detector 설치..."
& $py -m pip install --no-deps craft-text-detector==0.4.3 | Out-Null

Write-Host "  AI 의존성(torch 등) 설치 확인 중..."
& $py -c "import torch" 2>$null
$torchOk = ($LASTEXITCODE -eq 0)

if (-not $torchOk) {
    Write-Host "  [주의] torch import 실패 — Windows 260자 경로 제한(MAX_PATH)일 가능성이 높습니다." -ForegroundColor Yellow
    Write-Host "  backend\venv의 torch 관련 패키지를 정리하고, 짧은 경로(C:\ai_venv)로 우회 설치합니다..." -ForegroundColor Yellow

    & $py -m pip uninstall -y torch torchvision numpy opencv-python-headless scipy gdown Pillow craft-text-detector 2>$null | Out-Null

    $shortVenv = "C:\ai_venv"
    if (-not (Test-Path $shortVenv)) {
        python -m venv $shortVenv
    }
    $shortPy = "$shortVenv\Scripts\python.exe"
    & $shortPy -m pip install --upgrade pip | Out-Null
    & $shortPy -m pip install -r "$RepoRoot\ai\requirements.txt"
    & $shortPy -m pip install --no-deps craft-text-detector==0.4.3
    python "$RepoRoot\scripts\patch_craft_text_detector.py" $shortVenv

    $sitePackages = "$shortVenv\Lib\site-packages"
    New-Item -ItemType Directory -Force -Path "venv\Lib\site-packages" | Out-Null
    Set-Content -Path "venv\Lib\site-packages\ai_deps.pth" -Value $sitePackages -NoNewline
    Write-Host "  연결 완료: backend\venv -> $shortVenv (venv\Lib\site-packages\ai_deps.pth)" -ForegroundColor Green

    & $py -c "import torch" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [실패] 우회 설치 후에도 torch import가 안 됩니다. 직접 확인이 필요합니다." -ForegroundColor Red
    } else {
        Write-Host "  확인됨: backend venv에서 torch import 성공" -ForegroundColor Green
    }
} else {
    python "$RepoRoot\scripts\patch_craft_text_detector.py" "venv"
}

Write-Host "  Alembic 마이그레이션..."
& ".\venv\Scripts\alembic.exe" upgrade head

Set-Location $RepoRoot

Write-Host "`n=== 4. AI 검증용 venv (ai/tests, eval 스크립트 실행용 — 선택) ===" -ForegroundColor Cyan
if (-not (Test-Path "ai\venv") -and -not (Test-Path "C:\ai_venv")) {
    python -m venv "ai\venv"
    $aiPy = "ai\venv\Scripts\python.exe"
    & $aiPy -m pip install --upgrade pip | Out-Null
    & $aiPy -m pip install -r "ai\requirements.txt"
    & $aiPy -m pip install --no-deps craft-text-detector==0.4.3
    python "scripts\patch_craft_text_detector.py" "ai\venv"
    Write-Host "  생성됨: ai\venv" -ForegroundColor Green
} elseif (Test-Path "C:\ai_venv") {
    Write-Host "  이미 C:\ai_venv를 만들어서 재사용 중입니다. 검증 실행 예시:" -ForegroundColor Gray
    Write-Host "    C:\ai_venv\Scripts\python.exe -m pytest ai\tests -q"
} else {
    Write-Host "  이미 존재함: ai\venv" -ForegroundColor Gray
}

Write-Host "`n=== 5. 프론트엔드 ===" -ForegroundColor Cyan
Set-Location "$RepoRoot\frontend"
flutter pub get
if (-not (Test-Path "lib\firebase_options.dart")) {
    Write-Host "  [수동 작업 필요] Firebase 연동이 안 되어 있습니다:" -ForegroundColor Yellow
    Write-Host "    npm install -g firebase-tools"
    Write-Host "    dart pub global activate flutterfire_cli   (그 후 %LOCALAPPDATA%\Pub\Cache\bin을 PATH에 추가)"
    Write-Host "    firebase login"
    Write-Host "    flutterfire configure   (프로젝트: hanium-handwriting, 플랫폼: 최소 web 체크)"
} else {
    Write-Host "  firebase_options.dart 이미 있음" -ForegroundColor Gray
}
Set-Location $RepoRoot

Write-Host "`n=== 완료 ===" -ForegroundColor Green
Write-Host "백엔드 실행: cd backend; venv\Scripts\activate; uvicorn app.main:app --reload --port 8000"
Write-Host "프론트 실행: cd frontend; flutter run -d chrome --web-port=5000"
Write-Host "AI 자가 검증: (ai\venv 또는 C:\ai_venv)\Scripts\python.exe -m pytest ai\tests -q"
