import logging
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from app.config import settings
from app.providers.base import ProviderError
from app.providers.factory import get_provider
from app.schemas import AskRequest, AskResponse, ErrorResponse, HealthResponse, SuggestRequest, SuggestResponse
from app.security import enforce_rate_limit, verify_api_key
from app.services.assistant import process_ask, process_ask_stream, process_suggest
from app.services.image_utils import ImageValidationError

# Configure logger for AssistBall application
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",  # Print JSON messages cleanly
)
logger = logging.getLogger("assistball")

app = FastAPI(
    title="AssistBall Backend",
    description="Vision AI Assistant backend for AssistBall desktop application",
    version="1.0.0",
)

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ImageValidationError)
async def image_validation_exception_handler(request: Request, exc: ImageValidationError):
    """Map image validation errors to clean 400 Bad Request responses."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


@app.exception_handler(ProviderError)
async def provider_exception_handler(request: Request, exc: ProviderError):
    """Map provider errors to clean HTTP responses (400, 429, 502, 504)."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


@app.get(
    "/",
    summary="API overview",
    tags=["System"],
)
async def api_root():
    """Returns a lightweight status payload for the backend root URL."""
    return {
        "status": "ok",
        "service": "AssistBall Backend",
        "docs": "/docs",
        "endpoints": ["/health", "/suggest", "/ask", "/ask/stream"],
    }


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check endpoint",
    tags=["System"],
)
async def health_check():
    """Returns application status and active provider name. Unauthenticated."""
    try:
        active_provider = get_provider().provider_name
    except Exception:
        active_provider = settings.PROVIDER or "unknown"

    return HealthResponse(status="ok", provider=active_provider)


@app.post(
    "/analyze",
    response_model=AskResponse,
    include_in_schema=False,
    responses={
        400: {"model": ErrorResponse, "description": "Bad input or invalid image"},
        401: {"model": ErrorResponse, "description": "Invalid or missing X-API-Key"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        502: {"model": ErrorResponse, "description": "Provider failure"},
        504: {"model": ErrorResponse, "description": "Provider timeout"},
    },
    dependencies=[Depends(verify_api_key), Depends(enforce_rate_limit)],
    summary="Backward-compatible alias for image analysis requests",
    tags=["Assistant"],
)
async def analyze(request: AskRequest):
    """Backward-compatible alias kept for older clients that still call /analyze."""
    return await process_ask(request)


@app.post(
    "/suggest",
    response_model=SuggestResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Bad input or invalid image"},
        401: {"model": ErrorResponse, "description": "Invalid or missing X-API-Key"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        502: {"model": ErrorResponse, "description": "Provider failure"},
        504: {"model": ErrorResponse, "description": "Provider timeout"},
    },
    dependencies=[Depends(verify_api_key), Depends(enforce_rate_limit)],
    summary="Generate 2 smart screen suggestions based on screenshot context",
    tags=["Assistant"],
)
async def suggest(request: SuggestRequest):
    """Analyzes screenshot context and returns 2 smart suggested actions/questions."""
    return await process_suggest(request)


@app.post(
    "/ask",
    response_model=AskResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Bad input or invalid image"},
        401: {"model": ErrorResponse, "description": "Invalid or missing X-API-Key"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        502: {"model": ErrorResponse, "description": "Provider failure"},
        504: {"model": ErrorResponse, "description": "Provider timeout"},
    },
    dependencies=[Depends(verify_api_key), Depends(enforce_rate_limit)],
    summary="Execute vision query and return step-by-step help",
    tags=["Assistant"],
)
async def ask(request: AskRequest):
    """Processes a screenshot and query, returning the assistant's response."""
    return await process_ask(request)


@app.post(
    "/ask/stream",
    responses={
        200: {"description": "Server-Sent Events (SSE) stream"},
        401: {"model": ErrorResponse, "description": "Invalid or missing X-API-Key"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    dependencies=[Depends(verify_api_key), Depends(enforce_rate_limit)],
    summary="Stream vision query answer tokens via SSE",
    tags=["Assistant"],
)
async def ask_stream(request: AskRequest):
    """Streams answer tokens as Server-Sent Events (SSE)."""
    return StreamingResponse(
        process_ask_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

