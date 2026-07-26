from fastapi import APIRouter, Depends, HTTPException
from uuid import uuid4
from datetime import datetime

from app.schemas.canvas import CanvasAnalyzeRequest, CanvasAnalyzeResponse
from app.services.session_cache import set_session

from fastapi import HTTPException
from app.schemas.canvas import CanvasGroupResponse
from app.services.session_cache import get_session, set_session, delete_pattern
from app.services.stroke_grouping import rule_based_grouping, build_char_groups

from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.correction import CanvasAnalysisResult
from app.schemas.canvas import CanvasAnalysisResponse, CanvasCharAnalysis
from app.services.canvas_analysis import (
    get_standard, analyze_stroke_order, analyze_spacing, analyze_size, calculate_overall_score,
)

from app.schemas.canvas import CanvasFeedbackResponse, FeedbackItem
from app.services.feedback_generator import generate_canvas_feedback
from app.schemas.session import SessionSaveResult

router = APIRouter(prefix="/canvas", tags=["canvas"])


@router.post("/analyze", response_model=CanvasAnalyzeResponse)
async def analyze_canvas(payload: CanvasAnalyzeRequest):
    """
    SFR-003C: 캔버스 손글씨 입력 및 획 수집
    클라이언트로부터 획 좌표 시퀀스를 받아 session_id를 발급하고
    SFR-004C(획 그룹핑)에 넘길 데이터를 캐시에 저장한다.
    """
    canvas_session_id = str(uuid4())

    await set_session(canvas_session_id, {
        "strokes": [stroke.model_dump() for stroke in payload.strokes],
        "metadata": payload.metadata.model_dump(),
    })

    return CanvasAnalyzeResponse(
        canvas_session_id=canvas_session_id,
        stroke_count=payload.metadata.stroke_count,
    )

@router.post("/{canvas_session_id}/group", response_model=CanvasGroupResponse)
async def group_canvas_strokes(canvas_session_id: str):
    """
    SFR-004C: 획 그룹핑 및 문자 단위 분할
    """
    session_data = await get_session(canvas_session_id)
    if session_data is None:
        raise HTTPException(status_code=404, detail="유효하지 않거나 만료된 session_id 입니다.")

    strokes = session_data["strokes"]
    stroke_groups = rule_based_grouping(strokes)
    char_groups = build_char_groups(stroke_groups)

    # SFR-005C에서 사용할 수 있도록 같은 세션에 결과 갱신 저장
    session_data["char_groups"] = char_groups
    await set_session(canvas_session_id, session_data)

    low_confidence_count = sum(1 for g in char_groups if g["low_confidence"])

    # stroke_grouping.py는 내부적으로 bounding_box를 {x,y,w,h}로 다루지만,
    # 응답 스키마(및 프론트 BoundingBox 모델)는 {x,y,width,height}를 기대한다.
    # 캐시에 저장된 char_groups(analyze-detail이 참조)는 원본 그대로 두고,
    # 응답용으로만 키를 변환한다.
    response_char_groups = [
        {
            **g,
            "bounding_box": {
                "x": g["bounding_box"]["x"],
                "y": g["bounding_box"]["y"],
                "width": g["bounding_box"]["w"],
                "height": g["bounding_box"]["h"],
            },
        }
        for g in char_groups
    ]

    return CanvasGroupResponse(
        canvas_session_id=canvas_session_id,
        char_groups=response_char_groups,
        low_confidence_count=low_confidence_count,
    )

@router.post("/{canvas_session_id}/analyze-detail", response_model=CanvasAnalysisResponse)
async def analyze_canvas_detail(
    canvas_session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    SFR-005C: 획순 / 자간 / 크기 분석
    """
    session_data = await get_session(canvas_session_id)
    if session_data is None:
        raise HTTPException(status_code=404, detail="유효하지 않거나 만료된 session_id 입니다.")

    char_groups = session_data.get("char_groups")
    if char_groups is None:
        raise HTTPException(status_code=400, detail="먼저 /group 엔드포인트를 호출해야 합니다.")

    results = []
    prev_box = None

    for group in char_groups:
        # TODO: 실제로는 인식된 문자(char)가 필요하지만, 지금은 문자 인식 단계가 없어
        # 표준값을 못 찾고 항상 DEFAULT_STANDARD를 사용하게 됨.
        standard = await get_standard(db, char=None)

        stroke_order_result = analyze_stroke_order(group, standard)
        spacing_deviation = analyze_spacing(prev_box, group["bounding_box"], standard["standard_spacing"])
        size_deviation = analyze_size(group["bounding_box"], standard["standard_height"], standard["standard_width"])
        overall_score = calculate_overall_score(
            stroke_order_result["error_count"], spacing_deviation, size_deviation
        )

        result_row = CanvasAnalysisResult(
            session_id=canvas_session_id,
            user_id=current_user.id,
            char_id=group["char_id"],
            stroke_order_result=stroke_order_result,
            spacing_deviation=spacing_deviation,
            size_deviation=size_deviation,
            overall_score=overall_score,
        )
        db.add(result_row)

        results.append(CanvasCharAnalysis(
            char_id=group["char_id"],
            stroke_order_result=stroke_order_result,
            spacing_deviation=spacing_deviation,
            size_deviation=size_deviation,
            overall_score=overall_score,
        ))

        prev_box = group["bounding_box"]

    await db.commit()

    # 새 분석 결과가 저장됐으므로 이 유저의 대시보드 캐시(SFR-008)는 더 이상 최신이 아니다
    await delete_pattern(f"dashboard:{current_user.id}:*")

    # SFR-007에서 재사용할 수 있도록 캐시에도 저장
    session_data["analysis_results"] = [r.model_dump() for r in results]
    await set_session(canvas_session_id, session_data)

    return CanvasAnalysisResponse(canvas_session_id=canvas_session_id, results=results)

@router.get("/{canvas_session_id}/feedback", response_model=CanvasFeedbackResponse)
async def get_canvas_feedback(canvas_session_id: str):
    """
    SFR-007: 교정 피드백 생성 및 UI 표시 (캔버스 모드)
    """
    session_data = await get_session(canvas_session_id)
    if session_data is None:
        raise HTTPException(status_code=404, detail="유효하지 않거나 만료된 session_id 입니다.")

    analysis_results = session_data.get("analysis_results")
    if analysis_results is None:
        raise HTTPException(status_code=400, detail="먼저 /analyze-detail 엔드포인트를 호출해야 합니다.")

    feedback = generate_canvas_feedback(analysis_results)

    return CanvasFeedbackResponse(
        canvas_session_id=canvas_session_id,
        overall_score=feedback["overall_score"],
        achievement_message=feedback["achievement_message"],
        feedback_items=[FeedbackItem(**item) for item in feedback["feedback_items"]],
    )

@router.post("/{canvas_session_id}/confirm", response_model=SessionSaveResult)
async def confirm_canvas_session(canvas_session_id: str):
    """
    SFR-009: 학습 결과 저장 확인.
    실제 DB 저장은 /analyze-detail 시점에 이미 끝나 있으므로, 여기서는
    해당 세션의 분석이 완료됐는지 확인하고 저장 확인 응답만 돌려준다.
    """
    session_data = await get_session(canvas_session_id)
    if session_data is None or session_data.get("analysis_results") is None:
        raise HTTPException(status_code=400, detail="먼저 /analyze-detail 엔드포인트를 호출해야 합니다.")

    return SessionSaveResult(
        session_id=canvas_session_id,
        saved_at=datetime.utcnow(),
        mode="canvas",
        firestore_synced=False,
        s3_uploaded=False,
    )