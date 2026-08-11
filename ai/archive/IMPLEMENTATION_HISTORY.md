# AI 모듈 구현 과정 전체 기록

> 2026 한이음 드림업 — AI 손글씨 교정 플랫폼
> 최초 작성: 2026-07-08 / 최종 갱신: 2026-07-10
> 대상: SFR-003I(전처리) · SFR-004I(CRAFT 탐지) · SFR-005I(판단) 개발 과정

---

## 목차

1. [프로젝트 목표 요약](#1-프로젝트-목표-요약)
2. [AI 모듈 초기 설계](#2-ai-모듈-초기-설계)
3. [Phase 1 — 이미지 전처리 구현](#3-phase-1--이미지-전처리-구현-sfr-003i)
4. [Phase 2 — 글자 탐지 1차 시도 (OpenCV Contour)](#4-phase-2--글자-탐지-1차-시도-opencv-contour)
5. [Phase 3 — CRAFT Score Map 기반 탐지 (대규모 재설계)](#5-phase-3--craft-score-map-기반-탐지-대규모-재설계)
6. [Phase 4 — 탐지 후처리 튜닝 (자소→음절 병합, 이후 폐기)](#6-phase-4--탐지-후처리-튜닝-자소음절-병합-이후-폐기)
7. [Phase 5 — CRAFT 파인튜닝 1차 시도](#7-phase-5--craft-파인튜닝-1차-시도)
8. [Phase 6 — 1차 파인튜닝 결과 검증 및 실패 진단](#8-phase-6--1차-파인튜닝-결과-검증-및-실패-진단)
9. [Phase 7 — 핸드오프 문서 대조 및 크래시 버그 발견](#9-phase-7--핸드오프-문서-대조-및-크래시-버그-발견)
10. [Phase 8 — 학습 파이프라인 재설계](#10-phase-8--학습-파이프라인-재설계)
11. [Phase 9 — Colab → Kaggle 전환](#11-phase-9--colab--kaggle-전환)
12. [Phase 10 — 2차 파인튜닝(Kaggle 3,500장) — score map은 정상인데 실제 탐지 0개](#12-phase-10--2차-파인튜닝kaggle-3500장--score-map은-정상인데-실제-탐지-0개)
13. [Phase 11 — 3차 파인튜닝(Kaggle 전체 15,314장) 진행 중](#13-phase-11--3차-파인튜닝kaggle-전체-15314장-진행-중)
14. [Phase 12 — 체크포인트 선별 지표 개선 시도 및 파인튜닝 최종 롤백](#14-phase-12--체크포인트-선별-지표-개선-시도-및-파인튜닝-최종-롤백)
15. [현재 상태 및 남은 과제](#15-현재-상태-및-남은-과제)

---

## 1. 프로젝트 목표 요약

**핵심 목적**: 사용자가 카메라로 촬영한 손글씨 이미지를 분석하여 글자 단위 bounding box를 추출하고, 이를 토대로 크기 균일성 · 자간 · 높낮이를 정량적으로 평가해 교정 피드백 제공.

**이미지 모드 파이프라인**:
```
카메라 촬영 → OpenCV 전처리 → CRAFT 글자 탐지 → 크기/간격/높낮이 분석 → 피드백
```

**핵심 성능 요구사항** (SFR 기준):
- CRAFT 추론: 500ms 이내
- 이미지 전처리: 5초 이내
- 이미지 분석 (50자 기준): 2초 이내

**왜 글자(음절) 단위여야 하는가**: `requirement.md`의 SFR-005I는 `char_level: [{char_id, size_deviation, slant_angle, correction_flags}]`처럼 문자별 결과를 정식 요구사항(REQ-005I-2)으로 못박고 있고, Action 단계도 "각 문자 Bounding Box의 주축 각도를 측정", "탐지된 모든 문자"처럼 전부 문자 단위로 서술되어 있다. 단어 단위 박스로는 단어 내부의 글자별 편차(크기·기울기·baseline)를 볼 수 없어 이 요구사항 자체를 충족할 수 없다 — 그래서 어떤 재설계를 거치든 "글자 단위 분리"라는 목표는 계속 유지된다.

---

## 2. AI 모듈 초기 설계

### 2.1 디렉토리 구조 확정 (최초 설계 시점)

```
ai/
├── preprocessing/
│   └── image_preprocessor.py    # SFR-003I
├── detection/
│   └── craft_detector.py        # SFR-004I
├── analysis/
│   └── handwriting_analyzer.py  # SFR-005I (이후 664bae8a 커밋에서 삭제, 미재구현)
├── training/
│   ├── craft_model.py           # CRAFT 모델 정의
│   └── colab_finetune.py        # Colab 학습 스크립트
├── models/
│   └── craft_finetuned_raw.pth  # 파인튜닝 결과 가중치
├── test_images/                 # test.jpg ~ test7.jpg
├── AI_MODEL_INTERFACE.md        # 백엔드 연동 인터페이스 스펙
└── requirement.md               # SFR 전체 목록
```

### 2.2 백엔드 연동 인터페이스 계약

백엔드(`backend/app/services/ai_adapters.py`)와 AI 모듈 간 계약을 먼저 확정.
**함수 시그니처는 절대 변경하지 않고 내부 구현만 교체**하는 원칙.

| 함수 | SFR | 역할 |
|------|-----|------|
| `craft_detect_chars(binary_image_list, width, height)` | SFR-004I | 글자 bbox 탐지 |
| `lstm_refine_grouping(stroke_groups)` | SFR-004C | 획 그룹핑 보정 |
| `lstm_analyze_stroke_order(strokes, expected)` | SFR-005C | 획순 분석 |

---

## 3. Phase 1 — 이미지 전처리 구현 (SFR-003I)

### 3.1 구현 내용

`ai/preprocessing/image_preprocessor.py`

| 단계 | 처리 내용 |
|------|---------|
| 1. 그레이스케일 변환 | — |
| 2. 노이즈 제거 | Gaussian Blur (5×5) |
| 3. 품질 평가 | total 점수 40점 미만 → RETAKE 판단 |
| 4. 이진화 | Adaptive Threshold (Gaussian, blockSize=15, C=5) → `THRESH_BINARY_INV` (획=255, 배경=0) |
| 5. 기울기 보정 | HoughLinesP → 중앙값 각도(±6° 이내) → warpAffine deskew |
| 6. 해상도 정규화 | 장축 800~1280px 기준 비율 유지 리사이즈 |

**반환 구조**:
```python
@dataclass
class PreprocessResult:
    binary_image: np.ndarray    # (H, W) uint8, 획=255
    quality_score: Dict         # {total, sharpness, contrast, ...}
    skew_angle: float
    applied_filters: List[str]
    retake_required: bool
```

### 3.2 발생 문제 및 해결

**문제**: NumPy 2.x 환경에서 `cv2.HoughLinesP` 반환값 파싱 오류
- 구버전: `lines` shape `(N, 1, 4)` → `line[0]`으로 `[x1,y1,x2,y2]` 접근
- 신버전: shape `(N, 4)` → `line[0]`이 스칼라 `x1` 반환
- **해결**: `line.flatten()[:4]`로 두 버전 모두 대응

---

## 4. Phase 2 — 글자 탐지 1차 시도 (OpenCV Contour)

### 4.1 초기 접근법

`craft_detect_chars` 함수의 placeholder로 **OpenCV Contour 기반** 탐지 구현.

```
이진화 이미지 → findContours → boundingRect → 크기 필터링 → 정렬
```

**한계**:
- 필기체에서 자모가 붙어 있으면 하나의 contour로 묶임
- 이음획(ㅎ, ㅊ 등)을 여러 contour로 분리
- angle 계산 없이 0 고정 → SFR-005I 분석 불가

→ **CRAFT로 교체 결정**

---

## 5. Phase 3 — CRAFT Score Map 기반 탐지 (대규모 재설계)

### 5.1 방향 전환 배경

`craft_text_detector` 패키지의 사전학습 모델(craft_mlt_25k.pth)을 활용.
CRAFT 출력은 **픽셀 단위 score_text 맵**이므로 글자 단위 분리에 유리 — 특히 한글은 자모가 붙어 쓰이고 음절 블록 단위로 묶이는 구조라, contour/투영 기반 방식보다 픽셀 단위 heatmap 방식이 원래 더 적합하다(자모가 서로 다른 CC로 잡히는 것도 CRAFT의 affinity로 보완 가능하다는 판단).

### 5.2 첫 구현 — CRAFT + Morphology + Watershed 하이브리드

```
커밋: 426d4a1a (refactor: CRAFT + Morphology + Watershed 하이브리드 탐지 구현)
```

시도한 구조:
1. CRAFT → score_text 맵
2. Otsu threshold → 이진화
3. Morphological dilation → row/col 투영으로 줄/열 분리
4. Watershed로 겹친 글자 분리

**문제점**:
- dilation + 투영 방식이 글씨 밀도에 따라 파라미터 민감도가 너무 높음
- 행 간격 · 자간이 달라지면 파라미터 재조정 필요
- Watershed 적용 시 오히려 과분할 발생

### 5.3 2차 재설계 — Score Map 단독 CC 추출

```
커밋: c118499d (feat: CRAFT score map 기반 글자 탐지 구현)
커밋: 28e17e72 (feat: CRAFT score_text 기반 글자 탐지 뼈대 구현)
```

**핵심 변경**: Morphology/Watershed 전부 제거. Score map threshold → Connected Components만 사용.

```
predict.py 패치 필요 사항:
  - 반환 dict에 'score_text_raw' (0~1 float, CRAFT 원본 맵) 추가
  - 반환 dict에 'target_ratio' (스케일 비율) 추가
```

**파이프라인**:
```
score_text_raw → threshold(0.40) → CC 추출 → scale 보정 → tight bbox
→ 자소→음절 병합 → 읽기순서 정렬 → 출력
```

### 5.4 Distance Transform 도입

CRAFT는 텍스처/그레디언트 기반으로 학습됨.
순수 binary 이미지(0/255)를 입력하면 획 내부 정보가 부족해 score map이 약해짐.

```python
# _craft_prediction() 내부
dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
dist_norm = cv2.normalize(dist, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
rgb = cv2.cvtColor(dist_norm, cv2.COLOR_GRAY2RGB)
# → CRAFT에 입력 (흰 배경 대신 거리 그레디언트)
```

이 방식으로 score map 활성화가 눈에 띄게 향상됨. **이 distance-transform 트릭은 이후 파인튜닝 데이터 파이프라인의 입력 도메인을 맞추는 데도 핵심적인 역할을 하게 된다 (Phase 10 참조).**

---

## 6. Phase 4 — 탐지 후처리 튜닝 (자소→음절 병합, 이후 폐기)

### 6.1 문제 인식

한국어 자모(ㄱ, ㄴ, ㅏ 등)는 각각 별개의 CC로 검출됨.
음절(가, 나, 다 등) 단위로 병합하지 않으면 bbox가 과잉 분할됨.

### 6.2 Union-Find 기반 병합 구현

```python
# _merge_jaso_to_syllable() — 핵심 임계값
H_X_GAP  = med_w * 0.25   # 가로 병합 허용 x 간격
V_Y_GAP  = med_h * 0.25   # 세로 병합 허용 y 간격
NO_MERGE = med_w * 0.55   # x 간격 이 이상 → 다른 음절 (병합 차단)
OV_MIN   = 0.50           # y축 겹침 최소 비율 조건
MAX_CLUSTER = 4           # 음절당 최대 자소 수 (연쇄 병합 방지)
```

Union-Find로 조건 충족 쌍을 합집합 처리 → 클러스터별 외접 bbox 계산.

### 6.3 테스트 결과 (0.25/0.25/0.55 기준)

| 이미지 | raw blobs | 병합 결과 | 기대치 | 상태 |
|--------|-----------|----------|--------|------|
| test.jpg ("한이음 프로젝트 두둥실") | 12 | 10 | 10 | ✅ 정확 |
| test6.jpg (90° 회전) | 18 | 12 | ~12 | ✅ 정확 |
| test3.png (빽빽한 손글씨) | 328 | 150 | ~100 | ⚠️ 과소병합 |
| test5.jpg (밀도 높은 문장) | 38 | 18 | ~39 | ❌ 과대병합 |

### 6.4 발견된 핵심 문제 — 글씨 크기 의존성

CRAFT 출력 수준이 글씨 크기(med_w)에 따라 달라짐:
- **소형 글씨** (med_w < ~35px): 자소 수준 blob → 적극 병합 필요
- **중대형 글씨** (med_w ≥ ~35px): 이미 음절 수준 blob → 거의 병합 불필요

적응형 임계값(크기별로 다른 H_X_GAP/V_Y_GAP/NO_MERGE)을 제안했으나 실제로 적용해보기 전에, 아예 pretrained 가중치 자체가 한국어 손글씨 음절 단위를 모른다는 판단으로 **파인튜닝(Phase 5)으로 방향을 틀었다.**

### 6.5 이후 결과 (커밋 843ee22c, 2026-07-06)

파인튜닝 파이프라인을 구축하면서 `craft_detector.py`도 함께 리팩터링— 이 수동 CC+병합 로직(`_merge_jaso_to_syllable` 등, 376줄 중 261줄 삭제)을 **통째로 제거**하고, `craft_text_detector` 패키지 자체의 성숙한 region+affinity 기반 박스 그룹핑(`Craft.detect_text()`)에 위임 + 잉크 픽셀 기준 tight bbox 재계산으로 단순화했다. 즉 위 6.2~6.4의 적응형 임계값 아이디어는 **최종적으로 채택되지 않았고**, 현재 `craft_detector.py`에는 이 병합 함수 자체가 존재하지 않는다.

---

## 7. Phase 5 — CRAFT 파인튜닝 1차 시도

### 7.1 배경 및 목적

사전학습 CRAFT(craft_mlt_25k.pth)가 한국어 손글씨에 최적화되지 않았다는 판단 하에, AI Hub 053 손글씨 OCR 데이터셋으로 파인튜닝 시도.

```
데이터셋: AI Hub 053 — 손글씨 OCR 학습 데이터
총 이미지: 약 15,314장 (매칭 페어 기준)
학습 환경: Google Colab (무료 T4 GPU)
```

### 7.2 파인튜닝 파이프라인 구현

```
커밋: 68f52a6b → 843ee22c → b42e4e07 → 9e91a809
```

**주요 구성**:
- `ai/training/craft_model.py`: VGG16-BN + UNet 디코더 CRAFT 아키텍처
- `ai/training/colab_finetune.py`: Colab 실행용 학습 스크립트

**데이터 샘플링 전략**: stem 기준 정렬 후 비중복 슬라이싱으로 1차/2차 세션 분리 (5,000장 × 10 epoch → 나머지 이어서)

### 7.3 채널 버그 발생 및 수정

**에러**:
```
RuntimeError: Given groups=1, weight of size [256, 768, 1, 1],
expected input[...] to have 512 channels, but got 768 channels
```

**원인**: `craft_model.py` 디코더의 skip connection 채널 수 오계산 (VGG16-BN slice별 실제 출력 채널을 잘못 가정 — slice1을 64ch로 착각했으나 실제 128ch 등).

```
커밋: 0c69d17b, 66253ea6
```

### 7.4 데이터 레이블 문제 발견

AI Hub 053 데이터셋의 레이블을 직접 분석한 결과, 레이블이 **어절(단어) 단위** bbox임을 확인 (`{"data": "김현주", ...}` 형태 — "김현주" 전체가 박스 1개). 글자 단위 요구사항과 어긋난다고 판단했으나, 이 시점에는 아직 "그럼 단어를 글자로 어떻게 분할할지"에 대한 구체적 구현은 없었다.

---

## 8. Phase 6 — 1차 파인튜닝 결과 검증 및 실패 진단

### 8.1 검증 스크립트 (`compare_craft.py`, 이후 세션에서 유실)

7개 테스트 이미지에 대해 pretrained vs finetuned 모델 비교. **파인튜닝 모델: 전체 0개 탐지.**

| 이미지 | pretrained n | finetuned n |
|--------|-------------|-------------|
| test.jpg | 8 | 0 |
| test3.png | 130 | 0 |
| test5.jpg | 20 | 0 |

### 8.2 당시의 원인 진단 (일부 부정확 — 8.2절 하단 정정 참조)

score map 검사 결과 **전 픽셀에 걸쳐 동일한 상수값**(`score_text≈0.0010`, `score_link≈0.0003`) — 입력 이미지와 무관하게 "아무것도 없음"을 출력하는 collapse 상태로 진단. 당시엔 원인을 "① 어절 단위 bbox pseudo-label 문제, ② 채널 버그 수정 전 체크포인트, ③ 복합 작용" 정도로만 추정하고 다음 단계로 넘어갔다.

> **[정정, Phase 10 이후 추가]** 이 진단은 방향은 맞았지만 정밀하지 않았다. 실제로 collapse를 일으킨 핵심 원인은 **OHEM(hard negative mining) 부재로 인한 극단적 클래스 불균형**이었다(Phase 8.3). 어절 단위 bbox 문제도 실재했지만 그 자체가 "collapse"를 유발한 것은 아니고, 글자 단위가 아닌 잘못된 granularity로 학습된다는 별개의 문제였다. 두 문제가 섞여서 진단이 흐려졌던 것.

---

## 9. Phase 7 — 핸드오프 문서 대조 및 크래시 버그 발견

*(세션 재개, 2026-07-08 후반 ~ 2026-07-09)*

claude.ai에서 별도로 진행했던 디버깅 대화 내용을 `CONTEXT_HANDOFF.md` 문서로 정리해 Claude Code로 가져와 이어서 작업을 요청받음. 그 문서의 진단을 실제 리포지토리 코드와 **한 줄씩 대조 검증**한 결과, 문서가 "이미 해결됨"이라 주장한 항목 대부분이 실제로는 반영되어 있지 않은 것으로 확인됨.

| 문서 주장 | 실제 코드 상태 |
|---|---|
| `craft_model.py`를 clovaai 공식 구조(`basenet.slice1`, `upconv1`, `conv_cls`)로 재작성함 | ❌ 여전히 커스텀 네이밍(`slice1`, `up1`, `out`) |
| `forward()`에서 sigmoid 제거함 | ❌ `self.out`이 여전히 `nn.Sigmoid()`로 끝남 |
| `gt_generator.py`에 `split_word_box()`로 단어→글자 분할이 이미 구현됨 | ❌ 그런 함수 자체가 존재하지 않음 |

추가로, 그날 커밋(`501c8c9d`)이 새로 만든 크래시 버그 2개도 함께 발견:
1. `ai/detection/craft_detector.py` 1번째 줄이 `1"""`로 손상되어 **SyntaxError로 모듈 임포트 자체가 불가능**(미커밋 상태로 발견, 원인 특정 못함).
2. 학습(`craft_model.py`, 커스텀 키 이름)과 추론(`craft_text_detector` 패키지의 `CraftNet`, 공식 키 이름)의 state_dict 키가 근본적으로 달라, 파인튜닝 가중치가 존재하면 `CraftDetector()` 생성 시 `strict=True` 로드로 즉시 크래시.

**교훈**: 핸드오프 문서의 "완료/해결" 표시는 액면 그대로 신뢰할 수 없다 — claude.ai 세션이 로컬에 반영 안 된 편집안을 논의했을 가능성이 있고, 항상 실제 코드를 직접 grep/read로 재확인해야 한다.

---

## 10. Phase 8 — 학습 파이프라인 재설계

### 10.1 아키텍처 통합 — `craft_model.py` 재작성

학습(자체 `CRAFT` 클래스)과 추론(`craft_text_detector`의 `CraftNet`)이 서로 다른 아키텍처였던 것이 모든 호환성 문제의 근본 원인이라 판단. `craft_text_detector.models.craftnet.CraftNet`을 import/상속하는 대신 **그 구조를 그대로 직접 복제(vendor)** 하는 방식을 택함 — Colab/Kaggle처럼 그 패키지가 없거나 버전 호환이 안 되는 환경에서도 동작해야 하므로 torch/torchvision 표준 API에만 의존하게 만들기 위함.

**함정**: `nn.Sequential(*list)`는 자식 모듈을 "0","1",..로 재번호해버려 원래 VGG feature 인덱스가 유실됨 — 처음 이 방식으로 작성했다가 `craft_mlt_25k.pth` 로드 시 `missing=48 unexpected=48`로 실패. 공식 구현처럼 `add_module(str(원래_인덱스), ...)`로 인덱스를 서브모듈 이름으로 보존해야 키가 맞는다는 걸 직접 겪고 나서 수정.

**검증**: `craft_mlt_25k.pth`를 `missing=0 unexpected=0`으로 로드 확인. 이 한 가지 변경으로 레이어 네이밍 불일치와 sigmoid 불일치(공식 구조는 원래 sigmoid 없음)가 동시에 해결됨.

### 10.2 단어→글자 분할 — `gt_generator.py`에 `split_word_box()` 추가

4점 polygon의 상단 변(좌상→우상)과 하단 변(좌하→우하)을 각각 글자 수만큼 등분해서 대응점을 연결 — 사진 촬영으로 기울어진 단어도 올바르게 분할되도록 x좌표 단순분할이 아닌 변(edge) 기준 분할 사용. `parse_aihub_json()`이 각 bbox의 `data` 텍스트 길이만큼 자동으로 이 함수를 호출하도록 변경.

**중요한 설계 결정 — affinity_map은 항상 0으로 유지**: CRAFT의 affinity는 원래 "인접 글자가 같은 단어에 속한다"를 학습시켜 추론 시 `craft_text_detector`의 박스 병합 로직(`text_score_comb = text_score + link_score`로 connected components)이 글자들을 다시 단어로 합치기 위한 신호다. 이 프로젝트는 정반대로 글자 단위 분리가 목표이므로, 인접 글자 사이에 affinity를 학습시키면 추론 파이프라인이 그걸 근거로 다시 병합해버려 작업 전체의 목적이 무효화된다. 그래서 affinity GT는 항상 0으로 두어 모델이 "인접 글자를 연결하지 말라"를 자연히 학습하게 함.

### 10.3 OHEM(Online Hard Example Mining) 도입 — `colab_finetune.py`/`kaggle_finetune.py`의 `CRAFTLoss`

GT의 99%+가 배경(0)인 극단적 클래스 불균형 때문에 순수 MSE는 "이미지 내용과 무관하게 전부 0에 가까운 값 출력"만으로 loss를 충분히 낮출 수 있어 학습이 collapse했던 것으로 재진단(Phase 6.2 정정 참조). 양성 픽셀 전부 + 가장 틀린 음성 픽셀 top-k만 loss에 반영하도록 `CRAFTLoss`를 재작성.

```python
def _ohem_mse(self, pred, gt):
    loss = (pred - gt) ** 2
    pos_mask = gt > 0.1
    pos_loss = loss[pos_mask]
    neg_loss = loss[~pos_mask]
    k = min(max(self.ohem_min_neg, self.ohem_ratio * max(pos_mask.sum(), 1)), neg_loss.numel())
    hard_neg_loss, _ = torch.topk(neg_loss, k)
    return torch.cat([pos_loss, hard_neg_loss]).mean()
```

affinity GT가 항상 0이라 OHEM이 자연히 "가장 잘못 높게 예측된(false positive) 지점"만 벌점을 주게 되어, 의도(인접 글자 비병합)와도 잘 맞아떨어짐.

---

## 11. Phase 9 — Colab → Kaggle 전환

Colab 세션이 학습 도중 반복적으로 연결이 끊겨 무인 장시간 실행이 어렵다는 문제로, Kaggle Notebook의 **"Save & Run All (Commit)"**(브라우저/인터넷 연결과 무관하게 서버에서 끝까지 도는 배치 실행 모드)으로 전환.

### 11.1 데이터 패키징 — `ai/training/prepare_kaggle_dataset.py` (신규)

`matched_pairs.json`에서 stem 정렬 기준 N장을 골라 이미지+라벨+`craft_model.py`+`gt_generator.py`+`craft_mlt_25k.pth`를 하나의 폴더(`kaggle_upload/`)로 패키징 → zip으로 Kaggle Dataset에 업로드.

### 11.2 Kaggle 환경 이슈 (실행하며 발견 및 즉시 수정)

| 문제 | 원인 | 해결 |
|---|---|---|
| `ModuleNotFoundError: craft_model` | Kaggle이 zip 압축 해제 시 폴더를 한 겹 더 씌움(`/kaggle/input/<데이터셋>/kaggle_upload/craft_model.py`) | 경로 하드코딩 대신 `/kaggle/input/**/craft_model.py`를 `glob`으로 재귀 탐색해서 자동으로 찾도록 변경 |
| `URLError: Temporary failure in name resolution` | `CRAFT(pretrained_backbone=True)`가 torchvision ImageNet 가중치를 인터넷에서 받으려 시도 (Kaggle Internet:Off 환경) | 바로 다음 줄에서 `craft_mlt_25k.pth`(backbone 포함 전체 가중치)로 덮어쓸 것이므로 애초에 `pretrained_backbone=False`로 고정 — ImageNet 다운로드 자체가 불필요했음을 확인 |

두 문제 모두 "인터넷 켜기"처럼 우회하는 대신, 애초에 불필요한 의존성을 코드에서 제거하는 방향으로 해결 — 무인 장시간 실행 중 외부 네트워크 장애로 전체 작업이 실패할 위험을 줄이기 위함.

---

## 12. Phase 10 — 2차 파인튜닝(Kaggle 3,500장) — score map은 정상인데 실제 탐지 0개

### 12.1 학습 결과

3,500장 × 10 epoch, 63.6분 만에 완료 (`train=0.0186 val=0.0198`). `debug_gt.py ckpt`로 확인한 score map은 **collapse가 아니었음** — 이미지마다 region 최댓값이 0.25~0.47로 실제로 다르게 반응, affinity는 설계대로 0 근처.

### 12.2 그러나 실제 `CraftDetector`로는 7개 테스트 이미지 전부 0개 탐지

threshold를 크게 낮춰도(text_threshold=0.15) 2/0/0/11/1/1/0으로 정상 범위와 거리가 멂.

### 12.3 근본 원인 — 학습/추론 입력 도메인 불일치 (직접 실측으로 확인)

`HandwritingDataset.__getitem__`이 **원본 컬러 사진**을 그대로 모델에 학습시켰는데, 실제 서비스 추론 경로(`image_preprocessor.py`의 이진화+deskew → `craft_detector.py`의 distance-transform, Phase 3.4 참조)는 완전히 다르게 생긴 입력(회색조 그레디언트 이미지)을 CRAFT에 먹임. 같은 AI Hub 학습 이미지 1장으로 직접 비교:
```
원본 컬러 사진 입력                  → 65 boxes
이진화+deskew+distance-transform 입력 → 3 boxes  (같은 이미지, 같은 모델)
```
모델이 학습 때 한 번도 보지 못한 입력 분포를 서비스 단계에서 받은 것 — score map이 살아있던 것과 실제 탐지가 0인 것이 모순이 아니라, 정확히 이 도메인 갭 때문이었음.

### 12.4 수정 — 학습 파이프라인에 동일 전처리 반영

`HandwritingDataset`(`kaggle_finetune.py`, `colab_finetune.py`)에 `_binarize_and_deskew()` / `_detect_skew_angle()` / `_to_dist_transform_rgb()`를 추가해서 `image_preprocessor.py`와 완전히 동일한 파라미터(adaptiveThreshold blockSize=15, C=5 등)로 이진화+deskew한 뒤 distance-transform까지 거친 이미지로 학습하도록 재작성. deskew로 회전이 걸릴 때 GT box 좌표도 같은 회전행렬로 변환(`pts @ matrix.T`)해야 해서, 합성 이미지(회전된 사각형)로 좌표 변환 정확도를 별도 검증 — 96.8%→(에지 anti-aliasing 노이즈 제외 시) 사실상 100% 일치 확인, 실제 AI Hub 문서 이미지로도 172개 박스 전부 범위 내 확인.

---

## 13. Phase 11 — 3차 파인튜닝(Kaggle 전체 15,314장) 진행 중

시간을 넉넉히 쓸 수 있는 상황이 되어, 파이프라인은 이미 충분히 검증됐다고 판단하고 3,500장이 아닌 **전체 15,314장**으로 확대. 15 epoch, 시간 예산 6시간(360분).

### 13.1 1차 실행 — epoch 7에서 시간 예산 초과로 자동 종료

`train=0.0186 val=0.0147`(로그 기준 3,500장 실행보다 낮음). 그러나 실제 탐지 결과 진단:

```
실제 학습에 쓰인 AI Hub 이미지(완전 in-domain)를 프로덕션 파이프라인 그대로 태워도
text_threshold=0.05(매우 낮음)에서 27~72개 검출 (정답은 144~215개) — 15~33% 수준 recall
```

collapse는 아니고(threshold를 낮추면 검출량이 합리적으로 증가), 이번엔 test_images와 AI Hub 간 도메인 차이 문제도 아님(같은 AI Hub 이미지로 테스트했으므로) — **아직 학습이 덜 된 상태**로 진단. 15 epoch 계획 중 7에서 끊긴 게, 마침 `CosineAnnealingLR` 스케줄이 절반쯤(학습률이 아직 안 낮아진 구간)에서 멈춘 것과 시점이 맞물림 — 이 스케줄은 보통 뒷부분에서 학습률이 낮아지며 예측이 날카로워지는 구간이라, 그 전에 멈추면 "신호는 있지만 확신이 약한" 상태로 보이는 게 자연스러움.

### 13.2 resume 학습 준비

처음부터 다시 돌리는 대신, epoch 7 체크포인트에서 이어서 학습하도록 `kaggle_finetune.py`에 자동 resume 탐색 로직 추가:

```python
_resume_candidates = glob.glob("/kaggle/input/**/craft_best.pth", recursive=True)
_resume_from = _resume_candidates[0] if _resume_candidates else None
CFG["warmup_ep"] = 0 if _resume_from else 2   # resume 시엔 이미 backbone이 풀려있어 warmup 불필요
```

체크포인트를 별도의 작은 Kaggle Dataset으로 올리고 기존 이미지 Dataset과 함께 Notebook에 붙이면, 어느 Dataset에 뭐가 들었든 자동으로 찾아서 이어서 학습. 현재 이 resume 실행이 진행 중.

### 13.3 남은 근본적 한계 — 단어→글자 균등분할의 정밀도 (미해결, 우선순위 낮음)

`split_word_box()`가 실제 글자 폭 차이(예: "ㅣ" vs "쓰")를 반영하지 못하고 기계적으로 N등분하는 것은 여전히 근사치다. 모델이 등분선보다 실제 잉크 경계에 더 강하게 반응하도록 수렴할 여지는 있지만 보장되진 않는다. 지금 확인된 문제(recall 부족)는 이 정밀도 문제보다 앞단(애초에 확신을 갖고 반응 안 함)이라 아직 이 이슈가 눈에 보일 단계는 아님 — recall이 잡힌 뒤에도 박스 경계가 부정확하면, CRAFT 원 논문이 실제로 쓰는 "모델의 현재 예측에 watershed를 적용해 pseudo-GT를 반복 정제하는" 방식으로 업그레이드가 필요할 수 있음.

---

## 14. Phase 12 — 체크포인트 선별 지표 개선 시도 및 파인튜닝 최종 롤백

### 14.1 resume 학습(epoch 8~13) 결과 — val_loss는 개선, 실제 탐지는 악화

Phase 11의 resume 학습이 완료되어 epoch 9/11/13 체크포인트를 모두 확보. **val_loss 기준으로 가장 낮은(=가장 "좋은") 체크포인트를 골랐더니, 실제 AI Hub 이미지 3장에 대한 탐지 개수가 오히려 계속 줄어드는 역전 현상을 확인**(threshold=0.05, 정답 172/215/144 기준):

```
epoch  9 : [31, 42, 70]   val_loss 기준으로는 이보다 나쁨
epoch 11 : [15, 24, 33]   val_loss는 9보다 낮음(=더 좋음)
epoch 13 : [ 8, 20, 24]   val_loss는 11보다도 더 낮음
```

### 14.2 원인 진단 — OHEM이 GT 피크 주변의 저값 픽셀까지 "정답"으로 취급

`_ohem_mse`가 `gt > 0.1`인 모든 픽셀을 동일 가중치의 양성으로 취급하는데, Gaussian GT는 중심(피크, ≈1.0)에서 멀어질수록 값이 낮아진다. 이 저값 주변부 픽셀까지 동일 가중치로 학습에 반영되면, 모델이 "중심에서도 확신 있게 높은 값을 내는 것"보다 "전체적으로 무난하게 낮은 값을 내는 것"이 손실 관점에서 더 유리해지는 방향으로 서서히 편향된다 — val_loss는 실제로 떨어지지만, 정작 필요한 "박스 디코딩에 쓰일 만큼 뾰족하고 확신 있는 피크"는 오히려 무뎌지는 것으로 해석.

### 14.3 개선 시도 — GT 값 제곱 가중치 + `peak_quality` 지표

`_ohem_mse`의 양성 픽셀 loss에 `gt_value ** 2` 가중치를 곱해 GT 피크에 가까운 픽셀일수록 더 크게 반영되도록 수정. 체크포인트 선별 기준도 `val_loss` 대신, GT>0.7 픽셀에서의 평균 예측값을 뜻하는 자체 지표 `peak_quality`로 교체(`validate()`가 `(val_loss, peak_quality)` 튜플 반환, `is_best = peak_quality > best_peak`).

이 fix를 적용해 epoch 9에서 6 epoch 추가 학습(epoch 14 = peak_quality 기준 best, `peak_quality=0.72`, 미적용 대비 큰 개선).

### 14.4 검증 — peak_quality 개선이 실제 탐지 품질과 상관관계가 없음을 확인

같은 AI Hub 3장으로 재검증(threshold=0.05):

```
epoch  9 (fix 이전)     : [31, 42, 70]  ← 지금까지 전체 실험 중 최고
epoch 11               : [15, 24, 33]
epoch 13               : [ 8, 20, 24]
epoch 14 (peak-weighted OHEM 적용) : [15, 27, 34]  ← epoch13보다는 낫지만 epoch9엔 미달
```

test_images(도메인 밖) 7장에서는 격차가 더 뚜렷함 — 예: test.jpg가 pretrained/epoch9 기준 8/8 정확히 잡히던 것이 epoch14에서는 0개로 하락. `peak_quality=0.72`라는 지표상의 큰 개선이 실제 탐지 성능에는 반영되지 않음을 재확인.

### 14.5 결정적 발견 — 검증 자체가 실제 배포 경로를 쓰지 않고 있었음

이 시점까지의 모든 "epoch N: [a,b,c]" 비교는 `craft_text_detector`의 실제 `Craft.detect_text()`가 아니라, score map을 직접 꺼내 **임의로 낮춘 threshold(0.05)로 커스텀 connected-components 스크립트**를 돌린 결과였다. 실제 서비스가 쓰는 `CraftDetector` 클래스(기본 threshold text=0.7/link=0.4/low_text=0.4)로 다시 정식 검증하자 훨씬 심각한 결과가 나왔다:

| | AI Hub 3장 (정답 172/215/144) | test_images 7장 |
|---|---|---|
| **pretrained (파인튜닝 없음)** | 204/241/166 탐지 (112~119%) | 정상 탐지 (8,8,130,78,20,12,24) |
| **epoch 9 (지금까지의 "최선")** | **0 / 0 / 0** | **전부 0** |

epoch 9의 region score map 최댓값이 이미지당 0.54 수준까지밖에 오르지 않아 기본 threshold(0.7)를 절대 못 넘는다. threshold를 억지로 0.05까지 낮춰도 AI Hub 이미지에서 정답의 22% 수준(39/172)밖에 못 잡는다 — **정상적인 방식으로는 회복 불가능한 수준**.

### 14.6 최종 결론 — 파인튜닝 롤백, pretrained로 확정 배포

이번 세션에서 시도한 세 번의 연속된 재학습(원본 OHEM, 도메인일치+peak-weighted OHEM 등)이 전부 동일한 패턴을 보였다 — **어떤 지표(val_loss든 peak_quality든)로 체크포인트를 고르든, 실제 배포 경로 기준 탐지 성능은 학습이 진행될수록 pretrained보다 나빠졌다.** epoch 7~9 부근이 유일하게 그나마 쓸만했던 지점이었지만, 그마저도 정식 threshold 기준으로는 완전히 0 detection이라 실사용 불가.

**조치**: `ai/models/craft_finetuned_raw.pth`를 제거(`craft_finetuned_epoch9.pth.bak`로 보관)해 `craft_detector.py`의 기존 폴백 로직이 자동으로 pretrained 가중치를 쓰도록 되돌림. 코드 변경 없이 파일 존재 여부만으로 전환되므로 롤백/재시도 모두 안전하게 반복 가능.

**남는 가설(미검증)**: 어절 단위 bbox를 글자 수로 기계적 등분한 pseudo-GT의 부정확성(13.3절), distance-transform 전처리가 파인튜닝 상황에서 오히려 신호를 약화시킬 가능성, 학습률/스케줄이 이 소규모 파인튜닝에 비해 여전히 과도할 가능성 등 — 다음에 다시 시도한다면 이 중 하나를 바꿔서 **반드시 실제 `CraftDetector` 클래스로 검증**해야 한다(14.5절 교훈).

---

## 15. 현재 상태 및 남은 과제

*(2026-07-10 기준)*

### 15.1 확실히 동작하는 것

- **이미지 전처리** (`image_preprocessor.py`): 정상 동작
- **CRAFT 글자 탐지** (`craft_detector.py`): 현재 **pretrained(craft_mlt_25k.pth) 가중치로 배포 확정**. 7개 테스트 이미지에서 8~130개 글자 탐지, AI Hub 3장에서 정답 대비 112~119% 탐지, 기존 baseline과 회귀 없이 일치 확인
- **학습/추론 아키텍처 통합**: `craft_model.py`가 공식 구조와 `missing=0 unexpected=0`으로 완전 호환 (파인튜닝을 다시 시도할 때 재사용 가능한 자산)
- **단어→글자 GT 분할**: 실제 AI Hub 샘플로 시각 검증 완료(다글자 단어가 정확히 글자별로 분리됨)
- **크기·기울기 판단 모듈** (`analysis/handwriting_analyzer.py`, SFR-005I): 구현 완료. `craft_detect_chars()` 출력을 그대로 입력받아 행 분류, 크기 균일성, 기울기, baseline 정렬 편차를 산출

### 15.2 아직 미해결/보류

- **CRAFT 파인튜닝(SFR-004I 정확도 개선)**: 세 차례 재학습 전부 pretrained보다 낮은 성능으로 확인되어 **롤백, 현재 미배포 상태**(Phase 12 참조). 학습 파이프라인 코드 자체(아키텍처 통합, OHEM, 도메인 일치)는 검증돼 있어 재시도 시 그대로 재사용 가능하나, 근본 원인(pseudo-GT 정밀도/전처리/하이퍼파라미터 등, 14.6절 가설)은 미확정
- **`backend/app/services/ai_adapters.py`**: 아직 없음 — AI↔백엔드 연동 전, backend는 스켈레톤 수준
- **단어→글자 균등분할의 정밀도 한계** (13.3절): 파인튜닝 재시도 시 함께 재평가 필요
- **AI Hub 053(태블릿 촬영 대출신청서 양식)과 실제 앱 사용자가 촬영할 손글씨의 도메인 차이**: 파인튜닝을 아무리 잘해도 데이터셋 자체의 갭은 못 메움 — 실제 서비스 입력 환경(연습장/줄노트/자유 문장 등)에 대한 검증 필요

### 15.3 파일 현황

| 파일 | 상태 |
|---|---|
| `ai/preprocessing/image_preprocessor.py` | ✅ 완성 |
| `ai/detection/craft_detector.py` | ✅ 완성, **현재 pretrained 가중치로 동작 중** |
| `ai/analysis/handwriting_analyzer.py` | ✅ 완성 (SFR-005I) |
| `ai/training/craft_model.py` | ✅ 공식 구조로 재작성 완료, 키 호환 검증됨 (재파인튜닝 시 재사용) |
| `ai/training/gt_generator.py` | ✅ 단어→글자 분할 구현 및 검증됨 |
| `ai/training/colab_finetune.py` | ✅ OHEM/도메인일치/peak-weighted 반영 완료 (현재는 Kaggle로 전환해 미사용) |
| `ai/training/kaggle_finetune.py` | ✅ 현재 사용 중, resume 지원, peak_quality 기준 체크포인트 선별 |
| `ai/training/prepare_kaggle_dataset.py` | ✅ 완성 |
| `ai/debug_gt.py` / `ai/debug_compare_production.py` | ✅ 체크포인트 검증 도구 (반드시 실제 `CraftDetector` 경로로 검증) |
| `ai/models/craft_finetuned_epoch9.pth.bak` | 🔴 파인튜닝 최종 결과물이나 pretrained보다 성능이 낮아 미배포 (보관용) |

---

*이 문서는 구현 과정 중 발생한 문제, 판단 근거, 방향 전환의 이유를 기록한 것입니다.
코드 변경 이력은 `git log`를 통해 확인하세요.*
