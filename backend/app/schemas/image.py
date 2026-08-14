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
    preprocessed_image_base64: Optional[str] = None  # PNG, base64
    # True면 연한 글씨 보존 모드(gentle_stretch) — 비침이 획과 함께 남을 수 있다.
    # False면 비침 제거 모드. ai.preprocessing.image_preprocessor의 applied_filters로 판정.
    preservation_mode: Optional[bool] = None


class ImageDetectResponse(BaseModel):
    image_session_id: str
    detected_chars: List[DetectedChar]
    total_detected: int


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
    slant_consistency_score: Optional[int] = None
    line_alignment_score: Optional[int] = None
    overall_score: int
    char_analyses: List[ImageCharAnalysis]
    s3_image_url: Optional[str] = None
    overall_tilt: Optional[str] = None            # "straight" | "leaning_right" | "leaning_left"
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
