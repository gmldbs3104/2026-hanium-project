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
    created_at = Column(DateTime, default=datetime.utcnow)


class ImageAnalysisResult(Base):
    __tablename__ = "image_analysis_results"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String, nullable=False, index=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    size_uniformity_score = Column(Integer, nullable=True)
    avg_slant_angle = Column(Float, nullable=True)
    slant_consistency_score = Column(Integer, nullable=True)
    line_alignment_score = Column(Integer, nullable=True)
    char_level = Column(JSON, nullable=True)
    overall_score = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)