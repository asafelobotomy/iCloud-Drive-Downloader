"""Tests for execution helper functions and orchestration edge cases."""

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

from icloud_downloader_lib.execution import (
    check_free_space,
    collect_top_level_tasks,
    estimate_download_size,
    execute_download_session,
)
from icloud_downloader_lib.filters import FileFilter
from icloud_downloader_lib.inventory import DryRunInventory
from icloud_downloader_lib.state import DownloadManifest, DownloadStats, ShutdownHandler


class FakeDrive(dict):
    """Dictionary-backed drive stub."""

    def dir(self):
        return list(self.keys())


class TestExecutionHelpers(unittest.TestCase):
    """Test branch-heavy execution helpers."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("icloud_downloader_lib.execution.shutil.disk_usage")
    def test_check_free_space_exits_when_user_declines_low_space(self, disk_usage_mock):
        disk_usage_mock.return_value = SimpleNamespace(free=512 * 1024 * 1024)

        with patch("builtins.input", return_value="n"):
            with self.assertRaises(SystemExit) as exc_info:
                check_free_space(self.temp_dir, 1.0)

        self.assertEqual(exc_info.exception.code, 0)

    @patch("icloud_downloader_lib.execution.shutil.disk_usage")
    def test_check_free_space_reports_success_when_space_is_available(self, disk_usage_mock):
        disk_usage_mock.return_value = SimpleNamespace(free=3 * 1024**3)
        stdout = StringIO()

        with redirect_stdout(stdout):
            check_free_space(self.temp_dir, 1.0)

        self.assertIn("Free space available", stdout.getvalue())

    def test_estimate_download_size_extrapolates_beyond_the_first_50_items(self):
        drive = FakeDrive({f"file-{index}": SimpleNamespace(size=100, type="file") for index in range(60)})
        api = SimpleNamespace(drive=drive)

        estimate = estimate_download_size(api, list(drive.keys()))

        self.assertEqual(estimate["estimated_files"], 60)
        self.assertEqual(estimate["estimated_size"], 6000)

    def test_estimate_download_size_handles_folders_and_lookup_errors(self):
        drive = FakeDrive(
            {
                "folder": SimpleNamespace(type="folder"),
                "broken": object(),
            }
        )

        class BrokenDrive(FakeDrive):
            def __getitem__(self, key):
                if key == "broken":
                    raise RuntimeError("lookup failed")
                return super().__getitem__(key)

        api = SimpleNamespace(drive=BrokenDrive(drive))

        estimate = estimate_download_size(api, ["folder", "broken"])

        self.assertEqual(estimate["estimated_files"], 10)
        self.assertEqual(estimate["estimated_size"], 50 * 1024 * 1024)

    @patch("icloud_downloader_lib.execution.collect_download_tasks")
    def test_collect_top_level_tasks_collects_files_and_scans_folders(self, collect_download_tasks_mock):
        folder_item = SimpleNamespace(type="folder")
        file_item = SimpleNamespace(type="file", size=123)
        drive = FakeDrive({"Photos": folder_item, "note.txt": file_item})
        api = SimpleNamespace(drive=drive)
        failures = []
        stats = DownloadStats()
        manifest = DownloadManifest(os.path.join(self.temp_dir, "manifest.json"))
        shutdown_handler = ShutdownHandler.__new__(ShutdownHandler)
        shutdown_handler.should_stop = Mock(return_value=False)

        tasks = collect_top_level_tasks(
            api,
            ["Photos", "note.txt"],
            self.temp_dir,
            failures,
            {"max_items": None},
            manifest,
            None,
            FileFilter(include_patterns=["*.txt"]),
            stats,
            shutdown_handler,
        )

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0][2], "note.txt")
        self.assertEqual(stats.files_total, 1)
        collect_download_tasks_mock.assert_called_once()
        self.assertEqual(failures, [])

    @patch("icloud_downloader_lib.execution.collect_download_tasks")
    def test_collect_top_level_tasks_counts_all_root_items_even_after_max_items_cutoff(self, collect_download_tasks_mock):
        folder_item = SimpleNamespace(type="folder")
        file_item = SimpleNamespace(type="file", size=123)
        drive = FakeDrive({"Photos": folder_item, "Documents": folder_item, "note.txt": file_item})
        api = SimpleNamespace(drive=drive)
        failures = []
        stats = DownloadStats()
        manifest = DownloadManifest(os.path.join(self.temp_dir, "manifest.json"))
        shutdown_handler = ShutdownHandler.__new__(ShutdownHandler)
        shutdown_handler.should_stop = Mock(return_value=False)
        inventory = DryRunInventory()

        def hit_limit(*args, **kwargs):
            del args, kwargs
            stats.files_total = 50

        collect_download_tasks_mock.side_effect = hit_limit

        collect_top_level_tasks(
            api,
            ["Photos", "Documents", "note.txt"],
            self.temp_dir,
            failures,
            {"max_items": 50, "dry_run": True},
            manifest,
            None,
            FileFilter(),
            stats,
            shutdown_handler,
            collect_tasks=False,
            inventory=inventory,
        )

        summary = inventory.snapshot()

        self.assertEqual(summary["root_items"], 3)
        self.assertEqual(summary["root_folders"], 2)
        self.assertEqual(summary["root_files"], 1)
        self.assertEqual(failures, [])

    @patch("icloud_downloader_lib.execution.print_startup_banner")
    def test_execute_download_session_exits_when_drive_listing_is_empty(self, print_banner_mock):
        api = SimpleNamespace(drive=SimpleNamespace(dir=Mock(return_value=[])))
        args = SimpleNamespace(log=None, skip_confirm=False)

        with self.assertRaises(SystemExit) as exc_info:
            execute_download_session(
                api,
                args,
                {
                    "resume": False,
                    "dry_run": True,
                    "sequential": True,
                    "workers": 1,
                    "max_retries": 1,
                    "timeout": 60,
                    "max_depth": None,
                    "max_items": None,
                },
                None,
                self.temp_dir,
                [],
                [],
                None,
                None,
            )

        self.assertEqual(exc_info.exception.code, 1)
        print_banner_mock.assert_called_once()

    @patch("icloud_downloader_lib.execution.confirm_download", return_value=False)
    @patch("icloud_downloader_lib.execution.estimate_download_size", return_value={"estimated_files": 5, "estimated_size": 1024})
    def test_execute_download_session_creates_manifest_then_exits_when_user_declines_confirmation(
        self,
        estimate_download_size_mock,
        confirm_download_mock,
    ):
        created_manifest_paths = []

        class FakeManifest:
            def __init__(self, manifest_path, **kwargs):
                created_manifest_paths.append(manifest_path)

        api = SimpleNamespace(drive=SimpleNamespace(dir=Mock(return_value=["top.txt"])))
        args = SimpleNamespace(log=None, skip_confirm=False)

        with self.assertRaises(SystemExit) as exc_info:
            execute_download_session(
                api,
                args,
                {
                    "resume": True,
                    "dry_run": False,
                    "sequential": True,
                    "workers": 1,
                    "max_retries": 1,
                    "timeout": 60,
                    "max_depth": None,
                    "max_items": None,
                },
                None,
                self.temp_dir,
                [],
                [],
                None,
                None,
                manifest_cls=FakeManifest,
            )

        self.assertEqual(exc_info.exception.code, 0)
        self.assertEqual(len(created_manifest_paths), 1)
        estimate_download_size_mock.assert_called_once()
        confirm_download_mock.assert_called_once()

    @patch("icloud_downloader_lib.execution.print_session_summary")
    @patch("icloud_downloader_lib.execution.process_sequential_downloads")
    @patch("icloud_downloader_lib.execution.ShutdownHandler")
    @patch("icloud_downloader_lib.execution.StructuredLogger")
    def test_execute_download_session_runs_sequential_flow_and_logs_session_start(
        self,
        logger_cls_mock,
        shutdown_handler_cls_mock,
        process_sequential_downloads_mock,
        print_session_summary_mock,
    ):
        logger = Mock()
        logger_cls_mock.return_value = logger
        shutdown_handler = Mock()
        shutdown_handler_cls_mock.return_value = shutdown_handler
        api = SimpleNamespace(drive=SimpleNamespace(dir=Mock(return_value=["top.txt"])))
        args = SimpleNamespace(log=os.path.join(self.temp_dir, "events.jsonl"), skip_confirm=True)

        execute_download_session(
            api,
            args,
            {
                "resume": False,
                "dry_run": False,
                "sequential": True,
                "workers": 1,
                "max_retries": 1,
                "timeout": 60,
                "max_depth": None,
                "max_items": None,
                "session_dir": os.path.join(self.temp_dir, "session"),
            },
            Mock(),
            self.temp_dir,
            ["*.jpg"],
            ["*.tmp"],
            100,
            200,
        )

        logger.log.assert_called_once()
        self.assertNotIn("session_dir", logger.log.call_args.kwargs["config"])
        process_sequential_downloads_mock.assert_called_once()
        print_session_summary_mock.assert_called_once()

    @patch("icloud_downloader_lib.execution.print_session_summary")
    @patch("icloud_downloader_lib.execution.print_dry_run_inventory_summary")
    @patch("icloud_downloader_lib.execution.scan_drive_inventory")
    @patch("icloud_downloader_lib.execution.ShutdownHandler")
    def test_execute_download_session_uses_inventory_summary_for_dry_runs(
        self,
        shutdown_handler_cls_mock,
        scan_drive_inventory_mock,
        print_dry_run_inventory_summary_mock,
        print_session_summary_mock,
    ):
        shutdown_handler = Mock()
        shutdown_handler.should_stop.return_value = False
        shutdown_handler_cls_mock.return_value = shutdown_handler
        api = SimpleNamespace(drive=FakeDrive({"Photos": SimpleNamespace(type="folder")}))
        args = SimpleNamespace(log=None, skip_confirm=True)

        execute_download_session(
            api,
            args,
            {
                "resume": False,
                "dry_run": True,
                "sequential": False,
                "workers": 2,
                "max_retries": 1,
                "timeout": 60,
                "max_depth": 2,
                "max_items": 50,
            },
            Mock(),
            self.temp_dir,
            [],
            [],
            None,
            None,
        )

        scan_drive_inventory_mock.assert_called_once()
        self.assertIs(scan_drive_inventory_mock.call_args.args[0], api)
        self.assertEqual(scan_drive_inventory_mock.call_args.args[1], ["Photos"])
        print_dry_run_inventory_summary_mock.assert_called_once()
        print_session_summary_mock.assert_called_once()

    @patch("icloud_downloader_lib.execution.print_session_summary")
    @patch("icloud_downloader_lib.execution.process_concurrent_downloads")
    @patch("icloud_downloader_lib.execution.collect_top_level_tasks", return_value=[("item", "/tmp/file", "file", {}, None)])
    @patch("icloud_downloader_lib.execution.ShutdownHandler")
    def test_execute_download_session_runs_concurrent_flow_when_sequential_is_disabled(
        self,
        shutdown_handler_cls_mock,
        collect_top_level_tasks_mock,
        process_concurrent_downloads_mock,
        print_session_summary_mock,
    ):
        shutdown_handler_cls_mock.return_value = Mock()
        api = SimpleNamespace(drive=SimpleNamespace(dir=Mock(return_value=["top.txt"])))
        args = SimpleNamespace(log=None, skip_confirm=True)

        execute_download_session(
            api,
            args,
            {
                "resume": False,
                "dry_run": False,
                "sequential": False,
                "workers": 2,
                "max_retries": 1,
                "timeout": 60,
                "max_depth": None,
                "max_items": None,
            },
            Mock(),
            self.temp_dir,
            [],
            [],
            None,
            None,
        )

        collect_top_level_tasks_mock.assert_called_once()
        process_concurrent_downloads_mock.assert_called_once()
        print_session_summary_mock.assert_called_once()
