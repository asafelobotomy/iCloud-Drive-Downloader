import os
import sys
from getpass import getpass
from typing import Any, Callable, Dict, Optional, Tuple

from .privacy import harden_session_artifacts, redact_apple_id, sanitize_upstream_error_text
from .presentation import Colors
from .two_factor import (
    complete_staged_two_factor_auth,
)

try:
    from pyicloud import PyiCloudService  # type: ignore[import-untyped]
    from pyicloud.exceptions import (  # type: ignore[import-untyped]
        PyiCloudFailedLoginException,
        PyiCloudNoStoredPasswordAvailableException,
    )
    from pyicloud.utils import (  # type: ignore[import-untyped]
        password_exists_in_keyring,
        store_password_in_keyring,
    )

    PYICLOUD_AVAILABLE = True
except ImportError:
    PyiCloudService = None
    PyiCloudFailedLoginException = Exception
    PyiCloudNoStoredPasswordAvailableException = Exception
    password_exists_in_keyring = None
    store_password_in_keyring = None
    PYICLOUD_AVAILABLE = False


def ensure_pycloud_available(service_class: Optional[Any] = None) -> None:
    """Exit with guidance if pyicloud is not available."""
    if service_class is None and not PYICLOUD_AVAILABLE:
        print("ERROR: pyicloud is not installed. Install it with: pip install pyicloud")
        sys.exit(1)


def extract_login_failure_detail(error: BaseException) -> Optional[str]:
    """Extract the most useful nested pyicloud login detail for user-facing diagnostics."""
    generic_details = {
        "Failed login to iCloud",
        "Invalid email/password combination.",
    }
    details = []
    seen = set()

    def add_detail(candidate: Optional[str]) -> None:
        if not candidate:
            return
        text = sanitize_upstream_error_text(candidate)
        if not text or text in generic_details or text in seen:
            return
        seen.add(text)
        details.append(text)

    nested_errors = [error, getattr(error, "__cause__", None)]
    nested_errors.extend(
        arg for arg in getattr(error, "args", ()) if isinstance(arg, BaseException)
    )

    for nested_error in nested_errors:
        if nested_error is None:
            continue
        add_detail(getattr(nested_error, "reason", None))

        response = getattr(nested_error, "response", None)
        if response is not None:
            add_detail(getattr(response, "text", None))

        for arg in getattr(nested_error, "args", ()):
            if isinstance(arg, str):
                add_detail(arg)

    return details[0] if details else None


def resolve_credentials(
    wizard_config: Dict[str, Any],
    *,
    use_keyring: bool = False,
    prompt_for_password: bool = True,
    getpass_func: Callable[[str], str] = getpass,
) -> Tuple[str, Optional[str]]:
    """Resolve credentials from wizard data, environment, or prompts."""
    apple_id = wizard_config.get("_apple_id") or os.environ.get("ICLOUD_APPLE_ID")
    password = wizard_config.get("_password") or os.environ.get("ICLOUD_PASSWORD")

    if not apple_id:
        apple_id = input("Enter your Apple ID email: ")
    elif not wizard_config.get("_apple_id"):
        print(f"Using Apple ID from environment: {redact_apple_id(apple_id)}")

    if not password and prompt_for_password and not use_keyring:
        password = getpass_func("Enter your Apple ID password: ")
    elif not wizard_config.get("_password"):
        if password:
            print("Using password from environment variable")
        elif use_keyring:
            print("Attempting password lookup from the system keyring")

    return apple_id, password


def cleanup_session_files(config: Dict[str, Any]) -> None:
    """Remove session and cookie files to prevent login persistence between runs."""
    import glob

    session_dir = config.get("session_dir")
    if session_dir:
        directory = os.path.abspath(os.path.expanduser(str(session_dir)))
    else:
        directory = os.path.join(os.path.expanduser("~"), ".pyicloud")
    # Legacy pyicloud naming (pre-v2.5.0)
    for filename in ("session", "cookies"):
        path = os.path.join(directory, filename)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
    # pyicloud v2.5.0+ naming: <apple_id>.session / <apple_id>.cookiejar
    for pattern in ("*.session", "*.cookiejar"):
        for path in glob.glob(os.path.join(directory, pattern)):
            try:
                os.remove(path)
            except OSError:
                pass


def resolve_service_options(config: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve pyicloud service keyword arguments from runtime config."""
    session_dir = config.get("session_dir")
    if session_dir:
        requested_directory = os.path.abspath(os.path.expanduser(str(session_dir)))
        if os.path.lexists(requested_directory):
            if os.path.islink(requested_directory):
                print("ERROR: Session directory cannot be a symlink.")
                sys.exit(1)
            if not os.path.isdir(requested_directory):
                print("ERROR: Session directory must be a directory.")
                sys.exit(1)
        else:
            os.makedirs(requested_directory, mode=0o700, exist_ok=True)
        os.chmod(requested_directory, 0o700)
        cookie_directory = os.path.realpath(requested_directory)
    else:
        # Harden the default pyicloud session directory so other local users
        # cannot read session tokens or cookies.
        default_directory = os.path.join(os.path.expanduser("~"), ".pyicloud")
        os.makedirs(default_directory, mode=0o700, exist_ok=True)
        os.chmod(default_directory, 0o700)
        cookie_directory = None  # let pyicloud use its own default path
    return {
        "cookie_directory": cookie_directory,
        "china_mainland": bool(config.get("china_mainland", False)),
    }


def inspect_auth_status(
    wizard_config: Dict[str, Any],
    config: Dict[str, Any],
    *,
    service_class: Optional[Any] = None,
    getpass_func: Callable[[str], str] = getpass,
) -> Dict[str, Any]:
    """Inspect persisted session state without triggering a full login flow."""
    resolved_service_class = service_class or PyiCloudService
    ensure_pycloud_available(resolved_service_class)

    apple_id = wizard_config.get("_apple_id") or os.environ.get("ICLOUD_APPLE_ID")
    service_kwargs = resolve_service_options(config)
    cookie_directory = service_kwargs["cookie_directory"]

    if not apple_id:
        has_any_session = False
        check_dir = cookie_directory or os.path.join(os.path.expanduser("~"), ".pyicloud")
        if os.path.isdir(check_dir):
            import glob
            has_any_session = bool(
                glob.glob(os.path.join(check_dir, "*.session"))
                or glob.glob(os.path.join(check_dir, "*.cookiejar"))
                or os.path.exists(os.path.join(check_dir, "session"))
                or os.path.exists(os.path.join(check_dir, "cookies"))
            )
        return {
            "apple_id": None,
            "session_dir": check_dir,
            "session_path": None,
            "cookiejar_path": None,
            "has_session_file": has_any_session,
            "has_cookiejar_file": has_any_session,
            "use_keyring": bool(config.get("use_keyring", False)),
            "keyring_password_available": False,
            "china_mainland": bool(config.get("china_mainland", False)),
            "authenticated": False,
            "trusted_session": False,
            "requires_2fa": False,
            "requires_2sa": False,
        }

    probe_api = resolved_service_class(apple_id, None, authenticate=False, **service_kwargs)
    harden_session_artifacts(getattr(probe_api, "session", None))
    status = probe_api.get_auth_status() if hasattr(probe_api, "get_auth_status") else {
        "authenticated": False,
        "trusted_session": False,
        "requires_2fa": False,
        "requires_2sa": False,
    }
    session_path = probe_api.session.session_path
    cookiejar_path = probe_api.session.cookiejar_path
    keyring_password_available = False
    if password_exists_in_keyring is not None:
        try:
            keyring_password_available = bool(password_exists_in_keyring(apple_id))
        except Exception:
            keyring_password_available = False

    return {
        "apple_id": apple_id,
        "session_dir": os.path.dirname(session_path),
        "session_path": session_path,
        "cookiejar_path": cookiejar_path,
        "has_session_file": os.path.exists(session_path),
        "has_cookiejar_file": os.path.exists(cookiejar_path),
        "use_keyring": bool(config.get("use_keyring", False)),
        "keyring_password_available": keyring_password_available,
        "china_mainland": bool(config.get("china_mainland", False)),
        **status,
    }


def authenticate_session(
    wizard_config: Dict[str, Any],
    config: Dict[str, Any],
    *,
    service_class: Optional[Any] = None,
    getpass_func: Callable[[str], str] = getpass,
    session_key: Optional[bytes] = None,
) -> Any:
    """Authenticate against iCloud and handle optional 2FA."""
    resolved_service_class = service_class or PyiCloudService
    ensure_pycloud_available(resolved_service_class)

    apple_id, password = resolve_credentials(
        wizard_config,
        use_keyring=bool(config.get("use_keyring", False)),
        getpass_func=getpass_func,
    )
    service_kwargs = resolve_service_options(config)
    cookie_directory = service_kwargs.get("cookie_directory")

    from .crypto import decrypt_session_files, encrypt_session_files
    if cookie_directory and session_key:
        decrypt_session_files(cookie_directory, session_key)

    try:
        api = resolved_service_class(apple_id, password, **service_kwargs)
        harden_session_artifacts(getattr(api, "session", None))
    except PyiCloudNoStoredPasswordAvailableException:
        print(f"\n{Colors.RED}✗ No password was found in the system keyring{Colors.RESET}\n")
        print("Store a password first, provide ICLOUD_PASSWORD, or rerun without --use-keyring.")
        sys.exit(1)
    except PyiCloudFailedLoginException as error:
        print(f"\n{Colors.RED}✗ Login failed!{Colors.RESET}\n")
        detail = extract_login_failure_detail(error)
        if detail:
            print(f"{Colors.BOLD}pyicloud detail:{Colors.RESET} {detail}\n")
        print(f"{Colors.BOLD}Possible causes:{Colors.RESET}")
        print(
            f"  1. {Colors.YELLOW}Wrong password type or password{Colors.RESET} - "
            "pyicloud 2.x expects your regular Apple ID password, then Apple prompts for 2FA"
        )
        print(
            f"  2. {Colors.YELLOW}Account terms or security prompts pending{Colors.RESET} - "
            f"sign in once at {Colors.CYAN}https://www.icloud.com{Colors.RESET} and accept any prompts"
        )
        print(
            f"  3. {Colors.YELLOW}Mainland China Apple ID{Colors.RESET} - rerun with "
            f"{Colors.CYAN}--china-mainland{Colors.RESET} if your account region is China mainland"
        )
        print(f"  4. {Colors.YELLOW}Network issue{Colors.RESET} - Check your internet connection\n")
        print(
            f"{Colors.YELLOW}💡 Tip:{Colors.RESET} If you entered an app-specific password, "
            "try your normal Apple ID password instead."
        )
        print()
        sys.exit(1)
    finally:
        if cookie_directory and session_key:
            encrypt_session_files(cookie_directory, session_key)

    if api.requires_2fa:
        complete_staged_two_factor_auth(api)
        try:
            api.trust_session()
            harden_session_artifacts(getattr(api, "session", None))
            if cookie_directory and session_key:
                encrypt_session_files(cookie_directory, session_key)
        except Exception as error:
            sanitized_error = sanitize_upstream_error_text(str(error)) or "Apple would not mark this browser as trusted."
            print(f"Warning: could not trust session, you may be prompted for 2FA again. Error: {sanitized_error}")
        print("Successfully authenticated.")

    if (
        (config.get("store_in_keyring") or config.get("store_password_in_keyring"))
        and password
        and store_password_in_keyring is not None
    ):
        try:
            store_password_in_keyring(apple_id, password)
            print("Stored password in the system keyring.")
        except Exception as error:
            from .privacy import sanitize_upstream_error_text as _sanitize
            print(f"Warning: Could not store password in the system keyring. Error: {_sanitize(str(error))}")

    harden_session_artifacts(getattr(api, "session", None))

    return api