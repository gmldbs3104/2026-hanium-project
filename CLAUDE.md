# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI 손글씨 교정 플랫폼 — an AI-powered Korean handwriting correction platform (2026 Hanium Dream-Up project). Users submit handwriting via two independent pipelines: **canvas mode** (stroke coordinate data from an in-app drawing surface) and **image mode** (camera photo). Both pipelines converge at feedback generation and storage.

Tech stack:
- **Backend**: Python 3.13, FastAPI + Uvicorn (async), SQLAlchemy 2.0 async, Alembic, PostgreSQL
- **Auth**: Firebase Authentication (Google/Kakao OAuth 2.0) — the backend verifies Firebase ID tokens, not passwords
- **Frontend**: Flutter (`frontend/`), Riverpod + go_router; mock/real API switch via `AppConfig.useMockApi`
- **Storage**: AWS S3 for image uploads (implemented, graceful no-op if unconfigured); Firebase Firestore multi-device sync is planned but not implemented

## Backend Development Commands

All commands run from the `backend/` directory with the virtual environment activated.

```bash
# Activate virtual environment (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload --port 8000

# Run the canvas pipeline integration test (requires server running + FIREBASE_WEB_API_KEY)
FIREBASE_WEB_API_KEY=AIza... python test_canvas_pipeline.py
```

The `.env` file (copied from `.env.example`) must be present in `backend/` before running. Required vars: `DATABASE_URL`, `FIREBASE_CREDENTIALS_PATH`, `SECRET_KEY`.

## Architecture

### Backend layout

```
backend/
  app/
    main.py              # FastAPI app, router registration
    api/v1/routes/       # HTTP handlers: auth.py, handwriting.py, dashboard.py
    services/            # Business logic
      stroke_grouping.py   # Rule-based stroke → character grouping
      ai_adapters.py       # ai/ 패키지로 나가는 유일한 통로 (탐지·캔버스 분석·전처리)
      session_cache.py     # In-memory TTL cache (10 min) for pipeline state
      ocr_service.py       # (placeholder)
      ai_service.py        # (placeholder)
    models/              # SQLAlchemy ORM models
    schemas/             # Pydantic request/response schemas
    core/
      config.py          # Settings via pydantic-settings (reads .env)
      deps.py            # FastAPI dependency: get_current_user (Firebase token → User)
      firebase.py        # Firebase Admin SDK init + token verification
    db/
      session.py         # Async SQLAlchemy engine + get_db dependency
      base.py            # DeclarativeBase
      seed.py            # DB seeding
  alembic/               # Migration scripts
  test_canvas_pipeline.py  # End-to-end integration test
```

### Canvas pipeline (SFR-003C → SFR-004C → SFR-005C)

Three sequential API calls, with state passed through the in-memory session cache:

1. `POST /api/v1/canvas/analyze` — receives stroke coordinate array, issues `canvas_session_id`, stores raw strokes in cache
2. `POST /api/v1/canvas/{canvas_session_id}/group` — reads strokes from cache, runs `rule_based_grouping()` (centroid distance + time-gap thresholds from settings), assigns `char_id`s, stores `char_groups` back in cache
3. `POST /api/v1/canvas/{canvas_session_id}/analyze-detail` *(requires auth)* — reads `char_groups`, runs stroke-order / spacing / size analysis, writes results to `canvas_analysis_results` table

### Authentication flow

All protected endpoints use `get_current_user` (in `core/deps.py`): the client sends a Firebase ID Token in the `Authorization: Bearer <token>` header; the server verifies it with Firebase Admin SDK, then looks up the user in PostgreSQL by `firebase_uid`.

The `POST /api/v1/auth/login` endpoint creates or updates a user record in PostgreSQL when a valid Firebase token is presented.

### Database models

- `users` — Firebase UID, email, name, provider, timestamps
- `canvas_analysis_results` — per-character results (stroke order JSON, spacing/size deviation, overall score) keyed by session_id + user_id
- `image_analysis_results` — session-level scores (size uniformity, slant angle, line alignment) + char-level JSON
- `stroke_standards` — standard reference data for Korean characters (height, width, spacing, expected stroke sequence); seeded for all 11,172 Korean characters
- `font_standards` — per-character/per-font reference dimensions (height, width, aspect ratio) used by the image pipeline; seeded for all 11,172 characters (`myeongjo` font)

### Configurable thresholds (in `.env` / `Settings`)

| Setting | Default | Effect |
|---|---|---|
| `STROKE_DISTANCE_THRESHOLD` | 50.0 px | Max centroid distance to group strokes into one character |
| `STROKE_TIME_THRESHOLD_MS` | 500 ms | Max time gap between strokes in the same character |
| `GROUPING_CONFIDENCE_THRESHOLD` | 0.5 | Below this, a group is flagged `low_confidence` |

## Current Implementation Status

> ⚠️ 이 절은 **2026-08-17에 실제 코드로 재검증**했습니다(최초 재검증은 2026-08-12). 이전 판은
> 2026-04 시점 서술이 그대로 남아 "CRAFT는 TODO", "`get_standard()`는 항상 `DEFAULT_STANDARD`"처럼
> **지금은 거짓인 문장**을 담고 있었습니다. 상태를 단정할 때는 근거 커밋을 같이 적어 주세요.

**캔버스 파이프라인** — 2026-08-11 `ab9de5a`로 AI 분석기가 실제 연결됐습니다.
- `analyze-detail`이 `ai/canvas/canvas_quality_analyzer.analyze_canvas_writing()`을 **직접 호출**합니다.
  자체 구현이던 `services/canvas_analysis.py`는 **삭제**됐습니다.
- 획순은 **위치+모양 기하 비교**입니다(획 개수 비교 아님). 목표 글자(`target_text`)를 프론트가
  보내고 백엔드가 세션에 저장합니다. 표준 획순은 DB가 아니라 **AI의 유니코드 산술**로 만듭니다.
- 크기·자간 기준을 AI 쪽으로 통일했습니다(중앙값 대비 / 평균 글자폭 40%).
- 남은 스텁: `lstm_refine_grouping`(그룹핑 정제 — 입력 그대로 반환). 그룹핑은 여전히 규칙 기반입니다.
- ⚠️ **그룹핑 구현이 두 곳에 따로 있습니다.** `ai/canvas/stroke_grouping.py`(AI 쪽 정본)와
  `backend/app/services/stroke_grouping.py`(실서비스 `/canvas/{id}/group` 라우트가 실제로
  쓰는 것)가 별개 코드입니다. **2026-08-19에 AI 쪽에 `expected_count` 옵션을 추가**했습니다
  (목표 글자 수를 알 때 고정 임계값 대신 "간격이 가장 크게 벌어진 곳" 상대 순위로 정확히 그
  개수만큼 나눔 — 문장 쓰기 화면의 그룹핑 오류 개선용, `STATUS.md` §2·§5-5). **backend 쪽엔
  아직 포팅 안 됨** — `ai/`만 고쳐서는 실제 서비스에 반영되지 않습니다.
- ✅ 자모 단독(ㄱ·ㅏ)도 2026-08-19부터 획순 채점됩니다(전에는 `stroke_order_result: null`로
  빠졌음) — `stroke_standards.py`·`canvas_quality_analyzer.py`에 낱자 전용 경로 추가.

**이미지 파이프라인** — CRAFT가 실제로 붙어 있습니다.
- 전처리는 **측지 재구성 기반**입니다(단순 Otsu 아님). 비침·괘선을 획으로 승격하지 않으며,
  이미지별로 `geodesic`(비침 제거) / `gentle_stretch`(연한 글씨 보존) 라우팅을 합니다.
- 문자 영역 탐지는 **CRAFT**(pretrained `craft_mlt_25k.pth`)입니다. 파인튜닝은 미배포입니다.
- 기울기는 종횡비 근사가 아니라 **AI가 잰 각도**(`mean_angle`)를 그대로 씁니다.
- AI는 5지표(높이·기울기·자간·행간·기준선)를 채점하고 응답에도 5개가 다 실립니다. **DB에도 이제
  5개 전부 저장됩니다**(2026-08-16 `08019d3`, 마이그레이션 `b3f1c27a9d40`로 `spacing_uniformity_score`·
  `line_spacing_uniformity_score` 컬럼 추가) — 분석 화면 취약 항목에 자간·행간도 나타납니다.
- **측정 불가 지표는 `None`(미측정)으로 정확히 나갑니다**(2026-08-16 `8a660c4`) — 예전엔 AI가
  skipped일 때 `100.0`으로 덮어써서 재지도 않은 지표로 만점을 줬는데, 이제 `handwriting_analyzer.py`가
  `Optional`로 돌리고 백엔드도 `or 0`을 걷어내 집계에서 제외합니다. (탐지 0개면 여전히 `/analyze`가
  400으로 "사진에서 글자를 찾지 못했습니다"를 준다 — 만점이 아니라.)

**대시보드**(`/api/v1/dashboard`, SFR-008) — 기간/모드별 집계 + Redis 캐시. `recommended_exercises`는
항상 `[]`(연습 예문 DB 미구축). **캔버스 항목 점수는 이제 AI의 `canvas_item_scores()`를 그대로
씁니다**(2026-08-16 `e874828`, `ai_adapters`를 통해 호출만 함) — 결과 화면·분석 화면의 계수가
하나로 통일돼 더 이상 어긋나지 않습니다.

> 오늘(2026-08-17) 재검증: AI 유닛테스트 34개 통과, 서버를 띄운 상태에서 캔버스·이미지 파이프라인
> E2E(로그인→분석→피드백) 둘 다 통과. 상세 근거는 [CHANGES_2026-08-17.md](CHANGES_2026-08-17.md).

> 값 흐름 전체 대조와 남은 불일치 목록은 **[DATA_FLOW.md](DATA_FLOW.md)** 가 단일 출처입니다.

## Branch Strategy

- `main` — production
- `dev` — integration
- `feature/*` — individual features
