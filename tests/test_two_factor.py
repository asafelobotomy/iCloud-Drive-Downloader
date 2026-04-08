"""Tests for two-factor delivery routing helpers exposed through session auth."""

import os
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader_lib.session import authenticate_session


class TestTwoFactorDeliverySelection(unittest.TestCase):
    """Test staged device, SMS, and security-key delivery flows."""

    @patch("icloud_downloader_lib.two_factor.prompt_masked_secret", side_effect=["", "123456"])
    def test_authenticate_session_can_fall_back_to_sms_after_blank_trusted_device_code(self, prompt_mock):
        request_sms_mock = Mock()
        validate_code_mock = Mock(return_value=True)
        trust_session_mock = Mock(return_value=True)

        class TrustedPhone:
            @staticmethod
            def as_phone_number_payload():
                return {"id": 123456789}

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                self.requires_2fa = True
                self.security_key_names = ["Office Key"]
                self.two_factor_delivery_method = "unknown"
                self.two_factor_delivery_notice = None
                self.validate_2fa_code = validate_code_mock
                self.trust_session = trust_session_mock
                self._trusted_phone_number = Mock(return_value=TrustedPhone())
                self._request_sms_2fa_code = self.request_sms

            def request_2fa_code(self):
                self.two_factor_delivery_method = "trusted_device"
                return True

            def request_sms(self, notice=None):
                request_sms_mock(notice=notice)
                self.two_factor_delivery_method = "sms"
                self.two_factor_delivery_notice = notice
                return True

            def confirm_security_key(self):
                raise AssertionError("security key flow should not run when SMS is selected")

        authenticate_session(
            {"_apple_id": "user@example.com", "_password": "app-secret"},
            {},
            service_class=FakeService,
        )

        request_sms_mock.assert_called_once_with(notice=None)
        validate_code_mock.assert_called_once_with("123456")
        trust_session_mock.assert_called_once_with()
        self.assertEqual(
            prompt_mock.call_args_list,
            [
                unittest.mock.call("  Enter the 6-digit code: "),
                unittest.mock.call("  Enter the 6-digit code: "),
            ],
        )

    @patch("icloud_downloader_lib.two_factor.prompt_masked_secret", side_effect=["", ""])
    @patch("builtins.input", side_effect=[""])
    def test_authenticate_session_can_fall_back_to_security_key_after_blank_sms_code(self, input_mock, prompt_mock):
        confirm_security_key_mock = Mock()
        trust_session_mock = Mock(return_value=True)

        class TrustedPhone:
            @staticmethod
            def as_phone_number_payload():
                return {"id": 123456789}

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                self.requires_2fa = True
                self.security_key_names = ["Office Key"]
                self._auth_data = {"fsaChallenge": {"challenge": "abc", "keyHandles": ["key-1"], "rpId": "apple.com"}}
                self.two_factor_delivery_method = "unknown"
                self.two_factor_delivery_notice = None
                self._trusted_phone_number = Mock(return_value=TrustedPhone())
                self._request_sms_2fa_code = Mock(side_effect=self.request_sms)
                self.trust_session = trust_session_mock

            def request_2fa_code(self):
                self.two_factor_delivery_method = "trusted_device"
                return True

            def request_sms(self, notice=None):
                del notice
                self.two_factor_delivery_method = "sms"
                return True

            def confirm_security_key(self):
                confirm_security_key_mock()

        stdout = StringIO()
        with redirect_stdout(stdout):
            authenticate_session(
                {"_apple_id": "user@example.com", "_password": "app-secret"},
                {},
                service_class=FakeService,
            )

        confirm_security_key_mock.assert_called_once_with()
        trust_session_mock.assert_called_once_with()
        self.assertEqual(
            input_mock.call_args_list,
            [unittest.mock.call("Press Enter to continue with security-key verification...")],
        )
        self.assertEqual(prompt_mock.call_count, 2)
        rendered = stdout.getvalue()
        self.assertIn("If you do not have access to a trusted phone number, press Enter to use a security-key-only account!", rendered)

    @patch("builtins.input", side_effect=[""])
    def test_authenticate_session_shows_security_key_stage_when_webauthn_is_available_without_named_keys(self, input_mock):
        confirm_security_key_mock = Mock()
        trust_session_mock = Mock(return_value=True)

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                self.requires_2fa = True
                self.security_key_names = []
                self._auth_data = {"fsaChallenge": {"challenge": "abc", "keyHandles": ["key-1"], "rpId": "apple.com"}}
                self.trust_session = trust_session_mock

            def confirm_security_key(self):
                confirm_security_key_mock()

        stdout = StringIO()
        with redirect_stdout(stdout):
            authenticate_session(
                {"_apple_id": "user@example.com", "_password": "app-secret"},
                {},
                service_class=FakeService,
            )

        confirm_security_key_mock.assert_called_once_with()
        trust_session_mock.assert_called_once_with()
        self.assertEqual(
            input_mock.call_args_list,
            [unittest.mock.call("Press Enter to continue with security-key verification...")],
        )
        self.assertIn("If you do not have access to any verification method, you will not be able to complete login authentication!", stdout.getvalue())

    @patch("icloud_downloader_lib.two_factor.prompt_masked_secret", return_value="123456")
    def test_authenticate_session_automatically_requests_trusted_device_code_first(self, prompt_mock):
        validate_code_mock = Mock(return_value=True)
        confirm_security_key_mock = Mock()
        trust_session_mock = Mock(return_value=True)

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                self.requires_2fa = True
                self.security_key_names = ["Office Key"]
                self.two_factor_delivery_method = "unknown"
                self.two_factor_delivery_notice = None
                self.validate_2fa_code = validate_code_mock
                self.confirm_security_key = confirm_security_key_mock
                self.trust_session = trust_session_mock

            def request_2fa_code(self):
                self.two_factor_delivery_method = "trusted_device"
                return True

        stdout = StringIO()
        with redirect_stdout(stdout):
            authenticate_session(
                {"_apple_id": "user@example.com", "_password": "app-secret"},
                {},
                service_class=FakeService,
            )

        validate_code_mock.assert_called_once_with("123456")
        confirm_security_key_mock.assert_not_called()
        trust_session_mock.assert_called_once_with()
        prompt_mock.assert_called_once_with("  Enter the 6-digit code: ")
        rendered = stdout.getvalue()
        self.assertIn("Requested a fresh 2FA prompt from Apple.", rendered)
        self.assertIn("If you do not have access to a trusted device, press Enter to receive an SMS to your trusted phone number!", rendered)
        self.assertNotIn("Apple requires a security key to finish this sign-in.", rendered)

    @patch("icloud_downloader_lib.two_factor.prompt_masked_secret", return_value="123456")
    def test_authenticate_session_sends_sms_when_thats_the_only_code_delivery_available(self, prompt_mock):
        request_sms_mock = Mock()
        validate_code_mock = Mock(return_value=True)
        trust_session_mock = Mock(return_value=True)

        class TrustedPhone:
            @staticmethod
            def as_phone_number_payload():
                return {"id": 123456789}

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                self.requires_2fa = True
                self.security_key_names = ["Office Key"]
                self.two_factor_delivery_method = "unknown"
                self.two_factor_delivery_notice = None
                self.request_2fa_code = Mock(return_value=False)
                self._trusted_phone_number = Mock(return_value=TrustedPhone())
                self._request_sms_2fa_code = self.request_sms
                self.validate_2fa_code = validate_code_mock
                self.trust_session = trust_session_mock

            def request_sms(self, notice=None):
                request_sms_mock(notice=notice)
                self.two_factor_delivery_method = "sms"
                self.two_factor_delivery_notice = notice
                return True

            def confirm_security_key(self):
                raise AssertionError("security key flow should not run when SMS is the only available delivery method")

        authenticate_session(
            {"_apple_id": "user@example.com", "_password": "app-secret"},
            {},
            service_class=FakeService,
        )

        request_sms_mock.assert_called_once_with(notice=None)
        validate_code_mock.assert_called_once_with("123456")
        trust_session_mock.assert_called_once_with()
        prompt_mock.assert_called_once_with("  Enter the 6-digit code: ")

    @patch("icloud_downloader_lib.two_factor.prompt_masked_secret", return_value="123456")
    @patch("builtins.input", side_effect=["", ""])
    def test_authenticate_session_falls_back_to_legacy_trusted_devices_when_security_key_payload_is_missing(
        self, input_mock, prompt_mock
    ):
        send_code_mock = Mock(return_value=True)
        validate_post_mock = Mock()
        trust_session_mock = Mock(return_value=True)
        trusted_device = {"deviceName": "Example Device 1"}

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                self.requires_2fa = True
                self.security_key_names = ["Office Key"]
                self.two_factor_delivery_method = "unknown"
                self.two_factor_delivery_notice = None
                self.request_2fa_code = Mock(return_value=False)
                self._trusted_phone_number = Mock(return_value=None)
                self.trusted_devices = [trusted_device]
                self.send_verification_code = send_code_mock
                self._setup_endpoint = "https://setup.example.test"
                self.params = {"clientBuildNumber": "pytest"}
                self.session = SimpleNamespace(post=validate_post_mock)
                self.trust_session = trust_session_mock

            def confirm_security_key(self):
                raise RuntimeError("Missing WebAuthn challenge data")

        stdout = StringIO()
        with redirect_stdout(stdout):
            authenticate_session(
                {"_apple_id": "user@example.com", "_password": "app-secret"},
                {},
                service_class=FakeService,
            )

        send_code_mock.assert_called_once_with(trusted_device)
        validate_post_mock.assert_called_once_with(
            "https://setup.example.test/validateVerificationCode",
            params={"clientBuildNumber": "pytest"},
            json={
                "deviceName": "Example Device 1",
                "verificationCode": "123456",
                "trustBrowser": True,
            },
        )
        trust_session_mock.assert_called_once_with()
        self.assertEqual(
            input_mock.call_args_list,
            [unittest.mock.call("Select target [1]: ")],
        )
        prompt_mock.assert_called_once_with("  Enter the 6-digit code: ")
        self.assertIn("1. Trusted device", stdout.getvalue())
        self.assertNotIn("Example Device 1", stdout.getvalue())

    @patch("icloud_downloader_lib.two_factor.prompt_masked_secret", return_value="123456")
    @patch("builtins.input", side_effect=["", ""])
    def test_authenticate_session_legacy_trusted_device_flow_ignores_inner_trust_failure(self, input_mock, prompt_mock):
        send_code_mock = Mock(return_value=True)
        validate_post_mock = Mock()
        trust_session_mock = Mock(side_effect=RuntimeError("trust failed"))
        trusted_device = {"deviceName": "Example Device 1"}

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                self.requires_2fa = True
                self.security_key_names = ["Office Key"]
                self.two_factor_delivery_method = "unknown"
                self.two_factor_delivery_notice = None
                self.request_2fa_code = Mock(return_value=False)
                self._trusted_phone_number = Mock(return_value=None)
                self.trusted_devices = [trusted_device]
                self.send_verification_code = send_code_mock
                self._setup_endpoint = "https://setup.example.test"
                self.params = {"clientBuildNumber": "pytest"}
                self.session = SimpleNamespace(post=validate_post_mock)
                self.trust_session = trust_session_mock

            def confirm_security_key(self):
                raise RuntimeError("Missing WebAuthn challenge data")

        authenticate_session(
            {"_apple_id": "user@example.com", "_password": "app-secret"},
            {},
            service_class=FakeService,
        )

        send_code_mock.assert_called_once_with(trusted_device)
        validate_post_mock.assert_called_once()
        trust_session_mock.assert_called_once_with()
        self.assertEqual(input_mock.call_args_list, [unittest.mock.call("Select target [1]: ")])
        prompt_mock.assert_called_once_with("  Enter the 6-digit code: ")

    @patch("builtins.input", return_value="")
    def test_authenticate_session_exits_with_account_recovery_guidance_when_no_verification_method_is_available(self, input_mock):
        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                self.requires_2fa = True
                self.security_key_names = []

            def confirm_security_key(self):
                raise AssertionError("security key flow should not run without a WebAuthn challenge")

        stdout = StringIO()
        with redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as exc_info:
                authenticate_session(
                    {"_apple_id": "user@example.com", "_password": "app-secret"},
                    {},
                    service_class=FakeService,
                )

        self.assertEqual(exc_info.exception.code, 1)
        input_mock.assert_not_called()
        rendered = stdout.getvalue()
        self.assertIn("If you do not have access to any verification method, you will not be able to complete login authentication!", rendered)
        self.assertIn("https://iforgot.apple.com/", rendered)