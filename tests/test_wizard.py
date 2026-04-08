"""Tests for interactive wizard and configure-menu behavior."""

import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader import DEFAULT_DOWNLOAD_PATH
from icloud_downloader_lib.presentation import Colors
from icloud_downloader_lib.wizard import (
    prompt_yes_no,
    run_configure_menu,
    run_main_menu,
    run_setup_wizard,
    _migrate_saved_config,
)


class TestInteractiveWizard(unittest.TestCase):
    """Test configure-first wizard behavior."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_prompt_yes_no_respects_defaults_and_negative_answers(self):
        self.assertTrue(prompt_yes_no(lambda _prompt: "", "Prompt: ", default=True))
        self.assertFalse(prompt_yes_no(lambda _prompt: "no", "Prompt: ", default=True))

    @patch.dict(os.environ, {"ICLOUD_APPLE_ID": "", "ICLOUD_PASSWORD": ""}, clear=False)
    def test_run_setup_wizard_carries_saved_preferences_and_redacts_saved_apple_id(self):
        saved = {
            "destination": "/tmp/downloads",
            "workers": 5,
            "dry_run": True,
            "resume": False,
            "save_password": True,
            "session_dir": "/tmp/icloud-session",
            "china_mainland": True,
            "save_apple_id": True,
            "saved_apple_id": "saved@example.com",
            "refresh_inventory_cache": True,
            "select_from_cache": True,
            "selection_mode": "mixed",
        }
        stdout = StringIO()

        with redirect_stdout(stdout):
            wizard_config = run_setup_wizard(
                saved_config=saved,
                input_func=lambda _prompt: "",
                getpass_func=lambda _prompt: "app-secret",
            )

        self.assertEqual(wizard_config["_apple_id"], "saved@example.com")
        self.assertEqual(wizard_config["_password"], "app-secret")
        self.assertEqual(wizard_config["destination"], "/tmp/downloads")
        self.assertEqual(wizard_config["workers"], 5)
        self.assertTrue(wizard_config["dry_run"])
        self.assertFalse(wizard_config["resume"])
        self.assertTrue(wizard_config["use_keyring"])
        self.assertTrue(wizard_config["store_password_in_keyring"])
        self.assertEqual(wizard_config["session_dir"], "/tmp/icloud-session")
        self.assertTrue(wizard_config["china_mainland"])
        self.assertNotIn("selection_mode", wizard_config)
        self.assertNotIn("source", wizard_config)
        self.assertNotIn("photos_scope", wizard_config)
        self.assertTrue(wizard_config["_from_wizard"])
        rendered = stdout.getvalue()
        self.assertIn("sa***@example.com", rendered)
        self.assertNotIn("Step 3: Choose what to download", rendered)
        self.assertNotIn("Choose an option below:", rendered)

    @patch.dict(
        os.environ,
        {"ICLOUD_APPLE_ID": "user@example.com", "ICLOUD_PASSWORD": "env-secret"},
        clear=False,
    )
    def test_run_setup_wizard_uses_environment_credentials_and_saved_preferences(self):
        input_mock = unittest.mock.Mock(return_value="")
        getpass_mock = unittest.mock.Mock(side_effect=AssertionError("getpass should not be used"))

        wizard_config = run_setup_wizard(
            saved_config={
                "destination": "/tmp/downloads",
                "workers": 4,
                "photos_scope": "by-month",
                "source": "photos-library",
            },
            input_func=input_mock,
            getpass_func=getpass_mock,
        )

        self.assertNotIn("_apple_id", wizard_config)
        self.assertNotIn("_password", wizard_config)
        self.assertEqual(wizard_config["destination"], "/tmp/downloads")
        self.assertEqual(wizard_config["workers"], 4)
        self.assertNotIn("source", wizard_config)
        self.assertNotIn("photos_scope", wizard_config)
        input_mock.assert_not_called()
        getpass_mock.assert_not_called()

    @patch.dict(os.environ, {"ICLOUD_APPLE_ID": "", "ICLOUD_PASSWORD": ""}, clear=False)
    def test_run_setup_wizard_defers_download_mode_choice_until_after_login(self):
        saved = {
            "save_apple_id": True,
            "saved_apple_id": "saved@example.com",
            "select_from_cache": True,
            "selection_mode": "mixed",
        }
        stdout = StringIO()

        with redirect_stdout(stdout):
            wizard_config = run_setup_wizard(
                saved_config=saved,
                input_func=lambda _prompt: "",
                getpass_func=lambda _prompt: "app-secret",
            )

        self.assertNotIn("refresh_inventory_cache", wizard_config)
        self.assertNotIn("select_from_cache", wizard_config)
        self.assertNotIn("selection_mode", wizard_config)
        self.assertNotIn("source", wizard_config)
        self.assertNotIn("photos_scope", wizard_config)
        rendered = stdout.getvalue()
        self.assertNotIn("Choose an option below:", rendered)
        self.assertNotIn("  1. ☁️   Everything", rendered)
        self.assertNotIn("  iCloud Photo Library", rendered)

    @patch.dict(
        os.environ,
        {"ICLOUD_APPLE_ID": "user@example.com", "ICLOUD_PASSWORD": "env-secret"},
        clear=False,
    )
    @patch.dict(os.environ, {"ICLOUD_APPLE_ID": "", "ICLOUD_PASSWORD": ""}, clear=False)
    def test_run_setup_wizard_exits_when_apple_id_is_missing(self):
        with self.assertRaises(SystemExit) as exc_info:
            run_setup_wizard(input_func=lambda _prompt: "", getpass_func=lambda _prompt: "ignored")

        self.assertEqual(exc_info.exception.code, 1)

    @patch.dict(os.environ, {"ICLOUD_APPLE_ID": "user@example.com", "ICLOUD_PASSWORD": ""}, clear=False)
    def test_run_setup_wizard_exits_when_password_is_missing(self):
        with self.assertRaises(SystemExit) as exc_info:
            run_setup_wizard(input_func=lambda _prompt: "", getpass_func=lambda _prompt: "")

        self.assertEqual(exc_info.exception.code, 1)

    def test_run_main_menu_routes_to_start_with_saved_preferences(self):
        inputs = iter(["", "", ""])
        saved = {
            "save_apple_id": True,
            "saved_apple_id": "saved@example.com",
            "destination": "/tmp/downloads",
            "workers": 6,
            "dry_run": True,
        }

        with patch("icloud_downloader_lib.wizard._load_user_config", return_value=saved):
            wizard_config = run_main_menu(
                input_func=lambda _prompt: next(inputs),
                getpass_func=lambda _prompt: "app-secret",
            )

        self.assertEqual(wizard_config["_apple_id"], "saved@example.com")
        self.assertEqual(wizard_config["destination"], "/tmp/downloads")
        self.assertEqual(wizard_config["workers"], 6)
        self.assertTrue(wizard_config["dry_run"])

    def test_run_main_menu_exit(self):
        with patch("icloud_downloader_lib.wizard._load_user_config", return_value={}):
            with self.assertRaises(SystemExit) as exc_info:
                run_main_menu(input_func=lambda _prompt: "3")

        self.assertEqual(exc_info.exception.code, 0)

    def test_run_main_menu_invalid_choice_loops(self):
        stdout = StringIO()
        inputs = iter(["bad", "3"])

        with patch("icloud_downloader_lib.wizard._load_user_config", return_value={}):
            with redirect_stdout(stdout):
                with self.assertRaises(SystemExit):
                    run_main_menu(input_func=lambda _prompt: next(inputs))

        self.assertIn("1, 2, or 3", stdout.getvalue())

    def test_run_configure_menu_saves_download_directory(self):
        inputs = iter(["1", "/tmp/downloads", "11"])

        result = run_configure_menu({}, input_func=lambda _prompt: next(inputs))

        self.assertIsNotNone(result)
        self.assertEqual(result["destination"], "/tmp/downloads")

    def test_run_configure_menu_discards_on_cancel(self):
        result = run_configure_menu({}, input_func=lambda _prompt: "12")

        self.assertIsNone(result)

    def test_run_configure_menu_toggles_save_apple_id(self):
        inputs = iter(["2", "y", "11"])

        result = run_configure_menu({}, input_func=lambda _prompt: next(inputs))

        self.assertIsNotNone(result)
        self.assertTrue(result["save_apple_id"])

    def test_run_configure_menu_turning_off_save_2fa_clears_session_files(self):
        # Arrange: a saved config with save_2fa_session=True and a real session file on disk
        session_dir = tempfile.mkdtemp()
        session_file = os.path.join(session_dir, "session")
        cookies_file = os.path.join(session_dir, "cookies")
        open(session_file, "w").close()
        open(cookies_file, "w").close()

        saved_config = {
            "save_2fa_session": True,
            "saved_apple_id": "test.user@example.com",
            "session_dir": session_dir,
        }
        # Toggle off (choice 4, answer n), then save (choice 11)
        inputs = iter(["4", "n", "11"])

        with patch("icloud_downloader_lib.wizard.cleanup_session_files") as mock_cleanup:
            result = run_configure_menu(saved_config, input_func=lambda _prompt: next(inputs))

        self.assertIsNotNone(result)
        self.assertFalse(result.get("save_2fa_session", False))
        mock_cleanup.assert_called_once_with(result)

    def test_run_configure_menu_discard_does_not_clear_session_files(self):
        # Toggling off save_2fa_session and then discarding (choice 12) must NOT clear session files
        saved_config = {
            "save_2fa_session": True,
            "saved_apple_id": "test.user@example.com",
        }
        inputs = iter(["4", "n", "12"])

        with patch("icloud_downloader_lib.wizard.cleanup_session_files") as mock_cleanup:
            result = run_configure_menu(saved_config, input_func=lambda _prompt: next(inputs))

        self.assertIsNone(result)
        mock_cleanup.assert_not_called()

    def test_run_configure_menu_saves_password_in_keyring(self):
        inputs = iter(["3", "y", "11"])

        result = run_configure_menu({}, input_func=lambda _prompt: next(inputs))

        self.assertIsNotNone(result)
        self.assertTrue(result["save_password"])

    def test_run_configure_menu_sets_and_resets_session_directory(self):
        inputs = iter(["5", "/tmp/icloud-session", "5", "-", "11"])

        result = run_configure_menu({}, input_func=lambda _prompt: next(inputs))

        self.assertIsNotNone(result)
        self.assertNotIn("session_dir", result)

    def test_run_configure_menu_sets_workers_preview_resume_and_log_level(self):
        inputs = iter(["7", "5", "8", "y", "9", "n", "10", "1", "11"])

        result = run_configure_menu({}, input_func=lambda _prompt: next(inputs))

        self.assertIsNotNone(result)
        self.assertEqual(result["workers"], 5)
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["resume"])
        self.assertEqual(result["log_level"], "DEBUG")

    def test_run_configure_menu_invalid_choice_loops(self):
        inputs = iter(["99", "12"])
        stdout = StringIO()

        with redirect_stdout(stdout):
            result = run_configure_menu({}, input_func=lambda _prompt: next(inputs))

        self.assertIsNone(result)
        self.assertIn("1 to 13", stdout.getvalue())

    def test_run_configure_menu_offers_clear_all_user_data_in_red(self):
        stdout = StringIO()

        with redirect_stdout(stdout):
            result = run_configure_menu({}, input_func=lambda _prompt: "12")

        self.assertIsNone(result)
        rendered = stdout.getvalue()
        self.assertIn(f"{Colors.RED}13. CLEAR ALL USER DATA{Colors.RESET}", rendered)

    def test_run_configure_menu_clear_all_user_data_removes_local_state(self):
        saved_config = {
            "saved_apple_id": "test.user@example.com",
            "session_dir": "/tmp/icloud-session",
            "save_password": True,
            "save_2fa_session": True,
        }
        inputs = iter(["13", "y"])

        with patch("icloud_downloader_lib.wizard.USER_CONFIG_FILENAME", "config-private.json"):
            with patch("icloud_downloader_lib.wizard.cleanup_session_files") as mock_cleanup:
                with patch("icloud_downloader_lib.wizard.delete_password_in_keyring") as delete_password_mock:
                    with patch("icloud_downloader_lib.wizard.os.path.exists", side_effect=lambda path: path == "config-private.json"):
                        with patch("icloud_downloader_lib.wizard.os.remove") as remove_mock:
                            with patch("icloud_downloader_lib.wizard._invalidate_remote_session"):
                                result = run_configure_menu(saved_config, input_func=lambda _prompt: next(inputs))

        self.assertEqual(result, {"_clear_all_user_data": True})
        self.assertEqual(mock_cleanup.call_args_list, [unittest.mock.call(saved_config), unittest.mock.call({})])
        delete_password_mock.assert_called_once_with("test.user@example.com")
        remove_mock.assert_called_once_with("config-private.json")

    def test_migrate_saved_config_maps_save_login_info_true_to_new_keys(self):
        config = {"save_login_info": True, "destination": "/tmp/x"}
        _migrate_saved_config(config)
        self.assertNotIn("save_login_info", config)
        self.assertTrue(config["save_apple_id"])
        self.assertTrue(config["save_2fa_session"])
        self.assertEqual(config["destination"], "/tmp/x")

    def test_migrate_saved_config_maps_save_login_info_false_silently(self):
        config = {"save_login_info": False}
        _migrate_saved_config(config)
        self.assertNotIn("save_login_info", config)
        self.assertNotIn("save_apple_id", config)
        self.assertNotIn("save_2fa_session", config)

    def test_migrate_saved_config_does_not_overwrite_explicit_new_keys(self):
        # Explicit values set after a partial migration must be respected
        config = {"save_login_info": True, "save_2fa_session": False}
        _migrate_saved_config(config)
        self.assertTrue(config["save_apple_id"])
        self.assertFalse(config["save_2fa_session"])  # setdefault must not clobber

    def test_run_configure_menu_migrates_old_save_login_info_for_display_and_cleanup(self):
        # Old-format saved config: save_login_info=True implies 2FA session should persist.
        # The menu must show 2FA as Yes and trigger cleanup when the user turns it off and saves.
        saved_config = {"save_login_info": True, "saved_apple_id": "test.user@example.com"}
        inputs = iter(["4", "n", "11"])

        with patch("icloud_downloader_lib.wizard.cleanup_session_files") as mock_cleanup:
            result = run_configure_menu(saved_config, input_func=lambda _prompt: next(inputs))

        self.assertIsNotNone(result)
        self.assertFalse(result.get("save_2fa_session", False))
        mock_cleanup.assert_called_once_with(result)


if __name__ == "__main__":
    unittest.main()