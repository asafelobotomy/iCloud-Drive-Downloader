"""Tests for retry helper edge paths and tenacity integration wiring."""

import builtins
import importlib
import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import icloud_downloader_lib.retry as retry_module
from icloud_downloader_lib.retry import (
    ManualRetryState,
    build_retry_decorator,
    is_rate_limit_error,
    is_retryable_error,
)


class BadStringException(Exception):
    def __str__(self):
        raise RuntimeError("cannot stringify")


class TestRetryEdges(unittest.TestCase):
    """Test retry helper edge cases beyond the basic backoff suite."""

    def test_manual_retry_state_exposes_attempt_number_and_exception(self):
        error = ValueError("boom")
        state = ManualRetryState(error, 3)

        self.assertEqual(state.attempt_number, 3)
        self.assertIs(state.outcome.exception(), error)

    def test_is_retryable_error_returns_false_for_none(self):
        self.assertFalse(is_retryable_error(None))

    def test_is_retryable_error_handles_stringification_failures(self):
        self.assertFalse(is_retryable_error(BadStringException()))

    def test_is_rate_limit_error_handles_none_and_stringification_failures(self):
        self.assertFalse(is_rate_limit_error(None))
        self.assertFalse(is_rate_limit_error(BadStringException()))

    def test_is_rate_limit_error_detects_common_rate_limit_messages(self):
        self.assertTrue(is_rate_limit_error(Exception("HTTP 429: too many requests")))
        self.assertTrue(is_rate_limit_error(Exception("Request failed due to rate limit")))
        self.assertFalse(is_rate_limit_error(Exception("HTTP 500: internal server error")))

    def test_build_retry_decorator_raises_when_tenacity_is_unavailable(self):
        with patch.object(retry_module, "TENACITY_AVAILABLE", False):
            with self.assertRaises(RuntimeError):
                build_retry_decorator(lambda error: True, 3)

    def test_build_retry_decorator_wires_tenacity_helpers(self):
        tenacity_retry_mock = Mock(return_value="decorator")
        retry_if_exception_mock = Mock(return_value="retry-filter")
        stop_after_attempt_mock = Mock(return_value="stop-condition")

        with patch.object(retry_module, "TENACITY_AVAILABLE", True):
            with patch.object(retry_module, "tenacity_retry", tenacity_retry_mock):
                with patch.object(retry_module, "tenacity_retry_if_exception", retry_if_exception_mock):
                    with patch.object(retry_module, "tenacity_stop_after_attempt", stop_after_attempt_mock):
                        decorator = build_retry_decorator(lambda error: bool(error), 5)

        self.assertEqual(decorator, "decorator")
        stop_after_attempt_mock.assert_called_once_with(5)
        retry_if_exception_mock.assert_called_once()
        tenacity_retry_mock.assert_called_once_with(
            stop="stop-condition",
            retry="retry-filter",
            before_sleep=None,
            reraise=True,
        )

    def test_retry_module_handles_missing_tenacity_dependency_on_reload(self):
        original_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "tenacity":
                raise ImportError("tenacity missing")
            return original_import(name, globals, locals, fromlist, level)

        try:
            with patch("builtins.__import__", side_effect=fake_import):
                importlib.reload(retry_module)

            self.assertFalse(retry_module.TENACITY_AVAILABLE)
            self.assertIsNone(retry_module.tenacity_retry)
            self.assertIsNone(retry_module.tenacity_retry_if_exception)
            self.assertIsNone(retry_module.tenacity_stop_after_attempt)
        finally:
            importlib.reload(retry_module)


if __name__ == "__main__":
    unittest.main()