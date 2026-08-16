import base64

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from uuid import uuid4
from datetime import datetime
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.correction import ImageAnalysisResult
from app.services.session_cache import get_session, set_session, delete_pattern
from app.services.s3_service import upload_handwriting_image
from app.services.ai_adapters import (
    preprocess_image_full,
    craft_detect_chars,
    analyze_size_angle,
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
from app.schemas.session import SessionSaveResult

router = APIRouter(prefix="/image", tags=["image"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


class ImageConfirmRequest(BaseModel):
    save_image: bool = False


def _encode_png_base64(binary_image: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", binary_image)
    if not ok:
        raise RuntimeError("전처리 이미지를 PNG로 인코딩하지 못했습니다.")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _metric_score(metric: dict | None) -> int | None:
    """analyze_size_angle()의 metrics[...] 항목에서 점수를 뽑는다.
    측정 불가(글자/행 수 부족)면 {"skipped": 사유}라 "score" 키가 없다."""
    if not metric or "score" not in metric:
        return None
    return round(metric["score"])


@router.post("/preprocess", response_model=ImagePreprocessResponse)
async def preprocess(file: UploadFile = File(...)):
    """
    SFR-003I: 카메라 이미지 입력 및 AI 전처리(이진화+deskew+리사이즈).

    ⚠️ 이후 /detect(CRAFT)는 이 전처리 출력을 전제로 정확도가 검증되어 있다
    (ai/BACKEND_INTEGRATION.md §5-1) — 다른 이진화 방식과 섞지 않는다.
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="JPG, PNG, WEBP 형식만 지원합니다.")

    image_bytes = await file.read()
    try:
        pre = preprocess_image_full(image_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    image_session_id = str(uuid4())
    binary_image = pre["binary_image"]

    # S3 업로드 (미설정 시 None 반환 — 서비스 계속 동작). 원본 촬영 이미지를 그대로 보관.
    s3_url = await upload_handwriting_image(image_bytes, image_session_id, file.content_type)

    # numpy 배열은 tolist()로 직렬화해서 캐시 저장 (전처리 후 이미지 — 이후 좌표계 기준)
    await set_session(image_session_id, {
        "binary_image": binary_image.tolist(),
        "width": pre["width"],
        "height": pre["height"],
        "s3_image_url": s3_url,
    })

    return ImagePreprocessResponse(
        image_session_id=image_session_id,
        width=pre["width"],
        height=pre["height"],
        s3_image_url=s3_url,
        quality_score=round(pre["quality_score"]["total"]),
        retake_required=pre["retake_required"],
        preprocessed_image_base64=_encode_png_base64(binary_image),
        preservation_mode="gentle_stretch" in pre["applied_filters"],
    )


@router.post("/{image_session_id}/detect", response_model=ImageDetectResponse)
async def detect(image_session_id: str):
    """
    SFR-004I: 문자 영역 Bounding Box 탐지 (CRAFT, ai/detection/craft_detector.py).
    """
    session_data = await get_session(image_session_id)
    if session_data is None:
        raise HTTPException(status_code=404, detail="유효하지 않거나 만료된 session_id 입니다.")

    detected = craft_detect_chars(
        session_data["binary_image"], session_data["width"], session_data["height"]
    )

    # analyze()가 angle/confidence 등 전체 필드를 그대로 참조하므로 원본 그대로 캐시
    session_data["detected_chars"] = detected
    await set_session(image_session_id, session_data)

    return ImageDetectResponse(
        image_session_id=image_session_id,
        detected_chars=[
            DetectedChar(
                char_id=c["char_id"],
                bounding_box=BoundingBox(**c["bounding_box"]),
                angle=c.get("angle"),
                angle_reliable=c.get("angle_reliable"),
                confidence=c.get("confidence"),
            )
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
    SFR-005I: 크기 균일성 / 기울기 / 줄 정렬 분석 후 DB 저장 (ai/analysis/handwriting_analyzer.py).
    """
    session_data = await get_session(image_session_id)
    if session_data is None:
        raise HTTPException(status_code=404, detail="유효하지 않거나 만료된 session_id 입니다.")

    detected_chars = session_data.get("detected_chars")
    if detected_chars is None:
        raise HTTPException(status_code=400, detail="먼저 /detect 엔드포인트를 호출해야 합니다.")

    # 글자가 하나도 없으면 채점 자체가 성립하지 않는다. 종전에는 그대로 통과시켜
    # 종합 점수 100점·등급 "우수"가 나갔다 — 빈 종이를 찍어도 "완벽합니다"였다.
    # 안 잰 것으로 칭찬하지 않는다는 §4-1과 같은 원칙이라 여기서 막는다(DATA_FLOW §4-1).
    if len(detected_chars) == 0:
        raise HTTPException(
            status_code=400,
            detail="사진에서 글자를 찾지 못했습니다. 글씨가 잘 보이게 다시 촬영해 주세요.")

    binary_image = np.array(session_data["binary_image"], dtype=np.uint8)
    ana = analyze_size_angle(detected_chars, binary_image)

    # DB의 점수 컬럼은 Integer라 반올림해서 저장. 측정 불가면 None을 그대로 흘린다 —
    # 만점(예전 동작)도 0점도 아니다. 안 잰 지표로 칭찬하거나 혹평하지 않기 위함(DATA_FLOW §4-1).
    # 5지표를 모두 metrics에서 같은 방식으로 읽는다 ({"score":...} | {"skipped": 사유}).
    m = ana["metrics"]
    size_uniformity_score = _metric_score(m.get("height_uniformity"))
    slant_consistency_score = _metric_score(m.get("tilt_consistency"))
    line_alignment_score = _metric_score(m.get("baseline_deviation"))
    spacing_uniformity_score = _metric_score(m.get("spacing_uniformity"))
    line_spacing_uniformity_score = _metric_score(m.get("line_spacing_uniformity"))
    overall_score = round(ana["total_score"])   # 측정된 지표만으로 가중 평균한 값
    avg_slant_angle = ana["mean_angle"]

    char_analyses = [
        ImageCharAnalysis(
            char_id=c["char_id"],
            # size_ratio(1.0=정상)를 기존 계약의 "편차(%)" 의미로 변환
            size_deviation=round((c["size_ratio"] - 1.0) * 100, 1),
            slant_angle=c["angle"],
        )
        for c in ana["chars"]
    ]

    result_row = ImageAnalysisResult(
        session_id=image_session_id,
        user_id=current_user.id,
        size_uniformity_score=size_uniformity_score,
        avg_slant_angle=avg_slant_angle,
        slant_consistency_score=slant_consistency_score,
        line_alignment_score=line_alignment_score,
        # 5지표를 다 쌓는다 — 종전엔 3개만 저장돼 대시보드에 자간·행간이 안 올라왔다(§5-8)
        spacing_uniformity_score=spacing_uniformity_score,
        line_spacing_uniformity_score=line_spacing_uniformity_score,
        char_level=[c.model_dump() for c in char_analyses],
        overall_score=overall_score,
        s3_image_url=session_data.get("s3_image_url"),  # preprocess에서 업로드된 URL
    )
    db.add(result_row)
    await db.commit()

    # 새 분석 결과가 저장됐으므로 이 유저의 대시보드 캐시(SFR-008)는 더 이상 최신이 아니다
    await delete_pattern(f"dashboard:{current_user.id}:*")

    session_data["analysis_results"] = {
        "size_uniformity_score": size_uniformity_score,
        "avg_slant_angle": avg_slant_angle,
        "slant_consistency_score": slant_consistency_score,
        "line_alignment_score": line_alignment_score,
        "overall_score": overall_score,
        "overall_tilt": ana["overall_tilt"],
        "total_grade": ana["total_grade"],
        "clarity_warnings": ana["clarity_warnings"],
        "char_analyses": [c.model_dump() for c in char_analyses],
        "spacing_uniformity_score": spacing_uniformity_score,
        "line_spacing_uniformity_score": line_spacing_uniformity_score,
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
        overall_tilt=ana["overall_tilt"],
        total_grade=ana["total_grade"],
        clarity_warnings=ana["clarity_warnings"],
        spacing_uniformity_score=spacing_uniformity_score,
        line_spacing_uniformity_score=line_spacing_uniformity_score,
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

    def _score_feedback(score: int | None, warn: str, praise: str) -> None:
        """점수 구간별 문구. 측정 불가(None)면 아무 문구도 만들지 않는다 —
        안 잰 지표로 지적하거나 칭찬하지 않기 위함(DATA_FLOW §4-1)."""
        if score is None:
            return
        if score < 60:
            feedback_items.append(ImageFeedbackItem(
                target_id="global", feedback_message=warn, severity="warning"))
        elif score >= 85:
            feedback_items.append(ImageFeedbackItem(
                target_id="global", feedback_message=praise, severity="good"))

    _score_feedback(
        results["size_uniformity_score"],
        "글자 크기가 고르지 않습니다. 일정한 크기로 써보세요.",
        "글자 크기가 균일합니다!")
    _score_feedback(
        results["slant_consistency_score"],
        "글자 기울기가 일정하지 않습니다. 일관된 방향으로 써보세요.",
        "글자 기울기가 일정합니다!")
    _score_feedback(
        results["line_alignment_score"],
        "글자들이 수평선에 맞지 않습니다. 줄을 맞춰 써보세요.",
        "줄 정렬이 잘 되어 있습니다!")

    # 명료도 경고 — 점수엔 반영하지 않고 경고 문구로만 안내 (팀 결정, ai/BACKEND_INTEGRATION.md §1.1)
    for warning in results.get("clarity_warnings") or []:
        feedback_items.append(ImageFeedbackItem(
            target_id="global",
            feedback_message=warning,
            severity="warning",
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


@router.post("/{image_session_id}/confirm", response_model=SessionSaveResult)
async def confirm_image_session(image_session_id: str, payload: ImageConfirmRequest):
    """
    SFR-009: 학습 결과 저장 확인 (원본 이미지 저장 동의 여부 포함).
    S3 업로드 자체는 /preprocess 시점에 이미 끝나 있다. save_image=false일 때
    실제로 업로드된 원본을 삭제하는 정책은 아직 미구현 (TODO).
    """
    session_data = await get_session(image_session_id)
    if session_data is None or session_data.get("analysis_results") is None:
        raise HTTPException(status_code=400, detail="먼저 /analyze 엔드포인트를 호출해야 합니다.")

    return SessionSaveResult(
        session_id=image_session_id,
        saved_at=datetime.utcnow(),
        mode="image",
        firestore_synced=False,
        s3_uploaded=payload.save_image,
    )
