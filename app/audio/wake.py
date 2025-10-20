from __future__ import annotations

import collections
import threading
import time
from typing import Callable

from app.util.log import get_event_logger

from .mic import MicrophoneStream
from .stt import StreamingTranscriber


class WakeWordListener(threading.Thread):
    """Continuously listens for wake variants on a raw PCM stream (no VAD)."""

    def __init__(
        self,
        wake_variants: list[str],
        on_detect: Callable[[list[bytes]], None],
        transcriber: StreamingTranscriber,
        sample_rate: int = 16000,
        chunk_samples: int = 320,
        debounce_ms: int = 700,
        mic_device_name: str | None = None,
        pre_roll_ms: int = 300,
    ) -> None:
        super().__init__(daemon=True)
        self._wake_variants = [variant.lower() for variant in wake_variants if variant]
        self._on_detect = on_detect
        self._transcriber = transcriber
        self._sample_rate = sample_rate
        self._chunk_samples = chunk_samples
        self._debounce_ms = debounce_ms
        self._mic_device_name = mic_device_name
        self._last_trigger_time: float = 0.0
        self._stop_event = threading.Event()
        self._active_mic: MicrophoneStream | None = None

        # Continuous rolling buffer for pre-roll
        frame_ms = int((chunk_samples / sample_rate) * 1000)
        buffer_size = max(1, int(pre_roll_ms / frame_ms))
        self._rolling_buffer: collections.deque = collections.deque(maxlen=buffer_size)

    def stop(self) -> None:
        self._stop_event.set()
        if self._active_mic:
            try:
                self._active_mic.stop()
            except Exception:
                pass

    def run(self) -> None:
        """Run wake word detection loop with continuous rolling buffer for pre-roll."""
        logger = get_event_logger()
        try:
            while not self._stop_event.is_set():
                with MicrophoneStream(
                    rate=self._sample_rate,
                    chunk_samples=self._chunk_samples,
                    input_device_name=self._mic_device_name,
                ) as mic:
                    self._active_mic = mic
                    self._transcriber.start()
                    self._rolling_buffer.clear()

                    while not self._stop_event.is_set():
                        frame = mic.read(self._chunk_samples)

                        # Maintain rolling buffer of recent audio
                        self._rolling_buffer.append(frame)

                        # Feed to transcriber
                        self._transcriber.feed(frame)
                        text = self._transcriber.combined_text.lower()

                        if self._matches_variant(text):
                            if self._should_trigger():
                                logger.log_wake_detected()
                                # Pass the rolling buffer (contains wake word + pre-roll)
                                buffer_copy = list(self._rolling_buffer)
                                self._on_detect(buffer_copy)
                                return
                self._active_mic = None
        except Exception as exc:  # pragma: no cover
            print(f"[WakeWordListener] error: {exc}")
            import traceback
            traceback.print_exc()

    def _matches_variant(self, text: str) -> bool:
        return any(variant in text for variant in self._wake_variants)

    def _should_trigger(self) -> bool:
        now = time.time()
        if (now - self._last_trigger_time) * 1000 >= self._debounce_ms:
            self._last_trigger_time = now
            return True
        return False
