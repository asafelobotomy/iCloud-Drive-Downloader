from typing import Any, Callable, Dict

from .definitions import DEFAULT_DOWNLOAD_PATH, DEFAULT_MAX_WORKERS, PRESETS
from .presentation import Colors, format_path_for_display

MODE_KEYS = {
    "include",
    "exclude",
    "prompt_for_download_mode",
    "refresh_inventory_cache",
    "select_from_cache",
    "selection_mode",
    "source",
    "photos_scope",
    "photos_album",
    "photos_month",
    "photos_after",
    "photos_before",
    "max_depth",
    "max_items",
}

MODE_LABELS = {
    "1": "Everything from iCloud Drive",
    "2": "Browse iCloud Drive folders",
    "3": "Explore iCloud Drive folders and files",
    "4": "Documents from iCloud Drive",
    "5": "Quick test download",
    "6": "Custom filters",
    "7": "All photos and videos",
    "8": "Photos only",
    "9": "Videos only",
    "10": "Photos by album",
    "11": "Photos by month",
}


def current_download_choice(config: Dict[str, Any]) -> str:
    """Infer the configured download mode from saved preferences."""
    if config.get("source") == "photos-library":
        scope = str(config.get("photos_scope") or "all")
        return {
            "all": "7",
            "photos": "8",
            "videos": "9",
            "by-album": "10",
            "by_month": "11",
            "by-month": "11",
        }.get(scope, "7")
    if config.get("refresh_inventory_cache") and config.get("select_from_cache"):
        if config.get("selection_mode") == "folders":
            return "2"
        return "3"
    if config.get("include") == PRESETS["documents"]["include"] and not config.get("exclude"):
        return "4"
    if (
        config.get("max_items") == PRESETS["quick-test"]["max_items"]
        and config.get("max_depth") == PRESETS["quick-test"]["max_depth"]
    ):
        return "5"
    if config.get("include") or config.get("exclude"):
        return "6"
    return "1"


def download_mode_label(config: Dict[str, Any]) -> str:
    """Return a short human-readable label for the active download mode."""
    return MODE_LABELS[current_download_choice(config)]


def clear_download_preferences(config: Dict[str, Any]) -> None:
    """Remove mode-specific settings before applying a new download mode."""
    for key in MODE_KEYS:
        config.pop(key, None)


def _print_download_mode_options() -> None:
    """Render grouped download-mode options for Drive and Photos."""
    print("  iCloud Drive")
    print(f"  1. ☁️   Everything     — download all iCloud Drive files")
    print(f"  2. 📁  By directory    — pick folders after scanning Drive")
    print(f"  3. 🔍  Explore Drive   — pick folders and files after scanning")
    print(f"  4. 📄  Documents       — download common document files")
    print(f"  5. 🧪  Quick test      — first 50 files, 2 levels deep")
    print(f"  6. ⚙️   Custom filters  — set include and exclude patterns")
    print("\n  iCloud Photo Library")
    print(f"  7. 🖼️   All photos & videos — download the full library")
    print(f"  8. 📸  All photos          — photos only")
    print(f"  9. 🎬  All videos          — videos only")
    print(f" 10. 🗂️   By album            — choose one album")
    print(f" 11. 📅  By month            — choose one month")


def _apply_download_mode_choice(
    config: Dict[str, Any],
    choice: str,
    *,
    input_func: Callable[[str], str],
    enable_drive_selector: Callable[[Dict[str, Any]], None],
    enable_mixed_selector: Callable[[Dict[str, Any]], None],
    enable_photos_library: Callable[[Dict[str, Any], str], None],
    existing_include: list[str],
    existing_exclude: list[str],
) -> None:
    """Apply one menu choice to the runtime configuration."""
    clear_download_preferences(config)

    if choice == "2":
        enable_drive_selector(config)
    elif choice == "3":
        enable_mixed_selector(config)
    elif choice == "4":
        config.update(PRESETS["documents"])
    elif choice == "5":
        config.update(PRESETS["quick-test"])
    elif choice == "6":
        include_default = ",".join(existing_include)
        exclude_default = ",".join(existing_exclude)
        include = input_func(
            f"Include patterns [{include_default}]: " if include_default else "Include patterns [none]: "
        ).strip()
        exclude = input_func(
            f"Exclude patterns [{exclude_default}]: " if exclude_default else "Exclude patterns [none]: "
        ).strip()
        include_patterns = include_default if not include and include_default else include
        exclude_patterns = exclude_default if not exclude and exclude_default else exclude
        if include_patterns:
            config["include"] = [pattern.strip() for pattern in include_patterns.split(",") if pattern.strip()]
        if exclude_patterns:
            config["exclude"] = [pattern.strip() for pattern in exclude_patterns.split(",") if pattern.strip()]
    elif choice == "7":
        enable_photos_library(config, "all")
    elif choice == "8":
        enable_photos_library(config, "photos")
    elif choice == "9":
        enable_photos_library(config, "videos")
    elif choice == "10":
        enable_photos_library(config, "by-album")
    elif choice == "11":
        enable_photos_library(config, "by-month")


def configure_download_mode(
    config: Dict[str, Any],
    *,
    input_func: Callable[[str], str],
    enable_drive_selector: Callable[[Dict[str, Any]], None],
    enable_mixed_selector: Callable[[Dict[str, Any]], None],
    enable_photos_library: Callable[[Dict[str, Any], str], None],
    heading: str = "Choose what to download",
    result_label: str = "Download mode",
) -> bool:
    """Prompt for and apply the persistent download mode preference."""
    current_choice = current_download_choice(config)
    existing_include = list(config.get("include", []))
    existing_exclude = list(config.get("exclude", []))

    print(f"\n{Colors.BOLD}{heading}{Colors.RESET}")
    _print_download_mode_options()

    choice = input_func(f"\nEnter choice [{current_choice}]: ").strip() or current_choice
    if choice not in MODE_LABELS:
        print(f"{Colors.YELLOW}Please enter a number from 1 to 11{Colors.RESET}\n")
        return False

    _apply_download_mode_choice(
        config,
        choice,
        input_func=input_func,
        enable_drive_selector=enable_drive_selector,
        enable_mixed_selector=enable_mixed_selector,
        enable_photos_library=enable_photos_library,
        existing_include=existing_include,
        existing_exclude=existing_exclude,
    )

    print(f"{Colors.GREEN}✓{Colors.RESET} {result_label}: {download_mode_label(config)}\n")
    return True


def choose_download_mode_for_run(
    config: Dict[str, Any],
    *,
    input_func: Callable[[str], str],
    enable_drive_selector: Callable[[Dict[str, Any]], None],
    enable_mixed_selector: Callable[[Dict[str, Any]], None],
    enable_photos_library: Callable[[Dict[str, Any], str], None],
) -> None:
    """Show the run-time download mode menu after login."""
    print(f"{Colors.BOLD}Step 3: Choose what to download{Colors.RESET}")
    print("  Select an iCloud Drive or Photos option below.\n")

    selection_applied = False
    while not selection_applied:
        selection_applied = configure_download_mode(
            config,
            input_func=input_func,
            enable_drive_selector=enable_drive_selector,
            enable_mixed_selector=enable_mixed_selector,
            enable_photos_library=enable_photos_library,
            heading="Choose an option below:",
            result_label="Download mode",
        )


def print_current_preferences(config: Dict[str, Any], *, heading: str = "Step 3: Current preferences") -> None:
    """Print the saved preferences that will be used for this run."""
    print(f"{Colors.BOLD}{heading}{Colors.RESET}")
    print(f"  Download folder: {format_path_for_display(config.get('destination', DEFAULT_DOWNLOAD_PATH))}")
    print(f"  Download mode: {download_mode_label(config)}")
    print(f"  Concurrent downloads: {config.get('workers', DEFAULT_MAX_WORKERS)}")
    print(f"  Preview before downloading: {'Yes' if config.get('dry_run', False) else 'No'}")
    print(f"  Resume downloads: {'Yes' if config.get('resume', True) else 'No'}")
    if config.get("save_password") or config.get("use_keyring"):
        print("  System keyring: Enabled")
    if config.get("session_dir"):
        print(f"  Session directory: {format_path_for_display(config['session_dir'])}")
    if config.get("china_mainland"):
        print("  Apple China mainland endpoints: Enabled")
    print()