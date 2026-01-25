import os
import re
import sys
import argparse
import time
import random
import shutil
import json
import threading
import fnmatch
import signal
import logging
from pathlib import Path
from datetime import datetime
from getpass import getpass
from queue import Queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple, Any, Set

try:
    from tqdm import tqdm

    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

try:
    from pyicloud import PyiCloudService
    from pyicloud.exceptions import PyiCloudFailedLoginException

    PYICLOUD_AVAILABLE = True
except ImportError:
    PYICLOUD_AVAILABLE = False

try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception,
        before_sleep_log,
    )

    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False

# --- Version Information ---
__version__ = "4.0.0"
__author__ = "iCloud Drive Downloader Contributors"
__license__ = "MIT"
__description__ = "Download entire folders from iCloud Drive with resume capability, filters, and security"

# --- Default Configuration ---
DEFAULT_DOWNLOAD_PATH = os.path.join(os.path.expanduser("~"), "iCloud_Drive_Download")
DEFAULT_CHUNK_SIZE = 8192
DEFAULT_PROGRESS_EVERY_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT = 60  # seconds
DEFAULT_MIN_FREE_SPACE_GB = 1  # minimum free space in GB
DEFAULT_MAX_WORKERS = 3  # concurrent downloads
MANIFEST_FILENAME = ".icloud_download_manifest.json"
LOG_FILENAME = "icloud_download.log.jsonl"
CONFIG_FILENAME = ".icloud_downloader.json"

# Retryable HTTP status codes and exceptions
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
RETRYABLE_EXCEPTIONS = (ConnectionError, TimeoutError)


# ANSI Color codes for terminal output
class Colors:
    """ANSI color codes for terminal output."""

    # Check if colors are supported
    ENABLED = sys.stdout.isatty() and os.environ.get("TERM") != "dumb"

    RESET = "\033[0m" if ENABLED else ""
    BOLD = "\033[1m" if ENABLED else ""

    # Colors
    RED = "\033[91m" if ENABLED else ""
    GREEN = "\033[92m" if ENABLED else ""
    YELLOW = "\033[93m" if ENABLED else ""
    BLUE = "\033[94m" if ENABLED else ""
    MAGENTA = "\033[95m" if ENABLED else ""
    CYAN = "\033[96m" if ENABLED else ""
    WHITE = "\033[97m" if ENABLED else ""

    @classmethod
    def disable(cls):
        """Disable colors."""
        cls.ENABLED = False
        cls.RESET = cls.BOLD = ""
        cls.RED = cls.GREEN = cls.YELLOW = cls.BLUE = ""
        cls.MAGENTA = cls.CYAN = cls.WHITE = ""


def format_size(bytes_value: int) -> str:
    """Format bytes to human-readable size (e.g., '2.3 GB')."""
    if bytes_value is None:
        return "unknown"

    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_value < 1024.0:
            if unit == "B":
                return f"{bytes_value:.0f} {unit}"
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"


def format_speed(bytes_per_sec: float) -> str:
    """Format download speed to human-readable format."""
    return f"{format_size(int(bytes_per_sec))}/s"


def format_time(seconds: int) -> str:
    """Format seconds to human-readable time (e.g., '2h 15m 30s')."""
    if seconds < 0:
        return "calculating..."

    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)

    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or hours > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)


def calculate_eta(
    bytes_downloaded: int, total_bytes: int, elapsed_seconds: float
) -> str:
    """Calculate estimated time remaining."""
    if bytes_downloaded == 0 or elapsed_seconds == 0:
        return "calculating..."

    bytes_remaining = total_bytes - bytes_downloaded
    if bytes_remaining <= 0:
        return "0s"

    speed = bytes_downloaded / elapsed_seconds
    eta_seconds = bytes_remaining / speed

    return format_time(int(eta_seconds))


# Preset configurations
PRESETS = {
    "photos": {
        "name": "Photos & Videos",
        "description": "Download only photo and video files",
        "include": [
            "*.jpg",
            "*.jpeg",
            "*.png",
            "*.gif",
            "*.heic",
            "*.heif",
            "*.mp4",
            "*.mov",
            "*.avi",
            "*.mkv",
            "*.m4v",
        ],
        "workers": 5,
    },
    "documents": {
        "name": "Documents",
        "description": "Download only document files",
        "include": [
            "*.pdf",
            "*.doc",
            "*.docx",
            "*.txt",
            "*.rtf",
            "*.xls",
            "*.xlsx",
            "*.ppt",
            "*.pptx",
            "*.pages",
            "*.numbers",
            "*.key",
        ],
        "workers": 5,
    },
    "quick-test": {
        "name": "Quick Test",
        "description": "Safe test with limits (first 50 items, depth 2)",
        "max_items": 50,
        "max_depth": 2,
        "workers": 3,
    },
    "large-files": {
        "name": "Large Files Only",
        "description": "Download files larger than 100MB",
        "min_size": 104857600,  # 100MB
        "workers": 3,
    },
}


def confirm_download(stats_preview: Dict[str, Any]) -> bool:
    """Ask user to confirm large downloads."""
    estimated_count = stats_preview.get("estimated_files", 0)
    estimated_size = stats_preview.get("estimated_size", 0)

    if estimated_size == 0:
        return True

    # Show warning for large downloads
    size_str = format_size(estimated_size)

    print(f"\n{Colors.YELLOW}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}Download Summary:{Colors.RESET}")
    print(f"  Estimated files: {Colors.CYAN}{estimated_count:,}{Colors.RESET}")
    print(f"  Estimated size:  {Colors.CYAN}{size_str}{Colors.RESET}")
    print(f"{Colors.YELLOW}{'='*60}{Colors.RESET}\n")

    # Warn if >10GB
    if estimated_size > 10 * 1024 * 1024 * 1024:
        print(f"{Colors.YELLOW}⚠️  Warning: This is a large download!{Colors.RESET}")
        print(f"   Make sure you have enough disk space and a stable connection.\n")

    response = (
        input(f"{Colors.BOLD}Continue with download? [Y/n]:{Colors.RESET} ")
        .strip()
        .lower()
    )
    return response in ["", "y", "yes"]


def run_setup_wizard() -> Dict[str, Any]:
    """Interactive setup wizard for first-time users."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(
        f"{Colors.BOLD}{Colors.CYAN}   iCloud Drive Downloader - Interactive Setup{Colors.RESET}"
    )
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}\n")

    print(
        f"{Colors.BOLD}Welcome!{Colors.RESET} Let's download your iCloud Drive files.\n"
    )
    print(
        f"{Colors.YELLOW}💡 Tip:{Colors.RESET} Press Enter to use default values shown in [brackets]\n"
    )

    config = {}

    # Step 0: Apple ID credentials (if not in environment)
    if not os.environ.get("ICLOUD_APPLE_ID"):
        print(f"{Colors.BOLD}Step 1: Apple ID{Colors.RESET}")
        apple_id = input("Enter your Apple ID (email): ").strip()
        if apple_id:
            config["_apple_id"] = apple_id
            print(f"{Colors.GREEN}✓{Colors.RESET} Apple ID: {apple_id}\n")
        else:
            print(f"{Colors.RED}✗{Colors.RESET} Apple ID is required\n")
            sys.exit(1)
    else:
        print(f"{Colors.GREEN}✓{Colors.RESET} Using Apple ID from environment\n")

    if not os.environ.get("ICLOUD_PASSWORD"):
        print(f"{Colors.BOLD}Step 2: App-Specific Password{Colors.RESET}")
        print(
            f"{Colors.YELLOW}Important:{Colors.RESET} You need an app-specific password (NOT your regular password)"
        )
        print(
            f"Get one at: {Colors.CYAN}https://appleid.apple.com/account/manage{Colors.RESET}"
        )
        print(f"  → Sign in → Security → App-Specific Passwords → Generate\n")
        password = input("Enter app-specific password: ").strip()
        if password:
            config["_password"] = password
            print(f"{Colors.GREEN}✓{Colors.RESET} Password saved\n")
        else:
            print(f"{Colors.RED}✗{Colors.RESET} Password is required\n")
            sys.exit(1)
    else:
        print(f"{Colors.GREEN}✓{Colors.RESET} Using password from environment\n")

    # Step 3: Destination
    step_num = 3
    print(f"{Colors.BOLD}Step {step_num}: Choose download location{Colors.RESET}")
    default_path = DEFAULT_DOWNLOAD_PATH
    dest = input(f"Download folder [{default_path}]: ").strip()
    config["destination"] = dest if dest else default_path
    print(f"{Colors.GREEN}✓{Colors.RESET} Will save to: {config['destination']}\n")

    # Step 4: What to download
    print(f"{Colors.BOLD}Step 4: What would you like to download?{Colors.RESET}")
    print("  1. Everything (full backup)")
    print("  2. Photos and videos only")
    print("  3. Documents only")
    print("  4. Quick test (first 50 files)")
    print("  5. Custom filters (advanced)")

    choice = input("\nEnter choice [1]: ").strip()

    if choice == "2":
        config.update(PRESETS["photos"])
        print(f"{Colors.GREEN}✓{Colors.RESET} Will download photos and videos only\n")
    elif choice == "3":
        config.update(PRESETS["documents"])
        print(f"{Colors.GREEN}✓{Colors.RESET} Will download documents only\n")
    elif choice == "4":
        config.update(PRESETS["quick-test"])
        print(
            f"{Colors.GREEN}✓{Colors.RESET} Will run quick test (50 items, 2 levels deep)\n"
        )
    elif choice == "5":
        print("\nCustom filters:")
        include = input(
            "  Include patterns (comma-separated, e.g., *.jpg,*.pdf): "
        ).strip()
        if include:
            config["include"] = [p.strip() for p in include.split(",")]
        exclude = input(
            "  Exclude patterns (comma-separated, e.g., *.tmp,*/Cache/*): "
        ).strip()
        if exclude:
            config["exclude"] = [p.strip() for p in exclude.split(",")]
        print(f"{Colors.GREEN}✓{Colors.RESET} Custom filters set\n")
    else:
        print(f"{Colors.GREEN}✓{Colors.RESET} Will download everything\n")

    # Step 5: Performance
    print(f"{Colors.BOLD}Step 5: Performance settings{Colors.RESET}")
    print("How many concurrent downloads? (1-10)")
    print(
        f"{Colors.YELLOW}💡 Tip:{Colors.RESET} More workers = faster downloads, but uses more bandwidth"
    )
    workers = input("Workers [3]: ").strip()
    try:
        config["workers"] = max(1, min(10, int(workers))) if workers else 3
    except ValueError:
        config["workers"] = 3
    print(
        f"{Colors.GREEN}✓{Colors.RESET} Will use {config['workers']} concurrent downloads\n"
    )

    # Step 6: Dry run option
    print(
        f"{Colors.BOLD}Step 6: Preview before downloading (recommended){Colors.RESET}"
    )
    print("Preview what will be downloaded without actually downloading anything?")
    print(
        f"{Colors.YELLOW}💡 Tip:{Colors.RESET} This lets you verify before using bandwidth"
    )
    dry_run = input("Preview only? [Y/n]: ").strip().lower()
    if dry_run not in ["n", "no"]:
        config["dry_run"] = True
        print(
            f"{Colors.GREEN}✓{Colors.RESET} Will run in preview mode (no actual downloads)\n"
        )
    else:
        print(f"{Colors.GREEN}✓{Colors.RESET} Will download files\n")

    # Step 7: Save config
    print(f"{Colors.BOLD}Step 7: Save configuration (optional){Colors.RESET}")
    save = input("Save this configuration for next time? [Y/n]: ").strip().lower()
    if save in ["", "y", "yes"]:
        config_name = input("Config filename [icloud_config.json]: ").strip()
        config["_save_as"] = config_name if config_name else "icloud_config.json"
        print(f"{Colors.GREEN}✓{Colors.RESET} Will save configuration\n")

    # Summary
    print(f"\n{Colors.BOLD}{Colors.GREEN}✓ Setup complete!{Colors.RESET}\n")
    print(f"{Colors.CYAN}Starting download...{Colors.RESET}\n")

    input(f"Press Enter to begin...")
    print()

    return config


class ShutdownHandler:
    """Handle graceful shutdown on signals."""

    def __init__(self) -> None:
        self.shutdown_requested: bool = False
        self.lock: threading.Lock = threading.Lock()
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum: int, frame: Any) -> None:
        """Signal handler for SIGINT and SIGTERM."""
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
                sys.exit(1)

    def should_stop(self) -> bool:
        """Check if shutdown has been requested."""
        with self.lock:
            return self.shutdown_requested


class FileFilter:
    """Filter files based on patterns, size, and date thresholds."""

    def __init__(
        self,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        min_size: Optional[int] = None,
        max_size: Optional[int] = None,
        modified_after: Optional[datetime] = None,
        modified_before: Optional[datetime] = None,
    ) -> None:
        self.include_patterns: List[str] = include_patterns or []
        self.exclude_patterns: List[str] = exclude_patterns or []
        self.min_size = min_size
        self.max_size = max_size
        self.modified_after = modified_after
        self.modified_before = modified_before

    def should_include(self, file_path, size=None, modified_date=None):
        """Check if file should be included based on filters."""
        # If include patterns specified, file must match at least one
        if self.include_patterns:
            matched = False
            for pattern in self.include_patterns:
                if fnmatch.fnmatch(file_path, pattern) or fnmatch.fnmatch(
                    os.path.basename(file_path), pattern
                ):
                    matched = True
                    break
            if not matched:
                return False

        # If exclude patterns specified, file must not match any
        if self.exclude_patterns:
            for pattern in self.exclude_patterns:
                if fnmatch.fnmatch(file_path, pattern) or fnmatch.fnmatch(
                    os.path.basename(file_path), pattern
                ):
                    return False

        # Check size thresholds
        if size is not None:
            if self.min_size is not None and size < self.min_size:
                return False
            if self.max_size is not None and size > self.max_size:
                return False

        # Check date thresholds
        if modified_date is not None:
            if self.modified_after is not None and modified_date < self.modified_after:
                return False
            if (
                self.modified_before is not None
                and modified_date > self.modified_before
            ):
                return False

        return True


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
        """Mark start time."""
        with self.lock:
            self.start_time = time.time()

    def finish(self) -> None:
        """Mark end time."""
        with self.lock:
            self.end_time = time.time()

    def add_file(self, size: int = 0) -> None:
        """Add a file to total count."""
        with self.lock:
            self.files_total += 1
            self.bytes_total += size

    def mark_completed(self, bytes_downloaded: int = 0) -> None:
        """Mark a file as completed."""
        with self.lock:
            self.files_completed += 1
            self.bytes_downloaded += bytes_downloaded

    def mark_skipped(self) -> None:
        """Mark a file as skipped."""
        with self.lock:
            self.files_skipped += 1

    def mark_failed(self) -> None:
        """Mark a file as failed."""
        with self.lock:
            self.files_failed += 1

    def mark_throttled(self) -> None:
        """Mark a throttle/rate-limit event."""
        with self.lock:
            self.throttle_events += 1
            self.last_throttle_warning = time.time()

    def should_warn_throttle(self) -> bool:
        """Check if we should warn about throttling (max once per 60s)."""
        with self.lock:
            if self.throttle_events == 0:
                return False
            # Only warn once per minute to avoid spam
            return (time.time() - self.last_throttle_warning) < 1.0

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics."""
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
        """Calculate current download speed."""
        with self.lock:
            if not self.start_time:
                return 0.0
            elapsed = time.time() - self.start_time
            if elapsed > 0:
                return self.bytes_downloaded / elapsed
            return 0.0

    def get_eta(self) -> str:
        """Get estimated time remaining."""
        with self.lock:
            if (
                self.bytes_total == 0
                or self.bytes_downloaded == 0
                or not self.start_time
            ):
                return "calculating..."
            elapsed = time.time() - self.start_time
            if elapsed == 0:
                return "calculating..."
            return calculate_eta(self.bytes_downloaded, self.bytes_total, elapsed)

    def progress_percentage(self) -> float:
        """Get download progress percentage."""
        with self.lock:
            if self.bytes_total == 0:
                return 0.0
            return (self.bytes_downloaded / self.bytes_total) * 100


class StructuredLogger:
    """JSON Lines structured logger."""

    def __init__(self, log_path: Optional[str] = None) -> None:
        self.log_path: Optional[str] = log_path
        self.lock: threading.Lock = threading.Lock()

    def log(self, event_type: str, **data: Any) -> None:
        """Log an event in JSONL format."""
        if not self.log_path:
            return

        entry = {"timestamp": datetime.now().isoformat(), "event": event_type, **data}

        with self.lock:
            try:
                with open(self.log_path, "a") as f:
                    f.write(json.dumps(entry) + "\n")
            except IOError as e:
                print(f"Warning: Could not write to log: {e}")


class DownloadManifest:
    """Manages download state persistence and resume capability."""

    def __init__(self, manifest_path: str) -> None:
        self.manifest_path: str = manifest_path
        self.lock: threading.Lock = threading.Lock()
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        """Load manifest from disk or create new one."""
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load manifest ({e}), starting fresh.")
        return {"files": {}, "metadata": {"created": datetime.now().isoformat()}}

    def _save(self) -> None:
        """Save manifest to disk."""
        try:
            with open(self.manifest_path, "w") as f:
                json.dump(self.data, f, indent=2)
            os.chmod(self.manifest_path, 0o600)
        except IOError as e:
            print(f"Warning: Could not save manifest: {e}")

    def get_file_status(self, file_path: str) -> Dict[str, Any]:
        """Get status of a file from manifest."""
        with self.lock:
            return self.data["files"].get(file_path, {})

    def update_file(
        self,
        file_path: str,
        status: str,
        bytes_downloaded: int = 0,
        total_bytes: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """Update file status in manifest."""
        with self.lock:
            self.data["files"][file_path] = {
                "status": status,
                "bytes_downloaded": bytes_downloaded,
                "total_bytes": total_bytes,
                "last_updated": datetime.now().isoformat(),
                "error": error,
            }
            self._save()

    def mark_complete(self, file_path: str, total_bytes: int) -> None:
        """Mark file as completed."""
        self.update_file(file_path, "complete", total_bytes, total_bytes)

    def is_complete(self, file_path: str) -> bool:
        """Check if file is already complete."""
        status = self.get_file_status(file_path)
        return status.get("status") == "complete"


class DirectoryCache:
    """Cache directory listings to reduce API calls."""

    def __init__(self) -> None:
        self.cache: Dict[str, List[str]] = {}
        self.lock: threading.Lock = threading.Lock()

    def get(self, node_name: str) -> Optional[List[str]]:
        """Get cached directory listing."""
        with self.lock:
            return self.cache.get(node_name)

    def set(self, node_name: str, items: List[str]) -> None:
        """Cache directory listing."""
        with self.lock:
            self.cache[node_name] = items

    def clear(self) -> None:
        """Clear the cache."""
        with self.lock:
            self.cache.clear()


def sanitize_name(name: str) -> str:
    """Sanitize iCloud names for safe local filesystem use."""
    safe = name.replace(os.sep, "_").replace("\x00", "")
    safe = re.sub(r"[\r\n\t]", "_", safe)
    # Remove any remaining path traversal patterns
    safe = safe.replace("..", "_")
    safe = safe.strip()
    return safe or "unnamed"


def validate_path_safety(path: str, root: str) -> str:
    """Ensure path is within root directory and doesn't contain traversal patterns."""
    # Reject absolute paths and parent directory references
    if os.path.isabs(path):
        raise ValueError(f"Absolute paths not allowed: {path}")
    if ".." in path.split(os.sep):
        raise ValueError(f"Path traversal detected: {path}")

    # Resolve to absolute and check it's within root
    abs_path = os.path.abspath(path)
    abs_root = os.path.abspath(root)

    if not abs_path.startswith(abs_root + os.sep) and abs_path != abs_root:
        raise ValueError(f"Path escapes root: {path}")

    return abs_path


def calculate_backoff(
    attempt: int, base_delay: float = 1.0, max_delay: float = 60.0
) -> float:
    """Calculate exponential backoff with jitter.

    Note: This function is kept for backward compatibility with tests.
    The main retry logic now uses tenacity library when available.
    """
    # Ensure attempt is at least 1
    attempt = max(1, attempt)
    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
    jitter = random.uniform(0, delay * 0.1)  # 10% jitter
    return delay + jitter


def is_retryable_error(exception: Exception) -> bool:
    """Classify if an error is retryable."""
    if exception is None:
        return False

    if isinstance(exception, RETRYABLE_EXCEPTIONS):
        return True

    # Check for HTTP status codes in exception message
    try:
        error_str = str(exception).lower()
        for code in RETRYABLE_STATUS_CODES:
            if str(code) in error_str:
                return True
    except Exception:
        # If we can't convert to string, treat as non-retryable
        return False

    return False


def is_rate_limit_error(exception: Exception) -> bool:
    """Specifically detect HTTP 429 (rate limiting) errors."""
    if exception is None:
        return False

    try:
        error_str = str(exception).lower()
        # Check for 429 status code or rate limit keywords
        if (
            "429" in error_str
            or "too many requests" in error_str
            or "rate limit" in error_str
        ):
            return True
    except Exception:
        return False

    return False


def download_file(
    item: Any,
    local_path: str,
    failures: List[str],
    label: str,
    config: Dict[str, Any],
    manifest: Optional[DownloadManifest] = None,
    file_filter: Optional[FileFilter] = None,
    stats: Optional[DownloadStats] = None,
    logger: Optional[StructuredLogger] = None,
    dry_run: bool = False,
    pbar: Any = None,
) -> None:
    """Download a single file with retries and minimal progress feedback."""
    # Apply filters
    if file_filter:
        # Try to get file size (may not be available for all items)
        try:
            size = getattr(item, "size", None)
        except:
            size = None

        if not file_filter.should_include(local_path, size=size):
            if config.get("verbose"):
                print(f"  -> Filtered out: '{label}'")
            if logger:
                logger.log("file_filtered", file=local_path, reason="pattern_or_size")
            return

    # Dry run mode
    if dry_run:
        size = getattr(item, "size", 0) if hasattr(item, "size") else 0
        print(f"  [DRY RUN] Would download: '{label}' ({size} bytes)")
        if stats:
            stats.add_file(size)
        if logger:
            logger.log("dry_run_file", file=local_path, size=size)
        return

    # Check manifest for completion
    if manifest and manifest.is_complete(local_path):
        if os.path.exists(local_path):
            print(f"  -> Skipping '{label}' (already complete in manifest)")
            if stats:
                stats.mark_skipped()
            if logger:
                logger.log("file_skipped", file=local_path, reason="already_complete")
            return

    # Check if file exists and is complete
    existing_size = 0
    if os.path.exists(local_path):
        existing_size = os.path.getsize(local_path)
        # If manifest says incomplete, we can try to resume
        if manifest and existing_size > 0:
            status = manifest.get_file_status(local_path)
            if status.get("status") == "partial":
                print(f"  -> Resuming '{label}' from {existing_size} bytes")
                if logger:
                    logger.log(
                        "file_resume", file=local_path, existing_bytes=existing_size
                    )
            else:
                print(f"  -> Skipping '{label}' (already exists)")
                if stats:
                    stats.mark_skipped()
                if logger:
                    logger.log("file_skipped", file=local_path, reason="already_exists")
                return
        else:
            print(f"  -> Skipping '{label}' (already exists)")
            if stats:
                stats.mark_skipped()
            if logger:
                logger.log("file_skipped", file=local_path, reason="already_exists")
            return

    # Define retry behavior based on error type
    def should_retry(exception: Exception) -> bool:
        """Determine if exception should trigger retry."""
        return is_retryable_error(exception)

    def handle_retry_error(retry_state) -> None:
        """Handle retry attempts with custom backoff and warnings."""
        exception = retry_state.outcome.exception()
        attempt = retry_state.attempt_number
        is_throttled = is_rate_limit_error(exception)

        # Track throttle events
        if is_throttled and stats:
            stats.mark_throttled()

        # Calculate backoff (longer for rate limiting)
        if is_throttled:
            # Exponential backoff: 2s, 4s, 8s... max 120s
            wait_time = min(2.0 * (2 ** (attempt - 1)), 120.0)
            jitter = random.uniform(0, wait_time * 0.1)
            wait_time += jitter

            if stats and stats.should_warn_throttle():
                print(
                    f"{Colors.YELLOW}⚠️  Rate limiting detected! Slowing down...{Colors.RESET}"
                )
                print(
                    f"{Colors.YELLOW}    Consider reducing workers (current: {config.get('workers', 'N/A')}){Colors.RESET}"
                )
            print(
                f"{Colors.YELLOW}    -> Rate limited, waiting {wait_time:.1f}s before retry {attempt+1}. Error: {exception}{Colors.RESET}"
            )
        else:
            # Normal exponential backoff: 1s, 2s, 4s... max 60s
            wait_time = min(1.0 * (2 ** (attempt - 1)), 60.0)
            jitter = random.uniform(0, wait_time * 0.1)
            wait_time += jitter
            print(
                f"    -> Retryable error downloading '{label}', waiting {wait_time:.1f}s before retry {attempt+1}. Error: {exception}"
            )

        time.sleep(wait_time)

    def _download_with_retry(attempt_tracker: Dict[str, int]) -> int:
        """Inner function that performs actual download with tenacity retry."""
        # Determine if we're resuming
        current_size = os.path.getsize(local_path) if os.path.exists(local_path) else 0
        resume_from = current_size if current_size > 0 else 0
        attempt = attempt_tracker.get("count", 0) + 1
        attempt_tracker["count"] = attempt

        if resume_from > 0:
            print(
                f"  -> Resuming file: {label} from {resume_from} bytes (attempt {attempt}/{config['max_retries']})"
            )
        else:
            print(
                f"  -> Downloading file: {label} (attempt {attempt}/{config['max_retries']})"
            )

        if manifest:
            manifest.update_file(local_path, "partial", resume_from, 0)

        downloaded = resume_from
        next_progress = ((downloaded // config["progress_every_bytes"]) + 1) * config[
            "progress_every_bytes"
        ]

        # Open file in append mode if resuming, otherwise write mode
        file_mode = "ab" if resume_from > 0 else "wb"

        with item.open(stream=True) as response:
            with open(local_path, file_mode) as file_out:
                for chunk in response.iter_content(chunk_size=config["chunk_size"]):
                    if not chunk:
                        continue
                    file_out.write(chunk)
                    downloaded += len(chunk)
                    if downloaded >= next_progress:
                        print(
                            f"     ... {downloaded // (1024 * 1024)} MB downloaded for {label}"
                        )
                        next_progress += config["progress_every_bytes"]
                        if manifest:
                            manifest.update_file(local_path, "partial", downloaded, 0)

        return downloaded

    # Use tenacity if available, otherwise fall back to manual retry
    attempt_tracker = {"count": 0}
    try:
        if TENACITY_AVAILABLE:
            # Create dynamic retry decorator
            retry_decorator = retry(
                stop=stop_after_attempt(config["max_retries"]),
                retry=retry_if_exception(should_retry),
                reraise=True,
            )
            download_func = retry_decorator(_download_with_retry)

            # Wrap to handle before_sleep callback
            downloaded = None
            for attempt in range(config["max_retries"]):
                try:
                    downloaded = download_func(attempt_tracker)
                    break
                except Exception as e:
                    if attempt < config["max_retries"] - 1 and should_retry(e):
                        # Create mock retry_state for handle_retry_error
                        class RetryState:
                            def __init__(self, exc, attempt_num):
                                self.attempt_number = attempt_num
                                self._exception = exc

                            def outcome(self):
                                class Outcome:
                                    def __init__(self, exc):
                                        self._exc = exc

                                    def exception(self):
                                        return self._exc

                                return Outcome(self._exception)

                        handle_retry_error(RetryState(e, attempt + 1))
                    else:
                        raise

            if downloaded is None:
                raise Exception("Download failed after all retries")
        else:
            # Fallback: manual retry loop (if tenacity not installed)
            downloaded = None
            for attempt in range(1, config["max_retries"] + 1):
                try:
                    downloaded = _download_with_retry(attempt_tracker)
                    break
                except Exception as e:
                    if attempt < config["max_retries"] and should_retry(e):

                        class RetryState:
                            def __init__(self, exc, attempt_num):
                                self.attempt_number = attempt_num
                                self._exception = exc

                            def outcome(self):
                                class Outcome:
                                    def __init__(self, exc):
                                        self._exc = exc

                                    def exception(self):
                                        return self._exc

                                return Outcome(self._exception)

                        handle_retry_error(RetryState(e, attempt))
                    else:
                        raise

        print(f"  -> Saved '{label}' ({downloaded} bytes)")
        if manifest:
            manifest.mark_complete(local_path, downloaded)
        if stats:
            stats.mark_completed(downloaded)
        if logger:
            logger.log(
                "file_completed",
                file=local_path,
                bytes=downloaded,
                attempts=attempt_tracker["count"],
            )
        if pbar:
            pbar.update(1)

    except Exception as e:
        is_throttled = is_rate_limit_error(e)

        # Save partial progress
        if os.path.exists(local_path):
            partial_size = os.path.getsize(local_path)
            if manifest:
                manifest.update_file(local_path, "failed", partial_size, 0, str(e))

        failures.append(f"File '{label}': {e}")
        if is_throttled:
            print(
                f"{Colors.YELLOW}    -> RATE LIMITED: Failed to download '{label}' after {attempt_tracker['count']} attempts{Colors.RESET}"
            )
            print(
                f"{Colors.YELLOW}    💡 Tip: Try reducing workers with --workers 1 or --sequential{Colors.RESET}"
            )
        else:
            print(f"    -> FAILED to download '{label}'. Error: {e}")

        if stats:
            stats.mark_failed()
        if logger:
            logger.log(
                "file_failed",
                file=local_path,
                error=str(e),
                attempts=attempt_tracker["count"],
                throttled=is_throttled,
            )
        if pbar:
            pbar.update(1)


def download_node(
    node: Any,
    local_path: str,
    failures: List[str],
    config: Dict[str, Any],
    root_path: str,
    manifest: Optional[DownloadManifest] = None,
    dir_cache: Optional[DirectoryCache] = None,
    file_filter: Optional[FileFilter] = None,
    stats: Optional[DownloadStats] = None,
    logger: Optional[StructuredLogger] = None,
    dry_run: bool = False,
    pbar: Any = None,
    shutdown_handler: Optional[ShutdownHandler] = None,
    depth: int = 0,
    max_depth: Optional[int] = None,
) -> None:
    """
    This function recursively downloads folders and files.
    """
    # Check for shutdown request
    if shutdown_handler and shutdown_handler.should_stop():
        print(f"Skipping '{node.name}' due to shutdown request")
        return

    # Check max depth
    if max_depth is not None and depth >= max_depth:
        if config.get("verbose"):
            print(f"Skipping '{node.name}' (max depth {max_depth} reached)")
        return
    # Validate path safety
    try:
        validate_path_safety(local_path, root_path)
    except ValueError as e:
        msg = f"Path validation failed for '{local_path}': {e}"
        failures.append(msg)
        print(msg)
        return

    # Create the local directory, including empty ones for structure.
    if not os.path.exists(local_path):
        print(f"Creating directory: {local_path}")
        os.makedirs(local_path, exist_ok=True)
        os.chmod(local_path, 0o700)  # Secure permissions

    # Try to get cached directory listing first
    cache_key = f"{node.name}_{id(node)}"
    child_item_names = None

    if dir_cache:
        child_item_names = dir_cache.get(cache_key)

    # If not cached, fetch from API
    if child_item_names is None:
        try:
            child_item_names = node.dir()
            if dir_cache:
                dir_cache.set(cache_key, child_item_names)
        except Exception as e:
            msg = f"Could not list contents for '{node.name}', skipping. Error: {e}"
            failures.append(msg)
            print(msg)
            return

    if child_item_names:
        print(f"Found {len(child_item_names)} items inside '{node.name}'...")
        for item_name in child_item_names:
            try:
                item = node[item_name]
                safe_name = sanitize_name(item_name)
                child_local_path = os.path.join(local_path, safe_name)

                if item.type == "folder":
                    # Recursive call for the sub-folder
                    download_node(
                        item,
                        child_local_path,
                        failures,
                        config,
                        root_path,
                        manifest,
                        dir_cache,
                        file_filter,
                        stats,
                        logger,
                        dry_run,
                        pbar,
                        shutdown_handler,
                        depth + 1,
                        max_depth,
                    )
                elif item.type == "file":
                    # Check shutdown and max items
                    if shutdown_handler and shutdown_handler.should_stop():
                        break
                    if (
                        config.get("max_items")
                        and stats
                        and stats.files_total >= config["max_items"]
                    ):
                        if config.get("verbose"):
                            print(f"Max items limit ({config['max_items']}) reached")
                        break
                    download_file(
                        item,
                        child_local_path,
                        failures,
                        item_name,
                        config,
                        manifest,
                        file_filter,
                        stats,
                        logger,
                        dry_run,
                        pbar,
                    )
                    # Set secure permissions on downloaded file
                    if os.path.exists(child_local_path):
                        os.chmod(child_local_path, 0o600)
            except Exception as e:
                failures.append(f"Item '{item_name}' in folder '{node.name}': {e}")
                print(f"    -> FAILED to process '{item_name}'. Error: {e}")
    else:
        print(f"Folder '{node.name}' is empty.")


def download_worker(
    task: Tuple[
        Any,
        str,
        str,
        Dict[str, Any],
        Optional[DownloadManifest],
        Optional[FileFilter],
        Optional[DownloadStats],
        Optional[StructuredLogger],
        bool,
        Any,
    ],
) -> List[str]:
    """Worker function for concurrent downloads."""
    (
        item,
        local_path,
        label,
        config,
        manifest,
        file_filter,
        stats,
        logger,
        dry_run,
        pbar,
    ) = task
    failures = []
    download_file(
        item,
        local_path,
        failures,
        label,
        config,
        manifest,
        file_filter,
        stats,
        logger,
        dry_run,
        pbar,
    )
    return failures


def collect_download_tasks(
    node: Any,
    local_path: str,
    config: Dict[str, Any],
    root_path: str,
    manifest: Optional[DownloadManifest],
    dir_cache: Optional[DirectoryCache],
    tasks_list: List[Tuple[Any, str, str, Dict[str, Any], Optional[DownloadManifest]]],
    failures: List[str],
    file_filter: Optional[FileFilter] = None,
    stats: Optional[DownloadStats] = None,
    shutdown_handler: Optional[ShutdownHandler] = None,
    depth: int = 0,
    max_depth: Optional[int] = None,
) -> None:
    """Recursively collect all download tasks without downloading."""
    # Check for shutdown request
    if shutdown_handler and shutdown_handler.should_stop():
        return

    # Check max depth
    if max_depth is not None and depth >= max_depth:
        return

    # Check max items
    if config.get("max_items") and stats and stats.files_total >= config["max_items"]:
        return
    # Validate path safety
    try:
        validate_path_safety(local_path, root_path)
    except ValueError as e:
        msg = f"Path validation failed for '{local_path}': {e}"
        failures.append(msg)
        print(msg)
        return

    # Create the local directory
    if not os.path.exists(local_path):
        os.makedirs(local_path, exist_ok=True)
        os.chmod(local_path, 0o700)

    # Get directory listing
    cache_key = f"{node.name}_{id(node)}"
    child_item_names = None

    if dir_cache:
        child_item_names = dir_cache.get(cache_key)

    if child_item_names is None:
        try:
            child_item_names = node.dir()
            if dir_cache:
                dir_cache.set(cache_key, child_item_names)
        except Exception as e:
            msg = f"Could not list contents for '{node.name}', skipping. Error: {e}"
            failures.append(msg)
            print(msg)
            return

    if child_item_names:
        for item_name in child_item_names:
            try:
                item = node[item_name]
                safe_name = sanitize_name(item_name)
                child_local_path = os.path.join(local_path, safe_name)

                if item.type == "folder":
                    collect_download_tasks(
                        item,
                        child_local_path,
                        config,
                        root_path,
                        manifest,
                        dir_cache,
                        tasks_list,
                        failures,
                        file_filter,
                        stats,
                        shutdown_handler,
                        depth + 1,
                        max_depth,
                    )
                elif item.type == "file":
                    # Check shutdown and max items
                    if shutdown_handler and shutdown_handler.should_stop():
                        break
                    if (
                        config.get("max_items")
                        and stats
                        and stats.files_total >= config["max_items"]
                    ):
                        break

                    # Apply filters
                    should_include = True
                    if file_filter:
                        size = (
                            getattr(item, "size", None)
                            if hasattr(item, "size")
                            else None
                        )
                        should_include = file_filter.should_include(
                            child_local_path, size=size
                        )

                    if should_include:
                        # Skip if already complete
                        if not (
                            manifest
                            and manifest.is_complete(child_local_path)
                            and os.path.exists(child_local_path)
                        ):
                            size = (
                                getattr(item, "size", 0) if hasattr(item, "size") else 0
                            )
                            if stats:
                                stats.add_file(size)
                            tasks_list.append(
                                (item, child_local_path, item_name, config, manifest)
                            )
            except Exception as e:
                failures.append(f"Item '{item_name}' in folder '{node.name}': {e}")
                print(f"    -> FAILED to process '{item_name}'. Error: {e}")


def load_config_file(config_path: str) -> Dict[str, Any]:
    """Load configuration from JSON file."""
    if not os.path.exists(config_path):
        return {}

    try:
        with open(config_path, "r") as f:
            config = json.load(f)
        print(f"Loaded configuration from: {config_path}")
        return config
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Could not load config file ({e}), using defaults.")
        return {}


def save_config_file(config_path: str, config: Dict[str, Any]) -> None:
    """Save configuration to JSON file."""
    try:
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        os.chmod(config_path, 0o600)
        print(f"Configuration saved to: {config_path}")
    except IOError as e:
        print(f"Warning: Could not save config file: {e}")


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Download your entire iCloud Drive with enhanced reliability and security",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show version number and exit",
    )
    parser.add_argument(
        "--destination",
        "-d",
        default=DEFAULT_DOWNLOAD_PATH,
        help="Destination directory for downloads",
    )
    parser.add_argument(
        "--retries",
        "-r",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Maximum number of retries per file",
    )
    parser.add_argument(
        "--timeout",
        "-t",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Network timeout in seconds",
    )
    parser.add_argument(
        "--chunk-size",
        "-c",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help="Download chunk size in bytes",
    )
    parser.add_argument(
        "--min-free-space",
        "-f",
        type=float,
        default=DEFAULT_MIN_FREE_SPACE_GB,
        help="Minimum free space required in GB",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="Number of concurrent download workers",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Disable resume capability (start fresh)",
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Download files sequentially instead of concurrently",
    )
    parser.add_argument(
        "--include",
        action="append",
        help="Include files matching pattern (glob syntax, can be used multiple times)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        help="Exclude files matching pattern (glob syntax, can be used multiple times)",
    )
    parser.add_argument("--min-size", type=int, help="Minimum file size in bytes")
    parser.add_argument("--max-size", type=int, help="Maximum file size in bytes")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be downloaded without downloading",
    )
    parser.add_argument("--log", help="Path to structured JSONL log file")
    parser.add_argument(
        "--no-progress", action="store_true", help="Disable progress bars"
    )
    parser.add_argument(
        "--max-depth", type=int, help="Maximum directory depth to traverse"
    )
    parser.add_argument(
        "--max-items",
        type=int,
        help="Maximum number of items to process (safety limit)",
    )
    parser.add_argument("--config", help="Path to configuration file (JSON format)")
    parser.add_argument(
        "--save-config", help="Save current options to config file and exit"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level",
    )
    parser.add_argument(
        "--preset",
        choices=list(PRESETS.keys()),
        help="Use preset configuration (photos, documents, quick-test, large-files)",
    )
    parser.add_argument(
        "--wizard",
        action="store_true",
        help="Run interactive setup wizard",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )
    parser.add_argument(
        "--skip-confirm",
        action="store_true",
        help="Skip confirmation prompt for large downloads",
    )
    return parser.parse_args()


def check_free_space(path: str, min_gb: float) -> None:
    """Check if there's enough free space at the target path."""
    stat = shutil.disk_usage(path if os.path.exists(path) else os.path.dirname(path))
    free_gb = stat.free / (1024**3)

    if free_gb < min_gb:
        print(f"{Colors.YELLOW}\u26a0\ufe0f  WARNING: Low disk space!{Colors.RESET}")
        print(f"  Available: {Colors.RED}{free_gb:.2f} GB{Colors.RESET}")
        print(f"  Required: {Colors.GREEN}{min_gb:.2f} GB{Colors.RESET}")
        print(
            f"\\n{Colors.YELLOW}\ud83d\udca1 Tip: Use --min-free-space to adjust the threshold{Colors.RESET}"
        )
        response = input(f"\\nContinue anyway? [y/N]: ").strip().lower()
        if response not in ("yes", "y"):
            print(f"{Colors.RED}Aborted by user.{Colors.RESET}")
            sys.exit(0)
    else:
        print(
            f"{Colors.GREEN}\u2713{Colors.RESET} Free space available: {Colors.CYAN}{free_gb:.1f} GB{Colors.RESET}"
        )


def main() -> None:
    """
    Main function to handle login and start the download.
    """
    args = parse_arguments()

    # Handle no-color option
    if args.no_color:
        Colors.disable()

    # Set up logging
    log_level = getattr(logging, args.log_level)
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # Auto-run setup wizard if no significant arguments provided
    # Significant arguments are those that suggest non-interactive usage
    significant_args = [
        args.config,
        args.preset,
        args.save_config,
        args.wizard,
        args.dry_run,
        args.destination != DEFAULT_DOWNLOAD_PATH,
        args.include,
        args.exclude,
        args.max_items,
        args.max_depth,
    ]

    auto_wizard = not any(significant_args)

    # Run setup wizard if requested or auto-detected
    wizard_config = {}
    if args.wizard or auto_wizard:
        if auto_wizard:
            print(f"{Colors.CYAN}Running in interactive mode...{Colors.RESET}")
            print(
                f"{Colors.DIM}(Use --help to see command-line options)\n{Colors.RESET}"
            )
        wizard_config = run_setup_wizard()
        # Save config if requested
        if "_save_as" in wizard_config:
            save_file = wizard_config.pop("_save_as")
            save_config_file(save_file, wizard_config)
            print(
                f"{Colors.GREEN}\u2713{Colors.RESET} Configuration saved to: {Colors.CYAN}{save_file}{Colors.RESET}\\n"
            )

    # Load config file if specified
    file_config = {}
    if args.config:
        file_config = load_config_file(args.config)

    # Apply preset if specified
    preset_config = {}
    if args.preset:
        preset = PRESETS[args.preset]
        preset_config = {
            k: v for k, v in preset.items() if k not in ["name", "description"]
        }
        print(
            f"{Colors.CYAN}\ud83c\udfaf Preset:{Colors.RESET} {Colors.BOLD}{preset['name']}{Colors.RESET}"
        )
        print(f"   {preset['description']}\\n")

    # Merge config: CLI args > wizard_config > preset_config > file_config > defaults
    def get_value(arg_name, file_key=None, default=None):
        """Get value from CLI args, wizard, preset, file config, or default."""
        arg_val = getattr(args, arg_name, None)
        if arg_val is not None:
            return arg_val
        if arg_name in wizard_config:
            return wizard_config[arg_name]
        if arg_name in preset_config:
            return preset_config[arg_name]
        if file_key and file_key in file_config:
            return file_config[file_key]
        return default

    # Handle save-config mode
    if args.save_config:
        save_config = {
            "destination": args.destination,
            "retries": args.retries,
            "timeout": args.timeout,
            "chunk_size": args.chunk_size,
            "min_free_space": args.min_free_space,
            "workers": args.workers,
            "include": args.include,
            "exclude": args.exclude,
            "min_size": args.min_size,
            "max_size": args.max_size,
            "max_depth": args.max_depth,
            "max_items": args.max_items,
            "log_level": args.log_level,
        }
        # Remove None values
        save_config = {k: v for k, v in save_config.items() if v is not None}
        save_config_file(args.save_config, save_config)
        print("Configuration saved. Exiting.")
        sys.exit(0)

    # Check if pyicloud is available
    if not PYICLOUD_AVAILABLE:
        print("ERROR: pyicloud is not installed. Install it with: pip install pyicloud")
        sys.exit(1)

    # Build configuration dict with merged values
    config = {
        "max_retries": get_value("retries", "retries", DEFAULT_MAX_RETRIES),
        "timeout": get_value("timeout", "timeout", DEFAULT_TIMEOUT),
        "chunk_size": get_value("chunk_size", "chunk_size", DEFAULT_CHUNK_SIZE),
        "progress_every_bytes": DEFAULT_PROGRESS_EVERY_BYTES,
        "verbose": args.verbose or file_config.get("verbose", False),
        "workers": get_value("workers", "workers", DEFAULT_MAX_WORKERS),
        "sequential": args.sequential or file_config.get("sequential", False),
        "dry_run": args.dry_run or file_config.get("dry_run", False),
        "no_progress": args.no_progress or file_config.get("no_progress", False),
        "max_depth": get_value("max_depth", "max_depth"),
        "max_items": get_value("max_items", "max_items"),
    }

    # Initialize file filter with merged config
    include_patterns = args.include or file_config.get("include", [])
    exclude_patterns = args.exclude or file_config.get("exclude", [])
    min_size = get_value("min_size", "min_size")
    max_size = get_value("max_size", "max_size")

    file_filter = FileFilter(
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        min_size=min_size,
        max_size=max_size,
    )

    # Initialize stats and logger
    stats = DownloadStats()
    logger = StructuredLogger(args.log) if args.log else None

    download_path = os.path.abspath(
        get_value("destination", "destination", DEFAULT_DOWNLOAD_PATH)
    )

    # Merge include/exclude patterns from all sources
    include_patterns = (
        args.include
        or wizard_config.get("include")
        or preset_config.get("include")
        or file_config.get("include", [])
    )
    exclude_patterns = (
        args.exclude
        or wizard_config.get("exclude")
        or preset_config.get("exclude")
        or file_config.get("exclude", [])
    )

    print(f"\\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(
        f"{Colors.BOLD}{Colors.CYAN}   iCloud Drive Downloader v{__version__}{Colors.RESET}"
    )
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}\\n")

    print(f"{Colors.BOLD}Configuration:{Colors.RESET}")
    print(
        f"  {Colors.BOLD}Destination:{Colors.RESET} {Colors.CYAN}{download_path}{Colors.RESET}"
    )
    print(
        f"  {Colors.BOLD}Workers:{Colors.RESET} {config['workers']} {'(sequential)' if config['sequential'] else '(concurrent)'}"
    )
    print(
        f"  {Colors.BOLD}Retries:{Colors.RESET} {config['max_retries']} | {Colors.BOLD}Timeout:{Colors.RESET} {config['timeout']}s"
    )
    print(
        f"  {Colors.BOLD}Resume:{Colors.RESET} {'Disabled' if args.no_resume else 'Enabled'}"
    )
    print(
        f"  {Colors.BOLD}Mode:{Colors.RESET} {'Preview only' if config['dry_run'] else 'Download'}"
    )
    if config.get("max_depth"):
        print(f"  {Colors.BOLD}Max depth:{Colors.RESET} {config['max_depth']}")
    if config.get("max_items"):
        print(f"  {Colors.BOLD}Max items:{Colors.RESET} {config['max_items']}")
    if include_patterns:
        print(
            f"  {Colors.BOLD}Include:{Colors.RESET} {Colors.GREEN}{', '.join(include_patterns)}{Colors.RESET}"
        )
    if exclude_patterns:
        print(
            f"  {Colors.BOLD}Exclude:{Colors.RESET} {Colors.RED}{', '.join(exclude_patterns)}{Colors.RESET}"
        )
    if min_size:
        print(f"  {Colors.BOLD}Min size:{Colors.RESET} {format_size(min_size)}")
    if max_size:
        print(f"  {Colors.BOLD}Max size:{Colors.RESET} {format_size(max_size)}")
    if args.log:
        print(f"  {Colors.BOLD}Log file:{Colors.RESET} {args.log}")
    print()

    # Create download directory with secure permissions
    if not os.path.exists(download_path):
        os.makedirs(download_path, exist_ok=True)
        os.chmod(download_path, 0o700)

    # Check free space
    check_free_space(download_path, args.min_free_space)

    # Initialize shutdown handler
    shutdown_handler = ShutdownHandler()

    # Initialize manifest and directory cache
    manifest = None
    if not args.no_resume and not config["dry_run"]:
        manifest_path = os.path.join(download_path, MANIFEST_FILENAME)
        manifest = DownloadManifest(manifest_path)
        print(f"Manifest: {manifest_path}")

    dir_cache = DirectoryCache()
    stats.start()

    if logger:
        logger.log(
            "session_start",
            config=config,
            filters={
                "include": include_patterns,
                "exclude": exclude_patterns,
                "min_size": min_size,
                "max_size": max_size,
                "max_depth": config.get("max_depth"),
                "max_items": config.get("max_items"),
            },
        )

    print(
        f"\nAll files will be {'previewed in' if config['dry_run'] else 'saved to'}: {download_path}\n"
    )

    # Get credentials from wizard, environment, or prompt
    apple_id = wizard_config.get("_apple_id") or os.environ.get("ICLOUD_APPLE_ID")
    password = wizard_config.get("_password") or os.environ.get("ICLOUD_PASSWORD")

    if not apple_id:
        apple_id = input("Enter your Apple ID email: ")
    elif not wizard_config.get("_apple_id"):
        print(f"Using Apple ID from environment: {apple_id}")

    if not password:
        password = getpass("Enter your app-specific password: ")
    elif not wizard_config.get("_password"):
        print("Using password from environment variable")

    try:
        api = PyiCloudService(apple_id, password)
    except PyiCloudFailedLoginException:
        print(f"\n{Colors.RED}✗ Login failed!{Colors.RESET}\n")
        print(f"{Colors.BOLD}Possible causes:{Colors.RESET}")
        print(
            f"  1. {Colors.YELLOW}Wrong password{Colors.RESET} - Double-check your app-specific password"
        )
        print(
            f"  2. {Colors.YELLOW}Not an app-specific password{Colors.RESET} - Must generate one at:"
        )
        print(
            f"     {Colors.CYAN}https://appleid.apple.com/account/manage{Colors.RESET}"
        )
        print(f"     Sign in → Security → App-Specific Passwords → Generate")
        print(
            f"  3. {Colors.YELLOW}2FA not set up{Colors.RESET} - Two-factor authentication must be enabled"
        )
        print(
            f"  4. {Colors.YELLOW}Network issue{Colors.RESET} - Check your internet connection\n"
        )
        print(
            f"{Colors.YELLOW}💡 Tip: Try creating a new app-specific password{Colors.RESET}\n"
        )
        sys.exit(1)

    if api.requires_2fa:
        print(f"\n{Colors.YELLOW}Two-factor authentication required{Colors.RESET}")
        print(f"Check your trusted Apple device for the 6-digit code\n")
        code = input(f"  Enter the 6-digit code: ")
        if not api.validate_2fa_code(code):
            print(f"\n{Colors.RED}✗ Failed to verify the 2FA code{Colors.RESET}")
            print(f"\n{Colors.BOLD}Troubleshooting:{Colors.RESET}")
            print(
                f"  1. {Colors.YELLOW}Code expired{Colors.RESET} - Request a new code"
            )
            print(
                f"  2. {Colors.YELLOW}Wrong code{Colors.RESET} - Double-check the numbers"
            )
            print(
                f"  3. {Colors.YELLOW}Device not receiving codes{Colors.RESET} - Check device settings\n"
            )
            print(
                f"{Colors.YELLOW}💡 Tip: Make sure your trusted device is nearby and unlocked{Colors.RESET}\n"
            )
            sys.exit(1)
        try:
            api.trust_session()
        except Exception as e:
            print(
                f"Warning: could not trust session, you may be prompted for 2FA again. Error: {e}"
            )
        print("Successfully authenticated.")

    print("\nAccessing iCloud Drive...")

    failures = []

    top_level_items = api.drive.dir()
    if not top_level_items:
        print("Could not find any files or folders in your iCloud Drive.")
        sys.exit(1)

    print(f"Found {len(top_level_items)} top-level items to process.")

    # Estimate download size if not in dry-run and not skipping confirmation
    if not config["dry_run"] and not args.skip_confirm:
        print(f"\n{Colors.CYAN}Analyzing download size...{Colors.RESET}")
        estimated_files = 0
        estimated_size = 0

        # Quick scan to estimate size
        for item_name in top_level_items[:50]:  # Sample first 50 items
            try:
                item = api.drive[item_name]
                if hasattr(item, "size") and item.size:
                    estimated_files += 1
                    estimated_size += item.size
                elif item.type == "folder":
                    # Rough estimate for folders (can't traverse without taking time)
                    estimated_files += 10  # Assume 10 files per folder
                    estimated_size += 50 * 1024 * 1024  # Assume 50MB per folder
            except Exception:
                pass  # Skip items we can't access

        # Extrapolate if we have many items
        if len(top_level_items) > 50:
            ratio = len(top_level_items) / 50
            estimated_files = int(estimated_files * ratio)
            estimated_size = int(estimated_size * ratio)

        # Ask for confirmation
        if estimated_files > 0:
            stats_preview = {
                "estimated_files": estimated_files,
                "estimated_size": estimated_size,
            }
            if not confirm_download(stats_preview):
                print(f"{Colors.YELLOW}Download cancelled by user.{Colors.RESET}")
                sys.exit(0)

    if config["sequential"]:
        # Sequential mode - original behavior
        for item_name in top_level_items:
            if shutdown_handler.should_stop():
                print("\nStopping due to shutdown request...")
                break

            item = api.drive[item_name]
            safe_name = sanitize_name(item_name)
            local_item_path = os.path.join(download_path, safe_name)

            if item.type == "folder":
                print(f"\n--- Processing folder: '{item_name}' ---")
                download_node(
                    item,
                    local_item_path,
                    failures,
                    config,
                    download_path,
                    manifest,
                    dir_cache,
                    file_filter,
                    stats,
                    logger,
                    config["dry_run"],
                    None,
                    shutdown_handler,
                    0,
                    config.get("max_depth"),
                )
            elif item.type == "file":
                print(f"\n--- Downloading top-level file: '{item_name}' ---")
                download_file(
                    item,
                    local_item_path,
                    failures,
                    item_name,
                    config,
                    manifest,
                    file_filter,
                    stats,
                    logger,
                    config["dry_run"],
                    None,
                )
                # Set secure permissions on downloaded file
                if os.path.exists(local_item_path) and not config["dry_run"]:
                    os.chmod(local_item_path, 0o600)
    else:
        # Concurrent mode - collect all tasks first, then download in parallel
        print("\n--- Collecting download tasks ---")
        tasks = []

        for item_name in top_level_items:
            if shutdown_handler.should_stop():
                print("\nStopping task collection due to shutdown request...")
                break

            item = api.drive[item_name]
            safe_name = sanitize_name(item_name)
            local_item_path = os.path.join(download_path, safe_name)

            if item.type == "folder":
                print(f"Scanning folder: '{item_name}'...")
                collect_download_tasks(
                    item,
                    local_item_path,
                    config,
                    download_path,
                    manifest,
                    dir_cache,
                    tasks,
                    failures,
                    file_filter,
                    stats,
                    shutdown_handler,
                    0,
                    config.get("max_depth"),
                )
            elif item.type == "file":
                # Check max items
                if config.get("max_items") and stats.files_total >= config["max_items"]:
                    break

                # Apply filters
                should_include = True
                if file_filter:
                    size = (
                        getattr(item, "size", None) if hasattr(item, "size") else None
                    )
                    should_include = file_filter.should_include(
                        local_item_path, size=size
                    )

                if should_include:
                    if not (
                        manifest
                        and manifest.is_complete(local_item_path)
                        and os.path.exists(local_item_path)
                    ):
                        size = getattr(item, "size", 0) if hasattr(item, "size") else 0
                        stats.add_file(size)
                        tasks.append(
                            (item, local_item_path, item_name, config, manifest)
                        )

        action = "Previewing" if config["dry_run"] else "Downloading"
        print(f"\n--- {action} {len(tasks)} files with {config['workers']} workers ---")

        if tasks:
            # Create progress bar if tqdm available and not disabled
            pbar = None
            if TQDM_AVAILABLE and not config["no_progress"] and not config["dry_run"]:
                pbar = tqdm(total=len(tasks), desc="Downloading", unit="file")

            # Extend tasks with additional parameters
            extended_tasks = [
                (
                    t[0],
                    t[1],
                    t[2],
                    t[3],
                    t[4],
                    file_filter,
                    stats,
                    logger,
                    config["dry_run"],
                    pbar,
                )
                for t in tasks
            ]

            with ThreadPoolExecutor(max_workers=config["workers"]) as executor:
                future_to_task = {
                    executor.submit(download_worker, task): task
                    for task in extended_tasks
                }
                completed = 0

                for future in as_completed(future_to_task):
                    if shutdown_handler.should_stop():
                        print("\nShutdown requested. Cancelling remaining downloads...")
                        executor.shutdown(wait=False, cancel_futures=True)
                        break

                    task_failures = future.result()
                    failures.extend(task_failures)
                    completed += 1

                    if not pbar and (completed % 10 == 0 or completed == len(tasks)):
                        print(f"Progress: {completed}/{len(tasks)} files processed")

                    # Set secure permissions on completed files
                    task = future_to_task[future]
                    if os.path.exists(task[1]) and not config["dry_run"]:
                        os.chmod(task[1], 0o600)

            if pbar:
                pbar.close()
        else:
            print("No files to download (all complete or filtered out).")

    stats.finish()
    summary = stats.get_summary()

    if shutdown_handler.should_stop():
        print("\n--- Shutdown requested. Session terminated early. ---")
        print(
            "Manifest and progress have been saved. Resume by running the script again."
        )
    else:
        print("\n--- All done! Download complete. ---")
    print("\nStatistics:")
    print(f"  Total files: {summary['files_total']}")
    print(f"  Completed: {summary['files_completed']}")
    print(f"  Skipped: {summary['files_skipped']}")
    print(f"  Failed: {summary['files_failed']}")

    # Report throttle events if any occurred
    if summary.get("throttle_events", 0) > 0:
        print(
            f"{Colors.YELLOW}  \u26a0\ufe0f  Rate limit events: {summary['throttle_events']}{Colors.RESET}"
        )
        print(
            f"{Colors.YELLOW}     Next time, consider using fewer workers (e.g., --workers 1){Colors.RESET}"
        )

    print(f"  Bytes downloaded: {summary['bytes_downloaded']:,}")
    print(f"  Elapsed time: {summary['elapsed_seconds']:.1f}s")

    if summary["elapsed_seconds"] > 0 and summary["bytes_downloaded"] > 0:
        rate = summary["bytes_downloaded"] / summary["elapsed_seconds"] / (1024 * 1024)
        print(f"  Average speed: {rate:.2f} MB/s")

    if logger:
        logger.log("session_end", summary=summary, failures_count=len(failures))

    if failures:
        print("\nSome items failed to download:")
        for failure in failures:
            print(f"  - {failure}")
    else:
        if not args.dry_run:
            print("\nAll items downloaded successfully.")
        else:
            print("\nDry run completed.")


if __name__ == "__main__":
    main()
