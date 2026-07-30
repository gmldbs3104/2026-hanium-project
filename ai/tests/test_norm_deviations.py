"""SFR-005I 절대 규범 축 (1.3, 2026-07-20 결정 / 3.3 문헌 조사) 단위 테스트.

norm_deviations: 자기 일관성(종합점수)과 **별개의 절대 규범 축**.
  ① 기울기 — 문장(행) 수평(0°) 이탈      (TILT_NORM_DEG, 2026-07-27 T4)
  ② 자간   — 띄어쓰기(어간) 뭉개짐        (이봉 분포 붕괴 = 넓은 gap 소실)
  ③ 행간   — 줄 겹침 (baseline 간격 / 글자 높이 < LINE_NORM_MIN_RATIO)
규범 이탈은 **경고만** — 종합점수(total_score)에 반영되지 않는다.
"""
from ai.analysis.handwriting_analyzer import (
    analyze_size_angle,
    TILT_NORM_DEG,
    LINE_NORM_MIN_RATIO,
)


def _row(y, n, step=95.0):
    """(행 상단 y, 인접 글자 사이 x 스텝 리스트) — n글자."""
    return (y, [step] * (n - 1))


def _grid(rows_spec, angle=2.0, h=100.0, w=60.0, x0=50.0,
          conf=0.9, reliable=True, dy=0.0):
    """rows_spec: [(row_top_y, [x_steps]), ...]. 각 행 글자수 = len(steps)+1.

    글자는 명료도 게이트에 걸리지 않게 충분히 큼(h=100 ≥ CLARITY_MIN_H),
    폭이 좁아 병합 의심 아님, confidence 높음.
    dy>0이면 행 내에서 글자마다 y를 dy씩 내려 줄을 기울인다(문장 기울기 유발).
    """
    chars = []
    k = 0
    for (y, steps) in rows_spec:
        x = x0
        yy = float(y)
        n = len(steps) + 1
        for c in range(n):
            chars.append({
                "char_id": f"c{k}",
                "bounding_box": {"x": x, "y": yy,
                                 "width": w, "height": h},
                "angle": float(angle), "angle_reliable": reliable,
                "confidence": conf,
            })
            k += 1
            if c < n - 1:
                x += steps[c]
                yy += dy
    return chars


# ── ① 기울기 규범 (문장/행 수평 이탈, 2026-07-27 T4) ──────────────────
def test_tilt_norm_violated_when_line_slopes():
    # 4글자 행이 오른쪽 아래로 기욺: dy=15 / step=95 → atan(0.158)≈9° > TILT_NORM_DEG(7)
    chars = _grid([_row(80, 4)], dy=15.0)
    nd = analyze_size_angle(chars)["norm_deviations"]
    assert nd["tilt"]["violated"] is True
    assert nd["tilt"]["value"] >= TILT_NORM_DEG
    assert nd["tilt"]["message"]


def test_tilt_norm_ok_when_horizontal():
    chars = _grid([_row(80, 4)], dy=0.0)   # 수평 행
    nd = analyze_size_angle(chars)["norm_deviations"]
    assert nd["tilt"]["violated"] is False


def test_tilt_norm_skipped_when_too_few_chars_for_line():
    chars = _grid([_row(80, 2)], dy=15.0)   # 2글자 < 3 → 직선 적합 불가
    nd = analyze_size_angle(chars)["norm_deviations"]
    assert nd["tilt"]["violated"] is False
    assert nd["tilt"].get("evaluated") is False


# ── ② 자간 규범 (띄어쓰기 뭉개짐) ─────────────────────────────────────
def test_spacing_norm_violated_when_long_text_has_no_word_gaps():
    # 2행 × 8열 = 16글자, 모든 자간이 word_gap(=행높이×0.55=55) 이하 → 붙여 씀
    chars = _grid([_row(80, 8, step=95.0),    # edge_gap = 95-60 = 35 < 55
                   _row(230, 8, step=95.0)], angle=2.0)
    nd = analyze_size_angle(chars)["norm_deviations"]
    assert nd["spacing"]["violated"] is True
    assert nd["spacing"]["message"]


def test_spacing_norm_ok_when_word_gaps_present():
    # 같은 16글자지만 행마다 넓은 gap(150 → edge 90 > 55) 2개씩 삽입 → 띄어쓰기 존재
    rows = [
        (80.0,  [95, 95, 150, 95, 95, 150, 95]),
        (230.0, [95, 150, 95, 95, 150, 95, 95]),
    ]
    nd = analyze_size_angle(_grid(rows, angle=2.0))["norm_deviations"]
    assert nd["spacing"]["violated"] is False


def test_spacing_norm_skipped_for_short_text():
    # 5글자짜리 한 단어는 정상적으로 띄어쓰기가 없음 → 규범 판정 생략
    chars = _grid([_row(80, 5, step=95.0)], angle=2.0)
    nd = analyze_size_angle(chars)["norm_deviations"]
    assert nd["spacing"]["violated"] is False
    assert nd["spacing"].get("evaluated") is False


# ── ③ 행간 규범 (줄 겹침) ─────────────────────────────────────────────
def test_line_spacing_norm_violated_when_rows_overlap():
    # 3행, baseline 간격 80 < 글자 높이 100 → 비율 0.8 < 1.0 (겹침)
    chars = _grid([_row(80, 3), _row(160, 3), _row(240, 3)], angle=2.0)
    nd = analyze_size_angle(chars)["norm_deviations"]
    assert nd["line_spacing"]["violated"] is True
    assert nd["line_spacing"]["value"] < LINE_NORM_MIN_RATIO
    assert nd["line_spacing"]["message"]


def test_line_spacing_norm_ok_when_rows_well_separated():
    # 3행, baseline 간격 220 → 비율 2.2 > 1.0
    chars = _grid([_row(80, 3), _row(300, 3), _row(520, 3)], angle=2.0)
    nd = analyze_size_angle(chars)["norm_deviations"]
    assert nd["line_spacing"]["violated"] is False


# ── 규범은 점수에 반영되지 않는다 (별도 축) ──────────────────────────
def test_norm_deviations_do_not_affect_total_score():
    # 행간만 다름(겹침 gap80 vs 정상 gap220). 둘 다 등간격이라 행간 CV 등 점수 지표는
    # 동일 → 종합점수는 같고 '행간 규범(줄 겹침)'만 달라야 한다(규범=경고, 점수 미반영).
    overlap = _grid([_row(80, 3), _row(160, 3), _row(240, 3)])   # gap 80 < h100 → 겹침
    spaced  = _grid([_row(80, 3), _row(300, 3), _row(520, 3)])   # gap 220 → 정상
    r_o = analyze_size_angle(overlap)
    r_s = analyze_size_angle(spaced)
    assert r_o["total_score"] == r_s["total_score"]
    assert r_o["norm_deviations"]["line_spacing"]["violated"] is True
    assert r_s["norm_deviations"]["line_spacing"]["violated"] is False


def test_norm_deviations_present_with_three_axes_and_not_a_metric():
    r = analyze_size_angle(_grid([_row(80, 6)], angle=2.0))
    assert "norm_deviations" in r
    assert set(r["norm_deviations"].keys()) == {"tilt", "spacing", "line_spacing"}
    assert "norm_deviations" not in r["metrics"]   # 종합점수 지표가 아님
