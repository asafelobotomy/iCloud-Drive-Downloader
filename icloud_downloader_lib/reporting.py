from typing import Any, Dict, List, Optional

from .definitions import __version__
from .inventory import CATEGORY_ORDER, DryRunInventory
from .presentation import Colors, format_path_for_display, format_size, format_speed
from .privacy import sanitize_upstream_error_text
from .state import ShutdownHandler, StructuredLogger


def print_startup_banner(
    download_path: str,
    config: Dict[str, Any],
    include_patterns: List[str],
    exclude_patterns: List[str],
    min_size: Optional[int],
    max_size: Optional[int],
    log_path: Optional[str],
    no_resume: bool,
) -> None:
    """Print the resolved runtime configuration."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}   iCloud Drive Downloader v{__version__}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 60}{Colors.RESET}\n")

    print(f"{Colors.BOLD}Configuration:{Colors.RESET}")
    print(
        f"  {Colors.BOLD}Destination:{Colors.RESET} {Colors.CYAN}{format_path_for_display(download_path)}{Colors.RESET}"
    )
    print(
        f"  {Colors.BOLD}Workers:{Colors.RESET} {config['workers']} {'(sequential)' if config['sequential'] else '(concurrent)'}"
    )
    print(f"  {Colors.BOLD}Retries:{Colors.RESET} {config['max_retries']} | {Colors.BOLD}Timeout:{Colors.RESET} {config['timeout']}s")
    print(f"  {Colors.BOLD}Resume:{Colors.RESET} {'Disabled' if no_resume else 'Enabled'}")
    print(f"  {Colors.BOLD}Mode:{Colors.RESET} {'Preview only' if config['dry_run'] else 'Download'}")
    if config.get("max_depth"):
        print(f"  {Colors.BOLD}Max depth:{Colors.RESET} {config['max_depth']}")
    if config.get("max_items"):
        print(f"  {Colors.BOLD}Max items:{Colors.RESET} {config['max_items']}")
    if include_patterns:
        print(
            f"  {Colors.BOLD}Include:{Colors.RESET} "
            f"{Colors.GREEN}{', '.join(format_path_for_display(pattern) for pattern in include_patterns)}{Colors.RESET}"
        )
    if exclude_patterns:
        print(
            f"  {Colors.BOLD}Exclude:{Colors.RESET} "
            f"{Colors.RED}{', '.join(format_path_for_display(pattern) for pattern in exclude_patterns)}{Colors.RESET}"
        )
    if min_size:
        print(f"  {Colors.BOLD}Min size:{Colors.RESET} {format_size(min_size)}")
    if max_size:
        print(f"  {Colors.BOLD}Max size:{Colors.RESET} {format_size(max_size)}")
    if log_path:
        print(f"  {Colors.BOLD}Log file:{Colors.RESET} {format_path_for_display(log_path)}")
    print()


def print_session_summary(
    summary: Dict[str, Any],
    failures: List[str],
    dry_run: bool,
    logger: Optional[StructuredLogger],
    shutdown_handler: ShutdownHandler,
) -> None:
    """Print end-of-session statistics and failures."""
    if shutdown_handler.should_stop():
        print(f"\n{Colors.YELLOW}--- Shutdown requested. Session terminated early. ---{Colors.RESET}")
        print("Manifest and progress have been saved. Resume by running the script again.")
    elif dry_run:
        print(f"\n{Colors.CYAN}{Colors.BOLD}--- All done! Dry run complete. ---{Colors.RESET}")
    else:
        print(f"\n{Colors.GREEN}{Colors.BOLD}--- All done! Download complete. ---{Colors.RESET}")

    print("\nStatistics:")
    print(f"  Total files:  {summary['files_total']}")
    print(f"  {Colors.GREEN}✓ Completed:  {summary['files_completed']}{Colors.RESET}")
    if summary['files_skipped']:
        print(f"  {Colors.YELLOW}↷ Skipped:    {summary['files_skipped']}{Colors.RESET}")
    else:
        print(f"  Skipped:      {summary['files_skipped']}")
    if summary['files_failed']:
        print(f"  {Colors.RED}✗ Failed:     {summary['files_failed']}{Colors.RESET}")
    else:
        print(f"  Failed:       {summary['files_failed']}")

    if summary.get("throttle_events", 0) > 0:
        print(f"{Colors.YELLOW}  ⚠️  Rate limit events: {summary['throttle_events']}{Colors.RESET}")
        print(f"{Colors.YELLOW}     Next time, consider using fewer workers (e.g., --workers 1){Colors.RESET}")

    print(f"  Downloaded:   {Colors.CYAN}{format_size(summary['bytes_downloaded'])}{Colors.RESET}")
    print(f"  Elapsed time: {summary['elapsed_seconds']:.1f}s")

    if summary["elapsed_seconds"] > 0 and summary["bytes_downloaded"] > 0:
        print(f"  Avg speed:    {format_speed(summary['bytes_downloaded'] / summary['elapsed_seconds'])}")

    if logger:
        logger.log("session_end", summary=summary, failures_count=len(failures))

    if failures:
        print(f"\n{Colors.RED}Some items failed to download:{Colors.RESET}")
        for failure in failures:
            print(f"  {Colors.RED}✗{Colors.RESET} {sanitize_upstream_error_text(failure) or 'Download failed'}")
    elif not dry_run:
        print(f"\n{Colors.GREEN}✓ All items downloaded successfully.{Colors.RESET}")
    else:
        print("\nDry run completed.")


def print_dry_run_inventory_summary(inventory: DryRunInventory, config: Dict[str, Any]) -> None:
    """Print aggregate dry-run inventory metrics without exposing filenames."""
    summary = inventory.snapshot()
    category_labels = {
        "photos": "Photos",
        "videos": "Videos",
        "documents": "Documents",
        "audio": "Audio",
        "archives": "Archives",
        "other": "Other",
    }

    print("\nDry-run inventory summary:")
    print(
        f"  Root items: {summary['root_items']} "
        f"({summary['root_folders']} folders, {summary['root_files']} files)"
    )
    print(
        f"  Full inventory: {summary['total_items']} items "
        f"({summary['total_folders']} folders, {summary['total_files']} files)"
    )
    print(f"  Full data: {format_size(summary['total_bytes'])}")
    print(f"  Deepest item level: {summary['deepest_level']}")
    print(f"  Empty folders: {summary['empty_folders']}")
    print(
        f"  Media counts: {summary['category_counts']['photos']} photos, "
        f"{summary['category_counts']['videos']} videos"
    )
    print(
        f"  Matching current filters: {summary['matched_files']} files "
        f"({format_size(summary['matched_bytes'])})"
    )
    if summary["has_preview_limits"]:
        print(
            f"  Preview scope under current limits: {summary['preview_items']} items "
            f"({summary['preview_folders']} folders, {summary['preview_files']} files)"
        )
        print(
            f"  Would download under current limits: {summary['preview_matched_files']} files "
            f"({format_size(summary['preview_matched_bytes'])})"
        )
        print(
            f"  Preview limits: max_depth={config.get('max_depth', 'none')}, "
            f"max_items={config.get('max_items', 'none')}"
        )
        print("  Full totals above ignore the preview limits; the preview scope reflects the current settings.")

    print("  Storage breakdown:")
    total_bytes = max(summary["total_bytes"], 1)
    for category in CATEGORY_ORDER:
        if summary["category_counts"][category] == 0 and summary["category_bytes"][category] == 0:
            continue
        byte_share = (summary["category_bytes"][category] / total_bytes) * 100
        print(
            f"    {category_labels[category]}: {summary['category_counts'][category]} files, "
            f"{format_size(summary['category_bytes'][category])} ({byte_share:.1f}%)"
        )