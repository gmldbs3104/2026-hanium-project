from typing import List, Dict, Any
import math
from app.core.config import settings
from app.services.ai_adapters import lstm_refine_grouping


def _stroke_centroid(points: List[Dict]) -> tuple[float, float]:
    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _stroke_bounding_box(points: List[Dict]) -> Dict[str, float]:
    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    return {"x": x_min, "y": y_min, "w": x_max - x_min, "h": y_max - y_min}


def _merge_bounding_boxes(boxes: List[Dict[str, float]]) -> Dict[str, float]:
    x_min = min(b["x"] for b in boxes)
    y_min = min(b["y"] for b in boxes)
    x_max = max(b["x"] + b["w"] for b in boxes)
    y_max = max(b["y"] + b["h"] for b in boxes)
    return {"x": x_min, "y": y_min, "w": x_max - x_min, "h": y_max - y_min}


def rule_based_grouping(strokes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    REQ-004C-1: 규칙 기반 1차 그룹핑
    획 간 공간적 거리(centroid 거리)와 시간 간격이 임계값 이하인 획들을
    동일 문자 후보로 묶는다.
    """
    if not strokes:
        return []

    groups: List[List[Dict[str, Any]]] = [[strokes[0]]]

    for stroke in strokes[1:]:
        last_stroke = groups[-1][-1]

        curr_centroid = _stroke_centroid(stroke["points"])
        last_centroid = _stroke_centroid(last_stroke["points"])
        distance = math.dist(curr_centroid, last_centroid)

        curr_start_time = stroke["points"][0]["timestamp"]
        last_end_time = last_stroke["points"][-1]["timestamp"]
        time_gap = curr_start_time - last_end_time

        if distance <= settings.stroke_distance_threshold and time_gap <= settings.stroke_time_threshold_ms:
            groups[-1].append(stroke)
        else:
            groups.append([stroke])

    return lstm_refine_grouping(groups)


def build_char_groups(stroke_groups: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    그룹핑된 획들에 char_id를 부여하고 bounding box, 신뢰도를 산출한다.
    REQ-004C-4: 신뢰도 0.5 미만은 저신뢰 플래그 마킹
    """
    char_groups = []

    for idx, group in enumerate(stroke_groups):
        boxes = [_stroke_bounding_box(s["points"]) for s in group]
        merged_box = _merge_bounding_boxes(boxes)

        # 임시 신뢰도 로직: 그룹 내 획 수가 너무 많으면 신뢰도 하락 (LSTM 도입 전 임시 휴리스틱)
        confidence = max(0.0, 1.0 - (len(group) - 1) * 0.15)

        char_groups.append({
            "char_id": f"char_{idx}",
            "strokes": group,
            "bounding_box": merged_box,
            "stroke_count": len(group),
            "confidence": round(confidence, 2),
            "low_confidence": confidence < settings.grouping_confidence_threshold,
        })

    return char_groups