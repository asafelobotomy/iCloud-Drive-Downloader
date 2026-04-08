# Research: At-Rest Encryption for iCloud Drive Downloader

> Date: 2026-04-07 | Agent: Researcher | Status: final

## Summary

This report covers cryptographic and security options for protecting the manifest
JSON, event log JSONL, session/cookie files, and downloaded content in a portable
Python 3.10+ CLI. The central finding is that **`cryptography` v46.0.6 and `fido2`
v2.1.1 are already present as zero-cost transitive dependencies** via pyicloud==2.5.0,
which means robust AES-256-GCM encryption can be added with no increase to the
explicit dependency count (currently 5 / budget 6). All recommendations follow
the constraint that the user must never enter a separate encryption passphrase on
every run.

---

## Sources

| URL | Relevance |
|-----|-----------|
| https://cryptography.io/en/latest/fernet/ | Fernet API (AES-128-CBC) |
| https://cryptography.io/en/latest/hazmat/primitives/aead/ | AES-GCM, ChaCha20-Poly1305 |
| https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/ | PBKDF2, HKDF, Argon2id |
| https://github.com/woodruffw/pyrage | pyrage (age Python bindings) |
| https://age-encryption.org/ | age spec v1 |
| https://pypi.org/project/argon2-cffi/ | argon2-cffi package page |
| https://pypi.org/project/sqlcipher3/ | sqlcipher3 package page |
| https://pypi.org/project/keyring/ | keyring package page |
| https://github.com/Yubico/python-fido2 | python-fido2 page |
| https://nuetzlich.net/gocryptfs/ | gocryptfs project |

---

## Critical Pre-Finding: Transitive Dependency Audit

```
pyicloud==2.5.0 already requires:
  cryptography  46.0.6   (Apache-2.0 / BSD-3-Clause)
  fido2         2.1.1    (BSD-2-Clause)
  srp           1.0.22   (MIT)
  keyring       (already explicit)
```

**Implication**: The application can use the full `cryptography` library and `fido2`
at zero additional dependency cost. No budget slot is consumed. All encryption
recommendations below are therefore budget-neutral.

---

## A — At-Rest Encryption: Manifest (JSON) and Event Log (JSONL)

### Option A1: Fernet (`cryptography.fernet.Fernet`)

**Algorithm**: AES-128-CBC + HMAC-SHA256, with timestamp prepended in plaintext.

**Pros**:
- Simplest API: `Fernet.generate_key()`, `f.encrypt(data)`, `f.decrypt(token)`
- Thread-safe
- Authenticated encryption (integrity + confidentiality)

**Cons**:
- **AES-128**, not AES-256 — not aligned with the "best possible" security posture
- **Timestamp is visible in ciphertext** (plaintext prefix) — leaks "when was this
  file written" metadata without confidentiality of timing
- Requires the entire plaintext in memory at once — problematic for large JSONL logs
- URL-safe base64 encoding adds ~37% overhead

**Verdict**: Adequate for legacy compatibility but not the best choice when the
hazmat API is a single import away.

---

### Option A2: AES-256-GCM (`cryptography.hazmat.primitives.ciphers.aead.AESGCM`)

**Algorithm**: AES-256 in Galois/Counter Mode — an AEAD cipher providing both
confidentiality and integrity/authenticity in one operation.

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

key = AESGCM.generate_key(bit_length=256)     # 32 bytes
aesgcm = AESGCM(key)
nonce = os.urandom(12)                         # 96-bit nonce, never reuse with same key
ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data)
# Stored file format: nonce (12 bytes) || ciphertext+tag (len+16 bytes)
```

**Nonce management**: Nonces must be unique per encryption operation. For a file
that is re-written atomically (overwrite-on-save), a fresh `os.urandom(12)` nonce
per write is correct. For append-only JSONL, each line must carry its own nonce.
A monotonic counter encoded as 12 bytes also works, but `os.urandom(12)` with
$2^{96}$ space is safe for any non-adversarial workload.

**Pros**:
- True AES-256 (industry standard for "best available")
- AEAD: single-pass authenticated encryption
- Widely understood, NIST-standardized (SP 800-38D)
- Zero allocation overhead on hardware with AES-NI (Intel/Apple Silicon)

**Cons**:
- "Hazardous Materials" API label — correct usage requires understanding nonce rules
- GCM has a known catastrophic failure mode if a 96-bit nonce is ever reused with
  the same key: authentication AND confidentiality are compromised. Mitigated by
  using `os.urandom(12)` per operation.

**Verdict**: **Best choice for manifest and metadata files.** AES-NI makes this
essentially free performance-wise on modern hardware. Widely audited.

---

### Option A3: ChaCha20-Poly1305 (`cryptography.hazmat.primitives.ciphers.aead.ChaCha20Poly1305`)

**Algorithm**: ChaCha20 stream cipher + Poly1305 MAC (RFC 7539).

```python
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
import os

key = ChaCha20Poly1305.generate_key()          # 32 bytes
chacha = ChaCha20Poly1305(key)
nonce = os.urandom(12)                         # 96-bit nonce
ciphertext = chacha.encrypt(nonce, plaintext, associated_data)
```

**Pros**:
- Equivalent security to AES-256-GCM (256-bit key, authenticated)
- Faster than AES-256-GCM on devices WITHOUT hardware AES-NI (ARM CPUs without
  required extensions, older hardware)
- Same API surface as AESGCM
- No timing-side-channel risk from table lookups (pure software design)

**Cons**:
- Same nonce-reuse failure mode as GCM
- Slightly slower than AES-256-GCM on Intel/Apple Silicon (where AES-NI is available)

**Verdict**: Use ChaCha20-Poly1305 for **session/cookie files** (read-back on every
run — the repeated decrypt performance matters). Either works; the security levels
are equivalent.

---

### Option A4: Age Format (`pyrage`)

**Algorithm**: X25519+ChaCha20-Poly1305 for file encryption; scrypt for passphrase mode.

```python
from pyrage import x25519, encrypt, decrypt

# One-time key generation
identity = x25519.Identity.generate()
recipient = identity.to_public()

# Encrypt
ciphertext = encrypt(plaintext_bytes, [recipient])

# Decrypt
plaintext = decrypt(ciphertext, [identity])
```

**Pros**:
- Modern, clean format spec (C2SP age-encryption.org/v1)
- Natural key rotation via recipient lists
- SSH key support (users can reuse existing SSH keys)
- Serializable identities — keys can be stored as strings

**Cons**:
- **Rust extension** (PyO3/maturin) — no pure Python fallback; binary wheel required
- Adds one explicit dependency (not yet in transitive graph)
- Age format is designed for file-to-file encryption, not for "encrypt a small JSON
  dict and immediately read it back in the same process run"
- Identity key management adds a UX layer: where do you store the `age1...` private
  key? (Answer: in keyring — but then you need that anyway)
- pyrage 1.x requires Python 3.9+ (PyO3 constraint)

**Verdict**: Excellent choice for encrypting standalone download archives or large
files, but over-engineered for the manifest/log use case. Not recommended as the
primary at-rest encryption for structured application state.

---

### Option A5: SQLCipher (`sqlcipher3-binary`)

**Algorithm**: AES-256-CBC per-page encryption of a SQLite database file. Key
derived via PBKDF2-HMAC-SHA512 (4000 iterations by default in v4.x, configurable).

**Pros**:
- Transparent: the application uses a normal sqlite3-style Python API
- All data (schema, indexes, rows) encrypted
- ATTACH + re-key support for schema migrations
- Binary wheel ships with statically linked SQLCipher — no system library needed

**Cons**:
- **Requires a full data model migration** from JSON/JSONL to SQLite schema
- The binary wheel is 2.6–2.7 MB — not trivial for a "lightweight portable CLI"
- Uses CBC mode (not GCM) — no authentication by default (use SQLCipher 4's
  PRAGMA integrity_check + HMAC via cipher_hmac_algorithm)
- Adds one explicit dependency
- Compatible with the project's Python 3.10+ baseline via binary wheels, but the build setup is
  complex for source installs

**Verdict**: The right tool if the architecture ever migrates to SQLite. Not
appropriate as a drop-in for the current JSON/JSONL files.

---

### Key Derivation Strategy (No Password on Every Run)

The goal is machine-tied encryption that does not require user interaction.

**Recommended approach — OS keyring master key**:

1. At first run, generate a cryptographically random 32-byte master encryption key:
   ```python
   import secrets
   master_key = secrets.token_bytes(32)
   ```
2. Store in OS keyring:
   ```python
   import keyring
   keyring.set_password("icloud-downloader", "master-encryption-key", master_key.hex())
   ```
3. Retrieve on every run:
   ```python
   hex_key = keyring.get_password("icloud-downloader", "master-encryption-key")
   master_key = bytes.fromhex(hex_key)
   ```
4. Use HKDF-SHA256 to derive per-purpose subkeys — prevents cross-contamination
   if one subkey is ever compromised:
   ```python
   from cryptography.hazmat.primitives.kdf.hkdf import HKDF
   from cryptography.hazmat.primitives import hashes

   def derive_key(master: bytes, purpose: str) -> bytes:
       return HKDF(
           algorithm=hashes.SHA256(),
           length=32,
           salt=None,
           info=purpose.encode(),
       ).derive(master)

   manifest_key  = derive_key(master_key, "manifest-v1")
   eventlog_key  = derive_key(master_key, "eventlog-v1")
   session_key   = derive_key(master_key, "session-v1")
   ```

**Why not PBKDF2/Argon2 from a passphrase?**
The constraint explicitly forbids per-run password prompts. PBKDF2 and Argon2 are
for password-based key derivation — they are the right tool when a human types a
passphrase, but wrong here. HKDF from a random keyring secret is the correct KDF
for this use case (key stretching from a high-entropy secret, not a low-entropy
password).

**Why not machine-id / hardware-derived?**
- Linux `/etc/machine-id` changes after reinstall; macOS `IOPlatformUUID` changes
  after logic board replacement or SIP bypass. These make key recovery impossible.
- OS TPM access requires platform-specific code (Windows Hello / Apple Secure
  Enclave APIs) with no portable Python abstraction. The OS keyring is the correct
  abstraction — it IS the hardware-backed secret store on macOS (Secure Enclave for
  Touch ID-protected items) and Windows (DPAPI / Windows Hello).

---

## B — Session/Cookie File Encryption

pyicloud stores cookies in a `~/.pyicloud/` or user-configured session directory.
These files contain authentication cookies that are read back on every invocation
to avoid repeated 2FA.

**Current state**: Files are plaintext. Anyone with filesystem access to the cookie
directory can impersonate the user against the iCloud API indefinitely.

**Recommended approach**:

1. **Short-term (zero code beyond permissions)**:  
   Ensure the session directory has `0o700` permissions (owner-only read/write/exec).
   This already prevents other users on the same machine from reading cookies.
   ```python
   import os, stat
   os.makedirs(session_dir, mode=0o700, exist_ok=True)
   os.chmod(session_dir, 0o700)
   ```

2. **Medium-term (encrypt-on-write)**:  
   Intercept cookie jar save/load. On save: serialize to JSON → encrypt with
   ChaCha20-Poly1305 using the `session_key` derived above → write `.enc` file.
   On load: read `.enc` file → decrypt → deserialize. This adds ~10 lines of code
   and zero dependencies.

**Trade-off note**: Encrypting session files adds complexity to the pyicloud
integration. Since pyicloud reads/writes the session directory itself, the
application would need to either post-process files after pyicloud saves them or
use a custom session backend. The simpler immediate win is correct permissions.

---

## C — Downloaded File Encryption

The user requirement states: *"Downloaded Photos and Drive content stays visible
to the user but impenetrable to third parties."*

This is a fundamental conflict: files must be simultaneously readable by the user
and unreadable by everyone else. Application-layer encryption resolves this only
with either:
- A manually decrypted vault (violates the no-extra-passphrase rule), or
- A FUSE virtual filesystem that decrypts on-the-fly for the authenticated user.

### Option C1: OS Full-Disk Encryption (zero code)

| Platform | Solution | Notes |
|----------|----------|-------|
| macOS | FileVault 2 (AES-256-XTS) | Built-in, enabled at System Settings → Privacy & Security |
| Windows | BitLocker (AES-256-XTS) | Built-in on Pro/Enterprise; Home has "Device Encryption" |
| Linux | LUKS2 (AES-256-XTS) | Set up at install time; dm-crypt userspace accessible |

**Verdict**: The correct answer for most users. The application should **document**
this and check whether the destination directory is on an encrypted volume, but
not implement its own encryption. No code required. Works on all platforms.

### Option C2: FUSE-Based Encrypted Filesystem (gocryptfs)

gocryptfs uses per-file AES-256-GCM encryption + scrypt KDF. Each plaintext file
maps to one encrypted file, making it sync-friendly. Version 2.5.0, January 2025.

**Pros**:
- Files are visible normally when mounted
- Works on Linux natively; macOS via macFUSE (requires SIP adjustments in some versions)
- Transparent to the application — download to the mount point, files appear decrypted

**Cons**:
- Requires external binary (`gocryptfs`) to be installed — breaks the portability
  goal of a self-contained pip-installable tool
- macOS macFUSE requires a kernel extension — Apple has progressively tightened
  this (Reduced Security may be required on Apple Silicon)
- Windows has no official gocryptfs support (cppcryptfs exists but is third-party)
- Users must `gocryptfs --mount` before downloading and `fusermount -u` after

**Verdict**: Excellent for Linux power-users but unacceptable as the default for
a cross-platform tool aimed at non-technical users.

### Option C3: Application-Layer Virtual Drive

Encrypting individual files on write and serving them via a user-space virtual
filesystem (FUSE Python bindings, e.g. `pyfuse3`) is technically possible but:
- Requires root or kernel capabilities on many platforms
- Adds 1–2 large dependencies
- Complex multi-process architecture for a CLI
- No benefit over OS-level FDE that the user already has

**Verdict**: Do not implement.

### Practical Recommendation for Downloaded Files

1. **Set `0o700` permissions on the destination directory** — prevents other OS
   users from accessing downloaded files. Zero dependencies, 1 line of code.
2. **Document OS-level FDE in README** — with step-by-step links for each platform.
3. **Optionally warn** at startup if the destination directory is world-readable.

---

## D — Credential and Key Management

### Current state
Credentials (iCloud password, 2FA) stored in OS keyring via the `keyring` library.
This is correct.

### Enhancement: Separate Data Encryption Key

The iCloud credential and the data encryption key (DEK) should be stored as
**separate** keyring entries. If the download application is compromised, the
attacker should NOT automatically get the ability to read all historical cached
data.

```
keyring service "icloud-downloader" / key "icloud-password" → iCloud password
keyring service "icloud-downloader" / key "data-encryption-key" → 32-byte DEK (hex)
```

### OS Keyring Security by Platform

| Platform | Backend | Encryption | Hardware-backed? |
|----------|---------|-----------|-----------------|
| macOS | Keychain (Security.framework) | AES-256-GCM | Yes (Secure Enclave for Touch ID items) |
| Windows | Windows Credential Manager (DPAPI) | AES-256-CBC + user key | Yes (TPM on modern hardware) |
| Linux | GNOME Keyring / KWallet / kr.alt | libsecret (D-Bus) | Passphrase-protected |
| Linux headless | `keyrings.alt` (file-based, base64) | None by default | No |

**Linux headless note**: `keyrings.alt` is a fallback that provides NO real
encryption. The DEK should be considered plaintext on headless Linux systems.
The application should warn the user if a non-secure backend is detected:
```python
backend = keyring.get_keyring()
if "PlaintextKeyring" in type(backend).__name__ or "AltKeyring" in type(backend).__name__:
    warnings.warn("Keyring is using an unprotected backend — credentials stored in plaintext.")
```

### Hardware Security Keys (YubiKey via `fido2`)

`fido2` v2.1.1 is already a transitive dependency. It supports:
- CTAP2 credential creation and assertion
- FIDO2 resident keys (discoverable credentials)
- HMAC-SECRET extension (can derive a site-specific secret from a YubiKey)

The HMAC-SECRET extension is particularly relevant: a YubiKey can return
a 32-byte secret that varies by application ID — perfect for a hardware-backed DEK.

```python
# Conceptual — uses fido2.ctap2.extensions.HmacSecretExtension
# key = yubikey.get_hmac_secret(app_id="icloud.downloader", salt=user_salt)
```

**However**, FIDO2 hardware key flows require:
- The YubiKey to be physically present on every run
- Complex `fido2.client` flows (platform authenticator vs. roaming authenticator)
- `fido2` requires Python 3.10+ (confirmed from GitHub README)
- Linux udev rules for HID device access
- Administrator access on Windows 10 pre-1903

**Verdict**: Not recommended for the default flow. Could be offered as an advanced
opt-in. The OS keyring (which is already hardware-backed on macOS/modern Windows)
provides equivalent security for most users without the friction.

---

## E — Memory and Process Security

### The Python Memory Challenge

Python's memory management makes traditional "secure zeroing" unreliable:

1. **Strings are immutable and interned** — `str` objects cannot be overwritten in
   place. A `str` holding a password may persist until GC collects it.
2. **`bytes` are immutable** — same problem.
3. **`bytearray` is mutable** — contents can be overwritten with `memset` via ctypes.
4. **The CPython allocator uses free-lists** — even after `del`, the memory is not
   immediately returned to the OS.

### Practical Mitigation

Use `bytearray` for any in-memory credential or key material, and zero it
explicitly before going out of scope:

```python
import ctypes

def zero_bytearray(buf: bytearray) -> None:
    """Best-effort zeroing for CPython. Not guaranteed under PyPy."""
    if isinstance(buf, bytearray) and len(buf) > 0:
        ctypes.memset(id(buf) + ctypes.sizeof(ctypes.c_ssize_t) * 2, 0, len(buf))
    buf[:] = b"\x00" * len(buf)  # fallback for other implementations
```

This directly writes zeros into the CPython bytearray buffer. It is:
- CPython-specific (the object layout is implementation-defined)
- Not guaranteed to prevent GC from keeping a copy
- **Better than nothing** — prevents casual forensic inspection of swap/core dumps

### `mlock` to Prevent Swapping

On POSIX systems, `mlock` pins pages to physical RAM, preventing the OS from
paging them to disk (where they could be recovered from swap):

```python
import mmap, ctypes

# Allocate a locked memory region
mm = mmap.mmap(-1, 32, mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)
# On Linux, mlock the region (requires RLIMIT_MEMLOCK)
libc = ctypes.CDLL(None)
libc.mlock(ctypes.c_void_p(ctypes.addressof(ctypes.c_char.from_buffer(mm))), 32)
```

This is non-portable, requires elevated `RLIMIT_MEMLOCK` on many Linux configurations,
and is not available on Windows via Python's standard library. The benefit for a
short-lived CLI process (seconds to minutes) is marginal — there is negligible
time for the OS to page out key material before the process exits.

### CLI vs. Server Comparison

| Concern | CLI tool | Long-running server |
|---------|----------|-------------------|
| Key material in RAM | Minutes | Hours/days |
| Swap pressure | Low (brief process) | High (always-on) |
| Core dump risk | Triggered by user, low probability | Higher (crash under load) |
| Memory forensics window | Very narrow | Broad |

**Verdict**: For a CLI tool, the practical security priority is: **do not write
credentials to disk in cleartext** (already addressed by keyring) and **do not log
credentials** (already addressed by privacy.py). mlock and secure zeroing are
hardening measures that have diminishing returns for a CLI but add complexity.
They are worth implementing for the key material (`bytearray` + zeroing) but not
for the full `requests.Session` payload.

---

## F — Practical Recommendation Matrix

All recommendations below add **zero explicit dependencies** (cryptography and fido2
are already in the transitive graph via pyicloud==2.5.0).

| Protection goal | Recommended approach | Algorithm | Dep cost | UX friction |
|----------------|---------------------|-----------|----------|-------------|
| Manifest.json at-rest | AES-256-GCM via `AESGCM` | AES-256-GCM | 0 | None |
| Event log JSONL at-rest | AES-256-GCM, one nonce per line | AES-256-GCM | 0 | None |
| Session/cookie files | `0o700` permissions (phase 1); ChaCha20-Poly1305 (phase 2) | — / ChaCha20-Poly1305 | 0 | None |
| Downloaded files | OS-level FDE advice + `0o700` on dest dir | OS platform | 0 | One-time user setup |
| Master key storage | OS keyring (already used) | OS keychain | 0 | None |
| Subkey derivation | HKDF-SHA256 | HKDF | 0 | None |
| DEK generation | `secrets.token_bytes(32)` at first run | CSPRNG | 0 | None |
| Memory protection | `bytearray` + ctypes zeroing for key material | — | 0 | None |

### Implementation Sequence

**Phase 1 — Permissions (safest, zero risk of data loss)**:
1. On session directory creation: `os.chmod(session_dir, 0o700)`
2. On manifest/log file creation: `os.chmod(path, 0o600)`
3. On destination directory creation: `os.chmod(dest_dir, 0o700)`
4. Warn on startup if keyring backend is plaintext

**Phase 2 — Manifest and log encryption**:
1. At first run: generate 32-byte DEK, store in keyring
2. Derive per-purpose keys via HKDF
3. Wrap manifest JSON serialize/deserialize
4. Wrap JSONL event log append/read
5. Store format: `nonce (12B) || AESGCM-ciphertext+tag` in a `.enc` file alongside
   or replacing the plaintext file

**Phase 3 — Session file encryption** (requires pyicloud session backend override):
1. Subclass or monkey-patch pyicloud's cookie persistence
2. Encrypt on save, decrypt on load using the derived `session_key`

---

## G — Python Library Reference Table

| Library | PyPI name | Latest version | License | C/Rust extension? | Python 3.10+? | Maintenance (2025–2026) |
|---------|-----------|---------------|---------|------------------|--------------|------------------------|
| cryptography | `cryptography` | **46.0.6** (Mar 2026) | Apache-2.0 / BSD-3-Clause | **Yes** — Rust + OpenSSL via cffi | No (3.8+ minimum) | Very active — PyCA team, weekly releases |
| Fernet (part of cryptography) | — | same | same | same | same | same |
| pyrage | `pyrage` | ~1.2.x | MIT | **Yes** — Rust via PyO3/maturin | No (3.9+ per PyO3 ABI) | Active — maintained by @woodruffw |
| age-encryption (pure Python) | `age-encryption` | unknown | unknown | No (pure Python claimed) | unknown | Uncertain — not the reference impl |
| argon2-cffi | `argon2-cffi` | **25.1.0** (Jun 2025) | MIT | **Yes** — CFFI + C (argon2-cffi-bindings) | No (3.8+ as of v23) | Active — maintained by @hynek |
| sqlcipher3 | `sqlcipher3` / `sqlcipher3-binary` | **0.6.2** (Jan 2026) | BSD-2-Clause | **Yes** — C (statically links SQLCipher 4.x) | Yes (prebuilt wheels from cp37) | Maintained — Dominic Ramsden |
| keyring | `keyring` | **25.x** | MIT | No (pure Python + OS backends) | Yes | Very active — @jaraco |
| fido2 | `fido2` | **2.1.1** (2025) | BSD-2-Clause | No (pure Python) | No (3.10+ per docs) | Active — Yubico |

**Notes**:
- "Python 3.10+" in the constraint column means the library fits the project's
  supported baseline. The project's actual runtime (`.venv`) is Python 3.14, so the
  3.8+ minimum of `cryptography` and `argon2-cffi` is not a real constraint.
- `cryptography` 46.x uses Rust internally for its OpenSSL bindings (via pyo3-ffi),
  so the pre-built wheel works on all major platforms without a Rust toolchain at
  install time.
- `fido2` has no C extension but does require platform HID access libraries
  (hidapi) which may involve platform-specific installation steps on Linux.
- The `age-encryption` pure Python package is NOT the reference implementation.
  The reference is the Go `filippo.io/age`. `pyrage` is the highest-quality
  Python binding (via the Rust `rage` implementation). Both require non-Python
  extension wheels.

---

## Gaps / Further Research Needed

1. **Linux headless keyring hardening**: The `keyrings.alt` fallback provides no
   encryption. Research an encrypted file-based fallback (e.g., `keyrings.cryptfile`
   or using PBKDF2+AES to wrap the DEK in a local encrypted file).
2. **pyicloud session backend API**: Confirm whether pyicloud 2.5.0 exposes a
   session backend override (`requests.Session.cookies.jar` replacement) that would
   allow transparent cookie encryption without forking pyicloud.
3. **macOS Keychain ACLs**: Apple's Security framework allows restricting keychain
   item access to specific application bundles. This would prevent other processes
   from reading the DEK. Research whether `keyring` exposes this, or whether a
   direct `Security.framework` call via ctypes is needed.
4. **Fernet vs AES-GCM nonce exhaustion**: Fernet's internal timestamp acts as a
   partial nonce differentiator. For AES-GCM with random nonces writing the same
   file thousands of times, the birthday bound at $2^{32}$ operations means nonce
   collision risk is negligible at CLI scale (confirmed: safe).
5. **File format versioning**: Any encryption format needs a version byte to allow
   future algorithm rotation (e.g., AES-256-GCM → XChaCha20-Poly1305). Recommend
   a 1-byte magic prefix `\x01` = AES-256-GCM-v1 in the file header.

