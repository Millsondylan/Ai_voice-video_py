# 🚨 URGENT: Fix Speech Detection & TTS Delay

## Problems Identified

1. **"Not picking up on anything"** → Old config still loaded (VAD=1, silence=1800ms)
2. **"1 minute delay after second TTS"** → Possible pause_input deadlock

---

## Root Cause

Your logs show the **old config is still active**:
```
vad=1 silence_ms=1800 chunk_ms=20 pre_roll_ms=800
```

**The app needs to be restarted** to load the new optimized config!

---

## Quick Fix (Do This Now)

### Step 1: Stop the Application
```bash
# Press Ctrl+C or stop the app
```

### Step 2: Verify Config
```bash
cat config.json | grep -E "vad_aggressiveness|silence_ms|chunk_samples"
```

**Should show:**
```json
"chunk_samples": 4096,
"vad_aggressiveness": 3,
"silence_ms": 800,
```

### Step 3: IMPORTANT - Tune VAD Down First
VAD level 3 might be TOO aggressive. Let's start with level 2:

```bash
# Edit config.json - change this one line
sed -i.bak 's/"vad_aggressiveness": 3/"vad_aggressiveness": 2/' config.json
```

### Step 4: Restart App
```bash
python3 app/main.py
```

---

## Expected Behavior After Restart

✅ **Should detect speech** (VAD level 2 is balanced)
✅ **Faster response** (silence_ms now 800ms)
✅ **Better buffer performance** (chunk_samples now 4096)

---

## If Still Not Detecting Speech

### Diagnostic Test
```python
# Run this in a separate terminal
python3 -c "
from app.audio.mic import MicrophoneStream
from app.audio.vad import VoiceActivityDetector
import time

print('Testing microphone and VAD...')

# Test VAD levels
for vad_level in [1, 2, 3]:
    print(f'\nTesting VAD level {vad_level}:')
    vad = VoiceActivityDetector(aggressiveness=vad_level)

    with MicrophoneStream(rate=16000, chunk_samples=4096) as mic:
        print('Speak now...')
        for i in range(20):  # 20 frames = ~2.5 seconds
            frame = mic.read()
            is_speech = vad.is_speech(frame)
            print('█' if is_speech else '▁', end='', flush=True)
            time.sleep(0.1)
    print()
"
```

**Interpretation:**
- `█` = Speech detected
- `▁` = Silence/noise

If you see NO `█` bars at any level → Microphone issue
If level 1 shows `█` but level 3 doesn't → VAD too aggressive

---

## Recommended VAD Settings

| Level | Behavior | Use Case |
|-------|----------|----------|
| **0** | Very sensitive | Quiet room, clear speech |
| **1** | Balanced | Normal environment |
| **2** | ✅ **Recommended** | Some background noise |
| **3** | Very selective | Loud background (may miss speech!) |

**Change in config.json:**
```json
"vad_aggressiveness": 2  // Start here, not 3!
```

---

## Fix TTS 1-Minute Delay

The delay is likely from `pause_input` timeout. Let's add a safety timeout:

### Check Current Behavior
```bash
grep -A5 "wait_if_paused" app/audio/mic.py
```

### If No Timeout
The mic blocks forever if TTS doesn't resume it. Add this check:

```bash
# Check if there's a timeout parameter
grep "timeout" app/audio/io.py
```

**Solution**: The code already has timeout support! The issue is TTS might be failing to call `pause_input(False)`.

### Check TTS Logs
```bash
tail -50 glasses-debug.log | grep -E "TTS|pause"
```

Look for:
- ✅ "TTS started"
- ✅ "TTS completed"
- ❌ Missing "TTS completed" → TTS hung!

---

## Emergency Workaround

If TTS keeps hanging, **disable microphone pausing temporarily**:

```python
# Edit app/audio/tts.py
# Comment out these lines:

# Line 127: pause_input(True)  → # pause_input(True)
# Line 147: pause_input(False) → # pause_input(False)
```

**Trade-off**: May get echo, but app will work.

---

## Complete Fix Steps

1. **Stop app**
2. **Set VAD to level 2** (not 3)
   ```bash
   # In config.json
   "vad_aggressiveness": 2
   ```
3. **Verify other settings**
   ```bash
   cat config.json | grep -E "silence_ms|chunk_samples|tail_padding"
   ```
   Should show:
   ```json
   "silence_ms": 800,
   "chunk_samples": 4096,
   "tail_padding_ms": 200,
   ```
4. **Restart app**
   ```bash
   python3 app/main.py
   ```
5. **Test speech detection**
   - Say "Hey Glasses"
   - Should detect within 1 second

---

## Monitor Logs

```bash
tail -f glasses-debug.log | grep -E "VAD|TTS|Segment"
```

**Good signs:**
```
VAD detected speech during pre-roll
Segment stopped (reason=silence duration_ms=800...
TTS started len=...
TTS completed in ...ms
```

**Bad signs:**
```
# No VAD detection when you speak
# TTS started but no "TTS completed"
# "vad=1" instead of "vad=2" (means old config)
```

---

## Why VAD 3 Might Fail

WebRTC VAD level 3 is **extremely** selective:
- ❌ May reject normal speech as "noise"
- ❌ May miss quiet speakers
- ❌ May miss beginning of sentences

**Use level 2 instead** - it's the sweet spot:
- ✅ Rejects background noise
- ✅ Detects normal speech
- ✅ Works with most microphones

---

## Quick Test After Restart

1. Start app
2. Check logs show new config:
   ```bash
   tail -10 glasses-debug.log | grep "vad="
   # Should show: vad=2 (not vad=1)
   ```
3. Say "Hey Glasses"
4. Speak a sentence
5. Should respond in ~1 second

---

## Summary

**Problem 1**: Old config still loaded
- **Fix**: Restart app

**Problem 2**: VAD level 3 too aggressive
- **Fix**: Use level 2 instead

**Problem 3**: TTS 1-minute delay
- **Cause**: Likely old config timeout (silence_ms=1800)
- **Fix**: Restart with new config (silence_ms=800)

**Do this now:**
```bash
# 1. Edit config.json
nano config.json
# Change "vad_aggressiveness": 3 to 2

# 2. Restart app
python3 app/main.py

# 3. Test immediately
# Say "Hey Glasses" and speak
```
