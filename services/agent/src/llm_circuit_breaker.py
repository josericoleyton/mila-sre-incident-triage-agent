"""Circuit breaker for LLM model calls with automatic fallback.

When the primary model fails repeatedly, the breaker opens and routes
subsequent calls to a fallback model. After a cooldown period, it
half-opens to probe the primary model again.

States:
  CLOSED   → primary model, failures counted
  OPEN     → fallback model, cooldown timer running
  HALF_OPEN → next call probes primary; success closes, failure re-opens
"""

import logging
import time
from enum import Enum

from src.config import LLM_MODEL, LLM_FALLBACK_MODEL, FAILURE_THRESHOLD, COOLDOWN_SECONDS

logger = logging.getLogger(__name__)


class _State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Thread-safe circuit breaker for a single LLM provider path."""

    def __init__(
        self,
        primary: str = LLM_MODEL,
        fallback: str = LLM_FALLBACK_MODEL,
        failure_threshold: int = FAILURE_THRESHOLD,
        cooldown_seconds: int = COOLDOWN_SECONDS,
    ):
        self._primary = primary
        self._fallback = fallback
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds

        self._state = _State.CLOSED
        self._failure_count = 0
        self._opened_at: float = 0.0

    @property
    def model(self) -> str:
        """Return which model to use right now."""
        if self._state == _State.CLOSED:
            return self._primary

        if self._state == _State.OPEN:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self._cooldown_seconds:
                self._state = _State.HALF_OPEN
                logger.info(
                    "Circuit breaker HALF_OPEN — probing primary model %s (cooldown %.0fs elapsed)",
                    self._primary, elapsed,
                )
                return self._primary
            return self._fallback
        return self._primary

    def record_success(self) -> None:
        """Record a successful model call."""
        if self._state in (_State.HALF_OPEN, _State.OPEN):
            logger.info(
                "Circuit breaker CLOSED — primary model %s recovered",
                self._primary,
            )
        self._state = _State.CLOSED
        self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed model call."""
        self._failure_count += 1

        if self._state == _State.HALF_OPEN:
            self._open("probe failed")
            return

        if self._failure_count >= self._failure_threshold:
            self._open(f"{self._failure_count} consecutive failures")

    @property
    def state(self) -> str:
        return self._state.value

    def _open(self, reason: str) -> None:
        self._state = _State.OPEN
        self._opened_at = time.monotonic()
        logger.warning(
            "Circuit breaker OPEN — switching to fallback model %s (reason: %s)",
            self._fallback, reason,
        )



breaker = CircuitBreaker()
