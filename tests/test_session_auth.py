"""Tests for session authentication helpers and auth diagnostics."""

import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

# Add parent directory to path to import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import icloud_downloader_lib.session as session_module
from icloud_downloader_lib.session import authenticate_session, inspect_auth_status


class TestSessionAuthentication(unittest.TestCase):
    """Test auth/session helpers against fake pyicloud services."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("builtins.input", return_value="user@example.com")
    def test_authenticate_session_passes_session_options_to_pycloud(self, input_mock):
        session_dir = os.path.join(self.temp_dir, "session")
        captured = {}

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                captured["apple_id"] = apple_id
                captured["password"] = password
                captured["kwargs"] = kwargs
                self.requires_2fa = False

        api = authenticate_session(
            {},
            {
                "session_dir": session_dir,
                "china_mainland": True,
            },
            service_class=FakeService,
            getpass_func=lambda _: "app-secret",
        )

        self.assertIsInstance(api, FakeService)
        self.assertEqual(captured["apple_id"], "user@example.com")
        self.assertEqual(captured["password"], "app-secret")
        self.assertEqual(captured["kwargs"]["cookie_directory"], session_dir)
        self.assertTrue(captured["kwargs"]["china_mainland"])
        input_mock.assert_called_once_with("Enter your Apple ID email: ")

    @patch("builtins.input", return_value="user@example.com")
    def test_authenticate_session_can_use_keyring_without_prompting_for_password(self, input_mock):
        getpass_mock = Mock(side_effect=AssertionError("password prompt should not be used"))
        captured = {}

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                captured["apple_id"] = apple_id
                captured["password"] = password
                captured["kwargs"] = kwargs
                self.requires_2fa = False

        authenticate_session(
            {},
            {"use_keyring": True},
            service_class=FakeService,
            getpass_func=getpass_mock,
        )

        self.assertEqual(captured["apple_id"], "user@example.com")
        self.assertIsNone(captured["password"])
        self.assertEqual(captured["kwargs"]["cookie_directory"], None)
        self.assertFalse(captured["kwargs"]["china_mainland"])
        input_mock.assert_called_once_with("Enter your Apple ID email: ")

    @patch("icloud_downloader_lib.session.store_password_in_keyring")
    def test_authenticate_session_stores_password_in_keyring_after_success(self, store_password_mock):
        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                self.requires_2fa = False

        authenticate_session(
            {
                "_apple_id": "user@example.com",
                "_password": "app-secret",
            },
            {"store_password_in_keyring": True},
            service_class=FakeService,
        )

        store_password_mock.assert_called_once_with("user@example.com", "app-secret")

    @patch("icloud_downloader_lib.two_factor.prompt_masked_secret", return_value="123456")
    def test_authenticate_session_requests_2fa_code_when_supported(self, prompt_mock):
        request_code_mock = Mock(return_value=True)
        validate_code_mock = Mock(return_value=True)
        trust_session_mock = Mock(return_value=True)

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                self.requires_2fa = True
                self.request_2fa_code = request_code_mock
                self.validate_2fa_code = validate_code_mock
                self.trust_session = trust_session_mock

        authenticate_session(
            {
                "_apple_id": "user@example.com",
                "_password": "app-secret",
            },
            {},
            service_class=FakeService,
        )

        request_code_mock.assert_called_once_with()
        validate_code_mock.assert_called_once_with("123456")
        trust_session_mock.assert_called_once_with()
        prompt_mock.assert_called_once_with("  Enter the 6-digit code: ")

    def test_authenticate_session_exits_when_keyring_has_no_password(self):
        class MissingPasswordError(Exception):
            pass

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                raise MissingPasswordError()

        with patch.object(session_module, "PyiCloudNoStoredPasswordAvailableException", MissingPasswordError):
            with self.assertRaises(SystemExit) as exc_info:
                authenticate_session(
                    {"_apple_id": "user@example.com"},
                    {"use_keyring": True},
                    service_class=FakeService,
                )

        self.assertEqual(exc_info.exception.code, 1)

    def test_authenticate_session_exits_on_failed_login(self):
        class FailedLoginError(Exception):
            pass

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                raise FailedLoginError()

        with patch.object(session_module, "PyiCloudFailedLoginException", FailedLoginError):
            with self.assertRaises(SystemExit) as exc_info:
                authenticate_session(
                    {
                        "_apple_id": "user@example.com",
                        "_password": "app-secret",
                    },
                    {},
                    service_class=FakeService,
                )

        self.assertEqual(exc_info.exception.code, 1)

    def test_authenticate_session_reports_regular_password_guidance_on_failed_login(self):
        class FailedLoginError(Exception):
            pass

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                raise FailedLoginError("Invalid email/password combination.")

        stdout = StringIO()

        with patch.object(session_module, "PyiCloudFailedLoginException", FailedLoginError):
            with redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as exc_info:
                    authenticate_session(
                        {
                            "_apple_id": "user@example.com",
                            "_password": "secret",
                        },
                        {},
                        service_class=FakeService,
                    )

        self.assertEqual(exc_info.exception.code, 1)
        rendered = stdout.getvalue()
        self.assertIn("regular Apple ID password", rendered)
        self.assertIn("try your normal Apple ID password instead", rendered)
        self.assertNotIn("Double-check your app-specific password", rendered)
        self.assertNotIn("Not an app-specific password", rendered)

    @patch("icloud_downloader_lib.two_factor.prompt_masked_secret", return_value="123456")
    def test_authenticate_session_exits_when_2fa_code_validation_fails(self, prompt_mock):
        request_code_mock = Mock(return_value=True)
        validate_code_mock = Mock(return_value=False)
        trust_session_mock = Mock()

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                self.requires_2fa = True
                self.request_2fa_code = request_code_mock
                self.validate_2fa_code = validate_code_mock
                self.trust_session = trust_session_mock

        with self.assertRaises(SystemExit) as exc_info:
            authenticate_session(
                {
                    "_apple_id": "user@example.com",
                    "_password": "app-secret",
                },
                {},
                service_class=FakeService,
            )

        self.assertEqual(exc_info.exception.code, 1)
        request_code_mock.assert_called_once_with()
        validate_code_mock.assert_called_once_with("123456")
        trust_session_mock.assert_not_called()
        prompt_mock.assert_called_once_with("  Enter the 6-digit code: ")

    @patch("builtins.input", side_effect=[""])
    def test_authenticate_session_confirms_security_key_when_required(self, input_mock):
        confirm_security_key_mock = Mock()
        trust_session_mock = Mock(return_value=True)

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                self.requires_2fa = True
                self.security_key_names = ["Office Key"]
                self._auth_data = {"fsaChallenge": {"challenge": "abc", "keyHandles": ["key-1"], "rpId": "apple.com"}}
                self.confirm_security_key = confirm_security_key_mock
                self.trust_session = trust_session_mock

        authenticate_session(
            {
                "_apple_id": "user@example.com",
                "_password": "app-secret",
            },
            {},
            service_class=FakeService,
        )

        confirm_security_key_mock.assert_called_once_with()
        trust_session_mock.assert_called_once_with()
        self.assertEqual(
            input_mock.call_args_list,
            [unittest.mock.call("Press Enter to continue with security-key verification...")],
        )

    @patch("builtins.input", side_effect=[""])
    def test_authenticate_session_exits_when_security_key_confirmation_fails(self, input_mock):
        trust_session_mock = Mock(return_value=True)

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                self.requires_2fa = True
                self.security_key_names = ["Office Key"]
                self._auth_data = {"fsaChallenge": {"challenge": "abc", "keyHandles": ["key-1"], "rpId": "apple.com"}}
                self.trust_session = trust_session_mock

            def confirm_security_key(self):
                raise RuntimeError("device missing")

        with self.assertRaises(SystemExit) as exc_info:
            authenticate_session(
                {
                    "_apple_id": "user@example.com",
                    "_password": "app-secret",
                },
                {},
                service_class=FakeService,
            )

        self.assertEqual(exc_info.exception.code, 1)
        trust_session_mock.assert_not_called()
        self.assertEqual(
            input_mock.call_args_list,
            [unittest.mock.call("Press Enter to continue with security-key verification...")],
        )

    @patch("builtins.input", side_effect=[""])
    def test_authenticate_session_handles_security_key_when_code_request_returns_false(self, input_mock):
        request_code_mock = Mock(return_value=False)
        confirm_security_key_mock = Mock()
        trust_session_mock = Mock(return_value=True)

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                self.requires_2fa = True
                self.security_key_names = []
                self._auth_data = {"fsaChallenge": {"challenge": "abc", "keyHandles": ["key-1"], "rpId": "apple.com"}}
                self.request_2fa_code = request_code_mock
                self.confirm_security_key = confirm_security_key_mock
                self.trust_session = trust_session_mock

        authenticate_session(
            {
                "_apple_id": "user@example.com",
                "_password": "app-secret",
            },
            {},
            service_class=FakeService,
        )

        request_code_mock.assert_called_once_with()
        confirm_security_key_mock.assert_called_once_with()
        trust_session_mock.assert_called_once_with()
        self.assertEqual(
            input_mock.call_args_list,
            [unittest.mock.call("Press Enter to continue with security-key verification...")],
        )


class TestAuthStatusInspection(unittest.TestCase):
    """Test local auth/session status reporting."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.session_path = os.path.join(self.temp_dir, "session")
        self.cookiejar_path = os.path.join(self.temp_dir, "cookies")
        with open(self.session_path, "w", encoding="utf-8"):
            pass
        with open(self.cookiejar_path, "w", encoding="utf-8"):
            pass

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("icloud_downloader_lib.session.password_exists_in_keyring", return_value=True)
    def test_inspect_auth_status_reports_local_session_and_keyring_state(self, password_exists_mock):
        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                self.apple_id = apple_id
                self.password = password
                self.kwargs = kwargs
                self.session = SimpleNamespace(
                    session_path=self.kwargs["cookie_directory"] + "/session",
                    cookiejar_path=self.kwargs["cookie_directory"] + "/cookies",
                )

            def get_auth_status(self):
                return {
                    "authenticated": True,
                    "trusted_session": True,
                    "requires_2fa": False,
                    "requires_2sa": False,
                }

        status = inspect_auth_status(
            {"_apple_id": "user@example.com"},
            {
                "session_dir": self.temp_dir,
                "china_mainland": True,
                "use_keyring": True,
            },
            service_class=FakeService,
        )

        self.assertEqual(status["apple_id"], "user@example.com")
        self.assertEqual(status["session_dir"], self.temp_dir)
        self.assertEqual(status["session_path"], self.session_path)
        self.assertEqual(status["cookiejar_path"], self.cookiejar_path)
        self.assertTrue(status["has_session_file"])
        self.assertTrue(status["has_cookiejar_file"])
        self.assertTrue(status["authenticated"])
        self.assertTrue(status["trusted_session"])
        self.assertTrue(status["use_keyring"])
        self.assertTrue(status["keyring_password_available"])
        self.assertTrue(status["china_mainland"])
        password_exists_mock.assert_called_once_with("user@example.com")