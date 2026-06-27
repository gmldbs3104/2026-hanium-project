from fastapi import FastAPI
from app.api.v1.routes import auth, handwriting, dashboard, image

app = FastAPI(title="AI 손글씨 교정 플랫폼 API")

app.include_router(auth.router, prefix="/api/v1")
app.include_router(handwriting.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(image.router, prefix="/api/v1")

@app.get("/health")
def health_check():
    return {"status": "ok"}