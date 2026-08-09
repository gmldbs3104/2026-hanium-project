from pydantic import BaseModel, Field
from typing import List
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
    width: float
    height: float
    stroke_count: int


class CanvasAnalyzeRequest(BaseModel):
    strokes: List[Stroke]
    metadata: CanvasMetadata


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
    stroke_order_result: dict
    spacing_deviation: float
    size_deviation: float
    overall_score: int


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