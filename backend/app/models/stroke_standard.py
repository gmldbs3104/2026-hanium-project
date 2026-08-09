from sqlalchemy import Column, String, Integer, JSON
from app.db.base import Base


class StrokeStandard(Base):
    __tablename__ = "stroke_standards"

    char = Column(String, primary_key=True)  # 예: "가"
    expected_sequence = Column(JSON, nullable=False)  # 표준 획순 시퀀스 (방향 벡터 등)
    standard_height = Column(Integer, default=100)  # 표준 문자 높이(px) 기준값
    standard_width = Column(Integer, default=100)
    standard_spacing = Column(Integer, default=20)  # 표준 자간(px)