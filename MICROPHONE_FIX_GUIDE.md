# 🎤 Microphone & Wake Word Fix Guide

## Problems You Encountered

1. **Background noise transcribed as "the" constantly**
2. **Had to SHOUT for wake word detection**
3. **Wake listener running during active sessions**
4. **Poor STT accuracy** ("hey glasses" → "hey glad", "hay losses", etc.)

---

## ✅ Fixes Applied

### 1. Reduced Background Noise Logging ([app/audio/wake.py](app/audio/wake.py))

**Before**:
```
[WAKE] Listening... (heard: 'the')
[WAKE] Listening... (heard: 'the')
[WAKE] Listening... (heard: 'the the')
```

**After**:
- VAD level changed: 1 → **2** (filters ambient noise better)
- Diagnostic logging now filters out repeated junk words
- Only logs substantial transcriptions (> 3 chars, not just "the")
- Status message every 10 seconds instead of spamming

### 2. Config Updated ([config.json](config.json))

Changed:
```json
"vad_aggressiveness": 2  // Was: 1 → Better noise filtering
```

This setting now matches both wake detection AND speech capture.

### 3. Created Microphone Diagnostic Tool

New file: [test_microphone_levels.py](test_microphone_levels.py)

Run this to diagnose:
- Mic input level (too quiet? too loud?)
- Background noise levels
- Which VAD level works best for your environment

---

## 🚀 Next Steps

### Step 1: Test Microphone Levels

```bash
python3 test_microphone_levels.py
```

This will:
- Test VAD levels 1, 2, and 3
- Show your mic input in decibels (dB)
- Detect background noise
- Recommend optimal VAD setting

**Expected output**:
```
Testing with VAD Level 2
Recording 5 seconds...
  - First 2 seconds: Stay SILENT
  - Last 3 seconds: Speak at NORMAL volume

[2.5s] Level: -32.1dB ████████████████

Results:
  - Speech detected in 45/250 frames (18%)
  - Maximum level: -28.5dB
  - Dynamic range: 18.2dB

Diagnosis:
  ✅ Mic level is GOOD
```

### Step 2: Adjust System Mic Volume

**If mic is too quiet** (max level < -40dB):

**macOS**:
```
System Settings > Sound > Input
- Select your microphone
- Adjust Input volume to 50-70%
- Test by speaking - bars should reach middle
```

**If you have to shout**:
- Increase system mic volume to 70-80%
- Make sure "Use ambient noise reduction" is OFF
- Move closer to mic

### Step 3: Restart App with New Settings

```bash
# Stop app (Ctrl+C)
# Then restart:
python3 app/main.py
```

**You should now see**:
```
[WAKE] Listening...
[WAKE] Heard: 'hey glasses'
✓ Wake word detected!
```

**NOT**:
```
[WAKE] Listening... (heard: 'the')  ❌ This was the old bug
```

---

## 🎯 Expected Behavior After Fixes

### Wake Word Detection
- **No spam**: Status message every ~10 seconds, not constantly
- **No "the" artifacts**: Background noise filtered out
- **Clean detection**: `[WAKE] Heard: 'hey glasses'`
- **Normal volume**: Should NOT need to shout

### During Sessions
- Wake listener stops logging during active sessions
- No interference with STT during conversation
- Clean log output

---

## 🔧 Troubleshooting

### Still Need to Shout?

**Option 1**: Lower VAD threshold in wake listener

Edit [app/audio/wake.py:79](app/audio/wake.py#L79):
```python
vad_level = 1  # Change from 2 to 1 (more sensitive)
```

**Option 2**: Increase system mic volume
- macOS: System Settings > Sound > Input > 70-80%

**Option 3**: Check mic selection
```json
// In config.json, try specifying mic explicitly:
"mic_device_name": "MacBook Air Microphone"
```

To list available mics:
```bash
python3 -c "
import pyaudio
p = pyaudio.PyAudio()
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    if info['maxInputChannels'] > 0:
        print(f'{i}: {info[\"name\"]}')
"
```

### Too Many False Wake Activations?

**Increase VAD level**:

Edit [config.json](config.json):
```json
"vad_aggressiveness": 3  // Even less sensitive to noise
```

Or edit [app/audio/wake.py:79](app/audio/wake.py#L79):
```python
vad_level = 3  // Most aggressive noise filtering
```

### Poor STT Accuracy?

The Vosk model sometimes mishe ars:
- "glasses" → "glad", "gas", "losses"
- "hey" → "hay", "a", "have"

**Solutions**:

1. **Speak more clearly** (slight over-enunciation helps)
2. **Move closer to mic** (improves signal-to-noise ratio)
3. **Use wake word variants** already in config:
   - "hi glasses"
   - "ok glasses"
   - "hey glass" (singular)

4. **Consider larger Vosk model** (better accuracy but slower):
   - Download: https://alphacephei.com/vosk/models
   - Try `vosk-model-en-us-0.42-gigaspeech` (1.5GB, much better)

---

## 📊 Microphone Level Guidelines

| dB Level | Meaning | Action |
|----------|---------|--------|
| -60 to -50 dB | Too quiet | Increase mic volume to 60-80% |
| -45 to -20 dB | **GOOD** | Optimal range |
| -15 to -5 dB | Too loud | Reduce mic volume to 30-50% |
| 0 dB | Clipping | Severe distortion, reduce volume! |

**Test your levels**:
```bash
python3 test_microphone_levels.py
```

---

## 🎛️ VAD Level Reference

| Level | Sensitivity | Best For | Issue |
|-------|-------------|----------|-------|
| **0** | Most sensitive | Quiet environments | May pick up noise |
| **1** | High sensitivity | Soft speech | Background noise |
| **2** | **BALANCED** ✅ | Normal use | **RECOMMENDED** |
| **3** | Least sensitive | Noisy environments | May miss speech |

---

## ✅ Success Checklist

After applying fixes:

- [ ] Ran `python3 test_microphone_levels.py`
- [ ] Adjusted system mic volume (50-70%)
- [ ] Restarted app
- [ ] No more `[WAKE] (heard: 'the')` spam
- [ ] Wake word detected at **normal volume**
- [ ] Clean session logs (no wake messages during capture)

---

## 🆘 Still Having Issues?

1. **Check mic permissions**:
   ```
   System Settings > Privacy & Security > Microphone
   → Enable for Terminal/Python
   ```

2. **Check no other app is using mic**:
   ```bash
   lsof | grep -i "audio"
   ```

3. **Test basic mic capture**:
   ```bash
   python3 -c "
   from app.audio.mic import MicrophoneStream
   with MicrophoneStream(rate=16000, chunk_samples=320) as mic:
       print('Recording 2 seconds...')
       for i in range(100):
           frame = mic.read(320)
           print('.', end='', flush=True)
   print('\nDone!')
   "
   ```

4. **Share logs** with specific sections:
   - Mic level test output
   - Wake detection logs
   - STT accuracy examples

---

**Last Updated**: 2025-10-21
**Status**: ✅ Noise filtering applied, diagnostic tool created
