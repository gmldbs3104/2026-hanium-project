# 프론트엔드 수정 내역 (2026-08-22 ~ 2026-08-30 세션)

이번 세션은 **frontend만 수정**했다 — `backend/`, `ai/`는 건드리지 않기로 방침을 정했고
끝까지 지켰다. 백엔드가 필요한 부분은 각 항목에 "⚠️ 백엔드 미반영" 등으로 표시해뒀다.

## 변경된 파일 요약

| 영역 | 신규 파일 | 수정 파일 |
|---|---|---|
| 마이페이지 | — | `home_screen.dart`, `settings_screen.dart` |
| 대시보드 / 출석 | `dashboard_refresh_provider.dart` | `home_screen.dart`, `feedback_screen.dart`, `dashboard_response.dart`, `analysis_screen.dart` |
| 손글씨 기초 | — | `basics_screen.dart` |
| 피드백 화면 | — | `feedback_screen.dart` |
| 캔버스 / 문장 연습 | — | `sentence_practice_screen.dart`, `canvas_api_service.dart` |
| 라우팅 | — | `app_router.dart` |

파일 경로는 전부 `frontend/lib/features/...` 아래(위 표는 마지막 폴더명만 표기).

---

## 1. 마이페이지 버그 수정

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/home/screens/home_screen.dart` | 마이페이지에서 닉네임을 바꿔도 홈 화면엔 반영이 안 되던 문제 수정 — 마이페이지와 같은 `profileOverrideProvider`(로컬 저장 닉네임)를 보도록 변경 |
| `frontend/lib/features/mypage/screens/settings_screen.dart` | 상세환경설정에서 "데이터 초기화" 행/확인 다이얼로그/관련 상태(`_isResettingData`, `_confirmResetData`)를 완전히 제거. 소셜 계정 연동 표기를 한글 번역("구글"/"카카오"/"애플")에서 서버가 내려주는 provider 원문("google"/"kakao"/"apple") 그대로 표시하도록 변경(`_providerLabel` 함수 삭제) |

## 2. 대시보드 — 출석일 갱신 & 분석 탭 로딩 안정성

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/dashboard/providers/dashboard_refresh_provider.dart` *(신규)* | 대시보드 요약(레벨/연속 출석일) 새로고침 신호(`StateProvider<int>`). 홈 화면은 `StatefulShellRoute`(IndexedStack) 탭이라 연습 후 홈으로 돌아와도 `initState`가 재실행되지 않아, 오늘 첫 연습을 마쳐도 출석일이 "0일"에서 안 바뀌던 문제의 근본 원인이었다 |
| `frontend/lib/features/home/screens/home_screen.dart` | 위 provider를 `ref.listen`으로 감지해 값이 바뀌면 대시보드 요약을 다시 불러오도록 추가 |
| `frontend/lib/features/feedback/screens/feedback_screen.dart` | 피드백 화면에서 "홈으로" 이동할 때(액션바 버튼 + AppBar 버튼 모두) 위 provider를 bump해서 방금 완료한 세션이 출석일에 반영되게 함 |
| `frontend/lib/features/dashboard/models/dashboard_response.dart` | `DashboardResponse`/`PeriodSummary`의 `fromJson`을 널/필드 누락에 방어적으로 수정(없으면 빈 배열/0으로 안전 처리). 기존엔 필드 하나만 없어도(예: 백엔드 스키마 변경 직후 Redis에 남은 구버전 캐시) 예외가 터져 분석 탭 전체가 "분석 데이터를 불러오지 못했습니다"로 죽었다 |
| `frontend/lib/features/analysis/screens/analysis_screen.dart` | 데이터 로딩 실패 시 원인 예외를 삼키기만 하던 `catch (_)`에 `debugPrint`로 실제 예외/스택트레이스를 남기도록 추가 — 이후 같은 문제가 재발해도 콘솔에서 바로 원인 확인 가능 |

## 3. 손글씨 기초 화면

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/practice/screens/basics_screen.dart` | "올바른 습관 만들기" 화면에서 카드마다 있던 이미지 자리(16:10 비율, 아이콘 36px)를 고정 높이 56px 배너로 축소하고 안팎 여백도 줄여, 스크롤 없이 화면에 꽉 차도록 조정 |

## 4. 피드백 화면

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/feedback/screens/feedback_screen.dart` | ① AppBar에 항상 보이는 홈 이동 버튼 추가 — 기존엔 "학습 기록 저장"을 눌러 완료 상태가 되기 전에는 홈으로 갈 방법이 없었다. ② `analyze-detail` 응답에서 파싱만 되고 화면 어디에도 그려지지 않던 글자별 점수(`CanvasCharAnalysis.overallScore`)를 문자 상세 바텀시트 상단에 "이 글자 점수 N점"으로 표시 |

## 5. 캔버스 / 문장 연습

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/features/practice/screens/sentence_practice_screen.dart` | `analyze()` 호출에 `targetText: _sentence.replaceAll(' ', '')` 추가(공백 제거 — 백엔드 음절 단위 획순 채점과 정합). 배경 안내 문구(첫 줄)의 글자별 렌더링 위치를 `TextPainter`(`getBoxesForSelection`)로 계산하는 `_computeCharPositions()` 추가, `analyze()` 호출 시 `charPositions`로 함께 전송 |
| `frontend/lib/features/canvas_mode/services/canvas_api_service.dart` | `analyze()`에 `charPositions` 파라미터 추가, 요청 바디에 `char_positions` 필드로 포함. ⚠️ 백엔드 `CanvasAnalyzeRequest` 스키마엔 아직 이 필드가 없어 현재는 전송만 되고 무시된다(pydantic 기본 동작상 에러는 안 남) — 백엔드가 이 좌표를 실제로 쓰려면 별도 스키마/로직 작업 필요 |

## 6. 라우팅 — 화면 전환 크래시 수정

| 파일 | 변경 내용 |
|---|---|
| `frontend/lib/shared/router/app_router.dart` | `/feedback` 라우트가 `state.extra as Map<String, dynamic>`로 non-nullable 캐스팅을 하고 있어서, **브라우저 새로고침/뒤로·앞으로가기 등으로 `extra` 없이 이 라우트에 도달하면(특히 Flutter web) 즉시 크래시**가 나던 문제 수정. `redirect`를 추가해 `extra`가 없으면 크래시 대신 홈(`/main`)으로 보내도록 처리 |

---

## 참고 — 프론트 코드는 아님

로컬 테스트 중 백엔드가 기동조차 안 되는 문제가 있었다: `backend/.env`에 2026-08-12에
이미 `backend/app/core/config.py`의 `Settings`에서 제거된(채점 계수를 AI 쪽으로 일원화하며
삭제) `CANVAS_*`/`IMAGE_*_WEIGHT` 8개 키가 그대로 남아있어 pydantic-settings가
`extra_forbidden`으로 기동을 막고 있었다. `.env`는 gitignore 대상 로컬 설정 파일이라
버전 관리되지 않으며, 이 8개 키를 지운 것도 프론트 코드 변경은 아니다(참고용으로만 기록).
