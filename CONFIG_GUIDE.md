# Configuration Guide

This document explains all parameters in `config.json` and how they affect the voice assistant's behavior.

## Speech Capture Parameters

### `silence_ms: 1800`
**Purpose**: Duration of silence (in milliseconds) that marks the end of user speech.

**Current Value**: 1800ms (1.8 seconds)

**Explanation**: After the user stops speaking, the system waits this long before considering the utterance complete. Industry standard is 0.5-0.8 seconds, but we use 1.8s for extra safety to prevent cutting off mid-sentence when the user takes a breath or brief pause.

**Tuning**:
- **Too low** (< 1000ms): May cut off speech prematurely during natural pauses
- **Too high** (> 3000ms): Unnecessary delay before processing begins
- **Recommended range**: 1500-2500ms for natural conversation

---

### `vad_aggressiveness: 1`
**Purpose**: Voice Activity Detection (VAD) sensitivity level.

**Current Value**: 1 (fairly sensitive)

**Explanation**: Controls how strict the VAD is in classifying audio as speech vs. silence. Lower values are more sensitive and will catch soft speech; higher values filter out more background noise but may miss quiet words.

**Range**: 0-3
- `0` = Most sensitive (catches all speech, including very quiet)
- `1` = Fairly sensitive (recommended for general use)
- `2` = Moderately aggressive (filters more background noise)
- `3` = Most aggressive (strict, may miss soft speech)

**Tuning**:
- **Quiet environment**: Use 0-1 to ensure all speech is captured
- **Noisy environment**: Use 2-3 to filter background noise
- **Current setting (1)**: Good balance for most environments

---

### `pre_roll_ms: 600`
**Purpose**: Amount of audio (in milliseconds) to buffer BEFORE speech is detected.

**Current Value**: 600ms (0.6 seconds)

**Explanation**: The system continuously buffers audio in a rolling buffer. When speech is detected, it includes this pre-buffered audio in the recording. This ensures the first syllables aren't lost even if the user starts speaking immediately after the wake word.

**Tuning**:
- **Too low** (< 300ms): May miss the beginning of speech
- **Too high** (> 1000ms): Wastes memory, no additional benefit
- **Recommended range**: 400-800ms

---

### `min_speech_frames: 5`
**Purpose**: Minimum number of speech frames required before silence detection is allowed.

**Current Value**: 5 frames

**Explanation**: Prevents the system from stopping recording too early (e.g., after just one word). The system must detect at least this many frames of speech before it will consider ending the recording based on silence.

**Frame Duration**: With `chunk_samples: 320` and `sample_rate_hz: 16000`, each frame is 20ms. So 5 frames = 100ms of speech minimum.

**Tuning**:
- **Too low** (< 3): May stop after just 1-2 words
- **Too high** (> 10): No real benefit, just a longer minimum
- **Recommended range**: 3-8 frames

---

### `tail_padding_ms: 500`
**Purpose**: Amount of audio (in milliseconds) to capture AFTER silence is detected.

**Current Value**: 500ms (0.5 seconds)

**Explanation**: When the silence threshold is reached, the system continues recording for this additional duration. This ensures trailing words or syllables that occur right at the silence boundary are fully captured.

**Tuning**:
- **Too low** (< 200ms): May cut off the last syllable
- **Too high** (> 800ms): Adds unnecessary delay
- **Recommended range**: 300-600ms

---

## Wake Word Parameters

### `wake_variants: ["hey glasses", "hey-glasses", "hay glasses", "a glasses", "hey glass"]`
**Purpose**: List of accepted wake word phrases, including phonetic variations.

**Explanation**: The wake word detector uses fuzzy matching and will trigger on any of these variants. This handles speech-to-text quirks where "hey glasses" might be transcribed as "hi glasses" or "hey glass". The system accepts close matches to reduce false negatives.

**Adding More Variants**:
If you find the wake word is often missed, add common misrecognitions:
```json
"wake_variants": [
  "hey glasses",
  "hi glasses",
  "hay glasses",
  "hey glass",
  "hi glass",
  "a glasses"
]
```

---

### `wake_sensitivity: 0.65`
**Purpose**: Wake word detection sensitivity (0.0 to 1.0).

**Current Value**: 0.65 (moderate-high sensitivity)

**Explanation**: Controls how many consecutive matches are required before triggering. Lower values make the wake word easier to trigger (fewer false negatives but more false positives). Higher values make it stricter (fewer false positives but may miss valid wake words).

**Tuning**:
- **0.3-0.5**: Very sensitive (may have false triggers)
- **0.5-0.7**: Balanced (recommended for most use)
- **0.7-0.9**: Strict (fewer false triggers, may miss some valid ones)

---

## Audio Hardware Parameters

### `sample_rate_hz: 16000`
**Purpose**: Audio sample rate in Hertz.

**Current Value**: 16000 Hz (16 kHz)

**Explanation**: Standard sample rate for speech recognition. Higher rates (e.g., 44.1kHz) are used for music, but 16kHz is optimal for voice and is what Vosk expects.

**Do NOT change** unless you're using a different STT model that requires a different rate.

---

### `chunk_samples: 320`
**Purpose**: Number of audio samples per processing chunk.

**Current Value**: 320 samples

**Explanation**: With 16kHz sample rate, 320 samples = 20ms of audio per frame. This is the standard frame size for WebRTC VAD.

**Do NOT change** unless you understand the implications for VAD and STT timing.

---

### `mic_device_name: null`
**Purpose**: Specific microphone device to use.

**Current Value**: `null` (use system default)

**Explanation**: If `null`, the system uses the default microphone. You can specify a device name if you have multiple microphones.

**Finding Device Names**:
Run this Python code to list available devices:
```python
import pyaudio
p = pyaudio.PyAudio()
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    print(f"{i}: {info['name']}")
```

Then set in config:
```json
"mic_device_name": "MacBook Pro Microphone"
```

---

## Text-to-Speech Parameters

### `tts_voice: null`
**Purpose**: Specific TTS voice to use.

**Current Value**: `null` (use system default)

**Explanation**: On macOS, you can specify a voice like "Samantha" or "Alex". If `null`, uses the system default voice.

**Finding Available Voices** (macOS):
```bash
say -v '?'
```

Then set in config:
```json
"tts_voice": "Samantha"
```

---

### `tts_rate: 175`
**Purpose**: Speech rate (words per minute).

**Current Value**: 175 WPM

**Explanation**: Controls how fast the assistant speaks. Default is typically 175-200 WPM.

**Tuning**:
- **120-150**: Slow, very clear
- **160-180**: Normal conversational pace
- **190-220**: Fast, might be harder to understand
- **Recommended range**: 160-190 WPM

---

## Video/Camera Parameters

### `camera_source: "0"`
**Purpose**: Camera device index.

**Current Value**: "0" (first camera)

**Explanation**: Specifies which camera to use for video frames (if your assistant has vision capabilities).

---

### `video_width_px: 960`
**Purpose**: Video frame width in pixels.

**Current Value**: 960 pixels

**Explanation**: Captured video frames are resized to this width (maintaining aspect ratio).

---

### `center_crop_ratio: 0.38`
**Purpose**: Center crop ratio for video frames.

**Current Value**: 0.38 (38% crop)

**Explanation**: Crops the center portion of video frames to focus on the most relevant area.

---

### `frame_sample_fps: 2`
**Purpose**: Frame sampling rate (frames per second).

**Current Value**: 2 FPS

**Explanation**: How often to sample video frames during a recording.

---

### `frame_max_images: 6`
**Purpose**: Maximum number of video frames to capture per turn.

**Current Value**: 6 frames

**Explanation**: Limits the number of frames sent to the vision model.

---

### `max_segment_s: 45`
**Purpose**: Maximum recording duration in seconds.

**Current Value**: 45 seconds

**Explanation**: Hard limit on how long a single speech segment can be. Prevents infinite recording if silence detection fails.

---

## Porcupine Wake Word (Alternative)

### `prefer_porcupine: true`
**Purpose**: Whether to use Porcupine wake word engine instead of Vosk.

**Current Value**: `true`

**Explanation**: Porcupine is a specialized wake word engine that may be more accurate than general-purpose STT for wake word detection.

---

### `porcupine_sensitivity: 0.7`
**Purpose**: Porcupine wake word sensitivity (0.0 to 1.0).

**Current Value**: 0.7

**Explanation**: Similar to `wake_sensitivity`, but specific to Porcupine engine.

---

### `porcupine_keyword_path: null`
**Purpose**: Path to custom Porcupine keyword file.

**Current Value**: `null`

**Explanation**: If you've trained a custom wake word with Porcupine, specify the `.ppn` file path here.

---

## Quick Tuning Scenarios

### Scenario: Speech gets cut off mid-sentence
**Symptoms**: User's sentences are truncated before they finish speaking.

**Fix**:
```json
{
  "silence_ms": 2500,
  "tail_padding_ms": 600,
  "vad_aggressiveness": 0
}
```

---

### Scenario: Wake word rarely detected
**Symptoms**: "Hey glasses" doesn't trigger the assistant reliably.

**Fix**:
```json
{
  "wake_sensitivity": 0.4,
  "vad_aggressiveness": 1,
  "wake_variants": [
    "hey glasses",
    "hi glasses",
    "hay glasses",
    "hey glass",
    "hi glass"
  ]
}
```

---

### Scenario: Too many false wake word triggers
**Symptoms**: Assistant wakes up when you didn't say the wake word.

**Fix**:
```json
{
  "wake_sensitivity": 0.8,
  "vad_aggressiveness": 2
}
```

---

### Scenario: Background noise causes issues
**Symptoms**: Assistant picks up background conversations or TV audio.

**Fix**:
```json
{
  "vad_aggressiveness": 3,
  "min_speech_frames": 8,
  "wake_sensitivity": 0.75
}
```

---

### Scenario: First word of sentence is cut off
**Symptoms**: The beginning of user's speech is missing.

**Fix**:
```json
{
  "pre_roll_ms": 800
}
```

---

## Testing Configuration Changes

After changing config.json:

1. **Stop the assistant** (Ctrl+C)
2. **Restart the assistant** (`./start_assistant.sh`)
3. **Test with the wake word** and speak a full sentence
4. **Check debug logs** to verify behavior
5. **Iterate** if needed

## Backup Your Config

Before making changes, back up your working configuration:
```bash
cp config.json config.json.backup
```

To restore:
```bash
cp config.json.backup config.json
```

---

## Current Optimized Settings Summary

Your current config is optimized for:
- ✅ **Full utterance capture** without truncation (silence_ms: 1800)
- ✅ **Sensitive speech detection** (vad_aggressiveness: 1)
- ✅ **No missed first syllables** (pre_roll_ms: 600)
- ✅ **No cut-off endings** (tail_padding_ms: 500)
- ✅ **Reliable wake word** with variants and moderate sensitivity
- ✅ **Natural conversation flow** with proper timing

These settings are more generous than the minimum spec, providing a safe margin for reliable operation in most environments.
