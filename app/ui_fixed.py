from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ai.vlm_client import VLMClient
from app.audio.stt import StreamingTranscriber
from app.audio.tts import SpeechSynthesizer
from app.audio.wake import WakeWordListener
from app.audio.wake_hybrid import create_wake_listener
from app.segment import SegmentRecorder
from app.session import SessionCallbacks, SessionManager, SessionState
from app.util.config import AppConfig


class TimelineBar(QtWidgets.QWidget):
    """Compact horizontal indicator following the FSM."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._labels: dict[SessionState | str, QtWidgets.QLabel] = {}

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        stages = [
            ("wake", "Wake"),
            (SessionState.RECORDING, "Recording"),
            (SessionState.THINKING, "Thinking"),
            (SessionState.SPEAKING, "Speaking"),
            (SessionState.AWAIT_FOLLOWUP, "Await 15s"),
        ]

        for key, label_text in stages:
            label = QtWidgets.QLabel(label_text)
            label.setStyleSheet("color: #666; font-weight: 400;")
            layout.addWidget(label)
            self._labels[key] = label

        layout.addStretch(1)
        self.setFixedHeight(24)

    def set_state(self, state: SessionState | str) -> None:
        key_value = state.value if isinstance(state, SessionState) else state
        for entry, label in self._labels.items():
            comparison = entry.value if isinstance(entry, SessionState) else entry
            if comparison == key_value:
                label.setStyleSheet("color: #2a64f6; font-weight: 600;")
            else:
                label.setStyleSheet("color: #666; font-weight: 400;")


class GlassesWindow(QtWidgets.QMainWindow):
    wake_detected = QtCore.pyqtSignal(object)
    session_started_signal = QtCore.pyqtSignal(str)
    session_state_signal = QtCore.pyqtSignal(object, int)
    session_segment_signal = QtCore.pyqtSignal(int, object)
    session_response_signal = QtCore.pyqtSignal(int, str, dict)
    session_finished_signal = QtCore.pyqtSignal(str, str)
    error_signal = QtCore.pyqtSignal(str)

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
        self._session_running = False
        self._current_session_id: Optional[str] = None
        self._session_future: Optional[Future] = None
        self._transcripts: list[str] = []
        self._responses: list[str] = []

        self.session_manager = SessionManager(
            config=config,
            segment_recorder=segment_recorder,
            vlm_client=vlm_client,
            tts=tts,
        )

        self._callbacks = SessionCallbacks(
            session_started=lambda session_id: self.session_started_signal.emit(session_id),
            state_changed=lambda state, turn: self.session_state_signal.emit(state, turn),
            transcript_ready=lambda turn, result: self.session_segment_signal.emit(turn, result),
            response_ready=lambda turn, text, payload: self.session_response_signal.emit(turn, text, payload or {}),
            session_finished=lambda session_id, reason: self.session_finished_signal.emit(session_id, reason),
            error=lambda message: self.error_signal.emit(message),
        )

        self._setup_ui()
        self._connect_signals()
        self.start_wake_listener()

    # ------------------------------------------------------------------ UI setup
    def _setup_ui(self) -> None:
        self.setWindowTitle("Glasses Assistant")
        self.resize(640, 480)

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setSpacing(12)

        self.status_label = QtWidgets.QLabel("Idle — say the wake word, press Ctrl+G, or click Start")
        layout.addWidget(self.status_label)

        self.timeline_bar = TimelineBar()
        layout.addWidget(self.timeline_bar)

        self.start_button = QtWidgets.QPushButton("Start Session (Ctrl+G)")
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
        self.session_started_signal.connect(self._on_session_started)
        self.session_state_signal.connect(self._on_session_state_changed)
        self.session_segment_signal.connect(self._on_session_segment)
        self.session_response_signal.connect(self._on_session_response)
        self.session_finished_signal.connect(self._on_session_finished)
        self.error_signal.connect(self._on_error)

    # ----------------------------------------------------------- Wake handling
    def start_wake_listener(self) -> None:
        if self._wake_listener and self._wake_listener.is_alive():
            return

        def _on_detect(pre_roll_buffer):
            self.wake_detected.emit(pre_roll_buffer)

        try:
            self._wake_transcriber.reset()
        except RuntimeError as exc:
            self.error_signal.emit(str(exc))
            return

        # Use hybrid wake word manager (tries Porcupine, falls back to Vosk)
        try:
            listener = create_wake_listener(
                config=self.config,
                transcriber=self._wake_transcriber,
                on_detect=_on_detect,
            )
            self._wake_listener = listener
            listener.start()
        except Exception as exc:
            self.error_signal.emit(f"Failed to start wake word listener: {exc}")

    def _stop_wake_listener(self) -> None:
        if not self._wake_listener:
            return
        listener = self._wake_listener
        self._wake_listener = None
        listener.stop()
        listener.join(timeout=1.0)

    # -------------------------------------------------------------- Session flow
    def _manual_trigger(self) -> None:
        if self._session_running:
            self._cancel_session()
            return
        self._handle_wake_trigger(None)

    def _handle_wake_trigger(self, buffer) -> None:
        if self._session_running:
            return
        self._stop_wake_listener()
        self._start_session(buffer)

    def _start_session(self, pre_roll_buffer) -> None:
        self._session_running = True
        self.timeline_bar.set_state("wake")
        self.status_label.setText("Session started — capturing audio")
        self.start_button.setText("Stop Session (Ctrl+G)")
        self.transcript_edit.clear()
        self.response_edit.clear()
        self._transcripts.clear()
        self._responses.clear()

        future = self._executor.submit(
            self.session_manager.run_session,
            callbacks=self._callbacks,
            pre_roll_buffer=pre_roll_buffer,
        )
        self._session_future = future
        future.add_done_callback(self._on_session_future_done)

    def _cancel_session(self) -> None:
        if not self._session_running:
            return
        self.status_label.setText("Stopping session…")
        self.session_manager.cancel()

    # ----------------------------------------------------------- UI callbacks
    def _on_session_started(self, session_id: str) -> None:
        self._current_session_id = session_id

    def _on_session_state_changed(self, state: SessionState, turn_index: int) -> None:
        if state == SessionState.IDLE:
            self.timeline_bar.set_state("wake")
        else:
            self.timeline_bar.set_state(state)
        if state == SessionState.RECORDING:
            self.status_label.setText(f"Listening… speak now (turn {turn_index + 1})")
        elif state == SessionState.THINKING:
            self.status_label.setText("Thinking…")
        elif state == SessionState.SPEAKING:
            self.status_label.setText("Speaking…")
        elif state == SessionState.AWAIT_FOLLOWUP:
            self.status_label.setText("Awaiting follow-up (15s window)")
        elif state == SessionState.IDLE:
            self.status_label.setText("Idle — say the wake word, press Ctrl+G, or click Start")
            self.start_button.setText("Start Session (Ctrl+G)")

    def _on_session_segment(self, turn_index: int, result) -> None:
        text = result.clean_transcript or ""
        if len(self._transcripts) <= turn_index:
            self._transcripts.append(text)
        else:
            self._transcripts[turn_index] = text
        display = "\n\n".join(f"Turn {i + 1}:\n{t}" for i, t in enumerate(self._transcripts) if t)
        self.transcript_edit.setPlainText(display)

    def _on_session_response(self, turn_index: int, text: str, _payload: dict) -> None:
        if len(self._responses) <= turn_index:
            self._responses.append(text)
        else:
            self._responses[turn_index] = text
        display = "\n\n".join(f"Turn {i + 1}:\n{t}" for i, t in enumerate(self._responses) if t)
        self.response_edit.setPlainText(display)

    def _on_session_finished(self, session_id: str, reason: str) -> None:
        self._session_running = False
        self._current_session_id = session_id
        self._session_future = None
        self.timeline_bar.set_state("wake")
        self.status_label.setText(f"Session ended ({reason})")
        self.start_button.setText("Start Session (Ctrl+G)")
        self.start_wake_listener()

    def _on_session_future_done(self, future: Future) -> None:
        try:
            future.result()
        except Exception as exc:  # pragma: no cover
            self.error_signal.emit(str(exc))

    # ------------------------------------------------------------------ errors
    def _on_error(self, message: str) -> None:
        QtWidgets.QMessageBox.critical(self, "Glasses Error", message)
        self._session_running = False
        self._current_session_id = None
        self.status_label.setText("Error encountered — check logs")
        self.start_button.setText("Start Session (Ctrl+G)")
        self.start_wake_listener()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
        if self._session_running:
            self.session_manager.cancel()
        if self._wake_listener:
            self._wake_listener.stop()
            self._wake_listener.join(timeout=1.0)
        self._executor.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)
