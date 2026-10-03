from unittest.mock import patch
import pytest
from httpx import AsyncClient

from app.providers.base import ProviderError, VisionProvider
from app.providers.factory import get_provider, register_provider


class ErrorMockProvider(VisionProvider):
    """Mock provider configured to raise specific ProviderErrors for testing."""

    def __init__(self, error_to_raise: ProviderError):
        self.provider_name = "error_mock"
        self.error = error_to_raise

    async def answer(self, query, image_b64, media_type, history, system_prompt):
        raise self.error

    async def stream(self, query, image_b64, media_type, history, system_prompt):
        raise self.error
        yield ""  # generator requirement


def test_factory_invalid_provider():
    """Requesting an unknown provider must raise a 400 ProviderError."""
    with pytest.raises(ProviderError) as exc_info:
        get_provider(provider_name="nonexistent_provider")
    assert exc_info.value.status_code == 400
    assert "Unsupported provider" in exc_info.value.message


def test_factory_register_new_provider():
    """Tests dynamic registration of a new provider (single file extension requirement)."""
    class CustomNewProvider(VisionProvider):
        provider_name = "custom"
        async def answer(self, *args, **kwargs): return "Custom response"
        async def stream(self, *args, **kwargs): yield "Custom response"

    register_provider("custom", CustomNewProvider)
    provider = get_provider(provider_name="custom")
    assert provider.provider_name == "custom"


@pytest.mark.asyncio
async def test_mock_provider():
    """Verify built-in mock provider returns correct answer and stream tokens."""
    provider = get_provider(provider_name="mock")
    assert provider.provider_name == "mock"
    ans = await provider.answer("Test query", "b64", "image/png", [], "prompt")
    assert "Step 1:" in ans

    tokens = [t async for t in provider.stream("Test query", "b64", "image/png", [], "prompt")]
    assert len(tokens) > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code, expected_message",
    [
        (400, "Invalid image format sent to model."),
        (429, "Provider rate limit hit."),
        (502, "Upstream AI provider error."),
        (504, "Provider API timed out."),
    ],
)
async def test_provider_error_mapping(
    async_client: AsyncClient,
    headers: dict,
    valid_png_b64: str,
    status_code: int,
    expected_message: str,
):
    """Verify that ProviderError status codes are cleanly mapped to HTTP error responses."""
    error_provider = ErrorMockProvider(ProviderError(status_code, expected_message))

    payload = {
        "query": "Help",
        "image_b64": valid_png_b64,
        "media_type": "image/png",
    }

    with patch("app.services.assistant.get_provider", return_value=error_provider):
        response = await async_client.post("/ask", json=payload, headers=headers)
        assert response.status_code == status_code
        assert response.json()["detail"] == expected_message
