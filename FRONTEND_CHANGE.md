# 프론트엔드 수정 내역

두 세션 기록을 하나로 합쳤다(`FRONTEND_CHANGES.md` + `frontend_change.md` → 이 파일).
최신 세션이 위, 예전 세션이 아래.

- [2026-09-07 세션](#2026-09-07-세션)
- [2026-08-22 ~ 08-30 세션](#2026-08-22--08-30-세션)
- [2026-08-11 세션](#2026-08-11-세션)

---

## 2026-09-07 세션

이 세션도 **frontend만 수정**했다. 다만 세션 중간에 원격(`origin/feature/ai-integration`)에
`632d461`("캔버스 성분 박스 + 이미지 모드 채점 전면 개편") 커밋이 새로 올라와, 로컬에서
작업 중이던 프론트 변경사항과 상당 부분(이미지 모드 바운딩 박스·항목별 문구) 겹치는
일이 있었다. 그 부분은 아래 [§4](#4-git-병합-632d461-반영)에 정리했다 — **backend는
git 그대로**, **frontend는 로컬 수정을 우선**하되, 원격이 이미 서버 판정 기반으로 더
정확하게 구현해 둔 부분(이미지 모드 박스 색·문구)은 예외적으로 원격 버전을 채택했다.

세션 후반에 발견한 채점 로직 이슈 2건(§5)은 원인이 전부 `ai/canvas/canvas_quality_analyzer.py`
또는 `backend/app/services/stroke_grouping.py` 등 backend/AI 쪽이라, "backend/AI는 건드리지
않는다"는 이번 세션 방침에 따라 **코드 수정 없이 원인 진단만** 하고 되돌렸다(한 번 실제로
고쳤다가 방침을 재확인받고 revert함 — git 이력에는 남지 않음, 작업 트리에서만 되돌렸다).

### 변경된 파일 요약

| 영역 | 신규 파일 | 수정 파일 |
|---|---|---|
| 문장 쓰기 | — | `sentence_practice_screen.dart` |
| 분석 탭 성장 그래프 | — | `score_trend_chart.dart` |
| 이미지 모드 바운딩/문구 (§4, 원격 버전 채택) | — | `feedback_screen.dart`, `image_bbox_overlay_item.dart`, `image_bbox_overlay_view.dart`, `image_analysis_response.dart`, `image_api_service.dart` |
| 테스트 | — | `test/models/overlay_item_test.dart` |

파일 경로는 전부 `frontend/lib/features/...` 아래(테스트는 `frontend/test/...`).

---

### 1. 문장 쓰기 화면

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/practice/screens/sentence_practice_screen.dart` | ① "캘리그라피" 탭 삭제(2탭 `짧은 문장`/`긴 문장`만 남음). ② 캔버스 위에 따로 있던 "연습할 문장" 미리보기 카드를 없애고, 그 자리를 캔버스가 차지하도록 해서 캔버스 영역이 화면에 꽉 차게 함. ③ 캔버스 안쪽 가이드 문구가 진한 줄 1개 + 옅은 줄 4개, 총 5번 반복되던 것을 **1번만** 표시하도록 변경, `FittedBox(fit: BoxFit.contain)`로 캔버스 크기에 맞춰 자동 확대(짧은 문장/긴 문장 모두 동일 로직 — 짧으면 더 크게, 길면 줄바꿈 없이 한 줄로 꽉 차게 축소). ④ 가이드 문구 상단에 mint색 안내 바("'{문장}'를 크게 따라 써보세요") 추가(자음/모음 연습 화면의 안내 바와 톤 통일). ⑤ `_computeCharPositions()`(문장 제출 시 백엔드로 보내는 글자별 좌표)를 FittedBox가 실제로 적용하는 배율·중앙정렬 오프셋과 정확히 같은 공식으로 다시 계산하도록 수정 — 그래야 화면에 그려지는 위치와 백엔드가 받는 좌표가 어긋나지 않는다. |

### 2. 분석 탭 — 성장 그래프

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/dashboard/widgets/score_trend_chart.dart` | ① 그래프 하단에 있던 날짜 숫자 라벨(예: `9/19`, `9/1`) 제거, 그 공간을 차지하던 `_bottomAxisHeight`도 제거해 그래프가 세로로 꽉 차게 함. ② **버그 수정**: `CustomPaint`를 감싼 `SizedBox`가 `height`만 지정하고 `width`는 지정하지 않아서, 부모(`Column`)가 주는 느슨한 가로 제약 아래 `CustomPaint`(자식 없음, `size` 미지정)가 기본값인 `Size.zero`로 레이아웃돼 **실제 가로폭이 0으로 붕괴**하는 문제가 있었다. `CustomPaint`는 자기 크기를 벗어난 그리기를 클리핑하지 않아 화면엔 뭔가 그려지긴 했지만, `size.width`가 0이라 모든 데이터 포인트의 x좌표가 0으로 계산돼 그래프가 좌측 끝에서 위아래로만 움직이는 세로 선처럼 보였다("위로 쭉 뻗은 형태"로 사용자가 보고한 증상과 일치). `width: double.infinity` 추가로 해결 — 연속 출석일수와는 무관한 순수 레이아웃 버그였다. |

### 3. 문장 연습 캔버스 좌표 계산 검증

문장 쓰기 화면의 `_computeCharPositions()` 재계산(§1-⑤)은 시각적 변경(§1)에 종속된
부수정이라 별도 파일 변경은 없다 — 같은 파일(`sentence_practice_screen.dart`) 안에서
`_guideStyle`/`_guidePadding`을 FittedBox 렌더링과 `TextPainter` 계산 양쪽이 공유하도록
맞췄다.

### 4. git 병합(632d461) 반영

세션 도중 사용자가 "git에서 수정된 점을 가져와줘. 내가 수정한거 말고"라고 요청해
`origin/feature/ai-integration`의 새 커밋(`632d461`)을 fast-forward로 병합했다. 이후
"backend는 git을 따르고, frontend는 로컬의 수정 내용을 가져갈 것"으로 방침을 확정:

- **backend 전부**: git 버전 그대로(로컬에 있던 획 그룹핑 수정 1건을 되돌리고 병합 — §5-2 참고).
- **frontend**: 이번 세션에서 로컬로 고친 `sentence_practice_screen.dart`, `score_trend_chart.dart`는
  로컬 버전을 유지.
- **예외 — 이미지 모드 바운딩 박스/항목별 문구**: 이번 세션 초반에 로컬에서 직접 구현했던
  이미지 모드 박스 색상(자체 크기·기울기 편차 임계값 판정)과 채점 문구 생성(자체 지오메트리
  기반 자간/행간 방향 추정) 로직을, 원격 커밋이 **서버가 이미 정확하게 내려주는 판정**
  (`/analyze` 응답의 `char_boxes`: `ok`/`failed_items`, `/feedback` 응답의 `feedback_items`
  6문장)으로 대체한 것을 확인하고, 로컬 구현을 버리고 원격 버전을 채택했다. 코드 수준
  이유: 원격 쪽 `ImageCharBox` 모델 주석에 "서버가 이미 ok로 판정해서 내려준다. 앱이
  점수로 다시 판정하지 말 것"이라는 명시적 설계 의도가 있고, 로컬 구현은 이걸 어기고
  있었다(자체 재판정 + `overall_tilt` 값 이름이 `leaning_right/leaning_left`에서
  `falling/rising`으로 바뀐 걸 못 따라가 항상 기본 문구로 새는 버그도 있었음).
  - 삭제: `frontend/lib/features/feedback/utils/image_feedback_builder.dart`(로컬에서 새로
    만들었던 파일, 원격 버전 채택으로 불필요해짐).
  - 원격 버전 그대로 채택: `feedback_screen.dart`, `image_bbox_overlay_item.dart`,
    `image_bbox_overlay_view.dart`, `image_analysis_response.dart`, `image_api_service.dart`.
  - `test/models/overlay_item_test.dart`의 `ImageBBoxOverlayItem.merge` 관련 테스트를 새
    API(`charBoxes` 기반)에 맞게 다시 작성.
  - **부수 효과**: `feedback_screen.dart`를 원격 버전으로 교체하면서 캔버스 모드의 바운딩
    박스도 함께 바뀌었다 — 종전엔 음절(글자) 단위 박스였는데, 원격 버전은 **성분(초성·
    중성·종성) 단위**로 내려간 `ComponentOverlayView`를 쓴다(신규 파일
    `component_overlay_item.dart`/`component_overlay_view.dart`/`image_char_box.dart`는
    frontend가 직접 작성한 게 아니라 병합으로 들어온 것 — 별도 저작 없음). 이 변경이
    "모음/받침 연습에서 자음·모음 단위로 바운딩해야 한다"는 사용자 요청과 별개로 이미
    해결해 주는 효과가 있어 그대로 뒀다.
  - 병합 직후 남아있던 컴파일 에러 2건(제거된 필압(`pressure`) 필드 참조)을 frontend에서
    직접 고침: `sentence_practice_screen.dart`의 `StrokePoint(... pressure: 1.0 ...)`에서
    `pressure` 인자 제거, `feedback_screen.dart`의 "평균 필압" 표시 줄 제거(필압 자체가
    2026-09-01 결정으로 백엔드에서 완전히 빠졌다 — `WritingMotionProfile`에 필드 없음).

### 5. 범위 밖 — 채점 로직 이슈 2건 (backend/AI 원인, 이번 세션엔 미수정)

세션 막바지에 사용자가 요청한 두 가지는 조사 결과 **원인이 전부 backend/AI 코드에
있어서**, "backend/AI는 수정하지 않는다"는 이번 세션 방침에 따라 **코드는 그대로 두고
원인만 정리**했다. (한 항목은 실제로 `ai/canvas/canvas_quality_analyzer.py`를 고쳤다가
방침을 다시 확인받고 `git checkout`으로 되돌렸다 — 저장소에는 흔적이 없다.)

#### 5-1. 자음·모음(낱자)·한 글자 연습에서 "크기" 항목이 항상 미측정

**요청**: 낱자·한 글자 연습에서도 크기를 채점하게 해달라.

**원인**: `ai/canvas/canvas_quality_analyzer.py`의 크기 채점 분기가
`if multi_char and guide_area and target_char:`로 돼 있어, 글자가 1개뿐인 세션(자음·모음·
받침 연습)은 `guide_box`를 이미 보내고 있는데도(`canvas_input_screen.dart`가 항상
`strokeGuideBox()`를 실어 보냄) `multi_char`(글자 2개 이상) 조건에 걸려 통째로 건너뛰어진다.
바로 아래 있는 `size_score_from_fill()` 함수 자체의 설계 의도("한 글자만 쓰는 연습에서
크기를 채점할 수 있는 유일한 기준")와 정면으로 모순되는 조건이다.

**확인한 수정 방법**(적용은 안 함): 위 조건에서 `multi_char and`만 제거하면 된다 — 실제로
적용해서 `analyze_canvas_writing()`을 직접 호출하는 스크립트로 검증까지 마쳤다(낱자 'ㄱ'
1획에 대해 `size_fill_ratio`가 정상적으로 계산되고 `item_scores['크기']`가 채워짐을 확인).
아래 줄만 바꾸면 된다:

```python
# ai/canvas/canvas_quality_analyzer.py, analyze_canvas_writing() 안
if multi_char and guide_area and target_char:   # 수정 전
if guide_area and target_char:                  # 수정 후 (multi_char 제거)
```

세션 내 상대편차 폴백(`size_deviation_pct`, guide_box 없을 때만 쓰는 값)은 원래대로
`multi_char` 조건을 유지해야 한다 — 그건 "옆 글자와 비교"라 글자가 하나면 의미가 없다.
건드릴 부분은 절대 크기(가이드 박스 대비) 분기 하나뿐이다.

#### 5-2. 문장 쓰기에서 "성분비율(너무 큼)"/"자리가 벗어남"이 다수 발생

**요청**: 열심히 썼는데도 여러 글자가 틀렸다고 나온다 — 확인해달라.

**원인**: 사용자 필체 문제가 아니라 **획→음절 그룹핑이 실제로 틀리고 있었다.** 사용자의
직전 문장 연습 세션("시원한선풍기", 6글자) DB 기록을 직접 조회해 확인함 —
`backend/app/services/stroke_grouping.py`의 `_group_by_expected_count`(획 사이 간격의
상대 순위로 글자 수만큼 경계를 정하는 로직)가 몇몇 글자 경계를 잘못 잡아서, 예를 들어
4번째 글자("선", 기대 5획)가 실제로는 획 1개만 배정되고 나머지는 옆 글자로 새는 식으로
어긋나 있었다. 그 결과:
- 획순 채점이 `likely_wrong_character: true`(목표 글자와 다른 걸 쓴 것으로 오판)를 여러
  글자에서 반환.
- `spacing_deviation`이 `-263.9`px 같은 명백히 비정상적인 값으로 나옴(정상 범위를 크게
  벗어남 — 그룹 경계 자체가 깨졌다는 증거).
- 획순·획방향·성분비율이 전부 `_match_strokes()` 하나의 매칭 결과를 공유하므로, 그룹
  경계가 잘못되면 성분비율(초성/중성/종성 면적·자리 판정)도 같이 엉뚱한 값이 나온다 —
  사용자가 본 "성분비율(너무 큼)"/"자리가 벗어남" 다발은 이 매칭 실패의 연쇄 결과다.

**결론**: 프론트가 고칠 수 있는 문제가 아니다 — 그룹핑은 전부 서버(`POST /canvas/{id}/group`)
에서 끝나고, 프론트는 결과만 받는다. 근본 수정은 `_group_by_expected_count`(또는 그 AI
정본 `ai/canvas/stroke_grouping.py`)의 경계 판정 정확도를 실제 손글씨(빠르게 이어 쓴 문장)
기준으로 다시 보정하는 작업이 필요하다.

**참고**: 이전 세션(같은 날 앞부분, 아직 이 git 병합 전)에 자음/모음/받침 연습이 "한
획씩 인식"되던 별개 버그(`expected_count == 1`일 때 새 그룹핑 경로를 안 타던 문제)를
`backend/app/services/stroke_grouping.py`에서 고쳤었으나, git 병합 시 "backend는 git을
따른다" 방침에 따라 되돌렸다. 원격 632d461에도 이 버그는 그대로 남아있음을 병합 후 다시
읽은 `CLAUDE.md`로 확인함("한 글자 연습은 `expected_count`가 1이라 이 경로를 안 타고
옛 임계값 방식으로 묶입니다 — 미해결"). 필요하면 다음에 backend 쪽에서 처리.

### 6. 스키마 감사 후속 조치 — frontend/문서만 처리

§5 진단 이후 `DATA_FLOW.md`·`FEEDBACK_FIELDS_CONTRACT.md`·`ai/STATUS.md`·`ai/HANDOFF.md`와
backend/AI 스키마(`schemas/canvas.py`·`schemas/image.py`·`schemas/dashboard.py`·
`schemas/session.py`) 전체를 frontend 모델과 필드 단위로 대조했다. backend/AI 코드 수정이
필요한 항목(§5와 동일한 두 건 + `char_positions` 스키마 누락)은 이번에도 손대지 않고,
frontend·문서로 처리 가능한 두 건만 진행했다:

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/feedback/screens/feedback_screen.dart` | ① `_buildCanvasCharDetail()`에 `direction_result`/`tilt_result`의 `corrections` 문구를 표시하는 블록 추가(주황 카드, 획순 안내와 같은 위치). 두 값 모두 `analyze-detail`이 문자별로 이미 내려주고 있었지만 화면 어디에도 안 그려지고 있었다. ② **위 ①을 붙이다가 발견한 별개 문제를 같이 고침**: 자음·모음 낱자 연습은 성분이 하나뿐이라 `component_boxes` 자체가 없고, 상세 시트는 성분 박스를 탭해야만 열리는 구조라 **낱자 연습에서는 상세 시트를 열 방법이 아예 없었다**(①을 붙여도 화면에 안 뜸). `_buildCanvasOverlay()`에 성분 박스가 0개 + 글자가 정확히 1개일 때 캔버스 전체를 탭해 그 글자의 상세를 열 수 있는 폴백 추가 — 처음엔 `GestureDetector`로 감쌌는데, `ComponentOverlayView` 내부에 이미 전체 영역을 덮는 `GestureDetector`가 있어 제스처 아레나에서 안쪽 것이 탭을 가로채 바깥쪽 `onTap`이 전혀 안 불렸다(중첩 `GestureDetector`는 버블링 안 됨). 아레나 경쟁과 무관하게 히트테스트 경로의 모든 위젯에 원시 포인터 이벤트를 전달하는 `Listener`(`onPointerUp`)로 교체해 해결. |
| `DATA_FLOW.md` | §"화면 배선 결함 3건"을 `632d461`로 해결된 것으로 갱신(자간·행간 외 3항목 미표시 / `overall_tilt` 이름 불일치 / 이미지 모드 `feedback_items` 유실 — 셋 다 이제 정상 동작 확인). |
| `ai/STATUS.md` | ① "세부 점수 5개 노출 — 팀 결정 대기"를 해결됨으로 갱신. ② "문장 쓰기 그룹핑 1단계(글자수 제약)"를 완료로 갱신하고, 2단계(위치 근접 매칭)가 여전히 미착수이며 `char_positions` 스키마 누락이 그 원인임을 명시(§5 진단과 교차 연결). 우선순위 목록(4·5번)도 같이 갱신. |

**결론**: backend/AI 쪽 3건(`char_positions` 스키마 추가, 그룹핑 위치 매칭 구현, 낱자 크기
채점 게이트 제거)은 여전히 미착수 — 다음에 backend/AI를 건드릴 수 있을 때 §5·§6 기록을
그대로 작업 항목으로 쓰면 된다.

### 7. 이미지 모드 — 피드백 로딩 실패 시 "다시 시도" 버튼이 촬영 화면으로 안 돌아가던 버그

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/feedback/screens/feedback_screen.dart` | **버그 수정**: `_buildErrorState()`("피드백을 불러오지 못했습니다" 에러 화면)의 "다시 시도" 버튼이 모드와 무관하게 항상 `_loadFeedback()`을 그대로 재호출하고 있었다. 이미지 모드는 `/analyze`가 글자를 하나도 못 찾으면 항상 400("사진에서 글자를 찾지 못했습니다")을 던지는데, 같은 `session_id`로 다시 불러와 봤자 **같은 사진이라 매번 똑같이 실패**한다 — 사용자 입장에선 버튼을 눌러도 아무 반응이 없는 것처럼 보였다. 이미지 모드일 때는 버튼을 "다시 촬영"으로 바꾸고 `context.go('/image-capture')`로 촬영 화면으로 돌려보내도록 분기 추가. 캔버스 모드는 다시 그릴 화면이 없고 네트워크 일시 장애가 더 흔한 원인이라 기존 재요청 동작을 그대로 유지. |

---

## 2026-08-22 ~ 08-30 세션

이 세션은 **frontend만 수정**했다 — `backend/`, `ai/`는 건드리지 않기로 방침을 정했고
끝까지 지켰다(단, 로컬 테스트 환경 문제 2건은 코드가 아니라 설정/의존성이라 예외적으로
직접 손봤다 — 맨 아래 [참고](#참고--프론트-코드는-아님) 절 참고). 백엔드가 필요한 부분은
각 항목에 "⚠️ 백엔드 미반영" 등으로 표시해뒀다.

### 변경된 파일 요약

| 영역 | 신규 파일 | 수정 파일 |
|---|---|---|
| 마이페이지 | — | `home_screen.dart`, `settings_screen.dart` |
| 대시보드 / 출석 | `dashboard_refresh_provider.dart` | `home_screen.dart`, `feedback_screen.dart`, `dashboard_response.dart`, `analysis_screen.dart` |
| 손글씨 기초 | — | `basics_screen.dart` |
| 피드백 화면 | — | `feedback_screen.dart` |
| 캔버스 / 문장 연습 | — | `sentence_practice_screen.dart`, `canvas_api_service.dart` |
| 라우팅 | — | `app_router.dart` |
| 인증 | — | `auth_controller.dart`, `app_router.dart` |

파일 경로는 전부 `frontend/lib/features/...` 아래(위 표는 마지막 폴더명만 표기).

---

### 1. 마이페이지 버그 수정

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/home/screens/home_screen.dart` | 마이페이지에서 닉네임을 바꿔도 홈 화면엔 반영이 안 되던 문제 수정 — 마이페이지와 같은 `profileOverrideProvider`(로컬 저장 닉네임)를 보도록 변경 |
| `frontend/lib/features/mypage/screens/settings_screen.dart` | 상세환경설정에서 "데이터 초기화" 행/확인 다이얼로그/관련 상태(`_isResettingData`, `_confirmResetData`)를 완전히 제거. 소셜 계정 연동 표기를 한글 번역("구글"/"카카오"/"애플")에서 서버가 내려주는 provider 원문("google"/"kakao"/"apple") 그대로 표시하도록 변경(`_providerLabel` 함수 삭제) |

### 2. 대시보드 — 출석일 갱신 & 분석 탭 로딩 안정성

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/dashboard/providers/dashboard_refresh_provider.dart` *(신규)* | 대시보드 요약(레벨/연속 출석일) 새로고침 신호(`StateProvider<int>`). 홈 화면은 `StatefulShellRoute`(IndexedStack) 탭이라 연습 후 홈으로 돌아와도 `initState`가 재실행되지 않아, 오늘 첫 연습을 마쳐도 출석일이 "0일"에서 안 바뀌던 문제의 근본 원인이었다 |
| `frontend/lib/features/home/screens/home_screen.dart` | 위 provider를 `ref.listen`으로 감지해 값이 바뀌면 대시보드 요약을 다시 불러오도록 추가 |
| `frontend/lib/features/feedback/screens/feedback_screen.dart` | 피드백 화면에서 "홈으로" 이동할 때(액션바 버튼 + AppBar 버튼 모두) 위 provider를 bump해서 방금 완료한 세션이 출석일에 반영되게 함 |
| `frontend/lib/features/dashboard/models/dashboard_response.dart` | `DashboardResponse`/`PeriodSummary`의 `fromJson`을 널/필드 누락에 방어적으로 수정(없으면 빈 배열/0으로 안전 처리). 기존엔 필드 하나만 없어도(예: 백엔드 스키마 변경 직후 Redis에 남은 구버전 캐시) 예외가 터져 분석 탭 전체가 "분석 데이터를 불러오지 못했습니다"로 죽었다 |
| `frontend/lib/features/analysis/screens/analysis_screen.dart` | 데이터 로딩 실패 시 원인 예외를 삼키기만 하던 `catch (_)`에 `debugPrint`로 실제 예외/스택트레이스를 남기도록 추가 — 이후 같은 문제가 재발해도 콘솔에서 바로 원인 확인 가능 |

### 3. 손글씨 기초 화면

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/practice/screens/basics_screen.dart` | "올바른 습관 만들기" 화면에서 카드마다 있던 이미지 자리(16:10 비율, 아이콘 36px)를 고정 높이 56px 배너로 축소하고 안팎 여백도 줄여, 스크롤 없이 화면에 꽉 차도록 조정 |

### 4. 피드백 화면

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/feedback/screens/feedback_screen.dart` | ① AppBar에 항상 보이는 홈 이동 버튼 추가 — 기존엔 "학습 기록 저장"을 눌러 완료 상태가 되기 전에는 홈으로 갈 방법이 없었다. ② `analyze-detail` 응답에서 파싱만 되고 화면 어디에도 그려지지 않던 글자별 점수(`CanvasCharAnalysis.overallScore`)를 문자 상세 바텀시트 상단에 "이 글자 점수 N점"으로 표시. ③ 이미지 모드에서 파싱만 되고 화면에 없던 `total_grade`(우수/보통/불량 배지) · `overall_tilt`(전체 기울기 방향) · `clarity_warnings`(명료도 경고 목록)를 점수 카드에 표시 |

### 5. 캔버스 / 문장 연습

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/practice/screens/sentence_practice_screen.dart` | `analyze()` 호출에 `targetText: _sentence.replaceAll(' ', '')` 추가(공백 제거 — 백엔드 음절 단위 획순 채점과 정합). 배경 안내 문구(첫 줄)의 글자별 렌더링 위치를 `TextPainter`(`getBoxesForSelection`)로 계산하는 `_computeCharPositions()` 추가, `analyze()` 호출 시 `charPositions`로 함께 전송 |
| `frontend/lib/features/canvas_mode/services/canvas_api_service.dart` | `analyze()`에 `charPositions` 파라미터 추가, 요청 바디에 `char_positions` 필드로 포함. ⚠️ 백엔드 `CanvasAnalyzeRequest` 스키마엔 아직 이 필드가 없어 현재는 전송만 되고 무시된다(pydantic 기본 동작상 에러는 안 남) — 백엔드가 이 좌표를 실제로 쓰려면 별도 스키마/로직 작업 필요 |

### 6. 라우팅 — 화면 전환 크래시 수정

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/shared/router/app_router.dart` | `/feedback` 라우트가 `state.extra as Map<String, dynamic>`로 non-nullable 캐스팅을 하고 있어서, **브라우저 새로고침/뒤로·앞으로가기 등으로 `extra` 없이 이 라우트에 도달하면(특히 Flutter web) 즉시 크래시**가 나던 문제 수정. `redirect`를 추가해 `extra`가 없으면 크래시 대신 홈(`/main`)으로 보내도록 처리 |

### 7. 로그인 세션 유지 (새로고침 시 로그아웃되던 문제)

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/auth/providers/auth_controller.dart` | `AuthController.build()`가 항상 `AuthInitial`(로그인 안 됨)로 시작해서, Firebase가 실제로 세션을 유지하고 있어도(웹은 IndexedDB) 새로고침/재시작마다 로그인 화면으로 튕겨나가던 버그 수정. `!useMockApi`면 시작 상태를 `AuthLoading`으로 두고, `FirebaseAuth.instance.authStateChanges()`의 첫 값으로 세션 유무를 확인해 있으면 `/auth/login`을 다시 호출해 `AuthAuthenticated`로 복원(없으면 `AuthInitial`로 전환) |
| `frontend/lib/shared/router/app_router.dart` | redirect 로직에 `authState is AuthLoading`이면(=세션 복원 중) 리다이렉트를 보류하고 원래 있던 화면에 그대로 머무르는 분기 추가 — 없으면 복원 전에 `/login`으로 튕겼다가 복원 후 다시 원래 화면으로 돌아오는 깜빡임이 있었다. 결과: **첫 로그인**(온보딩 미완료)은 `/onboarding`으로, **로그인 기록 있는 새로고침**은 로그인 화면을 거치지 않고 바로 원래 화면 유지, **진짜 로그아웃 상태**는 정상적으로 `/login` |

### 8. 홈 화면 — 0일 출석 시 독려 문구

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/home/screens/home_screen.dart` | `_StreakBanner`가 연속 출석일이 0일이어도 "N일동안 연속으로 출석하셨어요"처럼 출석을 전제로 한 문구만 보여주던 것을, `days == 0`일 때 "연습해요!" / "아직 오늘 출석 기록이 없어요. 짧게라도 오늘 한 번 써볼까요? 할 수 있어요!"로 분기. 의미 없던 "D-0" 배지도 "시작 전"으로 변경 |

---

### 참고 — 프론트 코드는 아님

로컬 테스트 중 두 차례 백엔드가 안 되는 문제가 있었는데, 둘 다 코드가 아니라 로컬
환경/의존성 문제였다(참고용으로만 기록, 커밋되는 프론트 변경 아님):

1. `backend/.env`에 2026-08-12에 이미 `backend/app/core/config.py`의 `Settings`에서
   제거된(채점 계수를 AI 쪽으로 일원화하며 삭제) `CANVAS_*`/`IMAGE_*_WEIGHT` 8개 키가
   그대로 남아있어 pydantic-settings가 `extra_forbidden`으로 기동을 막고 있었다 — 8개
   키 삭제로 해결.
2. 팀원 커밋으로 새로 들어온 `backend/app/core/kakao.py`가 `httpx`를 쓰는데
   `requirements.txt`에 빠져 있고 로컬 venv에도 미설치 상태였다. `uvicorn --reload`가
   파일 변경을 감지해 재로드하다 `ModuleNotFoundError`로 죽으면서 포트만 붙잡고 응답을
   안 해 로그인이 "로딩중"에서 멈췄다 — venv에 `httpx` 설치로 해결. **`requirements.txt`에
   `httpx` 추가는 백엔드 쪽에서 처리 필요.**

---

## 2026-08-11 세션

### 변경된 파일 요약

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
> 남기고 되돌려졌다. 백엔드가 필요한 항목은 전부 [범위 밖](#범위-밖--보류-항목-2026-08-11) 절에
> 정리했다(원래 `mypage_upgrade.md`/`analysis_upgrade.md` 두 파일로 나눠 관리하다가 이
> 문서로 통합하며 삭제함).

### 1. 온보딩

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/onboarding/screens/onboarding_screen.dart` | 목표 선택 콘텐츠(제목+칩)를 화면 세로 정중앙에 배치(내용이 넘치면 스크롤). "시작하기" 클릭 시 `saveOnboardingCompleted()` 호출 추가 |
| `frontend/lib/features/onboarding/providers/onboarding_provider.dart` | `onboardingCompletedProvider`가 순수 인메모리 상태라 앱 재시작/새로고침마다 온보딩이 다시 떴던 문제 수정. `loadOnboardingCompleted()`/`saveOnboardingCompleted()`로 `SharedPreferences` 영속화 |
| `frontend/lib/main.dart` | `runApp` 전에 `loadOnboardingCompleted()`를 미리 읽어 `onboardingCompletedProvider`를 override — 라우터 redirect가 첫 프레임부터 정확히 판단하도록 (로그인 기록 있으면 온보딩 건너뜀) |

### 2. 홈 화면 / 하단 탭 구조

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/home/screens/home_screen.dart` | 우측 상단 레벨/아바타 영역 탭 시 마이페이지로 이동. `GET /api/v1/dashboard`를 호출해 레벨·연속 출석일을 실제 값으로 표시(이전엔 `'LV5'`/`21일` 하드코딩) |
| `frontend/lib/features/shell/main_shell.dart` | 하단 탭(홈/분석/마이) 상태를 `StatefulShellRoute`로 전환 — 각 탭이 실제 URL(`/main`, `/main/analysis`, `/main/mypage`)을 가져서 브라우저 새로고침해도 마지막 탭이 유지됨(이전엔 순수 앱 상태라 새로고침하면 항상 홈 탭으로 리셋) |
| `frontend/lib/shared/router/app_router.dart` | 위 셸 라우트 구조 반영 + `/achievements`, `/profile-edit` 라우트 추가 |
| `frontend/lib/features/dashboard/models/dashboard_response.dart` | 백엔드가 이미 보내고 있던 `level`/`streak_days` 필드를 프론트 모델이 안 읽고 있던 버그 수정 |

### 3. 마이페이지

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

### 4. 분석 화면 ("나의 글씨 분석")

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/analysis/screens/analysis_screen.dart` | 연속 출석 실제 값(`data.streakDays`) 연동(이전엔 `21` 하드코딩). "추가 연습이 필요한 글자" 카드의 "연습" 버튼을 `item.mode`에 따라 캔버스/이미지 연습 화면으로 이동하도록 연결(어떤 *글자*로 보낼지는 §범위 밖 참고). 성장 그래프 전용으로 `mode=all` 데이터를 별도 조회해 토글과 무관하게 두 계열이 항상 같이 보이도록 함. 실전 연습 계열 색을 블루(`#3B82F6`)로 바꿔 글씨 연습(teal)과 뚜렷이 구분 |
| `frontend/lib/features/dashboard/widgets/score_trend_chart.dart` | **버그 수정**: 범례엔 "글씨 연습"/"실전 연습" 2계열이 있었는데 실제로는 `mode`를 무시하고 한 가지 색 선 하나만 그리고 있었음. mode별로 나눠서 각자의 선을 실제 날짜 축 기준으로 동시에 그리도록 재작성 |
| `frontend/lib/features/dashboard/screens/report_screen.dart` | 향상률 표시를 공용 규칙으로 통일(아래 §향상률 참고). 추세 아이콘이 항상 상승 화살표였던 것을 방향에 맞게 수정 |
| `frontend/lib/features/dashboard/utils/improvement_rate_format.dart` *(신규)* | `formatImprovementRate()` — 향상률이 음수면 `-`만 표시, 0 이상이면 `+N%`(0은 `0%`)로 표시. analysis/report/achievement 화면에 공통 적용 |
| `frontend/lib/features/dashboard/screens/dashboard_screen.dart` | 어느 라우트에도 연결 안 된 죽은 화면(미사용) — `ScoreTrendChart` 시그니처 변경으로 컴파일이 깨져서 최소한으로 같이 고침 |

### 5. 캔버스 · 문장 연습 화면

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/canvas_mode/screens/canvas_input_screen.dart` | 뒤로가기를 항상 `/main`(홈)으로 명시적 이동(기존 `BackButton()`은 go_router `context.go()` 진입 화면에서 동작이 예측 불가능할 수 있었음). `_submit()`이 `targetText: _currentChar`를 같이 보내도록 준비(§범위 밖 참고 — 백엔드 미반영) |
| `frontend/lib/features/canvas_mode/services/canvas_api_service.dart` | `analyze()`에 `targetText` 파라미터 추가 + 백엔드가 받아야 할 스키마/라우트 변경사항을 상세 주석으로 남김(§범위 밖) |
| `frontend/lib/features/practice/screens/sentence_practice_screen.dart` | 뒤로가기 → 홈 이동(위와 동일 이유). "짧은 문장" 탭 예문을 완전한 문장 대신 형용사+명사 구(句)인 `'시원한 선풍기'`로 교체 |

### 6. 피드백 화면 (교정 결과)

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/feedback/screens/feedback_screen.dart` | **버그 수정**: 우측 "AI 분석" 패널이 백엔드 `weak_habits` 필드(스키마에 아예 없어 항상 빈 배열)만 보고 있어서 항상 "준비 중"만 표시했음 — 이미 왼쪽 오버레이가 쓰는 실제 문자별 피드백(`_canvasItems`/`_imageItems`)을 우측에도 같은 색으로 표시하도록 수정. `char_0` 같은 내부 식별자 텍스트 제거. 캔버스 모드는 한 문자의 피드백 문장(획순/자간/크기)을 문장 단위로 나눠 각각 줄바꿈+개별 색으로 표시 |
| `frontend/lib/features/feedback/utils/canvas_feedback_parser.dart` *(신규)* | 백엔드가 획순/자간/크기 피드백을 공백으로 이어붙인 문자열 하나(+단일 severity)로만 주는 것을 프론트가 문장 단위로 재분해. **키워드 기반**("획순"/"자간"/"글자+크기(%)"로 주제 판별, "오류"→빨강/"적절·정확·균일"→초록/그 외→주황)이라 백엔드 문구가 조금 바뀌어도 안정적으로 동작. 실제 예시로 검증 완료 |

### 범위 밖 — 보류 항목 (2026-08-11)

#### 취약 글자 단위 타겟팅 (분석 화면 "추가 연습이 필요한 글자")

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

> ✅ 2026-08-19 `9abaffe`, 2026-08-30 이후 세션에서 `target_text`/`char_positions` 전송까지는
> 프론트가 마저 구현했다(§5, §7 "2026-08-22 ~ 08-30 세션" 참고). 다만 여러 세션에 걸친
> 글자별 집계·`weak_chars` 노출은 이 문서 작성 시점 기준 아직 없다.

#### 캔버스 AI 분석 오류 (근본 원인 — 이 세션 시점엔 백엔드 미수정)

> ✅ **2026-08-11 `ab9de5a`로 해결됨** — `analyze-detail`이 `analyze_canvas_writing()`을 직접
> 호출하도록 바뀌면서 목표 글자(`target_text`)를 세션에 저장하고 표준 획순도 AI의 유니코드
> 산술로 만든다. 아래는 이 세션(같은 날 더 이른 시점) 기준 기록.

`/canvas/{id}/analyze-detail`가 항상 `get_standard(db, char=None)`으로 표준 획순을
조회해서 (목표 글자를 몰라서) 표준 획순이 항상 빈 배열이 되고, 그 결과 실제로 몇 획을
쓰든 "획이 N개 더 많습니다"류의 의미 없는 메시지만 나온다. 프론트는 목표 글자를
보낼 준비(§5 canvas_input_screen.dart)까지만 해뒀고, 백엔드가 이를 받아서
`get_standard()` 호출에 반영하는 부분은 되돌려져 있다.

#### 나의 성취도 — 배지 · 개별 세션 기록

- **배지**: `requirement.md`에 "종합 점수 90점 이상 시 성취 배지(Badge) 이벤트" 언급만
  있고, 배지 카탈로그·달성 판정·저장·API가 백엔드 어디에도 없다. 화면엔 "준비 중" 카드만
  넣어뒀다.
- **개별 세션 기록 목록**("몇월 며칠에 무엇을 써서 몇 점 받았는지" 같은 목록): 대시보드
  응답은 집계값만 주고, 세션 단위로 조회하는 엔드포인트가 없다.

#### 프로필 관리 — 서버 저장

닉네임/사진 편집 화면은 만들었지만, 백엔드에 프로필 수정 API(`PATCH /api/v1/auth/profile`
같은)가 없어서 `SharedPreferences`로 이 기기에만 저장된다. 다른 기기·재설치 시 유지되지
않는다.

#### 알림 설정 — 발송 자체

카테고리별 토글 UI는 프론트만으로 만들 수 있지만(로컬 저장), 실제로 알림이 오고 안 오게
하려면 FCM 연동과 서버 측 사용자별 알림 설정 저장이 필요하다. 지금은 메뉴 자체를 비활성
표시만 해뒀다.

#### 데이터 초기화 — 서버 반영

> ✅ 2026-08-22 이후 세션에서 이 메뉴 자체를 삭제했다(§1 "2026-08-22 ~ 08-30 세션" 참고) —
> 백엔드 엔드포인트가 끝내 추가되지 않아, 항상 실패하는 버튼을 두는 대신 UI에서 뺐다.

`SettingsApiService.resetHistory()`가 부르는 `DELETE /api/v1/user/history`는 아직
백엔드에 없다(계정 삭제 API와는 별개로, 계정은 유지한 채 학습 기록만 지우는 엔드포인트가
필요). 지금 버튼을 누르면 실패로 안내된다.

### 관련 문서

- [DATA_FLOW.md](DATA_FLOW.md) — AI·백엔드·프론트 값 흐름 전체 대조표
- [BACKEND_CHANGES.md](BACKEND_CHANGES.md) *(master 브랜치)* — 백엔드 쪽 최근 수정 내역
