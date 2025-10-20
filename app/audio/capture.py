from __future__ import annotations

import collections
import time
from dataclasses import dataclass
from typing import Optional

import webrtcvad

from app.audio.mic import MicrophoneStream
from app.audio.stt import StreamingTranscriber
from app.util.config import AppConfig
from app.util.log import get_event_logger


@dataclass
class SegmentCaptureResult:
    """Result of a full segment capture."""

    transcript: str
    clean_transcript: str
    audio_bytes: bytes
    stop_reason: str  # "silence" | "stopword" | "cap"
    duration_ms: int


def run_segment(
    mic: MicrophoneStream,
    stt: StreamingTranscriber,
    config: AppConfig,
    stop_event: Optional[object] = None,
) -> SegmentCaptureResult:
    """
    Capture a full audio segment with pre-roll buffer and robust stop detection.

    Args:
        mic: Active microphone stream
        stt: Streaming transcriber instance
        config: Application configuration
        stop_event: Optional threading.Event to allow external stop request

    Returns:
        SegmentCaptureResult with transcript, audio, and metadata
    """
    logger = get_event_logger()
    logger.log_segment_start()

    # Configuration
    vad_aggr = config.vad_aggressiveness
    silence_ms = config.silence_ms
    chunk_samples = config.chunk_samples
    sample_rate = config.sample_rate_hz
    pre_roll_ms = config.pre_roll_ms
    max_segment_s = config.max_segment_s

    # Calculate frame duration from chunk size
    frame_ms = int((chunk_samples / sample_rate) * 1000)
    ring_frames = pre_roll_ms // frame_ms

    # Initialize VAD
    vad = webrtcvad.Vad(vad_aggr)

    # Pre-roll ring buffer
    ring = collections.deque(maxlen=ring_frames)
    frames = []

    # Prime the pre-roll buffer
    for _ in range(ring_frames):
        pcm = mic.read()
        ring.append(pcm)

    # Start segment: include pre-roll in final audio
    frames.extend(list(ring))

    # Reset and start STT
    stt.reset()

    # Timing
    start_time_ms = int(time.time() * 1000)
    last_speech_ms = start_time_ms
    cap_deadline_ms = start_time_ms + (max_segment_s * 1000)

    # Main capture loop
    stop_reason = "unknown"
    has_spoken = False

    while True:
        # Check external stop event
        if stop_event and hasattr(stop_event, "is_set") and stop_event.is_set():
            stop_reason = "external_stop"
            break

        # Check time cap
        now_ms = int(time.time() * 1000)
        if now_ms >= cap_deadline_ms:
            stop_reason = "cap"
            break

        # Read audio frame
        pcm = mic.read()
        frames.append(pcm)

        # VAD check
        is_speech = vad.is_speech(pcm, sample_rate=sample_rate)

        # Feed to STT (continuous feeding, including silence for timing)
        stt.accept_audio(pcm)

        # Track speech activity
        if is_speech:
            has_spoken = True
            last_speech_ms = now_ms

        # Stop-word detection (streaming)
        if stt.detect_stopword("done"):
            stt.consume_stopword("done")
            # Brief grace period to capture last phoneme
            for _ in range(10):
                pcm = mic.read()
                frames.append(pcm)
            stop_reason = "stopword"
            break

        # Silence timeout (only after speech has been detected)
        if has_spoken:
            silence_duration_ms = now_ms - last_speech_ms
            if silence_duration_ms >= silence_ms:
                stop_reason = "silence"
                break

    # Finalize transcription
    stt.finalize()
    transcript = stt.transcript
    clean_transcript = stt.get_clean_transcript()

    # Calculate total duration
    end_time_ms = int(time.time() * 1000)
    total_duration_ms = end_time_ms - start_time_ms
    audio_bytes = b"".join(frames)

    # Calculate actual audio duration from frames
    audio_ms = int((len(frames) * chunk_samples / sample_rate) * 1000)
    stt_ms = total_duration_ms

    # Log completion
    logger.log_segment_stop(
        stop_reason=stop_reason,
        stt_final_text=clean_transcript,
        audio_ms=audio_ms,
        stt_ms=stt_ms,
    )

    return SegmentCaptureResult(
        transcript=transcript,
        clean_transcript=clean_transcript,
        audio_bytes=audio_bytes,
        stop_reason=stop_reason,
        duration_ms=total_duration_ms,
    )
