import json
import os
import signal
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from .filters import open_secure_file, validate_path_safety
from .privacy import stable_path_identifier
from .presentation import Colors, calculate_eta


class ShutdownHandler:
    """Handle graceful shutdown on signals."""

    def __init__(self) -> None:
        self.shutdown_requested: bool = False
        self.lock: threading.Lock = threading.Lock()
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum: int, frame: Any) -> None:
        del signum, frame
        with self.lock:
            if not self.shutdown_requested:
                print(
                    f"\n\n{Colors.YELLOW}*** Shutdown requested. Finishing current operations and saving state... ***{Colors.RESET}"
                )
                print(
                    f"{Colors.YELLOW}*** Press Ctrl+C again to force quit (may lose progress) ***{Colors.RESET}\n"
                )
                self.shutdown_requested = True
            else:
                print(f"\n{Colors.RED}*** Force quitting... ***{Colors.RESET}")
                raise SystemExit(1)

    def should_stop(self) -> bool:
        """Check if shutdown has been requested."""
        with self.lock:
            return self.shutdown_requested


class DownloadStats:
    """Track download statistics with real-time ETA."""

    def __init__(self) -> None:
        self.lock: threading.Lock = threading.Lock()
        self.files_total: int = 0
        self.files_completed: int = 0
        self.files_skipped: int = 0
        self.files_failed: int = 0
        self.bytes_total: int = 0
        self.bytes_downloaded: int = 0
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.last_update_time: float = 0
        self.last_bytes: int = 0
        self.throttle_events: int = 0
        self.last_throttle_warning: float = 0

    def start(self) -> None:
        with self.lock:
            self.start_time = time.time()

    def finish(self) -> None:
        with self.lock:
            self.end_time = time.time()

    def add_file(self, size: Optional[int] = 0) -> None:
        with self.lock:
            try:
                normalized_size = int(size or 0)
            except (TypeError, ValueError):
                normalized_size = 0
            self.files_total += 1
            self.bytes_total += normalized_size

    def mark_completed(self, bytes_downloaded: int = 0) -> None:
        with self.lock:
            self.files_completed += 1
            self.bytes_downloaded += bytes_downloaded

    def mark_skipped(self) -> None:
        with self.lock:
            self.files_skipped += 1

    def mark_failed(self) -> None:
        with self.lock:
            self.files_failed += 1

    def mark_throttled(self) -> None:
        with self.lock:
            self.throttle_events += 1
            self.last_throttle_warning = time.time()

    def should_warn_throttle(self) -> bool:
        with self.lock:
            if self.throttle_events == 0:
                return False
            return (time.time() - self.last_throttle_warning) < 1.0

    def get_summary(self) -> Dict[str, Any]:
        with self.lock:
            elapsed = (self.end_time or time.time()) - (self.start_time or time.time())
            return {
                "files_total": self.files_total,
                "files_completed": self.files_completed,
                "files_skipped": self.files_skipped,
                "files_failed": self.files_failed,
                "bytes_total": self.bytes_total,
                "bytes_downloaded": self.bytes_downloaded,
                "elapsed_seconds": elapsed,
                "throttle_events": self.throttle_events,
            }

    def current_speed(self) -> float:
        with self.lock:
            if not self.start_time:
                return 0.0
            elapsed = time.time() - self.start_time
            if elapsed > 0:
                return self.bytes_downloaded / elapsed
            return 0.0

    def get_eta(self) -> str:
        with self.lock:
            if self.bytes_total == 0 or self.bytes_downloaded == 0 or not self.start_time:
                return "calculating..."
            elapsed = time.time() - self.start_time
            if elapsed == 0:
                return "calculating..."
            return calculate_eta(self.bytes_downloaded, self.bytes_total, elapsed)

    def progress_percentage(self) -> float:
        with self.lock:
            if self.bytes_total == 0:
                return 0.0
            return (self.bytes_downloaded / self.bytes_total) * 100


class StructuredLogger:
    """JSON Lines structured logger."""

    def __init__(self, log_path: Optional[str] = None, base_path: Optional[str] = None, *, encryption_key: Optional[bytes] = None) -> None:
        self.log_path = log_path
        self.base_path = os.path.realpath(base_path) if base_path else None
        self.encryption_key = encryption_key
        self.lock: threading.Lock = threading.Lock()

    def log(self, event_type: str, **data: Any) -> None:
        if not self.log_path:
            return

        if isinstance(data.get("file"), str):
            file_path = data.pop("file")
            file_id: Optional[str] = None
            if self.base_path and os.path.isabs(file_path):
                try:
                    safe_path = validate_path_safety(file_path, self.base_path)
                    file_id = stable_path_identifier(safe_path, self.base_path)
                except ValueError:
                    file_id = stable_path_identifier(file_path)
            else:
                file_id = stable_path_identifier(file_path, self.base_path)

            if file_id:
                data = {**data, "file_id": file_id}

        entry = {"timestamp": datetime.now().isoformat(), "event": event_type, **data}
        log_root = os.path.dirname(os.path.abspath(self.log_path)) or "."
        line = json.dumps(entry)

        with self.lock:
            try:
                if self.encryption_key:
                    from .crypto import encrypt_log_line
                    write_line = encrypt_log_line(line.encode("utf-8"), self.encryption_key)
                else:
                    write_line = line
                with open_secure_file(self.log_path, log_root, "a", permissions=0o600, encoding="utf-8") as log_file:
                    log_file.write(write_line + "\n")
            except IOError as error:
                print(f"Warning: Could not write to log: {error}")


class DownloadManifest:
    """Manage download state persistence and resume capability."""

    def __init__(self, manifest_path: str, *, encryption_key: Optional[bytes] = None) -> None:
        self.manifest_path = manifest_path
        self.base_path = os.path.dirname(os.path.abspath(manifest_path)) or "."
        self.lock: threading.Lock = threading.Lock()
        self.encryption_key = encryption_key
        self._legacy_format_detected = False
        self.data: Dict[str, Any] = self._load()
        if self._legacy_format_detected:
            self._save()

    def _file_key(self, file_path: str) -> str:
        return stable_path_identifier(file_path, self.base_path) or file_path

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.manifest_path):
            try:
                with open_secure_file(self.manifest_path, self.base_path, "rb") as manifest_file:
                    raw: bytes = manifest_file.read()
                from .crypto import is_encrypted, decrypt_bytes
                if self.encryption_key and is_encrypted(raw):
                    raw = decrypt_bytes(self.encryption_key, raw, b"manifest-v1")
                data = json.loads(raw)
                migrated_files = {}
                for file_key, status in data.get("files", {}).items():
                    normalized_key = file_key if str(file_key).startswith("sha256:") else self._file_key(str(file_key))
                    if normalized_key != file_key:
                        self._legacy_format_detected = True
                    migrated_files[normalized_key] = status
                data["files"] = migrated_files
                return data
            except (json.JSONDecodeError, IOError, ValueError) as error:
                print(f"Warning: Could not load manifest ({error}), starting fresh.")
        return {"files": {}, "metadata": {"created": datetime.now().isoformat()}}

    def _save(self) -> None:
        try:
            json_bytes = json.dumps(self.data, indent=2).encode("utf-8")
            if self.encryption_key:
                from .crypto import encrypt_bytes
                json_bytes = encrypt_bytes(self.encryption_key, json_bytes, b"manifest-v1")
            with open_secure_file(self.manifest_path, self.base_path, "wb", permissions=0o600) as manifest_file:
                manifest_file.write(json_bytes)
        except IOError as error:
            print(f"Warning: Could not save manifest: {error}")

    def get_file_status(self, file_path: str) -> Dict[str, Any]:
        with self.lock:
            file_key = self._file_key(file_path)
            if file_key in self.data["files"]:
                return self.data["files"][file_key]
            return self.data["files"].get(file_path, {})

    def update_file(
        self,
        file_path: str,
        status: str,
        bytes_downloaded: int = 0,
        total_bytes: int = 0,
        error: Optional[str] = None,
    ) -> None:
        with self.lock:
            file_key = self._file_key(file_path)
            self.data["files"][file_key] = {
                "status": status,
                "bytes_downloaded": bytes_downloaded,
                "total_bytes": total_bytes,
                "last_updated": datetime.now().isoformat(),
                "error": error,
            }
            if file_key != file_path:
                self.data["files"].pop(file_path, None)
            self._save()

    def mark_complete(self, file_path: str, total_bytes: int) -> None:
        self.update_file(file_path, "complete", total_bytes, total_bytes)

    def is_complete(self, file_path: str) -> bool:
        status = self.get_file_status(file_path)
        return status.get("status") == "complete"


class DirectoryCache:
    """Cache directory listings to reduce API calls."""

    def __init__(self) -> None:
        self.cache: Dict[str, List[str]] = {}
        self.lock: threading.Lock = threading.Lock()

    def get(self, node_name: str) -> Optional[List[str]]:
        with self.lock:
            return self.cache.get(node_name)

    def set(self, node_name: str, items: List[str]) -> None:
        with self.lock:
            self.cache[node_name] = items

    def clear(self) -> None:
        with self.lock:
            self.cache.clear()