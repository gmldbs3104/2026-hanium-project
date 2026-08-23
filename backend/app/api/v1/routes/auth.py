from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime

from app.db.session import get_db
from app.core.deps import get_current_user
from app.core.firebase import verify_firebase_token, create_custom_token, delete_firebase_user
from app.core.kakao import fetch_kakao_profile, KakaoAuthError
from app.models.user import User
from app.models.correction import CanvasAnalysisResult, ImageAnalysisResult
from app.schemas.user import LoginRequest, UserOut, KakaoLoginRequest, CustomTokenOut
from app.services.s3_service import delete_handwriting_images

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=UserOut)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        decoded = verify_firebase_token(payload.id_token)
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

    firebase_uid = decoded["uid"]
    email = decoded.get("email")

    result = await db.execute(select(User).where(User.firebase_uid == firebase_uid))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            firebase_uid=firebase_uid,
            email=email,
            name=decoded.get("name"),
            profile_image_url=decoded.get("picture"),
            provider=payload.provider,
        )
        db.add(user)
    else:
        user.last_login_at = datetime.utcnow()

    await db.commit()
    await db.refresh(user)
    return user


@router.post("/kakao/custom-token", response_model=CustomTokenOut)
async def kakao_custom_token(payload: KakaoLoginRequest):
    """카카오 access_token을 검증하고 Firebase 커스텀 토큰을 발급한다.

    Firebase는 카카오를 기본 지원하지 않으므로 한 단계를 더 둔다.
      앱(카카오 SDK 로그인) → access_token → 이 엔드포인트 → Firebase 커스텀 토큰
      → 앱: signInWithCustomToken() → getIdToken() → 기존 POST /auth/login 재사용.
    이렇게 하면 이후의 토큰 검증·유저 upsert·Bearer 인증 로직은 그대로 쓸 수 있다.
    """
    try:
        profile = await fetch_kakao_profile(payload.access_token)
    except KakaoAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception:
        raise HTTPException(status_code=502, detail="카카오 인증 서버 통신에 실패했습니다.")

    uid = f"kakao:{profile['id']}"
    # 카카오는 이메일 동의를 못 받으면 email이 없다(비즈니스 앱 + 사용자 동의 필요).
    # users.email이 NOT NULL·UNIQUE라, 없을 때는 카카오 id 기반 안정적인 대체값을 만든다.
    email = profile["email"] or f"kakao_{profile['id']}@kakao.user"

    custom_token = create_custom_token(uid, {
        "email": email,
        "name": profile["nickname"],
        "picture": profile["profile_image"],
        "provider": "kakao",
    })
    return CustomTokenOut(custom_token=custom_token)


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """계정과 관련 데이터를 영구 삭제한다(REQ-009-7, 회원탈퇴).

    삭제 대상: 학습 기록(캔버스/이미지 분석 결과), S3에 업로드된 원본 이미지,
    Firebase 사용자, PostgreSQL 사용자 레코드.

    users.id를 참조하는 FK에 ON DELETE CASCADE가 없어 자식 레코드를 먼저 지운다.
    S3·Firebase 삭제는 실패해도 계정 삭제를 막지 않도록 각 헬퍼가 내부에서 흡수한다.
    """
    user_id = current_user.id
    firebase_uid = current_user.firebase_uid

    # 1) 이 유저의 이미지 세션에 업로드된 S3 원본 이미지 삭제.
    image_sessions = await db.execute(
        select(ImageAnalysisResult.session_id)
        .where(ImageAnalysisResult.user_id == user_id)
        .distinct()
    )
    for (session_id,) in image_sessions.all():
        await delete_handwriting_images(session_id)

    # 2) 학습 기록(자식 레코드) 삭제.
    await db.execute(
        delete(CanvasAnalysisResult).where(CanvasAnalysisResult.user_id == user_id)
    )
    await db.execute(
        delete(ImageAnalysisResult).where(ImageAnalysisResult.user_id == user_id)
    )

    # 3) 사용자 레코드 삭제 후 커밋.
    await db.delete(current_user)
    await db.commit()

    # 4) Firebase 사용자 삭제(DB 커밋 이후 — 존재하지 않아도 조용히 통과).
    delete_firebase_user(firebase_uid)