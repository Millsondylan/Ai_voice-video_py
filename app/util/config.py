from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Default configuration values aligned with the build brief.
DEFAULT_CONFIG: Dict[str, Any] = {
    "wake_word": "hey glasses",
    "silence_ms": 1200,
    "max_segment_s": 45,
    "frame_sample_fps": 2,
    "frame_max_images": 6,
    "video_width_px": 960,
    "center_crop_ratio": 0.38,
    "camera_source": "0",
    "vlm_provider": "http",
    "mic_device_name": None,
    "sample_rate_hz": 16000,
    "chunk_samples": 320,
    "vad_aggressiveness": 1,
    "pre_roll_ms": 600,
    "wake_variants": ["hey glasses", "hey-glasses", "hay glasses", "hey glaases"],
    "wake_sensitivity": 0.65,
    "wake_vad_level": 1,
    "wake_match_window_ms": 1200,
    "tts_voice": None,
    "tts_rate": 175,
    # Porcupine wake word detection (optional, falls back to Vosk)
    "prefer_porcupine": True,
    "porcupine_sensitivity": 0.65,
    "porcupine_keyword_path": None,
    # Advanced speech capture settings for complete word capture
    "min_speech_frames": 5,        # Minimum speech frames before allowing silence cutoff
    "tail_padding_ms": 400,        # Extra audio to capture after speech ends
    "noise_gate_threshold": 0,     # Amplitude threshold for STT noise gating (0 disables)
    "apply_noise_gate": False,     # Enable preprocessing noise gate before STT (off by default)
    "apply_speech_filter": False,  # Apply bandpass filter before STT
    "speech_filter_highpass_hz": 80,
    "speech_filter_lowpass_hz": 8000,
    "vosk_max_alternatives": 5,
    "resample_on_mismatch": True,
    "enable_agc": True,  # Enable Automatic Gain Control for quiet microphones
}


@dataclass
class AppConfig:
    wake_word: str = DEFAULT_CONFIG["wake_word"]
    silence_ms: int = DEFAULT_CONFIG["silence_ms"]
    max_segment_s: int = DEFAULT_CONFIG["max_segment_s"]
    frame_sample_fps: float = DEFAULT_CONFIG["frame_sample_fps"]
    frame_max_images: int = DEFAULT_CONFIG["frame_max_images"]
    video_width_px: int = DEFAULT_CONFIG["video_width_px"]
    center_crop_ratio: float = DEFAULT_CONFIG["center_crop_ratio"]
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
    # Audio system configuration
    mic_device_name: Optional[str] = DEFAULT_CONFIG["mic_device_name"]
    sample_rate_hz: int = DEFAULT_CONFIG["sample_rate_hz"]
    chunk_samples: int = DEFAULT_CONFIG["chunk_samples"]
    vad_aggressiveness: int = DEFAULT_CONFIG["vad_aggressiveness"]
    pre_roll_ms: int = DEFAULT_CONFIG["pre_roll_ms"]
    wake_vad_level: int = DEFAULT_CONFIG["wake_vad_level"]
    wake_match_window_ms: int = DEFAULT_CONFIG["wake_match_window_ms"]
    noise_gate_threshold: int = DEFAULT_CONFIG["noise_gate_threshold"]
    apply_noise_gate: bool = DEFAULT_CONFIG["apply_noise_gate"]
    apply_speech_filter: bool = DEFAULT_CONFIG["apply_speech_filter"]
    speech_filter_highpass_hz: int = DEFAULT_CONFIG["speech_filter_highpass_hz"]
    speech_filter_lowpass_hz: int = DEFAULT_CONFIG["speech_filter_lowpass_hz"]
    vosk_max_alternatives: int = DEFAULT_CONFIG["vosk_max_alternatives"]
    resample_on_mismatch: bool = DEFAULT_CONFIG["resample_on_mismatch"]
    wake_variants: List[str] = field(default_factory=lambda: DEFAULT_CONFIG["wake_variants"].copy())
    wake_sensitivity: float = DEFAULT_CONFIG["wake_sensitivity"]
    tts_voice: Optional[str] = DEFAULT_CONFIG["tts_voice"]
    tts_rate: int = DEFAULT_CONFIG["tts_rate"]
    # Porcupine wake word detection (primary method with Vosk fallback)
    prefer_porcupine: bool = DEFAULT_CONFIG["prefer_porcupine"]
    porcupine_access_key: Optional[str] = field(default_factory=lambda: os.getenv("PORCUPINE_ACCESS_KEY"))
    porcupine_sensitivity: float = DEFAULT_CONFIG["porcupine_sensitivity"]
    porcupine_keyword_path: Optional[str] = DEFAULT_CONFIG["porcupine_keyword_path"]
    # Advanced speech capture settings for complete word capture
    min_speech_frames: int = DEFAULT_CONFIG["min_speech_frames"]
    tail_padding_ms: int = DEFAULT_CONFIG["tail_padding_ms"]
    # AGC (Automatic Gain Control) for quiet microphones
    enable_agc: bool = DEFAULT_CONFIG["enable_agc"]

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
    if isinstance(DEFAULT_CONFIG.get("wake_variants"), list):
        config_data["wake_variants"] = list(DEFAULT_CONFIG["wake_variants"])

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
        ("GLASSES_CENTER_CROP_RATIO", "center_crop_ratio"),
        ("GLASSES_CAMERA_SOURCE", "camera_source"),
        ("GLASSES_VOSK_MODEL_PATH", "vosk_model_path"),
        ("GLASSES_VLM_MODEL", "vlm_model"),
        ("VLM_MODEL", "vlm_model"),
        ("GLASSES_VLM_PROVIDER", "vlm_provider"),
        ("VLM_PROVIDER", "vlm_provider"),
        ("GLASSES_MIC_DEVICE_NAME", "mic_device_name"),
        ("GLASSES_SAMPLE_RATE_HZ", "sample_rate_hz"),
        ("GLASSES_CHUNK_SAMPLES", "chunk_samples"),
        ("GLASSES_VAD_AGGRESSIVENESS", "vad_aggressiveness"),
        ("GLASSES_PRE_ROLL_MS", "pre_roll_ms"),
        ("GLASSES_NOISE_GATE_THRESHOLD", "noise_gate_threshold"),
        ("GLASSES_APPLY_NOISE_GATE", "apply_noise_gate"),
        ("GLASSES_APPLY_SPEECH_FILTER", "apply_speech_filter"),
        ("GLASSES_SPEECH_FILTER_HIGHPASS", "speech_filter_highpass_hz"),
        ("GLASSES_SPEECH_FILTER_LOWPASS", "speech_filter_lowpass_hz"),
        ("GLASSES_VOSK_MAX_ALTERNATIVES", "vosk_max_alternatives"),
        ("GLASSES_RESAMPLE_ON_MISMATCH", "resample_on_mismatch"),
        ("GLASSES_WAKE_VARIANTS", "wake_variants"),
        ("GLASSES_WAKE_SENSITIVITY", "wake_sensitivity"),
        ("GLASSES_WAKE_VAD_LEVEL", "wake_vad_level"),
        ("GLASSES_WAKE_MATCH_MS", "wake_match_window_ms"),
        ("GLASSES_TTS_VOICE", "tts_voice"),
        ("GLASSES_TTS_RATE", "tts_rate"),
        ("GLASSES_PREFER_PORCUPINE", "prefer_porcupine"),
        ("PORCUPINE_ACCESS_KEY", "porcupine_access_key"),
        ("GLASSES_PORCUPINE_SENSITIVITY", "porcupine_sensitivity"),
        ("GLASSES_PORCUPINE_KEYWORD_PATH", "porcupine_keyword_path"),
        ("GLASSES_MIN_SPEECH_FRAMES", "min_speech_frames"),
        ("GLASSES_TAIL_PADDING_MS", "tail_padding_ms"),
    ]:
        value = os.getenv(env_key)
        if value is not None:
            if config_key in {
                "silence_ms",
                "max_segment_s",
                "frame_max_images",
                "video_width_px",
                "sample_rate_hz",
                "chunk_samples",
                "vad_aggressiveness",
                "pre_roll_ms",
                "tts_rate",
                "min_speech_frames",
                "tail_padding_ms",
                "noise_gate_threshold",
                "speech_filter_highpass_hz",
                "speech_filter_lowpass_hz",
                "vosk_max_alternatives",
                "wake_vad_level",
                "wake_match_window_ms",
            }:
                config_data[config_key] = int(value)
            elif config_key in {"frame_sample_fps", "center_crop_ratio", "wake_sensitivity", "porcupine_sensitivity"}:
                config_data[config_key] = float(value)
            elif config_key in {"prefer_porcupine", "apply_noise_gate", "apply_speech_filter", "resample_on_mismatch"}:
                config_data[config_key] = value.lower() in ("true", "1", "yes")
            elif config_key == "wake_variants":
                config_data[config_key] = [variant.strip() for variant in value.split(",") if variant.strip()]
            else:
                config_data[config_key] = value

    app_config = AppConfig(**config_data)
    return app_config
