from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from app.ai.vlm_client import VLMClient
from app.util.config import AppConfig
from app.util.intent import wants_vision
from app.util.text import strip_scene_preface
from app.video.utils import process_frames_for_vision


def route_and_respond(
    config: AppConfig,
    vlm_client: VLMClient,
    transcript: str,
    segment_frames: List[np.ndarray],
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Route request based on intent and call VLM with/without images.

    This is the core chat-first routing logic:
    1. Determine if user's intent requires vision
    2. If yes: process frames (crop, resize, encode)
    3. If no: send empty image list
    4. Call VLM
    5. Strip accidental scene prefixes if no images were sent
    6. Return response

    Args:
        config: Application configuration
        vlm_client: Multimodal VLM client
        transcript: User's transcribed query
        segment_frames: Raw video frames from segment recording
        history: Optional conversation history in chronological order

    Returns:
        Dict containing:
        - payload: Request payload sent to VLM
        - response: Raw VLM response
        - text: Extracted response text
        - vision_used: Boolean indicating if images were sent
    """
    # Step 1: Determine intent
    needs_vision = wants_vision(transcript)

    # Step 2: Process frames if vision is needed
    images_b64: List[str] = []
    if needs_vision and segment_frames:
        images_b64 = process_frames_for_vision(
            frames=segment_frames,
            max_count=config.frame_max_images,
            crop_ratio=getattr(config, 'center_crop_ratio', 0.38),
            max_width=config.video_width_px,
            jpeg_quality=85,
        )

    # Step 3: Call VLM with or without images
    response = vlm_client.infer(transcript, images_b64, history=history)

    # Step 4: Clean up response text if no vision was used
    text = response.get("text", "")
    if not needs_vision and text:
        text = strip_scene_preface(text)
        response["text"] = text

    # Step 5: Add metadata
    response["vision_used"] = needs_vision and len(images_b64) > 0
    response["image_count"] = len(images_b64)

    return response
