from __future__ import annotations

import threading
import time
from typing import Callable

from app.util.log import get_event_logger

from .mic import MicrophoneStream
from .stt import StreamingTranscriber


class WakeWordListener(threading.Thread):
    """Continuously listens for a wake word phrase and invokes a callback."""

    def __init__(
        self,
        wake_word: str,
        on_detect: Callable[[], None],
        transcriber: StreamingTranscriber,
        sample_rate: int = 16000,
        frame_duration_ms: int = 20,
        debounce_ms: int = 700,
    ) -> None:
        super().__init__(daemon=True)
        self.wake_word = wake_word.lower()
        self._on_detect = on_detect
        self._transcriber = transcriber
        self._sample_rate = sample_rate
        self._frame_duration_ms = frame_duration_ms
        self._debounce_ms = debounce_ms
        self._last_trigger_time: float = 0
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        """Run wake word detection loop (no VAD preprocessing for low latency)."""
        logger = get_event_logger()
        try:
            while not self._stop_event.is_set():
                with MicrophoneStream(rate=self._sample_rate, frame_duration_ms=self._frame_duration_ms) as mic:
                    self._transcriber.reset()
                    while not self._stop_event.is_set():
                        frame = mic.read()
                        # Process ALL frames (no VAD filtering) for lowest latency
                        result = self._transcriber.accept_audio(frame)
                        transcript_lower = f"{self._transcriber.transcript} {result.text}".lower()
                        if self.wake_word in transcript_lower:
                            # Debounce: prevent rapid re-triggers
                            now = time.time()
                            if (now - self._last_trigger_time) * 1000 >= self._debounce_ms:
                                self._last_trigger_time = now
                                logger.log_wake_detected()
                                self._on_detect()
                                return
        except Exception as exc:  # pragma: no cover
            print(f"[WakeWordListener] error: {exc}")

