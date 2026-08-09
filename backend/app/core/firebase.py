import firebase_admin
from firebase_admin import credentials, auth
from app.core.config import settings

cred = credentials.Certificate(settings.firebase_credentials_path)
firebase_admin.initialize_app(cred)

def verify_firebase_token(id_token: str) -> dict:
    """ID Token을 검증하고 디코딩된 클레임을 반환"""
    return auth.verify_id_token(id_token)