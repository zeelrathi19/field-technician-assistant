"""App factory: validate config, initialise DB/KB/model once, serve API + built UI."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .agent import ChatService
from .api import router
from .config import Settings
from .db import Database
from .knowledge import KnowledgeBase
from .llm.base import ModelClient
from .llm.factory import build_model
from .logging_setup import configure
from .prompts.registry import PromptRegistry

log = logging.getLogger("fta.app")

MAX_BODY_BYTES = 64 * 1024  # a chat message is <= 8000 chars; anything bigger is refused unread


class BodyLimitMiddleware:
    """Pure-ASGI guard: rejects oversized bodies by Content-Length and while streaming."""

    def __init__(self, app, limit: int = MAX_BODY_BYTES):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.limit:
            return await JSONResponse({"detail": "Request body too large."}, status_code=413)(scope, receive, send)
        seen = 0

        async def limited_receive():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.limit:
                    raise _TooLarge()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _TooLarge:
            await JSONResponse({"detail": "Request body too large."}, status_code=413)(scope, receive, send)


class _TooLarge(Exception):
    pass


def create_app(settings: Settings | None = None, model: ModelClient | None = None) -> FastAPI:
    settings = settings or Settings()
    configure(settings.log_level)
    kb = KnowledgeBase.load(settings.knowledge_path)
    db = Database(settings.database_path)
    db.initialize(settings.work_orders_path)
    model = model or build_model(settings, kb)
    chat = ChatService(settings, db, kb, model, PromptRegistry())
    log.info("startup", extra={"provider": model.provider, "model": model.model, "kb_sections": len(kb.sections),
                               "prompt_version": chat.prompts.version, "prompt_hash": chat.prompts.hash("system")})

    app = FastAPI(title="Field Technician Assistant", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.settings = settings
    app.state.chat = chat
    app.include_router(router)
    app.add_middleware(BodyLimitMiddleware)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = sorted({".".join(str(p) for p in e["loc"][1:]) for e in exc.errors()})
        return JSONResponse({"detail": f"Invalid request: {', '.join(fields) or 'body'}."}, status_code=422)

    dist = Path(settings.frontend_dist)
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path == "api" or path.startswith("api/"):
                return JSONResponse({"detail": "Not found."}, status_code=404)  # never mask API typos with the SPA
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def no_ui() -> JSONResponse:
            return JSONResponse({"detail": "UI not built. Run `make build-ui` or use `docker compose up --build`."})

    return app


def app_factory() -> FastAPI:  # uvicorn --factory app.main:app_factory
    return create_app()
