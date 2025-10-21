from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import cv2

try:
    import numpy as np
except ImportError:  # pragma: no cover - numpy required for vision mode
    np = None  # type: ignore[assignment]

try:
    from PIL import Image
except ImportError:  # pragma: no cover - pillow required for preprocessing
    Image = None  # type: ignore[assignment]

from app.ai.prompt import create_vision_message_from_base64
from .validation import (
    encode_pil_to_base64,
    validate_base64_image,
    validate_image_for_api,
    validate_numpy_frame,
)


def capture_image_reliable(camera_index: int = 0, filename: Optional[str] = None):
    """
    Robust camera capture with warm-up and validation.

    Returns:
        Captured frame as numpy array or None if capture failed.
    """
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        return None

    try:
        # Allow auto-exposure to settle
        time.sleep(2.0)
        for _ in range(10):
            cap.read()

        ret, frame = cap.read()
        if not ret or frame is None or (np is not None and frame.size == 0):
            return None

        if filename:
            try:
                cv2.imwrite(filename, frame)
            except Exception:
                # Best-effort save; continue even if writing fails
                pass

        return frame
    finally:
        cap.release()


def preprocess_for_vision_api(
    image_path: str,
    max_size: Tuple[int, int] = (1024, 1024),
    quality: int = 85,
    image_format: str = "JPEG",
):
    """
    Complete preprocessing pipeline for vision APIs.

    - Opens and verifies the image
    - Converts to RGB (removing alpha)
    - Resizes while maintaining aspect ratio
    - Optimizes for upload
    """
    if Image is None:
        return None

    try:
        image = Image.open(image_path)
        image.verify()

        image = Image.open(image_path)

        if image.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            alpha = image.split()[-1] if "A" in image.mode else None
            background.paste(image, mask=alpha)
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        image.thumbnail(max_size, Image.LANCZOS)

        # Saving to a temporary buffer ensures optimizations are applied
        temp_buffer = tempfile.SpooledTemporaryFile()
        image.save(temp_buffer, format=image_format, quality=quality, optimize=True)
        temp_buffer.seek(0)

        processed = Image.open(temp_buffer)
        processed.load()
        return processed
    except Exception:
        return None


def _infer_mime_type(image_path: str) -> str:
    extension = Path(image_path).suffix.lower().lstrip(".")
    mime_map = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
        "bmp": "image/bmp",
    }
    return mime_map.get(extension, "image/jpeg")


class VisionPipeline:
    """
    Complete pipeline from camera/image file to API-ready message payload.

    This integrates validation at each stage to eliminate the common causes
    of "vision message missing image" and similar runtime failures.
    """

    def __init__(self, api_type: str = "openai", prompt: str = "What do you see in this image?") -> None:
        self.api_type = api_type.lower()
        self.prompt = prompt

    def process_image(self, image_path: str, *, mime_type: Optional[str] = None) -> Dict[str, object]:
        """
        Validate and prepare an image from disk for the configured API.

        Returns:
            Dict containing `messages`, `base64_image`, and metadata about processing.
        """
        validation_ok, validation_msg = validate_image_for_api(image_path)
        if not validation_ok:
            return {"success": False, "error": f"Validation failed: {validation_msg}"}

        processed = preprocess_for_vision_api(image_path)
        if processed is None:
            return {"success": False, "error": "Preprocessing failed"}

        base64_image, success, encode_msg = encode_pil_to_base64(processed)
        if not success or not base64_image:
            return {"success": False, "error": f"Encoding failed: {encode_msg}"}

        valid_b64, b64_msg = validate_base64_image(base64_image)
        if not valid_b64:
            return {"success": False, "error": f"Base64 validation failed: {b64_msg}"}

        resolved_mime = mime_type or _infer_mime_type(image_path)
        messages = create_vision_message_from_base64(
            self.prompt,
            base64_image,
            mime_type=resolved_mime,
            api_type=self.api_type,
        )

        width, height = processed.size
        return {
            "success": True,
            "messages": messages,
            "base64_image": base64_image,
            "meta": {
                "image_path": image_path,
                "width": width,
                "height": height,
                "mime_type": resolved_mime,
                "base64_chars": len(base64_image),
            },
        }

    def capture_and_process(self, camera_index: int = 0) -> Dict[str, object]:
        """
        Capture from camera and return API-ready payload.

        Returns:
            Dict with success flag, messages, and diagnostics.
        """
        if np is None:
            return {"success": False, "error": "NumPy not installed; required for camera capture"}

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            temp_path = Path(tmp.name)

        try:
            frame = capture_image_reliable(camera_index, str(temp_path))
            if frame is None:
                return {"success": False, "error": "Camera capture failed"}

            frame_valid, frame_msg = validate_numpy_frame(frame)
            if not frame_valid:
                return {"success": False, "error": f"Captured frame invalid: {frame_msg}"}

            result = self.process_image(str(temp_path))
            if not result.get("success"):
                return result

            result.setdefault("meta", {})
            result["meta"]["camera_index"] = camera_index
            return result
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass
