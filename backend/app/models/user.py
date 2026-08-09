from sqlalchemy import Column, String, DateTime, Uuid
from datetime import datetime
import uuid
from app.db.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firebase_uid = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=True)
    profile_image_url = Column(String, nullable=True)
    provider = Column(String, nullable=False)  # google / kakao
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, default=datetime.utcnow)