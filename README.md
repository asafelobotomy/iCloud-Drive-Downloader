# iCloud Drive Downloader

> **Download entire folders from iCloud Drive in minutes.** Simple, fast, and reliable.

[![Version](https://img.shields.io/badge/version-4.0.0-blue.svg)](CHANGELOG.md)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![Tests: 63 Passing](https://img.shields.io/badge/tests-63%20passing-success.svg)](tests/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**What it does:** Downloads your entire iCloud Drive (or selected folders/files) to your local machine. Includes resume capability, filters, concurrent downloads, and an interactive setup wizard.

**Why it exists:** Apple's iCloud.com doesn't let you download entire folders—only individual files. This tool solves that.

---

## Quick Start

### Installation

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

The script will guide you through 7 simple questions:
1. Your Apple ID
2. App-specific password (with setup link)
3. Where to save files
4. What to download (everything, photos, documents, or custom)
5. Performance settings
6. Preview mode (recommended)
7. Save configuration

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
python3 icloud_downloader.py --config my_backup.json
```

### Environment Variables (Optional)

Skip credential prompts:
```bash
export ICLOUD_APPLE_ID="user@example.com"
export ICLOUD_PASSWORD="xxxx-xxxx-xxxx-xxxx"
python3 icloud_downloader.py
```

---

## Authentication

### App-Specific Password Required

**Important:** You need an **app-specific password**, not your regular Apple password.

1. Go to [appleid.apple.com/account/manage](https://appleid.apple.com/account/manage)
2. Sign in with your Apple ID
3. Navigate to: **Security** → **App-Specific Passwords**
4. Click **Generate** and copy the password

The script will prompt you for this when it runs.

### Two-Factor Authentication (2FA)

If 2FA is enabled (recommended), the script will:
1. Prompt you for the 6-digit code
2. Send it to your trusted Apple device
3. Optionally trust the session to avoid repeated 2FA prompts

---

## CLI Reference

### Essential Flags

| Flag | Short | Description |
|------|-------|-------------|
| `--destination <path>` | `-d` | Download location (default: ~/iCloud_Drive_Download) |
| `--workers <1-10>` | `-w` | Concurrent downloads (default: 3) |
| `--dry-run` | - | Preview without downloading |
| `--preset <name>` | - | Use preset (photos, documents, quick-test, large-files) |
| `--wizard` | - | Interactive setup |

### Filters

| Flag | Description |
|------|-------------|
| `--include <pattern>` | Include files matching pattern (glob, repeatable) |
| `--exclude <pattern>` | Exclude files matching pattern (glob, repeatable) |
| `--min-size <bytes>` | Minimum file size |
| `--max-size <bytes>` | Maximum file size |
| `--max-depth <num>` | Maximum folder depth |
| `--max-items <num>` | Maximum number of files |

### Advanced

| Flag | Description |
|------|-------------|
| `--config <file>` | Load saved configuration |
| `--save-config <file>` | Save current settings to file |
| `--retries <num>` | Retry attempts per file (default: 3) |
| `--timeout <sec>` | Network timeout (default: 60) |
| `--sequential` | Download one file at a time |
| `--no-resume` | Start fresh (ignore previous progress) |
| `--log <file>` | Log events to JSONL file |
| `--no-color` | Disable colored output |
| `--skip-confirm` | Skip download confirmation |
| `--version` | Show version and exit |

Run `python3 icloud_downloader.py --help` for complete list.

---

## Troubleshooting

### Login Failed
**Cause:** Wrong password or not using app-specific password  
**Solution:** Generate a new app-specific password at [appleid.apple.com](https://appleid.apple.com/account/manage)

### 2FA Code Not Working
**Cause:** Code expired or incorrect  
**Solution:** Request a new code—they expire quickly

### Download Interrupted
**Cause:** Network issue, Ctrl+C pressed, computer crashed  
**Solution:** Just run the script again—it automatically resumes from where it stopped

### Out of Disk Space
**Cause:** Not enough free space for download  
**Solution:** Free up space or change destination with `-d /path/to/larger/drive`

### Slow Downloads
**Cause:** Network speed or too few workers  
**Solutions:**
- Increase workers: `--workers 10`
- Check network connection
- Try during off-peak hours

### Want to Stop Safely
**Action:** Press **Ctrl+C once** (saves progress for resume)  
**Force quit:** Press **Ctrl+C twice** (may lose some progress)

---

## Documentation

- **[Quick Reference](docs/QUICK_REFERENCE.md)** - Cheat sheet with common commands
- **[Interactive Mode Guide](docs/INTERACTIVE_MODE.md)** - Detailed walkthrough
- **[Rate Limiting & Throttling](docs/RATE_LIMITING_AND_THROTTLING.md)** - Apple's policies and best practices
- **[Configuration Examples](examples/README.md)** - Sample config files
- **[Full Documentation](docs/README.md)** - Complete docs index
- **[Changelog](CHANGELOG.md)** - Version history

---

## Testing

Run the comprehensive test suite:

```bash
# Using unittest (no extra dependencies)
python3 -m unittest discover tests/ -v

# Using pytest (install requirements-test.txt first)
python3 -m pytest tests/ -v

# With coverage report
python3 -m pytest tests/ --cov=icloud_downloader --cov-report=html
```

**63 tests** covering filters, security, resume capability, retries, caching, and more.

---

## Requirements

- **Python 3.7+**
- `pyicloud==1.0.0` - iCloud API
- `requests>=2.31.0` - HTTP library
- `tqdm>=4.66.0` - Progress bars (optional)

### Optional (Development)
- `pytest>=7.4.0` - Testing
- `pytest-cov>=4.1.0` - Coverage reports
- `mypy>=1.7.0` - Type checking

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development setup
- Testing guidelines
- Code patterns and conventions
- Single-file architecture notes

This project includes comprehensive type hints, thread-safe operations, and an A+ security audit.

---

## Project Structure

```
├── icloud_downloader.py       # Main application (1930 lines)
├── requirements.txt            # Dependencies
├── tests/                      # 63-test suite
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

