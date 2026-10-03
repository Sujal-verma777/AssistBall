import pytest
from httpx import AsyncClient
from app.config import settings


@pytest.mark.asyncio
async def test_auth_missing_header(async_client: AsyncClient, valid_png_b64: str):
    """Request without X-API-Key header should fail with 401 Unauthorized."""
    payload = {
        "query": "Test query",
        "image_b64": valid_png_b64,
        "media_type": "image/png",
    }
    response = await async_client.post("/ask", json=payload)
    assert response.status_code == 401
    assert "Invalid or missing API key" in response.json()["detail"]


@pytest.mark.asyncio
async def test_auth_invalid_header(async_client: AsyncClient, valid_png_b64: str):
    """Request with incorrect X-API-Key header should fail with 401 Unauthorized."""
    payload = {
        "query": "Test query",
        "image_b64": valid_png_b64,
        "media_type": "image/png",
    }
    headers = {"X-API-Key": "invalid-secret-key"}
    response = await async_client.post("/ask", json=payload, headers=headers)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_rate_limiting(
    async_client: AsyncClient, headers: dict, valid_png_b64: str, mock_vision_provider
):
    """Exceeding RATE_LIMIT_PER_MIN requests within window must return 429 Too Many Requests."""
    payload = {
        "query": "Rate limit test",
        "image_b64": valid_png_b64,
        "media_type": "image/png",
    }

    # Send up to allowed limit
    limit = settings.RATE_LIMIT_PER_MIN
    for _ in range(limit):
        res = await async_client.post("/ask", json=payload, headers=headers)
        assert res.status_code == 200

    # The next request should be blocked by rate limit
    exceeded_res = await async_client.post("/ask", json=payload, headers=headers)
    assert exceeded_res.status_code == 429
    assert "Rate limit exceeded" in exceeded_res.json()["detail"]
