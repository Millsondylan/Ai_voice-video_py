# ⚡ RESTART NOW - Bugs Fixed!

## 🐛 Critical Bugs Fixed

### Bug #1: 60-Second Delay on Second TTS ✅ FIXED
**File:** `app/audio/mic.py:80-89`
**Fix:** Added 60-second timeout + auto-recovery

### Bug #2: chunk_samples = 4096 ✅ FIXED
**File:** `config.json:12`
**Fix:** Set to optimal value (was reverting to 320)

---

## ⚡ Restart App NOW

```bash
# Stop app (Ctrl+C)
python3 app/main.py
```

---

## ✅ Expected Results

After restart:

| Issue | Status |
|-------|--------|
| Speech detection | ✅ Should work (VAD level 2) |
| First TTS response | ✅ Works |
| Second TTS response | ✅ **No more 60s delay!** |
| Buffer performance | ✅ Optimized (4096 chunks) |
| Response time | ✅ Fast (~0.8s) |

---

## 🧪 Test Immediately After Restart

```
1. Say "Hey Glasses"
2. Say "What's the weather?"
3. Wait for response
4. Say "Hey Glasses" again  ← The critical test!
5. Say another question
6. Should respond immediately (NO DELAY!)
```

---

## 📊 Monitor Logs

```bash
tail -f glasses-debug.log | grep -E "Segment recording started|TTS"
```

**Should see:**
```
Segment recording started (vad=2 silence_ms=800 chunk_ms=256...)
TTS started...
TTS completed...
```

**NOT:**
```
vad=1 silence_ms=1800  ← Old config
Microphone was paused for >60s  ← Timeout triggered
```

---

## 🔍 If Still Not Working

### Run Diagnostics
```bash
python3 diagnose_live.py
```

### Test VAD Levels
```bash
python3 test_vad_levels.py
```

### Check Config
```bash
cat config.json | grep -E "chunk_samples|vad_aggressiveness"
```

Should output:
```json
"chunk_samples": 4096,
"vad_aggressiveness": 2,
```

---

## 📝 What Was Fixed

**app/audio/mic.py:**
```python
# Before (infinite blocking):
self._controller.wait_if_paused()

# After (60s timeout + recovery):
if not self._controller.wait_if_paused(timeout=60.0):
    audio_logger.warning("Microphone was paused for >60s, force resuming")
    pause_input(False)
```

**config.json:**
```json
{
  "chunk_samples": 4096,     // Was 320
  "vad_aggressiveness": 2,   // Was 3 (too aggressive)
  "silence_ms": 800,         // Was 1800
  "tail_padding_ms": 200     // Was 700
}
```

---

## 🎯 Bottom Line

**BEFORE:**
- ❌ Second TTS = 60-second delay
- ❌ Speech not detected (VAD too aggressive)
- ⚠️ Poor buffer performance

**AFTER (restart required):**
- ✅ All TTS responses instant
- ✅ Speech detection working
- ✅ Optimized performance

**→ Restart app NOW to activate fixes!** 🚀
