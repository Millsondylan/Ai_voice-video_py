"""Automatic Gain Control (AGC) for audio normalization.

This ensures consistent audio levels regardless of microphone volume settings.
"""
from __future__ import annotations

import numpy as np
from typing import Optional


class AutomaticGainControl:
    """Adaptive audio level normalization with automatic gain adjustment.

    This class automatically adjusts audio gain to maintain consistent levels
    regardless of microphone volume settings, ensuring wake word detection
    and STT work reliably without manual volume adjustment.
    """

    def __init__(
        self,
        target_rms: float = 3000.0,  # Target RMS level for normalized audio
        min_gain: float = 1.0,       # Minimum gain multiplier
        max_gain: float = 10.0,      # Maximum gain multiplier (10x boost)
        attack_rate: float = 0.9,    # How fast gain increases (0-1)
        release_rate: float = 0.999, # How fast gain decreases (0-1)
    ):
        self.target_rms = target_rms
        self.min_gain = min_gain
        self.max_gain = max_gain
        self.attack_rate = attack_rate
        self.release_rate = release_rate

        self.current_gain = 1.0
        self.running_rms = 0.0
        self.frame_count = 0

    def process(self, audio_frame: bytes) -> bytes:
        """Apply automatic gain control to audio frame.

        Args:
            audio_frame: Raw PCM audio bytes (int16)

        Returns:
            Gain-adjusted audio bytes at consistent level
        """
        # Convert to numpy array
        audio_data = np.frombuffer(audio_frame, dtype=np.int16).astype(np.float32)

        # Calculate RMS (Root Mean Square) level
        rms = np.sqrt(np.mean(audio_data**2))

        # Update running average RMS (smoothed)
        if self.frame_count == 0:
            self.running_rms = rms
        else:
            # Exponential moving average
            alpha = 0.1  # Smoothing factor
            self.running_rms = alpha * rms + (1 - alpha) * self.running_rms

        self.frame_count += 1

        # Skip gain adjustment for very quiet frames (likely silence)
        if self.running_rms < 10.0:
            return audio_frame

        # Calculate desired gain
        if self.running_rms > 0:
            desired_gain = self.target_rms / self.running_rms
        else:
            desired_gain = self.min_gain

        # Clamp gain to min/max limits
        desired_gain = max(self.min_gain, min(self.max_gain, desired_gain))

        # Smooth gain changes (attack/release)
        if desired_gain > self.current_gain:
            # Attack: gain increasing (quieter signal needs boost)
            self.current_gain = self.attack_rate * desired_gain + (1 - self.attack_rate) * self.current_gain
        else:
            # Release: gain decreasing (louder signal needs reduction)
            self.current_gain = self.release_rate * desired_gain + (1 - self.release_rate) * self.current_gain

        # Apply gain
        gained_audio = audio_data * self.current_gain

        # Clip to prevent overflow
        gained_audio = np.clip(gained_audio, -32768, 32767)

        # Convert back to int16 bytes
        return gained_audio.astype(np.int16).tobytes()

    def get_stats(self) -> dict:
        """Get current AGC statistics for debugging."""
        return {
            "current_gain": round(self.current_gain, 2),
            "current_gain_db": round(20 * np.log10(self.current_gain), 1) if self.current_gain > 0 else 0,
            "running_rms": round(self.running_rms, 1),
            "target_rms": self.target_rms,
            "frame_count": self.frame_count,
        }

    def reset(self):
        """Reset AGC state."""
        self.current_gain = 1.0
        self.running_rms = 0.0
        self.frame_count = 0


class AdaptiveVAD:
    """Adaptive Voice Activity Detection with automatic threshold adjustment.

    Automatically selects the best VAD level based on measured background noise,
    ensuring reliable speech detection across different environments.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        min_level: int = 0,
        max_level: int = 3,
        initial_level: Optional[int] = None,
    ):
        self.sample_rate = sample_rate
        self.background_rms = 0.0
        self.speech_rms = 0.0
        self.calibration_frames = 0
        self.max_calibration_frames = 50  # ~1 second at 20ms chunks
        self.min_level = max(0, min(min_level, 3))
        self.max_level = max(self.min_level, min(max_level, 3))

        # Import webrtcvad here
        import webrtcvad

        if initial_level is None:
            initial_level = min(max(0, 2), self.max_level)
        else:
            initial_level = max(self.min_level, min(initial_level, self.max_level))

        self.vad_level = initial_level
        self.vad = webrtcvad.Vad(self.vad_level)

    def calibrate(self, audio_frame: bytes) -> None:
        """Calibrate background noise levels during initialization.

        Call this for the first ~1 second of audio to measure background noise.
        """
        if self.calibration_frames >= self.max_calibration_frames:
            return

        audio_data = np.frombuffer(audio_frame, dtype=np.int16).astype(np.float32)
        rms = np.sqrt(np.mean(audio_data**2))

        if self.calibration_frames == 0:
            self.background_rms = rms
        else:
            # Running average
            alpha = 0.2
            self.background_rms = alpha * rms + (1 - alpha) * self.background_rms

        self.calibration_frames += 1

        # After calibration, adjust VAD level based on background noise
        if self.calibration_frames == self.max_calibration_frames:
            self._adjust_vad_level()

    def _adjust_vad_level(self):
        """Automatically select optimal VAD level based on background noise.

        FIX: Thresholds adjusted for AGC-boosted audio (target_rms≈6000).
        This keeps VAD sensitive to quiet wake words even when AGC raises background noise.
        """
        import webrtcvad

        # Interpret thresholds relative to AGC target (~6000 RMS)
        if self.background_rms < 2500:
            level = 0
        elif self.background_rms < 4500:
            level = 1
        elif self.background_rms < 7000:
            level = 2
        else:
            level = 3

        level = max(self.min_level, min(level, self.max_level))
        self.vad_level = level

        self.vad = webrtcvad.Vad(self.vad_level)

        from app.util.log import logger
        logger.info(
            f"[AGC] Auto-selected VAD level {self.vad_level} "
            f"(background RMS: {self.background_rms:.1f})"
        )

    def is_speech(self, audio_frame: bytes) -> bool:
        """Detect speech using adaptive VAD."""
        # Continue calibration if not done
        if self.calibration_frames < self.max_calibration_frames:
            self.calibrate(audio_frame)
            # During calibration, assume no speech
            return False

        return self.vad.is_speech(audio_frame, self.sample_rate)

    def get_vad_level(self) -> int:
        """Get current VAD aggressiveness level."""
        return self.vad_level
