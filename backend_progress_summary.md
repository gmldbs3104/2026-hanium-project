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
- [x] **Async 방식으로 전체 아키텍처 결정** (sync → async 전환 완료)
  - `DATABASE_URL=postgresql+asyncpg://...`
  - `db/session.py`: `create_async_engine`, `AsyncSession`, `async_sessionmaker`
  - 모든 라우트 함수 `async def`, `db.query()` → `await db.execute(select(...))`
- [x] Alembic 마이그레이션 설정 (`alembic/env.py`에서 asyncpg → psycopg2 URL로 변환해서 동기 마이그레이션 처리)

### 2-2. DB 스키마 (마이그레이션 적용 완료)
| 테이블 | 설명 |
|---|---|
| `users` | SFR-001, Firebase 사용자 정보 |
| `canvas_analysis_results` | SFR-005C 캔버스 분석 결과 |
| `image_analysis_results` | SFR-005I 이미지 분석 결과 |
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
- [x] **규칙 기반 1차 그룹핑 구현** (거리·시간 임계값)
- [x] `ai_adapters.lstm_refine_grouping` 어댑터 연결 완료 — *LSTM 2차 보정은 AI팀 구현 대기*
- [x] 신뢰도 점수 산출 및 저신뢰 플래그 마킹

### 2-6. SFR-005C — 획순/자간/크기 분석
- [x] `POST /api/v1/canvas/{session_id}/analyze-detail` (인증 필요)
- [x] `ai_adapters.lstm_analyze_stroke_order` 어댑터 연결 완료 — *실제 LSTM 분석은 AI팀 구현 대기*
- [x] 자간/크기 분석 로직 구현
- [x] 종합 점수 산출 후 `canvas_analysis_results` 테이블에 저장 완료

### 2-7. SFR-003I — 이미지 입력 및 OpenCV 전처리
- [x] `POST /api/v1/image/preprocess` — 이미지 업로드 → 그레이스케일 이진화 → `image_session_id` 발급
- [x] Grayscale → GaussianBlur → Otsu 이진화 (opencv-python)

### 2-8. SFR-004I — 문자 영역 탐지
- [x] `POST /api/v1/image/{session_id}/detect`
- [x] `ai_adapters.craft_detect_chars` 어댑터 연결 완료 — *CRAFT 모델은 AI팀 구현 대기*
- [x] 현재 OpenCV contour 기반 bbox 탐지로 동작 중 (placeholder)

### 2-9. SFR-005I — 크기 균일성 / 기울기 / 줄 정렬 분석
- [x] `POST /api/v1/image/{session_id}/analyze` (인증 필요)
- [x] 크기 균일성 (CV 기반), 기울기 일관성 (std 기반), 줄 정렬 (y 분산 기반) 분석 구현
- [x] `image_analysis_results` 테이블에 저장 완료

### 2-10. SFR-007 — 교정 피드백 생성 (캔버스 + 이미지 모드)
- [x] `GET /api/v1/canvas/{session_id}/feedback`
- [x] `GET /api/v1/image/{session_id}/feedback`
- [x] 한국어 피드백 메시지 + severity(good/warning/error) + 성취 메시지 생성
- [x] *i18n 구조는 미적용 (지금은 한국어 하드코딩)*

### 2-11. AI 모델 협업 인터페이스
- [x] `services/ai_adapters.py` — 3개 어댑터 함수 시그니처 확정
  - `lstm_refine_grouping` — 획 그룹핑 2차 보정
  - `lstm_analyze_stroke_order` — 획순 분석
  - `craft_detect_chars` — 문자 영역 탐지
- [x] `AI_MODEL_INTERFACE.md` — AI팀 공유용 입출력 스펙 문서 작성 완료

### 2-12. 테스트 도구
- [x] `test_canvas_pipeline.py` — 캔버스 6단계 자동 테스트 (end-to-end 동작 확인)
- [x] `test_image_pipeline.py` — 이미지 4단계 자동 테스트 (테스트 이미지 자동 생성 포함)
- [x] 민감 정보 분리: `.env.test` (gitignore), `.env.test.example` (커밋)

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
| `500 Internal Server Error` (인증 후) | `INVALID_LOGIN_CREDENTIALS` — idToken과 refreshToken 혼동 | 정확한 idToken 필드 값 사용 |
| `ModuleNotFoundError: No module named 'app.services.feedback_generator'` | `feedback_generator.py` 파일 미생성 상태에서 서버 기동 시도 | 파일 생성 후 정상화 |
| `.env.test` gitignore 누락 | `*.env` 패턴은 `.env`로 끝나는 파일만 매칭, `.env.test`는 미적용 | `.gitignore`에 `.env.test` 명시적 추가 |

**공통 교훈**: Python 3.13처럼 최신 버전 사용 시 패키지 버전 고정값이 prebuilt wheel을 지원하지 않는 경우가 잦음 → 버전 범위를 유연하게 두거나 최신 패치 버전 사용 권장.

---

## 4. 아직 안 한 것 (TODO)

### 4-1. 캔버스 모드 — 남은 보강 작업
- [ ] LSTM 기반 2차 그룹핑 — AI팀 모델 완성 후 `ai_adapters.lstm_refine_grouping` 내부 교체
- [ ] 실제 획순 분석 모델 — AI팀 모델 완성 후 `ai_adapters.lstm_analyze_stroke_order` 내부 교체
- [ ] 표준 획순 DB 11,172자 전체 채우기 (현재 "가" 1글자만 시드)
- [ ] 문자 인식(어떤 글자인지 식별) — 지금은 `char=None`으로 항상 기본 표준값 사용
- [ ] 가중치 설정 파일화 (REQ-005C-6 — 현재 하드코딩)
- [ ] i18n 구조 적용 (REQ-007-5)

### 4-2. 이미지 모드 — 남은 보강 작업
- [ ] CRAFT 모델 연동 — AI팀 모델 완성 후 `ai_adapters.craft_detect_chars` 내부 교체
- [ ] `font_standards` 테이블 스키마 및 시드 데이터
- [ ] CRAFT angle 값을 기울기 분석에 반영 (현재 aspect ratio 근사 사용 중)

### 4-3. SFR-008 — 학습 관리 대시보드
- [ ] 전체 미착수 (우선순위 Medium)

### 4-4. SFR-009 — 저장 및 클라우드 동기화 보강
- [x] PostgreSQL 저장은 canvas/image analyze 단계에서 동작 중
- [ ] Firebase Firestore 동기화 (`user_sessions` 컬렉션)
- [ ] AWS S3 이미지 업로드 — `.env`의 AWS 키 항목 현재 비어있음
- [ ] 네트워크 장애 시 재시도 큐 메커니즘
- [ ] 계정 삭제 시 30일 내 데이터 영구 삭제 정책 구현

### 4-5. 인프라/운영 관련
- [ ] 인메모리 세션 캐시 → Redis로 교체
- [ ] 테스트 코드 (pytest) 작성 — 지금까지는 수동 스크립트 테스트만 진행
- [ ] 이메일/비밀번호 로그인은 테스트 목적으로만 켜놓은 상태 — 운영 전 비활성화 검토

---

## 5. 다음 작업 우선순위 추천

1. **AI 모델 트랙 연동** — `AI_MODEL_INTERFACE.md`를 AI팀에 공유하고 LSTM/CRAFT 모델 완성 시점 확인. 완성되면 `ai_adapters.py` 내부만 교체하면 됨
2. **표준 획순 DB 채우기** — 문자 인식 없이는 캔버스 분석 정확도가 낮음. 우선순위 높음
3. **Redis 도입** — 인메모리 캐시 TTL 만료 이슈 반복 발생. 개발 편의성·운영 안정성 모두를 위해 전환 권장
4. **SFR-008 대시보드** — 우선순위 Medium, 프론트와 API 스펙 협의 필요
