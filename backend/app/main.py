from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import (
    accounts,
    ai,
    alerts,
    analytics,
    chat,
    dashboard,
    health,
    imports,
    matching,
    proxies,
    searches,
    seller,
    ws,
)
from app.config import get_settings
from app.db.session import dispose_engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="avito-toolkit",
        version=__version__,
        description="Avito market analytics and mass listing management",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health.router)
    application.include_router(searches.router, prefix="/api/v1")
    application.include_router(analytics.router, prefix="/api/v1")
    application.include_router(matching.router, prefix="/api/v1")
    application.include_router(imports.router, prefix="/api/v1")
    application.include_router(ws.router, prefix="/api/v1")
    application.include_router(chat.router, prefix="/api/v1")
    application.include_router(alerts.router, prefix="/api/v1")
    application.include_router(ai.router, prefix="/api/v1")
    application.include_router(dashboard.router, prefix="/api/v1")
    application.include_router(proxies.router, prefix="/api/v1")
    application.include_router(accounts.router, prefix="/api/v1")
    application.include_router(seller.router, prefix="/api/v1")
    application.state.environment = settings.environment
    return application


app = create_app()
