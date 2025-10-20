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

Say “hey glasses” or press `Ctrl+G` to start recording. Speak your query, then pause (≥ 800 ms) or say “done” to stop. The assistant samples frames, calls the configured VLM, speaks the reply, and archives the session in `~/GlassesSessions/`.
