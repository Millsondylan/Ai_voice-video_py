from __future__ import annotations

import base64
from typing import List

from app.util.config import AppConfig


DEFAULT_SYSTEM_PROMPT = (
    "You are “Glasses,” a concise vision assistant.\n"
    "Only describe what you can confirm from the provided images; use the transcript solely to understand the user's question.\n"
    "Answer in 1–2 sentences, focusing on the visual evidence. If the images do not clearly answer the question, state that the view is inconclusive.\n"
    "Do not speculate, guess, or identify people. Be factual, neutral, and brief."
)


def build_system_prompt(config: AppConfig) -> str:
    return config.vlm_system_prompt or DEFAULT_SYSTEM_PROMPT


def build_vlm_payload(config: AppConfig, transcript: str, images_b64: List[str]) -> dict:
    system_prompt = build_system_prompt(config)
    transcript_clean = transcript.strip()

    if config.vlm_model:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": [{"type": "text", "text": system_prompt}]})

        user_content = []
        if transcript_clean:
            user_content.append({"type": "text", "text": transcript_clean})
        else:
            user_content.append({"type": "text", "text": "Describe the scene succinctly."})

        user_content.extend({"type": "input_image", "image_base64": img} for img in images_b64)
        messages.append({"role": "user", "content": user_content})
        return {"model": config.vlm_model, "messages": messages}

    return {
        "images": images_b64,
        "prompt": transcript_clean,
        "system": system_prompt,
    }


def build_together_messages(config: AppConfig, transcript: str, images_b64: List[str]) -> List[dict]:
    system_prompt = build_system_prompt(config)
    messages: List[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    prepared_images = _prepare_together_images(images_b64)

    user_lines: List[str] = []
    transcript_clean = transcript.strip()
    if transcript_clean:
        user_lines.append(f"User transcript:\n{transcript_clean}")
    else:
        user_lines.append("No transcript text captured. Please analyze the images.")

    if prepared_images:
        frame_lines = ["Attached frames (data:image/jpeg;base64, ...):"]
        for idx, img in enumerate(prepared_images, start=1):
            frame_lines.append(f"[Frame {idx}] data:image/jpeg;base64,{img}")
        dropped = len(images_b64) - len(prepared_images)
        if dropped > 0:
            frame_lines.append(f"(Dropped {dropped} additional frame(s) to stay within context limits.)")
        user_lines.append("\n".join(frame_lines))
    else:
        user_lines.append("No frames captured from the segment.")

    messages.append({"role": "user", "content": "\n\n".join(user_lines)})
    return messages


def _prepare_together_images(images_b64: List[str], max_images: int = 4, max_width: int = 512) -> List[str]:
    prepared: List[str] = []
    for raw_b64 in images_b64[:max_images]:
        processed = _compress_base64_image(raw_b64, max_width=max_width, quality=80)
        prepared.append(processed)
    return prepared


def _compress_base64_image(image_b64: str, *, max_width: int, quality: int) -> str:
    """Decode, downscale, and JPEG-compress a base64 PNG string to save tokens."""
    try:
        import cv2  # Lazy import to avoid mandatory dependency when unused
        import numpy as np

        image_bytes = base64.b64decode(image_b64)
        np_buffer = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)
        if image is None:
            return image_b64

        height, width = image.shape[:2]
        if width > max_width:
            scale = max_width / float(width)
            new_size = (int(width * scale), int(height * scale))
            image = cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)

        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        success, buffer = cv2.imencode(".jpg", image, encode_params)
        if not success:
            return image_b64
        return base64.b64encode(buffer.tobytes()).decode("utf-8")
    except Exception:
        return image_b64
