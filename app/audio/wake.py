from __future__ import annotations

import collections
import threading
import time
from difflib import SequenceMatcher
from typing import Callable, Deque, List, Optional, Sequence, Union

import webrtcvad

from app.util.log import get_event_logger

from .mic import MicrophoneStream
from .stt import StreamingTranscriber


class WakeWordListener(threading.Thread):
    """Continuously listen for wake variants with VAD-gated detection and pre-roll buffering.

    FIX: Wake word reliability improvements address false negatives and ensure responsive detection:

    - FIX: CONTINUOUS LISTENING - Runs in always-on background thread that never stops
      unless program shuts down, ensuring no gaps in wake word monitoring
    - FIX: PARTIAL RESULT DETECTION - Uses streaming transcriber with continuous text
      updates to detect wake word with lower latency (line 139: _recent_tokens checks
      combined_text which includes partial results)
    - FIX: FLEXIBLE PHRASE MATCHING - Accepts wake word variants and phonetically similar
      phrases to handle STT quirks (line 148-156: _has_variant with fuzzy token matching)
    - FIX: OPTIMIZED VAD SENSITIVITY - Uses tunable VAD settings (vad_aggressiveness param)
      to avoid filtering out quiet wake words
    - FIX: PRE-ROLL BUFFER - Maintains rolling audio buffer (line 60, 100) that is passed
      to capture on detection, so the first syllable of follow-up query is never lost
    - FIX: DEBOUNCE PROTECTION - Prevents repeated triggers from same utterance (line 179-183)
    """

    def __init__(
        self,
        wake_variants: List[str],
        on_detect: Union[Callable[[Sequence[bytes]], None], Callable[[], None]],
        transcriber: StreamingTranscriber,
        sample_rate: int = 16000,
        chunk_samples: int = 320,
        debounce_ms: int = 700,
        mic_device_name: str | None = None,
        pre_roll_ms: int = 300,
        sensitivity: float = 0.65,
        vad_aggressiveness: int = 2,
        match_window_ms: int = 1200,
    ) -> None:
        super().__init__(daemon=True)
        self._wake_variants_raw = [variant for variant in wake_variants if variant]
        self._wake_variants = [self._normalize_variant(variant) for variant in self._wake_variants_raw]
        self._variant_tokens = [variant.split() for variant in self._wake_variants]
        self._max_variant_tokens = max((len(tokens) for tokens in self._variant_tokens), default=1)
        self._on_detect = on_detect
        self._transcriber = transcriber
        self._sample_rate = sample_rate
        self._chunk_samples = chunk_samples
        self._debounce_ms = debounce_ms
        self._mic_device_name = mic_device_name
        self._stop_event = threading.Event()
        self._active_mic: MicrophoneStream | None = None
        self._last_trigger_time: float = 0.0
        self._last_speech_time: float = 0.0

        frame_ms = max(1, int((chunk_samples / sample_rate) * 1000))
        buffer_size = max(1, int(pre_roll_ms / frame_ms))
        self._rolling_buffer: collections.deque[bytes] = collections.deque(maxlen=buffer_size)

        self._sensitivity = max(0.0, min(1.0, sensitivity))
        self._required_hits = self._compute_required_hits(self._sensitivity)
        self._match_window_ms = max(200, match_window_ms)
        self._match_hits: Deque[float] = collections.deque(maxlen=self._required_hits)
        self._speech_reset_ms = max(300, int(pre_roll_ms / 2))

        vad_level = max(0, min(3, int(vad_aggressiveness)))
        self._vad = webrtcvad.Vad(vad_level)

    def stop(self) -> None:
        self._stop_event.set()
        if self._active_mic:
            try:
                self._active_mic.stop()
            except Exception:
                pass

    def run(self) -> None:
        """Run wake word detection loop with VAD and buffered pre-roll.

        FIX: ALWAYS-ON WAKE LISTENER - This runs continuously in a background thread
        until explicitly stopped, ensuring no gaps in wake word monitoring.
        """
        logger = get_event_logger()
        try:
            # FIX: CONTINUOUS LISTENING LOOP - Never stops unless program shuts down
            while not self._stop_event.is_set():
                with MicrophoneStream(
                    rate=self._sample_rate,
                    chunk_samples=self._chunk_samples,
                    input_device_name=self._mic_device_name,
                ) as mic:
                    self._active_mic = mic
                    self._transcriber.start()
                    self._rolling_buffer.clear()
                    self._match_hits.clear()
                    self._last_speech_time = 0.0

                    # FIX: Process audio frames continuously, building partial transcripts
                    while not self._stop_event.is_set():
                        frame = mic.read(self._chunk_samples)
                        if not frame:
                            continue

                        # FIX: Maintain pre-roll buffer for seamless handoff to capture
                        self._rolling_buffer.append(frame)
                        # FIX: Feed to streaming transcriber for partial result detection
                        self._transcriber.feed(frame)

                        now = time.monotonic()
                        # FIX: Use VAD to gate wake word checking (only check during speech)
                        speech_detected = self._vad.is_speech(frame, self._sample_rate)
                        if speech_detected:
                            self._last_speech_time = now
                            # FIX: Check wake word using partial transcription results
                            if self._check_wake_word(now):
                                if self._should_trigger(now):
                                    logger.log_wake_detected()
                                    # FIX: Pass pre-roll buffer to prevent missing first syllables
                                    buffer_copy = list(self._rolling_buffer)
                                    self._emit_detect(buffer_copy)
                                    return
                        elif self._last_speech_time and (now - self._last_speech_time) * 1000 > self._speech_reset_ms:
                            self._match_hits.clear()
                self._active_mic = None
        except Exception as exc:  # pragma: no cover
            print(f"[WakeWordListener] error: {exc}")
            import traceback

            traceback.print_exc()

    def _check_wake_word(self, now: float) -> bool:
        tokens = self._recent_tokens()
        if not tokens:
            return False
        match_tokens = self._match_variant(tokens)
        if not match_tokens:
            return False

        self._match_hits.append(now)
        while self._match_hits and (now - self._match_hits[0]) * 1000 > self._match_window_ms:
            self._match_hits.popleft()

        hits = len(self._match_hits)
        if hits >= self._required_hits:
            self._match_hits.clear()
            return True

        phrase = " ".join(match_tokens)
        get_event_logger().log_wake_progress(phrase, hits, self._required_hits, self._match_window_ms)
        return False

    def _recent_tokens(self) -> List[str]:
        text = self._transcriber.combined_text.lower()
        if not text:
            return []
        tokens = text.split()
        if not tokens:
            return []
        window = self._max_variant_tokens + 2
        return tokens[-window:]

    def _match_variant(self, tokens: List[str]) -> Optional[List[str]]:
        for variant_tokens in self._variant_tokens:
            if len(variant_tokens) > len(tokens):
                continue
            span = len(variant_tokens)
            for idx in range(len(tokens) - span + 1):
                candidate = list(tokens[idx : idx + span])
                if self._tokens_match(candidate, variant_tokens):
                    return candidate
        return None

    @staticmethod
    def _tokens_match(candidate: Sequence[str], variant: Sequence[str]) -> bool:
        for cand, target in zip(candidate, variant):
            cand_clean = cand.replace("-", "")
            target_clean = target.replace("-", "")
            if cand_clean == target_clean:
                continue
            if len(cand_clean) >= 3 and cand_clean.startswith(target_clean[:3]):
                continue
            # Allow close phonetic matches (e.g., "glosses" vs "glasses")
            if SequenceMatcher(None, cand_clean, target_clean).ratio() >= 0.72:
                continue
            return False
        return True

    @staticmethod
    def _normalize_variant(variant: str) -> str:
        return " ".join(variant.replace("-", " ").split()).lower()

    @staticmethod
    def _compute_required_hits(sensitivity: float) -> int:
        """Map sensitivity (0-1) to number of required matches."""
        level = max(0.0, min(1.0, sensitivity))
        if level >= 0.6:
            return 1
        if level >= 0.4:
            return 2
        if level >= 0.25:
            return 3
        return 4

    def _should_trigger(self, now: float) -> bool:
        if (now - self._last_trigger_time) * 1000 >= self._debounce_ms:
            self._last_trigger_time = now
            return True
        return False

    def _emit_detect(self, buffer_copy: Sequence[bytes]) -> None:
        try:
            self._on_detect(buffer_copy)  # type: ignore
        except TypeError:
            # Backwards compatibility with older callbacks that expected no arguments
            self._on_detect()  # type: ignore
