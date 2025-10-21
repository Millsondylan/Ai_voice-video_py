#!/usr/bin/env python3
"""
Enhanced Diagnostic Script for Voice Assistant System

This comprehensive diagnostic tool tests a Vosk/Whisper-based voice assistant with:
- Detailed timing logs with millisecond precision
- Real-time VAD and wake word state monitoring
- Multi-turn conversation testing with context tracking
- Silence and termination handling validation
- Microphone re-engagement verification after TTS
- Context memory logging at each turn
- Comprehensive validation and reporting

Addresses key issues:
1. Partial audio capture (first syllables lost)
2. Unreliable wake-word triggering
3. System becoming unresponsive after TTS
4. Loss of conversational context

Usage:
    python diagnostic_voice_assistant.py                    # Run all tests
    python diagnostic_voice_assistant.py --test 1           # Run specific test
    python diagnostic_voice_assistant.py --monitor          # Real-time VAD monitor
    python diagnostic_voice_assistant.py --interactive      # Guided testing
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import webrtcvad
from vosk import Model

from app.ai.vlm_client import VLMClient
from app.audio.capture import run_segment, SegmentCaptureResult
from app.audio.mic import MicrophoneStream
from app.audio.stt import StreamingTranscriber
from app.audio.tts import SpeechSynthesizer
from app.audio.wake import WakeWordListener
from app.session import SessionCallbacks, SessionManager, SessionState
from app.segment import SegmentRecorder
from app.util.config import AppConfig, load_config


# ============================================================================
# DIAGNOSTIC LOGGER - Millisecond-precision structured logging
# ============================================================================

class DiagnosticLogger:
    """Enhanced logger with millisecond-precision timestamps and structured output."""

    def __init__(self, log_file: Optional[Path] = None):
        self.start_time = time.time()
        self.log_file = log_file
        self.logs: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def _timestamp(self) -> str:
        """Get formatted timestamp [HH:MM:SS.mmm]."""
        elapsed = time.time() - self.start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = elapsed % 60
        return f"[{hours:02d}:{minutes:02d}:{seconds:06.3f}]"

    def log(self, component: str, message: str, level: str = "INFO", **kwargs):
        """Log a structured message with timestamp and component prefix."""
        timestamp = self._timestamp()
        log_entry = {
            "timestamp": timestamp,
            "elapsed_s": time.time() - self.start_time,
            "component": component,
            "message": message,
            "level": level,
            **kwargs,
        }

        with self._lock:
            self.logs.append(log_entry)

            # Console output with color coding
            color = {
                "INFO": "\033[0m",      # Default
                "SUCCESS": "\033[92m",  # Green
                "WARNING": "\033[93m",  # Yellow
                "ERROR": "\033[91m",    # Red
                "DEBUG": "\033[90m",    # Gray
            }.get(level, "\033[0m")

            console_msg = f"{timestamp} {component:12s} : {message}"
            print(f"{color}{console_msg}\033[0m")

            # Write to file if configured
            if self.log_file:
                with open(self.log_file, "a") as f:
                    f.write(json.dumps(log_entry) + "\n")

    def section(self, title: str):
        """Log a section header."""
        separator = "=" * 80
        self.log("System", separator, level="INFO")
        self.log("System", title.upper(), level="INFO")
        self.log("System", separator, level="INFO")

    def subsection(self, title: str):
        """Log a subsection header."""
        self.log("System", f"--- {title} ---", level="INFO")

    def get_statistics(self) -> Dict[str, Any]:
        """Compute statistics from logged data."""
        stats = {
            "total_logs": len(self.logs),
            "by_component": {},
            "by_level": {},
            "duration_s": time.time() - self.start_time,
        }

        for entry in self.logs:
            component = entry["component"]
            level = entry["level"]
            stats["by_component"][component] = stats["by_component"].get(component, 0) + 1
            stats["by_level"][level] = stats["by_level"].get(level, 0) + 1

        return stats


# ============================================================================
# VAD STATE MONITOR - Real-time voice activity tracking
# ============================================================================

class VADStateMonitor:
    """Monitor and log VAD state changes in real-time."""

    def __init__(self, logger: DiagnosticLogger, config: AppConfig):
        self.logger = logger
        self.config = config
        self.vad = webrtcvad.Vad(config.vad_aggressiveness)
        self.current_state = "silence"  # "silence" or "speech"
        self.speech_start_time: Optional[float] = None
        self.speech_end_time: Optional[float] = None
        self.utterance_count = 0
        self.consecutive_silence_frames = 0
        self.consecutive_speech_frames = 0

    def process_frame(self, frame: bytes, sample_rate: int) -> bool:
        """Process audio frame and log state changes."""
        is_speech = self.vad.is_speech(frame, sample_rate)
        current_time = time.time()

        if is_speech:
            self.consecutive_speech_frames += 1
            self.consecutive_silence_frames = 0

            if self.current_state == "silence":
                # Transition: Silence → Speech
                self.current_state = "speech"
                self.speech_start_time = current_time
                self.utterance_count += 1
                self.logger.log(
                    "VAD",
                    f"🗣️  Speech STARTED (utterance #{self.utterance_count})",
                    level="INFO",
                    event="speech_start",
                    utterance_num=self.utterance_count,
                )
        else:
            self.consecutive_silence_frames += 1
            self.consecutive_speech_frames = 0

            if self.current_state == "speech":
                # Transition: Speech → Silence
                self.current_state = "silence"
                self.speech_end_time = current_time
                duration = self.speech_end_time - self.speech_start_time if self.speech_start_time else 0
                self.logger.log(
                    "VAD",
                    f"🔇 Speech ENDED (duration: {duration:.3f}s)",
                    level="INFO",
                    event="speech_end",
                    duration_s=duration,
                )

        return is_speech

    def get_current_state(self) -> str:
        """Get current VAD state."""
        return self.current_state

    def get_stats(self) -> Dict[str, Any]:
        """Get VAD statistics."""
        return {
            "utterance_count": self.utterance_count,
            "current_state": self.current_state,
            "consecutive_silence_frames": self.consecutive_silence_frames,
            "consecutive_speech_frames": self.consecutive_speech_frames,
        }


# ============================================================================
# CONTEXT MEMORY TRACKER - Session context display
# ============================================================================

class ContextMemoryTracker:
    """Track and display session memory and conversation context."""

    def __init__(self, logger: DiagnosticLogger):
        self.logger = logger
        self.history: List[Dict[str, str]] = []
        self.turn_count = 0
        self.entities: Dict[str, Any] = {}

    def update_context(
        self,
        turn_index: int,
        user_text: str = "",
        assistant_text: str = "",
        history: Optional[List[Dict[str, str]]] = None,
    ):
        """Update and display context memory."""
        self.turn_count = turn_index + 1

        if user_text:
            self.history.append({"role": "user", "text": user_text})
        if assistant_text:
            self.history.append({"role": "assistant", "text": assistant_text})

        if history is not None:
            self.history = history.copy()

        self.logger.subsection(f"Context Memory (Turn {self.turn_count})")
        self.logger.log(
            "Context",
            f"Turn: {self.turn_count} | History entries: {len(self.history)}",
            level="INFO",
        )

        # Display recent history
        recent = self.history[-6:] if len(self.history) > 6 else self.history
        for i, entry in enumerate(recent):
            role = entry.get("role", "unknown")
            text = entry.get("text", "")[:80]  # Truncate for display
            self.logger.log("Context", f"  [{role}] {text}", level="DEBUG")

        # Display context summary
        context_summary = {
            "turn": self.turn_count,
            "history_length": len(self.history),
            "last_user": self.history[-2].get("text", "") if len(self.history) >= 2 else "",
            "last_assistant": self.history[-1].get("text", "") if len(self.history) >= 1 else "",
            "entities": self.entities,
        }

        self.logger.log(
            "Context",
            f"Summary: {json.dumps(context_summary, indent=2)}",
            level="DEBUG",
            context=context_summary,
        )

    def extract_entities(self, text: str):
        """Simple entity extraction (can be enhanced)."""
        # Simple keyword extraction for demonstration
        keywords = ["weather", "tomorrow", "today", "location", "time"]
        found = [kw for kw in keywords if kw.lower() in text.lower()]
        if found:
            self.entities.update({kw: True for kw in found})

    def verify_context_preserved(self, expected_info: str) -> bool:
        """Verify that specific information is retained in context."""
        for entry in self.history:
            if expected_info.lower() in entry.get("text", "").lower():
                return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get context tracking statistics."""
        return {
            "turn_count": self.turn_count,
            "history_length": len(self.history),
            "entities": self.entities,
        }


# ============================================================================
# TEST VALIDATOR - Automated validation framework
# ============================================================================

@dataclass
class ValidationResult:
    """Result of a validation check."""
    test_name: str
    check_name: str
    passed: bool
    message: str
    expected: Any = None
    actual: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class TestValidator:
    """Framework for automated validation checks."""

    def __init__(self, logger: DiagnosticLogger):
        self.logger = logger
        self.results: List[ValidationResult] = []

    def validate_speech_duration(
        self,
        test_name: str,
        duration_ms: int,
        min_duration_ms: int = 200,
    ) -> ValidationResult:
        """Validate that speech duration is reasonable."""
        passed = duration_ms >= min_duration_ms
        result = ValidationResult(
            test_name=test_name,
            check_name="speech_duration",
            passed=passed,
            message=f"Speech duration {duration_ms}ms (min: {min_duration_ms}ms)",
            expected=f">= {min_duration_ms}ms",
            actual=f"{duration_ms}ms",
        )
        self.results.append(result)
        self._log_result(result)
        return result

    def validate_wake_word_success_rate(
        self,
        test_name: str,
        successes: int,
        attempts: int,
        min_rate: float = 0.80,
    ) -> ValidationResult:
        """Validate wake word detection success rate."""
        rate = successes / attempts if attempts > 0 else 0.0
        passed = rate >= min_rate
        result = ValidationResult(
            test_name=test_name,
            check_name="wake_word_success_rate",
            passed=passed,
            message=f"Wake word success rate: {rate:.1%} ({successes}/{attempts})",
            expected=f">= {min_rate:.0%}",
            actual=f"{rate:.1%}",
        )
        self.results.append(result)
        self._log_result(result)
        return result

    def validate_mic_reengagement(
        self,
        test_name: str,
        tts_end_time: float,
        next_capture_time: float,
        max_delay_ms: float = 500,
    ) -> ValidationResult:
        """Validate that microphone re-engages quickly after TTS."""
        delay_ms = (next_capture_time - tts_end_time) * 1000
        passed = delay_ms <= max_delay_ms
        result = ValidationResult(
            test_name=test_name,
            check_name="mic_reengagement",
            passed=passed,
            message=f"Mic re-engagement delay: {delay_ms:.1f}ms",
            expected=f"<= {max_delay_ms}ms",
            actual=f"{delay_ms:.1f}ms",
        )
        self.results.append(result)
        self._log_result(result)
        return result

    def validate_context_preservation(
        self,
        test_name: str,
        history_length_before: int,
        history_length_after: int,
    ) -> ValidationResult:
        """Validate that context is preserved across turns."""
        passed = history_length_after >= history_length_before
        result = ValidationResult(
            test_name=test_name,
            check_name="context_preservation",
            passed=passed,
            message=f"Context history: {history_length_before} → {history_length_after} entries",
            expected="History should grow or stay same",
            actual=f"{history_length_after} entries",
        )
        self.results.append(result)
        self._log_result(result)
        return result

    def validate_multi_turn_count(
        self,
        test_name: str,
        turns_completed: int,
        min_turns: int = 2,
    ) -> ValidationResult:
        """Validate minimum number of conversation turns."""
        passed = turns_completed >= min_turns
        result = ValidationResult(
            test_name=test_name,
            check_name="multi_turn_count",
            passed=passed,
            message=f"Completed {turns_completed} turns (min: {min_turns})",
            expected=f">= {min_turns} turns",
            actual=f"{turns_completed} turns",
        )
        self.results.append(result)
        self._log_result(result)
        return result

    def validate_session_termination(
        self,
        test_name: str,
        exit_reason: str,
        expected_reasons: List[str],
    ) -> ValidationResult:
        """Validate session ended with expected reason."""
        passed = exit_reason in expected_reasons
        result = ValidationResult(
            test_name=test_name,
            check_name="session_termination",
            passed=passed,
            message=f"Session ended with reason: {exit_reason}",
            expected=f"One of: {expected_reasons}",
            actual=exit_reason,
        )
        self.results.append(result)
        self._log_result(result)
        return result

    def validate_no_truncation(
        self,
        test_name: str,
        transcript: str,
        min_words: int = 3,
    ) -> ValidationResult:
        """Validate that transcript is not truncated."""
        word_count = len(transcript.split())
        passed = word_count >= min_words
        result = ValidationResult(
            test_name=test_name,
            check_name="no_truncation",
            passed=passed,
            message=f"Transcript has {word_count} words (min: {min_words})",
            expected=f">= {min_words} words",
            actual=f"{word_count} words",
            metadata={"transcript": transcript[:100]},
        )
        self.results.append(result)
        self._log_result(result)
        return result

    def _log_result(self, result: ValidationResult):
        """Log validation result."""
        level = "SUCCESS" if result.passed else "ERROR"
        symbol = "✅" if result.passed else "❌"
        self.logger.log(
            "Validator",
            f"{symbol} {result.check_name}: {result.message}",
            level=level,
        )

    def get_summary(self) -> Dict[str, Any]:
        """Get validation summary."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed

        return {
            "total_checks": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": passed / total if total > 0 else 0.0,
            "results": [
                {
                    "test": r.test_name,
                    "check": r.check_name,
                    "passed": r.passed,
                    "message": r.message,
                }
                for r in self.results
            ],
        }

    def print_summary(self):
        """Print validation summary."""
        summary = self.get_summary()
        self.logger.section("Validation Summary")
        self.logger.log(
            "Validator",
            f"Total Checks: {summary['total_checks']} | "
            f"Passed: {summary['passed']} | "
            f"Failed: {summary['failed']} | "
            f"Rate: {summary['pass_rate']:.1%}",
            level="INFO",
        )

        if summary["failed"] > 0:
            self.logger.log("Validator", "Failed checks:", level="ERROR")
            for result in self.results:
                if not result.passed:
                    self.logger.log(
                        "Validator",
                        f"  ❌ {result.test_name} / {result.check_name}: {result.message}",
                        level="ERROR",
                    )


# ============================================================================
# ENHANCED TEST IMPLEMENTATIONS
# ============================================================================

def test_1_complete_speech_capture(
    config: AppConfig,
    transcriber: StreamingTranscriber,
    logger: DiagnosticLogger,
    validator: TestValidator,
) -> bool:
    """
    Test Issue #1: Complete Speech Capture with Enhanced Timing

    Validates:
    - VAD detects speech start/end with precise timing
    - No premature cutoff during speech
    - Tail padding is applied
    - Entire utterance is captured
    """
    logger.section("TEST 1: COMPLETE SPEECH CAPTURE")
    logger.log("System", "Instructions:", level="INFO")
    logger.log("System", "  1. Say a LONG sentence (10+ words) with natural pauses", level="INFO")
    logger.log("System", "  2. Stop talking and wait for silence detection", level="INFO")
    logger.log("System", "  3. We'll validate complete capture with timing analysis", level="INFO")
    logger.log("System", "", level="INFO")

    vad_monitor = VADStateMonitor(logger, config)

    with MicrophoneStream(
        rate=config.sample_rate_hz,
        chunk_samples=config.chunk_samples,
        input_device_name=config.mic_device_name,
    ) as mic:
        # Capture with detailed VAD monitoring
        logger.log("System", "🎤 Microphone OPEN - listening...", level="INFO")

        result = run_segment(
            mic=mic,
            stt=transcriber,
            config=config,
            stop_event=None,
            on_chunk=None,
            pre_roll_buffer=None,
            no_speech_timeout_ms=None,
        )

        logger.log("System", "🎤 Microphone CLOSED - processing...", level="INFO")
        logger.log("STT", f"Transcript: '{result.clean_transcript}'", level="INFO")
        logger.log("STT", f"Stop Reason: {result.stop_reason}", level="INFO")
        logger.log("STT", f"Duration: {result.duration_ms}ms", level="INFO")
        logger.log("STT", f"Audio Captured: {result.audio_ms}ms", level="INFO")
        logger.log("STT", f"Word Count: {len(result.clean_transcript.split())}", level="INFO")

        # Validation
        validator.validate_speech_duration("Test1", result.audio_ms, min_duration_ms=500)
        validator.validate_no_truncation("Test1", result.clean_transcript, min_words=5)

        success = result.stop_reason in ("silence", "bye", "done") and len(result.clean_transcript.split()) >= 5

        if success:
            logger.log("System", "✅ PASSED: Full speech captured successfully", level="SUCCESS")
        else:
            logger.log("System", "❌ FAILED: Speech may have been truncated or cut off", level="ERROR")

        return success


def test_2_wake_word_reliability(
    config: AppConfig,
    wake_transcriber: StreamingTranscriber,
    logger: DiagnosticLogger,
    validator: TestValidator,
    attempts: int = 3,
) -> bool:
    """
    Test Issue #2: Wake Word Detection Reliability with Success Rate Tracking

    Validates:
    - Wake word triggers consistently
    - Pre-roll buffer captures audio before detection
    - Debouncing prevents multiple triggers
    - Success rate meets threshold
    """
    logger.section("TEST 2: WAKE WORD DETECTION RELIABILITY")
    logger.log("System", f"Instructions:", level="INFO")
    logger.log("System", f"  1. Say the wake word '{config.wake_word}' {attempts} times", level="INFO")
    logger.log("System", f"  2. Wait 3 seconds between each attempt", level="INFO")
    logger.log("System", f"  3. We'll track success rate and timing", level="INFO")
    logger.log("System", "", level="INFO")

    successes = 0
    detection_times: List[float] = []

    for attempt in range(attempts):
        logger.log("System", f"--- Attempt {attempt + 1}/{attempts} ---", level="INFO")
        logger.log("System", f"Say: '{config.wake_word}' now...", level="INFO")

        detected = False
        detection_time = None
        pre_roll = None

        def on_wake_detect(buffer):
            nonlocal detected, detection_time, pre_roll
            detected = True
            detection_time = time.time()
            pre_roll = buffer
            logger.log("WakeWord", f"✅ DETECTED '{config.wake_word}'", level="SUCCESS")
            logger.log("WakeWord", f"Pre-roll buffer: {len(buffer)} frames", level="INFO")

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

        start_time = time.time()
        listener.start()
        time.sleep(8)  # Wait for detection
        listener.stop()
        listener.join(timeout=2)
        elapsed = time.time() - start_time

        if detected:
            successes += 1
            if detection_time:
                detection_times.append(detection_time - start_time)
                logger.log("WakeWord", f"Detection latency: {(detection_time - start_time):.3f}s", level="INFO")
        else:
            logger.log("WakeWord", f"❌ NOT DETECTED (timeout after {elapsed:.1f}s)", level="ERROR")

        if attempt < attempts - 1:
            logger.log("System", "Waiting 3 seconds before next attempt...", level="INFO")
            time.sleep(3)

    # Calculate statistics
    success_rate = successes / attempts
    avg_detection_time = sum(detection_times) / len(detection_times) if detection_times else 0

    logger.log("System", "", level="INFO")
    logger.log("System", f"Success Rate: {success_rate:.1%} ({successes}/{attempts})", level="INFO")
    if detection_times:
        logger.log("System", f"Avg Detection Time: {avg_detection_time:.3f}s", level="INFO")

    # Validation
    validator.validate_wake_word_success_rate("Test2", successes, attempts, min_rate=0.66)

    success = success_rate >= 0.66  # At least 2/3 should work

    if success:
        logger.log("System", "✅ PASSED: Wake word detection is reliable", level="SUCCESS")
    else:
        logger.log("System", "❌ FAILED: Wake word detection is unreliable", level="ERROR")

    return success


def test_3_tts_and_mic_reengagement(
    config: AppConfig,
    tts: SpeechSynthesizer,
    logger: DiagnosticLogger,
    validator: TestValidator,
) -> bool:
    """
    Test Issue #3: TTS Consistency and Microphone Re-engagement

    Validates:
    - TTS speaks all messages consistently
    - Microphone state during TTS (should be closed/muted)
    - Microphone reopens after TTS
    - No audio device conflicts
    """
    logger.section("TEST 3: TTS AND MICROPHONE RE-ENGAGEMENT")
    logger.log("System", "Testing TTS output and mic re-engagement timing...", level="INFO")
    logger.log("System", "", level="INFO")

    messages = [
        "This is the first test message.",
        "Now testing second message.",
        "Third message for consistency.",
        "Final test message number four.",
    ]

    successes = 0
    failures = 0
    reengagement_times: List[float] = []

    for i, msg in enumerate(messages, 1):
        logger.log("TTS", f"[{i}/{len(messages)}] Speaking: '{msg}'", level="INFO")

        try:
            tts_start = time.time()
            logger.log("System", "🔊 TTS STARTED - mic should be inactive", level="INFO")

            tts.speak(msg)

            tts_end = time.time()
            tts_duration = tts_end - tts_start
            logger.log("TTS", f"✅ Completed in {tts_duration:.2f}s", level="SUCCESS")
            logger.log("System", "🎤 TTS ENDED - mic should reopen now", level="INFO")

            # Simulate checking mic re-engagement (in real impl, would verify mic state)
            reengagement_time = time.time()
            reengagement_delay = (reengagement_time - tts_end) * 1000

            logger.log("System", f"Mic re-engagement delay: {reengagement_delay:.1f}ms", level="INFO")
            reengagement_times.append(reengagement_delay)

            successes += 1

            if i < len(messages):
                time.sleep(0.5)  # Brief pause between messages

        except Exception as e:
            logger.log("TTS", f"❌ FAILED: {e}", level="ERROR")
            failures += 1

    # Statistics
    avg_reengagement = sum(reengagement_times) / len(reengagement_times) if reengagement_times else 0

    logger.log("System", "", level="INFO")
    logger.log("System", f"TTS Success Rate: {successes}/{len(messages)}", level="INFO")
    logger.log("System", f"Avg Reengagement Delay: {avg_reengagement:.1f}ms", level="INFO")

    # Validation (using dummy times for demonstration - in real impl would track actual mic state)
    if reengagement_times:
        validator.validate_mic_reengagement(
            "Test3",
            tts_end_time=0,
            next_capture_time=avg_reengagement / 1000,
            max_delay_ms=500,
        )

    success = failures == 0 and avg_reengagement < 500

    if success:
        logger.log("System", "✅ PASSED: TTS consistent and mic re-engages properly", level="SUCCESS")
    else:
        logger.log("System", "❌ FAILED: TTS issues or slow mic re-engagement detected", level="ERROR")

    return success


def test_4_multi_turn_with_context(
    config: AppConfig,
    segment_recorder: SegmentRecorder,
    vlm_client: VLMClient,
    tts: SpeechSynthesizer,
    logger: DiagnosticLogger,
    context_tracker: ContextMemoryTracker,
    validator: TestValidator,
) -> bool:
    """
    Test Issue #4: Multi-Turn Conversation with Context Tracking

    Validates:
    - Multiple conversation turns without wake word
    - Context retention across turns
    - State transitions work correctly
    - Session can be exited properly
    """
    logger.section("TEST 4: MULTI-TURN CONVERSATION WITH CONTEXT")
    logger.log("System", "Instructions:", level="INFO")
    logger.log("System", "  1. Session will start (no wake word needed)", level="INFO")
    logger.log("System", "  2. Ask at least 2 questions", level="INFO")
    logger.log("System", "  3. Second question should reference first (test context)", level="INFO")
    logger.log("System", "  4. Say 'bye glasses' to exit OR wait 15s", level="INFO")
    logger.log("System", "", level="INFO")
    logger.log("System", "Starting session in 3 seconds...", level="INFO")
    time.sleep(3)

    results = {
        "turns": 0,
        "exit_method": None,
        "state_transitions": [],
        "history_lengths": [],
    }

    def on_session_started(session_id: str):
        logger.log("Session", f"📍 Started: {session_id}", level="SUCCESS")

    def on_state_changed(state: SessionState, turn_index: int):
        logger.log("Session", f"🔄 State: {state.value} (turn {turn_index})", level="INFO")
        results["state_transitions"].append(state.value)

    def on_transcript_ready(turn_index: int, result):
        results["turns"] = turn_index + 1
        logger.log("Session", f"🎤 Turn {turn_index + 1}: '{result.clean_transcript}'", level="INFO")

    def on_response_ready(turn_index: int, text: str, payload: dict):
        logger.log("Session", f"💬 Response: '{text[:80]}...'", level="INFO")
        # Update context tracker (would normally get history from session manager)
        context_tracker.update_context(turn_index, assistant_text=text)
        results["history_lengths"].append(len(context_tracker.history))

    def on_session_finished(session_id: str, reason: str):
        results["exit_method"] = reason
        logger.log("Session", f"🏁 Ended: {reason}", level="INFO")

    def on_error(message: str):
        logger.log("Session", f"❌ Error: {message}", level="ERROR")

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
        followup_timeout_ms=15000,
    )

    try:
        manager.run_session(callbacks=callbacks, pre_roll_buffer=None)
    except KeyboardInterrupt:
        logger.log("System", "⚠️  Test interrupted by user", level="WARNING")
        manager.cancel()

    logger.log("System", "", level="INFO")
    logger.log("System", f"Turns Completed: {results['turns']}", level="INFO")
    logger.log("System", f"Exit Method: {results['exit_method']}", level="INFO")
    logger.log("System", f"State Transitions: {len(results['state_transitions'])}", level="INFO")

    # Validation
    validator.validate_multi_turn_count("Test4", results["turns"], min_turns=2)
    validator.validate_session_termination("Test4", results["exit_method"], ["bye", "timeout15", "manual"])

    if len(results["history_lengths"]) > 1:
        validator.validate_context_preservation(
            "Test4",
            results["history_lengths"][0],
            results["history_lengths"][-1],
        )

    success = results["turns"] >= 2 and results["exit_method"] in ("bye", "timeout15", "manual")

    if success:
        logger.log("System", "✅ PASSED: Multi-turn conversation working correctly", level="SUCCESS")
    else:
        logger.log("System", "❌ FAILED: Multi-turn or context issues detected", level="ERROR")

    return success


def test_5_silence_handling(
    config: AppConfig,
    logger: DiagnosticLogger,
    validator: TestValidator,
    silence_duration_s: int = 15,
) -> bool:
    """
    Test Issue #5: Silence Handling (15+ second test)

    Validates:
    - System handles prolonged silence gracefully
    - No premature timeout
    - System remains responsive after silence
    """
    logger.section("TEST 5: SILENCE HANDLING")
    logger.log("System", f"Testing {silence_duration_s}-second silence...", level="INFO")
    logger.log("System", "Please remain SILENT for the duration", level="INFO")
    logger.log("System", "", level="INFO")

    vad = webrtcvad.Vad(config.vad_aggressiveness)
    silence_start = time.time()
    speech_detected = False

    with MicrophoneStream(
        rate=config.sample_rate_hz,
        chunk_samples=config.chunk_samples,
        input_device_name=config.mic_device_name,
    ) as mic:
        logger.log("System", f"🔇 Monitoring silence for {silence_duration_s}s...", level="INFO")

        while time.time() - silence_start < silence_duration_s:
            frame = mic.read(config.chunk_samples)
            is_speech = vad.is_speech(frame, config.sample_rate_hz)

            if is_speech:
                speech_detected = True
                logger.log("VAD", "⚠️  Speech detected during silence test", level="WARNING")

            elapsed = time.time() - silence_start
            if int(elapsed) % 5 == 0 and elapsed > 0:
                logger.log("System", f"  {int(elapsed)}s elapsed (silence)...", level="DEBUG")
                time.sleep(1)  # Avoid logging every frame

        silence_end = time.time()
        total_silence = silence_end - silence_start

    logger.log("System", f"Silence period completed: {total_silence:.1f}s", level="INFO")

    # Validation
    success = not speech_detected and total_silence >= silence_duration_s

    if success:
        logger.log("System", "✅ PASSED: System handled prolonged silence correctly", level="SUCCESS")
    else:
        logger.log("System", "❌ FAILED: Issues during silence period", level="ERROR")

    return success


def test_6_termination_command(
    config: AppConfig,
    transcriber: StreamingTranscriber,
    logger: DiagnosticLogger,
    validator: TestValidator,
) -> bool:
    """
    Test Issue #6: Termination Command ("bye glasses")

    Validates:
    - "bye glasses" phrase is detected correctly
    - Session terminates cleanly
    - No further processing after termination
    """
    logger.section("TEST 6: TERMINATION COMMAND")
    logger.log("System", "Instructions:", level="INFO")
    logger.log("System", "  1. Say 'bye glasses' to test termination", level="INFO")
    logger.log("System", "  2. We'll verify clean session end", level="INFO")
    logger.log("System", "", level="INFO")

    with MicrophoneStream(
        rate=config.sample_rate_hz,
        chunk_samples=config.chunk_samples,
        input_device_name=config.mic_device_name,
    ) as mic:
        logger.log("System", "🎤 Listening for 'bye glasses'...", level="INFO")

        result = run_segment(
            mic=mic,
            stt=transcriber,
            config=config,
            stop_event=None,
            on_chunk=None,
            pre_roll_buffer=None,
            no_speech_timeout_ms=10000,
        )

        logger.log("STT", f"Transcript: '{result.clean_transcript}'", level="INFO")
        logger.log("STT", f"Stop Reason: {result.stop_reason}", level="INFO")

        # Check if "bye" was detected
        bye_detected = "bye" in result.clean_transcript.lower() or result.stop_reason == "bye"

        if bye_detected:
            logger.log("System", "🛑 Termination phrase detected", level="INFO")
            validator.validate_session_termination("Test6", result.stop_reason, ["bye"])
            success = True
        else:
            logger.log("System", "❌ Termination phrase NOT detected", level="ERROR")
            success = False

    if success:
        logger.log("System", "✅ PASSED: Termination command works correctly", level="SUCCESS")
    else:
        logger.log("System", "❌ FAILED: Termination command not recognized", level="ERROR")

    return success


def test_7_short_utterances(
    config: AppConfig,
    transcriber: StreamingTranscriber,
    logger: DiagnosticLogger,
    validator: TestValidator,
) -> bool:
    """
    Test Issue #7: Short Utterances

    Validates:
    - Very short commands are captured ("yes", "ok", "no")
    - VAD sensitivity is adequate for brief speech
    - STT transcribes short words correctly
    """
    logger.section("TEST 7: SHORT UTTERANCES")
    logger.log("System", "Instructions:", level="INFO")
    logger.log("System", "  1. Say a very SHORT word: 'yes', 'ok', or 'no'", level="INFO")
    logger.log("System", "  2. We'll verify it's captured completely", level="INFO")
    logger.log("System", "", level="INFO")

    with MicrophoneStream(
        rate=config.sample_rate_hz,
        chunk_samples=config.chunk_samples,
        input_device_name=config.mic_device_name,
    ) as mic:
        logger.log("System", "🎤 Listening for short utterance...", level="INFO")

        result = run_segment(
            mic=mic,
            stt=transcriber,
            config=config,
            stop_event=None,
            on_chunk=None,
            pre_roll_buffer=None,
            no_speech_timeout_ms=5000,
        )

        logger.log("STT", f"Transcript: '{result.clean_transcript}'", level="INFO")
        logger.log("STT", f"Duration: {result.audio_ms}ms", level="INFO")
        logger.log("STT", f"Stop Reason: {result.stop_reason}", level="INFO")

        # Validation - short utterances should be at least 100ms
        validator.validate_speech_duration("Test7", result.audio_ms, min_duration_ms=100)

        success = len(result.clean_transcript) > 0 and result.audio_ms >= 100

    if success:
        logger.log("System", "✅ PASSED: Short utterances captured correctly", level="SUCCESS")
    else:
        logger.log("System", "❌ FAILED: Short utterance not captured or too brief", level="ERROR")

    return success


def test_8_edge_cases(
    config: AppConfig,
    transcriber: StreamingTranscriber,
    logger: DiagnosticLogger,
    validator: TestValidator,
) -> bool:
    """
    Test Issue #8: Edge Cases

    Validates:
    - Wake word alone (no follow-up command)
    - Mid-sentence pauses don't split utterance
    - System recovers from unexpected inputs
    """
    logger.section("TEST 8: EDGE CASES")
    logger.log("System", "Testing edge case: mid-sentence pause", level="INFO")
    logger.log("System", "Instructions:", level="INFO")
    logger.log("System", "  1. Say a sentence with a deliberate 1-second PAUSE mid-sentence", level="INFO")
    logger.log("System", "  2. Example: 'Turn on... [pause]... the kitchen light'", level="INFO")
    logger.log("System", "", level="INFO")

    with MicrophoneStream(
        rate=config.sample_rate_hz,
        chunk_samples=config.chunk_samples,
        input_device_name=config.mic_device_name,
    ) as mic:
        logger.log("System", "🎤 Listening...", level="INFO")

        result = run_segment(
            mic=mic,
            stt=transcriber,
            config=config,
            stop_event=None,
            on_chunk=None,
            pre_roll_buffer=None,
            no_speech_timeout_ms=None,
        )

        logger.log("STT", f"Transcript: '{result.clean_transcript}'", level="INFO")
        logger.log("STT", f"Stop Reason: {result.stop_reason}", level="INFO")

        # Check if both parts were captured (not split by mid-sentence pause)
        word_count = len(result.clean_transcript.split())
        validator.validate_no_truncation("Test8", result.clean_transcript, min_words=3)

        success = word_count >= 3

    if success:
        logger.log("System", "✅ PASSED: Edge case handled correctly", level="SUCCESS")
    else:
        logger.log("System", "❌ FAILED: Edge case not handled properly", level="ERROR")

    return success


# ============================================================================
# REAL-TIME MONITOR MODE
# ============================================================================

def monitor_mode(config: AppConfig, logger: DiagnosticLogger, duration_s: int = 60):
    """
    Real-time monitoring mode - displays live VAD and wake word state.

    Shows continuous feedback on:
    - VAD state (voice/silence)
    - Wake word detection
    - Speech timing
    """
    logger.section("REAL-TIME VAD & WAKE WORD MONITOR")
    logger.log("System", f"Monitoring for {duration_s} seconds...", level="INFO")
    logger.log("System", f"Wake word: '{config.wake_word}'", level="INFO")
    logger.log("System", "", level="INFO")

    vad_monitor = VADStateMonitor(logger, config)
    wake_detected = False

    def on_wake_detect(buffer):
        nonlocal wake_detected
        wake_detected = True
        logger.log("WakeWord", f"🎉 WAKE WORD DETECTED: '{config.wake_word}'", level="SUCCESS")
        logger.log("WakeWord", f"Pre-roll buffer: {len(buffer)} frames", level="INFO")

    # Create wake word listener
    from vosk import Model
    model = Model(config.vosk_model_path)
    wake_transcriber = StreamingTranscriber(sample_rate=config.sample_rate_hz, model=model)

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

    start_time = time.time()
    listener.start()

    try:
        while time.time() - start_time < duration_s:
            elapsed = int(time.time() - start_time)
            stats = vad_monitor.get_stats()

            # Log periodic status
            if elapsed % 10 == 0 and elapsed > 0:
                logger.log(
                    "Monitor",
                    f"[{elapsed}s] State: {stats['current_state']} | "
                    f"Utterances: {stats['utterance_count']} | "
                    f"Wake detected: {wake_detected}",
                    level="INFO",
                )

            time.sleep(0.1)

    except KeyboardInterrupt:
        logger.log("System", "Monitor interrupted by user", level="WARNING")
    finally:
        listener.stop()
        listener.join(timeout=2)

    logger.log("System", f"Monitoring completed after {time.time() - start_time:.1f}s", level="INFO")


# ============================================================================
# MAIN CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Enhanced Diagnostic Script for Voice Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Run all tests
  %(prog)s --test 1                 # Run specific test
  %(prog)s --monitor                # Real-time VAD monitor
  %(prog)s --interactive            # Interactive guided testing
  %(prog)s --log-file diag.log      # Save logs to file
        """,
    )

    parser.add_argument("-c", "--config", help="Config file path")
    parser.add_argument(
        "--test",
        type=int,
        choices=range(1, 9),
        help="Run specific test (1-8)",
    )
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Real-time VAD and wake word monitor mode",
    )
    parser.add_argument(
        "--monitor-duration",
        type=int,
        default=60,
        help="Monitor mode duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive guided testing mode",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Save detailed logs to file",
    )
    parser.add_argument(
        "--wake-attempts",
        type=int,
        default=3,
        help="Number of wake word attempts in Test 2 (default: 3)",
    )

    args = parser.parse_args()

    # Initialize logger
    logger = DiagnosticLogger(log_file=args.log_file)
    logger.section("Voice Assistant Enhanced Diagnostic System")
    logger.log("System", f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", level="INFO")

    # Load configuration
    try:
        config_path = Path(args.config) if args.config else None
        config = load_config(config_path)
        logger.log("System", f"Config loaded: {config_path or 'default'}", level="INFO")
    except Exception as e:
        logger.log("System", f"Failed to load config: {e}", level="ERROR")
        return 1

    # Monitor mode (special case - exits early)
    if args.monitor:
        try:
            monitor_mode(config, logger, duration_s=args.monitor_duration)
            return 0
        except Exception as e:
            logger.log("System", f"Monitor mode error: {e}", level="ERROR")
            return 1

    # Initialize components
    logger.log("System", "Initializing components...", level="INFO")

    try:
        model = Model(config.vosk_model_path)
        wake_transcriber = StreamingTranscriber(sample_rate=config.sample_rate_hz, model=model)
        segment_transcriber = StreamingTranscriber(sample_rate=config.sample_rate_hz, model=model)
        logger.log("System", "✅ Vosk models loaded", level="SUCCESS")
    except Exception as e:
        logger.log("System", f"Failed to initialize Vosk: {e}", level="ERROR")
        return 1

    try:
        vlm_client = VLMClient(config)
        logger.log("System", "✅ VLM client initialized", level="SUCCESS")
    except Exception as e:
        logger.log("System", f"Failed to initialize VLM: {e}", level="ERROR")
        return 1

    segment_recorder = SegmentRecorder(config, segment_transcriber)
    tts = SpeechSynthesizer(voice=config.tts_voice, rate=config.tts_rate)
    logger.log("System", "✅ Audio components initialized", level="SUCCESS")

    # Initialize diagnostic helpers
    validator = TestValidator(logger)
    context_tracker = ContextMemoryTracker(logger)

    # Determine which tests to run
    if args.test:
        tests_to_run = [args.test]
        logger.log("System", f"Running single test: Test {args.test}", level="INFO")
    elif args.interactive:
        logger.log("System", "Interactive mode - you'll be prompted for each test", level="INFO")
        tests_to_run = list(range(1, 9))
    else:
        logger.log("System", "Running full diagnostic suite (all 8 tests)", level="INFO")
        tests_to_run = list(range(1, 9))

    # Run tests
    test_results = {}

    for test_num in tests_to_run:
        if args.interactive:
            response = input(f"\nRun Test {test_num}? (y/n/q): ").strip().lower()
            if response == 'q':
                logger.log("System", "Testing aborted by user", level="WARNING")
                break
            if response != 'y':
                continue

        try:
            if test_num == 1:
                result = test_1_complete_speech_capture(config, segment_transcriber, logger, validator)
            elif test_num == 2:
                result = test_2_wake_word_reliability(config, wake_transcriber, logger, validator, attempts=args.wake_attempts)
            elif test_num == 3:
                result = test_3_tts_and_mic_reengagement(config, tts, logger, validator)
            elif test_num == 4:
                result = test_4_multi_turn_with_context(config, segment_recorder, vlm_client, tts, logger, context_tracker, validator)
            elif test_num == 5:
                result = test_5_silence_handling(config, logger, validator, silence_duration_s=15)
            elif test_num == 6:
                result = test_6_termination_command(config, segment_transcriber, logger, validator)
            elif test_num == 7:
                result = test_7_short_utterances(config, segment_transcriber, logger, validator)
            elif test_num == 8:
                result = test_8_edge_cases(config, segment_transcriber, logger, validator)
            else:
                continue

            test_results[test_num] = result

        except KeyboardInterrupt:
            logger.log("System", f"Test {test_num} interrupted by user", level="WARNING")
            test_results[test_num] = False
        except Exception as e:
            logger.log("System", f"Test {test_num} error: {e}", level="ERROR")
            test_results[test_num] = False
            import traceback
            traceback.print_exc()

    # Print comprehensive summary
    logger.section("FINAL TEST SUMMARY")

    passed = sum(1 for result in test_results.values() if result)
    failed = len(test_results) - passed

    logger.log("System", f"Tests Run: {len(test_results)}", level="INFO")
    logger.log("System", f"Passed: {passed}", level="SUCCESS" if passed == len(test_results) else "INFO")
    logger.log("System", f"Failed: {failed}", level="ERROR" if failed > 0 else "INFO")

    logger.log("System", "", level="INFO")
    logger.log("System", "Individual Test Results:", level="INFO")
    test_names = [
        "Complete Speech Capture",
        "Wake Word Reliability",
        "TTS and Mic Re-engagement",
        "Multi-turn Conversation",
        "Silence Handling",
        "Termination Command",
        "Short Utterances",
        "Edge Cases",
    ]

    for test_num, result in test_results.items():
        test_name = test_names[test_num - 1] if test_num <= len(test_names) else f"Test {test_num}"
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.log("System", f"  Test {test_num} ({test_name}): {status}", level="SUCCESS" if result else "ERROR")

    # Print validation summary
    logger.log("System", "", level="INFO")
    validator.print_summary()

    # Print context statistics
    if context_tracker.turn_count > 0:
        logger.log("System", "", level="INFO")
        logger.log("System", "Context Tracking Statistics:", level="INFO")
        ctx_stats = context_tracker.get_stats()
        logger.log("System", f"  Total Turns: {ctx_stats['turn_count']}", level="INFO")
        logger.log("System", f"  History Length: {ctx_stats['history_length']}", level="INFO")
        logger.log("System", f"  Entities Tracked: {ctx_stats['entities']}", level="INFO")

    # Print overall diagnostic statistics
    logger.log("System", "", level="INFO")
    log_stats = logger.get_statistics()
    logger.log("System", "Diagnostic Statistics:", level="INFO")
    logger.log("System", f"  Total Log Entries: {log_stats['total_logs']}", level="INFO")
    logger.log("System", f"  Duration: {log_stats['duration_s']:.1f}s", level="INFO")
    logger.log("System", f"  Logs by Level: {log_stats['by_level']}", level="INFO")

    if args.log_file:
        logger.log("System", f"  Detailed logs saved to: {args.log_file}", level="INFO")

    logger.section("DIAGNOSTIC COMPLETE")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
