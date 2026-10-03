from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Optional
from app.schemas import ChatMessage


class ProviderError(Exception):
    """
    Standard exception for AI Vision Provider errors.

    Attributes:
        status_code: Suggested HTTP status code (400, 429, 502, 504).
        message: Clean error message suitable for client response.
    """
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"[{status_code}] {message}")


class VisionProvider(ABC):
    """Abstract base class for vision-capable LLM providers."""

    provider_name: str = "base"
    model_name: str = "default"

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        if model_name:
            self.model_name = model_name

    @abstractmethod
    async def answer(
        self,
        query: str,
        image_b64: str,
        media_type: str,
        history: List[ChatMessage],
        system_prompt: str,
    ) -> str:
        """
        Executes a vision query and returns the complete text response.
        """
        pass

    @abstractmethod
    async def stream(
        self,
        query: str,
        image_b64: str,
        media_type: str,
        history: List[ChatMessage],
        system_prompt: str,
    ) -> AsyncIterator[str]:
        """
        Executes a vision query and streams text tokens as they arrive.
        """
        pass
