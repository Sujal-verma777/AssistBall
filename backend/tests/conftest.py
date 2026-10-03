import base64
import io
from typing import AsyncIterator, List, Optional
from unittest.mock import patch
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.config import settings
from app.main import app
from app.providers.base import VisionProvider
from app.schemas import ChatMessage
from app.security import rate_limiter


class DummyMockProvider(VisionProvider):
    """Mock VisionProvider for testing."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None, answer_text: str = "Step 1: Click the red button."):
        super().__init__(api_key=api_key, model_name=model_name)
        self.provider_name = "mock_provider"
        self.answer_text = answer_text

    async def answer(
        self,
        query: str,
        image_b64: str,
        media_type: str,
        history: List[ChatMessage],
        system_prompt: str,
    ) -> str:
        return self.answer_text

    async def stream(
        self,
        query: str,
        image_b64: str,
        media_type: str,
        history: List[ChatMessage],
        system_prompt: str,
    ) -> AsyncIterator[str]:
        words = self.answer_text.split(" ")
        for word in words:
            yield word + " "


@pytest.fixture(autouse=True)
def reset_rate_limiter_fixture():
    """Automatically reset rate limiter state before each test."""
    rate_limiter.reset()
    yield
    rate_limiter.reset()


@pytest.fixture
def valid_png_b64() -> str:
    """Generates a valid small 100x100 PNG image encoded in base64."""
    img = Image.new("RGB", (100, 100), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


@pytest.fixture
def valid_jpeg_b64() -> str:
    """Generates a valid 200x200 JPEG image encoded in base64."""
    img = Image.new("RGB", (200, 200), color="green")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


@pytest.fixture
def wide_image_b64() -> str:
    """Generates an image wider than 1568px (e.g. 2000x1000)."""
    img = Image.new("RGB", (2000, 1000), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


@pytest.fixture
def headers() -> dict:
    """Valid request headers containing X-API-Key."""
    return {"X-API-Key": settings.APP_API_KEY}


@pytest_asyncio.fixture
async def async_client() -> AsyncIterator[AsyncClient]:
    """Provides HTTPX AsyncClient bound to the FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_vision_provider():
    """Patches get_provider() to return a DummyMockProvider instance."""
    provider_inst = DummyMockProvider()
    with patch("app.services.assistant.get_provider", return_value=provider_inst):
        yield provider_inst
