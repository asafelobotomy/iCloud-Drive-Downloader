import html
import hashlib
import os
import re
import sys
from typing import Any, Callable, List, Optional

from .presentation import redact_paths_in_text


APPLE_ID_PATTERN = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d().\-\s]{6,}\d)(?!\w)")
HTML_DOCUMENT_PATTERN = re.compile(r"<(?:!doctype|html|body)\b", re.IGNORECASE)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")


def redact_apple_id(apple_id: Optional[str]) -> Optional[str]:
    """Redact an Apple ID for user-facing output."""
    if not apple_id or "@" not in apple_id:
        return apple_id

    local_part, domain = apple_id.split("@", 1)
    if len(local_part) <= 2:
        redacted_local = local_part[:1] + "*"
    else:
        redacted_local = local_part[:2] + "*" * max(2, len(local_part) - 2)
    return f"{redacted_local}@{domain}"


def summarize_trusted_target(device: Any) -> str:
    """Return a non-identifying label for a trusted verification target."""
    if isinstance(device, dict) and device.get("phoneNumber"):
        return "SMS target"
    return "Trusted device"


def sanitize_upstream_error_text(text: Optional[str]) -> Optional[str]:
    """Redact identifiers and collapse noisy upstream auth errors for stdout."""
    if not text:
        return None

    sanitized = WHITESPACE_PATTERN.sub(" ", html.unescape(str(text))).strip()
    if not sanitized:
        return None

    if HTML_DOCUMENT_PATTERN.search(sanitized):
        sanitized = "Apple returned a web authentication error."
    else:
        sanitized = HTML_TAG_PATTERN.sub(" ", sanitized)
        sanitized = WHITESPACE_PATTERN.sub(" ", sanitized).strip()
        sanitized = APPLE_ID_PATTERN.sub(
            lambda match: redact_apple_id(match.group(0)) or "[redacted Apple ID]",
            sanitized,
        )
        sanitized = PHONE_PATTERN.sub("[redacted phone]", sanitized)
        sanitized = redact_paths_in_text(sanitized)

    if len(sanitized) > 240:
        sanitized = sanitized[:237].rstrip() + "..."
    return sanitized


def stable_path_identifier(path: Optional[str], root: Optional[str] = None) -> Optional[str]:
    """Return a stable opaque identifier for a filesystem path."""
    if not path:
        return None

    normalized_path = os.path.realpath(os.path.abspath(os.path.expanduser(path)))
    if root:
        normalized_root = os.path.realpath(os.path.abspath(os.path.expanduser(root)))
        try:
            if os.path.commonpath([normalized_root, normalized_path]) == normalized_root:
                normalized_path = os.path.relpath(normalized_path, normalized_root)
        except ValueError:
            pass

    digest = hashlib.sha256(normalized_path.replace(os.sep, "/").encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


def stable_text_identifier(value: Optional[str]) -> Optional[str]:
    """Return a stable opaque identifier for arbitrary text values."""
    if not value:
        return None

    digest = hashlib.sha256(str(value).replace(os.sep, "/").encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


def harden_session_artifacts(session: Any) -> None:
    """Limit persisted session artifacts to owner-only permissions when present."""
    if session is None:
        return

    session_path = getattr(session, "session_path", None)
    cookiejar_path = getattr(session, "cookiejar_path", None)
    cookie_directory = getattr(session, "_cookie_directory", None)

    if not isinstance(cookie_directory, (str, bytes, os.PathLike)):
        cookie_directory = None
    normalized_paths = []
    for path in (session_path, cookiejar_path):
        if isinstance(path, (str, bytes, os.PathLike)):
            normalized_paths.append(path)

    if cookie_directory and os.path.isdir(cookie_directory):
        try:
            os.chmod(cookie_directory, 0o700)
        except OSError:
            pass

    for path in normalized_paths:
        if not os.path.exists(path):
            continue
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def redact_label(name: str) -> str:
    """Return a privacy-safe display label for a filename or item name.

    Shows the first two characters and preserves the file extension so the file
    type remains visible, masking the rest to prevent progress output from
    exposing private content names by default.
    """
    if not name:
        return "[unnamed]"
    base, _, ext = name.rpartition(".")
    if not base:
        base = name
        suffix = ""
    else:
        suffix = f".{ext}"
    if len(base) <= 2:
        redacted = base[:1] + "*"
    else:
        redacted = base[:2] + "*" * max(2, len(base) - 2)
    return f"{redacted}{suffix}"


def prompt_masked_secret(prompt: str) -> str:
    """Read a secret from the terminal while echoing mask characters instead of plaintext."""
    if os.name == "nt":
        return _prompt_masked_secret_windows(prompt)
    return _prompt_masked_secret_posix(prompt)


def _prompt_masked_secret_windows(prompt: str) -> str:
    import msvcrt

    read_char: Callable[[], str] = getattr(msvcrt, "getwch")
    sys.stdout.write(prompt)
    sys.stdout.flush()
    chars: List[str] = []
    while True:
        raw_char = read_char()
        if raw_char in ("\r", "\n"):
            sys.stdout.write("\n")
            sys.stdout.flush()
            return "".join(chars)
        if raw_char == "\003":
            raise KeyboardInterrupt
        if raw_char in ("\b", "\x7f"):
            if chars:
                chars.pop()
                sys.stdout.write("\b \b")
                sys.stdout.flush()
            continue
        chars.append(raw_char)
        sys.stdout.write("*")
        sys.stdout.flush()


def _prompt_masked_secret_posix(prompt: str) -> str:
    import termios
    import tty

    input_stream = sys.stdin
    output_stream = sys.stdout
    file_descriptor = input_stream.fileno()
    original_settings = termios.tcgetattr(file_descriptor)

    output_stream.write(prompt)
    output_stream.flush()

    chars: List[str] = []
    try:
        tty.setraw(file_descriptor)
        while True:
            raw_char = input_stream.read(1)
            if raw_char in ("\n", "\r"):
                output_stream.write("\n")
                output_stream.flush()
                return "".join(chars)
            if raw_char == "\x03":
                raise KeyboardInterrupt
            if raw_char in ("\x7f", "\b"):
                if chars:
                    chars.pop()
                    output_stream.write("\b \b")
                    output_stream.flush()
                continue
            chars.append(raw_char)
            output_stream.write("*")
            output_stream.flush()
    finally:
        termios.tcsetattr(file_descriptor, termios.TCSADRAIN, original_settings)