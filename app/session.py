from __future__ import annotations

import collections
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional, Sequence

import webrtcvad

from app.ai.vlm_client import VLMClient
from app.audio.mic import MicrophoneStream
from app.audio.tts import SpeechSynthesizer
from app.audio.agc import AutomaticGainControl, AdaptiveVAD
from app.route import route_and_respond
from app.segment import SegmentRecorder, SegmentResult
from app.util.config import AppConfig
from app.util.diagnostics import SessionDiagnostics
from app.util.log import get_event_logger


class SessionState(Enum):
    IDLE = "Idle"
    RECORDING = "Recording"
    THINKING = "Thinking"
    SPEAKING = "Speaking"
    AWAIT_FOLLOWUP = "AwaitFollowup"


@dataclass
class SessionTurn:
    index: int
    user_text: str
    assistant_text: str
    stop_reason: str
    duration_ms: int
    audio_ms: int


@dataclass
class SessionCallbacks:
    session_started: Callable[[str], None]
    state_changed: Callable[[SessionState, int], None]
    transcript_ready: Callable[[int, SegmentResult], None]
    response_ready: Callable[[int, str, Dict[str, object]], None]
    session_finished: Callable[[str, str], None]
    error: Callable[[str], None]


class SessionManager:
    """Finite state manager orchestrating the multi-turn voice session.

    FIX: MULTI-TURN CONVERSATION SUPPORT - This class manages complete conversation
    sessions with proper lifecycle handling:
    - Maintains conversation history across multiple turns (self._history)
    - Continues listening after each assistant response (no need to re-wake)
    - Only terminates on explicit "bye glasses" or 15-second timeout (followup_timeout_ms)
    - Returns to wake-listening state when session ends
    - Properly handles voice reply flow with mic muting during TTS
    """

    def __init__(
        self,
        config: AppConfig,
        segment_recorder: SegmentRecorder,
        vlm_client: VLMClient,
        tts: SpeechSynthesizer,
        diagnostics: Optional[SessionDiagnostics] = None,
        followup_timeout_ms: int = 15_000,  # FIX: 15-second timeout for follow-up
    ) -> None:
        self.config = config
        self.segment_recorder = segment_recorder
        self.vlm_client = vlm_client
        self.tts = tts
        self.followup_timeout_ms = followup_timeout_ms
        self.diagnostics = diagnostics or SessionDiagnostics(config)

        self._cancel_event = threading.Event()
        self._state: SessionState = SessionState.IDLE
        self._session_id: Optional[str] = None
        self._session_start_monotonic: float = 0.0
        self._turns: List[SessionTurn] = []
        self._history: List[Dict[str, str]] = []
        self._history_tokens: int = 0
        self._running: bool = False

    # ------------------------------------------------------------------ public
    def current_state(self) -> SessionState:
        return self._state

    def is_running(self) -> bool:
        return self._running

    def cancel(self) -> None:
        """Request the active session to stop."""
        self._cancel_event.set()
        self.segment_recorder.request_stop()

    def run_session(
        self,
        callbacks: SessionCallbacks,
        pre_roll_buffer: Optional[Sequence[bytes]] = None,
    ) -> None:
        if self._running:
            raise RuntimeError("Session already running")

        self._running = True
        self._cancel_event.clear()
        self._turns.clear()
        # FIX: CONVERSATION HISTORY - Maintained across all turns in this session
        self._history.clear()
        self._history_tokens = 0

        turn_index = 0
        end_reason = "unknown"

        try:
            self._session_start_monotonic = time.monotonic()
            self._session_id = self.diagnostics.start_session()
            callbacks.session_started(self._session_id)

            next_pre_roll = list(pre_roll_buffer) if pre_roll_buffer else None
            next_timeout_ms: Optional[int] = None

            # FIX: MULTI-TURN CONVERSATION LOOP - Continues until timeout or explicit exit
            # This loop handles multiple question-answer exchanges in a single session
            while not self._cancel_event.is_set():
                segment_result = self._capture_turn(
                    turn_index,
                    callbacks,
                    pre_roll_buffer=next_pre_roll,
                    no_speech_timeout_ms=next_timeout_ms,
                )

                if segment_result is None:
                    end_reason = "cancel"
                    break

                user_text = segment_result.clean_transcript.strip()
                stop_reason = segment_result.stop_reason

                callbacks.transcript_ready(turn_index, segment_result)

                # FIX: LIFECYCLE MANAGEMENT - 15-second timeout termination
                if stop_reason == "timeout15" and not user_text:
                    end_reason = "timeout15"
                    break

                if stop_reason == "manual":
                    end_reason = "manual"
                    break

                # FIX: LIFECYCLE MANAGEMENT - Explicit "bye glasses" termination
                user_requested_exit = stop_reason == "bye" or "bye glasses" in user_text.lower()

                assistant_payload: Dict[str, object]
                assistant_text: str

                if not user_text:
                    assistant_text = "I didn't hear anything."
                    assistant_payload: Dict[str, object] = {"text": assistant_text, "reason": "empty"}
                    self.diagnostics.record_model_io(
                        self._build_model_input(user_text),
                        assistant_text,
                    )
                elif user_requested_exit:
                    assistant_text = "Goodbye."
                    assistant_payload = {"text": assistant_text, "reason": "bye"}
                    self.diagnostics.record_model_io(
                        self._build_model_input(user_text),
                        assistant_text,
                    )
                else:
                    assistant_text, assistant_payload = self._think_and_respond(
                        turn_index,
                        user_text,
                        segment_result,
                        callbacks,
                    )

                self._append_history(user_text, assistant_text)

                callbacks.response_ready(turn_index, assistant_text, assistant_payload)

                self._speak_response(turn_index, assistant_text, callbacks)

                self.diagnostics.finalize_turn(
                    stop_reason=stop_reason,
                    transcript=user_text,
                    response_text=assistant_text,
                )

                self._turns.append(
                    SessionTurn(
                        index=turn_index,
                        user_text=user_text,
                        assistant_text=assistant_text,
                        stop_reason=stop_reason,
                        duration_ms=segment_result.duration_ms,
                        audio_ms=segment_result.audio_ms,
                    )
                )

                # FIX: LIFECYCLE MANAGEMENT - Exit on user bye command
                if user_requested_exit:
                    end_reason = "bye"
                    break

                if stop_reason in {"cap", "manual"}:
                    end_reason = stop_reason
                    break

                # FIX: AWAIT FOLLOW-UP - After assistant speaks, wait for user's next input
                # This enables multi-turn conversation without requiring a new wake word
                from app.util.log import logger as audio_logger
                audio_logger.info(f"Session Turn {turn_index}: Completed. Awaiting follow-up speech...")
                
                next_timeout_ms = None
                follow_reason, next_pre_roll = self._await_followup(callbacks)
                
                if follow_reason != "speech":
                    # User didn't respond within timeout or error occurred
                    audio_logger.info(f"Session Turn {turn_index}: Follow-up ended with reason: {follow_reason}")
                    end_reason = follow_reason
                    break

                # FIX: CONTINUE CONVERSATION - User is speaking again, process next turn
                # Set timeout for subsequent turns (15 seconds of silence will end session)
                audio_logger.info(f"Session Turn {turn_index}: Follow-up speech detected! Starting turn {turn_index + 1}...")
                next_timeout_ms = self.followup_timeout_ms
                turn_index += 1

            if end_reason == "unknown":
                end_reason = "cancel" if self._cancel_event.is_set() else "idle"

        except Exception as exc:  # pragma: no cover - protected at runtime
            callbacks.error(str(exc))
            end_reason = "error"
        finally:
            duration_s = max(0.0, time.monotonic() - self._session_start_monotonic)
            self._transition_state(SessionState.IDLE, turn_index if self._turns else 0, callbacks)
            if self._session_id:
                self.diagnostics.end_session(
                    end_reason,
                    turns=self._turns,
                    duration_s=duration_s,
                )
                callbacks.session_finished(self._session_id, end_reason)
            self._session_id = None
            self._running = False
            self._cancel_event.clear()

    # ----------------------------------------------------------------- internals
    def _capture_turn(
        self,
        turn_index: int,
        callbacks: SessionCallbacks,
        *,
        pre_roll_buffer: Optional[Sequence[bytes]],
        no_speech_timeout_ms: Optional[int],
    ) -> Optional[SegmentResult]:
        if self._cancel_event.is_set():
            return None

        get_event_logger().set_turn(turn_index)
        self._transition_state(SessionState.RECORDING, turn_index, callbacks)
        self.diagnostics.start_turn(SessionState.RECORDING.value)
        self.diagnostics.timeline_event("Recording started")

        try:
            result = self.segment_recorder.record_segment(
                pre_roll_buffer=pre_roll_buffer,
                no_speech_timeout_ms=no_speech_timeout_ms,
            )
        except Exception as exc:
            callbacks.error(str(exc))
            return None

        self.diagnostics.record_audio(result.audio_bytes)
        self.diagnostics.record_video(result.video_path)
        self.diagnostics.record_stt(result.partial_events, result.final_event)
        self.diagnostics.timeline_event(f"Recording stopped ({result.stop_reason})")

        return result

    def _think_and_respond(
        self,
        turn_index: int,
        user_text: str,
        segment_result: SegmentResult,
        callbacks: SessionCallbacks,
    ) -> tuple[str, Dict[str, object]]:
        self._transition_state(SessionState.THINKING, turn_index, callbacks)
        self.diagnostics.timeline_event("Thinking")

        model_input = self._build_model_input(user_text)

        response = route_and_respond(
            config=self.config,
            vlm_client=self.vlm_client,
            transcript=user_text,
            segment_frames=segment_result.frames,
            history=self._history,
        )

        assistant_text = response.get("text", "").strip()
        if not assistant_text:
            assistant_text = "I'm not sure yet, but I'll find out."

        self.diagnostics.record_model_io(model_input, assistant_text, raw_output=response)

        return assistant_text, response

    def _speak_response(
        self,
        turn_index: int,
        assistant_text: str,
        callbacks: SessionCallbacks,
    ) -> None:
        """Speak assistant response with detailed timing logs.
        
        FIX: CRITICAL TTS DELAY DIAGNOSTIC - Add detailed logging to track
        TTS delays, especially on 2nd turn where 45-60s delays have been observed.
        """
        import time
        from app.util.log import logger as audio_logger
        
        self._transition_state(SessionState.SPEAKING, turn_index, callbacks)
        self.diagnostics.timeline_event("Speaking")
        
        # FIX: Set turn index on TTS for diagnostic logging
        self.tts.set_turn_index(turn_index)
        
        # FIX: Log timing before and after TTS to identify delays
        pre_tts_time = time.monotonic()
        audio_logger.info(f"Session Turn {turn_index}: Starting TTS (text length: {len(assistant_text)} chars)")
        
        try:
            self.tts.speak(assistant_text)
        except Exception as exc:  # pragma: no cover - safeguard
            callbacks.error(str(exc))
        finally:
            post_tts_time = time.monotonic()
            tts_duration_ms = int((post_tts_time - pre_tts_time) * 1000)
            audio_logger.info(f"Session Turn {turn_index}: TTS completed in {tts_duration_ms}ms")
            
            # FIX: Warn if TTS took abnormally long (>10 seconds for normal speech)
            if tts_duration_ms > 10000:
                audio_logger.warning(
                    f"Session Turn {turn_index}: ⚠️  CRITICAL TTS DELAY DETECTED: {tts_duration_ms}ms (>10s)! "
                    f"This indicates a TTS engine issue."
                )
            
            self._transition_state(SessionState.AWAIT_FOLLOWUP, turn_index, callbacks)
            self.diagnostics.timeline_event("Awaiting follow-up")

    def _await_followup(
        self,
        callbacks: SessionCallbacks,
    ) -> tuple[str, Optional[List[bytes]]]:
        """Wait for user to speak again after assistant's response.

        FIX: 15-SECOND FOLLOW-UP TIMEOUT - This method waits up to 15 seconds
        (self.followup_timeout_ms) for the user to continue the conversation.
        If speech is detected, returns pre-roll buffer and continues session.
        If timeout expires with no speech, returns "timeout15" to end session.
        This enables multi-turn conversations without requiring a new wake word.
        """
        if self._cancel_event.is_set():
            return "cancel", None

        # FIX: Use adaptive VAD with stricter detection for follow-ups
        adaptive_vad = AdaptiveVAD(sample_rate=self.config.sample_rate_hz)

        # FIX: Initialize AGC for follow-up detection (boost quiet speech)
        agc = AutomaticGainControl(
            target_rms=6000.0,
            min_gain=1.0,
            max_gain=20.0,
            attack_rate=0.9,
            release_rate=0.999
        )

        chunk_samples = self.config.chunk_samples
        sample_rate = self.config.sample_rate_hz
        frame_ms = max(1, int((chunk_samples / sample_rate) * 1000))
        ring = collections.deque(maxlen=max(1, int(self.config.pre_roll_ms / frame_ms)))

        # FIX: LONGER COOLDOWN - Avoid detecting assistant's TTS echo (1.5s instead of 0.35s)
        cooldown_end = time.monotonic() + 1.5

        # FIX: 15-second deadline for follow-up speech
        deadline = time.monotonic() + self.followup_timeout_ms / 1000

        # FIX: REQUIRE CONSECUTIVE SPEECH - Prevent false triggers from noise spikes
        consecutive_speech_frames = 0
        required_speech_frames = 10  # 10 frames * 20ms = 200ms of sustained speech

        try:
            with MicrophoneStream(
                rate=sample_rate,
                chunk_samples=chunk_samples,
                input_device_name=self.config.mic_device_name,
                resample_on_mismatch=self.config.resample_on_mismatch,
            ) as mic:
                while time.monotonic() < deadline:
                    if self._cancel_event.is_set():
                        return "cancel", None

                    raw_frame = mic.read(chunk_samples)
                    # FIX: Apply AGC to boost quiet speech
                    gained_frame = agc.process(raw_frame)
                    ring.append(gained_frame)

                    if time.monotonic() < cooldown_end:
                        consecutive_speech_frames = 0  # Reset during cooldown
                        continue

                    # FIX: Use adaptive VAD with gained audio
                    if adaptive_vad.is_speech(gained_frame):
                        consecutive_speech_frames += 1

                        # FIX: Only trigger after sustained speech (200ms minimum)
                        if consecutive_speech_frames >= required_speech_frames:
                            pre_frames: List[bytes] = list(ring)
                            tail_frames = max(1, int(200 / frame_ms))
                            for _ in range(tail_frames):
                                raw_tail = mic.read(chunk_samples)
                                gained_tail = agc.process(raw_tail)
                                pre_frames.append(gained_tail)
                            self.diagnostics.timeline_event("Follow-up speech detected")
                            return "speech", pre_frames
                    else:
                        # Reset counter when silence detected
                        consecutive_speech_frames = 0

                self.diagnostics.timeline_event("Follow-up timeout (15s)")
                return "timeout15", None
        except Exception as exc:
            callbacks.error(str(exc))
            self.diagnostics.timeline_event(f"Follow-up wait error: {exc}")
            return "error", None

    def _transition_state(
        self,
        state: SessionState,
        turn_index: int,
        callbacks: SessionCallbacks,
    ) -> None:
        self._state = state
        self.diagnostics.update_state(state.value)
        get_event_logger().set_state(state.value)
        callbacks.state_changed(state, turn_index)

    def _build_model_input(self, latest_user: str) -> Dict[str, object]:
        history_excerpt = self._history[-6:]
        return {
            "history": history_excerpt,
            "latest_user": latest_user,
        }

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return max(1, len(text.split()))

    def _append_history(self, user_text: str, assistant_text: str) -> None:
        if user_text:
            self._history.append({"role": "user", "text": user_text})
            self._history_tokens += self._estimate_tokens(user_text)
        if assistant_text:
            self._history.append({"role": "assistant", "text": assistant_text})
            self._history_tokens += self._estimate_tokens(assistant_text)
        self.diagnostics.update_history_tokens(self._history_tokens)
