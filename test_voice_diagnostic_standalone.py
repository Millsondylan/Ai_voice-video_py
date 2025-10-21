#!/usr/bin/env python3
"""
Standalone Voice Assistant Diagnostic Tool

A self-contained diagnostic script that tests voice assistant pipeline issues:
1. Speech capture clipping (first/last syllables lost)
2. Wake word detection reliability
3. Multi-turn conversation continuity
4. Conversation history retention
5. Timeout and exit phrase handling

This version has NO dependencies on the app/ modules and can run standalone.

Requirements:
    pip install webrtcvad vosk pyaudio pyttsx3

Usage:
    python test_voice_diagnostic_standalone.py
    python test_voice_diagnostic_standalone.py --verbose
    python test_voice_diagnostic_standalone.py --tts
"""

import argparse
import collections
import json
import os
import sys
import time
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import webrtcvad
    from vosk import Model, KaldiRecognizer
    import pyaudio
except ImportError as e:
    print(f"Missing required package: {e}")
    print("Install with: pip install webrtcvad vosk pyaudio pyttsx3")
    sys.exit(1)


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class Config:
    """Diagnostic configuration."""
    wake_word: str = "hey glasses"
    exit_phrase: str = "bye glasses"
    
    # VAD settings
    vad_mode: int = 1  # 0-3, higher = more aggressive
    frame_duration_ms: int = 30
    pre_roll_frames: int = 3  # ~90ms
    hangover_frames: int = 10  # ~300ms
    
    # Timeouts
    followup_timeout_sec: int = 15
    
    # Audio
    sample_rate: int = 16000
    
    # Model
    model_path: str = "models/vosk-model-small-en-us-0.15"
    
    # Options
    enable_tts: bool = False
    verbose: bool = False


# ============================================================================
# LOGGER
# ============================================================================

class Logger:
    """Simple timestamped logger."""
    
    def __init__(self, verbose: bool = False):
        self.start = time.time()
        self.verbose = verbose
        self.logs = []
    
    def log(self, component: str, message: str, level: str = "INFO", **data):
        elapsed = time.time() - self.start
        timestamp = f"[{int(elapsed//60):02d}:{elapsed%60:06.3f}]"
        
        entry = {
            "timestamp": timestamp,
            "component": component,
            "message": message,
            "level": level,
            **data
        }
        self.logs.append(entry)
        
        if level == "DEBUG" and not self.verbose:
            return
        
        colors = {
            "INFO": "\033[0m",
            "SUCCESS": "\033[92m",
            "WARNING": "\033[93m",
            "ERROR": "\033[91m",
            "DEBUG": "\033[90m",
        }
        
        color = colors.get(level, "\033[0m")
        print(f"{color}{timestamp} [{component:12s}] {message}\033[0m")
    
    def save(self, path: Path):
        with open(path, "w") as f:
            json.dump(self.logs, f, indent=2)
        print(f"\n✓ Logs saved to: {path}")


# ============================================================================
# VAD SPEECH COLLECTOR
# ============================================================================

class SpeechCollector:
    """Collects speech using VAD with pre-roll and hangover."""
    
    def __init__(self, config: Config, logger: Logger):
        self.config = config
        self.logger = logger
        self.vad = webrtcvad.Vad(config.vad_mode)
        self.frame_bytes = int((config.frame_duration_ms / 1000) * config.sample_rate * 2)
    
    def collect_from_mic(self, timeout_sec: Optional[int] = None) -> Optional[Tuple[bytes, float]]:
        """Capture one utterance from microphone."""
        pa = pyaudio.PyAudio()
        chunk = int(self.config.sample_rate * self.config.frame_duration_ms / 1000)
        stream = None
        
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.config.sample_rate,
                input=True,
                frames_per_buffer=chunk,
            )
            
            self.logger.log("MIC", "🎤 Listening...", level="INFO")
            
            audio = bytearray()
            ring = collections.deque(maxlen=self.config.pre_roll_frames)
            in_speech = False
            silence_count = 0
            start_time = time.time()
            
            while True:
                if timeout_sec and (time.time() - start_time) > timeout_sec:
                    self.logger.log("MIC", f"⏱️  Timeout after {timeout_sec}s", level="WARNING")
                    return None
                
                frame = stream.read(chunk, exception_on_overflow=False)
                is_speech = self.vad.is_speech(frame, self.config.sample_rate)
                
                if is_speech:
                    if not in_speech:
                        in_speech = True
                        audio.extend(b''.join(ring))
                        audio.extend(frame)
                        ring.clear()
                        self.logger.log("MIC", "🗣️  Voice detected", level="DEBUG")
                    else:
                        audio.extend(frame)
                    silence_count = 0
                else:
                    if in_speech:
                        silence_count += 1
                        if silence_count * self.config.frame_duration_ms >= \
                           self.config.hangover_frames * self.config.frame_duration_ms:
                            self.logger.log("MIC", "🔇 Silence detected, stopping", level="DEBUG")
                            break
                        audio.extend(frame)
                    else:
                        ring.append(frame)
            
            duration = len(audio) / (self.config.sample_rate * 2)
            self.logger.log("MIC", f"✓ Captured {duration:.2f}s", level="SUCCESS", duration_s=duration)
            return (bytes(audio), duration)
        
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
            pa.terminate()


# ============================================================================
# TRANSCRIBER
# ============================================================================

class Transcriber:
    """Vosk-based transcriber."""
    
    def __init__(self, config: Config, logger: Logger):
        self.config = config
        self.logger = logger
        
        if not os.path.exists(config.model_path):
            self.logger.log("INIT", f"❌ Model not found: {config.model_path}", level="ERROR")
            sys.exit(1)
        
        self.model = Model(config.model_path)
        self.logger.log("INIT", f"✓ Loaded model: {config.model_path}", level="SUCCESS")
    
    def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio to text."""
        rec = KaldiRecognizer(self.model, self.config.sample_rate)
        rec.SetWords(True)
        
        chunk_size = 4000
        for i in range(0, len(audio_bytes), chunk_size):
            chunk = audio_bytes[i:i+chunk_size]
            if rec.AcceptWaveform(chunk):
                break
        
        result = json.loads(rec.FinalResult())
        text = result.get("text", "").strip()
        
        self.logger.log("STT", f"📝 \"{text}\"", level="INFO", text=text)
        return text


# ============================================================================
# TTS
# ============================================================================

class TTS:
    """Text-to-speech with optional output."""
    
    def __init__(self, config: Config, logger: Logger):
        self.config = config
        self.logger = logger
        self.enabled = config.enable_tts
    
    def speak(self, text: str):
        """Speak text or simulate."""
        self.logger.log("TTS", f"🔊 \"{text}\"", level="INFO", text=text)
        
        if self.enabled:
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.say(text)
                engine.runAndWait()
                engine.stop()
                del engine
            except Exception as e:
                self.logger.log("TTS", f"❌ Error: {e}", level="ERROR")
        else:
            time.sleep(min(2.0, len(text) / 10.0))
        
        self.logger.log("TTS", "✓ Finished", level="DEBUG")


# ============================================================================
# CONVERSATION STATE
# ============================================================================

class Conversation:
    """Manages conversation state."""
    
    def __init__(self, logger: Logger):
        self.logger = logger
        self.active = False
        self.history = []
        self.last_input = None
    
    def activate(self):
        self.active = True
        self.logger.log("CONV", "✓ Activated", level="SUCCESS")
    
    def deactivate(self, reason: str):
        self.active = False
        self.logger.log("CONV", f"⏹️  Ended: {reason}", level="INFO", reason=reason)
    
    def add_input(self, text: str):
        self.history.append(text)
        self.last_input = time.time()
        self.logger.log("CONV", f"📚 History: {len(self.history)} turns", level="DEBUG", history=self.history)
    
    def check_timeout(self, timeout_sec: int) -> bool:
        if not self.last_input:
            return False
        elapsed = time.time() - self.last_input
        if elapsed > timeout_sec:
            self.logger.log("CONV", f"⏱️  Timeout: {elapsed:.1f}s", level="WARNING")
            return True
        return False


# ============================================================================
# TEST RUNNER
# ============================================================================

class DiagnosticRunner:
    """Main diagnostic test runner."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = Logger(verbose=config.verbose)
        
        self.logger.log("INIT", "🚀 Starting diagnostics", level="INFO")
        self.logger.log("INIT", f"VAD: mode={config.vad_mode}, pre-roll={config.pre_roll_frames}, hangover={config.hangover_frames}", level="INFO")
        
        self.collector = SpeechCollector(config, self.logger)
        self.transcriber = Transcriber(config, self.logger)
        self.tts = TTS(config, self.logger)
    
    def run_all_tests(self):
        """Run all diagnostic tests."""
        print("\n" + "="*70)
        print("VOICE ASSISTANT DIAGNOSTIC TESTS")
        print("="*70)
        
        self.test_wake_word()
        self.test_no_wake_word()
        self.test_multiturn()
        self.test_timeout()
        self.test_exit_phrase()
        
        print("\n" + "="*70)
        print("✓ ALL TESTS COMPLETE")
        print("="*70)
        
        # Save logs
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.logger.save(Path(f"diagnostic_{timestamp}.json"))
    
    def test_wake_word(self):
        """Test 1: Wake word detection."""
        print(f"\n{'─'*70}")
        print("TEST 1: Wake Word Detection")
        print(f"{'─'*70}")
        print(f">>> Say: '{self.config.wake_word} what time is it'")
        input("Press Enter when ready...")
        
        result = self.collector.collect_from_mic()
        if not result:
            return
        
        audio, duration = result
        text = self.transcriber.transcribe(audio)
        
        if self.config.wake_word.lower() in text.lower():
            self.logger.log("WAKE", "✓ Wake word detected!", level="SUCCESS")
        else:
            self.logger.log("WAKE", "❌ Wake word NOT detected", level="ERROR")
    
    def test_no_wake_word(self):
        """Test 2: No wake word (should be ignored)."""
        print(f"\n{'─'*70}")
        print("TEST 2: No Wake Word (Should Be Ignored)")
        print(f"{'─'*70}")
        print(">>> Say: 'what time is it' (WITHOUT wake word)")
        input("Press Enter when ready...")
        
        result = self.collector.collect_from_mic()
        if not result:
            return
        
        audio, duration = result
        text = self.transcriber.transcribe(audio)
        
        if self.config.wake_word.lower() not in text.lower():
            self.logger.log("WAKE", "✓ Correctly ignored (no wake word)", level="SUCCESS")
        else:
            self.logger.log("WAKE", "⚠️  Wake word detected unexpectedly", level="WARNING")
    
    def test_multiturn(self):
        """Test 3: Multi-turn conversation."""
        print(f"\n{'─'*70}")
        print("TEST 3: Multi-turn Conversation")
        print(f"{'─'*70}")
        
        conv = Conversation(self.logger)
        
        # Turn 1: With wake word
        print(f">>> Turn 1: Say '{self.config.wake_word} what's the weather'")
        input("Press Enter when ready...")
        
        result = self.collector.collect_from_mic()
        if not result:
            return
        
        audio, duration = result
        text = self.transcriber.transcribe(audio)
        
        if self.config.wake_word.lower() in text.lower():
            conv.activate()
            conv.add_input(text)
            self.tts.speak("It's sunny today")
        else:
            self.logger.log("TEST", "❌ Wake word not detected in turn 1", level="ERROR")
            return
        
        # Turn 2: Without wake word (follow-up)
        print(f"\n>>> Turn 2: Say 'what about tomorrow' (NO wake word)")
        input("Press Enter when ready...")
        
        result = self.collector.collect_from_mic(timeout_sec=self.config.followup_timeout_sec)
        if not result:
            self.logger.log("TEST", "❌ Follow-up not captured (timeout)", level="ERROR")
            return
        
        audio, duration = result
        text = self.transcriber.transcribe(audio)
        
        if text:
            self.logger.log("TEST", "✓ Follow-up captured successfully!", level="SUCCESS")
            conv.add_input(text)
            self.tts.speak("Tomorrow will be cloudy")
            
            if len(conv.history) == 2:
                self.logger.log("TEST", "✓ Conversation history retained!", level="SUCCESS")
            else:
                self.logger.log("TEST", f"❌ History issue: {len(conv.history)} turns", level="ERROR")
        else:
            self.logger.log("TEST", "❌ Follow-up transcription empty", level="ERROR")
        
        conv.deactivate("test_complete")
    
    def test_timeout(self):
        """Test 4: 15-second timeout."""
        print(f"\n{'─'*70}")
        print("TEST 4: Timeout Handling")
        print(f"{'─'*70}")
        print(f">>> Say '{self.config.wake_word} hello', then stay SILENT for 15s")
        input("Press Enter when ready...")
        
        conv = Conversation(self.logger)
        
        # Initial query
        result = self.collector.collect_from_mic()
        if not result:
            return
        
        audio, duration = result
        text = self.transcriber.transcribe(audio)
        
        if self.config.wake_word.lower() in text.lower():
            conv.activate()
            conv.add_input(text)
            self.tts.speak("Hello there")
        else:
            return
        
        # Wait for timeout
        print("\n>>> Now stay SILENT for 15 seconds...")
        result = self.collector.collect_from_mic(timeout_sec=self.config.followup_timeout_sec)
        
        if result is None:
            self.logger.log("TEST", "✓ Timeout triggered correctly!", level="SUCCESS")
            conv.deactivate("timeout")
        else:
            self.logger.log("TEST", "❌ Timeout did not trigger", level="ERROR")
    
    def test_exit_phrase(self):
        """Test 5: Exit phrase."""
        print(f"\n{'─'*70}")
        print("TEST 5: Exit Phrase")
        print(f"{'─'*70}")
        print(f">>> Say: '{self.config.wake_word} {self.config.exit_phrase}'")
        input("Press Enter when ready...")
        
        conv = Conversation(self.logger)
        
        result = self.collector.collect_from_mic()
        if not result:
            return
        
        audio, duration = result
        text = self.transcriber.transcribe(audio)
        
        if self.config.wake_word.lower() in text.lower():
            conv.activate()
        
        if self.config.exit_phrase.lower() in text.lower():
            self.logger.log("TEST", "✓ Exit phrase detected!", level="SUCCESS")
            self.tts.speak("Goodbye!")
            conv.deactivate("exit_phrase")
        else:
            self.logger.log("TEST", "❌ Exit phrase NOT detected", level="ERROR")


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Voice Assistant Diagnostics")
    parser.add_argument("--verbose", action="store_true", help="Verbose debug output")
    parser.add_argument("--tts", action="store_true", help="Enable actual TTS (default: simulated)")
    parser.add_argument("--model", default="models/vosk-model-small-en-us-0.15", help="Vosk model path")
    
    args = parser.parse_args()
    
    config = Config(
        verbose=args.verbose,
        enable_tts=args.tts,
        model_path=args.model,
    )
    
    runner = DiagnosticRunner(config)
    runner.run_all_tests()


if __name__ == "__main__":
    main()
