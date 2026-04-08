"""Compatibility wrapper for the modular iCloud Drive downloader package."""

from getpass import getpass
from typing import Any, Dict

from icloud_downloader_lib import (
    CONFIG_FILENAME,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_DOWNLOAD_PATH,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_WORKERS,
    DEFAULT_MIN_FREE_SPACE_GB,
    DEFAULT_PROGRESS_EVERY_BYTES,
    DEFAULT_TIMEOUT,
    LOG_FILENAME,
    MANIFEST_FILENAME,
    PRESETS,
    RETRYABLE_STATUS_CODES,
    Colors,
    DirectoryCache,
    DownloadManifest,
    DownloadStats,
    FileFilter,
    PyiCloudFailedLoginException,
    PyiCloudService,
    ShutdownHandler,
    StructuredLogger,
    __author__,
    __description__,
    __license__,
    __version__,
    calculate_backoff,
    calculate_eta,
    check_free_space as _check_free_space,
    collect_download_tasks,
    download_file,
    download_node,
    download_worker,
    format_size,
    format_speed,
    format_time,
    is_rate_limit_error,
    is_retryable_error,
    load_config_file,
    parse_arguments as _parse_arguments,
    save_config_file as _save_config_file,
    sanitize_name,
    validate_path_safety,
)
from icloud_downloader_lib.app import main as _package_main
from icloud_downloader_lib.wizard import run_main_menu as _run_main_menu, run_setup_wizard as _run_setup_wizard

parse_arguments = _parse_arguments
save_config_file = _save_config_file
check_free_space = _check_free_space


def run_main_menu() -> Dict[str, Any]:
    """Run the interactive main menu using wrapper-level prompts for test patching."""
    return _run_main_menu(input_func=input, getpass_func=getpass)


def run_setup_wizard() -> Dict[str, Any]:
    """Run the interactive wizard using wrapper-level prompts for test patching."""
    return _run_setup_wizard(input_func=input, getpass_func=getpass)


def main() -> None:
    """Run the modular application while preserving top-level patch targets."""
    _package_main(
        parse_arguments_func=parse_arguments,
        run_setup_wizard_func=run_main_menu,
        save_config_file_func=save_config_file,
        check_free_space_func=check_free_space,
        pyicloud_service_cls=PyiCloudService,
        manifest_cls=DownloadManifest,
        getpass_func=getpass,
    )


__all__ = [
    "CONFIG_FILENAME",
    "Colors",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_DOWNLOAD_PATH",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_MAX_WORKERS",
    "DEFAULT_MIN_FREE_SPACE_GB",
    "DEFAULT_PROGRESS_EVERY_BYTES",
    "DEFAULT_TIMEOUT",
    "DirectoryCache",
    "DownloadManifest",
    "DownloadStats",
    "FileFilter",
    "LOG_FILENAME",
    "MANIFEST_FILENAME",
    "PRESETS",
    "PyiCloudFailedLoginException",
    "PyiCloudService",
    "RETRYABLE_STATUS_CODES",
    "ShutdownHandler",
    "StructuredLogger",
    "__author__",
    "__description__",
    "__license__",
    "__version__",
    "calculate_backoff",
    "calculate_eta",
    "check_free_space",
    "collect_download_tasks",
    "download_file",
    "download_node",
    "download_worker",
    "format_size",
    "format_speed",
    "format_time",
    "getpass",
    "is_rate_limit_error",
    "is_retryable_error",
    "load_config_file",
    "main",
    "parse_arguments",
    "run_main_menu",
    "run_setup_wizard",
    "sanitize_name",
    "save_config_file",
    "validate_path_safety",
]


if __name__ == "__main__":
    main()