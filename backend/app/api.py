"""HTTP boundary: request validation, browser-session scoping, Origin checks, error mapping."""

from __future__ import annotations

import secrets
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .agent import ChatService

COOKIE = "fta_browser"
router = APIRouter(prefix="/api")


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: uuid.UUID
    message: str = Field(min_length=1)


def get_chat(request: Request) -> ChatService:
    return request.app.state.chat


def browser_id(fta_browser: Annotated[str | None, Cookie()] = None) -> str:
    if not fta_browser or len(fta_browser) > 128:
        raise HTTPException(404, "Session not found.")
    return fta_browser


def check_origin(request: Request) -> None:
    """Same-origin writes only. Non-browser clients (no Origin header) are allowed for tooling."""
    origin = request.headers.get("origin")
    if origin is None:
        return
    allowed = request.app.state.settings.origin_list
    host_origin = f"{request.url.scheme}://{request.headers.get('host', '')}"
    if origin not in allowed and origin != host_origin:
        raise HTTPException(403, "Cross-origin request rejected.")


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    chat: ChatService = request.app.state.chat
    try:
        chat.db.principal()
        db_ok = True
    except Exception:
        db_ok = False
    return {"ok": db_ok, "database": db_ok, "knowledge_sections": len(chat.kb.sections),
            "provider": chat.model.provider}


@router.get("/meta")
def meta(request: Request) -> dict[str, Any]:
    chat: ChatService = request.app.state.chat
    return {"technician": {"id": chat.principal["id"], "name": chat.principal["name"]},
            "provider": chat.model.provider, "model": chat.model.model, "is_llm": chat.model.is_llm,
            "prompt_version": chat.prompts.version, "kb_hash": chat.kb.sha256[:12],
            "limits": {"max_message_chars": chat.settings.max_message_chars}}


@router.get("/work-orders")
def work_orders(chat: Annotated[ChatService, Depends(get_chat)]) -> dict[str, Any]:
    return {"work_orders": chat.roster()}


@router.post("/sessions", status_code=201, dependencies=[Depends(check_origin)])
def create_session(request: Request, response: Response,
                   chat: Annotated[ChatService, Depends(get_chat)],
                   fta_browser: Annotated[str | None, Cookie()] = None) -> dict[str, Any]:
    bid = fta_browser if fta_browser and len(fta_browser) <= 128 else secrets.token_urlsafe(32)
    response.set_cookie(COOKIE, bid, httponly=True, samesite="strict", path="/api",
                        secure=request.app.state.settings.secure_cookies, max_age=60 * 60 * 24 * 30)
    return chat.create_session(bid)


@router.get("/sessions/{session_id}")
def get_session(session_id: str, chat: Annotated[ChatService, Depends(get_chat)],
                bid: Annotated[str, Depends(browser_id)]) -> dict[str, Any]:
    view = chat.session_view(session_id, bid)
    if view is None:
        raise HTTPException(404, "Session not found.")
    return view


@router.post("/sessions/{session_id}/messages", dependencies=[Depends(check_origin)])
def post_message(session_id: str, body: MessageIn, chat: Annotated[ChatService, Depends(get_chat)],
                 bid: Annotated[str, Depends(browser_id)]) -> JSONResponse:
    text = body.message.strip()
    if not text:
        raise HTTPException(422, "Message is empty.")
    if len(text) > chat.settings.max_message_chars:
        raise HTTPException(413, f"Message is longer than {chat.settings.max_message_chars} characters.")
    status, payload = chat.handle_message(session_id, bid, str(body.request_id), text)
    return JSONResponse(payload, status_code=status)


@router.get("/sessions/{session_id}/requests/{request_id}")
def get_request(session_id: str, request_id: uuid.UUID, chat: Annotated[ChatService, Depends(get_chat)],
                bid: Annotated[str, Depends(browser_id)]) -> JSONResponse:
    found = chat.request_view(session_id, bid, str(request_id))
    if found is None:
        raise HTTPException(404, "Request not found.")
    status, payload = found
    return JSONResponse(payload, status_code=status)
