"""Tests for app-level privacy presentation behavior."""

import os
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader_lib.app import main as app_main
from tests.test_app_cli_edges import make_args


class TestAppPrivacy(unittest.TestCase):
    def test_main_auth_status_redacts_apple_id(self):
        args = make_args(auth_status=True)
        stdout = StringIO()

        with redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as exc_info:
                app_main(
                    parse_arguments_func=lambda: args,
                    inspect_auth_status_func=lambda *_args, **_kwargs: {
                        "apple_id": "user.privacy@example.com",
                        "session_dir": "/tmp/pyicloud/testuser",
                        "session_path": "/tmp/pyicloud/testuser/userprivacyexamplecom.session",
                        "cookiejar_path": "/tmp/pyicloud/testuser/userprivacyexamplecom.cookiejar",
                        "has_session_file": True,
                        "has_cookiejar_file": True,
                        "authenticated": True,
                        "trusted_session": True,
                        "requires_2fa": False,
                        "requires_2sa": False,
                        "use_keyring": False,
                        "keyring_password_available": False,
                        "china_mainland": False,
                    },
                )

        self.assertEqual(exc_info.exception.code, 0)
        rendered = stdout.getvalue()
        self.assertIn("us**********@example.com", rendered)
        self.assertNotIn("user.privacy@example.com", rendered)