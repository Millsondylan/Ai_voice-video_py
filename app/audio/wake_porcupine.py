"""
Porcupine-based wake word detection with acoustic modeling.
Primary wake word detector with high accuracy and low CPU usage.
"""
from __future__ import annotations

import collections
import threading
import time
from typing import Callable, Optional

from app.util.log import get_event_logger

from .mic import MicrophoneStream

try:
    import pvporcupine
    PORCUPINE_AVAILABLE = True
except ImportError:
    PORCUPINE_AVAILABLE = False
    pvporcupine = None


class PorcupineWakeListener(threading.Thread):
    """
    Continuously listens for wake word using Picovoice Porcupine.

    Features:
    - Acoustic model-based detection (more accurate than STT)
    - Tunable sensitivity (0.0-1.0)
    - Low CPU usage (~4% on RPi)
    - Pre-roll buffer for capturing audio before detection
    """

    def __init__(
        self,
        access_key: str,
        keyword_paths: Optional[list[str]] = None,
        keywords: Optional[list[str]] = None,
        on_detect: Callable[[list[bytes]], None] = None,
        sensitivity: float = 0.65,
        sample_rate: int = 16000,
        chunk_samples: int = 512,  # Porcupine frame length
        debounce_ms: int = 700,
        mic_device_name: Optional[str] = None,
        pre_roll_ms: int = 300,
    ) -> None:
        """
        Initialize Porcupine wake word listener.

        Args:
            access_key: Picovoice access key from console.picovoice.ai
            keyword_paths: List of paths to .ppn keyword files (custom models)
            keywords: List of built-in keywords (e.g. ['jarvis', 'alexa'])
            on_detect: Callback function called when wake word detected
            sensitivity: Detection sensitivity 0.0-1.0 (higher = more triggers)
            sample_rate: Audio sample rate (must be 16000 for Porcupine)
            chunk_samples: Samples per frame (must match Porcupine frame_length)
            debounce_ms: Minimum time between triggers
            mic_device_name: Specific microphone device
            pre_roll_ms: Pre-roll buffer duration in milliseconds
        """
        if not PORCUPINE_AVAILABLE:
            raise RuntimeError(
                "Porcupine is not installed. Install with: pip install pvporcupine"
            )

        if not access_key:
            raise RuntimeError(
                "Porcupine access key required. Get one from https://console.picovoice.ai"
            )

        super().__init__(daemon=True)

        self._access_key = access_key
        self._keyword_paths = keyword_paths
        self._keywords = keywords
        self._on_detect = on_detect or (lambda x: None)
        self._sensitivity = sensitivity
        self._sample_rate = sample_rate
        self._mic_device_name = mic_device_name
        self._debounce_ms = debounce_ms
        self._last_trigger_time: float = 0.0
        self._stop_event = threading.Event()
        self._active_mic: Optional[MicrophoneStream] = None
        self._porcupine = None

        # Initialize Porcupine
        self._init_porcupine(chunk_samples)

        # Pre-roll buffer setup
        frame_ms = int((self._porcupine.frame_length / sample_rate) * 1000)
        buffer_size = max(1, int(pre_roll_ms / frame_ms))
        self._rolling_buffer: collections.deque = collections.deque(maxlen=buffer_size)

    def _init_porcupine(self, chunk_samples: int) -> None:
        """Initialize Porcupine engine."""
        try:
            # Build sensitivity list
            num_keywords = 0
            if self._keyword_paths:
                num_keywords = len(self._keyword_paths)
            elif self._keywords:
                num_keywords = len(self._keywords)
            else:
                raise ValueError("Either keyword_paths or keywords must be provided")

            sensitivities = [self._sensitivity] * num_keywords

            # Create Porcupine instance
            self._porcupine = pvporcupine.create(
                access_key=self._access_key,
                keyword_paths=self._keyword_paths,
                keywords=self._keywords,
                sensitivities=sensitivities,
            )

            # Validate sample rate
            if self._sample_rate != self._porcupine.sample_rate:
                raise ValueError(
                    f"Sample rate must be {self._porcupine.sample_rate} Hz for Porcupine, "
                    f"got {self._sample_rate} Hz"
                )

            # Validate frame length
            if chunk_samples != self._porcupine.frame_length:
                raise ValueError(
                    f"Chunk samples must be {self._porcupine.frame_length} for Porcupine, "
                    f"got {chunk_samples}. Adjust chunk_samples in config."
                )

        except Exception as exc:
            if self._porcupine:
                self._porcupine.delete()
            raise RuntimeError(f"Failed to initialize Porcupine: {exc}") from exc

    def stop(self) -> None:
        """Stop the wake word listener."""
        self._stop_event.set()
        if self._active_mic:
            try:
                self._active_mic.stop()
            except Exception:
                pass

    def run(self) -> None:
        """Run wake word detection loop with Porcupine."""
        logger = get_event_logger()

        try:
            while not self._stop_event.is_set():
                with MicrophoneStream(
                    rate=self._sample_rate,
                    chunk_samples=self._porcupine.frame_length,
                    input_device_name=self._mic_device_name,
                ) as mic:
                    self._active_mic = mic
                    self._rolling_buffer.clear()

                    while not self._stop_event.is_set():
                        # Read audio frame (must be exact frame_length)
                        frame = mic.read(self._porcupine.frame_length)

                        # Maintain rolling buffer for pre-roll
                        self._rolling_buffer.append(frame)

                        # Process with Porcupine
                        keyword_index = self._porcupine.process(frame)

                        # Check if wake word detected
                        if keyword_index >= 0:
                            if self._should_trigger():
                                logger.log_wake_detected()
                                # Pass rolling buffer (contains wake word + pre-roll)
                                buffer_copy = list(self._rolling_buffer)
                                self._on_detect(buffer_copy)
                                return

                self._active_mic = None

        except Exception as exc:  # pragma: no cover
            logger = get_event_logger()
            logger.log_event('wake_listener_error', {'error': str(exc)})
            import logging
            logging.exception("PorcupineWakeListener error")
        finally:
            # Clean up Porcupine
            if self._porcupine:
                self._porcupine.delete()

    def _should_trigger(self) -> bool:
        """Check if enough time has passed since last trigger (debouncing)."""
        now = time.time()
        if (now - self._last_trigger_time) * 1000 >= self._debounce_ms:
            self._last_trigger_time = now
            return True
        return False

    @property
    def frame_length(self) -> int:
        """Get Porcupine's required frame length."""
        return self._porcupine.frame_length if self._porcupine else 512

    @property
    def version(self) -> str:
        """Get Porcupine version."""
        return self._porcupine.version if self._porcupine else "unknown"
