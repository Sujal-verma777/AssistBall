import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(async_client: AsyncClient):
    """Test that /health returns 200 OK without requiring an X-API-Key."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "provider" in data


@pytest.mark.asyncio
async def test_ask_endpoint_success(
    async_client: AsyncClient, headers: dict, valid_png_b64: str, mock_vision_provider
):
    """Test POST /ask with valid auth, payload, and mocked provider."""
    payload = {
        "query": "Where do I click?",
        "image_b64": valid_png_b64,
        "media_type": "image/png",
        "history": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "How can I help?"},
        ],
        "session_id": "test-session-123",
    }

    response = await async_client.post("/ask", json=payload, headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert "answer" in data
    assert data["answer"] == "Step 1: Click the red button."
    assert data["provider"] == "mock_provider"
    assert isinstance(data["latency_ms"], int)
    assert data["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_ask_stream_endpoint_success(
    async_client: AsyncClient, headers: dict, valid_jpeg_b64: str, mock_vision_provider
):
    """Test POST /ask/stream with valid payload yielding SSE tokens."""
    payload = {
        "query": "How do I proceed?",
        "image_b64": valid_jpeg_b64,
        "media_type": "image/jpeg",
        "history": [],
        "session_id": "test-stream-session",
    }

    response = await async_client.post("/ask/stream", json=payload, headers=headers)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    body = response.text
    assert "event: token" in body
    assert "event: done" in body
    assert "Step 1:" in body
    assert "mock_provider" in body


@pytest.mark.asyncio
async def test_suggest_endpoint_success(
    async_client: AsyncClient, headers: dict, valid_png_b64: str
):
    """Test POST /suggest returning 2 smart screen suggestions."""
    payload = {
        "image_b64": valid_png_b64,
        "media_type": "image/png",
        "session_id": "test-suggest-session",
    }

    response = await async_client.post("/suggest", json=payload, headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert "suggestions" in data
    assert isinstance(data["suggestions"], list)
    assert len(data["suggestions"]) == 2
    assert "detected_app" in data
    assert "provider" in data
    assert isinstance(data["latency_ms"], int)

