"""Starts the real app (built UI + API, offline model, temp DB) for browser tests."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url(tmp_path_factory):
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        pytest.skip("frontend not built; run `make build-ui`")
    port = _free_port()
    env = {**os.environ, "MODEL_PROVIDER": "offline", "LOG_LEVEL": "WARNING",
           "DATABASE_PATH": str(tmp_path_factory.mktemp("db") / "e2e.sqlite3")}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "--factory", "app.main:app_factory",
                             "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT / "backend", env=env)
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            urllib.request.urlopen(url + "/api/health", timeout=1)
            break
        except OSError:
            time.sleep(0.25)
    else:
        proc.terminate()
        raise RuntimeError("server did not start")
    yield url
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright
    exe = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or None
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe)
        yield b
        b.close()
