from __future__ import annotations

import audioop
import math
import threading
from typing import Optional, Tuple

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
        resample_on_mismatch: bool = True,
    ) -> None:
        self.rate = rate
        self.channels = channels
        self.format = pyaudio.paInt16
        self._audio = pyaudio.PyAudio()
        self._stream: Optional[pyaudio.Stream] = None
        self._lock = threading.Lock()
        self._controller = get_audio_io_controller()
        self._resample_state: Optional[tuple] = None
        self._resample_needed = False
        self._stream_rate = rate
        self._frames_per_buffer = None
        self._resample_on_mismatch = resample_on_mismatch
        self._warned_resample_disabled = False

        if chunk_samples is not None:
            self.chunk = int(chunk_samples)
            self.frame_duration_ms = max(1, int(1000 * self.chunk / self.rate))
        else:
            self.frame_duration_ms = frame_duration_ms
            self.chunk = int(rate * frame_duration_ms / 1000)
        self._frames_per_buffer = self.chunk

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
        # Add 60s timeout to prevent infinite blocking if TTS fails to unpause
        if not self._controller.wait_if_paused(timeout=60.0):
            audio_logger.warning("Microphone was paused for >60s, force resuming")
            from app.audio.io import pause_input
            pause_input(False)
        target_frames = int(frames) if frames is not None else self.chunk

        if not self._resample_needed:
            actual_frames = int(frames) if frames is not None else self._frames_per_buffer
            return self._stream.read(actual_frames, exception_on_overflow=False)

        # When the hardware runs at a different rate, resample to the target rate
        # requested by the application so Vosk always receives the expected format.
        if target_frames <= 0:
            target_frames = self.chunk

        input_frames = max(1, int(math.ceil(target_frames * self._stream_rate / self.rate)))
        raw = self._stream.read(input_frames, exception_on_overflow=False)

        converted, self._resample_state = audioop.ratecv(
            raw,
            2,  # 16-bit samples
            self.channels,
            self._stream_rate,
            self.rate,
            self._resample_state,
        )

        expected_bytes = target_frames * self.channels * 2
        if len(converted) < expected_bytes:
            converted += b"\x00" * (expected_bytes - len(converted))
        elif len(converted) > expected_bytes:
            converted = converted[:expected_bytes]
        return converted

    def stop(self) -> None:
        with self._lock:
            if self._stream:
                try:
                    self._stream.stop_stream()
                finally:
                    self._stream.close()
                self._stream = None
                self._controller.unregister_mic()
                self._resample_state = None
                self._resample_needed = False
                self._stream_rate = self.rate

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
        """Open the PyAudio stream, gracefully handling sample-rate mismatches."""
        desired_rate = self.rate
        desired_chunk = self.chunk
        self._resample_state = None
        self._resample_needed = False
        self._stream_rate = desired_rate
        self._frames_per_buffer = desired_chunk

        try:
            stream = self._audio.open(
                format=self.format,
                channels=self.channels,
                rate=desired_rate,
                input=True,
                frames_per_buffer=desired_chunk,
                input_device_index=device_index,
                stream_callback=None,
            )
            return stream
        except (ValueError, OSError) as exc:
            if not self._resample_on_mismatch:
                if not self._warned_resample_disabled:
                    audio_logger.error(
                        "Microphone device refused %d Hz and resampling disabled; re-raise error.",
                        desired_rate,
                    )
                    self._warned_resample_disabled = True
                raise

            info = None
            if device_index is not None:
                try:
                    info = self._audio.get_device_info_by_index(device_index)
                except Exception:
                    info = None
            if info is None:
                try:
                    info = self._audio.get_default_input_device_info()
                except Exception:
                    info = {}

            fallback_rate = int(info.get("defaultSampleRate", desired_rate))
            if fallback_rate == desired_rate:
                # If the rate matches but opening failed, re-raise original error.
                raise

            fallback_chunk = max(1, int(fallback_rate * self.frame_duration_ms / 1000))

            audio_logger.warning(
                "Microphone device does not support %d Hz; capturing at %d Hz and resampling.",
                desired_rate,
                fallback_rate,
            )

            stream = self._audio.open(
                format=self.format,
                channels=self.channels,
                rate=fallback_rate,
                input=True,
                frames_per_buffer=fallback_chunk,
                input_device_index=device_index,
                stream_callback=None,
            )

            self._resample_needed = True
            self._stream_rate = fallback_rate
            self._frames_per_buffer = fallback_chunk

            return stream

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
                            "default_sample_rate": info.get("defaultSampleRate"),
                        }
                    )
            return devices
        finally:
            audio.terminate()

    @staticmethod
    def validate_device_supports_format(
        device_index: int,
        sample_rate: int = 16000,
        channels: int = 1,
    ) -> Tuple[bool, Optional[str]]:
        """Validate that a device supports the required audio format.

        Args:
            device_index: PyAudio device index
            sample_rate: Target sample rate (default: 16000)
            channels: Number of channels (default: 1 for mono)

        Returns:
            Tuple of (is_supported, error_message)
        """
        audio = pyaudio.PyAudio()
        try:
            supported = audio.is_format_supported(
                sample_rate,
                input_device=device_index,
                input_channels=channels,
                input_format=pyaudio.paInt16,
            )
            return (True, None)
        except ValueError as e:
            return (False, str(e))
        finally:
            audio.terminate()

    @staticmethod
    def get_device_details(device_index: int) -> dict:
        """Get detailed information about a specific device.

        Args:
            device_index: PyAudio device index

        Returns:
            Dictionary with device details
        """
        audio = pyaudio.PyAudio()
        try:
            info = audio.get_device_info_by_index(device_index)
            details = {
                "index": device_index,
                "name": info.get("name"),
                "max_input_channels": info.get("maxInputChannels"),
                "max_output_channels": info.get("maxOutputChannels"),
                "default_sample_rate": info.get("defaultSampleRate"),
                "default_low_input_latency": info.get("defaultLowInputLatency"),
                "default_high_input_latency": info.get("defaultHighInputLatency"),
            }

            # Test 16kHz mono support
            supported, error = MicrophoneStream.validate_device_supports_format(
                device_index, 16000, 1
            )
            details["supports_16khz_mono"] = supported
            if not supported:
                details["format_error"] = error

            return details
        finally:
            audio.terminate()

    @staticmethod
    def print_device_info() -> None:
        """Print detailed information about all input devices."""
        devices = MicrophoneStream.list_input_devices()

        print("\n" + "=" * 70)
        print("Available Input Devices:")
        print("=" * 70)

        for device in devices:
            idx = device["index"]
            print(f"\nDevice {idx}: {device['name']}")
            print(f"  Max Channels: {device['channels']}")
            print(f"  Default Sample Rate: {device['default_sample_rate']} Hz")

            # Get detailed info
            details = MicrophoneStream.get_device_details(idx)
            if details["supports_16khz_mono"]:
                print(f"  16kHz Mono Support: ✅ YES")
            else:
                print(f"  16kHz Mono Support: ❌ NO")
                if "format_error" in details:
                    print(f"    Error: {details['format_error']}")

            # Highlight USB devices
            if "USB" in device["name"] or "Blue" in device["name"]:
                print(f"  Type: 🎤 USB Microphone (Recommended)")

        print("\n" + "=" * 70)
        print("\n💡 Tip: Use a device that supports 16kHz mono for best results")
        print("=" * 70 + "\n")
