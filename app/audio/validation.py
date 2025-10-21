"""Audio format validation utilities for Vosk STT accuracy."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class AudioFormatError(Exception):
    """Raised when audio format doesn't meet Vosk requirements."""
    pass


def validate_audio_format(wav_path: str | Path) -> Tuple[bool, List[str]]:
    """Validate audio meets Vosk requirements.

    Vosk requires:
    - Mono (1 channel)
    - 16-bit signed PCM
    - 16000 Hz sample rate
    - Uncompressed WAV format

    Args:
        wav_path: Path to WAV file

    Returns:
        Tuple of (is_valid, list of errors)
    """
    try:
        with wave.open(str(wav_path), "rb") as wf:
            errors = []

            # Check channels (must be mono)
            if wf.getnchannels() != 1:
                errors.append(
                    f"Must be mono (1 channel), got {wf.getnchannels()} channels. "
                    "Use: ffmpeg -i input.wav -ac 1 output.wav"
                )

            # Check sample width (must be 16-bit = 2 bytes)
            if wf.getsampwidth() != 2:
                errors.append(
                    f"Must be 16-bit PCM, got {wf.getsampwidth() * 8}-bit. "
                    "Use: ffmpeg -i input.wav -sample_fmt s16 output.wav"
                )

            # Check sample rate (should be 16kHz)
            if wf.getframerate() != 16000:
                errors.append(
                    f"Sample rate should be 16kHz, got {wf.getframerate()}Hz. "
                    "Use: ffmpeg -i input.wav -ar 16000 output.wav"
                )

            # Check compression (must be uncompressed PCM)
            if wf.getcomptype() != "NONE":
                errors.append(
                    f"Must be uncompressed PCM, got {wf.getcomptype()} compression. "
                    "Use: ffmpeg -i input.wav -acodec pcm_s16le output.wav"
                )

            return (len(errors) == 0, errors)

    except wave.Error as e:
        return (False, [f"Invalid WAV file: {e}"])
    except FileNotFoundError:
        return (False, [f"File not found: {wav_path}"])


def get_audio_info(wav_path: str | Path) -> Dict[str, any]:
    """Get detailed audio file information.

    Args:
        wav_path: Path to WAV file

    Returns:
        Dictionary with audio properties
    """
    try:
        with wave.open(str(wav_path), "rb") as wf:
            return {
                "channels": wf.getnchannels(),
                "sample_width_bytes": wf.getsampwidth(),
                "sample_width_bits": wf.getsampwidth() * 8,
                "sample_rate": wf.getframerate(),
                "num_frames": wf.getnframes(),
                "compression_type": wf.getcomptype(),
                "compression_name": wf.getcompname(),
                "duration_seconds": wf.getnframes() / wf.getframerate() if wf.getframerate() > 0 else 0,
            }
    except Exception as e:
        return {"error": str(e)}


def get_ffmpeg_conversion_command(
    input_path: str,
    output_path: Optional[str] = None,
    sample_rate: int = 16000,
) -> str:
    """Generate ffmpeg command to convert audio to Vosk-compatible format.

    Args:
        input_path: Path to input audio file
        output_path: Path for output file (defaults to input_vosk.wav)
        sample_rate: Target sample rate (default: 16000)

    Returns:
        ffmpeg command string
    """
    if output_path is None:
        output_path = str(Path(input_path).with_suffix("")) + "_vosk.wav"

    return (
        f'ffmpeg -i "{input_path}" '
        f"-ar {sample_rate} "  # Sample rate
        f"-ac 1 "  # Mono
        f"-sample_fmt s16 "  # 16-bit signed
        f'-acodec pcm_s16le "{output_path}"'  # PCM encoding
    )


def validate_with_suggestions(wav_path: str | Path) -> str:
    """Validate audio and provide actionable suggestions.

    Args:
        wav_path: Path to WAV file

    Returns:
        Human-readable validation report
    """
    is_valid, errors = validate_audio_format(wav_path)

    if is_valid:
        return f"✓ Audio format valid for Vosk: {wav_path}"

    report = [f"✗ Audio format issues for {wav_path}:\n"]
    for i, error in enumerate(errors, 1):
        report.append(f"  {i}. {error}")

    report.append("\nTo fix all issues at once:")
    report.append(f"  {get_ffmpeg_conversion_command(str(wav_path))}")

    return "\n".join(report)


def check_pyaudio_format(
    format_int: int,
    channels: int,
    rate: int,
) -> Tuple[bool, List[str]]:
    """Validate PyAudio stream configuration.

    Args:
        format_int: PyAudio format constant (e.g., pyaudio.paInt16)
        channels: Number of channels
        rate: Sample rate

    Returns:
        Tuple of (is_valid, list of warnings)
    """
    import pyaudio

    warnings = []

    # Check format (should be paInt16 = 8)
    if format_int != pyaudio.paInt16:
        warnings.append(
            f"Format should be pyaudio.paInt16 (8), got {format_int}. "
            "Vosk requires 16-bit signed PCM."
        )

    # Check channels
    if channels != 1:
        warnings.append(
            f"Channels should be 1 (mono), got {channels}. "
            "Vosk works best with mono audio."
        )

    # Check sample rate
    if rate != 16000:
        warnings.append(
            f"Sample rate should be 16000, got {rate}. "
            "Mismatch will cause severe transcription errors."
        )

    return (len(warnings) == 0, warnings)
