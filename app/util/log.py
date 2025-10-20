from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# Human-readable logging (stdout + optional log file)
# ---------------------------------------------------------------------------

logger = logging.getLogger("glasses.audio")
logger.setLevel(logging.INFO)

if not logger.handlers:
    formatter = logging.Formatter(
        "[%(asctime)s] %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    try:
        file_handler = logging.FileHandler("glasses-debug.log", mode="a", encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        # If the log file cannot be created we still want runtime logging
        pass


def now_ms() -> int:
    """Return current timestamp in milliseconds."""
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# Structured JSON logger
# ---------------------------------------------------------------------------


class StructuredLogger:
    """
    JSONL logger with optional session context and in-memory timeline.
    Each log call appends a record to disk and remembers it for timeline export.
    """

    def __init__(self, output_path: Path | str = "glasses_events.jsonl") -> None:
        self._lock = RLock()
        self._path = Path(output_path)
        self._session_id: Optional[str] = None
        self._session_state: Optional[str] = None
        self._turn_index: Optional[int] = None
        self._history_tokens: Optional[int] = None
        self._sinks: List[Callable[[Dict[str, Any]], None]] = []
        self._session_start_ms: Optional[int] = None
        self._timeline: list[dict] = []
        self._partials: list[dict] = []

    # ------------------------------------------------------------------ context
    def set_output_path(self, path: Path | str) -> None:
        with self._lock:
            self._path = Path(path)

    @property
    def output_path(self) -> Path:
        with self._lock:
            return self._path

    def start_session(self, session_id: str) -> None:
        with self._lock:
            self._session_id = session_id
            self._session_state = None
            self._turn_index = None
            self._history_tokens = None
            self._session_start_ms = now_ms()
            self._timeline.clear()
            self._partials.clear()

    def update_state(
        self,
        *,
        session_state: Optional[str] = None,
        turn_index: Optional[int] = None,
        history_tokens: Optional[int] = None,
    ) -> None:
        with self._lock:
            if session_state is not None:
                self._session_state = session_state
            if turn_index is not None:
                self._turn_index = turn_index
            if history_tokens is not None:
                self._history_tokens = history_tokens

    def reset(self) -> None:
        with self._lock:
            self._session_id = None
            self._session_state = None
            self._turn_index = None
            self._history_tokens = None
            self._session_start_ms = None
            self._timeline.clear()
            self._partials.clear()
            self._sinks.clear()

    def register_sink(self, sink: Callable[[Dict[str, Any]], None]) -> None:
        with self._lock:
            self._sinks.append(sink)

    def clear_sinks(self) -> None:
        with self._lock:
            self._sinks.clear()

    def remove_sink(self, sink: Callable[[Dict[str, Any]], None]) -> None:
        with self._lock:
            try:
                self._sinks.remove(sink)
            except ValueError:
                pass

    # ------------------------------------------------------------------- utils
    def _context_fields(self) -> Dict[str, Any]:
        context: Dict[str, Any] = {}
        if self._session_id is not None:
            context["session_id"] = self._session_id
        if self._session_state is not None:
            context["session_state"] = self._session_state
        if self._turn_index is not None:
            context["turn_index"] = self._turn_index
        if self._history_tokens is not None:
            context["history_tokens"] = self._history_tokens
        return context

    # --------------------------------------------------------------------- io
    def log(self, event: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        record: Dict[str, Any] = {"ts": now_ms(), "event": event}
        record.update(self._context_fields())
        if payload:
            record.update(payload)

        line = json.dumps(record, ensure_ascii=True)
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            for sink in self._sinks:
                try:
                    sink(dict(record))
                except Exception:
                    logger.debug("Structured logger sink failed", exc_info=True)
            rel_ts = 0 if self._session_start_ms is None else record["ts"] - self._session_start_ms
            self._timeline.append(
                {
                    "ts": record["ts"],
                    "rel_ms": rel_ts,
                    "event": event,
                    "payload": payload or {},
                    "turn_index": self._turn_index,
                    "session_state": self._session_state,
                }
            )
        return record

    # ---------------------------------------------------------------- exports
    def add_partial(self, text: str) -> None:
        entry = self.log("stt.partial", {"text": text})
        with self._lock:
            self._partials.append({"ts": entry["ts"], "text": text})

    def record_final(self, text: str) -> None:
        self.log("stt.final_text", {"text": text})

    def partial_history(self) -> list[dict]:
        with self._lock:
            return list(self._partials)

    def timeline(self) -> list[dict]:
        with self._lock:
            return list(self._timeline)

    def timeline_lines(self) -> list[str]:
        with self._lock:
            lines: list[str] = []
            for entry in self._timeline:
                payload = entry.get("payload", {})
                payload_str = "" if not payload else json.dumps(payload, ensure_ascii=True)
                turn = entry.get("turn_index")
                state = entry.get("session_state")
                turn_tag = f"turn={turn}" if turn is not None else "turn=-"
                state_tag = f"state={state}" if state else "state=-"
                lines.append(
                    f"{entry['rel_ms']:>7}ms | {turn_tag} | {state_tag} | {entry['event']}"
                    f"{' ' if payload_str else ''}{payload_str}"
                )
            return lines


_structured_logger = StructuredLogger()


def get_structured_logger() -> StructuredLogger:
    return _structured_logger


# ---------------------------------------------------------------------------
# Audio event helper (maintains backwards-compatible interface)
# ---------------------------------------------------------------------------


class AudioEventLogger:
    """Structured logger for audio system events."""

    def __init__(self) -> None:
        self._wake_detected_at: Optional[int] = None
        self._segment_start_at: Optional[int] = None
        self._segment_stop_at: Optional[int] = None
        self._stop_reason: Optional[str] = None
        self._stt_final_text: Optional[str] = None
        self._stt_ms_total: Optional[int] = None
        self._audio_ms_total: Optional[int] = None
        self._tts_started_at: Optional[int] = None
        self._tts_done_at: Optional[int] = None
        self._tts_error: Optional[str] = None
        self._structured = get_structured_logger()

    # ---------------------------------------------------------------- context
    def start_session(self, session_id: str) -> None:
        self._structured.start_session(session_id)
        self._structured.log("session.id", {"value": session_id})

    def set_state(self, state: str) -> None:
        self._structured.update_state(session_state=state)
        self._structured.log("session.state", {"state": state})

    def set_turn(self, turn_index: int) -> None:
        self._structured.update_state(turn_index=turn_index)
        self._structured.log("session.turn.index", {"turn_index": turn_index})

    def set_history_tokens(self, total: int) -> None:
        self._structured.update_state(history_tokens=total)
        self._structured.log("session.history.tokens", {"total": total})

    def log_wake_detected(self) -> None:
        self._wake_detected_at = now_ms()
        logger.info("Wake word detected")
        self._structured.log("wake.detected_at", {"wake_detected_ms": self._wake_detected_at})

    def log_segment_start(
        self,
        *,
        vad_aggr: int,
        silence_ms: int,
        chunk_ms: int,
        pre_roll_ms: int,
    ) -> None:
        self._segment_start_at = now_ms()
        logger.info(
            "Segment recording started (vad=%s silence_ms=%s chunk_ms=%s pre_roll_ms=%s)",
            vad_aggr,
            silence_ms,
            chunk_ms,
            pre_roll_ms,
        )
        self._structured.log(
            "segment.started_at",
            {
                "segment_start_ms": self._segment_start_at,
                "vad_aggr": vad_aggr,
                "silence_ms": silence_ms,
                "chunk_ms": chunk_ms,
                "pre_roll_ms": pre_roll_ms,
            },
        )

    def log_segment_stop(
        self,
        stop_reason: str,
        stt_final_text: str,
        audio_ms: int,
        stt_ms: int,
    ) -> None:
        self._segment_stop_at = now_ms()
        self._stop_reason = stop_reason
        self._stt_final_text = stt_final_text
        self._audio_ms_total = audio_ms
        self._stt_ms_total = stt_ms

        duration_ms = (
            self._segment_stop_at - self._segment_start_at
            if self._segment_start_at
            else 0
        )

        logger.info(
            "Segment stopped (reason=%s duration_ms=%s audio_ms=%s stt_ms=%s)",
            stop_reason,
            duration_ms,
            audio_ms,
            stt_ms,
        )
        self._structured.log(
            "segment.stopped_at",
            {
                "segment_stop_ms": self._segment_stop_at,
                "stop_reason": stop_reason,
                "duration_ms": duration_ms,
                "audio_ms": audio_ms,
                "stt_ms": stt_ms,
                "stt_final_text": stt_final_text,
            },
        )

    def log_tts_started(self, text: str) -> None:
        self._tts_started_at = now_ms()
        preview = text[:80]
        logger.info("TTS started len=%d", len(text))
        self._structured.log(
            "tts.text",
            {
                "tts_started_ms": self._tts_started_at,
                "text_preview": preview,
                "text_len": len(text),
            },
        )

    def log_tts_done(self) -> None:
        self._tts_done_at = now_ms()
        duration_ms = (
            self._tts_done_at - self._tts_started_at if self._tts_started_at else 0
        )
        logger.info("TTS completed in %d ms", duration_ms)
        self._structured.log(
            "tts.ms",
            {
                "tts_done_ms": self._tts_done_at,
                "duration_ms": duration_ms,
            },
        )

    def log_tts_error(self, error: str, retry: bool = False) -> None:
        self._tts_error = error
        retry_str = " (retrying)" if retry else ""
        logger.error("TTS error%s: %s", retry_str, error)
        self._structured.log(
            "tts.error",
            {
                "tts": {
                    "error": error,
                    "retry": retry,
                }
            },
        )

    def log_stt_partial(self, text: str) -> None:
        self._structured.add_partial(text)

    def log_stt_final(self, text: str) -> None:
        self._stt_final_text = text
        self._structured.record_final(text)

    def get_summary(self) -> dict:
        return {
            "wake_detected_at": self._wake_detected_at,
            "segment_start_at": self._segment_start_at,
            "segment_stop_at": self._segment_stop_at,
            "stop_reason": self._stop_reason,
            "stt_final_text": self._stt_final_text,
            "stt_ms_total": self._stt_ms_total,
            "audio_ms_total": self._audio_ms_total,
            "tts_started_at": self._tts_started_at,
            "tts_done_at": self._tts_done_at,
            "tts_error": self._tts_error,
        }

    def reset(self) -> None:
        self._wake_detected_at = None
        self._segment_start_at = None
        self._segment_stop_at = None
        self._stop_reason = None
        self._stt_final_text = None
        self._stt_ms_total = None
        self._audio_ms_total = None
        self._tts_started_at = None
        self._tts_done_at = None
        self._tts_error = None


_event_logger = AudioEventLogger()


def get_event_logger() -> AudioEventLogger:
    return _event_logger
