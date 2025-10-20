from __future__ import annotations

import base64
import json
import shutil
import tempfile
from pathlib import Path
from typing import List


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_temp_segment_dir(prefix: str = "glasses_segment_") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


def archive_session(
    session_root: Path,
    timestamp_key: str,
    video_path: Path,
    transcript: str,
    response_payload: dict,
    audio_path: Path | None = None,
) -> Path:
    session_dir = ensure_dir(session_root / timestamp_key)

    target_video = session_dir / "segment.mp4"
    shutil.move(str(video_path), target_video)

    transcript_path = session_dir / "transcript.txt"
    transcript_path.write_text(transcript, encoding="utf-8")

    answer_path = session_dir / "answer.json"
    answer_path.write_text(json.dumps(response_payload, indent=2), encoding="utf-8")

    if audio_path and audio_path.exists():
        shutil.move(str(audio_path), session_dir / audio_path.name)

    return session_dir


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def encode_image_to_base64(image) -> str:
    """Encode a BGR image (as ndarray) to base64 PNG string."""
    import cv2  # Local import to avoid importing cv2 for consumers that do not need it

    success, buffer = cv2.imencode(".png", image)
    if not success:
        raise RuntimeError("Failed to encode image to PNG")
    return base64.b64encode(buffer.tobytes()).decode("utf-8")
