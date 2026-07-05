from pydantic import BaseModel
from typing import List, Any
from datetime import date


class PeriodSummary(BaseModel):
    total_sessions: int
    avg_score: float
    improvement_rate: float  # 전반부 대비 후반부 점수 변화율 (%)
    canvas_sessions: int
    image_sessions: int


class WeakItem(BaseModel):
    item: str        # 항목명 (획순 / 자간 / 크기 / 크기 균일성 / 기울기 일관성 / 줄 정렬)
    avg_score: float
    frequency: int   # 해당 항목이 집계된 세션 수
    mode: str        # "canvas" | "image"


class ScoreTrendPoint(BaseModel):
    date: date
    avg_score: float
    mode: str        # "canvas" | "image"


class DashboardResponse(BaseModel):
    period_summary: PeriodSummary
    weak_items: List[WeakItem]
    score_trend: List[ScoreTrendPoint]
    recommended_exercises: List[Any] = []  # TODO: 연습 예문 DB 구축 후 구현
    is_new_user: bool = False              # True이면 프론트에서 온보딩 뷰 표시 (REQ-008-5)
