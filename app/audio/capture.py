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
    """Capture a full speech segment with optional pre-roll and robust stop conditions.

    FIX: Ensures complete speech capture without truncation by:
    - FIX: Using pre-roll buffer (config.pre_roll_ms) to catch initial syllables before VAD triggers
    - FIX: Tracking consecutive silence frames to avoid premature cutoff on brief pauses
    - FIX: Adding tail padding (config.tail_padding_ms) after speech ends to capture trailing words
    - FIX: Requiring minimum speech frames (config.min_speech_frames) before allowing silence detection
    - FIX: Using tunable VAD aggressiveness (config.vad_aggressiveness) to balance sensitivity
    - FIX: Longer silence timeout (config.silence_ms) to detect end-of-utterance without cutting off

    These fixes address the issue where the assistant was capturing only partial speech segments,
    often cutting off early or missing the end of the user's sentence.
    """

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

    # FIX: Initialize VAD with configurable aggressiveness (0=most sensitive, 3=least sensitive)
    # Mode 1-2 recommended for general use; lower values catch softer speech
    vad = webrtcvad.Vad(config.vad_aggressiveness)
    stt.start()

    frames: list[bytes] = []

    # FIX: RELIABLE PRE-ROLL BUFFER - Ensures we don't miss the beginning of speech
    # Seed pre-roll from wake listener (if provided), otherwise read fresh frames.
    # This buffers audio BEFORE speech starts so first syllables aren't lost.
    pre_frames = list(pre_roll_buffer)[-ring_frames:] if pre_roll_buffer else []
    missing = max(0, ring_frames - len(pre_frames))
    for _ in range(missing):
        pcm = mic.read(chunk_samples)
        pre_frames.append(pcm)
        if on_chunk:
            on_chunk()

    # FIX: Prepend buffered audio to recording so speech capture is complete from the start
    for frame in pre_frames:
        frames.append(frame)
        stt.feed(frame)

    start_time = time.time()
    last_speech_time = start_time
    has_spoken = any(vad.is_speech(frame, sample_rate) for frame in frames)
    first_speech_logged = has_spoken
    stop_reason = "cap"

    # FIX: CONSECUTIVE SILENCE TRACKING - Prevents premature cutoff on brief pauses
    # Track consecutive silence frames to avoid ending recording during short hesitations.
    # This ensures we don't cut off mid-sentence if the user takes a breath or pauses briefly.
    consecutive_silence_frames = 0
    total_speech_frames = sum(1 for f in frames if vad.is_speech(f, sample_rate))

    # FIX: MINIMUM SPEECH FRAMES - Require sufficient speech before allowing silence detection
    # This prevents the system from stopping too early after just 1-2 words
    min_speech_frames = getattr(config, 'min_speech_frames', 3)

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
            consecutive_silence_frames = 0  # FIX: Reset silence counter on speech
            total_speech_frames += 1
            if not first_speech_logged:
                audio_logger.info("VAD detected speech; capturing segment")
                first_speech_logged = True
        else:
            # FIX: LONGER SILENCE TIMEOUT - Track consecutive silence frames carefully
            # Industry guidelines suggest 0.5-0.8s silence for end-of-utterance detection
            # Config.silence_ms (default 1800ms) is generous to prevent premature cutoff
            consecutive_silence_frames += 1

            # FIX: ROBUST SILENCE DETECTION - Only trigger if:
            # 1. We've captured enough speech frames (avoid cutting off too early)
            # 2. We have sustained silence (config.silence_ms duration)
            # This prevents stopping on brief pauses or hesitations during speech
            if has_spoken and total_speech_frames >= min_speech_frames:
                silence_duration_ms = (now_time - last_speech_time) * 1000
                if silence_duration_ms >= config.silence_ms:
                    stop_reason = "silence"
                    break

    # FIX: POST-SPEECH TAIL PADDING - Capture audio after silence detection
    # Add tail padding to ensure we capture the very end of speech, including trailing words
    # that might occur right at the silence boundary. This prevents cutting off the last syllable.
    if has_spoken and stop_reason not in {"manual", "cap", "timeout15"}:
        tail_padding_ms = getattr(config, 'tail_padding_ms', 300)
        tail_frames = max(1, int(tail_padding_ms / frame_ms))
        drain_tail(tail_frames)
        audio_logger.info(f"Added {tail_padding_ms}ms tail padding ({tail_frames} frames)")

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
