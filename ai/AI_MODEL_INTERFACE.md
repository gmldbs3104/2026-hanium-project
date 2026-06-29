# AI 모델 인터페이스 스펙

> 백엔드 ↔ AI 모델 트랙 협업 문서  
> 작성 기준일: 2026-06-27  
> 구현 위치: `backend/app/services/ai_adapters.py`

AI 모델이 완성되면 아래 3개 함수의 **내부 구현만 교체**하면 된다.  
함수 이름, 파라미터, 반환 형식은 변경하지 않는다.

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
| 현재 | 1차 규칙 기반 결과를 그대로 반환 |
| 교체 | 획의 공간·시간 특징을 LSTM에 입력해 재분류 |
| 기대 효과 | 복잡한 자음/모음 조합에서 그룹핑 정확도 향상 |

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
| 현재 | stroke 개수 비교만 수행 |
| 교체 | 각 stroke의 방향 벡터 시퀀스 → LSTM → 획 레이블 분류 |
| 기대 효과 | 실제 획순 오류 감지 및 구체적 교정 메시지 제공 |

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
    "angle":        -2.5,
    "confidence":   0.97
  },
  {
    "char_id":      "char_1",
    "bounding_box": { "x": 180.0, "y": 78.0, "width": 88.0, "height": 105.0 },
    "angle":        -1.8,
    "confidence":   0.95
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
| `angle` | `float` | 기울기 (degree, 시계방향 양수) |
| `confidence` | `float` | 탐지 신뢰도 `0.0 ~ 1.0` |

**정렬 규칙**: 좌상단 → 우하단 순서 (줄 단위 y, 줄 내 x)

### 현재 상태 / 교체 목표

| 항목 | 내용 |
|------|------|
| 현재 | OpenCV contour 기반 탐지, `angle=0` 고정 |
| 교체 | CRAFT 모델 추론 결과 (회전 bbox + 기울기 포함) |
| 기대 효과 | 기울어진 글씨, 겹친 문자 영역 정확 탐지 + 실제 기울기 값 제공 |

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
