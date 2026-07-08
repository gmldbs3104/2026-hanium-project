# AI 모듈 구현 과정 전체 기록

> 2026 한이음 드림업 — AI 손글씨 교정 플랫폼  
> 작성일: 2026-07-08  
> 대상: SFR-003I(전처리) · SFR-004I(CRAFT 탐지) 개발 과정

---

## 목차

1. [프로젝트 목표 요약](#1-프로젝트-목표-요약)
2. [AI 모듈 초기 설계](#2-ai-모듈-초기-설계)
3. [Phase 1 — 이미지 전처리 구현](#3-phase-1--이미지-전처리-구현-sfr-003i)
4. [Phase 2 — 글자 탐지 1차 시도 (OpenCV Contour)](#4-phase-2--글자-탐지-1차-시도-opencv-contour)
5. [Phase 3 — CRAFT Score Map 기반 탐지 (대규모 재설계)](#5-phase-3--craft-score-map-기반-탐지-대규모-재설계)
6. [Phase 4 — 탐지 후처리 튜닝 (자소→음절 병합)](#6-phase-4--탐지-후처리-튜닝-자소음절-병합)
7. [Phase 5 — CRAFT 파인튜닝 시도](#7-phase-5--craft-파인튜닝-시도)
8. [Phase 6 — 파인튜닝 결과 검증 및 실패 진단](#8-phase-6--파인튜닝-결과-검증-및-실패-진단)
9. [현재 상태 및 남은 과제](#9-현재-상태-및-남은-과제)

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

---

## 2. AI 모듈 초기 설계

### 2.1 디렉토리 구조 확정

```
ai/
├── preprocessing/
│   └── image_preprocessor.py    # SFR-003I
├── detection/
│   └── craft_detector.py        # SFR-004I
├── analysis/
│   └── handwriting_analyzer.py  # SFR-005I
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
| 1. 크기 정규화 | 장축 1280px 기준 비율 유지 리사이즈 |
| 2. 그레이스케일 변환 | — |
| 3. 조명 보정 | CLAHE (clipLimit=2.0, tileGridSize=8×8) |
| 4. 노이즈 제거 | Gaussian Blur (3×3) |
| 5. 이진화 | Otsu Thresholding → `THRESH_BINARY_INV` (획=255, 배경=0) |
| 6. 기울기 보정 | HoughLinesP → 중앙값 각도 → warpAffine |
| 7. 품질 평가 | total 점수 → RETAKE 판단 |

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
CRAFT 출력은 **픽셀 단위 score_text 맵**이므로 글자 단위 분리에 유리.

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

이 방식으로 score map 활성화가 눈에 띄게 향상됨.

---

## 6. Phase 4 — 탐지 후처리 튜닝 (자소→음절 병합)

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

**제안된 적응형 임계값** (미적용):
```python
if med_w < 35:
    H_X_GAP, V_Y_GAP, NO_MERGE = med_w*0.28, med_h*0.28, med_w*0.60
else:
    H_X_GAP, V_Y_GAP, NO_MERGE = med_w*0.12, med_h*0.12, med_w*0.35
```

---

## 7. Phase 5 — CRAFT 파인튜닝 시도

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

**CFG 구조**:
```python
CFG = {
    "max_samples"  : 5_000,    # 1차 학습 (4~5시간)
    "sample_start" : 0,
    "epochs"       : 10,
    "batch_size"   : 4,
    "lr"           : 1e-4,
    ...
}
# RESUME_CFG: sample_start=5000, max_samples=None (나머지 전부)
```

**데이터 샘플링 전략**: stem 기준 정렬 후 비중복 슬라이싱으로 1차/2차 세션 분리

### 7.3 채널 버그 발생 및 수정

**에러**:
```
RuntimeError: Given groups=1, weight of size [256, 768, 1, 1],
expected input[...] to have 512 channels, but got 768 channels
```

**원인**: `craft_model.py` 디코더의 skip connection 채널 수 오계산

VGG16-BN 각 slice 출력 채널 (정확한 값):
```
slice1 (features[0:12])  → 128ch   ← 초기엔 64ch로 잘못 설정
slice2 (features[12:19]) → 256ch   ← 초기엔 128ch로 잘못 설정
slice3 (features[19:29]) → 512ch
slice4 (features[29:39]) → 512ch
slice5 (custom: pool+conv) → 1024ch
```

**수정 후 올바른 디코더**:
```python
self.up1 = DoubleConv(1024 + 512, 512, 256)   # slice5 + slice4
self.up2 = DoubleConv(256  + 512, 256, 128)   # up1_out + slice3  ← 수정
self.up3 = DoubleConv(128  + 256, 128,  64)   # up2_out + slice2  ← 수정
self.up4 = DoubleConv(64   + 128,  64,  32)   # up3_out + slice1  ← 수정
```

```
커밋: 0c69d17b, 66253ea6
```

### 7.4 데이터 레이블 문제 발견 (중요)

AI Hub 053 데이터셋의 레이블을 직접 분석한 결과:

```json
// 실제 json 샘플
{"data": "김현주", "bbox": {"x": [804,804,961,961], "y": [630,677,630,677]}}
{"data": "제주특별자치도", "bbox": ...}
```

**핵심 문제**: 레이블이 **어절(단어) 단위** bbox였음. 글자 단위 아님.

| 항목 | AI Hub 053 레이블 | 프로젝트 요구사항 |
|------|-----------------|----------------|
| bbox 단위 | 어절(단어) | **글자(음절)** |
| 예시 | "김현주" → bbox 1개 | "김", "현", "주" → bbox 3개 |

**영향**: 어절 단위 bbox로 CRAFT를 파인튜닝하면 글자 단위 score map을 생성하도록 학습되지 않음. 프로젝트 목표(크기/간격/높낮이 분석)에 근본적으로 부적합.

> 이 문제는 데이터 전처리와 Colab 학습 환경까지 모두 준비된 후에야 식별됨.

---

## 8. Phase 6 — 파인튜닝 결과 검증 및 실패 진단

### 8.1 검증 스크립트 (`compare_craft.py`)

7개 테스트 이미지에 대해 pretrained vs finetuned 모델 비교.

**결과**:
| 이미지 | pretrained n | pretrained conf | finetuned n | finetuned conf |
|--------|-------------|----------------|-------------|----------------|
| test.jpg | 8 | 0.406 | 0 | 0.000 |
| test2.png | 8 | 0.445 | 0 | 0.000 |
| test3.png | 130 | 0.397 | 0 | 0.000 |
| test4.png | 78 | 0.413 | 0 | 0.000 |
| test5.jpg | 20 | 0.339 | 0 | 0.000 |
| test6.jpg | 12 | 0.387 | 0 | 0.000 |
| test7.jpg | 24 | 0.415 | 0 | 0.000 |

**파인튜닝 모델: 전체 0개 탐지**

### 8.2 근본 원인 진단

`craft_finetuned_raw.pth`를 CraftNet에 직접 로드 후 score map 검사:

```python
score_text  min=0.0010  max=0.0010  mean=0.0010
score_link  min=0.0003  max=0.0003  mean=0.0003
```

**score map이 전 픽셀에 걸쳐 동일한 상수값** → 모델이 입력 이미지와 무관하게 "아무것도 없음"을 출력하는 collapse 상태.

**원인 분석**:
1. 어절 단위 bbox → 픽셀 단위 score map pseudo-label 생성이 올바르지 않았거나
2. 채널 버그가 수정되기 전의 checkpoint가 저장되었거나  
3. 두 요인이 복합적으로 작용하여 그레디언트가 모델을 0-output으로 수렴시킴

### 8.3 환경 이슈 (이번 세션에서 해결)

| 문제 | 원인 | 해결 |
|------|------|------|
| `ModuleNotFoundError: craft_text_detector` | 패키지 미설치 | `pip install craft-text-detector` |
| `ImportError: _ARRAY_API not found` (cv2) | `craft-text-detector` 설치 시 NumPy 2.x 업그레이드 | `pip install --upgrade opencv-python` |
| `ImportError: model_urls` | torchvision 0.13+ 에서 `model_urls` 제거 | `craft_text_detector/models/basenet/vgg16_bn.py` 2줄 패치 |
| `ValueError: inhomogeneous shape` (np.array) | NumPy 2.x 엄격한 배열 생성 | `craft_utils.py`, `predict.py` 에 `dtype=object` 추가 |
| `TypeError: cannot unpack numpy.int32` | HoughLinesP 반환 shape 변경 | `image_preprocessor.py` → `line.flatten()[:4]` |

---

## 9. 현재 상태 및 남은 과제

### 9.1 현재 동작하는 것

- **이미지 전처리** (`image_preprocessor.py`): 7개 이미지 모두 정상 동작
- **pretrained CRAFT 탐지**: 글자 단위 bbox 탐지 가능 (score map 정상 활성화)
- **읽기순서 정렬, confidence 계산, tight bbox**: 정상 동작
- **SFR-005I 품질 분석** (`handwriting_analyzer.py`): 크기균일성/간격/높낮이 지표 계산

### 9.2 동작하지 않는 것

- **파인튜닝 모델** (`craft_finetuned_raw.pth`): score map collapse, 탐지 0개
- **자소→음절 병합 튜닝**: 글씨 크기별 적응형 임계값 미적용

### 9.3 다음 단계 선택지

**Option A — pretrained CRAFT 그대로 사용 (권장)**  
- 현재 7개 테스트 이미지에서 8~130개 글자 탐지 가능
- 병합 임계값 적응형 전환으로 정확도 개선 가능
- 추가 학습 없이 SFR-004I 요건 충족 가능성 있음

**Option B — 파인튜닝 재시도**  
- 글자 단위 레이블 데이터가 필요 (AI Hub 053은 어절 단위라 부적합)
- 채널 버그 수정 버전으로 Colab 재실행 필요
- 적합한 공개 데이터셋: [KAIST 한글 손글씨], [AI Hub 062 글자 단위]

### 9.4 파일 현황

| 파일 | 상태 | 비고 |
|------|------|------|
| `ai/preprocessing/image_preprocessor.py` | ✅ 완성 | HoughLinesP 패치 완료 |
| `ai/detection/craft_detector.py` | ⚠️ 병합 튜닝 진행 중 | 적응형 임계값 미적용 |
| `ai/training/craft_model.py` | ✅ 채널 버그 수정 완료 | Colab 재실행 필요 |
| `ai/training/colab_finetune.py` | ✅ resume 지원 완성 | 학습 재실행 대기 |
| `ai/models/craft_finetuned_raw.pth` | ❌ score map collapse | 재학습 필요 |
| `ai/analysis/handwriting_analyzer.py` | ✅ 구현 완료 | 탐지 결과 입력 필요 |

---

*이 문서는 구현 과정 중 발생한 문제, 판단 근거, 방향 전환의 이유를 기록한 것입니다.  
코드 변경 이력은 `git log`를 통해 확인하세요.*
