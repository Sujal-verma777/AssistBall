import base64
import io
import pytest
from PIL import Image

from app.services.image_utils import ImageValidationError, validate_and_process_image


def test_small_png_preservation(valid_png_b64: str):
    """Small PNG (<= 512x512) should be preserved as PNG."""
    proc_b64, media_type = validate_and_process_image(valid_png_b64, "image/png")
    assert media_type == "image/png"
    assert isinstance(proc_b64, str)

    raw_bytes = base64.b64decode(proc_b64)
    img = Image.open(io.BytesIO(raw_bytes))
    assert img.format == "PNG"


def test_wide_image_resizing(wide_image_b64: str):
    """Images wider than 1568px must be resized to width=1568 while maintaining aspect ratio."""
    proc_b64, media_type = validate_and_process_image(wide_image_b64, "image/jpeg")
    assert media_type == "image/jpeg"

    raw_bytes = base64.b64decode(proc_b64)
    img = Image.open(io.BytesIO(raw_bytes))
    width, height = img.size
    assert width == 1568
    assert height == 784  # original 2000x1000 aspect ratio preserved


def test_invalid_base64():
    """Invalid base64 string must raise ImageValidationError."""
    with pytest.raises(ImageValidationError, match="Invalid base64"):
        validate_and_process_image("not-a-valid-base64-string!!!", "image/jpeg")


def test_non_image_payload():
    """Base64 string that is not an image (e.g. text) must raise ImageValidationError."""
    text_b64 = base64.b64encode(b"This is just raw text, not an image file.").decode("utf-8")
    with pytest.raises(ImageValidationError, match="not a valid image"):
        validate_and_process_image(text_b64, "image/jpeg")


def test_oversized_image_rejection():
    """Payload larger than 5 MB must raise ImageValidationError."""
    # Create 5.1 MB of dummy binary data
    oversized_data = b"0" * (5 * 1024 * 1024 + 100)
    oversized_b64 = base64.b64encode(oversized_data).decode("utf-8")
    with pytest.raises(ImageValidationError, match="exceeds maximum allowed limit of 5 MB"):
        validate_and_process_image(oversized_b64, "image/jpeg")
