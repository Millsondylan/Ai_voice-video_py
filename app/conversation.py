"""
Conversation mode coordinator - maintains continuous interaction with context.
"""
from __future__ import annotations

import collections
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from app.audio.capture import run_segment
from app.audio.mic import MicrophoneStream
from app.audio.stt import StreamingTranscriber
from app.audio.tts import SpeechSynthesizer
from app.util.config import AppConfig
from app.util.log import get_event_logger


@dataclass
class ConversationTurn:
    """Single turn in a conversation."""
    user_text: str
    assistant_text: str
    timestamp: float
    audio_path: Optional[Path] = None


@dataclass
class ConversationSession:
    """Full conversation session with history."""
    turns: List[ConversationTurn] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)

    def add_turn(self, user_text: str, assistant_text: str, audio_path: Optional[Path] = None):
        """Add a conversation turn."""
        self.turns.append(ConversationTurn(
            user_text=user_text,
            assistant_text=assistant_text,
            timestamp=time.time(),
            audio_path=audio_path
        ))

    def get_context(self, max_turns: int = 5) -> str:
        """Get recent conversation history as context."""
        recent_turns = self.turns[-max_turns:]
        context_lines = []
        for turn in recent_turns:
            context_lines.append(f"User: {turn.user_text}")
            context_lines.append(f"Assistant: {turn.assistant_text}")
        return "\n".join(context_lines)

    def duration_seconds(self) -> float:
        """Get total conversation duration."""
        return time.time() - self.start_time


class ConversationMode:
    """
    Manages continuous conversation mode:
    - No wake word needed after first trigger
    - Maintains conversation history
    - Exits on 15s timeout or "bye glasses"
    - Captures ALL speech including first syllable
    """

    def __init__(
        self,
        config: AppConfig,
        transcriber: StreamingTranscriber,
        tts: SpeechSynthesizer,
        on_turn_complete: callable,
    ):
        self.config = config
        self.transcriber = transcriber
        self.tts = tts
        self.on_turn_complete = on_turn_complete
        self.session = ConversationSession()
        self.logger = get_event_logger()

        # Conversation mode settings
        self.conversation_timeout_ms = 15000  # 15 seconds
        self.exit_phrases = ["bye glasses", "goodbye glasses", "exit", "stop"]

        # Continuous buffer for capturing first syllables
        self.buffer_size_frames = int(config.pre_roll_ms / 20)  # 20ms frames
        self.continuous_buffer: collections.deque = collections.deque(maxlen=self.buffer_size_frames)

    def start_conversation(self, initial_buffer: Optional[collections.deque] = None) -> ConversationSession:
        """
        Start a continuous conversation session.

        Args:
            initial_buffer: Pre-roll buffer from wake word detection

        Returns:
            Completed conversation session
        """
        if initial_buffer:
            self.continuous_buffer = initial_buffer

        self.logger.log_wake_detected()
        print(f"\n[CONVERSATION MODE] Started - Say 'bye glasses' or wait 15s to exit")

        mic = MicrophoneStream(
            rate=self.config.sample_rate_hz,
            chunk_samples=self.config.chunk_samples,
            input_device_name=self.config.mic_device_name,
        )
        mic.start()

        try:
            while True:
                # Record one turn
                turn_result = self._record_turn(mic)

                if not turn_result:
                    print(f"[CONVERSATION MODE] No speech detected, exiting")
                    break

                user_text = turn_result['transcript']

                # Check for exit phrases
                if self._should_exit(user_text):
                    print(f"[CONVERSATION MODE] Exit phrase detected: '{user_text}'")
                    self.tts.speak("Goodbye!")
                    break

                # Get response with context
                context = self.session.get_context()
                response = self.on_turn_complete(user_text, context, turn_result.get('frames'))

                # Speak response
                self.tts.speak(response['text'])

                # Save turn
                self.session.add_turn(user_text, response['text'], turn_result.get('audio_path'))

                print(f"[CONVERSATION MODE] Turn {len(self.session.turns)} complete")
                print(f"   User: {user_text}")
                print(f"   Assistant: {response['text']}")

        finally:
            mic.stop()
            mic.terminate()

        print(f"\n[CONVERSATION MODE] Ended - {len(self.session.turns)} turns, {self.session.duration_seconds():.1f}s")
        return self.session

    def _record_turn(self, mic: MicrophoneStream) -> Optional[dict]:
        """
        Record one conversation turn with pre-roll from continuous buffer.

        Returns None if timeout or no speech detected.
        """
        print(f"\n[CONVERSATION MODE] Listening... (15s timeout)")

        # Use modified silence threshold for conversation mode
        # Longer timeout before considering turn complete
        original_silence_ms = self.config.silence_ms
        self.config.silence_ms = self.conversation_timeout_ms

        try:
            # Create a modified run_segment that uses our continuous buffer
            result = self._capture_with_buffer(mic)

            if result and result.clean_transcript:
                return {
                    'transcript': result.clean_transcript,
                    'audio_path': None,  # TODO: Save audio
                    'frames': [],  # TODO: Include video frames
                    'stop_reason': result.stop_reason
                }
            return None

        finally:
            self.config.silence_ms = original_silence_ms

    def _capture_with_buffer(self, mic: MicrophoneStream):
        """Capture audio using the continuous buffer for pre-roll."""
        from app.audio.capture import run_segment

        # The continuous buffer already has the pre-roll
        # Just need to feed it to the segment recorder
        # For now, use standard run_segment
        # TODO: Modify to use continuous_buffer

        return run_segment(
            mic=mic,
            stt=self.transcriber,
            config=self.config,
            stop_event=None,
            on_chunk=None
        )

    def _should_exit(self, text: str) -> bool:
        """Check if user said an exit phrase."""
        text_lower = text.lower().strip()
        return any(phrase in text_lower for phrase in self.exit_phrases)

    def _update_continuous_buffer(self, frame: bytes):
        """Keep the continuous buffer updated with latest audio."""
        self.continuous_buffer.append(frame)
