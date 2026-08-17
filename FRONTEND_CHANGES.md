# 프론트엔드 수정 내역 (2026-08-11 세션)

## 변경된 파일 요약

| 영역 | 신규 파일 | 수정 파일 |
|---|---|---|
| 온보딩 | — | `onboarding_screen.dart`, `onboarding_provider.dart`, `main.dart` |
| 홈 / 하단 탭 | — | `home_screen.dart`, `main_shell.dart`, `app_router.dart`, `dashboard_response.dart` |
| 마이페이지 | `achievement_screen.dart`, `profile_edit_screen.dart`, `profile_photo_capture_screen.dart`, `profile_override_provider.dart`, `handwriting_env_provider.dart`, `settings_api_service.dart`, `level_title.dart` | `mypage_screen.dart`, `settings_screen.dart` |
| 분석 화면 | `improvement_rate_format.dart` | `analysis_screen.dart`, `score_trend_chart.dart`, `report_screen.dart`, `dashboard_screen.dart`(미사용, 컴파일 유지용) |
| 캔버스 · 문장 연습 | — | `canvas_input_screen.dart`, `canvas_api_service.dart`, `sentence_practice_screen.dart` |
| 피드백 화면 | `canvas_feedback_parser.dart` | `feedback_screen.dart` |
| 기타 | `app_config.dart`(엔드포인트 상수 추가) | |

파일 경로는 전부 `frontend/lib/features/...` 아래(위 표는 마지막 폴더명만 표기) — 각
파일에서 정확히 무엇이 바뀌었는지는 아래 절 참고.

> 백엔드는 의도적으로 건드리지 않았다 — 세션 중 "백엔드 코드는 지금 안 바꾼다"는 방침이
> 정해져서, 원래 백엔드 수정까지 포함했던 캔버스 분석 오류 수정(§5)이 프론트 절반만
> 남기고 되돌려졌다. 백엔드가 필요한 항목은 전부 [범위 밖](#범위-밖--보류-항목) 절에
> 정리했다(원래 `mypage_upgrade.md`/`analysis_upgrade.md` 두 파일로 나눠 관리하다가 이
> 문서로 통합하며 삭제함).

---

## 1. 온보딩

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/onboarding/screens/onboarding_screen.dart` | 목표 선택 콘텐츠(제목+칩)를 화면 세로 정중앙에 배치(내용이 넘치면 스크롤). "시작하기" 클릭 시 `saveOnboardingCompleted()` 호출 추가 |
| `frontend/lib/features/onboarding/providers/onboarding_provider.dart` | `onboardingCompletedProvider`가 순수 인메모리 상태라 앱 재시작/새로고침마다 온보딩이 다시 떴던 문제 수정. `loadOnboardingCompleted()`/`saveOnboardingCompleted()`로 `SharedPreferences` 영속화 |
| `frontend/lib/main.dart` | `runApp` 전에 `loadOnboardingCompleted()`를 미리 읽어 `onboardingCompletedProvider`를 override — 라우터 redirect가 첫 프레임부터 정확히 판단하도록 (로그인 기록 있으면 온보딩 건너뜀) |

---

## 2. 홈 화면 / 하단 탭 구조

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/home/screens/home_screen.dart` | 우측 상단 레벨/아바타 영역 탭 시 마이페이지로 이동. `GET /api/v1/dashboard`를 호출해 레벨·연속 출석일을 실제 값으로 표시(이전엔 `'LV5'`/`21일` 하드코딩) |
| `frontend/lib/features/shell/main_shell.dart` | 하단 탭(홈/분석/마이) 상태를 `StatefulShellRoute`로 전환 — 각 탭이 실제 URL(`/main`, `/main/analysis`, `/main/mypage`)을 가져서 브라우저 새로고침해도 마지막 탭이 유지됨(이전엔 순수 앱 상태라 새로고침하면 항상 홈 탭으로 리셋) |
| `frontend/lib/shared/router/app_router.dart` | 위 셸 라우트 구조 반영 + `/achievements`, `/profile-edit` 라우트 추가 |
| `frontend/lib/features/dashboard/models/dashboard_response.dart` | 백엔드가 이미 보내고 있던 `level`/`streak_days` 필드를 프론트 모델이 안 읽고 있던 버그 수정 |

---

## 3. 마이페이지

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/mypage/screens/mypage_screen.dart` | "나의 성취도"→`/achievements`, "프로필 관리"→`/profile-edit` 연결. "알림 설정"은 비활성 표시("백엔드 연동 필요 — 준비 중"). 실제 레벨/닉네임/사진(로컬 오버라이드) 반영 |
| `frontend/lib/features/mypage/screens/achievement_screen.dart` *(신규)* | "나의 성취도" 화면. 대시보드 API 재사용 — 레벨/연속 출석, 학습 기록 요약(세션 수·평균 점수·향상률·모드별 세션), 자주 발견된 습관, 레벨 구간 안내(현재 위치 + 다음 레벨까지 남은 세션 수) 표시. 배지는 "준비 중" 플레이스홀더만 |
| `frontend/lib/features/mypage/utils/level_title.dart` *(신규)* | 레벨 구간별 칭호: 1-10 초보자 / 11-20 연습생 / 21-30 숙련자 / 31-49 마스터 / 50+ 장인. 홈/마이페이지/성취도 화면에 공통 적용 |
| `frontend/lib/features/mypage/screens/profile_edit_screen.dart` *(신규)* | 닉네임·프로필 사진 편집 화면. 비밀번호 수정 없음(소셜 로그인 전용이라 개념 자체가 없음). 저장은 팝업 없이 바로 뒤로가기 |
| `frontend/lib/features/mypage/screens/profile_photo_capture_screen.dart` *(신규)* | 프로필 사진 촬영 화면 — 새 패키지 없이 기존 `camera` 패키지 재사용(갤러리 선택 미지원, 촬영만) |
| `frontend/lib/features/mypage/providers/profile_override_provider.dart` *(신규)* | 닉네임/사진 로컬 저장(`SharedPreferences`) — 백엔드 프로필 수정 API가 없어 이 기기에만 저장됨 |
| `frontend/lib/features/mypage/screens/settings_screen.dart` | "데이터 초기화" 확인 다이얼로그("모든 학습 기록이 사라집니다. 정말로 초기화하시겠습니까?") 연결. "소셜 계정 연동"을 클릭 불가 표시 전용으로 변경(로그인 제공자만 표시). 필기 환경 설정 미리보기가 투명도/그림판 테마/글씨 크기를 실시간 반영(이전엔 글씨 크기만). "저장" 버튼으로 로컬 provider에 반영(연습 화면 적용은 보류). 목표 점수/투명도/글씨 크기 슬라이더에 기본값 마커, 그림판 테마 '무지' 칩에 기본 배지 |
| `frontend/lib/features/mypage/providers/handwriting_env_provider.dart` *(신규)* | 필기 환경 설정(투명도/그림판 테마)의 "저장된" 값을 담는 로컬 provider — 실제 연습 화면 적용은 미연결(보류) |
| `frontend/lib/features/mypage/services/settings_api_service.dart` *(신규)* | 데이터 초기화 API 호출부. **백엔드에 해당 엔드포인트(`DELETE /api/v1/user/history`)가 없어 지금은 호출하면 실패한다** — 백엔드가 이렇게 구현되는 걸 가정하고 미리 연결해둔 코드(상세 계약은 파일 내 주석 참고) |

---

## 4. 분석 화면 ("나의 글씨 분석")

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/analysis/screens/analysis_screen.dart` | 연속 출석 실제 값(`data.streakDays`) 연동(이전엔 `21` 하드코딩). "추가 연습이 필요한 글자" 카드의 "연습" 버튼을 `item.mode`에 따라 캔버스/이미지 연습 화면으로 이동하도록 연결(어떤 *글자*로 보낼지는 §범위 밖 참고). 성장 그래프 전용으로 `mode=all` 데이터를 별도 조회해 토글과 무관하게 두 계열이 항상 같이 보이도록 함. 실전 연습 계열 색을 블루(`#3B82F6`)로 바꿔 글씨 연습(teal)과 뚜렷이 구분 |
| `frontend/lib/features/dashboard/widgets/score_trend_chart.dart` | **버그 수정**: 범례엔 "글씨 연습"/"실전 연습" 2계열이 있었는데 실제로는 `mode`를 무시하고 한 가지 색 선 하나만 그리고 있었음. mode별로 나눠서 각자의 선을 실제 날짜 축 기준으로 동시에 그리도록 재작성 |
| `frontend/lib/features/dashboard/screens/report_screen.dart` | 향상률 표시를 공용 규칙으로 통일(아래 §향상률 참고). 추세 아이콘이 항상 상승 화살표였던 것을 방향에 맞게 수정 |
| `frontend/lib/features/dashboard/utils/improvement_rate_format.dart` *(신규)* | `formatImprovementRate()` — 향상률이 음수면 `-`만 표시, 0 이상이면 `+N%`(0은 `0%`)로 표시. analysis/report/achievement 화면에 공통 적용 |
| `frontend/lib/features/dashboard/screens/dashboard_screen.dart` | 어느 라우트에도 연결 안 된 죽은 화면(미사용) — `ScoreTrendChart` 시그니처 변경으로 컴파일이 깨져서 최소한으로 같이 고침 |

---

## 5. 캔버스 · 문장 연습 화면

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/canvas_mode/screens/canvas_input_screen.dart` | 뒤로가기를 항상 `/main`(홈)으로 명시적 이동(기존 `BackButton()`은 go_router `context.go()` 진입 화면에서 동작이 예측 불가능할 수 있었음). `_submit()`이 `targetText: _currentChar`를 같이 보내도록 준비(§범위 밖 참고 — 백엔드 미반영) |
| `frontend/lib/features/canvas_mode/services/canvas_api_service.dart` | `analyze()`에 `targetText` 파라미터 추가 + 백엔드가 받아야 할 스키마/라우트 변경사항을 상세 주석으로 남김(§범위 밖) |
| `frontend/lib/features/practice/screens/sentence_practice_screen.dart` | 뒤로가기 → 홈 이동(위와 동일 이유). "짧은 문장" 탭 예문을 완전한 문장 대신 형용사+명사 구(句)인 `'시원한 선풍기'`로 교체 |

---

## 6. 피드백 화면 (교정 결과)

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/feedback/screens/feedback_screen.dart` | **버그 수정**: 우측 "AI 분석" 패널이 백엔드 `weak_habits` 필드(스키마에 아예 없어 항상 빈 배열)만 보고 있어서 항상 "준비 중"만 표시했음 — 이미 왼쪽 오버레이가 쓰는 실제 문자별 피드백(`_canvasItems`/`_imageItems`)을 우측에도 같은 색으로 표시하도록 수정. `char_0` 같은 내부 식별자 텍스트 제거. 캔버스 모드는 한 문자의 피드백 문장(획순/자간/크기)을 문장 단위로 나눠 각각 줄바꿈+개별 색으로 표시 |
| `frontend/lib/features/feedback/utils/canvas_feedback_parser.dart` *(신규)* | 백엔드가 획순/자간/크기 피드백을 공백으로 이어붙인 문자열 하나(+단일 severity)로만 주는 것을 프론트가 문장 단위로 재분해. **키워드 기반**("획순"/"자간"/"글자+크기(%)"로 주제 판별, "오류"→빨강/"적절·정확·균일"→초록/그 외→주황)이라 백엔드 문구가 조금 바뀌어도 안정적으로 동작. 실제 예시로 검증 완료 |

---

## 범위 밖 — 보류 항목 (백엔드 작업 필요)

### 취약 글자 단위 타겟팅 (분석 화면 "추가 연습이 필요한 글자")

**요청**: "추가 연습이 필요한 글자"가 실제 글자(예: '감')를 가리켜야 하고, "연습" 버튼이
정확히 그 글자의 연습 화면으로 이동해야 한다.

**현재 상태**: `WeakItem.item`은 백엔드 `dashboard_service.py`가 계산하는 **채점
카테고리**("획순"/"자간"/"크기" 또는 "크기 균일성"/"기울기 일관성"/"줄 정렬")일 뿐, 특정
글자를 가리키지 않는다. "연습" 버튼은 `item.mode`만 보고 해당 모드의 기본 연습 화면으로
이동하는 임시 동작으로 연결해뒀다.

**프론트만으로 안 되는 이유**:
1. 캔버스가 지금 어떤 글자를 쓰는 중인지 자체를 백엔드가 모른다 — `/canvas/analyze`에
   목표 글자(`target_text`)를 보내는 프론트 코드는 준비돼 있지만
   (`canvas_api_service.dart`), 백엔드가 이 값을 저장/활용하도록 고치는 작업은 "백엔드
   코드는 안 바꾼다"는 방침에 따라 보류됨(한 번 구현했다가 되돌린 코드가 git 히스토리에
   있음).
2. 설령 세션 하나에서 어떤 글자를 썼는지 안다 해도, 여러 세션에 걸쳐 "이 사용자는 특정
   글자를 반복해서 틀린다"를 집계하는 로직 자체가 DB/백엔드에 없다 — `CanvasAnalysisResult`는
   글자 원문이 아니라 `char_id`("char_0" 같은 세션 내 순번 라벨)만 저장한다.

**필요한 백엔드 작업** (요청 시 착수):
- `CanvasAnalyzeRequest.target_text` 필드 추가 + 세션 캐시 저장
  (`backend/app/schemas/canvas.py`, `backend/app/api/v1/routes/handwriting.py`)
- `CanvasAnalysisResult`(DB 모델)에 실제 글자 컬럼 추가
- `dashboard_service.py`에 "글자별 평균 점수/오류 빈도" 집계 추가, `GET /api/v1/dashboard`
  응답에 `weak_chars: [{char, avg_score, frequency, mode}]` 같은 새 필드로 노출
- 프론트는 그 필드를 받아 표시하고, "연습" 버튼이 해당 글자로 연습 화면을 시작하도록 연결
  (`canvas_input_screen.dart`는 이미 `initialTabIndex`/`initialCharIndex`를 받는 구조라
  진입점 연결 자체는 크지 않음 — 단, 지금 연습 세트가 고정 5글자라 "AI가 고른 임의의
  글자"를 끼워 넣는 방식의 설계가 추가로 필요)

### 캔버스 AI 분석 오류 (근본 원인 — 이 세션 시점엔 백엔드 미수정)

> ✅ **2026-08-11 `ab9de5a`로 해결됨** — `analyze-detail`이 `analyze_canvas_writing()`을 직접
> 호출하도록 바뀌면서 목표 글자(`target_text`)를 세션에 저장하고 표준 획순도 AI의 유니코드
> 산술로 만든다. 아래는 이 세션(같은 날 더 이른 시점) 기준 기록.

`/canvas/{id}/analyze-detail`가 항상 `get_standard(db, char=None)`으로 표준 획순을
조회해서 (목표 글자를 몰라서) 표준 획순이 항상 빈 배열이 되고, 그 결과 실제로 몇 획을
쓰든 "획이 N개 더 많습니다"류의 의미 없는 메시지만 나온다. 프론트는 목표 글자를
보낼 준비(§5 canvas_input_screen.dart)까지만 해뒀고, 백엔드가 이를 받아서
`get_standard()` 호출에 반영하는 부분은 되돌려져 있다.

### 나의 성취도 — 배지 · 개별 세션 기록

- **배지**: `requirement.md`에 "종합 점수 90점 이상 시 성취 배지(Badge) 이벤트" 언급만
  있고, 배지 카탈로그·달성 판정·저장·API가 백엔드 어디에도 없다. 화면엔 "준비 중" 카드만
  넣어뒀다.
- **개별 세션 기록 목록**("몇월 며칠에 무엇을 써서 몇 점 받았는지" 같은 목록): 대시보드
  응답은 집계값만 주고, 세션 단위로 조회하는 엔드포인트가 없다.

### 프로필 관리 — 서버 저장

닉네임/사진 편집 화면은 만들었지만, 백엔드에 프로필 수정 API(`PATCH /api/v1/auth/profile`
같은)가 없어서 `SharedPreferences`로 이 기기에만 저장된다. 다른 기기·재설치 시 유지되지
않는다.

### 알림 설정 — 발송 자체

카테고리별 토글 UI는 프론트만으로 만들 수 있지만(로컬 저장), 실제로 알림이 오고 안 오게
하려면 FCM 연동과 서버 측 사용자별 알림 설정 저장이 필요하다. 지금은 메뉴 자체를 비활성
표시만 해뒀다.

### 데이터 초기화 — 서버 반영

`SettingsApiService.resetHistory()`가 부르는 `DELETE /api/v1/user/history`는 아직
백엔드에 없다(계정 삭제 API와는 별개로, 계정은 유지한 채 학습 기록만 지우는 엔드포인트가
필요). 지금 버튼을 누르면 실패로 안내된다.

---

## 관련 문서

- [DATA_FLOW.md](DATA_FLOW.md) — AI·백엔드·프론트 값 흐름 전체 대조표
- [BACKEND_CHANGES.md](BACKEND_CHANGES.md) *(master 브랜치)* — 백엔드 쪽 최근 수정 내역
