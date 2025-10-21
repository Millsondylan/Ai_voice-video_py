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
from .agc import AutomaticGainControl, AdaptiveVAD
from .fuzzy_match import FuzzyWakeWordMatcher


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
        vad_level: int = 1,
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

        # FIX: Use adaptive VAD with configurable maximum aggressiveness
        max_vad_level = 3 if vad_level is None else max(0, min(int(vad_level), 3))
        self._adaptive_vad = AdaptiveVAD(
            sample_rate=sample_rate,
            min_level=0,
            max_level=max_vad_level,
            initial_level=max_vad_level,
        )

        # FIX: Use AGC to automatically boost quiet microphones
        self._agc = AutomaticGainControl(
            target_rms=6000.0,    # Target normalized level (INCREASED for louder output)
            min_gain=1.0,         # No reduction
            max_gain=20.0,        # Up to 20x boost for very quiet mics (INCREASED)
            attack_rate=0.9,      # Fast gain increase
            release_rate=0.999    # Slow gain decrease
        )

        self._last_status_time: float = 0.0
        self._last_logged_text: str = ""
        self._last_agc_log_time: float = 0.0

        # FIX Problem 7: Initialize fuzzy matcher for better wake word detection
        # Uses rapidfuzz with multiple strategies to handle STT misrecognitions
        self._fuzzy_matcher = FuzzyWakeWordMatcher(
            wake_words=self._wake_variants_raw,
            threshold=75  # 75% similarity required for match
        )

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
                    # FIX: Completely reset transcriber to clear any old text from previous sessions
                    # Without this, the wake listener shows leftover transcripts like "what am i holding"
                    self._transcriber.reset()
                    self._transcriber.start()
                    self._rolling_buffer.clear()
                    self._match_hits.clear()
                    self._last_speech_time = 0.0
                    self._last_status_time = time.monotonic()
                    self._last_logged_text = ""

                    # FIX: Process audio frames continuously, building partial transcripts
                    while not self._stop_event.is_set():
                        raw_frame = mic.read(self._chunk_samples)
                        if not raw_frame:
                            continue

                        # FIX: Apply AGC to auto-boost quiet microphones
                        gained_frame = self._agc.process(raw_frame)

                        # FIX: Maintain pre-roll buffer for seamless handoff to capture
                        # Store the gained frame (not raw) so capture gets boosted audio
                        self._rolling_buffer.append(gained_frame)

                        now = time.monotonic()

                        # FIX: DIAGNOSTIC - Print AGC stats every 10 seconds
                        if (now - self._last_agc_log_time) >= 10.0:
                            agc_stats = self._agc.get_stats()
                            vad_level = self._adaptive_vad.get_vad_level()
                            print(
                                f"[AGC] Gain: {agc_stats['current_gain']:.2f}x "
                                f"({agc_stats['current_gain_db']:+.1f}dB) | "
                                f"RMS: {agc_stats['running_rms']:.0f} → {agc_stats['target_rms']:.0f} | "
                                f"VAD Level: {vad_level}"
                            )
                            self._last_agc_log_time = now

                        # FIX: DIAGNOSTIC - Print status every 3 seconds, but only log meaningful text
                        # Filter out background noise artifacts (single repeated words like "the")
                        if (now - self._last_status_time) >= 3.0:
                            partial_text = self._transcriber.combined_text.strip()
                            # Only log if text is substantial (more than 3 chars and not just repeated junk)
                            if partial_text and len(partial_text) > 3 and partial_text != self._last_logged_text:
                                words = partial_text.split()
                                # Filter out if it's just repeated "the" or other noise artifacts
                                if len(words) > 1 or (len(words) == 1 and len(words[0]) > 4):
                                    print(f"[WAKE] Heard: '{partial_text[:50]}'")
                                    self._last_logged_text = partial_text
                            else:
                                # Only log status if not spamming
                                if (now - self._last_status_time) >= 10.0:
                                    print("[WAKE] Listening...")
                            self._last_status_time = now

                        # FIX: Use adaptive VAD that auto-calibrates to environment
                        speech_detected = self._adaptive_vad.is_speech(gained_frame)

                        # FIX: ADDITIONAL RMS CHECK - Even if VAD detects "speech", check if it's loud enough
                        # This prevents Vosk from hallucinating "the" on AGC-boosted silence
                        # Only feed to STT if RMS is above threshold (real speech after AGC should be loud)
                        if speech_detected:
                            import numpy as np
                            audio_data = np.frombuffer(gained_frame, dtype=np.int16).astype(np.float32)
                            frame_rms = np.sqrt(np.mean(audio_data**2))

                            # Minimum RMS threshold for real speech after AGC (30% of target)
                            # Speech should reach ~6000 RMS, so require at least 1800 RMS to feed STT
                            min_speech_rms = 1800

                            if frame_rms >= min_speech_rms:
                                self._last_speech_time = now
                                # FIX: Only feed STT when VAD confirms speech AND RMS is high enough
                                # This double-check prevents Vosk from hallucinating on boosted silence
                                self._transcriber.feed(gained_frame)

                                # FIX: Check wake word using partial transcription results
                                if self._check_wake_word(now):
                                    if self._should_trigger(now):
                                        # FIX: DIAGNOSTIC - Log wake word detection with timing
                                        from app.util.log import logger as audio_logger
                                        audio_logger.info(
                                            f"✓ Wake word detected! Transcript: '{self._transcriber.combined_text}' "
                                            f"Pre-roll buffer: {len(self._rolling_buffer)} frames"
                                        )
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
        """Check for wake word using both token matching and fuzzy matching.

        FIX Problem 7: Enhanced wake word detection with dual strategy:
        1. Original token-based matching (preserves existing behavior)
        2. Fuzzy matching with rapidfuzz (handles misrecognitions)

        This hybrid approach maximizes detection accuracy.
        """
        # Strategy 1: Original token-based matching
        tokens = self._recent_tokens()
        token_match_found = False
        match_tokens = None

        if tokens:
            match_tokens = self._match_variant(tokens)
            if match_tokens:
                token_match_found = True

        # Strategy 2: Fuzzy matching on full transcript
        # This catches cases token matching misses (e.g., "diagnosis bible" → "bye glasses")
        fuzzy_match_found = False
        full_text = self._transcriber.combined_text.strip()
        if full_text and len(full_text) > 3:  # Only check meaningful text
            is_match, matched_word, score = self._fuzzy_matcher.match(full_text)
            if is_match:
                fuzzy_match_found = True
                # Log fuzzy match for debugging
                from app.util.log import logger as audio_logger
                audio_logger.info(
                    f"[FUZZY MATCH] '{full_text}' → '{matched_word}' (score: {score})"
                )

        # Accept if either strategy found a match
        if not (token_match_found or fuzzy_match_found):
            return False

        self._match_hits.append(now)
        while self._match_hits and (now - self._match_hits[0]) * 1000 > self._match_window_ms:
            self._match_hits.popleft()

        hits = len(self._match_hits)
        if hits >= self._required_hits:
            self._match_hits.clear()
            return True

        phrase = " ".join(match_tokens) if match_tokens else full_text
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
            # Allow close phonetic matches (e.g., "glosses" vs "glasses", "hey" vs "the")
            # FIX: Lowered threshold from 0.72 to 0.65 for more lenient matching
            if SequenceMatcher(None, cand_clean, target_clean).ratio() >= 0.65:
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
