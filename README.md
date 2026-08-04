# 2026 한이음 드림업 - AI 손글씨 교정 플랫폼

## 프로젝트 구조
- `backend/` - FastAPI 기반 AI 추론 서버
- `frontend/` - Flutter 앱 (추후 추가)

## Backend 로컬 실행 방법

### 1. 환경변수 설정
cd backend

cp .env.example .env
# .env 파일을 열어서 실제 값 입력

### 2. 가상환경 및 패키지 설치
python -m venv venv

source venv/bin/activate  # Windows: venv\Scripts\activate

(끄려면 deactivate)

pip install -r requirements.txt

### 3. DB 마이그레이션
alembic upgrade head

### 4. 서버 실행
uvicorn app.main:app --reload --port 8000

http://localhost:8000/docs

## 브랜치 전략
- main: 배포용
- dev: 통합 개발
- feature/*: 기능 개발

### Frontend Flutter 실행 방법

### 1. 처음 한 번만
Flutter SDK 설치 → 환경변수 Path에 flutter\bin 추가
cd frontend

flutter pub get

### test때마다
기본으로 DB·Redis, backend 가상환경 켜기

cd frontend

flutter run -d chrome

http://127.0.0.1:8080
