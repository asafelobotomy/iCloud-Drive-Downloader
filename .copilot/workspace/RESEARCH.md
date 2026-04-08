# Research URL Tracker — iCloud Drive Downloader

> Living document. Append rows as new useful URLs are discovered. All agents may update this file.
> Do not delete rows — mark stale entries with `(stale)` in the Summary column.
>
> **Setup note**: Seed the tables below with links relevant to iCloud Drive Downloader's stack and domain.

## VS Code Copilot — AI Customisation

| URL | Summary | Date | Tags |
|-----|---------|------|------|
| https://code.visualstudio.com/docs/copilot/customization/custom-agents | Custom agents documentation | 2026-04-06 | agents, customisation |
| https://code.visualstudio.com/docs/copilot/reference/copilot-vscode-features#_chat-tools | Built-in tool reference list | 2026-04-06 | tools, reference |

## Project-Specific Resources

| URL | Summary | Date | Tags |
|-----|---------|------|------|
| https://github.com/timlaing/pyicloud | timlaing/pyicloud — the actively maintained fork installed as pyicloud 2.5.0 in this project | 2026-04-08 | pyicloud, 2fa, fork |
| https://github.com/timlaing/pyicloud/issues/204 | Issue #204: SMS mode not detected from auth response; no method to trigger SMS delivery — fixed in v2.5.0 | 2026-04-08 | pyicloud, 2fa, sms, bug |
| https://github.com/timlaing/pyicloud/pull/210 | PR #210: "fix: restore SMS and trusted-device 2FA auth flows" — added request_2fa_code(), HSA2 bridge, SMS fallback; merged 2026-04-03 | 2026-04-08 | pyicloud, 2fa, sms, trusted-device, fix |
| https://github.com/timlaing/pyicloud/releases/tag/2.5.0 | pyicloud v2.5.0 release — includes SMS and trusted-device 2FA fix, HSA2 bridge prover | 2026-04-08 | pyicloud, release, 2fa |

## Cryptography and Security Research

| URL | Summary | Date | Tags |
|-----|---------|------|------|
| https://cryptography.io/en/latest/fernet/ | Fernet symmetric encryption — AES-128-CBC + HMAC-SHA256, high-level API | 2026-04-07 | cryptography, encryption, fernet |
| https://cryptography.io/en/latest/hazmat/primitives/aead/ | AEAD algorithms in cryptography — AES-GCM, ChaCha20-Poly1305, nonce management | 2026-04-07 | cryptography, aead, aes-gcm |
| https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/ | KDFs in cryptography — PBKDF2, HKDF, Argon2id (v44+), scrypt | 2026-04-07 | cryptography, kdf, argon2, hkdf |
| https://github.com/woodruffw/pyrage | pyrage — Python bindings for the Rust age implementation (x25519, SSH, passphrase) | 2026-04-07 | age, encryption, rust, pyrage |
| https://age-encryption.org/ | age file encryption — Go reference implementation, C2SP spec, X25519+ChaCha20-Poly1305 | 2026-04-07 | age, encryption, specification |
| https://pypi.org/project/argon2-cffi/ | argon2-cffi v25.1.0 — Argon2 for Python, Python 3.8+ only | 2026-04-07 | argon2, kdf, cffi |
| https://pypi.org/project/sqlcipher3/ | sqlcipher3 v0.6.2 — encrypted SQLite via SQLCipher, binary wheel available | 2026-04-07 | sqlcipher, sqlite, encryption |
| https://pypi.org/project/keyring/ | keyring — cross-platform keychain access (macOS Keychain, Secret Service, Windows Credential Locker) | 2026-04-07 | keyring, credentials, secrets |
| https://github.com/Yubico/python-fido2 | python-fido2 v2.1.1 — FIDO2/WebAuthn library, Python 3.10+, BSD-2 | 2026-04-07 | fido2, yubikey, hardware-security |
| https://nuetzlich.net/gocryptfs/ | gocryptfs — FUSE filesystem with AES-256-GCM + scrypt; Linux/macOS only, v2.5.0 | 2026-04-07 | fuse, gocryptfs, filesystem-encryption |
| https://github.com/str4d/rage | rage — Rust implementation of age, backs pyrage Python bindings | 2026-04-07 | age, rage, rust |
