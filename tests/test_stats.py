"""Tests for DownloadStats class."""

import unittest
import sys
import os
import threading
import time

# Add parent directory to path to import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader import DownloadStats


class TestDownloadStats(unittest.TestCase):
    """Test DownloadStats functionality."""

    def test_initial_state(self):
        """Test initial state of stats."""
        stats = DownloadStats()

        self.assertEqual(stats.files_total, 0)
        self.assertEqual(stats.files_completed, 0)
        self.assertEqual(stats.files_skipped, 0)
        self.assertEqual(stats.files_failed, 0)
        self.assertEqual(stats.bytes_total, 0)
        self.assertEqual(stats.bytes_downloaded, 0)
        self.assertIsNone(stats.start_time)
        self.assertIsNone(stats.end_time)

    def test_start_and_finish(self):
        """Test timing functionality."""
        stats = DownloadStats()

        stats.start()
        self.assertIsNotNone(stats.start_time)
        self.assertIsNone(stats.end_time)

        time.sleep(0.1)

        stats.finish()
        self.assertIsNotNone(stats.end_time)
        self.assertGreater(stats.end_time, stats.start_time)

    def test_add_file(self):
        """Test adding files to total."""
        stats = DownloadStats()

        stats.add_file(1024)
        stats.add_file(2048)
        stats.add_file(512)

        self.assertEqual(stats.files_total, 3)
        self.assertEqual(stats.bytes_total, 1024 + 2048 + 512)

    def test_mark_completed(self):
        """Test marking files as completed."""
        stats = DownloadStats()

        stats.mark_completed(1024)
        stats.mark_completed(2048)

        self.assertEqual(stats.files_completed, 2)
        self.assertEqual(stats.bytes_downloaded, 1024 + 2048)

    def test_mark_skipped(self):
        """Test marking files as skipped."""
        stats = DownloadStats()

        stats.mark_skipped()
        stats.mark_skipped()
        stats.mark_skipped()

        self.assertEqual(stats.files_skipped, 3)

    def test_mark_failed(self):
        """Test marking files as failed."""
        stats = DownloadStats()

        stats.mark_failed()
        stats.mark_failed()

        self.assertEqual(stats.files_failed, 2)

    def test_get_summary(self):
        """Test getting summary statistics."""
        stats = DownloadStats()

        stats.start()
        stats.add_file(1024)
        stats.add_file(2048)
        stats.mark_completed(1024)
        stats.mark_skipped()
        time.sleep(0.1)
        stats.finish()

        summary = stats.get_summary()

        self.assertEqual(summary["files_total"], 2)
        self.assertEqual(summary["files_completed"], 1)
        self.assertEqual(summary["files_skipped"], 1)
        self.assertEqual(summary["files_failed"], 0)
        self.assertEqual(summary["bytes_total"], 1024 + 2048)
        self.assertEqual(summary["bytes_downloaded"], 1024)
        self.assertGreater(summary["elapsed_seconds"], 0.1)

    def test_thread_safety(self):
        """Test thread-safe counter updates."""
        stats = DownloadStats()
        errors = []

        def worker():
            try:
                for _ in range(100):
                    stats.add_file(100)
                    stats.mark_completed(50)
                    stats.mark_skipped()
                    stats.mark_failed()
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = [threading.Thread(target=worker) for _ in range(10)]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for completion
        for t in threads:
            t.join()

        # Verify counts
        self.assertEqual(len(errors), 0)
        self.assertEqual(stats.files_total, 1000)  # 10 threads * 100 iterations
        self.assertEqual(stats.files_completed, 1000)
        self.assertEqual(stats.files_skipped, 1000)
        self.assertEqual(stats.files_failed, 1000)
        self.assertEqual(stats.bytes_total, 100000)  # 1000 * 100
        self.assertEqual(stats.bytes_downloaded, 50000)  # 1000 * 50


if __name__ == "__main__":
    unittest.main()
