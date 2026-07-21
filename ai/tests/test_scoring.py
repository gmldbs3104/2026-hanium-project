"""SFR-005I 종합점수 개편 (2026-07-20 결정) 단위 테스트.

W1: 종합점수 = clarity 제외 + 교육적 가중(정렬·균일 3:2:1)
W2: 명료도는 점수 미반영 → clarity_warnings 경고로만
W3: 종합점수에 등급(우수/보통/불량) 병기
"""
from ai.analysis.handwriting_analyzer import (
    _weighted_total,
    _total_grade,
    WEIGHTS,
    analyze_size_angle,
)


def _row_chars(n=6, base_h=100):
    """한 줄 n글자 (기울기 신뢰, 명료도 게이트 안 걸리게 충분히 큼)."""
    chars = []
    x = 50.0
    for i in range(n):
        h = base_h + (i % 3 - 1) * 2  # 98~102 약간 변동
        chars.append({
            "char_id": f"char_{i}",
            "bounding_box": {"x": x, "y": 80.0, "width": 90.0, "height": float(h)},
            "angle": 2.0, "angle_reliable": True, "confidence": 0.92,
        })
        x += 120.0
    return chars


# ── W1: 교육적 가중 (3:2:1), clarity 제외 ──────────────────────────────
def test_weighted_total_applies_3_2_1_weights_and_excludes_clarity():
    metrics = {
        "height_uniformity":       {"score": 90.0},  # w=3
        "tilt_consistency":        {"score": 60.0},  # w=2
        "stroke_width_uniformity": {"score": 30.0},  # w=1
        "clarity":                 {"score": 0.0},   # 제외돼야 함
    }
    # (90*3 + 60*2 + 30*1) / (3+2+1) = 420/6 = 70.0
    assert _weighted_total(metrics) == 70.0


def test_weighted_total_ignores_skipped_metrics():
    metrics = {
        "height_uniformity":  {"score": 80.0},        # w=3
        "spacing_uniformity": {"skipped": "부족"},     # 제외 (score 없음)
        "baseline_deviation": {"score": 40.0},        # w=3
    }
    # (80*3 + 40*3) / (3+3) = 360/6 = 60.0
    assert _weighted_total(metrics) == 60.0


def test_weights_are_3_2_1_alignment_uniformity_first():
    assert WEIGHTS["height_uniformity"] == 3
    assert WEIGHTS["baseline_deviation"] == 3
    assert WEIGHTS["line_spacing_uniformity"] == 3
    assert WEIGHTS["tilt_consistency"] == 2
    assert WEIGHTS["spacing_uniformity"] == 2
    assert WEIGHTS["stroke_width_uniformity"] == 1
    assert "clarity" not in WEIGHTS


# ── W3: 종합점수 등급 ──────────────────────────────────────────────────
def test_total_grade_thresholds():
    assert _total_grade(85.0) == "우수"
    assert _total_grade(70.0) == "보통"
    assert _total_grade(30.0) == "불량"


# ── W2: 명료도 경고화 (점수 미반영) ───────────────────────────────────
def test_clarity_not_scored_but_warned():
    chars = _row_chars()
    # 한 글자를 과폭(폭 = 높이×2)으로 만들어 merged_suspect 유발
    chars[2]["bounding_box"]["width"] = chars[2]["bounding_box"]["height"] * 2.0
    r = analyze_size_angle(chars)
    assert r["clarity_warnings"], "명료도 이상 글자에 경고가 있어야 함"
    assert "clarity" not in r["metrics"], "명료도는 점수 지표에서 제외돼야 함"
    assert 0.0 <= r["total_score"] <= 100.0


def test_serialized_result_has_total_grade_and_clarity_warnings():
    r = analyze_size_angle(_row_chars())
    assert r["total_grade"] in ("우수", "보통", "불량")
    assert "clarity_warnings" in r
