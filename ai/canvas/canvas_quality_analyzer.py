"""
SFR-005C: 획순 / 자간 / 크기 분석 (종합)

requirement.md SFR-005C Output 스펙 준수:
  캔버스 분석 결과 목록 [{char_id, stroke_order_result, spacing_deviation(px),
  size_deviation(%), pressure_profile, speed_profile, overall_score(0~100),
  correction_flags[]}]

stroke_grouping.py(SFR-004C)의 char_groups 출력 + 각 글자의 목표 텍스트
(target_text — "제시형" 연습 화면에서는 앱이 미리 알고 있음, CANVAS_DATA_PLAN.md 참고)
를 받아서 획순·자간·크기를 함께 판단한다.

한계 노트
--------
- 획순 위치 매칭(analyze_stroke_order_by_position)은 중심점+모양(가로/세로 비율)
  기반 기하 비교라, 자모 내 두 획이 극단적으로 겹쳐 있거나 사용자가 표준과 완전히
  다른 위치에 그리면 오판할 수 있다. "어떤 stroke가 정확히 무슨 글자·획인지"를
  일반적으로 인식하는 수준의 정교함은 아니고, 목표 글자를 이미 아는 상황(제시형
  UI) 한정으로 쓸 수 있는 근사치.
- pressure_profile/speed_profile: 필압 센서 미지원 기기에서는 pressure가 항상
  1.0로 고정되어(canvas_input_screen.dart 참고) 의미 있는 신호가 아닐 수 있음.
"""
import math
from typing import Dict, List, Optional, Tuple

from stroke_grouping import _stroke_bbox
from stroke_standards import get_expected_sequence, lstm_analyze_stroke_order, decompose_syllable
from synthetic_stroke_generator import _syllable_layout

# 크기/간격 판정 임계값 (handwriting_analyzer.py와 동일한 CV 기반 설계)
SIZE_SCORE_MAX_CV = 0.30
SIZE_LARGE_THRESH = 1.5
SIZE_SMALL_THRESH = 0.65

# 자간: 인접 글자 bbox 간 gap을 "평균 글자 너비" 대비 비율로 판단
SPACING_MIN_RATIO = 0.15   # 이보다 좁으면 너무 붙어씀
SPACING_MAX_RATIO = 1.2    # 이보다 넓으면 너무 띄어씀
SPACING_SCORE_MAX_DEV = 1.0  # 비율 편차 1.0(=평균너비만큼 벗어남) → 0점

# 획순 매칭 시 위치 거리 대비 모양(가로/세로 비율) 차이에 두는 가중치.
# 자모 내 두 획의 중심점이 서로 가까운 경우(예: ㅏ의 세로선과 가로 짧은 획)
# 위치만으로는 헷갈리기 쉬워서, 모양(길쭉한 방향)도 같이 비교해 구분한다.
SHAPE_WEIGHT = 1.5

# 목표 글자와 완전히 다른 걸 썼는지 판단하는 임계값 (둘 중 하나라도 넘으면 "다른 글자로 보임")
MATCH_QUALITY_THRESHOLD = 0.6        # 매칭된 획들의 평균 위치+모양 오차 (정규화 좌표 기준)
COUNT_MISMATCH_RATIO_THRESHOLD = 2.0  # 실제 획수/기대 획수 비율이 이 배수 이상 벗어나면 의심


def _path_descriptor(path: List[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    """path의 (중심x, 중심y, 너비, 높이)."""
    xs = [p[0] for p in path]
    ys = [p[1] for p in path]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    return cx, cy, max(xs) - min(xs), max(ys) - min(ys)


def _descriptor_distance(a: Tuple[float, float, float, float],
                          b: Tuple[float, float, float, float]) -> float:
    pos_dist   = math.dist(a[:2], b[:2])
    shape_dist = math.dist(a[2:], b[2:])
    return pos_dist + SHAPE_WEIGHT * shape_dist


def _canonical_stroke_points(target_char: str) -> List[Tuple[str, Tuple[float, float, float, float]]]:
    """목표 글자의 기대 획 순서를 (자모라벨, (cx,cy,w,h)) 리스트로 반환 (정규화 [0,1] 공간).
    synthetic_stroke_generator.py의 기하 템플릿을 그대로 재사용한다."""
    decomposed = decompose_syllable(target_char)
    if decomposed is None:
        return []
    cho, jung, jong = decomposed
    layout = _syllable_layout(cho, jung, jong)
    return [(jamo_label, _path_descriptor(path)) for jamo_label, paths in layout for path in paths]


def _actual_stroke_centroid(stroke: Dict, bbox: Dict) -> Tuple[float, float, float, float]:
    """실제 stroke의 (중심x,중심y,너비,높이)를 글자 bounding box 기준 [0,1] 정규화 좌표로 변환."""
    xs = [p["x"] for p in stroke["points"]]
    ys = [p["y"] for p in stroke["points"]]
    bw, bh = bbox["width"] or 1.0, bbox["height"] or 1.0
    cx = (sum(xs) / len(xs) - bbox["x"]) / bw
    cy = (sum(ys) / len(ys) - bbox["y"]) / bh
    w = (max(xs) - min(xs)) / bw
    h = (max(ys) - min(ys)) / bh
    return (cx, cy, w, h)


def analyze_stroke_order_by_position(strokes: List[Dict], bbox: Dict, target_char: str) -> Dict:
    """
    ML 분류 모델 없이 순서 오류를 감지하는 위치 기반 획순 분석.

    아이디어: "이 획이 무슨 모양인지"를 처음부터 분류할 필요 없이(그건 실제로 학습
    데이터가 필요한 문제), 목표 글자를 이미 아는 상황(제시형 UI)이라는 점을 이용해
    "N번째로 그린 획이 표준상 기대되는 N번째 위치에 있는가"만 비교한다 — 순수 기하
    비교라 학습 데이터가 필요 없다. 타임스탬프(그린 순서)는 strokes 리스트 순서
    그대로 사용한다(stroke_grouping.py가 이미 시간순 정렬해서 넘겨줌).
    """
    canonical = _canonical_stroke_points(target_char)
    if not canonical or not strokes:
        return {
            "expected_sequence": [c[0] for c in canonical],
            "actual_sequence": [],
            "error_count": 0,
            "corrections": [],
        }

    actual_centroids = [_actual_stroke_centroid(s, bbox) for s in strokes]

    # 사용자가 그린 순서대로, 아직 안 쓰인 정답 획 중 위치가 가장 가까운 것에 그리디 매칭
    remaining = list(range(len(canonical)))
    matched_indices: List[int] = []
    matched_dists: List[float] = []
    for ac in actual_centroids:
        if not remaining:
            matched_indices.append(-1)
            continue
        best_idx = min(remaining, key=lambda ci: _descriptor_distance(ac, canonical[ci][1]))
        matched_indices.append(best_idx)
        matched_dists.append(_descriptor_distance(ac, canonical[best_idx][1]))
        remaining.remove(best_idx)

    # ── 애초에 목표 글자를 쓴 게 맞는지 먼저 확인 ──────────────────────────
    # 목표와 전혀 다른 글자(혹은 낙서)를 썼다면, 그걸 억지로 목표 템플릿에 끼워
    # 맞춰서 "몇 번째 획이 틀렸다"는 세부 피드백을 주는 건 오히려 혼란만 줌.
    # (1) 매칭된 획들의 평균 위치·모양 오차가 크거나 (2) 획 수 자체가 크게
    # 다르면 "다른 글자로 보임"으로 판단하고 세부 피드백은 생략한다.
    avg_match_dist = sum(matched_dists) / len(matched_dists) if matched_dists else 1.0
    count_ratio = len(strokes) / len(canonical) if canonical else 1.0
    likely_wrong_character = (
        avg_match_dist > MATCH_QUALITY_THRESHOLD
        or count_ratio > COUNT_MISMATCH_RATIO_THRESHOLD
        or count_ratio < 1.0 / COUNT_MISMATCH_RATIO_THRESHOLD
    )

    if likely_wrong_character:
        return {
            "expected_sequence": [c[0] for c in canonical],
            "actual_sequence": [canonical[m][0] if m != -1 else "unknown" for m in matched_indices],
            "error_count": len(canonical),
            "likely_wrong_character": True,
            "corrections": [f"목표 글자('{target_char}')와 많이 달라 보입니다. 다시 확인해주세요."],
        }

    # matched_indices[i] == i  →  i번째로 그린 획이 표준 순서상으로도 i번째 위치가 맞음
    error_count = sum(1 for i, m in enumerate(matched_indices) if m != i)
    corrections: List[str] = []
    for i, m in enumerate(matched_indices):
        if m not in (i, -1):
            corrections.append(
                f"{i + 1}번째로 그린 획은 표준 순서상 {m + 1}번째({canonical[m][0]}) "
                f"위치에 그려야 합니다."
            )
    if len(strokes) != len(canonical):
        corrections.append(
            f"획 수가 {'부족합니다' if len(strokes) < len(canonical) else '많습니다'} "
            f"(작성 {len(strokes)}개 / 표준 {len(canonical)}개)"
        )

    return {
        "expected_sequence": [c[0] for c in canonical],
        "actual_sequence": [canonical[m][0] if m != -1 else "unknown" for m in matched_indices],
        "error_count": error_count,
        "likely_wrong_character": False,
        "corrections": corrections,
    }


def _stroke_speed_stats(strokes: List[Dict]) -> Dict:
    """stroke 좌표+시간으로부터 평균 속도(px/ms), 평균 필압을 계산."""
    speeds = []
    pressures = []
    for stroke in strokes:
        pts = stroke["points"]
        pressures.extend(p["pressure"] for p in pts)
        for i in range(1, len(pts)):
            dt = pts[i]["timestamp"] - pts[i - 1]["timestamp"]
            if dt <= 0:
                continue
            dist = math.dist((pts[i]["x"], pts[i]["y"]), (pts[i - 1]["x"], pts[i - 1]["y"]))
            speeds.append(dist / dt)

    return {
        "mean_speed_px_per_ms": round(sum(speeds) / len(speeds), 4) if speeds else 0.0,
        "mean_pressure": round(sum(pressures) / len(pressures), 3) if pressures else 0.0,
    }


def analyze_canvas_writing(
    char_groups: List[Dict],
    target_text: Optional[str] = None,
) -> List[Dict]:
    """
    SFR-005C 종합 분석.

    Parameters
    ----------
    char_groups : stroke_grouping.group_strokes_into_chars() 반환값
                  (읽기 순서 = 리스트 순서로 가정)
    target_text : 이 캔버스 세션에서 사용자에게 제시한 목표 텍스트.
                  "제시형" 연습 화면(CANVAS_DATA_PLAN.md 5.1)처럼 목표를 미리
                  아는 경우에만 획순 채점이 가능 — None이면 크기/자간만 채점하고
                  stroke_order_result는 비워둔다.

    Returns
    -------
    List[Dict] — char_id별 {stroke_order_result, spacing_deviation, size_deviation,
                 pressure_profile, speed_profile, overall_score, correction_flags}
    """
    if not char_groups:
        return []

    heights = [g["bounding_box"]["height"] for g in char_groups]
    widths  = [g["bounding_box"]["width"] for g in char_groups]
    median_h = sorted(heights)[len(heights) // 2]
    mean_w   = sum(widths) / len(widths)

    results: List[Dict] = []
    for i, group in enumerate(char_groups):
        bb = group["bounding_box"]
        correction_flags: List[str] = []

        # ── 크기 분석 ──────────────────────────────────────────────
        size_ratio = (bb["height"] / median_h) if median_h > 0 else 1.0
        size_deviation_pct = round((size_ratio - 1.0) * 100.0, 1)
        if size_ratio > SIZE_LARGE_THRESH:
            correction_flags.append("size_large")
        elif size_ratio < SIZE_SMALL_THRESH:
            correction_flags.append("size_small")

        # ── 자간 분석 (이전 글자와의 간격) ────────────────────────────
        spacing_deviation_px = 0.0
        if i > 0:
            prev_bb = char_groups[i - 1]["bounding_box"]
            gap = bb["x"] - (prev_bb["x"] + prev_bb["width"])
            expected_gap = mean_w * 0.4  # 표준 자간 근사치(평균 글자폭의 40%)
            spacing_deviation_px = round(gap - expected_gap, 1)
            gap_ratio = gap / mean_w if mean_w > 0 else 0.0
            if gap_ratio < SPACING_MIN_RATIO:
                correction_flags.append("spacing_too_narrow")
            elif gap_ratio > SPACING_MAX_RATIO:
                correction_flags.append("spacing_too_wide")

        # ── 획순 분석 (target_text가 있을 때만) ───────────────────────
        # 위치 기반 매칭(analyze_stroke_order_by_position) 사용 — 목표 글자를
        # 아는 상황이라 ML 분류 없이 기하 템플릿과 비교해서 순서 오류까지 감지 가능.
        stroke_order_result = None
        order_error_count = 0
        if target_text and i < len(target_text):
            stroke_order_result = analyze_stroke_order_by_position(
                group["strokes"], bb, target_text[i]
            )
            order_error_count = stroke_order_result["error_count"]
            if order_error_count > 0:
                correction_flags.append("stroke_order_error")

        # ── 필압/속도 ─────────────────────────────────────────────
        motion_stats = _stroke_speed_stats(group["strokes"])

        # ── 종합 점수 (0~100, 세 항목 감점 방식) ───────────────────────
        size_penalty    = min(50.0, abs(size_deviation_pct) * 0.8)
        spacing_penalty = min(30.0, abs(spacing_deviation_px) * 0.3) if i > 0 else 0.0
        order_penalty   = min(40.0, order_error_count * 15.0) if stroke_order_result else 0.0
        overall_score = max(0, round(100 - size_penalty - spacing_penalty - order_penalty))

        results.append({
            "char_id": group["char_id"],
            "stroke_order_result": stroke_order_result,
            "spacing_deviation": spacing_deviation_px,
            "size_deviation": size_deviation_pct,
            "pressure_profile": {"mean_pressure": motion_stats["mean_pressure"]},
            "speed_profile": {"mean_speed_px_per_ms": motion_stats["mean_speed_px_per_ms"]},
            "overall_score": overall_score,
            "correction_flags": correction_flags,
        })

    return results
