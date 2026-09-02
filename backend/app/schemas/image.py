from pydantic import BaseModel
from typing import List, Optional


class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class DetectedChar(BaseModel):
    char_id: str
    bounding_box: BoundingBox
    angle: Optional[float] = None            # 세로획 slant (CRAFT). 측정 불가 시 None
    angle_reliable: Optional[bool] = None    # False면 angle 측정 불가 글자
    confidence: Optional[float] = None       # 탐지 신뢰도 0.0~1.0


class ImagePreprocessResponse(BaseModel):
    image_session_id: str
    width: int
    height: int
    s3_image_url: Optional[str] = None  # S3 미설정 시 null (원본 사진)
    quality_score: Optional[int] = None      # REQ-003I-4, 40점 미만이면 재촬영 권장
    retake_required: Optional[bool] = None
    # ⚠️ AI 전처리(deskew+리사이즈) 후 이미지 — width/height 및 이후 detect의
    # bounding_box는 전부 이 이미지 기준 좌표계다. 오버레이는 원본 사진이 아니라
    # 이 이미지 위에 그려야 한다 (ai/BACKEND_INTEGRATION.md §5-2).
    preprocessed_image_base64: Optional[str] = None  # PNG, base64 — 개발·디버그용
    # 사용자에게 보여줄 배경(JPEG, base64). 원본 컬러에 **회전·리사이즈만** 적용해
    # 좌표계는 위 이진본과 동일하다 — 탐지 박스를 그대로 얹을 수 있다.
    # 이진본은 AI가 실제로 본 것을 보여줘 개발 중 획 끊김·비침을 확인하기 좋지만,
    # 사용자에게는 자기가 찍은 사진이 자연스럽다(팀 결정 2026-08-16, DATA_FLOW §6.1).
    display_image_base64: Optional[str] = None
    # True면 연한 글씨 보존 모드(gentle_stretch) — 비침이 획과 함께 남을 수 있다.
    # False면 비침 제거 모드. ai.preprocessing.image_preprocessor의 applied_filters로 판정.
    preservation_mode: Optional[bool] = None


class ImageDetectResponse(BaseModel):
    image_session_id: str
    detected_chars: List[DetectedChar]
    total_detected: int


class ImageCharBox(BaseModel):
    """화면에 그릴 **글자 단위** 박스와 그 색 판정 (2026-09-01 신설).

    색은 두 가지뿐이다(사용자 결정) — 기본 초록, 아래 세 항목 중 **하나라도**
    미흡하면 빨강. 크기·기울기는 다른 글자들의 평균에서 벗어났는지, 줄 정렬은
    자기 행의 기준선에서 벗어났는지를 본다. 자간·행간은 글자 하나에 귀속되지
    않으므로 박스 색에 영향을 주지 않는다.

    ⚠️ 서버가 이미 `ok`로 판정해서 내려준다. 앱이 점수로 다시 판정하지 말 것 —
    종합 점수로 색을 정하면 한 항목을 크게 틀려도 다른 항목이 끌어올려 초록이 된다.
    """
    char_id: str
    box: BoundingBox
    ok: bool
    failed_items: List[str] = []


class ImageCharAnalysis(BaseModel):
    char_id: str
    size_deviation: float
    slant_angle: float


class ImageAnalysisResponse(BaseModel):
    image_session_id: str
    # ⚠️ 항목 점수는 측정 불가면 None이다(만점 아님). 예: 한 줄만 썼으면 행간을,
    # 행에 3글자 미만이면 기울기를 잴 수 없다. 클라이언트는 None을 "미측정"으로
    # 표시하고 평균·집계에서 제외할 것 (DATA_FLOW §4-1).
    size_uniformity_score: Optional[int] = None
    avg_slant_angle: float
    # 글자 기울기의 중앙값(도, 양수=오른쪽). '기울기 균일성'과 별개 축 —
    # 전부 똑같이 많이 기울여 쓰면 균일성은 만점이지만 이 값이 크다.
    # 점수엔 반영하지 않고 문구로만 쓴다. 측정 불가면 None.
    mean_char_slant: Optional[float] = None
    slant_consistency_score: Optional[int] = None
    line_alignment_score: Optional[int] = None
    overall_score: int
    char_analyses: List[ImageCharAnalysis]
    # 초록/빨강 박스 판정 — 앱은 이 목록만 그리면 된다(2026-09-01).
    char_boxes: List[ImageCharBox] = []
    s3_image_url: Optional[str] = None
    # 글줄 방향 — "straight" | "falling"(오른쪽으로 내려감) | "rising"(오른쪽으로 올라감).
    # ⚠️ 주석이 오래 leaning_right/leaning_left로 적혀 있었으나 코드는 그 값을 낸 적이 없다.
    # 프론트가 그 이름으로 매칭해 늘 "반듯하게 썼어요"가 뜨던 버그의 원인(2026-09-02 수정).
    overall_tilt: Optional[str] = None
    total_grade: Optional[str] = None             # "우수" | "보통" | "불량"
    clarity_warnings: List[str] = []              # 명료도 경고 (점수엔 반영 안 됨)
    # AI가 5지표로 채점하지만 기존 계약엔 3개(크기/기울기/줄 정렬)만 있었다 — 종합 점수엔
    # 이미 반영되지만 항목별로는 못 봤던 자간·행간 점수. 측정 불가(글자/행 수 부족)면 None.
    spacing_uniformity_score: Optional[int] = None
    line_spacing_uniformity_score: Optional[int] = None


class ImageFeedbackItem(BaseModel):
    target_id: str
    feedback_message: str
    severity: str  # "good" | "warning" | "error"


class ImageFeedbackResponse(BaseModel):
    image_session_id: str
    mode: str = "image"
    overall_score: int
    achievement_message: str
    feedback_items: List[ImageFeedbackItem]
