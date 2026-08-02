# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> 이 저장소(`2026-hanium-project/`)는 한이음 손글씨 교정 플랫폼입니다. 이 폴더는 그중
> **AI 파트(`ai/`)** 작업 공간(sparse clone, 브랜치 `feature/ai-setup`)입니다. `backend/`·
> `frontend/`는 형제 디렉토리이며 AI는 이들과 **3개 함수 계약**으로만 연결됩니다(아래 아키텍처).

## 먼저 읽을 것 (사전 지식 없는 새 세션)

`HANDOFF.md`(전체 지도 — 무엇이 어디 있고 뭐가 되고 안 되는지) → `STATUS.md`(현재 상태·남은
일의 **단일 출처**) 순서로 읽으면 처음부터 다시 조사하지 않고 이어갈 수 있습니다. 설계 배경은
`IMPLEMENTATION_PLAN.md`, 개발 서사는 `DEVLOG.md`.

## 명령어

모든 명령은 **git 루트(`2026-hanium-project/`)에서 venv 파이썬으로** 실행합니다. 이유: 코드가
`from ai.detection...` 같은 **절대 import**를 쓰므로 CWD가 `ai/`의 부모여야 하고, `cv2`·`torch`는
**venv에만** 설치돼 있습니다(시스템 python3에는 없음).

```bash
P=ai/venv/bin/python          # (Windows 로컬은 ai/venv/Scripts/python.exe)

# 테스트 (전체 / 단일)
$P -m pytest ai/tests -q
$P -m pytest ai/tests/test_scoring.py::test_total_grade_thresholds

# 탐지 정확도 평가 (F1@0.3/0.5 + count_ratio + merge/split 분리)
$P ai/eval/evaluate_detection.py            # AI Hub 양식지는 --aihub 지정 시에만 포함
# 실측 도구
$P ai/eval/measure_latency.py               # 500ms 목표 대비 레이턴시
$P ai/eval/measure_resize.py                # 전처리 리사이즈 정책 실측

# 디버그 시각화 (전처리 전후 / CRAFT 탐지 / GT / E2E 배포경로)
$P ai/debug_preprocess.py
$P ai/debug_craft.py
$P ai/debug_e2e_image_mode.py               # 백엔드 어댑터 경로 그대로 전처리→탐지→평가
```

> 파인튜닝 학습 코드(`ai/training/`)와 그 도구(`debug_gt.py`·`debug_compare_production.py`)는 3회 실패 후
> 2026-07-31에 트리에서 제거했습니다. 복원은 `git checkout ec3f0fb -- ai/training`. 재도전 방침은 STATUS §4·DEVLOG 13막.

**설치**는 `ai/requirements.txt` 상단 절차를 그대로 따를 것. Python 3.14 환경의 두 함정이
있어 단순 `pip install -r`만으로는 CRAFT import가 깨집니다: ① `opencv-python-headless`는
**4.x 고정**(5.x는 `HoughLinesP`/`connectedComponents`가 바뀌어 `craft_detector.py`가 깨짐),
② `craft-text-detector==0.4.3`은 잘못된 opencv 핀 때문에 **`--no-deps`로 따로 설치** 후
`vgg16_bn.py` 1줄 패치 필요(requirements.txt 주석에 정확한 수정 위치).

**GT 라벨링**은 `/gt-labeling` 스킬(`.claude/skills/gt-labeling/SKILL.md`)을 쓸 것 — 브라우저
GUI로 사람이 blob을 음절로 묶어 `groups.json`을 만들고 `label_helper.py`가 GT로 빌드합니다.
AI가 이미지를 판독하지 않아 토큰을 거의 안 쓰고 흘림에도 정확합니다.

## 아키텍처 (big picture)

**두 개의 완전히 독립된 파이프라인** — `requirement.md`가 로직 공유를 명시적으로 금지합니다.

- **이미지 모드** (카메라로 찍은 손글씨 사진):
  `preprocessing/image_preprocessor.py`(측지 재구성 기반 전처리 — 비침·괘선을 획으로 승격하지
  않음) → `detection/craft_detector.py`(CRAFT 문자 영역 탐지, `poly=False`로 호출) →
  `analysis/handwriting_analyzer.py`의 `analyze_size_angle()`(행 분류 후 크기·기울기·자간·
  행간·기준선 채점).
- **캔버스 모드** (태블릿 획 데이터): `canvas/` — 실사용자 데이터가 없어 **규칙 기반**.
  `stroke_grouping.py`(획→문자 그룹핑) → `canvas_quality_analyzer.py`의
  `analyze_canvas_writing()`(획순·크기·자간). `stroke_standards.py`는 유니코드 산술로
  **11,172자 전체**의 표준 획순을 외부 데이터 없이 다룹니다.

**백엔드 계약 (절대 준수)**: AI는 `backend/app/services/ai_adapters.py`의 3개 함수
`craft_detect_chars` / `lstm_refine_grouping` / `lstm_analyze_stroke_order`로만 연결됩니다.
**함수 이름·파라미터·반환 형식은 바꾸지 말고 내부 구현만 교체**하세요. 스펙과 JSON 형식은
`AI_MODEL_INTERFACE.md`.

몇 가지 반드시 알아야 할 비자명한 사실:

- **패키지 import 규약**: `ai/__init__.py`는 의도적으로 아무것도 eager-import하지 않습니다.
  `torch`/CRAFT는 이미지 모드 경로에서만 lazy 로드되므로 캔버스 경로는 torch 없이 import
  가능합니다. 그래서 코드·테스트·스크립트는 항상 `from ai.<sub>...` 절대경로를 쓰고 git
  루트에서 실행합니다.
- **모델 가중치**: 이 sparse clone에는 `models/*.pth`가 **없어** CRAFT는 자동으로
  pretrained(`craft_mlt_25k.pth`, gdown 다운로드)로 폴백합니다. 손글씨 도메인 파인튜닝은
  3회 시도 전부 pretrained보다 낮아 **미배포**입니다 — 재시도 전 `archive/
  IMPLEMENTATION_HISTORY.md` Phase 5~12(특히 "배포 클래스로 검증"이라는 교훈)를 반드시 읽으세요.
- **좌표계**: 전처리가 deskew·리사이즈를 하므로 탐지 bbox는 **"전처리 후" 좌표계**입니다.
  오버레이(프론트)는 **전처리 이미지 위에** 그리기로 확정됨 — 원본 사진 위에 그리면 전부
  어긋납니다(통합 첫날 터지는 버그).
- **획순 함수가 둘 공존**: `lstm_analyze_stroke_order`는 백엔드 계약용 **스텁**(개수 비교)이고,
  실제로 동작하는 것은 `canvas_quality_analyzer.analyze_stroke_order_by_position`(위치+모양
  기하 비교)입니다. "획순 분석이 안 된다"고 헷갈리지 마세요.
- **평가 채점 규칙**: 종합점수는 5개 지표(높이균일·기울기·자간·행간·기준선)의 **교육적 가중
  평균(3:2:1)**입니다. 명료도(clarity)와 절대 규범(`norm_deviations`)은 **점수 미반영·경고만**.
  지표 정의는 `handwriting_evaluation.md`, 규범 임계값 근거는 `NORM_STROKE_RESEARCH.md`.

## 환경 함정

- `cv2.imread`/`imwrite`는 **한글 경로에서 조용히 실패**합니다(Windows). 반드시 `imencode`/
  `imdecode`(`np.frombuffer`) 방식을 쓰세요 — 모든 `debug_*.py`가 이미 이 패턴입니다.
- 한글/이모지가 포함된 `print()`가 콘솔 인코딩 때문에 깨지면 `PYTHONIOENCODING=utf-8`로 실행.

---

# 문서 작성 규칙 (AI 파트)

## 정리 요청에 새 문서를 만들지 않는다 (사용자 지시, 2026-07-24)

"정리해줘 / 저장해줘 / 기록해줘" 요청을 받으면 **새 `.md` 파일을 만들지 말고, 아래 표에 따라
기존 문서에 성격별로 나눠 넣고 최신화한다.**

특히 `SESSION_*.md` · `SUMMARY_*.md` · `NOTES_*.md` 같은 **날짜/세션 단위 파일은 만들지 말 것.**
(2026-07-23 세션 정리를 `SESSION_2026-07-23.md`로 만들었다가, 이 규칙에 따라 해체·배분함.)

### 어디에 넣나

| 내용 성격 | 문서 |
|---|---|
| 무엇을·왜 했는지, 문제→원인→해결, 배운 점(🔑/🐛) | `DEVLOG.md` — 시간순 "N막"에 추가 |
| 남은 일 · 미결 · 팀 논의 · 우선순위 · 상태 배지 | `STATUS.md` — **남은 일의 단일 출처** |
| 현재 상태 요약, 날짜별 현황, 파일 지도, 통합 함정 | `HANDOFF.md` |
| 설계 결정과 그 배경 · 구현 계획 | `IMPLEMENTATION_PLAN.md` |
| 백엔드와의 함수 계약 | `AI_MODEL_INTERFACE.md` (시그니처 변경 금지) |
| 평가 지표 정의 / 규범·획순 문헌 근거 | `handwriting_evaluation.md` / `NORM_STROKE_RESEARCH.md` |
| 반복 작업의 절차·관례 | `.claude/skills/<name>/SKILL.md` |
| 끝나서 보존만 할 상세 원본 | `archive/` |

한 세션의 내용은 보통 **여러 문서로 쪼개져** 들어간다(한 일→DEVLOG, 남은 일→STATUS, 요약→HANDOFF).
한 곳에 몰아넣지 말 것.

### 시간순으로 쓴다

문서 안에서는 **최대한 시간순**으로 배치한다. 새 내용은 뒤에 이어 붙이고, 옛 내용을 흩뜨리지 않는다.
- `DEVLOG.md` — 새 "N막"을 **맨 뒤에** 추가. 한 막 안에서도 실제로 일어난 순서대로 쓰고,
  🔑 교훈은 **그 교훈이 나온 작업 바로 뒤**에 둔다(마지막에 몰아 붙이지 말 것).
- `HANDOFF.md` — 날짜별 항목을 시간순으로 이어 붙인다.
- 앞 항목의 "최신" 표시·낡은 수치는 새 항목을 추가할 때 **같이 옮기고 고친다.**
- `STATUS.md`는 예외 — 시간순이 아니라 **영역별 트래커**다(§1 이미지 / §2 캔버스 / §3 통합).

### DEVLOG에는 문답도 남긴다

`DEVLOG.md`에는 코드 변경뿐 아니라 **사용자가 물어본 것과 그에 대한 답변·판단 근거**를
"문답 ①/②/③" 형식으로 상세히 기록한다. 결론만 남기면 전제가 바뀌었을 때 다시 판단할 수 없다.
무엇을 물었는지, 무엇이라고 답했는지, **왜 그렇게 판단했는지**(대안을 왜 안 골랐는지 포함)를 쓴다.

### 배분하면서 최신화도 같이

기존 문서의 **낡은 수치·날짜·"최신" 표시를 함께 고친다.** 숫자는 문서끼리 베끼지 말고
**실제 데이터에서 확인**할 것(`eval/gt/*.json` 등). 실제로 2026-07-23 2차 검수로 test4가
238→239음절이 됐는데 DEVLOG·HANDOFF엔 옛 숫자가 남아 있었다.

### 예외

사용자가 **파일 이름을 직접 지정**했거나, 기존 어느 문서에도 성격이 맞지 않는 새로운 종류의
산출물일 때만 새 파일을 만든다. 이 경우 **만들기 전에 사용자에게 확인**하고, 만들었으면
`HANDOFF.md` §0(문서 읽는 순서)과 §2(파일 지도)에 등록한다.
