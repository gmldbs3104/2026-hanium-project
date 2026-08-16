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

    # ⚠️ 채점 계수·가중치는 여기 두지 않는다 — 채점은 AI가 소유한다(DATA_FLOW.md §5-11·§8-G).
    #   · 캔버스(REQ-005C-6) → ai/canvas/canvas_quality_analyzer.py의 canvas_item_scores()
    #   · 이미지(REQ-005I-5) → ai/analysis/handwriting_analyzer.py의 WEIGHTS (3:3:3:2:2)
    # 2026-08-12에 여기 있던 8개(canvas_* 5 + image_*_weight 3)를 지웠다.
    # image_* 3개는 아무 데서도 읽히지 않는 죽은 설정이었고(백엔드가 자체 채점하던 시절의
    # 잔재), canvas_* 5개는 대시보드만 이 계수로 재계산해 결과 화면과 점수가 어긋났다.
    # 임계값을 조정할 일이 생기면 AI 쪽 상수를 고칠 것.

    class Config:
        env_file = ".env"

settings = Settings()