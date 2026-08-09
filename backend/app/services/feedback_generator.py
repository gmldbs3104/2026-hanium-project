from typing import List, Dict, Any


def _severity_from_score(score: int) -> str:
    """점수 기준으로 severity 결정"""
    if score >= 80:
        return "good"
    elif score >= 50:
        return "warning"
    else:
        return "error"


def _stroke_order_message(error_count: int) -> str:
    if error_count == 0:
        return "획순이 정확합니다."
    return f"획순에 {error_count}개의 오류가 있습니다. 표준 획순을 다시 확인해보세요."


def _spacing_message(deviation: float) -> str:
    if abs(deviation) < 5:
        return "자간이 적절합니다."
    elif deviation > 0:
        return f"자간이 표준보다 {abs(deviation):.1f}px 넓습니다. 글자를 더 가깝게 써보세요."
    else:
        return f"자간이 표준보다 {abs(deviation):.1f}px 좁습니다. 글자 사이에 여유를 두어보세요."


def _size_message(deviation: float) -> str:
    if abs(deviation) < 10:
        return "글자 크기가 적절합니다."
    elif deviation > 0:
        return f"글자가 표준보다 {abs(deviation):.1f}% 큽니다."
    else:
        return f"글자가 표준보다 {abs(deviation):.1f}% 작습니다."


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
    """
    SFR-007: 캔버스 모드 분석 결과 → 피드백 메시지 생성
    """
    feedback_items = []

    for result in analysis_results:
        char_id = result["char_id"]
        score = result["overall_score"]
        severity = _severity_from_score(score)

        messages = [
            _stroke_order_message(result["stroke_order_result"]["error_count"]),
            _spacing_message(result["spacing_deviation"]),
            _size_message(result["size_deviation"]),
        ]

        feedback_items.append({
            "target_id": char_id,
            "feedback_message": " ".join(messages),
            "severity": severity,
        })

    overall_score = (
        round(sum(r["overall_score"] for r in analysis_results) / len(analysis_results))
        if analysis_results else 0
    )

    return {
        "feedback_items": feedback_items,
        "overall_score": overall_score,
        "achievement_message": _achievement_message(overall_score),
    }