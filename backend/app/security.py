import time
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Dict, List, Optional
from fastapi import Header, HTTPException, Request, status
from app.config import settings


class AbstractRateLimiter(ABC):
    """Abstract interface for rate limiting (supports in-memory, Redis, etc.)."""

    @abstractmethod
    async def is_allowed(self, client_id: str, max_requests: int, window_seconds: int = 60) -> bool:
        """Check if request from client_id is allowed within the rate limit window."""
        pass


class InMemoryRateLimiter(AbstractRateLimiter):
    """In-memory sliding window rate limiter."""

    def __init__(self):
        self._requests: Dict[str, List[float]] = defaultdict(list)

    async def is_allowed(self, client_id: str, max_requests: int, window_seconds: int = 60) -> bool:
        now = time.time()
        window_start = now - window_seconds

        # Filter out timestamps older than window_seconds
        timestamps = [ts for ts in self._requests[client_id] if ts > window_start]
        self._requests[client_id] = timestamps

        if len(timestamps) >= max_requests:
            return False

        self._requests[client_id].append(now)
        return True

    def reset(self):
        """Utility method to clear all rate limit records (useful for testing)."""
        self._requests.clear()


# Global rate limiter instance
rate_limiter = InMemoryRateLimiter()


async def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> str:
    """FastAPI dependency to validate X-API-Key header against APP_API_KEY."""
    if not x_api_key or x_api_key != settings.APP_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key header 'X-API-Key'.",
        )
    return x_api_key


async def enforce_rate_limit(request: Request) -> None:
    """FastAPI dependency to enforce per-client rate limit based on client IP."""
    client_ip = request.client.host if request.client else "unknown"

    allowed = await rate_limiter.is_allowed(
        client_id=client_ip,
        max_requests=settings.RATE_LIMIT_PER_MIN,
        window_seconds=60,
    )

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded ({settings.RATE_LIMIT_PER_MIN} requests/min). Please try again later.",
        )
