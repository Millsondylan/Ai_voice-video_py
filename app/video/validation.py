"""
FIX Problem 8: Vision processing pipeline validation.

According to diagnostic guide, vision failures occur when:
- Incorrect base64 encoding (wrong format or missing data)
- Unsupported image formats or sizes
- Corrupted image data
- Improper preprocessing

This module provides validation at each pipeline stage.
"""
import base64
import io
import os
from typing import Optional, Tuple

import cv2
import numpy as np

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None


def validate_image_path(image_path: str) -> Tuple[bool, str]:
    """Comprehensive validation before sending to API.

    Checks:
    - File exists
    - File not empty
    - File size reasonable (<20MB)

    Args:
        image_path: Path to image file

    Returns:
        (is_valid, error_message) tuple
    """
    # Check file exists
    if not os.path.exists(image_path):
        return False, "File does not exist"

    # Check file size
    file_size = os.path.getsize(image_path)
    if file_size == 0:
        return False, "File is empty"

    if file_size > 20 * 1024 * 1024:  # 20MB limit for most APIs
        return False, "File too large (>20MB)"

    return True, "Valid file"


def validate_image_content(image_path: str) -> Tuple[bool, str]:
    """Deep validation of image content using PIL if available.

    Args:
        image_path: Path to image file

    Returns:
        (is_valid, error_message) tuple
    """
    if not PIL_AVAILABLE:
        # Fallback to OpenCV validation
        try:
            img = cv2.imread(image_path)
            if img is None:
                return False, "Failed to load image with OpenCV"
            height, width = img.shape[:2]
            if width == 0 or height == 0:
                return False, "Invalid dimensions"
            return True, f"Valid image {width}x{height}"
        except Exception as e:
            return False, f"OpenCV validation failed: {str(e)}"

    try:
        # Validate with PIL
        img = Image.open(image_path)
        img.verify()

        # Reopen after verify (required by PIL)
        img = Image.open(image_path)
        img.load()  # Deep validation

        # Check dimensions
        width, height = img.size
        if width == 0 or height == 0:
            return False, "Invalid dimensions"

        # Check format
        valid_formats = ['JPEG', 'PNG', 'GIF', 'BMP', 'WEBP']
        if img.format not in valid_formats:
            return False, f"Unsupported format: {img.format}"

    return True, f"Valid {img.format} {width}x{height}"

    except Exception as e:
        return False, f"Validation failed: {str(e)}"


def validate_image_for_api(image_path: str) -> Tuple[bool, str]:
    """
    Comprehensive validation before sending image to a vision API.

    Combines filesystem checks with deep content validation so callers can
    catch issues (missing file, zero-byte file, unsupported format, corrupted
    data) before attempting to encode/submit the image.
    """
    path_ok, path_msg = validate_image_path(image_path)
    if not path_ok:
        return False, path_msg

    content_ok, content_msg = validate_image_content(image_path)
    if not content_ok:
        return False, content_msg

    return True, content_msg


def validate_numpy_frame(frame: np.ndarray) -> Tuple[bool, str]:
    """Validate numpy array frame before encoding.

    Args:
        frame: Numpy array representing image

    Returns:
        (is_valid, error_message) tuple
    """
    if frame is None:
        return False, "Frame is None"

    if frame.size == 0:
        return False, "Frame is empty"

    if len(frame.shape) < 2:
        return False, "Frame has invalid shape"

    height, width = frame.shape[:2]
    if width == 0 or height == 0:
        return False, "Frame has zero dimensions"

    return True, f"Valid frame {width}x{height}"


def validate_base64_image(base64_string: str) -> Tuple[bool, str]:
    """Validate base64 encoded image data.

    Checks:
    - Valid base64 encoding
    - Decodable to image
    - Image has valid dimensions

    Args:
        base64_string: Base64-encoded image string

    Returns:
        (is_valid, error_message) tuple
    """
    if not base64_string:
        return False, "Empty base64 string"

    try:
        # Decode base64
        img_bytes = base64.b64decode(base64_string)

        if len(img_bytes) == 0:
            return False, "Decoded image is empty"

        # Try to load as image
        if PIL_AVAILABLE:
            img = Image.open(io.BytesIO(img_bytes))
            img.verify()

            img = Image.open(io.BytesIO(img_bytes))
            img.load()

            width, height = img.size
            return True, f"Valid base64 image {img.format} {width}x{height}"
        else:
            # Fallback to OpenCV
            np_buffer = np.frombuffer(img_bytes, dtype=np.uint8)
            img = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)

            if img is None:
                return False, "Failed to decode image from base64"

            height, width = img.shape[:2]
            return True, f"Valid base64 image {width}x{height}"

    except base64.binascii.Error:
        return False, "Invalid base64 encoding"
    except Exception as e:
        return False, f"Invalid image data: {str(e)}"


def validate_opencv_to_base64(cv_image: np.ndarray) -> Tuple[bool, str, int]:
    """Validate OpenCV frame can be encoded to base64.

    Args:
        cv_image: OpenCV numpy array

    Returns:
        (success, error_message, size_bytes) tuple
    """
    # First validate the frame itself
    is_valid, msg = validate_numpy_frame(cv_image)
    if not is_valid:
        return False, msg, 0

    try:
        # Try encoding to JPEG
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, 85]
        success, buffer = cv2.imencode('.jpg', cv_image, encode_params)

        if not success:
            return False, "Failed to encode frame as JPEG", 0

        # Validate buffer
        if len(buffer) == 0:
            return False, "Encoded buffer is empty", 0

        # Convert to base64
        base64_string = base64.b64encode(buffer.tobytes()).decode('utf-8')

        if len(base64_string) == 0:
            return False, "Base64 string is empty", 0

        size_bytes = len(base64_string)
        return True, f"Successfully encoded {size_bytes} bytes", size_bytes

    except Exception as e:
        return False, f"Encoding failed: {str(e)}", 0


def encode_pil_to_base64(pil_image, format: str = "JPEG", quality: int = 85) -> Tuple[Optional[str], bool, str]:
    """Encode PIL Image to base64 string.

    Args:
        pil_image: PIL Image instance to encode
        format: Output format (default JPEG)
        quality: JPEG/WebP quality (0-100)

    Returns:
        (base64_str, success, message)
    """
    if not PIL_AVAILABLE:
        return None, False, "Pillow not installed"

    try:
        buffer = io.BytesIO()
        image_to_save = pil_image

        if format.upper() == "JPEG" and pil_image.mode != "RGB":
            image_to_save = pil_image.convert("RGB")

        image_to_save.save(buffer, format=format, quality=quality)
        buffer.seek(0)

        base64_string = base64.b64encode(buffer.getvalue()).decode("utf-8")
        if not base64_string:
            return None, False, "Encoded base64 string is empty"

        return base64_string, True, "Success"
    except Exception as exc:
        return None, False, f"Exception during encoding: {exc}"


def validate_vision_message_format(messages: list, api_type: str = "openai") -> Tuple[bool, str]:
    """Validate vision API message structure.

    Checks that messages follow proper OpenAI format:
    - Content is list for images
    - Image URLs have proper nested structure
    - Base64 data is valid

    Args:
        messages: List of message dicts

    Returns:
        (is_valid, error_message) tuple
    """
    api = (api_type or "openai").lower()
    for msg in messages:
        if 'role' not in msg or 'content' not in msg:
            return False, "Message missing role or content"

        content = msg['content']

        # If content is a list, validate structure
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    return False, "Content item must be dict"

                if 'type' not in item:
                    return False, "Content item missing type"

                if item['type'] == 'text':
                    if 'text' not in item or not isinstance(item['text'], str):
                        return False, "Text content missing text field"
                    continue

                if api == "claude":
                    if item['type'] != 'image':
                        return False, f"Unsupported content type '{item['type']}' for Claude"
                    source = item.get('source')
                    if not isinstance(source, dict):
                        return False, "Claude image content must include source dict"
                    for required_key in ('type', 'media_type', 'data'):
                        if required_key not in source:
                            return False, f"Claude image source missing '{required_key}'"
                    if source['type'] != 'base64':
                        return False, "Claude image source type must be 'base64'"
                    if not isinstance(source['data'], str) or not source['data']:
                        return False, "Claude image source data must be non-empty base64 string"
                    if not isinstance(source['media_type'], str) or not source['media_type'].startswith("image/"):
                        return False, "Claude image media_type must start with 'image/'"
                else:
                    if item['type'] != 'image_url':
                        return False, f"Unsupported content type '{item['type']}' for OpenAI"

                    image_url = item.get('image_url')
                    if not isinstance(image_url, dict):
                        return False, "image_url must be nested dict"

                    url = image_url.get('url')
                    if not isinstance(url, str) or not url.startswith('data:image/'):
                        return False, "image_url dict must contain data URI url"

    return True, "Valid message structure"
