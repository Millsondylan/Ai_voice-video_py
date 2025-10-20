from __future__ import annotations

import threading
from typing import Optional

import pyaudio

from app.audio.io import get_audio_io_controller
from app.util.log import logger as audio_logger


class MicrophoneStream:
    """Thin PyAudio wrapper that supports device selection and variable chunk sizes."""

    def __init__(
        self,
        rate: int = 16000,
        channels: int = 1,
        frame_duration_ms: int = 30,
        input_device_index: Optional[int] = None,
        input_device_name: Optional[str] = None,
        chunk_samples: Optional[int] = None,
    ) -> None:
        self.rate = rate
        self.channels = channels
        self.format = pyaudio.paInt16
        self._audio = pyaudio.PyAudio()
        self._stream: Optional[pyaudio.Stream] = None
        self._lock = threading.Lock()
        self._controller = get_audio_io_controller()

        if chunk_samples is not None:
            self.chunk = int(chunk_samples)
            self.frame_duration_ms = max(1, int(1000 * self.chunk / self.rate))
        else:
            self.frame_duration_ms = frame_duration_ms
            self.chunk = int(rate * frame_duration_ms / 1000)

        if input_device_name is not None:
            self.input_device_index = self._resolve_device_index(input_device_name)
        else:
            self.input_device_index = input_device_index

    def start(self) -> None:
        with self._lock:
            if self._stream and self._stream.is_active():
                return
            try:
                self._stream = self._open_stream(self.input_device_index)
            except OSError as exc:
                # Common error when no default input device is available
                if self.input_device_index is None:
                    fallback_index = self._find_first_input_device()
                    if fallback_index is not None:
                        audio_logger.warning(
                            "Primary microphone open failed (%s); falling back to device index %s",
                            exc,
                            fallback_index,
                        )
                        self._stream = self._open_stream(fallback_index)
                        self.input_device_index = fallback_index
                    else:
                        audio_logger.error("No input devices available for recording: %s", exc)
                        raise
                else:
                    audio_logger.error("Failed to open microphone device %s: %s", self.input_device_index, exc)
                    raise
            self._controller.register_mic(self)

    def read(self, frames: Optional[int] = None) -> bytes:
        if not self._stream:
            raise RuntimeError("MicrophoneStream not started")
        # Block if input is paused (e.g., during TTS playback)
        self._controller.wait_if_paused()
        frame_count = int(frames) if frames is not None else self.chunk
        return self._stream.read(frame_count, exception_on_overflow=False)

    def stop(self) -> None:
        with self._lock:
            if self._stream:
                try:
                    self._stream.stop_stream()
                finally:
                    self._stream.close()
                self._stream = None
                self._controller.unregister_mic()

    def terminate(self) -> None:
        self.stop()
        self._audio.terminate()

    def __enter__(self) -> "MicrophoneStream":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.terminate()

    def _resolve_device_index(self, device_name: str) -> Optional[int]:
        """Resolve a device name to an index using substring matching."""
        target = device_name.strip().lower()
        device_count = self._audio.get_device_count()
        fallback: Optional[int] = None
        for idx in range(device_count):
            info = self._audio.get_device_info_by_index(idx)
            if info.get("maxInputChannels", 0) <= 0:
                continue
            name = str(info.get("name", "")).strip()
            if not name:
                continue
            lowered = name.lower()
            if target == lowered:
                return idx
            if target in lowered or lowered in target:
                fallback = idx
        return fallback

    def _find_first_input_device(self) -> Optional[int]:
        """Return the first available input-capable device index, if any."""
        device_count = self._audio.get_device_count()
        for idx in range(device_count):
            info = self._audio.get_device_info_by_index(idx)
            if info.get("maxInputChannels", 0) > 0:
                return idx
        return None

    def _open_stream(self, device_index: Optional[int]):
        return self._audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk,
            input_device_index=device_index,
            stream_callback=None,
        )

    @staticmethod
    def list_input_devices() -> list[dict]:
        """List all available input-capable devices."""
        audio = pyaudio.PyAudio()
        try:
            device_count = audio.get_device_count()
            devices: list[dict] = []
            for idx in range(device_count):
                info = audio.get_device_info_by_index(idx)
                if info.get("maxInputChannels", 0) > 0:
                    devices.append(
                        {
                            "index": idx,
                            "name": info.get("name"),
                            "channels": info.get("maxInputChannels"),
                        }
                    )
            return devices
        finally:
            audio.terminate()
