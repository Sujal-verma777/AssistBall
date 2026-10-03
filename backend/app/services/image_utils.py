import base64
import io
import re
from typing import Tuple
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB limit
MAX_WIDTH = 1568  # Max width in pixels


class ImageValidationError(ValueError):
    """Custom exception raised when image validation or processing fails."""
    pass


def _normalize_base64_image(image_b64: str) -> str:
    """Normalizes common client-provided base64 variations into a valid payload."""
    if image_b64 is None:
        raise ImageValidationError("Image payload is required.")

    normalized = image_b64.strip()
    if not normalized:
        raise ImageValidationError("Image payload is empty.")

    if "," in normalized:
        normalized = normalized.split(",", 1)[1]

    normalized = re.sub(r"\s+", "", normalized)
    if "data:" in normalized:
        normalized = normalized.split("data:", 1)[1]
        if ";base64," in normalized:
            normalized = normalized.split(";base64,", 1)[1]

    # Some clients omit trailing padding. Add it back before decoding.
    padding = len(normalized) % 4
    if padding:
        normalized += "=" * (4 - padding)

    return normalized


def validate_and_process_image(image_b64: str, media_type: str) -> Tuple[str, str]:
    """
    Validates, resizes, and compresses base64-encoded screenshots.

    Args:
        image_b64: Base64-encoded string of the image.
        media_type: Declared MIME type ('image/jpeg' or 'image/png').

    Returns:
        Tuple of (processed_base64_string, final_media_type).

    Raises:
        ImageValidationError: If base64 is invalid, data is not a valid image, or size > 5 MB.
    """
    image_b64 = _normalize_base64_image(image_b64)

    # Decode base64
    try:
        raw_data = base64.b64decode(image_b64, validate=True)
    except Exception as exc:
        raise ImageValidationError("Invalid base64 encoding for image data.") from exc

    if not raw_data:
        raise ImageValidationError("Decoded image payload is empty.")

    # Reject > 5 MB
    if len(raw_data) > MAX_IMAGE_BYTES:
        raise ImageValidationError(
            f"Image size ({len(raw_data)} bytes) exceeds maximum allowed limit of 5 MB."
        )

    # Validate image using Pillow
    try:
        img_buffer = io.BytesIO(raw_data)
        image = Image.open(img_buffer)
        image.verify()
    except (UnidentifiedImageError, Exception) as exc:
        raise ImageValidationError("Payload is not a valid image file.") from exc

    # Re-open after verify() (verify invalidates the PIL Image instance)
    img_buffer.seek(0)
    image = Image.open(img_buffer)

    width, height = image.size

    # Check if small PNG (<= 512x512)
    is_small_png = (media_type == "image/png" and width <= 512 and height <= 512)

    # Resize if wider than 1568px while maintaining aspect ratio
    if width > MAX_WIDTH:
        new_width = MAX_WIDTH
        new_height = int(height * (MAX_WIDTH / width))
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    output_buffer = io.BytesIO()

    if is_small_png:
        final_media_type = "image/png"
        image.save(output_buffer, format="PNG", optimize=True)
    else:
        final_media_type = "image/jpeg"
        # Convert RGBA/Palette/Grayscale to RGB for JPEG compatibility
        if image.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        image.save(output_buffer, format="JPEG", quality=75, optimize=True)

    processed_bytes = output_buffer.getvalue()
    processed_b64 = base64.b64encode(processed_bytes).decode("utf-8")

    return processed_b64, final_media_type
