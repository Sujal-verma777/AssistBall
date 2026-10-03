from typing import List, Literal, Optional
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field, field_validator


class ChatMessage(BaseModel):
    """Represents a single message in the conversation history."""
    role: Literal["user", "assistant"]
    content: str

    @field_validator("content")
    @classmethod
    def validate_content_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty.")
        return v.strip()


class AskRequest(BaseModel):
    """Request payload for /ask and /ask/stream endpoints."""
    query: str = Field(..., min_length=1, description="The question about the screenshot")
    image_b64: str = Field(..., min_length=1, description="Base64-encoded image string")
    media_type: Literal["image/jpeg", "image/png"] = Field(
        default="image/jpeg", description="MIME type of the screenshot"
    )
    history: List[ChatMessage] = Field(
        default_factory=list,
        max_length=10,
        description="Text-only conversation history, up to 10 turns",
    )
    session_id: Optional[str] = Field(
        default=None, description="Optional session identifier for tracking"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "query": "Where do I click to save this file?",
                "image_b64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                "media_type": "image/png",
                "history": [],
                "session_id": "test_session_1"
            }
        }
    }

    @field_validator("query", "image_b64")
    @classmethod
    def validate_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or whitespace only.")
        return v.strip()

    @field_validator("history")
    @classmethod
    def validate_history_length(cls, v: List[ChatMessage]) -> List[ChatMessage]:
        if len(v) > 10:
            raise ValueError("Conversation history cannot exceed 10 turns.")
        return v


class AskResponse(BaseModel):
    """Response payload for /ask endpoint."""
    answer: str
    provider: str
    latency_ms: int


class HealthResponse(BaseModel):
    """Response payload for /health endpoint."""
    status: str = "ok"
    provider: str


class ErrorResponse(BaseModel):
    """Structured error response schema."""
    detail: str


class SuggestRequest(BaseModel):
    """Request payload for /suggest endpoint."""
    image_b64: str = Field(..., min_length=1, description="Base64-encoded image string")
    media_type: Literal["image/jpeg", "image/png"] = Field(
        default="image/jpeg", description="MIME type of the screenshot"
    )
    session_id: Optional[str] = Field(
        default=None, description="Optional session identifier for tracking"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "image_b64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                "media_type": "image/png",
                "session_id": "test_suggest_1"
            }
        }
    }

    @field_validator("image_b64")
    @classmethod
    def validate_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or whitespace only.")
        return v.strip()


class SuggestResponse(BaseModel):
    """Response payload for /suggest endpoint."""
    suggestions: List[str]
    detected_app: str
    provider: str
    latency_ms: int

