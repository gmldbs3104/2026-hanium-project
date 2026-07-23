# AI 모듈 인수인계 문서 (HANDOFF)

> 2026 한이음 드림업 — AI 손글씨 교정 플랫폼
> 최종 갱신: 2026-07-21 (문서 구조 재편 — 남은 일은 `STATUS.md`, 개발 서사는 `DEVLOG.md`)
> **이 문서는 새로운 세션(계정 변경 등으로 이전 대화 기록이 없는 상태)이 처음 열었을 때
> 가장 먼저 읽어야 할 문서입니다.** 아래 순서대로 읽으면 지금까지의 판단 근거와 현재
> 상태를 처음부터 다시 조사하지 않고도 파악할 수 있습니다.

## ⚡ 최신 현황 요약 (2026-07-18 ~ 07-19)

상세 경위는 `archive/DETECTION_IMPROVEMENT_PLAN.md` 11~17단계 진행 기록 참고. 핵심만:

1. **탐지 정확도** — 손글씨 공식 평가셋 4장(test/test2/test3_crop/test6, 수동 GT
   197음절, 2차 검수 완료): **평균 F1@0.3 0.968 / F1@0.5 0.946**. 평가 실행:
   `ai/venv/Scripts/python.exe eval/evaluate_detection.py` (AI Hub 양식지는 `--aihub`
   지정 시에만 포함).
2. **기울기 측정 개편 (16단계)** — minAreaRect 폐기 → 세로획 slant(HoughLinesP) +
   신뢰도 게이트(`angle_reliable`). 개별 slant를 전체 중앙값과 비교해 ±10° 초과
   이탈 글자는 흘림으로 보고 통계 제외(이상치 조정). 기울기 피드백은 문서 단위만.
3. **평가 지표 전면 구현 (17단계)** — `handwriting_evaluation.md` 지표 ①~⑥
   (높이·기울기·자간·행간·회귀선 기준선·획 굵기) + **명료도**(탐지 이상 글자 =
   못 쓴 글자로 감점, 통계에서 제외 — 팀 결정) + 지표별 등급·점수·종합 점수.
   지표 ⑦(자소 비율)은 제외 확정. `analyze_size_angle(chars, binary_image=None)`.
4. **E2E 수동 점검** — `ai/debug_e2e_image_mode.py` (백엔드 어댑터 경로 그대로
   전처리→탐지→평가 실행, 4장 종합점수 test 68.2 / test2 80.3 / test3_crop 59.4 /
   test6 63.4).
5. **잔여 과제** — 파인튜닝 재시도(이제 F1 하니스+정밀 GT로 체크포인트 선택 가능),
   test4 GT 확장, GPU/500ms 팀 협의, 백엔드 병합(팀 결정 대기), 윤곽선 이진화
   사진에서 획 굵기 지표 왜곡 보완.

### 2026-07-20 — 설계 인터뷰 결정 (상세·구현 계획: `IMPLEMENTATION_PLAN.md`)

인터뷰로 아래가 확정됨(대부분 **구현 예정**, 코드 미반영):
- **이미지 모드 = 자유 촬영**(OCR 없음): 자기 일관성 + **절대 규범(별도 축 — 기울기 수직 이탈 /
  자간 띄어쓰기 뭉개짐(이봉 분포) / 행간 줄 겹침)**. 규범 근거는 필기 교본/조판.
- **종합점수** = 지표별 + 교육적 가중(정렬·균일 3:2:1), **명료도는 경고만(점수 제외)**.
- **캔버스**: 표준=명조(기하 기준점), 획순 **복수 정본**, 엔진은 **LSTM 교체 목표**(위치기반 임시),
  기간 내 소규모 LSTM 학습 시도. 종합점수는 현행 감점 방식 유지.
- **모델**: pretrained 확정 후 **조건부 파인튜닝 재시도**, 평가셋 확장.
- **성능/통합**: 레이턴시 실측 기반 하향, 오버레이는 **전처리 이미지 기준**(좌표 역변환 불필요),
  백엔드 통합은 협의.
- **범위**: 두 모드 + 학습 대시보드까지. 개인화·실시간 영상·OCR·자유필기 획순은 청사진(범위 밖).

### 2026-07-21 — 2.1 획순 복수 정본 + 3.1 리사이즈 측정 구현 (상세: `IMPLEMENTATION_PLAN.md`)

인터뷰 후 아래를 **구현·검증 완료**(커밋은 대기):
1. **2.1 획순 복수 정본** — 근거 명확한 **ㅌ만** 대안 순열(`[0,2,1]`, 가운데 가로 마지막) 허용.
   `canvas/stroke_standards.py`에 `ALTERNATIVE_STROKE_ORDERS`, 채점부(`canvas_quality_analyzer.
   analyze_stroke_order_by_position`)가 자모 블록별 (표준+대안) 데카르트 곱 중 **최소 오류** 채택.
   대안 수용 시 **감점 없음 + 안내 병기**(`used_alternative_order`, `notes` 필드, "표준 필순은 …").
   ㅋ·ㅂ·ㄹ·ㅅ·ㅎ은 교과서 근거 확보 시 dict 한 줄로 확장(§3 미결). 테스트 5개(TDD) 통과.
2. **3.1 리사이즈 on/off** — `eval/measure_resize.py`로 실측. **리사이즈 제거는 대형 원본에서
   박스 손실+지연 급증** → **현행 유지(리사이즈 on) 확정**. `ImagePreprocessor(apply_resize=False)`
   토글만 자산으로 남김(기본 True, 동작 불변).
3. **검증 인프라** — `tests/test_preprocessor.py` 난수 시드 고정(간헐 실패 제거). 전체 29개 통과.
- ⚠️ **현재 CRAFT는 pretrained**(이 sparse clone엔 `models/*.pth` 없음 → 무조건 pretrained 폴백).
  파인튜닝은 여전히 미배포.

### 2026-07-23 — 평가셋 확장: test4·5·7 독립 GT 라벨링 완료 (상세: `DEVLOG.md` 9막)

1. 평가셋 **4장(197음절) → 7장(536음절)**: test4(238)·test5(39)·test7(62) 수동 라벨링.
   탐지기 미사용 **독립 라벨**(blob 그룹핑). 문장부호 제외, 영문(TEST)은 글자별 1박스.
2. `eval/label_helper.py`에 **blob 분할 기능** 추가(`"splits"`: x/y/격자 절단) — 흘림에서
   음절 경계를 넘는 blob을 잉크 픽셀 tight bbox로 나눔. 기존 groups 형식 하위 호환.
3. test4는 검수 지적(60여 박스) 반영해 2차 검수 완료 — 절단 위치를 잉크 프로파일 골짜기
   기준으로 재조정(경위·교훈은 `DEVLOG.md` 9막).
4. 확장 7장 평균 **F1@0.3 0.938 / F1@0.5 0.894** (기존 4장만은 0.968 — 흘림 포함으로
   상방 편향 축소가 목적이므로 하락은 의도된 것). 흘림 개별 0.87~0.93, 과병합 경향.

---

## 0. 문서 읽는 순서

**살아있는 참조 (자주 읽음 — ai/ 최상위):**
1. **이 문서(`HANDOFF.md`)** — 전체 지도. 무엇이 어디 있는지, 뭐가 되고 뭐가 안 되는지 요약.
2. **`STATUS.md`** — 현재 상태·남은 일·미결·팀논의의 **단일 출처**. "지금 뭐 하면 되나"는 여기.
3. `IMPLEMENTATION_PLAN.md` — 설계 결정 + 구현 계획(배경).
4. `AI_MODEL_INTERFACE.md` — 백엔드와 약속한 함수 시그니처 3개. **함수 이름/파라미터/
   반환 형식은 절대 바꾸면 안 됨** — 내부 구현만 교체 가능.
5. `requirement.md` — 전체 SFR(기능 요구사항) 목록.
6. `handwriting_evaluation.md` — 이미지 모드 평가 지표 정의. `NORM_STROKE_RESEARCH.md` — 규범
   임계값·획순 정본 문헌 근거.
7. `CANVAS_DATA_PLAN.md` (프로젝트 루트) — 캔버스 모드 실사용자 데이터 수집 전략, 팀 논의용.

**회고 (사람용):**
- **`DEVLOG.md`** — 처음부터 지금까지의 개발일지/TIL/트러블슈팅. 왜 이렇게 됐는지 시간순 서사.

**아카이브 (`ai/archive/` — 보존용, 드물게 참조):**
- `archive/IMPLEMENTATION_HISTORY.md` — 이미지 모드 개발사 전체(Phase 1~15). **파인튜닝이 왜
  실패했는지(Phase 12) 다시 시도 전 반드시 읽을 것.**
- `archive/DETECTION_IMPROVEMENT_PLAN.md` — 탐지 개선 17단계 진행기록.
- `archive/2026년_..._수행계획서.md` — 최초 기획서(청사진, 일부는 이제 범위 밖).

**외부 제출용 (`ai/report/`):**
- `report/PROJECT_REPORT_AI.md` (보고서 양식용) · `report/KEY_CODE_SUMMARY.md` (PPT용 압축).

> 이 문서는 **현재 상태 요약(지도)**, `STATUS.md`는 **남은 일(트래커)**, `DEVLOG.md`는 **과거 서사**,
> `archive/`는 **상세 원본**입니다. 서로 대체하지 않고 보완합니다.

---

## 1. 프로젝트 한 줄 요약

사용자가 (1) 카메라로 찍은 손글씨 사진(**이미지 모드**) 또는 (2) 태블릿/터치스크린에 직접
쓴 획 데이터(**캔버스 모드**)를 입력하면, AI가 글자 단위로 분석해서 크기·기울기·자간·
획순 교정 피드백을 만들어주는 게 이 프로젝트의 AI 파트 역할입니다. 이미지 모드와 캔버스
모드는 **완전히 독립된 파이프라인**이며(요구사항 문서가 로직 공유를 명시적으로 금지),
코드도 `ai/detection`·`ai/analysis` (이미지) vs `ai/canvas` (캔버스)로 분리돼 있습니다.

AI 모듈은 백엔드와 **3개의 함수 계약**으로만 연결됩니다(`AI_MODEL_INTERFACE.md`):
`craft_detect_chars`, `lstm_refine_grouping`, `lstm_analyze_stroke_order`.
**2026-07-18: 이 브랜치(feature/ai-setup)에 `backend/app/services/ai_adapters.py` 실구현
연결본을 작성 완료** — 3개 계약 함수가 `ai/` 패키지의 실제 구현으로 연결되고, AI 전처리
드롭인(`preprocess_image`)과 `analyze_size_angle`도 함께 제공됩니다 (상세는 5.1절).

---

## 2. 전체 파일 지도

```
ai/
├── HANDOFF.md                        ← 지금 읽고 있는 문서 (전체 지도)
├── STATUS.md                         ← 현재 상태·남은 일·미결 (단일 출처, 트래커)
├── DEVLOG.md                         ← 개발일지/TIL/트러블슈팅 (회고·복기용)
├── IMPLEMENTATION_PLAN.md            ← 2026-07-20 설계 결정 + 구현 계획
├── AI_MODEL_INTERFACE.md             ← 백엔드 연동 함수 계약 3개 (절대 준수)
├── requirement.md                    ← 전체 SFR 요구사항 원문
├── handwriting_evaluation.md         ← 이미지 모드 평가 지표 정의
├── NORM_STROKE_RESEARCH.md           ← 규범 임계값·획순 정본 문헌 근거
│
├── archive/                          ← 보존용 상세 원본 (드물게 참조)
│   ├── IMPLEMENTATION_HISTORY.md         ← 이미지 모드 개발사 (Phase 1~15, 파인튜닝 실패 경위)
│   ├── DETECTION_IMPROVEMENT_PLAN.md     ← 탐지 개선 17단계 진행기록
│   └── 2026년_..._수행계획서.md          ← 최초 프로젝트 기획서
│
├── report/                           ← 외부 제출용
│   ├── PROJECT_REPORT_AI.md              ← 한이음 보고서 양식용 (이미지 모드만)
│   └── KEY_CODE_SUMMARY.md               ← PPT용 압축 요약
│
├── preprocessing/
│   └── image_preprocessor.py         ← SFR-003I, 완성. 이진화/deskew/품질검사
│
├── detection/
│   └── craft_detector.py             ← SFR-004I, 완성. 현재 pretrained 가중치로 동작 중
│                                        (파인튜닝 가중치는 존재하면 자동 사용, 로드 실패 시
│                                        자동 pretrained 폴백)
│
├── analysis/
│   └── handwriting_analyzer.py       ← SFR-005I, 완성. analyze_size_angle()
│
├── canvas/                           ← 캔버스 모드 (아래 4절에서 상세 설명)
│   ├── stroke_grouping.py            ← SFR-004C 규칙 기반 그룹핑 + lstm_refine_grouping (스텁)
│   ├── stroke_standards.py           ← SFR-005C 표준 획순 데이터 + lstm_analyze_stroke_order (스텁)
│   ├── synthetic_stroke_generator.py ← 합성 학습 데이터 생성 (2단계 학습의 1단계용)
│   ├── canvas_quality_analyzer.py    ← SFR-005C 종합 분석 (실제 동작하는 규칙 기반 구현체)
│   ├── debug_canvas.py               ← 그룹핑/표준데이터 검증 스크립트
│   └── debug_synthetic.py            ← 합성 데이터 생성 검증 스크립트
│
├── training/                         ← CRAFT 파인튜닝 (현재 결과물은 미배포 상태, 12절 참고)
│   ├── craft_model.py                ← clovaai 공식 구조 vendoring (키 호환 검증 완료, 자산으로 남음)
│   ├── gt_generator.py               ← AI Hub 라벨 파싱 + 단어→글자 분할 + score map 생성
│   ├── colab_finetune.py             ← Colab용 학습 스크립트 (현재 미사용, Kaggle로 대체)
│   ├── kaggle_finetune.py            ← Kaggle용 학습 스크립트 (실제 사용됨, resume 지원)
│   └── prepare_kaggle_dataset.py     ← 학습 데이터를 Kaggle Dataset 형태로 패키징
│
├── models/
│   ├── craft_finetuned_epoch9.pth.bak  ← 파인튜닝 최종 결과물이나 **미배포** (pretrained보다 성능 낮음)
│   └── craft_ep007_wrapped.pth.bak     ← 더 이전 파인튜닝 결과물 (참고용 보관)
│   (craft_finetuned_raw.pth가 없으면 craft_detector.py가 자동으로 pretrained 가중치 사용)
│
├── test_images/                      ← test.jpg ~ test7.jpg, 수동 검증용 샘플
├── debug_craft.py                    ← CRAFT 탐지 결과 시각화
├── debug_gt.py                       ← GT score map 시각화 + 체크포인트 collapse 진단
├── debug_analysis.py                 ← SFR-005I 판단 모듈 검증
├── debug_preprocess.py               ← 전처리 전/후 비교 이미지 생성
└── debug_compare_production.py       ← **실제 배포 클래스(CraftDetector)로** pretrained vs
                                          파인튜닝 성능 비교 (반드시 이걸로 검증할 것, 12.5절 참고)
```

---

## 3. 이미지 모드 — 현재 상태 요약

**상세 서술은 `archive/IMPLEMENTATION_HISTORY.md`에 있습니다. 여기서는 결론만.**

| 구성요소 | 상태 |
|---|---|
| 이미지 전처리 (SFR-003I) | ✅ 완성, 정상 동작 |
| CRAFT 글자 탐지 (SFR-004I) | ✅ 완성 — **pretrained + region단독 디코딩(link=1.0) + 적응형 long_size + 과폭 분할 + 자소→음절 병합**. 실사용 유사 3장 평균 F1@0.3=**0.970** (test.jpg 10/10 완벽, 2026-07-18 11단계에서 행 그룹핑·병합 오작동 3건 수정으로 0.960→0.970, 밀집 다행 텍스트의 문단 통짜 박스 문제도 해소). 소형 밀집 글씨는 개선됐으나 한계 잔존. 정량 평가셋/전 과정은 `archive/DETECTION_IMPROVEMENT_PLAN.md` 참고 |
| 손글씨 도메인 CRAFT 파인튜닝 | ❌ 세 차례 시도(도메인 일치 → OHEM → peak-weighted OHEM) 전부 pretrained보다 낮은 성능. **최종 롤백, 미배포** |
| 크기·기울기 판단 (SFR-005I) | ✅ 완성. `craft_detect_chars()` 출력을 그대로 받아 행 분류, 크기 균일성, 기울기, baseline 정렬 분석 |

**CRAFT 파인튜닝이 왜 실패했는지, 무엇을 시도했는지는 `archive/IMPLEMENTATION_HISTORY.md` Phase
5~12를 반드시 읽으세요.** 요약하면:

1. 아키텍처 불일치(학습용 모델 클래스 vs 추론 패키지의 state_dict 키가 다름) → clovaai
   공식 구조를 그대로 복제(vendor)해서 해결
2. 학습/추론 입력 도메인 불일치(학습은 원본 사진, 추론은 이진화+deskew+distance-transform
   이미지) → 학습 파이프라인에도 동일 전처리 적용해서 해결
3. 극심한 배경 클래스 불균형으로 인한 collapse → OHEM 적용해서 해결
4. **val_loss 기준 체크포인트 선택이 실제 탐지 성능과 반대로 움직이는 현상 발견** → GT 피크
   가중치 손실함수 + `peak_quality` 지표로 재시도했으나 **역시 실제 탐지 성능과 상관관계
   없음을 확인**
5. **결정적으로**, 그동안의 모든 검증이 실제 배포 클래스(`CraftDetector`, 기본 threshold
   0.7/0.4/0.4)가 아니라 임의로 낮춘 threshold(0.05)의 커스텀 스크립트로 이뤄지고
   있었다는 것을 뒤늦게 발견. 실제 배포 경로로 재검증하니 **모든 파인튜닝 체크포인트가
   AI Hub 이미지에서도, test_images에서도 전부 0개 탐지**로 나타남 (pretrained는 정상
   동작). 이 시점에 파인튜닝을 최종 포기하고 pretrained로 롤백.

**교훈(중요, 다음에 파인튜닝을 다시 시도한다면 반드시 지킬 것)**: 학습 중 자체 정의한
지표(loss, peak_quality 등)로 체크포인트를 고르지 말고, **매번 실제 배포 클래스를 그대로
호출해서 검증**해야 한다. `debug_compare_production.py`가 이 용도로 만들어져 있음.

---

## 4. 캔버스 모드 — 현재 상태 상세 (이 문서가 유일한 종합 출처)

캔버스 모드는 `requirement.md`의 SFR-003C(프론트엔드 담당, 이 저장소 `ai/`의 범위 밖) →
SFR-004C(획 그룹핑) → SFR-005C(획순/자간/크기 분석) 흐름입니다. **실사용자 필기 데이터가
전혀 없는 상태**에서 시작했기 때문에, ML(LSTM) 학습은 불가능하고 대신 **규칙 기반 알고리즘
+ 프로그래밍적으로 생성한 표준 데이터**로 최대한 구현해뒀습니다.

### 4.1 왜 데이터가 없는가

이미지 모드는 AI Hub에 기존 데이터셋(053 손글씨 OCR)이 있었지만, 캔버스 모드에 필요한
"펜 좌표+시간 기록(온라인 필기 데이터)"은 한국어 공개 데이터셋을 찾지 못했습니다
(`CANVAS_DATA_PLAN.md`에 조사 내용 기록됨). 그래서 **2단계 학습 전략**을 세웠습니다:

```
1단계: 합성 데이터로 pretrain   ← 구현 완료 (synthetic_stroke_generator.py)
2단계: 실사용자 데이터로 fine-tune ← 팀 논의 대기 (데이터 수집 방법이 CANVAS_DATA_PLAN.md에 제안됨)
```

**핵심 아이디어(사용자가 직접 제안, 채택함)**: 앱의 "제시형" 연습 기능("이 글자를
써보세요: 가") 자체가 곧 자동 라벨링 도구가 된다 — 목표 글자를 앱이 이미 알고 있으므로
사용자가 쓴 획 데이터에 정답이 자동으로 붙는다. 별도 데이터 수집 프로젝트가 필요 없고,
서비스가 배포되어 사용자가 연습 기능을 쓰기 시작하는 순간부터 학습 데이터가 쌓인다.

### 4.2 SFR-004C — 획 그룹핑 (`stroke_grouping.py`)

- `group_strokes_by_rules()`: 획 간 bbox 중심 거리 + 시간 간격 임계값으로 클러스터링.
  ML 없이 순수 규칙.
- `group_strokes_into_chars()`: 위 규칙 기반 그룹핑 + 신뢰도 점수 + `low_confidence` 플래그를
  더한 전체 파이프라인. **실제로 쓰이는 함수는 이쪽.**
- `lstm_refine_grouping(stroke_groups)`: `AI_MODEL_INTERFACE.md`가 약속한 백엔드 연동
  함수. **현재는 입력을 그대로 반환하는 placeholder** — 실사용자 데이터 확보 후 LSTM으로
  교체 예정. 정직하게 스텁으로 남겨둔 것이며 가짜로 구현하지 않았음.

### 4.3 SFR-005C 표준 데이터 — `stroke_standards.py`

- 초성 19개·중성 21개·종성 27개 단위로 표준 획순 라벨을 하드코딩.
- `decompose_syllable(char)`: 완성형 한글 음절을 유니코드 산술
  (`syllable_index = (초성idx×21 + 중성idx)×28 + 종성idx`)로 분해 — **외부 데이터셋 없이
  11,172자 전체**를 프로그래밍적으로 다룸.
- `get_expected_sequence(char)`: 음절 분해 → 초성·중성·종성 획순 라벨 연결 (예:
  `["ㄱ_1", "ㅏ_1", "ㅏ_2"]` 형태).
- `lstm_analyze_stroke_order(strokes, expected_sequence)`: `AI_MODEL_INTERFACE.md`가
  약속한 백엔드 연동 함수. **현재는 stroke 개수 비교만 수행하는 단순 placeholder.**

### 4.4 합성 학습 데이터 — `synthetic_stroke_generator.py`

- 자모별 기하학적 획 경로(`_BASE_CONSONANT_PATHS`, `_BASE_VOWEL_PATHS`)와 음절 내 배치
  규칙(`_syllable_layout` — 세로/가로/복합 모음에 따른 레이아웃)을 코드로 정의.
- `generate_synthetic_strokes()` / `generate_synthetic_line()`: 위 템플릿에 손떨림/속도
  노이즈를 섞어 대량 생성 — 1단계 pretrain용 데이터.
- **버그 수정 이력**: 처음에 지터(noise)를 정규화 좌표([0,1])에 더한 뒤 스케일링해서
  노이즈가 100배 증폭되는 버그가 있었음(스케일링 후에 지터를 더하도록 수정). 이 문서
  기록 전까지 실제로 발생했던 실수이니, 좌표 변환 순서를 건드릴 때 주의.

### 4.5 SFR-005C 종합 판정 — `canvas_quality_analyzer.py` (실제 동작하는 핵심 구현체)

**여기가 인터페이스 문서와 실제 구현이 갈라지는 지점이니 주의해서 읽으세요.**

`AI_MODEL_INTERFACE.md`가 문서화한 `lstm_analyze_stroke_order`(단순 개수 비교 스텁)와
별개로, `canvas_quality_analyzer.py`에는 **훨씬 정교하게 실제로 동작하는**
`analyze_stroke_order_by_position()`이 있습니다:

- **아이디어**: "이 획이 무슨 모양인지"를 처음부터 분류하는 대신(그건 진짜 학습 데이터가
  필요한 문제), "제시형" UI라 목표 글자를 이미 안다는 점을 이용해 "N번째로 그린 획이
  표준상 기대되는 위치에 있는가"만 순수 기하 비교로 판단. **학습 데이터 없이도 실질적으로
  동작하는 획순 오류 감지기**입니다.
- 위치(중심점)만 보면 자모 내 서로 가까운 두 획(예: ㅏ의 세로선+가로 짧은 획)을
  헷갈리므로, 모양(가로/세로 bbox 비율, `SHAPE_WEIGHT=1.5`)도 함께 비교.
- **`likely_wrong_character` 안전장치**: 사용자가 목표와 완전히 다른 글자(또는 낙서)를
  쓴 경우, 억지로 정답 템플릿에 끼워 맞춰 "몇 번째 획이 틀렸다"는 세부 피드백을 주면
  오히려 혼란을 주므로, 매칭 오차(`MATCH_QUALITY_THRESHOLD=0.6`)나 획수 비율
  (`COUNT_MISMATCH_RATIO_THRESHOLD=2.0`)이 임계값을 넘으면 세부 피드백 대신 "다시
  확인해주세요" 안내만 반환.
- `analyze_canvas_writing(char_groups, target_text)`: SFR-005C 최종 종합 함수. 크기
  편차, 자간 편차, 위 획순 분석, 필압/속도 통계를 모아 `requirement.md` 스펙 그대로
  (`stroke_order_result`, `spacing_deviation`, `size_deviation`, `pressure_profile`,
  `speed_profile`, `overall_score`, `correction_flags`) 반환. `target_text`가 없으면
  획순 채점은 생략하고 크기/자간만 채점.

**왜 두 개의 획순 분석 함수가 공존하는가**: `lstm_analyze_stroke_order`는 백엔드와의
공식 계약 시그니처를 지키기 위한 자리이고(문서에 이미 "현재: 개수 비교, 교체 목표: LSTM"
로 명시돼 있어 나중에 실사용자 데이터로 LSTM을 학습시키면 이 함수 내부를 교체하는 게
계획), `analyze_stroke_order_by_position`은 **그 전까지 실질적으로 쓸만한 결과를 내기
위한 별도의, 더 나은 근사치**입니다. `analyze_canvas_writing()`은 후자를 사용합니다.
새 세션이 "획순 분석이 안 되는데?"라고 헷갈리지 않도록 기록해둡니다 — 실제로는
`canvas_quality_analyzer.py` 쪽이 진짜 동작하는 구현입니다.

### 4.6 캔버스 모드의 한계 (정직하게 기록)

- 이 모든 규칙 기반 구현은 "제시형"(목표를 먼저 보여주고 따라 쓰게 하는) UI 패턴을
  전제로 합니다. 목표 텍스트를 모르는 자유 필기에서는 획순 채점이 불가능합니다
  (`target_text=None`이면 크기/자간만 채점).
- 위치+모양 기반 매칭은 자모 내 두 획이 극단적으로 겹치거나 사용자가 표준과 완전히 다른
  위치에 그리면 오판할 수 있습니다(코드 docstring에 명시).
- 필압(pressure)은 센서 미지원 기기에서 항상 1.0 고정이라 의미 있는 신호가 아닐 수
  있습니다.
- 실사용자 데이터가 쌓이기 전까지는 이 근사치가 최선이고, `lstm_refine_grouping`/
  `lstm_analyze_stroke_order`의 실제 ML 교체는 데이터 수집 이후 과제로 남아있습니다.

---

## 5. 통합 — 아직 안 된 것 / 알아야 할 함정 모음

### 5.1 아직 안 된 것

- **AI↔백엔드 연동 — 어댑터 구현은 완료(2026-07-18), 백엔드측 반영이 남음.**
  이 브랜치(feature/ai-setup)의 `backend/app/services/ai_adapters.py`에 실구현 연결본이
  있음: 3개 계약 함수(craft_detect_chars → CRAFT 싱글턴 / lstm_* → ai/canvas 구현) +
  `preprocess_image`(백엔드 `image_preprocessing.preprocess_image`와 동일 반환 계약의
  AI 전처리 드롭인, Otsu 도메인 불일치 해소용) + `preprocess_image_full`(REQ-003I-4
  품질/재촬영 판정 포함) + `analyze_size_angle`. 이를 위해 `ai/`를 패키지화(`ai/__init__.py`
  추가, canvas 상대 import 전환)하고 CraftDetector를 프로세스당 1회 로드 싱글턴+Lock으로
  전환함(1차 호출 10.4s → 2차 1.9s 실측). 남은 것:
  1. **브랜치 병합**: `origin/feature/backend-setup`에도 같은 경로에 스텁 버전이 있어
     병합 시 충돌 발생 — **ai-setup 쪽(실구현)을 채택**하면 됨 (계약 문서에 명시된
     의도된 교체).
  2. **백엔드 라우트 반영(백엔드 트랙 결정)**: `image_preprocessing.preprocess_image`를
     어댑터의 AI 전처리로 교체할지, `image_analysis.py`(자체 SFR-005I 구현)를
     `analyze_size_angle`로 교체할지. **탐지 정확도 평가(F1@0.3=0.960)는 전부 AI 전처리
     전제이므로 Otsu 입력과 섞으면 성능 보장 안 됨.**
  3. **좌표계 논의**: AI 전처리는 deskew+리사이즈를 하므로 bbox가 "전처리 후" 좌표계 —
     원본 사진 오버레이(SFR-007)를 위해 역변환 또는 전처리 이미지 기준 오버레이 필요.
  4. **의존성**: 백엔드 requirements.txt에 torch/craft_text_detector 추가 필요
     (canvas 경로는 torch 없이 동작하도록 lazy import 처리돼 있음).
- **캔버스 모드 2단계(실사용자 데이터 fine-tuning)** — 데이터 수집 방법은
  `CANVAS_DATA_PLAN.md`에 제안돼 있으나 팀 논의/구현 전.
- **이미지 모드 CRAFT 파인튜닝** — 3차 시도까지 실패, 근본 원인 미확정(아래 5.2 참고).
- **캔버스 모드의 멀티라인(여러 줄) 처리** — `handwriting_analyzer.py`(이미지 모드)에
  해당하는 행(row) 그룹핑이 캔버스 모드에는 아직 없음. 한 글자씩 연습하는 화면이라면
  당장은 불필요할 수 있음.

### 5.2 CRAFT 파인튜닝 재시도 판단
→ **`STATUS.md` §4(파인튜닝 재도전 판단 메모)** 로 통합. 예전 실패 이유 · 지금 달라진 점 ·
다시 한다면 바꿔볼 가설 · 절대 규칙 · 재사용 자산이 한곳에 정리돼 있음. 상세 원본 경위는
`archive/IMPLEMENTATION_HISTORY.md` §14.6.

### 5.3 개발 환경 관련 함정 (Windows 로컬 개발 시 반복 발생했던 문제)

- **`cv2.imwrite`/`cv2.imread`가 한글 경로에서 조용히 실패**함(Windows). 반드시
  `cv2.imencode` + 수동 파일 쓰기, 또는 바이트 단위로 직접 읽는 방식(`np.frombuffer` +
  `cv2.imdecode`) 사용. 이 저장소의 모든 `debug_*.py`가 이미 이 패턴을 씀 — 새로 스크립트
  짤 때도 그대로 따라할 것.
- PowerShell/cp949 콘솔 인코딩 문제로 한글/이모지 포함 `print()`가 깨지거나 에러날 수
  있음 → `PYTHONIOENCODING=utf-8` 환경변수로 실행.
- Kaggle Internet:Off 환경에서는 `torchvision`의 온라인 ImageNet 가중치 다운로드가 전부
  실패함 — `pretrained_backbone=False`로 고정하고 자체 보유 가중치만 사용.
- AI Hub 데이터셋 경로: `C:\Users\dmack\Downloads\053.대용량 손글씨 OCR 데이터\` (이
  저장소 밖의 별도 다운로드 폴더, 이 세션의 "Additional working directories"로 잡혀있음).

---

## 6. 다음에 할 일 · 우선순위
→ **`STATUS.md`** 로 통합(단일 트래커). 현재 상태·남은 일·미결·팀논의·우선순위가 한곳에 있음.

---

*이 문서는 "새 세션이 아무 사전 지식 없이 읽고 프로젝트를 이어갈 수 있게" 하는 목적으로
작성되었습니다. 코드 자체의 최신 상태는 항상 `git log`와 실제 파일을 우선하고, 이 문서와
어긋나는 부분을 발견하면 이 문서를 업데이트하세요.*
