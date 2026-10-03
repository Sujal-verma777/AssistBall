import asyncio
import base64
import logging
from typing import AsyncIterator, List, Optional
try:
    from google import genai
    from google.genai import types
    _GEMINI_SDK_AVAILABLE = True
except ImportError:
    _GEMINI_SDK_AVAILABLE = False

from app.config import settings
from app.providers.base import ProviderError, VisionProvider
from app.schemas import ChatMessage

logger = logging.getLogger("assistball")

DEFAULT_MODEL = "gemini-3.8-flash"
FALLBACK_MODELS = ["gemini-3-flash-preview"]
DEPRECATED_MODELS = {
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-exp",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.5-flash-lite",
}


def _resolve_model(model_name: Optional[str]) -> str:
    chosen = (model_name or settings.MODEL_NAME or DEFAULT_MODEL).strip()
    if chosen in DEPRECATED_MODELS:
        return DEFAULT_MODEL
    return chosen


class GeminiProvider(VisionProvider):
    """Google Gemini Vision provider implementation using official google-genai SDK."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.provider_name = "gemini"
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = _resolve_model(model_name)

        if _GEMINI_SDK_AVAILABLE and self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None

    def _ensure_client(self):
        if not _GEMINI_SDK_AVAILABLE:
            raise ProviderError(502, "google-genai SDK is not installed.")
        if not self.client or not self.api_key:
            raise ProviderError(502, "Gemini API key is missing or not configured.")

    def _create_config(self, system_prompt: str) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=system_prompt,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    def _build_contents(
        self, query: str, image_b64: str, media_type: str, history: List[ChatMessage]
    ) -> List[types.Content]:
        contents = []

        # Convert text history (user / model)
        for msg in history:
            role = "user" if msg.role == "user" else "model"
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=msg.content)]
                )
            )

        # Attach image + query to final user turn
        raw_bytes = base64.b64decode(image_b64)
        image_part = types.Part.from_bytes(data=raw_bytes, mime_type=media_type)
        text_part = types.Part.from_text(text=query)

        contents.append(
            types.Content(
                role="user",
                parts=[image_part, text_part]
            )
        )
        return contents

    def _handle_exception(self, exc: Exception) -> ProviderError:
        if isinstance(exc, ProviderError):
            return exc
        exc_str = str(exc)
        exc_lower = exc_str.lower()
        if "timeout" in exc_lower:
            return ProviderError(504, "Gemini API request timed out after 30 seconds.")
        if "quota" in exc_lower or "429" in exc_lower or "resource_exhausted" in exc_lower:
            return ProviderError(429, "Gemini rate limit or quota exceeded.")
        if "not_found" in exc_lower or "404" in exc_lower:
            return ProviderError(404, f"Gemini model not found: {exc_str}")
        if "unauthenticated" in exc_lower or "permission_denied" in exc_lower or "api_key" in exc_lower:
            return ProviderError(401, f"Gemini API authentication failed: {exc_str}")
        if "invalid_argument" in exc_lower or "400" in exc_lower:
            return ProviderError(400, f"Invalid request submitted to Gemini API: {exc_str}")
        if "503" in exc_lower or "unavailable" in exc_lower:
            return ProviderError(503, "Gemini service is currently experiencing high demand. Please try again shortly.")
        return ProviderError(502, f"Gemini API error: {exc_str}")

    async def answer(
        self,
        query: str,
        image_b64: str,
        media_type: str,
        history: List[ChatMessage],
        system_prompt: str,
    ) -> str:
        self._ensure_client()
        contents = self._build_contents(query, image_b64, media_type, history)
        config = self._create_config(system_prompt)

        candidate_models = [self.model_name] + [m for m in FALLBACK_MODELS if m != self.model_name]
        last_exc = None

        for model in candidate_models:
            for attempt in range(1, 3):
                try:
                    response = await asyncio.wait_for(
                        self.client.aio.models.generate_content(
                            model=model,
                            contents=contents,
                            config=config,
                        ),
                        timeout=30.0,
                    )
                    return response.text or ""
                except asyncio.TimeoutError as exc:
                    last_exc = ProviderError(504, f"Gemini API request timed out on model '{model}'.")
                    break
                except Exception as exc:
                    last_exc = exc
                    exc_str = str(exc).lower()
                    if "404" in exc_str or "not_found" in exc_str:
                        break
                    if ("429" in exc_str or "quota" in exc_str or "500" in exc_str or "503" in exc_str) and attempt < 2:
                        await asyncio.sleep(1.0)
                    else:
                        break

        raise self._handle_exception(last_exc)

    async def stream(
        self,
        query: str,
        image_b64: str,
        media_type: str,
        history: List[ChatMessage],
        system_prompt: str,
    ) -> AsyncIterator[str]:
        self._ensure_client()
        contents = self._build_contents(query, image_b64, media_type, history)
        config = self._create_config(system_prompt)

        candidate_models = [self.model_name] + [m for m in FALLBACK_MODELS if m != self.model_name]
        last_exc = None
        stream_started = False

        for model in candidate_models:
            if stream_started:
                break
            for attempt in range(1, 3):
                try:
                    response_stream = await self.client.aio.models.generate_content_stream(
                        model=model,
                        contents=contents,
                        config=config,
                    )
                    async for chunk in response_stream:
                        if chunk.text:
                            stream_started = True
                            yield chunk.text
                    return
                except asyncio.TimeoutError as exc:
                    if stream_started:
                        return
                    last_exc = ProviderError(504, f"Gemini API request timed out on model '{model}'.")
                    break
                except Exception as exc:
                    if stream_started:
                        return
                    last_exc = exc
                    exc_str = str(exc).lower()
                    if "404" in exc_str or "not_found" in exc_str:
                        break
                    if ("429" in exc_str or "quota" in exc_str or "500" in exc_str or "503" in exc_str) and attempt < 2:
                        await asyncio.sleep(1.0)
                    else:
                        break

        if not stream_started:
            raise self._handle_exception(last_exc)

