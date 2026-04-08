"""Tests for session cleanup, dry-run prompt, and apple_id persistence."""

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
from icloud_downloader_lib.definitions import DEFAULT_DOWNLOAD_PATH
from icloud_downloader_lib.session import cleanup_session_files


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


class TestCleanupSessionFiles(unittest.TestCase):
    """Test session file cleanup behavior."""

    def test_cleanup_session_files_removes_matching_files(self):
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))

        for filename in ("session", "cookies"):
            with open(os.path.join(temp_dir, filename), "w") as f:
                f.write("test")

        cleanup_session_files({"session_dir": temp_dir})

        self.assertFalse(os.path.exists(os.path.join(temp_dir, "session")))
        self.assertFalse(os.path.exists(os.path.join(temp_dir, "cookies")))

    def test_cleanup_session_files_removes_v2_named_files(self):
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))

        for filename in ("userexamplecom.session", "userexamplecom.cookiejar"):
            with open(os.path.join(temp_dir, filename), "w") as f:
                f.write("test")

        cleanup_session_files({"session_dir": temp_dir})

        self.assertFalse(os.path.exists(os.path.join(temp_dir, "userexamplecom.session")))
        self.assertFalse(os.path.exists(os.path.join(temp_dir, "userexamplecom.cookiejar")))

    def test_cleanup_session_files_tolerates_missing_files(self):
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))

        cleanup_session_files({"session_dir": temp_dir})

    def test_cleanup_session_files_uses_default_pyicloud_dir(self):
        with patch("icloud_downloader_lib.session.os.path.exists", return_value=False):
            with patch("icloud_downloader_lib.session.os.remove") as remove_mock:
                cleanup_session_files({})

        remove_mock.assert_not_called()


class TestWizardRuntimePreferences(unittest.TestCase):
    """Test runtime behavior for saved wizard preferences in main()."""

    def test_main_does_not_prompt_for_preview_after_wizard(self):
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))

        args = make_args(wizard=True, destination=temp_dir)
        wizard_config = {
            "_apple_id": "user@example.com",
            "_password": "app-secret",
            "_from_wizard": True,
            "destination": temp_dir,
        }
        api = Mock()
        api.requires_2fa = False
        api.drive.dir.return_value = []
        input_mock = Mock(return_value="1")

        with patch("icloud_downloader_lib.app.authenticate_session", return_value=api):
            with self.assertRaises(SystemExit):
                app_main(
                    parse_arguments_func=lambda: args,
                    run_setup_wizard_func=lambda: wizard_config,
                    check_free_space_func=Mock(),
                    input_func=input_mock,
                )

                input_mock.assert_called_once_with("\nEnter choice [1]: ")

    def test_main_announces_saved_preview_mode_without_prompting(self):
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))

        args = make_args(wizard=True, dry_run=True)
        wizard_config = {
            "_apple_id": "user@example.com",
            "_password": "app-secret",
            "_from_wizard": True,
            "destination": temp_dir,
            "dry_run": True,
        }
        api = Mock()
        api.requires_2fa = False
        api.drive.dir.return_value = []
        input_mock = Mock(return_value="1")
        stdout = StringIO()

        with patch("icloud_downloader_lib.app.authenticate_session", return_value=api):
            with redirect_stdout(stdout):
                with self.assertRaises(SystemExit):
                    app_main(
                        parse_arguments_func=lambda: args,
                        run_setup_wizard_func=lambda: wizard_config,
                        check_free_space_func=Mock(),
                        input_func=input_mock,
                    )

        input_mock.assert_called_once_with("\nEnter choice [1]: ")
        self.assertIn("Preview mode enabled from saved preferences", stdout.getvalue())

    def test_main_prompts_for_download_mode_after_authentication_in_wizard_flow(self):
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))

        args = make_args(wizard=True, destination=temp_dir)
        wizard_config = {
            "_apple_id": "user@example.com",
            "_password": "app-secret",
            "_from_wizard": True,
            "destination": temp_dir,
            "dry_run": True,
        }
        api = Mock()
        api.requires_2fa = False
        order: list[str] = []

        def authenticate_then_return(*_args, **_kwargs):
            order.append("authenticate")
            return api

        def record_download_prompt(*_args, **_kwargs):
            order.append("choose-download-mode")

        with patch("icloud_downloader_lib.app.authenticate_session", side_effect=authenticate_then_return):
            with patch("icloud_downloader_lib.app.prompt_download_mode_after_auth", side_effect=record_download_prompt):
                with patch("icloud_downloader_lib.app.execute_download_session"):
                    app_main(
                        parse_arguments_func=lambda: args,
                        run_setup_wizard_func=lambda: wizard_config,
                        check_free_space_func=Mock(),
                    )

        self.assertEqual(order[:2], ["authenticate", "choose-download-mode"])

    def test_main_saves_apple_id_when_save_apple_id_enabled(self):
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))

        args = make_args(wizard=True, dry_run=True)
        wizard_config = {
            "_apple_id": "user@example.com",
            "_password": "app-secret",
            "save_apple_id": True,
            "destination": temp_dir,
            "dry_run": True,
        }
        api = Mock()
        api.requires_2fa = False
        api.drive.dir.return_value = []
        save_mock = Mock()

        with patch("icloud_downloader_lib.app.authenticate_session", return_value=api):
            with patch("icloud_downloader_lib.app.load_config_file", return_value={}):
                with self.assertRaises(SystemExit):
                    app_main(
                        parse_arguments_func=lambda: args,
                        run_setup_wizard_func=lambda: wizard_config,
                        save_config_file_func=save_mock,
                        check_free_space_func=Mock(),
                    )

        save_calls = [c for c in save_mock.call_args_list if "saved_apple_id" in str(c)]
        self.assertTrue(len(save_calls) > 0, "save_config_file should be called with saved_apple_id")


class TestInvalidateRemoteSession(unittest.TestCase):
    """Tests for server-side session invalidation during clear-all."""

    def setUp(self):
        from icloud_downloader_lib.wizard import _invalidate_remote_session
        self._invalidate = _invalidate_remote_session

    @patch("icloud_downloader_lib.wizard.PYICLOUD_AVAILABLE", False, create=True)
    def test_skips_when_pyicloud_unavailable(self):
        self._invalidate({"saved_apple_id": "user@example.com"})

    def test_skips_when_no_saved_apple_id(self):
        self._invalidate({})

    @patch("icloud_downloader_lib.session.resolve_service_options", return_value={"cookie_directory": None, "china_mainland": False})
    def test_calls_logout_when_session_exists(self, _mock_svc_opts):
        mock_api = Mock()
        mock_api.logout.return_value = {"remote_logout_confirmed": True, "local_session_cleared": True}

        with patch("pyicloud.PyiCloudService", return_value=mock_api) as mock_cls:
            with redirect_stdout(StringIO()) as stdout:
                self._invalidate({"saved_apple_id": "user@example.com"})

        mock_cls.assert_called_once_with("user@example.com", None, authenticate=False, cookie_directory=None, china_mainland=False)
        mock_api.logout.assert_called_once_with(keep_trusted=False, clear_local_session=True)
        self.assertIn("Remote session invalidated", stdout.getvalue())

    @patch("icloud_downloader_lib.session.resolve_service_options", return_value={"cookie_directory": None, "china_mainland": False})
    def test_reports_unconfirmed_logout(self, _mock_svc_opts):
        mock_api = Mock()
        mock_api.logout.return_value = {"remote_logout_confirmed": False, "local_session_cleared": True}

        with patch("pyicloud.PyiCloudService", return_value=mock_api):
            with redirect_stdout(StringIO()) as stdout:
                self._invalidate({"saved_apple_id": "user@example.com"})

        self.assertIn("not confirmed", stdout.getvalue())

    @patch("icloud_downloader_lib.session.resolve_service_options", return_value={"cookie_directory": None, "china_mainland": False})
    def test_exception_is_swallowed(self, _mock_svc_opts):
        with patch("pyicloud.PyiCloudService", side_effect=Exception("network error")):
            self._invalidate({"saved_apple_id": "user@example.com"})

    def test_clear_all_invokes_invalidate_then_local_cleanup(self):
        from icloud_downloader_lib.wizard import run_configure_menu
        saved_config = {"saved_apple_id": "test@example.com", "session_dir": "/tmp/s"}
        inputs = iter(["13", "y"])
        call_order: list[str] = []

        with patch("icloud_downloader_lib.wizard._invalidate_remote_session", side_effect=lambda _: call_order.append("remote")) as mock_remote:
            with patch("icloud_downloader_lib.wizard.USER_CONFIG_FILENAME", "config-private.json"):
                with patch("icloud_downloader_lib.wizard.cleanup_session_files", side_effect=lambda _: call_order.append("local")):
                    with patch("icloud_downloader_lib.wizard.delete_password_in_keyring"):
                        with patch("icloud_downloader_lib.wizard.os.path.exists", side_effect=lambda p: p == "config-private.json"):
                            with patch("icloud_downloader_lib.wizard.os.remove"):
                                run_configure_menu(saved_config, input_func=lambda _: next(inputs))

        mock_remote.assert_called_once_with(saved_config)
        self.assertEqual(call_order, ["remote", "local", "local"])


if __name__ == "__main__":
    unittest.main()
