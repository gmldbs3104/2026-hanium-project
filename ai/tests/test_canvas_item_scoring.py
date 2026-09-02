"""새 캔버스 채점 체계 — 항목별 독립성과 연습 종류별 채점 범위를 고정한다.

이 테스트의 핵심은 **한 가지를 틀리면 그 항목만 깎이는가**이다. 항목이 서로를
오염시키면 사용자는 "왜 감점됐는지"를 알 수 없고, 우리도 어느 로직이 틀렸는지
분리해서 고칠 수 없다.

참고로 이것이 참고한 방식(AI-WritingCorrection)과 갈리는 지점이다. 그쪽은 획 개수로
순서대로 잘라 자모를 나누므로 **획순이 틀리면 자모 분해가 통째로 무너져** 성분 비율
점수가 의미를 잃는다. 우리는 기하 매칭이라 순서가 틀려도 각 획이 어느 자모 자리에
있는지는 그대로 알아낸다 — test_wrong_order_does_not_touch_balance가 그걸 고정한다.
"""
from ai.canvas.canvas_quality_analyzer import (
    ITEM_BALANCE, ITEM_DIRECTION, ITEM_ORDER, ITEM_SIZE, ITEM_SPACING, ITEM_TILT,
    analyze_canvas_writing,
)
from ai.canvas.synthetic_stroke_generator import _single_jamo_layout, _syllable_layout

# 획 좌표가 [0,1] 정규화 공간이므로 가이드 상자도 같은 공간의 전체 넓이로 둔다.
GUIDE = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}


def _paths(char_parts):
    return [(jamo, path) for jamo, paths in char_parts for path in paths]


def _strokes(paths):
    out = []
    for i, (_, path) in enumerate(paths):
        out.append({
            "stroke_id": f"s{i}",
            "points": [{"x": x, "y": y, "timestamp": i * 100 + k}
                       for k, (x, y) in enumerate(path)],
        })
    return out


def _group(strokes):
    xs = [p["x"] for s in strokes for p in s["points"]]
    ys = [p["y"] for s in strokes for p in s["points"]]
    return [{"char_id": "c0", "strokes": strokes,
             "bounding_box": {"x": min(xs), "y": min(ys),
                              "width": max(xs) - min(xs), "height": max(ys) - min(ys)}}]


def _score(paths, target, guide=GUIDE):
    strokes = _strokes(paths)
    return analyze_canvas_writing(_group(strokes), target, guide_box=guide)[0]


def _standard_gak():
    return _paths(_syllable_layout("ㄱ", "ㅏ", "ㄱ"))


def _scale_about_center(path, factor):
    cx = sum(x for x, _ in path) / len(path)
    cy = sum(y for _, y in path) / len(path)
    return [(cx + (x - cx) * factor, cy + (y - cy) * factor) for x, y in path]


# ── 기준점: 표준대로 쓰면 전 항목 만점 ────────────────────────────────────

def test_standard_writing_scores_full_marks():
    r = _score(_standard_gak(), "각")
    items = r["item_scores"]
    assert items[ITEM_ORDER] == 100.0
    assert items[ITEM_DIRECTION] == 100.0
    assert items[ITEM_TILT] == 100.0
    assert items[ITEM_BALANCE] == 100.0
    # 크기는 문장에서만 잰다(2026-09-01) — 한 글자면 미측정이다.
    assert items[ITEM_SIZE] is None
    assert r["overall_score"] == 100


# ── 항목 독립성: 하나를 틀리면 그 항목만 깎인다 ──────────────────────────

def test_wrong_order_does_not_touch_balance():
    """획순만 뒤바꾼다. 자모별 잉크는 그대로이므로 성분 비율은 만점이어야 한다."""
    paths = _standard_gak()
    paths[0], paths[1] = paths[1], paths[0]
    items = _score(paths, "각")["item_scores"]
    assert items[ITEM_ORDER] < 100.0
    assert items[ITEM_BALANCE] == 100.0


def test_reversed_stroke_hits_direction_only():
    """첫 획을 반대로 긋는다. 지나간 자리는 같으므로 나머지는 만점이어야 한다."""
    paths = _standard_gak()
    jamo, path = paths[0]
    paths[0] = (jamo, list(reversed(path)))
    items = _score(paths, "각")["item_scores"]
    assert items[ITEM_DIRECTION] < 100.0
    assert items[ITEM_ORDER] == 100.0
    assert items[ITEM_BALANCE] == 100.0


def test_oversized_jongseong_hits_balance_only():
    """받침만 키운다 — 획순·방향은 그대로여야 한다."""
    paths = _standard_gak()
    jamo, path = paths[3]                     # 종성 ㄱ
    paths[3] = (jamo, _scale_about_center(path, 2.0))
    r = _score(paths, "각")
    items = r["item_scores"]
    assert items[ITEM_BALANCE] < 90.0
    assert items[ITEM_ORDER] == 100.0
    assert items[ITEM_DIRECTION] == 100.0
    # 점수 숫자보다 중요한 것: **종성만** 빨강이고 나머지는 초록이어야 한다.
    by_role = {b["role"]: b for b in r["component_boxes"]}
    assert by_role["종성"]["ok"] is False
    assert by_role["초성"]["ok"] is True and by_role["중성"]["ok"] is True


def test_whole_character_too_small_hits_size_only():
    """글자 전체를 줄여도 성분 **비율**은 그대로여야 한다 — 그게 비율의 뜻이다.

    크기 자체는 문장에서만 재므로(2026-09-01) 여기서는 두 글자로 만들어 확인한다.
    """
    small = [(j, [(0.5 + (x - 0.5) * 0.45, 0.5 + (y - 0.5) * 0.45) for x, y in p])
             for j, p in _standard_gak()]
    right = [(j, [(x + 1.2, y) for x, y in p]) for j, p in _standard_gak()]
    sl, sr = _strokes(small), _strokes(right)
    for st in sr:
        st["stroke_id"] += "_r"
    groups = _group(sl) + _group(sr)
    groups[1]["char_id"] = "c1"
    results = analyze_canvas_writing(groups, "각각", guide_box=GUIDE)
    items = results[0]["item_scores"]
    assert items[ITEM_SIZE] < 50.0          # 작게 쓴 첫 글자만 크기 감점
    assert items[ITEM_BALANCE] == 100.0     # 비율은 크기와 무관
    assert items[ITEM_ORDER] == 100.0


# ── 연습 종류별 채점 범위 (사용자 결정 2026-09-01) ────────────────────────

def test_solo_jamo_scores_order_and_direction_only():
    """자음·모음은 획순·획방향(+기울기)만. 성분비율·자간·크기는 성립하지 않는다.

    크기를 뺀 것은 2026-09-01 사용자 결정 — 글자 하나의 절대 크기는 임의값이다.
    """
    items = _score(_paths(_single_jamo_layout("ㄱ", is_vowel=False)), "ㄱ")["item_scores"]
    assert items[ITEM_ORDER] == 100.0
    assert items[ITEM_DIRECTION] == 100.0
    assert items[ITEM_BALANCE] is None
    assert items[ITEM_SPACING] is None
    assert items[ITEM_SIZE] is None


def test_single_syllable_has_no_spacing():
    """한 글자만 쓰면 비교할 옆 글자가 없다 — 자간은 만점이 아니라 미측정이다."""
    items = _score(_standard_gak(), "각")["item_scores"]
    assert items[ITEM_SPACING] is None


def test_two_characters_gain_spacing():
    left = _standard_gak()
    right = [(j, [(x + 1.2, y) for x, y in p]) for j, p in _standard_gak()]
    strokes_l, strokes_r = _strokes(left), _strokes(right)
    for s in strokes_r:
        s["stroke_id"] += "_r"
    groups = _group(strokes_l) + _group(strokes_r)
    groups[1]["char_id"] = "c1"
    results = analyze_canvas_writing(groups, "각각", guide_box=GUIDE)
    assert results[0]["item_scores"][ITEM_SPACING] is None      # 첫 글자는 왼쪽이 없다
    assert results[1]["item_scores"][ITEM_SPACING] is not None


# ── 미측정은 0점이 아니라 분모에서 빠진다 ────────────────────────────────

def test_unmeasured_items_are_excluded_from_overall():
    """낱자는 3항목만 재는데도 표준대로 썼으면 100점이어야 한다.

    미측정을 0점으로 세면 낱자는 아무리 잘 써도 만점을 받을 수 없다.
    """
    r = _score(_paths(_single_jamo_layout("ㄹ", is_vowel=False)), "ㄹ")
    assert r["item_scores"][ITEM_BALANCE] is None
    assert r["overall_score"] == 100


def test_single_character_never_scores_size():
    """한 글자 연습은 가이드가 있든 없든 크기를 재지 않는다(2026-09-01 결정)."""
    assert _score(_standard_gak(), "각")["item_scores"][ITEM_SIZE] is None
    assert _score(_standard_gak(), "각", guide=None)["item_scores"][ITEM_SIZE] is None


# ── 필압 제거 (사용자 결정 2026-09-01) ───────────────────────────────────

def test_pressure_is_gone_speed_remains():
    """필압은 채점·응답에서 완전히 제거하고, 속도는 기록만 유지한다."""
    r = _score(_standard_gak(), "각")
    assert "pressure_profile" not in r
    assert "mean_speed_px_per_ms" in r["speed_profile"]


# ── 성분 단위 박스와 2색 판정 (사용자 결정 2026-09-01) ────────────────────

def test_syllable_gets_one_box_per_component():
    """'각'은 초성·중성·종성 3개 박스. 박스 단위 = 채점 단위여야 한다."""
    boxes = _score(_standard_gak(), "각")["component_boxes"]
    assert boxes is not None
    assert [b["role"] for b in boxes] == ["초성", "중성", "종성"]
    assert all(b["box"]["width"] > 0 and b["box"]["height"] > 0 for b in boxes)


def test_solo_jamo_has_no_component_boxes():
    """낱자는 박스를 만들지 않는다 — 성분이 하나라 캔버스 테두리를 다시 그리는 셈이다."""
    r = _score(_paths(_single_jamo_layout("ㄱ", is_vowel=False)), "ㄱ")
    assert r["component_boxes"] is None


def test_standard_writing_makes_every_box_green():
    boxes = _score(_standard_gak(), "각")["component_boxes"]
    assert all(b["ok"] for b in boxes)
    assert all(b["failed_items"] == [] for b in boxes)


def test_one_failed_item_turns_only_that_component_red():
    """받침만 키우면 **종성 박스만** 빨강이어야 한다. 나머지는 초록 유지."""
    paths = _standard_gak()
    jamo, path = paths[3]
    paths[3] = (jamo, _scale_about_center(path, 2.0))
    boxes = _score(paths, "각")["component_boxes"]
    by_role = {b["role"]: b for b in boxes}
    assert by_role["종성"]["ok"] is False
    # 사유가 "성분비율(너무 큼)"처럼 붙으므로 부분일치로 본다.
    assert any(ITEM_BALANCE in f for f in by_role["종성"]["failed_items"])
    assert by_role["초성"]["ok"] is True
    assert by_role["중성"]["ok"] is True


def test_red_is_or_of_items_not_average():
    """획순 하나만 틀려도 그 성분은 빨강 — 종합 점수가 높아도 마찬가지다.

    가중 평균으로 색을 정하면 획순을 통째로 틀려도 다른 항목이 끌어올려 초록이
    나온다(2026-09-01 실측: 낱자 획순 0점인데 종합 62점). 그래서 OR로 합친다.
    """
    paths = _standard_gak()
    paths[0], paths[1] = paths[1], paths[0]      # 초성 안에서 순서만 뒤바꿈
    r = _score(paths, "각")
    boxes = {b["role"]: b for b in r["component_boxes"]}
    assert boxes["초성"]["ok"] is False
    assert any(ITEM_ORDER in f for f in boxes["초성"]["failed_items"])
    assert r["overall_score"] > 80          # 종합은 높은데도


# ── 허용치: 정상 필기는 통과하고, 눈에 띄는 오류만 잡힌다 ────────────────────
#
# 2026-09-01에 사용자가 **두 번** 같은 문제를 신고했다 — "그림자대로 따라 썼는데도
# 계속 빨간 박스가 뜬다." 원인은 버그가 아니라 허용치였다. 면적은 2차원이라
# ±30%가 한 변으로는 ±14%밖에 안 되는데 손글씨는 늘 그만큼 흔들리고, 세 축을
# OR로 묶으니 축마다의 빠듯함이 곱해져 실질 통과율이 훨씬 낮아졌다.
#
# 허용치는 눈금 없는 숫자라 언제든 다시 좁아질 수 있다. 그래서 **양쪽 끝**을 함께
# 고정한다 — 너무 좁히면 아래 test_normal_handwriting_passes가, 너무 넓히면
# test_clearly_wrong_size_still_caught가 깨진다.

def _jitter(paths, seed, jitter, offset, scale):
    """사람이 그림자를 따라 쓸 때 생기는 정도의 흔들림.

    자모마다 배율이 조금씩 다르고(사람은 획마다 크기를 못 맞춘다), 획마다 시작점이
    밀리고, 점마다 손이 떨린다 — 세 가지를 겹친다.
    """
    import random
    rng = random.Random(seed)

    # ⚠️ 자모 **문자열**로 묶으면 안 된다 — '각'은 초성과 종성이 둘 다 'ㄱ'이라
    # 한 덩어리가 되고, 둘의 중점을 기준으로 확대돼 실제로는 자리를 크게 옮긴다.
    # 연속한 같은 자모끼리만 묶어 **자리(초·중·종성)** 단위로 나눈다.
    blocks: list = []
    for jamo, path in paths:
        if blocks and blocks[-1][0] == jamo:
            blocks[-1][1].append(path)
        else:
            blocks.append((jamo, [path]))

    out = []
    for jamo, plist in blocks:
        pts = [p for path in plist for p in path]
        cx = sum(x for x, _ in pts) / len(pts)
        cy = sum(y for _, y in pts) / len(pts)
        sx = 1.0 + rng.uniform(-scale, scale)
        sy = 1.0 + rng.uniform(-scale, scale)
        for path in plist:
            ox, oy = rng.uniform(-offset, offset), rng.uniform(-offset, offset)
            out.append((jamo, [(cx + (x - cx) * sx + ox + rng.uniform(-jitter, jitter),
                                cy + (y - cy) * sy + oy + rng.uniform(-jitter, jitter))
                               for x, y in path]))
    return out


def test_normal_handwriting_passes():
    """정갈하게 따라 쓴 글씨는 성분이 전부 초록이어야 한다.

    이게 깨지면 사용자는 "잘 썼는데 왜 빨갛냐"를 다시 겪는다. 여러 seed로 도는 이유는
    한 번 우연히 통과하는 것으로는 허용치를 지킬 수 없기 때문이다.
    """
    for seed in range(12):
        paths = _jitter(_standard_gak(), seed, jitter=0.008, offset=0.010, scale=0.08)
        boxes = _score(paths, "각")["component_boxes"]
        bad = [(b["role"], b["failed_items"]) for b in boxes if not b["ok"]]
        assert not bad, f"정상 필기(seed={seed})인데 빨강이 떴다: {bad}"


def test_clearly_wrong_size_still_caught():
    """반대편 끝 — 허용치를 넓히다가 '아무거나 통과'가 되면 안 된다."""
    for factor, direction in ((0.5, "너무 작음"), (1.6, "너무 큼")):
        paths = _standard_gak()
        jamo, path = paths[3]
        paths[3] = (jamo, _scale_about_center(path, factor))
        boxes = {b["role"]: b for b in _score(paths, "각")["component_boxes"]}
        assert boxes["종성"]["ok"] is False, f"받침 ×{factor}인데 통과했다"
        assert any(direction in f for f in boxes["종성"]["failed_items"]), \
            f"받침 ×{factor}의 사유가 '{direction}'이 아니다: {boxes['종성']['failed_items']}"
        # 한 성분이 틀렸다고 멀쩡한 성분까지 빨개지면 안 된다
        assert boxes["초성"]["ok"] and boxes["중성"]["ok"]
