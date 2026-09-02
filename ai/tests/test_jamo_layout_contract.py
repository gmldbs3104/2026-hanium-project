"""자모 배치 정본이 AI와 프론트에서 **같은 자리**를 가리키는지 고정한다.

왜 이 테스트가 필요한가
----------------------
사용자는 프론트가 그려주는 획순 가이드 위에 글씨를 쓰고, AI는 자기 템플릿을 기준으로
채점한다. 두 배치가 어긋나면 **"가이드대로 잘 썼는데 성분 비율이 틀렸다"** 는 판정이
나온다. 실제로 2026-09-01 이전까지 두 벌이 최대 0.15까지 어긋나 있었다(AI는 캔버스를
꽉 채우는 단순화 값, 프론트는 명조 글리프 기준 값). 획순만 볼 때는 상대 비교라
드러나지 않았지만, 성분 비율 채점이 붙으면 바로 오판으로 이어진다.

그래서 이 테스트는 **프론트 dart 소스를 실제로 읽어서** 대조한다. 값을 여기에 베껴
두면 dart가 바뀌었을 때 못 잡으므로, 베끼지 말 것.
"""
import re
from pathlib import Path

from ai.canvas.synthetic_stroke_generator import jamo_boxes, single_jamo_box

# ai/tests/ → ai/ → 저장소 루트 → frontend/...
_DART = (Path(__file__).resolve().parents[2]
         / "frontend/lib/features/canvas_mode/data/stroke_order_data.dart")

# dart의 Rect.fromLTWH(left, top, width, height) → (x0, y0, x1, y1)
_RECT_RE = re.compile(
    r"Rect\.fromLTWH\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\)")

# dart 쪽은 사람이 읽는 소수 3자리로 적으므로 반올림 오차를 허용한다.
# 화면 1000px 기준 1.5px 미만 — 눈으로도 채점으로도 차이가 없다.
# (dart는 x,w를 따로 적어 x1=x+w 계산에 반올림이 두 번 쌓인다)
TOL = 1.5e-3


def _front_boxes():
    """dart의 _single/_syllable 구간에서 Rect 4개를 순서대로 뽑는다.

    반환 순서 = (낱자, 초성, 중성ㅏ, 종성) — dart 소스에 적힌 순서 그대로.
    """
    src = _DART.read_text(encoding="utf-8")
    start = src.index("List<List<Offset>> _single(")
    end = src.index("Offset _labelPos(")
    found = _RECT_RE.findall(src[start:end])
    assert len(found) == 4, (
        f"dart에서 Rect를 4개(낱자·초성·중성·종성) 찾아야 하는데 {len(found)}개다 — "
        f"stroke_order_data.dart의 _single/_syllable 구조가 바뀌었으면 이 파서도 고칠 것")
    boxes = []
    for l, t, w, h in found:
        l, t, w, h = float(l), float(t), float(w), float(h)
        boxes.append((l, t, l + w, t + h))
    return boxes


def _assert_box(actual, expected, label):
    for a, e, axis in zip(actual, expected, ("x0", "y0", "x1", "y1")):
        assert abs(a - e) < TOL, (
            f"{label} 의 {axis} 가 어긋난다: AI={a:.4f} vs 프론트={e:.4f}\n"
            f"  AI      = ai/canvas/synthetic_stroke_generator.py 의 배치 상수\n"
            f"  프론트  = {_DART.name} 의 _single/_syllable\n"
            f"  → 한쪽만 고치지 말고 양쪽을 함께 고칠 것")


def _skip_if_no_frontend():
    if not _DART.exists():
        import pytest
        pytest.skip("프론트가 없는 클론(파인튜닝 전용)에서는 대조할 대상이 없다")


def test_single_jamo_box_matches_frontend():
    _skip_if_no_frontend()
    front_single = _front_boxes()[0]
    _assert_box(single_jamo_box(), front_single, "낱자 상자")


def test_syllable_boxes_match_frontend():
    """받침 있는 세로모음 음절('각')이 배치 정본의 기준점이다."""
    _skip_if_no_frontend()
    _, f_cho, f_jung, f_jong = _front_boxes()
    boxes = dict(enumerate(jamo_boxes("ㄱ", "ㅏ", "ㄱ")))
    _assert_box(boxes[0][1], f_cho, "초성 상자")
    _assert_box(boxes[1][1], f_jung, "중성 상자")
    _assert_box(boxes[2][1], f_jong, "종성 상자")


def test_jamo_boxes_order_is_cho_jung_jong():
    """성분 비율 채점이 '1번이 모음'이라는 순서에 의존하므로 고정한다."""
    labels = [j for j, _ in jamo_boxes("ㄱ", "ㅏ", "ㄴ")]
    assert labels == ["ㄱ", "ㅏ", "ㄴ"]


def test_no_jongseong_drops_third_box():
    assert len(jamo_boxes("ㄱ", "ㅏ", "")) == 2


def test_body_grows_downward_without_jongseong():
    """종성이 없으면 본체(초성+중성)가 아래까지 내려와야 한다."""
    with_jong = dict((j, b) for j, b in jamo_boxes("ㄱ", "ㅏ", "ㄱ"))
    no_jong = dict((j, b) for j, b in jamo_boxes("ㄱ", "ㅏ", ""))
    assert no_jong["ㅏ"][3] > with_jong["ㅏ"][3]


def test_boxes_stay_inside_canvas():
    """어떤 조합이든 상자가 [0,1] 밖으로 나가면 정규화 좌표 가정이 깨진다."""
    for jung in ("ㅏ", "ㅗ", "ㅘ", "ㅣ", "ㅡ", "ㅢ"):
        for jong in ("", "ㄱ", "ㄻ"):
            for jamo, (x0, y0, x1, y1) in jamo_boxes("ㄱ", jung, jong):
                assert 0.0 <= x0 < x1 <= 1.0, f"{jung}/{jong} {jamo} x범위 {x0}~{x1}"
                assert 0.0 <= y0 < y1 <= 1.0, f"{jung}/{jong} {jamo} y범위 {y0}~{y1}"


# ── 자모 **획 정의**도 양쪽이 같아야 한다 ──────────────────────────────────
#
# 위쪽 테스트는 자모가 놓이는 **자리(상자)** 만 고정한다. 그런데 정작 반복해서 터진
# 것은 자리가 아니라 **획 자체**였다. 2026-09-01 하루에만 네 번 나왔다.
#   · ㄱ·ㄴ — AI는 2획, 프론트 가이드는 1획 (꺾여도 펜을 떼지 않는다)
#   · ㅁ    — AI 4획 vs 프론트 3획
#   · ㄹ    — AI ②가 우상단→좌중단 **사선**이었다. ㄹ에 사선은 없다.
#   · ㅓ·ㅕ·ㅗ — 획 순서가 서로 뒤집혀 있었다
# 게다가 대조하다 ㅗ·ㅜ·ㅛ·ㅠ는 **모양이 통째로 뒤바뀐 것**까지 드러났다
# (ㅗ 자리에 ㅜ 모양이 들어 있었다).
#
# 증상은 늘 같다 — 가이드대로 잘 썼는데 획순·획방향이 틀렸다고 나온다. 사용자가
# 보는 것은 프론트 가이드이므로 **프론트가 정답**이고 AI가 따라가야 한다.

_AI_PATH_TABLES = ("_BASE_CONSONANT_PATHS", "_BASE_VOWEL_PATHS")

# dart: 'ㄱ': [ [_o(.16, .22), ...], ... ],
_JAMO_ENTRY_RE = re.compile(r"'([\u3131-\u3163])'\s*:\s*\[(.*?)\n  \]", re.S)
_STROKE_RE = re.compile(r"\[((?:\s*_o\([^)]*\)\s*,?)+)\s*\]")
_PT_RE = re.compile(r"_o\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)")


def _front_jamo_paths():
    src = _DART.read_text(encoding="utf-8")
    out = {}
    for jamo, body in _JAMO_ENTRY_RE.findall(src):
        strokes = [[(float(x), float(y)) for x, y in _PT_RE.findall(s)]
                   for s in _STROKE_RE.findall(body)]
        if strokes:
            out[jamo] = strokes
    return out


def _ai_jamo_paths():
    from ai.canvas import synthetic_stroke_generator as g
    out = {}
    for name in _AI_PATH_TABLES:
        out.update(getattr(g, name))
    return out


def _shape(strokes):
    """획마다 (꺾임 수, 전체 진행 방향)으로 요약.

    좌표계가 서로 달라도(AI 0.15~0.85, 프론트 0.16~0.86) 비교되도록 **모양과 방향**만
    남긴다. 정확한 좌표까지 맞추라는 뜻은 아니다 — 획을 몇 번에 나눠 어느 쪽으로
    긋는지가 채점에 쓰이는 전부다.
    """
    out = []
    for st in strokes:
        if len(st) < 2:
            out.append("?")
            continue
        dx, dy = st[-1][0] - st[0][0], st[-1][1] - st[0][1]
        d = ("→" if dx > 0.08 else "←" if dx < -0.08 else "") + \
            ("↓" if dy > 0.08 else "↑" if dy < -0.08 else "")
        out.append(f"{len(st) - 1}절{d or '·'}")
    return " ".join(out)


def test_jamo_stroke_paths_match_frontend():
    _skip_if_no_frontend()
    ai, front = _ai_jamo_paths(), _front_jamo_paths()
    shared = sorted(set(ai) & set(front))
    assert shared, "프론트에서 자모 획 정의를 하나도 못 읽었다 — 이 파서를 고칠 것"
    problems = []
    for jamo in shared:
        if len(ai[jamo]) != len(front[jamo]):
            problems.append(f"{jamo}: 획수 AI={len(ai[jamo])} vs 프론트={len(front[jamo])}")
        elif _shape(ai[jamo]) != _shape(front[jamo]):
            problems.append(
                f"{jamo}: 획 모양/순서 AI=[{_shape(ai[jamo])}] vs 프론트=[{_shape(front[jamo])}]")
    assert not problems, (
        "자모 획 정의가 AI와 프론트에서 다르다 — 사용자는 프론트 가이드를 보고 쓰므로\n"
        "**프론트가 정답**이고 AI(synthetic_stroke_generator.py)를 맞춰야 한다:\n  "
        + "\n  ".join(problems))


def test_horizontal_vowel_tick_is_on_the_right_side():
    """ㅗ·ㅛ는 짧은 획이 막대 **위**, ㅜ·ㅠ는 **아래**다.

    프론트에 ㅜ·ㅛ·ㅠ가 없어 위 대조로는 안 걸린다. 그런데 실제로 AI 표에서
    ㅗ↔ㅜ, ㅛ↔ㅠ의 **모양이 통째로 뒤바뀌어** 있었다(2026-09-01). 자모의 정체가
    걸린 문제라 프론트 유무와 무관하게 따로 고정한다.
    """
    ai = _ai_jamo_paths()
    for jamo, tick_side in (("ㅗ", "위"), ("ㅛ", "위"), ("ㅜ", "아래"), ("ㅠ", "아래")):
        strokes = ai[jamo]
        bars = [s for s in strokes
                if abs(s[-1][0] - s[0][0]) > abs(s[-1][1] - s[0][1])]
        ticks = [s for s in strokes if s not in bars]
        assert bars and ticks, f"{jamo}: 가로 막대와 짧은 획을 못 갈랐다"
        bar_y = sum(p[1] for s in bars for p in s) / sum(len(s) for s in bars)
        tick_y = sum(p[1] for s in ticks for p in s) / sum(len(s) for s in ticks)
        actual = "위" if tick_y < bar_y else "아래"   # y는 아래로 증가
        assert actual == tick_side, (
            f"{jamo}: 짧은 획이 막대의 {actual}쪽에 있다 (표준은 {tick_side}쪽) — "
            f"{jamo}와 짝 자모의 모양이 뒤바뀐 게 아닌지 확인할 것")
