"""
Conversation state machine with 15-second timeout and proper turn management.

This implements Fix #4: 15-SECOND TIMEOUT WITH STATE MACHINE
"""
from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class AssistantState(Enum):
    """Assistant conversation states."""
    SLEEPING = 1  # Waiting for wake word
    ACTIVE = 2  # In conversation, listening for commands
    PROCESSING = 3  # Generating/speaking response


class ConversationStateMachine:
    """
    Manages conversation state with timeout monitoring.

    Implements the state machine pattern from requirements:
    - SLEEPING: Waiting for wake word
    - ACTIVE: In conversation, listening for follow-up (15s timeout)
    - PROCESSING: Generating/speaking response

    Exit conditions:
    - User says "Bye Glasses" or similar (explicit)
    - 15 seconds of silence (implicit)
    """

    def __init__(
        self,
        listening_timeout: int = 15,
        exit_commands: Optional[list[str]] = None,
    ):
        """
        Initialize conversation state machine.

        Args:
            listening_timeout: Seconds to wait for user input before exiting
            exit_commands: List of phrases that trigger exit
        """
        self.state = AssistantState.SLEEPING
        self.listening_timeout = listening_timeout

        # Default exit commands
        self.exit_commands = exit_commands or [
            "bye glasses",
            "goodbye glasses",
            "goodbye",
            "exit",
            "stop listening",
            "stop",
        ]

        # Activity tracking
        self.last_activity_time = time.time()
        self.exit_event = threading.Event()
        self.state_lock = threading.Lock()

        # Timeout monitor thread
        self._monitor_thread: Optional[threading.Thread] = None

        logger.info(
            f"ConversationStateMachine initialized: {listening_timeout}s timeout, "
            f"{len(self.exit_commands)} exit commands"
        )

    def reset_activity_timer(self) -> None:
        """
        Reset the activity timer.

        Call this whenever the user speaks to prevent timeout.
        """
        self.last_activity_time = time.time()
        logger.debug("Activity timer reset")

    def start_timeout_monitor(self, on_timeout: Callable[[], None]) -> None:
        """
        Start background thread monitoring for timeouts.

        Args:
            on_timeout: Callback function called when timeout occurs
        """
        if self._monitor_thread and self._monitor_thread.is_alive():
            logger.warning("Timeout monitor already running")
            return

        self.exit_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._timeout_monitor_loop,
            args=(on_timeout,),
            daemon=True,
        )
        self._monitor_thread.start()
        logger.info("Timeout monitor started")

    def stop_timeout_monitor(self) -> None:
        """Stop the timeout monitor thread."""
        if self._monitor_thread:
            self.exit_event.set()
            self._monitor_thread.join(timeout=2.0)
            self._monitor_thread = None
            logger.info("Timeout monitor stopped")

    def _timeout_monitor_loop(self, on_timeout: Callable[[], None]) -> None:
        """
        Background thread checking for timeouts.

        Runs while in ACTIVE state and checks if enough time has passed
        since last activity.
        """
        while not self.exit_event.is_set():
            with self.state_lock:
                if self.state == AssistantState.ACTIVE:
                    elapsed = time.time() - self.last_activity_time

                    if elapsed >= self.listening_timeout:
                        logger.info(
                            f"Conversation timeout after {elapsed:.1f}s of inactivity"
                        )
                        self.state = AssistantState.SLEEPING
                        try:
                            on_timeout()
                        except Exception as e:
                            logger.error(f"Timeout callback error: {e}")
                        return

            # Check every 500ms
            self.exit_event.wait(timeout=0.5)

    def is_exit_command(self, text: str) -> bool:
        """
        Check if user said an exit phrase.

        Uses fuzzy matching to catch variations.

        Args:
            text: User's transcribed text

        Returns:
            True if text contains an exit command
        """
        if not text:
            return False

        text_lower = text.lower().strip()

        for cmd in self.exit_commands:
            if cmd in text_lower:
                logger.info(f"Exit command detected: '{cmd}' in '{text}'")
                return True

        return False

    def transition_to(self, new_state: AssistantState) -> None:
        """
        Transition to a new state.

        Args:
            new_state: State to transition to
        """
        with self.state_lock:
            if self.state != new_state:
                old_state = self.state
                self.state = new_state
                logger.info(f"State transition: {old_state.name} -> {new_state.name}")

                # Reset activity timer on state changes
                if new_state == AssistantState.ACTIVE:
                    self.reset_activity_timer()

    def get_state(self) -> AssistantState:
        """Get current state (thread-safe)."""
        with self.state_lock:
            return self.state

    def cleanup(self) -> None:
        """Clean up resources."""
        self.stop_timeout_monitor()
        logger.info("ConversationStateMachine cleaned up")
