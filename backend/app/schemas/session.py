from pydantic import BaseModel
from datetime import datetime


class SessionSaveResult(BaseModel):
    session_id: str
    saved_at: datetime
    mode: str
    firestore_synced: bool = False
    s3_uploaded: bool = False
