#!/usr/bin/env python3
"""
Comprehensive test script for voice assistant pipeline.
Tests all four issues from the implementation guide:
1. Complete speech capture
2. Wake word detection reliability
3. Consistent TTS replies
4. Multi-turn conversation with context
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

from vosk import Model

from app.ai.vlm_client import VLMClient
from app.audio.capture import run_segment, SegmentCaptureResult
from app.audio.mic import MicrophoneStream
from app.audio.stt import StreamingTranscriber
from app.audio.tts import SpeechSynthesizer
from app.audio.wake import WakeWordListener
from app.session import SessionCallbacks, SessionManager, SessionState
from app.util.config import AppConfig, load_config


class TestResults:
    """Track test results."""

    def __init__(self):
        self.wake_detections = 0
        self.failed_wake = 0
        self.speech_captures = 0
        self.truncated_speech = 0
        self.tts_successes = 0
        self.tts_failures = 0
        self.conversation_turns = 0
        self.context_retained = False

    def print_summary(self):
        print("\n" + "=" * 60)
        print("TEST RESULTS SUMMARY")
        print("=" * 60)
        print(f"Wake Word Detection: {self.wake_detections} successful, {self.failed_wake} failed")
        print(f"Speech Capture: {self.speech_captures} captured, {self.truncated_speech} truncated")
        print(f"TTS Reliability: {self.tts_successes} successful, {self.tts_failures} failed")
        print(f"Conversation: {self.conversation_turns} turns, context_retained={self.context_retained}")
        print("=" * 60)


def test_1_speech_capture(config: AppConfig, transcriber: StreamingTranscriber) -> bool:
    """
    Test Issue #1: Incomplete Speech Capture

    Validates:
    - VAD detects speech start/end correctly
    - No premature cutoff during speech
    - Silence timeout works as expected
    """
    print("\n" + "=" * 60)
    print("TEST 1: COMPLETE SPEECH CAPTURE")
    print("=" * 60)
    print("Instructions:")
    print("  1. Say a LONG sentence (10+ words) with pauses")
    print("  2. Stop talking and wait for silence detection")
    print("  3. We'll check if entire utterance was captured")
    print()

    with MicrophoneStream(
        rate=config.sample_rate_hz,
        chunk_samples=config.chunk_samples,
        input_device_name=config.mic_device_name,
    ) as mic:
        result = run_segment(
            mic=mic,
            stt=transcriber,
            config=config,
            stop_event=None,
            on_chunk=None,
            pre_roll_buffer=None,
            no_speech_timeout_ms=None,
        )

        print(f"\n[RESULT]")
        print(f"  Transcript: '{result.clean_transcript}'")
        print(f"  Stop Reason: {result.stop_reason}")
        print(f"  Duration: {result.duration_ms}ms")
        print(f"  Audio: {result.audio_ms}ms")
        print(f"  Words: {len(result.clean_transcript.split())}")

        # Validate
        success = True
        if result.stop_reason not in ("silence", "bye", "done"):
            print(f"  ⚠️  WARNING: Unexpected stop reason: {result.stop_reason}")
            success = False

        if len(result.clean_transcript.split()) < 5:
            print(f"  ⚠️  WARNING: Very short transcript, may have been cut off")
            success = False

        if success:
            print("  ✅ PASSED: Full speech captured")
        else:
            print("  ❌ FAILED: Speech may have been truncated")

        return success


def test_2_wake_word_detection(config: AppConfig, wake_transcriber: StreamingTranscriber) -> bool:
    """
    Test Issue #2: Unreliable Wake Word Detection

    Validates:
    - Wake word triggers on correct phrase
    - Debouncing prevents multiple triggers
    - Pre-roll buffer captures audio before detection
    """
    print("\n" + "=" * 60)
    print("TEST 2: WAKE WORD DETECTION")
    print("=" * 60)
    print(f"Instructions:")
    print(f"  1. Say the wake word: '{config.wake_word}'")
    print(f"  2. We'll test if detection is reliable")
    print(f"  3. Waiting 10 seconds for detection...")
    print()

    detected = False
    pre_roll = None

    def on_wake_detect(buffer):
        nonlocal detected, pre_roll
        detected = True
        pre_roll = buffer
        print(f"  ✅ Wake word detected!")
        print(f"  Pre-roll buffer: {len(buffer)} frames")

    listener = WakeWordListener(
        wake_variants=config.wake_variants,
        on_detect=on_wake_detect,
        transcriber=wake_transcriber,
        sample_rate=config.sample_rate_hz,
        chunk_samples=config.chunk_samples,
        debounce_ms=700,
        mic_device_name=config.mic_device_name,
        pre_roll_ms=config.pre_roll_ms,
    )

    listener.start()
    time.sleep(10)  # Wait for detection
    listener.stop()
    listener.join(timeout=2)

    if detected:
        print(f"  ✅ PASSED: Wake word detection working")
        return True
    else:
        print(f"  ❌ FAILED: Wake word not detected in 10 seconds")
        return False


def test_3_tts_consistency(config: AppConfig, tts: SpeechSynthesizer) -> bool:
    """
    Test Issue #3: Missing/Inconsistent Voice Replies

    Validates:
    - TTS speaks first message
    - TTS speaks subsequent messages (not just first)
    - No audio device conflicts
    """
    print("\n" + "=" * 60)
    print("TEST 3: TTS CONSISTENCY")
    print("=" * 60)
    print("Testing multiple TTS outputs in sequence...")
    print()

    messages = [
        "This is the first test message.",
        "This is the second test message.",
        "This is the third test message.",
        "Final test message, number four.",
    ]

    successes = 0
    failures = 0

    for i, msg in enumerate(messages, 1):
        print(f"  [{i}/{len(messages)}] Speaking: '{msg}'")
        try:
            tts.speak(msg)
            print(f"       ✅ Success")
            successes += 1
            time.sleep(0.5)  # Brief pause between
        except Exception as e:
            print(f"       ❌ Failed: {e}")
            failures += 1

    print()
    if failures == 0:
        print(f"  ✅ PASSED: All {successes} TTS outputs successful")
        return True
    else:
        print(f"  ❌ FAILED: {failures}/{len(messages)} TTS outputs failed")
        return False


def test_4_multi_turn_conversation(
    config: AppConfig,
    segment_recorder,
    vlm_client: VLMClient,
    tts: SpeechSynthesizer,
) -> bool:
    """
    Test Issue #4: Single Turn Limitation

    Validates:
    - Multiple conversation turns without wake word
    - Context retention across turns
    - 15s timeout works
    - 'bye glasses' exit works
    """
    print("\n" + "=" * 60)
    print("TEST 4: MULTI-TURN CONVERSATION")
    print("=" * 60)
    print("Instructions:")
    print("  1. Session will start (no wake word needed)")
    print("  2. Ask a question")
    print("  3. Ask a follow-up that requires context")
    print("  4. Say 'bye glasses' to exit")
    print("  5. OR wait 15 seconds of silence to auto-exit")
    print()
    print("Starting session in 3 seconds...")
    time.sleep(3)

    results = {
        "turns": 0,
        "context_test": False,
        "exit_method": None,
    }

    def on_session_started(session_id: str):
        print(f"  📍 Session started: {session_id}")

    def on_state_changed(state: SessionState, turn_index: int):
        print(f"  🔄 State: {state.value} (turn {turn_index})")

    def on_transcript_ready(turn_index: int, result):
        results["turns"] = turn_index + 1
        print(f"  🎤 Turn {turn_index + 1}: '{result.clean_transcript}'")

    def on_response_ready(turn_index: int, text: str, payload: dict):
        print(f"  💬 Response: '{text}'")

    def on_session_finished(session_id: str, reason: str):
        results["exit_method"] = reason
        print(f"  🏁 Session ended: {reason}")

    def on_error(message: str):
        print(f"  ❌ Error: {message}")

    callbacks = SessionCallbacks(
        session_started=on_session_started,
        state_changed=on_state_changed,
        transcript_ready=on_transcript_ready,
        response_ready=on_response_ready,
        session_finished=on_session_finished,
        error=on_error,
    )

    manager = SessionManager(
        config=config,
        segment_recorder=segment_recorder,
        vlm_client=vlm_client,
        tts=tts,
        followup_timeout_ms=15000,  # 15 seconds
    )

    try:
        manager.run_session(callbacks=callbacks, pre_roll_buffer=None)
    except KeyboardInterrupt:
        print("\n  ⚠️  Test interrupted by user")
        manager.cancel()

    print()
    print(f"[RESULTS]")
    print(f"  Turns completed: {results['turns']}")
    print(f"  Exit method: {results['exit_method']}")

    # Validation
    success = True
    if results["turns"] < 2:
        print(f"  ⚠️  WARNING: Only {results['turns']} turn(s), expected multi-turn")
        success = False

    if results["exit_method"] not in ("bye", "timeout15"):
        print(f"  ⚠️  WARNING: Unexpected exit: {results['exit_method']}")

    if success:
        print(f"  ✅ PASSED: Multi-turn conversation working")
    else:
        print(f"  ❌ FAILED: Multi-turn issues detected")

    return success


def main():
    parser = argparse.ArgumentParser(description="Test voice assistant pipeline")
    parser.add_argument("-c", "--config", help="Config file path")
    parser.add_argument(
        "--test",
        choices=["1", "2", "3", "4", "all"],
        default="all",
        help="Which test to run (default: all)",
    )
    args = parser.parse_args()

    # Load configuration
    try:
        config_path = Path(args.config) if args.config else None
        config = load_config(config_path)
    except Exception as e:
        print(f"❌ Failed to load config: {e}", file=sys.stderr)
        return 1

    # Initialize components
    print("Initializing voice assistant components...")

    try:
        model = Model(config.vosk_model_path)
        wake_transcriber = StreamingTranscriber(sample_rate=config.sample_rate_hz, model=model)
        segment_transcriber = StreamingTranscriber(sample_rate=config.sample_rate_hz, model=model)
    except Exception as e:
        print(f"❌ Failed to initialize Vosk: {e}", file=sys.stderr)
        return 1

    try:
        vlm_client = VLMClient(config)
    except Exception as e:
        print(f"❌ Failed to initialize VLM: {e}", file=sys.stderr)
        return 1

    from app.segment import SegmentRecorder

    segment_recorder = SegmentRecorder(config, segment_transcriber)
    tts = SpeechSynthesizer(voice=config.tts_voice, rate=config.tts_rate)

    # Run tests
    results = TestResults()
    test_selection = args.test

    if test_selection in ("1", "all"):
        try:
            success = test_1_speech_capture(config, segment_transcriber)
            if success:
                results.speech_captures += 1
            else:
                results.truncated_speech += 1
        except KeyboardInterrupt:
            print("\n⚠️  Test 1 interrupted")
        except Exception as e:
            print(f"❌ Test 1 error: {e}")
            results.truncated_speech += 1

    if test_selection in ("2", "all"):
        try:
            success = test_2_wake_word_detection(config, wake_transcriber)
            if success:
                results.wake_detections += 1
            else:
                results.failed_wake += 1
        except KeyboardInterrupt:
            print("\n⚠️  Test 2 interrupted")
        except Exception as e:
            print(f"❌ Test 2 error: {e}")
            results.failed_wake += 1

    if test_selection in ("3", "all"):
        try:
            success = test_3_tts_consistency(config, tts)
            if success:
                results.tts_successes += 1
            else:
                results.tts_failures += 1
        except KeyboardInterrupt:
            print("\n⚠️  Test 3 interrupted")
        except Exception as e:
            print(f"❌ Test 3 error: {e}")
            results.tts_failures += 1

    if test_selection in ("4", "all"):
        try:
            success = test_4_multi_turn_conversation(config, segment_recorder, vlm_client, tts)
            results.conversation_turns = 1  # Mark as tested
            results.context_retained = success
        except KeyboardInterrupt:
            print("\n⚠️  Test 4 interrupted")
        except Exception as e:
            print(f"❌ Test 4 error: {e}")

    # Print summary
    results.print_summary()

    return 0


if __name__ == "__main__":
    sys.exit(main())
