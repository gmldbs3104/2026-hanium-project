from sqlalchemy import Column, String, Integer, Float
from app.db.base import Base


class FontStandard(Base):
    __tablename__ = "font_standards"

    char = Column(String, primary_key=True)
    font_id = Column(String, primary_key=True, default="myeongjo")  # 서체 ID (명조, 고딕 등)
    standard_height = Column(Integer, nullable=False, default=100)   # 정규화 기준 높이(px)
    standard_width = Column(Integer, nullable=False)                  # 정규화 기준 너비(px)
    aspect_ratio = Column(Float, nullable=False)                      # width / height 비율
