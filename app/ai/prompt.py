from __future__ import annotations

import base64
import re
from typing import Dict, List, Optional, Sequence, Tuple

from app.util.config import AppConfig
from app.video.validation import validate_vision_message_format


DEFAULT_SYSTEM_PROMPT = (
    "You are \"Glasses,\" a concise assistant that can see images but only uses them when necessary.\n"
    "Rules:\n"
    "• If the user's intent is normal chat (greeting, small talk, general Q&A), ignore images and reply normally.\n"
    "• If the user asks about the scene (\"what is this/that?\", \"read this\", \"what color…\", \"where is…\", \"look at…\") then analyze provided images and answer in ≤2 sentences.\n"
    "• For \"what is that/this\", assume the user points at the main focus/center. Identify just that item.\n"
    "• If unclear, ask one short clarifying question.\n"
    "• Don't comment on irrelevant background. Don't identify real people."
)


_DATA_URI_RE = re.compile(r"^data:(?P<mime>[\w.+/-]+);base64,(?P<data>.+)$", re.IGNORECASE | re.DOTALL)


def _resolve_api_type(config: AppConfig) -> str:
    """Determine which vision message schema to generate."""
    provider = (config.vlm_provider or "").lower()
    model = (config.vlm_model or "").lower()

    if provider in {"anthropic", "claude"}:
        return "claude"
    if "anthropic" in model or model.startswith("claude"):
        return "claude"
    return "openai"


def _split_data_uri(image_b64: str) -> Tuple[str, str]:
    """Return (mime_type, base64_data) regardless of data URI presence."""
    match = _DATA_URI_RE.match(image_b64.strip())
    if match:
        return match.group("mime"), match.group("data")
    return "image/jpeg", image_b64.strip()


def _build_history_messages(
    history: Sequence[Dict[str, str]],
    *,
    api_type: str,
) -> List[Dict[str, object]]:
    """Convert history turns into API-specific message entries."""
    messages: List[Dict[str, object]] = []
    for turn in history:
        text = turn.get("text", "").strip()
        if not text:
            continue
        role = turn.get("role", "user")
        if role not in {"user", "assistant"}:
            role = "user"

        if api_type == "claude":
            messages.append({"role": role, "content": [{"type": "text", "text": text}]})
        else:
            messages.append({"role": role, "content": text})
    return messages


def _build_openai_user_message(transcript: str, images_b64: Sequence[str]) -> Dict[str, object]:
    """Create OpenAI-formatted user message supporting optional images."""
    cleaned_images = [img for img in images_b64 if img]
    user_text = transcript if transcript else ("Describe the scene succinctly." if cleaned_images else "Hello")

    if not cleaned_images:
        return {"role": "user", "content": user_text}

    content: List[Dict[str, object]] = [{"type": "text", "text": user_text}]
    for image_b64 in cleaned_images:
        mime_type, data = _split_data_uri(image_b64)
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{data}",
                    "detail": "high",
                },
            }
        )
    return {"role": "user", "content": content}


def _build_claude_user_message(transcript: str, images_b64: Sequence[str]) -> Dict[str, object]:
    """Create Anthropic Claude-formatted user message with optional images."""
    cleaned_images = [img for img in images_b64 if img]
    content: List[Dict[str, object]] = []

    for image_b64 in cleaned_images:
        mime_type, data = _split_data_uri(image_b64)
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": data,
                },
            }
        )

    user_text = transcript if transcript else ("Describe the scene succinctly." if cleaned_images else "Hello")
    content.append({"type": "text", "text": user_text})
    return {"role": "user", "content": content}


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

    api_type = _resolve_api_type(config)

    if config.vlm_model:
        messages: List[Dict[str, object]] = []

        if api_type == "claude":
            if system_prompt:
                messages.append({"role": "system", "content": [{"type": "text", "text": system_prompt}]})

            messages.extend(_build_history_messages(history, api_type=api_type))
            messages.append(_build_claude_user_message(transcript_clean, images_b64))

            is_valid, error_msg = validate_vision_message_format(messages, api_type=api_type)
            if not is_valid:
                raise ValueError(f"Invalid Claude vision payload: {error_msg}")

            return {"model": config.vlm_model, "messages": messages}

        # Default to OpenAI / OpenRouter schema
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.extend(_build_history_messages(history, api_type="openai"))
        messages.append(_build_openai_user_message(transcript_clean, images_b64))

        is_valid, error_msg = validate_vision_message_format(messages, api_type="openai")
        if not is_valid:
            raise ValueError(f"Invalid OpenAI vision payload: {error_msg}")

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
