"""
자모 단독(ㄱ·ㅏ 등) 획순 채점 테스트.

이전에는 표준 획순을 완성형 음절 분해(decompose_syllable)로만 만들었기 때문에,
낱개 자모 입력은 분해가 안 돼 stroke_order_result 없이 크기/자간만 채점됐다.
자음/모음 연습 탭(canvas_input_screen.dart의 '자음 쓰기'·'모음 쓰기', 연습 세트의
3분의 2)이 매번 이 경로를 탔다. _single_jamo_layout으로 예외 경로를 추가해
해결한다(DATA_FLOW.md §8 말미, STATUS.md §2).

이 테스트도 stroke_order_variants 테스트와 같은 방식으로, 표준 배치 템플릿에서
직접 획을 만들어(노이즈 없음) '재배열'만으로 순서를 통제한다.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from canvas.canvas_quality_analyzer import (
    analyze_stroke_order_by_position,
    analyze_canvas_writing,
)
from canvas.synthetic_stroke_generator import _single_jamo_layout
from canvas.stroke_standards import get_expected_sequence

FULL_BBOX = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}


def _standard_paths(jamo, is_vowel):
    """낱개 자모의 표준 획 경로 목록([0,1] 좌표계, canonical 순서)."""
    layout = _single_jamo_layout(jamo, is_vowel=is_vowel)
    return [p for _, paths in layout for p in paths]


def _build_strokes(jamo, is_vowel, order=None):
    """jamo의 표준 획을 order(전체 인덱스 순열)대로 재배열해 stroke dict 목록으로."""
    paths = _standard_paths(jamo, is_vowel)
    if order is not None:
        paths = [paths[i] for i in order]
    strokes = []
    for i, path in enumerate(paths):
        pts = [{"x": x, "y": y, "pressure": 1.0, "timestamp": i * 100 + j}
               for j, (x, y) in enumerate(path)]
        strokes.append({"stroke_id": f"s{i}", "points": pts})
    return strokes


def test_expected_sequence_no_longer_empty_for_solo_consonant():
    assert get_expected_sequence("ㄹ") == ["ㄹ_1", "ㄹ_2", "ㄹ_3"]


def test_expected_sequence_no_longer_empty_for_solo_vowel():
    assert get_expected_sequence("ㅑ") == ["ㅑ_1", "ㅑ_2", "ㅑ_3"]


def test_solo_consonant_standard_order_has_no_error():
    strokes = _build_strokes("ㄹ", is_vowel=False)  # ㄹ = 3획, 표준 순서대로
    result = analyze_stroke_order_by_position(strokes, FULL_BBOX, "ㄹ")
    # analyze_stroke_order_by_position의 expected_sequence는 (음절과 마찬가지로)
    # 자모 라벨만 쓰고 획 순번은 안 붙인다 — 순번 라벨은 get_expected_sequence 전용.
    assert result["expected_sequence"] == ["ㄹ", "ㄹ", "ㄹ"]
    assert result["error_count"] == 0


def test_solo_consonant_wrong_order_is_flagged():
    strokes = _build_strokes("ㄹ", is_vowel=False, order=[1, 0, 2])  # 순서 뒤바꿈
    result = analyze_stroke_order_by_position(strokes, FULL_BBOX, "ㄹ")
    assert result["error_count"] > 0


def test_solo_vowel_standard_order_has_no_error():
    strokes = _build_strokes("ㅑ", is_vowel=True)  # ㅑ = 3획
    result = analyze_stroke_order_by_position(strokes, FULL_BBOX, "ㅑ")
    assert result["error_count"] == 0


def test_solo_jamo_in_full_analysis_scores_stroke_order_not_null():
    strokes = _build_strokes("ㅏ", is_vowel=True)
    char_groups = [{"char_id": "c0", "strokes": strokes, "bounding_box": FULL_BBOX}]
    results = analyze_canvas_writing(char_groups, target_text="ㅏ")
    assert len(results) == 1
    assert results[0]["stroke_order_result"] is not None
    assert results[0]["stroke_order_result"]["error_count"] == 0
