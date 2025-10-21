# Quick Fix Guide - Voice Assistant Issues

## 🚀 Quick Start

If you're experiencing issues, follow these steps in order:

### 1. Update Configuration (30 seconds)

Edit `config.json` and update these values:

```json
{
  "vad_aggressiveness": 1,
  "silence_ms": 1200,
  "pre_roll_ms": 500,
  "min_speech_frames": 3,
  "tail_padding_ms": 300
}
```

### 2. Test the System (2 minutes)

```bash
python3 test_voice_pipeline.py
```

This will test all components and tell you exactly what's wrong.

### 3. Run the Application

```bash
python3 -m app.main
```

---

## 🔧 Common Issues & Instant Fixes

### Issue: "Speech gets cut off mid-sentence"

**Quick Fix:**
```json
// In config.json, increase silence timeout:
"silence_ms": 1500  // or even 2000 for slow speakers
```

**Why it works:** Gives you more time to pause between words without the system thinking you're done.

---

### Issue: "Wake word doesn't trigger"

**Quick Fix 1 - Increase Sensitivity:**
```json
"wake_sensitivity": 0.75  // Increase from 0.65
```

**Quick Fix 2 - Use Manual Trigger:**
Press `Ctrl+G` instead of saying the wake word.

**Quick Fix 3 - Check Microphone:**
```bash
# List available microphones
python3 -c "from app.audio.mic import MicrophoneStream; print([d['name'] for d in MicrophoneStream.list_input_devices()])"

# Set specific mic in config.json:
"mic_device_name": "MacBook Pro Microphone"
```

---

### Issue: "Assistant doesn't speak back"

**Quick Fix 1 - Test TTS:**
```bash
python3 -c "from app.audio.tts import SpeechSynthesizer; SpeechSynthesizer().speak('Testing one two three')"
```

**Quick Fix 2 - Check Audio Output:**
- Make sure volume is up
- Check correct output device is selected
- Try unplugging/replugging headphones

**Quick Fix 3 - Restart Audio:**
```bash
# macOS only:
sudo killall coreaudiod
```

---

### Issue: "First syllable is missing"

**Quick Fix:**
```json
// In config.json, increase pre-roll buffer:
"pre_roll_ms": 600  // Increase from 500
```

**Why it works:** Captures more audio before speech detection, ensuring first syllables are included.

---

### Issue: "Conversation ends after one turn"

**This should already work!** The system is configured for 15-second follow-up timeout.

**To verify:**
1. Say wake word
2. Ask a question
3. Wait for response
4. Ask another question (WITHOUT saying wake word)
5. It should respond

**If it doesn't work:**
- Check you're not accidentally saying "bye glasses"
- Make sure you speak within 15 seconds
- Try manual trigger (Ctrl+G) to rule out wake word issues

---

### Issue: "Background noise triggers false wakes"

**Quick Fix:**
```json
// In config.json, decrease sensitivity:
"wake_sensitivity": 0.55  // Decrease from 0.65
"vad_aggressiveness": 2   // Increase from 1
```

---

## 📊 Optimal Settings by Environment

### Quiet Room (Home Office)
```json
{
  "vad_aggressiveness": 1,
  "silence_ms": 1200,
  "wake_sensitivity": 0.65
}
```

### Noisy Environment (Coffee Shop)
```json
{
  "vad_aggressiveness": 0,
  "silence_ms": 1000,
  "wake_sensitivity": 0.55
}
```

### Fast Speaker
```json
{
  "silence_ms": 800,
  "vad_aggressiveness": 1
}
```

### Slow Speaker / Long Pauses
```json
{
  "silence_ms": 2000,
  "vad_aggressiveness": 1,
  "min_speech_frames": 5
}
```

---

## 🎯 Testing Checklist

After applying fixes, test these scenarios:

- [ ] Wake word triggers reliably (5/5 attempts)
- [ ] Long sentence with pauses is fully captured
- [ ] Assistant speaks response (not silent)
- [ ] Second question works without wake word
- [ ] Context is retained ("What about Paris?" after asking about France)
- [ ] Session ends after 15s of silence
- [ ] "Bye glasses" exits immediately

---

## 🐛 Debug Mode

Enable detailed logging:

```bash
# Run with debug output
python3 run_with_debug.py

# Check the log file
tail -f glasses_debug.log
```

Look for:
- `[DEBUG] Wake listener STARTED` - Wake word detection active
- `[DEBUG] run_segment STARTED` - Recording started
- `[DEBUG] Transcript: '...'` - What was heard
- `[DEBUG] TTS started` - Speaking response

---

## 📞 Still Not Working?

1. **Check Permissions:**
   - System Settings → Privacy & Security → Microphone
   - Grant access to Terminal/IDE

2. **Increase Microphone Volume:**
   - System Settings → Sound → Input
   - Drag slider to maximum

3. **Test Components Individually:**
   ```bash
   python3 test_components.py
   ```

4. **Try Minimal Config:**
   ```json
   {
     "vosk_model_path": "models/vosk-model-small-en-us-0.15",
     "mic_device_name": null,
     "vad_aggressiveness": 0,
     "silence_ms": 2000
   }
   ```

5. **Check Logs:**
   - Look in `glasses_debug.log`
   - Check for error messages
   - Note what happens vs. what should happen

---

## ✅ Success Indicators

You'll know it's working when:

- ✅ Wake word triggers within 1 second
- ✅ Full sentences captured (no truncation)
- ✅ Assistant speaks every response
- ✅ Can have 3+ turn conversation without wake word
- ✅ Context is maintained ("it" and "there" work)
- ✅ Session ends gracefully after 15s or "bye glasses"

---

## 🔄 Quick Reset

If things get weird, reset to defaults:

```bash
# Restore original config
git checkout config.json

# Apply recommended fixes
# Edit config.json and set:
# - vad_aggressiveness: 1
# - silence_ms: 1200
# - pre_roll_ms: 500

# Restart the app
python3 -m app.main
```

---

## 📚 More Help

- Full details: See `FIXES_APPLIED.md`
- Troubleshooting: See `TROUBLESHOOTING.md`
- Test suite: Run `python3 test_voice_pipeline.py`
- Component tests: Run `python3 test_components.py`
