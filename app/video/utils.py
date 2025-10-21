from __future__ import annotations

import base64
from typing import List

import cv2
import numpy as np

from .validation import validate_numpy_frame, validate_opencv_to_base64


def center_crop(frame: np.ndarray, ratio: float) -> np.ndarray:
    """
    Crop frame to center portion specified by ratio.

    For ratio=0.38, crops to 38% of both width and height, centered.
    This simulates a "pointing focus" where the user is pointing at the center.

    Args:
        frame: Input video frame (numpy array)
        ratio: Portion of frame to keep (0.0 to 1.0)

    Returns:
        Center-cropped frame
    """
    if ratio <= 0 or ratio >= 1:
        raise ValueError("Crop ratio must be between 0 and 1 (exclusive)")

    height, width = frame.shape[:2]

    # Calculate crop dimensions
    crop_width = int(width * ratio)
    crop_height = int(height * ratio)

    # Calculate crop coordinates (centered)
    start_x = (width - crop_width) // 2
    start_y = (height - crop_height) // 2
    end_x = start_x + crop_width
    end_y = start_y + crop_height

    # Crop and return
    return frame[start_y:end_y, start_x:end_x]


def resize_frame(frame: np.ndarray, max_width: int) -> np.ndarray:
    """
    Resize frame to fit within max_width while maintaining aspect ratio.

    If frame is already smaller than max_width, returns unchanged.

    Args:
        frame: Input video frame
        max_width: Maximum width in pixels

    Returns:
        Resized frame
    """
    height, width = frame.shape[:2]
    if width <= max_width:
        return frame

    scale = max_width / float(width)
    new_size = (int(width * scale), int(height * scale))
    return cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)


def frame_to_jpeg_b64(frame: np.ndarray, quality: int = 85) -> str:
    """
    Convert numpy frame to JPEG and encode as base64 string.

    Uses JPEG instead of PNG for better compression and token efficiency.

    FIX Problem 8: Added validation to prevent encoding failures.

    Args:
        frame: Input video frame (numpy array)
        quality: JPEG quality (0-100, default 85)

    Returns:
        Base64-encoded JPEG string

    Raises:
        RuntimeError: If frame validation or encoding fails
    """
    # FIX Problem 8: Validate frame before encoding
    is_valid, msg = validate_numpy_frame(frame)
    if not is_valid:
        raise RuntimeError(f"Frame validation failed: {msg}")

    # Encode as JPEG with validation
    success, error_msg, size_bytes = validate_opencv_to_base64(frame)

    if not success:
        raise RuntimeError(f"Failed to encode frame: {error_msg}")

    # If validation passed, do actual encoding (already validated above)
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    success, buffer = cv2.imencode(".jpg", frame, encode_params)

    if not success:
        raise RuntimeError("Failed to encode frame as JPEG")

    # Convert to base64
    jpg_bytes = buffer.tobytes()
    b64_string = base64.b64encode(jpg_bytes).decode("utf-8")

    # Final validation
    if len(b64_string) == 0:
        raise RuntimeError("Base64 encoding resulted in empty string")

    return b64_string


def sample_frames(
    frames: List[np.ndarray],
    max_count: int,
    interval: int = 1
) -> List[np.ndarray]:
    """
    Sample frames from list at specified interval.

    Args:
        frames: List of video frames
        max_count: Maximum number of frames to return
        interval: Take every Nth frame (default 1 = all frames)

    Returns:
        Sampled list of frames
    """
    if not frames:
        return []

    sampled = frames[::interval]
    return sampled[:max_count]


def process_frames_for_vision(
    frames: List[np.ndarray],
    max_count: int = 6,
    crop_ratio: float = 0.38,
    max_width: int = 960,
    jpeg_quality: int = 85
) -> List[str]:
    """
    Process raw video frames for VLM inference.

    Pipeline:
    1. Sample up to max_count frames
    2. Center-crop each frame to crop_ratio
    3. Resize to max_width
    4. Encode as JPEG and convert to base64

    Args:
        frames: List of raw video frames
        max_count: Maximum frames to include
        crop_ratio: Center crop ratio (0.0 to 1.0)
        max_width: Maximum frame width in pixels
        jpeg_quality: JPEG compression quality

    Returns:
        List of base64-encoded JPEG strings
    """
    if not frames:
        return []

    # Sample frames evenly
    if len(frames) > max_count:
        interval = len(frames) // max_count
        sampled = sample_frames(frames, max_count, interval)
    else:
        sampled = frames[:max_count]

    processed_b64: List[str] = []
    for frame in sampled:
        try:
            # 1. Center crop
            cropped = center_crop(frame, crop_ratio)
            # 2. Resize
            resized = resize_frame(cropped, max_width)
            # 3. Encode to JPEG base64
            b64_str = frame_to_jpeg_b64(resized, quality=jpeg_quality)
            processed_b64.append(b64_str)
        except Exception as e:
            # Skip frames that fail processing
            print(f"Warning: Failed to process frame: {e}")
            continue

    return processed_b64
