# Glasses Desktop Prototype

Voice-activated vision assistant prototype that records synchronized audio/video segments and queries a multimodal model.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
curl -L -o models/vosk-model-small-en-us-0.15.zip https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip -q models/vosk-model-small-en-us-0.15.zip -d models
```

The repo already includes a ready-to-use `config.json` pointing at `models/vosk-model-small-en-us-0.15`. You can override defaults via environment variables or by editing that file. `.env` is pre-populated for Together.ai with model `openai/gpt-oss-20b`; the same API key is provided via both `VLM_API_KEY` and `TOGETHER_API_KEY`. Swap in your own credentials if needed.

## Running

```bash
python app/main.py
```

Say "hey glasses" or press `Ctrl+G` to start recording. Speak your query, then pause (≥ 800 ms) or say "done" to stop. The assistant samples frames, calls the configured VLM, speaks the reply, and archives the session in `~/GlassesSessions/`.

## Chat-First Vision Behavior

The assistant intelligently determines whether to use vision based on your intent, optimizing token usage and providing more natural conversational interactions.

### How It Works

**Vision is ONLY used when you ask about the scene:**
- Deictic/identifying queries: "what is this/that?", "look at...", "see this...", "identify...", "is this..."
- OCR/reading queries: "read this", "what does it say?", "text on...", "label", "sign", "price", "serial number"
- Visual questions: "what color...", "where is...", "how many..."

**Vision is NOT used for normal chat:**
- Greetings: "hi", "hello", "hey", "good morning"
- Small talk: "how are you?", "what's up?"
- General Q&A that doesn't require seeing

### Behavior Examples

**Example 1: Greeting**
```
User: "Hey glasses... Hi there!"
Assistant: "Hi! How can I help you?"
```
→ **No images sent.** Pure chat response, no scene commentary.

**Example 2: Deictic Query**
```
User: "Hey glasses... What is that?"
Assistant: "That's a coffee mug."
```
→ **Up to 6 images sent.** Center-cropped frames identify the main object in focus.

**Example 3: OCR Query**
```
User: "Hey glasses... Read this price tag."
Assistant: "$24.99"
```
→ **Up to 6 images sent.** Text extraction, no background description.

**Example 4: General Question**
```
User: "Hey glasses... What's the capital of France?"
Assistant: "Paris."
```
→ **No images sent.** Knowledge-based response, ignores video.

### Technical Details

- **Intent Detection**: Conservative pattern matching ensures vision is only used when clearly needed
- **Frame Processing**: When vision is required, frames are:
  - Sampled at 2 FPS (max 6 frames)
  - Center-cropped to 38% (simulates pointing at center object)
  - Resized to ≤960px width
  - JPEG-encoded for token efficiency
- **Token Savings**: Chat queries use ~95% fewer tokens by skipping image encoding
- **Response Cleanup**: If the model accidentally references images when none were sent, prefixes like "I see..." are automatically stripped

### Configuration

All thresholds are configurable in `config.json`:
```json
{
  "silence_ms": 800,           // Silence threshold to end recording
  "max_segment_s": 30,         // Maximum recording duration
  "frame_sample_fps": 2,       // Frames per second to sample
  "frame_max_images": 6,       // Maximum frames to send to VLM
  "video_width_px": 960,       // Maximum frame width
  "center_crop_ratio": 0.38    // Center crop ratio (0.0-1.0)
}
```

Override via environment variables (e.g., `GLASSES_FRAME_MAX_IMAGES=4`) or directly edit `config.json`.
