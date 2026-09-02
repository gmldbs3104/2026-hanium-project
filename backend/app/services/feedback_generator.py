from typing import List, Dict, Any, Optional


def _severity_from_score(score: Optional[int]) -> Optional[str]:
    """점수 기준으로 severity 결정. 잰 항목이 하나도 없으면 None(등급 없음).

    None을 0점으로 떨어뜨리면 "아무것도 못 쟀다"가 "형편없다"로 뒤바뀐다.
    """
    if score is None:
        return None
    if score >= 80:
        return "good"
    elif score >= 50:
        return "warning"
    else:
        return "error"


def _stroke_order_message(stroke_order_result: Optional[Dict[str, Any]]) -> str:
    # target_text가 없었던 세션(제시형이 아님)은 획순 채점 자체가 생략된다.
    if stroke_order_result is None:
        return ""
    if stroke_order_result.get("likely_wrong_character"):
        return "; ".join(stroke_order_result.get("corrections", [])) or "목표 글자와 많이 달라 보입니다."
    error_count = stroke_order_result["error_count"]
    if error_count == 0:
        return "획순이 정확합니다."
    return f"획순에 {error_count}개의 오류가 있습니다. 표준 획순을 다시 확인해보세요."


def _direction_message(direction_result: Optional[Dict[str, Any]]) -> str:
    """획을 올바른 방향으로 그었는가 (2026-09-01 신설)."""
    if not direction_result or direction_result.get("checked", 0) == 0:
        return ""
    if direction_result["error_count"] == 0:
        return "획을 모두 올바른 방향으로 그었습니다."
    # 어느 획이 문제인지는 AI가 이미 문장으로 만들어 준다.
    return " ".join(direction_result.get("corrections", [])) or "일부 획의 방향이 표준과 다릅니다."


def _balance_message(balance_result: Optional[Dict[str, Any]]) -> str:
    """초·중·종성의 크기·자리 균형 (2026-09-01 신설).

    낱자(ㄱ·ㅏ)는 성분이 하나뿐이라 balance_result 자체가 None이다 — 이 경우
    아무 문구도 만들지 않는다. 안 잰 것을 잘했다고 말하지 않기 위해서다.
    """
    if not balance_result or not balance_result.get("components"):
        return ""
    corrections = balance_result.get("corrections") or []
    if not corrections:
        return "초성·중성·종성의 크기 균형이 좋습니다."
    return " ".join(corrections)


def _spacing_message(deviation: Optional[float]) -> str:
    # 글자가 하나뿐인 연습에서는 비교할 옆 글자가 없다 → None. 문구를 만들지 않는다.
    if deviation is None:
        return ""
    if abs(deviation) < 5:
        return "자간이 적절합니다."
    elif deviation > 0:
        return f"자간이 표준보다 {abs(deviation):.1f}px 넓습니다. 글자를 더 가깝게 써보세요."
    else:
        return f"자간이 표준보다 {abs(deviation):.1f}px 좁습니다. 글자 사이에 여유를 두어보세요."


def _size_message(size_fill_ratio: Optional[float], deviation: Optional[float]) -> str:
    """크기 — 가이드 상자 대비 배율이 있으면 그걸 쓰고, 없으면 상대 편차로 폴백."""
    if size_fill_ratio is not None:
        if 0.75 <= size_fill_ratio <= 1.30:
            return "글자 크기가 적절합니다."
        if size_fill_ratio < 0.75:
            return "글자가 표준보다 작습니다. 칸을 좀 더 채워서 써보세요."
        return "글자가 표준보다 큽니다. 칸 안에 들어오도록 써보세요."
    if deviation is None:
        return ""
    if abs(deviation) < 10:
        return "글자 크기가 적절합니다."
    elif deviation > 0:
        return f"글자가 다른 글자보다 {abs(deviation):.1f}% 큽니다."
    else:
        return f"글자가 다른 글자보다 {abs(deviation):.1f}% 작습니다."


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
        score = result.get("overall_score")
        severity = _severity_from_score(score)
        if severity is None:
            continue        # 잰 항목이 없으면 등급도 문구도 만들지 않는다

        # 안 잰 항목은 빈 문자열을 돌려주고 아래에서 걸러진다 — 미측정을 칭찬으로
        # 바꾸지 않기 위해서다. 연습 종류마다 실제로 나가는 문구 수가 다르다.
        messages = [
            _stroke_order_message(result["stroke_order_result"]),
            _direction_message(result.get("direction_result")),
            _balance_message(result.get("balance_result")),
            _size_message(result.get("size_fill_ratio"), result.get("size_deviation")),
            _spacing_message(result.get("spacing_deviation")),
        ]

        feedback_items.append({
            "target_id": char_id,
            "feedback_message": " ".join(m for m in messages if m),
            "severity": severity,
        })

    # 종합 점수를 못 낸 글자(잰 항목이 하나도 없는 경우)는 평균에서 제외한다.
    scored = [r["overall_score"] for r in analysis_results
              if r.get("overall_score") is not None]
    overall_score = round(sum(scored) / len(scored)) if scored else 0

    return {
        "feedback_items": feedback_items,
        "overall_score": overall_score,
        "achievement_message": _achievement_message(overall_score),
    }