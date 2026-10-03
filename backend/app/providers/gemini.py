import asyncio
import base64
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


class GeminiProvider(VisionProvider):
    """Google Gemini Vision provider implementation using official google-genai SDK."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.provider_name = "gemini"
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.MODEL_NAME or "gemini-2.5-flash"

        if _GEMINI_SDK_AVAILABLE and self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None

    def _ensure_client(self):
        if not _GEMINI_SDK_AVAILABLE:
            raise ProviderError(502, "google-genai SDK is not installed.")
        if not self.client or not self.api_key:
            raise ProviderError(502, "Gemini API key is missing or not configured.")

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
        exc_str = str(exc).lower()
        if "timeout" in exc_str:
            return ProviderError(504, "Gemini API request timed out after 30 seconds.")
        if "quota" in exc_str or "429" in exc_str or "resource_exhausted" in exc_str:
            return ProviderError(429, "Gemini rate limit or quota exceeded.")
        if "invalid_argument" in exc_str or "400" in exc_str:
            return ProviderError(400, "Invalid request submitted to Gemini API.")
        return ProviderError(502, "An unexpected error occurred while communicating with Gemini API.")

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
        config = types.GenerateContentConfig(system_instruction=system_prompt)

        attempts = 0
        max_attempts = 2
        last_exc = None

        while attempts < max_attempts:
            attempts += 1
            try:
                # Use asyncio.wait_for to enforce 30s timeout
                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=self.model_name,
                        contents=contents,
                        config=config,
                    ),
                    timeout=30.0,
                )
                return response.text or ""
            except asyncio.TimeoutError as exc:
                raise ProviderError(504, "Gemini API request timed out after 30 seconds.") from exc
            except Exception as exc:
                last_exc = exc
                exc_str = str(exc).lower()
                if ("429" in exc_str or "quota" in exc_str or "500" in exc_str or "503" in exc_str) and attempts < max_attempts:
                    await asyncio.sleep(1.0)
                else:
                    raise self._handle_exception(exc) from exc

        if last_exc:
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
        config = types.GenerateContentConfig(system_instruction=system_prompt)

        attempts = 0
        max_attempts = 2

        while attempts < max_attempts:
            attempts += 1
            try:
                response_stream = await self.client.aio.models.generate_content_stream(
                    model=self.model_name,
                    contents=contents,
                    config=config,
                )
                async for chunk in response_stream:
                    if chunk.text:
                        yield chunk.text
                return
            except asyncio.TimeoutError as exc:
                raise ProviderError(504, "Gemini API request timed out after 30 seconds.") from exc
            except Exception as exc:
                exc_str = str(exc).lower()
                if ("429" in exc_str or "quota" in exc_str or "500" in exc_str or "503" in exc_str) and attempts < max_attempts:
                    await asyncio.sleep(1.0)
                else:
                    raise self._handle_exception(exc) from exc
