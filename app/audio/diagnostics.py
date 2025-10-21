from __future__ import annotations

import audioop
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pyaudio
import webrtcvad

# =============================================================================
# CORE AUDIO CONSTANTS
# =============================================================================

SAMPLE_RATE = 16000
AUDIO_FORMAT = pyaudio.paInt16
CHANNELS = 1
CHUNK_SIZE = 4096  # Frames per chunk (≈256 ms at 16 kHz)
CHUNK_BYTES = CHUNK_SIZE * 2  # 16-bit samples
VAD_FRAME_MS = 30
VAD_FRAME_SIZE = int(SAMPLE_RATE * VAD_FRAME_MS / 1000)  # Samples per VAD frame
VAD_FRAME_BYTES = VAD_FRAME_SIZE * 2  # 16-bit samples


# =============================================================================
# LOGGING / DIAGNOSTICS
# =============================================================================

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("VoiceAssistant")


class AudioDiagnostics:
    """Track audio levels and event timing across the pipeline."""

    def __init__(self) -> None:
        self.start_time = time.time()
        self.events: List[Dict[str, object]] = []
        self.audio_levels: Deque[float] = deque(maxlen=100)

    # --------------------------------------------------------------------- utils
    def _elapsed(self) -> float:
        return time.time() - self.start_time

    def log_event(self, stage: str, **kwargs) -> None:
        """Log a pipeline event with timestamped metadata."""
        timestamp = self._elapsed()
        event = {"timestamp": timestamp, "stage": stage}
        if kwargs:
            event.update(kwargs)
        self.events.append(event)

        message = f"[{timestamp:7.3f}s] {stage}"
        for key, value in kwargs.items():
            message += f" | {key}={value}"
        logger.info(message)

    def log_audio_chunk(self, audio_data: bytes, stage: str) -> Tuple[int, float]:
        """Compute and log audio level statistics for an audio chunk."""
        rms = audioop.rms(audio_data, 2)
        db = 20 * np.log10(rms / 32768.0) if rms > 0 else -96.0

        self.audio_levels.append(rms)
        avg_rms = float(np.mean(self.audio_levels)) if self.audio_levels else 0.0

        self.log_event(
            stage,
            rms=f"{rms:5d}",
            db=f"{db:6.2f}",
            avg_rms=f"{avg_rms:.0f}",
            chunk_bytes=len(audio_data),
        )

        bar_length = min(int((rms / 1000) * 20), 40)
        bar = "█" * max(bar_length, 0)
        if rms < 500:
            status = "⚠️  TOO QUIET"
        elif rms > 20000:
            status = "⚠️  CLIPPING"
        else:
            status = "✓ GOOD"
        logger.debug(f"    Audio: [{bar:<40}] {status}")
        return rms, db


diagnostics = AudioDiagnostics()


# =============================================================================
# AUDIO GAIN / NORMALIZATION
# =============================================================================

def apply_gain_to_audio(audio_data: bytes, gain_db: float) -> bytes:
    """Apply fixed gain with clipping prevention."""
    if not audio_data:
        return audio_data
    audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
    gain_factor = 10 ** (gain_db / 20.0)
    processed = np.clip(audio_array * gain_factor, -32768, 32767)
    return processed.astype(np.int16).tobytes()


def normalize_audio_rms(audio_data: bytes, target_rms_db: float = -20.0) -> bytes:
    """Normalize audio to a target RMS level."""
    if not audio_data:
        return audio_data

    audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
    if not audio_array.size:
        return audio_data

    rms = np.sqrt(np.mean(audio_array ** 2))
    if rms < 1e-10:
        return audio_data

    current_db = 20 * np.log10(rms / 32768.0)
    gain_db = target_rms_db - current_db
    gain_factor = 10 ** (gain_db / 20.0)

    processed = np.clip(audio_array * gain_factor, -32768, 32767)
    return processed.astype(np.int16).tobytes()


def diagnose_audio_levels(
    stream,
    duration_seconds: int = 5,
    sample_rate: int = SAMPLE_RATE,
    chunk_frames: int = CHUNK_SIZE,
) -> Dict[str, float]:
    """Capture audio for a duration and report RMS/DB statistics."""
    logger.info("=" * 60)
    logger.info("AUDIO LEVEL DIAGNOSTIC - Speak normally for %s seconds", duration_seconds)
    logger.info("=" * 60)

    rms_values: List[int] = []
    db_values: List[float] = []

    chunks_to_record = int((sample_rate / chunk_frames) * duration_seconds)
    for _ in range(chunks_to_record):
        audio_chunk = stream.read(chunk_frames, exception_on_overflow=False)
        rms = audioop.rms(audio_chunk, 2)
        db = 20 * np.log10(rms / 32768.0) if rms > 0 else -96.0

        rms_values.append(rms)
        db_values.append(db)

        bar = "█" * min(int(rms / 100), 50)
        print(f"\rRMS: {rms:5d} | dB: {db:6.2f} | {bar:<50}", end="")

    print()
    logger.info("=" * 60)
    logger.info("AUDIO LEVEL ANALYSIS RESULTS")
    logger.info("=" * 60)
    stats = {
        "min_rms": float(min(rms_values) if rms_values else 0),
        "avg_rms": float(np.mean(rms_values) if rms_values else 0),
        "max_rms": float(max(rms_values) if rms_values else 0),
        "min_db": float(min(db_values) if db_values else -96.0),
        "avg_db": float(np.mean(db_values) if db_values else -96.0),
        "max_db": float(max(db_values) if db_values else -96.0),
    }
    for key, value in stats.items():
        logger.info("%s: %.2f", key, value)

    avg_rms = stats["avg_rms"]
    if avg_rms < 500:
        needed_gain_db = 20 * np.log10(1000 / max(avg_rms, 1))
        logger.warning("⚠️  AUDIO TOO QUIET - Apply +%.1f dB gain", needed_gain_db)
        stats["recommended_gain_db"] = needed_gain_db
    elif avg_rms > 15000:
        logger.warning("⚠️  AUDIO TOO LOUD - Reduce gain or check mic settings")
    else:
        logger.info("✓ Audio levels look good")
    logger.info("=" * 60)
    return stats


# =============================================================================
# VAD MANAGEMENT
# =============================================================================

class VADManager:
    """Wrap WebRTC VAD with frame buffering for stable speech detection."""

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        frame_duration_ms: int = VAD_FRAME_MS,
        aggressiveness: int = 3,
        buffer_frames: int = 10,
    ) -> None:
        if frame_duration_ms not in (10, 20, 30):
            raise ValueError("frame_duration_ms must be 10, 20, or 30")
        if sample_rate not in (8000, 16000, 32000, 48000):
            raise ValueError("sample_rate must be 8000, 16000, 32000, or 48000")

        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)
        self.frame_bytes = self.frame_size * 2
        self.vad = webrtcvad.Vad(aggressiveness)
        self.ring_buffer: Deque[Tuple[bytes, bool]] = deque(maxlen=buffer_frames)
        self.triggered = False

        diagnostics.log_event(
            "VAD_INITIALIZED",
            sample_rate=sample_rate,
            frame_ms=frame_duration_ms,
            aggressiveness=aggressiveness,
            frame_bytes=self.frame_bytes,
        )

    def is_speech(self, audio_chunk: bytes) -> bool:
        """Return True if the frame contains speech."""
        frame = audio_chunk
        if len(frame) != self.frame_bytes:
            diagnostics.log_event(
                "VAD_FRAME_MISMATCH",
                expected=self.frame_bytes,
                actual=len(frame),
            )
            if len(frame) < self.frame_bytes:
                frame = frame + b"\x00" * (self.frame_bytes - len(frame))
            else:
                frame = frame[: self.frame_bytes]

        try:
            is_speech = self.vad.is_speech(frame, self.sample_rate)
            diagnostics.log_event("VAD_RESULT", is_speech=is_speech, chunk_bytes=len(frame))
            return is_speech
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("VAD error: %s", exc)
            return False

    def process_with_buffer(self, audio_chunk: bytes) -> Tuple[bool, bool]:
        """Return (speech_started, speech_ended) using buffering thresholds."""
        is_speech = self.is_speech(audio_chunk)
        self.ring_buffer.append((audio_chunk, is_speech))

        voiced = sum(1 for _, speech in self.ring_buffer if speech)
        speech_started = False
        speech_ended = False

        if not self.triggered and self.ring_buffer:
            if voiced > 0.8 * len(self.ring_buffer):
                self.triggered = True
                speech_started = True
                diagnostics.log_event(
                    "SPEECH_STARTED",
                    voiced_frames=voiced,
                    total_frames=len(self.ring_buffer),
                )
        elif self.triggered and self.ring_buffer:
            if voiced < 0.2 * len(self.ring_buffer):
                self.triggered = False
                speech_ended = True
                diagnostics.log_event(
                    "SPEECH_ENDED",
                    voiced_frames=voiced,
                    total_frames=len(self.ring_buffer),
                )

        return speech_started, speech_ended

    def reset(self) -> None:
        """Reset VAD state."""
        self.ring_buffer.clear()
        self.triggered = False
        diagnostics.log_event("VAD_RESET")


# =============================================================================
# AUDIO BUFFERS
# =============================================================================

class AudioRingBuffer:
    """Rolling buffer of recent audio chunks."""

    def __init__(self, duration_seconds: float = 1.0, chunk_bytes: int = CHUNK_BYTES, sample_rate: int = SAMPLE_RATE):
        # Estimate how many chunks to retain based on duration; assume chunk_bytes correspond to CHUNK_SIZE frames
        frames_per_chunk = CHUNK_SIZE
        chunks_to_store = max(1, int((sample_rate / frames_per_chunk) * duration_seconds))
        self.chunk_bytes = chunk_bytes
        self.buffer: Deque[bytes] = deque(maxlen=chunks_to_store)
        diagnostics.log_event(
            "RING_BUFFER_CREATED",
            duration_sec=duration_seconds,
            max_chunks=chunks_to_store,
            total_bytes=chunks_to_store * chunk_bytes,
        )

    def add(self, chunk: bytes) -> None:
        self.buffer.append(chunk)

    def get_all(self) -> bytes:
        return b"".join(self.buffer)

    def clear(self) -> None:
        self.buffer.clear()

    def get_size(self) -> int:
        return len(self.buffer)


# =============================================================================
# TIMEOUT MANAGEMENT
# =============================================================================

class TimeoutManager:
    """Manage silence-based timeouts with natural pauses."""

    def __init__(
        self,
        no_speech_timeout_ms: int = 3000,
        mid_speech_pause_ms: int = 1500,
        min_recording_duration_ms: int = 500,
    ) -> None:
        self.no_speech_timeout_ms = no_speech_timeout_ms
        self.mid_speech_pause_ms = mid_speech_pause_ms
        self.min_recording_duration_ms = min_recording_duration_ms
        self.recording_start_time: Optional[float] = None
        self.last_speech_time: Optional[float] = None
        self.speech_detected_yet = False
        diagnostics.log_event(
            "TIMEOUT_MANAGER_INIT",
            no_speech_timeout_ms=no_speech_timeout_ms,
            mid_speech_pause_ms=mid_speech_pause_ms,
            min_recording_ms=min_recording_duration_ms,
        )

    def start_recording(self) -> None:
        self.recording_start_time = time.time()
        self.last_speech_time = None
        self.speech_detected_yet = False
        diagnostics.log_event("TIMEOUT_RECORDING_START")

    def update_speech_detected(self) -> None:
        self.last_speech_time = time.time()
        if not self.speech_detected_yet:
            self.speech_detected_yet = True
            diagnostics.log_event("TIMEOUT_FIRST_SPEECH_DETECTED")

    def check_timeout(self) -> Tuple[bool, Optional[str]]:
        if self.recording_start_time is None:
            return False, None

        now = time.time()
        recording_duration_ms = (now - self.recording_start_time) * 1000

        if not self.speech_detected_yet:
            if recording_duration_ms > self.no_speech_timeout_ms:
                diagnostics.log_event("TIMEOUT_NO_SPEECH", duration_ms=recording_duration_ms)
                return True, "no_speech"
            return False, None

        if self.last_speech_time is None:
            return False, None

        silence_duration_ms = (now - self.last_speech_time) * 1000
        if recording_duration_ms < self.min_recording_duration_ms:
            return False, None

        if silence_duration_ms > self.mid_speech_pause_ms:
            diagnostics.log_event(
                "TIMEOUT_SPEECH_ENDED",
                silence_ms=silence_duration_ms,
                total_duration_ms=recording_duration_ms,
            )
            return True, "speech_ended"
        return False, None

    def reset(self) -> None:
        self.recording_start_time = None
        self.last_speech_time = None
        self.speech_detected_yet = False
        diagnostics.log_event("TIMEOUT_RESET")


# =============================================================================
# HYBRID SPEECH DETECTOR
# =============================================================================

@dataclass
class HybridDetectionResult:
    is_speech: bool
    confidence: float
    vad_score: float
    volume_score: float
    rms: int


class HybridSpeechDetector:
    """Combine WebRTC VAD with RMS thresholding for resilient detection."""

    def __init__(
        self,
        vad_manager: VADManager,
        volume_threshold: int = 500,
        vad_weight: float = 0.7,
        volume_weight: float = 0.3,
        activation_threshold: float = 0.5,
    ) -> None:
        self.vad_manager = vad_manager
        self.volume_threshold = volume_threshold
        self.vad_weight = vad_weight
        self.volume_weight = volume_weight
        self.activation_threshold = activation_threshold
        diagnostics.log_event(
            "HYBRID_DETECTOR_INIT",
            volume_threshold=volume_threshold,
            vad_weight=vad_weight,
            volume_weight=volume_weight,
            activation_threshold=f"{activation_threshold:.2f}",
        )

    def detect_speech(self, audio_chunk: bytes) -> HybridDetectionResult:
        vad_frame = audio_chunk[: self.vad_manager.frame_bytes]
        vad_result = self.vad_manager.is_speech(vad_frame)
        vad_score = 1.0 if vad_result else 0.0

        rms = audioop.rms(audio_chunk, 2)
        volume_score = min(rms / (self.volume_threshold * 2), 1.0)
        combined_score = vad_score * self.vad_weight + volume_score * self.volume_weight
        is_speech = combined_score >= self.activation_threshold

        diagnostics.log_event(
            "HYBRID_DETECTION",
            vad=vad_result,
            rms=rms,
            volume_score=f"{volume_score:.2f}",
            combined_score=f"{combined_score:.2f}",
            activation_threshold=f"{self.activation_threshold:.2f}",
            is_speech=is_speech,
        )

        return HybridDetectionResult(
            is_speech=is_speech,
            confidence=combined_score,
            vad_score=vad_score,
            volume_score=volume_score,
            rms=rms,
        )
