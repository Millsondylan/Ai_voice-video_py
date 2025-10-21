"""Audio quality diagnostics for troubleshooting STT accuracy issues."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


def analyze_audio_quality(wav_path: str | Path) -> Dict[str, any]:
    """Generate comprehensive audio quality metrics.

    Analyzes:
    - Clipping (amplitude exceeding normal range)
    - RMS energy (overall volume level)
    - DC offset (microphone bias issues)
    - Estimated SNR (signal-to-noise ratio)

    Args:
        wav_path: Path to WAV file

    Returns:
        Dictionary with quality metrics and warnings
    """
    if not NUMPY_AVAILABLE:
        return {"error": "numpy not installed - required for audio analysis"}

    try:
        with wave.open(str(wav_path), "rb") as wf:
            # Read audio data
            frames = wf.readframes(wf.getnframes())
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()

            # Convert to numpy array
            if sample_width == 2:  # 16-bit
                audio = np.frombuffer(frames, dtype=np.int16)
            elif sample_width == 4:  # 32-bit
                audio = np.frombuffer(frames, dtype=np.int32)
            else:
                return {"error": f"Unsupported sample width: {sample_width}"}

            # Normalize to [-1.0, 1.0] range
            max_val = float(2 ** (sample_width * 8 - 1))
            normalized = audio.astype(np.float32) / max_val

            # Calculate metrics
            metrics = {}

            # Check for clipping
            max_amplitude = np.max(np.abs(normalized))
            metrics["max_amplitude"] = float(max_amplitude)
            metrics["clipping_detected"] = max_amplitude > 0.95

            # Calculate RMS energy
            rms = np.sqrt(np.mean(normalized ** 2))
            metrics["rms_energy"] = float(rms)
            metrics["low_volume"] = rms < 0.01

            # Check for DC offset
            mean = np.mean(normalized)
            metrics["dc_offset"] = float(mean)
            metrics["dc_offset_detected"] = abs(mean) > 0.01

            # Estimate SNR (crude approximation)
            noise_floor = float(np.percentile(np.abs(normalized), 10))
            signal_peak = float(np.percentile(np.abs(normalized), 90))

            if noise_floor > 0:
                snr_db = 20 * np.log10(signal_peak / noise_floor)
                metrics["estimated_snr_db"] = float(snr_db)
                metrics["low_snr"] = snr_db < 10
            else:
                metrics["estimated_snr_db"] = None
                metrics["low_snr"] = False

            # Overall assessment
            warnings = []
            if metrics["clipping_detected"]:
                warnings.append(
                    f"⚠️ Audio clipping detected ({max_amplitude:.2f}). "
                    "Reduce microphone gain or input volume."
                )
            if metrics["low_volume"]:
                warnings.append(
                    f"⚠️ Audio level very low (RMS: {rms:.4f}). "
                    "Increase microphone gain or speak closer."
                )
            if metrics["dc_offset_detected"]:
                warnings.append(
                    f"⚠️ DC offset detected ({mean:.4f}). "
                    "Microphone may have bias issue."
                )
            if metrics["low_snr"]:
                warnings.append(
                    f"⚠️ Very low SNR ({metrics['estimated_snr_db']:.1f} dB). "
                    "Reduce background noise or use noise reduction."
                )

            metrics["warnings"] = warnings
            metrics["duration_seconds"] = len(audio) / sample_rate

            return metrics

    except Exception as e:
        return {"error": str(e)}


def generate_quality_report(wav_path: str | Path) -> str:
    """Generate human-readable audio quality report.

    Args:
        wav_path: Path to WAV file

    Returns:
        Formatted quality report string
    """
    metrics = analyze_audio_quality(wav_path)

    if "error" in metrics:
        return f"❌ Error analyzing {wav_path}: {metrics['error']}"

    report = [f"\n📊 Audio Quality Report: {Path(wav_path).name}"]
    report.append("=" * 60)

    # Basic metrics
    report.append(f"\n🎵 Signal Metrics:")
    report.append(f"  Duration: {metrics['duration_seconds']:.2f}s")
    report.append(f"  Max Amplitude: {metrics['max_amplitude']:.3f}")
    report.append(f"  RMS Energy: {metrics['rms_energy']:.4f}")
    report.append(f"  DC Offset: {metrics['dc_offset']:.4f}")

    if metrics['estimated_snr_db'] is not None:
        report.append(f"  Estimated SNR: {metrics['estimated_snr_db']:.1f} dB")

    # Quality indicators
    report.append(f"\n✓ Quality Indicators:")
    report.append(f"  Clipping: {'❌ YES' if metrics['clipping_detected'] else '✅ No'}")
    report.append(f"  Low Volume: {'⚠️ YES' if metrics['low_volume'] else '✅ No'}")
    report.append(f"  DC Offset Issue: {'⚠️ YES' if metrics['dc_offset_detected'] else '✅ No'}")
    report.append(f"  Low SNR: {'⚠️ YES' if metrics['low_snr'] else '✅ No'}")

    # Warnings
    if metrics['warnings']:
        report.append(f"\n⚠️ Issues Found:")
        for warning in metrics['warnings']:
            report.append(f"  {warning}")
    else:
        report.append(f"\n✅ No quality issues detected!")

    report.append("=" * 60)

    return "\n".join(report)


def compare_audio_engines(wav_path: str | Path) -> Dict[str, any]:
    """Compare transcription across multiple STT engines for debugging.

    This helps isolate whether issues are Vosk-specific or general audio problems.

    Args:
        wav_path: Path to WAV file

    Returns:
        Dictionary with results from different engines
    """
    results = {}

    # Test with Vosk (if available)
    try:
        from vosk import Model, KaldiRecognizer
        import json

        model_path = "models/vosk-model-en-us-0.22"
        model = Model(model_path)

        with wave.open(str(wav_path), "rb") as wf:
            rec = KaldiRecognizer(model, wf.getframerate())
            rec.SetWords(True)

            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                rec.AcceptWaveform(data)

            vosk_result = json.loads(rec.FinalResult())
            results["vosk"] = {
                "text": vosk_result.get("text", ""),
                "available": True,
            }

            # Calculate confidence
            if "result" in vosk_result:
                confidences = [w.get("conf", 0) for w in vosk_result["result"]]
                avg_conf = sum(confidences) / len(confidences) if confidences else 0
                results["vosk"]["avg_confidence"] = avg_conf

    except Exception as e:
        results["vosk"] = {"available": False, "error": str(e)}

    # Test with speech_recognition library (if available)
    try:
        import speech_recognition as sr

        r = sr.Recognizer()
        with sr.AudioFile(str(wav_path)) as source:
            audio = r.record(source)

        # Try Google (free, no API key)
        try:
            google_result = r.recognize_google(audio)
            results["google"] = {
                "text": google_result,
                "available": True,
            }
        except Exception as e:
            results["google"] = {"available": False, "error": str(e)}

    except ImportError:
        results["google"] = {"available": False, "error": "speech_recognition not installed"}

    return results


def generate_comparison_report(wav_path: str | Path) -> str:
    """Generate comparison report across STT engines.

    Args:
        wav_path: Path to WAV file

    Returns:
        Formatted comparison report
    """
    results = compare_audio_engines(wav_path)

    report = [f"\n🔍 STT Engine Comparison: {Path(wav_path).name}"]
    report.append("=" * 60)

    for engine, data in results.items():
        report.append(f"\n{engine.upper()}:")
        if data.get("available"):
            report.append(f"  Result: '{data.get('text', '')}'")
            if "avg_confidence" in data:
                report.append(f"  Avg Confidence: {data['avg_confidence']:.2f}")
        else:
            report.append(f"  Status: Not available")
            if "error" in data:
                report.append(f"  Error: {data['error']}")

    report.append("\n" + "=" * 60)
    report.append("\n💡 Interpretation:")
    report.append("  - If all engines fail: Audio quality issue")
    report.append("  - If only Vosk fails: Vosk configuration issue")
    report.append("  - If results differ significantly: Model vocabulary mismatch")

    return "\n".join(report)
