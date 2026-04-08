import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Type

from .definitions import MANIFEST_FILENAME
from .filters import FileFilter, sanitize_name, set_file_permissions, validate_path_safety
from .inventory import DryRunInventory, build_log_config, estimate_download_size
from .inventory_scan import scan_drive_inventory
from .presentation import Colors, confirm_download, format_path_for_display
from .reporting import print_dry_run_inventory_summary, print_session_summary, print_startup_banner
from .state import DirectoryCache, DownloadManifest, DownloadStats, ShutdownHandler, StructuredLogger
from .transfer import DownloadWorkerTask, download_file, download_worker
from .traversal import CollectedDownloadTask, collect_download_tasks, download_node

try:
    from tqdm import tqdm  # type: ignore[import-untyped]

    TQDM_AVAILABLE = True
except ImportError:
    tqdm = None
    TQDM_AVAILABLE = False

def resolve_local_item_path(item_name: str, download_path: str, failures: List[str]) -> Optional[str]:
    """Resolve and validate a local target path for a top-level item."""
    safe_name = sanitize_name(item_name)
    local_item_path = os.path.join(download_path, safe_name)
    try:
        return validate_path_safety(local_item_path, download_path)
    except ValueError as error:
        msg = f"Path validation failed for '{format_path_for_display(local_item_path)}': {error}"
        failures.append(msg)
        print(msg)
        return None


def check_free_space(path: str, min_gb: float) -> None:
    """Check if there's enough free space at the target path."""
    stat = shutil.disk_usage(path if os.path.exists(path) else os.path.dirname(path))
    free_gb = stat.free / (1024**3)

    if free_gb < min_gb:
        print(f"{Colors.YELLOW}⚠️  WARNING: Low disk space!{Colors.RESET}\n"
              f"  Available: {Colors.RED}{free_gb:.2f} GB{Colors.RESET}\n"
              f"  Required: {Colors.GREEN}{min_gb:.2f} GB{Colors.RESET}\n"
              f"\n{Colors.YELLOW}💡 Tip: Use --min-free-space to adjust the threshold{Colors.RESET}")
        response = input("\nContinue anyway? [y/N]: ").strip().lower()
        if response not in ("yes", "y"):
            print(f"{Colors.RED}Aborted by user.{Colors.RESET}")
            sys.exit(0)
    else:
        print(f"{Colors.GREEN}✓{Colors.RESET} Free space available: {Colors.CYAN}{free_gb:.1f} GB{Colors.RESET}")


def process_sequential_downloads(
    api: Any,
    top_level_items: List[str],
    download_path: str,
    failures: List[str],
    config: Dict[str, Any],
    manifest: Optional[DownloadManifest],
    dir_cache: DirectoryCache,
    file_filter: FileFilter,
    stats: DownloadStats,
    logger: Optional[StructuredLogger],
    shutdown_handler: ShutdownHandler,
) -> None:
    """Run the sequential folder and file processing flow."""
    for item_name in top_level_items:
        if shutdown_handler.should_stop():
            print("\nStopping due to shutdown request...")
            break

        item = api.drive[item_name]
        local_item_path = resolve_local_item_path(item_name, download_path, failures)
        if local_item_path is None:
            continue

        if item.type == "folder":
            if config.get("verbose"): print(f"\n--- Processing folder: '{item_name}' ---")
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
            if not config["dry_run"] and stats:
                _size = getattr(item, "size", None) if hasattr(item, "size") else None
                _include = not file_filter or file_filter.should_include(local_item_path, size=_size)
                if _include and not (
                    manifest and manifest.is_complete(local_item_path) and os.path.exists(local_item_path)
                ):
                    stats.add_file(int(_size or 0))
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
            if os.path.exists(local_item_path) and not config["dry_run"]:
                set_file_permissions(local_item_path, download_path, 0o600)


def collect_top_level_tasks(
    api: Any,
    top_level_items: List[str],
    download_path: str,
    failures: List[str],
    config: Dict[str, Any],
    manifest: Optional[DownloadManifest],
    dir_cache: DirectoryCache,
    file_filter: FileFilter,
    stats: DownloadStats,
    shutdown_handler: ShutdownHandler,
    collect_tasks: bool = True,
    inventory: Optional[DryRunInventory] = None,
) -> List[CollectedDownloadTask]:
    """Collect file download tasks for concurrent execution."""
    tasks: List[CollectedDownloadTask] = []

    for item_name in top_level_items:
        if shutdown_handler.should_stop():
            print("\nStopping task collection due to shutdown request...")
            break

        item = api.drive[item_name]
        local_item_path = resolve_local_item_path(item_name, download_path, failures)
        if local_item_path is None:
            continue

        if inventory:
            if item.type == "folder":
                inventory.record_root_folder()
            elif item.type == "file":
                inventory.record_root_file()

        if item.type == "folder":
            if config.get("max_items") and stats.files_total >= config["max_items"]:
                continue
            if config.get("verbose") and not config.get("dry_run"):
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
                collect_tasks,
                inventory,
            )
        elif item.type == "file":
            if config.get("max_items") and stats.files_total >= config["max_items"]:
                continue

            size = getattr(item, "size", None) if hasattr(item, "size") else None
            should_include = True
            if file_filter:
                should_include = file_filter.should_include(local_item_path, size=size)

            if inventory:
                inventory.record_file(local_item_path, size, included=should_include, level=1)

            if should_include:
                if not (manifest and manifest.is_complete(local_item_path) and os.path.exists(local_item_path)):
                    stats.add_file(int(size or 0))
                    if collect_tasks:
                        tasks.append((item, local_item_path, item_name, config, manifest))

    return tasks


def process_concurrent_downloads(
    tasks: List[CollectedDownloadTask],
    failures: List[str],
    config: Dict[str, Any],
    file_filter: FileFilter,
    stats: DownloadStats,
    logger: Optional[StructuredLogger],
    shutdown_handler: ShutdownHandler,
) -> None:
    """Run concurrent downloads for the collected tasks."""
    action = "Previewing" if config["dry_run"] else "Downloading"
    print(f"\n--- {action} {len(tasks)} files with {config['workers']} workers ---")

    if not tasks:
        print("No files to download (all complete or filtered out).")
        return

    pbar = None
    if TQDM_AVAILABLE and config["progress"] and not config["dry_run"]:
        pbar = tqdm(total=len(tasks), desc="Downloading", unit="file")

    extended_tasks: List[DownloadWorkerTask] = [
        (*task, file_filter, stats, logger, config["dry_run"], pbar)
        for task in tasks
    ]

    with ThreadPoolExecutor(max_workers=config["workers"]) as executor:
        future_to_task = {executor.submit(download_worker, task): task for task in extended_tasks}
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

            task = future_to_task[future]
            if os.path.exists(task[1]) and not config["dry_run"]:
                set_file_permissions(task[1], str(config.get("download_root") or os.path.dirname(task[1]) or "."), 0o600)

    if pbar:
        pbar.close()


def execute_download_session(
    api: Any,
    args: Any,
    config: Dict[str, Any],
    file_filter: FileFilter,
    download_path: str,
    include_patterns: List[str],
    exclude_patterns: List[str],
    min_size: Optional[int],
    max_size: Optional[int],
    *,
    manifest_cls: Type[DownloadManifest] = DownloadManifest,
    manifest_key: Optional[bytes] = None,
    log_key: Optional[bytes] = None,
) -> None:
    """Execute the download workflow after configuration and authentication."""
    log_path = getattr(args, "log", None)
    skip_confirm = getattr(args, "skip_confirm", False)

    print_startup_banner(
        download_path,
        config,
        include_patterns,
        exclude_patterns,
        min_size,
        max_size,
        log_path,
        not config["resume"],
    )

    manifest = None
    if config["resume"] and not config["dry_run"]:
        manifest_path = os.path.join(download_path, MANIFEST_FILENAME)
        manifest = manifest_cls(manifest_path, encryption_key=manifest_key)
        print(f"Manifest: {format_path_for_display(manifest_path)}")
    dir_cache = DirectoryCache()
    stats = DownloadStats()
    logger = StructuredLogger(log_path, base_path=download_path, encryption_key=log_key) if log_path else None
    stats.start()
    config["download_root"] = download_path

    if logger:
        logger.log(
            "session_start",
            config=build_log_config(config),
            filters={
                "include_count": len(include_patterns) if include_patterns else 0,
                "exclude_count": len(exclude_patterns) if exclude_patterns else 0,
                "min_size": min_size,
                "max_size": max_size,
                "max_depth": config.get("max_depth"),
                "max_items": config.get("max_items"),
            },
        )

    print(f"\nAll files will be {'previewed in' if config['dry_run'] else 'saved to'}: {format_path_for_display(download_path)}\n")

    print("\nAccessing iCloud Drive...")

    failures: List[str] = []
    top_level_items = api.drive.dir()
    if not top_level_items:
        print("Could not find any files or folders in your iCloud Drive.")
        raise SystemExit(1)

    print(f"Found {len(top_level_items)} top-level items to process.")

    if not config["dry_run"] and not skip_confirm:
        print(f"\n{Colors.CYAN}Analyzing download size...{Colors.RESET}")
        selection_summary = config.get("selection_summary")
        if isinstance(selection_summary, dict):
            stats_preview = {
                "estimated_files": int(selection_summary.get("files", 0)),
                "estimated_size": int(selection_summary.get("bytes", 0)),
            }
        else:
            stats_preview = estimate_download_size(api, top_level_items)
        if stats_preview["estimated_files"] > 0 and not confirm_download(stats_preview):
            print(f"{Colors.YELLOW}Download cancelled by user.{Colors.RESET}")
            raise SystemExit(0)

    shutdown_handler = ShutdownHandler()

    if config["dry_run"]:
        print("\n--- Scanning iCloud Drive inventory ---")
        inventory = DryRunInventory(max_depth=config.get("max_depth"), max_items=config.get("max_items"))
        scan_drive_inventory(
            api,
            top_level_items,
            download_path,
            failures,
            config,
            dir_cache,
            inventory,
            file_filter,
            stats,
            shutdown_handler,
        )
        stats.finish()
        print_dry_run_inventory_summary(inventory, config)
        summary = stats.get_summary()
        print_session_summary(summary, failures, True, logger, shutdown_handler)
        return

    if config["sequential"]:
        process_sequential_downloads(
            api,
            top_level_items,
            download_path,
            failures,
            config,
            manifest,
            dir_cache,
            file_filter,
            stats,
            logger,
            shutdown_handler,
        )
    else:
        print("\n--- Collecting download tasks ---")
        tasks = collect_top_level_tasks(
            api,
            top_level_items,
            download_path,
            failures,
            config,
            manifest,
            dir_cache,
            file_filter,
            stats,
            shutdown_handler,
        )
        process_concurrent_downloads(
            tasks,
            failures,
            config,
            file_filter,
            stats,
            logger,
            shutdown_handler,
        )

    stats.finish()
    summary = stats.get_summary()
    print_session_summary(summary, failures, config["dry_run"], logger, shutdown_handler)