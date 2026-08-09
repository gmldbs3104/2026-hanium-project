# 백엔드 연동 정리 문서

작성일: 2026-07-25
대상: `frontend/` (실제 Flutter 앱) ↔ `backend/` (FastAPI)

> 주의: 저장소 루트에도 `lib/`, `android/`, `ios/` 등 중복된 Flutter 스캐폴딩이 있으나 이는 `frontend/` 밖에서 `flutter create .`가 잘못 실행되어 생긴 것으로, 실제 앱과 무관합니다. 이 문서는 `frontend/`를 기준으로 작성했습니다.

## 0. 현재 상태 요약

- 프론트엔드는 `frontend/lib/core/app_config.dart`의 `useMockApi = true` 스위치로 전체 화면이 목업 데이터로 동작 중이며, 각 기능별 `*_api_service.dart`가 목업/실서버 분기를 이미 갖추고 있음. 연동 자체의 배선은 되어 있으나, **실서버로 전환 시 아래 계약 불일치 때문에 대부분의 흐름이 실패**함.
- `CLAUDE.md`에 적힌 "이미지 파이프라인 미구현", "대시보드는 빈 스텁"이라는 설명은 **오래된 정보**임. 실제로는 둘 다 구현되어 있음 (이미지 파이프라인은 CRAFT 대신 OpenCV contour 플레이스홀더 사용, 캔버스 파이프라인은 문자 인식 없이 `DEFAULT_STANDARD` 고정 사용). 연동 작업과 별개로 `CLAUDE.md` 갱신 필요.
- 백엔드는 Redis가 떠 있어야 동작함 (세션 캐시 + 대시보드 캐시). 로컬 연동 테스트 전에 Redis 기동 필요.

## 1. 최우선 수정 항목 (연동 시 즉시 깨지는 것들)

| # | 문제 | 위치 | 조치 |
|---|---|---|---|
| 1 | **CORS 미설정** — `backend/app/main.py`에 `CORSMiddleware`가 전혀 없음 | 백엔드 | 웹/Flutter web 프론트 오리진 허용하는 CORS 미들웨어 추가 |
| 2 | **캔버스 `/feedback` 400 확정** — `analyze-detail` 호출 없이 `feedback`을 바로 부름 | `frontend/lib/features/canvas_mode/canvas_api_service.dart` | `group()` 이후 `analyzeDetail()` 호출 추가 (인증 필요) |
| 3 | **이미지 `/feedback` 400 확정** — `analyze` 호출 없이 `feedback`을 바로 부름 | `frontend/lib/features/image_mode/image_api_service.dart` | `detect()` 이후 `analyze()` 호출 추가 (인증 필요, `AppConfig`에 엔드포인트 상수 없음 → 추가 필요) |
| 4 | **`/canvas/analyze` 필드명 불일치** — FE는 `canvas_metadata`로 보내는데 BE는 `metadata`를 기대 | `frontend/lib/core/app_config.dart` 또는 `canvas_api_service.dart` | 요청 바디 키를 `metadata`로 수정 |
| 5 | **`/image/preprocess` 요청 형식 불일치** — FE는 base64 JSON, BE는 `multipart/form-data` (필드명 `file`) 기대 | `frontend/lib/features/image_mode/image_api_service.dart`, `frontend/lib/shared/services/api_client.dart` | `ApiClient`에 multipart 업로드 메서드 추가, `input_type`/`roi` 필드 제거, 응답에서 FE가 기대하는 `quality_score`/`detected_slant_angle`는 BE가 반환하지 않으므로 모델 수정 |

## 2. 설계 결정이 필요한 항목 (코드만으로 해결 불가)

| # | 항목 | 내용 |
|---|---|---|
| 6 | **`confirm` 엔드포인트 부재** | FE는 `POST /canvas/{id}/confirm`, `POST /image/{id}/confirm`으로 "사용자 동의 후 저장" 흐름(SFR-009)을 기대하지만 백엔드엔 없음. 실제 저장은 `/analyze-detail`, `/analyze` 호출 시점에 자동으로 일어나고, 이미지 S3 업로드는 `/preprocess` 시점에 **동의 절차 없이 즉시** 발생함. → 백엔드에 별도 confirm/동의 게이트를 추가할지, 프론트엔드가 "분석 시 자동 저장" UX로 재설계할지 결정 필요 |
| 7 | **카카오 로그인 미구현** | `AuthController.signInWithKakao()`가 `UnimplementedError`. 카카오 액세스 토큰 → Firebase 커스텀 토큰 교환 엔드포인트(`POST /api/v1/auth/kakao/custom-token` 등)가 백엔드에 없음 |
| 8 | **계정 삭제 엔드포인트 부재** | FE의 `authDeleteAccountEndpoint` (`DELETE /api/v1/auth/account`, REQ-009-7)는 추정 경로일 뿐 백엔드에 없음 |

## 3. 엔드포인트 대조표

| 프론트 상수 (`app_config.dart`) | 경로 | 백엔드 존재? | 비고 |
|---|---|---|---|
| `authLoginEndpoint` | `POST /api/v1/auth/login` | ✅ | 필드명 일치 (`provider`, `id_token`), JWT 미발급 — 이후 모든 인증 호출은 Firebase ID 토큰을 그대로 `Authorization: Bearer`로 재사용 |
| `authDeleteAccountEndpoint` | `DELETE /api/v1/auth/account` | ❌ | 미구현 (§2-8) |
| `canvasAnalyzeEndpoint` | `POST /api/v1/canvas/analyze` | ✅ | 바디 키 불일치 (§1-4) |
| `canvasGroupEndpoint(id)` | `POST /api/v1/canvas/{id}/group` | ✅ | 일치 |
| `canvasAnalyzeDetailEndpoint(id)` | `POST /api/v1/canvas/{id}/analyze-detail` | ✅ (인증 필요) | 정의는 있으나 FE가 호출 안 함 (§1-2) |
| `canvasFeedbackEndpoint(id)` | `GET /api/v1/canvas/{id}/feedback` | ✅ | analyze-detail 누락으로 현재 400 |
| `canvasConfirmEndpoint(id)` | `POST /api/v1/canvas/{id}/confirm` | ❌ | 미구현 (§2-6) |
| `imagePreprocessEndpoint` | `POST /api/v1/image/preprocess` | ✅ | 요청 형식 불일치 (§1-5) |
| `imageDetectEndpoint(id)` | `POST /api/v1/image/{id}/detect` | ✅ | 일치 |
| *(FE에 상수 없음)* | `POST /api/v1/image/{id}/analyze` | ✅ (인증 필요) | FE가 아예 호출 안 함, 상수도 없음 (§1-3) |
| `imageFeedbackEndpoint(id)` | `GET /api/v1/image/{id}/feedback` | ✅ | analyze 누락으로 현재 400, `target_id`는 항상 `"global"` (문자별 피드백 아님) |
| `imageConfirmEndpoint(id)` | `POST /api/v1/image/{id}/confirm` | ❌ | 미구현 (§2-6) |
| `dashboardEndpoint` | `GET /api/v1/dashboard` | ✅ (인증 필요) | 일치, 실제 구현됨, `recommended_exercises`는 항상 `[]` |

## 4. 파이프라인별 실제 계약

### 4.1 인증
- `POST /api/v1/auth/login` — 인증 불필요. Body: `{ "provider": "google"|"kakao", "id_token": "<firebase id token>" }` → Response: `{ id, email, name, profile_image_url, provider, last_login_at }`
- 이후 보호된 엔드포인트는 매 요청마다 `Authorization: Bearer <firebase_id_token>`을 그대로 재전송 (백엔드가 별도 세션/JWT를 발급하지 않음)
- `get_current_user` (`backend/app/core/deps.py`): `Authorization` 헤더가 없으면 FastAPI 기본 422 (깔끔한 401이 아님) — 프론트에서 "미로그인" vs "잘못된 요청"을 구분하려면 유의

### 4.2 캔버스 파이프라인 (SFR-003C → 004C → 005C)
1. `POST /api/v1/canvas/analyze` (인증 불필요) — Body: `{ strokes: [{stroke_id, points:[{x,y,pressure,timestamp}]}], metadata: {width,height,stroke_count} }` → `{ canvas_session_id, stroke_count, status }`
2. `POST /api/v1/canvas/{id}/group` (인증 불필요, 빈 바디) → `{ canvas_session_id, char_groups:[{char_id,bounding_box,stroke_count,confidence,low_confidence}], low_confidence_count }`
3. `POST /api/v1/canvas/{id}/analyze-detail` (**인증 필요**, 빈 바디) → `{ canvas_session_id, results:[{char_id,stroke_order_result,spacing_deviation,size_deviation,overall_score}] }` — DB에 `canvas_analysis_results` 행 저장, `/feedback`이 참조할 캐시도 여기서 채워짐
4. `GET /api/v1/canvas/{id}/feedback` (인증 불필요, but analyze-detail 캐시 필요) → `{ canvas_session_id, mode:"canvas", overall_score, achievement_message, feedback_items:[{target_id,feedback_message,severity}] }`

### 4.3 이미지 파이프라인 (SFR-003I → 004I → 005I)
1. `POST /api/v1/image/preprocess` (인증 불필요, **multipart/form-data**, 필드명 `file`, content-type은 jpeg/png/webp만 허용) → `{ image_session_id, width, height, s3_image_url|null }` — S3 업로드가 이 시점에 동의 절차 없이 즉시 발생
2. `POST /api/v1/image/{id}/detect` (인증 불필요, 빈 바디) → `{ image_session_id, detected_chars:[{char_id,bounding_box}], total_detected }`
3. `POST /api/v1/image/{id}/analyze` (**인증 필요**) → `{ image_session_id, size_uniformity_score, avg_slant_angle, slant_consistency_score, line_alignment_score, overall_score, char_analyses:[{char_id,size_deviation,slant_angle}], s3_image_url|null }` — DB에 `image_analysis_results` 저장
4. `GET /api/v1/image/{id}/feedback` (인증 불필요, but analyze 캐시 필요) → `{ image_session_id, mode:"image", overall_score, achievement_message, feedback_items:[{target_id:"global", feedback_message, severity}] }`

### 4.4 대시보드 (SFR-008)
- `GET /api/v1/dashboard?period=week|month|all&mode=canvas|image|all` (**인증 필요**), Redis에 `(user_id, period, mode)` 단위 캐시
- Response: `{ period_summary:{total_sessions,avg_score,improvement_rate,canvas_sessions,image_sessions}, weak_items:[{item,avg_score,frequency,mode}], score_trend:[{date,avg_score,mode}], recommended_exercises:[], is_new_user }`

## 5. 로컬 연동 테스트 준비물
- Redis 실행 (세션 캐시 + 대시보드 캐시 필수)
- 백엔드 `.env`: `DATABASE_URL`, `FIREBASE_CREDENTIALS_PATH`, `SECRET_KEY` 설정
- 백엔드에 CORS 미들웨어 추가 (§1-1) 없이는 웹 프론트에서 호출 자체가 막힘
- 프론트: `frontend/lib/core/app_config.dart`에서 `useMockApi = false`, `apiBaseUrl`을 백엔드 주소로 설정

## 6. 참고
- 프론트엔드 자체 감사 문서: `frontend/frontend_progress_summary.md` (2026-07-10 작성, 위 내용과 교차 검증하여 일치 확인)
- 백엔드 라우트 소스: `backend/app/api/v1/routes/{auth,handwriting,image,dashboard}.py`
- 백엔드 스키마: `backend/app/schemas/{user,canvas,image,dashboard}.py`
