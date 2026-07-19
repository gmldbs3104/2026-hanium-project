# AI 모델 인터페이스 스펙

> 백엔드 ↔ AI 모델 트랙 협업 문서  
> 작성 기준일: 2026-06-27  
> 구현 위치: `backend/app/services/ai_adapters.py`

AI 모델이 완성되면 아래 3개 함수의 **내부 구현만 교체**하면 된다.  
함수 이름, 파라미터, 반환 형식은 변경하지 않는다.

> **2026-07-18 교체 완료**: feature/ai-setup 브랜치의 `backend/app/services/ai_adapters.py`에
> 3개 함수가 전부 `ai/` 패키지 실구현으로 연결됨 (+ AI 전처리 드롭인 `preprocess_image`,
> `preprocess_image_full`, `analyze_size_angle` 추가 제공). feature/backend-setup의 스텁
> 버전과 병합 시 충돌하면 **ai-setup 쪽을 채택**할 것. 연동 잔여 항목(라우트 반영,
> 좌표계, torch 의존성)은 `HANDOFF.md` 5.1절 참고.

---

## 1. LSTM 획 그룹핑 보정 (SFR-004C)

**함수명**: `lstm_refine_grouping`  
**역할**: 규칙 기반 1차 그룹핑 결과를 LSTM으로 보정한다.

### Input

```python
stroke_groups: List[List[Dict]]
```

규칙 기반으로 묶인 획 그룹 리스트. 각 그룹은 한 문자 후보.

```json
[
  [
    {
      "stroke_id": "s0",
      "points": [
        { "x": 10.5, "y": 20.1, "pressure": 0.8, "timestamp": 1000 },
        { "x": 11.0, "y": 21.0, "pressure": 0.9, "timestamp": 1016 }
      ]
    },
    {
      "stroke_id": "s1",
      "points": [ ... ]
    }
  ],
  [
    {
      "stroke_id": "s2",
      "points": [ ... ]
    }
  ]
]
```

### Output

```python
List[List[Dict]]  # 입력과 동일한 구조
```

보정된 그룹 리스트. 잘못 묶인 획은 분리, 잘못 나뉜 획은 합쳐서 반환.

```json
[
  [ { "stroke_id": "s0", "points": [...] } ],
  [ { "stroke_id": "s1", "points": [...] }, { "stroke_id": "s2", "points": [...] } ]
]
```

### 현재 상태 / 교체 목표

| 항목 | 내용 |
|------|------|
| 현재 | `ai/canvas/stroke_grouping.py`의 1차 규칙 기반 결과(`group_strokes_by_rules`)를 그대로 반환하는 placeholder |
| 교체 | 획의 공간·시간 특징을 LSTM에 입력해 재분류 — 실사용자 캔버스 데이터 확보 후 진행 (`CANVAS_DATA_PLAN.md` 참고) |
| 기대 효과 | 복잡한 자음/모음 조합에서 그룹핑 정확도 향상 |

> 캔버스 모드 전체 현황(어떤 파일이 뭘 하는지, 데이터 없이도 동작하는 규칙 기반 부분이
> 어디까지인지)은 `HANDOFF.md` 4절에 종합 정리되어 있습니다.

---

## 2. LSTM 획순 분석 (SFR-005C)

**함수명**: `lstm_analyze_stroke_order`  
**역할**: 한 문자를 구성하는 획들의 순서가 올바른지 분석한다.

### Input

```python
strokes: List[Dict]          # 한 문자의 획 리스트
expected_sequence: List[str] # 표준 DB의 올바른 획순 레이블
```

```json
// strokes
[
  {
    "stroke_id": "s0",
    "points": [
      { "x": 10.5, "y": 20.1, "pressure": 0.8, "timestamp": 1000 },
      { "x": 50.0, "y": 20.1, "pressure": 0.9, "timestamp": 1050 }
    ]
  }
]

// expected_sequence
["horizontal", "vertical", "dot"]
```

### Output

```python
Dict
```

```json
{
  "expected_sequence": ["horizontal", "vertical", "dot"],
  "actual_sequence":   ["vertical", "horizontal", "dot"],
  "error_count":       1,
  "corrections":       ["첫 번째 획은 가로획이어야 합니다."]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `expected_sequence` | `List[str]` | 표준 획순 레이블 |
| `actual_sequence` | `List[str]` | 모델이 인식한 실제 획순 레이블 |
| `error_count` | `int` | 틀린 획 수 |
| `corrections` | `List[str]` | 교정 메시지 (없으면 빈 리스트) |

### 현재 상태 / 교체 목표

| 항목 | 내용 |
|------|------|
| 현재 | `ai/canvas/stroke_standards.py`의 `lstm_analyze_stroke_order`는 stroke 개수 비교만 수행하는 placeholder(백엔드 계약 시그니처 유지용) |
| **실질적으로 동작하는 대안** | `ai/canvas/canvas_quality_analyzer.py`의 `analyze_stroke_order_by_position()`이 위치+모양 기하 비교로 **학습 데이터 없이도 실제 획순 오류를 감지**함 (SFR-005C 종합 함수 `analyze_canvas_writing()`이 이쪽을 사용). 상세는 `HANDOFF.md` 4.5절 |
| 교체 목표 | 각 stroke의 방향 벡터 시퀀스 → LSTM → 획 레이블 분류로, 실사용자 데이터 확보 후 이 인터페이스 함수 내부만 교체 |
| 기대 효과 | 실제 획순 오류 감지 및 구체적 교정 메시지 제공 (현재도 근사치로는 달성됨) |

---

## 3. CRAFT 문자 영역 탐지 (SFR-004I)

**함수명**: `craft_detect_chars`  
**역할**: 이진화 이미지에서 문자 영역 Bounding Box를 탐지한다.

### Input

```python
binary_image_list: List[List[int]]  # 이진화 이미지 (0 or 255)
image_width:  int                   # 이미지 너비 (px)
image_height: int                   # 이미지 높이 (px)
```

- `binary_image_list`: 2D 배열, `[row][col]` 순서, 값은 `0`(배경) 또는 `255`(획)
- numpy 배열 변환: `np.array(binary_image_list, dtype=np.uint8)`

### Output

```python
List[Dict]
```

```json
[
  {
    "char_id":      "char_0",
    "bounding_box": { "x": 50.0, "y": 80.0, "width": 90.0, "height": 100.0 },
    "angle":          -2.5,
    "angle_reliable": true,
    "confidence":     0.97
  },
  {
    "char_id":        "char_1",
    "bounding_box":   { "x": 180.0, "y": 78.0, "width": 88.0, "height": 105.0 },
    "angle":          0.0,
    "angle_reliable": false,
    "confidence":     0.95
  }
]
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `char_id` | `str` | `"char_0"`, `"char_1"`, ... 순서대로 |
| `bounding_box.x` | `float` | 좌상단 x (px) |
| `bounding_box.y` | `float` | 좌상단 y (px) |
| `bounding_box.width` | `float` | 너비 (px) |
| `bounding_box.height` | `float` | 높이 (px) |
| `angle` | `float` | 세로획 slant 기울기 (degree, 양수=시계방향=글자 상단이 오른쪽). `angle_reliable=false`면 `0.0` |
| `angle_reliable` | `bool` | 세로획이 충분히 검출돼 기울기를 신뢰할 수 있는지. ㅇ 위주 글자 등은 `false` — 기울기 평가에서 제외할 것 |
| `confidence` | `float` | 탐지 신뢰도 `0.0 ~ 1.0` |

**정렬 규칙**: 좌상단 → 우하단 순서 (줄 단위 y, 줄 내 x)

### 현재 상태 / 교체 목표

| 항목 | 내용 |
|------|------|
| 현재 | **CRAFT 모델(pretrained, craft_mlt_25k.pth) 추론 기반 탐지 — 이미 구현 완료** (2026-07-09 변경, 아래 참고). `angle`은 2026-07-19부터 minAreaRect가 아니라 **세로획 slant**(HoughLinesP 근수직 선분의 길이가중 평균, `craft_detector.py` docstring 참고)로 산출하며 `angle_reliable` 필드가 추가됨 |
| 파인튜닝 시도 | 손글씨 도메인(AI Hub 053)으로 파인튜닝을 3차례 시도했으나 전부 pretrained보다 낮은 성능으로 확인되어 롤백. 현재 pretrained로 배포 확정. 상세 경위는 `IMPLEMENTATION_HISTORY.md` Phase 5~12 참고 |
| 기대 효과(달성됨) | 기울어진 글씨, 겹친 문자 영역 정확 탐지 + 실제 기울기 값 제공 |

> **2026-07-13 정정**: 이 표는 한동안 "OpenCV contour 기반, angle=0 고정"이라는 초기
> 구현 상태를 그대로 남겨두고 있었으나, 실제로는 훨씬 이전(Phase 3, `IMPLEMENTATION_HISTORY.md`
> 참고)에 CRAFT 기반으로 전면 교체되었습니다. 문서가 실제 코드 상태를 못 따라간 사례이니,
> 이 문서를 신뢰하기 전에 항상 `ai/detection/craft_detector.py`를 직접 확인하세요.

---

## 4. 크기 균일성 / 기울기 분석 (SFR-005I)

**함수명**: `analyze_size_angle`  
**역할**: 탐지된 글자 bounding box를 분석해 크기 균일성·기울기·기준선 정렬을 반환한다.

> **2026-07-09 변경**: 기존에는 `binary_image_list`를 다시 잘라 기울기를 자체
> 재계산했으나, `craft_detect_chars()`가 계산한 `angle` 필드를 그대로 재사용하도록
> 변경. 이미지 파라미터가 더 이상 필요 없어져 시그니처에서 제거함.
>
> **2026-07-19 변경 (기울기 평가 개편)**: `angle`이 minAreaRect에서 세로획 slant로
> 교체되면서(3절 참고) 기울기 평가를 **문서 단위**로 전환 — `angle_reliable=true`인
> 글자만 집계해 전체 평균 기울기와 **일관성 점수(`tilt_consistency_score`)**를 내고,
> "오른쪽으로 기운 글자: char_7" 같은 개별 글자 지적 문구는 제거함 (측정 노이즈에
> 민감하고 서비스 목적이 글 전체 평가이기 때문). 신뢰 글자 3자 미만이면 기울기
> 평가를 생략함.

### Input

```python
chars: List[Dict]                                  # craft_detect_chars() 반환값 그대로
binary_image: Optional[np.ndarray] = None          # 전처리 binary — 지표 6(획 굵기)에만
                                                   # 사용. 생략하면 해당 지표만 skipped.
```

### Output

```python
Dict
```

```json
{
  "size_uniformity_score": 87.4,
  "mean_angle": 2.1,
  "angle_std": 3.5,
  "tilt_consistency_score": 82.5,
  "overall_tilt": "straight",
  "total_score": 78.9,
  "metrics": {
    "height_uniformity":       {"value": 8.9,  "unit": "%", "grade": "우수", "score": 82.2},
    "tilt_consistency":        {"value": 3.5,  "unit": "°", "grade": "보통", "score": 75.0,
                                "n_outlier": 2, "n_unmeasured": 5},
    "spacing_uniformity":      {"value": 8.2,  "unit": "%", "grade": "우수", "score": 89.0, "n_gaps": 14},
    "line_spacing_uniformity": {"value": 2.8,  "unit": "%", "grade": "우수", "score": 94.4, "n_rows": 3},
    "baseline_deviation":      {"value": 5.6,  "unit": "%", "grade": "보통", "score": 77.6},
    "stroke_width_uniformity": {"value": 17.7, "unit": "%", "grade": "보통", "score": 59.5,
                                "mean_width_px": 5.3},
    "clarity":                 {"value": 8.3,  "unit": "%", "grade": "우수", "score": 83.3, "n_flagged": 2}
  },
  "line_alignment_score": 91.2,
  "issues": ["글씨가 전체적으로 오른쪽으로 약간(2.1°) 기울어져 있습니다"],
  "chars": [
    {
      "char_id": "char_0",
      "size_ratio": 1.05,
      "angle": 1.8,
      "size_flag": "normal",
      "angle_flag": "normal",
      "clarity_flag": "clear"
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `size_uniformity_score` | `float` | 크기 균일성 0~100점 (100=완전균일) |
| `mean_angle` | `float` | 전체 평균 기울기 (degrees, 양수=시계방향; `angle_reliable` 글자만 집계) |
| `angle_std` | `float` | 기울기 표준편차 (신뢰 글자만 집계) |
| `tilt_consistency_score` | `float` | 기울기 일관성 0~100점 (신뢰 글자 3자 미만이면 100) |
| `total_score` | `float` | 종합 점수 — 측정된 지표(skipped 제외)의 평균 |
| `metrics` | `Dict` | 지표별 상세 (handwriting_evaluation.md ①~⑥ + clarity). 각 항목 `{value, unit, grade(우수/보통/불량), score}` 또는 측정 불가 시 `{"skipped": 사유}` |
| `overall_tilt` | `str` | `"straight"` \| `"leaning_right"` \| `"leaning_left"` |
| `line_alignment_score` | `float` | 행 내 기준선(baseline) 정렬도 0~100점 |
| `issues` | `List[str]` | SFR-007에 전달할 피드백 메시지 목록 |
| `chars[].size_ratio` | `float` | 행 내 중앙값 대비 높이 비율 (1.0=정상) |
| `chars[].angle` | `float` | 글자 개별 slant (degrees, `craft_detect_chars()`의 `angle` 그대로) |
| `chars[].size_flag` | `str` | `"normal"` \| `"large"` \| `"small"` |
| `chars[].angle_flag` | `str` | `"normal"` \| `"tilted_cw"` \| `"tilted_ccw"` \| `"unmeasured"` (`angle_reliable=false`) |
| `chars[].clarity_flag` | `str` | `"clear"` \| `"merged_suspect"`(병합 의심 과폭) \| `"tilt_outlier"`(습관 slant 이탈) \| `"low_confidence"` — clear가 아니면 명료도 감점 대상이며 다른 지표 통계에서 제외 |

### 현재 상태 / 교체 목표

| 항목 | 내용 |
|------|------|
| 현재 | **handwriting_evaluation.md 지표 ①~⑥ 전면 구현 (2026-07-19)**: 높이 CV·기울기 slant σ(이상치 조정)·자간 pitch CV·행간 CV·회귀선 기준선 이탈도·획 굵기 CV + 명료도(탐지 이상 글자 감점, "탐지가 안 된 글자 = 또렷하지 않은 글자" 팀 결정). 지표 ⑦(자소 비율)은 제외 확정 |
| 교체 목표 | 필요 시 딥러닝 기반 기울기 추정으로 교체 가능 |

---

## 교체 방법

1. AI팀이 모델 추론 코드 작성
2. `backend/app/services/ai_adapters.py` 해당 함수 내부를 모델 호출로 교체
3. 입출력 형식은 이 문서의 스펙을 준수

```python
# 교체 예시 — craft_detect_chars
def craft_detect_chars(binary_image_list, image_width, image_height):
    import numpy as np
    from your_craft_module import CRAFTModel

    model = CRAFTModel.load("craft_weights.pth")
    image = np.array(binary_image_list, dtype=np.uint8)
    return model.detect(image)  # 반환 형식은 위 Output 스펙 준수
```
