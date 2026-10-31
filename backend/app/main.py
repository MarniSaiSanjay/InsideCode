from contextlib import closing
from dataclasses import asdict
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import MIB, Settings, load_settings
from .explain import (
    MAX_EVIDENCE,
    AIUnavailable,
    evidence_context,
    explain,
    general_answer,
    suggest_terms,
)
from .indexing import ImportRejected
from .languages import LANGUAGES
from .search import MAX_QUERY_CHARS, RESULT_SQL, search
from .storage import StaleSnapshot, Store, fts5_available

LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)


class Evidence(Question):
    snapshot_id: str
    chunk_ids: list[int] = Field(min_length=1, max_length=MAX_EVIDENCE)


def _hostname(value: str) -> str:
    return (urlsplit(f"//{value}").hostname or "").lower()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    store = Store(settings.state_dir)
    app = FastAPI(title="InsideCode")

    @app.exception_handler(ImportRejected)
    def rejected(_: Request, exc: ImportRejected):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(StaleSnapshot)
    def stale(_: Request, __: StaleSnapshot):
        detail = "This result belongs to an older upload. Search again."
        return JSONResponse({"detail": detail}, status_code=409)

    @app.exception_handler(AIUnavailable)
    def unavailable(_: Request, exc: AIUnavailable):
        detail = f"AI answer unavailable: {exc}. Search results are unaffected."
        return JSONResponse({"detail": detail}, status_code=503)

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
            "languages": [language.name for language in LANGUAGES],
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

    @app.get("/api/search")
    def find(snapshot_id: str, q: str = Query(max_length=MAX_QUERY_CHARS), expand: bool = False):
        suggested, ai_note = [], None
        if expand:
            try:
                suggested = suggest_terms(settings, q)
            except AIUnavailable as exc:
                ai_note = f"{exc}. Showing local search results only."
        with closing(store.connect(snapshot_id)) as db:
            results = search(db, q, extra=suggested)
        return {
            "snapshot_id": snapshot_id,
            "query": q,
            "suggested_terms": suggested,
            "ai_note": ai_note,
            "results": results,
        }

    @app.get("/api/snapshots/{snapshot_id}/files/{file_id}")
    def source(snapshot_id: str, file_id: int):
        found = store.source(snapshot_id, file_id)
        if not found:
            raise HTTPException(404, "File not found in this snapshot")
        return found

    def evidence_rows(body: Evidence) -> list[dict]:
        with closing(store.connect(body.snapshot_id)) as db:
            rows = [db.execute(RESULT_SQL, (i,)).fetchone() for i in dict.fromkeys(body.chunk_ids)]
        if not all(rows):
            raise HTTPException(404, "Evidence not found in this snapshot")
        return [dict(row) for row in rows]

    @app.post("/api/explain/context")
    def explain_context(body: Evidence):
        return {"context": evidence_context(body.question, evidence_rows(body))}

    @app.post("/api/explain")
    def explain_evidence(body: Evidence):
        return explain(settings, body.question, evidence_rows(body))

    @app.post("/api/general")
    def general(body: Question):
        return {"answer": general_answer(settings, body.question)}

    if settings.ui_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.ui_dir, html=True), name="ui")
    return app
