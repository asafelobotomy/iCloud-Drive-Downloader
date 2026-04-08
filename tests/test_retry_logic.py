"""Tests for retry logic and backoff calculations."""

import unittest
import sys
import os

# Add parent directory to path to import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader import (
    calculate_backoff,
    is_retryable_error,
    RETRYABLE_STATUS_CODES,
)


class TestCalculateBackoff(unittest.TestCase):
    """Test calculate_backoff function."""

    def test_first_attempt(self):
        """Test backoff for first retry."""
        delay = calculate_backoff(1, base_delay=1.0, max_delay=60.0)
        # Should be around 1 second with jitter (1.0 ± 10%)
        self.assertGreaterEqual(delay, 0.9)
        self.assertLessEqual(delay, 1.2)

    def test_exponential_growth(self):
        """Test that delay grows exponentially."""
        delay1 = calculate_backoff(1, base_delay=1.0, max_delay=60.0)
        delay2 = calculate_backoff(2, base_delay=1.0, max_delay=60.0)
        delay3 = calculate_backoff(3, base_delay=1.0, max_delay=60.0)

        # Delay should roughly double each time (accounting for jitter)
        self.assertLess(delay1, delay2)
        self.assertLess(delay2, delay3)

        # Check approximate exponential relationship
        # delay2 should be around 2x delay1, delay3 around 4x delay1
        self.assertGreater(delay2, 1.5)  # At least 1.5s (2s - jitter)
        self.assertGreater(delay3, 3.0)  # At least 3s (4s - jitter)

    def test_max_delay_cap(self):
        """Test that delay is capped at max_delay."""
        # After many attempts, should hit the cap
        delay = calculate_backoff(10, base_delay=1.0, max_delay=60.0)
        self.assertLessEqual(delay, 66.0)  # 60 + 10% jitter

    def test_custom_parameters(self):
        """Test with custom base and max delays."""
        delay = calculate_backoff(1, base_delay=5.0, max_delay=30.0)
        self.assertGreaterEqual(delay, 4.5)  # 5.0 - 10%
        self.assertLessEqual(delay, 5.5)  # 5.0 + 10%

    def test_jitter_variation(self):
        """Test that jitter provides variation."""
        delays = [
            calculate_backoff(1, base_delay=1.0, max_delay=60.0) for _ in range(100)
        ]

        # All delays should be different (extremely high probability)
        unique_delays = set(delays)
        self.assertGreater(len(unique_delays), 90)  # At least 90% unique

    def test_jitter_bounds(self):
        """Test that jitter stays within 10% bounds."""
        for attempt in range(1, 6):
            delay = calculate_backoff(attempt, base_delay=1.0, max_delay=60.0)
            expected = min(1.0 * (2 ** (attempt - 1)), 60.0)

            # Jitter adds 0–10% on top of the base delay
            self.assertGreaterEqual(delay, expected)
            self.assertLessEqual(delay, expected * 1.1)


class TestIsRetryableError(unittest.TestCase):
    """Test is_retryable_error function."""

    def test_retryable_exceptions(self):
        """Test that retryable exceptions are identified."""
        self.assertTrue(is_retryable_error(ConnectionError("Connection reset")))
        self.assertTrue(is_retryable_error(TimeoutError("Request timeout")))

    def test_non_retryable_exceptions(self):
        """Test that non-retryable exceptions are identified."""
        self.assertFalse(is_retryable_error(ValueError("Invalid value")))
        self.assertFalse(is_retryable_error(TypeError("Type error")))
        self.assertFalse(is_retryable_error(KeyError("Key not found")))

    def test_retryable_status_codes(self):
        """Test that HTTP status codes in messages are identified."""
        for code in RETRYABLE_STATUS_CODES:
            error = Exception(f"HTTP Error {code}: Server Error")
            self.assertTrue(
                is_retryable_error(error), f"Status code {code} should be retryable"
            )

    def test_non_retryable_status_codes(self):
        """Test that non-retryable status codes are identified."""
        non_retryable = [400, 401, 403, 404, 405]
        for code in non_retryable:
            error = Exception(f"HTTP Error {code}: Client Error")
            self.assertFalse(
                is_retryable_error(error), f"Status code {code} should not be retryable"
            )

    def test_mixed_case_status_codes(self):
        """Test that status code detection is case-insensitive."""
        error = Exception("HTTP ERROR 500: Internal Server Error")
        self.assertTrue(is_retryable_error(error))

    def test_status_code_in_middle_of_message(self):
        """Test status code detection anywhere in message."""
        error = Exception("Request failed with status 503 from server")
        self.assertTrue(is_retryable_error(error))


if __name__ == "__main__":
    unittest.main()
