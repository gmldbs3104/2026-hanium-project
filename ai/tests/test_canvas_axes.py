"""축 점수 조립(build_axes) — 세부 판정 건수 → 100/70/40, 미측정은 None.

설계: docs/superpowers/specs/2026-10-08-canvas-scoring-axes-design.md 3·4절.
"""
from ai.canvas.canvas_quality_analyzer import (
    AXIS_BALANCE, AXIS_LAYOUT, AXIS_ORDER, AXIS_SHAPE, ALL_AXES,
    axis_label, axis_score, build_axes, overall_from_axes,
)


def _axes(**kw):
    base = dict(stroke_order_result=None, direction_result=None, tilt_result=None,
                char_rotation_deg=None, corner_result=None, shape_failed=None,
                balance_result=None, size_reason=None, spacing_reason=None,
                position_failed=None)
    base.update(kw)
    return build_axes(**base)


def test_axis_score_levels():
    assert axis_score(0, measured=True) == 100
    assert axis_score(1, measured=True) == 70
    assert axis_score(2, measured=True) == 40
    assert axis_score(5, measured=True) == 40
    assert axis_score(0, measured=False) is None


def test_nothing_measured_gives_four_none_axes():
    axes = _axes()
    assert set(axes) == set(ALL_AXES)
    assert all(a["score"] is None and a["reasons"] == [] for a in axes.values())
    assert overall_from_axes(axes) is None


def test_order_axis_counts_swap_as_one():
    """두 획이 자리를 바꾼 것(어긋난 자리 2곳)은 1건이다 — 어긋난 자리 수 ÷ 2, 올림."""
    so = {"order_error_count": 2, "stroke_count": 4, "expected_count": 4, "error_count": 2}
    axes = _axes(stroke_order_result=so)
    assert axes[AXIS_ORDER]["score"] == 70
    assert axes[AXIS_ORDER]["reasons"] == ["1획 순서 틀림"]


def test_order_axis_adds_reversed_and_count():
    so = {"order_error_count": 0, "stroke_count": 3, "expected_count": 4, "error_count": 1}
    d = {"checked": 3, "error_count": 1}
    axes = _axes(stroke_order_result=so, direction_result=d)
    assert axes[AXIS_ORDER]["score"] == 40
    assert axes[AXIS_ORDER]["reasons"] == ["1획 반대로 그음", "획 수 3개 / 표준 4개"]


def test_shape_axis_counts_any_tilt_as_one_mistake():
    """획 기울기와 글자 전체 기울기는 같은 습관(기울임)이다 — 둘 다 걸려도 1건."""
    axes = _axes(tilt_result={"checked": 2, "error_count": 1},
                 char_rotation_deg=20.0, corner_result={"checked": 2, "error_count": 0},
                 shape_failed=False)
    assert axes[AXIS_SHAPE]["score"] == 70
    assert axes[AXIS_SHAPE]["reasons"] == ["1획 기울어짐", "글자 전체가 오른쪽으로 20도 기울어짐"]


def test_shape_axis_does_not_count_shape_distance_when_tilted():
    """기울여 쓰면 모양 거리도 같이 벌어진다 — 기울임이 걸린 글자의 '표준과 다른 모양'은 세지 않는다."""
    axes = _axes(char_rotation_deg=20.0, shape_failed=True)
    assert axes[AXIS_SHAPE]["score"] == 70
    assert axes[AXIS_SHAPE]["reasons"] == ["글자 전체가 오른쪽으로 20도 기울어짐"]


def test_shape_axis_tilt_plus_corner_is_two_mistakes():
    axes = _axes(tilt_result={"checked": 2, "error_count": 2},
                 corner_result={"checked": 2, "error_count": 1})
    assert axes[AXIS_SHAPE]["score"] == 40
    assert axes[AXIS_SHAPE]["reasons"] == ["2획 기울어짐", "모서리 1곳 둥글림"]


def test_shape_axis_measured_but_clean_is_100():
    axes = _axes(tilt_result={"checked": 2, "error_count": 0})
    assert axes[AXIS_SHAPE]["score"] == 100
    assert axes[AXIS_SHAPE]["reasons"] == []


def test_balance_axis_counts_failed_components():
    comps = [{"role": "초성", "jamo": "ㄱ", "balance_failed": False, "balance_reasons": []},
             {"role": "중성", "jamo": "ㅏ", "balance_failed": True, "balance_reasons": ["자리가 벗어남"]},
             {"role": "종성", "jamo": "ㄱ", "balance_failed": True, "balance_reasons": ["너무 큼", "납작함"]}]
    axes = _axes(balance_result={"components": comps})
    assert axes[AXIS_BALANCE]["score"] == 40
    assert axes[AXIS_BALANCE]["reasons"] == ["중성 'ㅏ' 자리가 벗어남", "종성 'ㄱ' 너무 큼·납작함"]


def test_layout_axis_counts_size_spacing_position():
    axes = _axes(size_reason="너무 작음", spacing_reason="", position_failed=False)
    assert axes[AXIS_LAYOUT]["score"] == 70
    assert axes[AXIS_LAYOUT]["reasons"] == ["크기 너무 작음"]
    axes = _axes(size_reason="", spacing_reason="앞 글자와 너무 좁음", position_failed=True)
    assert axes[AXIS_LAYOUT]["score"] == 40
    assert axes[AXIS_LAYOUT]["reasons"] == ["앞 글자와 너무 좁음", "글자 칸에서 벗어남"]


def test_layout_axis_unmeasured_when_nothing_given():
    """한 글자 연습 — 배치 축 자체가 없다. None이어야지 100이면 안 된다."""
    assert _axes(tilt_result={"checked": 1, "error_count": 0})[AXIS_LAYOUT]["score"] is None


def test_overall_is_mean_of_measured_axes():
    axes = _axes(stroke_order_result={"order_error_count": 0, "stroke_count": 2,
                                      "expected_count": 2, "error_count": 0},
                 tilt_result={"checked": 1, "error_count": 1})
    assert axes[AXIS_ORDER]["score"] == 100 and axes[AXIS_SHAPE]["score"] == 70
    assert overall_from_axes(axes) == 85


def test_axis_label_format():
    assert axis_label(AXIS_SHAPE, ["1획 기울어짐", "모서리 1곳 둥글림"]) == "모양(1획 기울어짐, 모서리 1곳 둥글림)"


# ── 채점 거부: 잉크 기준 (설계 5절) ─────────────────────────────────────────
from ai.canvas.canvas_quality_analyzer import (  # noqa: E402
    INK_MISMATCH_MAX, SHAPE_FAIL_DIST, _layout_for_char, assess_character_match,
    jamo_shape_failed,
)
from ai.canvas.synthetic_stroke_generator import _consonant_paths  # noqa: E402


def _strokes(paths):
    return [{"stroke_id": f"s{i}", "points": [{"x": x, "y": y, "timestamp": i * 100 + k}
                                              for k, (x, y) in enumerate(p)]}
            for i, p in enumerate(paths)]


def _tmpl(ch):
    return [p for _, ps in _layout_for_char(ch) for p in ps]


def _join(paths):
    out = list(paths[0])
    for p in paths[1:]:
        out += list(p[1:]) if p[0] == out[-1] else list(p)
    return out


def test_refusal_reasons_are_only_three():
    assert assess_character_match([], "각")["reason"] == "missing"
    scribble = [[(0.1 + 0.15 * i, 0.2), (0.2 + 0.15 * i, 0.8)] for i in range(5)]
    assert assess_character_match(_strokes(scribble), "ㅣ")["reason"] == "too_many_strokes"
    line = [[(0.2, 0.5), (0.8, 0.5)]]
    a = assess_character_match(_strokes(line), "ㄱ")
    # 딴 글자 = 획 모양으로도 다르고(거리 기록) 잉크도 제자리에 없다(0.15 초과).
    assert a["reason"] == "shape_mismatch" and a["ink_gap"] > INK_MISMATCH_MAX
    assert a["max_distance"] is not None


def test_tilted_writing_is_scored_not_refused():
    """기울여 쓴 글씨는 틀리게 쓴 것이지 다른 글자가 아니다 — 잉크 기준만으로는 거부됐다."""
    import math
    lean = math.tan(math.radians(25))
    tilted = [[(0.5 + (y - 0.5) * lean, y) for _, y in p] for p in _tmpl("ㅣ")]
    assert assess_character_match(_strokes(tilted), "ㅣ")["scorable"] is True
    ri = _tmpl("리")
    x0, y0 = ri[-1][0]
    ri[-1] = [(x0 + (y - y0) * lean, y) for _, y in ri[-1]]
    assert assess_character_match(_strokes(ri), "리")["scorable"] is True


def test_order_axis_counts_only_stroke_count_when_counts_differ():
    """획을 합쳐 쓰면 짝이 밀려 순서 어긋남이 따라 나온다 — 획 수 1건으로만 센다."""
    so = {"order_error_count": 1, "stroke_count": 1, "expected_count": 2, "error_count": 1}
    axes = build_axes(stroke_order_result=so, direction_result=None, tilt_result=None,
                      char_rotation_deg=None, corner_result=None, shape_failed=None,
                      balance_result=None, size_reason=None, spacing_reason=None,
                      position_failed=None)
    assert axes[AXIS_ORDER]["score"] == 70
    assert axes[AXIS_ORDER]["reasons"] == ["획 수 1개 / 표준 2개"]


def _guide(jamo):
    """프론트 가이드(stroke_order_data.dart `_single`)처럼 자모 원형을 상자에 **그대로** 넣는다.

    _layout_for_char의 낱자 배치는 잉크를 상자에 꽉 채워 늘리므로 사용자가 보는 가이드와
    모양이 다르다(ㅏ의 가로획이 세로획만큼 길어진다). 거부 기준은 가이드대로 쓴 글씨를
    기준으로 확인해야 한다.
    """
    from ai.canvas.stroke_standards import CHOSUNG
    from ai.canvas.synthetic_stroke_generator import _vowel_paths
    paths = _consonant_paths(jamo) if jamo in CHOSUNG else _vowel_paths(jamo)
    return [[(0.2 + x * 0.6, 0.16 + y * 0.68) for x, y in p] for p in paths]


def test_merged_and_standard_writing_are_not_refused():
    for ch in ("각", "밤", "시", "느"):
        assert assess_character_match(_strokes(_tmpl(ch)), ch)["scorable"] is True, ch
    for jamo in "ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎㅏㅑㅓㅕㅗㅛㅜㅠㅡㅣ":
        a = assess_character_match(_strokes(_guide(jamo)), jamo)
        assert a["scorable"] is True, (jamo, a)
    for jamo in ("ㄷ", "ㄹ", "ㅁ"):
        a = assess_character_match(_strokes([_join(_consonant_paths(jamo))]), jamo)
        assert a["scorable"] is True, (jamo, a)


def test_jamo_shape_failed_only_when_counts_match():
    assert jamo_shape_failed(_strokes(_tmpl("ㅁ")), "ㅁ") is False
    assert jamo_shape_failed(_strokes([_join(_tmpl("ㅁ"))]), "ㅁ") is None     # 획 수 다름 → 미측정
    assert jamo_shape_failed(_strokes(_tmpl("각")), "각") is None               # 음절 → 미측정
    squashed = [[(0.2, 0.4), (0.2, 0.6)], [(0.2, 0.4), (0.8, 0.4), (0.8, 0.6)], [(0.2, 0.6), (0.8, 0.6)]]
    assert jamo_shape_failed(_strokes(squashed), "ㅁ") is True                 # 세로로 납작한 ㅁ
    assert SHAPE_FAIL_DIST == 0.15
