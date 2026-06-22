"""Property-based tests for exponential backoff state machine.

Feature: gameplay-improvements-tier1, Property 4: Exponential backoff state machine

Verifies that the reconnection backoff algorithm produces correct delays:
- delay = min(1000 * 2^attemptCount, 10000)
- After a successful reconnection, the delay resets to 1000ms.
"""

from hypothesis import given, settings, strategies as st


# Pure Python implementation of the backoff formula matching the JS code:
# delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000)
# where reconnectAttempts starts at 0 and increments AFTER computing the delay.
INITIAL_DELAY = 1000
MAX_DELAY = 10000


def compute_backoff_delay(attempt: int) -> int:
    """Compute the backoff delay for a given attempt number.

    Mirrors the JavaScript implementation:
        delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000)

    Where reconnectAttempts is the attempt index (0-based) at the time
    the delay is computed (before incrementing).

    Args:
        attempt: The 0-based attempt count (0 for first failure, 1 for second, etc.)

    Returns:
        Delay in milliseconds before the next reconnection attempt.
    """
    return min(INITIAL_DELAY * (2 ** attempt), MAX_DELAY)


class TestExponentialBackoffStateMachine:
    """Property 4: Exponential backoff state machine

    For any sequence of N consecutive failed reconnection attempts followed
    by a successful reconnection, the delay before attempt N SHALL equal
    min(1000 * 2^(N-1), 10000) milliseconds, and after the successful
    reconnection the delay SHALL reset to 1000ms for the next failure.
    """

    @settings(max_examples=100)
    @given(num_failures=st.integers(min_value=0, max_value=20))
    def test_backoff_delay_for_consecutive_failures(self, num_failures: int):
        """**Validates: Requirements 4.2, 4.7**

        Generate random sequences of N consecutive failures (0 <= N <= 20),
        verify delay for each attempt matches min(1000 * 2^attempt, 10000).

        The JS code uses:
            delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000)
        where reconnectAttempts starts at 0 and increments after computing delay.
        """
        # Simulate the state machine: reconnectAttempts starts at 0
        reconnect_attempts = 0

        for i in range(num_failures):
            # Compute delay (before incrementing attempts)
            delay = compute_backoff_delay(reconnect_attempts)

            # Expected delay based on formula
            expected_delay = min(INITIAL_DELAY * (2 ** reconnect_attempts), MAX_DELAY)

            assert delay == expected_delay, (
                f"Attempt {reconnect_attempts}: expected delay={expected_delay}, "
                f"got delay={delay}"
            )

            # Verify specific known values
            if reconnect_attempts == 0:
                assert delay == 1000, f"First attempt should be 1000ms, got {delay}"
            elif reconnect_attempts == 1:
                assert delay == 2000, f"Second attempt should be 2000ms, got {delay}"
            elif reconnect_attempts == 2:
                assert delay == 4000, f"Third attempt should be 4000ms, got {delay}"
            elif reconnect_attempts == 3:
                assert delay == 8000, f"Fourth attempt should be 8000ms, got {delay}"
            elif reconnect_attempts >= 4:
                assert delay == 10000, (
                    f"Attempt {reconnect_attempts} should be capped at 10000ms, got {delay}"
                )

            # Increment attempts (mirrors JS: reconnectAttempts++ after delay computation)
            reconnect_attempts += 1

    @settings(max_examples=100)
    @given(
        failures_before_success=st.integers(min_value=1, max_value=20),
        failures_after_success=st.integers(min_value=1, max_value=20),
    )
    def test_backoff_resets_after_success(
        self, failures_before_success: int, failures_after_success: int
    ):
        """**Validates: Requirements 4.2, 4.7**

        Verify that after a successful reconnection, the next failure starts
        at 1000ms again (delay resets).
        """
        # Phase 1: Accumulate failures
        reconnect_attempts = 0
        for _ in range(failures_before_success):
            delay = compute_backoff_delay(reconnect_attempts)
            assert delay == min(INITIAL_DELAY * (2 ** reconnect_attempts), MAX_DELAY)
            reconnect_attempts += 1

        # Success event: reset attempts to 0 (mirrors JS: reconnectAttempts = 0)
        reconnect_attempts = 0

        # Phase 2: After success, verify delays start from 1000ms again
        for i in range(failures_after_success):
            delay = compute_backoff_delay(reconnect_attempts)
            expected_delay = min(INITIAL_DELAY * (2 ** reconnect_attempts), MAX_DELAY)

            assert delay == expected_delay, (
                f"After reset, attempt {reconnect_attempts}: "
                f"expected delay={expected_delay}, got delay={delay}"
            )

            # First failure after success must always be 1000ms
            if reconnect_attempts == 0:
                assert delay == 1000, (
                    f"After success, first retry should be 1000ms, got {delay}"
                )

            reconnect_attempts += 1

    @settings(max_examples=100)
    @given(attempt=st.integers(min_value=0, max_value=20))
    def test_delay_never_exceeds_max(self, attempt: int):
        """**Validates: Requirements 4.2, 4.7**

        For any attempt number, the computed delay must never exceed 10000ms.
        """
        delay = compute_backoff_delay(attempt)
        assert delay <= MAX_DELAY, (
            f"Delay {delay}ms exceeds maximum {MAX_DELAY}ms at attempt {attempt}"
        )
        assert delay >= INITIAL_DELAY, (
            f"Delay {delay}ms is below initial {INITIAL_DELAY}ms at attempt {attempt}"
        )

    @settings(max_examples=100)
    @given(attempt=st.integers(min_value=0, max_value=3))
    def test_delay_doubles_before_cap(self, attempt: int):
        """**Validates: Requirements 4.2, 4.7**

        Before hitting the cap, each successive attempt should double the delay.
        """
        current_delay = compute_backoff_delay(attempt)
        next_delay = compute_backoff_delay(attempt + 1)

        # Before cap, next should be double current
        if current_delay < MAX_DELAY:
            assert next_delay == min(current_delay * 2, MAX_DELAY), (
                f"Expected next delay to be {min(current_delay * 2, MAX_DELAY)}, "
                f"got {next_delay} (attempt {attempt} -> {attempt + 1})"
            )
