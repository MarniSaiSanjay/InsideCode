from dataclasses import asdict
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import Settings, load_settings
from .storage import fts5_available

LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


def _hostname(value: str) -> str:
    return (urlsplit(f"//{value}").hostname or "").lower()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="Brahmaniss")

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        # Host blocks DNS rebinding; Origin blocks requests from unrelated websites.
        host_ok = _hostname(request.headers.get("host", "")) in LOCAL_HOSTS
        origin = request.headers.get("origin")
        origin_ok = origin is None or urlsplit(origin).hostname in LOCAL_HOSTS
        if not (host_ok and origin_ok):
            return JSONResponse({"detail": "Local access only"}, status_code=403)
        return await call_next(request)

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "fts5": fts5_available(),
            "ai_configured": settings.ai_configured,
            "limits": asdict(settings.limits),
        }

    return app
