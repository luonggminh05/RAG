from functools import lru_cache
from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from app.core.config import settings

def _build_openai_compat(**overrides) -> BaseChatModel:
    endpoint = overrides.pop("base_url", None) or getattr(settings, "llm_endpoint", "http://localhost:11434/v1")
    model = overrides.pop("model", None) or getattr(settings, "llm_model_id", "qwen2.5vl:7b")
    api_key = overrides.pop("api_key", None) or getattr(settings, "llm_api_key", "ollama")
    temp = overrides.pop("temperature", None) or getattr(settings, "llm_temperature", 0.2)
    max_tokens = overrides.pop("max_tokens", None) or getattr(settings, "llm_max_tokens", 2048)

    return ChatOpenAI(
        model=model,
        base_url=endpoint,
        api_key=api_key if api_key and api_key != "EMPTY" else "ollama",
        temperature=temp,
        max_tokens=max_tokens,
        **overrides
    )

_BUILDER = {
    "openai_compat": _build_openai_compat,
    "ollama": _build_openai_compat,
    "vllm": _build_openai_compat,
    "lmstudio": _build_openai_compat,
}

@lru_cache(maxsize=8)
def get_chat_model(provider: str = "openai_compat", **overrides) -> BaseChatModel:
    builder_fn = _BUILDER.get(provider.lower(), _build_openai_compat)
    return builder_fn(**overrides)
