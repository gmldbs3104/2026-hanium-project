# AI 손글씨 교정 플랫폼 — 시스템 기능 요구사항 (SFR)

## 1. 개요

본 시스템은 메인 화면에서 두 가지 분석 모드로 분기됩니다.

- **캔버스 모드**: 앱 내에서 직접 필기 → 획 좌표 데이터 기반 분석 파이프라인
- **이미지 모드**: 카메라 촬영 → 이미지 기반 분석 파이프라인

두 모드는 입력부터 분석까지 완전히 독립된 파이프라인을 가지며, 피드백 생성(SFR-007) 및 데이터 저장(SFR-009) 단계에서 합류합니다.

```
[캔버스 모드]                    [이미지 모드]
획 좌표 데이터                   카메라 이미지
      ↓                               ↓
획 그룹핑 (규칙/LSTM)           OpenCV 전처리
    (SFR-003C)                    (SFR-003I)
      ↓                               ↓
획순/자간/크기 분석              CRAFT Bounding Box
    (SFR-004C)                    (SFR-004I)
      ↓                               ↓
                              크기 균일성/기울기 분석
                                  (SFR-005I)
      ↓                               ↓
              피드백 생성 (SFR-007)
                       ↓
              데이터 저장 (SFR-009)
```

본 SFR은 이후 시스템 아키텍처 설계(SDD), 상세 설계, 구현 단계의 기준 문서로 활용됩니다.

> **AI 트랙 결정 메모 (2026-07-20, 설계 인터뷰 기반 — 상세: `IMPLEMENTATION_PLAN.md`)**
> 아래는 확정된 결정이나 대부분 **구현 예정** 상태입니다. 이 SFR 원문의 수치·서술과 어긋나는
> 부분은 후속 개정 시 이 메모를 우선합니다.
> - **이미지 모드 = 자유 촬영**(OCR·목표 텍스트 없음). SFR-005I의 "표준 서체 대비"는 실제로는
>   **자기 일관성(크기·기울기·간격 균일성) + 절대 규범**으로 운영(표준 자형 비교 아님).
>   기울기는 `minAreaRect`가 아니라 **문장 기울기(행별 박스 중심선 회귀, 수평 이탈 |평균각도|)**로
>   측정 (정정 2026-07: 옛 "세로획 slant"도 폐기).
> - **절대 규범(별도 축)**: 자간·기울기·행간이 "일반적인 글 형식"을 벗어나면 경고 —
>   기울기=수직(0°) 이탈, 자간=띄어쓰기 뭉개짐(자간 분포 이봉성으로 감지), 행간=줄 겹침.
>   자기 일관성 점수와 **분리 표시**. 근거값은 필기 교본/조판 규범으로 확정 예정.
> - **종합점수(SFR-005I)** = 지표별 점수 + 교육적 가중(정렬·균일 우선 **3:2:1**),
>   **명료도는 경고만**(점수 제외).
> - **레이턴시**: `REQ-004I-1`(500ms)·`REQ-005C-4`(문자당 300ms)는 실측(CRAFT CPU 1.8~9.7초)
>   기준으로 **하향 개정 예정**(또는 비동기 처리). GPU 배포는 인프라 결정 후.
> - **표준 서체(SFR-005C, `myeongjo`)** = 자형 비교의 **기하 기준점**(코드의 자모 기하 템플릿).
>   획순 표준은 논쟁 자모에 **복수 정본(정본+대안) 허용**.
> - **범위**: 이번 산출물 = 두 모드 분석 + 학습 대시보드(SFR-008)까지. 수행계획서의 개인화·
>   실시간 영상(YOLO)·OCR 텍스트 변환·자유필기 획순 채점은 초기 기획 청사진(이번 범위 밖).

> ### ⚠️ 명세와 구현이 어긋난 조항 (2026-09-02 기준 · **팀 결정 대기**)
>
> 아래 조항들은 **구현이 명세를 따르지 않습니다.** 명세를 고칠지 구현을 되돌릴지는 팀 결정
> 사항이라, 여기에 기록만 하고 SFR 원문은 그대로 둡니다. 배경은 `DEVLOG.md` 30~32막.
>
> | 조항 | 명세 | 구현 (2026-09-02) |
> |---|---|---|
> | `REQ-004C-1` | 규칙 기반 + **LSTM** 2단계 파이프라인 | **규칙 기반 1단계.** LSTM 스텁은 2026-09-01 제거 |
> | `REQ-005C-3` | 획 좌표를 **LSTM 모델에 투입** | **기하 비교**(위치+모양 매칭). 모델 없음 |
> | `REQ-005C-1` | 획순·자간·크기 **3항목** | **6항목** — 획순·획방향·기울기·성분비율·크기·자간 |
> | SFR-004C/005C Pre-condition | "LSTM 모델 가중치가 로드된 상태" | 해당 없음 |
> | `REQ-005C-1` "독립적으로 분석" | — | ✅ 지켜짐. 기하 매칭이라 **획순이 틀려도 성분비율이 독립**으로 채점됨 |
>
> **왜 LSTM을 걷어냈나** — 실사용자 캔버스 데이터가 **한 건도 없어** 학습이 불가능했고,
> 그동안 두 함수는 이름만 LSTM인 **껍데기**였습니다(그룹핑은 입력을 그대로 반환, 획순은 개수
> 비교). 새 채점이 전부 기하 계산으로 풀리면서 껍데기를 유지할 이유가 사라졌습니다.
> **실사용 경로는 2026-08-11부터 이미 이 둘을 안 쓰고 있었습니다** — 명세와의 간극은 그때
> 생겼고, 2026-09-01에 코드에서 껍데기를 치운 것입니다.
>
> 되살릴 경우의 함수 시그니처는 `AI_MODEL_INTERFACE.md` §1·§2에 계약 기록으로 남겨뒀습니다.
>
> **이미지 모드(SFR-005I)도 지표 정의가 바뀌었습니다** — "기울기"가 줄 오르내림에서
> **글자끼리의 균일성**으로, "기준선 이탈도"가 **줄 정렬**(수평 + 잔차)로 재정의됐습니다.
> 상세는 `handwriting_evaluation.md` 지표 ②·⑤.

---

## 2. 기능 목록 요약

| ID | 기능명 | 모드 | 연관 SFR | 우선순위 |
| --- | --- | --- | --- | --- |
| SFR-001 | 사용자 인증 및 계정 관리 | 공통 | — | 🔴 High |
| SFR-002 | 메인 화면 모드 분기 | 공통 | SFR-003C, SFR-003I | 🔴 High |
| SFR-003C | 캔버스 손글씨 입력 및 획 수집 | 캔버스 | SFR-004C | 🔴 High |
| SFR-004C | 획 그룹핑 및 문자 단위 분할 | 캔버스 | SFR-005C | 🔴 High |
| SFR-005C | 획순 / 자간 / 크기 분석 | 캔버스 | SFR-007 | 🔴 High |
| SFR-003I | 카메라 이미지 입력 및 OpenCV 전처리 | 이미지 | SFR-004I | 🔴 High |
| SFR-004I | CRAFT 기반 Bounding Box 탐지 | 이미지 | SFR-005I | 🔴 High |
| SFR-005I | 크기 균일성 / 기울기 분석 | 이미지 | SFR-007 | 🔴 High |
| SFR-007 | 교정 피드백 생성 및 UI 표시 | 공통 | SFR-009 | 🔴 High |
| SFR-008 | 학습 관리 대시보드 조회 | 공통 | SFR-009 | 🟡 Medium |
| SFR-009 | 학습 데이터 저장 및 클라우드 동기화 | 공통 | SFR-007, SFR-008 | 🔴 High |

---

## 3. 시스템 기능 요구사항 상세

### SFR-001 · 사용자 인증 및 계정 관리

| 속성 | 내용 |
| --- | --- |
| **Function** | 사용자 인증 및 계정 관리 (User Authentication & Account Management) |
| **Description** | 소셜 계정(Google, 카카오)을 통한 OAuth 2.0 기반 사용자 인증을 처리하고, Firebase Authentication을 이용해 세션 토큰을 발급·검증·갱신하며 사용자 프로필 데이터를 안전하게 관리한다. |
| **Inputs** | 소셜 로그인 제공자 선택값 (Google / Kakao), OAuth 인가 코드 (Authorization Code), 디바이스 식별자 (Device ID) |
| **Source** | 모바일 앱 로그인 UI (Flutter), 소셜 로그인 제공자 (Google OAuth / Kakao OAuth) |
| **Outputs** | Firebase ID Token (JWT), Refresh Token, 사용자 프로필 객체 (UID, 이름, 이메일, 프로필 이미지 URL) |
| **Destination** | 앱 내 상태 관리 레이어 (Flutter Provider/Bloc), PostgreSQL `users` 테이블 |
| **Action** | ① 앱이 선택된 소셜 제공자의 OAuth 2.0 플로우를 시작한다. ② 제공자로부터 인가 코드를 수신한다. ③ Firebase Authentication SDK가 인가 코드를 ID Token으로 교환한다. ④ ID Token을 백엔드 FastAPI 서버에 전달하여 검증한다. ⑤ 신규 사용자라면 PostgreSQL에 프로필 레코드를 생성하고, 기존 사용자라면 `last_login_at`을 업데이트한다. ⑥ 앱에 세션 토큰과 사용자 프로필을 반환한다. |
| **Requirements** | `REQ-001-1` 시스템은 Google 및 Kakao OAuth 2.0 프로토콜을 지원해야 한다.<br>`REQ-001-2` ID Token 유효 기간은 1시간이며 Refresh Token으로 자동 갱신되어야 한다.<br>`REQ-001-3` 모든 토큰 전송은 TLS 1.2 이상으로 암호화되어야 한다.<br>`REQ-001-4` 인증 실패 시 사용자에게 명확한 오류 메시지를 표시해야 한다.<br>`REQ-001-5` 사용자 PII(개인식별정보)는 Firebase 및 PostgreSQL에서 암호화 저장되어야 한다. |
| **Pre-condition** | 사용자가 앱을 설치하고 로그인 화면에 접근한 상태. 인터넷 연결이 활성화되어 있어야 한다. |
| **Post-condition** | 유효한 세션 토큰이 발급되고 앱 내 인증 상태가 `authenticated`로 전환된다. PostgreSQL `users` 테이블에 사용자 레코드가 존재한다. |
| **Side Effects** | 첫 로그인 시 PostgreSQL에 신규 사용자 레코드 생성. 기존 사용자의 `last_login_at` 타임스탬프 갱신. Firebase Firestore에 기본 사용자 설정 문서 초기화. |

---

### SFR-002 · 메인 화면 모드 분기

| 속성 | 내용 |
| --- | --- |
| **Function** | 메인 화면 모드 분기 (Main Screen Mode Branching) |
| **Description** | 인증된 사용자가 메인 화면에서 분석 모드를 선택하면, 선택에 따라 캔버스 파이프라인(SFR-003C) 또는 이미지 파이프라인(SFR-003I)으로 분기한다. 두 파이프라인은 이후 완전히 독립적으로 동작한다. |
| **Inputs** | 사용자 모드 선택 이벤트 (`canvas` / `image`) |
| **Source** | Flutter 앱 메인 화면 UI (모드 선택 버튼) |
| **Outputs** | 선택된 모드 플래그 (`canvas` / `image`), 해당 모드 화면으로의 라우팅 이벤트 |
| **Destination** | SFR-003C (캔버스 모드 선택 시), SFR-003I (이미지 모드 선택 시) |
| **Action** | ① 메인 화면에서 사용자가 '글씨 연습' 또는 '실전 모드' 버튼을 탭한다. ② 앱이 선택된 모드 플래그를 상태 관리 레이어에 저장한다. ③ 해당 모드의 첫 화면으로 라우팅한다. |
| **Requirements** | `REQ-002-1` 메인 화면은 두 가지 모드를 명확히 구분하여 표시해야 한다.<br>`REQ-002-2` 모드 선택 후 해당 화면 전환은 500ms 이내에 완료되어야 한다.<br>`REQ-002-3` 두 모드는 서로 다른 독립된 파이프라인으로 연결되어야 하며, 로직을 공유하지 않아야 한다. |
| **Pre-condition** | 사용자가 SFR-001을 통해 인증된 상태. 메인 화면이 렌더링된 상태여야 한다. |
| **Post-condition** | 선택된 모드 플래그가 앱 상태에 저장되고, 해당 모드의 첫 화면으로 전환된다. |
| **Side Effects** | 모드 선택 이벤트가 Firebase Analytics에 로깅됨. |

---

## ── 캔버스 모드 파이프라인 ──

### SFR-003C · 캔버스 손글씨 입력 및 획 수집 (글씨 연습)

| 속성 | 내용 |
| --- | --- |
| **Function** | 캔버스 손글씨 입력 및 획 수집 (Canvas Handwriting Input & Stroke Collection) |
| **Description** | 사용자가 앱 내 캔버스에서 직접 필기한 터치/스타일러스 입력을 실시간으로 수집한다. 이미지 변환 없이 획 좌표 시퀀스 원본 데이터를 수집하여 이후 획 그룹핑 및 분석 파이프라인에 전달한다. |
| **Inputs** | 터치/스타일러스 이벤트 `[{x, y, pressure, timestamp}]` (획 단위), 캔버스 설정 (캔버스 크기 width×height, 선 굵기, 격자 표시 여부), 분석 시작 트리거 (사용자의 '분석하기' 버튼 탭 이벤트) |
| **Source** | Flutter `CustomPainter` + `GestureDetector` (터치/스타일러스 이벤트) |
| **Outputs** | 획 좌표 시퀀스 `[{stroke_id, points: [{x, y, pressure, timestamp}]}]`, 캔버스 메타데이터 `{width, height, stroke_count}`, 캔버스 스냅샷 PNG (UI 피드백 오버레이 표시 전용, 분석에 미사용) |
| **Destination** | SFR-004C (획 그룹핑 및 문자 단위 분할), SFR-007 (피드백 UI에서 스냅샷 PNG 오버레이 표시 용도) |
| **Action** | ① 사용자가 캔버스에 필기하는 동안 `GestureDetector`의 `onPanUpdate` 이벤트로 `{x, y, pressure, timestamp}`를 실시간 수집하여 stroke 배열에 누적한다. ② 손가락/펜을 뗄 때마다(`onPanEnd`) 하나의 stroke가 완성되고 `stroke_id`가 부여된다. ③ 사용자가 '제출'을 탭하면 앱이 `CustomPainter.toImage()`로 캔버스 스냅샷 PNG를 생성한다 (UI 오버레이 표시 전용). ④ 획 좌표 시퀀스와 캔버스 메타데이터를 FastAPI `/api/v1/canvas/analyze`로 POST 전송한다 (PNG는 서버로 전송하지 않음). ⑤ 서버가 `canvas_session_id`를 발급하고 SFR-004C로 데이터를 전달한다. |
| **Requirements** | `REQ-003C-1` 획 좌표 수집은 60fps 이상의 샘플링 레이트를 유지해야 한다.<br>`REQ-003C-2` 캔버스 스냅샷 PNG는 분석에 사용되지 않으며 UI 피드백 오버레이 표시 전용으로만 활용되어야 한다.<br>`REQ-003C-3` 획 데이터 전송 및 `canvas_session_id` 발급은 '제출' 버튼 탭 후 1초 이내에 완료되어야 한다.<br>`REQ-003C-4` 사용자가 필기 중 한 획 지우기 및 전체 지우기(Clear)를 할 수 있어야 하며 해당 액션은 stroke 배열에 즉시 반영되어야 한다.<br>`REQ-003C-5` 캔버스 실시간 렌더링 중 프레임 드롭 방지를 위해 `RepaintBoundary`를 적용해야 한다.<br>`REQ-003C-6` 이미지 변환·스케일링·노이즈 제거 등 이미지 모드의 전처리 파이프라인(SFR-003I)을 거치지 않아야 한다. |
| **Pre-condition** | 사용자가 SFR-002에서 캔버스 모드를 선택한 상태. 캔버스에 한 획 이상 입력된 상태여야 분석 트리거가 활성화된다. |
| **Post-condition** | `canvas_session_id`가 발급되고 획 시퀀스가 SFR-004C로 전달 준비가 완료된다. 캔버스 스냅샷 PNG가 앱 메모리에 임시 보관되어 SFR-007 피드백 오버레이에 사용된다. |
| **Side Effects** | 획 데이터가 `canvas_session_id`에 연결되어 서버 메모리 캐시에 저장됨 (TTL: 10분). 캔버스 스냅샷 PNG는 세션 종료 시 앱 메모리에서 해제됨. |

---

### SFR-004C · 획 그룹핑 및 문자 단위 분할

| 속성 | 내용 |
| --- | --- |
| **Function** | 획 그룹핑 및 문자 단위 분할 (Stroke Grouping & Character Segmentation) |
| **Description** | SFR-003C에서 수집된 획 좌표 시퀀스를 문자 단위로 그룹핑한다. 규칙 기반(획 간 거리·시간 간격)과 LSTM 기반 시퀀스 모델을 결합하여 각 획이 어느 문자에 속하는지 분류하고, 문자별 획 그룹을 SFR-005C에 전달한다. |
| **Inputs** | 획 좌표 시퀀스 `[{stroke_id, points: [{x, y, pressure, timestamp}]}]` (SFR-003C 출력), `canvas_session_id`, 캔버스 메타데이터 `{width, height}` |
| **Source** | SFR-003C (캔버스 손글씨 입력 및 획 수집) 출력 |
| **Outputs** | 문자별 획 그룹 목록 `[{char_id, strokes: [{stroke_id, points}], bounding_box(x,y,w,h), stroke_count}]`, 그룹핑 신뢰도 점수 |
| **Destination** | SFR-005C (획순 / 자간 / 크기 분석) |
| **Action** | ① `canvas_session_id`에 연결된 획 시퀀스를 수신한다. ② 규칙 기반 1차 그룹핑: 획 간 공간적 거리(Bounding Box 중심 거리)와 시간 간격이 임계값 이하인 획들을 동일 문자 후보로 묶는다. ③ LSTM 기반 2차 분류: 1차 그룹핑 결과를 LSTM 모델에 입력하여 획 순서와 방향 패턴을 기반으로 문자 경계를 재조정한다. ④ 각 문자 그룹에 `char_id`를 부여하고 Bounding Box를 산출한다. ⑤ 그룹핑 신뢰도가 0.5 미만인 경우 저신뢰 플래그를 마킹한다. ⑥ 결과를 SFR-005C로 전달한다. |
| **Requirements** | `REQ-004C-1` 규칙 기반 그룹핑과 LSTM 기반 분류를 순차적으로 적용하는 2단계 파이프라인을 구성해야 한다.<br>`REQ-004C-2` 획 간 거리 및 시간 간격 임계값은 설정 파일로 조정 가능해야 한다.<br>`REQ-004C-3` 그룹핑 처리 시간은 획 수 50개 기준 500ms 이내이어야 한다.<br>`REQ-004C-4` 그룹핑 신뢰도 0.5 미만 결과는 저신뢰 플래그로 마킹하여 SFR-005C 분석 시 참고 정보로 제공해야 한다.<br>`REQ-004C-5` 한글 자모음 결합 규칙(초성·중성·종성)을 그룹핑 로직에 반영해야 한다. |
| **Pre-condition** | SFR-003C가 정상 완료되어 유효한 `canvas_session_id`와 획 시퀀스가 존재해야 한다. LSTM 그룹핑 모델 가중치가 서버에 로드된 상태여야 한다. |
| **Post-condition** | 모든 획이 문자 단위로 그룹핑되고 `char_id`가 부여된다. 문자별 획 그룹 목록이 SFR-005C로 전달 준비가 완료된다. |
| **Side Effects** | 그룹핑 결과가 `canvas_session_id`에 연결되어 서버 메모리 캐시에 저장됨 (TTL: 10분). 저신뢰 그룹이 존재할 경우 SFR-007 피드백 UI에 '일부 문자 인식 불확실' 안내가 표시됨. |

---

### SFR-005C · 획순 / 자간 / 크기 분석

| 속성 | 내용 |
| --- | --- |
| **Function** | 획순 / 자간 / 크기 분석 (Stroke Order / Spacing / Size Analysis — Canvas Mode) |
| **Description** | SFR-004C에서 그룹핑된 문자별 획 데이터를 기반으로 획순(Stroke Order), 자간(Character Spacing), 크기(Character Size) 세 가지 항목을 분석한다. 이미지 변환 없이 획 좌표 원본 데이터를 직접 활용하여 분석 정밀도를 높이고, 필압·속도 데이터를 추가 분석 요소로 활용한다. |
| **Inputs** | 문자별 획 그룹 목록 `[{char_id, strokes, bounding_box, stroke_count}]` (SFR-004C 출력), 표준 서체 ID (myeongjo), `canvas_session_id` |
| **Source** | SFR-004C (획 그룹핑 및 문자 단위 분할) 출력, 표준 획순 데이터베이스 (PostgreSQL `stroke_standards` 테이블) |
| **Outputs** | 캔버스 분석 결과 목록 `[{char_id, stroke_order_result: {expected_sequence, actual_sequence, error_count}, spacing_deviation(px), size_deviation(%), pressure_profile, speed_profile, overall_score(0~100), correction_flags[]}]` |
| **Destination** | SFR-007 (교정 피드백 생성 및 UI 표시), PostgreSQL `canvas_analysis_results` 테이블 |
| **Action** | ① 각 `char_id`에 대해 표준 획순 DB에서 해당 문자의 표준 획순 시퀀스를 조회한다. ② **획순 분석**: 사용자 획의 방향 벡터 시퀀스를 LSTM 모델에 입력하여 표준 획순과 비교하고 오류 횟수 및 위치를 산출한다. ③ **자간 분석**: 인접 문자 그룹의 Bounding Box 간 거리를 측정하여 표준 자간 대비 편차(px)를 산출한다. ④ **크기 분석**: 각 문자 Bounding Box의 높이/너비를 표준 대비 비율(%)로 산출하고 문자 간 크기 균일성을 계산한다. ⑦ 획순·자간·크기 항목을 가중 합산하여 종합 점수(0~100)를 산출한다. ⑧ 결과를 SFR-007과 PostgreSQL에 전달한다. |
| **Requirements** | `REQ-005C-1` 획순, 자간, 크기 세 가지 항목을 모두 독립적으로 분석해야 한다.<br>`REQ-005C-3` 획순 분석은 이미지 기반 contour 분석을 수행하지 않고 획 좌표 원본 데이터를 직접 LSTM 모델에 투입해야 한다.<br>`REQ-005C-4` 종합 분석은 문자당 300ms 이내에 완료되어야 한다.<br>`REQ-005C-5` 표준 획순 DB는 한글 11,172자(완성형) 전체의 획순 시퀀스를 포함해야 한다.<br>`REQ-005C-6` 각 항목의 가중치는 설정 파일로 조정 가능해야 한다. |
| **Pre-condition** | SFR-004C가 정상 완료되어 유효한 문자별 획 그룹 목록이 존재해야 한다. 사용자가 표준 서체를 선택한 상태여야 한다. LSTM 분석 모델 가중치가 서버에 로드된 상태여야 한다. |
| **Post-condition** | 모든 `char_id`에 대한 획순·자간·크기 분석 결과가 생성된다. 결과가 PostgreSQL `canvas_analysis_results` 테이블에 저장된다. SFR-007이 트리거될 데이터가 준비된다. |
| **Side Effects** | PostgreSQL `canvas_analysis_results` 테이블에 레코드 삽입. 사용자 누적 약점 패턴 통계가 갱신됨. 종합 점수 90점 이상 시 성취 이벤트 플래그가 설정됨. |

---

## ── 이미지 모드 파이프라인 ──

### SFR-003I · 카메라 이미지 입력 및 OpenCV 전처리

| 속성 | 내용 |
| --- | --- |
| **Function** | 카메라 이미지 입력 및 OpenCV 전처리 (Camera Image Input & OpenCV Preprocessing) |
| **Description** | 사용자가 카메라로 촬영한 손글씨 이미지를 수신하고, OpenCV를 이용한 노이즈 제거·이진화·기울기 보정 등의 전처리를 수행하여 CRAFT 문자 탐지에 최적화된 형태로 변환한다. |
| **Inputs** | 원본 손글씨 이미지 (JPEG/PNG, 최대 10MB), 입력 방식 플래그 (`camera`), 선택적 관심영역(ROI) 좌표 |
| **Source** | Flutter 앱의 카메라 모듈 (`camera` 패키지) |
| **Outputs** | 전처리 완료 이미지 (Grayscale PNG, 원본 해상도 유지 — **정정 2026-07**: 옛 "표준화 해상도 1280×960"은 폐기하고 A방향(원본 해상도 유지·장축<800이면만 업스케일·다운스케일 없음)으로 개정), 이미지 품질 점수 (0~100), 전처리 메타데이터 (적용된 필터 목록, 감지된 기울기 각도) |
| **Destination** | SFR-004I (CRAFT 기반 Bounding Box 탐지), FastAPI 서버 임시 스토리지 (`/tmp` 디렉터리) |
| **Action** | ① 앱에서 이미지를 Base64 인코딩하여 FastAPI `/api/v1/image/preprocess`로 POST 전송한다. ② 서버가 Base64를 디코딩하여 OpenCV Mat 객체로 변환한다. ③ **(정정 2026-07)** 채널 max 그레이 변환 → 조명 정규화 → 측지 재구성(morphological geodesic reconstruction)으로 비침을 제거하되, 진한 앵커 유무에 따라 gentle(연한 글씨 보존)/geodesic 경로를 이미지별로 라우팅한다. (옛 "Grayscale → Gaussian Blur → Adaptive Thresholding 이진화"는 연한 글씨가 지워져 폐기.) ④ Hough Transform으로 기울기를 감지하고 자동 회전 보정한다. ⑤ **(정정 2026-07)** 다운스케일을 폐기하고 원본 해상도를 유지한다(A방향: 장축<800이면만 업스케일, 다운스케일 없음). 옛 "표준 해상도(1280×960) 리사이즈"는 소형 글자 손실로 폐기. ⑥ 품질 점수를 산출하고 40점 미만이면 재촬영을 요청한다. |
| **Requirements** | `REQ-003I-1` 전처리 파이프라인은 5초 이내에 완료되어야 한다.<br>`REQ-003I-2` JPEG, PNG를 지원하며 최대 파일 크기는 10MB이다.<br>`REQ-003I-3` 기울기 보정 범위는 ±45° 이내이어야 한다.<br>`REQ-003I-4` 품질 점수가 40점 미만인 경우 분석을 중단하고 재촬영을 요구해야 한다.<br>`REQ-003I-5` 전처리된 이미지는 처리 완료 후 24시간 내 자동 삭제되어야 한다.<br>`REQ-003I-6` 캔버스 모드의 파이프라인(SFR-003C 이후)과 로직을 공유하지 않아야 한다. |
| **Pre-condition** | 사용자가 SFR-002에서 이미지 모드를 선택한 상태. 촬영된 이미지 파일이 존재해야 한다. |
| **Post-condition** | 전처리된 이미지가 서버 임시 경로에 저장되고 고유한 `image_session_id`가 발급된다. 품질 점수가 40점 이상인 경우에만 SFR-004I가 트리거된다. |
| **Side Effects** | 서버 `/tmp`에 임시 파일 생성 (TTL 24시간). 품질이 낮을 경우 앱 UI에 재촬영 안내 팝업이 표시됨. |

---

### SFR-004I · CRAFT 기반 Bounding Box 탐지

| 속성 | 내용 |
| --- | --- |
| **Function** | CRAFT 기반 Bounding Box 탐지 (CRAFT-based Character Region Detection) |
| **Description** | 전처리된 손글씨 이미지에서 CRAFT(Character Region Awareness for Text Detection) 모델을 이용하여 개별 문자 및 단어 단위의 Bounding Box를 탐지한다. CRAFT는 문자 영역(character region)과 문자 간 연결성(affinity)을 동시에 예측하여 손글씨처럼 불규칙한 텍스트에 강인한 탐지를 수행한다. |
| **Inputs** | 전처리 완료 이미지 (SFR-003I 출력), `image_session_id` |
| **Source** | SFR-003I (카메라 이미지 입력 및 OpenCV 전처리) 출력 |
| **Outputs** | 문자 탐지 결과 목록 `[{char_id, bounding_box(x,y,w,h), region_score, affinity_score, char_image_patch}]`, 탐지된 문자 수, 평균 탐지 신뢰도 |
| **Destination** | SFR-005I (크기 균일성 / 기울기 분석) |
| **Action** | ① SFR-003I로부터 전처리 이미지와 `image_session_id`를 수신한다. ② CRAFT 모델이 이미지를 입력받아 문자 영역 히트맵(region score map)과 연결성 히트맵(affinity score map)을 생성한다. ③ 두 히트맵을 결합하여 문자 단위 Bounding Box를 산출한다. ④ region_score 0.5 미만의 탐지 결과를 필터링한다. ⑤ 각 Bounding Box 영역을 크롭하여 문자 패치 이미지를 생성한다. ⑥ 탐지된 문자들을 좌상단 기준 읽기 순서(행 우선)로 정렬한다. ⑦ 결과를 SFR-005I로 전달한다. |
| **Requirements** | `REQ-004I-1` CRAFT 모델의 단일 이미지 추론 시간은 500ms 이내이어야 한다. **(정정 2026-07: CPU 실측 미달 — 하향 개정/GPU 배포 협의 대상.)**<br>`REQ-004I-2` 손글씨 환경에서 문자 탐지 정확도는 검증 데이터셋 기준 85% 이상이어야 한다.<br>`REQ-004I-3` region_score 임계값은 기본 0.5이며 설정 파일로 조정 가능해야 한다.<br>`REQ-004I-4` **(정정 2026-07)** 탐지된 Bounding Box 정보는 **전처리 후 좌표계** 기준으로 반환되어야 한다(오버레이는 전처리 이미지 위에 그림 — 인터뷰 결정). 옛 "원본 이미지 좌표계"는 deskew·리사이즈로 어긋나 폐기.<br>`REQ-004I-5` 탐지 문자 수가 0인 경우 사용자에게 '글씨를 인식할 수 없습니다' 오류를 반환해야 한다. |
| **Pre-condition** | SFR-003I의 전처리가 성공적으로 완료되어 유효한 `image_session_id`가 존재해야 한다. CRAFT 모델 가중치가 서버에 로드된 상태여야 한다. |
| **Post-condition** | 하나 이상의 문자 Bounding Box가 탐지되고 `char_id`가 부여된다. 각 문자 패치 이미지가 메모리 또는 임시 경로에 저장된다. SFR-005I가 트리거된다. |
| **Side Effects** | 탐지 결과가 `image_session_id`에 연결된 서버 메모리 캐시에 저장됨 (TTL: 10분). GPU 메모리를 점유하며 동시 추론 요청은 최대 큐 크기(10)로 제한됨. |

---

### SFR-005I · 크기 균일성 / 기울기 분석

| 속성 | 내용 |
| --- | --- |
| **Function** | 크기 균일성 / 기울기 분석 (Size Uniformity & Slant Analysis — Image Mode) |
| **Description** | SFR-004I에서 탐지된 문자 Bounding Box 데이터를 기반으로 문자 크기 균일성과 기울기를 분석한다. 전체 손글씨의 일관성을 평가하는 데 중점을 두며, 개별 문자보다 문서 전체 수준의 가독성 품질을 측정한다. |
| **Inputs** | 문자 탐지 결과 목록 `[{char_id, bounding_box, char_image_patch}]` (SFR-004I 출력), `image_session_id`, 사용자 선택 표준 서체 ID |
| **Source** | SFR-004I (CRAFT 기반 Bounding Box 탐지) 출력, 표준 서체 데이터베이스 (PostgreSQL `font_standards` 테이블) |
| **Outputs** | 이미지 분석 결과 `{session_level: {size_uniformity_score(0~100), avg_slant_angle(°), slant_consistency_score(0~100), line_alignment_score(0~100)}, char_level: [{char_id, size_deviation(%), slant_angle(°), correction_flags[]}], overall_score(0~100)}` |
| **Destination** | SFR-007 (교정 피드백 생성 및 UI 표시), PostgreSQL `image_analysis_results` 테이블 |
| **Action** | ① 탐지된 모든 문자 Bounding Box의 높이/너비를 수집한다. ② **크기 균일성 분석**: 전체 문자 높이의 평균과 표준편차를 산출하여 균일성 점수를 계산한다. 표준 서체 대비 각 문자의 크기 편차(%)를 산출한다. ③ **기울기 분석 (정정 2026-07)**: 옛 "글자별 주축 각도를 OpenCV `minAreaRect`/세로획 slant로 측정"은 폐기하고, **문장 기울기 = 행별 글자 박스 중심선의 회귀 기울기(수평 0° 이탈, |평균각도|°)**로 산출한다. 개별 글자 slant의 σ가 아니라 행별 중심선 회귀로 문장이 수평에서 벗어난 정도를 측정한다. ④ **행 정렬 분석**: 동일 행으로 분류된 문자들의 기준선(baseline) 편차를 측정하여 정렬 점수를 산출한다. ⑤ 크기 균일성·기울기 일관성·행 정렬 점수를 가중 합산하여 종합 점수(0~100)를 산출한다. ⑥ 결과를 SFR-007과 PostgreSQL에 전달한다. |
| **Requirements** | `REQ-005I-1` 크기 균일성, 기울기, 행 정렬 세 가지 항목을 모두 독립적으로 분석해야 한다.<br>`REQ-005I-2` 세션 수준(전체 손글씨)과 문자 수준(개별 문자) 두 가지 단위로 결과를 제공해야 한다.<br>`REQ-005I-3` 종합 분석은 탐지 문자 50자 기준 2초 이내에 완료되어야 한다.<br>`REQ-005I-4` 캔버스 모드의 분석 파이프라인(SFR-005C)과 로직을 공유하지 않아야 한다.<br>`REQ-005I-5` 종합 점수는 0~100 정수로 표현되며 각 항목의 가중치는 설정 파일로 조정 가능해야 한다. |
| **Pre-condition** | SFR-004I가 정상 완료되어 유효한 문자 탐지 결과가 존재해야 한다. 탐지된 문자 수가 3개 이상이어야 균일성 분석이 의미 있는 결과를 산출할 수 있다. |
| **Post-condition** | 세션 수준 및 문자 수준 분석 결과가 생성된다. 결과가 PostgreSQL `image_analysis_results` 테이블에 저장된다. SFR-007이 트리거된다. |
| **Side Effects** | PostgreSQL `image_analysis_results` 테이블에 레코드 삽입. 사용자 누적 약점 패턴 통계가 갱신됨. 탐지 문자 수가 3개 미만인 경우 SFR-007에 '분석 데이터 부족' 안내가 전달됨. |

---

## ── 공통 파이프라인 ──

### SFR-007 · 교정 피드백 생성 및 UI 표시

| 속성 | 내용 |
| --- | --- |
| **Function** | 교정 피드백 생성 및 UI 표시 (Correction Feedback Generation & Display) |
| **Description** | 캔버스 모드(SFR-005C) 또는 이미지 모드(SFR-005I)의 분석 결과를 수신하여 사용자에게 시각적 교정 피드백을 제공한다. 캔버스 모드는 캔버스 스냅샷 위에, 이미지 모드는 원본 이미지 위에 Flutter Canvas 오버레이를 렌더링한다. 두 모드의 결과 데이터 구조가 다르므로 모드별 렌더링 로직을 분리하여 처리한다. |
| **Inputs** | 분석 결과 객체 (SFR-005C 또는 SFR-005I 출력), 입력 모드 플래그 (`canvas` / `image`), 배경 이미지 (캔버스 스냅샷 PNG 또는 원본 촬영 이미지), UI 테마 설정 (light / dark) |
| **Source** | SFR-005C (캔버스 모드 분석 결과) 또는 SFR-005I (이미지 모드 분석 결과) |
| **Outputs** | 교정 오버레이 렌더링 데이터 (Canvas 드로잉 명령 목록), 피드백 텍스트 목록 `[{target_id, feedback_message, severity(info/warning/error)}]`, 종합 결과 요약 `{overall_score, achievement_message, mode}` |
| **Destination** | Flutter 앱의 Canvas 렌더링 레이어, 앱 UI 피드백 패널, SFR-009 (저장 트리거) |
| **Action** | ① 입력 모드 플래그를 확인하여 렌더링 로직을 분기한다. ② **[canvas 모드]** UI 로딩한 후 화면 왼편에 피드백 제공한다. 캔버스 스냅샷 PNG 위에 획순 오류 위치에 번호 레이블, 자간 오류 위치에 간격 표시 화살표, 크기 오류 문자에 색상 하이라이트를 오버레이한다. ③ **[이미지 모드]** UI 로딩한 후 화면 왼편에 피드백 제공한다. + 이미지 위에 박스 친 부분까지는 표시. 원본 이미지 위에 문자별 Bounding Box에 severity 색상 하이라이트(🔴 error, 🟡 warning, 🟢 good), 기울기 오류 문자에 교정 방향 화살표를 오버레이한다. ④ 각 교정 항목에 대한 자연어 피드백 메시지를 한국어로 생성한다. ⑤ 종합 점수에 따라 성취 메시지를 선택한다. ⑥ 최종 렌더링 데이터를 앱으로 반환한다. |
| **Requirements** | `REQ-007-1` 피드백 UI는 분석 완료 후 1초 이내에 화면에 표시되어야 한다.<br>`REQ-007-2` 캔버스 모드와 이미지 모드의 렌더링 로직은 분리되어야 하며, 각 모드의 분석 결과 데이터 구조에 맞게 처리해야 한다.<br>`REQ-007-3` 오버레이는 error(빨강), warning(노랑), good(초록) 세 가지 severity 레벨을 색상으로 구분해야 한다.<br>`REQ-007-4` 사용자가 개별 항목을 탭하면 해당 항목의 상세 교정 내용이 팝업으로 표시되어야 한다.<br>`REQ-007-5` 피드백 메시지는 한국어로 제공되며 향후 다국어 확장을 위한 i18n 구조를 유지해야 한다.<br>`REQ-007-6` 색맹 사용자를 위한 보조 아이콘을 색상 하이라이트와 함께 표시해야 한다. |
| **Pre-condition** | SFR-005C 또는 SFR-005I의 분석이 정상 완료되어 분석 결과 데이터가 존재해야 한다. 배경 이미지(캔버스 스냅샷 또는 원본 이미지)가 앱 메모리에 존재해야 한다. |
| **Post-condition** | 교정 오버레이가 배경 이미지 위에 렌더링된다. 피드백 패널에 종합 점수와 항목별 안내 메시지가 표시된다. 사용자가 피드백을 확인(confirm)하면 SFR-009가 트리거된다. |
| **Side Effects** | 학습 이벤트 로그가 Firebase Analytics에 전송됨. 종합 점수 90점 이상 시 앱 내 성취 배지(Badge) 이벤트가 발생함. |

---

### SFR-008 · 학습 관리 대시보드 조회

| 속성 | 내용 |
| --- | --- |
| **Function** | 학습 관리 대시보드 조회 (Learning Dashboard Retrieval) |
| **Description** | 사용자의 누적 교정 이력 데이터를 집계하여 일별/월별 교정 통계, 취약 항목 분석, 개선 추이 그래프, 맞춤형 연습 예문을 대시보드 형태로 제공한다. 캔버스 모드(`canvas_analysis_results`)와 이미지 모드(`image_analysis_results`) 데이터를 모두 집계하여 통합 통계를 제공한다. |
| **Inputs** | 사용자 UID (인증 토큰에서 추출), 조회 기간 (`period`: week / month / all), 모드 필터 (`mode`: canvas / image / all) |
| **Source** | Flutter 앱 대시보드 화면, 사용자 인증 토큰 (SFR-001 출력) |
| **Outputs** | 대시보드 데이터 객체 `{period_summary: {total_sessions, avg_score, improvement_rate(%), canvas_sessions, image_sessions}, weak_items: [{item, avg_score, frequency, mode}], score_trend: [{date, avg_score, mode}], recommended_exercises: [{text, target_items[], difficulty, mode}]}` |
| **Destination** | Flutter 앱 대시보드 UI (차트 및 리스트 위젯) |
| **Action** | ① 앱이 인증 토큰과 함께 FastAPI `/api/v1/dashboard`에 GET 요청을 전송한다. ② 서버가 토큰에서 UID를 추출하고 권한을 검증한다. ③ 모드 필터에 따라 `canvas_analysis_results` 및/또는 `image_analysis_results` 테이블을 GROUP BY 쿼리로 집계한다. ④ 취약 항목 목록을 평균 점수 오름차순으로 정렬하고 상위 10개를 선택한다. ⑤ 날짜별 평균 점수를 산출하여 추이 데이터를 구성한다. ⑥ 취약 항목을 기반으로 연습 예문 DB에서 맞춤 예문을 조회한다. ⑦ 집계 결과를 JSON으로 직렬화하여 앱에 반환한다. |
| **Requirements** | `REQ-008-1` 대시보드 데이터 로딩 시간은 3초 이내이어야 한다.<br>`REQ-008-2` 캔버스 모드와 이미지 모드의 데이터를 통합하여 집계하되, 모드별 필터링도 지원해야 한다.<br>`REQ-008-3` 취약 항목은 최근 30일 데이터 기준으로 평균 점수 하위 10개를 표시해야 한다.<br>`REQ-008-4` 맞춤 연습 예문은 취약 항목을 포함하는 문장 3~5개를 난이도 순으로 추천해야 한다.<br>`REQ-008-5` 데이터가 없는 경우(신규 사용자) 온보딩 안내 메시지를 표시해야 한다. |
| **Pre-condition** | 사용자가 SFR-001을 통해 인증된 상태이어야 한다. 최소 1회 이상의 교정 세션 이력이 존재해야 통계가 표시된다 (없으면 온보딩 뷰 표시). |
| **Post-condition** | 대시보드 UI에 기간별 통계, 취약 항목 차트, 개선 추이 그래프, 추천 예문이 렌더링된다. |
| **Side Effects** | 집계 결과가 인메모리 캐시에 저장됨 (TTL: 1시간). 캐시 히트 시 DB 쿼리 없이 응답. |

---

### SFR-009 · 학습 데이터 저장 및 클라우드 동기화

| 속성 | 내용 |
| --- | --- |
| **Function** | 학습 데이터 저장 및 클라우드 동기화 (Learning Data Storage & Cloud Sync) |
| **Description** | 교정 세션이 완료될 때마다 분석 결과를 PostgreSQL에 영구 저장하고 Firebase Firestore와 동기화하여 멀티 디바이스 접근을 지원한다. 캔버스 모드와 이미지 모드의 결과는 각각 독립된 테이블에 저장된다. |
| **Inputs** | 교정 세션 결과 객체 `{session_id, user_id, mode(canvas/image), timestamp, analysis_results, overall_score}`, 이미지 저장 동의 여부 (`save_image: boolean`, 이미지 모드 한정) |
| **Source** | SFR-007 (교정 피드백 확인 이벤트) |
| **Outputs** | 저장 완료 응답 `{session_id, saved_at, mode}`, 동기화 상태 `{firestore_synced: boolean, s3_uploaded: boolean}` |
| **Destination** | PostgreSQL `canvas_analysis_results` 또는 `image_analysis_results` 테이블, Firebase Firestore (`user_sessions` 컬렉션), AWS S3 (이미지 모드 + 동의 시) |
| **Action** | ① 피드백 확인 이벤트와 모드 플래그를 수신하고 저장 트랜잭션을 시작한다. ② 모드에 따라 대상 테이블을 선택한다 (`canvas_analysis_results` 또는 `image_analysis_results`). ③ 해당 테이블에 세션 메타데이터와 분석 결과를 배치 INSERT한다. ④ 이미지 모드이고 `save_image: true`인 경우, 원본 이미지를 AWS S3 `{user_id}/{session_id}/original.jpg`에 업로드한다. ⑤ Firebase Firestore의 `user_sessions/{user_id}/sessions`에 세션 요약 문서를 upsert한다. ⑥ PostgreSQL 트랜잭션을 커밋하고 저장 완료 응답을 반환한다. ⑦ 저장 실패 시 롤백하고 재시도 큐에 추가한다. |
| **Requirements** | `REQ-009-1` PostgreSQL 저장 작업은 ACID 트랜잭션으로 처리되어야 한다.<br>`REQ-009-2` 저장 완료까지의 응답 시간은 2초 이내이어야 한다.<br>`REQ-009-3` 캔버스 모드와 이미지 모드의 분석 결과는 각각 독립된 테이블에 저장되어야 한다.<br>`REQ-009-4` 이미지 저장은 이미지 모드에서 사용자의 명시적 동의가 있을 경우에만 수행되어야 한다.<br>`REQ-009-5` 네트워크 장애 시 로컬 큐에 저장하고 연결 복구 후 자동으로 재전송(Retry)해야 한다.<br>`REQ-009-6` AWS S3에 저장된 이미지는 SSE-S3 서버 측 암호화가 적용되어야 한다.<br>`REQ-009-7` 사용자가 계정 삭제를 요청할 경우 30일 이내 모든 개인 데이터(DB 레코드, S3 이미지)를 영구 삭제해야 한다. |
| **Pre-condition** | SFR-007의 피드백이 사용자에게 표시되고 사용자가 '확인' 버튼을 탭한 상태여야 한다. 네트워크가 연결된 상태이거나 로컬 큐 메커니즘이 활성화된 상태여야 한다. |
| **Post-condition** | 학습 세션 데이터가 모드에 맞는 PostgreSQL 테이블에 영구 저장된다. Firebase Firestore에 세션 요약이 동기화된다. SFR-008 대시보드의 캐시가 무효화(Invalidate)된다. |
| **Side Effects** | SFR-008 대시보드 캐시가 무효화되어 다음 조회 시 DB에서 신선한 데이터를 로드함. Firebase Firestore 실시간 리스너를 통해 다른 디바이스의 대시보드가 자동 갱신됨. |

---

## 4. 용어 정의 및 약어

| 약어/용어 | 정의 |
| --- | --- |
| SFR | System Functional Requirement — 시스템이 제공해야 하는 기능에 대한 요구사항 |
| CRAFT | Character Region Awareness for Text Detection — 문자 영역과 연결성을 동시에 예측하는 텍스트 탐지 모델 |
| LSTM | Long Short-Term Memory — 시퀀스 데이터 처리에 특화된 순환 신경망 구조 |
| Stroke | 펜/손가락을 대고 뗄 때까지의 연속된 좌표 시퀀스 (한 획) |
| JWT | JSON Web Token — 사용자 인증을 위한 서명된 토큰 형식 |
| ACID | Atomicity, Consistency, Isolation, Durability — 데이터베이스 트랜잭션 신뢰성 원칙 |
| TLS | Transport Layer Security — 네트워크 통신 암호화 프로토콜 |
| TTL | Time To Live — 데이터의 유효 보존 기간 |
| i18n | Internationalization — 다국어 지원을 위한 소프트웨어 설계 원칙 |
| SSE-S3 | Server-Side Encryption with S3 Managed Keys — AWS S3 서버 측 암호화 |
| ROI | Region of Interest — 관심 영역 |
| NMS | Non-Maximum Suppression — 중복된 객체 탐지 박스를 제거하는 알고리즘 |
| Affinity Map | CRAFT 모델이 생성하는 인접 문자 간 연결성 히트맵 |
| Baseline | 텍스트 줄의 기준선 |
