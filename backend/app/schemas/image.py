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
    size_uniformity_score: int
    avg_slant_angle: float
    slant_consistency_score: int
    line_alignment_score: int
    overall_score: int
    char_analyses: List[ImageCharAnalysis]
    s3_image_url: Optional[str] = None
    overall_tilt: Optional[str] = None            # "straight" | "leaning_right" | "leaning_left"
    total_grade: Optional[str] = None             # "우수" | "보통" | "불량"
    clarity_warnings: List[str] = []              # 명료도 경고 (점수엔 반영 안 됨)


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
