#!/usr/bin/env bash
# 한이음 프로젝트 개발 환경 한 번에 세팅 (Mac / Linux / WSL)
#
# 사용법: 저장소 루트에서 실행
#   bash scripts/setup.sh
#
# Windows의 260자 경로 제한(scripts/setup.ps1 참고) 문제는 Mac/Linux에는 없으므로
# 별도 우회 없이 각 venv에 그대로 설치한다.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo ""
echo "=== 1. 필수 도구 확인 ==="
missing=()
for cmd in python3 flutter docker git; do
  if command -v "$cmd" &>/dev/null; then
    echo "  [OK] $cmd"
  else
    echo "  [없음] $cmd"
    missing+=("$cmd")
  fi
done
if [ ${#missing[@]} -gt 0 ]; then
  echo ""
  echo "먼저 아래를 설치하고 다시 실행하세요:"
  for m in "${missing[@]}"; do
    case "$m" in
      python3) echo "  Python 3.13+: https://www.python.org/downloads/" ;;
      flutter) echo "  Flutter: https://docs.flutter.dev/get-started/install" ;;
      docker)  echo "  Docker: https://www.docker.com/products/docker-desktop/" ;;
      git)     echo "  Git: https://git-scm.com/downloads" ;;
    esac
  done
  exit 1
fi

echo ""
echo "=== 2. Docker 컨테이너 (Postgres, Redis) ==="
if docker ps -a --format '{{.Names}}' | grep -qx hanium-postgres; then
  docker start hanium-postgres >/dev/null
  echo "  hanium-postgres 기동"
else
  docker run --name hanium-postgres -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=password -e POSTGRES_DB=hanium_db -p 5432:5432 -d postgres:16 >/dev/null
  echo "  hanium-postgres 새로 생성"
fi
if docker ps -a --format '{{.Names}}' | grep -qx hanium-redis; then
  docker start hanium-redis >/dev/null
  echo "  hanium-redis 기동"
else
  docker run --name hanium-redis -p 6379:6379 -d redis:7 >/dev/null
  echo "  hanium-redis 새로 생성"
fi

echo ""
echo "=== 3. 백엔드: venv + 의존성 (AI 포함) ==="
cd "$REPO_ROOT/backend"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "  .env 생성됨 — FIREBASE_CREDENTIALS_PATH, SECRET_KEY 등 직접 채워야 합니다!"
fi

if [ ! -d venv ]; then
  python3 -m venv venv
fi
PY="./venv/bin/python"
"$PY" -m pip install --upgrade pip >/dev/null
"$PY" -m pip install -r requirements.txt
echo "  craft-text-detector 설치..."
"$PY" -m pip install --no-deps craft-text-detector==0.4.3
python3 "$REPO_ROOT/scripts/patch_craft_text_detector.py" venv

echo "  Alembic 마이그레이션..."
"./venv/bin/alembic" upgrade head

cd "$REPO_ROOT"

echo ""
echo "=== 4. AI 검증용 venv (ai/tests, eval 스크립트 실행용 — 선택) ==="
if [ ! -d ai/venv ]; then
  python3 -m venv ai/venv
  AI_PY="ai/venv/bin/python"
  "$AI_PY" -m pip install --upgrade pip >/dev/null
  "$AI_PY" -m pip install -r ai/requirements.txt
  "$AI_PY" -m pip install --no-deps craft-text-detector==0.4.3
  python3 scripts/patch_craft_text_detector.py ai/venv
  echo "  생성됨: ai/venv"
else
  echo "  이미 존재함: ai/venv"
fi

echo ""
echo "=== 5. 프론트엔드 ==="
cd "$REPO_ROOT/frontend"
flutter pub get
if [ ! -f lib/firebase_options.dart ]; then
  echo "  [수동 작업 필요] Firebase 연동이 안 되어 있습니다:"
  echo "    npm install -g firebase-tools"
  echo "    dart pub global activate flutterfire_cli"
  echo "    firebase login"
  echo "    flutterfire configure   (프로젝트: hanium-handwriting, 플랫폼: 최소 web 체크)"
else
  echo "  firebase_options.dart 이미 있음"
fi
cd "$REPO_ROOT"

echo ""
echo "=== 완료 ==="
echo "백엔드 실행: cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8000"
echo "프론트 실행: cd frontend && flutter run -d chrome --web-port=5000"
echo "AI 자가 검증: ai/venv/bin/python -m pytest ai/tests -q"
