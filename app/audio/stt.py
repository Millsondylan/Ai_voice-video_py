from __future__ import annotations

import json
import os
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

    def reset(self) -> None:
        self.recognizer = KaldiRecognizer(self.model, self.sample_rate)
        self._final_chunks.clear()

    def accept_audio(self, frame: bytes) -> TranscriptionResult:
        if self.recognizer.AcceptWaveform(frame):
            result = json.loads(self.recognizer.Result())
            text = result.get("text", "").strip()
            if text:
                self._final_chunks.append(text)
            return TranscriptionResult(text=self.transcript, is_final=True)

        partial_json = json.loads(self.recognizer.PartialResult())
        partial = partial_json.get("partial", "").strip()
        return TranscriptionResult(text=partial, is_final=False)

    @property
    def transcript(self) -> str:
        return " ".join(chunk for chunk in self._final_chunks if chunk)

    def finalize(self) -> str:
        result = json.loads(self.recognizer.FinalResult())
        text = result.get("text", "").strip()
        if text:
            self._final_chunks.append(text)
        return self.transcript
