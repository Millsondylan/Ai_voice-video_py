from __future__ import annotations

import base64
from typing import Dict, List, Optional

from app.util.config import AppConfig


DEFAULT_SYSTEM_PROMPT = (
    "You are \"Glasses,\" a concise assistant that can see images but only uses them when necessary.\n"
    "Rules:\n"
    "• If the user's intent is normal chat (greeting, small talk, general Q&A), ignore images and reply normally.\n"
    "• If the user asks about the scene (\"what is this/that?\", \"read this\", \"what color…\", \"where is…\", \"look at…\") then analyze provided images and answer in ≤2 sentences.\n"
    "• For \"what is that/this\", assume the user points at the main focus/center. Identify just that item.\n"
    "• If unclear, ask one short clarifying question.\n"
    "• Don't comment on irrelevant background. Don't identify real people."
)


def build_system_prompt(config: AppConfig) -> str:
    return config.vlm_system_prompt or DEFAULT_SYSTEM_PROMPT


def build_vlm_payload(
    config: AppConfig,
    transcript: str,
    images_b64: List[str],
    history: Optional[List[Dict[str, str]]] = None,
) -> dict:
    system_prompt = build_system_prompt(config)
    transcript_clean = transcript.strip()
    history = history or []

    if config.vlm_model:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": [{"type": "text", "text": system_prompt}]})

        for turn in history:
            text = turn.get("text", "").strip()
            if not text:
                continue
            role = turn.get("role", "user")
            if role not in {"user", "assistant"}:
                role = "user"
            messages.append({"role": role, "content": [{"type": "text", "text": text}]})

        user_content = []
        if transcript_clean:
            user_content.append({"type": "text", "text": transcript_clean})
        else:
            # Only ask for scene description if images are provided
            if images_b64:
                user_content.append({"type": "text", "text": "Describe the scene succinctly."})
            else:
                user_content.append({"type": "text", "text": "Hello"})

        # Only add images if the list is non-empty
        if images_b64:
            user_content.extend({"type": "input_image", "image_base64": img} for img in images_b64)

        messages.append({"role": "user", "content": user_content})
        return {"model": config.vlm_model, "messages": messages}

    history_lines: List[str] = []
    for turn in history:
        text = turn.get("text", "").strip()
        if not text:
            continue
        role = turn.get("role", "user").title()
        history_lines.append(f"{role}: {text}")

    if transcript_clean:
        history_lines.append(f"User: {transcript_clean}")

    prompt = "\n".join(history_lines).strip()

    return {
        "images": images_b64,
        "prompt": prompt or transcript_clean,
        "system": system_prompt,
    }


def build_together_messages(
    config: AppConfig,
    transcript: str,
    images_b64: List[str],
    history: Optional[List[Dict[str, str]]] = None,
) -> List[dict]:
    system_prompt = build_system_prompt(config)
    messages: List[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    # Prepare images (resize and compress)
    prepared_images = _prepare_together_images(images_b64) if images_b64 else []

    transcript_clean = transcript.strip()
    history = history or []

    for turn in history:
        text = turn.get("text", "").strip()
        if not text:
            continue
        role = turn.get("role", "user")
        if role not in {"user", "assistant"}:
            role = "user"
        messages.append({"role": role, "content": text})

    # If no images: use simple string format (Together.ai expects string, not list)
    if not prepared_images:
        user_text = transcript_clean if transcript_clean else "Hello"
        messages.append({"role": "user", "content": user_text})
        return messages

    # If images present: use OpenAI-style vision format with content blocks
    user_content = []

    # Add transcript as text
    if transcript_clean:
        user_content.append({"type": "text", "text": transcript_clean})

    # Add images using proper vision API format
    for img_b64 in prepared_images:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
        })

    messages.append({"role": "user", "content": user_content})
    return messages


def _prepare_together_images(images_b64: List[str], max_images: int = 6, max_width: int = 960) -> List[str]:
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
