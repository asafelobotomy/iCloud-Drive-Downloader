"""Tests for shutdown handling and structured logging utilities."""

import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader_lib.state import DownloadManifest, DownloadStats, ShutdownHandler, StructuredLogger


class TestShutdownHandler(unittest.TestCase):
    """Test graceful and forced shutdown behavior."""

    @patch("icloud_downloader_lib.state.signal.signal")
    def test_shutdown_handler_sets_stop_on_first_signal_and_exits_on_second(self, signal_mock):
        handler = ShutdownHandler()

        self.assertEqual(signal_mock.call_count, 2)
        self.assertFalse(handler.should_stop())

        handler._handle_signal(2, None)
        self.assertTrue(handler.should_stop())

        with self.assertRaises(SystemExit) as exc_info:
            handler._handle_signal(2, None)

        self.assertEqual(exc_info.exception.code, 1)


class TestStructuredLoggerAndStats(unittest.TestCase):
    """Test runtime helpers that are not covered by manifest/stats suites."""

    def test_structured_logger_writes_json_line(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = os.path.join(temp_dir, "events.jsonl")
            logger = StructuredLogger(log_path)

            logger.log("session_start", workers=3)

            with open(log_path, "r", encoding="utf-8") as log_file:
                entry = json.loads(log_file.read().strip())

            self.assertEqual(oct(os.stat(log_path).st_mode & 0o777), "0o600")

        self.assertEqual(entry["event"], "session_start")
        self.assertEqual(entry["workers"], 3)
        self.assertIn("timestamp", entry)

    def test_structured_logger_relativizes_file_paths_within_base_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = os.path.join(temp_dir, "events.jsonl")
            logger = StructuredLogger(log_path, base_path=temp_dir)

            logger.log("file_completed", file=os.path.join(temp_dir, "nested", "file.txt"))

            with open(log_path, "r", encoding="utf-8") as log_file:
                entry = json.loads(log_file.read().strip())

        self.assertNotIn("file", entry)
        self.assertTrue(entry["file_id"].startswith("sha256:"))

    @patch("icloud_downloader_lib.state.open_secure_file", side_effect=IOError("disk full"))
    def test_structured_logger_handles_io_errors(self, open_mock):
        logger = StructuredLogger("/tmp/events.jsonl")

        logger.log("session_end", status="failed")

        self.assertTrue(open_mock.called)

    @patch("icloud_downloader_lib.state.open_secure_file")
    def test_structured_logger_ignores_calls_without_log_path(self, open_mock):
        logger = StructuredLogger(None)

        logger.log("session_end", status="skipped")

        open_mock.assert_not_called()

    def test_structured_logger_warns_when_log_path_is_a_symlink(self):
        if not hasattr(os, "O_NOFOLLOW"):
            self.skipTest("O_NOFOLLOW is not available on this platform")

        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = os.path.join(temp_dir, "real-log.jsonl")
            link_path = os.path.join(temp_dir, "link-log.jsonl")
            with open(target_path, "w", encoding="utf-8") as handle:
                handle.write("existing\n")
            os.symlink(target_path, link_path)
            logger = StructuredLogger(link_path)
            stdout = StringIO()

            with redirect_stdout(stdout):
                logger.log("session_start", workers=3)

            with open(target_path, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "existing\n")
            self.assertIn("Warning: Could not write to log", stdout.getvalue())

    @patch("icloud_downloader_lib.state.time.time", side_effect=[100.0, 102.0, 102.0, 102.0, 102.0])
    def test_download_stats_reports_speed_eta_progress_and_throttle(self, time_mock):
        del time_mock
        stats = DownloadStats()
        stats.start()
        stats.add_file(400)
        stats.mark_completed(200)
        stats.mark_throttled()

        self.assertEqual(stats.current_speed(), 100.0)
        self.assertEqual(stats.get_eta(), "2s")
        self.assertEqual(stats.progress_percentage(), 50.0)
        self.assertTrue(stats.should_warn_throttle())

    def test_download_stats_eta_defaults_when_not_started(self):
        stats = DownloadStats()

        self.assertEqual(stats.current_speed(), 0.0)
        self.assertEqual(stats.get_eta(), "calculating...")
        self.assertEqual(stats.progress_percentage(), 0.0)
        self.assertFalse(stats.should_warn_throttle())

    @patch("icloud_downloader_lib.state.time.time", side_effect=[100.0, 100.0, 100.0])
    def test_download_stats_handles_zero_elapsed_time(self, _time_mock):
        stats = DownloadStats()
        stats.start()
        stats.add_file(100)
        stats.mark_completed(50)

        self.assertEqual(stats.current_speed(), 0.0)
        self.assertEqual(stats.get_eta(), "calculating...")

    def test_download_manifest_warns_when_save_fails(self):
        stdout = StringIO()
        manifest_path = os.path.join(tempfile.gettempdir(), "manifest-save-failure.json")
        manifest = DownloadManifest(manifest_path)

        with patch("icloud_downloader_lib.state.open_secure_file", side_effect=IOError("disk full")):
            with redirect_stdout(stdout):
                manifest.update_file("/tmp/file.bin", "partial", 10, 20)

        self.assertIn("Warning: Could not save manifest", stdout.getvalue())

    def test_download_manifest_uses_hashed_file_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = DownloadManifest(os.path.join(temp_dir, "manifest.json"))
            local_path = os.path.join(temp_dir, "nested", "file.txt")

            manifest.update_file(local_path, "partial", 10, 20, "RuntimeError: boom")

            stored_keys = list(manifest.data["files"].keys())
            self.assertEqual(len(stored_keys), 1)
            self.assertTrue(stored_keys[0].startswith("sha256:"))
            self.assertNotEqual(stored_keys[0], local_path)