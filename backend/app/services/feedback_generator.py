"""SFR-007 캔버스 피드백 — AI가 만든 축별 사유를 그대로 전달한다 (2026-10-08 재설계).

종전에는 여기서 항목마다 문장을 조립했다("획순이 정확합니다", "자간이 12.3px 좁습니다"…).
문구가 AI 사유·백엔드 문장·앱 라벨 세 곳에서 따로 만들어져 서로 어긋났다. 이제 문구는
AI의 failed_items 하나뿐이고, 백엔드는 점수 구간 문구만 붙인다.
설계: docs/superpowers/specs/2026-10-08-canvas-scoring-axes-design.md 7.2절
"""
from typing import Any, Dict, List, Optional


def _severity_from_score(score: Optional[int]) -> str:
    """점수 → 등급. 점수가 없는 글자(채점 거부)는 error."""
    if score is None or score < 50:
        return "error"
    return "good" if score >= 80 else "warning"


def _achievement_message(overall_score: int) -> str:
    """REQ-007 종합 점수에 따른 성취 메시지. SFR-005C Side Effects: 90점 이상 시 성취 이벤트"""
    if overall_score >= 90:
        return "훌륭해요! 표준 글씨체에 매우 가깝습니다. 🎉"
    elif overall_score >= 70:
        return "좋아요! 조금만 더 연습하면 완벽해질 거예요."
    elif overall_score >= 50:
        return "괜찮아요. 몇 가지 교정이 필요합니다."
    else:
        return "교정이 많이 필요합니다. 천천히 다시 연습해볼까요?"


def generate_canvas_feedback(analysis_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """글자별 채점 결과 → 피드백 응답.

    - 글자 문구 = 그 글자의 failed_items를 이은 것(비어 있으면 통과 — 앱이 그렇게 다룬다).
    - 세션 점수 = 점수가 있는 글자의 평균. 문장의 거부 글자는 AI가 0점으로 넣어 두므로
      평균을 끌어내린다(설계 5절). 낱자·한 글자의 거부는 점수가 None이라 세션도 None.
    """
    feedback_items = [{
        "target_id": r["char_id"],
        "feedback_message": ", ".join(r.get("failed_items") or []),
        "severity": _severity_from_score(r.get("overall_score")),
    } for r in analysis_results]

    scored = [r["overall_score"] for r in analysis_results if r.get("overall_score") is not None]
    # round()는 .5를 짝수로 보내 92.5가 92가 된다 — 사람이 기대하는 반올림(93)으로.
    overall_score = int(sum(scored) / len(scored) + 0.5) if scored else None
    refused = sum(1 for r in analysis_results if not r.get("scorable", True))

    if overall_score is None:
        message = "목표 글자와 달라 채점하지 않았어요. 다시 써 볼까요?"
    else:
        message = _achievement_message(overall_score)
        if refused:
            message += f" 다시 써야 할 글자가 {refused}자 있어요."
    return {
        "feedback_items": feedback_items,
        "overall_score": overall_score,
        "achievement_message": message,
    }
