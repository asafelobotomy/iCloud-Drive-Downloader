import argparse
import textwrap
from datetime import date as _date

from .definitions import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_DOWNLOAD_PATH,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_WORKERS,
    DEFAULT_MIN_FREE_SPACE_GB,
    DEFAULT_TIMEOUT,
    PHOTOS_SCOPES,
    PRESETS,
    __version__,
)


class CliHelpFormatter(
    argparse.ArgumentDefaultsHelpFormatter,
    argparse.RawDescriptionHelpFormatter,
):
    """Format help text with examples while still showing resolved defaults."""


def positive_int(value: str) -> int:
    """Argparse type for integers greater than zero."""
    parsed_value = int(value)
    if parsed_value <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed_value


def non_negative_int(value: str) -> int:
    """Argparse type for integers greater than or equal to zero."""
    parsed_value = int(value)
    if parsed_value < 0:
        raise argparse.ArgumentTypeError("must be greater than or equal to 0")
    return parsed_value


def worker_count(value: str) -> int:
    """Argparse type for worker counts within the supported range."""
    parsed_value = positive_int(value)
    if parsed_value > 10:
        raise argparse.ArgumentTypeError("must be between 1 and 10")
    return parsed_value


def non_negative_float(value: str) -> float:
    """Argparse type for floats greater than or equal to zero."""
    parsed_value = float(value)
    if parsed_value < 0:
        raise argparse.ArgumentTypeError("must be greater than or equal to 0")
    return parsed_value


def human_size(value: str) -> int:
    """Argparse type accepting byte counts with optional unit suffix.

    Accepts plain integers (bytes) or a number followed by a unit:
    B, KB, MB, GB, TB (case-insensitive, with or without B suffix).
    Examples: 500, 10KB, 2.5GB, 1.2tb
    """
    multipliers = [
        ("tb", 1024 ** 4),
        ("gb", 1024 ** 3),
        ("mb", 1024 ** 2),
        ("kb", 1024),
        ("b", 1),
    ]
    stripped = value.strip().lower()
    for suffix, mult in multipliers:
        if stripped.endswith(suffix):
            numeric = stripped[: -len(suffix)].strip()
            try:
                result = int(float(numeric) * mult)
            except ValueError:
                raise argparse.ArgumentTypeError(
                    f"Invalid size {value!r}: expected a number before '{suffix.upper()}'"
                )
            if result < 0:
                raise argparse.ArgumentTypeError("size must be >= 0")
            return result
    try:
        result = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid size {value!r}. Use bytes (e.g. 1048576) or a unit suffix (e.g. 10KB, 2.5GB)"
        )
    if result < 0:
        raise argparse.ArgumentTypeError("size must be >= 0")
    return result


def print_presets() -> None:
    """Print the available preset names and descriptions."""
    print("Available presets:\n")
    for preset_name, preset in PRESETS.items():
        print(f"  {preset_name:<12} {preset['name']}")
        print(f"  {'':12} {preset['description']}")
        print()


def validate_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Validate cross-argument constraints after parsing."""
    min_size = getattr(args, "min_size", None)
    max_size = getattr(args, "max_size", None)
    if min_size is not None and max_size is not None and min_size > max_size:
        parser.error("--min-size cannot be greater than --max-size")
    if getattr(args, "selection_mode", None) and not getattr(args, "select_from_cache", False):
        parser.error("--selection-mode requires --select-from-cache")
    for date_flag, arg_name in (("--photos-after", "photos_after"), ("--photos-before", "photos_before")):
        value = getattr(args, arg_name, None)
        if value:
            try:
                _date.fromisoformat(value)
            except ValueError:
                parser.error(f"{date_flag} must be in YYYY-MM-DD format, got: {value}")


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Download your entire iCloud Drive with enhanced reliability and security",
        formatter_class=CliHelpFormatter,
        epilog=textwrap.dedent(
            """
            Examples:
              python3 icloud_downloader.py
              python3 icloud_downloader.py --preset photos --dry-run
              python3 icloud_downloader.py --config examples/example-config.json
              python3 icloud_downloader.py --list-presets
            """
        ),
    )
    parser.add_argument("--version", "-V", action="version", version=f"%(prog)s {__version__}", help="Show version number and exit")

    discovery_group = parser.add_argument_group("Discovery")
    discovery_group.add_argument("--list-presets", action="store_true", default=argparse.SUPPRESS, help="List available presets and exit")
    discovery_group.add_argument("--preset", choices=list(PRESETS.keys()), default=argparse.SUPPRESS, help="Use preset configuration")
    discovery_group.add_argument("--wizard", action="store_true", default=argparse.SUPPRESS, help="Run interactive setup wizard")
    discovery_group.add_argument("--source", choices=["drive", "photos-library"], default=argparse.SUPPRESS, help="Content source: iCloud Drive (default) or Photos Library")
    discovery_group.add_argument("--photos-scope", choices=list(PHOTOS_SCOPES.keys()), default=argparse.SUPPRESS, help="Photos Library scope: all, photos, videos, by-album, by-month (default: all)")
    discovery_group.add_argument("--photos-album", default=argparse.SUPPRESS, help="Album name to download (with --source photos-library --photos-scope by-album)")
    discovery_group.add_argument("--photos-month", default=argparse.SUPPRESS, help="Month to download in YYYY-MM format (with --source photos-library --photos-scope by-month)")

    auth_group = parser.add_argument_group("Authentication And Session")
    auth_group.add_argument("--auth-status", action="store_true", default=argparse.SUPPRESS, help="Print local iCloud auth/session status and exit")
    auth_group.add_argument("--session-dir", default=argparse.SUPPRESS, help="Directory for persisted iCloud session cookies and state")
    auth_group.add_argument("--china-mainland", action="store_true", default=argparse.SUPPRESS, help="Use iCloud China mainland endpoints")
    auth_group.add_argument("--use-keyring", action="store_true", default=argparse.SUPPRESS, help="Load the password from the system keyring when available")
    auth_group.add_argument("--store-in-keyring", action="store_true", default=argparse.SUPPRESS, help="Store the password from this run in the system keyring")

    destination_group = parser.add_argument_group("Destination And Transfer")
    destination_group.add_argument("--destination", "-d", default=argparse.SUPPRESS, help=f"Destination directory for downloads (default: {DEFAULT_DOWNLOAD_PATH})")
    destination_group.add_argument("--workers", "-w", type=worker_count, default=argparse.SUPPRESS, help=f"Number of concurrent download workers (default: {DEFAULT_MAX_WORKERS})")
    destination_group.add_argument("--sequential", action="store_true", default=argparse.SUPPRESS, help="Download files sequentially instead of concurrently")
    destination_group.add_argument("--chunk-size", "-c", type=positive_int, default=argparse.SUPPRESS, help=f"Download chunk size in bytes (default: {DEFAULT_CHUNK_SIZE})")
    destination_group.add_argument("--timeout", "-t", type=positive_int, default=argparse.SUPPRESS, help=f"Network timeout in seconds (default: {DEFAULT_TIMEOUT})")
    destination_group.add_argument("--retries", "-r", type=positive_int, default=argparse.SUPPRESS, help=f"Maximum number of retries per file (default: {DEFAULT_MAX_RETRIES})")
    destination_group.add_argument("--min-free-space", "-f", type=non_negative_float, default=argparse.SUPPRESS, help=f"Minimum free space required in GB (default: {DEFAULT_MIN_FREE_SPACE_GB})")
    resume_group = destination_group.add_mutually_exclusive_group()
    resume_group.add_argument("--resume", dest="resume", action="store_true", default=argparse.SUPPRESS, help="Enable resume capability")
    resume_group.add_argument("--no-resume", dest="resume", action="store_false", default=argparse.SUPPRESS, help="Disable resume capability (start fresh)")
    destination_group.add_argument("--skip-confirm", action="store_true", default=argparse.SUPPRESS, help="Skip confirmation prompt for large downloads")

    filter_group = parser.add_argument_group("Filters And Limits")
    filter_group.add_argument("--include", action="append", default=argparse.SUPPRESS, help="Include files matching pattern (glob syntax, repeatable)")
    filter_group.add_argument("--exclude", action="append", default=argparse.SUPPRESS, help="Exclude files matching pattern (glob syntax, repeatable)")
    filter_group.add_argument("--min-size", type=human_size, default=argparse.SUPPRESS, help="Minimum file size (e.g. 10MB, 2.5GB, 1048576)")
    filter_group.add_argument("--max-size", type=human_size, default=argparse.SUPPRESS, help="Maximum file size (e.g. 500MB, 1GB, 1073741824)")
    filter_group.add_argument("--max-depth", type=non_negative_int, default=argparse.SUPPRESS, help="Maximum directory depth to traverse")
    filter_group.add_argument("--max-items", type=positive_int, default=argparse.SUPPRESS, help="Maximum number of items to process (safety limit)")
    filter_group.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS, help="Preview what would be downloaded without downloading")
    filter_group.add_argument("--photos-after", default=argparse.SUPPRESS, metavar="DATE", help="Only include Photos Library assets created on or after this date (YYYY-MM-DD)")
    filter_group.add_argument("--photos-before", default=argparse.SUPPRESS, metavar="DATE", help="Only include Photos Library assets created on or before this date (YYYY-MM-DD)")

    inventory_group = parser.add_argument_group("Inventory Cache And Selection")
    inventory_group.add_argument("--inventory-cache", default=argparse.SUPPRESS, help="Path to the secure local inventory cache")
    inventory_group.add_argument("--build-inventory-cache", action="store_true", default=argparse.SUPPRESS, help="Scan iCloud Drive, save the secure inventory cache, and exit")
    inventory_group.add_argument("--refresh-inventory-cache", action="store_true", default=argparse.SUPPRESS, help="Refresh the secure inventory cache before continuing")
    inventory_group.add_argument("--select-from-cache", action="store_true", default=argparse.SUPPRESS, help="Choose folders and files from the secure inventory cache before running")
    inventory_group.add_argument("--selection-mode", choices=["mixed", "folders", "files"], default=argparse.SUPPRESS, help="Limit selector toggles to folders, files, or both")

    config_group = parser.add_argument_group("Configuration And Output")
    config_group.add_argument("--show-config", action="store_true", default=argparse.SUPPRESS, help="Print the resolved configuration and exit")
    config_group.add_argument("--config", default=argparse.SUPPRESS, help="Path to configuration file (JSON format)")
    config_group.add_argument("--save-config", default=argparse.SUPPRESS, help="Save current settings to a config file and exit")
    config_group.add_argument("--log", default=argparse.SUPPRESS, help="Path to structured JSONL log file")
    config_group.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default=argparse.SUPPRESS, help="Logging level")
    config_group.add_argument("--verbose", "-v", action="store_true", default=argparse.SUPPRESS, help="Enable verbose output")
    progress_group = config_group.add_mutually_exclusive_group()
    progress_group.add_argument("--progress", dest="progress", action="store_true", default=argparse.SUPPRESS, help="Enable progress bars")
    progress_group.add_argument("--no-progress", dest="progress", action="store_false", default=argparse.SUPPRESS, help="Disable progress bars")
    config_group.add_argument("--no-color", action="store_true", default=argparse.SUPPRESS, help="Disable colored output")

    args = parser.parse_args()
    validate_arguments(parser, args)
    return args