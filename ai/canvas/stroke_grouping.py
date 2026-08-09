"""
SFR-004C: 획 그룹핑 및 문자 단위 분할

파이프라인 (requirement.md Action ①~⑥):
  획 시퀀스 → 규칙 기반 1차 그룹핑(거리+시간) → lstm_refine_grouping(현재 placeholder)
  → char_id/bounding_box 부여 → 저신뢰 그룹 플래그

AI_MODEL_INTERFACE.md 섹션 1(lstm_refine_grouping) 스펙 준수.
"""
import math
from typing import Dict, List

# REQ-004C-2: 설정 파일로 조정 가능해야 함 — 일단 모듈 상수로 노출
DIST_THRESHOLD_PX   = 60.0   # 획 bbox 중심 간 최대 허용 거리
TIME_THRESHOLD_MS    = 400.0  # 이전 획 종료 ~ 다음 획 시작 최대 허용 시간 간격
MAX_STROKES_PER_CHAR = 8      # 자모 결합 규칙 반영(REQ-004C-5)의 단순화 버전 —
                                # 초성+중성+종성이 아무리 복잡해도 한 글자당 획 수는
                                # 이 이상을 넘기지 않는다고 가정해 폭주 병합을 방지
LOW_CONFIDENCE_THRESH = 0.5    # REQ-004C-4


def _stroke_bbox(stroke: Dict) -> Dict:
    xs = [p["x"] for p in stroke["points"]]
    ys = [p["y"] for p in stroke["points"]]
    return {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}


def _stroke_center(bbox: Dict) -> tuple:
    return (bbox["x"] + bbox["width"] / 2.0, bbox["y"] + bbox["height"] / 2.0)


def _stroke_time_range(stroke: Dict) -> tuple:
    ts = [p["timestamp"] for p in stroke["points"]]
    return min(ts), max(ts)


def group_strokes_by_rules(
    strokes: List[Dict],
    dist_threshold: float = DIST_THRESHOLD_PX,
    time_threshold_ms: float = TIME_THRESHOLD_MS,
    max_strokes_per_group: int = MAX_STROKES_PER_CHAR,
) -> List[List[Dict]]:
    """
    규칙 기반 1차 그룹핑 (requirement.md Action ②).

    입력 시간순으로 훑으면서, 직전 그룹의 마지막 획과 공간적으로 가깝고(bbox 중심 거리)
    시간적으로 이어지면(간격이 짧으면) 같은 그룹에 합친다. 둘 중 하나라도 임계값을
    넘으면 새 문자 그룹 시작.
    """
    if not strokes:
        return []

    ordered = sorted(strokes, key=lambda s: min(p["timestamp"] for p in s["points"]))

    groups: List[List[Dict]] = [[ordered[0]]]

    for stroke in ordered[1:]:
        current_group = groups[-1]
        prev_stroke = current_group[-1]

        prev_bbox = _stroke_bbox(prev_stroke)
        curr_bbox = _stroke_bbox(stroke)
        dist = math.dist(_stroke_center(prev_bbox), _stroke_center(curr_bbox))

        _, prev_end = _stroke_time_range(prev_stroke)
        curr_start, _ = _stroke_time_range(stroke)
        gap = curr_start - prev_end

        same_char = (
            dist <= dist_threshold
            and gap <= time_threshold_ms
            and len(current_group) < max_strokes_per_group
        )
        if same_char:
            current_group.append(stroke)
        else:
            groups.append([stroke])

    return groups


def lstm_refine_grouping(stroke_groups: List[List[Dict]]) -> List[List[Dict]]:
    """
    AI_MODEL_INTERFACE.md 섹션 1 규격 함수.

    현재: 1차 규칙 기반 결과를 그대로 반환 (placeholder).
    교체 목표: 획의 공간·시간 특징을 LSTM에 입력해 재분류 — 실 사용자 필기 stroke
    학습 데이터가 확보되기 전까지는 학습이 불가능해 스텁으로 유지.
    """
    return stroke_groups


def _group_confidence(group: List[Dict], dist_threshold: float, time_threshold_ms: float) -> float:
    """
    그룹 내 인접 획 쌍들의 거리/시간 간격이 임계값에 얼마나 여유 있게 못 미치는지로
    신뢰도를 근사. 여유가 클수록(임계값에서 멀수록) 1.0에 가깝고, 임계값에 바짝
    붙어 있을수록 0에 가깝다. 단일 획 그룹은 항상 1.0.
    """
    if len(group) <= 1:
        return 1.0

    margins = []
    for i in range(1, len(group)):
        prev_bbox = _stroke_bbox(group[i - 1])
        curr_bbox = _stroke_bbox(group[i])
        dist = math.dist(_stroke_center(prev_bbox), _stroke_center(curr_bbox))
        _, prev_end = _stroke_time_range(group[i - 1])
        curr_start, _ = _stroke_time_range(group[i])
        gap = curr_start - prev_end

        dist_margin = max(0.0, 1.0 - dist / dist_threshold) if dist_threshold > 0 else 1.0
        time_margin = max(0.0, 1.0 - gap / time_threshold_ms) if time_threshold_ms > 0 else 1.0
        margins.append(min(dist_margin, time_margin))

    return float(sum(margins) / len(margins))


def group_strokes_into_chars(
    strokes: List[Dict],
    dist_threshold: float = DIST_THRESHOLD_PX,
    time_threshold_ms: float = TIME_THRESHOLD_MS,
) -> List[Dict]:
    """
    SFR-004C 전체 파이프라인: 규칙 기반 그룹핑 → lstm_refine_grouping → 문자 단위 결과.

    Returns
    -------
    List[Dict] — [{char_id, strokes, bounding_box, stroke_count, confidence, low_confidence}]
    """
    groups = group_strokes_by_rules(strokes, dist_threshold, time_threshold_ms)
    groups = lstm_refine_grouping(groups)

    result: List[Dict] = []
    for i, group in enumerate(groups):
        bboxes = [_stroke_bbox(s) for s in group]
        x0 = min(b["x"] for b in bboxes)
        y0 = min(b["y"] for b in bboxes)
        x1 = max(b["x"] + b["width"] for b in bboxes)
        y1 = max(b["y"] + b["height"] for b in bboxes)
        confidence = _group_confidence(group, dist_threshold, time_threshold_ms)

        result.append({
            "char_id": f"char_{i}",
            "strokes": group,
            "bounding_box": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0},
            "stroke_count": len(group),
            "confidence": round(confidence, 3),
            "low_confidence": confidence < LOW_CONFIDENCE_THRESH,   # REQ-004C-4
        })
    return result
