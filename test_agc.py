#!/usr/bin/env python3
"""Test AGC (Automatic Gain Control) functionality.

This script tests the AGC system to verify it automatically boosts quiet microphones.
Run this to see AGC in action with your microphone.
"""

import time
import numpy as np
from app.audio.mic import MicrophoneStream
from app.audio.agc import AutomaticGainControl, AdaptiveVAD


def calculate_rms(frame: bytes) -> float:
    """Calculate RMS level of audio frame."""
    audio_data = np.frombuffer(frame, dtype=np.int16)
    rms = np.sqrt(np.mean(audio_data**2))
    return rms


def rms_to_db(rms: float) -> float:
    """Convert RMS to decibels."""
    if rms == 0:
        return -96.0
    return 20 * np.log10(rms / 32768.0)


def main():
    """Test AGC with live microphone input."""
    print("=" * 70)
    print("AGC (Automatic Gain Control) Test")
    print("=" * 70)
    print()
    print("This test will show how AGC automatically boosts quiet microphones.")
    print("Speak at normal volume during the test.")
    print()

    sample_rate = 16000
    chunk_samples = 320  # 20ms frames

    # Initialize AGC
    agc = AutomaticGainControl(
        target_rms=3000.0,    # Target normalized level
        min_gain=1.0,         # Minimum 1x gain
        max_gain=10.0,        # Maximum 10x gain
        attack_rate=0.9,      # Fast attack
        release_rate=0.999    # Slow release
    )

    # Initialize Adaptive VAD
    adaptive_vad = AdaptiveVAD(sample_rate=sample_rate)

    print("Starting 10-second test...")
    print()
    print("Legend:")
    print("  [AGC] = AGC statistics (gain, RMS levels)")
    print("  [VAD] = Voice Activity Detection status")
    print("  █ = Speech detected")
    print("  ▁ = Silence")
    print()

    with MicrophoneStream(rate=sample_rate, chunk_samples=chunk_samples) as mic:
        test_duration_s = 10
        frames_per_second = sample_rate / chunk_samples
        total_frames = int(test_duration_s * frames_per_second)

        raw_rms_values = []
        gained_rms_values = []

        for i in range(total_frames):
            raw_frame = mic.read(chunk_samples)

            # Calculate raw RMS
            raw_rms = calculate_rms(raw_frame)
            raw_db = rms_to_db(raw_rms)

            # Apply AGC
            gained_frame = agc.process(raw_frame)

            # Calculate gained RMS
            gained_rms = calculate_rms(gained_frame)
            gained_db = rms_to_db(gained_rms)

            # Use adaptive VAD
            is_speech = adaptive_vad.is_speech(gained_frame)

            # Store values
            raw_rms_values.append(raw_rms)
            gained_rms_values.append(gained_rms)

            # Print status every second
            if i % int(frames_per_second) == 0:
                agc_stats = agc.get_stats()
                vad_level = adaptive_vad.get_vad_level()

                print(f"Second {i // int(frames_per_second) + 1}:")
                print(f"  [AGC] Gain: {agc_stats['current_gain']:.2f}x ({agc_stats['current_gain_db']:+.1f}dB)")
                print(f"  [AGC] Raw RMS: {raw_rms:.0f} ({raw_db:.1f}dB) → Gained RMS: {gained_rms:.0f} ({gained_db:.1f}dB)")
                print(f"  [VAD] Level: {vad_level} | Speech: {'█ YES' if is_speech else '▁ no'}")
                print()

    # Final statistics
    print()
    print("=" * 70)
    print("Test Complete - Results")
    print("=" * 70)
    print()

    avg_raw_rms = np.mean(raw_rms_values)
    max_raw_rms = np.max(raw_rms_values)
    avg_gained_rms = np.mean(gained_rms_values)
    max_gained_rms = np.max(gained_rms_values)

    avg_raw_db = rms_to_db(avg_raw_rms)
    max_raw_db = rms_to_db(max_raw_rms)
    avg_gained_db = rms_to_db(avg_gained_rms)
    max_gained_db = rms_to_db(max_gained_rms)

    final_agc_stats = agc.get_stats()
    final_vad_level = adaptive_vad.get_vad_level()

    print(f"Raw Audio (without AGC):")
    print(f"  Average RMS: {avg_raw_rms:.0f} ({avg_raw_db:.1f}dB)")
    print(f"  Maximum RMS: {max_raw_rms:.0f} ({max_raw_db:.1f}dB)")
    print()

    print(f"Gained Audio (with AGC):")
    print(f"  Average RMS: {avg_gained_rms:.0f} ({avg_gained_db:.1f}dB)")
    print(f"  Maximum RMS: {max_gained_rms:.0f} ({max_gained_db:.1f}dB)")
    print()

    print(f"AGC Final Statistics:")
    print(f"  Final Gain: {final_agc_stats['current_gain']:.2f}x ({final_agc_stats['current_gain_db']:+.1f}dB)")
    print(f"  Target RMS: {final_agc_stats['target_rms']:.0f}")
    print(f"  Achieved RMS: {final_agc_stats['running_rms']:.0f}")
    print(f"  Frames Processed: {final_agc_stats['frame_count']}")
    print()

    print(f"Adaptive VAD:")
    print(f"  Auto-selected Level: {final_vad_level}")
    print()

    # Diagnostics
    print("Diagnostics:")

    if avg_raw_db < -45:
        print(f"  ⚠️  Raw microphone is VERY QUIET ({avg_raw_db:.1f}dB)")
        print(f"      → AGC boosted it by {final_agc_stats['current_gain']:.2f}x to compensate")
        if avg_gained_db > -30:
            print(f"      ✅ AGC successfully normalized audio to {avg_gained_db:.1f}dB")
        else:
            print(f"      ⚠️  Even with AGC, audio is still quiet ({avg_gained_db:.1f}dB)")
            print(f"         Try increasing system microphone volume")
    elif avg_raw_db < -30:
        print(f"  ℹ️  Raw microphone is quiet ({avg_raw_db:.1f}dB)")
        print(f"      → AGC boosted it by {final_agc_stats['current_gain']:.2f}x")
        print(f"      ✅ Result: {avg_gained_db:.1f}dB (good level)")
    else:
        print(f"  ✅ Raw microphone level is good ({avg_raw_db:.1f}dB)")
        print(f"      → AGC applied minimal gain ({final_agc_stats['current_gain']:.2f}x)")

    print()

    if final_vad_level == 1:
        print("  ℹ️  VAD Level 1 (most sensitive) - quiet environment detected")
    elif final_vad_level == 2:
        print("  ✅ VAD Level 2 (balanced) - moderate noise environment")
    else:
        print("  ℹ️  VAD Level 3 (least sensitive) - noisy environment detected")

    print()
    print("=" * 70)
    print()

    # Recommendations
    print("Recommendations:")

    if avg_raw_db < -50:
        print("  1. Your microphone is very quiet. Check:")
        print("     - System microphone volume (should be 80-90%)")
        print("     - Selected microphone device (use best quality mic)")
        print("     - Physical microphone placement (closer to mouth)")
        print("  2. AGC will help, but increasing system volume is better")
    elif avg_raw_db < -35:
        print("  1. Microphone is a bit quiet but AGC should handle it")
        print("  2. For best results, increase system mic volume to 80-90%")
    else:
        print("  ✅ Your microphone level is optimal for voice detection")

    print()
    print("The voice assistant will now use these AGC settings automatically!")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
