# Fixes Applied & Next Steps

## 🎯 Issues Identified

Based on your report:
1. **"Captures SOME words but not ALL"** - Pre-roll buffer wasn't working
2. **"After it finishes, must still be on and wait for me to reply"** - Need conversation mode
3. **"Ongoing convo with history saved"** - Need context tracking
4. **"Only exits after 15s silence or 'bye glasses'"** - Need timeout + exit phrases

---

## ✅ Fixes Already Applied

### 1. **Pre-Roll Buffer - Captures First Syllable** ✅

**Root Cause Found**:
- Wake word detection and segment recording used **separate mic streams**
- When wake word triggered, new mic opened → **first syllable already gone**

**Fix Applied**:
- **`app/audio/wake.py`**:
  - Added `_rolling_buffer` deque (300ms continuous buffer)
  - Buffer is maintained during wake word listening
  - **Buffer is passed** to callback when wake word triggers
  - Contains the wake word + speech right after = **FIRST SYLLABLE CAPTURED!**

- **`app/audio/capture.py`**:
  - Added `pre_roll_buffer` parameter
  - If buffer provided, uses it instead of reading silence
  - Feeds buffer frames to STT immediately

**Status**: ✅ Code complete, needs UI integration

### 2. **TTS Threading Issue** ✅

**Fix Applied**:
- Added proper locking in `app/audio/tts.py`
- TTS now works multiple times (verified with component test)

**Status**: ✅ Complete and tested

---

## ⏳ Remaining Work - UI Integration

The core fixes are done, but the **UI needs to be updated** to:

1. Accept the rolling buffer from wake word listener
2. Pass it to segment recording
3. Implement conversation mode loop

### Required Changes to `app/ui.py`:

#### Change 1: Accept Buffer from Wake Listener (Line ~94)
```python
# BEFORE:
def _on_detect() -> None:
    self.wake_detected.emit()

# AFTER:
def _on_detect(buffer: collections.deque) -> None:
    self._pre_roll_buffer = buffer  # Store for use in recording
    self.wake_detected.emit()
```

#### Change 2: Pass pre_roll_ms to WakeWordListener (Line ~103)
```python
listener = WakeWordListener(
    wake_variants=variants,
    on_detect=_on_detect,
    transcriber=self._wake_transcriber,
    sample_rate=self.config.sample_rate_hz,
    chunk_samples=self.config.chunk_samples,
    debounce_ms=700,
    mic_device_name=self.config.mic_device_name,
    pre_roll_ms=self.config.pre_roll_ms,  # ADD THIS LINE
)
```

#### Change 3: Add Instance Variable (Line ~43 in __init__)
```python
self._pre_roll_buffer = None
self._conversation_mode = False
self._conversation_history = []
```

#### Change 4: Pass Buffer to Segment Recording (Line ~141)
```python
# In _record_segment method:
def _record_segment(self) -> None:
    try:
        result = self.segment_recorder.record_segment(
            pre_roll_buffer=self._pre_roll_buffer  # ADD THIS
        )
        self._pre_roll_buffer = None  # Clear after use
        self.segment_completed.emit(result)
    except Exception as exc:
        self.error_occurred.emit(str(exc))
```

#### Change 5: Update SegmentRecorder.record_segment (app/segment.py Line ~42)
```python
def record_segment(self, pre_roll_buffer=None) -> SegmentResult:
    ...
    capture_result: SegmentCaptureResult = run_segment(
        mic=mic,
        stt=self.transcriber,
        config=self.config,
        stop_event=self._stop_event,
        on_chunk=_capture_frame,
        pre_roll_buffer=pre_roll_buffer,  # ADD THIS LINE
    )
```

---

## 🔄 Conversation Mode Implementation

After the above changes fix the pre-roll buffer, implement conversation mode:

### Option A: Quick Implementation (Recommended)

Modify `app/ui.py` `_on_response_ready` method to loop instead of restarting wake listener:

```python
def _on_response_ready(self, response: dict) -> None:
    text = response.get("text", "")
    self.response_edit.setPlainText(text)

    if text:
        self.tts.speak_async(text)
    else:
        self.tts.speak_async("I don't have an answer for that yet.")

    # Archive session...
    if self._current_segment:
        timestamp_key = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        archive_session(...)

    # Check for exit
    if self._should_exit_conversation(self._current_segment.clean_transcript):
        self.tts.speak_async("Goodbye!")
        self._exit_conversation_mode()
        return

    # NEW: Stay in conversation mode
    if self._conversation_mode:
        self.status_label.setText("Listening... (15s timeout, or say 'bye glasses')")
        time.sleep(1)  # Brief pause
        self._recording = True
        # Record next turn with longer timeout
        future = self._executor.submit(self._record_segment_with_timeout)
        future.add_done_callback(lambda _: None)
    else:
        # First trigger - enter conversation mode
        self._conversation_mode = True
        self.status_label.setText("Listening... (15s timeout, or say 'bye glasses')")
        self._recording = True
        future = self._executor.submit(self._record_segment_with_timeout)
        future.add_done_callback(lambda _: None)

def _record_segment_with_timeout(self) -> None:
    """Record with 15-second timeout for conversation mode."""
    original_silence = self.config.silence_ms
    self.config.silence_ms = 15000  # 15 seconds

    try:
        result = self.segment_recorder.record_segment()
        self.config.silence_ms = original_silence

        if result.clean_transcript:
            self.segment_completed.emit(result)
        else:
            self._exit_conversation_mode()
    except Exception as exc:
        self.config.silence_ms = original_silence
        self.error_occurred.emit(str(exc))

def _should_exit_conversation(self, text: str) -> bool:
    """Check if user said bye."""
    exit_phrases = ["bye glasses", "goodbye glasses", "exit", "stop"]
    text_lower = text.lower().strip()
    return any(phrase in text_lower for phrase in exit_phrases)

def _exit_conversation_mode(self) -> None:
    """Return to wake word listening."""
    self._conversation_mode = False
    self._recording = False
    self.status_label.setText("Idle — say the wake word, press Ctrl+G, or click Start")
    self.start_button.setText("Start Recording (Ctrl+G)")
    self.start_wake_listener()
```

---

## 📋 Implementation Steps

### Step 1: Test Pre-Roll Buffer Fix (Priority 1)
1. Make the 5 UI changes listed above
2. Run the app
3. Say "hey glasses" then immediately "hello world"
4. Check transcript - should be **"hello world"** not **"ello world"**

### Step 2: Implement Basic Conversation Mode (Priority 2)
1. Add the conversation mode methods to UI
2. Test: "hey glasses" → "what's the weather" → wait for response → "and tomorrow" (no wake word)
3. Should respond to second question without needing wake word

### Step 3: Add Exit Detection (Priority 3)
1. Implement `_should_exit_conversation()` and `_exit_conversation_mode()`
2. Test: Say "bye glasses" during conversation
3. Should exit and return to wake word listening

### Step 4: Add Timeout (Priority 4)
1. Implement 15-second silence timeout
2. Test: Start conversation, wait 15+ seconds
3. Should automatically exit

---

## 🧪 Testing Commands

### Quick Test (Pre-Roll Only):
```bash
.venv/bin/python3 app/main.py
# Say: "hey glasses" (wait for recording to start)
# Immediately say: "hello world"
# Check transcript shows: "hello world" (not "ello world")
```

### Full Test (With Conversation Mode):
```bash
.venv/bin/python3 app/main.py
# 1. Say: "hey glasses"
# 2. Say: "what is the weather"
# 3. Wait for response
# 4. Say: "and tomorrow" (NO wake word!)
# 5. Wait for response
# 6. Say: "bye glasses"
# Should have 3 turns, then exit
```

---

## 📁 Files Modified

| File | Status | Changes |
|------|--------|---------|
| `app/audio/wake.py` | ✅ Complete | Rolling buffer, passes to callback |
| `app/audio/capture.py` | ✅ Complete | Accepts pre_roll_buffer |
| `app/audio/tts.py` | ✅ Complete | Threading fix |
| `app/segment.py` | ⏳ Needs update | Pass pre_roll_buffer parameter |
| `app/ui.py` | ⏳ Needs update | Accept buffer, conversation mode |

---

## 🆘 If You Get Stuck

### Issue: "Still losing first syllable"
**Check**:
1. Is `_pre_roll_buffer` being passed to `record_segment()`?
2. Add `print(f"[DEBUG] Buffer: {len(self._pre_roll_buffer) if self._pre_roll_buffer else 0}")` in `_record_segment`
3. Should show `[DEBUG] Buffer: 15` (or similar)

### Issue: "Conversation mode not working"
**Check**:
1. Is `_conversation_mode` flag being set to `True`?
2. Is `_on_response_ready` checking the flag and looping?
3. Add `print(f"[DEBUG] Conversation mode: {self._conversation_mode}")` after TTS

### Issue: "Won't exit conversation"
**Check**:
1. Is `_should_exit_conversation()` being called?
2. Are exit phrases correct? (lowercase matching)
3. Add `print(f"[DEBUG] Checking exit: '{text}'")` in method

---

## 📝 Complete Implementation Guide

See **[CONVERSATION_MODE_IMPLEMENTATION.md](CONVERSATION_MODE_IMPLEMENTATION.md)** for:
- Detailed code examples
- Line-by-line changes
- Alternative implementation approaches
- Full test scenarios

---

## ✨ Expected Behavior After Implementation

1. **Pre-Roll Fix**:
   - Wake word: "hey glasses"
   - You say: "hello world"
   - Transcript: "hello world" ← ALL words captured!

2. **Conversation Mode**:
   - You: "hey glasses"
   - You: "what's the weather"
   - Bot: *responds*
   - You: "and tomorrow" ← No wake word needed!
   - Bot: *responds*
   - You: "bye glasses"
   - Bot: "Goodbye!"
   - Returns to wake word listening

3. **Timeout**:
   - After 15 seconds of silence, automatically exits
   - Returns to wake word listening

---

## 🚀 Ready to Implement?

**Recommended order**:
1. ✅ Pre-roll buffer fix (5 small changes)
2. ✅ Test pre-roll works
3. ✅ Add conversation mode loop
4. ✅ Test conversation mode
5. ✅ Add exit detection
6. ✅ Add timeout

Each step can be tested independently!
