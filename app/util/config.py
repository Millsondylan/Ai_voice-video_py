from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

# Default configuration values aligned with the build brief.
DEFAULT_CONFIG: Dict[str, Any] = {
    "wake_word": "hey glasses",
    "silence_ms": 800,
    "max_segment_s": 30,
    "frame_sample_fps": 2,
    "frame_max_images": 20,
    "video_width_px": 960,
    "camera_source": "0",
    "vlm_provider": "http",
}


@dataclass
class AppConfig:
    wake_word: str = DEFAULT_CONFIG["wake_word"]
    silence_ms: int = DEFAULT_CONFIG["silence_ms"]
    max_segment_s: int = DEFAULT_CONFIG["max_segment_s"]
    frame_sample_fps: float = DEFAULT_CONFIG["frame_sample_fps"]
    frame_max_images: int = DEFAULT_CONFIG["frame_max_images"]
    video_width_px: int = DEFAULT_CONFIG["video_width_px"]
    camera_source: str = DEFAULT_CONFIG["camera_source"]
    vlm_endpoint: Optional[str] = field(default_factory=lambda: os.getenv("VLM_ENDPOINT"))
    vlm_api_key: Optional[str] = field(default_factory=lambda: os.getenv("VLM_API_KEY"))
    vlm_system_prompt: Optional[str] = field(default_factory=lambda: os.getenv("VLM_SYSTEM_PROMPT"))
    vlm_model: Optional[str] = field(default_factory=lambda: os.getenv("VLM_MODEL") or os.getenv("GLASSES_VLM_MODEL"))
    vlm_provider: str = DEFAULT_CONFIG["vlm_provider"]
    vosk_model_path: Optional[str] = field(default_factory=lambda: os.getenv("VOSK_MODEL_PATH"))
    session_root: Path = field(
        default_factory=lambda: Path(os.getenv("GLASSES_SESSION_ROOT", "~/GlassesSessions")).expanduser()
    )

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON serializable dict representation."""
        data = asdict(self)
        data["session_root"] = str(self.session_root)
        return data


def _load_json_config(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fp:
            return json.load(fp)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in config file {path}: {exc}") from exc


def _merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = base.copy()
    for key, value in override.items():
        if value is None:
            continue
        merged[key] = value
    return merged


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    """Load configuration by merging defaults, JSON file, and environment variables."""
    load_dotenv()

    config_data: Dict[str, Any] = DEFAULT_CONFIG.copy()

    if config_path:
        path = Path(config_path)
        if path.is_file():
            config_data = _merge_dicts(config_data, _load_json_config(path))
    else:
        default_file = Path("config.json")
        if default_file.is_file():
            config_data = _merge_dicts(config_data, _load_json_config(default_file))

    for env_key, config_key in [
        ("GLASSES_WAKE_WORD", "wake_word"),
        ("GLASSES_SILENCE_MS", "silence_ms"),
        ("GLASSES_MAX_SEGMENT_S", "max_segment_s"),
        ("GLASSES_FRAME_SAMPLE_FPS", "frame_sample_fps"),
        ("GLASSES_FRAME_MAX_IMAGES", "frame_max_images"),
        ("GLASSES_VIDEO_WIDTH_PX", "video_width_px"),
        ("GLASSES_CAMERA_SOURCE", "camera_source"),
        ("GLASSES_VOSK_MODEL_PATH", "vosk_model_path"),
        ("GLASSES_VLM_MODEL", "vlm_model"),
        ("VLM_MODEL", "vlm_model"),
        ("GLASSES_VLM_PROVIDER", "vlm_provider"),
        ("VLM_PROVIDER", "vlm_provider"),
    ]:
        value = os.getenv(env_key)
        if value is not None:
            if config_key in {"silence_ms", "max_segment_s", "frame_max_images", "video_width_px"}:
                config_data[config_key] = int(value)
            elif config_key == "frame_sample_fps":
                config_data[config_key] = float(value)
            else:
                config_data[config_key] = value

    app_config = AppConfig(**config_data)
    return app_config
