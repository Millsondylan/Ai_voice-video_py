# Voice Assistant Diagnostic Tools - Complete Summary

## 📦 What's Been Created

Three comprehensive diagnostic tools have been created to help you identify and fix voice assistant pipeline issues:

### 1. **Standalone Diagnostic Script** ⭐ RECOMMENDED
**File:** `test_voice_diagnostic_standalone.py`

- ✅ **Zero dependencies** on app/ modules
- ✅ **Self-contained** - runs immediately
- ✅ **Interactive tests** with clear prompts
- ✅ **Comprehensive logging** with timestamps
- ✅ **5 core tests** covering all major issues

**Quick Start:**
```bash
pip install webrtcvad vosk pyaudio pyttsx3
python3 test_voice_diagnostic_standalone.py
```

### 2. **Integrated Diagnostic Script**
**File:** `test_voice_diagnostic_comprehensive.py`

- Uses existing app/ components
- More detailed integration testing
- Requires app modules to be working

**Usage:**
```bash
python3 test_voice_diagnostic_comprehensive.py --test multiturn
```

### 3. **Documentation**

- **`QUICK_DIAGNOSTIC_START.md`** - Fast start guide
- **`DIAGNOSTIC_COMPREHENSIVE_GUIDE.md`** - Detailed reference
- **`DIAGNOSTIC_TOOLS_SUMMARY.md`** - This file

---

## 🎯 What Problems Do These Tools Solve?

### Problem 1: Unreliable Full-Utterance Capture

**Symptoms:**
- First syllables cut off ("lasses" instead of "hey glasses")
- Last words missing ("what time" instead of "what time is it")

**How Diagnostics Help:**
- Logs exact audio capture duration
- Shows VAD frame-by-frame decisions
- Compares captured vs. expected duration
- Identifies pre-roll/hangover issues

**Example Log:**
```
[00:02.345] [MIC] 🗣️  Voice detected
[00:04.567] [MIC] 🔇 Silence detected, stopping
[00:04.678] [MIC] ✓ Captured 2.22s
[00:04.890] [STT] 📝 "lasses what time is it"  # ❌ Missing "hey g"
```

**Fix:** Increase `pre_roll_frames` from 3 to 5

### Problem 2: Inconsistent Wake Word Detection

**Symptoms:**
- Wake word sometimes not recognized
- False positives (activates without wake word)

**How Diagnostics Help:**
- Tests wake word detection explicitly
- Logs transcription vs. wake word match
- Measures detection accuracy

**Example Log:**
```
[00:04.890] [STT] 📝 "hey glasses what time is it"
[00:04.901] [WAKE] ✓ Wake word detected!
```

**Fix:** If transcription correct but wake word not detected → check matching logic

### Problem 3: Failure to Continue Listening After First Response

**Symptoms:**
- System responds once, then stops
- Follow-up queries require wake word again
- Microphone doesn't re-engage after TTS

**How Diagnostics Help:**
- Multi-turn test explicitly checks this
- Logs TTS completion and mic re-engagement
- Verifies conversation state persistence

**Example Log:**
```
[00:05.123] [TTS] 🔊 "It's sunny today"
[00:05.456] [TTS] ✓ Finished
[00:05.457] [CONV] 📚 History: 1 turns
[00:07.890] [MIC] 🎤 Listening...  # ✓ Mic re-engaged!
[00:08.123] [STT] 📝 "what about tomorrow"  # ✓ No wake word needed!
```

**Fix:** If mic doesn't re-engage → TTS blocking issue (pyttsx3 bug)

### Problem 4: Multi-turn Conversation State Lost

**Symptoms:**
- Conversation history resets
- Context not maintained across turns
- Each query treated as new session

**How Diagnostics Help:**
- Logs conversation history after each turn
- Verifies history accumulation
- Checks state persistence

**Example Log:**
```
[00:05.457] [CONV] 📚 History: 1 turns
[00:08.234] [CONV] 📚 History: 2 turns  # ✓ History growing!
```

**Fix:** If history resets → state management bug

### Problem 5: Timeout Not Working

**Symptoms:**
- System waits indefinitely
- Timeout never triggers
- Can't exit conversation

**How Diagnostics Help:**
- Explicit timeout test
- Logs timeout trigger
- Verifies 15-second timing

**Example Log:**
```
[00:20.456] [MIC] ⏱️  Timeout after 15s
[00:20.457] [CONV] ⏹️  Ended: timeout
```

**Fix:** If timeout doesn't trigger → timer logic not implemented

---

## 🚀 Quick Start Guide

### Step 1: Install Dependencies

```bash
pip install webrtcvad vosk pyaudio pyttsx3
```

### Step 2: Download Vosk Model (if needed)

```bash
cd models
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
```

### Step 3: Run Diagnostics

```bash
python3 test_voice_diagnostic_standalone.py
```

### Step 4: Follow Interactive Prompts

The script will guide you through 5 tests:

1. Say "hey glasses what time is it"
2. Say "what time is it" (without wake word)
3. Multi-turn conversation test
4. Timeout test (stay silent)
5. Say "hey glasses bye glasses"

### Step 5: Review Results

Check the console output and generated JSON log file:

```bash
cat diagnostic_20250121_143022.json | jq '.'
```

---

## 📊 Understanding the Output

### Console Output Format

```
[MM:SS.mmm] [COMPONENT   ] Message
```

- **Timestamp:** Minutes:Seconds.milliseconds since start
- **Component:** Which part of the system (MIC, STT, WAKE, TTS, CONV, TEST)
- **Message:** What happened

### Color Coding

- 🟢 **Green (SUCCESS):** Test passed, feature working
- 🟡 **Yellow (WARNING):** Potential issue, needs attention
- 🔴 **Red (ERROR):** Test failed, bug detected
- ⚪ **White (INFO):** Informational message
- ⚫ **Gray (DEBUG):** Detailed debug info (--verbose only)

### Key Indicators

| Icon | Meaning |
|------|---------|
| 🎤 | Microphone listening |
| 🗣️ | Voice detected |
| 🔇 | Silence detected |
| 📝 | Transcription result |
| 🔊 | TTS speaking |
| ✓ | Success |
| ❌ | Failure |
| ⏱️ | Timeout |
| 📚 | Conversation history |

---

## 🔧 Configuration & Tuning

### Default Parameters

```python
vad_mode = 1              # VAD aggressiveness (0-3)
frame_duration_ms = 30    # Frame size
pre_roll_frames = 3       # ~90ms pre-roll
hangover_frames = 10      # ~300ms hangover
followup_timeout_sec = 15 # Timeout duration
```

### When to Adjust

| Issue | Parameter | Change |
|-------|-----------|--------|
| First syllables cut | `pre_roll_frames` | Increase to 5-7 |
| Last words cut | `hangover_frames` | Increase to 15-20 |
| Too much noise | `vad_mode` | Increase to 2-3 |
| Soft speech missed | `vad_mode` | Decrease to 0-1 |
| Timeout too short | `followup_timeout_sec` | Increase to 20-30 |

### How to Modify

Edit the script directly:

```python
# In test_voice_diagnostic_standalone.py
@dataclass
class Config:
    pre_roll_frames: int = 5  # Changed from 3
    hangover_frames: int = 15  # Changed from 10
```

---

## 📁 Output Files

### JSON Log File

**Format:** `diagnostic_YYYYMMDD_HHMMSS.json`

**Contents:**
```json
[
  {
    "timestamp": "[00:01.234]",
    "component": "MIC",
    "message": "🎤 Listening...",
    "level": "INFO"
  },
  {
    "timestamp": "[00:02.345]",
    "component": "STT",
    "message": "📝 \"hey glasses what time is it\"",
    "level": "INFO",
    "text": "hey glasses what time is it"
  }
]
```

### Analyzing Logs

**Find all errors:**
```bash
cat diagnostic_*.json | jq '.[] | select(.level == "ERROR")'
```

**Extract transcriptions:**
```bash
cat diagnostic_*.json | jq '.[] | select(.component == "STT") | .text'
```

**Check timing:**
```bash
cat diagnostic_*.json | jq '.[] | {timestamp, component, message}'
```

---

## 🐛 Troubleshooting

### Common Issues

#### 1. PyAudio Not Found

**Error:**
```
ModuleNotFoundError: No module named 'pyaudio'
```

**Fix:**
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

#### 2. Vosk Model Not Found

**Error:**
```
❌ Model not found: models/vosk-model-small-en-us-0.15
```

**Fix:**
```bash
cd models
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
```

#### 3. Microphone Permission Denied

**Error:**
```
OSError: [Errno -9996] Invalid input device
```

**Fix:**
- macOS: System Preferences → Security & Privacy → Microphone
- Grant Terminal/Python permission to access microphone

#### 4. TTS Hangs

**Error:**
```
# Script freezes after TTS
```

**Fix:**
- Don't use `--tts` flag (use simulated TTS)
- Or upgrade pyttsx3: `pip install --upgrade pyttsx3`

---

## 📈 Interpreting Test Results

### Test 1: Wake Word Detection

**✅ Pass:**
```
[WAKE] ✓ Wake word detected!
```

**❌ Fail:**
```
[STT] 📝 "hey glasses what time is it"
[WAKE] ❌ Wake word NOT detected
```
→ Wake word matching logic broken

### Test 2: No Wake Word

**✅ Pass:**
```
[WAKE] ✓ Correctly ignored (no wake word)
```

**❌ Fail:**
```
[WAKE] ⚠️  Wake word detected unexpectedly
```
→ False positive in wake word detection

### Test 3: Multi-turn

**✅ Pass:**
```
[TEST] ✓ Follow-up captured successfully!
[TEST] ✓ Conversation history retained!
```

**❌ Fail:**
```
[TEST] ❌ Follow-up not captured (timeout)
```
→ Microphone not re-engaging after TTS

### Test 4: Timeout

**✅ Pass:**
```
[TEST] ✓ Timeout triggered correctly!
```

**❌ Fail:**
```
[TEST] ❌ Timeout did not trigger
```
→ Timer logic not working

### Test 5: Exit Phrase

**✅ Pass:**
```
[TEST] ✓ Exit phrase detected!
```

**❌ Fail:**
```
[TEST] ❌ Exit phrase NOT detected
```
→ Exit phrase matching broken

---

## 🎓 Best Practices

### 1. Testing Environment

- ✅ Quiet room (minimal background noise)
- ✅ Consistent microphone position
- ✅ Same microphone as production
- ✅ Normal speaking volume

### 2. Test Methodology

- ✅ Run tests multiple times
- ✅ Test at different times of day
- ✅ Test with different speakers
- ✅ Document baseline results

### 3. Iterative Improvement

1. Run diagnostic → Identify issues
2. Adjust parameters → Re-run
3. Compare results → Verify improvement
4. Document changes → Track progress

### 4. Log Analysis

- ✅ Save all log files
- ✅ Compare before/after changes
- ✅ Look for patterns
- ✅ Track metrics over time

---

## 📚 Additional Resources

### Documentation Files

1. **`QUICK_DIAGNOSTIC_START.md`**
   - Fast start guide
   - Common issues
   - Quick fixes

2. **`DIAGNOSTIC_COMPREHENSIVE_GUIDE.md`**
   - Detailed explanations
   - Advanced configuration
   - In-depth troubleshooting

3. **`DIAGNOSTIC_TOOLS_SUMMARY.md`** (this file)
   - Overview of all tools
   - Complete reference
   - Best practices

### Script Files

1. **`test_voice_diagnostic_standalone.py`** ⭐
   - Standalone, self-contained
   - No app/ dependencies
   - Recommended for most users

2. **`test_voice_diagnostic_comprehensive.py`**
   - Integrated with app/
   - More detailed testing
   - For advanced users

---

## 🎯 Next Steps

### After Running Diagnostics

1. **Review the logs** - Identify specific issues
2. **Adjust parameters** - Tune VAD settings
3. **Fix bugs** - Address detected problems
4. **Re-test** - Verify improvements
5. **Document** - Record optimal settings

### Integration with Main App

Once diagnostics pass:

1. Apply same VAD settings to main app
2. Implement fixes for detected bugs
3. Add monitoring/logging to production
4. Set up automated testing
5. Track metrics over time

---

## ✅ Success Criteria

Your voice assistant is working correctly when:

- ✅ Wake word detected 100% of the time
- ✅ No audio clipping (first/last syllables intact)
- ✅ Follow-up queries work without wake word
- ✅ Conversation history maintained across turns
- ✅ 15-second timeout triggers correctly
- ✅ Exit phrase terminates session properly

---

## 🆘 Getting Help

If you encounter issues:

1. **Check the logs** - Most issues are logged
2. **Review documentation** - Guides cover common problems
3. **Adjust parameters** - Try different VAD settings
4. **Test incrementally** - Isolate the problem
5. **Document findings** - Track what works/doesn't

---

**Created:** 2025-01-21  
**Version:** 1.0  
**Status:** Production Ready ✅
