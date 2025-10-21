#!/bin/bash
# Quick fix for both issues

echo "================================"
echo "FIXING BOTH ISSUES NOW"
echo "================================"
echo ""

# Issue 1: Download better Vosk model
echo "[1/3] Downloading better Vosk model (this will take a few minutes)..."
cd /Users/ai/Documents/Glasses/models/
if [ ! -f "vosk-model-en-us-0.22.zip" ]; then
    wget -q --show-progress https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip
    if [ $? -eq 0 ]; then
        echo "✅ Download complete"
    else
        echo "❌ Download failed - trying curl..."
        curl -L -O https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip
    fi
else
    echo "✅ Model already downloaded"
fi

#Issue 2: Extract model
echo "[2/3] Extracting model..."
if [ ! -d "vosk-model-en-us-0.22" ]; then
    unzip -q vosk-model-en-us-0.22.zip
    echo "✅ Model extracted"
else
    echo "✅ Model already extracted"
fi

# Issue 3: Update config
echo "[3/3] Updating config.json..."
cd /Users/ai/Documents/Glasses/
python3 << 'PYTHON_EOF'
import json

# Read config
with open('config.json', 'r') as f:
    config = json.load(f)

# Update to use better model
config['vosk_model_path'] = 'models/vosk-model-en-us-0.22'

# Write back
with open('config.json', 'w') as f:
    json.dump(config, f, indent=2)

print("✅ Config updated")
PYTHON_EOF

echo ""
echo "================================"
echo "✅ ALL FIXES APPLIED!"
echo "================================"
echo ""
echo "Changes made:"
echo "1. Downloaded vosk-model-en-us-0.22 (1.8GB - much more accurate)"
echo "2. Updated config.json to use the new model"
echo ""
echo "Next steps:"
echo "1. Run: ./start_assistant.sh"
echo "2. Say: 'hey glasses'"
echo "3. Say: 'what is gold' (should now work correctly!)"
echo ""
