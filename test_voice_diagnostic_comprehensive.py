#!/usr/bin/env python3
"""
Comprehensive Voice Assistant Diagnostic Tool

This diagnostic script tests the entire voice assistant pipeline to identify and log:
1. Unreliable full-utterance capture (clipped audio at start/end)
2. Inconsistent wake word detection
3. Failure to continue listening after first response
4. Multi-turn conversation state and timeout issues

The script provides detailed timestamped logs for each stage of the pipeline:
- VAD (Voice Activity Detection) with pre-roll and hangover
- STT (Speech-to-Text) transcription accuracy
- Wake word detection reliability
- TTS (Text-to-Speech) response and microphone re-engagement
- Conversation history retention
- Timeout and exit phrase handling

Usage:
    python test_voice_diagnostic_comprehensive.py                    # Run all tests
    python test_voice_diagnostic_comprehensive.py --test wake        # Test wake word only
    python test_voice_diagnostic_comprehensive.py --test multiturn   # Test multi-turn
    python test_voice_diagnostic_comprehensive.py --test timeout     # Test timeout
    python test_voice_diagnostic_comprehensive.py --live             # Use live microphone
    python test_voice_diagnostic_comprehensive.py --verbose          # Extra debug output
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time
import wave
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import webrtcvad
from vosk import Model, KaldiRecognizer

# Import existing app components
try:
    from app.audio.mic import MicrophoneStream
    from app.audio.stt import StreamingTranscriber
    from app.audio.tts import SpeechSynthesizer
    from app.audio.vad import VoiceActivityDetector, SilenceTracker
    from app.util.config import AppConfig, load_config
except ImportError as e:
    print(f"Error importing app modules: {e}")
    print("Make sure you're running this from the project root directory.")
    sys.exit(1)


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class DiagnosticConfig:
    """Configuration for diagnostic tests."""
    # Wake word settings
    wake_word: str = "hey glasses"
    exit_phrase: str = "bye glasses"
    require_wake_word: bool = True
    
    # VAD parameters
    vad_mode: int = 1  # 0-3, higher = more aggressive
    frame_duration_ms: int = 30  # 10, 20, or 30 ms
    pre_roll_frames: int = 3  # ~90ms pre-roll at 30ms frames
    hangover_frames: int = 10  # ~300ms hangover at 30ms frames
    
    # Timeout settings
    followup_timeout_sec: int = 15
    
    # Audio settings
    sample_rate: int = 16000
    
    # Test scenarios
    use_microphone: bool = False
    mic_device_index: Optional[int] = None
    
    # Vosk model
    model_path: str = "models/vosk-model-en-us-0.22"
    
    # TTS settings
    enable_tts_output: bool = False  # Set to True to actually speak
    
    # Logging
    verbose: bool = False
    log_file: Optional[Path] = None


# ============================================================================
# DIAGNOSTIC LOGGER
# ============================================================================

class DiagnosticLogger:
    """Structured logger with millisecond-precision timestamps."""
    
    def __init__(self, log_file: Optional[Path] = None, verbose: bool = False):
        self.start_time = time.time()
        self.log_file = log_file
        self.verbose = verbose
        self.logs: List[Dict[str, Any]] = []
        
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
        """Log a structured message."""
        timestamp = self._timestamp()
        log_entry = {
            "timestamp": timestamp,
            "elapsed_s": time.time() - self.start_time,
            "component": component,
            "message": message,
            "level": level,
            **kwargs,
        }
        
        self.logs.append(log_entry)
        
        # Console output with color
        color = {
            "INFO": "\033[0m",
            "SUCCESS": "\033[92m",
            "WARNING": "\033[93m",
            "ERROR": "\033[91m",
            "DEBUG": "\033[90m",
        }.get(level, "\033[0m")
        
        reset = "\033[0m"
        
        if level == "DEBUG" and not self.verbose:
            return
        
        print(f"{color}{timestamp} [{component}] {message}{reset}")
        
        # Write to file if configured
        if self.log_file:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
    
    def save_summary(self, output_path: Path):
        """Save all logs to a JSON file."""
        with open(output_path, "w") as f:
            json.dump(self.logs, f, indent=2)
        print(f"\n✓ Diagnostic logs saved to: {output_path}")


# ============================================================================
# TEST SCENARIO DEFINITIONS
# ============================================================================

@dataclass
class TestScenario:
    """Definition of a test scenario."""
    name: str
    description: str
    audio_file: Optional[str] = None
    expect_wake: bool = False
    expect_exit: bool = False
    is_followup: bool = False
    expected_duration_s: Optional[float] = None


# Predefined test scenarios
TEST_SCENARIOS = {
    "wake": [
        TestScenario(
            name="wake_word_present",
            description="Query with wake word 'hey glasses'",
            expect_wake=True,
        ),
    ],
    "nowake": [
        TestScenario(
            name="no_wake_word",
            description="Query without wake word (should be ignored)",
            expect_wake=False,
        ),
    ],
    "multiturn": [
        TestScenario(
            name="multiturn_initial",
            description="Multi-turn: Initial query with wake word",
            expect_wake=True,
        ),
        TestScenario(
            name="multiturn_followup",
            description="Multi-turn: Follow-up without wake word",
            expect_wake=False,
            is_followup=True,
        ),
    ],
    "timeout": [
        TestScenario(
            name="timeout_test",
            description="Test 15-second timeout (stay silent)",
            expect_wake=True,
        ),
    ],
    "exit": [
        TestScenario(
            name="exit_phrase",
            description="Exit with 'bye glasses'",
            expect_wake=True,
            expect_exit=True,
        ),
    ],
}


# ============================================================================
# VAD AUDIO COLLECTOR
# ============================================================================

class VADAudioCollector:
    """Collects speech segments using VAD with pre-roll and hangover."""
    
    def __init__(
        self,
        vad: webrtcvad.Vad,
        sample_rate: int,
        frame_bytes: int,
        pre_roll_frames: int,
        hangover_frames: int,
        logger: DiagnosticLogger,
    ):
        self.vad = vad
        self.sample_rate = sample_rate
        self.frame_bytes = frame_bytes
        self.pre_roll_frames = pre_roll_frames
        self.hangover_frames = hangover_frames
        self.logger = logger
    
    def collect_speech_segments(self, pcm_data: bytes) -> List[Tuple[bytes, float]]:
        """
        Collect speech segments from PCM data using VAD.
        
        Returns:
            List of (speech_bytes, duration_seconds) tuples
        """
        frames = [
            pcm_data[i:i+self.frame_bytes]
            for i in range(0, len(pcm_data), self.frame_bytes)
        ]
        
        speech_segments = []
        ring_buffer = collections.deque(maxlen=self.pre_roll_frames)
        audio_buffer = bytearray()
        in_speech = False
        speech_start_frame = 0
        
        for idx, frame in enumerate(frames):
            # Pad last frame if needed
            if len(frame) < self.frame_bytes:
                frame = frame + b'\x00' * (self.frame_bytes - len(frame))
            
            is_speech = self.vad.is_speech(frame, self.sample_rate)
            
            if is_speech:
                if not in_speech:
                    # Speech just started
                    in_speech = True
                    speech_start_frame = max(0, idx - self.pre_roll_frames)
                    
                    # Prepend pre-roll frames
                    for buf_frame in list(ring_buffer):
                        audio_buffer.extend(buf_frame)
                    
                    self.logger.log(
                        "VAD",
                        f"Speech started at frame {idx} (including {len(ring_buffer)} pre-roll frames)",
                        level="DEBUG",
                        frame_index=idx,
                        pre_roll_frames=len(ring_buffer),
                    )
                    
                    audio_buffer.extend(frame)
                else:
                    audio_buffer.extend(frame)
                
                # Reset ring buffer while in speech
                ring_buffer.clear()
            else:
                if in_speech:
                    # Accumulate hangover frames
                    ring_buffer.append(frame)
                    
                    if len(ring_buffer) >= self.hangover_frames:
                        # Speech ended after hangover
                        in_speech = False
                        
                        # Add hangover frames to buffer
                        for buf_frame in list(ring_buffer):
                            audio_buffer.extend(buf_frame)
                        
                        # Calculate duration
                        bytes_per_sec = self.sample_rate * 2
                        duration = len(audio_buffer) / bytes_per_sec
                        
                        speech_segments.append((bytes(audio_buffer), duration))
                        
                        self.logger.log(
                            "VAD",
                            f"Speech ended at frame {idx}; segment duration {duration:.2f}s",
                            level="DEBUG",
                            frame_index=idx,
                            duration_s=duration,
                        )
                        
                        # Reset buffers
                        audio_buffer = bytearray()
                        ring_buffer.clear()
                else:
                    # Not in speech, accumulate pre-roll
                    ring_buffer.append(frame)
        
        # Flush remaining buffer if still in speech
        if in_speech and len(audio_buffer) > 0:
            bytes_per_sec = self.sample_rate * 2
            duration = len(audio_buffer) / bytes_per_sec
            speech_segments.append((bytes(audio_buffer), duration))
            
            self.logger.log(
                "VAD",
                f"Audio ended while in speech; last segment duration {duration:.2f}s",
                level="DEBUG",
                duration_s=duration,
            )
        
        return speech_segments


# ============================================================================
# SPEECH TRANSCRIBER
# ============================================================================

class DiagnosticTranscriber:
    """Wrapper around Vosk for transcription with logging."""
    
    def __init__(self, model: Model, sample_rate: int, logger: DiagnosticLogger):
        self.model = model
        self.sample_rate = sample_rate
        self.logger = logger
    
    def transcribe(self, speech_bytes: bytes) -> str:
        """Transcribe audio bytes to text."""
        rec = KaldiRecognizer(self.model, self.sample_rate)
        rec.SetWords(True)
        
        # Feed data in chunks
        chunk_size = 4000
        for i in range(0, len(speech_bytes), chunk_size):
            data_chunk = speech_bytes[i:i+chunk_size]
            if rec.AcceptWaveform(data_chunk):
                break
        
        # Get final result
        result = rec.FinalResult()
        
        try:
            result_json = json.loads(result)
            text = result_json.get("text", "")
        except json.JSONDecodeError:
            text = result
        
        self.logger.log(
            "STT",
            f"Transcription: \"{text}\"",
            level="INFO",
            text=text,
        )
        
        return text


# ============================================================================
# TTS SIMULATOR
# ============================================================================

class TTSSimulator:
    """Simulates TTS with optional actual speech output."""
    
    def __init__(self, enable_output: bool, logger: DiagnosticLogger):
        self.enable_output = enable_output
        self.logger = logger
        self.engine = None
        
        if self.enable_output:
            try:
                import pyttsx3
                self.engine = pyttsx3.init()
            except Exception as e:
                self.logger.log("TTS", f"Failed to initialize TTS: {e}", level="ERROR")
                self.enable_output = False
    
    def speak(self, text: str):
        """Speak the text or simulate speaking."""
        self.logger.log("TTS", f"Speaking: \"{text}\"", level="INFO", text=text)
        
        if self.enable_output and self.engine:
            try:
                # Reinitialize engine to avoid pyttsx3 bug
                import pyttsx3
                engine = pyttsx3.init()
                engine.say(text)
                engine.runAndWait()
                engine.stop()
                del engine
            except Exception as e:
                self.logger.log("TTS", f"TTS error: {e}", level="ERROR")
        else:
            # Simulate speaking time
            duration = min(2.0, len(text) / 10.0)
            time.sleep(duration)
        
        self.logger.log("TTS", "Finished speaking", level="DEBUG")


# ============================================================================
# MICROPHONE AUDIO CAPTURE
# ============================================================================

class MicrophoneCapture:
    """Capture audio from microphone with VAD."""
    
    def __init__(
        self,
        sample_rate: int,
        frame_duration_ms: int,
        vad: webrtcvad.Vad,
        pre_roll_frames: int,
        hangover_frames: int,
        logger: DiagnosticLogger,
        device_index: Optional[int] = None,
    ):
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.vad = vad
        self.pre_roll_frames = pre_roll_frames
        self.hangover_frames = hangover_frames
        self.logger = logger
        self.device_index = device_index
    
    def capture_utterance(self, timeout_sec: Optional[int] = None) -> Optional[Tuple[bytes, float]]:
        """
        Capture a single utterance from microphone.
        
        Returns:
            (audio_bytes, duration_seconds) or None if timeout
        """
        import pyaudio
        
        pa = pyaudio.PyAudio()
        chunk_samples = int(self.sample_rate * self.frame_duration_ms / 1000)
        stream = None
        
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=chunk_samples,
                input_device_index=self.device_index,
            )
            
            self.logger.log("MIC", "Listening...", level="INFO")
            
            audio_data = bytearray()
            ring_buffer = collections.deque(maxlen=self.pre_roll_frames)
            in_speech = False
            silence_run = 0
            start_time = time.time()
            
            while True:
                # Check timeout
                if timeout_sec and (time.time() - start_time) > timeout_sec:
                    self.logger.log("MIC", f"Timeout after {timeout_sec}s", level="WARNING")
                    return None
                
                data = stream.read(chunk_samples, exception_on_overflow=False)
                is_speech = self.vad.is_speech(data, self.sample_rate)
                
                if is_speech:
                    if not in_speech:
                        in_speech = True
                        # Prepend pre-roll
                        audio_data.extend(b''.join(ring_buffer))
                        audio_data.extend(data)
                        ring_buffer.clear()
                        self.logger.log("MIC", "Voice detected, capturing...", level="DEBUG")
                    else:
                        audio_data.extend(data)
                    silence_run = 0
                else:
                    if in_speech:
                        # Hangover period
                        silence_run += 1
                        if silence_run * self.frame_duration_ms >= self.hangover_frames * self.frame_duration_ms:
                            self.logger.log("MIC", "Silence hangover elapsed, stopping", level="DEBUG")
                            break
                        audio_data.extend(data)
                    else:
                        # Accumulate pre-roll
                        ring_buffer.append(data)
            
            duration = len(audio_data) / (self.sample_rate * 2)
            return (bytes(audio_data), duration)
        
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            pa.terminate()


# ============================================================================
# CONVERSATION STATE MANAGER
# ============================================================================

class ConversationState:
    """Manages conversation state and history."""
    
    def __init__(self, logger: DiagnosticLogger):
        self.logger = logger
        self.active = False
        self.history: List[str] = []
        self.last_input_time: Optional[float] = None
    
    def activate(self):
        """Activate conversation mode."""
        self.active = True
        self.logger.log("CONVERSATION", "Conversation activated", level="SUCCESS")
    
    def deactivate(self, reason: str):
        """Deactivate conversation mode."""
        self.active = False
        self.logger.log("CONVERSATION", f"Conversation ended: {reason}", level="INFO", reason=reason)
    
    def add_user_input(self, text: str):
        """Add user input to history."""
        self.history.append(text)
        self.last_input_time = time.time()
        self.logger.log(
            "CONVERSATION",
            f"History updated: {len(self.history)} turns",
            level="DEBUG",
            history=self.history.copy(),
        )
    
    def check_timeout(self, timeout_sec: int) -> bool:
        """Check if conversation has timed out."""
        if not self.last_input_time:
            return False
        
        elapsed = time.time() - self.last_input_time
        if elapsed > timeout_sec:
            self.logger.log(
                "CONVERSATION",
                f"Timeout: {elapsed:.1f}s since last input",
                level="WARNING",
                elapsed_s=elapsed,
            )
            return True
        return False


# ============================================================================
# MAIN DIAGNOSTIC TEST RUNNER
# ============================================================================

class DiagnosticTestRunner:
    """Main test runner for voice assistant diagnostics."""
    
    def __init__(self, config: DiagnosticConfig):
        self.config = config
        self.logger = DiagnosticLogger(
            log_file=config.log_file,
            verbose=config.verbose,
        )
        
        # Initialize components
        self._init_components()
    
    def _init_components(self):
        """Initialize all diagnostic components."""
        self.logger.log("INIT", "Initializing diagnostic components...", level="INFO")
        
        # Load Vosk model
        if not os.path.exists(self.config.model_path):
            self.logger.log("INIT", f"Vosk model not found: {self.config.model_path}", level="ERROR")
            sys.exit(1)
        
        self.model = Model(self.config.model_path)
        self.logger.log("INIT", f"Loaded Vosk model: {self.config.model_path}", level="SUCCESS")
        
        # Initialize VAD
        self.vad = webrtcvad.Vad(self.config.vad_mode)
        self.frame_bytes = int((self.config.frame_duration_ms / 1000) * self.config.sample_rate * 2)
        
        self.logger.log(
            "INIT",
            f"VAD initialized: mode={self.config.vad_mode}, frame={self.config.frame_duration_ms}ms, "
            f"pre-roll={self.config.pre_roll_frames}, hangover={self.config.hangover_frames}",
            level="SUCCESS",
        )
        
        # Initialize other components
        self.vad_collector = VADAudioCollector(
            self.vad,
            self.config.sample_rate,
            self.frame_bytes,
            self.config.pre_roll_frames,
            self.config.hangover_frames,
            self.logger,
        )
        
        self.transcriber = DiagnosticTranscriber(
            self.model,
            self.config.sample_rate,
            self.logger,
        )
        
        self.tts = TTSSimulator(
            self.config.enable_tts_output,
            self.logger,
        )
        
        if self.config.use_microphone:
            self.mic_capture = MicrophoneCapture(
                self.config.sample_rate,
                self.config.frame_duration_ms,
                self.vad,
                self.config.pre_roll_frames,
                self.config.hangover_frames,
                self.logger,
                self.config.mic_device_index,
            )
    
    def run_test_suite(self, test_name: str = "all"):
        """Run a test suite."""
        self.logger.log("TEST", f"Starting test suite: {test_name}", level="INFO")
        
        if test_name == "all":
            # Run all tests
            for name in TEST_SCENARIOS.keys():
                self._run_test(name)
        elif test_name in TEST_SCENARIOS:
            self._run_test(test_name)
        else:
            self.logger.log("TEST", f"Unknown test: {test_name}", level="ERROR")
            return
        
        # Save summary
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_path = Path(f"diagnostic_summary_{timestamp}.json")
        self.logger.save_summary(summary_path)
    
    def _run_test(self, test_name: str):
        """Run a specific test."""
        scenarios = TEST_SCENARIOS[test_name]
        
        self.logger.log("TEST", f"\n{'='*60}", level="INFO")
        self.logger.log("TEST", f"Running test: {test_name}", level="INFO")
        self.logger.log("TEST", f"{'='*60}", level="INFO")
        
        conversation = ConversationState(self.logger)
        
        for scenario in scenarios:
            self._run_scenario(scenario, conversation)
    
    def _run_scenario(self, scenario: TestScenario, conversation: ConversationState):
        """Run a single test scenario."""
        self.logger.log("SCENARIO", f"\n*** {scenario.description} ***", level="INFO")
        
        # Capture audio
        if self.config.use_microphone:
            result = self.mic_capture.capture_utterance(
                timeout_sec=self.config.followup_timeout_sec if conversation.active else None
            )
            
            if result is None:
                if conversation.active:
                    conversation.deactivate("timeout")
                return
            
            speech_bytes, speech_dur = result
        else:
            # For file-based testing, prompt user to speak
            print(f"\n>>> Please say: ", end="")
            if scenario.expect_wake:
                print(f"'{self.config.wake_word} [your query]'")
            elif scenario.expect_exit:
                print(f"'{self.config.exit_phrase}'")
            elif scenario.is_followup:
                print("[follow-up query without wake word]")
            else:
                print("[query without wake word]")
            
            input("Press Enter when ready to speak...")
            
            result = self.mic_capture.capture_utterance(
                timeout_sec=self.config.followup_timeout_sec if conversation.active else None
            )
            
            if result is None:
                if conversation.active:
                    conversation.deactivate("timeout")
                return
            
            speech_bytes, speech_dur = result
        
        self.logger.log(
            "CAPTURE",
            f"Captured {speech_dur:.2f}s of audio",
            level="INFO",
            duration_s=speech_dur,
        )
        
        # Transcribe
        text = self.transcriber.transcribe(speech_bytes).strip()
        
        # Check for wake word
        wake_detected = self.config.wake_word.lower() in text.lower()
        
        if wake_detected:
            self.logger.log("WAKE", "Wake word detected!", level="SUCCESS")
        else:
            self.logger.log("WAKE", "No wake word detected", level="DEBUG")
        
        # Handle conversation state
        if not conversation.active:
            if self.config.require_wake_word and not wake_detected:
                self.logger.log(
                    "CONVERSATION",
                    "Ignoring input (no wake word)",
                    level="WARNING",
                )
                return
            
            conversation.activate()
        
        # Add to history
        conversation.add_user_input(text)
        
        # Check for exit phrase
        if self.config.exit_phrase.lower() in text.lower():
            self.logger.log("EXIT", "Exit phrase detected", level="SUCCESS")
            self.tts.speak("Goodbye!")
            conversation.deactivate("exit_phrase")
            return
        
        # Generate response
        response_text = f"You said: {text}"
        
        # Speak response
        self.tts.speak(response_text)
        
        self.logger.log("CONVERSATION", "Resuming listening for follow-up...", level="INFO")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive Voice Assistant Diagnostic Tool"
    )
    parser.add_argument(
        "--test",
        choices=["all", "wake", "nowake", "multiturn", "timeout", "exit"],
        default="all",
        help="Which test suite to run",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use live microphone input",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug output",
    )
    parser.add_argument(
        "--tts",
        action="store_true",
        help="Enable actual TTS output (default: simulated)",
    )
    parser.add_argument(
        "--model",
        default="models/vosk-model-en-us-0.22",
        help="Path to Vosk model",
    )
    
    args = parser.parse_args()
    
    # Create config
    config = DiagnosticConfig(
        use_microphone=True,  # Always use microphone for now
        enable_tts_output=args.tts,
        verbose=args.verbose,
        model_path=args.model,
        log_file=Path(f"diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"),
    )
    
    # Run tests
    runner = DiagnosticTestRunner(config)
    runner.run_test_suite(args.test)
    
    print("\n" + "="*60)
    print("Diagnostic tests complete!")
    print("="*60)


if __name__ == "__main__":
    main()
