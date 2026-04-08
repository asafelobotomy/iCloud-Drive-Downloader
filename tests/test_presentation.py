"""Tests for presentation helpers and confirmation prompts."""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader_lib.presentation import (
    Colors,
    calculate_eta,
    confirm_download,
    format_path_for_display,
    format_size,
    format_speed,
    format_time,
    redact_paths_in_text,
)


class TestPresentationHelpers(unittest.TestCase):
    """Test human-readable formatting and confirmation prompts."""

    def test_format_size_and_speed_cover_small_and_large_values(self):
        self.assertEqual(format_size(None), "unknown")
        self.assertEqual(format_size(512), "512 B")
        self.assertEqual(format_size(1024), "1.0 KB")
        self.assertEqual(format_speed(2048), "2.0 KB/s")

    def test_colors_disable_and_format_size_supports_petabytes(self):
        Colors.disable()

        self.assertFalse(Colors.ENABLED)
        self.assertEqual(Colors.RED, "")
        self.assertEqual(format_size(1024**5), "1.0 PB")

    def test_format_time_and_eta_handle_edge_cases(self):
        self.assertEqual(format_time(-1), "calculating...")
        self.assertEqual(format_time(0), "0s")
        self.assertEqual(format_time(3661), "1h 1m 1s")
        self.assertEqual(calculate_eta(0, 100, 10.0), "calculating...")
        self.assertEqual(calculate_eta(100, 100, 10.0), "0s")
        self.assertEqual(calculate_eta(50, 100, 10.0), "10s")

    def test_format_path_for_display_shortens_absolute_paths(self):
        cwd_path = os.path.join(os.getcwd(), "nested", "file.txt")
        self.assertEqual(format_path_for_display(cwd_path), os.path.join("nested", "file.txt"))
        self.assertEqual(format_path_for_display("/tmp/example.json"), os.path.join("...", "example.json"))
        self.assertEqual(format_path_for_display("relative/path.txt"), "relative/path.txt")

    def test_redact_paths_in_text_rewrites_absolute_paths(self):
        redacted = redact_paths_in_text("Failure writing /tmp/private/file.txt during sync")

        self.assertNotIn("/tmp/private/file.txt", redacted)
        self.assertIn(".../file.txt", redacted)

    @patch("builtins.input", return_value="n")
    def test_confirm_download_rejects_large_download_when_user_declines(self, input_mock):
        confirmed = confirm_download({
            "estimated_files": 100,
            "estimated_size": 11 * 1024 * 1024 * 1024,
        })

        self.assertFalse(confirmed)
        input_mock.assert_called_once()

    @patch("builtins.input", side_effect=AssertionError("prompt should not be used"))
    def test_confirm_download_skips_prompt_for_zero_sized_estimate(self, input_mock):
        confirmed = confirm_download({"estimated_files": 0, "estimated_size": 0})

        self.assertTrue(confirmed)
        input_mock.assert_not_called()

    @patch("builtins.input", return_value="yes")
    def test_confirm_download_accepts_affirmative_response(self, input_mock):
        confirmed = confirm_download({"estimated_files": 2, "estimated_size": 1024})

        self.assertTrue(confirmed)
        input_mock.assert_called_once()