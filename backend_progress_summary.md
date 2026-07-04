# AI 손글씨 교정 플랫폼 — 백엔드 진행 현황 정리

> 작성 기준일: 2026-07-04 (최초 2026-06-27)
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

### 2-13. 표준 획순 DB 11,172자 시딩 (2026-07-04)
- [x] `app/db/seed_stroke_standards.py` 작성
- [x] 한글 음절 전체(U+AC00~U+D7A3) 초성/중성/종성 분해 → 자모별 획순 시퀀스 합산
- [x] 획 레이블 6종: `horizontal`, `vertical`, `dot`, `diagonal-left`, `diagonal-right`, `curve` (AI_MODEL_INTERFACE.md 스펙 준수)
- [x] `standard_width`를 모음 유형별로 차등 적용 (세로 모음=75, 복합=85, 가로 모음=95)
- [x] `ON CONFLICT DO UPDATE`로 멱등성 보장 — 재실행 가능
- [x] 500자씩 배치 INSERT, 약 3초 소요
- [x] DB 반영 완료: `stroke_standards` 11,172행

### 2-14. Redis 세션 캐시 교체 완료 확인 및 보완 (2026-07-04)
- [x] `app/services/session_cache.py`: `redis.asyncio` 기반 구현 확인 (TTL 10분, set/get/delete)
- [x] `requirements.txt`: `redis==5.0.8` 등록 확인
- [x] Docker 컨테이너 `hanium-redis` 실행 중 (포트 6379)
- [x] `.env` / `.env.example` `REDIS_URL=redis://localhost:6379` 설정 확인
- [x] `app/main.py` lifespan에 **startup Redis ping** 추가 — Redis 미연결 시 서버 시작 단계에서 즉시 실패
- [x] `.env.test.example`에 `REDIS_URL` 항목 추가

### 2-15. font_standards 테이블 스키마 및 시드 (2026-07-04)
- [x] `app/models/font_standard.py` — `FontStandard` 모델 생성 (복합 PK: `char` + `font_id`)
- [x] Alembic 마이그레이션 생성 및 적용 (`0ed239e13499_add_font_standards_table.py`)
- [x] `app/db/seed_font_standards.py` — 11,172자 × `myeongjo` 서체 시딩 스크립트 작성
  - `standard_height=100`, `standard_width`는 모음 유형별 차등 (75/85/95)
  - `aspect_ratio = standard_width / standard_height`
  - `ON CONFLICT DO UPDATE`로 멱등성 보장
- [x] DB 반영 완료: `font_standards` 11,172행
- [x] `app/services/image_analysis.py`에 `get_font_standard(db, char, font_id)` 추가
  - `canvas_analysis.get_standard()`와 동일한 패턴으로 설계
  - `char=None` 시 `DEFAULT_FONT_STANDARD` 반환 (TODO: OCR 구현 후 실제 char 사용)

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
| seed 스크립트 SQLAlchemy 로그가 stdout을 가득 채움 | `AsyncSessionLocal` 생성 시 `echo=True` 기본값 또는 로깅 설정으로 인해 모든 SQL이 출력됨 | 확인 목적으로 `2>&1 \| Where-Object { $_ -notmatch "INFO\|ENGINE" }` 필터링으로 우회. 운영 시 `echo=False`(기본값) 유지 |
| `seed_stroke_standards.py` 실행 후 터미널에 한글이 깨짐 | Windows PowerShell 기본 인코딩(CP949)과 Python UTF-8 출력 불일치 | 동작 자체는 정상 — DB 데이터는 정확히 저장됨. PowerShell에서 `[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()` 설정으로 해결 가능 |
| Redis startup ping 추가 후 `AbstractConnection.__del__` RuntimeError 발생 | 테스트 스크립트 종료 시 이벤트 루프가 닫힌 뒤 Redis 연결 객체의 `__del__`이 호출됨 | 서버(uvicorn) 환경에서는 `close_redis()`가 lifespan 종료 시 정상 호출되므로 무해한 경고. 단독 스크립트에서는 `await close_redis()` 명시 호출로 해결 |
| `font_standards` 복합 PK upsert 시 `there is no unique or exclusion constraint matching the ON CONFLICT specification` | `pg_insert().on_conflict_do_update(index_elements=["char"])`처럼 PK 컬럼 하나만 지정하면 PostgreSQL이 매칭되는 unique constraint를 찾지 못함 | `index_elements=["char", "font_id"]`로 복합 PK 컬럼 전체를 지정해야 함 |
| `image_analysis.py`에 `get_font_standard()` 추가 후 라우트에서 호출 시 coroutine 반환 | 기존 함수들은 모두 동기(`def`)인데 신규 함수는 비동기(`async def`) — `await` 없이 호출하면 coroutine 객체가 반환됨 | 라우트에서 호출 시 `await get_font_standard(db, char)` 형태로 반드시 `await` 붙여야 함. 동기/비동기 혼재 파일에서 특히 주의 |
| 새 모델 추가 시 `alembic/env.py` import 누락 패턴 반복 | `font_standard.py` 모델을 `env.py`에 import하지 않으면 autogenerate가 테이블을 감지하지 못함 (`stroke_standards` 때와 동일) | `from app.models import ..., font_standard` 추가. **신규 모델 생성 체크리스트**: 모델 파일 → `env.py` import → `alembic revision --autogenerate` → `alembic upgrade head` 순서 필수 |

**공통 교훈**: Python 3.13처럼 최신 버전 사용 시 패키지 버전 고정값이 prebuilt wheel을 지원하지 않는 경우가 잦음 → 버전 범위를 유연하게 두거나 최신 패치 버전 사용 권장.

---

## 4. 아직 안 한 것 (TODO)

### 4-1. 캔버스 모드 — 남은 보강 작업
- [ ] LSTM 기반 2차 그룹핑 — AI팀 모델 완성 후 `ai_adapters.lstm_refine_grouping` 내부 교체
- [ ] 실제 획순 분석 모델 — AI팀 모델 완성 후 `ai_adapters.lstm_analyze_stroke_order` 내부 교체
- [x] ~~표준 획순 DB 11,172자 전체 채우기~~ → **완료** (`seed_stroke_standards.py`, 2026-07-04)
- [ ] 문자 인식(어떤 글자인지 식별) — 지금은 `char=None`으로 항상 기본 표준값 사용
- [ ] 가중치 설정 파일화 (REQ-005C-6 — 현재 하드코딩)
- [ ] i18n 구조 적용 (REQ-007-5)

### 4-2. 이미지 모드 — 남은 보강 작업
- [ ] CRAFT 모델 연동 — AI팀 모델 완성 후 `ai_adapters.craft_detect_chars` 내부 교체
- [x] ~~`font_standards` 테이블 스키마 및 시드 데이터~~ → **완료** (`seed_font_standards.py`, 2026-07-04)
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
- [x] ~~인메모리 세션 캐시 → Redis로 교체~~ → **완료** (구현 확인 + startup ping 추가, 2026-07-04)
- [ ] 테스트 코드 (pytest) 작성 — 지금까지는 수동 스크립트 테스트만 진행
- [ ] 이메일/비밀번호 로그인은 테스트 목적으로만 켜놓은 상태 — 운영 전 비활성화 검토

---

## 5. 다음 작업 우선순위 추천

1. **AI 모델 트랙 연동** — `AI_MODEL_INTERFACE.md`를 AI팀에 공유하고 LSTM/CRAFT 모델 완성 시점 확인. 완성되면 `ai_adapters.py` 내부만 교체하면 됨
2. ~~**표준 획순 DB 채우기**~~ → **완료** (2026-07-04)
3. ~~**Redis 도입**~~ → **완료** (2026-07-04)
4. ~~**`font_standards` 테이블 스키마 및 시드 데이터**~~ → **완료** (2026-07-04)
5. **가중치 설정 파일화** — canvas 분석 가중치 하드코딩 → `.env` 또는 config 파일로 분리
6. **SFR-008 대시보드** — 우선순위 Medium, 프론트와 API 스펙 협의 필요
