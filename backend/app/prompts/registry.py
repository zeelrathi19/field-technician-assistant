"""Versioned prompt files bundled with the app. No runtime editing, no user-chosen paths."""

from __future__ import annotations

import hashlib
from pathlib import Path

PROMPT_VERSION = "v1"
_DIR = Path(__file__).parent
_REQUIRED = {"system": ("{knowledge}", "{kb_hash}")}


class PromptRegistry:
    def __init__(self, version: str = PROMPT_VERSION):
        if version not in {"v1"}:
            raise ValueError(f"unknown prompt version {version}")
        self.version = version
        self._templates: dict[str, str] = {}
        for name, placeholders in _REQUIRED.items():
            text = (_DIR / version / f"{name}.txt").read_text(encoding="utf-8")
            missing = [p for p in placeholders if p not in text]
            if missing:
                raise ValueError(f"prompt {version}/{name} is missing {missing}")
            self._templates[name] = text

    def hash(self, name: str) -> str:
        return hashlib.sha256(self._templates[name].encode()).hexdigest()[:12]

    def system(self, knowledge_block: str, kb_hash: str) -> str:
        return self._templates["system"].replace("{kb_hash}", kb_hash[:12]).replace("{knowledge}", knowledge_block)
