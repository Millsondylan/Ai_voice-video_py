# Troubleshooting Guide: Voice Capture & TTS Issues

## Quick Diagnostics

Run this first to identify the problem:

```bash
python3 test_audio_system.py
```

This will test each component and show exactly where the issue is.

---

## Issue 1: Voice Not Being Captured

### Symptoms
- Wake word doesn't trigger
- Recording starts but no transcript appears
- Empty or partial transcripts

### Diagnosis Steps

1. **Check Microphone Permissions**
   ```
   System Settings → Privacy & Security → Microphone
   ```
   - Ensure Terminal (or your IDE) has microphone access
   - You may need to restart the app after granting permission

2. **Verify Microphone Selection**
   ```bash
   python3 -c "from app.audio.mic import MicrophoneStream; print([d['name'] for d in MicrophoneStream.list_input_devices()])"
   ```
   - Check if the correct mic is listed
   - Update `config.json` with exact device name if needed:
   ```json
   {
     "mic_device_name": "MacBook Pro Microphone"
   }
   ```

3. **Test Microphone Directly**
   ```bash
   # Record 3 seconds of audio
   rec -r 16000 -c 1 test.wav trim 0 3
   # Play it back
   play test.wav
   ```

4. **Check Vosk Model**
   ```bash
   ls -la models/vosk-model-small-en-us-0.15/
   ```
   If missing, download from: https://alphacephei.com/vosk/models
   ```bash
   cd models
   wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
   unzip vosk-model-small-en-us-0.15.zip
   ```

5. **Enable Debug Logging**

   Add to the top of `app/main.py`:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

### Common Fixes

**Fix 1: Wrong Microphone Selected**
```json
// config.json
{
  "mic_device_name": null  // Use default
  // OR specify exact name:
  "mic_device_name": "USB Microphone"
}
```

**Fix 2: Microphone Volume Too Low**
```
System Settings → Sound → Input → Input volume (increase slider)
```

**Fix 3: Pre-roll Buffer Causing Issues**

If speech is cut off at the beginning, increase pre-roll:
```json
{
  "pre_roll_ms": 500  // Increase from 300
}
```

**Fix 4: VAD Too Aggressive**

If voice isn't detected, reduce VAD sensitivity:
```json
{
  "vad_aggressiveness": 1  // Reduce from 2 (0-3 range)
}
```

---

## Issue 2: TTS Only Works Once

### Symptoms
- First response is spoken
- Subsequent responses are silent
- No error messages

### Diagnosis Steps

1. **Check for Thread Errors**

   Add logging to see if TTS is being called:
   ```python
   # In app/ui.py, add before line 171:
   print(f"DEBUG: About to speak: '{text}'")
   ```

2. **Test TTS Directly**
   ```bash
   python3 -c "from app.audio.tts import SpeechSynthesizer; tts = SpeechSynthesizer(); tts.speak('Test 1'); tts.speak('Test 2'); tts.speak('Test 3')"
   ```

3. **Check Wake Listener Restart**

   Add logging to verify restart:
   ```python
   # In app/ui.py, add at line 114:
   print(f"DEBUG: Wake listener started")
   ```

### Common Fixes

**Fix 1: TTS Engine Not Reinitializing**

The pyttsx3 engine sometimes needs a fresh instance. Modified code now includes better error handling with retry + fallback.

**Fix 2: Audio Output Locked**

Run this to reset audio:
```bash
# macOS
sudo killall coreaudiod
```

**Fix 3: Wake Listener Not Restarting**

Check console for this message after first interaction:
```
DEBUG: Wake listener started
```

If missing, there's a bug in the restart logic. Check:
- Line 189 in app/ui.py should call `start_wake_listener()`
- No exceptions in `_on_response_ready()`

---

## General Debugging

### Enable Full Logging

Create `logging_config.py`:
```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('glasses_debug.log')
    ]
)
```

Import at top of `app/main.py`:
```python
import logging_config
```

### Check System Resources

```bash
# Check if any processes are holding the microphone
lsof | grep -i audio

# Check CPU usage (high CPU = possible infinite loop)
top -o cpu
```

### Verify Configuration

```bash
python3 -c "from app.util.config import load_config; import json; print(json.dumps(load_config().to_dict(), indent=2))"
```

---

## Expected Log Output

When working correctly, you should see:

```
[2025-01-15 10:23:45] glasses.audio - INFO - Wake word detected at 1736944225123
[2025-01-15 10:23:45] glasses.audio - INFO - Segment recording started at 1736944225150
[2025-01-15 10:23:52] glasses.audio - INFO - Segment stopped: reason=silence, duration=7.12s, ...
[2025-01-15 10:23:53] glasses.audio - INFO - TTS started at 1736944233012, text_len=78
[2025-01-15 10:23:56] glasses.audio - INFO - TTS completed in 3210ms
```

If you see errors instead, that indicates the problem area.

---

## Still Not Working?

1. Run the full diagnostic:
   ```bash
   python3 test_audio_system.py 2>&1 | tee diagnostic.log
   ```

2. Check the log file for errors

3. Try with minimal config:
   ```json
   {
     "vosk_model_path": "models/vosk-model-small-en-us-0.15",
     "mic_device_name": null,
     "silence_ms": 1200,
     "max_segment_s": 45
   }
   ```

4. Test with manual trigger (Ctrl+G) instead of wake word

5. Check GitHub issues: https://github.com/[your-repo]/issues

---

## Platform-Specific Issues

### macOS

**Microphone Permission Prompt Not Showing**
```bash
# Reset permissions database
tccutil reset Microphone
```

**pyttsx3 Not Working**
```bash
pip3 uninstall pyttsx3
pip3 install pyttsx3 --no-cache-dir
```

### Linux

**No Audio Output**
```bash
# Install espeak
sudo apt-get install espeak

# Test
espeak "Hello world"
```

**Microphone Issues**
```bash
# List devices
arecord -l

# Test recording
arecord -d 3 -f cd test.wav
aplay test.wav
```

---

## Success Indicators

✅ **Voice Capture Working:**
- Wake word triggers reliably
- Transcript appears immediately
- All words captured (including first syllable)
- Stops on silence or "done"

✅ **TTS Working:**
- Voice reply after every query
- Clear, understandable speech
- No delays or stuttering
- Works repeatedly without failure

If you see these indicators, the system is working correctly!
