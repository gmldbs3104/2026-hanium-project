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

    stroke_distance_threshold: float = 50.0
    stroke_time_threshold_ms: int = 500
    grouping_confidence_threshold: float = 0.5

    # 캔버스 모드 종합 점수 가중치 (REQ-005C-6)
    canvas_stroke_order_penalty: float = 10.0  # 획순 오류 1건당 감점
    canvas_spacing_penalty_coeff: float = 0.5  # 자간 편차 감점 계수
    canvas_spacing_penalty_max: float = 30.0   # 자간 최대 감점
    canvas_size_penalty_coeff: float = 0.5     # 크기 편차 감점 계수
    canvas_size_penalty_max: float = 30.0      # 크기 최대 감점

    # 이미지 모드 종합 점수 가중치 (REQ-005I-5) — 합계 = 1.0
    image_size_weight: float = 0.4    # 크기 균일성
    image_slant_weight: float = 0.35  # 기울기 일관성
    image_line_weight: float = 0.25   # 줄 정렬

    class Config:
        env_file = ".env"

settings = Settings()