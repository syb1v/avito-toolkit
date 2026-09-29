from fastapi import APIRouter

from app import __version__
from app.config import get_settings

router = APIRouter(tags=["system"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "environment": settings.environment,
    }
