import json
import logging
import os
import sys
from getpass import getpass
from typing import Any, Callable, Dict, Type

from .cli import (
    build_filter_context,
    build_runtime_config,
    build_save_config,
    extract_preset_config,
    load_config_file,
    parse_arguments,
    print_presets,
    resolve_download_path,
    save_config_file,
)
from .crypto import init_session_keys, warn_plaintext_keyring
from .definitions import DEFAULT_DOWNLOAD_PATH, MANIFEST_FILENAME, PRESETS, USER_CONFIG_FILENAME
from .execution import check_free_space, execute_download_session
from .inventory import DryRunInventory
from .inventory_cache import (
    InventoryTreeBuilder,
    load_inventory_cache,
    resolve_inventory_cache_path,
    save_inventory_cache,
)
from .inventory_scan import scan_drive_inventory
from .photos_executor import run_photos_session
from .privacy import redact_apple_id
from .presentation import Colors, format_path_for_display
from .reporting import print_dry_run_inventory_summary
from .selector import run_inventory_selector
from .session import PyiCloudService, authenticate_session, cleanup_session_files, inspect_auth_status
from .state import DirectoryCache, DownloadManifest, DownloadStats, ShutdownHandler, StructuredLogger, StructuredLogger
from .wizard import prompt_download_mode_after_auth, run_main_menu, run_setup_wizard


def format_display_config(config: Dict[str, Any], path_keys: Any) -> Dict[str, Any]:
    """Apply display-only path redaction to selected config fields."""
    return {
        key: (
            redact_apple_id(value)
            if key == "apple_id" and isinstance(value, str)
            else
            [format_path_for_display(item) if isinstance(item, str) else item for item in value]
            if key in path_keys and isinstance(value, list)
            else format_path_for_display(value)
            if key in path_keys and isinstance(value, str) and value
            else value
        )
        for key, value in config.items()
    }


def _migrate_config_file(config: Dict[str, Any]) -> None:
    """Upgrade legacy config-file keys to current equivalents (in-place).

    Handles ``save_login_info`` → ``save_apple_id`` + ``save_2fa_session``
    so that old ``--config`` files work correctly without the wizard.
    """
    if "save_login_info" in config:
        if config.pop("save_login_info"):
            config.setdefault("save_apple_id", True)
            config.setdefault("save_2fa_session", True)


def _main_impl(
    *,
    parse_arguments_func: Callable[[], Any] = parse_arguments,
    run_setup_wizard_func: Callable[[], Dict[str, Any]] = run_main_menu,
    save_config_file_func: Callable[[str, Dict[str, Any]], None] = save_config_file,
    check_free_space_func: Callable[[str, float], None] = check_free_space,
    pyicloud_service_cls: Any = PyiCloudService,
    manifest_cls: Type[DownloadManifest] = DownloadManifest,
    getpass_func: Callable[[str], str] = getpass,
    input_func: Callable[[str], str] = input,
    inspect_auth_status_func: Any = None,
) -> None:
    """Handle argument resolution, authentication, and workflow orchestration."""
    args = parse_arguments_func()

    if getattr(args, "list_presets", False):
        print_presets()
        raise SystemExit(0)

    if getattr(args, "no_color", False):
        Colors.disable()

    warn_plaintext_keyring()

    _sig_keys = [
        "config", "preset", "save_config", "wizard", "dry_run",
        "session_dir", "china_mainland", "use_keyring", "store_in_keyring",
        "include", "exclude", "max_items", "max_depth", "inventory_cache",
        "build_inventory_cache", "refresh_inventory_cache", "select_from_cache", "source",
    ]
    significant_args = [getattr(args, k, None) for k in _sig_keys] + [
        getattr(args, "auth_status", False),
        getattr(args, "show_config", False),
        getattr(args, "destination", DEFAULT_DOWNLOAD_PATH) != DEFAULT_DOWNLOAD_PATH,
    ]
    auto_wizard = not any(significant_args)

    wizard_config: Dict[str, Any] = {}
    if getattr(args, "wizard", False) or auto_wizard:
        if auto_wizard:
            print(f"{Colors.CYAN}Running in interactive mode...{Colors.RESET}")
            print(f"{Colors.DIM}(Use --help to see command-line options)\n{Colors.RESET}")
        wizard_config = run_setup_wizard_func()

    file_config: Dict[str, Any] = {}
    if getattr(args, "config", None):
        file_config = load_config_file(args.config)
        _migrate_config_file(file_config)

    preset_config = extract_preset_config(args)
    if getattr(args, "preset", None):
        preset = PRESETS[args.preset]
        print(f"{Colors.CYAN}🎯 Preset:{Colors.RESET} {Colors.BOLD}{preset['name']}{Colors.RESET}")
        print(f"   {preset['description']}\n")

    if getattr(args, "save_config", None):
        save_config_file_func(args.save_config, build_save_config(args))
        print("Configuration saved. Exiting.")
        raise SystemExit(0)

    config = build_runtime_config(args, wizard_config, preset_config, file_config)
    if inspect_auth_status_func is None:
        inspect_auth_status_func = inspect_auth_status

    if getattr(args, "auth_status", False):
        auth_status = inspect_auth_status_func(
            wizard_config,
            config,
            service_class=pyicloud_service_cls,
            getpass_func=getpass_func,
        )
        print(
            json.dumps(
                format_display_config(
                    auth_status,
                    {"session_dir", "session_path", "cookiejar_path"},
                ),
                indent=2,
            )
        )
        raise SystemExit(0)

    download_path = resolve_download_path(args, wizard_config, preset_config, file_config)
    config["inventory_cache"] = resolve_inventory_cache_path(download_path, config.get("inventory_cache"))
    file_filter, include_patterns, exclude_patterns, min_size, max_size = build_filter_context(
        args,
        wizard_config,
        preset_config,
        file_config,
        selection_root=download_path,
    )

    if getattr(args, "show_config", False):
        resolved_config = {
            "destination": download_path,
            "retries": config["max_retries"],
            "timeout": config["timeout"],
            "chunk_size": config["chunk_size"],
            "min_free_space": config["min_free_space"],
            "workers": config["workers"],
            "sequential": config["sequential"],
            "resume": config["resume"],
            "dry_run": config["dry_run"],
            "progress": config["progress"],
            "verbose": config["verbose"],
            "session_dir": config["session_dir"],
            "save_password": config["use_keyring"] or config["store_password_in_keyring"],
            "china_mainland": config["china_mainland"],
            "include": include_patterns,
            "exclude": exclude_patterns,
            "min_size": min_size,
            "max_size": max_size,
            "max_depth": config["max_depth"],
            "max_items": config["max_items"],
            "inventory_cache": config["inventory_cache"],
            "build_inventory_cache": config["build_inventory_cache"],
            "refresh_inventory_cache": config["refresh_inventory_cache"],
            "select_from_cache": config["select_from_cache"],
            "selection_mode": config["selection_mode"],
            "log": getattr(args, "log", None),
            "log_level": config["log_level"],
            "config": getattr(args, "config", None),
            "preset": getattr(args, "preset", None),
        }
        print(
            json.dumps(
                format_display_config(
                    resolved_config,
                    {"destination", "session_dir", "log", "config", "include", "exclude"},
                ),
                indent=2,
            )
        )
        raise SystemExit(0)

    log_level = getattr(logging, config["log_level"])
    logging.basicConfig(level=log_level, format="%(asctime)s - %(levelname)s - %(message)s")

    if not os.path.exists(download_path):
        os.makedirs(download_path, exist_ok=True)
        os.chmod(download_path, 0o700)

    _manifest_key, _log_key, _session_key = init_session_keys()

    api = authenticate_session(
        wizard_config,
        config,
        service_class=pyicloud_service_cls,
        getpass_func=getpass_func,
        session_key=_session_key,
    )

    if wizard_config.get("save_apple_id") and wizard_config.get("_apple_id"):
        try:
            saved = load_config_file(USER_CONFIG_FILENAME) if os.path.exists(USER_CONFIG_FILENAME) else {}
            saved["saved_apple_id"] = wizard_config["_apple_id"]
            save_config_file_func(USER_CONFIG_FILENAME, saved)
        except Exception as exc:
            print(f"Warning: Could not save Apple ID for next run ({exc}).")

    if wizard_config.get("_from_wizard"):
        prompt_download_mode_after_auth(config, input_func=input_func)
        config = build_runtime_config(args, config, preset_config, file_config)
        file_filter, include_patterns, exclude_patterns, min_size, max_size = build_filter_context(
            args,
            config,
            preset_config,
            file_config,
            selection_root=download_path,
        )

    if wizard_config.get("_from_wizard") and config.get("dry_run"):
        print(f"{Colors.GREEN}✓{Colors.RESET} Preview mode enabled from saved preferences\n")

    needs_download_space = not config["build_inventory_cache"] or config["select_from_cache"]
    if needs_download_space:
        check_free_space_func(download_path, config["min_free_space"])

    if config.get("source") == "photos-library":
        photos_manifest = None
        if config["resume"] and not config["dry_run"]:
            manifest_path = os.path.join(download_path, MANIFEST_FILENAME)
            photos_manifest = manifest_cls(manifest_path, encryption_key=_manifest_key)
        photos_log_path = getattr(args, "log", None)
        photos_logger = StructuredLogger(
            photos_log_path, base_path=download_path, encryption_key=_log_key
        ) if photos_log_path else None
        photos_stats = DownloadStats()
        photos_stats.start()
        photos_failures: list[str] = []
        if photos_logger:
            photos_logger.log(
                "session_start",
                source="photos-library",
                scope=config.get("photos_scope", "all"),
            )
        run_photos_session(
            api,
            config,
            download_path,
            photos_failures,
            manifest=photos_manifest,
            stats=photos_stats,
            logger=photos_logger,
        )
        photos_stats.finish()
        summary = photos_stats.get_summary()
        if photos_logger:
            photos_logger.log("session_end", summary=summary, failures_count=len(photos_failures))
        if photos_failures:
            print(
                f"{Colors.YELLOW}{len(photos_failures)} file(s) failed to download.{Colors.RESET}"
            )
        print(
            f"\n{Colors.GREEN}Session complete.{Colors.RESET} "
            f"{summary['files_completed']} downloaded, "
            f"{summary['files_skipped']} skipped, "
            f"{summary['files_failed']} failed."
        )
        if wizard_config and not wizard_config.get("save_2fa_session", False):
            cleanup_session_files(config)
        raise SystemExit(0)

    cache_path = config["inventory_cache"]
    should_refresh_cache = bool(config["refresh_inventory_cache"] or config["build_inventory_cache"])
    if config["select_from_cache"] and not should_refresh_cache and not os.path.exists(cache_path):
        print(f"{Colors.CYAN}Inventory cache not found. Building it now...{Colors.RESET}")
        should_refresh_cache = True

    if should_refresh_cache:
        print("\n--- Scanning iCloud Drive inventory ---")
        inventory = DryRunInventory(max_depth=config.get("max_depth"), max_items=config.get("max_items"))
        inventory_stats = DownloadStats()
        inventory_stats.start()
        inventory_failures: list[str] = []
        dir_cache = DirectoryCache()
        shutdown_handler = ShutdownHandler()
        tree_builder = InventoryTreeBuilder(download_path)
        top_level_items = api.drive.dir()
        if not top_level_items:
            print("Could not find any files or folders in your iCloud Drive.")
            raise SystemExit(1)
        scan_drive_inventory(
            api,
            top_level_items,
            download_path,
            inventory_failures,
            config,
            dir_cache,
            inventory,
            file_filter,
            inventory_stats,
            shutdown_handler,
            tree_builder=tree_builder,
        )
        inventory_stats.finish()
        cache_payload = tree_builder.build_payload(inventory, config, len(top_level_items))
        save_inventory_cache(cache_path, cache_payload)
        print(f"{Colors.GREEN}✓{Colors.RESET} Inventory cache saved to: {format_path_for_display(cache_path)}")
        print_dry_run_inventory_summary(inventory, config)
        if inventory_failures:
            print(f"{Colors.YELLOW}Inventory scan completed with {len(inventory_failures)} warning(s).{Colors.RESET}")
        if config["build_inventory_cache"] and not config["select_from_cache"]:
            raise SystemExit(0)

    if config["select_from_cache"]:
        cache_payload = load_inventory_cache(cache_path)
        selection = run_inventory_selector(cache_payload, config["selection_mode"])
        if selection is None:
            print(f"{Colors.YELLOW}Selection cancelled. Exiting without downloading.{Colors.RESET}")
            raise SystemExit(0)
        config["selection_summary"] = selection["summary"]
        file_filter, include_patterns, exclude_patterns, min_size, max_size = build_filter_context(
            args,
            wizard_config,
            preset_config,
            file_config,
            selection_root=download_path,
            selected_files=sorted(selection["selected_files"]),
            selected_folders=sorted(selection["selected_folders"]),
        )

    execute_download_session(
        api,
        args,
        config,
        file_filter,
        download_path,
        include_patterns,
        exclude_patterns,
        min_size,
        max_size,
        manifest_cls=manifest_cls,
        manifest_key=_manifest_key,
        log_key=_log_key,
    )

    if wizard_config and not wizard_config.get("save_2fa_session", False):
        cleanup_session_files(config)


def main(
    *,
    parse_arguments_func: Callable[[], Any] = parse_arguments,
    run_setup_wizard_func: Callable[[], Dict[str, Any]] = run_main_menu,
    save_config_file_func: Callable[[str, Dict[str, Any]], None] = save_config_file,
    check_free_space_func: Callable[[str, float], None] = check_free_space,
    pyicloud_service_cls: Any = PyiCloudService,
    manifest_cls: Type[DownloadManifest] = DownloadManifest,
    getpass_func: Callable[[str], str] = getpass,
    input_func: Callable[[str], str] = input,
    inspect_auth_status_func: Any = None,
) -> None:
    """Handle argument resolution, authentication, and workflow orchestration."""
    try:
        _main_impl(
            parse_arguments_func=parse_arguments_func,
            run_setup_wizard_func=run_setup_wizard_func,
            save_config_file_func=save_config_file_func,
            check_free_space_func=check_free_space_func,
            pyicloud_service_cls=pyicloud_service_cls,
            manifest_cls=manifest_cls,
            getpass_func=getpass_func,
            input_func=input_func,
            inspect_auth_status_func=inspect_auth_status_func,
        )
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Cancelled by user.{Colors.RESET}")
        raise SystemExit(130)