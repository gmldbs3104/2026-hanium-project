"""
SFR-004C: 획 그룹핑 및 문자 단위 분할

파이프라인:
  획 시퀀스 → 규칙 기반 그룹핑(거리+시간, 또는 목표 글자 수) → char_id/bounding_box
  부여 → 저신뢰 그룹 플래그

⚠️ 종전에는 여기에 LSTM 2차 보정 단계(입력을 그대로 반환하는 스텁)가 하나 더 있었다.
실사용자 필기 데이터가 없어 학습이 불가능했고, 새 채점 체계(획순·획방향·성분비율)가
전부 기하 계산으로 풀리므로 2026-09-01에 제거했다. 되살릴 일이 생기면
group_strokes_by_rules 결과를 후처리하는 자리에 넣으면 된다.
"""
import math
from typing import Dict, List, Optional

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
    expected_count: Optional[int] = None,
) -> List[List[Dict]]:
    """
    규칙 기반 1차 그룹핑 (requirement.md Action ②).

    입력 시간순으로 훑으면서, 직전 그룹의 마지막 획과 공간적으로 가깝고(bbox 중심 거리)
    시간적으로 이어지면(간격이 짧으면) 같은 그룹에 합친다. 둘 중 하나라도 임계값을
    넘으면 새 문자 그룹 시작.

    expected_count: 목표 텍스트 길이 등으로 몇 글자인지 미리 아는 경우(제시형 연습 —
    문장 쓰기처럼 여러 글자를 한 화면에 쓰는 상황)에 넘긴다. 있으면 고정 임계값 대신
    "획 사이 간격이 가장 크게 벌어진 (expected_count-1)곳"을 경계로 삼아 정확히
    expected_count개 그룹으로 나눈다 — 임계값을 안 넘는 애매한 머뭇거림 때문에 잘못
    합쳐지는 걸 줄인다. 없으면(기존 자음/모음/받침 화면처럼 한 글자만 쓰는 경우) 지금
    방식 그대로 동작한다.

    ⚠️ **한 글자(expected_count == 1)도 이 경로를 탄다.** 종전에는 `1 < expected_count`라
    한 글자 연습이 옛 임계값(거리·시간)으로 빠졌는데, 한 글자 안의 자모끼리도 50px는 우습게
    넘어서 '각'이 3조각으로 쪼개졌다(2026-09-01 실측: 연습 글자 15개 중 8개가 쪼개짐).
    글자 수를 **가장 확실히 아는** 경우에 그 정보를 못 쓰던 셈이다. expected_count가 1이면
    자를 곳이 0개이므로 전부 한 덩어리가 된다 — 그게 정확히 원하는 동작이다.
    """
    if not strokes:
        return []

    ordered = sorted(strokes, key=lambda s: min(p["timestamp"] for p in s["points"]))

    if expected_count and 1 <= expected_count <= len(ordered):
        return _group_by_expected_count(ordered, expected_count, dist_threshold, time_threshold_ms)

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


def _group_by_expected_count(
    ordered: List[Dict],
    expected_count: int,
    dist_threshold: float,
    time_threshold_ms: float,
) -> List[List[Dict]]:
    """
    시간순 정렬된 획을 정확히 expected_count개 그룹으로 나눈다.

    인접한 두 획 사이의 "벌어진 정도"를 거리·시간 각각 임계값 대비 배수로 정규화한
    뒤 더 큰 쪽을 그 지점의 점수로 삼고, 점수가 가장 큰 (expected_count-1)곳을 글자
    경계로 고른다. 고정 임계값을 넘는지 여부(이분법)가 아니라 상대적 순위로 판단하므로,
    모든 간격이 임계값 밑이어도(예: 짧은 문장을 빠르게 이어 쓴 경우) 그 안에서 상대적으로
    더 벌어진 곳을 경계로 잡을 수 있다.
    """
    gaps = []  # (score, boundary_index) — ordered[i]와 ordered[i+1] 사이 경계
    for i in range(len(ordered) - 1):
        prev_bbox = _stroke_bbox(ordered[i])
        curr_bbox = _stroke_bbox(ordered[i + 1])
        dist = math.dist(_stroke_center(prev_bbox), _stroke_center(curr_bbox))

        _, prev_end = _stroke_time_range(ordered[i])
        curr_start, _ = _stroke_time_range(ordered[i + 1])
        gap = curr_start - prev_end

        dist_ratio = dist / dist_threshold if dist_threshold > 0 else 0.0
        time_ratio = gap / time_threshold_ms if time_threshold_ms > 0 else 0.0
        gaps.append((max(dist_ratio, time_ratio), i))

    n_boundaries = expected_count - 1
    boundary_indices = {i for _, i in sorted(gaps, key=lambda g: -g[0])[:n_boundaries]}

    groups: List[List[Dict]] = [[ordered[0]]]
    for i, stroke in enumerate(ordered[1:], start=1):
        if (i - 1) in boundary_indices:
            groups.append([stroke])
        else:
            groups[-1].append(stroke)
    return groups


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
    expected_count: Optional[int] = None,
) -> List[Dict]:
    """
    SFR-004C 전체 파이프라인: 규칙 기반 그룹핑 → 문자 단위 결과.

    expected_count: group_strokes_by_rules 참고 — 목표 텍스트 길이를 알 때(문장 쓰기 등)
    넘기면 정확히 그 개수로 그룹핑한다.

    Returns
    -------
    List[Dict] — [{char_id, strokes, bounding_box, stroke_count, confidence, low_confidence}]
    """
    groups = group_strokes_by_rules(strokes, dist_threshold, time_threshold_ms, expected_count=expected_count)

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
