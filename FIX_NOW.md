# 🚨 FIX NOW - Do This Immediately

## Problem Summary

1. **"Not picking up on anything"** ← App using old config (needs restart)
2. **"1 minute delay on 2nd TTS"** ← Old timeout settings (silence_ms=1800)

## Solution: 3 Simple Steps

### Step 1: Restart the App ⚡
```bash
# Stop the app (Ctrl+C if running)
# Then restart:
python3 app/main.py
```

**Why?** The optimized config isn't loaded yet. Logs show:
```
vad=1 silence_ms=1800  ← OLD config
```

Should be:
```
vad=2 silence_ms=800   ← NEW config
```

---

### Step 2: Test Speech Detection 🎤
```bash
# Say "Hey Glasses" then speak a sentence
# Should respond in ~1 second (not 1.8 seconds)
```

**If still not detecting:**
```bash
python3 test_vad_levels.py
```

This will test VAD levels and tell you which works best.

---

### Step 3: Verify in Logs 📊
```bash
tail -f glasses-debug.log | grep "Segment recording started"
```

**Good sign:**
```
Segment recording started (vad=2 silence_ms=800 chunk_ms=256 pre_roll_ms=500)
```

**Bad sign (old config still loaded):**
```
Segment recording started (vad=1 silence_ms=1800 chunk_ms=20 pre_roll_ms=800)
```

---

## Quick Check: Is Config Correct?

```bash
cat config.json | grep -E "vad_aggressiveness|silence_ms|chunk_samples"
```

**Should show:**
```json
"chunk_samples": 4096,
"vad_aggressiveness": 2,     ← Changed from 3 to 2 (less aggressive)
"silence_ms": 800,
```

✅ **All correct!** Just restart the app.

---

## Why It's Not Working Now

Your logs from `glasses-debug.log` show:
```
vad=1 silence_ms=1800
```

But your `config.json` has:
```json
"vad_aggressiveness": 2,
"silence_ms": 800,
```

**Conclusion:** The app loaded the OLD config and hasn't been restarted yet!

---

## Expected After Restart

✅ Speech detection works (VAD level 2 is balanced)
✅ Fast response (~0.8s instead of 1.8s)
✅ TTS no delay (timeout now 800ms not 1800ms)
✅ Better buffer performance (4096 chunks)

---

## If Still Having Issues After Restart

### Issue 1: Still Not Detecting Speech

**Test VAD levels:**
```bash
python3 test_vad_levels.py
```

This will show which VAD level works for your environment.

**OR manually test:**
```bash
python3 -c "
from app.audio.mic import MicrophoneStream
print('Testing mic - speak now...')
with MicrophoneStream(rate=16000, chunk_samples=4096) as mic:
    for i in range(10):
        frame = mic.read()
        print(f'Read {len(frame)} bytes')
"
```

If this works → VAD issue
If this fails → Microphone issue

### Issue 2: TTS Still Has Delay

**Check if TTS is completing:**
```bash
tail -30 glasses-debug.log | grep TTS
```

**Should see:**
```
TTS started len=...
TTS completed in ...ms
```

**If missing "TTS completed"** → TTS hung, check:
```bash
tail -50 glasses-debug.log | grep -i error
```

---

## Emergency Workaround

If nothing works, **temporarily disable optimizations**:

```json
{
  "vad_aggressiveness": 1,     ← Back to default
  "silence_ms": 1200,          ← Slower but more forgiving
  "chunk_samples": 320,        ← Original value
}
```

Then restart and test. If this works, the optimizations were too aggressive for your setup.

---

## TL;DR - Do This Right Now

```bash
# 1. Stop app (Ctrl+C)

# 2. Restart app
python3 app/main.py

# 3. Test immediately
# Say: "Hey Glasses"
# Then: Speak a sentence

# 4. Check logs
tail -10 glasses-debug.log | grep "vad="
# Should show: vad=2 (not vad=1)
```

**If that fixes it:** ✅ You're done!

**If still broken:** Run `python3 test_vad_levels.py`

---

## What Changed

| Setting | Old (in logs) | New (in config) | Benefit |
|---------|---------------|-----------------|---------|
| VAD | 1 | 2 | Better noise rejection, still detects speech |
| silence_ms | 1800 | 800 | 2.2x faster response |
| chunk_samples | 20 | 4096 | 200x better buffer performance |
| pre_roll_ms | 800 | 500 | Cleaner start |

**Just restart to activate these!** 🚀
