from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.routes import auth, handwriting, dashboard, image
from app.services.session_cache import get_redis, close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_redis().ping()
    yield
    await close_redis()


app = FastAPI(title="AI 손글씨 교정 플랫폼 API", lifespan=lifespan)

# Flutter web 개발 서버는 임의 포트를 사용하므로 정규식으로 localhost 오리진을 허용한다.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    # ⚠️ "*"는 CORS 스펙상 Authorization 헤더를 커버하지 않는다 — 명시적으로 나열해야 함
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(handwriting.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(image.router, prefix="/api/v1")

@app.get("/health")
def health_check():
    return {"status": "ok"}