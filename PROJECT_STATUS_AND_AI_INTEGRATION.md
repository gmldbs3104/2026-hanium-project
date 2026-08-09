# 프로젝트 현황 및 AI 파트 통합 가이드

> 작성일: 2026-07-26
> 목적: 지금까지 뭐가 연결됐는지, 그리고 AI팀 브랜치(`feature/ai-setup`)를 합치려면 뭘 해야 하는지 정리
>
> **새 컴퓨터에서 처음 세팅하는 경우**: 이 문서 말고 [`SETUP.md`](SETUP.md)와 `scripts/setup.ps1`(Windows) / `scripts/setup.sh`(Mac/Linux)를 먼저 보세요.

---

## 1. 지금까지 연결된 것 (현재 상태)

### 브랜치
- `feature/frontend-backend-integration` — `feature/backend-setup`(백엔드) + `feature/frontend-setup`(Flutter 프론트)을 병합하고, 실기기 테스트로 연동 버그를 찾아 고친 브랜치. 원격에 푸시됨.
- 아직 안 합쳐진 것: `feature/ai-setup` (AI팀 작업, 아래 2절)

### 실기기로 검증 완료된 흐름
Flutter 웹(Chrome) + 실제 Firebase 구글 로그인 + 로컬 FastAPI 백엔드로 아래를 전부 눌러서 확인함:
- 구글 로그인 → 백엔드 `/api/v1/auth/login`
- **캔버스 모드**: 그리기 → analyze → group → analyze-detail → feedback → 결과 화면 표시 → "학습 기록 저장"(confirm) → 대시보드 반영
- **이미지 모드**: 촬영 → preprocess(멀티파트 업로드) → detect → analyze → feedback → 결과 화면 표시 → 저장 → 대시보드 반영
- **대시보드**: 캔버스/이미지 세션 집계, 새 세션 저장 시 즉시 반영

### 이번 세션에 고친 버그 (연동 전엔 몰랐던 것들)
| 버그 | 위치 | 내용 |
|---|---|---|
| CORS `Authorization` 헤더 차단 | `backend/app/main.py` | `allow_headers=["*"]`가 스펙상 `Authorization`은 커버 안 함 → 인증 필요한 요청(analyze-detail, analyze)이 브라우저 preflight 단계에서 조용히 막힘. `["Content-Type", "Authorization"]`로 명시 |
| `bounding_box` 필드명 불일치 | `backend/app/api/v1/routes/handwriting.py` | 캔버스 파이프라인 내부(`stroke_grouping.py`)는 `{x,y,w,h}`, 프론트 모델은 `{x,y,width,height}` 기대 → `/group` 응답에서만 변환 (내부 캐시는 그대로 둠, `analyze-detail`이 참조하므로) |
| 대시보드 캐시 무효화 없음 | `backend/app/services/session_cache.py`, `handwriting.py`, `image.py` | Redis에 유저별 1시간 캐시하는데 새 세션 저장돼도 안 지워짐 → `delete_pattern()` 추가, analyze-detail/analyze 성공 시 `dashboard:{user_id}:*` 삭제 |
| SFR-009 confirm 엔드포인트 부재 | `backend/app/api/v1/routes/{handwriting,image}.py`, `schemas/session.py` | 프론트의 "학습 기록 저장" 버튼이 호출할 백엔드 엔드포인트가 아예 없었음 → 신규 추가 |
| 캔버스 요청 필드명 | `canvas_api_service.dart` | FE가 `canvas_metadata`로 보내는데 BE는 `metadata` 기대 |
| 이미지 업로드 형식 | `image_api_service.dart`, `api_client.dart` | FE가 JSON base64로 보내는데 BE는 multipart 기대 → `postMultipart()` 추가 |
| analyze-detail/analyze 호출 누락 | `feedback_screen.dart` | FE가 결과 조회 전 분석 트리거 호출을 안 하고 있었음 |

### 실서버 연동 활성화
- `AppConfig.useMockApi = false`로 전환 (더 이상 mock 아님, 실제 백엔드 사용)
- Firebase 웹 앱 설정: `flutterfire configure` 실행 → `firebase_options.dart` 생성, `main.dart` 연결, `web/index.html`에 `google-signin-client_id` 메타 태그 추가
- `web/` 플랫폼 폴더는 원래 `.gitignore` 대상이었으나, 로그인 메타 태그를 팀원 간 공유하기 위해 예외 처리해서 커밋함
- **보안 조치**: 웹 API 키가 GitHub에 노출되어 경고를 받아 Google Cloud Console에서 HTTP 리퍼러 제한(`localhost:5000`)을 걸고 curl로 차단 동작까지 검증함. Android/iOS 키는 아직 안 쓰므로 재발급 필요 시 나중에 처리

### 범위 밖으로 남겨둔 것 (문서화된 TODO, 이번엔 손 안 댐)
- 카카오 로그인 (`POST /api/v1/auth/kakao/custom-token` 등 — Firebase Custom Token 발급 엔드포인트 백엔드에 없음)
- 계정 삭제 엔드포인트 (`DELETE /api/v1/auth/account`)
- confirm에서 `save_image=false`일 때 실제 S3 원본 삭제
- Firestore 동기화

---

## 2. AI 파트 현황 (`origin/feature/ai-setup` 브랜치)

**아직 이 브랜치는 merge 안 됐음.** 탐색해보니 예상보다 훨씬 많이 진행되어 있음. AI팀 자체 문서(`ai/HANDOFF.md`, `ai/STATUS.md`)가 매우 상세하게 관리되고 있으니, 실제 작업 전에 그 두 문서를 먼저 읽는 걸 강력 추천.

### 뭐가 이미 되어있나
| 영역 | 상태 |
|---|---|
| 이미지 전처리 (`ai/preprocessing/image_preprocessor.py`) | ✅ 완성 — 이진화, deskew(기울기 보정), 리사이즈, 품질점수 |
| 이미지 문자 탐지 (`ai/detection/craft_detector.py`) | ✅ 완성 — CRAFT pretrained 모델, F1@0.3=0.968 실측. 프로세스당 1회 로드하는 싱글턴으로 최적화됨 (최초 호출 10.4초 → 이후 1.9초) |
| 이미지 크기/기울기/자간 분석 (`ai/analysis/handwriting_analyzer.py`) | ✅ 완성 — `analyze_size_angle()`, 절대 규범 기반 채점까지 포함 |
| 캔버스 규칙 기반 그룹핑/채점 | ✅ 동작 중 (임시 근사치로 충분히 쓸만함) |
| 캔버스 LSTM 2곳 (`lstm_refine_grouping`, `lstm_analyze_stroke_order`) | ⛔ 여전히 스텁 — 실사용자 데이터 수집이 선행되어야 함 (팀 논의 필요, `CANVAS_DATA_PLAN.md` 참고) |
| CRAFT 파인튜닝 | ⛔ 3차 시도까지 실패, pretrained로 서비스하는 게 현재 결론 (재도전은 후순위) |

### 중요: AI팀이 이미 `backend/app/services/ai_adapters.py` 실구현본을 작성해둠
2026-07-18에 이 브랜치에서 우리 백엔드의 계약 함수 3개(`craft_detect_chars`, `lstm_refine_grouping`, `lstm_analyze_stroke_order`)를 실제 `ai/` 패키지 구현으로 연결한 버전을 이미 만들어놨음. 시그니처는 우리 `AI_MODEL_INTERFACE.md` 계약 그대로 유지했고, 추가로 다음도 제공:
- `preprocess_image(image_bytes)` — 우리 백엔드의 `image_preprocessing.preprocess_image`와 같은 반환 계약(`binary, width, height`)을 갖는 **AI 전처리 드롭인 대체**
- `preprocess_image_full(image_bytes)` — 품질점수/재촬영 판정까지 포함
- `analyze_size_angle(...)` — SFR-005I 크기/기울기 분석의 더 정교한 버전

---

## 3. AI 파트와 합치는 방법

### 3-1. 브랜치 병합 — 기술적으로는 충돌 거의 없을 것으로 예상됨

확인해본 결과: `feature/ai-setup`은 우리와 완전히 같은 초기 스켈레톤 커밋(`8a68f9a`)에서 갈라져 나갔고, 그 이후로 **`backend/app/services/ai_adapters.py` 한 파일만 수정**했음 (나머지 `backend/`는 스켈레톤 그대로, 즉 안 건드림). 우리 쪽도 `ai_adapters.py`는 이번 통합 작업에서 전혀 안 건드렸으므로, git 3-way merge 관점에서:

- `ai_adapters.py`: 우리=안 바뀜, 쟤네=많이 바뀜 → **자동으로 쟤네 버전 채택됨** (충돌 없음)
- 나머지 `backend/*`: 우리=많이 바뀜, 쟤네=안 바뀜 → **자동으로 우리 버전 유지됨** (충돌 없음)
- `ai/` 디렉토리 전체: 우리한텐 아예 없었음 → **그냥 새로 추가됨**
- `backend/requirements.txt`: 쟤네 쪽은 비어있는 채로 남아있어서 → 우리 버전이 유지됨 (torch는 아래 3-2-③에서 수동으로 추가해야 함)

```bash
git checkout feature/frontend-backend-integration   # 또는 새 통합 브랜치를 파도 됨
git fetch origin
git merge origin/feature/ai-setup
```

병합 후 반드시 `git status`로 실제 충돌 여부를 확인하고, 혹시 충돌 나면 `ai_adapters.py`는 **AI팀(ai-setup) 쪽을 채택**하면 됨 (AI팀 문서에도 "의도된 교체"라고 명시돼 있음).

### 3-2. 병합만으로는 안 끝남 — 백엔드 라우트에서 실제로 결정해야 할 것들

병합해도 지금 라우트(`image.py`, `handwriting.py`)는 여전히 기존 placeholder 함수(`image_preprocessing.preprocess_image`, `image_analysis.py`)를 그대로 호출하고 있음. `ai_adapters.py`의 새 함수들을 실제로 라우트에서 호출하도록 바꿔야 진짜 AI가 동작함. 이때 아래 4가지를 결정/처리해야 함 (전부 AI팀 문서 `HANDOFF.md` §5.1에 명시된 블로커).

**① 라우트가 AI 전처리를 쓰도록 교체할지 결정**
- 지금 `/image/preprocess`는 자체 Otsu 이진화(`image_preprocessing.preprocess_image`)를 씀
- AI팀의 탐지 정확도(F1@0.3=0.968)는 **전부 AI 자체 전처리(adaptive threshold + deskew + 리사이즈)를 전제**로 측정된 것 → Otsu 결과를 CRAFT에 넣으면 정확도 보장 안 됨
- 즉 CRAFT 탐지를 실제로 쓰려면 전처리도 `ai_adapters.preprocess_image`로 같이 바꿔야 함 (둘 중 하나만 바꾸면 안 됨)

**② 좌표계 문제 — 이게 제일 까다로움**
- AI 전처리는 이미지를 deskew(회전 보정)하고 리사이즈함 → `craft_detect_chars`가 반환하는 bounding box는 **"전처리 후" 이미지 기준 좌표**
- 근데 우리 프론트(`feedback_screen.dart`)는 **원본 촬영 이미지**(`imageBytes`) 위에 bounding box를 오버레이로 그리고 있음
- 이대로 두면 박스 위치가 원본 사진과 안 맞게 틀어짐. 선택지 두 가지:
  - (a) 프론트에서 원본 대신 **전처리된 이미지**를 오버레이 배경으로 쓰도록 변경 (전처리된 이미지를 응답에 포함해서 내려줘야 함)
  - (b) 백엔드에서 bounding box를 원본 좌표계로 역변환해서 내려줌 (deskew 각도 + 리사이즈 비율 역산 필요, 더 복잡함)
- AI팀 문서는 (a)를 권장하는 뉘앙스임 ("오버레이는 전처리 이미지 기준 — 좌표 역변환 불필요")

**③ 의존성 추가**
- `backend/requirements.txt`에 `torch`, `craft-text-detector` 등 추가 필요
- 용량이 꽤 크고, CPU 환경에서 추론 속도가 1.8~11초로 측정됨(목표는 500ms) → GPU 없이 쓸 만한 속도가 나올지 팀 논의 필요. 최초 로드는 프로세스 시작 후 첫 요청에서 ~10초 걸리고 이후론 빨라짐(싱글턴 로딩)

**⚠️ Windows에서만 발생하는 함정 — 260자 경로 제한**
- 이 저장소 경로가 깊으면(`...\2026-hanium-project\2026-hanium-project\backend\venv\...`), `torch` 설치 중 라이선스 파일의 깊은 하위 경로(`.../third_party/kineto/.../googlemock/scripts/generator`)가 Windows 기본 260자 경로 제한(`MAX_PATH`)에 걸려 `WinError 206`으로 설치가 중간에 실패한다.
- 정석 해결책은 관리자 권한으로 레지스트리 `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled=1`을 켜는 것이지만, 관리자 권한이 없으면 불가능하다.
- 우회법: `torch`/`opencv`/`craft-text-detector` 등을 저장소 밖의 **짧은 경로**(예: `C:\ai_venv`)에 별도 venv로 설치한 뒤, `backend/venv/Lib/site-packages/`에 그 경로를 가리키는 `.pth` 파일(한 줄짜리 텍스트 파일, 내용은 그 경로 하나)을 만들어 `backend/venv`가 그 패키지들을 참조하도록 연결한다. 이 우회는 **git에 안 잡히는 로컬 상태**라 컴퓨터마다 다시 해야 한다 (아래 `scripts/setup.ps1`이 자동으로 감지해서 처리해줌).
- Mac/Linux는 이 문제 자체가 없다 (경로 길이 제한이 훨씬 김).

**④ 캔버스 모드는 사실 지금과 크게 안 달라짐**
- LSTM 2곳은 여전히 스텁이라, 캔버스 쪽은 병합해도 실질적 동작 변화는 거의 없음 (지금처럼 규칙/기하 기반 근사치 그대로 사용)
- 나중에 실사용자 데이터가 쌓이면 그때 다시 논의

### 3-3. 검증 방법
- AI팀이 이미 만들어둔 `ai/debug_e2e_image_mode.py` — 백엔드 어댑터 경로 그대로 전처리→탐지→평가를 실행해보는 스크립트. 병합 후 이걸로 먼저 스모크 테스트 가능
- 그 다음 우리가 이번 세션에 했던 것처럼 `test_image_pipeline.py` 재실행 + 실제 Flutter 앱으로 이미지 모드 다시 눌러보면서 오버레이 위치가 실제 글자와 맞는지 눈으로 확인 (좌표계 문제가 해결됐는지 가장 확실히 알 수 있는 방법)

---

## 4. 알려진 프론트 이슈 — 레벨/연속 출석 하드코딩 (백엔드 완료, 프론트 반영 대기)

**증상**: 가입 직후 신규 유저인데도 마이페이지/홈 화면에 "Lv.5", "21일 연속 출석"이 표시됨.

**원인**: 최근 프론트 리디자인 때 추가된 화면들에 레벨/연속 출석이 **숫자로 하드코딩**되어 있음 (`requirement.md`에 원래 없던, 프론트가 화면 만들면서 자체적으로 추가한 게이미피케이션 요소). 실제 유저 데이터와 무관하게 항상 같은 값이 뜸.
- `frontend/lib/features/home/screens/home_screen.dart` — `_Header(..., level: 'LV5', ...)`, `_StreakBanner(days: 21, ...)`
- `frontend/lib/features/mypage/screens/mypage_screen.dart` — `Text('손글씨 마스터 Lv.5', ...)`
- `frontend/lib/features/analysis/screens/analysis_screen.dart` — `_StreakCard(days: 21)` (주석에 "백엔드 스키마에 없어 표시용 고정값"이라고 이미 명시돼 있었음)

**백엔드 조치 완료** (`backend/app/services/dashboard_service.py`, `backend/app/schemas/dashboard.py`): `GET /api/v1/dashboard` 응답에 필드 2개 추가. `period`/`mode` 필터와 무관하게 항상 전체 기간 기준으로 계산됨.
- `level: int` — `1 + (전체 누적 세션 수 // 5)`. 캔버스는 `session_id` distinct 개수, 이미지는 행 개수 그대로 합산. 신규 유저는 `level=1`.
- `streak_days: int` — 오늘(아직 그날 연습을 안 했으면 어제까지) 기준으로 캔버스/이미지 어느 쪽이든 연습을 완료한 날짜가 끊기지 않고 이어진 일수. 신규 유저는 `streak_days=0`.
- 실제 DB 데이터 + 신규 유저(빈 DB) 양쪽으로 검증 완료.

**프론트 후속 작업 (아직 안 함)**:
1. 위 세 화면에서 `DashboardApiService.fetch(...)`를 호출해 실제 `DashboardResponse`의 `level`, `streak_days`를 받아오도록 교체
2. `DashboardResponse` Dart 모델(`frontend/lib/features/dashboard/models/dashboard_response.dart`)에 `level`, `streak_days` 필드 추가 필요 (현재 모델에 없음 — 없으면 `fromJson`에서 그냥 무시되니 당장 에러는 안 나지만 값도 안 들어옴)
3. `_Header(level: 'LV5', ...)`처럼 문자열로 박아둔 부분은 `'LV$level'` 형태로, `days: 21`은 실제 `streakDays` 값으로 교체

---

## 5. 참고 문서 위치

| 문서 | 위치 | 내용 |
|---|---|---|
| AI 인수인계 문서 (가장 먼저 읽을 것) | `ai/HANDOFF.md` (ai-setup 브랜치) | 전체 지도, 5.1절에 통합 블로커 상세 |
| AI 현재 상태 트래커 | `ai/STATUS.md` (ai-setup 브랜치) | 뭐가 됐고 안 됐는지 한눈에 |
| AI 모델 인터페이스 계약 | `AI_MODEL_INTERFACE.md` (루트, 이번에 병합한 브랜치) / `ai/AI_MODEL_INTERFACE.md` (ai-setup) | 3개 함수 계약 스펙 |
| 이번 세션 백엔드-프론트 연동 정리 | `BACKEND_INTEGRATION_PLAN.md` (루트) | 이번에 고친 연동 이슈들의 최초 분석 |
| 캔버스 실사용자 데이터 수집 제안 | `CANVAS_DATA_PLAN.md` (ai-setup 브랜치 루트) | LSTM 학습용 데이터 수집 방법 논의 자료 |
