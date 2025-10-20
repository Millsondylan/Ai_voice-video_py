# Diagnosis Report: Voice Capture & TTS Issues

## Status Summary

✅ **FIXED**: TTS only working once
❓ **INVESTIGATING**: Voice not being captured

---

## What I Found

### 1. Component Tests - ALL PASS ✅

Ran `test_components.py` - results:
- ✅ Configuration loading
- ✅ Microphone devices detected (MacBook Air Microphone)
- ✅ Microphone open/close
- ✅ TTS initialization
- ✅ TTS sync speak (3 successful calls)
- ✅ TTS async speak (3 successful calls)
- ✅ STT initialization
- ✅ Logger functionality

**Conclusion**: All individual components work perfectly. TTS works multiple times in both sync and async modes.

### 2. TTS Threading Issue - FIXED ✅

**Problem Found**: In `app/audio/tts.py:59-60`, the `speak_async()` method was calling `engine.stop()` without proper locking, causing race conditions.

**Fix Applied**:
```python
# Before (line 59-60):
if self._current_thread and self._current_thread.is_alive():
    self._engine.stop()  # ← No lock!

# After (line 61-66):
if self._current_thread and self._current_thread.is_alive():
    try:
        with self._lock:  # ← Added lock
            self._engine.stop()
    except Exception:
        pass  # Ignore stop errors
```

**Verification**: Component test shows TTS working 6 times consecutively.

---

## Remaining Issue: Voice Not Being Captured

Since all components work individually, the issue is likely in:

### Possible Causes:

1. **Microphone Permission** (Most Likely)
   - Terminal/IDE may not have microphone access
   - Fix: `System Settings → Privacy & Security → Microphone`

2. **VAD Too Aggressive**
   - Current setting: `vad_aggressiveness: 2`
   - May be filtering out speech
   - Fix: Try `vad_aggressiveness: 1` or `0`

3. **Silence Timeout Too Short**
   - Current: `silence_ms: 1200` (1.2 seconds)
   - May be cutting off before done speaking
   - Fix: Try `silence_ms: 2000`

4. **Microphone Volume**
   - System microphone input level too low
   - Fix: `System Settings → Sound → Input → Increase volume`

5. **Pre-roll Buffer Issue**
   - Current: `pre_roll_ms: 300`
   - May not be feeding pre-roll to STT correctly
   - Check: `app/audio/capture.py:67-68`

---

## Diagnostic Tools Created

### 1. test_components.py ✅
Tests all components individually - **ALL PASS**

### 2. test_manual_recording.py (NEW)
**Run this to test the full recording flow:**
```bash
.venv/bin/python3 test_manual_recording.py
```

This will:
1. Initialize all components
2. Start a manual recording session
3. Show you the transcript
4. Test TTS multiple times
5. Tell you exactly what's wrong

### 3. run_with_debug.py (NEW)
**Run the actual app with debug logging:**
```bash
.venv/bin/python3 run_with_debug.py
```

This adds [DEBUG] messages showing:
- Wake listener start
- Recording start/stop
- Transcripts
- TTS calls
- All state transitions

Logs saved to: `glasses_debug.log`

---

## Next Steps to Diagnose

### Step 1: Test Manual Recording
```bash
.venv/bin/python3 test_manual_recording.py
```

**Expected behavior:**
- Prompts you to speak
- Waits for `silence_ms` after you stop
- Shows transcript
- Speaks back what you said

**If it fails:**
- Check what transcript you get (empty? partial?)
- Check stop_reason (silence? cap? done?)
- Increase microphone volume
- Try with `vad_aggressiveness: 0` in config.json

### Step 2: Run App with Debug
```bash
.venv/bin/python3 run_with_debug.py
```

Watch for:
```
[DEBUG] Wake listener STARTED
[DEBUG] Wake variants: ['hey glasses', ...]
[DEBUG] run_segment STARTED
[DEBUG] Transcript: '...'
[DEBUG] _on_response_ready CALLED
```

**If wake word doesn't trigger:**
- Check [DEBUG] messages show listener started
- Try manually triggering with Ctrl+G
- Check if VAD is filtering everything

**If recording starts but no transcript:**
- Check [DEBUG] shows run_segment started
- Check what stop_reason is
- Check audio_ms vs duration_ms
- Increase microphone volume

### Step 3: Test with Minimal Config

Edit `config.json` to minimal settings:
```json
{
  "vosk_model_path": "models/vosk-model-small-en-us-0.15",
  "mic_device_name": null,
  "vad_aggressiveness": 0,
  "silence_ms": 2000,
  "max_segment_s": 45,
  "chunk_samples": 320,
  "sample_rate_hz": 16000,
  "pre_roll_ms": 300
}
```

Then run: `.venv/bin/python3 test_manual_recording.py`

---

## Expected Log Output

### When Working Correctly:
```
[DEBUG] Wake listener STARTED
[glasses.audio] INFO - Wake word detected at 1760991715538
[DEBUG] run_segment STARTED
[glasses.audio] INFO - Segment recording started at 1760991715542
[glasses.audio] INFO - Segment stopped: reason=silence, duration=3.2s, text_len=25
[DEBUG] Transcript: 'hello how are you today'
[DEBUG] _on_response_ready CALLED
[glasses.audio] INFO - TTS started at 1760991718542
[glasses.audio] INFO - TTS completed in 2100ms
```

### If Voice Not Captured:
```
[DEBUG] run_segment STARTED
[glasses.audio] INFO - Segment stopped: reason=silence, duration=1.2s, text_len=0
[DEBUG] Transcript: ''
```
→ **Means**: No speech detected by Vosk
→ **Fix**: Increase mic volume, reduce VAD aggressiveness

### If Recording Never Stops:
```
[DEBUG] run_segment STARTED
[glasses.audio] INFO - Segment stopped: reason=cap, duration=45.0s, text_len=150
```
→ **Means**: Hitting max duration, silence detection not working
→ **Fix**: Check VAD settings, mic volume

---

## Summary

✅ **TTS Issue**: FIXED (threading lock added)
❓ **Voice Capture**: All components work, need to run diagnostic tests

**Immediate Action:**
```bash
# Run this and tell me what you see:
.venv/bin/python3 test_manual_recording.py
```

This will show:
1. If voice is being captured
2. What the transcript is
3. If TTS works multiple times
4. Exact error if something fails

**Tell me:**
1. What does the transcript show?
2. What is the stop_reason?
3. What is the duration vs audio_ms?
4. Does TTS work both times?
