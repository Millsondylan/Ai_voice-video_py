from __future__ import annotations

import time
import re
from dataclasses import dataclass, field
from threading import Event
from typing import Any, Callable, Dict, List, Optional, Sequence

import webrtcvad
from difflib import SequenceMatcher

from app.audio import preprocessing
from app.audio.mic import MicrophoneStream
from app.audio.stt import StreamingTranscriber
from app.audio.agc import AutomaticGainControl, AdaptiveVAD
from app.util.config import AppConfig
from app.util.log import get_event_logger, logger as audio_logger


class FrameProcessor:
    """Apply lightweight per-frame audio cleanup before feeding STT."""

    def __init__(
        self,
        sample_rate: int,
        enable_noise_gate: bool = False,
        noise_gate_threshold: int = 500,
        enable_speech_filter: bool = False,
        highpass_hz: int = 80,
        lowpass_hz: int = 8000,
    ) -> None:
        self.sample_rate = sample_rate
        self.enable_noise_gate = enable_noise_gate
        self.noise_gate_threshold = noise_gate_threshold
        self.enable_speech_filter = enable_speech_filter
        self.highpass_hz = highpass_hz
        self.lowpass_hz = lowpass_hz
        self._warned_numpy = False
        self._warned_scipy = False

    @property
    def is_enabled(self) -> bool:
        return self.enable_noise_gate or self.enable_speech_filter

    def process(self, frame: bytes) -> bytes:
        if not self.is_enabled:
            return frame

        if not preprocessing.NUMPY_AVAILABLE:
            if not self._warned_numpy:
                audio_logger.warning(
                    "Audio preprocessing requested but NumPy is not installed; skipping noise cleanup."
                )
                self._warned_numpy = True
            return frame

        import numpy as np

        audio = np.frombuffer(frame, dtype=np.int16).astype(np.float32)

        if self.enable_speech_filter:
            if preprocessing.SCIPY_AVAILABLE:
                try:
                    audio = preprocessing.apply_speech_filter(
                        audio,
                        self.sample_rate,
                        highpass_freq=self.highpass_hz,
                        lowpass_freq=self.lowpass_hz,
                    )
                except Exception as exc:  # pragma: no cover - defensive logging
                    if not self._warned_scipy:
                        audio_logger.warning(
                            "Speech bandpass filter failed (%s); disabling filter for this session.",
                            exc,
                        )
                        self._warned_scipy = True
                    self.enable_speech_filter = False
            else:
                if not self._warned_scipy:
                    audio_logger.warning(
                        "Speech filter requested but SciPy is not installed; skipping filter."
                    )
                    self._warned_scipy = True
                self.enable_speech_filter = False

        audio = np.clip(audio, -32768, 32767).astype(np.int16)

        if self.enable_noise_gate:
            try:
                audio = preprocessing.apply_noise_gate(audio, threshold=self.noise_gate_threshold)
            except Exception as exc:  # pragma: no cover - defensive logging
                audio_logger.warning(
                    "Noise gate failed (%s); disabling gate for this session.",
                    exc,
                )
                self.enable_noise_gate = False

        return audio.tobytes()


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
    average_confidence: Optional[float] = None
    low_confidence_words: List[Dict[str, Any]] = field(default_factory=list)


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

    def _phrase_match(text: str, phrases: Sequence[str], threshold: float = 0.72) -> bool:
        """Return True if any phrase appears in text (exact or fuzzy)."""
        if not text:
            return False
        cleaned = re.sub(r"[^a-z\s]", " ", text.lower())
        tokens = cleaned.split()
        if not tokens:
            return False
        for phrase in phrases:
            phrase_clean = phrase.lower()
            if phrase_clean in cleaned:
                return True
            phrase_tokens = phrase_clean.split()
            span = len(phrase_tokens)
            if span == 0 or len(tokens) < span:
                continue
            for idx in range(len(tokens) - span + 1):
                candidate = " ".join(tokens[idx : idx + span])
                if SequenceMatcher(None, candidate, phrase_clean).ratio() >= threshold:
                    return True
        return False

    bye_variants = [
        "bye glasses",
        "by glasses",
        "buy glasses",
        "bi glasses",
        "goodbye glasses",
        "diagnosis bible",  # frequent misrecognition of "bye glasses"
    ]
    done_variants = [
        "done",
        "all done",
        "that's done",
        "we're done",
    ]

    sample_rate = config.sample_rate_hz
    chunk_samples = config.chunk_samples
    frame_ms = max(1, int((chunk_samples / sample_rate) * 1000))
    ring_frames = max(1, int(config.pre_roll_ms / frame_ms))

    noise_gate_threshold = getattr(config, "noise_gate_threshold", 0)
    apply_noise_gate = getattr(config, "apply_noise_gate", True) and noise_gate_threshold > 0
    frame_processor = FrameProcessor(
        sample_rate=sample_rate,
        enable_noise_gate=apply_noise_gate,
        noise_gate_threshold=noise_gate_threshold,
        enable_speech_filter=getattr(config, "apply_speech_filter", False),
        highpass_hz=getattr(config, "speech_filter_highpass_hz", 80),
        lowpass_hz=getattr(config, "speech_filter_lowpass_hz", 8000),
    )

    # FIX: Initialize AGC for automatic audio level normalization during capture
    # This ensures consistent audio levels even if microphone volume changes during recording
    enable_agc = getattr(config, "enable_agc", True)
    agc = AutomaticGainControl(
        target_rms=6000.0,    # INCREASED for louder output
        min_gain=1.0,
        max_gain=20.0,        # INCREASED to 20x boost for very quiet speech
        attack_rate=0.9,
        release_rate=0.999
    ) if enable_agc else None

    # FIX: Use adaptive VAD for capture (auto-selected level based on environment)
    adaptive_vad = AdaptiveVAD(sample_rate=sample_rate)

    logger = get_event_logger()
    logger.log_segment_start(
        vad_aggr=config.vad_aggressiveness,
        silence_ms=config.silence_ms,
        chunk_ms=frame_ms,
        pre_roll_ms=config.pre_roll_ms,
    )

    # FIX: DIAGNOSTIC LOGGING - Log capture configuration for debugging
    audio_logger.info(
        f"Capture config: VAD={config.vad_aggressiveness}, silence={config.silence_ms}ms, "
        f"pre_roll={config.pre_roll_ms}ms, min_speech_frames={getattr(config, 'min_speech_frames', 3)}, "
        f"chunk_ms={frame_ms}ms, sample_rate={sample_rate}Hz, AGC={'enabled' if enable_agc else 'disabled'}"
    )

    # FIX: Initialize VAD with configurable aggressiveness (0=most sensitive, 3=least sensitive)
    # Mode 1-2 recommended for general use; lower values catch softer speech
    vad = webrtcvad.Vad(config.vad_aggressiveness)
    
    # FIX: CRITICAL - Reset and start STT transcriber
    # This ensures transcriber is in clean state for each capture segment
    audio_logger.info("Resetting and starting STT transcriber...")
    stt.reset()
    stt.start()

    frames: list[bytes] = []

    # FIX: RELIABLE PRE-ROLL BUFFER - Ensures we don't miss the beginning of speech
    # Seed pre-roll from wake listener (if provided), otherwise read fresh frames.
    # This buffers audio BEFORE speech starts so first syllables aren't lost.
    # NOTE: Pre-roll frames from wake.py already have AGC applied
    pre_frames = list(pre_roll_buffer)[-ring_frames:] if pre_roll_buffer else []
    missing = max(0, ring_frames - len(pre_frames))
    for _ in range(missing):
        raw_pcm = mic.read(chunk_samples)
        # Apply AGC to newly read frames (pre-roll buffer doesn't need it)
        pcm = agc.process(raw_pcm) if agc else raw_pcm
        pre_frames.append(pcm)
        if on_chunk:
            on_chunk()

    # FIX: Prepend buffered audio to recording so speech capture is complete from the start
    for frame in pre_frames:
        frames.append(frame)
        processed = frame_processor.process(frame)
        stt.feed(processed)

    start_time = time.time()
    last_speech_time = start_time
    has_spoken = any(vad.is_speech(frame, sample_rate) for frame in frames)
    first_speech_logged = has_spoken
    stop_reason = "cap"

    # FIX: GRACE PERIOD - Don't check for silence in first 1000ms after wake word
    # This gives user time to start speaking without being cut off
    grace_period_ms = 1000
    grace_period_end_time = start_time + (grace_period_ms / 1000.0)

    # FIX: CONSECUTIVE SILENCE TRACKING - Prevents premature cutoff on brief pauses
    # Track consecutive silence frames to avoid ending recording during short hesitations.
    # This ensures we don't cut off mid-sentence if the user takes a breath or pauses briefly.
    consecutive_silence_frames = 0
    total_speech_frames = sum(1 for f in frames if vad.is_speech(f, sample_rate))

    # FIX: MINIMUM SPEECH FRAMES - Require sufficient speech before allowing silence detection
    # This prevents the system from stopping too early after just 1-2 words
    min_speech_frames = getattr(config, 'min_speech_frames', 3)

    # FIX: DIAGNOSTIC LOGGING - Track pre-roll buffer state
    if has_spoken:
        audio_logger.info(
            f"[CAPTURE] VAD detected speech during pre-roll ({total_speech_frames} speech frames); "
            f"grace_period={grace_period_ms}ms; capturing segment"
        )
    else:
        audio_logger.info(
            f"[CAPTURE] No speech in pre-roll buffer ({len(frames)} frames); "
            f"grace_period={grace_period_ms}ms; waiting for user to speak..."
        )

    def append_frame(pcm: bytes) -> None:
        """Append a frame to recording (already has AGC applied from caller)."""
        frames.append(pcm)
        processed_pcm = frame_processor.process(pcm)
        stt.feed(processed_pcm)
        if on_chunk:
            on_chunk()

    def drain_tail(frame_count: int) -> None:
        """Read and append tail padding frames with AGC."""
        for _ in range(frame_count):
            raw_tail = mic.read(chunk_samples)
            # Apply AGC to tail frames
            tail = agc.process(raw_tail) if agc else raw_tail
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

        # FIX: Read frame and apply AGC for consistent audio levels
        raw_pcm = mic.read(chunk_samples)
        pcm = agc.process(raw_pcm) if agc else raw_pcm
        append_frame(pcm)

        # FIX: Use adaptive VAD that auto-calibrates to environment
        speech = adaptive_vad.is_speech(pcm)

        combined_lower = stt.combined_text.lower()
        if _phrase_match(combined_lower, bye_variants, threshold=0.58):
            stt.consume_stopword("bye")
            stt.consume_stopword("glasses")
            drain_tail(10)
            stop_reason = "bye"
            break

        if stt.detect_stopword("done") or _phrase_match(combined_lower, done_variants, threshold=0.8):
            stt.consume_stopword("done")
            drain_tail(8)
            stop_reason = "done"
            break

        if speech:
            has_spoken = True
            last_speech_time = now_time
            consecutive_silence_frames = 0  # FIX: Reset silence counter on speech
            total_speech_frames += 1
            if not first_speech_logged:
                # FIX: DIAGNOSTIC - Log exact timing when first speech is detected
                time_to_first_speech_ms = int((now_time - start_time) * 1000)
                audio_logger.info(
                    f"[VAD→SPEECH] First voice detected at +{time_to_first_speech_ms}ms "
                    f"(total frames: {len(frames)})"
                )
                first_speech_logged = True
        else:
            # FIX: GRACE PERIOD - Skip silence detection during initial grace period
            in_grace_period = now_time < grace_period_end_time
            if in_grace_period:
                continue  # Don't check for silence yet

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
                    audio_logger.info(
                        f"[VAD→SILENCE] Silence for {silence_duration_ms:.0f}ms "
                        f"(threshold={config.silence_ms}ms); ending capture"
                    )
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
    average_confidence = stt.get_average_confidence()
    low_confidence_words = stt.get_low_confidence_words()

    # FIX: Log AGC statistics after capture completes
    if agc:
        agc_stats = agc.get_stats()
        audio_logger.info(
            f"[AGC] Capture complete: Final gain {agc_stats['current_gain']:.2f}x "
            f"({agc_stats['current_gain_db']:+.1f}dB), "
            f"RMS {agc_stats['running_rms']:.0f}/{agc_stats['target_rms']:.0f}, "
            f"Processed {agc_stats['frame_count']} frames"
        )

    if average_confidence is not None and average_confidence < 0.7:
        audio_logger.warning(
            "Low average confidence detected (%.2f). Consider fallback STT or vocabulary tuning.",
            average_confidence,
        )

    duration_ms = int((time.time() - start_time) * 1000)
    audio_ms = len(frames) * frame_ms

    logger.log_segment_stop(
        stop_reason=stop_reason,
        stt_final_text=clean_transcript,
        audio_ms=audio_ms,
        stt_ms=stt.elapsed_ms(),
        avg_confidence=average_confidence,
        low_confidence_words=low_confidence_words if low_confidence_words else None,
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
        average_confidence=average_confidence,
        low_confidence_words=low_confidence_words,
    )
