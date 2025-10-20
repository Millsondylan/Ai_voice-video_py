# Complete Implementation Guide: Session FSM + Full Capture + Echo Prevention

## 🎯 What's Been Built

### Core Infrastructure (✅ Complete)

1. **Structured Logging** (`app/util/structured_log.py`)
   - JSON-formatted event logs with timestamps
   - Events: wake, segment, session, VAD, STT, TTS, model
   - Enables timeline reconstruction

2. **Session FSM** (`app/session.py`)
   - States: Idle → Recording → Thinking → Speaking → AwaitFollowup
   - Manages conversation history and context
   - 15-second followup timeout
   - "bye glasses" exit detection

3. **Artifact Saving** (`app/util/artifacts.py`)
   - Saves per-turn: mic_raw.wav, segment.mp4, stt_final.txt, model_output.txt, timeline.txt
   - Directory: `~/GlassesSessions/<session_id>/turn_N/`

4. **Audio I/O Controller** (`app/audio/audioio.py`)
   - Mic muting during TTS (prevents echo)
   - 150ms grace period after TTS
   - Thread-safe operations

5. **Enhanced TTS** (`app/audio/tts.py`)
   - Structured logging with turn index
   - Retry logic with fallback

6. **Pre-Roll Buffer** (`app/audio/wake.py` + `app/audio/capture.py`)
   - Rolling buffer in wake word detection
   - Passed to segment capture
   - **Captures first syllable!**

---

## 🔧 Integration Needed

The modules are built, but need to be wired into the UI. Here's exactly what to do:

### Step 1: Update UI to Use Session Manager

**File: `app/ui.py`**

Add imports and initialize session manager:

```python
# Add to imports (top of file)
from app.session import SessionManager, SessionState
from app.util.structured_log import reset_structured_logger
from app.util.artifacts import create_session_artifacts
from app.audio.audioio import get_audio_io

# In __init__ (around line 43), add:
self._session_manager = SessionManager(followup_timeout_ms=15000)
self._current_artifacts = None
self._audio_io = get_audio_io()
```

### Step 2: Start Session on Wake Word

```python
# Modify _handle_wake_trigger (line ~123):
def _handle_wake_trigger(self) -> None:
    if self._recording:
        return

    # Stop wake listener
    if self._wake_listener:
        self._wake_listener.stop()
        self._wake_listener = None

    # Start new session
    session = self._session_manager.start_session()
    self._current_artifacts = create_session_artifacts(session.session_id)

    # Reset structured logger for this session
    reset_structured_logger(session.session_id)

    self.status_label.setText(self._session_manager.get_state_display())
    self.start_button.setText("Stop Recording (Ctrl+G)")
    self.transcript_edit.clear()
    self.response_edit.clear()
    self._recording = True

    # Start recording
    future = self._executor.submit(self._record_segment)
    future.add_done_callback(lambda _: None)
```

### Step 3: Handle Recording Complete

```python
# Modify _on_segment_completed (line ~146):
def _on_segment_completed(self, result: SegmentResult) -> None:
    self._current_segment = result
    self.transcript_edit.setPlainText(result.clean_transcript)

    session = self._session_manager.get_current_session()
    if not session:
        return

    # Check for exit phrase
    if self._session_manager.should_exit_on_phrase(result.clean_transcript):
        self._audio_io.with_tts_guard(lambda: self.tts.speak("Goodbye!"))
        self._session_manager.end_session("bye_glasses")
        self._exit_to_idle()
        return

    # Transition to Thinking
    self._session_manager.transition_to_thinking()
    self.status_label.setText(self._session_manager.get_state_display())

    # Call VLM
    future = self._executor.submit(self._call_vlm, result)
    future.add_done_callback(lambda _: None)
```

### Step 4: Handle Response Ready (Speaking → AwaitFollowup)

```python
# Modify _on_response_ready (line ~167):
def _on_response_ready(self, response: dict) -> None:
    text = response.get("text", "")
    self.response_edit.setPlainText(text)

    session = self._session_manager.get_current_session()
    if not session:
        return

    # Transition to Speaking
    self._session_manager.transition_to_speaking()
    self.status_label.setText(self._session_manager.get_state_display())

    # Speak with mic muting (prevents echo!)
    self.tts.set_turn_index(session.turn_count())
    self._audio_io.with_tts_guard(lambda: self.tts.speak(text or "I don't have an answer for that yet."))

    # Save turn
    if self._current_segment and self._current_artifacts:
        turn_artifacts = self._current_artifacts.get_turn_artifacts(session.turn_count())
        turn_artifacts.save_raw_audio(self._current_segment.audio_bytes if hasattr(self._current_segment, 'audio_bytes') else b"")
        turn_artifacts.save_stt_final(self._current_segment.clean_transcript)
        turn_artifacts.save_model_output(text)
        turn_artifacts.save_video(self._current_segment.video_path)
        turn_artifacts.save_timeline()

    session.add_turn(
        user_text=self._current_segment.clean_transcript,
        assistant_text=text,
        audio_path=self._current_segment.audio_path if self._current_segment else None,
        video_path=self._current_segment.video_path if self._current_segment else None,
        stop_reason=self._current_segment.stop_reason if hasattr(self._current_segment, 'stop_reason') else None,
        duration_ms=self._current_segment.duration_ms if hasattr(self._current_segment, 'stop_reason') else 0,
    )

    # Transition to AwaitFollowup
    self._session_manager.transition_to_await_followup()
    self.status_label.setText(self._session_manager.get_state_display())
    self._recording = False

    # Start followup listener
    self._start_followup_listener()
```

### Step 5: Implement Followup Listener

```python
# Add new method to UI:
def _start_followup_listener(self):
    """Start a timer to check for followup timeout and speech."""
    # Check every 500ms
    QtCore.QTimer.singleShot(500, self._check_followup_state)

def _check_followup_state(self):
    """Check followup state and handle transitions."""
    if not self._session_manager.is_in_followup():
        return

    # Check timeout
    if self._session_manager.check_followup_timeout():
        self._exit_to_idle()
        return

    # Still in followup - check again
    QtCore.QTimer.singleShot(500, self._check_followup_state)

def _exit_to_idle(self):
    """Exit session and return to wake word listening."""
    # Save session summary
    if self._current_artifacts and self._session_manager.get_current_session():
        session = self._session_manager.get_current_session()
        from app.util.artifacts import generate_session_summary
        summary = generate_session_summary(
            session.session_id,
            session.turns,
            session.duration_seconds(),
            "session_ended"
        )
        self._current_artifacts.save_session_summary(summary)

    self._session_manager.end_session("completed")
    self._current_artifacts = None
    self._recording = False
    self.status_label.setText("Idle — say the wake word, press Ctrl+G, or click Start")
    self.start_button.setText("Start Recording (Ctrl+G)")
    self.start_wake_listener()
```

### Step 6: Enable Followup Speech Detection

The key is: when in AwaitFollowup, if user speaks, continue the session!

Two approaches:

**Option A: Manual trigger during followup** (Simplest)
- User presses Ctrl+G during AwaitFollowup
- Triggers new recording in same session

**Option B: Auto-detect speech** (Full implementation)
- Run VAD in background during AwaitFollowup
- When speech detected, automatically start recording
- Requires background VAD thread

For now, implement **Option A** (manual trigger):

```python
# Modify _manual_trigger (line ~116):
def _manual_trigger(self) -> None:
    # If in followup, continue session
    if self._session_manager.is_in_followup():
        self._session_manager.transition_to_recording_from_followup()
        self.status_label.setText(self._session_manager.get_state_display())
        self._recording = True
        future = self._executor.submit(self._record_segment)
        future.add_done_callback(lambda _: None)
        return

    # If recording, stop
    if self._recording:
        self.segment_recorder.request_stop()
        self.status_label.setText("Stopping…")
        return

    # Otherwise, start new session
    self._handle_wake_trigger()
```

---

## 📊 Expected Log Output

When working correctly, structured logs show:

```json
{"timestamp_ms": 1234567890, "event": "wake.detected", "wake_word": "hey glasses"}
{"timestamp_ms": 1234567891, "event": "session.start", "session_id": "abc12345"}
{"timestamp_ms": 1234567892, "event": "session.state_change", "from_state": "Idle", "to_state": "Recording", "reason": "wake_detected"}
{"timestamp_ms": 1234568000, "event": "vad.speech_detected", "turn_index": 0}
{"timestamp_ms": 1234568100, "event": "segment.stop", "turn_index": 0, "stop_reason": "silence", "duration_ms": 3200, "text_len": 25}
{"timestamp_ms": 1234568101, "event": "session.state_change", "from_state": "Recording", "to_state": "Thinking"}
{"timestamp_ms": 1234568500, "event": "session.state_change", "from_state": "Thinking", "to_state": "Speaking"}
{"timestamp_ms": 1234568501, "event": "tts.start", "turn_index": 0, "text_preview": "The weather today is sunny..."}
{"timestamp_ms": 1234570000, "event": "tts.complete", "turn_index": 0, "duration_ms": 1499}
{"timestamp_ms": 1234570001, "event": "session.state_change", "from_state": "Speaking", "to_state": "AwaitFollowup"}
```

---

## 🧪 Testing

### Test 1: Pre-Roll Buffer (First Syllable)
```
1. Say "hey glasses"
2. Immediately say "hello world"
3. Check transcript

✅ Expected: "hello world" (complete, not "ello world")
```

### Test 2: Conversation Continues
```
1. Say "hey glasses"
2. Say "what's the weather"
3. Wait for TTS response
4. Press Ctrl+G (or wait for auto-detect)
5. Say "and tomorrow"
6. Wait for response

✅ Expected: 2 turns, both captured
```

### Test 3: 15-Second Timeout
```
1. Say "hey glasses"
2. Say "hello"
3. Wait for response
4. Wait 15+ seconds (don't speak)

✅ Expected: Session ends, returns to Idle
```

### Test 4: Exit on "bye glasses"
```
1. Say "hey glasses"
2. Say "tell me a joke"
3. Wait for response
4. Say "bye glasses"

✅ Expected: TTS says "Goodbye!", session ends
```

### Test 5: No Echo
```
1. Start session
2. Ask question
3. During TTS response, check logs for "🔇 Microphone MUTED"
4. After TTS, check logs for "🎤 Microphone UNMUTED"

✅ Expected: No echo in next recording
```

### Test 6: Artifacts Saved
```
1. Complete a session with 2 turns
2. Check ~/GlassesSessions/<session_id>/
3. Verify folders: turn_0/, turn_1/
4. Verify files in each: mic_raw.wav, stt_final.txt, model_output.txt, timeline.txt

✅ Expected: All files present
```

---

## 📁 File Summary

### Created (Infrastructure):
- ✅ `app/util/structured_log.py` - JSON event logging
- ✅ `app/session.py` - Session FSM
- ✅ `app/util/artifacts.py` - Artifact saving
- ✅ `app/audio/audioio.py` - Mic muting controller

### Modified:
- ✅ `app/audio/tts.py` - Structured logging, turn index
- ✅ `app/audio/wake.py` - Rolling buffer (already done)
- ✅ `app/audio/capture.py` - Accepts pre_roll_buffer (already done)
- ⏳ `app/ui.py` - **NEEDS INTEGRATION** (steps above)

---

## 🚀 Quick Start

1. **Backup UI**: `cp app/ui.py app/ui.py.backup`
2. **Apply changes**: Follow Steps 1-6 above
3. **Test pre-roll**: Test 1
4. **Test conversation**: Test 2-4
5. **Check artifacts**: Test 6

---

## 🐛 Debugging

### Issue: "Still losing first syllable"
**Check**:
- Is pre_roll_buffer being passed to run_segment?
- Add print in capture.py to verify buffer received

**Fix**: See `FIXES_APPLIED_AND_NEXT_STEPS.md`

### Issue: "Session doesn't continue"
**Check**:
- Is _session_manager.transition_to_await_followup() called?
- Is _start_followup_listener() running?
- Check session state with print(self._session_manager.get_timeline_state())

### Issue: "Hearing echo"
**Check**:
- Is audio_io.with_tts_guard() being used?
- Check logs for "🔇 Microphone MUTED"
- Verify 150ms grace period after TTS

### Issue: "No artifacts saved"
**Check**:
- Is _current_artifacts initialized?
- Check ~/GlassesSessions/ exists
- Verify permissions

---

## 📝 Configuration

Add to `config.json`:
```json
{
  "followup_timeout_s": 15,
  "exit_phrases": ["bye glasses", "goodbye glasses"],
  "save_artifacts": true,
  "artifacts_base_dir": "~/GlassesSessions"
}
```

---

## ✨ Result

After integration:
- ✅ Captures **all words** including first syllable
- ✅ Conversation **continues** until timeout or exit phrase
- ✅ **No echo** during TTS
- ✅ Full **diagnostic artifacts** saved per turn
- ✅ Comprehensive **structured logs** for debugging
- ✅ **Timeline visualization** of session states

**Timeline UI**: In AwaitFollowup, status shows:
`⏳ Listening... (12s timeout, or say 'bye glasses')`

Perfect debugging! 🎉
