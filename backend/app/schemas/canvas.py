from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class Point(BaseModel):
    x: float
    y: float
    pressure: float
    timestamp: int  # 클라이언트 측 ms 타임스탬프


class Stroke(BaseModel):
    stroke_id: str
    points: List[Point]


class CanvasMetadata(BaseModel):
    width: int
    height: int
    stroke_count: int


class CanvasAnalyzeRequest(BaseModel):
    strokes: List[Stroke]
    metadata: CanvasMetadata
    # 이 세션에서 사용자에게 제시한 목표 글자(들). "제시형" 연습 화면에서만 채워지며,
    # 없으면 획순 채점은 생략되고 크기/자간만 채점된다 (DATA_FLOW.md §4-3, §8-A).
    target_text: Optional[str] = None


class CanvasAnalyzeResponse(BaseModel):
    canvas_session_id: str
    stroke_count: int
    status: str = "received"

class CharGroup(BaseModel):
    char_id: str
    bounding_box: dict
    stroke_count: int
    confidence: float
    low_confidence: bool


class CanvasGroupResponse(BaseModel):
    canvas_session_id: str
    char_groups: List[CharGroup]
    low_confidence_count: int

class CanvasCharAnalysis(BaseModel):
    char_id: str
    # target_text가 없거나 해당 글자 위치를 벗어나면 None (획순 채점 생략)
    stroke_order_result: Optional[dict] = None
    spacing_deviation: float
    size_deviation: float
    pressure_profile: dict
    speed_profile: dict
    overall_score: int
    correction_flags: List[str]


class CanvasAnalysisResponse(BaseModel):
    canvas_session_id: str
    results: List[CanvasCharAnalysis]

class FeedbackItem(BaseModel):
    target_id: str
    feedback_message: str
    severity: str  # "good" | "warning" | "error"


class CanvasFeedbackResponse(BaseModel):
    canvas_session_id: str
    mode: str = "canvas"
    overall_score: int
    achievement_message: str
    feedback_items: List[FeedbackItem]