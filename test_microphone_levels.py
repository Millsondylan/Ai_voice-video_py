#!/usr/bin/env python3
"""Quick microphone level test to diagnose audio issues."""

import sys
import time
import numpy as np
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.audio.mic import MicrophoneStream
import webrtcvad

def calculate_rms(frame):
    """Calculate RMS (Root Mean Square) audio level."""
    audio_data = np.frombuffer(frame, dtype=np.int16)
    rms = np.sqrt(np.mean(audio_data**2))
    return rms

def rms_to_db(rms):
    """Convert RMS to decibels."""
    if rms == 0:
        return -96.0  # Silence floor
    return 20 * np.log10(rms / 32768.0)  # 32768 is max value for int16

def main():
    print("=" * 60)
    print("MICROPHONE LEVEL TEST")
    print("=" * 60)
    print("\nThis will help diagnose:")
    print("  - If your mic is too quiet")
    print("  - If there's too much background noise")
    print("  - If VAD settings are appropriate")
    print("\nSpeak at NORMAL volume when prompted...")
    print("=" * 60)

    sample_rate = 16000
    chunk_samples = 320

    # Test with different VAD levels
    for vad_level in [1, 2, 3]:
        print(f"\n\n{'='*60}")
        print(f"Testing with VAD Level {vad_level}")
        print(f"{'='*60}")
        print(f"Sensitivity: {['Most Sensitive', 'Balanced', 'Less Sensitive', 'Least Sensitive'][vad_level]}")
        print("\nRecording 5 seconds...")
        print("  - First 2 seconds: Stay SILENT")
        print("  - Last 3 seconds: Speak at NORMAL volume")
        print("\nStarting in 3...")
        time.sleep(1)
        print("2...")
        time.sleep(1)
        print("1...")
        time.sleep(1)
        print("GO!\n")

        vad = webrtcvad.Vad(vad_level)

        with MicrophoneStream(rate=sample_rate, chunk_samples=chunk_samples) as mic:
            samples = []
            speech_frames = 0
            total_frames = 0
            max_level = -96.0
            min_level = 0.0

            start_time = time.time()
            while time.time() - start_time < 5.0:
                frame = mic.read(chunk_samples)
                if not frame:
                    continue

                # Calculate audio level
                rms = calculate_rms(frame)
                db = rms_to_db(rms)

                # Track levels
                max_level = max(max_level, db)
                if db > -90:  # Ignore silence floor
                    min_level = max(min_level, db) if min_level == 0 else min(min_level, db)

                # VAD detection
                is_speech = vad.is_speech(frame, sample_rate)
                total_frames += 1
                if is_speech:
                    speech_frames += 1

                # Real-time display
                elapsed = time.time() - start_time
                bar = "█" if is_speech else "▁"
                print(f"\r[{elapsed:4.1f}s] Level: {db:6.1f}dB {bar * 20} ", end="", flush=True)

                samples.append((rms, db, is_speech))

        print("\n")
        print(f"Results for VAD Level {vad_level}:")
        print(f"  - Speech detected in {speech_frames}/{total_frames} frames ({speech_frames/total_frames*100:.1f}%)")
        print(f"  - Maximum level: {max_level:.1f}dB")
        print(f"  - Minimum level: {min_level:.1f}dB")
        print(f"  - Dynamic range: {max_level - min_level:.1f}dB")

        # Diagnosis
        print("\nDiagnosis:")
        if max_level < -40:
            print("  ⚠️  Mic input is TOO QUIET")
            print("      - Check system mic volume (should be ~50-70%)")
            print("      - Move closer to microphone")
            print("      - Check if mic is muted")
        elif max_level > -10:
            print("  ⚠️  Mic input is TOO LOUD (may clip/distort)")
            print("      - Reduce system mic volume")
        else:
            print("  ✅ Mic level is GOOD")

        if min_level < -50 and speech_frames < total_frames * 0.3:
            print("  ⚠️  High background noise detected")
            print("      - Use VAD level 2 or 3 to filter noise")
            print("      - Reduce ambient noise if possible")

        if speech_frames > total_frames * 0.8 and vad_level >= 2:
            print("  ⚠️  VAD too sensitive - detecting noise as speech")
            print("      - Try VAD level 3")

        if speech_frames < 5 and vad_level <= 2:
            print("  ⚠️  VAD not detecting speech properly")
            print("      - Try VAD level 1 (more sensitive)")
            print("      - Speak louder")
            print("      - Check mic is working")

    print("\n" + "=" * 60)
    print("RECOMMENDED SETTINGS")
    print("=" * 60)

    # Provide recommendations
    print("\nBased on the test above, update config.json:")
    print('  "vad_aggressiveness": 2  // Start with 2 (balanced)')
    print("\nIf wake word still requires shouting:")
    print('  "vad_aggressiveness": 1  // More sensitive')
    print("\nIf too many false activations from noise:")
    print('  "vad_aggressiveness": 3  // Less sensitive')

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest cancelled.")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
