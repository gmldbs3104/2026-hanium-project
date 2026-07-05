from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard_service import get_dashboard_data, DASHBOARD_CACHE_TTL
from app.services.session_cache import get_session, set_session

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse, summary="학습 관리 대시보드 조회 (SFR-008)")
async def get_dashboard(
    period: Literal["week", "month", "all"] = Query("month", description="집계 기간"),
    mode: Literal["canvas", "image", "all"] = Query("all", description="분석 모드 필터"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    SFR-008: 사용자의 학습 현황 대시보드 집계 결과를 반환합니다.

    - **period**: 집계 기간 (week=7일 / month=30일 / all=전체)
    - **mode**: 분석 모드 필터 (canvas / image / all)
    - 집계 결과는 Redis에 1시간 캐싱됩니다. (SFR-008-캐시)
    - 데이터가 없는 신규 사용자는 `is_new_user: true` 반환 (REQ-008-5)
    """
    cache_key = f"dashboard:{current_user.id}:{period}:{mode}"
    cached = await get_session(cache_key)
    if cached is not None:
        return cached

    data = await get_dashboard_data(db, current_user.id, period, mode)
    await set_session(cache_key, data, ttl=DASHBOARD_CACHE_TTL)
    return data
