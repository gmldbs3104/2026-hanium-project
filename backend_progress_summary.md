# AI 손글씨 교정 플랫폼 — 백엔드 진행 현황 정리

> 작성 기준일: 2026-06-27
> 용도: 팀 공유 / 작업 인계 / 다음 세션 컨텍스트 제공용

---

## 1. 프로젝트 기본 정보

- **프로젝트명**: AI 손글씨 교정 플랫폼 (2026 한이음 드림업)
- **백엔드 스택**: FastAPI + Uvicorn (async), SQLAlchemy 2.0 (AsyncSession), PostgreSQL (Docker), Alembic, Firebase Admin SDK
- **개발 환경**: Windows + Git Bash(MINGW64), Python 3.13, venv
- **DB**: Docker 컨테이너로 PostgreSQL 16 실행 (컨테이너명 `hanium-postgres`)
- **인증**: Firebase Authentication (ID Token 검증 방식)
- **기준 문서**: SFR(System Functional Requirement) 명세서 — SFR-001~SFR-009

---

## 2. 지금까지 완료된 작업

### 2-1. 프로젝트 셋업
- [x] venv 가상환경 구성
- [x] FastAPI + Uvicorn 기본 프로젝트 구조 (`app/api/v1/routes`, `core`, `db`, `models`, `schemas`, `services`)
- [x] Docker로 PostgreSQL 컨테이너 실행
  ```bash
  docker run --name hanium-postgres -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=password -e POSTGRES_DB=hanium_db -p 5432:5432 -d postgres:16
  ```
- [x] **Async 방식으로 전체 아키�처 결정** (sync → async 전환 완료)
  - `DATABASE_URL=postgresql+asyncpg://...`
  - `db/session.py`: `create_async_engine`, `AsyncSession`, `async_sessionmaker`
  - 모든 라우트 함수 `async def`, `db.query()` → `await db.execute(select(...))`
- [x] Alembic 마이그레이션 설정 (`alembic/env.py`에서 asyncpg → psycopg2 URL로 변환해서 동기 마이그레이션 처리)

### 2-2. DB 스키마 (마이그레이션 적용 완료)
| 테이블 | 설명 |
|---|---|
| `users` | SFR-001, Firebase 사용자 정보 |
| `canvas_analysis_results` | SFR-005C 캔버스 분석 결과 |
| `image_analysis_results` | SFR-005I 이미지 분석 결과 (테이블만 존재, 로직 미구현) |
| `stroke_standards` | SFR-005C 표준 획순 DB (테스트용 1글자만 시드, 11,172자 미완성) |

### 2-3. SFR-001 — 사용자 인증
- [x] Firebase Admin SDK 연동 (`core/firebase.py`)
- [x] `POST /api/v1/auth/login` — ID Token 검증 → 신규 유저 생성 / 기존 유저 `last_login_at` 갱신
- [x] `core/deps.py`의 `get_current_user` 인증 dependency
- [x] 실제 Firebase 테스트 계정으로 end-to-end 동작 검증 완료

### 2-4. SFR-003C — 캔버스 손글씨 입력 및 획 수집
- [x] `POST /api/v1/canvas/analyze` — 획 좌표 시퀀스 입력 → `canvas_session_id` 발급
- [x] 인메모리 세션 캐시 (`services/session_cache.py`, TTL 10분) — *추후 Redis 교체 필요*

### 2-5. SFR-004C — 획 그룹핑 및 문자 단위 분할
- [x] `POST /api/v1/canvas/{session_id}/group`
- [x] **규칙 기반 1차 그룹핑만 구현** (거리·시간 임계값) — *LSTM 2차 분류는 미구현 (placeholder)*
- [x] 신뢰도 점수 산출 및 저신뢰 플래그 마킹

### 2-6. SFR-005C — 획순/자간/크기 분석
- [x] `POST /api/v1/canvas/{session_id}/analyze-detail` (인증 필요)
- [x] 획순/자간/크기 분석 로직 — **모두 임시 placeholder 로직** (실제 LSTM 모델 없음, stroke 개수 비교 등 단순 휴리스틱)
- [x] 종합 점수 산출 후 `canvas_analysis_results` 테이블에 저장 완료

### 2-7. SFR-007 — 교정 피드백 생성 (캔버스 모드만)
- [x] `GET /api/v1/canvas/{session_id}/feedback`
- [x] 한국어 피드백 메시지 + severity(good/warning/error) + 성취 메시지 생성
- [x] *i18n 구조는 미적용 (지금은 한국어 하드코딩, 추후 다국어 확장 시 구조 분리 필요)*

### 2-8. 테스트 도구
- [x] `test_canvas_pipeline.py` — Firebase 계정 생성 → 로그인 → 캔버스 입력 → 그룹핑 → 분석 → 피드백까지 6단계 자동 테스트 스크립트 작성 완료, 정상 동작 확인

---

## 3. 주요 트러블슈팅 기록

| 증상 | 원인 | 해결 |
|---|---|---|
| `psycopg2-binary` 빌드 실패 (`pg_config not found`) | Python 3.13용 prebuilt wheel 없음 (버전 2.9.9 기준) | `psycopg2-binary==2.9.10`으로 버전 업 |
| `asyncpg` 빌드 실패 | 동일하게 Python 3.13 wheel 미지원 (0.29.0 기준) | `asyncpg==0.30.0`으로 버전 업 |
| `NoSuchModuleError: driver` (Alembic) | `alembic/env.py`를 async 환경에 맞게 커스터마이징 안 하고 기본 템플릿 그대로 실행 | `env.py`에서 `DATABASE_URL`을 psycopg2 URL로 변환하는 코드 추가 |
| `relation "stroke_standards" does not exist` | 새 모델(`stroke_standard.py`)을 `alembic/env.py`에서 import 안 해서 autogenerate가 감지 못함 | `from app.models import ..., stroke_standard` 추가 후 재생성 |
| `Can't locate revision identified by 'd6c4fb8dd904'` | 빈 마이그레이션 파일을 수동 삭제하면서 DB의 `alembic_version` 기록과 실제 파일 히스토리가 불일치 | `DELETE FROM alembic_version` + `alembic stamp head`로 히스토리 강제 동기화 |
| `ModuleNotFoundError: No module named 'greenlet'` | SQLAlchemy async 엔진의 내부 의존성이 `requirements.txt`에서 누락 | `pip install greenlet` 추가 |
| `FileNotFoundError: firebase-credentials.json` | Firebase 서비스 계정 키 파일을 다운로드만 하고 정확한 경로/파일명으로 옮기지 않음 | 파일을 `backend/` 루트로 이동, `.env`의 경로와 파일명 일치시킴 |
| `AttributeError: module 'handwriting' has no attribute 'router'` | 라우트 파일을 빈 채로 두고 `main.py`에서 import만 함 | 각 라우트 파일에 최소 `router = APIRouter()` 정의 |
| `500 Internal Server Error` (인증 후) | `INVALID_LOGIN_CREDENTIALS` — 가입 정보 불일치 / idToken과 refreshToken 혼동 (`AMf-...`로 시작하는 건 refreshToken, `eyJ...`가 idToken) | 정확한 idToken 필드 값 사용, 필요 시 새 테스트 계정 생성 |
| `404 Not Found` (analyze-detail) | 코드가 실제 파일에 반영 안 됨 (붙여넣기 누락) | 코드 추가 후 정상화 |
| `사용자를 찾을 수 없습니다` | 새 Firebase 계정으로 `/auth/login`을 먼저 호출하지 않고 바로 인증이 필요한 엔드포인트 호출 | `/auth/login` 선행 호출로 DB에 사용자 레코드 생성 |
| `유효하지 않거나 만료된 session_id` | 인메모리 캐시 TTL(10분) 초과 | 전체 플로우를 빠르게 연속 실행, 또는 테스트 자동화 스크립트로 해결 |

**공통 교훈**: Python 3.13처�럼 최신 버전 사용 시 패키지 버전 고정값이 prebuilt wheel을 지원하지 않는 경우가 잦음 → 버전 범위를 유연하게 두거나 최신 패치 버전 사용 권장.

---

## 4. 아직 안 한 것 (TODO)

### 4-1. 캔버스 모드 — 남은 보강 작업
- [ ] LSTM 기반 2차 그룹핑 (현재 규칙 기반만 적용됨, REQ-004C-1 미완성)
- [ ] 실제 획순 분석 모델 (현재 stroke 개수 비교하는 placeholder)
- [ ] 표준 획순 DB 11,172자 전체 채우기 (현재 "가" 1글자만 시드)
- [ ] 문자 인식(어떤 글자인지 식별하는 과정) — 지금은 `char=None`으로 항상 기본 표준값만 사용 중. 표준 DB와 매칭하려면 이 과정이 선행되어야 함
- [ ] 가중치 설정 파일화 (REQ-005C-6 — 현재 하드코딩됨)
- [ ] i18n 구조 적용 (REQ-007-5)
- [ ] 색맹 보조 아이콘 등 UI 관련 메타데이터 (REQ-007-6, 프론트와 협의 필요)

### 4-2. 이미지 모드 파이프라인 — 전체 미착수
- [ ] SFR-003I: 카메라 이미지 입력 + OpenCV 전처리 (`/api/v1/image/preprocess`)
- [ ] SFR-004I: CRAFT 기반 Bounding Box 탐지
- [ ] SFR-005I: 크기 균일성 / 기울기 분석
- [ ] `font_standards` 테이블 스키마 및 시드 데이터
- [ ] 이미지 모드용 피드백 생성 로직 (SFR-007의 이미지 모드 분기)

### 4-3. SFR-008 — 학습 관리 대시보드
- [ ] 전체 미착수 (우선순위 Medium)

### 4-4. SFR-009 — 저장 및 클라우드 동기화 보강
- [x] PostgreSQL 저장은 이미 `analyze-detail` 단계에서 동작 중
- [ ] Firebase Firestore 동기화 (`user_sessions` 컬렉션)
- [ ] AWS S3 이미지 업로드 (이미지 모드 + 동의 시) — `.env`의 AWS 키 항목 현재 비어있음
- [ ] 네트워크 장애 시 재시도 큐 메커니즘
- [ ] 계정 삭제 시 30일 내 데이터 영구 삭제 정책 구현

### 4-5. 인프라/운영 관련
- [ ] 인메모리 세션 캐시 → Redis로 교체 (다중 서버 환경 대응, TTL 만료 문제 해결)
- [ ] `.gitignore`에 `.env`, `firebase-credentials.json` 포함 여부 재확인
- [ ] 테스트 코드 (pytest) 작성 — 지금까지는 수동 curl / 스크립트 테스트만 진행
- [ ] API 문서 정비 (Swagger 자동 생성 외 추가 설명 필요 시)
- [ ] 이메일/비밀번호 로그인은 테스트 목적으로만 켜놓은 상태 — 실제 서비스에서는 Google/Kakao OAuth만 사용할 계획이므로 운영 전 비활성화 검토

---

## 5. 다음 작업 우선순위 추천

1. **이미지 모드 파이프라인 착수** (SFR-003I~005I) — 우선순위 🔴 High, 캔버스 모드와 동일한 구조로 작업 가능
2. **AI 모델 트랙과의 협업 포인트 정리** — LSTM 그룹핑, 획순 분석, CRAFT 탐지는 현재 모두 placeholder 상태이므로, AI 모델 개발자와 인터페이스(입출력 스펙)를 먼저 확정해두는 것이 중요
3. **Redis 도입** — 디버깅 중 세션 만료로 인한 반복적인 트러블슈팅이 있었으므로, 개발 편의성과 운영 안정성 모두를 위해 비교적 빠른 시점에 전환 권장
