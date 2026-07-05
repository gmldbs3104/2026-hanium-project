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


class ImagePreprocessResponse(BaseModel):
    image_session_id: str
    width: int
    height: int
    s3_image_url: Optional[str] = None  # S3 미설정 시 null


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
