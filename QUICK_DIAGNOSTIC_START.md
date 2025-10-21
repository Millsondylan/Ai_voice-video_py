# Quick Start: Voice Assistant Diagnostics

## 🚀 Fastest Way to Run Diagnostics

### 1. Install Dependencies

```bash
pip install webrtcvad vosk pyaudio pyttsx3
```

### 2. Run the Standalone Diagnostic

```bash
python test_voice_diagnostic_standalone.py
```

This will run 5 comprehensive tests:

1. ✅ **Wake Word Detection** - Tests "hey glasses" recognition
2. ✅ **No Wake Word** - Verifies non-wake inputs are ignored  
3. ✅ **Multi-turn Conversation** - Tests continuous listening after response
4. ✅ **Timeout Handling** - Tests 15-second silence timeout
5. ✅ **Exit Phrase** - Tests "bye glasses" termination

## 📊 What You'll See

### Successful Test Output

```
======================================================================
VOICE ASSISTANT DIAGNOSTIC TESTS
======================================================================

──────────────────────────────────────────────────────────────────────
TEST 1: Wake Word Detection
──────────────────────────────────────────────────────────────────────
>>> Say: 'hey glasses what time is it'
Press Enter when ready...

[00:00.123] [INIT        ] ✓ Loaded model: models/vosk-model-small-en-us-0.15
[00:01.234] [MIC         ] 🎤 Listening...
[00:02.345] [MIC         ] 🗣️  Voice detected
[00:04.567] [MIC         ] 🔇 Silence detected, stopping
[00:04.678] [MIC         ] ✓ Captured 2.22s
[00:04.890] [STT         ] 📝 "hey glasses what time is it"
[00:04.901] [WAKE        ] ✓ Wake word detected!
```

### Common Issues Detected

#### ❌ First Syllables Cut Off

```
[STT] 📝 "lasses what time is it"  # Missing "hey g"
```

**Fix:** Increase `pre_roll_frames` in the script

#### ❌ Last Words Cut Off

```
[STT] 📝 "hey glasses what time"  # Missing "is it"
```

**Fix:** Increase `hangover_frames` in the script

#### ❌ Follow-up Not Captured

```
[TEST] ❌ Follow-up not captured (timeout)
```

**Fix:** TTS blocking issue or microphone not re-engaging

## 🔧 Configuration Options

### Enable Verbose Output

```bash
python test_voice_diagnostic_standalone.py --verbose
```

Shows detailed VAD frame-by-frame analysis.

### Enable Actual TTS

```bash
python test_voice_diagnostic_standalone.py --tts
```

By default, TTS is simulated. Use `--tts` to hear actual speech.

### Custom Model Path

```bash
python test_voice_diagnostic_standalone.py --model models/vosk-model-en-us-0.22
```

## 📁 Output Files

After running, you'll get:

```
diagnostic_20250121_143022.json
```

This contains all timestamped events for detailed analysis.

## 🐛 Troubleshooting

### PyAudio Not Found

```bash
# macOS
brew install portaudio
pip install pyaudio

# Linux
sudo apt-get install portaudio19-dev
pip install pyaudio

# Windows
pip install pipwin
pipwin install pyaudio
```

### Vosk Model Not Found

```bash
cd models
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
```

### Microphone Not Working

```bash
# List available microphones
python -c "import pyaudio; pa = pyaudio.PyAudio(); [print(f'{i}: {pa.get_device_info_by_index(i)[\"name\"]}') for i in range(pa.get_device_count())]"
```

## 📖 Understanding the Tests

### Test 1: Wake Word Detection

**Purpose:** Verify "hey glasses" is recognized consistently

**What to check:**
- Does transcription include "hey glasses"?
- Is wake word detected in the transcript?

### Test 2: No Wake Word

**Purpose:** Ensure non-wake inputs are ignored

**What to check:**
- System should NOT activate without wake word
- Input should be logged but not processed

### Test 3: Multi-turn Conversation

**Purpose:** Verify continuous listening after first response

**What to check:**
- First turn activates with wake word
- Second turn works WITHOUT wake word
- Conversation history shows 2 turns

### Test 4: Timeout

**Purpose:** Test 15-second inactivity timeout

**What to check:**
- After initial query, system waits 15s
- Timeout triggers correctly
- Conversation ends gracefully

### Test 5: Exit Phrase

**Purpose:** Verify "bye glasses" terminates session

**What to check:**
- Exit phrase is recognized
- System says "Goodbye"
- Conversation ends

## 🎯 Key Metrics to Monitor

| Metric | Good | Bad | Fix |
|--------|------|-----|-----|
| **Capture Duration** | Matches speech length | Shorter than speech | Increase pre-roll/hangover |
| **Wake Word Detection** | 100% when spoken | <100% | Check STT accuracy |
| **Follow-up Capture** | Works without wake word | Requires wake word | Check conversation state |
| **History Retention** | Grows each turn | Resets | Check state management |
| **Timeout** | Triggers at 15s | Never triggers | Check timer logic |

## 🔍 Detailed Analysis

### Analyzing Log Files

Open the generated JSON file:

```bash
cat diagnostic_20250121_143022.json | jq '.[] | select(.level == "ERROR")'
```

This shows all errors encountered during testing.

### Common Log Patterns

**Successful Wake Detection:**
```json
{
  "component": "WAKE",
  "message": "✓ Wake word detected!",
  "level": "SUCCESS"
}
```

**Clipped Audio:**
```json
{
  "component": "MIC",
  "message": "✓ Captured 1.23s",
  "duration_s": 1.23
}
```
If duration is much shorter than expected, audio is being clipped.

**Timeout Working:**
```json
{
  "component": "MIC",
  "message": "⏱️  Timeout after 15s",
  "level": "WARNING"
}
```

## 📚 Next Steps

1. **Run the diagnostic** to establish baseline
2. **Review the logs** to identify issues
3. **Tune parameters** based on findings
4. **Re-run tests** to verify improvements
5. **Document optimal settings** for your environment

## 💡 Pro Tips

- **Run in a quiet room** for best results
- **Speak clearly** at consistent volume
- **Use the same microphone** as production
- **Test multiple times** to check consistency
- **Compare logs** before/after changes

---

**Need Help?** Check the full guide: `DIAGNOSTIC_COMPREHENSIVE_GUIDE.md`
