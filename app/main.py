from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PyQt6 import QtWidgets
from vosk import Model

if __package__ is None:  # allow running `python app/main.py`
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.ai.vlm_client import VLMClient
from app.audio.stt import StreamingTranscriber
from app.audio.tts import SpeechSynthesizer
from app.segment import SegmentRecorder
from app.ui import GlassesWindow
from app.util.config import AppConfig, load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Glasses desktop assistant")
    parser.add_argument("-c", "--config", type=str, help="Path to configuration JSON file")
    return parser.parse_args()


def build_transcribers(config: AppConfig) -> tuple[StreamingTranscriber, StreamingTranscriber]:
    model_path = config.vosk_model_path or os.getenv("VOSK_MODEL_PATH")
    if not model_path:
        raise RuntimeError("Set VOSK_MODEL_PATH or provide 'vosk_model_path' in the config.")

    model = Model(model_path)
    wake_transcriber = StreamingTranscriber(sample_rate=16000, model=model)
    segment_transcriber = StreamingTranscriber(sample_rate=16000, model=model)
    return wake_transcriber, segment_transcriber


def main() -> int:
    args = parse_args()
    try:
        config = load_config(Path(args.config) if args.config else None)
    except Exception as exc:
        print(f"Failed to load configuration: {exc}", file=sys.stderr)
        return 1

    config.session_root.mkdir(parents=True, exist_ok=True)

    try:
        wake_transcriber, segment_transcriber = build_transcribers(config)
    except Exception as exc:
        print(f"Speech recognition initialization failed: {exc}", file=sys.stderr)
        return 1

    try:
        vlm_client = VLMClient(config)
    except Exception as exc:
        print(f"VLM client initialization failed: {exc}", file=sys.stderr)
        return 1

    segment_recorder = SegmentRecorder(config, segment_transcriber)
    tts = SpeechSynthesizer()

    qt_app = QtWidgets.QApplication(sys.argv)
    window = GlassesWindow(
        config=config,
        segment_recorder=segment_recorder,
        vlm_client=vlm_client,
        tts=tts,
        wake_transcriber=wake_transcriber,
    )
    window.show()
    return qt_app.exec()


if __name__ == "__main__":
    sys.exit(main())
