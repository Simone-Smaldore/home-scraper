from fastapi import FastAPI

from app.api.health import router as health_router

# Every route carries the /api prefix on purpose. On Vercel the rewrite
# /api/(.*) -> /api/index hands the function the *original* path, so the app
# must answer on /api/health both in production and behind the local Vite proxy.
app = FastAPI(
    title="Casa Radar API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

app.include_router(health_router)
