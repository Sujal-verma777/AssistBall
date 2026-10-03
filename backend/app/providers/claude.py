import asyncio
from typing import AsyncIterator, List, Optional
import anthropic
from app.config import settings
from app.providers.base import ProviderError, VisionProvider
from app.schemas import ChatMessage


class ClaudeProvider(VisionProvider):
    """Anthropic Claude vision provider implementation."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.provider_name = "claude"
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        self.model_name = model_name or settings.MODEL_NAME or "claude-sonnet-5-5"
        if self.api_key:
            self.client = anthropic.AsyncAnthropic(api_key=self.api_key, timeout=30.0)
        else:
            self.client = None

    def _ensure_client(self):
        if not self.client or not self.api_key:
            raise ProviderError(502, "Anthropic API key is missing or not configured.")

    def _build_messages(
        self, query: str, image_b64: str, media_type: str, history: List[ChatMessage]
    ) -> List[dict]:
        messages = []
        for msg in history:
            messages.append({"role": msg.role, "content": msg.content})

        user_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_b64,
                },
            },
            {"type": "text", "text": query},
        ]
        messages.append({"role": "user", "content": user_content})
        return messages

    def _handle_exception(self, exc: Exception) -> ProviderError:
        if isinstance(exc, ProviderError):
            return exc
        if isinstance(exc, anthropic.APITimeoutError):
            return ProviderError(504, "Anthropic API request timed out after 30 seconds.")
        if isinstance(exc, anthropic.RateLimitError):
            return ProviderError(429, "Anthropic rate limit exceeded. Please try again later.")
        if isinstance(exc, anthropic.BadRequestError):
            return ProviderError(400, "Invalid request submitted to Anthropic API.")
        if isinstance(exc, anthropic.APIStatusError):
            status = exc.status_code
            if status >= 500:
                return ProviderError(502, f"Anthropic service error (HTTP {status}).")
            if status == 429:
                return ProviderError(429, "Anthropic rate limit exceeded.")
            return ProviderError(502, f"Anthropic API returned error HTTP {status}.")
        if isinstance(exc, anthropic.APIConnectionError):
            return ProviderError(502, "Unable to connect to Anthropic API.")
        return ProviderError(502, "An unexpected error occurred while communicating with Anthropic.")

    async def answer(
        self,
        query: str,
        image_b64: str,
        media_type: str,
        history: List[ChatMessage],
        system_prompt: str,
    ) -> str:
        self._ensure_client()
        messages = self._build_messages(query, image_b64, media_type, history)

        attempts = 0
        max_attempts = 2
        last_exc = None

        while attempts < max_attempts:
            attempts += 1
            try:
                response = await self.client.messages.create(
                    model=self.model_name,
                    max_tokens=1024,
                    system=system_prompt,
                    messages=messages,
                    timeout=30.0,
                )
                text_blocks = [block.text for block in response.content if block.type == "text"]
                return "".join(text_blocks)
            except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
                last_exc = exc
                if attempts < max_attempts:
                    await asyncio.sleep(1.0)
                else:
                    raise self._handle_exception(exc) from exc
            except Exception as exc:
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
        messages = self._build_messages(query, image_b64, media_type, history)

        attempts = 0
        max_attempts = 2
        stream_context = None

        while attempts < max_attempts:
            attempts += 1
            try:
                stream_context = self.client.messages.stream(
                    model=self.model_name,
                    max_tokens=1024,
                    system=system_prompt,
                    messages=messages,
                    timeout=30.0,
                )
                async with stream_context as stream:
                    async for text in stream.text_stream:
                        yield text
                return
            except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
                if attempts < max_attempts:
                    await asyncio.sleep(1.0)
                else:
                    raise self._handle_exception(exc) from exc
            except Exception as exc:
                raise self._handle_exception(exc) from exc
