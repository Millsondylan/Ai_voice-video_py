# Porcupine Wake Word Detection - Setup Guide

## Overview

Your voice assistant now supports **dual wake word detection**:

1. **Primary: Picovoice Porcupine** (acoustic model-based, high accuracy, low CPU)
2. **Fallback: Vosk STT** (transcription-based, works offline, no API key needed)

The system automatically uses Porcupine if available and configured, otherwise falls back to Vosk.

---

## Why Use Porcupine?

**Advantages over Vosk STT Wake Word Detection:**

| Feature | Porcupine | Vosk STT |
|---------|-----------|----------|
| **Accuracy** | ✅ Very High (acoustic model) | ⚠️ Good (text matching) |
| **False Positives** | ✅ Very Low | ⚠️ Moderate |
| **CPU Usage** | ✅ ~4% (optimized) | ⚠️ Higher (continuous transcription) |
| **Sensitivity Tuning** | ✅ Yes (0.0-1.0 scale) | ❌ No |
| **Offline** | ✅ Yes (after setup) | ✅ Yes |
| **Setup** | ⚠️ Requires API key | ✅ No setup |
| **Custom Wake Words** | ✅ Yes (train custom models) | ✅ Yes (any phrase) |

**Recommendation:** Use Porcupine for production, keep Vosk as fallback for testing/development.

---

## Quick Setup (5 Minutes)

### Step 1: Install Porcupine

```bash
pip install pvporcupine
```

### Step 2: Get Access Key

1. Go to [Picovoice Console](https://console.picovoice.ai)
2. Sign up for free account
3. Create new access key
4. Copy the access key

### Step 3: Configure Environment

Add to your `.env` file:

```bash
# Porcupine Access Key (REQUIRED)
PORCUPINE_ACCESS_KEY=your_access_key_here

# Optional: Sensitivity tuning (0.0-1.0, default 0.65)
GLASSES_PORCUPINE_SENSITIVITY=0.65

# Optional: Prefer Porcupine (default true)
GLASSES_PREFER_PORCUPINE=true
```

### Step 4: Test It!

```bash
python app/main.py
```

Check the console output - you should see:
```
✅ Using Porcupine wake word detection (sensitivity=0.65)
```

If you see this instead, Porcupine fell back to Vosk:
```
✅ Using Vosk STT wake word detection (variants=3)
```

---

## Using Built-in Wake Words

Porcupine supports several built-in wake words without training:

| Wake Word | Config Value |
|-----------|--------------|
| "Alexa" | `wake_word: "alexa"` |
| "Hey Google" | `wake_word: "hey google"` |
| "OK Google" | `wake_word: "ok google"` |
| "Hey Siri" | `wake_word: "hey siri"` |
| "Jarvis" | `wake_word: "jarvis"` |
| "Computer" | `wake_word: "computer"` |
| "Porcupine" | `wake_word: "porcupine"` |
| "Bumblebee" | `wake_word: "bumblebee"` |

To use a built-in wake word, just set it in [config.json](config.json):

```json
{
  "wake_word": "jarvis",
  "prefer_porcupine": true
}
```

---

## Training Custom Wake Words (e.g., "Hey Glasses")

To use "Hey Glasses" or any custom phrase with Porcupine:

### Step 1: Access Picovoice Console

1. Go to [Picovoice Console](https://console.picovoice.ai)
2. Navigate to **"Porcupine"** section
3. Click **"Train Custom Wake Word"**

### Step 2: Train Your Wake Word

1. Enter phrase: `hey glasses`
2. Select language: `English (US)`
3. Select platform: Your OS (macOS, Linux, Windows, etc.)
4. Click **"Train"** (takes a few minutes)
5. Download the `.ppn` file (e.g., `hey-glasses_en_mac.ppn`)

### Step 3: Install Custom Model

```bash
# Create models directory if it doesn't exist
mkdir -p models

# Move your .ppn file to models directory
mv ~/Downloads/hey-glasses_en_mac.ppn models/
```

### Step 4: Configure

Update your [config.json](config.json):

```json
{
  "wake_word": "hey glasses",
  "prefer_porcupine": true,
  "porcupine_keyword_path": "models/hey-glasses_en_mac.ppn",
  "porcupine_sensitivity": 0.65
}
```

Or use environment variable in `.env`:

```bash
GLASSES_PORCUPINE_KEYWORD_PATH=models/hey-glasses_en_mac.ppn
```

### Step 5: Test

```bash
python app/main.py
```

Say "Hey Glasses" - it should trigger using the Porcupine model!

---

## Tuning Sensitivity

Porcupine's sensitivity parameter controls the detection threshold:

| Sensitivity | Behavior |
|-------------|----------|
| **0.0 - 0.3** | Very strict, few false positives, may miss sometimes |
| **0.4 - 0.6** | Balanced, good for most cases |
| **0.7 - 0.9** | Very sensitive, triggers easily, more false positives |
| **1.0** | Maximum sensitivity |

**Recommended Starting Points:**

```json
{
  "porcupine_sensitivity": 0.5   // Quiet room
  "porcupine_sensitivity": 0.65  // Normal room (default)
  "porcupine_sensitivity": 0.75  // Noisy room or far from mic
}
```

### How to Tune:

1. **Too many misses?** Increase sensitivity by 0.05-0.1
2. **Too many false triggers?** Decrease sensitivity by 0.05-0.1
3. Test with: `python test_voice_pipeline.py --test 2`

---

## Fallback Behavior

The system automatically falls back to Vosk if:

- ❌ Porcupine not installed (`pip install pvporcupine`)
- ❌ No access key in environment (`PORCUPINE_ACCESS_KEY`)
- ❌ Invalid access key or network error
- ❌ Custom keyword file not found
- ✅ `prefer_porcupine` set to `false` in config

**Fallback is seamless** - the system will log a warning and continue with Vosk:

```
⚠️  Porcupine initialization failed: Invalid access key
Falling back to Vosk STT-based detection...
✅ Using Vosk STT wake word detection (variants=3)
```

You can force Vosk mode by setting:

```json
{
  "prefer_porcupine": false
}
```

Or environment variable:

```bash
GLASSES_PREFER_PORCUPINE=false
```

---

## Technical Details

### Porcupine Requirements

- **Sample Rate:** Must be 16000 Hz
- **Frame Length:** 512 samples (Porcupine standard)
- **Audio Format:** 16-bit PCM, mono
- **Platform:** macOS, Linux, Windows, Raspberry Pi

### Chunk Size Compatibility

**Important:** Porcupine requires `chunk_samples=512`, while Vosk works best with `chunk_samples=320`.

The hybrid manager handles this automatically:
- Uses 512 samples for Porcupine
- Uses 320 samples for Vosk fallback

No configuration changes needed!

### Memory & CPU

**Porcupine:**
- RAM: ~10 MB
- CPU: ~4% on Raspberry Pi 4
- Latency: ~30ms

**Vosk (fallback):**
- RAM: ~50 MB (small model)
- CPU: ~15% on Raspberry Pi 4
- Latency: ~100ms

---

## Testing Both Methods

Use the test script to compare:

```bash
# Test Porcupine (if configured)
GLASSES_PREFER_PORCUPINE=true python test_voice_pipeline.py --test 2

# Test Vosk fallback
GLASSES_PREFER_PORCUPINE=false python test_voice_pipeline.py --test 2
```

Compare:
- Detection accuracy
- False positive rate
- Response time
- CPU usage (use `htop` or Activity Monitor)

---

## Troubleshooting

### "Porcupine not available (not installed)"

**Fix:**
```bash
pip install pvporcupine
```

### "Porcupine access key not found"

**Fix:** Add to `.env`:
```bash
PORCUPINE_ACCESS_KEY=your_key_here
```

### "Invalid access key"

**Causes:**
- Expired or revoked key
- Copy/paste error (check for spaces)
- Network/firewall blocking Picovoice servers

**Fix:**
1. Verify key at [console.picovoice.ai](https://console.picovoice.ai)
2. Copy fresh key
3. Ensure no extra spaces: `echo "$PORCUPINE_ACCESS_KEY" | wc -c` should be ~88 characters

### "Keyword file not found"

**Fix:**
```bash
# Check path
ls -l models/hey-glasses_en_mac.ppn

# Update config
GLASSES_PORCUPINE_KEYWORD_PATH=models/hey-glasses_en_mac.ppn
```

### "Sample rate must be 16000 Hz"

**Fix:** Ensure config has:
```json
{
  "sample_rate_hz": 16000
}
```

### "Wake word never triggers"

**Debugging:**
1. Check console logs for detection method:
   ```
   ✅ Using Porcupine wake word detection (sensitivity=0.65)
   ```
2. Increase sensitivity:
   ```json
   "porcupine_sensitivity": 0.80
   ```
3. Test microphone:
   ```bash
   python -c "import pyaudio; p=pyaudio.PyAudio(); print([p.get_device_info_by_index(i)['name'] for i in range(p.get_device_count())])"
   ```
4. Try built-in keyword first (e.g., "Jarvis") to isolate custom model issues

### Falls back to Vosk unexpectedly

**Check logs for reason:**
- Missing API key → Add `PORCUPINE_ACCESS_KEY`
- Custom model error → Verify `.ppn` file exists and matches your OS
- Network error → Check internet connection (first run only)

---

## Free vs Paid Plans

### Picovoice Free Tier

- ✅ Unlimited wake word detections
- ✅ Up to 3 custom wake words
- ✅ All platforms supported
- ✅ No credit card required

**More than enough for personal use!**

### When to Upgrade

Only needed if:
- More than 3 custom wake words
- Commercial deployment (high volume)
- Advanced features (barge-in, etc.)

See [Picovoice Pricing](https://picovoice.ai/pricing/) for details.

---

## Best Practices

### Development

```bash
# Use Vosk for faster iteration (no API key needed)
GLASSES_PREFER_PORCUPINE=false python app/main.py
```

### Production

```bash
# Use Porcupine for best accuracy
GLASSES_PREFER_PORCUPINE=true python app/main.py
```

### Testing

```bash
# Test both methods
python test_voice_pipeline.py --test 2
```

### Monitoring

Check which method is active:

```python
# In code
from app.audio.wake_hybrid import HybridWakeWordManager

manager = HybridWakeWordManager(...)
listener = manager.create_listener()
print(f"Using: {manager.detection_method}")  # "porcupine" or "vosk"
```

---

## Summary

**With Porcupine configured:**
```
✅ High accuracy wake word detection
✅ Low CPU usage
✅ Tunable sensitivity
✅ Automatic fallback to Vosk if issues
```

**Without Porcupine (Vosk only):**
```
✅ Still works great!
✅ No API key needed
✅ Offline by default
⚠️ Slightly higher CPU
⚠️ More false positives possible
```

Both methods are production-ready. Porcupine is recommended for best experience, but Vosk fallback ensures your assistant always works!

---

## Quick Reference

### Porcupine + "Hey Glasses"

```bash
# 1. Install
pip install pvporcupine

# 2. Get API key
# Visit: https://console.picovoice.ai

# 3. Train custom wake word
# Console → Porcupine → Train → Download .ppn

# 4. Configure .env
PORCUPINE_ACCESS_KEY=your_key_here
GLASSES_PORCUPINE_KEYWORD_PATH=models/hey-glasses_en_mac.ppn
GLASSES_PORCUPINE_SENSITIVITY=0.65

# 5. Test
python app/main.py
```

### Vosk Only (No Setup)

```bash
# Set in config.json
{
  "prefer_porcupine": false,
  "wake_word": "hey glasses",
  "wake_variants": ["hey glasses", "hay glasses", "hey glass"]
}

# Run
python app/main.py
```

Done! 🎉
