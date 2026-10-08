"""캔버스 채점 — 축 구조 (2026-10-08 재설계).

단계마다 측정되는 축이 다르고(자모음: 획순·모양 / 한 글자: +짜임새 / 문장: +배치),
축 점수는 100/70/40, 글자 점수는 측정된 축 평균이다.
설계: docs/superpowers/specs/2026-10-08-canvas-scoring-axes-design.md
"""
import math
import random

from ai.canvas.canvas_quality_analyzer import (
    AXIS_BALANCE, AXIS_LAYOUT, AXIS_ORDER, AXIS_SHAPE, ALL_AXES,
    _layout_for_char, analyze_canvas_writing,
)
from ai.canvas.synthetic_stroke_generator import _consonant_paths, _syllable_layout

GUIDE = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
_PRACTICE_SENTENCES = ("시원한 선풍기", "천 리 길도 한 걸음부터 시작된다는 마음으로")
_PRACTICE_SYLLABLES = sorted(set("각간달밤상" + "".join("".join(s.split())
                                                     for s in _PRACTICE_SENTENCES)))


def _paths(char_parts):
    return [(jamo, path) for jamo, paths in char_parts for path in paths]


def _template(target):
    return _paths(_layout_for_char(target))


def _jamo(jamo):
    """낱자는 **프론트 가이드 모양**으로 쓴다(stroke_order_data.dart `_single`: 원형을 상자에 그대로).

    _layout_for_char의 낱자 배치는 잉크를 상자에 꽉 채워 늘려서 사용자가 보는 가이드와
    모양이 다르다(ㅏ의 가로획이 세로획만큼 길어진다). 채점은 가이드대로 쓴 글씨를 기준으로 본다.
    """
    from ai.canvas.stroke_standards import CHOSUNG
    from ai.canvas.synthetic_stroke_generator import _vowel_paths
    paths = _consonant_paths(jamo) if jamo in CHOSUNG else _vowel_paths(jamo)
    return [(jamo, [(0.2 + x * 0.6, 0.16 + y * 0.68) for x, y in p]) for p in paths]


def _dense(paths, per=8):
    """획을 촘촘한 점렬로 — 실제 펜 입력처럼 만든다(꺾임각은 점 밀도를 탄다)."""
    out = []
    for jamo, path in paths:
        pts = []
        for a, b in zip(path, path[1:]):
            for k in range(per):
                u = k / per
                pts.append((a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u))
        pts.append(path[-1])
        out.append((jamo, pts))
    return out


def _strokes(paths):
    return [{"stroke_id": f"s{i}", "points": [{"x": x, "y": y, "timestamp": i * 100 + k}
                                              for k, (x, y) in enumerate(path)]}
            for i, (_, path) in enumerate(paths)]


def _group(strokes, cid="c0"):
    xs = [p["x"] for s in strokes for p in s["points"]]
    ys = [p["y"] for s in strokes for p in s["points"]]
    return [{"char_id": cid, "strokes": strokes,
             "bounding_box": {"x": min(xs), "y": min(ys),
                              "width": max(xs) - min(xs), "height": max(ys) - min(ys)}}]


def _score(paths, target, guide=GUIDE):
    return analyze_canvas_writing(_group(_strokes(paths)), target, guide_box=guide)[0]


def _scores(r):
    return {k: v["score"] for k, v in r["axes"].items()}


def _scale_about_center(path, factor):
    cx = sum(x for x, _ in path) / len(path)
    cy = sum(y for _, y in path) / len(path)
    return [(cx + (x - cx) * factor, cy + (y - cy) * factor) for x, y in path]


def _rotate(paths, deg):
    pts = [pt for _, path in paths for pt in path]
    cx = (min(x for x, _ in pts) + max(x for x, _ in pts)) / 2.0
    cy = (min(y for _, y in pts) + max(y for _, y in pts)) / 2.0
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(j, [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca)
                 for x, y in p]) for j, p in paths]


def _shake(paths, seed, amount=0.01):
    """점마다 글자 크기의 ±amount만큼 흔든다 — 아주 정갈한 손글씨 수준의 떨림."""
    rng = random.Random(seed)
    return [(j, [(x + rng.uniform(-amount, amount), y + rng.uniform(-amount, amount))
                 for x, y in p]) for j, p in paths]


def _join(paths):
    out = list(paths[0])
    for p in paths[1:]:
        out += list(p[1:]) if p[0] == out[-1] else list(p)
    return out


def _round_corners(path, r):
    """꼭짓점을 2차 베지어로 둥글린다. r은 인접 변 길이 대비 비율."""
    if len(path) < 3 or r <= 0:
        return path
    out = [path[0]]
    for i in range(1, len(path) - 1):
        a, b, c = path[i - 1], path[i], path[i + 1]
        t = min(r, 0.49)
        pa = (b[0] + (a[0] - b[0]) * t, b[1] + (a[1] - b[1]) * t)
        pc = (b[0] + (c[0] - b[0]) * t, b[1] + (c[1] - b[1]) * t)
        out.append(pa)
        for u in (0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875):
            out.append(((1 - u) ** 2 * pa[0] + 2 * (1 - u) * u * b[0] + u * u * pc[0],
                        (1 - u) ** 2 * pa[1] + 2 * (1 - u) * u * b[1] + u * u * pc[1]))
        out.append(pc)
    out.append(path[-1])
    return out


def _sentence(text, cell=100.0, shifts=None, scales=None, drop=()):
    """글자 칸(cell×cell)에 표준 자형을 놓은 문장 → (char_groups, char_positions). drop의 글자는 빈 칸."""
    groups, positions = [], []
    for i, ch in enumerate(text):
        positions.append({"char": ch, "index": i, "x": i * cell, "y": 0.0,
                          "width": cell, "height": cell})
        if i in drop:
            groups.append({"char_id": f"char_{i}", "strokes": [],
                           "bounding_box": {"x": i * cell, "y": 0.0, "width": cell, "height": cell}})
            continue
        dx = (shifts or {}).get(i, 0.0)
        k = (scales or {}).get(i, 1.0)
        paths = [(j, [((0.5 + (x - 0.5) * k) * cell + i * cell + dx,
                       (0.5 + (y - 0.5) * k) * cell) for x, y in p])
                 for j, p in _dense(_template(ch))]
        strokes = _strokes(paths)
        for s in strokes:
            s["stroke_id"] = f"c{i}_{s['stroke_id']}"
        groups.append(_group(strokes, f"char_{i}")[0])
    return groups, positions


# ── 단계별로 측정되는 축 ────────────────────────────────────────────────────

def test_jamo_measures_order_and_shape_only():
    r = _score(_dense(_jamo("ㄱ")), "ㄱ")
    s = _scores(r)
    assert set(r["axes"]) == set(ALL_AXES)
    assert s[AXIS_ORDER] == 100 and s[AXIS_SHAPE] == 100
    assert s[AXIS_BALANCE] is None and s[AXIS_LAYOUT] is None
    assert r["overall_score"] == 100 and r["component_boxes"] is None


def test_syllable_adds_balance_but_not_layout():
    s = _scores(_score(_dense(_template("각")), "각"))
    assert s[AXIS_ORDER] == 100 and s[AXIS_SHAPE] == 100 and s[AXIS_BALANCE] == 100
    assert s[AXIS_LAYOUT] is None            # 한 글자에는 배치 축이 없다(guide_box가 있어도)


def test_sentence_adds_layout():
    groups, positions = _sentence("각간달")
    for r in analyze_canvas_writing(groups, "각간달", char_positions=positions):
        assert _scores(r)[AXIS_LAYOUT] == 100, (r["char_id"], r["axes"][AXIS_LAYOUT])
        assert r["overall_score"] == 100


def test_item_scores_key_is_gone():
    assert "item_scores" not in _score(_dense(_template("각")), "각")


# ── 표준대로 쓰면 만점, 사유 없음 ─────────────────────────────────────────────

def test_template_exact_practice_characters_score_full_marks():
    jamo_set = "ㄱㄴㄷㄹㅁㅏㅑㅓㅕㅗ"                     # 자음·모음 탭의 연습 글자
    for ch in _PRACTICE_SYLLABLES + list("느그드르스뜨") + list(jamo_set):
        paths = _jamo(ch) if ch in jamo_set else _template(ch)
        r = _score(_dense(paths), ch)
        assert r["scorable"], (ch, r["unscorable_reason"])
        assert r["failed_items"] == [], (ch, r["failed_items"])
        assert r["overall_score"] == 100, ch


def test_line_vowel_syllables_survive_hand_tremor():
    """받침 없는 ㅣ·ㅡ 글자는 손떨림만으로 짜임새가 걸리면 안 된다(2026-09-30 오탐)."""
    for ch in "시기이으리미그느":
        for seed in range(10):
            r = _score(_shake(_dense(_template(ch)), seed), ch)
            assert r["axes"][AXIS_BALANCE]["reasons"] == [], (ch, seed, r["failed_items"])


# ── 축 점수 100/70/40 ─────────────────────────────────────────────────────

def test_one_swap_costs_partial_on_order_axis_only():
    paths = _template("각")
    paths[0], paths[1] = paths[1], paths[0]
    r = _score(paths, "각")
    s = _scores(r)
    assert s[AXIS_ORDER] == 70 and r["axes"][AXIS_ORDER]["reasons"] == ["1획 순서 틀림"]
    assert s[AXIS_SHAPE] == 100 and s[AXIS_BALANCE] == 100
    assert r["overall_score"] == 90
    assert r["failed_items"] == [f"{AXIS_ORDER}(1획 순서 틀림)"]


def test_reversed_stroke_hits_order_axis_only():
    paths = _template("각")
    jamo, path = paths[0]
    paths[0] = (jamo, list(reversed(path)))
    r = _score(paths, "각")
    assert r["axes"][AXIS_ORDER]["reasons"] == ["1획 반대로 그음"]
    assert _scores(r)[AXIS_SHAPE] == 100 and _scores(r)[AXIS_BALANCE] == 100


def test_two_bad_components_make_balance_severe():
    factors = [2.0, 1.0, 1.0, 0.5]
    paths = [(j, _scale_about_center(p, f)) for (j, p), f in zip(_template("각"), factors)]
    r = _score(paths, "각")
    assert _scores(r)[AXIS_BALANCE] == 40
    assert len(r["axes"][AXIS_BALANCE]["reasons"]) == 2
    assert _scores(r)[AXIS_ORDER] == 100


def test_merged_consonant_is_order_axis_only():
    """획을 이어 쓴 것은 획순 축의 '획 수' 1건이다 — 모양 축에 엉뚱한 사유가 붙으면 안 된다."""
    for jamo in ("ㄷ", "ㄹ", "ㅁ"):
        r = _score(_dense([(jamo, _join(_consonant_paths(jamo)))]), jamo)
        assert r["scorable"] is True, jamo
        assert _scores(r)[AXIS_ORDER] == 70, (jamo, r["axes"][AXIS_ORDER])
        assert r["axes"][AXIS_ORDER]["reasons"] == [f"획 수 1개 / 표준 {len(_consonant_paths(jamo))}개"]
        assert r["axes"][AXIS_SHAPE]["reasons"] == [], (jamo, r["axes"][AXIS_SHAPE])


def test_merging_the_last_strokes_still_counts():
    """마지막 두 획을 합치면 순서 어긋남은 0건이지만 획 수로 잡혀야 한다."""
    layout = _syllable_layout("ㅂ", "ㅏ", "ㅁ")
    paths = []
    for i, (jamo, ps) in enumerate(layout):
        if i == len(layout) - 1:
            ps = [ps[0], ps[1] + ps[2][::-1][1:]]
        paths += [(jamo, p) for p in ps]
    r = _score(_dense(paths), "밤")
    assert r["axes"][AXIS_ORDER]["reasons"] == ["획 수 8개 / 표준 9개"]
    boxes = {b["role"]: b for b in r["component_boxes"]}
    assert boxes["종성"]["ok"] is False and boxes["초성"]["ok"] and boxes["중성"]["ok"]


def test_merged_stroke_in_one_component_does_not_redden_the_others():
    """'닥'의 ㄷ을 한 획에 쓰면 초성만 빨강이어야 한다 — 밀린 짝 때문에 중성·종성이 '순서 틀림'이 되면 안 된다."""
    layout = _syllable_layout("ㄷ", "ㅏ", "ㄱ")
    paths = []
    for i, (jamo, ps) in enumerate(layout):
        ps = [_join(ps)] if i == 0 else ps
        paths += [(jamo, p) for p in ps]
    r = _score(_dense(paths), "닥")
    boxes = {b["role"]: b for b in r["component_boxes"]}
    assert boxes["초성"]["failed_items"] == [f"{AXIS_ORDER}(획 수 1개 / 표준 2개)"]
    assert boxes["중성"]["ok"] is True and boxes["종성"]["ok"] is True, boxes
    assert r["axes"][AXIS_ORDER]["reasons"] == ["획 수 4개 / 표준 5개"]


# ── 모양 축 ───────────────────────────────────────────────────────────────

def test_rotated_jamo_is_caught_on_shape_axis():
    for jamo in ("ㄱ", "ㄴ", "ㅁ"):
        r = _score(_dense(_rotate(_jamo(jamo), 25)), jamo)
        assert _scores(r)[AXIS_SHAPE] < 100, (jamo, r["axes"][AXIS_SHAPE])
        assert any("기울어짐" in x for x in r["axes"][AXIS_SHAPE]["reasons"]), jamo


def test_tilted_jamo_costs_partial_only():
    """기울여 쓴 낱자는 모양 축 70이다 — 획 기울기·글자 기울기·모양 거리가 따로 세어져 40이 되면 안 된다."""
    for jamo in ("ㅣ", "ㄱ", "ㄹ", "ㅌ", "ㅁ"):
        r = _score(_dense(_rotate(_jamo(jamo), 20)), jamo)
        assert r["scorable"] is True, (jamo, r["unscorable_reason"])
        assert _scores(r)[AXIS_SHAPE] == 70, (jamo, r["axes"][AXIS_SHAPE])
        assert _scores(r)[AXIS_ORDER] == 100, (jamo, r["axes"][AXIS_ORDER])


def test_slightly_tilted_single_stroke_jamo_is_not_called_misshapen():
    """ㄱ을 10° 기울인 것은 허용 안(15°)이다 — 모양 거리로 돌아 들어와 잡히면 안 된다."""
    r = _score(_dense(_rotate(_jamo("ㄱ"), 10)), "ㄱ")
    assert r["axes"][AXIS_SHAPE]["reasons"] == [], r["axes"][AXIS_SHAPE]


def test_right_angled_giyeok_is_not_called_rotated():
    r = _score(_dense([("ㄱ", [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8)])]), "ㄱ")
    assert r["axes"][AXIS_SHAPE]["reasons"] == [], r["axes"][AXIS_SHAPE]


def test_tilted_straight_stroke_is_caught_in_a_narrow_character():
    paths = _dense(_template("리"))
    jamo, stroke = paths[-1]
    x0, y0 = stroke[0]
    lean = math.tan(math.radians(25))
    paths[-1] = (jamo, [(x0 + (y - y0) * lean, y) for _, y in stroke])
    r = _score(paths, "리")
    assert any("기울어짐" in x for x in r["axes"][AXIS_SHAPE]["reasons"]), r["axes"][AXIS_SHAPE]


def test_rounded_corners_are_caught_and_angular_pass():
    parts = _dense([(j, _round_corners(p, 0.35)) for j, p in _template("달")])
    r = _score(parts, "달")
    assert any("모서리" in x for x in r["axes"][AXIS_SHAPE]["reasons"]), r["axes"][AXIS_SHAPE]
    assert r["axes"][AXIS_ORDER]["reasons"] == []
    for ch in ("달", "문", "느"):
        assert _score(_dense(_template(ch)), ch)["axes"][AXIS_SHAPE]["reasons"] == [], ch


def test_reversed_stroke_is_not_also_called_rounded():
    paths = _dense(_jamo("ㄹ"))
    jamo, stroke = paths[0]
    paths[0] = (jamo, stroke[::-1])
    r = _score(paths, "ㄹ")
    assert r["axes"][AXIS_ORDER]["reasons"] == ["1획 반대로 그음"]
    assert r["axes"][AXIS_SHAPE]["reasons"] == []


def test_squashed_jamo_fails_shape():
    """세로로 납작하게 쓴 ㅁ(높이 45%)은 거부가 아니라 **모양 축**에서 잡힌다.

    더 심하면(높이 1/3) 딴 글자로 거부된다 — 모양 축은 그 사이의 "눈에 띄는 변형"을 본다.
    """
    squashed = [(j, [(x, 0.5 + (y - 0.5) * 0.45) for x, y in p]) for j, p in _jamo("ㅁ")]
    r = _score(_dense(squashed), "ㅁ")
    assert r["scorable"] is True, r["unscorable_reason"]
    assert r["axes"][AXIS_SHAPE]["reasons"] == ["표준 모양과 많이 다름"], r["axes"][AXIS_SHAPE]
    assert _scores(r)[AXIS_SHAPE] == 70


def test_shape_axis_is_measured_for_curvy_jamo_and_syllables():
    """ㅅ·ㅇ 낱자도 '표준과 다른 모양' 판정이 있어 측정된다. 음절 '소'는 곧은 획이 있어 측정된다."""
    assert _scores(_score(_dense(_jamo("ㅅ")), "ㅅ"))[AXIS_SHAPE] == 100
    assert _scores(_score(_dense(_template("소")), "소"))[AXIS_SHAPE] == 100


# ── 채점 거부 ───────────────────────────────────────────────────────────────

def test_refused_jamo_has_no_score():
    r = _score([("?", [(0.2, 0.5), (0.8, 0.5)])], "ㄱ")
    assert r["scorable"] is False and r["unscorable_reason"] == "shape_mismatch"
    assert r["overall_score"] is None
    assert all(a["score"] is None for a in r["axes"].values())
    assert r["failed_items"] == ["다시 써 주세요(목표 글자와 다름)"]
    assert "unscorable" in r["correction_flags"] and "unscorable:shape_mismatch" in r["correction_flags"]
    assert any(f.startswith("ink_gap:") for f in r["correction_flags"])      # 거리값은 기록용으로 남긴다


def test_refused_character_in_a_sentence_scores_zero_and_others_continue():
    groups, positions = _sentence("각간달")
    groups[1]["strokes"] = _strokes([("?", [(110.0, 50.0), (190.0, 50.0)])])
    results = analyze_canvas_writing(groups, "각간달", char_positions=positions)
    assert results[1]["scorable"] is False
    assert results[1]["overall_score"] == 0
    box = results[1]["component_boxes"][0]
    assert box["role"] == "글자" and box["jamo"] == "간" and box["ok"] is False
    assert box["failed_items"] == ["다시 써 주세요(목표 글자와 다름)"]
    assert results[0]["overall_score"] == 100 and results[2]["overall_score"] == 100


def test_skipped_cell_in_a_sentence_is_missing_and_zero():
    groups, positions = _sentence("각간달", drop=(1,))
    r = analyze_canvas_writing(groups, "각간달", char_positions=positions)[1]
    assert r["unscorable_reason"] == "missing" and r["overall_score"] == 0
    assert r["failed_items"] == ["다시 써 주세요(쓰지 않음)"]


def test_all_characters_refused_sentence_is_zero_not_none():
    groups, positions = _sentence("각간", drop=(0, 1))
    results = analyze_canvas_writing(groups, "각간", char_positions=positions)
    assert [r["overall_score"] for r in results] == [0, 0]


# ── 문장: 글자 박스와 배치 축 ───────────────────────────────────────────────

def test_sentence_boxes_are_one_per_character():
    groups, positions = _sentence("각간달", shifts={2: -40.0})
    results = analyze_canvas_writing(groups, "각간달", char_positions=positions)
    for r, ch in zip(results, "각간달"):
        assert len(r["component_boxes"]) == 1
        box = r["component_boxes"][0]
        assert box["role"] == "글자" and box["jamo"] == ch
        assert box["failed_items"] == r["failed_items"]
    assert results[2]["component_boxes"][0]["ok"] is False
    assert f"{AXIS_LAYOUT}(앞 글자와 너무 좁음)" in results[2]["failed_items"]


def test_spacing_against_the_guide_catches_gaps():
    groups, positions = _sentence("각간달", shifts={0: -45.0, 1: 45.0})
    r = analyze_canvas_writing(groups, "각간달", char_positions=positions)[1]
    assert "앞 글자와 너무 넓음" in r["axes"][AXIS_LAYOUT]["reasons"]


def test_positions_are_ignored_when_their_count_does_not_match():
    groups, positions = _sentence("각간달")
    for r in analyze_canvas_writing(groups, "각간달", char_positions=positions[:2]):
        assert r["position_result"] is None
        assert "글자 칸에서 벗어남" not in r["axes"][AXIS_LAYOUT]["reasons"]


def test_flat_syllable_is_not_called_small_but_a_small_one_is():
    groups, positions = _sentence("한으로")
    r = analyze_canvas_writing(groups, "한으로", char_positions=positions)[1]
    assert "크기 너무 작음" not in r["axes"][AXIS_LAYOUT]["reasons"]
    groups, positions = _sentence("한각로", scales={1: 0.45})
    r = analyze_canvas_writing(groups, "한각로", char_positions=positions)[1]
    assert "크기 너무 작음" in r["axes"][AXIS_LAYOUT]["reasons"]
    assert r["component_boxes"][0]["ok"] is False


def test_non_hangul_target_in_a_sentence_measures_layout_only():
    groups, positions = _sentence("각간달")
    results = analyze_canvas_writing(groups, "각A달", char_positions=positions)
    s = _scores(results[1])
    assert s[AXIS_ORDER] is None and s[AXIS_SHAPE] is None and s[AXIS_BALANCE] is None
    assert s[AXIS_LAYOUT] == 100
    assert results[1]["overall_score"] == 100


# ── 성분 박스(한 글자) 사유는 축 라벨 ────────────────────────────────────────

def test_component_box_reasons_use_axis_names():
    paths = _template("각")
    jamo, path = paths[3]
    paths[3] = (jamo, _scale_about_center(path, 2.0))
    r = _score(paths, "각")
    boxes = {b["role"]: b for b in r["component_boxes"]}
    assert boxes["종성"]["ok"] is False
    assert boxes["종성"]["failed_items"] == [f"{AXIS_BALANCE}(너무 큼)"]
    assert boxes["초성"]["ok"] and boxes["중성"]["ok"]
