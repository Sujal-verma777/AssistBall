import asyncio
from typing import AsyncIterator, List, Optional
from app.providers.base import VisionProvider
from app.schemas import ChatMessage


class MockProvider(VisionProvider):
    """Mock provider for local testing and offline demos without external API calls."""

    provider_name: str = "mock"
    model_name: str = "mock-vision-v1"

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        super().__init__(api_key=api_key, model_name=model_name)

    async def answer(
        self,
        query: str,
        image_b64: str,
        media_type: str,
        history: List[ChatMessage],
        system_prompt: str,
    ) -> str:
        if "proactive screen analyzer" in system_prompt or "suggest" in query.lower():
            return '{"detected_app": "Desktop Application", "suggestions": ["How do I complete the action on screen?", "How to save or export current work?"]}'
        return (
            f"Step 1: Analyzed query '{query}'.\n"
            "Step 2: Located target element on screenshot.\n"
            "Step 3: Click the highlighted button to proceed."
        )

    async def stream(
        self,
        query: str,
        image_b64: str,
        media_type: str,
        history: List[ChatMessage],
        system_prompt: str,
    ) -> AsyncIterator[str]:
        tokens = [
            "Step 1: ",
            f"Analyzed query '{query}'.\n",
            "Step 2: ",
            "Located target element on screenshot.\n",
            "Step 3: ",
            "Click the highlighted button to proceed.",
        ]
        for token in tokens:
            await asyncio.sleep(0.05)
            yield token
