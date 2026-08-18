from fastapi import FastAPI

from app.api.routes import health, thoughts
from app.api.routes import settings as settings_routes
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
    )
    app.include_router(health.router)
    app.include_router(settings_routes.router)
    app.include_router(thoughts.router)
    return app


app = create_app()
