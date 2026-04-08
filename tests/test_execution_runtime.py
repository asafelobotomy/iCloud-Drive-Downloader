"""Tests for execution runtime helpers outside the high-level session entrypoint."""

import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader_lib.execution import process_concurrent_downloads, process_sequential_downloads
from icloud_downloader_lib.state import DownloadStats, ShutdownHandler


class FakeFuture:
    """Minimal future implementation for patched executor tests."""

    def __init__(self, result):
        self._result = result

    def result(self):
        return self._result


class FakeDrive(dict):
    """Dictionary-backed drive stub."""

    def dir(self):
        return list(self.keys())


class TestExecutionRuntime(unittest.TestCase):
    """Test sequential and concurrent helper branches."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("icloud_downloader_lib.execution.download_node")
    @patch("icloud_downloader_lib.execution.download_file")
    def test_process_sequential_downloads_handles_folders_files_and_shutdown(
        self,
        download_file_mock,
        download_node_mock,
    ):
        folder_item = SimpleNamespace(type="folder")
        file_item = SimpleNamespace(type="file")
        drive = FakeDrive({"Photos": folder_item, "top.txt": file_item})
        api = SimpleNamespace(drive=drive)
        file_path = os.path.join(self.temp_dir, "top.txt")

        def write_file(*args, **kwargs):
            del kwargs
            with open(args[1], "wb") as saved_file:
                saved_file.write(b"ok")

        download_file_mock.side_effect = write_file
        shutdown_handler = ShutdownHandler.__new__(ShutdownHandler)
        shutdown_handler.should_stop = Mock(side_effect=[False, False, True])

        process_sequential_downloads(
            api,
            ["Photos", "top.txt", "ignored.txt"],
            self.temp_dir,
            [],
            {"dry_run": False, "max_depth": None},
            None,
            Mock(),
            Mock(),
            DownloadStats(),
            None,
            shutdown_handler,
        )

        download_node_mock.assert_called_once()
        download_file_mock.assert_called_once()
        self.assertEqual(oct(os.stat(file_path).st_mode & 0o777), "0o600")

    @patch("icloud_downloader_lib.execution.download_node")
    @patch("icloud_downloader_lib.execution.download_file")
    def test_process_sequential_downloads_tracks_files_total_in_stats(
        self,
        download_file_mock,
        download_node_mock,
    ):
        file_item = SimpleNamespace(type="file", size=4096)
        drive = FakeDrive({"readme.txt": file_item})
        api = SimpleNamespace(drive=drive)
        stats = DownloadStats()
        file_filter = Mock()
        file_filter.should_include = Mock(return_value=True)
        shutdown_handler = ShutdownHandler.__new__(ShutdownHandler)
        shutdown_handler.should_stop = Mock(return_value=False)

        download_file_mock.side_effect = lambda *a, **kw: None

        process_sequential_downloads(
            api,
            ["readme.txt"],
            self.temp_dir,
            [],
            {"dry_run": False, "max_depth": None},
            None,
            Mock(),
            file_filter,
            stats,
            None,
            shutdown_handler,
        )

        self.assertEqual(stats.files_total, 1)
        self.assertEqual(stats.bytes_total, 4096)
        del download_node_mock

    def test_process_concurrent_downloads_returns_early_with_no_tasks(self):
        stdout = StringIO()

        with redirect_stdout(stdout):
            process_concurrent_downloads(
                [],
                [],
                {"dry_run": False, "workers": 2, "progress": False},
                Mock(),
                DownloadStats(),
                None,
                Mock(),
            )

        self.assertIn("No files to download", stdout.getvalue())

    @patch("icloud_downloader_lib.execution.as_completed", side_effect=lambda future_map: list(future_map))
    @patch("icloud_downloader_lib.execution.ThreadPoolExecutor")
    @patch("icloud_downloader_lib.execution.tqdm")
    @patch("icloud_downloader_lib.execution.TQDM_AVAILABLE", True)
    def test_process_concurrent_downloads_uses_progress_bar_and_chmods_completed_files(
        self,
        tqdm_mock,
        executor_cls_mock,
        as_completed_mock,
    ):
        del as_completed_mock
        local_path = os.path.join(self.temp_dir, "done.txt")
        with open(local_path, "wb") as saved_file:
            saved_file.write(b"done")

        future = FakeFuture([])
        executor = Mock()
        executor.__enter__ = Mock(return_value=executor)
        executor.__exit__ = Mock(return_value=False)
        executor.submit.return_value = future
        executor_cls_mock.return_value = executor
        pbar = Mock()
        tqdm_mock.return_value = pbar
        shutdown_handler = Mock()
        shutdown_handler.should_stop.return_value = False

        process_concurrent_downloads(
            [(Mock(), local_path, "done.txt", {}, None)],
            [],
            {"dry_run": False, "workers": 2, "progress": True},
            Mock(),
            DownloadStats(),
            None,
            shutdown_handler,
        )

        tqdm_mock.assert_called_once()
        pbar.close.assert_called_once_with()
        self.assertEqual(oct(os.stat(local_path).st_mode & 0o777), "0o600")

    @patch("icloud_downloader_lib.execution.as_completed", side_effect=lambda future_map: list(future_map))
    @patch("icloud_downloader_lib.execution.ThreadPoolExecutor")
    def test_process_concurrent_downloads_cancels_remaining_work_on_shutdown(
        self,
        executor_cls_mock,
        as_completed_mock,
    ):
        del as_completed_mock
        future = FakeFuture([])
        executor = Mock()
        executor.__enter__ = Mock(return_value=executor)
        executor.__exit__ = Mock(return_value=False)
        executor.submit.return_value = future
        executor_cls_mock.return_value = executor
        shutdown_handler = Mock()
        shutdown_handler.should_stop.return_value = True

        process_concurrent_downloads(
            [(Mock(), os.path.join(self.temp_dir, "later.txt"), "later.txt", {}, None)],
            [],
            {"dry_run": False, "workers": 2, "progress": False},
            Mock(),
            DownloadStats(),
            None,
            shutdown_handler,
        )

        executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)