#!/usr/bin/env python3
"""Run the app with extensive debug logging."""

import sys
import logging
from pathlib import Path

# Setup debug logging FIRST
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('glasses_debug.log', mode='w')
    ]
)

# Patch the app modules to add debug prints
import app.audio.wake
import app.audio.capture
import app.segment
import app.ui

original_wake_run = app.audio.wake.WakeWordListener.run

def debug_wake_run(self):
    print(f"\n[DEBUG] Wake listener STARTED")
    print(f"[DEBUG] Wake variants: {self._wake_variants}")
    print(f"[DEBUG] Mic device: {self._mic_device_name}")
    print(f"[DEBUG] Sample rate: {self._sample_rate}, chunk: {self._chunk_samples}")
    try:
        return original_wake_run(self)
    except Exception as e:
        print(f"\n[DEBUG] Wake listener ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise

app.audio.wake.WakeWordListener.run = debug_wake_run

original_run_segment = app.audio.capture.run_segment

def debug_run_segment(*args, **kwargs):
    print(f"\n[DEBUG] run_segment STARTED")
    print(f"[DEBUG] Config: silence_ms={kwargs.get('config').silence_ms if 'config' in kwargs else 'N/A'}")
    result = original_run_segment(*args, **kwargs)
    print(f"\n[DEBUG] run_segment COMPLETED")
    print(f"[DEBUG] Transcript: '{result.clean_transcript}'")
    print(f"[DEBUG] Stop reason: {result.stop_reason}")
    print(f"[DEBUG] Duration: {result.duration_ms}ms, Audio: {result.audio_ms}ms")
    return result

app.audio.capture.run_segment = debug_run_segment

original_record_segment = app.segment.SegmentRecorder.record_segment

def debug_record_segment(self):
    print(f"\n[DEBUG] SegmentRecorder.record_segment STARTED")
    result = original_record_segment(self)
    print(f"\n[DEBUG] SegmentRecorder.record_segment COMPLETED")
    print(f"[DEBUG] Clean transcript: '{result.clean_transcript}'")
    return result

app.segment.SegmentRecorder.record_segment = debug_record_segment

original_on_response_ready = app.ui.GlassesWindow._on_response_ready

def debug_on_response_ready(self, response):
    print(f"\n[DEBUG] _on_response_ready CALLED")
    print(f"[DEBUG] Response text: '{response.get('text', '')}'")
    print(f"[DEBUG] About to call TTS...")
    result = original_on_response_ready(self, response)
    print(f"[DEBUG] TTS called, restarting wake listener...")
    return result

app.ui.GlassesWindow._on_response_ready = debug_on_response_ready

print("=" * 60)
print("RUNNING APP WITH DEBUG LOGGING")
print("=" * 60)
print("Watch for [DEBUG] messages to trace execution")
print("Log file: glasses_debug.log")
print("=" * 60)

# Now run the actual app
from app.main import main
sys.exit(main())
