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
from ai.analysis.handwriting_analyzer import CHAR_SLANT_NORM_DEG
from app.schemas.image import (
    ImagePreprocessResponse,
    ImageDetectResponse,
    DetectedChar,
    BoundingBox,
    ImageAnalysisResponse,
    ImageCharAnalysis,
    ImageCharBox,
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


# 표시용 컬러본은 사진이라 PNG로 담으면 수 MB가 된다(실측: 폰 사진 최대 1.2MB+).
# 화면에 띄우는 용도이므로 JPEG로 압축하고, 장축을 이 값으로 줄여 보낸다.
# 종횡비를 유지하면 배율이 상쇄되어 **탐지 박스 좌표는 그대로 맞는다**
# (프론트가 이미지 크기에 맞춰 비율로 그리기 때문 — DEVLOG 12막 문답).
_DISPLAY_MAX_SIDE = 1280
_DISPLAY_JPEG_QUALITY = 82


def _encode_display_jpeg_base64(display_image: np.ndarray) -> str:
    """사용자에게 보여줄 배경(원본 컬러에 회전·리사이즈만 적용된 것)을 JPEG로."""
    h, w = display_image.shape[:2]
    long_side = max(h, w)
    if long_side > _DISPLAY_MAX_SIDE:
        scale = _DISPLAY_MAX_SIDE / long_side
        display_image = cv2.resize(
            display_image,
            (max(1, round(w * scale)), max(1, round(h * scale))),
            interpolation=cv2.INTER_AREA,
        )
    ok, buf = cv2.imencode(
        ".jpg", display_image, [int(cv2.IMWRITE_JPEG_QUALITY), _DISPLAY_JPEG_QUALITY]
    )
    if not ok:
        raise RuntimeError("표시용 이미지를 JPEG로 인코딩하지 못했습니다.")
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
        # 사용자에게 보여줄 배경 — 이진화 전, 회전·리사이즈만 적용된 원본 컬러.
        # 프론트는 이쪽을 쓰고, 위 이진본은 개발·디버그용으로 남긴다(팀 결정 2026-08-16).
        display_image_base64=_encode_display_jpeg_base64(pre["display_image"]),
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

    # 초록/빨강 박스 (2026-09-01) — 판정은 AI가 항목별로 끝내서 ok/failed_items로
    # 내려주고, 여기서는 탐지 좌표만 붙인다. 좌표계는 **전처리 후** 이미지 기준이라
    # 앱은 반드시 전처리 이미지 위에 그려야 한다(원본 사진 위에 그리면 다 어긋난다).
    _boxes_by_id = {c["char_id"]: c["bounding_box"] for c in detected_chars}
    char_boxes = [
        ImageCharBox(
            char_id=c["char_id"],
            box=BoundingBox(**_boxes_by_id[c["char_id"]]),
            ok=c["ok"],
            failed_items=c["failed_items"],
        )
        for c in ana["chars"] if c["char_id"] in _boxes_by_id
    ]

    result_row = ImageAnalysisResult(
        session_id=image_session_id,
        user_id=current_user.id,
        size_uniformity_score=size_uniformity_score,
        avg_slant_angle=avg_slant_angle,
        # mean_char_slant는 DB에 컬럼이 없어 저장하지 않는다 — 점수가 아니라 문구용
        # 값이라 소급 집계 대상이 아니다. 필요해지면 마이그레이션과 함께 추가할 것.
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
        "mean_char_slant": ana.get("mean_char_slant"),
        "slant_consistency_score": slant_consistency_score,
        "line_alignment_score": line_alignment_score,
        "overall_score": overall_score,
        "overall_tilt": ana["overall_tilt"],
        "total_grade": ana["total_grade"],
        "clarity_warnings": ana["clarity_warnings"],
        "char_analyses": [c.model_dump() for c in char_analyses],
        "char_boxes": [b.model_dump() for b in char_boxes],
        "spacing_uniformity_score": spacing_uniformity_score,
        "line_spacing_uniformity_score": line_spacing_uniformity_score,
    }
    await set_session(image_session_id, session_data)

    return ImageAnalysisResponse(
        image_session_id=image_session_id,
        size_uniformity_score=size_uniformity_score,
        avg_slant_angle=avg_slant_angle,
        mean_char_slant=ana.get("mean_char_slant"),
        slant_consistency_score=slant_consistency_score,
        line_alignment_score=line_alignment_score,
        overall_score=overall_score,
        char_analyses=char_analyses,
        char_boxes=char_boxes,
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

    # ── 항목별 문구: **5개 항목 모두 한 문장씩** (사용자 결정 2026-09-01) ──
    #
    # 종전에는 60점 미만이면 지적, 85점 이상이면 칭찬이라 **60~84점 구간은 아무 문구도
    # 안 나갔다** — 정작 개선이 필요한 구간인데 화면이 비었다. 또 자간·행간은 점수를
    # 재서 대시보드에 쌓으면서도 문구가 아예 없어, 왜 감점됐는지 알 수 없었다.
    # 이제 기준은 80점 하나다(= _band_score의 '우수' 경계라 등급과도 정합).
    #
    # 수치는 넣지 않는다. "높이 CV 24.3%"는 사용자에게 아무 뜻이 없다(사용자 결정).
    feedback_items = []

    def _item(score: int | None, warn: str, praise: str) -> None:
        """측정 불가(None)면 문구를 만들지 않는다 — 안 잰 지표로 지적도 칭찬도 하지
        않기 위함(DATA_FLOW §4-1). 그래서 문구가 6개보다 적을 수는 있다."""
        if score is None:
            return
        good = score >= 80
        feedback_items.append(ImageFeedbackItem(
            target_id="global",
            feedback_message=praise if good else warn,
            severity="good" if good else "warning"))

    _item(results["size_uniformity_score"],
          "글자 크기가 고르지 않습니다. 일정한 크기로 써보세요.",
          "글자 크기가 고르게 유지되고 있습니다.")
    # 기울기는 **두 가지**를 한 문장에 담는다(사용자 요청 2026-09-02).
    #   ① 글자들끼리 고른가 (= 점수, slant_consistency_score)
    #   ② 그 기울기 자체가 수직에서 너무 벗어났나 (= mean_char_slant, 점수 미반영)
    # ②가 없으면 **전부 똑같이 많이 기울여 쓴 글씨가 만점**으로 나간다 — 고르기는
    # 고르니까. 그건 "바르게 쓴 글씨"가 아니다. 다만 글자 하나의 잘못이 아니라
    # 글씨체 전체의 습관이므로 **박스는 치지 않는다**(사용자 결정).
    _slant = results.get("mean_char_slant")
    _too_slanted = _slant is not None and abs(_slant) > CHAR_SLANT_NORM_DEG
    _tilt_score = results["slant_consistency_score"]
    if _tilt_score is not None:
        _dir = "오른쪽" if (_slant or 0) > 0 else "왼쪽"
        _even = _tilt_score >= 80
        if _too_slanted and _even:
            _msg = f"글자 기울기는 고르지만, 전체적으로 {_dir}으로 많이 기울어 있습니다. 조금 더 세워서 써보세요."
        elif _too_slanted:
            _msg = f"글자마다 기울기가 제각각이고, 전체적으로도 {_dir}으로 많이 기울어 있습니다. 세워서 써보세요."
        elif _even:
            _msg = "글자 기울기가 고르게 유지되고 있습니다."
        else:
            _msg = "글자마다 기울기가 제각각입니다. 같은 기울기로 써보세요."
        # ⚠️ 고르기만 하면 칭찬(good)으로 나가면 안 된다 — 전부 똑같이 많이 기울여
        # 쓴 글씨가 초록으로 칭찬받게 된다. 둘 중 하나라도 걸리면 경고다.
        feedback_items.append(ImageFeedbackItem(
            target_id="global",
            feedback_message=_msg,
            severity="good" if (_even and not _too_slanted) else "warning"))

    # 줄 정렬만 방향을 함께 알려준다 — 줄이 어느 쪽으로 기울었는지는 사용자가
    # 바로 고칠 수 있는 정보다. overall_tilt는 글줄 회귀선의 방향이다
    # ("falling" = 오른쪽으로 내려감, "rising" = 오른쪽으로 올라감).
    _tilt = results.get("overall_tilt")
    # ⚠️ 글은 왼쪽에서 오른쪽으로 나아가므로 **올라가든 내려가든 방향은 '오른쪽'**이다.
    # 종전에 rising을 "왼쪽으로 기울어 올라갑니다"라고 썼는데, 같은 값을 점수 카드는
    # "오른쪽으로 올라가요"로 표시해 **한 화면에서 좌우가 반대로** 보였다
    # (2026-09-02 사용자 지적). 문구는 점수 카드 쪽 표현에 맞춘다.
    if _tilt == "falling":
        _line_warn = "글줄이 오른쪽으로 내려갑니다. 수평을 맞춰 써보세요."
    elif _tilt == "rising":
        _line_warn = "글줄이 오른쪽으로 올라갑니다. 수평을 맞춰 써보세요."
    else:
        _line_warn = "글자들이 줄에서 벗어나 있습니다. 줄을 맞춰 써보세요."
    _item(results["line_alignment_score"],
          _line_warn,
          "글자들이 줄에 잘 맞춰져 있습니다.")

    _item(results.get("spacing_uniformity_score"),
          "글자 사이 간격이 고르지 않습니다. 일정하게 띄워 보세요.",
          "글자 사이 간격이 고르게 유지되고 있습니다.")
    _item(results.get("line_spacing_uniformity_score"),
          "줄 간격이 고르지 않습니다. 일정하게 띄워 보세요.",
          "줄 간격이 고르게 유지되고 있습니다.")

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
