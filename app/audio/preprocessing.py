"""Audio preprocessing utilities for improving STT accuracy."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Optional, Tuple

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import noisereduce as nr
    NOISEREDUCE_AVAILABLE = True
except ImportError:
    NOISEREDUCE_AVAILABLE = False

try:
    from scipy import signal
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


def apply_noise_reduction(
    audio: np.ndarray,
    sample_rate: int,
    stationary: bool = True,
    prop_decrease: float = 0.75,
) -> np.ndarray:
    """Apply noise reduction to audio data.

    Args:
        audio: Audio data as numpy array
        sample_rate: Sample rate in Hz
        stationary: Whether noise is stationary (default: True)
        prop_decrease: Proportion of noise to reduce (0-1, default: 0.75)

    Returns:
        Noise-reduced audio as numpy array

    Raises:
        ImportError: If noisereduce library not installed
    """
    if not NOISEREDUCE_AVAILABLE:
        raise ImportError(
            "noisereduce library required. Install with: pip install noisereduce"
        )

    return nr.reduce_noise(
        y=audio,
        sr=sample_rate,
        stationary=stationary,
        prop_decrease=prop_decrease,
    )


def apply_speech_filter(
    audio: np.ndarray,
    sample_rate: int,
    highpass_freq: int = 80,
    lowpass_freq: int = 8000,
) -> np.ndarray:
    """Apply bandpass filter to keep only speech frequencies.

    Args:
        audio: Audio data as numpy array
        sample_rate: Sample rate in Hz
        highpass_freq: High-pass cutoff frequency (default: 80 Hz)
        lowpass_freq: Low-pass cutoff frequency (default: 8000 Hz)

    Returns:
        Filtered audio as numpy array

    Raises:
        ImportError: If scipy library not installed
    """
    if not SCIPY_AVAILABLE:
        raise ImportError(
            "scipy library required. Install with: pip install scipy"
        )

    # High-pass filter to remove rumble
    sos = signal.butter(6, highpass_freq, "hp", fs=sample_rate, output="sos")
    audio = signal.sosfilt(sos, audio)

    # Low-pass filter to remove high-frequency noise
    sos = signal.butter(6, lowpass_freq, "lp", fs=sample_rate, output="sos")
    audio = signal.sosfilt(sos, audio)

    return audio


def apply_noise_gate(
    audio: np.ndarray,
    threshold: int = 500,
) -> np.ndarray:
    """Apply simple noise gate to remove very quiet sounds.

    Args:
        audio: Audio data as int16 numpy array
        threshold: Amplitude threshold (default: 500 for 16-bit audio)

    Returns:
        Gated audio as numpy array
    """
    if not NUMPY_AVAILABLE:
        raise ImportError("numpy required")

    return np.where(np.abs(audio) > threshold, audio, 0)


def normalize_audio(audio: np.ndarray) -> np.ndarray:
    """Normalize audio to full dynamic range.

    Args:
        audio: Audio data as numpy array

    Returns:
        Normalized audio
    """
    if not NUMPY_AVAILABLE:
        raise ImportError("numpy required")

    max_val = np.max(np.abs(audio))
    if max_val > 0:
        return audio * (0.95 / max_val)
    return audio


def preprocess_audio_file(
    input_path: str | Path,
    output_path: str | Path,
    apply_nr: bool = True,
    apply_filter: bool = True,
    apply_gate: bool = False,
    normalize: bool = True,
) -> None:
    """Preprocess audio file for optimal STT accuracy.

    Args:
        input_path: Path to input WAV file
        output_path: Path to save processed WAV file
        apply_nr: Apply noise reduction (default: True)
        apply_filter: Apply speech bandpass filter (default: True)
        apply_gate: Apply noise gate (default: False)
        normalize: Normalize audio levels (default: True)
    """
    if not NUMPY_AVAILABLE:
        raise ImportError("numpy required for audio preprocessing")

    # Read input file
    with wave.open(str(input_path), "rb") as wf:
        sample_rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()

    # Convert to numpy
    if sample_width == 2:
        audio = np.frombuffer(frames, dtype=np.int16)
    else:
        raise ValueError(f"Unsupported sample width: {sample_width}")

    # Handle stereo
    if channels == 2:
        audio = audio.reshape(-1, 2).mean(axis=1).astype(np.int16)
    elif channels != 1:
        raise ValueError(f"Unsupported channel count: {channels}")

    # Convert to float for processing
    audio_float = audio.astype(np.float32)

    # Apply preprocessing
    if apply_filter and SCIPY_AVAILABLE:
        audio_float = apply_speech_filter(audio_float, sample_rate)

    if apply_nr and NOISEREDUCE_AVAILABLE:
        audio_float = apply_noise_reduction(audio_float, sample_rate)

    if normalize:
        audio_float = normalize_audio(audio_float)

    # Convert back to int16
    audio_processed = audio_float.astype(np.int16)

    if apply_gate:
        audio_processed = apply_noise_gate(audio_processed)

    # Write output file
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)  # Always output mono
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(audio_processed.tobytes())


class AudioPreprocessor:
    """Real-time audio preprocessor for streaming applications."""

    def __init__(
        self,
        sample_rate: int = 16000,
        enable_gate: bool = True,
        gate_threshold: int = 500,
    ):
        """Initialize audio preprocessor.

        Args:
            sample_rate: Audio sample rate
            enable_gate: Enable noise gate
            gate_threshold: Noise gate threshold
        """
        if not NUMPY_AVAILABLE:
            raise ImportError("numpy required")

        self.sample_rate = sample_rate
        self.enable_gate = enable_gate
        self.gate_threshold = gate_threshold

    def process_chunk(self, audio_bytes: bytes) -> bytes:
        """Process a single audio chunk.

        Args:
            audio_bytes: Raw audio bytes (16-bit PCM)

        Returns:
            Processed audio bytes
        """
        # Convert to numpy
        audio = np.frombuffer(audio_bytes, dtype=np.int16)

        # Apply noise gate if enabled
        if self.enable_gate:
            audio = apply_noise_gate(audio, self.gate_threshold)

        # Convert back to bytes
        return audio.astype(np.int16).tobytes()


def get_preprocessing_recommendations(audio_path: str | Path) -> str:
    """Analyze audio and recommend preprocessing steps.

    Args:
        audio_path: Path to audio file

    Returns:
        Recommendations as formatted string
    """
    # Import diagnostics
    from app.audio.audio_diagnostics import analyze_audio_quality

    metrics = analyze_audio_quality(audio_path)

    if "error" in metrics:
        return f"❌ Cannot analyze: {metrics['error']}"

    recommendations = ["\n🔧 Preprocessing Recommendations:"]
    recommendations.append("=" * 60)

    should_preprocess = False

    if metrics.get("low_snr"):
        recommendations.append("\n✓ Apply Noise Reduction")
        recommendations.append("  Reason: Low SNR detected")
        should_preprocess = True

    if metrics.get("clipping_detected"):
        recommendations.append("\n✓ Normalize Audio")
        recommendations.append("  Reason: Clipping detected")
        should_preprocess = True

    if metrics.get("low_volume"):
        recommendations.append("\n✓ Normalize Audio")
        recommendations.append("  Reason: Low volume detected")
        should_preprocess = True

    if metrics.get("dc_offset_detected"):
        recommendations.append("\n✓ Apply High-Pass Filter")
        recommendations.append("  Reason: DC offset detected")
        should_preprocess = True

    if not should_preprocess:
        recommendations.append("\n✅ No preprocessing needed - audio quality is good!")
    else:
        recommendations.append("\n\n📝 To apply preprocessing:")
        recommendations.append("  from app.audio.preprocessing import preprocess_audio_file")
        recommendations.append(f"  preprocess_audio_file('{audio_path}', 'output.wav')")

    recommendations.append("\n" + "=" * 60)

    return "\n".join(recommendations)
