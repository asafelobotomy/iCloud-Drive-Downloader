"""Tests for startup and session summary reporting."""

import os
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader_lib.inventory import DryRunInventory
from icloud_downloader_lib.reporting import (
    print_dry_run_inventory_summary,
    print_session_summary,
    print_startup_banner,
)


class TestReporting(unittest.TestCase):
    """Test console reporting helpers."""

    def test_print_startup_banner_renders_optional_configuration(self):
        stdout = StringIO()

        with redirect_stdout(stdout):
            print_startup_banner(
                "/tmp/downloads",
                {
                    "workers": 3,
                    "sequential": False,
                    "max_retries": 4,
                    "timeout": 60,
                    "dry_run": False,
                    "max_depth": 5,
                    "max_items": 20,
                },
                ["/tmp/private/photos/*.jpg"],
                ["/tmp/private/cache/*.tmp"],
                1024,
                2048,
                "/tmp/session.jsonl",
                False,
            )

        rendered = stdout.getvalue()
        self.assertIn("Destination:", rendered)
        self.assertIn("Max depth:", rendered)
        self.assertIn(".../*.jpg", rendered)
        self.assertIn(".../*.tmp", rendered)
        self.assertIn("Log file:", rendered)
        self.assertNotIn("/tmp/downloads", rendered)
        self.assertNotIn("/tmp/session.jsonl", rendered)
        self.assertIn(".../downloads", rendered)
        self.assertIn(".../session.jsonl", rendered)

    def test_print_session_summary_redacts_paths_inside_failure_text(self):
        stdout = StringIO()
        shutdown_handler = Mock()
        shutdown_handler.should_stop.return_value = False

        with redirect_stdout(stdout):
            print_session_summary(
                {
                    "files_total": 1,
                    "files_completed": 0,
                    "files_skipped": 0,
                    "files_failed": 1,
                    "bytes_downloaded": 0,
                    "elapsed_seconds": 1.0,
                    "throttle_events": 0,
                },
                ["Path validation failed for '/tmp/private/file.txt': outside root"],
                False,
                None,
                shutdown_handler,
            )

        rendered = stdout.getvalue()
        self.assertNotIn("/tmp/private/file.txt", rendered)
        self.assertIn(".../file.txt", rendered)

    def test_print_session_summary_redacts_transfer_identifiers(self):
        stdout = StringIO()
        shutdown_handler = Mock()
        shutdown_handler.should_stop.return_value = False

        with redirect_stdout(stdout):
            print_session_summary(
                {
                    "files_total": 1,
                    "files_completed": 0,
                    "files_skipped": 0,
                    "files_failed": 1,
                    "bytes_downloaded": 0,
                    "elapsed_seconds": 1.0,
                    "throttle_events": 0,
                },
                [
                    "Download failed: RuntimeError: test.user@example.com via +1 555 123 4567 at /tmp/private/file.txt"
                ],
                False,
                None,
                shutdown_handler,
            )

        rendered = stdout.getvalue()
        self.assertIn("te*******@example.com", rendered)
        self.assertIn("[redacted phone]", rendered)
        self.assertIn(".../file.txt", rendered)
        self.assertNotIn("test.user@example.com", rendered)

    def test_print_dry_run_inventory_summary_renders_aggregate_counts_only(self):
        stdout = StringIO()
        inventory = DryRunInventory(max_depth=2, max_items=50)
        inventory.record_folder(level=1, preview=True, is_root=True)
        inventory.record_folder(level=2, preview=True)
        inventory.record_file("/tmp/private/photo.jpg", 200, included=True, level=1, preview=True, is_root=True)
        inventory.record_file("/tmp/private/video.mov", 500, included=True, level=3, preview=True)
        inventory.record_file("/tmp/private/doc.pdf", 100, included=False, level=2, preview=True)

        with redirect_stdout(stdout):
            print_dry_run_inventory_summary(inventory, {"max_depth": 2, "max_items": 50})

        rendered = stdout.getvalue()
        self.assertIn("Root items: 2 (1 folders, 1 files)", rendered)
        self.assertIn("Full inventory: 5 items (2 folders, 3 files)", rendered)
        self.assertIn("Full data: 800 B", rendered)
        self.assertIn("Deepest item level: 3", rendered)
        self.assertIn("Media counts: 1 photos, 1 videos", rendered)
        self.assertIn("Matching current filters: 2 files", rendered)
        self.assertIn("Preview scope under current limits: 5 items (2 folders, 3 files)", rendered)
        self.assertIn("Would download under current limits: 2 files", rendered)
        self.assertIn("Preview limits: max_depth=2, max_items=50", rendered)
        self.assertIn("Photos: 1 files, 200 B (25.0%)", rendered)
        self.assertIn("Videos: 1 files, 500 B (62.5%)", rendered)
        self.assertIn("Documents: 1 files, 100 B (12.5%)", rendered)
        self.assertNotIn("photo.jpg", rendered)
        self.assertNotIn("video.mov", rendered)

    def test_print_session_summary_handles_shutdown_failures_and_logging(self):
        stdout = StringIO()
        logger = Mock()
        shutdown_handler = Mock()
        shutdown_handler.should_stop.return_value = True
        summary = {
            "files_total": 5,
            "files_completed": 3,
            "files_skipped": 1,
            "files_failed": 1,
            "bytes_downloaded": 4096,
            "elapsed_seconds": 2.0,
            "throttle_events": 2,
        }

        with redirect_stdout(stdout):
            print_session_summary(summary, ["file.txt: failed"], False, logger, shutdown_handler)

        rendered = stdout.getvalue()
        self.assertIn("Session terminated early", rendered)
        self.assertIn("Rate limit events", rendered)
        self.assertIn("file.txt: failed", rendered)
        logger.log.assert_called_once()

    def test_print_session_summary_reports_dry_run_success(self):
        stdout = StringIO()
        shutdown_handler = Mock()
        shutdown_handler.should_stop.return_value = False

        with redirect_stdout(stdout):
            print_session_summary(
                {
                    "files_total": 1,
                    "files_completed": 0,
                    "files_skipped": 0,
                    "files_failed": 0,
                    "bytes_downloaded": 0,
                    "elapsed_seconds": 1.0,
                    "throttle_events": 0,
                },
                [],
                True,
                None,
                shutdown_handler,
            )

        self.assertIn("Dry run complete.", stdout.getvalue())
        self.assertIn("Dry run completed.", stdout.getvalue())

    def test_print_session_summary_reports_successful_downloads(self):
        stdout = StringIO()
        shutdown_handler = Mock()
        shutdown_handler.should_stop.return_value = False

        with redirect_stdout(stdout):
            print_session_summary(
                {
                    "files_total": 2,
                    "files_completed": 2,
                    "files_skipped": 0,
                    "files_failed": 0,
                    "bytes_downloaded": 1024,
                    "elapsed_seconds": 2.0,
                    "throttle_events": 0,
                },
                [],
                False,
                None,
                shutdown_handler,
            )

        self.assertIn("All items downloaded successfully.", stdout.getvalue())