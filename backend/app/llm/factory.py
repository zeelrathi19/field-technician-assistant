"""Build the configured ModelClient. Adding a provider = one adapter + one branch here."""

from __future__ import annotations

from ..config import Settings
from ..knowledge import KnowledgeBase
from .base import ModelClient


def build_model(settings: Settings, kb: KnowledgeBase) -> ModelClient:
    key = settings.model_api_key.get_secret_value()
    if settings.model_provider == "openai":
        from .openai_compat import OpenAICompatClient
        return OpenAICompatClient(settings.model_name, key, settings.model_base_url, settings.model_compat,
                                  settings.model_temperature)
    if settings.model_provider == "anthropic":
        from .anthropic_native import AnthropicClient
        return AnthropicClient(settings.model_name, key, settings.model_base_url, settings.model_temperature)
    if settings.model_provider == "codex":
        from .codex_cli import CodexCLIClient
        if not CodexCLIClient.available(settings.codex_bin):
            raise ValueError(f"MODEL_PROVIDER=codex but '{settings.codex_bin}' is not on PATH "
                             "(install the Codex CLI and run `codex login`, or set CODEX_BIN)")
        return CodexCLIClient(settings.model_name, settings.codex_bin)
    if settings.model_provider == "offline":
        from .offline import OfflineModel
        return OfflineModel(kb)
    raise ValueError(f"unsupported MODEL_PROVIDER {settings.model_provider}")  # pragma: no cover
