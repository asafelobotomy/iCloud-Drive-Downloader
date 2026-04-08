"""Targeted regressions for refreshed MFA boot-data fallback behavior."""

import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader_lib.session import authenticate_session


class TestTwoFactorRefresh(unittest.TestCase):
    """Cover SMS becoming available only after Apple refreshes MFA boot data."""

    @patch("icloud_downloader_lib.two_factor.prompt_masked_secret", return_value="444444")
    def test_authenticate_session_refreshes_auth_options_before_sms(self, prompt_mock):
        validate_code_mock = Mock(return_value=True)
        request_sms_mock = Mock()
        trust_session_mock = Mock(return_value=True)
        refresh_auth_options_mock = Mock(
            return_value={"trustedPhoneNumber": {"id": 123456789, "pushMode": "sms"}}
        )

        class FakeService:
            def __init__(self, apple_id, password, **kwargs):
                del apple_id, password, kwargs
                self.requires_2fa = True
                self.validate_2fa_code = validate_code_mock
                self.two_factor_delivery_method = "unknown"
                self.two_factor_delivery_notice = None
                self.request_2fa_code = Mock(return_value=False)
                self._auth_data = {}
                self._get_mfa_auth_options = refresh_auth_options_mock
                self._request_sms_2fa_code = self.request_sms
                self.trust_session = trust_session_mock

            def _trusted_phone_number(self):
                payload = self._auth_data.get("trustedPhoneNumber")
                if not isinstance(payload, dict):
                    return None

                class TrustedPhone:
                    def __init__(self, phone_payload):
                        self.phone_payload = phone_payload

                    def as_phone_number_payload(self):
                        return {"id": self.phone_payload["id"]}

                return TrustedPhone(payload)

            def request_sms(self, notice=None):
                request_sms_mock(notice=notice)
                self.two_factor_delivery_method = "sms"
                self.two_factor_delivery_notice = notice
                return True

        authenticate_session(
            {"_apple_id": "user@example.com", "_password": "dummy-password"},
            {},
            service_class=FakeService,
        )

        refresh_auth_options_mock.assert_called_once_with()
        request_sms_mock.assert_called_once_with(notice=None)
        validate_code_mock.assert_called_once_with("444444")
        trust_session_mock.assert_called_once_with()
        prompt_mock.assert_called_once_with("  Enter the 6-digit code: ")


if __name__ == "__main__":
    unittest.main()