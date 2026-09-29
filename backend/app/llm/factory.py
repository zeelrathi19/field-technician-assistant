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
    if settings.model_provider == "gemini":
        from .gemini_native import GeminiClient
        return GeminiClient(settings.model_name, key, settings.model_base_url, settings.model_temperature)
    if settings.model_provider == "offline":
        from .offline import OfflineModel
        return OfflineModel(kb)
    raise ValueError(f"unsupported MODEL_PROVIDER {settings.model_provider}")  # pragma: no cover
