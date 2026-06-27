from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.stroke_standard import StrokeStandard

DEFAULT_STANDARD = {"standard_height": 100, "standard_width": 100, "standard_spacing": 20}


async def get_standard(db: AsyncSession, char: Optional[str]) -> Dict[str, Any]:
    """표준 획순 DB에서 조회. 없으면 기본값 사용 (TODO: 11,172자 데이터 채우기)"""
    if char is None:
        return DEFAULT_STANDARD

    result = await db.execute(select(StrokeStandard).where(StrokeStandard.char == char))
    standard = result.scalar_one_or_none()
    if standard is None:
        return DEFAULT_STANDARD

    return {
        "standard_height": standard.standard_height,
        "standard_width": standard.standard_width,
        "standard_spacing": standard.standard_spacing,
        "expected_sequence": standard.expected_sequence,
    }


def analyze_stroke_order(char_group: Dict[str, Any], standard: Dict[str, Any]) -> Dict[str, Any]:
    """
    REQ-005C-3: 획순 분석 (LSTM 모델 도입 전 임시 로직)
    TODO: 실제로는 방향 벡터 시퀀스를 LSTM에 입력해서 비교해야 함.
    지금은 stroke 개수만 비교하는 단순 placeholder.
    """
    expected_sequence = standard.get("expected_sequence", [])
    actual_sequence = [f"stroke_{i}" for i in range(char_group["stroke_count"])]

    error_count = abs(len(expected_sequence) - len(actual_sequence)) if expected_sequence else 0

    return {
        "expected_sequence": expected_sequence,
        "actual_sequence": actual_sequence,
        "error_count": error_count,
    }


def analyze_spacing(prev_box: Optional[Dict[str, float]], curr_box: Dict[str, float], standard_spacing: float) -> float:
    """REQ-005C-1: 자간 분석 - 인접 문자 bounding box 간 거리 측정"""
    if prev_box is None:
        return 0.0

    actual_gap = curr_box["x"] - (prev_box["x"] + prev_box["w"])
    deviation = actual_gap - standard_spacing
    return round(deviation, 2)


def analyze_size(box: Dict[str, float], standard_height: float, standard_width: float) -> float:
    """REQ-005C-1: 크기 분석 - 표준 대비 크기 편차(%)"""
    height_ratio = (box["h"] / standard_height) * 100 if standard_height else 100
    width_ratio = (box["w"] / standard_width) * 100 if standard_width else 100
    avg_ratio = (height_ratio + width_ratio) / 2
    deviation_percent = round(avg_ratio - 100, 2)
    return deviation_percent


def calculate_overall_score(stroke_order_error: int, spacing_deviation: float, size_deviation: float) -> int:
    """REQ-005C-1, REQ-005C-6: 가중 합산 종합 점수 (가중치는 추후 설정 파일화 가능)"""
    stroke_order_penalty = stroke_order_error * 10
    spacing_penalty = min(abs(spacing_deviation) * 0.5, 30)
    size_penalty = min(abs(size_deviation) * 0.5, 30)

    score = 100 - stroke_order_penalty - spacing_penalty - size_penalty
    return max(0, min(100, round(score)))