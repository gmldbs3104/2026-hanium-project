from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.v1.routes import auth, handwriting, dashboard, image
from app.services.session_cache import close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_redis()


app = FastAPI(title="AI 손글씨 교정 플랫폼 API", lifespan=lifespan)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(handwriting.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(image.router, prefix="/api/v1")

@app.get("/health")
def health_check():
    return {"status": "ok"}