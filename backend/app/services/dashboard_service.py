from collections import defaultdict
from datetime import datetime, timedelta, date as date_type
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.correction import CanvasAnalysisResult, ImageAnalysisResult
from app.services.ai_adapters import canvas_item_scores

DASHBOARD_CACHE_TTL = 3600  # SFR-008: 집계 결과 1시간 캐시
SESSIONS_PER_LEVEL = 5  # 게이미피케이션: 누적 세션 5회당 1레벨


def _since(period: str) -> Optional[datetime]:
    if period == "week":
        return datetime.utcnow() - timedelta(days=7)
    if period == "month":
        return datetime.utcnow() - timedelta(days=30)
    return None


def _canvas_item_scores(row: CanvasAnalysisResult) -> dict[str, float]:
    """저장된 편차에서 항목 점수를 만든다 — 계산은 AI 함수 하나에 위임한다.

    종전에는 여기서 백엔드 설정 계수(크기·자간 0.5 / 획순 10)로 다시 계산했는데,
    AI가 세션 점수를 만들 때 쓰는 계수(0.8 / 0.3 / 15)와 달라서 **같은 글씨인데
    결과 화면과 분석 화면의 점수가 어긋났다**(DATA_FLOW.md §8-G).

    목표 글자를 몰라 획순을 못 잰 경우 "획순"은 None으로 오며, 호출부가 집계에서
    제외한다 — 0건 오류로 보고 만점을 주면 안 잰 지표로 칭찬하는 셈이다(§4-1).
    """
    scores = canvas_item_scores(
        row.size_deviation, row.spacing_deviation, row.stroke_order_result
    )
    return {name: score for name, score in scores.items() if score is not None}


def _improvement_rate(ordered_scores: list[float]) -> float:
    """시간순 점수 목록에서 전반부 vs 후반부 평균 변화율(%)을 반환."""
    if len(ordered_scores) < 2:
        return 0.0
    mid = len(ordered_scores) // 2
    first_avg = sum(ordered_scores[:mid]) / mid
    second_avg = sum(ordered_scores[mid:]) / (len(ordered_scores) - mid)
    if first_avg == 0:
        return 0.0
    return round((second_avg - first_avg) / first_avg * 100, 1)


def _consecutive_streak(active_dates: set[date_type]) -> int:
    """오늘(아직 연습 안 했으면 어제)부터 거꾸로 훑어 끊기지 않고 이어진 날짜 수."""
    if not active_dates:
        return 0
    today = datetime.utcnow().date()
    cursor = today if today in active_dates else today - timedelta(days=1)
    streak = 0
    while cursor in active_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


async def _compute_level_and_streak(db: AsyncSession, user_id: UUID) -> tuple[int, int]:
    """
    게이미피케이션 요약치. period/mode 필터와 무관하게 항상 전체 기간 기준으로 계산한다
    (요구사항 문서에 없는 프론트 자체 추가 기능 — 정의는 팀 협의 결과).

    레벨 = 1 + 전체 누적 세션 수 // SESSIONS_PER_LEVEL
      - 캔버스는 session_id 단위(문자별로 여러 행 존재), 이미지는 행 하나 = 세션 하나
    연속 출석 = 캔버스/이미지 어느 쪽이든 하루에 한 번 이상 연습을 완료한 날의 연속 일수
    """
    canvas_session_ids = (
        await db.execute(
            select(CanvasAnalysisResult.session_id)
            .where(CanvasAnalysisResult.user_id == user_id)
            .distinct()
        )
    ).scalars().all()
    image_session_count = (
        await db.execute(
            select(func.count())
            .select_from(ImageAnalysisResult)
            .where(ImageAnalysisResult.user_id == user_id)
        )
    ).scalar_one()
    total_sessions = len(canvas_session_ids) + image_session_count
    level = 1 + total_sessions // SESSIONS_PER_LEVEL

    canvas_dates = (
        await db.execute(
            select(CanvasAnalysisResult.created_at).where(CanvasAnalysisResult.user_id == user_id)
        )
    ).scalars().all()
    image_dates = (
        await db.execute(
            select(ImageAnalysisResult.created_at).where(ImageAnalysisResult.user_id == user_id)
        )
    ).scalars().all()
    active_dates = {d.date() for d in canvas_dates} | {d.date() for d in image_dates}
    streak_days = _consecutive_streak(active_dates)

    return level, streak_days


async def get_dashboard_data(
    db: AsyncSession,
    user_id: UUID,
    period: str,
    mode: str,
) -> dict:
    since = _since(period)

    canvas_rows: list[CanvasAnalysisResult] = []
    image_rows: list[ImageAnalysisResult] = []

    if mode in ("canvas", "all"):
        q = (
            select(CanvasAnalysisResult)
            .where(CanvasAnalysisResult.user_id == user_id)
            .order_by(CanvasAnalysisResult.created_at)
        )
        if since:
            q = q.where(CanvasAnalysisResult.created_at >= since)
        canvas_rows = (await db.execute(q)).scalars().all()

    if mode in ("image", "all"):
        q = (
            select(ImageAnalysisResult)
            .where(ImageAnalysisResult.user_id == user_id)
            .order_by(ImageAnalysisResult.created_at)
        )
        if since:
            q = q.where(ImageAnalysisResult.created_at >= since)
        image_rows = (await db.execute(q)).scalars().all()

    # canvas 행을 session_id 단위로 묶기
    canvas_by_session: dict[str, list[CanvasAnalysisResult]] = defaultdict(list)
    for row in canvas_rows:
        canvas_by_session[row.session_id].append(row)

    # 세션 수준 요약 계산 (canvas)
    c_sessions = []
    for rows in canvas_by_session.values():
        overall = sum(r.overall_score or 0 for r in rows) / len(rows)
        item_acc: dict[str, list[float]] = defaultdict(list)
        for r in rows:
            for item, score in _canvas_item_scores(r).items():
                item_acc[item].append(score)
        c_sessions.append({
            "overall": overall,
            "date": rows[0].created_at.date(),
            "items": {k: sum(v) / len(v) for k, v in item_acc.items()},
        })

    # 세션 수준 요약 계산 (image)
    # ⚠️ 측정 불가 지표는 None으로 저장된다(글자/행 수 부족). 이를 0점으로 세면 "안 잰
    # 지표 = 최악"이 되어 평균과 취약 항목 순위가 오염된다 → items에서 아예 뺀다.
    # (종전 `or 0`이 이 버그였다. DATA_FLOW §4-2)
    i_sessions = [
        {
            "overall": row.overall_score or 0,
            "date": row.created_at.date(),
            "items": {
                name: score
                for name, score in (
                    ("크기 균일성", row.size_uniformity_score),
                    ("기울기 일관성", row.slant_consistency_score),
                    ("줄 정렬", row.line_alignment_score),
                    # 2026-08-12 추가(§5-8). AI는 원래 5지표를 채점했는데 DB에 3개만
                    # 쌓여서 자간·행간은 취약 항목 후보로도 오르지 못했다.
                    # 프론트는 항목 이름을 모른 채 목록을 그리므로 여기만 늘리면 화면에 뜬다.
                    ("자간 균등성", row.spacing_uniformity_score),
                    ("행간 균등성", row.line_spacing_uniformity_score),
                )
                if score is not None
            },
        }
        for row in image_rows
    ]

    total_canvas = len(c_sessions)
    total_image = len(i_sessions)

    # period/mode 필터와 무관하게 항상 전체 기간 기준 (이번 조회가 텅 비어도 레벨/연속출석은 유지)
    level, streak_days = await _compute_level_and_streak(db, user_id)

    if total_canvas + total_image == 0:
        return _empty_dashboard(level, streak_days)

    # --- period_summary ---
    # 날짜 순으로 정렬된 전체 점수 (improvement_rate 계산용)
    all_sessions_by_date = sorted(
        [(s["date"], s["overall"]) for s in c_sessions]
        + [(s["date"], s["overall"]) for s in i_sessions]
    )
    ordered_scores = [score for _, score in all_sessions_by_date]
    avg_score = round(sum(ordered_scores) / len(ordered_scores), 1)

    period_summary = {
        "total_sessions": total_canvas + total_image,
        "avg_score": avg_score,
        "improvement_rate": _improvement_rate(ordered_scores),
        "canvas_sessions": total_canvas,
        "image_sessions": total_image,
    }

    # --- weak_items (REQ-008-3: 점수 하위 10개) ---
    item_acc: dict[tuple[str, str], list[float]] = defaultdict(list)
    for s in c_sessions:
        for item, score in s["items"].items():
            item_acc[(item, "canvas")].append(score)
    for s in i_sessions:
        for item, score in s["items"].items():
            item_acc[(item, "image")].append(score)

    weak_items = sorted(
        [
            {
                "item": item,
                "avg_score": round(sum(scores) / len(scores), 1),
                "frequency": len(scores),
                "mode": m,
            }
            for (item, m), scores in item_acc.items()
        ],
        key=lambda x: x["avg_score"],
    )[:10]

    # --- score_trend (날짜 × 모드별 평균 점수) ---
    trend_acc: dict[tuple[date_type, str], list[float]] = defaultdict(list)
    for s in c_sessions:
        trend_acc[(s["date"], "canvas")].append(s["overall"])
    for s in i_sessions:
        trend_acc[(s["date"], "image")].append(s["overall"])

    score_trend = [
        {
            "date": d,
            "avg_score": round(sum(scores) / len(scores), 1),
            "mode": m,
        }
        for (d, m), scores in sorted(trend_acc.items())
    ]

    return {
        "period_summary": period_summary,
        "weak_items": weak_items,
        "score_trend": score_trend,
        "recommended_exercises": [],  # TODO: 연습 예문 DB 구축 후 구현
        "is_new_user": False,
        "level": level,
        "streak_days": streak_days,
    }


def _empty_dashboard(level: int = 1, streak_days: int = 0) -> dict:
    return {
        "period_summary": {
            "total_sessions": 0,
            "avg_score": 0.0,
            "improvement_rate": 0.0,
            "canvas_sessions": 0,
            "image_sessions": 0,
        },
        "weak_items": [],
        "score_trend": [],
        "recommended_exercises": [],
        "is_new_user": True,
        "level": level,
        "streak_days": streak_days,
    }
