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
    # 게이미피케이션(요구사항 문서에 없는 프론트 자체 추가 기능) — period/mode 필터와 무관하게
    # 항상 "전체 기간" 기준으로 계산한다.
    level: int = 1                # 1 + 전체 누적 세션 수 // 5
    streak_days: int = 0          # 오늘(또는 어제까지) 기준 연속 연습일 수
