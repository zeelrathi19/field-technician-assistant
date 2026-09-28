"""Approved knowledge base: stable section IDs, content hashes, verbatim-quote checks.

Reference text is *data*. Nothing here interprets it as an instruction.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

_HEADING = re.compile(r"^##\s+(?:(\d+)\.\s*)?(.+?)\s*$")
_ELLIPSIS = re.compile(r"\s*(?:\.\.\.|…)\s*")


def normalize(text: str) -> str:
    t = text.replace("**", "").replace("__", "").replace("`", "")
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.replace("—", "-").replace("–", "-")
    t = re.sub(r"(?m)^\s*(?:[-*]|\d+\.)\s+", " ", t)  # list markers
    t = re.sub(r"\s+", " ", t)
    return t.strip().lower()


@dataclass(frozen=True)
class Section:
    id: str
    number: int
    heading: str
    body: str  # original markdown, heading excluded
    sha256: str

    @property
    def normalized(self) -> str:
        return normalize(self.body)

    def to_source(self) -> dict[str, str]:
        return {"kind": "knowledge", "section_id": self.id, "heading": self.heading,
                "content_hash": self.sha256[:12], "text": self.body}


class KnowledgeBase:
    def __init__(self, sections: list[Section], sha256: str):
        if not sections:
            raise ValueError("knowledge base has no sections")
        self.sections = sections
        self.by_id = {s.id: s for s in sections}
        self.sha256 = sha256

    @classmethod
    def load(cls, path: Path | str) -> "KnowledgeBase":
        raw = Path(path).read_text(encoding="utf-8")
        return cls.parse(raw)

    @classmethod
    def parse(cls, raw: str) -> "KnowledgeBase":
        sections: list[Section] = []
        current: tuple[int, str] | None = None
        buf: list[str] = []

        def flush() -> None:
            if current is None:
                return
            body = "\n".join(buf).strip()
            body = re.sub(r"\n-{3,}\s*$", "", body).strip()  # trailing horizontal rule
            number, heading = current
            sections.append(Section(f"kb-{number}", number, heading, body,
                                    hashlib.sha256(body.encode()).hexdigest()))

        for line in raw.splitlines():
            m = _HEADING.match(line)
            if m:
                flush()
                number = int(m.group(1)) if m.group(1) else len(sections) + 1
                current, buf = (number, m.group(2).strip()), []
            elif current is not None:
                if line.strip() == "---":
                    continue
                buf.append(line)
        flush()
        return cls(sections, hashlib.sha256(raw.encode()).hexdigest())

    def get(self, section_id: str) -> Section | None:
        return self.by_id.get(section_id)

    def quote_in_section(self, section_id: str, quote: str) -> bool:
        section = self.by_id.get(section_id)
        if section is None:
            return False
        hay = section.normalized
        pieces = [normalize(p).rstrip(".;:,") for p in _ELLIPSIS.split(quote)]
        pieces = [p for p in pieces if p]
        if not pieces:
            return False
        # Each fragment must be verbatim and meaningful (>= 12 chars or a full numeric fact).
        return all((len(p) >= 12 or re.search(r"\d", p)) and p in hay for p in pieces)

    def prompt_block(self) -> str:
        parts = [f'<section id="{s.id}" title="{s.heading}">\n{s.body}\n</section>' for s in self.sections]
        return "\n".join(parts)
