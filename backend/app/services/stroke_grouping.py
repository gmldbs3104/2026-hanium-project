from typing import List, Dict, Any, Optional
import math
from app.core.config import settings


def _stroke_centroid(points: List[Dict]) -> tuple[float, float]:
    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _stroke_bounding_box(points: List[Dict]) -> Dict[str, float]:
    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    return {"x": x_min, "y": y_min, "width": x_max - x_min, "height": y_max - y_min}


def _merge_bounding_boxes(boxes: List[Dict[str, float]]) -> Dict[str, float]:
    x_min = min(b["x"] for b in boxes)
    y_min = min(b["y"] for b in boxes)
    x_max = max(b["x"] + b["width"] for b in boxes)
    y_max = max(b["y"] + b["height"] for b in boxes)
    return {"x": x_min, "y": y_min, "width": x_max - x_min, "height": y_max - y_min}


def rule_based_grouping(
    strokes: List[Dict[str, Any]],
    expected_count: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    REQ-004C-1: 규칙 기반 1차 그룹핑
    획 간 공간적 거리(centroid 거리)와 시간 간격이 임계값 이하인 획들을
    동일 문자 후보로 묶는다.

    expected_count: 목표 텍스트 길이 등으로 몇 글자인지 미리 아는 경우(제시형 연습 —
    문장 쓰기처럼 여러 글자를 한 화면에 쓰는 상황)에 넘긴다. 있으면 고정 임계값 대신
    "획 사이 간격이 가장 크게 벌어진 (expected_count-1)곳"을 경계로 삼아 정확히
    expected_count개 그룹으로 나눈다 — 문장을 빠르게 이어 써서 글자 사이 간격이 절대
    임계값 밑으로 떨어져도 상대적으로 더 벌어진 곳을 경계로 찾아낸다. 없으면(자음/모음/
    받침 화면처럼 한 글자만 쓰는 경우) 기존 임계값 방식 그대로 동작한다.

    ⚠️ 이 함수는 `ai/canvas/stroke_grouping.py`의 `group_strokes_by_rules`와 별개
    구현이다(그쪽이 정본, 여기가 실서비스 `/canvas/{id}/group` 라우트가 실제로 쓰는 것).
    알고리즘·테스트 근거는 `ai/canvas/stroke_grouping.py`(`_group_by_expected_count`)와
    `ai/tests/test_grouping_expected_count.py`. 상세: `STATUS.md` §2·§5-5.
    """
    if not strokes:
        return []

    if expected_count and 1 <= expected_count <= len(strokes):
        return _group_by_expected_count(strokes, expected_count)

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

    return groups


def _group_by_expected_count(
    strokes: List[Dict[str, Any]],
    expected_count: int,
) -> List[List[Dict[str, Any]]]:
    """
    획을 정확히 expected_count개 그룹으로 나눈다(목표 글자 수를 아는 제시형 연습용).

    인접한 두 획 사이의 거리·시간 간격을 각각 임계값 대비 배수로 정규화한 뒤 더 큰 쪽을
    그 경계의 점수로 삼고, 점수가 가장 큰 (expected_count-1)곳을 글자 경계로 고른다.
    고정 임계값을 넘는지(이분법)가 아니라 상대적 순위로 판단하므로, 모든 간격이 임계값
    밑이어도 그 안에서 상대적으로 더 벌어진 곳을 경계로 잡는다.

    입력 순서를 시간순으로 가정한다(프론트가 획을 그린 순서대로 보냄 — 기존
    rule_based_grouping의 기본 경로와 동일한 전제).
    """
    dist_threshold = settings.stroke_distance_threshold
    time_threshold = settings.stroke_time_threshold_ms

    gaps: List[tuple[float, int]] = []  # (score, boundary_index): strokes[i]와 strokes[i+1] 사이
    for i in range(len(strokes) - 1):
        curr_centroid = _stroke_centroid(strokes[i]["points"])
        next_centroid = _stroke_centroid(strokes[i + 1]["points"])
        distance = math.dist(curr_centroid, next_centroid)

        prev_end_time = strokes[i]["points"][-1]["timestamp"]
        next_start_time = strokes[i + 1]["points"][0]["timestamp"]
        time_gap = next_start_time - prev_end_time

        dist_ratio = distance / dist_threshold if dist_threshold > 0 else 0.0
        time_ratio = time_gap / time_threshold if time_threshold > 0 else 0.0
        gaps.append((max(dist_ratio, time_ratio), i))

    n_boundaries = expected_count - 1
    boundary_indices = {i for _, i in sorted(gaps, key=lambda g: -g[0])[:n_boundaries]}

    groups: List[List[Dict[str, Any]]] = [[strokes[0]]]
    for i, stroke in enumerate(strokes[1:], start=1):
        if (i - 1) in boundary_indices:
            groups.append([stroke])
        else:
            groups[-1].append(stroke)
    return groups


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