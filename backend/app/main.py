from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.operations import router as operations_router
from app.api.routes import router
from app.config import settings

app = FastAPI(title="Development CRM Adapter", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:18000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(operations_router)


@app.get("/api/config")
def frontend_config() -> dict[str, str | int]:
    return {
        "n8n_webhook_url": settings.n8n_webhook_url,
        "n8n_booking_webhook_url": settings.n8n_booking_webhook_url,
        "n8n_request_timeout_ms": settings.n8n_request_timeout_ms,
        "business_timezone": settings.business_timezone,
    }


frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
