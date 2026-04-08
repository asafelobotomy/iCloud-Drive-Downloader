"""Tests for CLI configuration, wizard, and main flow behavior."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

# Add parent directory to path to import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader import DEFAULT_DOWNLOAD_PATH, main, run_setup_wizard, save_config_file
from icloud_downloader_lib.cli import build_runtime_config, parse_arguments


class TestConfigPersistence(unittest.TestCase):
    """Test configuration persistence behavior."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "config-private.json")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_save_config_file_omits_private_session_fields(self):
        save_config_file(
            self.config_path,
            {
                "destination": "/tmp/downloads",
                "workers": 3,
                "use_keyring": True,
                "store_password_in_keyring": True,
                "store_in_keyring": True,
                "_apple_id": "user@example.com",
                "_password": "app-secret",
                "_save_as": "config-private.json",
            },
        )

        with open(self.config_path, "r") as config_file:
            saved_config = json.load(config_file)

        self.assertEqual(
            saved_config,
            {
                "destination": "/tmp/downloads",
                "workers": 3,
                "use_keyring": True,
                "store_password_in_keyring": True,
            },
        )

        permissions = os.stat(self.config_path).st_mode & 0o777
        self.assertEqual(permissions, 0o600)


class TestMainFlow(unittest.TestCase):
    """Test main() behavior for wizard-driven configuration."""

    def _make_args(self, **overrides):
        defaults = {
            "wizard": True,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    @patch("icloud_downloader.DownloadManifest")
    @patch("icloud_downloader.check_free_space")
    @patch("icloud_downloader.save_config_file")
    @patch("icloud_downloader.run_main_menu")
    @patch("icloud_downloader.parse_arguments")
    @patch("icloud_downloader.PyiCloudService")
    def test_main_honors_wizard_dry_run_and_saves_local_config(
        self,
        pyicloud_service_mock,
        parse_arguments_mock,
        run_main_menu_mock,
        save_config_file_mock,
        check_free_space_mock,
        manifest_mock,
    ):
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))

        parse_arguments_mock.return_value = self._make_args()
        run_main_menu_mock.return_value = {
            "_apple_id": "user@example.com",
            "_password": "app-secret",
            "destination": temp_dir,
            "dry_run": True,
            "workers": 2,
        }

        api = Mock()
        api.requires_2fa = False
        api.drive.dir.return_value = []
        pyicloud_service_mock.return_value = api

        with self.assertRaises(SystemExit):
            main()

        pyicloud_service_mock.assert_called_once_with(
            "user@example.com",
            "app-secret",
            cookie_directory=None,
            china_mainland=False,
        )
        check_free_space_mock.assert_called_once()
        manifest_mock.assert_not_called()

    @patch("icloud_downloader.DownloadManifest")
    @patch("icloud_downloader.check_free_space")
    @patch("icloud_downloader.save_config_file")
    @patch("icloud_downloader.run_setup_wizard")
    @patch("icloud_downloader.parse_arguments")
    @patch("icloud_downloader.PyiCloudService")
    def test_main_show_config_prints_resolved_config_and_exits(
        self,
        pyicloud_service_mock,
        parse_arguments_mock,
        run_setup_wizard_mock,
        save_config_file_mock,
        check_free_space_mock,
        manifest_mock,
    ):
        parse_arguments_mock.return_value = self._make_args(show_config=True, config=None, wizard=False)
        stdout = StringIO()

        with redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as exc_info:
                main()

        self.assertEqual(exc_info.exception.code, 0)
        rendered = stdout.getvalue()
        self.assertIn('"destination":', rendered)
        self.assertIn('"resume": true', rendered)
        self.assertIn('"progress": true', rendered)
        self.assertNotIn(f'"destination": "{DEFAULT_DOWNLOAD_PATH}"', rendered)
        self.assertIn('"destination": "~/iCloud_Drive_Download"', rendered)
        pyicloud_service_mock.assert_not_called()
        run_setup_wizard_mock.assert_not_called()
        save_config_file_mock.assert_not_called()
        check_free_space_mock.assert_not_called()
        manifest_mock.assert_not_called()

    @patch("icloud_downloader.DownloadManifest")
    @patch("icloud_downloader.check_free_space")
    @patch("icloud_downloader.save_config_file")
    @patch("icloud_downloader.run_setup_wizard")
    @patch("icloud_downloader.parse_arguments")
    @patch("icloud_downloader.PyiCloudService")
    def test_main_show_config_redacts_absolute_include_and_exclude_patterns(
        self,
        pyicloud_service_mock,
        parse_arguments_mock,
        run_setup_wizard_mock,
        save_config_file_mock,
        check_free_space_mock,
        manifest_mock,
    ):
        parse_arguments_mock.return_value = self._make_args(
            show_config=True,
            config=None,
            wizard=False,
            include=["/tmp/private/photos/*.jpg"],
            exclude=["/tmp/private/cache/*.tmp"],
        )
        stdout = StringIO()

        with redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as exc_info:
                main()

        self.assertEqual(exc_info.exception.code, 0)
        rendered = stdout.getvalue()
        self.assertNotIn("/tmp/private/photos/*.jpg", rendered)
        self.assertNotIn("/tmp/private/cache/*.tmp", rendered)
        self.assertIn('"include": [', rendered)
        self.assertIn('".../*.jpg"', rendered)
        self.assertIn('".../*.tmp"', rendered)
        pyicloud_service_mock.assert_not_called()
        run_setup_wizard_mock.assert_not_called()
        save_config_file_mock.assert_not_called()
        check_free_space_mock.assert_not_called()
        manifest_mock.assert_not_called()

    @patch("icloud_downloader_lib.app.inspect_auth_status")
    @patch("icloud_downloader.DownloadManifest")
    @patch("icloud_downloader.check_free_space")
    @patch("icloud_downloader.save_config_file")
    @patch("icloud_downloader.run_setup_wizard")
    @patch("icloud_downloader.parse_arguments")
    @patch("icloud_downloader.PyiCloudService")
    def test_main_auth_status_prints_json_and_exits(
        self,
        pyicloud_service_mock,
        parse_arguments_mock,
        run_setup_wizard_mock,
        save_config_file_mock,
        check_free_space_mock,
        manifest_mock,
        inspect_auth_status_mock,
    ):
        parse_arguments_mock.return_value = self._make_args(auth_status=True, config=None, wizard=False)
        inspect_auth_status_mock.return_value = {
            "authenticated": True,
            "trusted_session": True,
            "session_dir": "/tmp/icloud-session",
        }
        stdout = StringIO()

        with redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as exc_info:
                main()

        self.assertEqual(exc_info.exception.code, 0)
        rendered = stdout.getvalue()
        self.assertIn('"authenticated": true', rendered)
        self.assertIn('"session_dir": ".../icloud-session"', rendered)
        inspect_auth_status_mock.assert_called_once()
        pyicloud_service_mock.assert_not_called()
        run_setup_wizard_mock.assert_not_called()
        save_config_file_mock.assert_not_called()
        check_free_space_mock.assert_not_called()
        manifest_mock.assert_not_called()


class TestCliArgumentParsing(unittest.TestCase):
    """Test CLI parsing, precedence, and validation behavior."""

    def test_build_runtime_config_uses_preset_when_cli_arg_is_absent(self):
        args = SimpleNamespace()

        config = build_runtime_config(
            args,
            wizard_config={},
            preset_config={"workers": 5, "timeout": 120},
            file_config={},
        )

        self.assertEqual(config["workers"], 5)
        self.assertEqual(config["timeout"], 120)

    def test_build_runtime_config_prefers_cli_over_file_config(self):
        args = SimpleNamespace(workers=2, timeout=30)

        config = build_runtime_config(
            args,
            wizard_config={},
            preset_config={"workers": 5},
            file_config={"workers": 7, "timeout": 120},
        )

        self.assertEqual(config["workers"], 2)
        self.assertEqual(config["timeout"], 30)

    def test_build_runtime_config_uses_file_log_level_when_cli_arg_is_absent(self):
        args = SimpleNamespace()

        config = build_runtime_config(
            args,
            wizard_config={},
            preset_config={},
            file_config={"log_level": "DEBUG"},
        )

        self.assertEqual(config["log_level"], "DEBUG")

    def test_build_runtime_config_supports_positive_progress_and_resume_config(self):
        args = SimpleNamespace()

        config = build_runtime_config(
            args,
            wizard_config={},
            preset_config={},
            file_config={"progress": False, "resume": False},
        )

        self.assertFalse(config["progress"])
        self.assertFalse(config["resume"])

    def test_build_runtime_config_cli_booleans_override_saved_config(self):
        args = SimpleNamespace(progress=True, resume=True)

        config = build_runtime_config(
            args,
            wizard_config={},
            preset_config={},
            file_config={"progress": False, "resume": False},
        )

        self.assertTrue(config["progress"])
        self.assertTrue(config["resume"])

    def test_build_runtime_config_merges_auth_session_settings(self):
        args = SimpleNamespace(session_dir="/tmp/new-session", use_keyring=True)

        config = build_runtime_config(
            args,
            wizard_config={},
            preset_config={},
            file_config={
                "session_dir": "/tmp/old-session",
                "china_mainland": True,
                "use_keyring": False,
                "store_password_in_keyring": True,
            },
        )

        self.assertEqual(config["session_dir"], "/tmp/new-session")
        self.assertTrue(config["use_keyring"])
        self.assertTrue(config["china_mainland"])
        self.assertTrue(config["store_password_in_keyring"])

    def test_build_runtime_config_honors_legacy_negative_boolean_keys(self):
        args = SimpleNamespace()

        config = build_runtime_config(
            args,
            wizard_config={},
            preset_config={},
            file_config={"no_progress": True, "no_resume": True},
        )

        self.assertFalse(config["progress"])
        self.assertFalse(config["resume"])

    def test_parse_arguments_rejects_min_size_larger_than_max_size(self):
        stderr = StringIO()

        with patch.object(
            sys,
            "argv",
            ["icloud_downloader.py", "--min-size", "20", "--max-size", "10"],
        ):
            with redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as exc_info:
                    parse_arguments()

        self.assertEqual(exc_info.exception.code, 2)
        self.assertIn("--min-size cannot be greater than --max-size", stderr.getvalue())

    def test_parse_arguments_rejects_out_of_range_worker_count(self):
        stderr = StringIO()

        with patch.object(sys, "argv", ["icloud_downloader.py", "--workers", "11"]):
            with redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as exc_info:
                    parse_arguments()

        self.assertEqual(exc_info.exception.code, 2)
        self.assertIn("must be between 1 and 10", stderr.getvalue())

    def test_parse_arguments_accepts_list_presets_flag(self):
        with patch.object(sys, "argv", ["icloud_downloader.py", "--list-presets"]):
            args = parse_arguments()

        self.assertTrue(args.list_presets)

    def test_parse_arguments_accepts_boolean_toggle_flags(self):
        with patch.object(
            sys,
            "argv",
            ["icloud_downloader.py", "--resume", "--no-progress", "--show-config"],
        ):
            args = parse_arguments()

        self.assertTrue(args.resume)
        self.assertFalse(args.progress)
        self.assertTrue(args.show_config)

    def test_parse_arguments_accepts_auth_session_flags(self):
        with patch.object(
            sys,
            "argv",
            [
                "icloud_downloader.py",
                "--auth-status",
                "--session-dir",
                "/tmp/icloud-session",
                "--china-mainland",
                "--use-keyring",
                "--store-in-keyring",
            ],
        ):
            args = parse_arguments()

        self.assertTrue(args.auth_status)
        self.assertEqual(args.session_dir, "/tmp/icloud-session")
        self.assertTrue(args.china_mainland)
        self.assertTrue(args.use_keyring)
        self.assertTrue(args.store_in_keyring)
