import math
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.font_standard import FontStandard

DEFAULT_FONT_STANDARD = {"standard_height": 100, "standard_width": 80, "aspect_ratio": 0.8}


async def get_font_standard(
    db: AsyncSession,
    char: Optional[str],
    font_id: str = "myeongjo",
) -> Dict[str, Any]:
    """
    font_standards DB에서 문자별 표준 서체 크기 조회.
    char가 None이거나 DB에 없으면 기본값 반환.
    TODO: CRAFT + OCR 구현 후 char를 실제 인식 결과로 채울 것.
    """
    if char is None:
        return DEFAULT_FONT_STANDARD

    result = await db.execute(
        select(FontStandard).where(
            FontStandard.char == char,
            FontStandard.font_id == font_id,
        )
    )
    standard = result.scalar_one_or_none()
    if standard is None:
        return DEFAULT_FONT_STANDARD

    return {
        "standard_height": standard.standard_height,
        "standard_width": standard.standard_width,
        "aspect_ratio": standard.aspect_ratio,
    }


def _bbox_area(bbox: Dict) -> float:
    return bbox["width"] * bbox["height"]


def analyze_size_uniformity(detected_chars: List[Dict]) -> Tuple[int, List[Dict]]:
    """
    글자 크기 균일성 점수 및 글자별 크기 편차 반환.
    편차 지표: 면적의 변동계수(CV = std/mean). CV가 낮을수록 균일.
    """
    if not detected_chars:
        return 100, []

    areas = [_bbox_area(c["bounding_box"]) for c in detected_chars]
    mean_area = sum(areas) / len(areas)
    variance = sum((a - mean_area) ** 2 for a in areas) / len(areas)
    std_area = math.sqrt(variance)
    cv = std_area / mean_area if mean_area > 0 else 0

    score = max(0, int(100 - cv * 150))

    char_analyses = []
    for char in detected_chars:
        area = _bbox_area(char["bounding_box"])
        deviation = ((area - mean_area) / mean_area * 100) if mean_area > 0 else 0.0
        char_analyses.append({
            "char_id": char["char_id"],
            "size_deviation": round(deviation, 2),
        })

    return score, char_analyses


def analyze_slant(detected_chars: List[Dict]) -> Tuple[float, int]:
    """
    글자 기울기 분석.
    각 bbox의 가로/세로 비율로 기울기를 근사하고 일관성 점수를 반환.
    Returns (avg_slant_angle, slant_consistency_score)
    실제 서비스에서는 CRAFT 회전 bbox의 angle 값을 사용 예정 (placeholder).
    """
    if not detected_chars:
        return 0.0, 100

    angles = []
    for c in detected_chars:
        bb = c["bounding_box"]
        # aspect ratio 기반 기울기 근사 (placeholder)
        ratio = bb["width"] / bb["height"] if bb["height"] > 0 else 1.0
        angle = math.degrees(math.atan(max(0.0, ratio - 1.0)))
        angles.append(angle)

    avg_angle = sum(angles) / len(angles)
    variance = sum((a - avg_angle) ** 2 for a in angles) / len(angles)
    std_angle = math.sqrt(variance)

    # 표준편차가 클수록 일관성 낮음
    consistency_score = max(0, int(100 - std_angle * 10))

    return round(avg_angle, 2), consistency_score


def analyze_line_alignment(detected_chars: List[Dict], image_height: int) -> int:
    """
    글자들이 수평선에 잘 정렬되어 있는지 평가.
    y 좌표를 줄 단위로 그룹핑한 후 그룹 내 y 분산으로 점수 산출.
    """
    if not detected_chars:
        return 100

    row_height = image_height / 8
    rows: Dict[int, List[float]] = {}
    for c in detected_chars:
        row_key = int(c["bounding_box"]["y"] / row_height)
        rows.setdefault(row_key, []).append(c["bounding_box"]["y"])

    variances = []
    for ys in rows.values():
        if len(ys) < 2:
            continue
        mean_y = sum(ys) / len(ys)
        var = sum((y - mean_y) ** 2 for y in ys) / len(ys)
        variances.append(math.sqrt(var))

    if not variances:
        return 100

    avg_variance = sum(variances) / len(variances)
    score = max(0, int(100 - avg_variance * 0.5))
    return score


def calculate_overall_score(
    size_uniformity_score: int,
    slant_consistency_score: int,
    line_alignment_score: int,
) -> int:
    return int(
        size_uniformity_score * 0.4
        + slant_consistency_score * 0.35
        + line_alignment_score * 0.25
    )
