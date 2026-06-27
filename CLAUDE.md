# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI 손글씨 교정 플랫폼 — an AI-powered Korean handwriting correction platform (2026 Hanium Dream-Up project). Users submit handwriting via two independent pipelines: **canvas mode** (stroke coordinate data from an in-app drawing surface) and **image mode** (camera photo). Both pipelines converge at feedback generation and storage.

Tech stack:
- **Backend**: Python 3.13, FastAPI + Uvicorn (async), SQLAlchemy 2.0 async, Alembic, PostgreSQL
- **Auth**: Firebase Authentication (Google/Kakao OAuth 2.0) — the backend verifies Firebase ID tokens, not passwords
- **Frontend**: Flutter (not yet in this repo)
- **Planned**: AWS S3 for image storage, Firebase Firestore for multi-device sync

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
      canvas_analysis.py   # Stroke order, spacing, size analysis + scoring
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
- `stroke_standards` — standard reference data for Korean characters (height, width, spacing, expected stroke sequence); currently sparse — TODO: populate all 11,172 Korean characters

### Configurable thresholds (in `.env` / `Settings`)

| Setting | Default | Effect |
|---|---|---|
| `STROKE_DISTANCE_THRESHOLD` | 50.0 px | Max centroid distance to group strokes into one character |
| `STROKE_TIME_THRESHOLD_MS` | 500 ms | Max time gap between strokes in the same character |
| `GROUPING_CONFIDENCE_THRESHOLD` | 0.5 | Below this, a group is flagged `low_confidence` |

## Current Implementation Status

The **canvas pipeline** is functional end-to-end with placeholder logic:
- Stroke grouping uses rule-based only (LSTM second pass is planned but not implemented)
- Stroke order analysis compares stroke counts only (LSTM model inference is a TODO)
- Character recognition (identifying *which* Korean character) is not yet implemented; `get_standard()` always returns `DEFAULT_STANDARD`

The **image pipeline** (SFR-003I through SFR-005I: OpenCV preprocessing → CRAFT bounding box detection → size/slant analysis) is **not yet implemented**.

The **dashboard** route (`/api/v1/dashboard`) exists as an empty stub — SFR-008 is pending.

## Branch Strategy

- `main` — production
- `dev` — integration
- `feature/*` — individual features
