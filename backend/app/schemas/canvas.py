from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class Point(BaseModel):
    x: float
    y: float
    timestamp: int  # 클라이언트 측 ms 타임스탬프
    # 필압은 2026-09-01에 제거했다(사용자 결정). 구버전 앱이 여전히 보낼 수 있으므로
    # 필드를 남겨 두되 무시한다 — 필수로 두면 새 앱 요청이 422로 거절되고,
    # 아예 없애면 구버전 앱 요청이 (pydantic 기본 동작상 통과하긴 하나) 의도가 흐려진다.
    pressure: Optional[float] = None


class Stroke(BaseModel):
    stroke_id: str
    points: List[Point]


class CanvasMetadata(BaseModel):
    width: int
    height: int
    stroke_count: int


class GuideBox(BaseModel):
    """화면에 그려준 획순 가이드 상자 (획 좌표와 같은 캔버스 좌표계).

    **크기 채점의 절대 기준**이다. 사용자는 이 상자 위에 글씨를 쓰므로, 이걸 알아야
    "표준만큼 크게 썼는가"를 물을 수 있다. 없으면 크기는 세션 내 상대 편차로
    폴백하는데 글자가 하나뿐인 연습에서는 비교 대상이 없어 미측정으로 남는다.
    """
    x: float
    y: float
    width: float
    height: float


class CanvasAnalyzeRequest(BaseModel):
    strokes: List[Stroke]
    metadata: CanvasMetadata
    # 이 세션에서 사용자에게 제시한 목표 글자(들). "제시형" 연습 화면에서만 채워지며,
    # 없으면 획순·획방향·성분비율 채점이 생략된다 (DATA_FLOW.md §4-3, §8-A).
    target_text: Optional[str] = None
    # 획순 가이드를 그린 영역. 프론트가 그리는 값을 그대로 보낸다(2026-09-01 추가).
    guide_box: Optional[GuideBox] = None


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
    """글자 하나의 채점 결과.

    ⚠️ 대부분의 필드가 Optional인 것은 의도다 — **잴 수 없으면 None**이고 그건
    0점이 아니라 '미측정'이다(종합 점수의 분모에서도 빠진다). 연습 종류마다
    실제로 채점되는 항목이 다르다:
      · 자음·모음(낱자)  획순 · 획방향 · 크기
      · 한 글자          + 성분비율
      · 단어·문장        + 자간
    소비자는 None을 만점으로 채워 쓰지 말 것(DATA_FLOW.md §4-1의 재발 방지).
    """
    char_id: str
    # 아래 셋은 목표 글자(target_text)를 알 때만 잴 수 있다.
    stroke_order_result: Optional[dict] = None
    direction_result: Optional[dict] = None     # 획을 올바른 방향으로 그었는가(역방향)
    tilt_result: Optional[dict] = None          # 곧게 그어야 할 획의 기울기(15도 기준)
    balance_result: Optional[dict] = None       # 초·중·종성의 크기·자리 균형
    # 화면에 그릴 **성분(초·중·종성) 단위 박스**. 낱자는 성분이 하나라 None이다.
    # 각 항목: {block, jamo, role, box:{x,y,width,height}, ok, failed_items[]}
    # ok=False면 빨강 — 항목을 따로 판정해 **하나라도 오류면** False다(가중 평균 아님).
    component_boxes: Optional[list] = None
    spacing_deviation: Optional[float] = None   # 글자가 2개 이상일 때만
    size_deviation: Optional[float] = None      # 세션 내 상대 편차(폴백용)
    size_fill_ratio: Optional[float] = None     # 표준 자형 대비 크기 배율(1.0=표준)
    item_scores: dict = {}                      # {항목명: 0~100 또는 None}
    speed_profile: dict                         # 채점 미반영, 기록만
    overall_score: Optional[int] = None
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