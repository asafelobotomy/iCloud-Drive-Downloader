"""Tests for transfer edge paths beyond the basic failure-path suite."""

import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader_lib.state import DownloadManifest, DownloadStats
from icloud_downloader_lib.transfer import download_file


class SizeErrorItem:
    """Item stub that raises when its size is inspected."""

    def __getattr__(self, name):
        if name == "size":
            raise RuntimeError("size unavailable")
        raise AttributeError(name)


class SuccessfulResponse:
    """Streaming response with predefined chunks."""

    def __init__(self, chunks):
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_content(self, chunk_size):
        del chunk_size
        for chunk in self._chunks:
            yield chunk


class SuccessfulItem:
    """Item that returns a successful streaming response."""

    def __init__(self, chunks, size=8):
        self._chunks = chunks
        self.size = size

    def open(self, stream=True):
        del stream
        return SuccessfulResponse(self._chunks)


class ConnectionResetResponse:
    """Streaming response that raises a retryable non-throttle error."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_content(self, chunk_size):
        del chunk_size
        yield b"part"
        raise ConnectionError("connection reset")


class ConnectionResetItem:
    """Item that raises a retryable non-throttle error while streaming."""

    size = 8

    def open(self, stream=True):
        del stream
        return ConnectionResetResponse()


class TestTransferEdges(unittest.TestCase):
    """Test transfer helper edge branches that were split from the main suite."""

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

    def test_download_file_filters_items_when_size_lookup_fails_and_logs_reason(self):
        failures = []
        logger = Mock()
        file_filter = Mock()
        file_filter.should_include.return_value = False

        download_file(
            SizeErrorItem(),
            self.file_path,
            failures,
            "file.bin",
            {**self.base_config, "verbose": True},
            file_filter=file_filter,
            logger=logger,
        )

        self.assertEqual(failures, [])
        file_filter.should_include.assert_called_once_with(self.file_path, size=None)
        logger.log.assert_called_once_with("file_filtered", file=self.file_path, reason="pattern_or_size")

    def test_download_file_dry_run_logs_the_planned_download(self):
        failures = []
        logger = Mock()
        stats = DownloadStats()

        download_file(
            SuccessfulItem([b"ignored"], size=8),
            self.file_path,
            failures,
            "file.bin",
            self.base_config,
            stats=stats,
            logger=logger,
            dry_run=True,
        )

        self.assertEqual(failures, [])
        self.assertEqual(stats.files_total, 1)
        logger.log.assert_called_once_with("dry_run_file", file=self.file_path, size=8)

    @patch("icloud_downloader_lib.transfer.TENACITY_AVAILABLE", False)
    def test_download_file_creates_missing_parent_directories_at_write_time(self):
        nested_path = os.path.join(self.temp_dir, "nested", "file.bin")

        download_file(
            SuccessfulItem([b"abcd"], size=4),
            nested_path,
            [],
            "file.bin",
            {**self.base_config, "max_retries": 1, "download_root": self.temp_dir},
        )

        self.assertTrue(os.path.exists(nested_path))
        with open(nested_path, "rb") as downloaded_file:
            self.assertEqual(downloaded_file.read(), b"abcd")

    def test_download_file_skips_manifest_completed_file_and_logs_reason(self):
        with open(self.file_path, "wb") as existing_file:
            existing_file.write(b"complete")
        self.manifest.mark_complete(self.file_path, 8)
        stats = DownloadStats()
        logger = Mock()

        download_file(
            SuccessfulItem([b"ignored"], size=8),
            self.file_path,
            [],
            "file.bin",
            self.base_config,
            manifest=self.manifest,
            stats=stats,
            logger=logger,
        )

        self.assertEqual(stats.files_skipped, 1)
        logger.log.assert_called_once_with("file_skipped", file=self.file_path, reason="already_complete")

    def test_download_file_skips_existing_file_when_manifest_status_is_not_partial(self):
        with open(self.file_path, "wb") as existing_file:
            existing_file.write(b"existing")
        self.manifest.update_file(self.file_path, "failed", 8, 8)
        stats = DownloadStats()
        logger = Mock()

        download_file(
            SuccessfulItem([b"ignored"], size=8),
            self.file_path,
            [],
            "file.bin",
            self.base_config,
            manifest=self.manifest,
            stats=stats,
            logger=logger,
        )

        self.assertEqual(stats.files_skipped, 1)
        logger.log.assert_called_once_with("file_skipped", file=self.file_path, reason="already_exists")

    @patch("icloud_downloader_lib.transfer.TENACITY_AVAILABLE", False)
    @patch("icloud_downloader_lib.transfer.random.uniform", return_value=0.0)
    @patch("icloud_downloader_lib.transfer.time.sleep")
    def test_download_file_retries_non_rate_limited_errors_and_logs_failure(
        self,
        sleep_mock,
        random_mock,
    ):
        del random_mock
        failures = []
        logger = Mock()
        stats = DownloadStats()
        stdout = StringIO()

        with redirect_stdout(stdout):
            download_file(
                ConnectionResetItem(),
                self.file_path,
                failures,
                "file.bin",
                self.base_config,
                manifest=self.manifest,
                stats=stats,
                logger=logger,
            )

        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0], "Download failed: ConnectionError: connection reset")
        self.assertIn("Retryable transfer error", stdout.getvalue())
        self.assertIn("FAILED to download after 2 attempts", stdout.getvalue())
        logger.log.assert_called_with(
            "file_failed",
            file=self.file_path,
            error_type="ConnectionError",
            attempts=2,
            throttled=False,
        )
        sleep_mock.assert_called_once_with(1.0)

    @patch("icloud_downloader_lib.transfer.TENACITY_AVAILABLE", False)
    def test_download_file_resumes_partials_skips_empty_chunks_and_logs_success(self):
        with open(self.file_path, "wb") as existing_file:
            existing_file.write(b"ab")
        self.manifest.update_file(self.file_path, "partial", 2, 8)
        logger = Mock()
        pbar = Mock()
        stats = DownloadStats()

        download_file(
            SuccessfulItem([b"", b"abcd", b"efgh"], size=8),
            self.file_path,
            [],
            "file.bin",
            {**self.base_config, "max_retries": 1},
            manifest=self.manifest,
            stats=stats,
            logger=logger,
            pbar=pbar,
        )

        with open(self.file_path, "rb") as downloaded_file:
            self.assertEqual(downloaded_file.read(), b"abcdefgh")

        self.assertEqual(self.manifest.get_file_status(self.file_path)["status"], "complete")
        self.assertEqual(stats.files_completed, 1)
        self.assertEqual(stats.bytes_downloaded, 8)
        self.assertIn(
            ("file_resume", self.file_path, 2),
            [
                (call.args[0], call.kwargs["file"], call.kwargs.get("existing_bytes"))
                for call in logger.log.call_args_list
                if call.args
            ],
        )
        pbar.update.assert_called_once_with(1)

    @patch("icloud_downloader_lib.transfer.random.uniform", return_value=0.0)
    @patch("icloud_downloader_lib.transfer.time.sleep")
    @patch("icloud_downloader_lib.transfer.build_retry_decorator")
    @patch("icloud_downloader_lib.transfer.TENACITY_AVAILABLE", True)
    def test_download_file_uses_tenacity_retry_branch_for_retryable_errors(
        self,
        build_retry_decorator_mock,
        sleep_mock,
        random_mock,
    ):
        del random_mock
        decorated = Mock(side_effect=ConnectionError("fatal"))
        build_retry_decorator_mock.return_value = lambda func: decorated
        failures = []

        download_file(
            Mock(),
            self.file_path,
            failures,
            "file.bin",
            self.base_config,
        )

        self.assertEqual(len(failures), 1)
        self.assertIn("fatal", failures[0])
        build_retry_decorator_mock.assert_called_once()
        # before_sleep=handle_retry_error must be forwarded to build_retry_decorator
        _, kwargs = build_retry_decorator_mock.call_args
        self.assertIsNotNone(kwargs.get("before_sleep"))
        # the outer loop is gone — sleep is tenacity's responsibility, not ours
        sleep_mock.assert_not_called()

    @patch("icloud_downloader_lib.transfer.TENACITY_AVAILABLE", False)
    def test_download_file_reports_failure_when_manual_retry_loop_has_zero_attempts(self):
        failures = []

        download_file(
            SuccessfulItem([b"abcd"], size=4),
            self.file_path,
            failures,
            "file.bin",
            {**self.base_config, "max_retries": 0},
        )

        self.assertEqual(len(failures), 1)
        self.assertIn("Download failed after all retries", failures[0])

    @patch("icloud_downloader_lib.transfer.build_retry_decorator")
    @patch("icloud_downloader_lib.transfer.TENACITY_AVAILABLE", True)
    def test_download_file_tenacity_branch_calls_decorated_function_exactly_once(self, build_retry_decorator_mock):
        """The outer retry loop has been removed; the decorated function is invoked once."""
        decorated = Mock(return_value=4)
        build_retry_decorator_mock.return_value = lambda func: decorated
        failures = []

        download_file(
            SuccessfulItem([b"abcd"], size=4),
            self.file_path,
            failures,
            "file.bin",
            {**self.base_config, "max_retries": 3},
        )

        self.assertEqual(len(failures), 0)
        self.assertEqual(decorated.call_count, 1)


if __name__ == "__main__":
    unittest.main()