from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from app.db.session import get_db
from app.core.firebase import verify_firebase_token
from app.models.user import User
from app.schemas.user import LoginRequest, UserOut

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