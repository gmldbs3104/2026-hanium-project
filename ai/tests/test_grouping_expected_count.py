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
