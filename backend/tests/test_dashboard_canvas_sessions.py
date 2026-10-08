"""대시보드 캔버스 집계 — 저장된 축 점수(item_scores)로 세션을 요약한다."""
import os
import sys
import types
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.services.dashboard_service import summarize_canvas_sessions  # noqa: E402


def _row(score, items=None, flags=None):
    return types.SimpleNamespace(overall_score=score, item_scores=items, correction_flags=flags or [],
                                 created_at=datetime(2026, 10, 8, 12, 0))


def test_session_overall_is_mean_including_zero_for_refused_characters():
    out = summarize_canvas_sessions({"s1": [
        _row(100, {"획순": 100, "모양": 100}),
        _row(0, None, ["unscorable"]),
        _row(70, {"획순": 70, "모양": 100}),
    ]})
    assert len(out) == 1
    assert round(out[0]["overall"]) == 57
    assert out[0]["items"] == {"획순": 85.0, "모양": 100.0}


def test_session_with_no_scores_is_skipped():
    assert summarize_canvas_sessions({"s1": [_row(None, None, ["unscorable"])]}) == []


def test_legacy_rows_without_item_scores_count_for_overall_only():
    out = summarize_canvas_sessions({"s1": [_row(80, None), _row(60, None)]})
    assert out[0]["overall"] == 70.0 and out[0]["items"] == {}


def test_none_axis_scores_are_excluded_not_zero():
    out = summarize_canvas_sessions({"s1": [_row(100, {"획순": 100, "짜임새": None})]})
    assert out[0]["items"] == {"획순": 100.0}
