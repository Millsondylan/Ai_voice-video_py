#!/usr/bin/env python3
"""Test VAD levels to find optimal setting for your environment."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.audio.mic import MicrophoneStream
from app.audio.vad import VoiceActivityDetector


def test_vad_level(level: int, duration_seconds: int = 3):
    """Test a specific VAD aggressiveness level."""
    print(f"\n{'='*60}")
    print(f"Testing VAD Level {level}")
    print(f"{'='*60}")
    print(f"Aggressiveness: {'Very Sensitive' if level == 0 else 'Sensitive' if level == 1 else 'Balanced' if level == 2 else 'Very Selective'}")
    print(f"\nSpeak now for {duration_seconds} seconds...")
    print("Legend: █ = Speech detected | ▁ = Silence/Noise\n")

    vad = VoiceActivityDetector(sample_rate=16000, frame_duration_ms=30, aggressiveness=level)

    speech_frames = 0
    total_frames = 0

    try:
        with MicrophoneStream(rate=16000, chunk_samples=480) as mic:  # 30ms frames
            start = time.time()

            while (time.time() - start) < duration_seconds:
                frame = mic.read(480)  # 30ms at 16kHz
                is_speech = vad.is_speech(frame)

                total_frames += 1
                if is_speech:
                    speech_frames += 1

                # Print bar
                print('█' if is_speech else '▁', end='', flush=True)

                if total_frames % 33 == 0:  # New line every ~1 second
                    percentage = (speech_frames / total_frames * 100) if total_frames > 0 else 0
                    print(f"  {percentage:.0f}%")

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nError: {e}")
        return None

    percentage = (speech_frames / total_frames * 100) if total_frames > 0 else 0
    print(f"\n\nResults:")
    print(f"  Total frames: {total_frames}")
    print(f"  Speech detected: {speech_frames} ({percentage:.1f}%)")

    if percentage == 0:
        print(f"  ❌ No speech detected - Level {level} may be TOO AGGRESSIVE")
    elif percentage < 20:
        print(f"  ⚠️ Very little speech detected - Level {level} might be too aggressive")
    elif percentage < 50:
        print(f"  ✅ Some speech detected - Level {level} is working")
    elif percentage < 80:
        print(f"  ✅ Good speech detection - Level {level} looks good!")
    else:
        print(f"  ⚠️ Very high detection - Level {level} might be too sensitive (picking up noise?)")

    return percentage


def main():
    """Test all VAD levels."""
    print("\n" + "="*60)
    print("VAD LEVEL TESTING")
    print("="*60)
    print("\nThis will test VAD levels 1, 2, and 3.")
    print("Speak normally during each test.\n")

    input("Press Enter to start testing...")

    results = {}

    # Test levels 1, 2, 3 (skip 0 as it's too sensitive for most cases)
    for level in [1, 2, 3]:
        percentage = test_vad_level(level, duration_seconds=3)
        if percentage is not None:
            results[level] = percentage

        if level < 3:
            print("\nReady for next test...")
            time.sleep(1)

    # Summary
    print("\n" + "="*60)
    print("SUMMARY & RECOMMENDATION")
    print("="*60)

    if not results:
        print("\n❌ No valid results collected")
        return

    print("\nSpeech Detection Rates:")
    for level, percentage in results.items():
        status = "✅" if 20 < percentage < 80 else "⚠️" if percentage > 0 else "❌"
        print(f"  {status} Level {level}: {percentage:.1f}%")

    # Find best level
    valid_levels = [level for level, pct in results.items() if 20 < pct < 80]

    if valid_levels:
        # Prefer higher level (more selective) if it still detects speech
        recommended = max(valid_levels)
        print(f"\n🎯 RECOMMENDED: Use VAD level {recommended}")
        print(f"\nUpdate your config.json:")
        print(f'  "vad_aggressiveness": {recommended}')
    else:
        # No ideal level found
        if all(pct == 0 for pct in results.values()):
            print(f"\n❌ NO SPEECH DETECTED AT ANY LEVEL")
            print("\nPossible issues:")
            print("  1. Microphone not working or muted")
            print("  2. Wrong microphone selected")
            print("  3. Microphone doesn't support 16kHz")
            print("\nTry:")
            print("  python3 -c 'from app.audio.mic import MicrophoneStream; MicrophoneStream.print_device_info()'")
        elif all(pct > 80 for pct in results.values()):
            print(f"\n⚠️ HIGH DETECTION AT ALL LEVELS - May be picking up too much noise")
            print(f"\n🎯 RECOMMENDED: Use VAD level 3 (most selective)")
            print("\nAlso consider:")
            print("  - Reduce microphone gain")
            print("  - Move microphone away from noise sources")
            print("  - Enable noise gate in config: 'apply_noise_gate': true")
        else:
            # Use level with closest to 50% detection
            best_level = min(results.keys(), key=lambda k: abs(results[k] - 50))
            print(f"\n🎯 RECOMMENDED: Use VAD level {best_level} (closest to balanced)")
            print(f"\nUpdate your config.json:")
            print(f'  "vad_aggressiveness": {best_level}')

    print("\n" + "="*60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTesting cancelled by user")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
