import json
import logging
import time
from datetime import datetime, timezone
from typing import AsyncIterator, Tuple
from app.prompts import SUGGEST_PROMPT, SYSTEM_PROMPT
from app.providers.base import ProviderError
from app.providers.factory import get_provider
from app.schemas import AskRequest, AskResponse, SuggestRequest, SuggestResponse
from app.services.image_utils import ImageValidationError, validate_and_process_image

logger = logging.getLogger("assistball")


def log_structured_event(
    session_id: str | None,
    query_length: int,
    image_size_bytes: int,
    provider: str,
    latency_ms: int,
    status: str,
) -> None:
    """Log structured metadata for audit and observability (No image or prompt leaks)."""
    log_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id or "anonymous",
        "query_length": query_length,
        "image_size_bytes": image_size_bytes,
        "provider": provider,
        "latency_ms": latency_ms,
        "status": status,
    }
    logger.info(json.dumps(log_payload))


async def process_ask(request: AskRequest) -> AskResponse:
    """
    Orchestrates the /ask endpoint logic.

    1. Validates and resizes/compresses image.
    2. Instantiates active vision provider.
    3. Executes answer call.
    4. Records structured execution metrics.
    """
    start_time = time.perf_counter()

    # 1. Validate & process image
    processed_b64, final_media_type = validate_and_process_image(
        request.image_b64, request.media_type
    )

    # Calculate image size in bytes after base64 decoding approximation
    image_size_bytes = len(processed_b64) * 3 // 4

    # 2. Get provider
    provider_inst = get_provider()
    provider_name = provider_inst.provider_name

    try:
        # 3. Call provider
        answer_text = await provider_inst.answer(
            query=request.query,
            image_b64=processed_b64,
            media_type=final_media_type,
            history=request.history,
            system_prompt=SYSTEM_PROMPT,
        )
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        # 4. Log structured success
        log_structured_event(
            session_id=request.session_id,
            query_length=len(request.query),
            image_size_bytes=image_size_bytes,
            provider=provider_name,
            latency_ms=latency_ms,
            status="success",
        )

        return AskResponse(
            answer=answer_text,
            provider=provider_name,
            latency_ms=latency_ms,
        )

    except (ImageValidationError, ProviderError) as exc:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        log_structured_event(
            session_id=request.session_id,
            query_length=len(request.query),
            image_size_bytes=image_size_bytes,
            provider=provider_name,
            latency_ms=latency_ms,
            status=f"error_{getattr(exc, 'status_code', 400)}",
        )
        raise exc
    except Exception as exc:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        log_structured_event(
            session_id=request.session_id,
            query_length=len(request.query),
            image_size_bytes=image_size_bytes,
            provider=provider_name,
            latency_ms=latency_ms,
            status="error_502",
        )
        raise ProviderError(502, "An internal error occurred while processing the assistant request.") from exc


async def process_ask_stream(request: AskRequest) -> AsyncIterator[str]:
    """
    Orchestrates the /ask/stream endpoint SSE generator.

    Yields formatted Server-Sent Events (SSE):
    - event: token, data: {"token": "..."}
    - event: done, data: {"answer": "...", "provider": "...", "latency_ms": 123}
    - event: error, data: {"error": "..."}
    """
    start_time = time.perf_counter()
    accumulated_tokens = []
    provider_name = "unknown"
    image_size_bytes = 0

    try:
        # 1. Process image
        processed_b64, final_media_type = validate_and_process_image(
            request.image_b64, request.media_type
        )
        image_size_bytes = len(processed_b64) * 3 // 4

        # 2. Get provider
        provider_inst = get_provider()
        provider_name = provider_inst.provider_name

        # 3. Stream tokens from provider
        token_stream = provider_inst.stream(
            query=request.query,
            image_b64=processed_b64,
            media_type=final_media_type,
            history=request.history,
            system_prompt=SYSTEM_PROMPT,
        )

        async for token in token_stream:
            accumulated_tokens.append(token)
            data_json = json.dumps({"token": token})
            yield f"event: token\ndata: {data_json}\n\n"

        full_answer = "".join(accumulated_tokens)
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        log_structured_event(
            session_id=request.session_id,
            query_length=len(request.query),
            image_size_bytes=image_size_bytes,
            provider=provider_name,
            latency_ms=latency_ms,
            status="success",
        )

        done_payload = json.dumps({
            "answer": full_answer,
            "provider": provider_name,
            "latency_ms": latency_ms,
        })
        yield f"event: done\ndata: {done_payload}\n\n"

    except ImageValidationError as exc:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        log_structured_event(
            session_id=request.session_id,
            query_length=len(request.query),
            image_size_bytes=image_size_bytes,
            provider=provider_name,
            latency_ms=latency_ms,
            status="error_400",
        )
        err_payload = json.dumps({"error": str(exc)})
        yield f"event: error\ndata: {err_payload}\n\n"

    except ProviderError as exc:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        log_structured_event(
            session_id=request.session_id,
            query_length=len(request.query),
            image_size_bytes=image_size_bytes,
            provider=provider_name,
            latency_ms=latency_ms,
            status=f"error_{exc.status_code}",
        )
        err_payload = json.dumps({"error": exc.message})
        yield f"event: error\ndata: {err_payload}\n\n"

    except Exception as exc:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        log_structured_event(
            session_id=request.session_id,
            query_length=len(request.query),
            image_size_bytes=image_size_bytes,
            provider=provider_name,
            latency_ms=latency_ms,
            status="error_502",
        )
        err_payload = json.dumps({"error": "An internal error occurred during streaming."})
        yield f"event: error\ndata: {err_payload}\n\n"


async def process_suggest(request: SuggestRequest) -> SuggestResponse:
    """
    Orchestrates the /suggest endpoint logic to generate 2 smart suggestions based on screen context.
    """
    start_time = time.perf_counter()

    # 1. Validate & process image
    processed_b64, final_media_type = validate_and_process_image(
        request.image_b64, request.media_type
    )
    image_size_bytes = len(processed_b64) * 3 // 4

    # 2. Get provider
    provider_inst = get_provider()
    provider_name = provider_inst.provider_name

    try:
        # 3. Query provider with SUGGEST_PROMPT
        raw_response = await provider_inst.answer(
            query="Analyze screen and suggest top 2 tasks or questions.",
            image_b64=processed_b64,
            media_type=final_media_type,
            history=[],
            system_prompt=SUGGEST_PROMPT,
        )

        # Parse JSON output from LLM (strip markdown code blocks if present)
        cleaned = raw_response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned.split("```json", 1)[1]
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        parsed = json.loads(cleaned)
        suggestions = parsed.get("suggestions", [])
        detected_app = parsed.get("detected_app", "Active Screen")

        # Fallback if AI returned empty or invalid suggestion list length
        if not isinstance(suggestions, list) or len(suggestions) < 2:
            suggestions = [
                "How do I complete the action on screen?",
                "How to save or export current work?"
            ]
        else:
            suggestions = [str(s) for s in suggestions[:2]]

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        log_structured_event(
            session_id=request.session_id,
            query_length=0,
            image_size_bytes=image_size_bytes,
            provider=provider_name,
            latency_ms=latency_ms,
            status="suggest_success",
        )

        return SuggestResponse(
            suggestions=suggestions,
            detected_app=detected_app,
            provider=provider_name,
            latency_ms=latency_ms,
        )

    except (ImageValidationError, ProviderError) as exc:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        log_structured_event(
            session_id=request.session_id,
            query_length=0,
            image_size_bytes=image_size_bytes,
            provider=provider_name,
            latency_ms=latency_ms,
            status=f"error_{getattr(exc, 'status_code', 400)}",
        )
        raise exc
    except Exception:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        log_structured_event(
            session_id=request.session_id,
            query_length=0,
            image_size_bytes=image_size_bytes,
            provider=provider_name,
            latency_ms=latency_ms,
            status="error_502",
        )
        # Fallback response in case JSON parsing fails
        return SuggestResponse(
            suggestions=[
                "How do I complete the action on screen?",
                "How to save or export current work?"
            ],
            detected_app="Active Screen",
            provider=provider_name,
            latency_ms=latency_ms,
        )

