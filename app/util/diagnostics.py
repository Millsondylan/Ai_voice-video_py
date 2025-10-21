from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.util.artifacts import (
    SessionArtifacts,
    TurnArtifacts,
    create_session_artifacts,
    generate_session_summary,
)
from app.util.config import AppConfig
from app.util.log import get_structured_logger


@dataclass
class TurnContext:
    index: int
    stop_reason: Optional[str] = None
    transcript: str = ""
    response_text: str = ""
    audio_bytes: Optional[bytes] = None
    video_path: Optional[Path] = None


class SessionDiagnostics:
    """Handles structured logging context, artifact persistence, and timelines."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._structured = get_structured_logger()
        self._session_id: Optional[str] = None
        self._artifacts: Optional[SessionArtifacts] = None
        self._current_turn_artifacts: Optional[TurnArtifacts] = None
        self._current_turn_context: Optional[TurnContext] = None
        self._turn_index: int = -1
        self._history_tokens: int = 0
        self._sink_registered = False
        self._active = False

    # ------------------------------------------------------------------ session
    def start_session(self, session_id: Optional[str] = None) -> str:
        if self._active:
            self.end_session("reset")

        if session_id is None:
            session_id = uuid.uuid4().hex[:12]

        self._session_id = session_id
        self._artifacts = create_session_artifacts(session_id, self._config.session_root)
        self._turn_index = -1
        self._history_tokens = 0
        self._current_turn_artifacts = None
        self._current_turn_context = None

        if self._sink_registered:
            self._structured.remove_sink(self._sink_callback)
            self._sink_registered = False

        self._structured.reset()
        self._structured.start_session(session_id)
        self._structured.update_state(session_state="Idle", turn_index=0, history_tokens=0)
        self._structured.register_sink(self._sink_callback)
        self._sink_registered = True
        self._active = True
        return session_id

    def end_session(
        self,
        reason: str,
        *,
        turns: Optional[List[Any]] = None,
        duration_s: Optional[float] = None,
    ) -> Optional[Path]:
        if not self._active:
            return None

        if self._current_turn_artifacts:
            self._current_turn_artifacts.save_timeline()

        session_dir: Optional[Path] = None
        if self._artifacts and turns is not None and duration_s is not None:
            summary = generate_session_summary(self._session_id or "", turns, duration_s, reason)
            self._artifacts.save_session_summary(summary)
            session_dir = self._artifacts.get_session_dir()

        if self._sink_registered:
            self._structured.remove_sink(self._sink_callback)
            self._sink_registered = False

        self._structured.reset()
        self._current_turn_artifacts = None
        self._current_turn_context = None
        self._session_id = None
        self._artifacts = None
        self._turn_index = -1
        self._history_tokens = 0
        self._active = False
        return session_dir

    def session_dir(self) -> Optional[Path]:
        return self._artifacts.get_session_dir() if self._artifacts else None

    # ------------------------------------------------------------------- turns
    def start_turn(self, state: str) -> TurnArtifacts:
        if not self._active:
            raise RuntimeError("Diagnostics session not started")

        self._turn_index += 1
        self._structured.update_state(
            session_state=state,
            turn_index=self._turn_index,
            history_tokens=self._history_tokens,
        )

        if not self._artifacts:
            raise RuntimeError("Session artifacts not initialized")

        self._current_turn_artifacts = self._artifacts.get_turn_artifacts(self._turn_index)
        self._current_turn_artifacts.add_timeline_event(f"Turn {self._turn_index} entered {state}")
        self._current_turn_context = TurnContext(index=self._turn_index)
        return self._current_turn_artifacts

    def update_state(self, state: str, reason: Optional[str] = None) -> None:
        if not self._active:
            return
        self._structured.update_state(session_state=state)
        if self._current_turn_artifacts:
            message = f"State → {state}"
            if reason:
                message += f" ({reason})"
            self._current_turn_artifacts.add_timeline_event(message)

    def update_history_tokens(self, token_count: int) -> None:
        self._history_tokens = token_count
        self._structured.update_state(history_tokens=token_count)
        get_event_logger().set_history_tokens(token_count)

    # ----------------------------------------------------------------- artifacts
    def record_audio(self, audio_bytes: bytes) -> None:
        if self._current_turn_artifacts and audio_bytes:
            self._current_turn_artifacts.save_raw_audio(audio_bytes, self._config.sample_rate_hz)
            if self._current_turn_context:
                self._current_turn_context.audio_bytes = audio_bytes

    def record_video(self, video_path: Optional[Path]) -> None:
        if self._current_turn_artifacts and video_path:
            self._current_turn_artifacts.save_video(video_path)
            if self._current_turn_context:
                self._current_turn_context.video_path = video_path

    def record_stt(self, partial_events: List[Dict[str, Any]], final_event: Optional[Dict[str, Any]]) -> None:
        if not self._current_turn_artifacts:
            return
        if partial_events:
            base_ts = partial_events[0]["ts_ms"]
            for event in partial_events:
                elapsed = max(0, event["ts_ms"] - base_ts)
                self._current_turn_artifacts.append_stt_partial(event["text"], elapsed)
        if final_event:
            self._current_turn_artifacts.save_stt_final(final_event.get("text", ""))

    def record_model_io(
        self,
        model_input: Dict[str, Any],
        model_output_text: str,
        raw_output: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self._current_turn_artifacts:
            return
        self._current_turn_artifacts.save_model_input(model_input)

        output_text = model_output_text or ""
        if raw_output is not None:
            try:
                raw_dump = json.dumps(raw_output, indent=2, ensure_ascii=True)
            except TypeError:
                raw_dump = str(raw_output)
            output_text = f"{output_text}\n\n--- raw response ---\n{raw_dump}" if output_text else raw_dump
        self._current_turn_artifacts.save_model_output(output_text)

    def timeline_event(self, message: str) -> None:
        if self._current_turn_artifacts:
            self._current_turn_artifacts.add_timeline_event(message)

    def finalize_turn(
        self,
        *,
        stop_reason: Optional[str] = None,
        transcript: str = "",
        response_text: str = "",
    ) -> None:
        if not self._current_turn_artifacts:
            return

        if stop_reason:
            self._current_turn_artifacts.add_timeline_event(f"Stop reason: {stop_reason}")
        if transcript:
            self._current_turn_artifacts.add_timeline_event(f"Transcript: {transcript}")
        if response_text:
            self._current_turn_artifacts.add_timeline_event(f"Response: {response_text}")
        self._current_turn_artifacts.save_timeline()

        if self._current_turn_context:
            self._current_turn_context.stop_reason = stop_reason
            self._current_turn_context.transcript = transcript
            self._current_turn_context.response_text = response_text

    # ----------------------------------------------------------------- internals
    def _sink_callback(self, record: Dict[str, Any]) -> None:
        if self._artifacts:
            self._artifacts.append_log_event(record)
