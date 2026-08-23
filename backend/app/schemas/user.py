from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class UserOut(BaseModel):
    id: UUID
    email: str
    name: str | None
    profile_image_url: str | None
    provider: str
    last_login_at: datetime

    class Config:
        from_attributes = True

class LoginRequest(BaseModel):
    provider: str   # "google" | "kakao"
    id_token: str   # Firebase에서 발급받은 ID Token


class KakaoLoginRequest(BaseModel):
    access_token: str   # 카카오 SDK 로그인으로 받은 access token


class CustomTokenOut(BaseModel):
    custom_token: str   # 앱이 signInWithCustomToken()에 넘길 Firebase 커스텀 토큰