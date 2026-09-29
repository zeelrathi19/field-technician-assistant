"""Validated settings, loaded once at startup. Hard policy limits are constants, not env."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

# ---- Hard invariants (never configurable) -------------------------------------------
MAX_MUTATIONS_PER_TURN = 1
MAX_RAW_TOOL_ARGS_BYTES = 8_192
MAX_RESPOND_TEXT_CHARS = 1_200
MAX_CITATIONS = 6


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(REPO_ROOT / ".env", ".env"), env_file_encoding="utf-8", extra="ignore")

    # Model provider
    model_provider: Literal["openai", "gemini", "offline"] = "offline"
    model_name: str = ""
    model_api_key: SecretStr = SecretStr("")
    model_base_url: str = ""  # OpenAI-compatible endpoints (Gemini, Groq, OpenRouter, Ollama, vLLM ...)
    model_compat: Literal["openai", "generic"] = "openai"  # generic drops strict/parallel params
    model_temperature: float | None = None

    # Budgets (engineering defaults; bounded)
    model_timeout_seconds: float = Field(30, gt=0, le=300)
    turn_timeout_seconds: float = Field(60, gt=0, le=900)
    max_model_calls_per_turn: int = Field(3, ge=1, le=4)
    max_tool_calls_per_turn: int = Field(3, ge=1, le=4)
    max_output_tokens: int = Field(1024, ge=256, le=8192)
    model_concurrency: int = Field(4, ge=1, le=32)
    history_messages: int = Field(8, ge=0, le=24)
    history_char_budget: int = Field(12_000, ge=1_000, le=100_000)

    # Input limits
    max_message_chars: int = Field(8_000, ge=100, le=32_000)
    max_note_chars: int = Field(2_000, ge=10, le=10_000)
    max_reason_chars: int = Field(500, ge=10, le=5_000)

    # Paths
    database_path: Path = REPO_ROOT / "data" / "assistant.sqlite3"
    knowledge_path: Path = REPO_ROOT / "inputs" / "knowledge.md"
    work_orders_path: Path = REPO_ROOT / "inputs" / "work_orders.json"
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"

    # HTTP
    allowed_origins: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173,http://127.0.0.1:5173"
    secure_cookies: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @model_validator(mode="after")
    def _check_provider(self) -> "Settings":
        if self.model_provider in ("openai", "gemini"):
            if not self.model_name.strip():
                raise ValueError(f"MODEL_NAME is required for MODEL_PROVIDER={self.model_provider}")
            local_compat = self.model_provider == "openai" and self.model_base_url.startswith(
                ("http://localhost", "http://127.0.0.1", "http://host.docker.internal", "http://ollama")
            )
            if not self.model_api_key.get_secret_value() and not local_compat:
                raise ValueError(f"MODEL_API_KEY is required for MODEL_PROVIDER={self.model_provider}")
        return self

    @property
    def origin_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
