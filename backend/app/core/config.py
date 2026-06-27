from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    app_name: str = "AI Handwriting Correction API"
    debug: bool = False

    database_url: str

    firebase_credentials_path: str

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_s3_bucket_name: Optional[str] = None
    aws_region: str = "ap-northeast-2"

    # Settings 클래스 안에 추가
    redis_url: str = "redis://localhost:6379"

    stroke_distance_threshold: float = 50.0   # px 단위
    stroke_time_threshold_ms: int = 500       # ms 단위
    grouping_confidence_threshold: float = 0.5
    
    class Config:
        env_file = ".env"

settings = Settings()