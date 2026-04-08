"""Tests for transfer failure paths and worker behavior."""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader_lib.state import DownloadManifest, DownloadStats
from icloud_downloader_lib.transfer import download_file, download_worker


class FailingResponse:
    """Streaming response that fails after yielding a partial chunk."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_content(self, chunk_size):
        del chunk_size
        yield b"part"
        raise RuntimeError("429 Too Many Requests")


class RetryableItem:
    """Item that returns a failing streaming response."""

    size = 8

    def open(self, stream=True):
        del stream
        return FailingResponse()


class TestTransferFailurePaths(unittest.TestCase):
    """Test transfer retry, skip, and worker behaviors."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.file_path = os.path.join(self.temp_dir, "file.bin")
        self.manifest = DownloadManifest(os.path.join(self.temp_dir, "manifest.json"))
        self.base_config = {
            "max_retries": 2,
            "timeout": 60,
            "chunk_size": 4,
            "progress_every_bytes": 2,
            "workers": 3,
            "verbose": False,
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("icloud_downloader_lib.transfer.TENACITY_AVAILABLE", False)
    @patch("icloud_downloader_lib.transfer.random.uniform", return_value=0.0)
    @patch("icloud_downloader_lib.transfer.time.sleep")
    def test_download_file_marks_rate_limited_failures_and_logs_them(
        self,
        sleep_mock,
        random_mock,
    ):
        del random_mock
        failures = []
        stats = DownloadStats()
        logger = Mock()
        pbar = Mock()

        download_file(
            RetryableItem(),
            self.file_path,
            failures,
            "file.bin",
            self.base_config,
            manifest=self.manifest,
            stats=stats,
            logger=logger,
            dry_run=False,
            pbar=pbar,
        )

        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0], "Download failed: RuntimeError: 429 Too Many Requests")
        self.assertEqual(stats.files_failed, 1)
        self.assertEqual(stats.throttle_events, 1)
        self.assertEqual(self.manifest.get_file_status(self.file_path)["status"], "failed")
        self.assertEqual(self.manifest.get_file_status(self.file_path)["bytes_downloaded"], 4)
        self.assertEqual(
            self.manifest.get_file_status(self.file_path)["error"],
            "RuntimeError: 429 Too Many Requests",
        )
        logger.log.assert_called_with(
            "file_failed",
            file=self.file_path,
            error_type="RuntimeError",
            attempts=2,
            throttled=True,
        )
        pbar.update.assert_called_once_with(1)
        sleep_mock.assert_called_once_with(2.0)

    def test_download_file_skips_existing_file_without_manifest_and_logs_skip(self):
        with open(self.file_path, "wb") as existing_file:
            existing_file.write(b"existing")

        failures = []
        stats = DownloadStats()
        logger = Mock()

        download_file(
            Mock(size=8),
            self.file_path,
            failures,
            "file.bin",
            self.base_config,
            manifest=None,
            stats=stats,
            logger=logger,
            dry_run=False,
            pbar=None,
        )

        self.assertEqual(failures, [])
        self.assertEqual(stats.files_skipped, 1)
        logger.log.assert_called_once_with(
            "file_skipped",
            file=self.file_path,
            reason="already_exists",
        )

    @patch("icloud_downloader_lib.transfer.download_file")
    def test_download_worker_returns_failures_from_download_file(self, download_file_mock):
        def inject_failure(*args, **kwargs):
            del kwargs
            args[2].append("Download failed: failed")

        download_file_mock.side_effect = inject_failure

        failures = download_worker(
            (
                Mock(),
                self.file_path,
                "file.bin",
                self.base_config,
                None,
                None,
                None,
                None,
                False,
                None,
            )
        )

        self.assertEqual(failures, ["Download failed: failed"])