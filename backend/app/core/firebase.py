import firebase_admin
from firebase_admin import credentials, auth
from app.core.config import settings

cred = credentials.Certificate(settings.firebase_credentials_path)
firebase_admin.initialize_app(cred)

def verify_firebase_token(id_token: str) -> dict:
    """ID Token을 검증하고 디코딩된 클레임을 반환"""
    return auth.verify_id_token(id_token)


def delete_firebase_user(uid: str) -> None:
    """Firebase 사용자를 삭제한다(계정 삭제, REQ-009-7).

    이미 삭제됐거나 존재하지 않는 uid면 조용히 넘어간다 — DB·S3 정리는 계속돼야
    하므로 여기서 예외로 전체 삭제를 막지 않는다.
    """
    try:
        auth.delete_user(uid)
    except auth.UserNotFoundError:
        pass


def create_custom_token(uid: str, claims: dict | None = None) -> str:
    """Firebase 커스텀 토큰을 발급한다.

    카카오처럼 Firebase가 기본 지원하지 않는 로그인 수단을 Firebase 계정에
    연결하기 위해 쓴다. 여기서 넣은 claims(email/name/picture 등)는 앱이
    signInWithCustomToken → getIdToken으로 받는 ID Token에 그대로 실린다.
    (iss·aud·sub·exp 등 예약 클레임은 넣을 수 없음.)
    """
    token = auth.create_custom_token(uid, claims or {})
    return token.decode("utf-8") if isinstance(token, bytes) else token