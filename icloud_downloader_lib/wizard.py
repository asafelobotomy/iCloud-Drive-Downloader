import os
import sys
from getpass import getpass
from typing import Any, Callable, Dict, Optional

from .cli import load_config_file, save_config_file
from .definitions import DEFAULT_DOWNLOAD_PATH, DEFAULT_MAX_WORKERS, USER_CONFIG_FILENAME
from .privacy import redact_apple_id
from .session import cleanup_session_files
from .presentation import Colors, format_path_for_display
from .wizard_preferences import (
    clear_download_preferences,
    choose_download_mode_for_run,
    configure_download_mode,
    download_mode_label,
    print_current_preferences,
)

try:
    from pyicloud.utils import delete_password_in_keyring  # type: ignore[import-untyped]
except ImportError:
    delete_password_in_keyring = None


def prompt_yes_no(
    input_func: Callable[[str], str],
    prompt: str,
    *,
    default: bool,
) -> bool:
    """Prompt for a yes/no answer with a default."""
    raw_value = input_func(prompt).strip().lower()
    if not raw_value:
        return default
    return raw_value in {"y", "yes"}


def enable_drive_selector(config: Dict[str, Any], *, selection_mode: str) -> None:
    """Enable the cache-backed iCloud Drive selector for the wizard flow."""
    config["refresh_inventory_cache"] = True
    config["select_from_cache"] = True
    config["selection_mode"] = selection_mode


def enable_photos_library(config: Dict[str, Any], *, scope: str) -> None:
    """Set the Photos Library source and scope in the wizard config."""
    config["source"] = "photos-library"
    config["photos_scope"] = scope


def prompt_download_mode_after_auth(
    config: Dict[str, Any],
    *,
    input_func: Callable[[str], str] = input,
) -> None:
    """Prompt for the download mode after authentication succeeds."""
    choose_download_mode_for_run(
        config,
        input_func=input_func,
        enable_drive_selector=lambda updated_config: enable_drive_selector(updated_config, selection_mode="folders"),
        enable_mixed_selector=lambda updated_config: enable_drive_selector(updated_config, selection_mode="mixed"),
        enable_photos_library=lambda updated_config, scope: enable_photos_library(updated_config, scope=scope),
    )
    print_current_preferences(config, heading="Step 4: Current preferences")


def _load_user_config() -> Dict[str, Any]:
    """Load saved user preferences from the config file."""
    if os.path.exists(USER_CONFIG_FILENAME):
        return load_config_file(USER_CONFIG_FILENAME)
    return {}


def _save_user_config(config: Dict[str, Any]) -> None:
    """Save user preferences to the config file."""
    if not config:
        if os.path.exists(USER_CONFIG_FILENAME):
            os.remove(USER_CONFIG_FILENAME)
        return
    save_config_file(USER_CONFIG_FILENAME, config)


def _invalidate_remote_session(saved_config: Dict[str, Any]) -> None:
    """Best-effort server-side logout so Apple revokes the device trust."""
    from .session import PYICLOUD_AVAILABLE, resolve_service_options
    if not PYICLOUD_AVAILABLE:
        return
    apple_id = saved_config.get("saved_apple_id")
    if not apple_id:
        return
    try:
        from pyicloud import PyiCloudService  # type: ignore[import-untyped]
        svc_kwargs = resolve_service_options(saved_config)
        api = PyiCloudService(apple_id, None, authenticate=False, **svc_kwargs)
        if not hasattr(api, "logout"):
            return
        result = api.logout(keep_trusted=False, clear_local_session=True)
        if result.get("remote_logout_confirmed"):
            print("Remote session invalidated.")
        else:
            print("Remote logout was not confirmed — local data will still be cleared.")
    except Exception as exc:
        print(f"Warning: Remote session invalidation failed ({type(exc).__name__}). Local data will still be cleared.")


def _clear_all_user_data(saved_config: Dict[str, Any]) -> None:
    """Remove saved local auth state, config, and any stored password."""
    _invalidate_remote_session(saved_config)

    cleanup_session_files(saved_config)
    if saved_config.get("session_dir"):
        cleanup_session_files({})

    apple_id = saved_config.get("saved_apple_id")
    if apple_id and delete_password_in_keyring is not None:
        try:
            delete_password_in_keyring(apple_id)
        except Exception as exc:
            print(f"Warning: Could not clear the saved password from the system keyring ({exc}).")

    if os.path.exists(USER_CONFIG_FILENAME):
        os.remove(USER_CONFIG_FILENAME)


def _migrate_saved_config(config: Dict[str, Any]) -> None:
    """In-place migration of legacy config keys to current names."""
    # save_login_info used to control both email address and 2FA session persistence.
    # Split it into the two distinct keys introduced in the config restructure.
    if "save_login_info" in config:
        if config.pop("save_login_info"):
            config.setdefault("save_apple_id", True)
            config.setdefault("save_2fa_session", True)


def _initial_wizard_config(saved_config: Dict[str, Any]) -> Dict[str, Any]:
    """Copy saved preferences into the runtime wizard config."""
    config = {
        key: value
        for key, value in saved_config.items()
        if not key.startswith("_") and key != "saved_apple_id"
    }
    _migrate_saved_config(config)
    # Translate unified save_password key to internal runtime keys used by session.py
    if config.get("save_password"):
        config["use_keyring"] = True
        config["store_password_in_keyring"] = True
    clear_download_preferences(config)
    return config


def run_configure_menu(
    saved_config: Dict[str, Any],
    *,
    input_func: Callable[[str], str] = input,
) -> Optional[Dict[str, Any]]:
    """Configuration sub-menu for setting preferences."""
    config = dict(saved_config)
    _migrate_saved_config(config)
    clear_download_preferences(config)
    _original_save_2fa = config.get("save_2fa_session", False)

    while True:
        dest = format_path_for_display(config.get("destination", DEFAULT_DOWNLOAD_PATH))
        save_apple_id = config.get("save_apple_id", False)
        save_password = config.get("save_password", False)
        save_2fa = config.get("save_2fa_session", False)
        session_dir = config.get("session_dir")
        session_label = format_path_for_display(session_dir) if session_dir else "Default (~/.pyicloud)"
        china_mainland = config.get("china_mainland", False)
        workers = config.get("workers", DEFAULT_MAX_WORKERS)
        preview = config.get("dry_run", False)
        resume = config.get("resume", True)
        log_level = config.get("log_level", "INFO")

        print(f"\n{Colors.BOLD}⚙️  Configuration{Colors.RESET}\n")
        print(f"  {Colors.DIM}These settings are used every time you choose Start.{Colors.RESET}")
        print(f"  1. 📂  Download directory         [{dest}]")
        print(f"  2. 👤  Save Apple ID email         [{'Yes' if save_apple_id else 'No'}]")
        print(f"  3. 🔑  Save password               [{'Yes' if save_password else 'No'}]")
        print(f"  4. 🔐  Save 2FA verification       [{'Yes' if save_2fa else 'No'}]")
        print(f"  5. 🗄️   Session directory           [{session_label}]")
        print(f"  6. 🌏  China mainland mode         [{'Yes' if china_mainland else 'No'}]")
        print(f"  7. ⚡  Concurrent downloads        [{workers}]")
        print(f"  8. 👀  Preview before start        [{'Yes' if preview else 'No'}]")
        print(f"  9. 🔄  Resume downloads            [{'Yes' if resume else 'No'}]")
        print(f" 10. 📊  Log level                   [{log_level}]")
        print(f" 11. 💾  Save & return to main menu")
        print(f" 12. ↩️   Discard & return")
        print(f" {Colors.RED}13. CLEAR ALL USER DATA{Colors.RESET}")

        choice = input_func("\nEnter choice: ").strip()

        if choice == "1":
            current = config.get("destination", DEFAULT_DOWNLOAD_PATH)
            new_dest = input_func(f"Download folder [{current}]: ").strip()
            if new_dest:
                config["destination"] = new_dest
            print(f"{Colors.GREEN}✓{Colors.RESET} Download directory: {format_path_for_display(config.get('destination', DEFAULT_DOWNLOAD_PATH))}\n")
        elif choice == "2":
            hint = "Y/n" if save_apple_id else "y/N"
            yn = input_func(f"Save Apple ID email address? [{hint}]: ").strip().lower()
            if yn:
                config["save_apple_id"] = yn in ("y", "yes")
            if config.get("save_apple_id"):
                print(f"{Colors.GREEN}✓{Colors.RESET} Apple ID email will be saved — no need to retype it each run")
                print(f"  {Colors.DIM}Password is never saved — you will always be prompted{Colors.RESET}\n")
            else:
                config.pop("saved_apple_id", None)
                print(f"{Colors.GREEN}✓{Colors.RESET} Apple ID email will not be saved.\n")
        elif choice == "3":
            hint = "Y/n" if save_password else "y/N"
            yn = input_func(f"Save password in system keyring? [{hint}]: ").strip().lower()
            if yn:
                new_val = yn in ("y", "yes")
                if new_val:
                    config["save_password"] = True
                else:
                    config.pop("save_password", None)
            print(f"{Colors.GREEN}✓{Colors.RESET} Save password: {'Enabled — password stored and read from system keyring' if config.get('save_password') else 'Disabled — password prompted each run'}\n")
        elif choice == "4":
            hint = "Y/n" if save_2fa else "y/N"
            yn = input_func(f"Keep 2FA verification session between runs? [{hint}]: ").strip().lower()
            if yn:
                config["save_2fa_session"] = yn in ("y", "yes")
            if config.get("save_2fa_session"):
                print(f"{Colors.GREEN}✓{Colors.RESET} 2FA verification session will persist between runs")
                print(f"  {Colors.DIM}Session tokens are encrypted at rest{Colors.RESET}\n")
            else:
                print(f"{Colors.GREEN}✓{Colors.RESET} 2FA will be required each run — save with option 11 to clear existing tokens.\n")
        elif choice == "5":
            current = config.get("session_dir")
            prompt = "Custom session directory [blank keeps current, '-' resets to default]: "
            new_session_dir = input_func(prompt).strip()
            if new_session_dir == "-":
                config.pop("session_dir", None)
            elif new_session_dir:
                config["session_dir"] = new_session_dir
            if config.get("session_dir"):
                print(f"{Colors.GREEN}✓{Colors.RESET} Session directory: {format_path_for_display(config['session_dir'])}\n")
            else:
                print(f"{Colors.GREEN}✓{Colors.RESET} Session directory: default (~/.pyicloud)\n")
        elif choice == "6":
            hint = "Y/n" if china_mainland else "y/N"
            yn = input_func(f"Use Apple China mainland endpoints? [{hint}]: ").strip().lower()
            if yn:
                config["china_mainland"] = yn in ("y", "yes")
            print(f"{Colors.GREEN}✓{Colors.RESET} China mainland mode: {'Enabled' if config.get('china_mainland') else 'Disabled'}\n")
        elif choice == "7":
            new_workers = input_func(f"Concurrent downloads (1-10) [{workers}]: ").strip()
            if new_workers:
                try:
                    config["workers"] = max(1, min(10, int(new_workers)))
                except ValueError:
                    pass
            print(f"{Colors.GREEN}✓{Colors.RESET} Concurrent downloads: {config.get('workers', DEFAULT_MAX_WORKERS)}\n")
        elif choice == "8":
            hint = "Y/n" if preview else "y/N"
            yn = input_func(f"Run a preview first before downloading? [{hint}]: ").strip().lower()
            if yn:
                config["dry_run"] = yn in ("y", "yes")
            print(f"{Colors.GREEN}✓{Colors.RESET} Preview before start: {'Yes' if config.get('dry_run', False) else 'No'}\n")
        elif choice == "9":
            hint = "Y/n" if resume else "y/N"
            yn = input_func(f"Resume downloads? [{hint}]: ").strip().lower()
            if yn:
                config["resume"] = yn in ("y", "yes")
            print(f"{Colors.GREEN}✓{Colors.RESET} Resume downloads: {'Yes' if config.get('resume', True) else 'No'}\n")
        elif choice == "10":
            print("  1. DEBUG  2. INFO  3. WARNING")
            level_choice = input_func(f"Log level [{log_level}]: ").strip()
            level_map = {"1": "DEBUG", "2": "INFO", "3": "WARNING"}
            if level_choice in level_map:
                config["log_level"] = level_map[level_choice]
            elif level_choice.upper() in ("DEBUG", "INFO", "WARNING"):
                config["log_level"] = level_choice.upper()
            print(f"{Colors.GREEN}✓{Colors.RESET} Log level: {config.get('log_level', 'INFO')}\n")
        elif choice == "11":
            if _original_save_2fa and not config.get("save_2fa_session", False):
                cleanup_session_files(config)
                print(f"{Colors.GREEN}✓{Colors.RESET} Session tokens and cookies cleared.\n")
            return config
        elif choice == "12":
            return None
        elif choice == "13":
            confirmed = input_func("This will remove saved email, password, 2FA sessions, cookies, and local config. Continue? [y/N]: ").strip().lower()
            if confirmed not in {"y", "yes"}:
                print(f"{Colors.YELLOW}Clear-all cancelled.{Colors.RESET}\n")
                continue
            _clear_all_user_data(saved_config)
            print(f"{Colors.GREEN}✓{Colors.RESET} All user data cleared.\n")
            return {"_clear_all_user_data": True}
        else:
            print(f"{Colors.YELLOW}Please enter a number from 1 to 13{Colors.RESET}")


def run_main_menu(
    *,
    input_func: Callable[[str], str] = input,
    getpass_func: Callable[[str], str] = getpass,
) -> Dict[str, Any]:
    """Main menu with Start, Configure, and Exit options."""
    saved_config = _load_user_config()

    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}   iCloud Drive Downloader{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 60}{Colors.RESET}")

    while True:
        print(f"\n  1. 🚀  Start          — use saved preferences and log in")
        print(f"  2. ⚙️   Configure      — change download and auth defaults")
        print(f"  3. 🚪  Exit")

        choice = input_func("\nEnter choice [1]: ").strip()

        if choice in ("", "1"):
            return run_setup_wizard(
                saved_config=saved_config,
                input_func=input_func,
                getpass_func=getpass_func,
            )
        elif choice == "2":
            result = run_configure_menu(saved_config, input_func=input_func)
            if result is not None:
                if result.get("_clear_all_user_data"):
                    saved_config = {}
                    print(f"{Colors.GREEN}✓{Colors.RESET} Configuration cleared\n")
                else:
                    saved_config = result
                    _save_user_config(saved_config)
                    print(f"{Colors.GREEN}✓{Colors.RESET} Configuration saved\n")
            else:
                print(f"{Colors.YELLOW}Changes discarded{Colors.RESET}\n")
        elif choice == "3":
            print(f"\n{Colors.CYAN}Goodbye!{Colors.RESET}\n")
            sys.exit(0)
        else:
            print(f"{Colors.YELLOW}Please enter 1, 2, or 3{Colors.RESET}")


def run_setup_wizard(
    *,
    saved_config: Optional[Dict[str, Any]] = None,
    input_func: Callable[[str], str] = input,
    getpass_func: Callable[[str], str] = getpass,
) -> Dict[str, Any]:
    """Interactive setup wizard for first-time users."""
    prefs = saved_config or {}

    print(f"\n{Colors.BOLD}Let's download your iCloud Drive files.{Colors.RESET}\n")
    print(
        f"{Colors.YELLOW}💡 Tip:{Colors.RESET} Use Configure from the main menu to change your saved defaults.\n"
    )

    config: Dict[str, Any] = _initial_wizard_config(prefs)

    if not os.environ.get("ICLOUD_APPLE_ID"):
        print(f"{Colors.BOLD}Step 1: Apple ID{Colors.RESET}")
        saved_apple_id = prefs.get("saved_apple_id") if config.get("save_apple_id") else None
        if saved_apple_id:
            raw = input_func("Enter your Apple ID (email): ").strip()
            apple_id = raw if raw else saved_apple_id
        else:
            apple_id = input_func("Enter your Apple ID (email): ").strip()
        if apple_id:
            config["_apple_id"] = apple_id
            print(f"{Colors.GREEN}✓{Colors.RESET} Apple ID: {redact_apple_id(apple_id)}\n")
        else:
            print(f"{Colors.RED}✗{Colors.RESET} Apple ID is required\n")
            sys.exit(1)
    else:
        print(f"{Colors.GREEN}✓{Colors.RESET} Using Apple ID from environment\n")

    if not os.environ.get("ICLOUD_PASSWORD"):
        print(f"{Colors.BOLD}Step 2: Apple ID Password{Colors.RESET}")
        print(
            f"{Colors.YELLOW}Important:{Colors.RESET} pyicloud signs in with your regular Apple ID password,"
        )
        print("then Apple handles any required two-factor authentication.")
        print("The password stays in memory for this session unless you choose keyring storage.\n")
        password = getpass_func("Enter your Apple ID password: ").strip()
        if password:
            config["_password"] = password
            print(f"{Colors.GREEN}✓{Colors.RESET} Password captured for this session only\n")
        else:
            print(f"{Colors.RED}✗{Colors.RESET} Password is required\n")
            sys.exit(1)
    else:
        print(f"{Colors.GREEN}✓{Colors.RESET} Using password from environment\n")

    config["_from_wizard"] = True

    print(f"\n{Colors.BOLD}{Colors.GREEN}✓ Setup complete!{Colors.RESET}\n")
    print(f"{Colors.CYAN}Starting...{Colors.RESET}\n")

    return config