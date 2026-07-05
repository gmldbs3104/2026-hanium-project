from collections import defaultdict
from datetime import datetime, timedelta, date as date_type
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.correction import CanvasAnalysisResult, ImageAnalysisResult
from app.core.config import settings

DASHBOARD_CACHE_TTL = 3600  # SFR-008: 집계 결과 1시간 캐시


def _since(period: str) -> Optional[datetime]:
    if period == "week":
        return datetime.utcnow() - timedelta(days=7)
    if period == "month":
        return datetime.utcnow() - timedelta(days=30)
    return None


def _canvas_item_scores(row: CanvasAnalysisResult) -> dict[str, float]:
    error_count = (row.stroke_order_result or {}).get("error_count", 0)
    stroke = max(0.0, 100.0 - error_count * settings.canvas_stroke_order_penalty)
    spacing = max(0.0, 100.0 - min(
        abs(row.spacing_deviation or 0.0) * settings.canvas_spacing_penalty_coeff,
        settings.canvas_spacing_penalty_max,
    ))
    size = max(0.0, 100.0 - min(
        abs(row.size_deviation or 0.0) * settings.canvas_size_penalty_coeff,
        settings.canvas_size_penalty_max,
    ))
    return {"획순": stroke, "자간": spacing, "크기": size}


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
    i_sessions = [
        {
            "overall": row.overall_score or 0,
            "date": row.created_at.date(),
            "items": {
                "크기 균일성": row.size_uniformity_score or 0,
                "기울기 일관성": row.slant_consistency_score or 0,
                "줄 정렬": row.line_alignment_score or 0,
            },
        }
        for row in image_rows
    ]

    total_canvas = len(c_sessions)
    total_image = len(i_sessions)

    if total_canvas + total_image == 0:
        return _empty_dashboard()

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
    }


def _empty_dashboard() -> dict:
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
    }
