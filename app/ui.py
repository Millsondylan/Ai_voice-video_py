from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ai.vlm_client import VLMClient
from app.audio.tts import SpeechSynthesizer
from app.audio.wake import WakeWordListener
from app.audio.stt import StreamingTranscriber
from app.route import route_and_respond
from app.segment import SegmentRecorder, SegmentResult
from app.util.config import AppConfig
from app.util.fileio import archive_session


class GlassesWindow(QtWidgets.QMainWindow):
    wake_detected = QtCore.pyqtSignal()
    segment_completed = QtCore.pyqtSignal(object)
    response_ready = QtCore.pyqtSignal(object)
    error_occurred = QtCore.pyqtSignal(str)

    def __init__(
        self,
        config: AppConfig,
        segment_recorder: SegmentRecorder,
        vlm_client: VLMClient,
        tts: SpeechSynthesizer,
        wake_transcriber: StreamingTranscriber,
    ) -> None:
        super().__init__()
        self.config = config
        self.segment_recorder = segment_recorder
        self.vlm_client = vlm_client
        self.tts = tts
        self._wake_transcriber = wake_transcriber

        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="glasses")
        self._wake_listener: Optional[WakeWordListener] = None
        self._current_segment: Optional[SegmentResult] = None
        self._recording = False

        self._setup_ui()
        self._connect_signals()
        self.start_wake_listener()

    # --- UI setup -----------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setWindowTitle("Glasses Assistant")
        self.resize(640, 480)

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)

        self.status_label = QtWidgets.QLabel("Idle — say the wake word, press Ctrl+G, or click Start")
        layout.addWidget(self.status_label)

        self.start_button = QtWidgets.QPushButton("Start Recording (Ctrl+G)")
        self.start_button.clicked.connect(self._manual_trigger)
        layout.addWidget(self.start_button)

        self.transcript_edit = QtWidgets.QTextEdit()
        self.transcript_edit.setPlaceholderText("Transcript will appear here…")
        self.transcript_edit.setReadOnly(True)
        layout.addWidget(QtWidgets.QLabel("Transcript"))
        layout.addWidget(self.transcript_edit)

        self.response_edit = QtWidgets.QTextEdit()
        self.response_edit.setPlaceholderText("Assistant responses will appear here…")
        self.response_edit.setReadOnly(True)
        layout.addWidget(QtWidgets.QLabel("Response"))
        layout.addWidget(self.response_edit)

        self.setCentralWidget(central)

        shortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+G"), self)
        shortcut.activated.connect(self._manual_trigger)

    def _connect_signals(self) -> None:
        self.wake_detected.connect(self._handle_wake_trigger)
        self.segment_completed.connect(self._on_segment_completed)
        self.response_ready.connect(self._on_response_ready)
        self.error_occurred.connect(self._on_error)

    # --- Wake word -----------------------------------------------------------------

    def start_wake_listener(self) -> None:
        if self._wake_listener and self._wake_listener.is_alive():
            return

        def _on_detect() -> None:
            self.wake_detected.emit()

        try:
            self._wake_transcriber.reset()
        except RuntimeError as exc:
            self.error_occurred.emit(str(exc))
            return

        variants = list({v.lower(): v for v in ([self.config.wake_word] + self.config.wake_variants)}.values())
        listener = WakeWordListener(
            wake_variants=variants,
            on_detect=_on_detect,
            transcriber=self._wake_transcriber,
            sample_rate=self.config.sample_rate_hz,
            chunk_samples=self.config.chunk_samples,
            debounce_ms=700,
            mic_device_name=self.config.mic_device_name,
        )
        self._wake_listener = listener
        listener.start()

    def _manual_trigger(self) -> None:
        if self._recording:
            self.segment_recorder.request_stop()
            self.status_label.setText("Stopping…")
            return
        self._handle_wake_trigger()

    def _handle_wake_trigger(self) -> None:
        if self._recording:
            return
        if self._wake_listener:
            self._wake_listener.stop()
            self._wake_listener = None
        self.status_label.setText("Recording… press Ctrl+G or click Stop to end")
        self.start_button.setText("Stop Recording (Ctrl+G)")
        self.transcript_edit.clear()
        self.response_edit.clear()
        self._recording = True
        future = self._executor.submit(self._record_segment)
        future.add_done_callback(lambda _: None)  # keep reference

    # --- Recording -----------------------------------------------------------------

    def _record_segment(self) -> None:
        try:
            result = self.segment_recorder.record_segment()
            self.segment_completed.emit(result)
        except Exception as exc:  # pragma: no cover - UI surface
            self.error_occurred.emit(str(exc))

    def _on_segment_completed(self, result: SegmentResult) -> None:
        self._current_segment = result
        self.transcript_edit.setPlainText(result.clean_transcript)
        self.status_label.setText("Thinking…")
        future = self._executor.submit(self._call_vlm, result)
        future.add_done_callback(lambda _: None)

    # --- VLM interaction -----------------------------------------------------------

    def _call_vlm(self, result: SegmentResult) -> None:
        try:
            response = route_and_respond(
                config=self.config,
                vlm_client=self.vlm_client,
                transcript=result.clean_transcript,
                segment_frames=result.frames,
            )
            self.response_ready.emit(response)
        except Exception as exc:  # pragma: no cover - UI surface
            self.error_occurred.emit(str(exc))

    def _on_response_ready(self, response: dict) -> None:
        text = response.get("text", "")
        self.response_edit.setPlainText(text)
        if text:
            self.tts.speak_async(text)
        else:
            self.tts.speak_async("I don't have an answer for that yet.")

        if self._current_segment:
            timestamp_key = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            archive_session(
                self.config.session_root,
                timestamp_key,
                self._current_segment.video_path,
                self._current_segment.clean_transcript,
                response,
                audio_path=self._current_segment.audio_path,
            )

        self.status_label.setText("Idle — say the wake word, press Ctrl+G, or click Start")
        self.start_button.setText("Start Recording (Ctrl+G)")
        self._recording = False
        self.start_wake_listener()

    # --- Errors --------------------------------------------------------------------

    def _on_error(self, message: str) -> None:
        QtWidgets.QMessageBox.critical(self, "Glasses Error", message)
        self.status_label.setText("Error encountered — check logs")
        self.start_button.setText("Start Recording (Ctrl+G)")
        self.tts.speak_async(f"An error occurred. {message}")
        self._current_segment = None
        self._recording = False
        self.start_wake_listener()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
        if self._wake_listener:
            self._wake_listener.stop()
            self._wake_listener.join(timeout=1)
        self._executor.shutdown(wait=False, cancel_futures=True)
        return super().closeEvent(event)
