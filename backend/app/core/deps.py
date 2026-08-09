from fastapi import Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.core.firebase import verify_firebase_token
from app.models.user import User

async def get_current_user(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = authorization.replace("Bearer ", "")
    try:
        decoded = verify_firebase_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="인증 실패")

    result = await db.execute(select(User).where(User.firebase_uid == decoded["uid"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return user