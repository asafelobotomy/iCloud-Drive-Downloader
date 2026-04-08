"""Tests for icloud_downloader_lib.crypto."""

import base64
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from icloud_downloader_lib.crypto import (
    bootstrap_data_key,
    decrypt_bytes,
    decrypt_log_line,
    decrypt_session_files,
    encrypt_bytes,
    encrypt_log_line,
    encrypt_session_files,
    derive_subkey,
    init_session_keys,
    is_crypto_available,
    is_encrypted,
    warn_plaintext_keyring,
)


class TestIsCryptoAvailable(unittest.TestCase):
    def test_returns_true_when_cryptography_installed(self) -> None:
        self.assertTrue(is_crypto_available())


class TestEncryptDecryptRoundtrip(unittest.TestCase):
    def setUp(self) -> None:
        self.key = os.urandom(32)

    def test_roundtrip_empty_plaintext(self) -> None:
        ct = encrypt_bytes(self.key, b"")
        self.assertEqual(decrypt_bytes(self.key, ct), b"")

    def test_roundtrip_non_empty_plaintext(self) -> None:
        pt = b"hello icloud"
        ct = encrypt_bytes(self.key, pt)
        self.assertEqual(decrypt_bytes(self.key, ct), pt)

    def test_roundtrip_with_aad(self) -> None:
        pt = b"secret data"
        aad = b"context-tag"
        ct = encrypt_bytes(self.key, pt, aad)
        self.assertEqual(decrypt_bytes(self.key, ct, aad), pt)

    def test_wrong_aad_raises_value_error(self) -> None:
        ct = encrypt_bytes(self.key, b"data", aad=b"right-context")
        with self.assertRaises(ValueError):
            decrypt_bytes(self.key, ct, aad=b"wrong-context")

    def test_ciphertext_starts_with_version_byte(self) -> None:
        ct = encrypt_bytes(self.key, b"x")
        self.assertEqual(ct[0:1], b"\x01")

    def test_different_nonces_each_call(self) -> None:
        ct1 = encrypt_bytes(self.key, b"same")
        ct2 = encrypt_bytes(self.key, b"same")
        # Nonces occupy bytes 1–12; different random nonces → different bytes
        self.assertNotEqual(ct1[1:13], ct2[1:13])


class TestTamperDetection(unittest.TestCase):
    def setUp(self) -> None:
        self.key = os.urandom(32)

    def test_flipped_bit_in_ciphertext_raises_value_error(self) -> None:
        ct = bytearray(encrypt_bytes(self.key, b"sensitive"))
        ct[-1] ^= 0xFF
        with self.assertRaises(ValueError):
            decrypt_bytes(self.key, bytes(ct))

    def test_wrong_key_raises_value_error(self) -> None:
        ct = encrypt_bytes(self.key, b"secret")
        wrong_key = os.urandom(32)
        with self.assertRaises(ValueError):
            decrypt_bytes(wrong_key, ct)

    def test_truncated_ciphertext_raises(self) -> None:
        ct = encrypt_bytes(self.key, b"data")
        with self.assertRaises(ValueError):
            decrypt_bytes(self.key, ct[:5])

    def test_wrong_version_byte_raises(self) -> None:
        ct = bytearray(encrypt_bytes(self.key, b"data"))
        ct[0] = 0x02
        with self.assertRaises(ValueError):
            decrypt_bytes(self.key, bytes(ct))


class TestIsEncrypted(unittest.TestCase):
    def test_recognises_encrypted_blob(self) -> None:
        key = os.urandom(32)
        ct = encrypt_bytes(key, b"hello")
        self.assertTrue(is_encrypted(ct))

    def test_rejects_short_data(self) -> None:
        self.assertFalse(is_encrypted(b"\x01" * 5))

    def test_rejects_plaintext_json(self) -> None:
        self.assertFalse(is_encrypted(b'{"status": "ok"}'))


class TestDeriveSubkey(unittest.TestCase):
    def test_produces_32_bytes(self) -> None:
        master = os.urandom(32)
        sk = derive_subkey(master, "test-domain")
        self.assertEqual(len(sk), 32)

    def test_different_purposes_yield_different_keys(self) -> None:
        master = os.urandom(32)
        k1 = derive_subkey(master, "manifest-v1")
        k2 = derive_subkey(master, "eventlog-v1")
        self.assertNotEqual(k1, k2)

    def test_same_inputs_yield_same_key(self) -> None:
        master = os.urandom(32)
        self.assertEqual(
            derive_subkey(master, "session-v1"),
            derive_subkey(master, "session-v1"),
        )


class TestJsonlLogLine(unittest.TestCase):
    def setUp(self) -> None:
        self.key = os.urandom(32)

    def test_roundtrip(self) -> None:
        data = json.dumps({"event": "download", "file": "photo.jpg"}).encode()
        encoded = encrypt_log_line(data, self.key)
        self.assertEqual(decrypt_log_line(encoded, self.key), data)

    def test_encoded_is_valid_ascii(self) -> None:
        encoded = encrypt_log_line(b"test", self.key)
        encoded.encode("ascii")  # must not raise

    def test_wrong_key_raises(self) -> None:
        encoded = encrypt_log_line(b"secret", self.key)
        with self.assertRaises(Exception):
            decrypt_log_line(encoded, os.urandom(32))


class TestBootstrapDataKey(unittest.TestCase):
    def test_returns_32_bytes_with_mock_keyring(self) -> None:
        mock_kr = MagicMock()
        mock_kr.get_password.return_value = None
        mock_kr.set_password.return_value = None
        with patch("icloud_downloader_lib.crypto._keyring", mock_kr), \
             patch("icloud_downloader_lib.crypto._KEYRING_AVAILABLE", True):
            key = bootstrap_data_key()
        self.assertIsNotNone(key)
        assert key is not None
        self.assertEqual(len(key), 32)

    def test_reuses_existing_key_from_keyring(self) -> None:
        existing = os.urandom(32)
        mock_kr = MagicMock()
        mock_kr.get_password.return_value = existing.hex()
        with patch("icloud_downloader_lib.crypto._keyring", mock_kr), \
             patch("icloud_downloader_lib.crypto._KEYRING_AVAILABLE", True):
            key = bootstrap_data_key()
        self.assertEqual(key, existing)

    def test_returns_none_when_keyring_unavailable(self) -> None:
        with patch("icloud_downloader_lib.crypto._KEYRING_AVAILABLE", False):
            key = bootstrap_data_key()
        self.assertIsNone(key)

    def test_returns_none_when_keyring_write_fails(self) -> None:
        mock_kr = MagicMock()
        mock_kr.get_password.return_value = None
        mock_kr.set_password.side_effect = RuntimeError("locked")
        with patch("icloud_downloader_lib.crypto._keyring", mock_kr), \
             patch("icloud_downloader_lib.crypto._KEYRING_AVAILABLE", True):
            key = bootstrap_data_key()
        self.assertIsNone(key)

    def test_regenerates_key_when_keyring_read_fails(self) -> None:
        mock_kr = MagicMock()
        mock_kr.get_password.side_effect = UnicodeDecodeError("utf-8", b"\xd3", 0, 1, "bad data")
        mock_kr.set_password.return_value = None
        with patch("icloud_downloader_lib.crypto._keyring", mock_kr), \
             patch("icloud_downloader_lib.crypto._KEYRING_AVAILABLE", True):
            key = bootstrap_data_key()
        self.assertIsNotNone(key)
        assert key is not None
        self.assertEqual(len(key), 32)
        mock_kr.set_password.assert_called_once()


class TestInitSessionKeys(unittest.TestCase):
    def test_returns_three_independent_keys_when_available(self) -> None:
        master = os.urandom(32)
        with patch("icloud_downloader_lib.crypto.bootstrap_data_key", return_value=master):
            mk, lk, sk = init_session_keys()
        self.assertIsNotNone(mk)
        self.assertIsNotNone(lk)
        self.assertIsNotNone(sk)
        self.assertNotEqual(mk, lk)
        self.assertNotEqual(lk, sk)
        self.assertNotEqual(mk, sk)

    def test_returns_nones_when_crypto_unavailable(self) -> None:
        with patch("icloud_downloader_lib.crypto.bootstrap_data_key", return_value=None):
            mk, lk, sk = init_session_keys()
        self.assertIsNone(mk)
        self.assertIsNone(lk)
        self.assertIsNone(sk)


class TestWarnPlaintextKeyring(unittest.TestCase):
    def test_warns_for_plaintext_backend(self) -> None:
        mock_backend = MagicMock()
        mock_backend.__class__.__name__ = "PlaintextKeyring"
        mock_kr = MagicMock()
        mock_kr.get_keyring.return_value = mock_backend
        with patch("icloud_downloader_lib.crypto._KEYRING_AVAILABLE", True), \
             patch("icloud_downloader_lib.crypto._keyring", mock_kr):
            import io
            import sys
            captured = io.StringIO()
            sys.stdout = captured
            try:
                warn_plaintext_keyring()
            finally:
                sys.stdout = sys.__stdout__
            self.assertIn("WARNING", captured.getvalue())

    def test_silent_for_secure_backend(self) -> None:
        mock_backend = MagicMock()
        mock_backend.__class__.__name__ = "SecretServiceKeyring"
        mock_kr = MagicMock()
        mock_kr.get_keyring.return_value = mock_backend
        with patch("icloud_downloader_lib.crypto._KEYRING_AVAILABLE", True), \
             patch("icloud_downloader_lib.crypto._keyring", mock_kr):
            import io
            import sys
            captured = io.StringIO()
            sys.stdout = captured
            try:
                warn_plaintext_keyring()
            finally:
                sys.stdout = sys.__stdout__
            self.assertEqual(captured.getvalue(), "")


class TestSessionFileEncryption(unittest.TestCase):
    def setUp(self) -> None:
        self.key = os.urandom(32)
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, filename: str, data: bytes) -> str:
        path = os.path.join(self.tmpdir, filename)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def test_encrypt_then_decrypt_roundtrip(self) -> None:
        payload = b'{"token": "abc123"}'
        self._write("session", payload)
        encrypt_session_files(self.tmpdir, self.key)
        with open(os.path.join(self.tmpdir, "session"), "rb") as fh:
            raw = fh.read()
        self.assertTrue(is_encrypted(raw))
        decrypt_session_files(self.tmpdir, self.key)
        with open(os.path.join(self.tmpdir, "session"), "rb") as fh:
            result = fh.read()
        self.assertEqual(result, payload)

    def test_encrypt_is_idempotent(self) -> None:
        payload = b'{"cookie": "xyz"}'
        self._write("cookies", payload)
        encrypt_session_files(self.tmpdir, self.key)
        with open(os.path.join(self.tmpdir, "cookies"), "rb") as fh:
            first = fh.read()
        encrypt_session_files(self.tmpdir, self.key)
        with open(os.path.join(self.tmpdir, "cookies"), "rb") as fh:
            second = fh.read()
        # Second encrypt should be a no-op (files already encrypted)
        self.assertEqual(first, second)

    def test_decrypt_skips_plaintext_file(self) -> None:
        payload = b'{"unencrypted": true}'
        self._write("session", payload)
        decrypt_session_files(self.tmpdir, self.key)
        with open(os.path.join(self.tmpdir, "session"), "rb") as fh:
            result = fh.read()
        self.assertEqual(result, payload)

    def test_missing_files_do_not_raise(self) -> None:
        # No session/cookies files present — should be a no-op
        encrypt_session_files(self.tmpdir, self.key)
        decrypt_session_files(self.tmpdir, self.key)

    def test_encrypt_then_decrypt_v2_named_files(self) -> None:
        """pyicloud v2.5.0+ uses <apple_id>.session / <apple_id>.cookiejar naming."""
        session_payload = b'{"session_token": "v2"}'
        cookie_payload = b'{"cookies": "v2"}'
        self._write("userexamplecom.session", session_payload)
        self._write("userexamplecom.cookiejar", cookie_payload)

        encrypt_session_files(self.tmpdir, self.key)
        with open(os.path.join(self.tmpdir, "userexamplecom.session"), "rb") as fh:
            self.assertTrue(is_encrypted(fh.read()))
        with open(os.path.join(self.tmpdir, "userexamplecom.cookiejar"), "rb") as fh:
            self.assertTrue(is_encrypted(fh.read()))

        decrypt_session_files(self.tmpdir, self.key)
        with open(os.path.join(self.tmpdir, "userexamplecom.session"), "rb") as fh:
            self.assertEqual(fh.read(), session_payload)
        with open(os.path.join(self.tmpdir, "userexamplecom.cookiejar"), "rb") as fh:
            self.assertEqual(fh.read(), cookie_payload)


class TestStructuredLoggerEncrypted(unittest.TestCase):
    """End-to-end: StructuredLogger writes are opaque on disk when encryption_key is supplied."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.key = derive_subkey(os.urandom(32), "eventlog-v1")

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_log_event_is_not_plaintext_on_disk(self) -> None:
        from icloud_downloader_lib.state import StructuredLogger
        log_path = os.path.join(self.tmpdir, "test.jsonl")
        logger = StructuredLogger(log_path, base_path=self.tmpdir, encryption_key=self.key)
        logger.log("test_event", secret_value="supersecret")
        with open(log_path, "rb") as fh:
            raw = fh.read()
        self.assertNotIn(b"supersecret", raw, "Secret value must not appear as plaintext in log file")
        self.assertNotIn(b"test_event", raw, "Event name must not appear as plaintext in log file")

    def test_log_event_decrypts_correctly(self) -> None:
        from icloud_downloader_lib.state import StructuredLogger
        log_path = os.path.join(self.tmpdir, "test.jsonl")
        logger = StructuredLogger(log_path, base_path=self.tmpdir, encryption_key=self.key)
        logger.log("test_event", secret_value="supersecret")
        with open(log_path, "rb") as fh:
            raw_line = fh.read().strip()
        decrypted = decrypt_log_line(raw_line, self.key).decode()
        self.assertIn("test_event", decrypted)
        self.assertIn("supersecret", decrypted)
