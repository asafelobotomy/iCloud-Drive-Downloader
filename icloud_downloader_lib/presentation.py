import os
import re
import sys
from typing import Any, Dict


class Colors:
    """ANSI color codes for terminal output."""

    ENABLED = sys.stdout.isatty() and os.environ.get("TERM") != "dumb" and not os.environ.get("NO_COLOR")

    RESET = "\033[0m" if ENABLED else ""
    BOLD = "\033[1m" if ENABLED else ""
    DIM = "\033[2m" if ENABLED else ""

    RED = "\033[91m" if ENABLED else ""
    GREEN = "\033[92m" if ENABLED else ""
    YELLOW = "\033[93m" if ENABLED else ""
    BLUE = "\033[94m" if ENABLED else ""
    MAGENTA = "\033[95m" if ENABLED else ""
    CYAN = "\033[96m" if ENABLED else ""
    WHITE = "\033[97m" if ENABLED else ""

    @classmethod
    def disable(cls) -> None:
        """Disable colors."""
        cls.ENABLED = False
        cls.RESET = cls.BOLD = cls.DIM = ""
        cls.RED = cls.GREEN = cls.YELLOW = cls.BLUE = ""
        cls.MAGENTA = cls.CYAN = cls.WHITE = ""


def format_size(bytes_value: int) -> str:
    """Format bytes to human-readable size (e.g., '2.3 GB')."""
    if bytes_value is None:
        return "unknown"

    size = float(bytes_value)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            if unit == "B":
                return f"{size:.0f} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def format_speed(bytes_per_sec: float) -> str:
    """Format download speed to human-readable format."""
    return f"{format_size(int(bytes_per_sec))}/s"


def format_path_for_display(path: str) -> str:
    """Reduce absolute local path disclosure in user-facing output."""
    if not path:
        return path

    if not os.path.isabs(path):
        return path

    normalized_path = os.path.abspath(os.path.expanduser(path))
    home = os.path.abspath(os.path.expanduser("~"))
    cwd = os.path.abspath(os.getcwd())

    try:
        if os.path.commonpath([cwd, normalized_path]) == cwd:
            relative_to_cwd = os.path.relpath(normalized_path, cwd)
            return "." if relative_to_cwd == "." else relative_to_cwd
    except ValueError:
        pass

    try:
        if os.path.commonpath([home, normalized_path]) == home:
            relative_to_home = os.path.relpath(normalized_path, home)
            return "~" if relative_to_home == "." else os.path.join("~", relative_to_home)
    except ValueError:
        pass

    name = os.path.basename(normalized_path.rstrip(os.sep))
    return os.path.join("...", name) if name else path


def redact_paths_in_text(text: str) -> str:
    """Redact absolute filesystem paths that appear inside free-form text."""
    return re.sub(r"(/[A-Za-z0-9._~/-]+)", lambda match: format_path_for_display(match.group(1)), text)


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


def calculate_eta(bytes_downloaded: int, total_bytes: int, elapsed_seconds: float) -> str:
    """Calculate estimated time remaining."""
    if bytes_downloaded == 0 or elapsed_seconds == 0:
        return "calculating..."

    bytes_remaining = total_bytes - bytes_downloaded
    if bytes_remaining <= 0:
        return "0s"

    speed = bytes_downloaded / elapsed_seconds
    eta_seconds = bytes_remaining / speed

    return format_time(int(eta_seconds))


def confirm_download(stats_preview: Dict[str, Any]) -> bool:
    """Ask user to confirm large downloads."""
    estimated_count = stats_preview.get("estimated_files", 0)
    estimated_size = stats_preview.get("estimated_size", 0)

    if estimated_size == 0:
        return True

    size_str = format_size(estimated_size)

    print(f"\n{Colors.YELLOW}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}Download Summary:{Colors.RESET}")
    print(f"  Estimated files: {Colors.CYAN}{estimated_count:,}{Colors.RESET}")
    print(f"  Estimated size:  {Colors.CYAN}{size_str}{Colors.RESET}")
    print(f"{Colors.YELLOW}{'=' * 60}{Colors.RESET}\n")

    if estimated_size > 10 * 1024 * 1024 * 1024:
        print(f"{Colors.YELLOW}⚠️  Warning: This is a large download!{Colors.RESET}")
        print(f"   Make sure you have enough disk space and a stable connection.\n")

    response = input(f"{Colors.BOLD}Continue with download? [Y/n]:{Colors.RESET} ").strip().lower()
    return response in ["", "y", "yes"]