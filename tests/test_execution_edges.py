"""Tests for remaining execution helper edge paths and fallback imports."""

import builtins
import importlib
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import icloud_downloader_lib.execution as execution_module
from icloud_downloader_lib.execution import collect_top_level_tasks, process_concurrent_downloads
from icloud_downloader_lib.filters import FileFilter
from icloud_downloader_lib.state import DownloadStats, ShutdownHandler


class FakeDrive(dict):
    def dir(self):
        return list(self.keys())


class TestExecutionEdges(unittest.TestCase):
    """Test execution branches not covered by the main helper suites."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_execution_module_handles_missing_tqdm_dependency_on_reload(self):
        original_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "tqdm":
                raise ImportError("tqdm missing")
            return original_import(name, globals, locals, fromlist, level)

        try:
            with patch("builtins.__import__", side_effect=fake_import):
                importlib.reload(execution_module)

            self.assertFalse(execution_module.TQDM_AVAILABLE)
            self.assertIsNone(execution_module.tqdm)
        finally:
            importlib.reload(execution_module)

    def test_collect_top_level_tasks_stops_when_shutdown_is_requested(self):
        api = SimpleNamespace(drive=FakeDrive({"top.txt": SimpleNamespace(type="file", size=5)}))
        shutdown_handler = ShutdownHandler.__new__(ShutdownHandler)
        shutdown_handler.should_stop = Mock(return_value=True)
        stdout = StringIO()

        with redirect_stdout(stdout):
            tasks = collect_top_level_tasks(
                api,
                ["top.txt"],
                self.temp_dir,
                [],
                {"max_items": None},
                None,
                None,
                FileFilter(),
                DownloadStats(),
                shutdown_handler,
            )

        self.assertEqual(tasks, [])
        self.assertIn("Stopping task collection due to shutdown request", stdout.getvalue())

    def test_collect_top_level_tasks_breaks_when_top_level_item_limit_is_reached(self):
        api = SimpleNamespace(drive=FakeDrive({"top.txt": SimpleNamespace(type="file", size=5)}))
        stats = DownloadStats()
        stats.files_total = 1
        shutdown_handler = ShutdownHandler.__new__(ShutdownHandler)
        shutdown_handler.should_stop = Mock(return_value=False)

        tasks = collect_top_level_tasks(
            api,
            ["top.txt"],
            self.temp_dir,
            [],
            {"max_items": 1},
            None,
            None,
            FileFilter(),
            stats,
            shutdown_handler,
        )

        self.assertEqual(tasks, [])

    def test_collect_top_level_tasks_rejects_symlinked_top_level_target(self):
        outside_root = tempfile.mkdtemp()
        try:
            os.symlink(outside_root, os.path.join(self.temp_dir, "escape.txt"))
            failures = []
            shutdown_handler = ShutdownHandler.__new__(ShutdownHandler)
            shutdown_handler.should_stop = Mock(return_value=False)

            tasks = collect_top_level_tasks(
                SimpleNamespace(drive=FakeDrive({"escape.txt": SimpleNamespace(type="file", size=5)})),
                ["escape.txt"],
                self.temp_dir,
                failures,
                {"max_items": None},
                None,
                None,
                FileFilter(),
                DownloadStats(),
                shutdown_handler,
            )

            self.assertEqual(tasks, [])
            self.assertEqual(len(failures), 1)
            self.assertIn("Path validation failed", failures[0])
        finally:
            shutil.rmtree(outside_root, ignore_errors=True)

    @patch("icloud_downloader_lib.execution.os.path.exists", return_value=False)
    @patch("icloud_downloader_lib.execution.download_worker", return_value=[])
    @patch("icloud_downloader_lib.execution.TQDM_AVAILABLE", False)
    def test_process_concurrent_downloads_prints_progress_without_progress_bar(
        self,
        _download_worker_mock,
        _path_exists_mock,
    ):
        stdout = StringIO()
        shutdown_handler = ShutdownHandler.__new__(ShutdownHandler)
        shutdown_handler.should_stop = Mock(return_value=False)

        with redirect_stdout(stdout):
            process_concurrent_downloads(
                [(Mock(), os.path.join(self.temp_dir, "file.bin"), "file.bin", {}, None)],
                [],
                {"dry_run": False, "workers": 1, "progress": False},
                FileFilter(),
                DownloadStats(),
                None,
                shutdown_handler,
            )

        self.assertIn("Progress: 1/1 files processed", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()