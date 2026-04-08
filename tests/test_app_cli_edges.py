"""Tests for app and CLI edge paths not covered by the main flow suites."""

import json
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

from icloud_downloader_lib.app import main as app_main
from icloud_downloader_lib.cli import (
    build_filter_context,
    build_runtime_config,
    extract_preset_config,
    load_config_file,
    resolve_download_path,
    save_config_file,
)
from icloud_downloader_lib.definitions import DEFAULT_DOWNLOAD_PATH, DEFAULT_MIN_FREE_SPACE_GB, PRESETS


def make_args(**overrides):
    defaults = {
        "auth_status": False,
        "chunk_size": None,
        "china_mainland": False,
        "config": None,
        "destination": DEFAULT_DOWNLOAD_PATH,
        "dry_run": False,
        "exclude": None,
        "include": None,
        "inventory_cache": None,
        "list_presets": False,
        "log": None,
        "log_level": None,
        "max_depth": None,
        "max_items": None,
        "max_size": None,
        "min_free_space": None,
        "min_size": None,
        "no_color": False,
        "preset": None,
        "progress": None,
        "resume": None,
        "retries": None,
        "save_config": None,
        "build_inventory_cache": None,
        "refresh_inventory_cache": None,
        "sequential": None,
        "select_from_cache": None,
        "selection_mode": None,
        "session_dir": None,
        "show_config": False,
        "store_in_keyring": False,
        "timeout": None,
        "use_keyring": False,
        "verbose": None,
        "wizard": False,
        "workers": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestAppEdgePaths(unittest.TestCase):
    """Test app-level early exits and setup branches."""

    def test_main_lists_presets_and_exits(self):
        args = make_args(list_presets=True)

        with patch("icloud_downloader_lib.app.print_presets") as print_presets_mock:
            with self.assertRaises(SystemExit) as exc_info:
                app_main(parse_arguments_func=lambda: args)

        self.assertEqual(exc_info.exception.code, 0)
        print_presets_mock.assert_called_once_with()

    def test_main_loads_config_and_prints_selected_preset_before_show_config_exit(self):
        args = make_args(config="/tmp/config.json", preset="photos", show_config=True)
        stdout = StringIO()

        with patch("icloud_downloader_lib.app.load_config_file", return_value={"destination": "/tmp/from-config"}) as load_config_mock:
            with redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as exc_info:
                    app_main(parse_arguments_func=lambda: args)

        self.assertEqual(exc_info.exception.code, 0)
        self.assertIn("Preset:", stdout.getvalue())
        self.assertIn(PRESETS["photos"]["name"], stdout.getvalue())
        load_config_mock.assert_called_once_with("/tmp/config.json")

    def test_main_saves_config_and_exits_without_authenticating(self):
        args = make_args(
            save_config="/tmp/config-private.json",
            destination="/tmp/downloads",
            retries=7,
            timeout=15,
            chunk_size=2048,
            min_free_space=3.5,
            workers=4,
            session_dir="/tmp/session",
            include=["*.jpg"],
            exclude=["*.tmp"],
            min_size=10,
            max_size=20,
            max_depth=2,
            max_items=3,
            log_level="DEBUG",
            verbose=True,
            sequential=True,
            dry_run=True,
            progress=False,
            resume=False,
            china_mainland=True,
            use_keyring=True,
        )
        stdout = StringIO()
        save_config_file_mock = Mock()

        with patch("icloud_downloader_lib.app.authenticate_session") as authenticate_session_mock:
            with redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as exc_info:
                    app_main(
                        parse_arguments_func=lambda: args,
                        save_config_file_func=save_config_file_mock,
                    )

        self.assertEqual(exc_info.exception.code, 0)
        save_config_file_mock.assert_called_once()
        saved_path, saved_payload = save_config_file_mock.call_args.args
        self.assertEqual(saved_path, "/tmp/config-private.json")
        self.assertEqual(saved_payload["destination"], "/tmp/downloads")
        self.assertTrue(saved_payload["use_keyring"])
        self.assertFalse(saved_payload["resume"])
        self.assertIn("Configuration saved. Exiting.", stdout.getvalue())
        authenticate_session_mock.assert_not_called()

    def test_main_auto_wizard_prints_banner_and_disables_color(self):
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))

        args = make_args(no_color=True)
        wizard_mock = Mock(
            return_value={
                "_apple_id": "user@example.com",
                "_password": "app-secret",
                "destination": temp_dir,
                "dry_run": True,
            }
        )
        stdout = StringIO()

        with patch("icloud_downloader_lib.app.Colors.disable") as disable_mock:
            with patch("icloud_downloader_lib.app.authenticate_session", return_value=Mock()) as authenticate_session_mock:
                with patch("icloud_downloader_lib.app.execute_download_session") as execute_download_session_mock:
                    with redirect_stdout(stdout):
                        app_main(
                            parse_arguments_func=lambda: args,
                            run_setup_wizard_func=wizard_mock,
                            check_free_space_func=Mock(),
                        )

        self.assertIn("Running in interactive mode", stdout.getvalue())
        disable_mock.assert_called_once_with()
        wizard_mock.assert_called_once_with()
        authenticate_session_mock.assert_called_once()
        execute_download_session_mock.assert_called_once()

    def test_main_exits_cleanly_on_keyboard_interrupt_during_wizard(self):
        args = make_args()
        stdout = StringIO()

        with redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as exc_info:
                app_main(
                    parse_arguments_func=lambda: args,
                    run_setup_wizard_func=Mock(side_effect=KeyboardInterrupt),
                )

        self.assertEqual(exc_info.exception.code, 130)
        self.assertIn("Cancelled by user.", stdout.getvalue())

    def test_main_creates_destination_directory_when_missing(self):
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        missing_path = os.path.join(temp_dir, "downloads")
        args = make_args(destination=missing_path, dry_run=True)
        check_free_space_mock = Mock()

        def fake_exists(path):
            if path == missing_path:
                return False
            return os.path.exists(path)

        with patch("icloud_downloader_lib.app.os.path.exists", side_effect=fake_exists):
            with patch("icloud_downloader_lib.app.os.makedirs") as makedirs_mock:
                with patch("icloud_downloader_lib.app.os.chmod") as chmod_mock:
                    with patch("icloud_downloader_lib.app.authenticate_session", return_value=Mock()):
                        with patch("icloud_downloader_lib.app.execute_download_session"):
                            app_main(
                                parse_arguments_func=lambda: args,
                                check_free_space_func=check_free_space_mock,
                            )

        makedirs_mock.assert_called_once_with(missing_path, exist_ok=True)
        self.assertEqual(chmod_mock.call_args_list[0].args, (missing_path, 0o700))
        check_free_space_mock.assert_called_once_with(missing_path, DEFAULT_MIN_FREE_SPACE_GB)

class TestCliEdgePaths(unittest.TestCase):
    """Test CLI helper behavior that is not covered by parser tests."""

    def test_load_config_file_reads_valid_json(self):
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        config_path = os.path.join(temp_dir, "config.json")
        stdout = StringIO()

        with open(config_path, "w") as config_file:
            config_file.write('{"workers": 4, "use_keyring": true}')

        with redirect_stdout(stdout):
            config = load_config_file(config_path)

        self.assertEqual(config, {"workers": 4, "use_keyring": True})
        self.assertIn("Loaded configuration from:", stdout.getvalue())

    def test_load_config_file_reads_relative_json_path(self):
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        config_dir = os.path.join(temp_dir, "examples")
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, "config.json")
        relative_path = os.path.join("examples", "config.json")
        stdout = StringIO()

        with open(config_path, "w", encoding="utf-8") as config_file:
            config_file.write('{"workers": 4, "use_keyring": true}')

        previous_cwd = os.getcwd()
        os.chdir(temp_dir)
        self.addCleanup(lambda: os.chdir(previous_cwd))

        with redirect_stdout(stdout):
            config = load_config_file(relative_path)

        self.assertEqual(config, {"workers": 4, "use_keyring": True})
        self.assertIn("Loaded configuration from:", stdout.getvalue())

    def test_load_config_file_returns_empty_dict_for_missing_path(self):
        self.assertEqual(load_config_file("/tmp/does-not-exist.json"), {})

    def test_load_config_file_warns_and_returns_empty_dict_for_invalid_json(self):
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        config_path = os.path.join(temp_dir, "broken.json")
        stdout = StringIO()

        with open(config_path, "w") as config_file:
            config_file.write("{not-valid-json")

        with redirect_stdout(stdout):
            config = load_config_file(config_path)

        self.assertEqual(config, {})
        self.assertIn("Warning: Could not load config file", stdout.getvalue())

    def test_save_config_file_warns_when_write_fails(self):
        stdout = StringIO()

        with patch("icloud_downloader_lib.cli.open_secure_file", side_effect=IOError("disk full")):
            with redirect_stdout(stdout):
                save_config_file("/tmp/config.json", {"destination": "/tmp/downloads"})

        self.assertIn("Warning: Could not save config file", stdout.getvalue())

    def test_save_config_file_writes_relative_path(self):
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        relative_path = os.path.join("examples", "config.json")
        config_path = os.path.join(temp_dir, relative_path)

        previous_cwd = os.getcwd()
        os.chdir(temp_dir)
        self.addCleanup(lambda: os.chdir(previous_cwd))

        save_config_file(relative_path, {"destination": "/tmp/downloads", "workers": 2})

        with open(config_path, "r", encoding="utf-8") as config_file:
            self.assertEqual(json.load(config_file), {"destination": "/tmp/downloads", "workers": 2})

    def test_build_runtime_config_prefers_wizard_values_when_cli_is_absent(self):
        args = make_args(use_keyring=None)

        config = build_runtime_config(
            args,
            wizard_config={
                "workers": 6,
                "use_keyring": True,
                "progress": False,
                "select_from_cache": True,
                "refresh_inventory_cache": True,
            },
            preset_config={"workers": 4, "use_keyring": False, "progress": True},
            file_config={"workers": 2, "use_keyring": False, "progress": True},
        )

        self.assertEqual(config["workers"], 6)
        self.assertTrue(config["use_keyring"])
        self.assertFalse(config["progress"])
        self.assertTrue(config["select_from_cache"])
        self.assertTrue(config["refresh_inventory_cache"])

    def test_build_runtime_config_uses_preset_booleans_when_wizard_is_absent(self):
        args = make_args(use_keyring=None, progress=None)

        config = build_runtime_config(
            args,
            wizard_config={},
            preset_config={"use_keyring": True, "progress": False},
            file_config={"use_keyring": False, "progress": True},
        )

        self.assertTrue(config["use_keyring"])
        self.assertFalse(config["progress"])

    def test_extract_preset_config_returns_runtime_values_without_metadata(self):
        config = extract_preset_config(make_args(preset="photos"))

        self.assertNotIn("name", config)
        self.assertNotIn("description", config)
        self.assertEqual(config, {key: value for key, value in PRESETS["photos"].items() if key not in {"name", "description"}})
        self.assertEqual(extract_preset_config(make_args()), {})

    def test_build_filter_context_uses_file_config_values(self):
        file_filter, include_patterns, exclude_patterns, min_size, max_size = build_filter_context(
            make_args(),
            wizard_config={},
            preset_config={},
            file_config={
                "include": ["*.jpg"],
                "exclude": ["*.tmp"],
                "min_size": 10,
                "max_size": 99,
            },
        )

        self.assertEqual(include_patterns, ["*.jpg"])
        self.assertEqual(exclude_patterns, ["*.tmp"])
        self.assertEqual(min_size, 10)
        self.assertEqual(max_size, 99)
        self.assertTrue(file_filter.should_include("photo.jpg", size=50))
        self.assertFalse(file_filter.should_include("scratch.tmp", size=50))

    def test_resolve_download_path_uses_file_config_destination(self):
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        relative_path = os.path.join(temp_dir, "..", os.path.basename(temp_dir), "downloads")

        resolved_path = resolve_download_path(
            make_args(destination=None),
            wizard_config={},
            preset_config={},
            file_config={"destination": relative_path},
        )

        self.assertEqual(resolved_path, os.path.abspath(relative_path))


if __name__ == "__main__":
    unittest.main()