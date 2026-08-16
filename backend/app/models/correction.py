from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, JSON, Uuid
from datetime import datetime
import uuid
from app.db.base import Base

class CanvasAnalysisResult(Base):
    __tablename__ = "canvas_analysis_results"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String, nullable=False, index=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    char_id = Column(String, nullable=False)
    stroke_order_result = Column(JSON, nullable=True)
    spacing_deviation = Column(Float, nullable=True)
    size_deviation = Column(Float, nullable=True)
    overall_score = Column(Integer, nullable=True)
    # AI가 내주지만 응답에만 실리고 사라지던 값들 (DATA_FLOW.md §8-B·C, 2026-08-12 추가).
    # 소급이 안 되는 값이라 화면 노출 여부와 무관하게 먼저 쌓기 시작한다.
    speed_profile = Column(JSON, nullable=True)      # {mean_speed_px_per_ms: ...}
    correction_flags = Column(JSON, nullable=True)   # ["size_large", "spacing_too_narrow", ...]
    # 필압(pressure_profile)은 일부러 안 넣었다 — 프론트가 1.0을 하드코딩해서 보내
    # 전부 같은 값이다. 진짜 값을 읽게 고친 뒤에 컬럼을 만든다.
    created_at = Column(DateTime, default=datetime.utcnow)


class ImageAnalysisResult(Base):
    __tablename__ = "image_analysis_results"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String, nullable=False, index=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    # 점수 컬럼은 전부 nullable — 측정 불가면 None이다(만점도 0점도 아님, §4-1).
    size_uniformity_score = Column(Integer, nullable=True)
    avg_slant_angle = Column(Float, nullable=True)
    slant_consistency_score = Column(Integer, nullable=True)
    line_alignment_score = Column(Integer, nullable=True)
    # AI는 5지표를 채점하는데 DB엔 3개뿐이라 대시보드에 자간·행간이 안 쌓였다
    # (DATA_FLOW.md §5-8, 2026-08-12 추가).
    spacing_uniformity_score = Column(Integer, nullable=True)
    line_spacing_uniformity_score = Column(Integer, nullable=True)
    char_level = Column(JSON, nullable=True)
    overall_score = Column(Integer, nullable=True)
    s3_image_url = Column(String, nullable=True)  # S3 원본 이미지 URL (SFR-009)
    created_at = Column(DateTime, default=datetime.utcnow)