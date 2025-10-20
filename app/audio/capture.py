from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Event
from typing import Any, Callable, Dict, List, Optional, Sequence

import webrtcvad

from app.audio.mic import MicrophoneStream
from app.audio.stt import StreamingTranscriber
from app.util.config import AppConfig
from app.util.log import get_event_logger, logger as audio_logger


@dataclass
class SegmentCaptureResult:
    transcript: str
    clean_transcript: str
    audio_bytes: bytes
    stop_reason: str  # silence | done | cap | manual | timeout15 | bye
    duration_ms: int
    audio_ms: int
    partial_events: List[Dict[str, Any]]
    final_event: Optional[Dict[str, Any]]


def run_segment(
    mic: MicrophoneStream,
    stt: StreamingTranscriber,
    config: AppConfig,
    stop_event: Optional[Event] = None,
    on_chunk: Optional[Callable[[], None]] = None,
    pre_roll_buffer: Optional[Sequence[bytes]] = None,
    no_speech_timeout_ms: Optional[int] = None,
) -> SegmentCaptureResult:
    """Capture a full speech segment with optional pre-roll and robust stop conditions."""

    sample_rate = config.sample_rate_hz
    chunk_samples = config.chunk_samples
    frame_ms = max(1, int((chunk_samples / sample_rate) * 1000))
    ring_frames = max(1, int(config.pre_roll_ms / frame_ms))

    logger = get_event_logger()
    logger.log_segment_start(
        vad_aggr=config.vad_aggressiveness,
        silence_ms=config.silence_ms,
        chunk_ms=frame_ms,
        pre_roll_ms=config.pre_roll_ms,
    )

    vad = webrtcvad.Vad(config.vad_aggressiveness)
    stt.start()

    frames: list[bytes] = []

    # Seed pre-roll from wake listener (if provided), otherwise read fresh frames.
    pre_frames = list(pre_roll_buffer)[-ring_frames:] if pre_roll_buffer else []
    missing = max(0, ring_frames - len(pre_frames))
    for _ in range(missing):
        pcm = mic.read(chunk_samples)
        pre_frames.append(pcm)
        if on_chunk:
            on_chunk()

    for frame in pre_frames:
        frames.append(frame)
        stt.feed(frame)

    start_time = time.time()
    last_speech_time = start_time
    has_spoken = any(vad.is_speech(frame, sample_rate) for frame in frames)
    first_speech_logged = has_spoken
    stop_reason = "cap"

    if has_spoken:
        audio_logger.info("VAD detected speech during pre-roll; capturing segment")

    def append_frame(pcm: bytes) -> None:
        frames.append(pcm)
        stt.feed(pcm)
        if on_chunk:
            on_chunk()

    def drain_tail(frame_count: int) -> None:
        for _ in range(frame_count):
            tail = mic.read(chunk_samples)
            append_frame(tail)

    while True:
        if stop_event and stop_event.is_set():
            stop_reason = "manual"
            break

        now_time = time.time()
        elapsed_ms = int((now_time - start_time) * 1000)

        if elapsed_ms >= config.max_segment_s * 1000:
            stop_reason = "cap"
            break

        if (not has_spoken) and no_speech_timeout_ms is not None and elapsed_ms >= no_speech_timeout_ms:
            stop_reason = "timeout15"
            break

        pcm = mic.read(chunk_samples)
        append_frame(pcm)

        speech = vad.is_speech(pcm, sample_rate)

        combined_lower = stt.combined_text.lower()
        if "bye glasses" in combined_lower:
            stt.consume_stopword("bye")
            stt.consume_stopword("glasses")
            drain_tail(10)
            stop_reason = "bye"
            break

        if stt.detect_stopword("done"):
            stt.consume_stopword("done")
            drain_tail(10)
            stop_reason = "done"
            break

        if speech:
            has_spoken = True
            last_speech_time = now_time
            if not first_speech_logged:
                audio_logger.info("VAD detected speech; capturing segment")
                first_speech_logged = True
        elif has_spoken and (now_time - last_speech_time) * 1000 >= config.silence_ms:
            stop_reason = "silence"
            break

    if has_spoken and stop_reason not in {"manual", "cap", "timeout15"}:
        drain_tail(max(1, int(200 / frame_ms)))

    stt.end()
    transcript = stt.transcript
    clean_transcript = stt.result()

    duration_ms = int((time.time() - start_time) * 1000)
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
        partial_events=list(stt.partial_events),
        final_event=stt.final_event,
    )
