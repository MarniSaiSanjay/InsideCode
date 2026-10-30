from dataclasses import asdict
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from .config import MIB, Settings, load_settings
from .indexing import ImportRejected
from .storage import StaleSnapshot, Store, fts5_available

LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


def _hostname(value: str) -> str:
    return (urlsplit(f"//{value}").hostname or "").lower()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    store = Store(settings.state_dir)
    app = FastAPI(title="Brahmaniss")

    @app.exception_handler(ImportRejected)
    def rejected(_: Request, exc: ImportRejected):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(StaleSnapshot)
    def stale(_: Request, __: StaleSnapshot):
        detail = "This result belongs to an older upload. Search again."
        return JSONResponse({"detail": detail}, status_code=409)

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        # Host blocks DNS rebinding; Origin blocks requests from unrelated websites.
        host_ok = _hostname(request.headers.get("host", "")) in LOCAL_HOSTS
        origin = request.headers.get("origin")
        origin_ok = origin is None or urlsplit(origin).hostname in LOCAL_HOSTS
        if not (host_ok and origin_ok):
            return JSONResponse({"detail": "Local access only"}, status_code=403)
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > settings.limits.max_zip_bytes + MIB:
            return JSONResponse({"detail": "Upload is larger than the limit"}, status_code=413)
        return await call_next(request)

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "fts5": fts5_available(),
            "ai_configured": settings.ai_configured,
            "limits": asdict(settings.limits),
        }

    @app.get("/api/status")
    def status():
        return {"importing": store.lock.locked(), "snapshot": store.current}

    @app.post("/api/snapshots")
    def upload(file: UploadFile):
        limit = settings.limits.max_zip_bytes
        data = file.file.read(limit + 1)
        name = PurePosixPath((file.filename or "upload.zip").replace("\\", "/")).name[:100]
        return store.import_zip(name, data, settings.limits)

    @app.get("/api/snapshots/{snapshot_id}/files/{file_id}")
    def source(snapshot_id: str, file_id: int):
        found = store.source(snapshot_id, file_id)
        if not found:
            raise HTTPException(404, "File not found in this snapshot")
        return found

    return app
