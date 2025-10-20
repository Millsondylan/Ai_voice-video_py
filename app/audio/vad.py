from __future__ import annotations

import time
from dataclasses import dataclass

import webrtcvad


class VoiceActivityDetector:
    """Wrapper over WebRTC VAD for PCM16 audio."""

    def __init__(self, sample_rate: int = 16000, frame_duration_ms: int = 30, aggressiveness: int = 2) -> None:
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self._vad = webrtcvad.Vad(aggressiveness)
        self._expected_frame_bytes = int(sample_rate * frame_duration_ms / 1000 * 2)

    def is_speech(self, frame: bytes) -> bool:
        if len(frame) != self._expected_frame_bytes:
            raise ValueError("Unexpected frame length for configured duration")
        return self._vad.is_speech(frame, self.sample_rate)


@dataclass
class SilenceTracker:
    silence_ms: int
    frame_ms: int

    def __post_init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._last_speech_ts = time.monotonic()

    def update(self, speech_detected: bool) -> bool:
        if speech_detected:
            self._last_speech_ts = time.monotonic()
            return False
        elapsed_ms = (time.monotonic() - self._last_speech_ts) * 1000
        return elapsed_ms >= self.silence_ms
