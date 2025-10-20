from __future__ import annotations

import threading
from typing import Optional

import pyaudio


class MicrophoneStream:
    """Simple wrapper around PyAudio for 16kHz mono PCM streaming."""

    def __init__(
        self,
        rate: int = 16000,
        channels: int = 1,
        frame_duration_ms: int = 30,
        input_device_index: Optional[int] = None,
    ) -> None:
        self.rate = rate
        self.channels = channels
        self.frame_duration_ms = frame_duration_ms
        self.format = pyaudio.paInt16
        self.chunk = int(rate * frame_duration_ms / 1000)
        self.input_device_index = input_device_index

        self._audio = pyaudio.PyAudio()
        self._stream: Optional[pyaudio.Stream] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._stream and self._stream.is_active():
                return
            self._stream = self._audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.chunk,
                input_device_index=self.input_device_index,
                stream_callback=None,
            )

    def read(self) -> bytes:
        if not self._stream:
            raise RuntimeError("MicrophoneStream not started")
        return self._stream.read(self.chunk, exception_on_overflow=False)

    def stop(self) -> None:
        with self._lock:
            if self._stream:
                try:
                    self._stream.stop_stream()
                finally:
                    self._stream.close()
                self._stream = None

    def terminate(self) -> None:
        self.stop()
        self._audio.terminate()

    def __enter__(self) -> "MicrophoneStream":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.terminate()
