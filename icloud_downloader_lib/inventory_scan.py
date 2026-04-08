import os
from typing import Any, Dict, List, Optional

from .filters import FileFilter, sanitize_name, validate_path_safety
from .inventory import DryRunInventory
from .presentation import format_path_for_display
from .state import DirectoryCache, DownloadStats, ShutdownHandler

try:
    from tqdm import tqdm  # type: ignore[import-untyped]

    TQDM_AVAILABLE = True
except ImportError:
    tqdm = None
    TQDM_AVAILABLE = False


class InventoryScanProgress:
    """Render inventory progress without exposing file or folder names."""

    def __init__(self, total_root_items: int, enabled: bool) -> None:
        self.total_root_items = total_root_items
        self.enabled = enabled
        self.processed_root_items = 0
        self.progress_bar = None
        if self.enabled and TQDM_AVAILABLE:
            self.progress_bar = tqdm(total=total_root_items, desc="Scanning inventory", unit="root")

    def advance(self, inventory: DryRunInventory) -> None:
        if not self.enabled:
            return

        self.processed_root_items += 1
        if self.progress_bar is not None:
            self.progress_bar.update(1)
            return

        summary = inventory.snapshot()
        print(
            "Scanning inventory: "
            f"{self.processed_root_items}/{self.total_root_items} root items, "
            f"{summary['total_items']} items discovered"
        )

    def close(self) -> None:
        if self.progress_bar is not None:
            self.progress_bar.close()


def collect_inventory_metrics(
    node: Any,
    local_path: str,
    config: Dict[str, Any],
    root_path: str,
    dir_cache: Optional[DirectoryCache],
    failures: List[str],
    inventory: DryRunInventory,
    file_filter: Optional[FileFilter] = None,
    stats: Optional[DownloadStats] = None,
    shutdown_handler: Optional[ShutdownHandler] = None,
    level: int = 1,
    preview_enabled: bool = False,
    is_root: bool = False,
    tree_builder: Optional[Any] = None,
) -> None:
    """Traverse a folder tree for dry-run metrics without creating local files or directories."""
    if shutdown_handler and shutdown_handler.should_stop():
        return

    try:
        validate_path_safety(local_path, root_path)
    except ValueError as error:
        msg = f"Path validation failed for '{format_path_for_display(local_path)}': {error}"
        failures.append(msg)
        print(msg)
        return

    inventory.record_folder(level=level, preview=preview_enabled, is_root=is_root)

    cache_key = f"{node.name}_{id(node)}"
    child_item_names = dir_cache.get(cache_key) if dir_cache else None

    if child_item_names is None:
        try:
            child_item_names = node.dir()
            if dir_cache:
                dir_cache.set(cache_key, child_item_names)
        except Exception as error:
            msg = f"Could not list contents for '{node.name}', skipping. Error: {error}"
            failures.append(msg)
            print(msg)
            return

    if tree_builder:
        tree_builder.record_folder(
            local_path,
            getattr(node, "name", os.path.basename(local_path)),
            depth=level,
            child_count=len(child_item_names or []),
        )

    if not child_item_names:
        inventory.mark_empty_folder()
        return

    for item_name in child_item_names:
        if shutdown_handler and shutdown_handler.should_stop():
            break
        try:
            item = node[item_name]
            safe_name = sanitize_name(item_name)
            child_local_path = os.path.join(local_path, safe_name)
            child_level = level + 1

            if item.type == "folder":
                child_preview_enabled = (
                    preview_enabled
                    and inventory.preview_allows_folder(child_level)
                    and not inventory.preview_limit_reached()
                )
                collect_inventory_metrics(
                    item,
                    child_local_path,
                    config,
                    root_path,
                    dir_cache,
                    failures,
                    inventory,
                    file_filter,
                    stats,
                    shutdown_handler,
                    child_level,
                    child_preview_enabled,
                    tree_builder=tree_builder,
                )
            elif item.type == "file":
                size = getattr(item, "size", None) if hasattr(item, "size") else None
                should_include = True
                if file_filter:
                    should_include = file_filter.should_include(child_local_path, size=size)

                preview_file = (
                    preview_enabled
                    and inventory.preview_allows_file(child_level)
                    and not inventory.preview_limit_reached()
                )
                inventory.record_file(
                    child_local_path,
                    size,
                    included=should_include,
                    level=child_level,
                    preview=preview_file,
                )
                if tree_builder:
                    tree_builder.record_file(
                        child_local_path,
                        item_name,
                        size=size,
                        depth=child_level,
                        included=should_include,
                    )
                if preview_file and should_include and stats:
                    stats.add_file(int(size or 0))
        except Exception as error:
            failures.append(f"Item '{item_name}' in folder '{node.name}': {error}")
            print(f"    -> FAILED to process '{item_name}'. Error: {error}")


def scan_drive_inventory(
    api: Any,
    top_level_items: List[str],
    download_path: str,
    failures: List[str],
    config: Dict[str, Any],
    dir_cache: Optional[DirectoryCache],
    inventory: DryRunInventory,
    file_filter: Optional[FileFilter] = None,
    stats: Optional[DownloadStats] = None,
    shutdown_handler: Optional[ShutdownHandler] = None,
    tree_builder: Optional[Any] = None,
) -> None:
    """Collect full dry-run inventory metrics plus preview-scope counters for the current config."""
    progress = InventoryScanProgress(len(top_level_items), bool(config.get("progress", True)))
    try:
        for item_name in top_level_items:
            if shutdown_handler and shutdown_handler.should_stop():
                print("\nStopping inventory scan due to shutdown request...")
                break

            item = api.drive[item_name]
            safe_name = sanitize_name(item_name)
            local_item_path = os.path.join(download_path, safe_name)
            try:
                local_item_path = validate_path_safety(local_item_path, download_path)
            except ValueError as error:
                msg = f"Path validation failed for '{format_path_for_display(local_item_path)}': {error}"
                failures.append(msg)
                print(msg)
                progress.advance(inventory)
                continue

            if item.type == "folder":
                collect_inventory_metrics(
                    item,
                    local_item_path,
                    config,
                    download_path,
                    dir_cache,
                    failures,
                    inventory,
                    file_filter,
                    stats,
                    shutdown_handler,
                    level=1,
                    preview_enabled=inventory.preview_allows_folder(1),
                    is_root=True,
                    tree_builder=tree_builder,
                )
            elif item.type == "file":
                size = getattr(item, "size", None) if hasattr(item, "size") else None
                should_include = True
                if file_filter:
                    should_include = file_filter.should_include(local_item_path, size=size)
                preview_file = inventory.preview_allows_file(1) and not inventory.preview_limit_reached()
                inventory.record_file(
                    local_item_path,
                    size,
                    included=should_include,
                    level=1,
                    preview=preview_file,
                    is_root=True,
                )
                if tree_builder:
                    tree_builder.record_file(
                        local_item_path,
                        item_name,
                        size=size,
                        depth=1,
                        included=should_include,
                    )
                if preview_file and should_include and stats:
                    stats.add_file(int(size or 0))
            progress.advance(inventory)
    finally:
        progress.close()