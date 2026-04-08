# Research: pyicloud SMS 2FA Flow — SMS Fallback Mechanics and Root Cause Analysis

> Date: 2026-04-08 | Agent: Researcher | Status: complete

## Summary

The installed `pyicloud` is **v2.5.0 from `timlaing/pyicloud`** (not the original `picklepete/pyicloud`). This fork added an HSA2 trusted-device bridge and fixed SMS mode detection in PR #210, merged 2026-04-03 — five days before this research. The SMS regression in the complex staged flow stems from a method-state mismatch: the bridge startup sets `_two_factor_delivery_method = "trusted_device"`, so `validate_2fa_code()` routes SMS codes to the wrong Apple endpoint. The simple flow worked because it never started the bridge, so SMS mode was detected dynamically from Apple's auth data.

---

## Sources

| URL | Relevance |
|-----|-----------|
| https://github.com/timlaing/pyicloud | Home repo for the installed fork — all code and issues |
| https://github.com/timlaing/pyicloud/issues/204 | The exact bug: SMS mode detection broken, no method to trigger SMS |
| https://github.com/timlaing/pyicloud/pull/210 | PR that fixed it, merged as v2.5.0 (2026-04-03) |
| https://github.com/timlaing/pyicloud/releases/tag/2.5.0 | v2.5.0 release notes confirming the fix |
| `/home/solon/.../pyicloud/base.py` | Installed source: validate_2fa_code, _validate_sms_code, two_factor_delivery_method, request_2fa_code |

---

## Findings

### 1. The installed pyicloud is a maintained fork — not picklepete's

**pyicloud v2.5.0** is from `https://github.com/timlaing/pyicloud`. The `pip show pyicloud` homepage field points to this repo, not `picklepete/pyicloud`. The fork is significantly more advanced: it adds the HSA2 trusted-device bridge (WebSocket + SPAKE2/P-256 prover), SRP-based login, security key/FIDO2 WebAuthn support, and Notes/Reminders services. The PR history for `base.py` shows the most recent relevant commit is `0ee22b97` ("fix: restore SMS and trusted-device 2FA auth flows") merged 2026-04-03.

**The original `picklepete/pyicloud` repo is effectively unmaintained** — the API search for issues there returned only 1 result (PR #310 from 2021), and no SMS-specific issues.

---

### 2. How `validate_2fa_code()` routes in v2.5.0

```python
# base.py — validate_2fa_code (current v2.5.0)
def validate_2fa_code(self, code: str) -> bool:
    bridge_state = self._trusted_device_bridge_state
    try:
        if self.two_factor_delivery_method == "sms":
            self._validate_sms_code(code)           # → POST /verify/phone/securitycode
        elif (bridge_state is not None and
              not bridge_state.uses_legacy_trusted_device_verifier):
            self._trusted_device_bridge.validate_code(...)   # → Bridge WebSocket path
        else:
            self._validate_trusted_device_code(code)  # → POST /verify/trusteddevice/securitycode
    ...
```

**Routing is entirely determined by `two_factor_delivery_method`**, which reads the internal `_two_factor_delivery_method` field. This field starts as `"unknown"` and is updated by:
- `_request_sms_2fa_code()` → sets it to `"sms"`
- `_trusted_device_bridge.start()` → sets it to `"trusted_device"`
- `request_2fa_code()` → calls one of the above

If the field stays `"unknown"`, the property falls through a dynamic check:

```python
@property
def two_factor_delivery_method(self) -> str:
    if self._two_factor_delivery_method != "unknown":
        return self._two_factor_delivery_method        # explicit state wins
    if self._auth_data.get("fsaChallenge") or self.security_key_names:
        return "security_key"
    if self._supports_trusted_device_bridge():
        return "trusted_device"                        # bridge available → trusted device
    if self._two_factor_mode() == "sms":
        return "sms"                                   # SMS-only account detected
    return "unknown"
```

---

### 3. The two Apple verification endpoints — and what each accepts

| Endpoint | Path | What it validates |
|----------|------|-------------------|
| **Trusted-device** | `POST /appleauth/auth/verify/trusteddevice/securitycode` | Push codes sent to trusted Apple devices (iPhone, iPad, Mac) via Apple's device-to-device system |
| **Phone/SMS** | `POST /appleauth/auth/verify/phone/securitycode` | Codes delivered by SMS or phone call to a trusted phone number |

**The trusted-device endpoint does NOT accept SMS codes.** Issue #204 explicitly states: "The code falls through to the else branch and tries `/verify/trusteddevice/securitycode`, which expects a push-delivered code that was never sent."

To trigger SMS delivery, Apple also requires a prior `PUT /appleauth/auth/verify/phone` request. Without that PUT, Apple never sends the SMS (for most account configurations).

---

### 4. Issue #204 — The exact bug (filed 2026-03-23, closed 2026-04-03)

**Title**: "SMS-based 2FA broken: mode not detected from auth response, and no method to request SMS delivery"

**Root cause (as documented in the issue)**:

1. **Wrong JSON path for mode detection** (in pre-v2.5.0 code):
   ```python
   # OLD (broken): top-level "mode" key never exists in Apple's response
   if self._auth_data.get("mode") == "sms":
   ```
   Apple nests it here:
   ```json
   {
     "phoneNumberVerification": {
       "trustedPhoneNumber": {
         "pushMode": "sms",   ← actual location
         "id": 1,
         "obfuscatedNumber": "(•••) •••-••XX"
       }
     }
   }
   ```
   So `_auth_data.get("mode")` always returned `None`, making SMS detection fail silently.

2. **No method to request SMS delivery** before validation — Apple requires a PUT request before it will send the code.

**Fix in v2.5.0** (PR #210):
- Reads mode via `trusted_phone_number.push_mode` (through `_trusted_phone_number()`)
- Added `request_2fa_code()` public method that triggers delivery
- Added `_request_sms_2fa_code()` for explicit SMS delivery
- Reworked auth option fetching to parse HTML boot context (not just JSON)

---

### 5. KEY QUESTION: Does `validate_2fa_code(code)` work for SMS WITHOUT first calling `_request_sms_2fa_code()`?

**Short answer: NO for most scenarios in v2.5.0. It depended on account type before.**

**Detailed breakdown by account configuration:**

#### Account with trusted Apple devices (has bridge capability)

When `_supports_trusted_device_bridge()` is True:
- Without calling `request_2fa_code()` first: `two_factor_delivery_method` dynamically returns `"trusted_device"` (bridge available)
- `validate_2fa_code()` routes to bridge path or `_validate_trusted_device_code()`
- **An SMS code submitted here will fail** — wrong endpoint
- Apple may have auto-sent an SMS when login was triggered from an untrusted device, but validation still goes to wrong endpoint

#### SMS-only account (no trusted Apple devices — bridge NOT available)

When `_supports_trusted_device_bridge()` is False:
- `two_factor_delivery_method` dynamically returns `"sms"` (if `_trusted_phone_number().push_mode == "sms"`)
- `validate_2fa_code()` routes to `_validate_sms_code()` → correct endpoint
- **BUT**: Apple needs a prior PUT to `/verify/phone` to actually send the SMS — without it, the user has no code to enter
- Exception: some accounts (no trusted devices, SMS-primary) get an SMS auto-sent by Apple at login, before any explicit PUT request — in that case the simple flow may work end-to-end

#### Why the "original simple flow" appeared to work

The simple flow (check `requires_2fa`, prompt user, call `validate_2fa_code()`) bypasses the bridge entirely. For SMS-primary accounts that receive an SMS automatically from Apple at login time, the dynamic mode detection correctly routes to `_validate_sms_code()`. This is the scenario where no explicit `_request_sms_2fa_code()` call is needed — Apple already sent the code.

---

### 6. Why the complex staged flow breaks SMS

The complex staged flow in this project calls `request_trusted_device_code()` (in `two_factor.py`) which starts the HSA2 bridge. The bridge startup:
1. Calls `api._trusted_device_bridge.start(...)` 
2. Sets `_two_factor_delivery_method = "trusted_device"`
3. Sends Apple the bridge initiation payload — triggering a **device push**, not SMS

After this, `validate_2fa_code()` always routes to the bridge verifier. If the user received an SMS (either auto-sent by Apple or from a prior session), entering it at the bridge prompt fails because the bridge expects a P-256/SPAKE2 confirmation, not a simple 6-digit SMS code submitted to `/verify/phone/securitycode`.

**The specific failure scenario:**
1. User logs in → Apple auto-sends SMS to trusted phone number
2. Complex flow starts bridge → Apple now awaits device-side confirmation instead
3. User receives (or already has) an SMS code
4. User enters SMS code at the first prompt (trusted-device prompt)
5. `validate_2fa_code()` → method is `"trusted_device"` → bridge path → **fails**
6. `_exit_invalid_two_factor_code()` → `sys.exit(1)`

The user never gets to the SMS fallback prompt because the code entry already failed.

---

### 7. The correct flow in v2.5.0 for accounts with both device and SMS capability

**For trusted-device accounts** (bridge available):
```
request_2fa_code()         → starts bridge → Apple pushes to device → method = "trusted_device"
  ↓ (if bridge fails)
_request_sms_2fa_code()    → PUT /verify/phone → Apple sends SMS → method = "sms"
validate_2fa_code(code)    → routes by method: bridge path or _validate_sms_code()
```

**For SMS-only accounts** (no bridge):
```
request_2fa_code()         → bridge not supported → _request_sms_2fa_code() → method = "sms"
validate_2fa_code(code)    → routes to _validate_sms_code() → POST /verify/phone/securitycode
```

**Critical**: `_two_factor_delivery_method` must match the actual delivery path at the time the user enters their code. If bridge is started but SMS fallback is requested, `_request_sms_2fa_code()` must be called (which updates the method to "sms") before `validate_2fa_code()` is called.

---

### 8. State machine for `_two_factor_delivery_method`

```
Initial state: "unknown"
  ↓ login triggers 2FA
  ↓ _get_mfa_auth_options() called → _auth_data populated

[Explicit state transitions]
  _request_sms_2fa_code()           → "sms"
  _trusted_device_bridge.start()    → "trusted_device"  (via _set_two_factor_delivery_state)
  _set_two_factor_delivery_state()  → any value

[Dynamic fallback if still "unknown"]
  two_factor_delivery_method property:
    - fsaChallenge in auth_data? → "security_key"
    - _supports_trusted_device_bridge()? → "trusted_device"
    - _two_factor_mode() == "sms"? → "sms"
    - else → "unknown"

[Reset on trust_session()]
  _two_factor_delivery_method → "unknown" (via _authenticate_with_token → _set_two_factor_delivery_state)
```

---

### 9. Alternative pyicloud forks

- **`homeassistant/pyicloud`** — Forked for Home Assistant; similar SRP/HSA2 structure but diverged further
- **`picklepete/pyicloud`** — Original; last significant activity 2021; missing bridge, SRP, and current Apple auth flows
- **`timlaing/pyicloud`** — The actively maintained fork, v2.5.0 (2026-04-03), best current Apple iCloud API compatibility

No other fork was found that handles SMS differently in a way that would be better suited.

---

## Recommendations

### Immediate: The staged flow needs to intercept Apple's auto-SMS when the bridge is active

The most likely regression cause is users who receive Apple's auto-SMS **before** the bridge is started (because Apple sends it at login time for untrusted sessions), then enter that code at the trusted-device prompt. The fix is either:

**Option A** — Detect auto-SMS and route early:
After calling `request_trusted_device_code()` but before prompting, check `api.two_factor_delivery_method`. If it's already `"sms"` (meaning the bridge failed and fell back to SMS), skip the trusted-device prompt and go straight to the SMS prompt.

```python
if device_requested and api.two_factor_delivery_method == "sms":
    sms_requested = True
    # Skip device prompt, go straight to SMS prompt
```

The current `complete_staged_two_factor_auth` already does this via:
```python
if getattr(api, "two_factor_delivery_method", "unknown") == "sms":
    sms_requested = True
    if prompt_for_two_factor_code_or_fallback(...):
        return
```

But the **real gap** is when bridge is "trusted_device" and the user enters their SMS code at the trusted-device prompt — it silently fails and exits instead of reprinting with SMS context.

**Option B** — Accept codes at the trusted-device prompt, and if trusted-device validation fails, automatically fall back to SMS validation:
When `validate_2fa_code()` returns False and method is "trusted_device", try `_validate_sms_code()` as a silent fallback. This handles the auto-SMS scenario without changing the UX.

**Option C** — Check whether Apple auto-sent an SMS at login by examining `_auth_data["phoneNumberVerification"]` before starting the bridge. If SMS mode is active AND no trusted device flag is explicitly set, skip the bridge and go straight to SMS.

### Longer-term: Align with v2.5.0's `request_2fa_code()` contract

In v2.5.0, `request_2fa_code()` is the single entry point for delivery initiation — it handles bridge, SMS fallback, and state setting atomically. The project's custom `request_trusted_device_code()` partially duplicates this and can race with internal state. Consider delegating to `api.request_2fa_code()` exclusively and checking `api.two_factor_delivery_method` after it returns to know which prompt to show.

---

## Gaps / Further research needed

- **Does Apple auto-send SMS at login time** for HSA2 accounts with only a trusted phone number and no trusted devices? The fix in PR #210 implies yes for some accounts, but the exact account-type conditions are not documented.
- **Does `/verify/trusteddevice/securitycode`** ever accept SMS codes on any Apple account configuration? Current evidence says no.
- **Bridge WebSocket protocol details** — the `hsa2_bridge.py` and `hsa2_bridge_prover.py` modules implement a SPAKE2/P-256 handshake; if this fails silently, it may leave the method stuck at "trusted_device" even for SMS-primary accounts. Further testing with accounts that have only SMS would clarify.
