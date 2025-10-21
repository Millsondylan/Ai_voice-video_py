#!/bin/bash
# Glasses Voice Assistant - Quick Start Script

echo "=========================================="
echo "  Glasses Voice Assistant"
echo "=========================================="
echo ""

# Load environment
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "✅ Environment loaded"
else
    echo "⚠️  Warning: .env file not found"
fi

# Check if configuration is valid
if [ ! -f config.json ]; then
    echo "❌ Error: config.json not found"
    echo "Run: python3 configure_assistant.py"
    exit 1
fi

echo "✅ Configuration found"
echo ""

# Start the assistant
echo "Starting voice assistant..."
echo "Press Ctrl+C to stop"
echo ""

# Run with Python 3
python3 app/main.py "$@"
