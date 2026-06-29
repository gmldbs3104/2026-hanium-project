# AI 모듈 — 손글씨 교정 플랫폼

2026 한이음 ICT 멘토링 프로젝트 AI 트랙.  
카메라 이미지에서 한글 손글씨를 전처리하고 글자 단위로 탐지합니다.

---

## 디렉토리 구조

```
ai/
├── preprocessing/
│   ├── image_preprocessor.py   # SFR-003I: 이미지 전처리 파이프라인
│   ├── quality_scorer.py       # 품질 점수 산출
│   └── perspective_corrector.py
├── detection/
│   ├── craft_detector.py       # SFR-004I: CRAFT + Column Projection 글자 탐지
│   └── bbox_utils.py           # Reading order 정렬, bbox 유틸
├── tests/
│   └── test_preprocessor.py
├── debug_levels.py             # 3단계 시각화 스크립트 (행→단어→글자)
├── AI_MODEL_INTERFACE.md       # 백엔드 연결 인터페이스 스펙
└── requirement.md              # 시스템 기능 요구사항 (SFR)
```

---

## 구현 현황

### SFR-003I · 이미지 전처리 (`preprocessing/image_preprocessor.py`)

카메라 입력 이미지를 CRAFT 탐지에 적합한 이진 이미지로 변환합니다.

| 단계 | 내용 |
|------|------|
| Grayscale | BGR → 흑백 변환 |
| Gaussian Blur | 노이즈 제거 (5×5 커널) |
| 품질 점수 | 밝기·선명도 기반 40점 미만 시 재촬영 요청 |
| Adaptive Threshold | 조명 불균일 보정 (THRESH_BINARY_INV) |
| Deskew | Hough 변환 기반 기울기 보정 (±6° 이내) |
| Resize | 긴 변 최대 1280px, 최소 800px (소형 이미지 업스케일 포함) |

**입력**: 카메라 이미지 (파일 / bytes / base64)  
**출력**: `PreprocessResult` — 이진 이미지 + 품질 점수 + 기울기 각도

### SFR-004I · 글자 탐지 (`detection/craft_detector.py`)

CRAFT 텍스트 탐지 모델과 Column Projection을 결합해 글자 단위 bounding box를 반환합니다.

**파이프라인**

```
CRAFT → 행(row) 탐지
      → y-overlap 기준 행 병합
      → Column Projection으로 글자 경계 탐지
      → 좁은 span 병합 (노이즈 조각 제거)
      → 넓은 span 재분할 (붙은 글자 분리)
      → 실제 잉크 bounding box 정밀화 (수평·수직 패딩 포함)
      → Reading order 정렬 (위→아래, 좌→우)
```

**출력 형식** (백엔드 인터페이스 규격)

```json
[
  {
    "char_id": "char_0",
    "bounding_box": { "x": 116, "y": 67, "width": 232, "height": 290 },
    "angle": 0.0,
    "confidence": 1.0
  }
]
```

---

## 테스트 결과

| 이미지 | 종류 | 행 | 단어 | 글자 |
|--------|------|----|------|------|
| test.jpg | 손글씨 | 3 | 3 | 10 |
| test2.png | 폰트 | 3 | 8 | 23 |

**test.jpg** (한이음 / 프로젝트 / 두둥실)  
→ 한(1) 이(2) 음(3) / 프(4) 로(5) 젝(6) 트(7) / 두(8) 둥(9) 실(10) — 음절 단위 완전 분리

**test2.png** (안녕하세요 한이음 / ICT 프로젝트 두둥실 / 객체 인식 테스트)  
→ 23글자 정상 탐지 (ICT는 1덩어리로 처리)

---

## 설치 및 실행

```bash
# 가상환경 생성 및 활성화
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # macOS/Linux

# 의존성 설치
pip install opencv-python numpy craft-text-detector
```

### 3단계 시각화 실행

```bash
cd ai
python debug_levels.py
# debug_output/ 폴더에 level1_rows.jpg / level2_words.jpg / level3_chars.jpg 생성
```

---

## 백엔드 연결 인터페이스

`AI_MODEL_INTERFACE.md` 참고.  
백엔드 `backend/app/services/ai_adapters.py`의 아래 함수와 연결됩니다.

| 함수 | SFR | 상태 |
|------|-----|------|
| `craft_detect_chars()` | SFR-004I | ✅ 구현 완료 |
| `lstm_refine_grouping()` | SFR-004C | 🔲 미구현 (placeholder) |
| `lstm_analyze_stroke_order()` | SFR-005C | 🔲 미구현 (placeholder) |

---

## 앞으로 구현할 것

- **SFR-005I**: 크기 균일성 / 기울기 분석
- **SFR-004C**: 캔버스 획 그룹핑 LSTM 연결
- **SFR-005C**: 획순 분석 LSTM 연결
- **SFR-007**: 교정 피드백 생성 로직
