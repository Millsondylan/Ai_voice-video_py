from __future__ import annotations

import threading
from typing import Callable

from .mic import MicrophoneStream
from .stt import StreamingTranscriber
from .vad import VoiceActivityDetector


class WakeWordListener(threading.Thread):
    """Continuously listens for a wake word phrase and invokes a callback."""

    def __init__(
        self,
        wake_word: str,
        on_detect: Callable[[], None],
        transcriber: StreamingTranscriber,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
    ) -> None:
        super().__init__(daemon=True)
        self.wake_word = wake_word.lower()
        self._on_detect = on_detect
        self._transcriber = transcriber
        self._sample_rate = sample_rate
        self._frame_duration_ms = frame_duration_ms
        self._vad = VoiceActivityDetector(sample_rate=sample_rate, frame_duration_ms=frame_duration_ms)
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            while not self._stop_event.is_set():
                with MicrophoneStream(rate=self._sample_rate, frame_duration_ms=self._frame_duration_ms) as mic:
                    self._transcriber.reset()
                    while not self._stop_event.is_set():
                        frame = mic.read()
                        if not self._vad.is_speech(frame):
                            continue
                        result = self._transcriber.accept_audio(frame)
                        transcript_lower = f"{self._transcriber.transcript} {result.text}".lower()
                        if self.wake_word in transcript_lower:
                            self._on_detect()
                            return
        except Exception as exc:  # pragma: no cover - logging hook could be added
            print(f"[WakeWordListener] error: {exc}")

