"""Tests for CLI support helper functions and preset rendering."""

import argparse
import os
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader_lib.cli_support import (
    human_size,
    non_negative_float,
    non_negative_int,
    positive_int,
    print_presets,
    validate_arguments,
    worker_count,
)
from icloud_downloader_lib.definitions import PRESETS


class TestCliSupportHelpers(unittest.TestCase):
    """Test standalone CLI helper branches not covered by parser tests."""

    def test_positive_int_accepts_positive_values(self):
        self.assertEqual(positive_int("3"), 3)

    def test_positive_int_rejects_zero(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            positive_int("0")

    def test_non_negative_int_accepts_zero(self):
        self.assertEqual(non_negative_int("0"), 0)

    def test_non_negative_int_rejects_negative_values(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            non_negative_int("-1")

    def test_worker_count_accepts_upper_bound(self):
        self.assertEqual(worker_count("10"), 10)

    def test_worker_count_rejects_values_above_limit(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            worker_count("11")

    def test_non_negative_float_accepts_zero(self):
        self.assertEqual(non_negative_float("0"), 0.0)

    def test_non_negative_float_rejects_negative_values(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            non_negative_float("-0.5")

    def test_print_presets_renders_all_preset_names_and_descriptions(self):
        stdout = StringIO()

        with redirect_stdout(stdout):
            print_presets()

        rendered = stdout.getvalue()
        self.assertIn("Available presets:", rendered)
        for preset_name, preset in PRESETS.items():
            self.assertIn(preset_name, rendered)
            self.assertIn(preset["name"], rendered)
            self.assertIn(preset["description"], rendered)

    def test_validate_arguments_calls_parser_error_for_inverted_size_range(self):
        parser = Mock()
        args = SimpleNamespace(min_size=20, max_size=10)

        validate_arguments(parser, args)

        parser.error.assert_called_once_with("--min-size cannot be greater than --max-size")

    def test_validate_arguments_allows_missing_or_ordered_bounds(self):
        parser = Mock()

        validate_arguments(parser, SimpleNamespace(min_size=None, max_size=10))
        validate_arguments(parser, SimpleNamespace(min_size=5, max_size=10))

        parser.error.assert_not_called()


class TestHumanSize(unittest.TestCase):
    """Tests for the human_size argparse type helper."""

    def test_plain_integer_returns_bytes(self):
        self.assertEqual(human_size("0"), 0)
        self.assertEqual(human_size("1048576"), 1048576)

    def test_kb_suffix_case_insensitive(self):
        self.assertEqual(human_size("10KB"), 10 * 1024)
        self.assertEqual(human_size("10kb"), 10 * 1024)
        self.assertEqual(human_size("10Kb"), 10 * 1024)

    def test_mb_suffix(self):
        self.assertEqual(human_size("2MB"), 2 * 1024 ** 2)
        self.assertEqual(human_size("2mb"), 2 * 1024 ** 2)

    def test_gb_suffix(self):
        self.assertEqual(human_size("1GB"), 1024 ** 3)
        self.assertEqual(human_size("1gb"), 1024 ** 3)

    def test_tb_suffix(self):
        self.assertEqual(human_size("1TB"), 1024 ** 4)

    def test_b_suffix(self):
        self.assertEqual(human_size("500B"), 500)
        self.assertEqual(human_size("500b"), 500)

    def test_fractional_mb(self):
        self.assertEqual(human_size("2.5MB"), int(2.5 * 1024 ** 2))

    def test_fractional_gb(self):
        self.assertEqual(human_size("1.5GB"), int(1.5 * 1024 ** 3))

    def test_invalid_string_raises(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            human_size("abc")

    def test_invalid_suffix_raises(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            human_size("10XB")

    def test_negative_value_raises(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            human_size("-1")

    def test_whitespace_is_stripped(self):
        self.assertEqual(human_size(" 5MB "), 5 * 1024 ** 2)


if __name__ == "__main__":
    unittest.main()