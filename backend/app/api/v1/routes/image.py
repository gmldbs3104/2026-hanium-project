from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.correction import ImageAnalysisResult
from app.services.session_cache import get_session, set_session
from app.services.s3_service import upload_handwriting_image
from app.services.image_preprocessing import preprocess_image, detect_char_bboxes
from app.services.image_analysis import (
    analyze_size_uniformity,
    analyze_slant,
    analyze_line_alignment,
    calculate_overall_score,
)
from app.schemas.image import (
    ImagePreprocessResponse,
    ImageDetectResponse,
    DetectedChar,
    BoundingBox,
    ImageAnalysisResponse,
    ImageCharAnalysis,
    ImageFeedbackResponse,
    ImageFeedbackItem,
)

router = APIRouter(prefix="/image", tags=["image"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.post("/preprocess", response_model=ImagePreprocessResponse)
async def preprocess(file: UploadFile = File(...)):
    """
    SFR-003I: 카메라 이미지 입력 및 OpenCV 전처리.
    이진화된 이미지 메타데이터를 캐시에 저장하고 image_session_id를 발급한다.
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="JPG, PNG, WEBP 형식만 지원합니다.")

    image_bytes = await file.read()
    try:
        binary_image, width, height = preprocess_image(image_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    image_session_id = str(uuid4())

    # S3 업로드 (미설정 시 None 반환 — 서비스 계속 동작)
    s3_url = await upload_handwriting_image(image_bytes, image_session_id, file.content_type)

    # numpy 배열은 tolist()로 직렬화해서 캐시 저장
    await set_session(image_session_id, {
        "binary_image": binary_image.tolist(),
        "width": width,
        "height": height,
        "s3_image_url": s3_url,
    })

    return ImagePreprocessResponse(
        image_session_id=image_session_id,
        width=width,
        height=height,
        s3_image_url=s3_url,
    )


@router.post("/{image_session_id}/detect", response_model=ImageDetectResponse)
async def detect(image_session_id: str):
    """
    SFR-004I: 문자 영역 Bounding Box 탐지.
    현재는 OpenCV contour 기반 placeholder — 추후 CRAFT 모델로 교체 예정.
    """
    session_data = await get_session(image_session_id)
    if session_data is None:
        raise HTTPException(status_code=404, detail="유효하지 않거나 만료된 session_id 입니다.")

    import numpy as np
    binary_image = np.array(session_data["binary_image"], dtype=np.uint8)
    detected = detect_char_bboxes(binary_image)

    session_data["detected_chars"] = detected
    await set_session(image_session_id, session_data)

    return ImageDetectResponse(
        image_session_id=image_session_id,
        detected_chars=[
            DetectedChar(char_id=c["char_id"], bounding_box=BoundingBox(**c["bounding_box"]))
            for c in detected
        ],
        total_detected=len(detected),
    )


@router.post("/{image_session_id}/analyze", response_model=ImageAnalysisResponse)
async def analyze(
    image_session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    SFR-005I: 크기 균일성 / 기울기 / 줄 정렬 분석 후 DB 저장.
    """
    session_data = await get_session(image_session_id)
    if session_data is None:
        raise HTTPException(status_code=404, detail="유효하지 않거나 만료된 session_id 입니다.")

    detected_chars = session_data.get("detected_chars")
    if detected_chars is None:
        raise HTTPException(status_code=400, detail="먼저 /detect 엔드포인트를 호출해야 합니다.")

    height = session_data.get("height", 1000)

    size_uniformity_score, char_size_analyses = analyze_size_uniformity(detected_chars)
    avg_slant_angle, slant_consistency_score = analyze_slant(detected_chars)
    line_alignment_score = analyze_line_alignment(detected_chars, height)
    overall_score = calculate_overall_score(
        size_uniformity_score, slant_consistency_score, line_alignment_score
    )

    char_analyses = [
        ImageCharAnalysis(
            char_id=c["char_id"],
            size_deviation=c["size_deviation"],
            slant_angle=avg_slant_angle,
        )
        for c in char_size_analyses
    ]

    result_row = ImageAnalysisResult(
        session_id=image_session_id,
        user_id=current_user.id,
        size_uniformity_score=size_uniformity_score,
        avg_slant_angle=avg_slant_angle,
        slant_consistency_score=slant_consistency_score,
        line_alignment_score=line_alignment_score,
        char_level=[c.model_dump() for c in char_analyses],
        overall_score=overall_score,
        s3_image_url=session_data.get("s3_image_url"),  # preprocess에서 업로드된 URL
    )
    db.add(result_row)
    await db.commit()

    session_data["analysis_results"] = {
        "size_uniformity_score": size_uniformity_score,
        "avg_slant_angle": avg_slant_angle,
        "slant_consistency_score": slant_consistency_score,
        "line_alignment_score": line_alignment_score,
        "overall_score": overall_score,
        "char_analyses": [c.model_dump() for c in char_analyses],
    }
    await set_session(image_session_id, session_data)

    return ImageAnalysisResponse(
        image_session_id=image_session_id,
        size_uniformity_score=size_uniformity_score,
        avg_slant_angle=avg_slant_angle,
        slant_consistency_score=slant_consistency_score,
        line_alignment_score=line_alignment_score,
        overall_score=overall_score,
        char_analyses=char_analyses,
        s3_image_url=session_data.get("s3_image_url"),
    )


@router.get("/{image_session_id}/feedback", response_model=ImageFeedbackResponse)
async def feedback(image_session_id: str):
    """
    SFR-007 (이미지 모드): 분석 결과 기반 한국어 피드백 생성.
    """
    session_data = await get_session(image_session_id)
    if session_data is None:
        raise HTTPException(status_code=404, detail="유효하지 않거나 만료된 session_id 입니다.")

    results = session_data.get("analysis_results")
    if results is None:
        raise HTTPException(status_code=400, detail="먼저 /analyze 엔드포인트를 호출해야 합니다.")

    feedback_items = []

    if results["size_uniformity_score"] < 60:
        feedback_items.append(ImageFeedbackItem(
            target_id="global",
            feedback_message="글자 크기가 고르지 않습니다. 일정한 크기로 써보세요.",
            severity="warning",
        ))
    elif results["size_uniformity_score"] >= 85:
        feedback_items.append(ImageFeedbackItem(
            target_id="global",
            feedback_message="글자 크기가 균일합니다!",
            severity="good",
        ))

    if results["slant_consistency_score"] < 60:
        feedback_items.append(ImageFeedbackItem(
            target_id="global",
            feedback_message="글자 기울기가 일정하지 않습니다. 일관된 방향으로 써보세요.",
            severity="warning",
        ))
    elif results["slant_consistency_score"] >= 85:
        feedback_items.append(ImageFeedbackItem(
            target_id="global",
            feedback_message="글자 기울기가 일정합니다!",
            severity="good",
        ))

    if results["line_alignment_score"] < 60:
        feedback_items.append(ImageFeedbackItem(
            target_id="global",
            feedback_message="글자들이 수평선에 맞지 않습니다. 줄을 맞춰 써보세요.",
            severity="warning",
        ))
    elif results["line_alignment_score"] >= 85:
        feedback_items.append(ImageFeedbackItem(
            target_id="global",
            feedback_message="줄 정렬이 잘 되어 있습니다!",
            severity="good",
        ))

    overall_score = results["overall_score"]
    if overall_score >= 90:
        achievement_message = "훌륭합니다! 매우 균일하고 단정한 손글씨입니다."
    elif overall_score >= 70:
        achievement_message = "잘 쓰고 있습니다. 조금만 더 다듬으면 완벽해질 거예요."
    elif overall_score >= 50:
        achievement_message = "계속 연습하면 나아질 거예요. 피드백을 참고해 보세요."
    else:
        achievement_message = "기초부터 차근차근 연습해 봅시다."

    return ImageFeedbackResponse(
        image_session_id=image_session_id,
        overall_score=overall_score,
        achievement_message=achievement_message,
        feedback_items=feedback_items,
    )
