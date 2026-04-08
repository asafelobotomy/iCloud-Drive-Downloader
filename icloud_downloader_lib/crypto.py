"""At-rest encryption for manifest, log, and session files.

AES-256-GCM via the ``cryptography`` library (already a transitive
dependency of pyicloud).  The master DEK (data-encryption key) is
generated once with a CSPRNG, stored in the OS keyring, and per-purpose
subkeys are derived via HKDF-SHA256 so a compromise of one file type
does not expose another.

File format (VERSION 0x01):
    VERSION(1) || NONCE(12) || CIPHERTEXT+TAG(n+16)

JSONL log files: each line is encrypted individually and stored as a
UTF-8 base64 string followed by ``\\n`` so the file stays line-oriented.
Existing plaintext entries are recognised by the absence of the version
byte and remain readable as a graceful legacy fallback.
"""

import base64
import os
import secrets
from typing import Optional, Tuple

try:
    import keyring as _keyring
    _KEYRING_AVAILABLE = True
except ImportError:
    _keyring = None  # type: ignore[assignment]
    _KEYRING_AVAILABLE = False

_SERVICE = "icloud-downloader"
_DEK_ACCOUNT = "data-encryption-key"
_VERSION = b"\x01"
_NONCE_LEN = 12
_MIN_CT_LEN = 1 + _NONCE_LEN + 16  # version + nonce + min GCM tag

# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


def is_crypto_available() -> bool:
    """Return True if the ``cryptography`` package is importable."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# AES-256-GCM primitives
# ---------------------------------------------------------------------------


def encrypt_bytes(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    """Encrypt *plaintext* with AES-256-GCM.

    Returns ``VERSION || NONCE(12) || CIPHERTEXT+TAG``.
    Each call uses a fresh random nonce — never reuse a key+nonce pair.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(_NONCE_LEN)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad or None)
    return _VERSION + nonce + ciphertext


def decrypt_bytes(key: bytes, data: bytes, aad: bytes = b"") -> bytes:
    """Decrypt data produced by :func:`encrypt_bytes`.

    Raises :exc:`ValueError` on version mismatch or GCM authentication failure.
    """
    if len(data) < _MIN_CT_LEN:
        raise ValueError(f"Ciphertext too short ({len(data)} bytes)")
    if data[0:1] != _VERSION:
        raise ValueError(f"Unknown encryption format version: {data[0]:#04x}")
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.exceptions import InvalidTag

    nonce = data[1: 1 + _NONCE_LEN]
    ct_and_tag = data[1 + _NONCE_LEN:]
    try:
        return AESGCM(key).decrypt(nonce, ct_and_tag, aad or None)
    except InvalidTag:
        raise ValueError("GCM authentication failed (wrong key or corrupted data)")


def is_encrypted(data: bytes) -> bool:
    """Return True if *data* begins with the AES-256-GCM version marker."""
    return len(data) >= _MIN_CT_LEN and data[0:1] == _VERSION


# ---------------------------------------------------------------------------
# HKDF key derivation
# ---------------------------------------------------------------------------


def derive_subkey(master: bytes, purpose: str) -> bytes:
    """Derive a 256-bit subkey from *master* for the given *purpose* string.

    Uses HKDF-SHA256 with domain separation so each purpose yields an
    independent key even when sharing the same master DEK.
    """
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes

    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=purpose.encode("utf-8"),
    ).derive(master)


# ---------------------------------------------------------------------------
# JSONL line helpers
# ---------------------------------------------------------------------------


def encrypt_log_line(line_bytes: bytes, key: bytes) -> str:
    """Return a base64-encoded encrypted representation of *line_bytes*."""
    return base64.b64encode(encrypt_bytes(key, line_bytes, b"log-line-v1")).decode("ascii")


def decrypt_log_line(encoded: str, key: bytes) -> bytes:
    """Decrypt a log line produced by :func:`encrypt_log_line`."""
    return decrypt_bytes(key, base64.b64decode(encoded.strip()), b"log-line-v1")


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------


def bootstrap_data_key() -> Optional[bytes]:
    """Return the master DEK, generating and persisting it on the first call.

    Returns ``None`` when ``cryptography`` or the OS keyring is unavailable,
    and the tool falls back to unencrypted operation transparently.
    """
    if not is_crypto_available() or not _KEYRING_AVAILABLE:
        return None

    try:
        existing = _keyring.get_password(_SERVICE, _DEK_ACCOUNT)
    except Exception as exc:
        print(
            f"Warning: Could not read encryption key from system keyring ({exc}). "
            "A new key will be generated if the backend allows writes."
        )
        existing = None

    if existing:
        try:
            return bytes.fromhex(existing)
        except ValueError:
            print(
                "Warning: Encryption key in keyring is corrupted and has been regenerated. "
                "Previously encrypted files (manifest, logs, session) cannot be recovered."
            )

    master = secrets.token_bytes(32)
    try:
        _keyring.set_password(_SERVICE, _DEK_ACCOUNT, master.hex())
    except Exception as exc:
        print(
            f"Warning: Could not persist encryption key to system keyring ({exc}). "
            "Session tokens, manifest, and logs will not be encrypted this run."
        )
        return None  # keyring not writable — operate without encryption
    return master


def init_session_keys() -> Tuple[Optional[bytes], Optional[bytes], Optional[bytes]]:
    """Bootstrap the DEK and return ``(manifest_key, log_key, session_key)``.

    Returns ``(None, None, None)`` when encryption is not available.
    All three subkeys are independent via HKDF domain separation.
    """
    master = bootstrap_data_key()
    if not master:
        return None, None, None
    return (
        derive_subkey(master, "manifest-v1"),
        derive_subkey(master, "eventlog-v1"),
        derive_subkey(master, "session-v1"),
    )


# ---------------------------------------------------------------------------
# OS keyring backend warning
# ---------------------------------------------------------------------------


def warn_plaintext_keyring() -> None:
    """Warn if the keyring backend stores secrets as plaintext.

    ``keyrings.alt`` (common on headless Linux) base64-encodes credentials
    with no encryption — effectively plaintext.  Users should install
    ``gnome-keyring`` or ``kwallet`` for hardware-backed key storage.
    This warning is emitted on every startup when the condition is met.
    """
    if not _KEYRING_AVAILABLE:
        return
    try:
        backend = _keyring.get_keyring()
        name = type(backend).__name__
        if "Plaintext" in name:
            print(
                f"WARNING: OS keyring backend ({name}) stores secrets as base64 plaintext. "
                "Credentials and encryption keys have limited protection on this system.\n"
                "         Install gnome-keyring or kwallet for hardware-backed key storage."
            )
    except Exception as exc:
        print(f"Warning: Could not inspect keyring backend — assuming safe ({exc}).")


# ---------------------------------------------------------------------------
# Session file at-rest encryption (Phase 3)
# ---------------------------------------------------------------------------


def _session_file_paths(directory: str) -> list:
    """Return session/cookie file paths covering legacy and v2.5.0+ naming."""
    import glob

    paths: list = []
    # Legacy pyicloud naming (pre-v2.5.0)
    for filename in ("session", "cookies"):
        path = os.path.join(directory, filename)
        if os.path.exists(path):
            paths.append(path)
    # pyicloud v2.5.0+ naming: <apple_id>.session / <apple_id>.cookiejar
    for pattern in ("*.session", "*.cookiejar"):
        for path in glob.glob(os.path.join(directory, pattern)):
            if path not in paths:
                paths.append(path)
    return paths


def decrypt_session_files(directory: str, key: bytes) -> None:
    """Decrypt session and cookie files in *directory* if they are encrypted.

    Called before pyicloud initialises so it receives the original plaintext.
    Silently skips files that cannot be decrypted — they will be refreshed by
    a new authentication challenge.
    """
    for path in _session_file_paths(directory):
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
            if not raw or not is_encrypted(raw):
                continue
            plaintext = decrypt_bytes(key, raw, b"session-v1")
            with open(path, "wb") as fh:
                fh.write(plaintext)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except Exception:
            pass  # on failure pyicloud will treat file as missing / fresh session


def encrypt_session_files(directory: str, key: bytes) -> None:
    """Encrypt session and cookie files in *directory* after pyicloud writes them.

    Only encrypts files that are currently plaintext (idempotent).
    """
    for path in _session_file_paths(directory):
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
            if not raw or is_encrypted(raw):
                continue
            encrypted = encrypt_bytes(key, raw, b"session-v1")
            with open(path, "wb") as fh:
                fh.write(encrypted)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except Exception as exc:
            print(f"Warning: Could not encrypt session file {os.path.basename(path)} — it remains in plaintext ({exc}).")
