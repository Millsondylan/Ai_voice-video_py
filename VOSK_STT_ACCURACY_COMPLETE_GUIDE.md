# 🛠️ FIXING CATASTROPHIC VOSK STT ACCURACY — COMPLETE TECHNICAL GUIDE

Clear speech turning into nonsense almost always signals a configuration mismatch between your audio capture pipeline and Vosk’s expectations. This guide walks you through the exact fixes that consistently restore accurate transcription for Python voice assistants built on Vosk, PyAudio, and WebRTC VAD.

---

## 🚨 Typical Symptoms & Primary Root Causes

- **Gibberish output from clean speech**: Most often caused by sample rate or audio-format mismatches. Vosk models expect mono, 16-bit PCM audio at 16 kHz with no compression.
- **Missing or truncated words**: Aggressive VAD trimming, undersized buffers, or PyAudio overflows drop speech frames.
- **Consistently wrong vocabulary**: Small (~50 MB) models or OOV (out-of-vocabulary) words from specialized domains.
- **Inconsistent device behavior**: USB interface resampling, automatic gain control, or incorrect default device selection.

> 🔍 **Key stat**: Field debugging shows **60–70 %** of catastrophic failures trace back to sample rate mismatch, with 48 kHz input fed to 16 kHz models creating extreme spectral distortion.

---

## ✅ Critical Audio Specifications (Non-Negotiable)

| Requirement | Value | Why it matters |
|-------------|-------|----------------|
| Channels | 1 (mono) | Stereo halves effective data for each channel and confuses the recognizer. |
| Bit depth | 16-bit signed PCM | Vosk expects `pcm_s16le`; other formats distort quantization. |
| Sample rate | 16 000 Hz | Mismatches introduce aliasing; resample if hardware cannot capture at 16 kHz. |
| Encoding | Raw PCM / WAV PCM | MP3/AAC compression destroys timing cues and harmonics. |

Validate captured audio before handing it to the recognizer:

```python
import wave

def validate_audio_format(wav_path):
    """Raise early if audio is incompatible with Vosk."""
    with wave.open(wav_path, "rb") as wf:
        errors = []
        if wf.getnchannels() != 1:
            errors.append(f"Must be mono, got {wf.getnchannels()} channels")
        if wf.getsampwidth() != 2:
            errors.append(f"Must be 16-bit, got {wf.getsampwidth()*8}-bit")
        if wf.getframerate() != 16_000:
            errors.append(f"Sample rate should be 16kHz, got {wf.getframerate()}Hz")
        if wf.getcomptype() != "NONE":
            errors.append(f"Must be PCM, got {wf.getcomptype()} compression")
        if errors:
            raise ValueError("Audio format issues:\n" + "\n".join(errors))
        print("✓ Audio format valid for Vosk")
```

Normalize any bad inputs with ffmpeg:

```bash
# Convert compressed/incorrect source to Vosk-compliant PCM
ffmpeg -i input.mp3 -ar 16000 -ac 1 -sample_fmt s16 output.wav

# Re-save existing WAV with proper settings
ffmpeg -i input.wav -ar 16000 -ac 1 -acodec pcm_s16le output.wav
```

---

## 📦 Choose the Right Model

- **Upgrade immediately to `vosk-model-en-us-0.22` (≈1.8 GB)** unless you have strict vocabulary control. Expect **~20 % lower WER** versus the small 0.15 model.
- **Avoid small models** for general speech—they top out near 60 % accuracy and lack vocabulary depth.
- **For specialized domains**, adapt the language model with domain text (≥100 MB). Generic models deliver ~35 % WER on technical jargon, while adapted models drop to ~18 %.

```python
from vosk import Model, KaldiRecognizer, SetLogLevel
import json

SetLogLevel(-1)
model = Model("/path/to/vosk-model-en-us-0.22")
recognizer = KaldiRecognizer(model, 16_000)
recognizer.SetWords(True)
recognizer.SetMaxAlternatives(5)
```

Review confidence per word to spot vocabulary gaps:

```python
result = json.loads(recognizer.Result())
for word in result.get("result", []):
    if word["conf"] < 0.7:
        print(f"⚠️  Low confidence: {word['word']} ({word['conf']:.2f})")
```

---

## 🎛️ Audio Preprocessing & Noise Control

Even with perfect format, noise and low-frequency rumble damage accuracy. Adopt a lightweight preprocessing stage:

```python
import librosa
import noisereduce as nr
import soundfile as sf

def preprocess_audio(input_path, output_path):
    """Clean, normalize, and save PCM audio at 16 kHz."""
    audio, sr = librosa.load(input_path, sr=16_000)
    cleaned = nr.reduce_noise(y=audio, sr=sr, stationary=True, prop_decrease=0.75)
    cleaned = librosa.util.normalize(cleaned)
    sf.write(output_path, cleaned, sr, subtype="PCM_16")
    return cleaned
```

Add simple band-limiting filters to focus on human speech (80 Hz–8 kHz):

```python
from scipy import signal

def apply_speech_filter(samples, sr):
    """Remove rumble and hiss outside the speech band."""
    samples = signal.sosfilt(signal.butter(6, 80, "hp", fs=sr, output="sos"), samples)
    samples = signal.sosfilt(signal.butter(6, 8_000, "lp", fs=sr, output="sos"), samples)
    return samples
```

---

## 🔄 PyAudio Configuration & Buffer Reliability

### Prevent Buffer Overflows

- Increase `frames_per_buffer` to reduce callback frequency.
- Use blocking reads with `exception_on_overflow=False` or implement a queue inside the callback to decouple capture from processing.

```python
import pyaudio
from vosk import Model, KaldiRecognizer
import json

CHUNK = 4096
RATE = 16_000
p = pyaudio.PyAudio()

stream = p.open(
    format=pyaudio.paInt16,
    channels=1,
    rate=RATE,
    input=True,
    frames_per_buffer=CHUNK,
    stream_callback=None
)

model = Model("vosk-model-en-us-0.22")
rec = KaldiRecognizer(model, RATE)

while True:
    data = stream.read(CHUNK, exception_on_overflow=False)
    if rec.AcceptWaveform(data):
        print(json.loads(rec.Result())["text"])
```

For zero-drop pipelines, use a callback with a thread-safe queue:

```python
import queue
import threading

audio_queue = queue.Queue()

def audio_callback(in_data, frame_count, time_info, status_flags):
    if status_flags:
        print(f"Stream status: {status_flags}")
    audio_queue.put(in_data)
    return (None, pyaudio.paContinue)
```

Process queued audio on a worker thread so the callback never blocks.

### Resolve Sample Rate Errors

If `-9997` or similar errors appear, your device cannot record at 16 kHz. Enumerate devices and test support:

```python
p = pyaudio.PyAudio()
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    if info["maxInputChannels"] > 0:
        print(f"Device {i}: {info['name']}")
        try:
            supported = p.is_format_supported(
                16_000,
                input_device=i,
                input_channels=1,
                input_format=pyaudio.paInt16,
            )
            print(f"  16kHz supported: {supported}")
        except ValueError:
            print("  16kHz supported: False")
```

When the hardware maxes out at 44.1 kHz or 48 kHz, capture at that rate and resample before feeding Vosk:

```python
import numpy as np
from scipy import signal as sp_signal

def resample_bytes(audio_bytes, orig_rate, target_rate=16_000):
    """Resample PCM16 bytes to the recognizer rate."""
    samples = np.frombuffer(audio_bytes, dtype=np.int16)
    count = int(len(samples) * target_rate / orig_rate)
    resampled = sp_signal.resample(samples, count)
    return resampled.astype(np.int16).tobytes()
```

### Explicit Device Selection

Never rely on OS defaults—explicitly pick your microphone by index to avoid silent configuration changes:

```python
device_index = next(
    i for i in range(p.get_device_count())
    if "USB" in p.get_device_info_by_index(i)["name"]
)

stream = p.open(
    format=pyaudio.paInt16,
    channels=1,
    rate=16_000,
    input=True,
    input_device_index=device_index,
    frames_per_buffer=CHUNK,
)
```

---

## 🗣️ WebRTC VAD: Avoid Cutting Off Speech

- Start with VAD mode 1 (balanced).
- Feed frames of exactly 10, 20, or 30 ms.
- Add pre/post padding to avoid slicing words at detection boundaries.

```python
import webrtcvad

class VADBuffer:
    def __init__(self, vad_mode=1, padding_frames=10):
        self.vad = webrtcvad.Vad(vad_mode)
        self.padding_frames = padding_frames
        self.buffer = []
        self.in_speech = False
        self.remaining = 0

    def process(self, frame, sample_rate):
        is_speech = self.vad.is_speech(frame, sample_rate)
        if is_speech:
            self.in_speech = True
            self.remaining = self.padding_frames
            self.buffer.append(frame)
            return None
        if self.in_speech:
            self.buffer.append(frame)
            self.remaining -= 1
            if self.remaining <= 0:
                chunk = b"".join(self.buffer)
                self.buffer.clear()
                self.in_speech = False
                return chunk
        else:
            self.buffer.append(frame)
            if len(self.buffer) > self.padding_frames:
                self.buffer.pop(0)
        return None
```

---

## 🧱 Production-Ready Streaming Transcriber

Combine all best practices into a resilient class with noise gating, queue-based buffering, and confidence feedback:

```python
import json
import queue
import threading

import numpy as np
import pyaudio
from vosk import KaldiRecognizer, Model, SetLogLevel

class StreamingTranscriber:
    def __init__(self, model_path, rate=16_000, chunk=4096, noise_threshold=500):
        SetLogLevel(-1)
        self.model = Model(model_path)
        self.rate = rate
        self.chunk = chunk
        self.noise_threshold = noise_threshold

        self.audio_queue = queue.Queue()
        self.py_audio = pyaudio.PyAudio()
        self.device_index = self._select_device()

        self.running = False

    def _select_device(self):
        """Prefer USB/Blue microphones; fallback to system default."""
        for i in range(self.py_audio.get_device_count()):
            info = self.py_audio.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0 and (
                "USB" in info["name"] or "Blue" in info["name"]
            ):
                print(f"Selected input device: {info['name']}")
                return i
        return self.py_audio.get_default_input_device_info()["index"]

    def _callback(self, in_data, frame_count, time_info, status_flags):
        if status_flags:
            print(f"Audio status: {status_flags}")
        self.audio_queue.put(in_data)
        return (None, pyaudio.paContinue)

    def start(self):
        """Begin capturing audio and processing in a worker thread."""
        self.running = True
        self.stream = self.py_audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.rate,
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=self.chunk,
            stream_callback=self._callback,
        )
        self.stream.start_stream()
        self.worker = threading.Thread(target=self._process_loop, daemon=True)
        self.worker.start()

    def _process_loop(self):
        recognizer = KaldiRecognizer(self.model, self.rate)
        recognizer.SetWords(True)
        recognizer.SetMaxAlternatives(3)

        while self.running:
            try:
                data = self.audio_queue.get(timeout=1)
            except queue.Empty:
                continue

            if self.noise_threshold:
                samples = np.frombuffer(data, dtype=np.int16)
                samples = np.where(np.abs(samples) > self.noise_threshold, samples, 0)
                data = samples.astype(np.int16).tobytes()

            if recognizer.AcceptWaveform(data):
                self._handle_final(json.loads(recognizer.Result()))
            else:
                self._handle_partial(json.loads(recognizer.PartialResult()))

        final = json.loads(recognizer.FinalResult())
        if final.get("text"):
            self._handle_final(final)

    def _handle_partial(self, payload):
        text = payload.get("partial")
        if text:
            print(f"\rPARTIAL: {text}", end="", flush=True)

    def _handle_final(self, payload):
        text = payload.get("text", "")
        if not text:
            return

        avg_conf = 0.0
        if "result" in payload:
            confs = [word["conf"] for word in payload["result"]]
            if confs:
                avg_conf = sum(confs) / len(confs)

        print(f"\nFINAL: {text}")
        if avg_conf:
            print(f"Confidence: {avg_conf:.2f}")
        if avg_conf and avg_conf < 0.7:
            print("⚠️  Low confidence — consider fallback transcription.")

    def stop(self):
        self.running = False
        if hasattr(self, "worker"):
            self.worker.join()
        if hasattr(self, "stream"):
            self.stream.stop_stream()
            self.stream.close()
        self.py_audio.terminate()
```

---

## 🧪 Systematic Debugging Workflow

1. **Capture a 5-second sample** from your live pipeline and validate with `validate_audio_format`. Listen to confirm clarity—hardware or AGC issues become obvious.
2. **Benchmark against a known-good sample** (`test.wav` from Vosk). If this fails, the model installation or code path is broken.
3. **Cross-check with alternate STT** (e.g., `speech_recognition` with Google). If others succeed, keep debugging Vosk configuration; if all engines fail, investigate capture hardware or environment.
4. **Analyze audio quality metrics** with librosa to surface clipping, low RMS, DC offset, or poor SNR.

Example quality check:

```python
import librosa
import numpy as np

def analyze_audio_quality(path):
    y, sr = librosa.load(path, sr=None)
    max_amp = np.max(np.abs(y))
    rms = np.sqrt(np.mean(y**2))
    mean = np.mean(y)
    snr = 20 * np.log10(
        np.percentile(np.abs(y), 90) / np.percentile(np.abs(y), 10)
    )

    if max_amp > 0.95:
        print(f"⚠️  Clipping detected ({max_amp:.2f})")
    if rms < 0.01:
        print("⚠️  Audio level is very low")
    if abs(mean) > 0.01:
        print(f"⚠️  DC offset present ({mean:.4f})")
    if snr < 10:
        print(f"⚠️  Low estimated SNR ({snr:.1f} dB)")
```

---

## 🔁 When to Escalate Beyond Vosk

- **Accuracy requirements above ~90 %**: OpenAI Whisper Large reaches 95–98 % on clean English; consider it for batch tasks.
- **Need punctuation, casing, diarization**: Vosk outputs plain lowercase text. Whisper and cloud APIs include formatting and speaker tagging.
- **Heavy domain vocabulary with limited time**: Training custom Vosk graphs is labor-intensive; cloud engines with domain models may be faster.
- **Persistent live-mic issues** despite implementing this guide: Switch to Whisper or commercial APIs to confirm whether the limitation is Vosk’s acoustic model.

Hybrid strategy for cost control:

```python
def hybrid_transcribe(path):
    vosk_result, avg_conf = transcribe_with_vosk(path)
    if avg_conf >= 0.8:
        return vosk_result
    whisper_model = whisper.load_model("base")
    return whisper_model.transcribe(path)["text"]
```

---

## 🗂️ Quick Fix Sequence

1. **Immediate (≤1 hour)**: Validate audio format, set `exception_on_overflow=False`, explicitly choose the input device.
2. **High-impact (≤1 day)**: Upgrade to `vosk-model-en-us-0.22`, record and inspect live captures, enable word-level confidences.
3. **Advanced (≤1 week)**: Deploy the resilient streaming class, tune VAD padding, add noise reduction, evaluate hybrid transcription fallbacks.

Follow the above order—most teams see dramatic accuracy improvements after fixing sample rate and upgrading models, with the remaining steps polishing reliability and resilience.

---

## ✔️ Final Checklist

- [ ] Audio verified: mono, 16-bit PCM, 16 kHz, no compression.
- [ ] Large Vosk model installed and loaded successfully.
- [ ] PyAudio stream stable (no overflows, correct device, correct rate).
- [ ] VAD configured with padding; no truncated words.
- [ ] Confidence logging in place; low-confidence fallback path defined.
- [ ] Noise mitigation strategy (software preprocessing or hardware improvement) implemented.

Work through this checklist and catastrophic “gibberish” transcriptions become accurate, actionable transcripts.

