from __future__ import annotations

import collections
import time
from dataclasses import dataclass
from threading import Event
from typing import Callable, Optional

import webrtcvad

from app.audio.mic import MicrophoneStream
from app.audio.stt import StreamingTranscriber
from app.util.config import AppConfig
from app.util.log import get_event_logger


@dataclass
class SegmentCaptureResult:
    transcript: str
    clean_transcript: str
    audio_bytes: bytes
    stop_reason: str  # silence | done | cap | manual
    duration_ms: int
    audio_ms: int


def run_segment(
    mic: MicrophoneStream,
    stt: StreamingTranscriber,
    config: AppConfig,
    stop_event: Optional[Event] = None,
    on_chunk: Optional[Callable[[], None]] = None,
) -> SegmentCaptureResult:
    """
    Capture a full speech segment with pre-roll, VAD-based stop detection, and stop-word handling.

    Args:
        mic: Active microphone stream
        stt: Streaming transcriber
        config: Application configuration
        stop_event: Optional threading.Event to request manual stop
        on_chunk: Optional callback invoked after each audio chunk (useful for video capture)
    """

    logger = get_event_logger()
    logger.log_segment_start()

    sample_rate = config.sample_rate_hz
    chunk_samples = config.chunk_samples
    frame_ms = max(1, int((chunk_samples / sample_rate) * 1000))
    ring_frames = max(1, int(config.pre_roll_ms / frame_ms))

    vad = webrtcvad.Vad(config.vad_aggressiveness)
    ring = collections.deque(maxlen=ring_frames)
    frames: list[bytes] = []

    # Prime pre-roll buffer
    for _ in range(ring_frames):
        pcm = mic.read(chunk_samples)
        ring.append(pcm)
        if on_chunk:
            on_chunk()

    frames.extend(list(ring))

    stt.start()
    for frame in ring:
        stt.feed(frame)

    start_ms = int(time.time() * 1000)
    last_speech_ms = start_ms
    cap_deadline_ms = start_ms + config.max_segment_s * 1000
    has_spoken = False
    stop_reason = "cap"

    while True:
        if stop_event and stop_event.is_set():
            stop_reason = "manual"
            break

        now_ms = int(time.time() * 1000)
        if now_ms >= cap_deadline_ms:
            stop_reason = "cap"
            break

        pcm = mic.read(chunk_samples)
        frames.append(pcm)
        if on_chunk:
            on_chunk()

        speech = vad.is_speech(pcm, sample_rate)
        stt.feed(pcm, is_speech=speech)

        if stt.detect_stopword("done"):
            stt.consume_stopword("done")
            for _ in range(10):
                tail = mic.read(chunk_samples)
                frames.append(tail)
                if on_chunk:
                    on_chunk()
            stop_reason = "done"
            break

        if speech:
            has_spoken = True
            last_speech_ms = now_ms
        elif has_spoken and now_ms - last_speech_ms >= config.silence_ms:
            stop_reason = "silence"
            break

    stt.end()
    transcript = stt.transcript
    clean_transcript = stt.result()

    end_ms = int(time.time() * 1000)
    duration_ms = end_ms - start_ms
    audio_ms = len(frames) * frame_ms

    logger.log_segment_stop(
        stop_reason=stop_reason,
        stt_final_text=clean_transcript,
        audio_ms=audio_ms,
        stt_ms=stt.elapsed_ms(),
    )

    return SegmentCaptureResult(
        transcript=transcript,
        clean_transcript=clean_transcript,
        audio_bytes=b"".join(frames),
        stop_reason=stop_reason,
        duration_ms=duration_ms,
        audio_ms=audio_ms,
    )
