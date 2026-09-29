"""Safe, useful provider error details for operator logs (never shown to end users)."""

from __future__ import annotations

import re

_SECRETISH = re.compile(r"(AIza[0-9A-Za-z_\-]{20,}|AQ\.[0-9A-Za-z_\-.]{20,}|sk-[A-Za-z0-9_\-]{16,}|"
                        r"gsk_[A-Za-z0-9]{20,}|Bearer\s+\S+|key=[^&\s\"']+)")


def redact(text: str) -> str:
    return _SECRETISH.sub("[redacted]", text)


def detail(exc: BaseException, limit: int = 300) -> str:
    """Status code + provider message, redacted and truncated, e.g. '404: models/x is not found'."""
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    msg = ""
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict):
            msg = str(err.get("message") or err.get("status") or "")
        elif isinstance(body, list) and body:
            msg = str(body[0])
    if not msg:
        msg = str(getattr(exc, "message", "") or exc)
    out = f"{status}: {msg}" if status else msg
    return redact(" ".join(out.split()))[:limit]
