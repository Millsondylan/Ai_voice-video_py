#!/usr/bin/env python3
"""
Voice Assistant Diagnostic & Fix Guide
======================================

This standalone diagnostic script implements the end-to-end troubleshooting
workflow for the Glasses voice assistant. It provides:

* Timestamped audio diagnostics with RMS/DB tracking
* Gain-normalized wake word detection tuned for normal speaking volumes
* WebRTC VAD capture pipeline with ring buffers and hybrid speech detection
* Configurable timeout management for natural conversation flow
* Interactive tests for wake word sensitivity, VAD capture, and timeout tuning

Usage:
    python voice_assistant_diagnostic_prompt.py --model models/vosk-model-small-en-us-0.15
    python voice_assistant_diagnostic_prompt.py --diagnose-levels
    python voice_assistant_diagnostic_prompt.py --test wake
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pyaudio
from vosk import KaldiRecognizer, Model, SetLogLevel

from app.audio.diagnostics import (
    AUDIO_FORMAT,
    CHANNELS,
    CHUNK_SIZE,
    SAMPLE_RATE,
    VAD_FRAME_BYTES,
    VAD_FRAME_MS,
    AudioRingBuffer,
    HybridDetectionResult,
    HybridSpeechDetector,
    TimeoutManager,
    VADManager,
    apply_gain_to_audio,
    diagnose_audio_levels,
    normalize_audio_rms,
    diagnostics,
)


# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

GAIN_DB = 28
TARGET_RMS_DB = -18.0
DEFAULT_WAKE_WORDS = ["hey glasses", "hey computer"]


# =============================================================================
# INITIALIZATION HELPERS
# =============================================================================

def list_input_devices(pa: pyaudio.PyAudio) -> List[Dict[str, object]]:
    """Return a list of available microphone devices."""
    devices: List[Dict[str, object]] = []
    for index in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(index)
        if info.get("maxInputChannels", 0) > 0:
            device_info = {
                "index": index,
                "name": info.get("name"),
                "channels": info.get("maxInputChannels"),
                "default_rate": info.get("defaultSampleRate"),
            }
            devices.append(device_info)
    return devices


def initialize_audio_stream(device_index: Optional[int] = None) -> Tuple[pyaudio.PyAudio, pyaudio.Stream]:
    """Open a PyAudio stream configured for the diagnostic pipeline."""
    pa = pyaudio.PyAudio()
    devices = list_input_devices(pa)
    for device in devices:
        diagnostics.log_event(
            "AUDIO_DEVICE",
            index=device["index"],
            name=device["name"],
            channels=device["channels"],
            default_rate=device["default_rate"],
        )
    if device_index is None:
        default_info = pa.get_default_input_device_info()
        diagnostics.log_event("AUDIO_DEFAULT_DEVICE", name=default_info.get("name"), index=default_info.get("index"))
        device_index = default_info.get("index")

    stream = pa.open(
        format=AUDIO_FORMAT,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        input_device_index=device_index,
        frames_per_buffer=CHUNK_SIZE,
        start=True,
    )
    diagnostics.log_event(
        "AUDIO_STREAM_OPENED",
        device_index=device_index,
        rate=SAMPLE_RATE,
        chunk_frames=CHUNK_SIZE,
    )
    return pa, stream


def initialize_vosk_for_wake_word(model_path: Path, wake_words: Sequence[str]) -> KaldiRecognizer:
    """Initialize Vosk recognizer tuned for wake word detection."""
    SetLogLevel(-1)
    model = Model(str(model_path))

    # Use grammar limited to wake words + unknown for faster detection
    grammar = json.dumps(list(wake_words) + ["[unk]"])
    recognizer = KaldiRecognizer(model, SAMPLE_RATE, grammar)
    recognizer.SetWords(True)
    diagnostics.log_event("VOSK_INITIALIZED", model=str(model_path), wake_words=",".join(wake_words))
    return recognizer


# =============================================================================
# WAKE WORD UTILITIES
# =============================================================================

def check_wake_word_vosk(
    audio_chunk: bytes,
    recognizer: KaldiRecognizer,
    wake_words: Sequence[str],
) -> Tuple[bool, str]:
    """Check both full and partial Vosk results for a wake word hit."""
    detected = False
    transcript = ""

    if recognizer.AcceptWaveform(audio_chunk):
        result = json.loads(recognizer.Result())
        transcript = result.get("text", "").lower()
        diagnostics.log_event("VOSK_FULL_RESULT", text=transcript)
        for word in wake_words:
            if word.lower() in transcript:
                detected = True
                break

    if not detected:
        partial = json.loads(recognizer.PartialResult())
        partial_text = partial.get("partial", "").lower()
        if partial_text:
            diagnostics.log_event("VOSK_PARTIAL_RESULT", text=partial_text)
        for word in wake_words:
            if word.lower() in partial_text:
                detected = True
                transcript = partial_text
                break

    return detected, transcript


# =============================================================================
# VOICE ASSISTANT PIPELINE
# =============================================================================

class VoiceAssistantPipeline:
    """Self-contained diagnostic pipeline for wake word + speech capture."""

    def __init__(
        self,
        model_path: Path,
        wake_words: Optional[Sequence[str]] = None,
        gain_db: float = GAIN_DB,
    ) -> None:
        self.wake_words: Sequence[str] = tuple(wake_words or DEFAULT_WAKE_WORDS)
        self.gain_db = gain_db
        self.pyaudio, self.stream = initialize_audio_stream()
        self.recognizer = initialize_vosk_for_wake_word(model_path, self.wake_words)

        self.vad_manager = VADManager(sample_rate=SAMPLE_RATE, frame_duration_ms=VAD_FRAME_MS, aggressiveness=0)
        self.hybrid_detector = HybridSpeechDetector(
            self.vad_manager,
            volume_threshold=200,
            vad_weight=0.5,
            volume_weight=0.5,
            activation_threshold=0.3,
        )
        self.timeout_manager = TimeoutManager(
            no_speech_timeout_ms=3000,
            mid_speech_pause_ms=1500,
            min_recording_duration_ms=500,
        )
        self.pre_wake_buffer = AudioRingBuffer(duration_seconds=1.5)
        self.recording_buffer: List[bytes] = []

        self.state = "LISTENING_FOR_WAKE"
        self.loop_running = True
        diagnostics.log_event("PIPELINE_INITIALIZED", wake_words=",".join(self.wake_words))

    # ------------------------------------------------------------------ lifecycle
    def run(self) -> None:
        diagnostics.log_event("PIPELINE_START")
        try:
            while self.loop_running:
                audio_chunk = self.stream.read(CHUNK_SIZE, exception_on_overflow=False)
                if self.state == "LISTENING_FOR_WAKE":
                    self.process_wake_detection(audio_chunk)
                elif self.state == "RECORDING_COMMAND":
                    self.process_command_recording(audio_chunk)
        except KeyboardInterrupt:
            diagnostics.log_event("PIPELINE_INTERRUPTED")
        finally:
            self.cleanup()

    def stop(self) -> None:
        self.loop_running = False

    # ----------------------------------------------------------------- wake phase
    def process_wake_detection(self, audio_chunk: bytes) -> None:
        diagnostics.log_event("AUDIO_CAPTURE_START")
        diagnostics.log_audio_chunk(audio_chunk, "WAKE_AUDIO_RAW")
        boosted_chunk = apply_gain_to_audio(audio_chunk, self.gain_db)
        diagnostics.log_audio_chunk(boosted_chunk, "WAKE_AUDIO_GAINED")
        normalized_chunk = normalize_audio_rms(boosted_chunk, target_rms_db=TARGET_RMS_DB)
        diagnostics.log_audio_chunk(normalized_chunk, "WAKE_AUDIO_NORMALIZED")
        self.pre_wake_buffer.add(normalized_chunk)

        detected, text = check_wake_word_vosk(normalized_chunk, self.recognizer, self.wake_words)
        diagnostics.log_event("WAKE_DETECTION_RESULT", detected=detected, text=text)

        if detected:
            diagnostics.log_event("WAKE_WORD_DETECTED", transcript=text)
            self.transition_to_recording()

    def transition_to_recording(self) -> None:
        diagnostics.log_event("TRANSITION_START")
        available = getattr(self.stream, "get_read_available", lambda: 0)()
        if available:
            # Flush stale frames
            self.stream.read(available, exception_on_overflow=False)
            diagnostics.log_event("BUFFER_FLUSHED", frames_discarded=available)

        self.recording_buffer = [self.pre_wake_buffer.get_all()]
        diagnostics.log_event("PRE_WAKE_AUDIO_INCLUDED", chunks=len(self.recording_buffer))
        self.pre_wake_buffer.clear()

        self.vad_manager.reset()
        self.timeout_manager.reset()
        self.timeout_manager.start_recording()
        self.state = "RECORDING_COMMAND"
        diagnostics.log_event("TRANSITION_COMPLETE", new_state=self.state)

    # --------------------------------------------------------------- record phase
    def process_command_recording(self, audio_chunk: bytes) -> None:
        diagnostics.log_audio_chunk(audio_chunk, "RECORD_AUDIO_RAW")
        boosted_chunk = apply_gain_to_audio(audio_chunk, self.gain_db)
        diagnostics.log_audio_chunk(boosted_chunk, "RECORD_AUDIO_GAINED")
        normalized_chunk = normalize_audio_rms(boosted_chunk, target_rms_db=TARGET_RMS_DB)
        diagnostics.log_audio_chunk(normalized_chunk, "RECORD_AUDIO_NORMALIZED")

        self.recording_buffer.append(normalized_chunk)

        vad_frame = normalized_chunk[:VAD_FRAME_BYTES]
        speech_started, speech_ended = self.vad_manager.process_with_buffer(vad_frame)
        if speech_started:
            diagnostics.log_event("USER_SPEECH_STARTED")
            self.timeout_manager.update_speech_detected()

        hybrid_result: HybridDetectionResult = self.hybrid_detector.detect_speech(normalized_chunk)
        if hybrid_result.is_speech:
            self.timeout_manager.update_speech_detected()

        timed_out, reason = self.timeout_manager.check_timeout()
        if speech_ended or timed_out:
            diagnostics.log_event(
                "RECORDING_TERMINATED",
                speech_ended=speech_ended,
                timed_out=timed_out,
                reason=reason,
            )
            # Capture a short tail after speech ends to avoid clipping the final syllable.
            self._capture_tail(duration_ms=600)
            self.finalize_recording(reason or "speech_ended")

    def finalize_recording(self, stop_reason: str) -> None:
        audio_bytes = b"".join(self.recording_buffer)
        duration_sec = len(audio_bytes) / (SAMPLE_RATE * 2)
        diagnostics.log_event(
            "RECORDING_COMPLETE",
            total_bytes=len(audio_bytes),
            duration_sec=f"{duration_sec:.2f}",
            stop_reason=stop_reason,
        )
        self.recording_buffer.clear()
        self.state = "LISTENING_FOR_WAKE"
        self.timeout_manager.reset()
        diagnostics.log_event("STATE_RESET", new_state=self.state)

    # ------------------------------------------------------------------- cleanup
    def _capture_tail(self, duration_ms: int) -> None:
        """Read additional audio after stop trigger to capture trailing speech."""
        frames_needed = max(1, int((duration_ms / 1000.0) * SAMPLE_RATE / CHUNK_SIZE))
        diagnostics.log_event("TAIL_CAPTURE_START", duration_ms=duration_ms, frames=frames_needed)
        for _ in range(frames_needed):
            tail_chunk = self.stream.read(CHUNK_SIZE, exception_on_overflow=False)
            diagnostics.log_audio_chunk(tail_chunk, "TAIL_AUDIO_RAW")
            boosted_tail = apply_gain_to_audio(tail_chunk, self.gain_db)
            diagnostics.log_audio_chunk(boosted_tail, "TAIL_AUDIO_GAINED")
            normalized_tail = normalize_audio_rms(boosted_tail, target_rms_db=TARGET_RMS_DB)
            diagnostics.log_audio_chunk(normalized_tail, "TAIL_AUDIO_NORMALIZED")
            self.recording_buffer.append(normalized_tail)
        diagnostics.log_event("TAIL_CAPTURE_COMPLETE")

    def cleanup(self) -> None:
        if getattr(self, "stream", None):
            try:
                self.stream.stop_stream()
            except Exception:
                pass
            try:
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        if getattr(self, "pyaudio", None):
            try:
                self.pyaudio.terminate()
            except Exception:
                pass
            self.pyaudio = None
        diagnostics.log_event("CLEANUP_COMPLETE")


# =============================================================================
# TESTS AND VERIFICATION
# =============================================================================

def test_wake_word_sensitivity(
    stream: pyaudio.Stream,
    recognizer: KaldiRecognizer,
    wake_words: Sequence[str],
    gain_db: float,
    duration: float = 30.0,
) -> bool:
    """Run interactive wake word sensitivity test."""
    print("\n" + "=" * 60)
    print("WAKE WORD SENSITIVITY TEST")
    print("=" * 60)
    print("Speak the wake word at normal, quiet, and loud volumes.")
    print(f"Listening for {duration:.0f} seconds...")
    print("=" * 60)

    detections: List[Dict[str, object]] = []
    start_time = time.time()
    while time.time() - start_time < duration:
        chunk = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        rms, _ = diagnostics.log_audio_chunk(chunk, "WAKE_TEST_AUDIO")
        boosted = apply_gain_to_audio(chunk, gain_db)
        diagnostics.log_audio_chunk(boosted, "WAKE_TEST_AUDIO_GAINED")
        normalized = normalize_audio_rms(boosted, target_rms_db=TARGET_RMS_DB)
        diagnostics.log_audio_chunk(normalized, "WAKE_TEST_AUDIO_NORMALIZED")
        detected, text = check_wake_word_vosk(normalized, recognizer, wake_words)
        if detected:
            detections.append({"time": time.time() - start_time, "text": text, "rms": rms})
            print(f"✓ DETECTED at {time.time() - start_time:5.1f}s: '{text}' (RMS: {rms})")

    print("\n" + "=" * 60)
    print(f"RESULTS: {len(detections)} detections in {duration:.0f} seconds")
    for detection in detections:
        print(f"  {detection['time']:5.1f}s: '{detection['text']}' (RMS: {detection['rms']})")
    print("=" * 60)
    return bool(detections)


def test_vad_capture(pipeline: VoiceAssistantPipeline, max_commands: int = 1) -> None:
    """Prompt user to speak and verify VAD capture via diagnostics."""
    print("\n" + "=" * 60)
    print("VAD SPEECH CAPTURE TEST")
    print("=" * 60)
    print("Say 'hey glasses' followed by a command.")
    print("Press Ctrl+C to stop after completing the test.")
    print("=" * 60)

    commands_captured = 0
    try:
        while commands_captured < max_commands:
            chunk = pipeline.stream.read(CHUNK_SIZE, exception_on_overflow=False)
            if pipeline.state == "LISTENING_FOR_WAKE":
                pipeline.process_wake_detection(chunk)
            else:
                before = len(pipeline.recording_buffer)
                pipeline.process_command_recording(chunk)
                if pipeline.state == "LISTENING_FOR_WAKE" and before:
                    commands_captured += 1
                    print(f"✓ Command #{commands_captured} captured")
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.stop()
        pipeline.cleanup()


def test_timeout_behavior(
    stream: pyaudio.Stream,
    vad_manager: VADManager,
    duration_sec: float = 10.0,
) -> None:
    """Evaluate timeout parameters with real-time feedback."""
    timeout_manager = TimeoutManager(
        no_speech_timeout_ms=3000,
        mid_speech_pause_ms=1500,
        min_recording_duration_ms=500,
    )
    timeout_manager.start_recording()

    print("\n" + "=" * 60)
    print("TIMEOUT BEHAVIOR TEST")
    print("=" * 60)
    print("1. Say nothing for a few seconds (expect timeout).")
    print("2. Speak with pauses to evaluate mid-speech handling.")
    print("=" * 60)

    start_time = time.time()
    while time.time() - start_time < duration_sec:
        chunk = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        vad_frame = chunk[:VAD_FRAME_BYTES]
        is_speech = vad_manager.is_speech(vad_frame)
        print("." if is_speech else " ", end="", flush=True)
        if is_speech:
            timeout_manager.update_speech_detected()
        timed_out, reason = timeout_manager.check_timeout()
        if timed_out:
            elapsed = time.time() - start_time
            print(f"\n✓ TIMEOUT ({reason}) triggered at {elapsed:.2f}s")
            break
    print("\n" + "=" * 60)


# =============================================================================
# COMMAND-LINE INTERFACE
# =============================================================================

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Voice Assistant Diagnostic & Fix Guide")
    parser.add_argument("--model", type=Path, required=True, help="Path to Vosk model directory")
    parser.add_argument("--wake-words", nargs="*", default=DEFAULT_WAKE_WORDS, help="Wake words to detect")
    parser.add_argument("--gain-db", type=float, default=GAIN_DB, help="Gain in dB to apply before Vosk/VAD")
    parser.add_argument("--diagnose-levels", action="store_true", help="Run audio level diagnostics and exit")
    parser.add_argument("--test", choices=["wake", "vad", "timeout"], help="Run a specific diagnostic test")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    model_path = args.model
    if not model_path.exists():
        print(f"Model not found: {model_path}", file=sys.stderr)
        return 1

    diagnostics.log_event("CLI_ARGS", model=str(model_path), wake_words=",".join(args.wake_words))

    pa, stream = initialize_audio_stream()
    try:
        recognizer = initialize_vosk_for_wake_word(model_path, args.wake_words)

        if args.diagnose_levels:
            diagnose_audio_levels(stream)
            return 0

        if args.test == "wake":
            success = test_wake_word_sensitivity(stream, recognizer, args.wake_words, args.gain_db)
            return 0 if success else 1
        if args.test == "timeout":
            vad_manager = VADManager(sample_rate=SAMPLE_RATE, frame_duration_ms=VAD_FRAME_MS, aggressiveness=0)
            test_timeout_behavior(stream, vad_manager)
            return 0
        if args.test == "vad":
            pipeline = VoiceAssistantPipeline(model_path, args.wake_words, gain_db=args.gain_db)
            test_vad_capture(pipeline)
            return 0

    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()

    pipeline = VoiceAssistantPipeline(model_path, args.wake_words, gain_db=args.gain_db)
    pipeline.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
