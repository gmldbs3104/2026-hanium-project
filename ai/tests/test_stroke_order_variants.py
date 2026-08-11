"""
SFR-005C 획순 복수 정본 (IMPLEMENTATION_PLAN 2.1) 테스트.

근거: NORM_STROKE_RESEARCH.md §2 — 한글 필순은 어문 규범상 미규정이라 단일 정답을
강제할 근거가 없고, ㅌ은 '가운데 가로획 순서(2번째 vs 마지막)'에 이견이 흔하다.
템플릿(canvas/synthetic_stroke_generator._BASE_CONSONANT_PATHS["ㅌ"]) canonical 순서는
[위가로(0), 가운데가로(1), ㄴ자(2)]이므로, 관습(가운데 가로를 마지막)은 순열 [0,2,1].

이 테스트는 획을 생성기가 아니라 표준 배치 템플릿에서 직접 만들어(노이즈 없음)
'재배열'만으로 순서를 통제한다 — 채점 로직의 순서 판정만 결정적으로 검증하기 위함.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from canvas.canvas_quality_analyzer import (
    analyze_stroke_order_by_position,
    analyze_canvas_writing,
)
from canvas.synthetic_stroke_generator import _syllable_layout
from canvas.stroke_standards import decompose_syllable

FULL_BBOX = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}


def _standard_paths(char):
    """음절의 표준 획 경로 목록([0,1] 음절 좌표계, canonical 순서)."""
    cho, jung, jong = decompose_syllable(char)
    layout = _syllable_layout(cho, jung, jong)
    return [p for _, paths in layout for p in paths]


def _build_strokes(char, order=None):
    """char의 표준 획을 order(전체 인덱스 순열)대로 재배열해 stroke dict 목록으로."""
    paths = _standard_paths(char)
    if order is not None:
        paths = [paths[i] for i in order]
    strokes = []
    for i, path in enumerate(paths):
        pts = [{"x": x, "y": y, "pressure": 1.0, "timestamp": i * 100 + j}
               for j, (x, y) in enumerate(path)]
        strokes.append({"stroke_id": f"s{i}", "points": pts})
    return strokes


# "트" = ㅌ(3획) + ㅡ(1획) → 인덱스 0,1,2 = ㅌ / 3 = ㅡ. ㅌ 대안 [0,2,1] → 전체 [0,2,1,3].


def test_standard_order_has_no_error_and_no_alternative_note():
    strokes = _build_strokes("트")  # 표준 순서
    result = analyze_stroke_order_by_position(strokes, FULL_BBOX, "트")
    assert result["error_count"] == 0
    assert result.get("used_alternative_order") is False
    assert not result.get("notes")


def test_alternative_taeut_order_is_accepted_without_penalty():
    strokes = _build_strokes("트", order=[0, 2, 1, 3])  # ㅌ 가운데 가로를 마지막에
    result = analyze_stroke_order_by_position(strokes, FULL_BBOX, "트")
    assert result["error_count"] == 0
    assert result.get("used_alternative_order") is True


def test_alternative_order_carries_informational_note():
    strokes = _build_strokes("트", order=[0, 2, 1, 3])
    result = analyze_stroke_order_by_position(strokes, FULL_BBOX, "트")
    notes = result.get("notes") or []
    assert len(notes) >= 1
    joined = " ".join(notes)
    assert "표준" in joined  # "통용 순서입니다. 표준 필순은 …" 형태의 안내 병기


def test_genuinely_wrong_order_still_counts_as_error():
    # 첫 두 획을 뒤바꾼 순서 [1,0,2,3]는 허용 대안이 아니므로 오류로 남아야 한다.
    strokes = _build_strokes("트", order=[1, 0, 2, 3])
    result = analyze_stroke_order_by_position(strokes, FULL_BBOX, "트")
    assert result["error_count"] > 0
    assert result.get("used_alternative_order") is False


def test_alternative_order_yields_no_penalty_flag_in_full_analysis():
    strokes = _build_strokes("트", order=[0, 2, 1, 3])
    char_groups = [{"char_id": "c0", "strokes": strokes, "bounding_box": FULL_BBOX}]
    results = analyze_canvas_writing(char_groups, target_text="트")
    assert len(results) == 1
    assert "stroke_order_error" not in results[0]["correction_flags"]
