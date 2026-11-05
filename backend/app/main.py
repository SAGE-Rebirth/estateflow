from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.core.db import close_client, ensure_indexes, get_client
from app.core.logging import configure_logging
from app.services.storage import public_dir


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    await ensure_indexes()
    yield
    await close_client()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title=f"{s.app_name} API", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=s.api_prefix)
    # Only the public area (listing photos) is served statically; brochures and buyers'
    # WhatsApp media live in the private area behind authenticated endpoints.
    public_dir().mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=public_dir()), name="media")

    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict[str, str]:
        await get_client().admin.command("ping")
        return {"status": "ok"}

    return app


app = create_app()
