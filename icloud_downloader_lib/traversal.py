import os
from typing import Any, Dict, List, Optional, Tuple

from .filters import FileFilter, ensure_directory, sanitize_name, set_file_permissions, validate_path_safety
from .inventory import DryRunInventory
from .presentation import format_path_for_display
from .privacy import sanitize_upstream_error_text
from .state import DirectoryCache, DownloadManifest, DownloadStats, ShutdownHandler, StructuredLogger
from .transfer import download_file

CollectedDownloadTask = Tuple[Any, str, str, Dict[str, Any], Optional[DownloadManifest]]


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
    """Recursively download folders and files."""
    if shutdown_handler and shutdown_handler.should_stop():
        print(f"Skipping '{node.name}' due to shutdown request")
        return

    if max_depth is not None and depth >= max_depth:
        if config.get("verbose"):
            print(f"Skipping '{node.name}' (max depth {max_depth} reached)")
        return

    try:
        validate_path_safety(local_path, root_path)
    except ValueError as error:
        msg = f"Path validation failed for '{format_path_for_display(local_path)}': {error}"
        failures.append(msg)
        print(msg)
        return

    if not os.path.exists(local_path):
        print(f"Creating directory: {format_path_for_display(local_path)}")
    ensure_directory(local_path, root_path, 0o700)

    cache_key = f"{node.name}_{id(node)}"
    child_item_names = dir_cache.get(cache_key) if dir_cache else None

    if child_item_names is None:
        try:
            child_item_names = node.dir()
            if dir_cache:
                dir_cache.set(cache_key, child_item_names)
        except Exception as error:
            msg = f"Could not list contents for '{node.name}', skipping. Error: {sanitize_upstream_error_text(str(error))}"
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
                    if file_filter and not file_filter.should_traverse_directory(child_local_path):
                        continue
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
                    if shutdown_handler and shutdown_handler.should_stop():
                        break
                    if config.get("max_items") and stats and stats.files_total >= config["max_items"]:
                        if config.get("verbose"):
                            print(f"Max items limit ({config['max_items']}) reached")
                        break
                    if not dry_run and stats:
                        _size = getattr(item, "size", None) if hasattr(item, "size") else None
                        _include = not file_filter or file_filter.should_include(child_local_path, size=_size)
                        if _include and not (
                            manifest and manifest.is_complete(child_local_path) and os.path.exists(child_local_path)
                        ):
                            stats.add_file(int(_size or 0))
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
                    if os.path.exists(child_local_path):
                        set_file_permissions(child_local_path, root_path, 0o600)
            except Exception as error:
                failures.append(f"Item '{item_name}' in folder '{node.name}': {sanitize_upstream_error_text(str(error))}")
                print(f"    -> FAILED to process '{item_name}'. Error: {sanitize_upstream_error_text(str(error))}")
    else:
        print(f"Folder '{node.name}' is empty.")


def collect_download_tasks(
    node: Any,
    local_path: str,
    config: Dict[str, Any],
    root_path: str,
    manifest: Optional[DownloadManifest],
    dir_cache: Optional[DirectoryCache],
    tasks_list: List[CollectedDownloadTask],
    failures: List[str],
    file_filter: Optional[FileFilter] = None,
    stats: Optional[DownloadStats] = None,
    shutdown_handler: Optional[ShutdownHandler] = None,
    depth: int = 0,
    max_depth: Optional[int] = None,
    collect_tasks: bool = True,
    inventory: Optional[DryRunInventory] = None,
) -> None:
    """Recursively collect all download tasks without downloading."""
    if shutdown_handler and shutdown_handler.should_stop():
        return

    if max_depth is not None and depth >= max_depth:
        return

    if config.get("max_items") and stats and stats.files_total >= config["max_items"]:
        return

    try:
        validate_path_safety(local_path, root_path)
    except ValueError as error:
        msg = f"Path validation failed for '{format_path_for_display(local_path)}': {error}"
        failures.append(msg)
        print(msg)
        return

    if inventory:
        inventory.record_folder(level=depth + 1)

    cache_key = f"{node.name}_{id(node)}"
    child_item_names = dir_cache.get(cache_key) if dir_cache else None

    if child_item_names is None:
        try:
            child_item_names = node.dir()
            if dir_cache:
                dir_cache.set(cache_key, child_item_names)
        except Exception as error:
            msg = f"Could not list contents for '{node.name}', skipping. Error: {sanitize_upstream_error_text(str(error))}"
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
                    if file_filter and not file_filter.should_traverse_directory(child_local_path):
                        continue
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
                        collect_tasks,
                        inventory,
                    )
                elif item.type == "file":
                    if shutdown_handler and shutdown_handler.should_stop():
                        break
                    if config.get("max_items") and stats and stats.files_total >= config["max_items"]:
                        break

                    size = getattr(item, "size", None) if hasattr(item, "size") else None
                    should_include = True
                    if file_filter:
                        should_include = file_filter.should_include(child_local_path, size=size)

                    if inventory:
                        inventory.record_file(child_local_path, size, included=should_include, level=depth + 2)

                    if should_include:
                        if not (
                            manifest
                            and manifest.is_complete(child_local_path)
                            and os.path.exists(child_local_path)
                        ):
                            size = getattr(item, "size", 0) if hasattr(item, "size") else 0
                            if stats:
                                stats.add_file(size)
                            if collect_tasks:
                                tasks_list.append((item, child_local_path, item_name, config, manifest))
            except Exception as error:
                failures.append(f"Item '{item_name}' in folder '{node.name}': {sanitize_upstream_error_text(str(error))}")
                print(f"    -> FAILED to process '{item_name}'. Error: {sanitize_upstream_error_text(str(error))}")