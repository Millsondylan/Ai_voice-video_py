from __future__ import annotations

import collections
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, List, Optional

import webrtcvad

from app.route import route_and_respond
from app.segment import SegmentRecorder, SegmentResult
from app.session_artifacts import SessionArtifactWriter
from app.util.config import AppConfig
from app.util.log import get_event_logger, get_structured_logger, logger as audio_logger


@dataclass
class SessionCallbacks:
    on_state: Callable[[str, int], None]
    on_user_transcript: Callable[[int, str], None]
    on_assistant_response: Callable[[int, str, Dict[str, Any]], None]
    on_session_complete: Callable[[str], None]
    on_error: Callable[[str], None]
    on_session_started: Callable[[str], None] = lambda session_id: None


def _token_count(text: str) -> int:
    return len(text.strip().split()) if text else 0


class SessionController:
    """Drive the multi-turn voice session finite-state-machine."""

    def __init__(
        self,
        config: AppConfig,
        segment_recorder: SegmentRecorder,
        vlm_client,
        tts,
    ) -> None:
        self.config = config
        self.segment_recorder = segment_recorder
        self.vlm_client = vlm_client
        self.tts = tts
        self.followup_timeout_ms = 15_000
        self._cancel_flag = False
        self._callbacks: Optional[SessionCallbacks] = None

    # ------------------------------------------------------------------ public api
    def cancel(self) -> None:
        self._cancel_flag = True
        self.segment_recorder.request_stop()

    def run_session(
        self,
        callbacks: SessionCallbacks,
        initial_pre_roll: Optional[Deque[bytes]] = None,
    ) -> None:
        self._callbacks = callbacks
        self._cancel_flag = False

        session_id = uuid.uuid4().hex
        callbacks.on_session_started(session_id)

        self.config.session_root.mkdir(parents=True, exist_ok=True)

        event_logger = get_event_logger()
        structured_logger = get_structured_logger()
        previous_log_path = structured_logger.output_path
        structured_logger.set_output_path(self.config.session_root / session_id / "events.jsonl")
        event_logger.start_session(session_id)
        event_logger.set_history_tokens(0)
        self._set_state("Wake", 0)

        artifact_writer = SessionArtifactWriter(session_id, self.config.session_root)

        conversation_history: List[Dict[str, str]] = []
        history_tokens = 0
        turn_index = 0
        if initial_pre_roll:
            initial_max = getattr(initial_pre_roll, "maxlen", None) or len(initial_pre_roll)
            pre_roll_buffer: Optional[Deque[bytes]] = collections.deque(initial_pre_roll, maxlen=initial_max)
        else:
            pre_roll_buffer = None

        try:
            while not self._cancel_flag:
                event_logger.set_turn(turn_index)
                self._set_state("Recording", turn_index)

                segment_result = self._capture_turn(pre_roll_buffer)
                if segment_result is None:
                    break

                user_text = segment_result.clean_transcript.strip()
                callbacks.on_user_transcript(turn_index, user_text)

                if not user_text:
                    break

                conversation_history.append({"role": "user", "text": user_text})
                history_tokens += _token_count(user_text)
                event_logger.set_history_tokens(history_tokens)

                goodbye_requested = segment_result.stop_reason == "bye" or "bye glasses" in user_text.lower()

                self._set_state("Thinking", turn_index)
                response_data: Optional[Dict[str, Any]]

                if goodbye_requested:
                    assistant_text = "Goodbye!"
                    response_data = {"text": assistant_text, "reason": "bye"}
                else:
                    context_history = conversation_history[:-1]
                    if len(context_history) > 10:
                        context_history = context_history[-10:]
                    response_data = route_and_respond(
                        config=self.config,
                        vlm_client=self.vlm_client,
                        transcript=user_text,
                        segment_frames=segment_result.frames,
                        history=context_history,
                    )
                    assistant_text = response_data.get("text", "").strip() or "I'm not sure yet, but I'll learn."

                conversation_history.append({"role": "assistant", "text": assistant_text})
                history_tokens += _token_count(assistant_text)
                event_logger.set_history_tokens(history_tokens)

                self._set_state("Speaking", turn_index)
                self._speak_text(assistant_text)
                callbacks.on_assistant_response(turn_index, assistant_text, response_data or {"text": assistant_text})

                self._set_state("AwaitFollowup", turn_index)

                structured_timeline = [
                    entry
                    for entry in structured_logger.timeline()
                    if entry.get("turn_index") == turn_index
                ]
                timeline_lines = [
                    f"{entry['rel_ms']:>7}ms | state={entry.get('session_state')} | {entry['event']}"
                    for entry in structured_timeline
                ]

                model_input = {
                    "history": conversation_history[-12:],
                    "latest_user": user_text,
                }

                artifact_writer.persist_turn(
                    turn_index=turn_index,
                    audio_path=segment_result.audio_path,
                    video_path=segment_result.video_path,
                    partial_events=segment_result.partial_events,
                    final_event=segment_result.final_event,
                    final_text=segment_result.clean_transcript,
                    model_input=model_input,
                    model_output_text=assistant_text,
                    model_output_raw=response_data,
                    timeline_lines=timeline_lines,
                    timeline_events=structured_timeline,
                    stop_reason=segment_result.stop_reason,
                    duration_ms=segment_result.duration_ms,
                    audio_ms=segment_result.audio_ms,
                    extra_meta={"goodbye": goodbye_requested},
                )

                if goodbye_requested or segment_result.stop_reason in {"manual", "cap", "timeout15"}:
                    break

                follow_reason, pre_roll_buffer = self._await_followup()
                if follow_reason != "speech":
                    break

                turn_index += 1

        except Exception as exc:  # pragma: no cover
            callbacks.on_error(str(exc))
        finally:
            self._set_state("Idle", turn_index)
            callbacks.on_session_complete(session_id)
            structured_logger.reset()
            structured_logger.set_output_path(previous_log_path)
            event_logger.reset()
            self._callbacks = None

    # ------------------------------------------------------------------ helpers
    def _set_state(self, state: str, turn_index: int) -> None:
        event_logger = get_event_logger()
        event_logger.set_state(state)
        if self._callbacks:
            self._callbacks.on_state(state, turn_index)

    def _capture_turn(self, pre_roll_buffer: Optional[Deque[bytes]]) -> Optional[SegmentResult]:
        if self._cancel_flag:
            return None
        try:
            return self.segment_recorder.record_segment(pre_roll_buffer=pre_roll_buffer)
        except Exception as exc:
            if self._callbacks:
                self._callbacks.on_error(str(exc))
            return None

    def _speak_text(self, text: str) -> None:
        try:
            self.tts.speak(text)
            time.sleep(0.15)
        except Exception as exc:  # pragma: no cover
            audio_logger.error("TTS failed: %s", exc)

    def _await_followup(self) -> tuple[str, Optional[Deque[bytes]]]:
        if self._cancel_flag:
            return "cancel", None

        vad = webrtcvad.Vad(max(0, min(3, self.config.vad_aggressiveness)))
        chunk_samples = self.config.chunk_samples
        sample_rate = self.config.sample_rate_hz
        frame_ms = max(1, int((chunk_samples / sample_rate) * 1000))
        ring_frames = max(1, int(self.config.pre_roll_ms / frame_ms))
        ring: Deque[bytes] = collections.deque(maxlen=ring_frames)
        cooldown_end = time.monotonic() + 0.3
        deadline = time.monotonic() + self.followup_timeout_ms / 1000

        try:
            from app.audio.mic import MicrophoneStream

            with MicrophoneStream(
                rate=sample_rate,
                chunk_samples=chunk_samples,
                input_device_name=self.config.mic_device_name,
            ) as mic:
                while time.monotonic() < deadline:
                    if self._cancel_flag:
                        return "cancel", None
                    frame = mic.read(chunk_samples)
                    ring.append(frame)
                    if time.monotonic() < cooldown_end:
                        continue
                    if vad.is_speech(frame, sample_rate):
                        tail_frames = max(1, int(200 / frame_ms))
                        for _ in range(tail_frames):
                            ring.append(mic.read(chunk_samples))
                        return "speech", ring
                return "timeout15", None
        except Exception as exc:
            audio_logger.error("Follow-up wait failed: %s", exc)
            return "error", None
