"""Tests for cache-aware CLI, app, and execution workflows."""

import os
import shutil
import sys
import tempfile
import unittest
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader_lib.app import main as app_main
from icloud_downloader_lib.cli import build_runtime_config, parse_arguments
from icloud_downloader_lib.execution import execute_download_session
from tests.test_app_cli_edges import make_args


class TestCacheAwareCli(unittest.TestCase):
    """Test cache-aware CLI parsing and config merging."""

    def test_build_runtime_config_merges_inventory_cache_settings(self):
        args = SimpleNamespace(
            inventory_cache="/tmp/cache.json",
            build_inventory_cache=True,
            refresh_inventory_cache=False,
            select_from_cache=True,
            selection_mode="files",
        )

        config = build_runtime_config(
            args,
            wizard_config={},
            preset_config={},
            file_config={"inventory_cache": "/tmp/old-cache.json", "selection_mode": "mixed"},
        )

        self.assertEqual(config["inventory_cache"], "/tmp/cache.json")
        self.assertTrue(config["build_inventory_cache"])
        self.assertTrue(config["select_from_cache"])
        self.assertEqual(config["selection_mode"], "files")

    def test_build_runtime_config_uses_file_backed_selector_flags(self):
        args = SimpleNamespace()

        config = build_runtime_config(
            args,
            wizard_config={},
            preset_config={},
            file_config={
                "select_from_cache": True,
                "refresh_inventory_cache": True,
                "build_inventory_cache": False,
                "selection_mode": "folders",
            },
        )

        self.assertTrue(config["select_from_cache"])
        self.assertTrue(config["refresh_inventory_cache"])
        self.assertFalse(config["build_inventory_cache"])
        self.assertEqual(config["selection_mode"], "folders")

    def test_parse_arguments_rejects_selection_mode_without_cache_selector(self):
        stderr = StringIO()

        with patch.object(sys, "argv", ["icloud_downloader.py", "--selection-mode", "files"]):
            with patch("sys.stderr", stderr):
                with self.assertRaises(SystemExit) as exc_info:
                    parse_arguments()

        self.assertEqual(exc_info.exception.code, 2)
        self.assertIn("--selection-mode requires --select-from-cache", stderr.getvalue())

    def test_parse_arguments_accepts_inventory_cache_flags(self):
        with patch.object(
            sys,
            "argv",
            [
                "icloud_downloader.py",
                "--select-from-cache",
                "--selection-mode",
                "folders",
                "--inventory-cache",
                "/tmp/cache.json",
                "--refresh-inventory-cache",
            ],
        ):
            args = parse_arguments()

        self.assertTrue(args.select_from_cache)
        self.assertTrue(args.refresh_inventory_cache)
        self.assertEqual(args.selection_mode, "folders")
        self.assertEqual(args.inventory_cache, "/tmp/cache.json")


class TestCacheAwareAppAndExecution(unittest.TestCase):
    """Test cache build and selection-aware execution flows."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_main_build_inventory_cache_saves_cache_and_exits_before_download(self):
        args = make_args(destination=self.temp_dir, build_inventory_cache=True)
        api = Mock()
        api.drive.dir.return_value = ["Docs"]

        with patch("icloud_downloader_lib.app.authenticate_session", return_value=api):
            with patch("icloud_downloader_lib.app.scan_drive_inventory") as scan_drive_inventory_mock:
                with patch("icloud_downloader_lib.app.save_inventory_cache") as save_inventory_cache_mock:
                    with patch("icloud_downloader_lib.app.print_dry_run_inventory_summary"):
                        with patch("icloud_downloader_lib.app.execute_download_session") as execute_download_session_mock:
                            with self.assertRaises(SystemExit) as exc_info:
                                app_main(
                                    parse_arguments_func=lambda: args,
                                    check_free_space_func=Mock(),
                                )

        self.assertEqual(exc_info.exception.code, 0)
        scan_drive_inventory_mock.assert_called_once()
        save_inventory_cache_mock.assert_called_once()
        execute_download_session_mock.assert_not_called()

    @patch("icloud_downloader_lib.execution.confirm_download", return_value=False)
    @patch("icloud_downloader_lib.execution.estimate_download_size")
    def test_execute_download_session_uses_selection_summary_for_confirmation(
        self,
        estimate_download_size_mock,
        confirm_download_mock,
    ):
        api = SimpleNamespace(drive=SimpleNamespace(dir=Mock(return_value=["top.txt"])))
        args = SimpleNamespace(log=None, skip_confirm=False)

        with self.assertRaises(SystemExit) as exc_info:
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
                    "selection_summary": {"files": 2, "bytes": 2048},
                },
                None,
                self.temp_dir,
                [],
                [],
                None,
                None,
            )

        self.assertEqual(exc_info.exception.code, 0)
        estimate_download_size_mock.assert_not_called()
        confirm_download_mock.assert_called_once_with({"estimated_files": 2, "estimated_size": 2048})

    def test_main_honors_wizard_selector_settings_for_drive_browsing(self):
        args = make_args(wizard=True)
        api = Mock()
        api.drive.dir.return_value = ["Docs"]

        with patch("icloud_downloader_lib.app.authenticate_session", return_value=api):
            with patch("icloud_downloader_lib.app.scan_drive_inventory") as scan_drive_inventory_mock:
                with patch("icloud_downloader_lib.app.save_inventory_cache") as save_inventory_cache_mock:
                    with patch("icloud_downloader_lib.app.load_inventory_cache", return_value={"nodes": [], "metadata": {}}) as load_inventory_cache_mock:
                        with patch(
                            "icloud_downloader_lib.app.run_inventory_selector",
                            return_value={
                                "selected_files": set(),
                                "selected_folders": {"Docs"},
                                "summary": {"files": 3, "bytes": 900},
                            },
                        ) as run_inventory_selector_mock:
                            with patch("icloud_downloader_lib.app.execute_download_session") as execute_download_session_mock:
                                app_main(
                                    parse_arguments_func=lambda: args,
                                    run_setup_wizard_func=lambda: {
                                        "destination": self.temp_dir,
                                        "refresh_inventory_cache": True,
                                        "select_from_cache": True,
                                        "selection_mode": "folders",
                                        "dry_run": True,
                                    },
                                    check_free_space_func=Mock(),
                                )

        scan_drive_inventory_mock.assert_called_once()
        save_inventory_cache_mock.assert_called_once()
        load_inventory_cache_mock.assert_called_once()
        run_inventory_selector_mock.assert_called_once()
        self.assertEqual(run_inventory_selector_mock.call_args.args[1], "folders")
        execute_download_session_mock.assert_called_once()