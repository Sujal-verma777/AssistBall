from typing import Dict, Optional, Type
from app.config import settings
from app.providers.base import ProviderError, VisionProvider
from app.providers.mock import MockProvider

# Provider classes are imported lazily so local/mock mode can run without
# installing every optional cloud SDK. Production provider selection imports
# only the SDK required by that provider.
PROVIDER_REGISTRY: Dict[str, Type[VisionProvider]] = {
    "mock": MockProvider,
}


def _load_provider_class(name: str) -> Type[VisionProvider]:
    if name == "claude":
        from app.providers.claude import ClaudeProvider
        return ClaudeProvider
    if name == "openai":
        from app.providers.openai_provider import OpenAIProvider
        return OpenAIProvider
    if name == "gemini":
        from app.providers.gemini import GeminiProvider
        return GeminiProvider
    raise ProviderError(
        400,
        f"Unsupported provider '{name}'. Supported providers are: claude, openai, gemini, mock.",
    )


def register_provider(name: str, provider_cls: Type[VisionProvider]) -> None:
    PROVIDER_REGISTRY[name.lower()] = provider_cls


def get_provider(
    provider_name: Optional[str] = None,
    model_name: Optional[str] = None,
) -> VisionProvider:
    target_provider = (provider_name or settings.PROVIDER or "mock").lower()
    target_model = model_name or settings.MODEL_NAME

    provider_cls = PROVIDER_REGISTRY.get(target_provider)
    if provider_cls is None:
        provider_cls = _load_provider_class(target_provider)
        PROVIDER_REGISTRY[target_provider] = provider_cls

    return provider_cls(model_name=target_model)
