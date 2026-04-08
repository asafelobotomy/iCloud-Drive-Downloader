"""Tests for additional session helper edge paths and fallback branches."""

import builtins
import importlib
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

import icloud_downloader_lib.session as session_module
from icloud_downloader_lib.session import (
    authenticate_session,
    ensure_pycloud_available,
    inspect_auth_status,
    resolve_credentials,
    resolve_service_options,
)


class TestSessionEdges(unittest.TestCase):
    """Test session helper branches that are not covered by the main auth tests."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ensure_pycloud_available_exits_when_dependency_is_missing(self):
        with patch.object(session_module, "PYICLOUD_AVAILABLE", False):
            with self.assertRaises(SystemExit) as exc_info:
                ensure_pycloud_available()

        self.assertEqual(exc_info.exception.code, 1)

    def test_resolve_credentials_reads_environment_values_and_prints_hints(self):
        stdout = StringIO()

        with patch.dict(os.environ, {"ICLOUD_APPLE_ID": "env@example.com", "ICLOUD_PASSWORD": "dummy-password"}, clear=False):
            with redirect_stdout(stdout):
                apple_id, password = resolve_credentials({}, prompt_for_password=False)

        self.assertEqual(apple_id, "env@example.com")
        self.assertEqual(password, "dummy-password")
        self.assertIn("Using Apple ID from environment", stdout.getvalue())
        self.assertIn("en**@example.com", stdout.getvalue())
        self.assertNotIn("env@example.com", stdout.getvalue())
        self.assertIn("Using password from environment variable", stdout.getvalue())

    def test_resolve_credentials_announces_keyring_lookup_without_prompting(self):
        stdout = StringIO()
        getpass_mock = Mock(side_effect=AssertionError("password prompt should not be used"))

        with patch.dict(os.environ, {"ICLOUD_APPLE_ID": "env@example.com"}, clear=False):
            with redirect_stdout(stdout):
                apple_id, password = resolve_credentials(
                    {},
                    use_keyring=True,
                    getpass_func=getpass_mock,
                )

        self.assertEqual(apple_id, "env@example.com")
        self.assertIsNone(password)
        self.assertIn("Attempting password lookup from the system keyring", stdout.getvalue())

    def test_resolve_service_options_expands_user_paths(self):
        expanded_session_dir = os.path.join(self.temp_dir, "expanded-session")
        with patch("os.path.expanduser", return_value=expanded_session_dir) as expanduser_mock:
            options = resolve_service_options({"session_dir": "~/icloud-session", "china_mainland": True})

        self.assertEqual(options["cookie_directory"], expanded_session_dir)
        self.assertTrue(options["china_mainland"])
        expanduser_mock.assert_called_once_with("~/icloud-session")
        self.assertEqual(oct(os.stat(expanded_session_dir).st_mode & 0o777), "0o700")

    def test_resolve_service_options_exits_for_symlinked_session_directory(self):
        target_dir = os.path.join(self.temp_dir, "real-session")
        os.makedirs(target_dir, exist_ok=True)
        session_link = os.path.join(self.temp_dir, "session-link")
        os.symlink(target_dir, session_link)

        with self.assertRaises(SystemExit) as exc_info:
            resolve_service_options({"session_dir": session_link})

        self.assertEqual(exc_info.exception.code, 1)

    def test_resolve_service_options_exits_for_non_directory_session_path(self):
        session_file = os.path.join(self.temp_dir, "session-file")
        with open(session_file, "w", encoding="utf-8") as handle:
            handle.write("not-a-directory")

        with self.assertRaises(SystemExit) as exc_info:
            resolve_service_options({"session_dir": session_file})

        self.assertEqual(exc_info.exception.code, 1)

    @patch("icloud_downloader_lib.session.password_exists_in_keyring", side_effect=RuntimeError("keyring unavailable"))
    def test_inspect_auth_status_uses_default_status_when_service_has_no_auth_method(self, _password_exists_mock):
        session_dir = os.path.join(self.temp_dir, "session")
        os.makedirs(session_dir, exist_ok=True)
        session_path = os.path.join(session_dir, "session")
        cookiejar_path = os.path.join(session_dir, "cookies")
        with open(session_path, "w", encoding="utf-8"):
            pass
        with open(cookiejar_path, "w", encoding="utf-8"):
            pass

        class FakeService:
            def __init__(self, apple_id, password, authenticate=False, **kwargs):
                self.apple_id = apple_id
                self.password = password
                self.authenticate = authenticate
                self.kwargs = kwargs
                self.session = SimpleNamespace(
                    session_path=session_path,
                    cookiejar_path=cookiejar_path,
                )

        status = inspect_auth_status(
            {"_apple_id": "user@example.com"},
            {"session_dir": session_dir, "use_keyring": True},
            service_class=FakeService,
        )

        self.assertFalse(status["authenticated"])
        self.assertFalse(status["trusted_session"])
        self.assertFalse(status["requires_2fa"])
        self.assertFalse(status["requires_2sa"])
        self.assertFalse(status["keyring_password_available"])

    def test_inspect_auth_status_does_not_prompt_without_apple_id(self):
        service_class = Mock(side_effect=AssertionError("service should not be constructed"))
        getpass_mock = Mock(side_effect=AssertionError("password prompt should not be used"))

        with patch.object(builtins, "input", side_effect=AssertionError("apple id prompt should not be used")):
            status = inspect_auth_status({}, {}, service_class=service_class, getpass_func=getpass_mock)

        self.assertIsNone(status["apple_id"])
        expected_default_dir = os.path.join(os.path.expanduser("~"), ".pyicloud")
        self.assertEqual(status["session_dir"], expected_default_dir)
        self.assertIsNone(status["session_path"])
        self.assertIsNone(status["cookiejar_path"])
        self.assertFalse(status["has_session_file"])
        self.assertFalse(status["has_cookiejar_file"])
        self.assertFalse(status["authenticated"])
        self.assertFalse(status["trusted_session"])
        self.assertFalse(status["requires_2fa"])
        self.assertFalse(status["requires_2sa"])
        self.assertFalse(status["keyring_password_available"])
        self.assertFalse(status["use_keyring"])
        self.assertFalse(status["china_mainland"])
        service_class.assert_not_called()
        getpass_mock.assert_not_called()

    def test_inspect_auth_status_detects_session_files_in_default_pyicloud_dir(self):
        fake_home = os.path.join(self.temp_dir, "home")
        default_pyicloud = os.path.join(fake_home, ".pyicloud")
        os.makedirs(default_pyicloud, exist_ok=True)
        with open(os.path.join(default_pyicloud, "user@example.com.session"), "w") as f:
            f.write("{}")

        service_class = Mock(side_effect=AssertionError("service should not be constructed"))

        with patch("os.path.expanduser", return_value=fake_home):
            status = inspect_auth_status({}, {}, service_class=service_class)

        self.assertIsNone(status["apple_id"])
        self.assertEqual(status["session_dir"], default_pyicloud)
        self.assertTrue(status["has_session_file"])

    @patch("icloud_downloader_lib.session.store_password_in_keyring", side_effect=RuntimeError("locked"))
    def test_authenticate_session_warns_when_keyring_storage_fails(self, _store_password_mock):
        stdout = StringIO()

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                self.requires_2fa = False

        with redirect_stdout(stdout):
            authenticate_session(
                {"_apple_id": "user@example.com", "_password": "dummy-password"},
                {"store_in_keyring": True},
                service_class=FakeService,
            )

        self.assertIn("Warning: Could not store password in the system keyring", stdout.getvalue())

    def test_authenticate_session_redacts_upstream_login_detail(self):
        class FailedLoginError(Exception):
            pass

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                raise FailedLoginError(
                    "Login failed for test.user@example.com via +1 555 123 4567 at /tmp/pyicloud/testuser/session"
                )

        stdout = StringIO()

        with patch.object(session_module, "PyiCloudFailedLoginException", FailedLoginError):
            with redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as exc_info:
                    authenticate_session(
                        {"_apple_id": "user@example.com", "_password": "dummy-password"},
                        {},
                        service_class=FakeService,
                    )

        self.assertEqual(exc_info.exception.code, 1)
        rendered = stdout.getvalue()
        self.assertIn("te*******@example.com", rendered)
        self.assertIn("[redacted phone]", rendered)
        self.assertIn(".../session", rendered)
        self.assertNotIn("test.user@example.com", rendered)
        self.assertNotIn("+1 555 123 4567", rendered)
        self.assertNotIn("/tmp/pyicloud/testuser/session", rendered)

    @patch("icloud_downloader_lib.two_factor.prompt_masked_secret", return_value="111111")
    def test_authenticate_session_redacts_upstream_2fa_warning_text(self, prompt_mock):
        validate_code_mock = Mock(return_value=True)

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                self.requires_2fa = True
                self.security_key_names = []
                self.validate_2fa_code = validate_code_mock

            def request_2fa_code(self):
                raise RuntimeError(
                    "send code to test.user@example.com via +1 555 123 4567 using /tmp/pyicloud/testuser/session"
                )

            def trust_session(self):
                raise RuntimeError(
                    "trust failed for test.user@example.com via /tmp/pyicloud/testuser/session"
                )

        stdout = StringIO()

        with redirect_stdout(stdout):
            authenticate_session(
                {"_apple_id": "user@example.com", "_password": "dummy-password"},
                {},
                service_class=FakeService,
            )

        rendered = stdout.getvalue()
        self.assertIn("te*******@example.com", rendered)
        self.assertIn("[redacted phone]", rendered)
        self.assertIn(".../session", rendered)
        self.assertNotIn("test.user@example.com", rendered)
        self.assertNotIn("+1 555 123 4567", rendered)
        self.assertNotIn("/tmp/pyicloud/testuser/session", rendered)
        prompt_mock.assert_called_once_with("  Enter the 6-digit code: ")

    @patch("icloud_downloader_lib.two_factor.prompt_masked_secret", return_value="111111")
    def test_authenticate_session_exits_when_manual_2fa_fallback_code_is_invalid(self, prompt_mock):
        validate_code_mock = Mock(return_value=False)

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                self.requires_2fa = True
                self.security_key_names = []
                self.validate_2fa_code = validate_code_mock

            def request_2fa_code(self):
                raise RuntimeError("request unavailable")

        with self.assertRaises(SystemExit) as exc_info:
            authenticate_session(
                {"_apple_id": "user@example.com", "_password": "dummy-password"},
                {},
                service_class=FakeService,
            )

        self.assertEqual(exc_info.exception.code, 1)
        validate_code_mock.assert_called_once_with("111111")
        prompt_mock.assert_called_once_with("  Enter the 6-digit code: ")

    @patch("icloud_downloader_lib.two_factor.prompt_masked_secret", return_value="222222")
    def test_authenticate_session_exits_when_direct_2fa_fallback_code_is_invalid(self, prompt_mock):
        validate_code_mock = Mock(return_value=False)

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                self.requires_2fa = True
                self.validate_2fa_code = validate_code_mock

        with self.assertRaises(SystemExit) as exc_info:
            authenticate_session(
                {"_apple_id": "user@example.com", "_password": "dummy-password"},
                {},
                service_class=FakeService,
            )

        self.assertEqual(exc_info.exception.code, 1)
        validate_code_mock.assert_called_once_with("222222")
        prompt_mock.assert_called_once_with("  Enter the 6-digit code: ")

    @patch("icloud_downloader_lib.two_factor.prompt_masked_secret", return_value="333333")
    def test_authenticate_session_last_resort_prompt_tries_sms_fallback_on_validate_failure(self, prompt_mock):
        """When validate_2fa_code fails (wrong endpoint), try SMS validation."""
        validate_code_mock = Mock(return_value=False)
        validate_sms_mock = Mock()
        trust_session_mock = Mock(return_value=True)

        class TrustedPhone:
            @staticmethod
            def as_phone_number_payload():
                return {"id": 123456789}

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                self.requires_2fa = True
                self.validate_2fa_code = validate_code_mock
                self._validate_sms_code = validate_sms_mock
                self.two_factor_delivery_method = "unknown"
                self.two_factor_delivery_notice = None
                self.request_2fa_code = Mock(return_value=False)
                self._trusted_phone_number = Mock(return_value=TrustedPhone())
                self.trust_session = trust_session_mock

        authenticate_session(
            {"_apple_id": "user@example.com", "_password": "dummy-password"},
            {},
            service_class=FakeService,
        )

        validate_code_mock.assert_called_once_with("333333")
        validate_sms_mock.assert_called_once_with("333333")
        trust_session_mock.assert_called_once_with()
        prompt_mock.assert_called_once_with("  Enter the 6-digit code: ")

    @patch("icloud_downloader_lib.two_factor.prompt_masked_secret", return_value="")
    def test_authenticate_session_manual_2fa_blank_entry_exits_cleanly_when_no_fallback_exists(self, prompt_mock):
        validate_code_mock = Mock(return_value=True)

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                self.requires_2fa = True
                self.validate_2fa_code = validate_code_mock
                self.request_2fa_code = Mock(return_value=False)
                self._trusted_phone_number = Mock(return_value=None)

        with self.assertRaises(SystemExit) as exc_info:
            authenticate_session(
                {"_apple_id": "user@example.com", "_password": "dummy-password"},
                {},
                service_class=FakeService,
            )

        self.assertEqual(exc_info.exception.code, 1)
        validate_code_mock.assert_not_called()
        prompt_mock.assert_called_once_with("  Enter the 6-digit code: ")

    def test_session_module_handles_missing_pycloud_dependency_on_reload(self):
        original_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "pyicloud" or name.startswith("pyicloud."):
                raise ImportError("pyicloud missing")
            return original_import(name, globals, locals, fromlist, level)

        try:
            with patch("builtins.__import__", side_effect=fake_import):
                importlib.reload(session_module)

            self.assertFalse(session_module.PYICLOUD_AVAILABLE)
            self.assertIsNone(session_module.PyiCloudService)
            self.assertIsNone(session_module.password_exists_in_keyring)
            self.assertIsNone(session_module.store_password_in_keyring)
        finally:
            importlib.reload(session_module)


if __name__ == "__main__":
    unittest.main()