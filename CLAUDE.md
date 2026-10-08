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

**캔버스 파이프라인** — 2026-08-11 `ab9de5a`로 AI 분석기가 실제 연결됐고, **2026-10-08 `cc5e141`로
채점을 네 축으로 재설계**했습니다(설계: `docs/superpowers/specs/2026-10-08-canvas-scoring-axes-design.md`,
개발 서사: `ai/DEVLOG.md` 33·34막).
- `analyze-detail`이 `ai/canvas/canvas_quality_analyzer.analyze_canvas_writing()`을 **직접 호출**합니다.
  자체 구현이던 `services/canvas_analysis.py`는 **삭제**됐습니다. 획순은 **위치+모양 기하 비교**이고
  표준 획순은 DB가 아니라 **AI의 유니코드 산술**로 만듭니다.
- **채점 축은 4개이고, 연습 단계가 축을 더해 갑니다** — 자모음: **획순·모양** / 한 글자: + **짜임새** /
  문장: + **배치**. 축 이름은 단계가 올라가도 같습니다(`AXIS_*` 상수, 응답·DB·화면 공통).
  - 획순 = 순서 어긋남(두 획이 자리를 바꾼 것은 1건) · 반대로 그은 획 · 획 수 다름. 획 수가 다르면
    순서 어긋남은 세지 않습니다(합친 획은 짝이 밀려 따라 나오는 것).
  - 모양 = 기울어짐(획 기울기 12° · 글자 전체 기울기 15°를 **합쳐 1건**) · 둥글린 모서리 ·
    표준과 다른 모양(낱자만, 기울어진 글자에서는 세지 않음).
  - 짜임새 = 초·중·종성의 크기·비율·자리(걸린 성분 1개 = 1건). 허용치 ±55% / 중심 26% / 중성 ×1.3.
  - 배치 = 크기 · 자간 · 위치(문장만). 자간은 **화면 가이드의 글자 중심 간격**이 기준입니다 —
    자유 필기 기준('평균 글자폭 40%')을 대면 가이드대로 따라 쓴 글씨가 "좁다"가 됩니다.
- **축 점수는 100 / 70 / 40 세 값뿐**(걸린 세부 판정 0 / 1 / 2건 이상). 글자 점수는 측정된 축의
  평균(.5는 올림), 문장 점수는 글자 평균. **측정 불가 축은 0이 아니라 None**이고 평균에서 빠집니다 —
  소비자(백엔드·앱)는 None을 0이나 100으로 채우면 안 됩니다. 종전의 "틀린 항목 × 20, 절반 넘으면
  두 배"와 그 전의 가중 평균은 **없어졌습니다**.
- **채점 거부**는 세 조건 — 획 없음(건너뜀 `missing`) · 획 수가 표준의 2배 초과(`too_many_strokes`) ·
  **획 모양이 다르고 잉크도 제자리에 없음**(`shape_mismatch`, 둘 다 넘어야). 기울여 쓴 글씨는
  거부하지 않습니다(모양 축이 지적). 자모음·한 글자는 세션 채점 불가(`None`), **문장은 그 글자만
  0점**이고 나머지는 정상 채점합니다.
- **박스**: 자모음 없음 / 한 글자 성분 박스(초록·빨강) / **문장은 글자 박스, 빨강만**. 색은 축별 OR.
  사유 글자는 캔버스 위에 그리지 않고 우측 패널에 `원 — 모양(…), 획순(…)` 형식으로 글자별
  한 줄입니다(`frontend/lib/features/feedback/utils/canvas_habit_lines.dart`).
- **문구는 AI의 `failed_items` 하나만** 씁니다. 백엔드 `feedback_generator.py`는 문장을 조립하지
  않고 점수 구간 문구만 붙입니다. 축 점수는 `canvas_analysis_results.item_scores`(JSON,
  마이그레이션 `a1f3c5e7b9d2`)에 저장되고 대시보드는 그 값을 그대로 집계합니다(재계산 없음).
  10-08 이전 행은 축 집계에서 빠집니다(종합 점수 추세는 유지).
- **표준과 사용자 획은 같은 좌표 공간에서 비교합니다**(2026-09-30 수정). 각도·호길이는 표준을
  사용자 테두리에 맞춰 편 뒤(`_template_paths_in_pixels`) 잽니다 — 종전에는 '리'를 표준대로 써도
  "12도 기울었습니다", '느·그·드·르'는 "모서리를 둥글게"가 나왔습니다. 꺾인 획(ㄱ·ㄴ 모양)은
  기울기 대상이 아닙니다. 받침 없는 ㅣ·ㅡ 음절('시·기·이·으')의 성분 배율도 넓이가 아니라
  긴 축 길이로 잡습니다(종전엔 떨림 1%에 두 성분이 모두 "너무 작음").
- **획을 합쳐 쓰거나 나눠 쓴 글자**는 획 수가 같은 자모 블록만 획 단위 비교(방향·기울기·모서리)를
  하고, 나머지는 획순 축이 획 수로 지적합니다. 낱자 모양 거리도 획 수가 같을 때만 잽니다.
- **전수 점검(2026-10-08)**: 11,172자 전체를 표준대로 쓰면 걸리는 글자 0, 글자당 약 2.6ms.
  연습 글자(각간달밤상 + 두 문장 + 낱자 10종)는 떨림 1%에서 오탐 0.
- **자모 배치 정본은 `ai/canvas/synthetic_stroke_generator.py`의 `jamo_boxes()` 한 곳입니다.**
  프론트 `stroke_order_data.dart`가 같은 자리를 그리며, `ai/tests/test_jamo_layout_contract.py`가
  **dart 소스를 파싱해** 양쪽 일치를 고정합니다. 이 계약 테스트는 배치뿐 아니라 **획수·모양·순서**도
  대조합니다(2026-09-01 하루에만 자모 정의가 네 번 어긋났음). 프론트에 없는 자모(ㅈ·ㅊ·ㅋ·ㅌ·ㅍ·ㅎ)는
  **대조 대상이 없어 미검증**입니다. ⚠️ 낱자의 AI 내부 배치(`_single_jamo_layout`)는 잉크를 상자에
  꽉 채워 늘리므로 프론트 가이드와 모양이 다릅니다 — 거부·모양 판정은 늘리지 않은 원형을 쓰고,
  테스트도 가이드 모양(`_jamo()`)으로 씁니다.
- **임계값은 실사용자 필기로 보정된 값이 아닙니다.** 🔑 합성 노이즈는 사람 손을 과소평가합니다.
  거부 시 `correction_flags`에 `unscorable:<사유>`·`match_dist:…`·`ink_gap:…`이 남으므로
  보정은 그 분포를 보고 합니다(화면에는 콜론 든 플래그를 숨깁니다).
- **LSTM 스텁 2개는 제거됐습니다(2026-09-01).** ⚠️ `requirement.md`의 `REQ-004C-1`·`REQ-005C-3`은
  **아직 LSTM을 요구하는 상태** — 명세 개정은 팀 결정 대기 중입니다.
- **필압은 제거, 속도는 수집만** 합니다(2026-09-01).
- **그룹핑** — 문장은 2026-09-17부터 **화면 글자 칸(`char_positions`)으로 나눕니다**
  (`ai/canvas/stroke_grouping.group_strokes_by_positions`, 라우트가 어댑터로 호출). 칸 수가 글자 수와
  다르면 쓰지 않고 간격 기반(`backend/app/services/stroke_grouping.py`, AI 쪽 정본과 별개 구현)으로
  폴백합니다. ⚠️ 글자가 칸의 35%쯤 밀리면 획이 옆 칸으로 넘어가 두 글자가 거부될 수 있습니다(미해결).
  한 글자 연습은 `expected_count`가 1이라 옛 임계값(50px·0.5초)으로 묶입니다.
- ✅ 자모 단독(ㄱ·ㅏ)도 2026-08-19부터 채점됩니다(`_single_jamo_layout` 경로).

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
항상 `[]`(연습 예문 DB 미구축). **캔버스 취약 항목은 저장된 축 점수(`item_scores`)의
축별 평균**입니다(2026-10-08 `cc5e141`). 중간 결과로 다시 계산하지 않으므로 결과 화면과 잣대가 같고,
10-08 이전 행은 축 집계에서 빠집니다(종합 점수 추세는 유지). 세션 종합은 글자 점수 평균이며 문장의
거부 글자(0점)도 들어갑니다.

> 2026-08-17 재검증: AI 유닛테스트 34개 통과, 서버를 띄운 상태에서 캔버스·이미지 파이프라인
> E2E(로그인→분석→피드백) 둘 다 통과. 상세 근거는 [CHANGES_2026-08-17.md](CHANGES_2026-08-17.md).
> 2026-10-08 재검증: AI 128 · 백엔드 7 · Flutter 51 테스트 통과, 서버 스모크(analyze→group) 통과.
> 실기기 확인(자모음·한 글자·문장 각 1회)은 아직 안 했다.

> 값 흐름 전체 대조와 남은 불일치 목록은 **[DATA_FLOW.md](DATA_FLOW.md)** 가 단일 출처입니다.

## Branch Strategy

- `main` — production
- `dev` — integration
- `feature/*` — individual features
