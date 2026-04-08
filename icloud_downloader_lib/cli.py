import argparse
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from .cli_support import (
    non_negative_float,
    non_negative_int,
    parse_arguments,
    positive_int,
    print_presets,
    validate_arguments,
    worker_count,
)

from .definitions import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_DOWNLOAD_PATH,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_WORKERS,
    DEFAULT_MIN_FREE_SPACE_GB,
    DEFAULT_PROGRESS_EVERY_BYTES,
    DEFAULT_TIMEOUT,
    PRESETS,
    __version__,
)
from .filters import FileFilter, ensure_directory, open_secure_file
from .presentation import format_path_for_display


def load_config_file(config_path: str) -> Dict[str, Any]:
    """Load configuration from JSON file."""
    if not os.path.exists(config_path):
        return {}

    resolved_config_path = os.path.abspath(config_path)
    config_dir = os.path.dirname(resolved_config_path) or "."
    try:
        with open_secure_file(resolved_config_path, config_dir, "r", encoding="utf-8") as config_file:
            config = json.load(config_file)
        print(f"Loaded configuration from: {format_path_for_display(config_path)}")
        return config
    except (json.JSONDecodeError, IOError, ValueError) as error:
        from .privacy import sanitize_upstream_error_text as _sanitize
        print(f"Warning: Could not load config file ({_sanitize(str(error))}), using defaults.")
        return {}


def save_config_file(config_path: str, config: Dict[str, Any]) -> None:
    """Save configuration to JSON file."""
    one_shot_keys = {"store_in_keyring"}
    persisted_config = {
        key: value
        for key, value in config.items()
        if not key.startswith("_") and key not in one_shot_keys
    }
    resolved_config_path = os.path.abspath(config_path)
    config_dir = os.path.dirname(resolved_config_path) or "."
    try:
        ensure_directory(config_dir, config_dir, 0o700)
        with open_secure_file(resolved_config_path, config_dir, "w", permissions=0o600, encoding="utf-8") as config_file:
            json.dump(persisted_config, config_file, indent=2)
        print(f"Configuration saved to: {format_path_for_display(config_path)}")
    except (IOError, ValueError) as error:
        from .privacy import sanitize_upstream_error_text as _sanitize
        print(f"Warning: Could not save config file: {_sanitize(str(error))}")


def build_save_config(args: argparse.Namespace) -> Dict[str, Any]:
    """Build the config payload written by --save-config."""
    save_config: Dict[str, Any] = {
        "destination": getattr(args, "destination", DEFAULT_DOWNLOAD_PATH),
        "retries": getattr(args, "retries", DEFAULT_MAX_RETRIES),
        "timeout": getattr(args, "timeout", DEFAULT_TIMEOUT),
        "chunk_size": getattr(args, "chunk_size", DEFAULT_CHUNK_SIZE),
        "min_free_space": getattr(args, "min_free_space", DEFAULT_MIN_FREE_SPACE_GB),
        "workers": getattr(args, "workers", DEFAULT_MAX_WORKERS),
        "session_dir": getattr(args, "session_dir", None),
        "include": getattr(args, "include", None),
        "exclude": getattr(args, "exclude", None),
        "min_size": getattr(args, "min_size", None),
        "max_size": getattr(args, "max_size", None),
        "max_depth": getattr(args, "max_depth", None),
        "max_items": getattr(args, "max_items", None),
        "inventory_cache": getattr(args, "inventory_cache", None),
        "selection_mode": getattr(args, "selection_mode", None),
        "log_level": getattr(args, "log_level", "INFO"),
    }
    for key in [
        "verbose",
        "sequential",
        "dry_run",
        "progress",
        "resume",
        "china_mainland",
        "use_keyring",
        "store_password_in_keyring",
        "build_inventory_cache",
        "refresh_inventory_cache",
        "select_from_cache",
        "source",
        "photos_scope",
        "photos_album",
        "photos_month",
        "photos_after",
        "photos_before",
    ]:
        if hasattr(args, key):
            save_config[key] = getattr(args, key)
    return {key: value for key, value in save_config.items() if value is not None}


def extract_preset_config(args: argparse.Namespace) -> Dict[str, Any]:
    """Get the selected preset configuration values, if any."""
    preset_name = getattr(args, "preset", None)
    if not preset_name:
        return {}
    preset = PRESETS[preset_name]
    return {key: value for key, value in preset.items() if key not in ["name", "description"]}


def get_merged_value(
    args: argparse.Namespace,
    wizard_config: Dict[str, Any],
    preset_config: Dict[str, Any],
    file_config: Dict[str, Any],
    arg_name: str,
    file_key: Optional[str] = None,
    default: Any = None,
) -> Any:
    """Get a config value from CLI args, wizard, preset, file config, or default."""
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


def get_merged_boolean(
    args: argparse.Namespace,
    wizard_config: Dict[str, Any],
    preset_config: Dict[str, Any],
    file_config: Dict[str, Any],
    arg_name: str,
    file_key: str,
    default: bool,
    legacy_negative_key: Optional[str] = None,
) -> bool:
    """Resolve boolean settings while supporting legacy negative config keys."""
    arg_val = getattr(args, arg_name, None)
    if arg_val is not None:
        return bool(arg_val)
    if arg_name in wizard_config:
        return bool(wizard_config[arg_name])
    if arg_name in preset_config:
        return bool(preset_config[arg_name])
    if file_key in file_config:
        return bool(file_config[file_key])
    if legacy_negative_key and legacy_negative_key in file_config:
        return not bool(file_config[legacy_negative_key])
    return default


def build_runtime_config(
    args: argparse.Namespace,
    wizard_config: Dict[str, Any],
    preset_config: Dict[str, Any],
    file_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the merged runtime configuration."""
    return {
        "max_retries": get_merged_value(args, wizard_config, preset_config, file_config, "retries", "retries", DEFAULT_MAX_RETRIES),
        "timeout": get_merged_value(args, wizard_config, preset_config, file_config, "timeout", "timeout", DEFAULT_TIMEOUT),
        "chunk_size": get_merged_value(args, wizard_config, preset_config, file_config, "chunk_size", "chunk_size", DEFAULT_CHUNK_SIZE),
        "min_free_space": get_merged_value(
            args,
            wizard_config,
            preset_config,
            file_config,
            "min_free_space",
            "min_free_space",
            DEFAULT_MIN_FREE_SPACE_GB,
        ),
        "progress_every_bytes": DEFAULT_PROGRESS_EVERY_BYTES,
        "verbose": get_merged_value(args, wizard_config, preset_config, file_config, "verbose", "verbose", False),
        "workers": get_merged_value(args, wizard_config, preset_config, file_config, "workers", "workers", DEFAULT_MAX_WORKERS),
        "session_dir": get_merged_value(args, wizard_config, preset_config, file_config, "session_dir", "session_dir"),
        "sequential": get_merged_value(args, wizard_config, preset_config, file_config, "sequential", "sequential", False),
        "dry_run": get_merged_value(args, wizard_config, preset_config, file_config, "dry_run", "dry_run", False),
        "china_mainland": get_merged_boolean(
            args,
            wizard_config,
            preset_config,
            file_config,
            "china_mainland",
            "china_mainland",
            False,
        ),
        "use_keyring": get_merged_boolean(
            args,
            wizard_config,
            preset_config,
            file_config,
            "use_keyring",
            "use_keyring",
            False,
        ),
        "store_password_in_keyring": get_merged_boolean(
            args,
            wizard_config,
            preset_config,
            file_config,
            "store_password_in_keyring",
            "store_password_in_keyring",
            False,
        ),
        "store_in_keyring": bool(getattr(args, "store_in_keyring", False)),
        "progress": get_merged_boolean(
            args,
            wizard_config,
            preset_config,
            file_config,
            "progress",
            "progress",
            True,
            legacy_negative_key="no_progress",
        ),
        "resume": get_merged_boolean(
            args,
            wizard_config,
            preset_config,
            file_config,
            "resume",
            "resume",
            True,
            legacy_negative_key="no_resume",
        ),
        "max_depth": get_merged_value(args, wizard_config, preset_config, file_config, "max_depth", "max_depth"),
        "max_items": get_merged_value(args, wizard_config, preset_config, file_config, "max_items", "max_items"),
        "inventory_cache": get_merged_value(
            args,
            wizard_config,
            preset_config,
            file_config,
            "inventory_cache",
            "inventory_cache",
        ),
        "build_inventory_cache": get_merged_boolean(
            args,
            wizard_config,
            preset_config,
            file_config,
            "build_inventory_cache",
            "build_inventory_cache",
            False,
        ),
        "refresh_inventory_cache": get_merged_boolean(
            args,
            wizard_config,
            preset_config,
            file_config,
            "refresh_inventory_cache",
            "refresh_inventory_cache",
            False,
        ),
        "select_from_cache": get_merged_boolean(
            args,
            wizard_config,
            preset_config,
            file_config,
            "select_from_cache",
            "select_from_cache",
            False,
        ),
        "selection_mode": get_merged_value(
            args,
            wizard_config,
            preset_config,
            file_config,
            "selection_mode",
            "selection_mode",
            "mixed",
        ),
        "log_level": get_merged_value(args, wizard_config, preset_config, file_config, "log_level", "log_level", "INFO"),
        "source": get_merged_value(args, wizard_config, preset_config, file_config, "source", "source", "drive"),
        "photos_scope": get_merged_value(args, wizard_config, preset_config, file_config, "photos_scope", "photos_scope", "all"),
        "photos_album": get_merged_value(args, wizard_config, preset_config, file_config, "photos_album", "photos_album"),
        "photos_month": get_merged_value(args, wizard_config, preset_config, file_config, "photos_month", "photos_month"),
        "photos_after": get_merged_value(args, wizard_config, preset_config, file_config, "photos_after", "photos_after"),
        "photos_before": get_merged_value(args, wizard_config, preset_config, file_config, "photos_before", "photos_before"),
    }


def build_filter_context(
    args: argparse.Namespace,
    wizard_config: Dict[str, Any],
    preset_config: Dict[str, Any],
    file_config: Dict[str, Any],
    *,
    selection_root: Optional[str] = None,
    selected_files: Optional[List[str]] = None,
    selected_folders: Optional[List[str]] = None,
) -> Tuple[FileFilter, List[str], List[str], Optional[int], Optional[int]]:
    """Build include/exclude context and the runtime FileFilter."""
    include_patterns = (
        getattr(args, "include", None)
        or wizard_config.get("include")
        or preset_config.get("include")
        or file_config.get("include", [])
    )
    exclude_patterns = (
        getattr(args, "exclude", None)
        or wizard_config.get("exclude")
        or preset_config.get("exclude")
        or file_config.get("exclude", [])
    )
    min_size = get_merged_value(args, wizard_config, preset_config, file_config, "min_size", "min_size")
    max_size = get_merged_value(args, wizard_config, preset_config, file_config, "max_size", "max_size")
    file_filter = FileFilter(
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        min_size=min_size,
        max_size=max_size,
        selected_files=selected_files,
        selected_folders=selected_folders,
        selection_root=selection_root,
    )
    return file_filter, include_patterns, exclude_patterns, min_size, max_size


def resolve_download_path(
    args: argparse.Namespace,
    wizard_config: Dict[str, Any],
    preset_config: Dict[str, Any],
    file_config: Dict[str, Any],
) -> str:
    """Resolve the absolute download destination path."""
    destination = get_merged_value(
        args,
        wizard_config,
        preset_config,
        file_config,
        "destination",
        "destination",
        DEFAULT_DOWNLOAD_PATH,
    )
    return os.path.abspath(destination)