from __future__ import annotations

import json
import os
import time
from collections import Counter
from dataclasses import dataclass
from typing import Optional


try:
    from vosk import KaldiRecognizer, Model
except ImportError as exc:  # pragma: no cover - allows lazy dependency installation
    raise RuntimeError(
        "The 'vosk' package is required for speech recognition. Install it via 'pip install vosk'."
    ) from exc


@dataclass
class TranscriptionResult:
    text: str
    is_final: bool


class StreamingTranscriber:
    """Manage a Vosk streaming recognizer for low-latency transcripts."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        sample_rate: int = 16000,
        model: Optional[Model] = None,
    ) -> None:
        model_path = model_path or os.getenv("VOSK_MODEL_PATH")
        if not model_path and model is None:
            raise RuntimeError("VOSK_MODEL_PATH environment variable or config must be set")
        if model is None:
            if not os.path.isdir(model_path):
                raise RuntimeError(f"Vosk model directory not found: {model_path}")
            self.model = Model(model_path)
        else:
            self.model = model

        self.sample_rate = sample_rate
        self.model_path = model_path
        self.recognizer = KaldiRecognizer(self.model, sample_rate)

        self._final_chunks: list[str] = []
        self._partial: str = ""
        self._latest_tokens: list[str] = []
        self._stopword_consumed: Counter[str] = Counter()
        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None
        self._finalized_text: Optional[str] = None

    # --------------------------------------------------------------------- lifecycle
    def reset(self) -> None:
        self.recognizer = KaldiRecognizer(self.model, self.sample_rate)
        self._final_chunks.clear()
        self._partial = ""
        self._latest_tokens = []
        self._stopword_consumed = Counter()
        self._start_time = None
        self._end_time = None
        self._finalized_text = None

    def start(self) -> None:
        self.reset()

    def feed(self, frame: bytes, is_speech: Optional[bool] = None) -> TranscriptionResult:
        return self.accept_audio(frame)

    def accept_audio(self, frame: bytes) -> TranscriptionResult:
        if self._start_time is None:
            self._start_time = time.monotonic()

        if self.recognizer.AcceptWaveform(frame):
            result = json.loads(self.recognizer.Result())
            text = result.get("text", "").strip()
            if text:
                self._final_chunks.append(text)
            self._partial = ""
            self._refresh_tokens()
            return TranscriptionResult(text=self.transcript, is_final=True)

        partial_json = json.loads(self.recognizer.PartialResult())
        partial = partial_json.get("partial", "").strip()
        self._partial = partial
        self._refresh_tokens()
        return TranscriptionResult(text=partial, is_final=False)

    def end(self) -> None:
        if self._end_time is not None:
            return
        self._finalized_text = self.finalize()
        self._end_time = time.monotonic()

    def finalize(self) -> str:
        result = json.loads(self.recognizer.FinalResult())
        text = result.get("text", "").strip()
        if text:
            self._final_chunks.append(text)
        self._partial = ""
        self._refresh_tokens()
        return self.transcript

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
