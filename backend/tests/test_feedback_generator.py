"""SFR-007 캔버스 피드백 — AI 축 사유를 그대로 전달하고, 점수 구간 문구만 붙인다."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.services.feedback_generator import generate_canvas_feedback  # noqa: E402


def _char(cid, score, failed=(), scorable=True):
    return {"char_id": cid, "overall_score": score, "failed_items": list(failed), "scorable": scorable}


def test_messages_are_the_failed_items_joined():
    fb = generate_canvas_feedback([
        _char("char_0", 85, ["모양(1획 기울어짐)", "획순(1획 반대로 그음)"]),
        _char("char_1", 100),
    ])
    assert fb["feedback_items"][0]["feedback_message"] == "모양(1획 기울어짐), 획순(1획 반대로 그음)"
    assert fb["feedback_items"][0]["severity"] == "good"
    assert fb["feedback_items"][1]["feedback_message"] == ""
    assert fb["feedback_items"][1]["severity"] == "good"
    assert fb["overall_score"] == 93          # 92.5 → 93 (짝수 반올림이면 92)


def test_refused_character_in_sentence_is_zero_and_counted():
    fb = generate_canvas_feedback([
        _char("char_0", 100),
        _char("char_1", 0, ["다시 써 주세요(목표 글자와 다름)"], scorable=False),
        _char("char_2", 70, ["짜임새(종성 'ㄹ' 너무 큼)"]),
    ])
    assert fb["overall_score"] == 57
    assert fb["feedback_items"][1]["severity"] == "error"
    assert fb["achievement_message"].endswith("다시 써야 할 글자가 1자 있어요.")


def test_refused_single_character_has_no_score():
    fb = generate_canvas_feedback([
        _char("char_0", None, ["다시 써 주세요(목표 글자와 다름)"], scorable=False),
    ])
    assert fb["overall_score"] is None
    assert fb["achievement_message"] == "목표 글자와 달라 채점하지 않았어요. 다시 써 볼까요?"
    assert fb["feedback_items"][0]["severity"] == "error"
