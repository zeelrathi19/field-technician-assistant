#!/usr/bin/env python3
"""Fail if tracked (or staged) files contain obvious secrets or confidential inputs.

Usage: python tools/scan_secrets.py [--staged]
"""

from __future__ import annotations

import re
import subprocess
import sys

PATTERNS = {
    "OpenAI-style key": re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_\-]{20,}"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "GitHub fine-grained token": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    "Groq key": re.compile(r"\bgsk_[A-Za-z0-9]{40,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "Non-empty MODEL_API_KEY": re.compile(r"^\s*MODEL_API_KEY\s*=\s*[^\s#]{8,}", re.M),
}
FORBIDDEN_FILES = re.compile(r"(^|/)(\.env(\..+)?|ASSIGNMENT\.pdf|.*\.sqlite3?|.*\.db)$")
ALLOWED = {".env.example"}


def files(staged: bool) -> list[str]:
    cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"] if staged else ["git", "ls-files"]
    return [f for f in subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.splitlines() if f]


def main() -> int:
    staged = "--staged" in sys.argv
    problems = []
    for path in files(staged):
        if FORBIDDEN_FILES.search(path) and path.split("/")[-1] not in ALLOWED:
            problems.append(f"{path}: file must not be committed")
            continue
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
        except (IsADirectoryError, FileNotFoundError):
            continue
        for name, rx in PATTERNS.items():
            if rx.search(text):
                problems.append(f"{path}: looks like a {name}")
    for p in problems:
        print(f"SECRET-SCAN: {p}", file=sys.stderr)
    if not problems:
        print(f"secret scan: clean ({'staged' if staged else 'tracked'} files)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
