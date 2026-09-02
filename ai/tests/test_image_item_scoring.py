"""이미지 모드 채점 5항목과 **글자 단위 초록/빨강 판정**을 고정한다.

2026-09-01 개편(사용자 결정)
--------------------------
· 문구는 항상 6문장 — 종합 1 + 항목 5(크기 균일성·기울기 균일성·줄 정렬·자간·행간).
  종전에는 60점 미만이면 지적, 85점 이상이면 칭찬이라 **60~84점 구간은 아무 문구도
  안 나갔고**, 자간·행간은 점수만 재고 문구가 아예 없었다.
· 박스는 기본 초록, **크기·기울기·줄 정렬 중 하나라도 미흡한 글자만** 빨강.
  자간·행간은 글자 하나에 귀속되지 않아 색에 반영하지 않는다.
· 기준은 **다른 글자들의 평균**이다. 글씨체가 원래 비스듬해도 고르게 쓰면 통과한다.
"""
import pytest

from ai.analysis.handwriting_analyzer import analyze_size_angle

ROWS, COLS = 4, 6


def _chars(bad=None, tilt_all=0.0, drift=0.0, gaps=None):
    """반듯한 4행 × 6열 글자판을 만들고, 지정한 글자만 흐트러뜨린다.

    drift  — 열이 늘어날수록 아래로 내려간다(글줄이 기울어 쓰인 경우).
    gaps   — 열별 x 간격 목록(자간을 들쭉날쭉하게 만들 때).
    """
    bad = bad or {}
    out, i = [], 0
    for r in range(ROWS):
        x = 60.0
        for c in range(COLS):
            h, y, a = 40.0, 100.0 + r * 80 + drift * c, tilt_all
            kind = bad.get(i)
            if kind == "big":
                h = 70.0
            elif kind == "small":
                h = 22.0
            elif kind == "low":
                y += 20.0
            elif kind == "tilt":
                a = tilt_all + 16.0
            out.append({"char_id": f"char_{i}",
                        "bounding_box": {"x": x, "y": y, "width": 40.0, "height": h},
                        "angle": a, "angle_reliable": True, "confidence": 0.9})
            x += gaps[c % len(gaps)] if gaps else 60.0
            i += 1
    return out


def _scores(result):
    return {k: (m.get("score") and round(m["score"]))
            for k, m in result["metrics"].items()}


def _red(result):
    return {c["char_id"]: c["failed_items"] for c in result["chars"] if not c["ok"]}


# ── 기준점 ────────────────────────────────────────────────────────────────

def test_tidy_writing_is_all_green():
    r = analyze_size_angle(_chars())
    assert _red(r) == {}, "반듯하게 쓴 글에 빨간 박스가 생기면 안 된다"
    assert all(s == 100 for s in _scores(r).values())


def test_five_items_are_always_measured_when_enough_chars():
    """항목이 하나라도 빠지면 화면에 6문장이 안 나간다."""
    r = analyze_size_angle(_chars())
    assert set(r["metrics"]) == {
        "height_uniformity", "tilt_consistency", "baseline_deviation",
        "spacing_uniformity", "line_spacing_uniformity"}


# ── 글자 단위 판정: 평균에서 벗어난 글자만 빨강 ───────────────────────────

@pytest.mark.parametrize("kind, expect", [
    ("big",   "크기(너무 큼)"),
    ("small", "크기(너무 작음)"),
    ("tilt",  "기울기(오른쪽으로 기욺)"),
    ("low",   "줄 정렬(아래로 벗어남)"),
])
def test_only_the_odd_char_turns_red(kind, expect):
    r = analyze_size_angle(_chars(bad={7: kind}))
    red = _red(r)
    assert "char_7" in red, f"{kind}로 흐트러뜨린 글자가 빨강이 아니다"
    assert expect in red["char_7"]
    # 멀쩡한 글자까지 물들면 "어디를 고쳐야 하나"를 알 수 없게 된다
    assert set(red) == {"char_7"}, f"엉뚱한 글자까지 빨개졌다: {sorted(red)}"


def test_uniformly_slanted_handwriting_passes():
    """글씨체가 원래 비스듬해도 **고르면** 통과다 — 항목이 '균일성'이기 때문.

    종전에는 수직(0°)에서 7°만 넘으면 무조건 기울었다고 봐서, 비스듬한 글씨체는
    아무리 고르게 써도 전부 빨개졌다.
    """
    r = analyze_size_angle(_chars(tilt_all=12.0))
    assert _red(r) == {}
    assert _scores(r)["tilt_consistency"] == 100


def test_tilt_score_and_red_box_agree():
    """박스는 빨간데 점수는 100점 같은 모순이 없어야 한다.

    실제로 그런 적이 있다 — 명료도가 크게 기운 글자를 'tilt_outlier'로 찍어
    통계에서 빼는데, **그 플래그가 각도로 정해져서** 기울기 지표가 정작 기운 글자를
    영영 못 보는 순환이었다(2026-09-01: 한 글자만 16° 기울였더니 σ=0, 점수 100).
    """
    r = analyze_size_angle(_chars(bad={3: "tilt"}))
    assert "char_3" in _red(r)
    assert _scores(r)["tilt_consistency"] < 80, "기울어진 글자가 있는데 점수는 칭찬 구간이다"


# ── 줄 정렬: 수평인가 + 줄에 앉았나, 둘 다 본다 ───────────────────────────

def test_sloping_line_is_caught_even_when_chars_sit_on_it():
    """비스듬히 **반듯하게** 쓴 글도 줄 정렬에서 걸려야 한다.

    회귀선이 기울기를 통째로 흡수하므로 잔차만 보면 만점이 나온다(2026-09-01 실측:
    5.7° 내려가는 글이 줄 정렬 100점). 그래서 수평 이탈과 잔차 중 나쁜 쪽을 쓴다.
    """
    r = analyze_size_angle(_chars(drift=6.0))
    assert r["overall_tilt"] == "falling", "줄이 내려가는데 방향이 안 잡힌다"
    assert _scores(r)["baseline_deviation"] < 80
    assert r["metrics"]["baseline_deviation"]["driver"] == "tilt"


def test_line_direction_is_reported_for_message():
    """문구가 '오른쪽/왼쪽'을 고르는 근거 — 방향이 안 오면 문구를 못 만든다."""
    assert analyze_size_angle(_chars(drift=-6.0))["overall_tilt"] == "rising"
    assert analyze_size_angle(_chars())["overall_tilt"] == "straight"


# ── 자간·행간은 문구로만 — 박스 색에 영향을 주지 않는다 ───────────────────

def test_uneven_spacing_warns_but_colors_no_box():
    # 간격이 행 높이 × 0.55(= 22px)를 넘으면 **띄어쓰기**로 보고 자간에서 빼므로,
    # 그 아래에서만 들쭉날쭉하게 만든다(안 그러면 흐트러뜨린 간격이 통째로 제외된다).
    r = analyze_size_angle(_chars(gaps=[41.0, 58.0, 44.0, 60.0, 43.0, 57.0]))
    assert _scores(r)["spacing_uniformity"] < 80, "자간이 들쭉날쭉한데 안 걸린다"
    assert _red(r) == {}, "자간은 글자 하나의 잘못이 아니므로 박스를 칠하면 안 된다"


# ── 기울기의 **절대** 기울어짐 — 고르기만 해서는 안 된다 ──────────────────
#
# 2026-09-02 사용자 지적: "평균 자체가 너무 기울어져 있으면 글자를 너무 기울여
# 쓴다는 평가도 있어야 한다." 균일성만 보면 **전부 똑같이 30° 기울여 쓴 글씨가
# 만점**으로 나간다 — 고르기는 고르니까. 박스는 치지 않고 문구로만 알린다.

def test_uniform_but_heavily_slanted_is_reported():
    from ai.analysis.handwriting_analyzer import CHAR_SLANT_NORM_DEG
    r = analyze_size_angle(_chars(tilt_all=25.0))
    # 고르게 썼으니 균일성 점수는 그대로 만점이어야 한다 — 두 축은 별개다.
    assert _scores(r)["tilt_consistency"] == 100
    # 그런데 기울기 중앙값 자체가 규범을 넘는다 → 문구로 지적할 근거가 나가야 한다.
    assert r["mean_char_slant"] is not None
    assert abs(r["mean_char_slant"]) > CHAR_SLANT_NORM_DEG
    # 글씨체 전체의 습관이라 특정 글자를 짚을 수 없다 — 박스는 그대로 초록.
    assert _red(r) == {}, "절대 기울어짐으로 빨간 박스를 치면 안 된다"


def test_slightly_slanted_is_not_nagged():
    """조금 기운 글씨까지 지적하면 잔소리가 된다 — 0~4°는 곧게 쓴 글씨로 인식된다."""
    from ai.analysis.handwriting_analyzer import CHAR_SLANT_NORM_DEG
    r = analyze_size_angle(_chars(tilt_all=4.0))
    assert abs(r["mean_char_slant"]) <= CHAR_SLANT_NORM_DEG


def test_mean_char_slant_matches_the_red_box_reference():
    """문구가 쓰는 기준값과 빨간 박스가 쓰는 기준값이 **같아야** 한다.

    다르면 "전체적으로 오른쪽으로 기울었다"는데 정작 오른쪽으로 기운 글자가
    빨갛지 않은, 앞뒤가 안 맞는 화면이 된다.
    """
    chars = _chars(tilt_all=18.0, bad={5: "tilt"})
    r = analyze_size_angle(chars)
    # 기준이 중앙값(=18°)이므로, 거기서 16° 더 기운 char_5만 빨갛다.
    assert abs(r["mean_char_slant"] - 18.0) < 0.01
    assert set(_red(r)) == {"char_5"}


def test_slant_is_none_when_unmeasurable():
    """못 잰 것을 0°(=완벽히 곧음)로 읽으면 안 된다."""
    chars = [{"char_id": "c0",
              "bounding_box": {"x": 10.0, "y": 10.0, "width": 40.0, "height": 40.0},
              "angle": 30.0, "angle_reliable": False, "confidence": 0.9}]
    assert analyze_size_angle(chars)["mean_char_slant"] is None
