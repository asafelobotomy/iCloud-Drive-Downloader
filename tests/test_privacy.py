"""Tests for privacy helpers used by auth and session flows."""

import os
import shutil
import stat
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader_lib.privacy import (
    harden_session_artifacts,
    redact_apple_id,
    redact_label,
    sanitize_upstream_error_text,
    stable_path_identifier,
    stable_text_identifier,
    summarize_trusted_target,
)


class TestPrivacyHelpers(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_redact_apple_id_masks_local_part(self):
        self.assertEqual(redact_apple_id("test.user@example.com"), "te*******@example.com")
        self.assertEqual(redact_apple_id("ab@example.com"), "a*@example.com")

    def test_summarize_trusted_target_uses_generic_labels(self):
        self.assertEqual(summarize_trusted_target({"phoneNumber": "5551234567"}), "SMS target")
        self.assertEqual(summarize_trusted_target({"deviceName": "Jamie's iPhone"}), "Trusted device")

    def test_sanitize_upstream_error_text_redacts_ids_phones_and_paths(self):
        sanitized = sanitize_upstream_error_text(
            "challenge for test.user@example.com via +1 555 123 4567 at /tmp/pyicloud/testuser/session"
        )

        self.assertEqual(
            sanitized,
            "challenge for te*******@example.com via [redacted phone] at .../session",
        )

    def test_sanitize_upstream_error_text_collapses_html_documents(self):
        sanitized = sanitize_upstream_error_text("<html><body>login error</body></html>")

        self.assertEqual(sanitized, "Apple returned a web authentication error.")

    def test_harden_session_artifacts_sets_owner_only_permissions(self):
        session_dir = os.path.join(self.temp_dir, "session-state")
        os.makedirs(session_dir, mode=0o755, exist_ok=True)
        session_path = os.path.join(session_dir, "session")
        cookiejar_path = os.path.join(session_dir, "cookies")
        for path in (session_path, cookiejar_path):
            with open(path, "w", encoding="utf-8"):
                pass
            os.chmod(path, 0o644)

        harden_session_artifacts(
            SimpleNamespace(
                _cookie_directory=session_dir,
                session_path=session_path,
                cookiejar_path=cookiejar_path,
            )
        )

        self.assertEqual(stat.S_IMODE(os.stat(session_dir).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(session_path).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(cookiejar_path).st_mode), 0o600)


class TestPrivacyEdgePaths(unittest.TestCase):
    """Edge-case coverage for privacy helpers not exercised by the happy path."""

    # --- redact_apple_id ---

    def test_redact_apple_id_returns_none_unchanged(self):
        self.assertIsNone(redact_apple_id(None))

    def test_redact_apple_id_returns_non_email_string_unchanged(self):
        self.assertEqual(redact_apple_id("notanemail"), "notanemail")
        self.assertEqual(redact_apple_id(""), "")

    # --- sanitize_upstream_error_text ---

    def test_sanitize_upstream_error_text_returns_none_for_none_input(self):
        self.assertIsNone(sanitize_upstream_error_text(None))

    def test_sanitize_upstream_error_text_returns_none_for_empty_string(self):
        self.assertIsNone(sanitize_upstream_error_text(""))

    def test_sanitize_upstream_error_text_returns_none_for_whitespace_only(self):
        # Normalizes to empty string after strip → returns None
        self.assertIsNone(sanitize_upstream_error_text("   \t\n  "))

    def test_sanitize_upstream_error_text_strips_inline_html_tags(self):
        # Non-document HTML with inline tags is stripped but not replaced wholesale
        result = sanitize_upstream_error_text("<b>Bad</b> credentials")
        self.assertIsNotNone(result)
        self.assertIn("Bad", result)
        self.assertNotIn("<b>", result)

    def test_sanitize_upstream_error_text_truncates_long_input(self):
        long_text = "x" * 300
        result = sanitize_upstream_error_text(long_text)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertLessEqual(len(result), 240)
        self.assertTrue(result.endswith("..."))

    # --- stable_path_identifier ---

    def test_stable_path_identifier_returns_none_for_empty_path(self):
        self.assertIsNone(stable_path_identifier(None))
        self.assertIsNone(stable_path_identifier(""))

    def test_stable_path_identifier_with_root_returns_relative_digest(self):
        result_with_root = stable_path_identifier("/tmp/dl/sub/file.txt", "/tmp/dl")
        result_without_root = stable_path_identifier("/tmp/dl/sub/file.txt")
        # Hashes should differ because one uses the relative path
        self.assertIsNotNone(result_with_root)
        self.assertIsNotNone(result_without_root)
        self.assertNotEqual(result_with_root, result_without_root)

    # --- stable_text_identifier ---

    def test_stable_text_identifier_returns_none_for_empty_value(self):
        self.assertIsNone(stable_text_identifier(None))
        self.assertIsNone(stable_text_identifier(""))

    def test_stable_text_identifier_returns_sha256_prefix(self):
        result = stable_text_identifier("hello")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.startswith("sha256:"))

    # --- redact_label ---

    def test_redact_label_returns_placeholder_for_empty_name(self):
        self.assertEqual(redact_label(""), "[unnamed]")

    def test_redact_label_handles_name_with_no_extension(self):
        # Short base (≤2 chars)
        self.assertEqual(redact_label("ab"), "a*")
        # Long base
        result = redact_label("hello")
        self.assertTrue(result.startswith("he"))
        self.assertNotIn(".", result)

    def test_redact_label_preserves_file_extension(self):
        result = redact_label("photo.jpg")
        self.assertTrue(result.endswith(".jpg"))
        self.assertFalse(result.startswith("photo"))

    def test_redact_label_handles_short_base_with_extension(self):
        # "a.jpg" — base="a", extension="jpg" (base has 1 char ≤ 2)
        result = redact_label("a.jpg")
        self.assertEqual(result, "a*.jpg")


if __name__ == "__main__":
    unittest.main()