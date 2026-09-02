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
- **채점 항목이 5개입니다 (2026-09-01 개편, DEVLOG 30막)** — 획순 · **획방향** · **성분비율**
  (초·중·종성 크기 균형) · 크기 · 자간. **연습 종류마다 채점되는 항목이 다릅니다**:
  자음·모음(낱자)은 획순·획방향·크기 3개, 한 글자는 +성분비율, 단어·문장은 +자간.
  합산은 감점 누적이 아니라 **가중 평균**(바르게 쓰기 3 : 보조 2)이고, **측정 불가 항목은
  0점이 아니라 분모에서 빠집니다.** 소비자(백엔드·앱·화면)는 `None`을 0이나 만점으로 채우면
  안 됩니다 — 그 순간 "안 잰 지표로 감점/칭찬"이 됩니다.
- **크기 채점은 `guide_box`가 있어야 제대로 됩니다** — 프론트가 획순 가이드 영역을 함께 보내고,
  서버는 '표준 자형 대비 배율'로 판정합니다. 안 보내면 세션 내 상대 편차로 폴백하는데
  **글자가 하나뿐인 연습에서는 비교 대상이 없어 미측정**으로 남습니다.
- **자모 배치 정본은 `ai/canvas/synthetic_stroke_generator.py`의 `jamo_boxes()` 한 곳입니다.**
  프론트 `stroke_order_data.dart`가 같은 자리를 그리며, `ai/tests/test_jamo_layout_contract.py`가
  **dart 소스를 파싱해** 양쪽 일치를 고정합니다. 한쪽만 고치면 "가이드대로 썼는데 비율이 틀렸다"가
  나옵니다(2026-09-01 이전에 실제로 최대 0.15 어긋나 있었음).
  ⚠️ 이 계약 테스트는 배치뿐 아니라 **획수·모양·순서**도 대조합니다 — 2026-09-01 하루에만
  자모 정의가 네 번 어긋났기 때문입니다(ㄱ·ㄴ 2획vs1획, ㅁ 4vs3획, ㄹ에 없는 사선, ㅓ·ㅕ 순서).
  덤으로 **ㅗ↔ㅜ·ㅛ↔ㅠ의 모양이 통째로 뒤바뀐 것**도 드러났습니다. 프론트에 없는 자모
  (ㅈ·ㅊ·ㅋ·ㅌ·ㅍ·ㅎ)는 **대조 대상이 없어 미검증**입니다.
- **채점 항목이 6개입니다 (2026-09-01 추가 개편, DEVLOG 31막)** — 위 5개에 **기울기**(곧게
  그어야 할 획이 15° 초과로 어긋남)가 더해졌고, **획방향은 역방향(135° 초과)만** 봅니다.
  둘을 한 항목에 섞으면 "반대로 그었다"와 "삐뚤게 그었다"가 구분되지 않습니다.
- **바운딩 박스는 성분(초·중·종성) 단위이고 색은 초록/빨강 2색입니다.** 판정은 **항목별 OR** —
  종합 점수로 색을 정하면 낱자 획순 0점인데 종합 62점이라 초록이 나옵니다(실측).
  낱자는 박스를 치지 않고(성분이 하나뿐), 문장은 **빨강만** 그립니다(45성분을 다 칠하면 안 보임).
- **허용치는 2026-09-01에 두 번 완화됐습니다** — 성분 면적·종횡비 ±55%, 중심 26%, 중성 ×1.3.
  선형 자모(ㅡ·ㅣ)는 넓이 대신 **긴 축의 길이**로 봅니다(높이가 0에 가까워 넓이가 손 떨림에
  폭발). 🔑 **합성 노이즈는 사람 손을 과소평가합니다** — 1차 완화 후 합성으로는 오탐 0%였는데
  실사용에서는 여전히 빡빡했습니다. 여전히 실사용자 필기로는 미보정입니다.
- **LSTM 스텁 2개는 제거됐습니다(2026-09-01).** 새 채점이 전부 기하 계산으로 풀리고 학습
  데이터도 없어서입니다. ⚠️ `requirement.md`의 `REQ-004C-1`·`REQ-005C-3`은 **아직 LSTM을
  요구하는 상태** — 명세 개정은 팀 결정 대기 중입니다.
- **필압은 제거, 속도는 수집만** 합니다(2026-09-01). 필압은 미지원 기기에서 늘 1.0 상수라
  신호가 아니었습니다. 속도는 채점에 안 쓰지만 소급이 안 되므로 계속 쌓습니다.
- ⚠️ **그룹핑 구현이 두 곳에 따로 있습니다.** `ai/canvas/stroke_grouping.py`(AI 쪽 정본)와
  `backend/app/services/stroke_grouping.py`(실서비스 `/canvas/{id}/group` 라우트가 실제로
  쓰는 것)가 별개 코드입니다. `expected_count`(목표 글자 수로 정확히 나누기)는 **양쪽 다
  반영돼 있습니다** — 종전 이 문단의 "backend 미포팅"은 낡은 서술이었습니다.
  다만 **한 글자 연습은 `expected_count`가 1이라 이 경로를 안 타고** 옛 임계값(50px·0.5초)으로
  묶입니다 — 크게 쓰거나 천천히 쓰면 한 글자가 쪼개질 수 있습니다(미해결).
- ✅ 자모 단독(ㄱ·ㅏ)도 2026-08-19부터 획순 채점됩니다(전에는 `stroke_order_result: null`로
  빠졌음) — `stroke_standards.py`·`canvas_quality_analyzer.py`에 낱자 전용 경로 추가.

**이미지 파이프라인** — CRAFT가 실제로 붙어 있습니다.
- 전처리는 **측지 재구성 기반**입니다(단순 Otsu 아님). 비침·괘선을 획으로 승격하지 않으며,
  이미지별로 `geodesic`(비침 제거) / `gentle_stretch`(연한 글씨 보존) 라우팅을 합니다.
- 문자 영역 탐지는 **CRAFT**(pretrained `craft_mlt_25k.pth`)입니다. 파인튜닝은 미배포입니다.
- 기울기는 종횡비 근사가 아니라 **AI가 잰 각도**(`mean_angle`)를 그대로 씁니다.
- **채점 항목과 문구가 2026-09-02에 재정의됐습니다 (DEVLOG 32막).** 항목 5개 —
  크기 균일성 · **기울기 균일성**(글자들끼리 기울기가 고른가) · **줄 정렬**(행 기준선이 수평인가
  **+** 글자가 그 줄에 앉았나, 나쁜 쪽) · 자간 · 행간. 화면에는 **항상 6문장**이 나갑니다
  (종합 1 + 항목 5). 항목 기준은 **80점**(= `_band_score`의 '우수' 경계)이고 **수치는 넣지
  않습니다**. 종전에는 60~84점 구간에 아무 문구도 안 나갔고 자간·행간은 문구가 아예 없었습니다.
- **박스는 기본 초록, 크기·기울기·줄 정렬 중 하나라도 미흡한 글자만 빨강**입니다(항목별 OR).
  기준은 수직이 아니라 **다른 글자들의 중앙값** — 글씨체가 원래 비스듬해도 고르게 쓰면 통과합니다.
  자간·행간은 글자에 귀속되지 않아 박스에 반영하지 않고 문구로만 나갑니다.
- **글자를 너무 기울여 쓰는 습관**은 균일성과 별개 축입니다(`CHAR_SLANT_NORM_DEG = 10°`).
  전부 똑같이 기울여 쓰면 균일성은 만점이라 따로 봅니다. **박스는 치지 않습니다.**
  ⚠️ `slant_consistency_score`는 **이름은 그대로인데 의미가 바뀌었습니다**(줄 오르내림 →
  글자 기울기 균일성) — 대시보드에 이전에 쌓인 값과 뜻이 다릅니다. `mean_char_slant`는
  **DB 컬럼이 없어 저장되지 않습니다.**
- ⚠️ **`ai/NORM_STROKE_RESEARCH.md` ①이 코드와 어긋납니다** — 문서는 `TILT_NORM_DEG`를 세로획
  기준이라 적었는데, 코드와 `test_norm_deviations.py`는 **행 수평 이탈**을 잽니다(2026-07-27 T4).
  `ai/handwriting_evaluation.md`의 지표 2 정의도 낡았습니다. **문서 정정 대기**(STATUS §1).
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
