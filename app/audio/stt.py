from __future__ import annotations

import json
import os
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:  # Optional dependency for noise gating
    import numpy as np
except ImportError:  # pragma: no cover - numpy optional
    np = None  # type: ignore[assignment]


try:
    from vosk import KaldiRecognizer, Model, SetLogLevel
except ImportError as exc:  # pragma: no cover - allows lazy dependency installation
    raise RuntimeError(
        "The 'vosk' package is required for speech recognition. Install it via 'pip install vosk'."
    ) from exc

from app.util.log import get_event_logger, now_ms


@dataclass
class TranscriptionResult:
    text: str
    is_final: bool
    confidence: Optional[float] = None
    alternatives: Optional[List[str]] = None


class StreamingTranscriber:
    """Manage a Vosk streaming recognizer for low-latency transcripts.

    This class provides real-time speech-to-text transcription with word-level
    confidence scoring and diagnostic capabilities to identify transcription issues.

    Features:
    - Word-level timing and confidence scores
    - Alternative transcription hypotheses
    - Low-confidence word tracking for vocabulary gap detection
    - Automatic logging of confidence metrics

    Args:
        model_path: Path to Vosk model directory (e.g., "models/vosk-model-en-us-0.22")
        sample_rate: Audio sample rate in Hz (must match audio input, typically 16000)
        model: Pre-loaded Vosk Model object (if provided, model_path is ignored)
        enable_words: Enable word-level timing and confidence scores (default: True)
        max_alternatives: Number of alternative transcription hypotheses (default: 3)

    Example:
        >>> transcriber = StreamingTranscriber(
        ...     model_path="models/vosk-model-en-us-0.22",
        ...     enable_words=True,
        ...     max_alternatives=3
        ... )
        >>> # Feed audio frames
        >>> result = transcriber.accept_audio(audio_frame)
        >>> # Get final transcription
        >>> text = transcriber.finalize()
        >>> # Check confidence
        >>> avg_conf = transcriber.get_average_confidence()
        >>> if avg_conf < 0.7:
        ...     print("Low confidence - possible vocabulary gap")
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        sample_rate: int = 16000,
        model: Optional[Model] = None,
        enable_words: bool = True,
        max_alternatives: int = 3,
        noise_gate_threshold: int = 0,
    ) -> None:
        model_path = model_path or os.getenv("VOSK_MODEL_PATH")
        if not model_path and model is None:
            raise RuntimeError("VOSK_MODEL_PATH environment variable or config must be set")

        try:  # Reduce verbose Kaldi logging
            SetLogLevel(-1)
        except Exception:  # pragma: no cover - defensive
            pass

        if model is None:
            if model_path is None:
                raise RuntimeError("VOSK_MODEL_PATH must be set when model is not provided")
            if not os.path.isdir(model_path):
                raise RuntimeError(f"Vosk model directory not found: {model_path}")
            self.model = Model(model_path)
        else:
            self.model = model

        self.sample_rate = sample_rate
        self.model_path = model_path
        self._enable_words = enable_words
        self._max_alternatives = max_alternatives
        self.noise_gate_threshold = max(0, int(noise_gate_threshold))
        self.recognizer = KaldiRecognizer(self.model, sample_rate)

        self._configure_recognizer()

        self._final_chunks: list[str] = []
        self._partial: str = ""
        self._latest_tokens: list[str] = []
        self._stopword_consumed: Counter[str] = Counter()
        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None
        self._finalized_text: Optional[str] = None
        self._partial_events: List[Dict[str, Any]] = []
        self._last_partial_logged: Optional[str] = None
        self._final_event: Optional[Dict[str, Any]] = None
        self._final_logged: bool = False
        self._last_result: Optional[Dict[str, Any]] = None
        self._low_confidence_words: List[Dict[str, Any]] = []
        self._last_alternatives: List[str] = []

    # --------------------------------------------------------------------- lifecycle
    def reset(self) -> None:
        self.recognizer = KaldiRecognizer(self.model, self.sample_rate)
        self._configure_recognizer()
        self._final_chunks.clear()
        self._partial = ""
        self._latest_tokens = []
        self._stopword_consumed = Counter()
        self._start_time = None
        self._end_time = None
        self._finalized_text = None
        self._partial_events = []
        self._last_partial_logged = None
        self._final_event = None
        self._final_logged = False
        self._last_result = None
        self._low_confidence_words = []
        self._last_alternatives = []

    def start(self) -> None:
        self.reset()

    def feed(self, frame: bytes, is_speech: Optional[bool] = None) -> TranscriptionResult:
        return self.accept_audio(frame)

    def accept_audio(self, frame: bytes) -> TranscriptionResult:
        if self._start_time is None:
            self._start_time = time.monotonic()

        frame = self._apply_noise_gate(frame)

        if self.recognizer.AcceptWaveform(frame):
            result = json.loads(self.recognizer.Result())
            self._last_result = result

            previous_partial = self._partial

            # Analyze confidence if word-level results available
            if "result" in result:
                self._analyze_confidence(result["result"])

            text, alternatives = self._resolve_transcription(result, previous_partial)
            avg_confidence = self.get_average_confidence()

            if text:
                self._final_chunks.append(text)
            self._partial = ""
            self._refresh_tokens()
            self._last_alternatives = alternatives
            return TranscriptionResult(
                text=self.transcript,
                is_final=True,
                confidence=avg_confidence,
                alternatives=alternatives or None,
            )

        partial_json = json.loads(self.recognizer.PartialResult())
        partial = partial_json.get("partial", "").strip()
        self._partial = partial
        self._refresh_tokens()
        self._record_partial(partial)
        self._last_alternatives = []
        return TranscriptionResult(text=partial, is_final=False)

    def end(self) -> None:
        if self._end_time is not None:
            return
        self._finalized_text = self.finalize()
        self._end_time = time.monotonic()

    def finalize(self) -> str:
        result = json.loads(self.recognizer.FinalResult())
        self._last_result = result
        previous_partial = self._partial

        text, alternatives = self._resolve_transcription(result, previous_partial)

        # Analyze confidence if word-level results available
        if "result" in result:
            self._analyze_confidence(result["result"])

        if text:
            self._final_chunks.append(text)
        self._partial = ""
        self._refresh_tokens()
        final_text = self.transcript
        avg_confidence = self.get_average_confidence()
        low_conf_words = self.get_low_confidence_words()
        self._last_alternatives = alternatives
        self._record_final(
            final_text,
            confidence=avg_confidence,
            low_confidence_words=low_conf_words,
            alternatives=alternatives,
        )
        return final_text

    # ------------------------------------------------------------------ internals
    def _configure_recognizer(self) -> None:
        """Apply recognizer options based on configuration flags."""
        if self._enable_words:
            self.recognizer.SetWords(True)
        if self._max_alternatives > 0:
            self.recognizer.SetMaxAlternatives(self._max_alternatives)

    def _resolve_transcription(
        self,
        result: Dict[str, Any],
        fallback_partial: Optional[str] = None,
    ) -> tuple[str, List[str]]:
        """Determine the best transcription text and alternatives from a Vosk result."""
        primary = result.get("text", "").strip()
        alternatives: List[str] = []

        for alt in result.get("alternatives", []):
            candidate = str(alt.get("text", "")).strip()
            if not candidate:
                continue
            if not primary:
                primary = candidate
                continue
            if candidate != primary and candidate not in alternatives:
                alternatives.append(candidate)

        if not primary and "result" in result:
            words = [
                str(word.get("word", "")).strip()
                for word in result["result"]
                if word.get("word")
            ]
            candidate = " ".join(w for w in words if w)
            if candidate:
                primary = candidate

        if not primary and fallback_partial:
            primary = fallback_partial.strip()

        # Ensure alternatives do not duplicate the primary text
        alternatives = [alt for alt in alternatives if alt and alt != primary]

        return primary, alternatives

    def _apply_noise_gate(self, frame: bytes) -> bytes:
        """Suppress samples below the configured threshold before recognition."""
        if not frame or self.noise_gate_threshold <= 0 or np is None:
            return frame

        try:
            samples = np.frombuffer(frame, dtype=np.int16)  # type: ignore[arg-type]
        except TypeError:
            return frame

        if samples.size == 0:
            return frame

        gated = np.where(np.abs(samples) > self.noise_gate_threshold, samples, 0)
        return gated.astype(np.int16).tobytes()

    # ------------------------------------------------------------------- properties
    @property
    def transcript(self) -> str:
        return " ".join(chunk for chunk in self._final_chunks if chunk)

    @property
    def partial(self) -> str:
        return self._partial

    @property
    def combined_text(self) -> str:
        combined = f"{self.transcript} {self._partial}".strip()
        return combined

    def elapsed_ms(self) -> int:
        if self._start_time is None:
            return 0
        end = self._end_time or time.monotonic()
        return int((end - self._start_time) * 1000)

    # ---------------------------------------------------------------- stopword utils
    def detect_stopword(self, word: str) -> bool:
        word_lower = word.lower()
        count = self._latest_tokens.count(word_lower)
        return count > self._stopword_consumed.get(word_lower, 0)

    def consume_stopword(self, word: str) -> None:
        word_lower = word.lower()
        if self._latest_tokens.count(word_lower) > self._stopword_consumed.get(word_lower, 0):
            self._stopword_consumed[word_lower] += 1

    def result(self) -> str:
        if self._end_time is None:
            self.end()
        text = self._finalized_text or self.transcript
        if not text:
            return ""
        tokens = text.split()
        consumed = Counter(self._stopword_consumed)
        kept_tokens: list[str] = []
        for token in tokens:
            lowered = token.lower()
            if consumed.get(lowered, 0) > 0:
                consumed[lowered] -= 1
                continue
            kept_tokens.append(token)
        return " ".join(kept_tokens).strip()

    def _refresh_tokens(self) -> None:
        combined = self.combined_text
        self._latest_tokens = combined.lower().split() if combined else []

    def _analyze_confidence(self, word_results: List[Dict[str, Any]]) -> None:
        """Analyze word-level confidence scores and track low-confidence words."""
        LOW_CONFIDENCE_THRESHOLD = 0.7

        for word_data in word_results:
            conf = word_data.get("conf", 1.0)
            word = word_data.get("word", "")

            if conf < LOW_CONFIDENCE_THRESHOLD:
                self._low_confidence_words.append({
                    "word": word,
                    "confidence": conf,
                    "start": word_data.get("start"),
                    "end": word_data.get("end")
                })
        if self._low_confidence_words:
            self._low_confidence_words.sort(key=lambda item: item.get("confidence", 1.0))

    def get_average_confidence(self) -> Optional[float]:
        """Calculate average confidence from last result.

        Returns:
            Average confidence score from 0.0 to 1.0, or ``None`` if no scores available.

        Interpretation:
            - > 0.8: High confidence, transcription likely accurate
            - 0.7-0.8: Moderate confidence, review recommended
            - < 0.7: Low confidence, possible accuracy issues or vocabulary gaps

        Example:
            >>> avg_conf = transcriber.get_average_confidence()
            >>> print(f"Confidence: {avg_conf:.2%}")
            Confidence: 87.5%
        """
        if not self._last_result or "result" not in self._last_result:
            return None

        confidences = [w.get("conf", 0.0) for w in self._last_result["result"] if "conf" in w]
        if not confidences:
            return None
        return sum(confidences) / len(confidences)

    def get_low_confidence_words(self) -> List[Dict[str, Any]]:
        """Get list of words with confidence below threshold (< 0.7).

        Returns:
            List of dictionaries with keys:
            - "word": The word text
            - "confidence": Confidence score (0.0-1.0)
            - "start": Start time in audio (seconds)
            - "end": End time in audio (seconds)

        Use this to identify:
        - Out-of-vocabulary (OOV) words that may need custom language model
        - Technical terms or proper nouns not in base model
        - Poorly articulated or distorted words

        Example:
            >>> low_conf = transcriber.get_low_confidence_words()
            >>> for word_data in low_conf:
            ...     print(f"{word_data['word']}: {word_data['confidence']:.2f}")
            kubernetes: 0.42
            prometheus: 0.58
        """
        return list(self._low_confidence_words)

    # ------------------------------------------------------------------- telemetry
    def _record_partial(self, text: str) -> None:
        if not text:
            return
        if text == self._last_partial_logged:
            return
        ts = now_ms()
        event = {"ts_ms": ts, "text": text}
        self._partial_events.append(event)
        try:
            get_event_logger().log_stt_partial(text)
        except Exception:
            pass
        self._last_partial_logged = text

    def _record_final(
        self,
        text: str,
        *,
        confidence: Optional[float],
        low_confidence_words: List[Dict[str, Any]],
        alternatives: List[str],
    ) -> None:
        if self._final_logged:
            return
        ts = now_ms()
        event_payload: Dict[str, Any] = {"ts_ms": ts, "text": text}
        if confidence is not None:
            event_payload["confidence"] = confidence
        if alternatives:
            event_payload["alternatives"] = alternatives
        if low_confidence_words:
            event_payload["low_confidence_words"] = [
                {"word": w.get("word"), "confidence": w.get("confidence")}
                for w in low_confidence_words
            ]
        self._final_event = event_payload
        try:
            get_event_logger().log_stt_final(
                text,
                confidence=confidence,
                low_confidence_words=low_confidence_words if low_confidence_words else None,
                alternatives=alternatives if alternatives else None,
            )
        except Exception:
            pass
        self._final_logged = True

    @property
    def partial_events(self) -> List[Dict[str, Any]]:
        return list(self._partial_events)

    @property
    def final_event(self) -> Optional[Dict[str, Any]]:
        return dict(self._final_event) if self._final_event else None

    @property
    def last_alternatives(self) -> List[str]:
        """Return alternative hypotheses from the most recent final result."""
        return list(self._last_alternatives)
