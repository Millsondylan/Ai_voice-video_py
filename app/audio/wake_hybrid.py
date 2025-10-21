"""
Hybrid wake word detection with automatic fallback.
Tries Porcupine (acoustic model) first, falls back to Vosk (STT-based) if unavailable.
"""
from __future__ import annotations

import os
from typing import Callable, Optional

from app.audio.stt import StreamingTranscriber
from app.audio.wake import WakeWordListener
from app.util.log import logger

try:
    from app.audio.wake_porcupine import PORCUPINE_AVAILABLE, PorcupineWakeListener
except ImportError:
    PORCUPINE_AVAILABLE = False
    PorcupineWakeListener = None


class HybridWakeWordManager:
    """
    Manages wake word detection with automatic fallback:
    1. Primary: Porcupine (acoustic model-based, low CPU, high accuracy)
    2. Fallback: Vosk STT (transcription-based, works offline)

    Automatically chooses the best available method based on:
    - Porcupine installation and API key availability
    - Configuration preferences
    - Initialization success
    """

    def __init__(
        self,
        wake_word: str,
        wake_variants: list[str],
        on_detect: Callable[[list[bytes]], None],
        transcriber: StreamingTranscriber,
        sample_rate: int = 16000,
        chunk_samples: int = 320,
        debounce_ms: int = 700,
        mic_device_name: Optional[str] = None,
        pre_roll_ms: int = 300,
        # Porcupine-specific settings
        porcupine_access_key: Optional[str] = None,
        porcupine_keyword_path: Optional[str] = None,
        porcupine_sensitivity: float = 0.65,
        prefer_porcupine: bool = True,
    ) -> None:
        """
        Initialize hybrid wake word manager.

        Args:
            wake_word: Primary wake word phrase (e.g. "hey glasses")
            wake_variants: Variant phrases for Vosk fallback
            on_detect: Callback when wake word detected
            transcriber: Vosk transcriber for STT-based detection
            sample_rate: Audio sample rate (16000 Hz)
            chunk_samples: Samples per chunk
            debounce_ms: Minimum time between triggers
            mic_device_name: Specific microphone device
            pre_roll_ms: Pre-roll buffer duration
            porcupine_access_key: Picovoice API key (from env or config)
            porcupine_keyword_path: Path to custom .ppn keyword file
            porcupine_sensitivity: Detection sensitivity 0.0-1.0
            prefer_porcupine: Try Porcupine first if True
        """
        self.wake_word = wake_word
        self.wake_variants = wake_variants
        self.on_detect = on_detect
        self.transcriber = transcriber
        self.sample_rate = sample_rate
        self.chunk_samples = chunk_samples
        self.debounce_ms = debounce_ms
        self.mic_device_name = mic_device_name
        self.pre_roll_ms = pre_roll_ms

        self.porcupine_access_key = porcupine_access_key or os.getenv("PORCUPINE_ACCESS_KEY")
        self.porcupine_keyword_path = porcupine_keyword_path
        self.porcupine_sensitivity = porcupine_sensitivity
        self.prefer_porcupine = prefer_porcupine

        self._active_listener = None
        self._detection_method = None

    def create_listener(self):
        """
        Create the best available wake word listener.

        Returns:
            WakeWordListener or PorcupineWakeListener instance

        Priority:
            1. Porcupine (if available, configured, and preferred)
            2. Vosk STT fallback (always available)
        """
        # Try Porcupine first if preferred and available
        if self.prefer_porcupine:
            if self._can_use_porcupine():
                try:
                    listener = self._create_porcupine_listener()
                    self._detection_method = "porcupine"
                    logger.info(f"✅ Using Porcupine wake word detection (sensitivity={self.porcupine_sensitivity})")
                    return listener
                except Exception as e:
                    logger.warning(f"⚠️  Porcupine initialization failed: {e}")
                    logger.info("→ Falling back to Vosk STT-based detection...")
            else:
                logger.info("→ Porcupine not available, using Vosk STT-based detection")

        # Fallback to Vosk STT
        listener = self._create_vosk_listener()
        self._detection_method = "vosk"
        logger.info(f"✅ Using Vosk STT wake word detection (variants={len(self.wake_variants)})")
        return listener

    def _can_use_porcupine(self) -> bool:
        """Check if Porcupine can be used."""
        if not PORCUPINE_AVAILABLE:
            logger.info("Porcupine not available (pvporcupine not installed) - using Vosk fallback")
            return False

        if not self.porcupine_access_key:
            logger.info("Porcupine access key not found (set PORCUPINE_ACCESS_KEY env var) - using Vosk fallback")
            return False

        # Check if we have either a custom keyword path or a mappable built-in keyword
        if not self.porcupine_keyword_path:
            builtin = self._map_to_builtin_keyword()
            if not builtin:
                logger.info(f"Wake word '{self.wake_word}' is not a Porcupine built-in keyword and no custom keyword path provided - using Vosk fallback")
                return False

        return True

    def _create_porcupine_listener(self):
        """Create Porcupine-based wake word listener."""
        # Porcupine requires chunk_samples = frame_length = 512
        porcupine_frame_length = 512

        if self.porcupine_keyword_path:
            # Custom keyword model
            logger.info(f"Using custom Porcupine keyword: {self.porcupine_keyword_path}")
            listener = PorcupineWakeListener(
                access_key=self.porcupine_access_key,
                keyword_paths=[self.porcupine_keyword_path],
                on_detect=self.on_detect,
                sensitivity=self.porcupine_sensitivity,
                sample_rate=self.sample_rate,
                chunk_samples=porcupine_frame_length,
                debounce_ms=self.debounce_ms,
                mic_device_name=self.mic_device_name,
                pre_roll_ms=self.pre_roll_ms,
            )
        else:
            # Try to map wake word to built-in keywords
            builtin_keyword = self._map_to_builtin_keyword()
            if builtin_keyword:
                logger.info(f"Using built-in Porcupine keyword: {builtin_keyword}")
                listener = PorcupineWakeListener(
                    access_key=self.porcupine_access_key,
                    keywords=[builtin_keyword],
                    on_detect=self.on_detect,
                    sensitivity=self.porcupine_sensitivity,
                    sample_rate=self.sample_rate,
                    chunk_samples=porcupine_frame_length,
                    debounce_ms=self.debounce_ms,
                    mic_device_name=self.mic_device_name,
                    pre_roll_ms=self.pre_roll_ms,
                )
            else:
                raise ValueError(
                    f"Wake word '{self.wake_word}' not a built-in keyword. "
                    f"Provide porcupine_keyword_path for custom wake word, or use Vosk fallback."
                )

        return listener

    def _create_vosk_listener(self):
        """Create Vosk STT-based wake word listener."""
        return WakeWordListener(
            wake_variants=self.wake_variants,
            on_detect=self.on_detect,
            transcriber=self.transcriber,
            sample_rate=self.sample_rate,
            chunk_samples=self.chunk_samples,
            debounce_ms=self.debounce_ms,
            mic_device_name=self.mic_device_name,
            pre_roll_ms=self.pre_roll_ms,
        )

    def _map_to_builtin_keyword(self) -> Optional[str]:
        """
        Map wake word to Porcupine built-in keyword if possible.

        Built-in keywords (as of 2024):
        - alexa, americano, blueberry, bumblebee, computer, grapefruit,
        - grasshopper, hey google, hey siri, jarvis, ok google, picovoice,
        - porcupine, terminator, etc.

        Returns:
            Built-in keyword name or None
        """
        wake_lower = self.wake_word.lower().strip()

        # Common mappings
        builtin_keywords = {
            "alexa": "alexa",
            "hey google": "hey google",
            "ok google": "ok google",
            "hey siri": "hey siri",
            "jarvis": "jarvis",
            "computer": "computer",
            "porcupine": "porcupine",
            "picovoice": "picovoice",
            "terminator": "terminator",
            "bumblebee": "bumblebee",
        }

        return builtin_keywords.get(wake_lower)

    @property
    def detection_method(self) -> Optional[str]:
        """Get active detection method: 'porcupine' or 'vosk'."""
        return self._detection_method

    def get_info(self) -> dict:
        """Get information about the active detection method."""
        return {
            "method": self._detection_method,
            "wake_word": self.wake_word,
            "variants": self.wake_variants if self._detection_method == "vosk" else [],
            "sensitivity": self.porcupine_sensitivity if self._detection_method == "porcupine" else None,
            "porcupine_available": PORCUPINE_AVAILABLE,
            "porcupine_configured": self._can_use_porcupine(),
        }


def create_wake_listener(
    config,
    transcriber: StreamingTranscriber,
    on_detect: Callable[[list[bytes]], None],
) -> WakeWordListener:
    """
    Convenience function to create the best wake word listener for the config.

    Args:
        config: AppConfig with wake word settings
        transcriber: Vosk transcriber instance
        on_detect: Wake detection callback

    Returns:
        Wake word listener instance (Porcupine or Vosk)
    """
    manager = HybridWakeWordManager(
        wake_word=config.wake_word,
        wake_variants=config.wake_variants,
        on_detect=on_detect,
        transcriber=transcriber,
        sample_rate=config.sample_rate_hz,
        chunk_samples=config.chunk_samples,
        debounce_ms=700,
        mic_device_name=config.mic_device_name,
        pre_roll_ms=config.pre_roll_ms,
        porcupine_access_key=getattr(config, "porcupine_access_key", None),
        porcupine_keyword_path=getattr(config, "porcupine_keyword_path", None),
        porcupine_sensitivity=getattr(config, "porcupine_sensitivity", 0.65),
        prefer_porcupine=getattr(config, "prefer_porcupine", True),
    )

    listener = manager.create_listener()

    # Log detection method info
    info = manager.get_info()
    logger.info(f"Wake word detection info: {info}")

    return listener
