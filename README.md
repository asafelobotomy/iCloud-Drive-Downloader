# iCloud Drive Downloader

> **Download entire folders from iCloud Drive in minutes.** Simple, fast, and reliable.

[![Version](https://img.shields.io/badge/version-4.0.0-blue.svg)](CHANGELOG.md)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://github.com/asafelobotomy/iCloud-Drive-Downloader/actions/workflows/ci.yml/badge.svg)](https://github.com/asafelobotomy/iCloud-Drive-Downloader/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**What it does:** Downloads your entire iCloud Drive or Photos Library selection to your local machine. Includes resume capability, filters, concurrent downloads, an interactive main menu, and a setup wizard.

**Why it exists:** Apple's iCloud.com doesn't let you download entire folders—only individual files. This tool solves that.

---

## Quick Start

### Installation

This project now requires Python 3.10 or newer.

```bash
# Install dependencies
pip install -r requirements.txt

# Verify installation
python3 icloud_downloader.py --version
```

### Run It (Interactive Mode)

**No command-line knowledge needed!** Just run:

```bash
python3 icloud_downloader.py
```

The script opens a simple main menu. Choose Start to sign in, then pick what to download from iCloud Drive or iCloud Photo Library.

Configure handles login, session, destination, preview, and performance defaults. The actual download selection happens after login in Start.

That's it! Follow the prompts and download starts automatically.

---

## Key Features

### 🎯 Interactive Mode (Default)

Run without arguments—script asks simple questions and guides you through setup. Perfect for beginners.

### 🚀 Quick Presets

```bash
python3 icloud_downloader.py --preset photos      # Photos and videos only
python3 icloud_downloader.py --preset documents   # Documents only
python3 icloud_downloader.py --preset quick-test  # Test with 50 files
```

### 📂 Smart Downloads

- **Resume capability** - Interrupted downloads continue from where they stopped
- **Concurrent downloads** - Multiple files at once (1-10 workers, default: 3)
- **Pattern filters** - Include/exclude by filename patterns
- **Size filters** - Download only files within size range
- **Depth limits** - Control how deep into folders to go
- **Secure inventory cache** - Save a full local iCloud Drive tree with owner-only permissions for later selection
- **Interactive selection** - Browse cached folders and files in the terminal and multi-select exactly what to download

### 🎨 User-Friendly

- **Colorized output** - Green for success, red for errors, yellow for warnings
- **Progress tracking** - Real-time speed, ETA, and progress bars
- **Smart confirmations** - Preview before large downloads
- **Helpful errors** - Clear messages with solutions when things go wrong

### 🔒 Secure & Reliable

- **Path security** - Prevents malicious path traversal attacks
- **Owner-only permissions** - Files: 0o600, Directories: 0o700
- **Graceful shutdown** - Press Ctrl+C once to stop safely (saves progress)
- **Network resilience** - Automatic retries with exponential backoff

---

## Common Usage

### Basic Examples

```bash
# Interactive mode - simplest way
python3 icloud_downloader.py

# Use a preset
python3 icloud_downloader.py --preset photos

# Download all Photos Library photos
python3 icloud_downloader.py --source photos-library --photos-scope photos

# Custom destination
python3 icloud_downloader.py -d /mnt/backup

# Preview before downloading
python3 icloud_downloader.py --dry-run

# More workers for faster downloads
python3 icloud_downloader.py -w 10
```

### With Filters

```bash
# Only photos
python3 icloud_downloader.py --include "*.jpg" --include "*.png" --include "*.heic"

# Exclude cache and temporary files
python3 icloud_downloader.py --exclude "*/Cache/*" --exclude "*.tmp"

# Files between 1MB and 100MB
python3 icloud_downloader.py --min-size 1048576 --max-size 104857600

# First 2 folder levels only
python3 icloud_downloader.py --max-depth 2
```

### Save & Reuse Configuration

```bash
# Save configuration during interactive setup
python3 icloud_downloader.py --wizard
# (Choose "Save configuration" when prompted)

# Reuse saved config
python3 icloud_downloader.py --config config-private.json
```

Saved config files never include your Apple ID or Apple ID password.

### Build A Secure Inventory Cache

```bash
# Scan iCloud Drive, save a secure local cache, and exit
python3 icloud_downloader.py --build-inventory-cache

# Refresh the cache and then choose folders/files interactively
python3 icloud_downloader.py --select-from-cache --refresh-inventory-cache

# Use an existing cache and limit the selector to files only
python3 icloud_downloader.py --select-from-cache --selection-mode files
```

The cache stays local on your machine, uses owner-only permissions, and stores the directory tree for later terminal selection. It does not write filenames to the structured log.

### Environment Variables (Optional)

Skip credential prompts:

```bash
export ICLOUD_APPLE_ID="user@example.com"
export ICLOUD_PASSWORD="your-apple-id-password"
python3 icloud_downloader.py
```

---

## Authentication

### Apple ID Password Required

With `pyicloud 2.x`, sign in using your regular Apple ID password. Apple then handles the next verification step.

App-specific passwords are not used by pyicloud's web login flow.

1. Go to [icloud.com](https://www.icloud.com) once in a browser if you have not signed in recently
2. Complete any pending Apple security prompts or updated terms
3. Run the downloader and enter your normal Apple ID password when prompted

The script will prompt you for this when it runs.

### Two-Factor Authentication (2FA)

If 2FA is enabled (recommended), the script will:

1. Offer the available delivery methods for the current Apple challenge
2. Let you choose a trusted-device prompt, SMS code, or phone-call code when Apple exposes those routes
3. Prompt you for the 6-digit code and optionally trust the session to avoid repeated 2FA prompts

If pyicloud exposes a broken security-key challenge without the required WebAuthn payload, the CLI avoids that dead end and uses the available code-delivery methods instead.

For rate-limit guidance and mitigation steps, see [docs/RATE_LIMITING_AND_THROTTLING.md](docs/RATE_LIMITING_AND_THROTTLING.md).

---

## CLI Reference

### Essential Flags

| Flag | Short | Description |
| ---- | ----- | ----------- |
| `--destination <path>` | `-d` | Download location (default: ~/iCloud_Drive_Download) |
| `--workers <1-10>` | `-w` | Concurrent downloads (default: 3) |
| `--dry-run` | - | Preview without downloading |
| `--preset <name>` | - | Use preset (photos, documents, quick-test, large-files) |
| `--source <drive\|photos-library>` | - | Choose iCloud Drive or Photos Library |
| `--photos-scope <scope>` | - | Choose a Photos Library view (all, photos, videos, by-album, by-month) |
| `--list-presets` | - | Show preset names and descriptions |
| `--show-config` | - | Print the resolved configuration and exit |
| `--auth-status` | - | Print local iCloud session status and exit |
| `--wizard` | - | Interactive setup |

### Filters

| Flag | Description |
| ---- | ----------- |
| `--include <pattern>` | Include files matching pattern (glob, repeatable) |
| `--exclude <pattern>` | Exclude files matching pattern (glob, repeatable) |
| `--min-size <size>` | Minimum file size (e.g. 10MB, 2.5GB, 1048576) |
| `--max-size <size>` | Maximum file size (e.g. 10MB, 2.5GB, 1048576) |
| `--max-depth <num>` | Maximum folder depth |
| `--max-items <num>` | Maximum number of files |

### Photos Library Filters

| Flag | Description |
| ---- | ----------- |
| `--photos-album <name>` | Download one named album with `--source photos-library --photos-scope by-album` |
| `--photos-month <YYYY-MM>` | Download one month with `--source photos-library --photos-scope by-month` |
| `--photos-after <YYYY-MM-DD>` | Include Photos Library assets created on or after this date |
| `--photos-before <YYYY-MM-DD>` | Include Photos Library assets created on or before this date |

### Inventory Cache And Selection

| Flag | Description |
| ---- | ----------- |
| `--inventory-cache <file>` | Use a custom secure inventory cache path |
| `--build-inventory-cache` | Scan iCloud Drive, save the secure inventory cache, and exit |
| `--refresh-inventory-cache` | Refresh the secure inventory cache before continuing |
| `--select-from-cache` | Browse the secure inventory cache and select folders/files before running |
| `--selection-mode <mixed\|folders\|files>` | Restrict selector toggles to folders, files, or both |

### Advanced

| Flag | Description |
| ---- | ----------- |
| `--config <file>` | Load saved configuration |
| `--save-config <file>` | Save current settings to file |
| `--retries <num>` | Retry attempts per file (default: 3) |
| `--timeout <sec>` | Network timeout (default: 60) |
| `--sequential` | Download one file at a time |
| `--resume` / `--no-resume` | Force resume on or off |
| `--progress` / `--no-progress` | Force progress bars on or off |
| `--session-dir <path>` | Store iCloud session cookies and state in a custom directory |
| `--use-keyring` | Load the password from the system keyring when available |
| `--store-in-keyring` | Save the password from this run into the system keyring |
| `--china-mainland` | Use Apple’s China mainland iCloud endpoints |
| `--log <file>` | Log events to JSONL file |
| `--log-level <level>` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `--verbose` / `-v` | Enable verbose output |
| `--chunk-size <bytes>` / `-c` | Download chunk size in bytes (default: 8192) |
| `--min-free-space <GB>` / `-f` | Minimum free disk space in GB (default: 1) |
| `--no-color` | Disable colored output |
| `--skip-confirm` | Skip download confirmation |
| `--version` | Show version and exit |

Run `python3 icloud_downloader.py --help` for complete list.

### Auth And Session Examples

```bash
# Inspect the local session cache without starting a download
python3 icloud_downloader.py --auth-status --use-keyring

# Persist iCloud cookies in a dedicated directory
python3 icloud_downloader.py --session-dir /path/to/session/state

# Store the prompted Apple ID password in the system keyring
python3 icloud_downloader.py --store-in-keyring
```

---

## Troubleshooting

### Login Failed

**Cause:** Wrong password type, wrong password, pending Apple account prompts, or an account-region mismatch  
**Solution:** Use your regular Apple ID password, not an app-specific password. Sign in once at [icloud.com](https://www.icloud.com) to accept any prompts, and use `--china-mainland` if your Apple ID region is China mainland.

### 2FA Code Not Working

**Cause:** Code expired or incorrect  
**Solution:** Request a new code—they expire quickly

If you see `Missing WebAuthn challenge data`, choose one of the available code-delivery methods instead of retrying the broken security-key path.

### Download Interrupted

**Cause:** Network issue, Ctrl+C pressed, computer crashed  
**Solution:** Just run the script again—it automatically resumes from where it stopped

### Out of Disk Space

**Cause:** Not enough free space for download  
**Solution:** Free up space or change destination with `-d /path/to/larger/drive`

### Slow Downloads

**Cause:** Network speed, Apple throttling, or too few workers  
**Solutions:**

- Increase workers: `--workers 10`
- Reduce workers if you see HTTP 429 or throttle warnings
- Check network connection
- Try during off-peak hours

### Want to Stop Safely

**Action:** Press **Ctrl+C once** (saves progress for resume)  
**Force quit:** Press **Ctrl+C twice** (may lose some progress)

---

## Documentation

- **[Quick Reference](docs/QUICK_REFERENCE.md)** - Cheat sheet with common commands
- **[Interactive Mode Guide](docs/INTERACTIVE_MODE.md)** - Detailed walkthrough
- **[Rate Limiting & Throttling](docs/RATE_LIMITING_AND_THROTTLING.md)** - Practical throttling guidance, warning signs, and mitigation steps
- **[Configuration Examples](examples/README.md)** - Sample config files
- **[Full Documentation](docs/README.md)** - Complete docs index
- **[Changelog](CHANGELOG.md)** - Version history

---

## Testing

Run the comprehensive test suite:

```bash
# Using pytest (install requirements-test.txt first)
python3 -m pytest tests/ -v

# With coverage report
python3 -m pytest tests/ --cov=icloud_downloader_lib --cov=icloud_downloader --cov-report=html
```

CI enforces a 70% minimum coverage gate on the modular package plus the wrapper.

The suite covers filters, path safety, manifest persistence, retry logic, config persistence, auth/session flows, dry-run behavior, and streamed download flows.

---

## Requirements

- **Python 3.10+**
- `pyicloud==2.5.0` - iCloud API
- `requests>=2.33.1,<3.0.0` - HTTP library
- `tenacity>=9.1.4,<10.0.0` - Retry framework
- `tqdm>=4.67.3,<5.0.0` - Progress bars (optional)
- `prompt_toolkit>=3.0` - Interactive file selector (only needed for `--select-from-cache`)

### Optional (Development)

- `pytest>=9.0.2,<10.0.0` - Testing
- `pytest-cov>=7.1.0,<8.0.0` - Coverage reports
- `pytest-timeout>=2.4.0,<3.0.0` - Test timeout guardrails
- `mypy>=1.20.0,<2.0.0` - Type checking

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for:

- Development setup
- Testing guidelines
- Code patterns and conventions
- Wrapper and modular package notes

This project includes a thin CLI wrapper, a modular implementation package, typed interfaces, thread-safe helpers, and path-safety safeguards.

---

## Project Structure

```text
├── icloud_downloader.py        # CLI compatibility wrapper
├── icloud_downloader_lib/      # Main implementation package
├── requirements.txt            # Runtime dependencies
├── requirements-test.txt       # Test and type-check dependencies
├── tests/                      # Test suite
├── docs/                       # Documentation
├── examples/                   # Config examples
├── scripts/                    # Utility scripts
└── archive/                    # Historical files
```

---

## License

MIT License - See [LICENSE](LICENSE) for details.

**Personal use:** Use this tool responsibly and in accordance with Apple's Terms of Service. This script uses official Apple APIs and requires your valid iCloud credentials.

---

## Why This Tool?

Apple's iCloud.com doesn't support downloading entire folders. Your options are:

- **privacy.apple.com** - Takes days or weeks
- **iPhone/iPad workarounds** - Manual and slow
- **macOS Finder sync** - Requires local storage for everything
- **Manual selection** - Impractical for large folders

**This tool downloads folders directly in minutes**, with resume capability and progress tracking.

---

## Credits

Built by the iCloud Drive Downloader community. Powered by [pyicloud](https://github.com/picklepete/pyicloud).

**Star this repo** if it helped you! Questions? Check [docs/](docs/) or open an issue.

See [docs/README.md](docs/README.md) for the full documentation index.
