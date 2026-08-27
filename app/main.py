from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import ask, health, thoughts
from app.api.routes import settings as settings_routes
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Total-Count",
            "X-Page",
            "X-Page-Size",
            "X-Total-Pages",
        ],
    )
    app.include_router(health.router)
    app.include_router(ask.router)
    app.include_router(settings_routes.router)
    app.include_router(thoughts.router)
    return app


app = create_app()
