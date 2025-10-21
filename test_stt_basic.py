#!/usr/bin/env python3
"""Quick STT test to diagnose Vosk transcription issues."""

import sys
from vosk import Model, KaldiRecognizer
from app.audio.mic import MicrophoneStream
from app.util.config import load_config

def test_basic_stt():
    """Test if Vosk can transcribe anything at all."""
    print("Loading config...")
    config = load_config()

    print(f"Loading Vosk model from: {config.vosk_model_path}")
    model = Model(config.vosk_model_path)

    print(f"Creating recognizer (sample rate: {config.sample_rate_hz}Hz)")
    recognizer = KaldiRecognizer(model, config.sample_rate_hz)
    recognizer.SetWords(True)

    print("\n" + "="*60)
    print("BASIC STT TEST")
    print("="*60)
    print("Speak clearly into the microphone...")
    print("I will show you partial results in real-time")
    print("Press Ctrl+C to stop")
    print("="*60 + "\n")

    frame_count = 0
    max_frames = 500  # About 10 seconds at 20ms per frame

    try:
        with MicrophoneStream(
            rate=config.sample_rate_hz,
            chunk_samples=config.chunk_samples,
            input_device_name=config.mic_device_name,
        ) as mic:
            while frame_count < max_frames:
                frame = mic.read(config.chunk_samples)
                frame_count += 1

                if recognizer.AcceptWaveform(frame):
                    result = recognizer.Result()
                    print(f"\n[FINAL] {result}")
                else:
                    partial = recognizer.PartialResult()
                    # Only print if there's actual text
                    if '"partial" : "' in partial and partial.count('"') > 3:
                        # Extract just the partial text
                        try:
                            import json
                            partial_obj = json.loads(partial)
                            if partial_obj.get("partial"):
                                print(f"\r[PARTIAL] {partial_obj['partial']}", end='', flush=True)
                        except:
                            pass

            # Get final result
            final = recognizer.FinalResult()
            print(f"\n\n[FINAL RESULT] {final}")

    except KeyboardInterrupt:
        print("\n\nStopped by user")
        final = recognizer.FinalResult()
        print(f"[FINAL RESULT] {final}")

    print("\n" + "="*60)
    print("Test complete")
    print("="*60)

if __name__ == "__main__":
    test_basic_stt()
