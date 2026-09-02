"""
AI 모델 어댑터 모듈 — AI 트랙 실구현 연결본.

백엔드와 AI 모델 트랙의 연결 지점(인터페이스). 함수 이름/파라미터/반환 형식은
AI_MODEL_INTERFACE.md 계약 그대로이며, 내부 구현만 `ai/` 패키지의 실제 모듈로
교체되었다 (기존 placeholder: contour 탐지 / 개수 비교 / passthrough).

계약 함수:
  1. craft_detect_chars        — CRAFT 문자 탐지    (ai/detection/craft_detector.py)

⚠️ 종전의 lstm_refine_grouping / lstm_analyze_stroke_order 두 스텁은 2026-09-01에
제거했다. 전자는 입력을 그대로 반환했고 후자는 실사용 경로에서 쓰이지도 않았다
(analyze_canvas_writing이 기하 비교로 대체). 실사용자 필기 데이터가 없어 학습이
불가능했고, 새 채점 체계가 전부 기하 계산으로 풀린다.

추가 제공 (선택 사용):
  - preprocess_image        — SFR-003I AI 전처리, 기존 image_preprocessing.preprocess_image
                              와 동일한 (binary, width, height) 반환 계약의 드롭인 대체
  - preprocess_image_full   — 품질점수/재촬영 판정(REQ-003I-4) 포함 전체 결과
  - analyze_size_angle      — SFR-005I 크기/기울기/기준선 분석 (AI_MODEL_INTERFACE.md 4절)
  - analyze_canvas_writing  — SFR-005C 캔버스 채점 (DATA_FLOW.md §8-A).
                              획순/획방향/성분비율/크기/자간을 기하 비교로 판정한다.
  - canvas_item_scores      — 캔버스 항목별 점수. 대시보드 집계가 이걸 쓴다.
                              채점 기준을 AI가 소유하므로 백엔드에 감점 계수를 따로 두지
                              않는다 — 종전에 config.py에 다른 계수가 있어 결과 화면과
                              분석 화면 점수가 어긋났다(DATA_FLOW.md §8-G).

주의 — 전처리 좌표계:
  AI 전처리는 이진화 + 기울기 보정(deskew) + 장축 800~1280px 리사이즈를 수행하므로,
  반환되는 width/height 및 이후 craft_detect_chars의 bounding_box 좌표는 모두
  "전처리 후" 이미지 기준이다. 원본 사진 위 오버레이가 필요하면 스케일 비율
  (전처리 height / 원본 height)과 skew 각도로 역변환해야 한다.
  탐지 정확도 평가(F1@0.3=0.960, ai/DETECTION_IMPROVEMENT_PLAN.md)는 전부 이
  전처리를 전제로 하므로, 단순 Otsu 이진화 입력과 섞어 쓰면 성능이 보장되지 않는다.

주의 — CRAFT 의존성:
  craft_detect_chars는 최초 호출 시 torch/craft_text_detector를 로드한다
  (프로세스당 1회, ~4초, 이후 요청은 재사용). torch 미설치 환경에서도 캔버스
  모드 함수들은 정상 동작하도록 CRAFT 관련 import는 함수 내부에서 수행한다.
"""
import os
import sys
from typing import Any, Dict, List, Tuple

# 저장소 루트(= ai/ 패키지의 부모)를 import 경로에 추가.
# uvicorn을 backend/ 에서 실행하든 저장소 루트에서 실행하든 동일하게 동작한다.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from ai.analysis.handwriting_analyzer import analyze_size_angle  # noqa: E402,F401
from ai.canvas.canvas_quality_analyzer import (  # noqa: E402,F401
    analyze_canvas_writing,
    canvas_item_scores,
)
from ai.preprocessing.image_preprocessor import ImagePreprocessor  # noqa: E402

# 전처리기는 무상태에 가깝고 생성 비용이 거의 없지만, 관례상 모듈 전역 1개를 재사용
_PREPROCESSOR = ImagePreprocessor()


# ────────────────────────────────────────────────────────────────
# 3. CRAFT 문자 영역 탐지 (SFR-004I)
# ────────────────────────────────────────────────────────────────

def craft_detect_chars(
    binary_image_list: List[List[int]],
    image_width: int,
    image_height: int,
) -> List[Dict[str, Any]]:
    """
    이진화 이미지에서 문자 영역 Bounding Box를 탐지한다.

    구현: ai/detection/craft_detector.py — pretrained CRAFT + region 단독 디코딩
    + 적응형 long_size + 과폭 분할 + 자소→음절 병합. 모델은 프로세스당 1회만
    로드되는 싱글턴이며 동시 호출은 내부 lock으로 직렬화된다.

    Input/Output 형식은 AI_MODEL_INTERFACE.md 3절 스펙 그대로:
      → [{"char_id", "bounding_box": {x, y, width, height}, "angle",
          "angle_reliable", "confidence"}]
      (angle은 세로획 slant, angle_reliable=False면 측정 불가 글자 — 2026-07-19 개편)
      (좌상단→우하단 읽기 순서 정렬)
    """
    from ai.detection.craft_detector import craft_detect_chars as _impl
    return _impl(binary_image_list, image_width, image_height)


# ────────────────────────────────────────────────────────────────
# SFR-003I 전처리 (선택 사용 — image_preprocessing.preprocess_image 드롭인 대체)
# ────────────────────────────────────────────────────────────────

def preprocess_image(image_bytes: bytes) -> Tuple["Any", int, int]:
    """
    Raw 이미지 바이트 → (binary_image, width, height).

    기존 image_preprocessing.preprocess_image와 동일한 반환 계약이지만,
    단순 Otsu 대신 AI 전처리 파이프라인(Adaptive Threshold blockSize=15 C=5
    → Hough deskew → 장축 800~1280px 리사이즈)을 수행한다.
    width/height는 전처리 후 이미지 크기다 (모듈 docstring의 좌표계 주의 참조).

    Raises
    ------
    ValueError : 디코딩 실패 또는 10MB 초과 (REQ-003I-2)
    """
    result = _PREPROCESSOR.preprocess_from_bytes(image_bytes)
    binary = result.binary_image
    h, w = binary.shape[:2]
    return binary, w, h


def preprocess_image_full(image_bytes: bytes) -> Dict[str, Any]:
    """
    preprocess_image + 품질 판정 전체 결과.

    REQ-003I-4(품질 40점 미만 재촬영 요구)를 라우트에서 구현할 때 사용.

    Returns
    -------
    {
      "binary_image":    np.ndarray (H, W) uint8,   # 획=255, 배경=0 — **채점용**
      "display_image":   np.ndarray (H, W, 3) uint8, # 원본 컬러에 회전·리사이즈만 — **표시용**
                                                     # 좌표계가 binary_image와 같아 박스를 그대로 얹는다
      "width", "height": int,                        # 전처리 후 크기
      "quality_score":   {"total", "sharpness", "contrast", "bimodality"},
      "retake_required": bool,                       # total < 40
      "retake_reason":   str,
      "skew_angle":      float,                      # 보정된 기울기 (deg)
      "applied_filters": List[str],
    }
    """
    result = _PREPROCESSOR.preprocess_from_bytes(image_bytes)
    h, w = result.binary_image.shape[:2]
    return {
        "binary_image": result.binary_image,
        "display_image": result.display_image,
        "width": w,
        "height": h,
        "quality_score": result.quality_score,
        "retake_required": result.retake_required,
        "retake_reason": result.retake_reason,
        "skew_angle": result.skew_angle,
        "applied_filters": result.applied_filters,
    }
