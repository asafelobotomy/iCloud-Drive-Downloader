import sys
from typing import Any, Optional

from .privacy import prompt_masked_secret, sanitize_upstream_error_text, summarize_trusted_target
from .presentation import Colors

TRUSTED_DEVICE_FALLBACK_MESSAGE = "If you do not have access to a trusted device, press Enter to receive an SMS to your trusted phone number!"
SMS_FALLBACK_MESSAGE = "If you do not have access to a trusted phone number, press Enter to use a security-key-only account!"
RECOVERY_MESSAGE = "If you do not have access to any verification method, you will not be able to complete login authentication!"


def print_account_recovery_guidance() -> None:
    """Print the final account-recovery guidance for unrecoverable 2FA flows."""
    print(f"{Colors.RED}{RECOVERY_MESSAGE}{Colors.RESET}")
    print("Recover your Apple account at https://iforgot.apple.com/ and try again.")


def exit_account_recovery() -> None:
    """Exit the current login flow with recovery guidance."""
    print()
    print_account_recovery_guidance()
    sys.exit(1)


def print_two_factor_request_warning(error: Exception) -> None:
    """Print a sanitized warning when Apple rejects an active code request."""
    sanitized_error = sanitize_upstream_error_text(str(error)) or "Apple returned an unexpected 2FA delivery error."
    print(f"Warning: Could not actively request a 2FA code. Error: {sanitized_error}")


def handle_security_key_challenge(api: Any) -> None:
    """Complete a security-key challenge through pyicloud's WebAuthn support."""
    security_key_names = list(getattr(api, "security_key_names", []) or [])

    print("Apple requires a security key to finish this sign-in.")
    if security_key_names:
        print(f"Configured security keys detected: {len(security_key_names)}")
    print("Connect or unlock your security key, then follow the local prompt.")

    input("Press Enter to continue with security-key verification...")
    try:
        api.confirm_security_key()
    except Exception as error:
        if (
            "Missing WebAuthn challenge data" in str(error)
            and attempt_sms_2fa_fallback(
                api,
                notice="Security-key challenge data missing; falling back to SMS.",
            )
        ):
            return
        if (
            "Missing WebAuthn challenge data" in str(error)
            and attempt_legacy_trusted_device_fallback(
                api,
                notice="Security-key challenge data missing; trying Apple's trusted verification targets instead.",
            )
        ):
            return
        print(f"\n{Colors.RED}✗ Security key verification failed{Colors.RESET}")
        sanitized_error = sanitize_upstream_error_text(str(error)) or "Apple returned an unexpected security-key error."
        print(f"Error: {sanitized_error}")
        print("Try reconnecting the security key and rerun the downloader.")
        print_account_recovery_guidance()
        sys.exit(1)

    print("Security key verification completed.")


def validate_two_factor_code(api: Any, code: str) -> bool:
    """Validate a 2FA code, trying the SMS endpoint as a fallback.

    pyicloud's ``validate_2fa_code()`` routes based on the
    ``two_factor_delivery_method`` property which may return ``"security_key"``
    even when the user actually has an SMS code (Apple includes
    ``fsaChallenge`` / ``keyNames`` for many accounts).  When the primary path
    rejects the code, fall back to SMS validation so auto-sent codes still work.
    """
    if getattr(api, "two_factor_delivery_method", "unknown") == "phone_call":
        validate_sms_code = getattr(api, "_validate_sms_code", None)
        if callable(validate_sms_code):
            try:
                validate_sms_code(code)
            except Exception:
                return False
            return True

    if api.validate_2fa_code(code):
        return True

    # The code may be valid on a different endpoint — try SMS validation
    # directly when pyicloud routed to the wrong one.
    validate_sms_code = getattr(api, "_validate_sms_code", None)
    if callable(validate_sms_code) and trusted_phone_number(api) is not None:
        try:
            validate_sms_code(code)
        except Exception:
            return False
        set_two_factor_delivery_state(api, "sms")
        return True

    return False


def _exit_invalid_two_factor_code() -> None:
    """Exit with the shared invalid-code guidance."""
    print(f"\n{Colors.RED}✗ Failed to verify the 2FA code{Colors.RESET}")
    print(f"\n{Colors.BOLD}Troubleshooting:{Colors.RESET}")
    print(f"  1. {Colors.YELLOW}Code expired{Colors.RESET} - Request a new code")
    print(f"  2. {Colors.YELLOW}Wrong code{Colors.RESET} - Double-check the numbers")
    print(f"  3. {Colors.YELLOW}Device not receiving codes{Colors.RESET} - Check device settings\n")
    print(f"{Colors.YELLOW}💡 Tip: Make sure your trusted device is nearby and unlocked{Colors.RESET}\n")
    sys.exit(1)


def prompt_for_two_factor_code(api: Any) -> None:
    """Prompt for and validate a 2FA code for the active delivery method."""
    code = prompt_masked_secret("  Enter the 6-digit code: ").strip()
    if not validate_two_factor_code(api, code):
        _exit_invalid_two_factor_code()


def prompt_for_two_factor_code_or_fallback(api: Any, fallback_message: str, *, color: str) -> bool:
    """Prompt for a code and allow Enter to advance to the next fallback stage."""
    print(f"{color}{fallback_message}{Colors.RESET}")
    code = prompt_masked_secret("  Enter the 6-digit code: ").strip()
    if not code:
        return False
    if not validate_two_factor_code(api, code):
        _exit_invalid_two_factor_code()
    return True


def try_manual_two_factor_code_then_fallback(api: Any) -> bool:
    """Prompt for a device code and allow Enter to advance to a later fallback."""
    print("Check your trusted Apple device for the 6-digit code\n")
    if prompt_for_two_factor_code_or_fallback(api, TRUSTED_DEVICE_FALLBACK_MESSAGE, color=Colors.YELLOW):
        return True
    if request_sms_2fa_code(api, notice="Trusted-device code entry skipped; falling back to SMS."):
        announce_two_factor_delivery(api)
        if prompt_for_two_factor_code_or_fallback(api, SMS_FALLBACK_MESSAGE, color=Colors.YELLOW):
            return True
    return False


def announce_two_factor_delivery(api: Any) -> None:
    """Print the current 2FA delivery route in a user-friendly form."""
    notice = getattr(api, "two_factor_delivery_notice", None)
    if notice:
        print(notice)

    delivery_method = getattr(api, "two_factor_delivery_method", "unknown")
    if delivery_method == "trusted_device":
        print("Requested a fresh 2FA prompt from Apple.")
        print("Approve the sign-in or enter the code shown on your trusted device.\n")
    elif delivery_method == "sms":
        print("Requested a 2FA code by SMS.")
        print("Check your trusted phone for the 6-digit code.\n")
    elif delivery_method == "phone_call":
        print("Requested a 2FA code by phone call.")
        print("Answer your trusted phone and enter the 6-digit code.\n")


def trusted_phone_number(api: Any) -> Optional[Any]:
    """Return the trusted phone payload when pyicloud exposes one."""
    get_trusted_phone_number = getattr(api, "_trusted_phone_number", None)
    if not callable(get_trusted_phone_number):
        return None
    return get_trusted_phone_number()


def can_request_sms_2fa_code(api: Any) -> bool:
    """Return whether pyicloud can attempt an SMS request for the current challenge."""
    return callable(getattr(api, "_request_sms_2fa_code", None)) and trusted_phone_number(api) is not None


def refresh_two_factor_auth_options(api: Any) -> bool:
    """Refresh pyicloud's cached MFA auth options when Apple exposes new fallback data."""
    refresh_auth_options = getattr(api, "_get_mfa_auth_options", None)
    if not callable(refresh_auth_options):
        return False
    try:
        refreshed = refresh_auth_options()
    except Exception:
        return False
    if not isinstance(refreshed, dict):
        return False
    auth_data = getattr(api, "_auth_data", None)
    if isinstance(auth_data, dict):
        auth_data.update(refreshed)
    else:
        api._auth_data = dict(refreshed)
    return True


def can_use_security_key(api: Any) -> bool:
    """Return whether the current challenge can use WebAuthn security-key verification."""
    challenge = getattr(api, "_auth_data", {}).get("fsaChallenge")
    if not isinstance(challenge, dict):
        return False
    return all(challenge.get(field) for field in ("challenge", "keyHandles", "rpId"))


def set_two_factor_delivery_state(api: Any, method: str, *, notice: Optional[str] = None) -> None:
    """Persist the current delivery state on the pyicloud service when possible."""
    set_state = getattr(api, "_set_two_factor_delivery_state", None)
    if callable(set_state):
        set_state(method, notice)
        return
    api.two_factor_delivery_method = method
    api.two_factor_delivery_notice = notice


def request_sms_2fa_code(api: Any, *, notice: Optional[str] = None) -> bool:
    """Request an SMS 2FA code through pyicloud's private HSA2 helpers."""
    request_sms = getattr(api, "_request_sms_2fa_code", None)
    if not callable(request_sms):
        return False
    if trusted_phone_number(api) is None and not refresh_two_factor_auth_options(api):
        return False
    if trusted_phone_number(api) is None:
        return False

    request_sms(notice=notice)
    return True


def attempt_sms_2fa_fallback(api: Any, *, notice: Optional[str] = None) -> bool:
    """Attempt pyicloud's private SMS fallback for HSA2 challenges when available."""
    if not request_sms_2fa_code(api, notice=notice):
        return False
    announce_two_factor_delivery(api)
    prompt_for_two_factor_code(api)
    return True


def attempt_legacy_trusted_device_fallback(api: Any, *, notice: Optional[str] = None) -> bool:
    """Fallback to pyicloud's older trusted-device verification APIs when available."""
    try:
        devices = list(getattr(api, "trusted_devices", []) or [])
    except Exception:
        return False

    send_code = getattr(api, "send_verification_code", None)
    if not devices or not callable(send_code):
        return False

    if notice:
        print(notice)
    print("Apple exposed trusted verification targets for this sign-in:")
    for index, device in enumerate(devices, start=1):
        print(f"  {index}. {summarize_trusted_target(device)}")

    while True:
        selection = input("Select target [1]: ").strip() or "1"
        if selection.isdigit() and 1 <= int(selection) <= len(devices):
            break
        print(f"Enter a number between 1 and {len(devices)}.")

    device = devices[int(selection) - 1]
    if not send_code(device):
        return False
    print("Requested a verification code from the selected target.\n")

    if not validate_legacy_trusted_device_code(api, device, prompt_masked_secret("  Enter the 6-digit code: ").strip()):
        print(f"\n{Colors.RED}✗ Failed to verify the 2FA code{Colors.RESET}\n")
        sys.exit(1)
    return True


def validate_legacy_trusted_device_code(api: Any, device: Any, code: str) -> bool:
    """Validate a code against Apple's legacy trusted-device endpoint without coupling success to session trust."""
    request_device = dict(device)
    request_device.update({"verificationCode": code, "trustBrowser": True})

    try:
        response = api.session.post(
            f"{api._setup_endpoint}/validateVerificationCode",
            params=api.params,
            json=request_device,
        )
    except Exception as error:
        if getattr(error, "code", None) == -21669:
            return False
        raise

    if hasattr(response, "ok") and not response.ok:
        return False
    return True


def complete_staged_two_factor_auth(api: Any) -> None:
    """Run the guided trusted-device -> SMS -> security-key 2FA flow.

    Delegates delivery to ``api.request_2fa_code()`` whenever possible so that
    pyicloud's internal state machine chooses the correct delivery method and
    ``validate_2fa_code()`` routes to the matching Apple endpoint.
    """
    print(f"\n{Colors.YELLOW}Two-factor authentication required{Colors.RESET}")

    # --- Stage 1: let pyicloud choose the best delivery method ---
    request_code = getattr(api, "request_2fa_code", None)
    delivery_requested = False
    if callable(request_code):
        try:
            delivery_requested = request_code()
        except Exception as error:
            print_two_factor_request_warning(error)

    delivery_method = getattr(api, "two_factor_delivery_method", "unknown")

    # When pyicloud bails on request_2fa_code() because it saw fsaChallenge or
    # keyNames (setting delivery to "security_key"), but we determine actual
    # WebAuthn is not viable, reset the state so validate_2fa_code() can use
    # dynamic detection to route codes to the correct Apple endpoint.
    if not delivery_requested and delivery_method == "security_key" and not can_use_security_key(api):
        set_two_factor_delivery_state(api, "unknown")
        delivery_method = "unknown"

    # --- Stage 2a: pyicloud chose a known delivery path ---
    if delivery_requested:
        announce_two_factor_delivery(api)
        if delivery_method == "sms":
            if prompt_for_two_factor_code_or_fallback(api, SMS_FALLBACK_MESSAGE, color=Colors.YELLOW):
                return
        else:
            if prompt_for_two_factor_code_or_fallback(api, TRUSTED_DEVICE_FALLBACK_MESSAGE, color=Colors.YELLOW):
                return
            # User pressed Enter — reset delivery state so pyicloud's dynamic
            # detection can route a subsequent code to the correct endpoint
            # (e.g. SMS for accounts where Apple auto-sent a text at login).
            set_two_factor_delivery_state(api, "unknown")
            if request_sms_2fa_code(api):
                announce_two_factor_delivery(api)
                if prompt_for_two_factor_code_or_fallback(api, SMS_FALLBACK_MESSAGE, color=Colors.YELLOW):
                    return

    # --- Stage 2b: pyicloud couldn't deliver — try SMS independently ---
    if not delivery_requested:
        try:
            if request_sms_2fa_code(api):
                announce_two_factor_delivery(api)
                if prompt_for_two_factor_code_or_fallback(api, SMS_FALLBACK_MESSAGE, color=Colors.YELLOW):
                    return
        except Exception as error:
            print_two_factor_request_warning(error)

    # --- Stage 3: legacy trusted-device fallback ---
    if attempt_legacy_trusted_device_fallback(api):
        return

    # --- Stage 4: security key ---
    if can_use_security_key(api):
        print(f"{Colors.RED}{RECOVERY_MESSAGE}{Colors.RESET}")
        handle_security_key_challenge(api)
        return

    # --- Stage 5: last-resort prompt (Apple may have auto-sent a code via
    # SMS or trusted device at login — let the user type it and our
    # validate_two_factor_code wrapper will try both endpoints) ---
    if callable(getattr(api, "validate_2fa_code", None)):
        print("Check your trusted Apple device or phone for the 6-digit code\n")
        print(f"{Colors.YELLOW}If you received an SMS or a push notification, enter the code now.{Colors.RESET}")
        code = prompt_masked_secret("  Enter the 6-digit code: ").strip()
        if code:
            if validate_two_factor_code(api, code):
                return
            _exit_invalid_two_factor_code()

    exit_account_recovery()