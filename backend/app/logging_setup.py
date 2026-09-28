"""Structured JSON logs with metadata only — never message bodies, notes, prompts or keys."""

from __future__ import annotations

import json
import logging
import sys

_STD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"), "level": record.levelname,
               "logger": record.name, "event": record.getMessage()}
        out.update({k: v for k, v in record.__dict__.items() if k not in _STD})
        if record.exc_info:
            out["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(out, default=str)


def configure(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("fta")
    root.handlers[:] = [handler]
    root.setLevel(level)
    root.propagate = False
    for noisy in ("httpx", "openai", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
