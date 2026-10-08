"""
문장 쓰기 그룹핑 1단계 — expected_count(목표 글자 수) 기반 경계 판정 테스트.

문제: 기존 그룹핑은 고정 임계값(DIST_THRESHOLD_PX=60px, TIME_THRESHOLD_MS=400ms)을
"넘었는지"만으로 글자 경계를 판단한다. 문장을 빠르게 이어 쓰면 글자 사이 간격이
임계값을 안 넘어서(임계값보다 상대적으로 크더라도) 전부 한 글자로 뭉쳐버릴 수 있다.
목표 텍스트 길이(제시형 연습이라 이미 앎)를 알려주면, 절대 임계값이 아니라
"가장 크게 벌어진 (글자수-1)곳" 상대 순위로 경계를 잡아 이 문제를 줄인다.

이 테스트는 실제로 임계값을 넘지 않는(=옛 방식이면 전부 한 그룹으로 뭉쳐질)
간격을 일부러 만들어서, expected_count 유무에 따라 결과가 달라짐을 검증한다.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from canvas.stroke_grouping import (
    group_strokes_by_rules,
    group_strokes_into_chars,
    DIST_THRESHOLD_PX,
    TIME_THRESHOLD_MS,
)

assert DIST_THRESHOLD_PX == 60.0 and TIME_THRESHOLD_MS == 400.0, (
    "이 테스트의 좌표·시간 값은 기본 임계값(60px/400ms)을 전제로 설계됨 — "
    "임계값이 바뀌면 이 테스트도 같이 조정할 것."
)


def _point(x, y, t):
    return {"x": x, "y": y, "timestamp": t}


def _stroke(stroke_id, x, y, t):
    """단일 점짜리 획 — 그룹핑 로직은 bbox 중심·시작/끝 시간만 보므로 이걸로 충분."""
    return {"stroke_id": stroke_id, "points": [_point(x, y, t)]}


def _three_chars_written_quickly():
    """
    3글자, 글자당 2획. 글자 내부 간격(거리 ~5.8px, 시간 15ms)보다 글자 사이 간격
    (거리 ~25.2px, 시간 155ms)이 뚜렷이 크지만, 절대 임계값(60px/400ms)은 둘 다
    안 넘는다 — "빠르게 이어 쓴 문장"을 흉내낸 상황.
    """
    return [
        _stroke("s0", 10, 10, 0),     # 글자A 획1
        _stroke("s1", 15, 13, 15),    # 글자A 획2
        _stroke("s2", 40, 10, 170),   # 글자B 획1 (글자 경계)
        _stroke("s3", 45, 13, 185),   # 글자B 획2
        _stroke("s4", 70, 10, 340),   # 글자C 획1 (글자 경계)
        _stroke("s5", 75, 13, 355),   # 글자C 획2
    ]


def test_without_expected_count_everything_merges_into_one_group():
    """옛 방식(고정 임계값)은 이 간격들을 전부 안 넘긴다고 보고 한 그룹으로 뭉친다 —
    회귀 확인용: expected_count를 안 주면 지금까지와 동일하게 동작해야 한다."""
    strokes = _three_chars_written_quickly()
    groups = group_strokes_by_rules(strokes)
    assert len(groups) == 1
    assert len(groups[0]) == 6


def test_with_expected_count_splits_into_correct_groups():
    strokes = _three_chars_written_quickly()
    groups = group_strokes_by_rules(strokes, expected_count=3)
    assert len(groups) == 3
    assert [s["stroke_id"] for s in groups[0]] == ["s0", "s1"]
    assert [s["stroke_id"] for s in groups[1]] == ["s2", "s3"]
    assert [s["stroke_id"] for s in groups[2]] == ["s4", "s5"]


def test_expected_count_one_returns_single_group():
    """자음/모음 화면처럼 한 글자만 쓸 때(expected_count=1)는 항상 한 그룹."""
    strokes = _three_chars_written_quickly()
    groups = group_strokes_by_rules(strokes, expected_count=1)
    assert len(groups) == 1
    assert len(groups[0]) == 6


def test_expected_count_larger_than_stroke_count_falls_back_safely():
    """획보다 기대 글자 수가 많으면(입력 도중 등) 정확히 못 나누므로 기존 임계값
    방식으로 안전하게 폴백한다 — 크래시하거나 빈 그룹을 만들지 않는다."""
    strokes = _three_chars_written_quickly()  # 획 6개
    groups = group_strokes_by_rules(strokes, expected_count=10)
    assert sum(len(g) for g in groups) == 6
    assert all(len(g) > 0 for g in groups)


def test_group_strokes_into_chars_passes_expected_count_through():
    strokes = _three_chars_written_quickly()
    char_groups = group_strokes_into_chars(strokes, expected_count=3)
    assert len(char_groups) == 3
    assert [g["stroke_count"] for g in char_groups] == [2, 2, 2]


# ── 화면에 보여준 글자 자리로 나누기 (2026-09-17 신설) ────────────────────
#
# 종전에는 획 사이 간격의 상대 순위로 경계를 정했다. 문장을 빠르게 이어 쓰면 글자
# 사이 간격이 글자 안 간격보다 좁아질 수 있어 경계가 어긋난다 — 실제 사용 기록에서
# 6글자 문장의 4번째 글자('선', 5획)에 획이 1개만 배정되고 나머지가 옆 글자로 샌
# 사례가 확인됐다(FRONTEND_CHANGE.md §5-2). 획순·획방향·성분비율이 **같은 매칭
# 결과를 공유**하므로, 경계 하나가 틀리면 세 항목이 줄줄이 오판된다.
#
# 프론트는 화면에 그린 글자마다 자리를 보내준다 — 추측하지 말고 그걸 쓴다.

from ai.canvas.stroke_grouping import group_strokes_by_positions


def _line_stroke(x0, y0, x1, y1, t=0):
    return {"stroke_id": f"s{x0}_{y0}_{t}",
            "points": [{"x": x0, "y": y0, "timestamp": t},
                       {"x": x1, "y": y1, "timestamp": t + 10}]}


def _cells(n, width=100.0):
    return [{"char": "?", "index": i, "x": i * width, "y": 0.0,
             "width": width * 0.9, "height": 100.0} for i in range(n)]


def test_strokes_land_in_the_cell_they_were_written_in():
    cells = _cells(3)
    strokes = [_line_stroke(10, 10, 40, 40, 0),     # 0번 칸
               _line_stroke(210, 10, 240, 40, 10),  # 2번 칸
               _line_stroke(110, 10, 140, 40, 20)]  # 1번 칸
    groups = group_strokes_by_positions(strokes, cells)
    assert [len(g) for g in groups] == [1, 1, 1]
    assert groups[2][0]["points"][0]["x"] == 210


def test_gap_between_characters_does_not_decide_the_boundary():
    """글자 안 간격이 글자 사이 간격보다 넓어도 자리대로 갈라야 한다.

    간격 순위 방식이 틀리는 바로 그 조건이다.
    """
    cells = _cells(2, width=100.0)
    strokes = [_line_stroke(5, 5, 15, 15, 0),        # 0번 칸 왼쪽 끝
               _line_stroke(85, 5, 88, 15, 10),      # 0번 칸 오른쪽 끝(같은 글자, 멀리 떨어짐)
               _line_stroke(105, 5, 115, 15, 20)]    # 1번 칸(바로 옆, 간격은 좁음)
    groups = group_strokes_by_positions(strokes, cells)
    assert [len(g) for g in groups] == [2, 1]


def test_skipped_character_keeps_its_empty_slot():
    """안 쓴 글자를 지우면 뒤 글자들이 한 칸씩 당겨져 전부 다른 글자로 채점된다."""
    cells = _cells(3)
    strokes = [_line_stroke(10, 10, 40, 40, 0), _line_stroke(210, 10, 240, 40, 10)]
    groups = group_strokes_by_positions(strokes, cells)
    assert [len(g) for g in groups] == [1, 0, 1]


def test_stroke_outside_every_cell_goes_to_the_nearest_one():
    cells = _cells(2)
    groups = group_strokes_by_positions([_line_stroke(300, 10, 310, 40)], cells)
    assert [len(g) for g in groups] == [0, 1]


def test_order_within_a_character_follows_writing_time():
    """획순 채점이 이 순서를 본다 — 시간순이 깨지면 멀쩡한 획순이 틀렸다고 나온다."""
    cells = _cells(1)
    strokes = [_line_stroke(50, 10, 60, 40, t=500), _line_stroke(10, 10, 20, 40, t=100)]
    groups = group_strokes_by_positions(strokes, cells)
    assert [s["points"][0]["timestamp"] for s in groups[0]] == [100, 500]
