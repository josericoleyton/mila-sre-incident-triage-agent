"""Tests for LLM circuit breaker with model fallback."""

import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "services" / "agent"))

from src.llm_circuit_breaker import CircuitBreaker


@pytest.fixture
def cb():
    """Fresh circuit breaker: threshold=3, cooldown=2s."""
    return CircuitBreaker(
        primary="openrouter:primary-model",
        fallback="openrouter:fallback-model",
        failure_threshold=3,
        cooldown_seconds=2,
    )


# ==========================================================================
# State transitions
# ==========================================================================
class TestCircuitBreakerStates:
    def test_starts_closed(self, cb):
        assert cb.state == "closed"
        assert cb.model == "openrouter:primary-model"

    def test_stays_closed_under_threshold(self, cb):
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "closed"
        assert cb.model == "openrouter:primary-model"

    def test_opens_at_threshold(self, cb):
        for _ in range(3):
            cb.record_failure()
        assert cb.state == "open"
        assert cb.model == "openrouter:fallback-model"

    def test_success_resets_failure_count(self, cb):
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == "closed"
        # Need 3 more failures to open again
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "closed"

    def test_open_returns_fallback(self, cb):
        for _ in range(3):
            cb.record_failure()
        assert cb.model == "openrouter:fallback-model"
        # Multiple reads stay on fallback
        assert cb.model == "openrouter:fallback-model"

    def test_half_open_after_cooldown(self, cb):
        for _ in range(3):
            cb.record_failure()
        assert cb.state == "open"

        # Simulate cooldown elapsed
        cb._opened_at = time.monotonic() - 3  # 3s > 2s cooldown
        model = cb.model
        assert model == "openrouter:primary-model"
        assert cb.state == "half_open"

    def test_half_open_success_closes(self, cb):
        for _ in range(3):
            cb.record_failure()
        cb._opened_at = time.monotonic() - 3
        _ = cb.model  # triggers half_open
        cb.record_success()
        assert cb.state == "closed"
        assert cb.model == "openrouter:primary-model"

    def test_half_open_failure_reopens(self, cb):
        for _ in range(3):
            cb.record_failure()
        cb._opened_at = time.monotonic() - 3
        _ = cb.model  # triggers half_open
        cb.record_failure()
        assert cb.state == "open"
        assert cb.model == "openrouter:fallback-model"


# ==========================================================================
# Edge cases
# ==========================================================================
class TestCircuitBreakerEdgeCases:
    def test_success_in_closed_state_is_noop(self, cb):
        cb.record_success()
        assert cb.state == "closed"
        assert cb.model == "openrouter:primary-model"

    def test_open_before_cooldown_stays_fallback(self, cb):
        for _ in range(3):
            cb.record_failure()
        # No time elapsed
        assert cb.model == "openrouter:fallback-model"
        assert cb.state == "open"

    def test_multiple_opens_reset_cooldown(self, cb):
        for _ in range(3):
            cb.record_failure()
        first_opened = cb._opened_at

        # Half-open then fail again
        cb._opened_at = time.monotonic() - 3
        _ = cb.model  # half_open
        cb.record_failure()

        # Cooldown timer restarted
        assert cb._opened_at > first_opened

    def test_threshold_of_one(self):
        cb = CircuitBreaker(
            primary="a", fallback="b",
            failure_threshold=1, cooldown_seconds=1,
        )
        cb.record_failure()
        assert cb.state == "open"
        assert cb.model == "b"


# ==========================================================================
# Default singleton
# ==========================================================================
class TestSingleton:
    def test_module_level_breaker_exists(self):
        from src.llm_circuit_breaker import breaker
        assert breaker is not None
        assert breaker.state == "closed"
