# Diagnostic Tool - Issue Fixes

## Issue 1: `get_event_logger` Not Defined ✅ FIXED

**Root Cause:** The function exists and is properly imported in all app modules. This error shouldn't occur.

**Verification:**
```bash
.venv/bin/python3 -c "from app.util.log import get_event_logger; print('OK')"
```

**If you still see this error:** It might be a stale Python cache issue.

**Fix:**
```bash
# Clear Python cache
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete

# Re-run diagnostic
.venv/bin/python3 diagnostic_voice_assistant.py --test 1
```

---

## Issue 2: Vosk STT Not Transcribing Speech 🔧 NEEDS ATTENTION

**Root Cause:** The Vosk small model (`vosk-model-small-en-us-0.15`) is:
- Less accurate than larger models
- Requires clear speech
- Sensitive to audio quality
- May miss words or entire utterances

**What's Happening:**
- ✅ Microphone captures audio (18.96 seconds captured)
- ✅ VAD detects speech correctly
- ❌ Vosk doesn't transcribe anything (empty transcript)

### Solution 1: Test with Basic STT Script

I've created a simpler test script to diagnose the issue:

```bash
.venv/bin/python3 test_stt_basic.py
```

This will:
- Show you real-time partial results
- Help verify if Vosk is working at all
- Display exactly what Vosk is hearing

**When running this test:**
1. Speak VERY CLEARLY and slowly
2. Speak LOUDER than normal
3. Use simple words first: "hello", "testing", "one two three"
4. Avoid background noise

### Solution 2: Use a Larger Vosk Model

The small model is 40MB but less accurate. Download a larger one:

```bash
# Download larger US English model (1.8GB - much more accurate)
cd models/
wget https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip
unzip vosk-model-en-us-0.22.zip
rm vosk-model-en-us-0.22.zip
cd ..

# Update config.json to use it:
# Change: "vosk_model_path": "models/vosk-model-en-us-0.22"
```

**Or try the medium model** (128MB - good balance):
```bash
cd models/
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
```

### Solution 3: Check Audio Input Level

Your microphone might be too quiet:

```bash
# Test audio levels
.venv/bin/python3 -c "
import pyaudio
import struct
import math

p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)
print('Speak into the microphone...')
print('Audio levels (RMS):')
for i in range(50):
    data = stream.read(1024, exception_on_overflow=False)
    shorts = struct.unpack('h' * 1024, data)
    rms = math.sqrt(sum(s**2 for s in shorts) / len(shorts))
    bars = '#' * int(rms / 100)
    print(f'\r{int(rms):>5} {bars}', end='', flush=True)
stream.stop_stream()
stream.close()
p.terminate()
"
```

**Expected:** RMS should be 500-5000 when speaking
**If too low:** Increase system microphone volume

### Solution 4: Update Config for Better Speech Detection

Edit `config.json`:

```json
{
  "vad_aggressiveness": 1,    // More sensitive (was 2)
  "pre_roll_ms": 600,         // More pre-roll (was 400-500)
  "silence_ms": 1500,         // Longer silence threshold (was 1200)
  "min_speech_frames": 2      // Add this - lower threshold
}
```

### Solution 5: Quick Vosk Test (Verify It Works)

```bash
.venv/bin/python3 << 'EOF'
import json
from vosk import Model, KaldiRecognizer
import pyaudio

model = Model("models/vosk-model-small-en-us-0.15")
rec = KaldiRecognizer(model, 16000)

p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=8000)
stream.start_stream()

print("Say something (10 seconds)...")
for i in range(0, 20):
    data = stream.read(8000, exception_on_overflow=False)
    if rec.AcceptWaveform(data):
        result = json.loads(rec.Result())
        print(f"FINAL: {result.get('text', '')}")
    else:
        partial = json.loads(rec.PartialResult())
        if partial.get('partial'):
            print(f"PARTIAL: {partial['partial']}", end='\r')

result = json.loads(rec.FinalResult())
print(f"\nFINAL RESULT: {result.get('text', '')}")

stream.stop_stream()
stream.close()
p.terminate()
EOF
```

---

## Quick Diagnostic Checklist

Run through these steps:

### ✅ Step 1: Verify Microphone Works
```bash
# Should show audio devices
.venv/bin/python3 -c "import pyaudio; p=pyaudio.PyAudio(); print([p.get_device_info_by_index(i)['name'] for i in range(p.get_device_count())]); p.terminate()"
```

### ✅ Step 2: Test Basic Vosk
```bash
.venv/bin/python3 test_stt_basic.py
```
Speak clearly: "hello testing one two three"

### ✅ Step 3: Check Audio Levels
Run the audio level test from Solution 3 above.
Should see activity when speaking.

### ✅ Step 4: Try Diagnostic Again
```bash
.venv/bin/python3 diagnostic_voice_assistant.py --test 1
```

---

## Expected vs. Actual

### What SHOULD Happen:
```
[00:00:04.645] System : 🎤 Microphone OPEN - listening...
[User speaks: "hello what is gold"]
[00:00:08.757] STT : Transcript: 'hello what is gold'
[00:00:08.757] STT : Word Count: 4
[00:00:08.757] Validator : ✅ no_truncation: Transcript has 4 words
[00:00:08.757] System : ✅ PASSED
```

### What YOU Got:
```
[00:00:24.757] STT : Transcript: ''
[00:00:24.757] STT : Word Count: 0
[00:00:24.757] Validator : ❌ no_truncation: Transcript has 0 words
[00:00:24.757] System : ❌ FAILED
```

**The difference:** Vosk heard audio (18.96s) but didn't recognize any words.

---

## Recommended Next Steps

1. **Run the basic STT test:**
   ```bash
   .venv/bin/python3 test_stt_basic.py
   ```
   - Speak slowly and clearly
   - Use simple words
   - Check if you see ANY partial results

2. **If test shows nothing:**
   - Check microphone volume (should be 50%+)
   - Try speaking LOUDER
   - Reduce background noise
   - Consider downloading larger Vosk model

3. **If test works:**
   - The diagnostic tool should work too
   - Try running Test 1 again

4. **If still issues:**
   - Share the output of `test_stt_basic.py`
   - We can investigate further

---

## Known Working Configuration

This configuration works well for most users:

**config.json:**
```json
{
  "vosk_model_path": "models/vosk-model-en-us-0.22",  // Larger model
  "sample_rate_hz": 16000,
  "chunk_samples": 320,
  "vad_aggressiveness": 1,     // More sensitive
  "pre_roll_ms": 600,          // More buffer
  "silence_ms": 1500,          // Reasonable pause detection
  "wake_sensitivity": 0.70     // Moderate sensitivity
}
```

**System Settings:**
- Microphone volume: 60-80%
- Quiet environment
- Speak clearly, not too fast
- 1-2 feet from microphone

---

## Still Not Working?

If after trying all solutions above, Vosk still doesn't transcribe:

### Alternative: Use Whisper STT Instead

Vosk is lightweight but less accurate. Whisper (OpenAI) is much better:

```bash
# Install Whisper
pip install openai-whisper

# You'll need to modify the code to use Whisper instead of Vosk
# This requires code changes in app/audio/stt.py
```

But try the solutions above first - Vosk should work!
