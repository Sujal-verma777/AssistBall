import asyncio
from typing import AsyncIterator, List, Optional
import openai
from app.config import settings
from app.providers.base import ProviderError, VisionProvider
from app.schemas import ChatMessage


class OpenAIProvider(VisionProvider):
    """OpenAI Vision provider implementation."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.provider_name = "openai"
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model_name = model_name or settings.MODEL_NAME or "gpt-4o"
        if self.api_key:
            self.client = openai.AsyncOpenAI(api_key=self.api_key, timeout=30.0)
        else:
            self.client = None

    def _ensure_client(self):
        if not self.client or not self.api_key:
            raise ProviderError(502, "OpenAI API key is missing or not configured.")

    def _build_messages(
        self, query: str, image_b64: str, media_type: str, history: List[ChatMessage], system_prompt: str
    ) -> List[dict]:
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history:
            messages.append({"role": msg.role, "content": msg.content})

        user_content = [
            {"type": "text", "text": query},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{image_b64}"},
            },
        ]
        messages.append({"role": "user", "content": user_content})
        return messages

    def _handle_exception(self, exc: Exception) -> ProviderError:
        if isinstance(exc, ProviderError):
            return exc
        if isinstance(exc, openai.APITimeoutError):
            return ProviderError(504, "OpenAI API request timed out after 30 seconds.")
        if isinstance(exc, openai.RateLimitError):
            return ProviderError(429, "OpenAI rate limit exceeded. Please try again later.")
        if isinstance(exc, openai.BadRequestError):
            return ProviderError(400, "Invalid request submitted to OpenAI API.")
        if isinstance(exc, openai.APIStatusError):
            status = exc.status_code
            if status >= 500:
                return ProviderError(502, f"OpenAI service error (HTTP {status}).")
            if status == 429:
                return ProviderError(429, "OpenAI rate limit exceeded.")
            return ProviderError(502, f"OpenAI API returned error HTTP {status}.")
        if isinstance(exc, openai.APIConnectionError):
            return ProviderError(502, "Unable to connect to OpenAI API.")
        return ProviderError(502, "An unexpected error occurred while communicating with OpenAI.")

    async def answer(
        self,
        query: str,
        image_b64: str,
        media_type: str,
        history: List[ChatMessage],
        system_prompt: str,
    ) -> str:
        self._ensure_client()
        messages = self._build_messages(query, image_b64, media_type, history, system_prompt)

        attempts = 0
        max_attempts = 2
        last_exc = None

        while attempts < max_attempts:
            attempts += 1
            try:
                response = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    max_tokens=1024,
                    timeout=30.0,
                )
                if response.choices and response.choices[0].message.content:
                    return response.choices[0].message.content
                return ""
            except (openai.RateLimitError, openai.APIStatusError, openai.APIConnectionError) as exc:
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
        messages = self._build_messages(query, image_b64, media_type, history, system_prompt)

        attempts = 0
        max_attempts = 2

        while attempts < max_attempts:
            attempts += 1
            try:
                response_stream = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    max_tokens=1024,
                    stream=True,
                    timeout=30.0,
                )
                async for chunk in response_stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return
            except (openai.RateLimitError, openai.APIStatusError, openai.APIConnectionError) as exc:
                if attempts < max_attempts:
                    await asyncio.sleep(1.0)
                else:
                    raise self._handle_exception(exc) from exc
            except Exception as exc:
                raise self._handle_exception(exc) from exc
