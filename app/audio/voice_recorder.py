"""
Complete speech capture with WebRTC VAD and ring buffer pattern.

This module implements the EXACT pattern from the requirements to ensure
complete speech capture without missing syllables or cutting off early.
"""
from __future__ import annotations

import collections
import logging
from typing import Optional

import webrtcvad

logger = logging.getLogger(__name__)


class VoiceRecorder:
    """
    WebRTC VAD-based voice recorder with ring buffer for complete speech capture.

    Implements the pattern from requirements to fix Issue #1 (Speech Not Fully Captured):
    - Ring buffer for pre-roll capture (frames BEFORE speech detection)
    - 90% threshold for triggering (robust against noise)
    - Adaptive padding for Bluetooth devices (500ms vs 300ms)
    - Correct frame size calculation
    - Single VAD instance (not recreated per frame)
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        padding_duration_ms: int = 300,
        aggressiveness: int = 3,
        is_bluetooth: bool = False,
    ):
        """
        Initialize voice recorder with WebRTC VAD.

        Args:
            sample_rate: Audio sample rate (must be 8000, 16000, 32000, or 48000)
            frame_duration_ms: Frame duration (must be 10, 20, or 30)
            padding_duration_ms: Silence padding duration (300ms baseline, 500ms for Bluetooth)
            aggressiveness: VAD aggressiveness 0-3 (3 = most aggressive)
            is_bluetooth: True if using Bluetooth audio device (increases padding)
        """
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms

        # FIX: Correct frame size calculation as per requirements
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)
        self.frame_bytes = self.frame_size * 2  # 16-bit = 2 bytes per sample

        # FIX: Adaptive buffering - detect Bluetooth and increase padding
        if is_bluetooth and padding_duration_ms < 500:
            padding_duration_ms = 500
            logger.info("Bluetooth device detected, using 500ms padding")

        # FIX: Single VAD instance - NEVER recreate per frame
        self.vad = webrtcvad.Vad(aggressiveness)

        # FIX: Ring buffer for pre-roll capture
        self.padding_frames = int(padding_duration_ms / frame_duration_ms)
        self.ring_buffer = collections.deque(maxlen=self.padding_frames)

        # State tracking
        self.triggered = False
        self.voiced_frames = []

        # Thresholds for robust detection
        self.trigger_threshold = 0.9  # 90% of ring buffer must contain speech
        self.detrigger_threshold = 0.9  # 90% must be silence to end

        logger.info(
            f"VoiceRecorder initialized: {sample_rate}Hz, {frame_duration_ms}ms frames, "
            f"{padding_duration_ms}ms padding ({self.padding_frames} frames), "
            f"aggressiveness={aggressiveness}"
        )

    def process_frame(self, frame_data: bytes) -> Optional[bytes]:
        """
        Process a single audio frame and return complete utterance when speech ends.

        Args:
            frame_data: Audio frame (must be exact frame_bytes length)

        Returns:
            Complete utterance as bytes when speech ends, None otherwise

        Raises:
            ValueError: If frame_data length doesn't match expected frame_bytes
        """
        # Validate frame size
        if len(frame_data) != self.frame_bytes:
            raise ValueError(
                f"Frame data length {len(frame_data)} doesn't match expected "
                f"{self.frame_bytes} bytes for {self.frame_duration_ms}ms at {self.sample_rate}Hz"
            )

        # Run VAD on frame
        is_speech = self.vad.is_speech(frame_data, self.sample_rate)

        if not self.triggered:
            # Not yet triggered - collecting in ring buffer
            self.ring_buffer.append((frame_data, is_speech))

            # Count how many frames in ring buffer contain speech
            num_voiced = sum(1 for f, s in self.ring_buffer if s)

            # FIX: Trigger when 90% of ring buffer frames contain speech
            if num_voiced > self.trigger_threshold * self.ring_buffer.maxlen:
                self.triggered = True
                # Copy all frames from ring buffer (includes pre-roll)
                self.voiced_frames = [f for f, s in self.ring_buffer]
                self.ring_buffer.clear()
                logger.debug(
                    f"Speech triggered! Captured {len(self.voiced_frames)} pre-roll frames"
                )

        else:
            # Already triggered - recording speech
            self.voiced_frames.append(frame_data)
            self.ring_buffer.append((frame_data, is_speech))

            # Count how many frames in ring buffer are silence
            num_unvoiced = sum(1 for f, s in self.ring_buffer if not s)

            # FIX: Detrigger when 90% of ring buffer frames are silence
            if num_unvoiced > self.detrigger_threshold * self.ring_buffer.maxlen:
                self.triggered = False
                # Return complete utterance
                complete_utterance = b''.join(self.voiced_frames)
                total_frames = len(self.voiced_frames)
                duration_ms = total_frames * self.frame_duration_ms

                logger.info(
                    f"Speech completed! Captured {total_frames} frames ({duration_ms}ms)"
                )

                # Reset state for next utterance
                self.voiced_frames = []
                self.ring_buffer.clear()

                return complete_utterance

        return None

    def reset(self) -> None:
        """Reset the recorder state."""
        self.triggered = False
        self.voiced_frames = []
        self.ring_buffer.clear()
        logger.debug("VoiceRecorder reset")

    def is_recording(self) -> bool:
        """Check if currently recording speech."""
        return self.triggered

    def get_buffer_status(self) -> dict:
        """Get current buffer status for debugging."""
        num_voiced = sum(1 for f, s in self.ring_buffer if s)
        return {
            'triggered': self.triggered,
            'ring_buffer_size': len(self.ring_buffer),
            'ring_buffer_max': self.ring_buffer.maxlen,
            'voiced_in_buffer': num_voiced,
            'voiced_frames': len(self.voiced_frames),
        }
