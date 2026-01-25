# iCloud Drive Downloader

> **Download entire folders from iCloud Drive** - The functionality Apple should have built into iCloud.com

[![Version](https://img.shields.io/badge/version-4.0.0-blue.svg)](CHANGELOG.md)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![Code Quality: A+](https://img.shields.io/badge/code%20quality-A+-brightgreen.svg)](docs/development/CODE_REVIEW_REPORT.md)
[![Tests: 63 Passing](https://img.shields.io/badge/tests-63%20passing-success.svg)](tests/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## Why This Tool Exists

**Apple makes it unnecessarily difficult to download your own data.**

When you need to retrieve files from iCloud Drive, you quickly discover that **Apple's iCloud web interface does not support downloading entire folders**—you can only download individual files or manually select multiple files one by one. For large or nested folder structures, this is impractical at best and impossible at worst.

### The Problem: No Built-In Solution

Apple does not provide a straightforward way to download full folders from your iCloud Drive. Your limited options are:

#### 1. **privacy.apple.com** (Days of Waiting)
Apple's data export portal can take **days or even weeks** to prepare your data archive, and you have no control over what gets included or how it's organized.

#### 2. **iPhone/iPad Workarounds** (Manual & Time-Consuming)
- Open Files app, navigate to your folder
- Long-press → Compress to create a .zip file
- Share via AirDrop or upload to another cloud service
- **Limitation**: Extremely slow for large folders, requires manual intervention for each folder

#### 3. **macOS Finder Method** (Requires Syncing Everything)
- Enable iCloud Drive sync on a Mac
- Wait for everything to download (fills local storage)
- Manually copy folders to external drive
- **Limitation**: Forces you to sync your entire iCloud Drive locally, consuming disk space you may not have

#### 4. **Manual File Selection** (Impractical)
- Select files one-by-one at iCloud.com
- Click download for each batch
- Manually recreate folder structure
- **Limitation**: Completely impractical for nested directories with hundreds or thousands of files

### The Core Issue

This lack of functionality is not an oversight—it's a **documented limitation** that has frustrated users for years. Apple has designed iCloud Drive with a sync-first philosophy that assumes you're always using their ecosystem devices with local storage to spare.

**But what if you:**
- Need to migrate away from iCloud?
- Are on Linux or Windows and can't use macOS Finder?
- Simply want to download a folder right now without waiting days for it to be approved?

**That's where this tool comes in.**

### This Tool's Philosophy

**You own your data. You should be able to download it efficiently, on your terms.**

This script provides what Apple should have built into iCloud.com from day one: a straightforward, reliable way to download entire folder structures from iCloud Drive with:

- **Zero sync requirements** - Download directly
- **Resume capability** - Interrupted downloads pick up where they left off
- **Selective downloading** - Choose exactly what you want with pattern filters
- **Speed & efficiency** - Concurrent downloads with configurable workers
- **Full transparency** - Detailed logging and progress tracking
- **Your timeline** - Minutes or hours, not days or weeks

This is not about circumventing Apple's services—it's about exercising your fundamental right to efficiently access data you already own.

---

## Features

### Phase 0: Foundation & Security ✅
- **CLI Interface**: Comprehensive argparse-based command-line interface
- **Path Security**: Strict validation prevents path traversal attacks
- **Network Resilience**: Timeout configuration, retryable error classification, exponential backoff with jitter
- **Free Space Check**: Preflight validation with interactive override
- **Secure Permissions**: Files (0o600) and directories (0o700) created with owner-only access

### Phase 1: Performance & Resume ✅
- **Manifest Tracking**: JSON-based state persistence for reliable resume capability
- **Range Requests**: Resume interrupted downloads from partial bytes
- **Directory Caching**: Reduces API calls by caching folder listings
- **Concurrent Downloads**: ThreadPoolExecutor with configurable worker pool (default: 3)
- **Smart Skipping**: Automatically skips completed files based on manifest

### Phase 2: Filtering & UX ✅
- **Pattern Filters**: Include/exclude files using glob patterns (supports multiple)
- **Size Thresholds**: Filter by minimum and maximum file size
- **Dry-Run Mode**: Preview what would be downloaded without transferring
- **Structured Logging**: JSON Lines format with detailed event tracking
- **Progress Bars**: Visual feedback via tqdm (optional, graceful fallback)
- **Statistics**: Comprehensive summary (files, bytes, speed, elapsed time)

### Phase 3: Operational Hardening ✅
- **Signal Handling**: Graceful shutdown on SIGINT/SIGTERM with state preservation
- **Safety Guardrails**: `--max-depth` and `--max-items` for controlled downloads
- **Config Files**: JSON-based configuration for reusable settings
- **Environment Variables**: Credentials via `ICLOUD_APPLE_ID` and `ICLOUD_PASSWORD`
- **Log Levels**: Configurable logging (DEBUG, INFO, WARNING, ERROR)

### Phase 4: User Experience ✅ NEW!
- **Interactive Setup Wizard**: First-time user friendly configuration with `--wizard`
- **Preset Configurations**: Quick-start presets (`--preset photos`, `documents`, `quick-test`, `large-files`)
- **Colorized Output**: Color-coded success/warning/error messages for easy scanning
- **Human-Readable Sizes**: Display "2.3 GB" instead of "2458931200 bytes"
- **Progress Estimates**: Real-time ETA and speed calculations
- **Smart Confirmations**: Prompts before large downloads with size estimates
- **Better Error Messages**: Actionable suggestions with links to help resources
- **Helpful Tips**: Context-sensitive tips throughout the interface

## Installation

```bash
# Clone or download this repository
cd "iCloud Downloader"

# Install dependencies
pip install -r requirements.txt

# Optional: Install test dependencies
pip install -r requirements-test.txt

# Check version
python3 icloud_downloader.py --version
```

## Testing

This project includes a comprehensive test suite covering all core functionality.

### Run all tests
```bash
# Using unittest (no dependencies)
python3 -m unittest discover tests/ -v

# Using pytest (recommended, install requirements-test.txt)
python3 -m pytest tests/ -v

# With coverage report
python3 -m pytest tests/ --cov=icloud_downloader --cov-report=html
```

### Type checking
```bash
# Install mypy (included in requirements-test.txt)
python3 -m mypy icloud_downloader.py --check-untyped-defs
```

See [tests/README.md](tests/README.md) for detailed testing documentation.

## Quick Start

### 🎯 Simplest Way: Just Run It!

**No command-line arguments needed!** Just run the script and it will guide you through everything:

```bash
python3 icloud_downloader.py
```

The script will automatically start in **interactive mode** and walk you through:
1. **Apple ID** - Enter your iCloud email
2. **App-Specific Password** - Generate one at [appleid.apple.com](https://appleid.apple.com/account/manage) (with clickable instructions)
3. **Download Location** - Where to save your files (default: `~/iCloud_Drive_Download`)
4. **What to Download** - Everything, photos only, documents only, quick test, or custom filters
5. **Performance** - How many concurrent downloads (1-10 workers, default: 3)
6. **Preview Mode** - Option to see what will be downloaded first (recommended!)
7. **Save Config** - Optionally save your choices for next time

**That's it!** No memorizing command-line flags. No reading documentation first. Just run and follow the prompts.

### 🔄 Returning Users

If you've already configured things once, you can:

```bash
# Use your saved configuration
python3 icloud_downloader.py --config my_config.json

# Or use command-line arguments directly
python3 icloud_downloader.py -d /mnt/backup -w 5
```

### 🚀 Quick Presets

Use predefined configurations for common scenarios:

```bash
# Download only photos and videos
python3 icloud_downloader.py --preset photos

# Download only documents
python3 icloud_downloader.py --preset documents

# Safe test run (first 50 files, 2 levels deep)
python3 icloud_downloader.py --preset quick-test

# Only files larger than 100MB
python3 icloud_downloader.py --preset large-files
```

### Advanced Command-Line Usage

For automation or scripts, you can use command-line arguments directly:

```bash
# Custom destination with more workers
python3 icloud_downloader.py -d /mnt/backup -w 5 --skip-confirm

# Preview before downloading
python3 icloud_downloader.py --dry-run
```

### With Filters
```bash
# Only download photos
python3 icloud_downloader.py --include "*.jpg" --include "*.png" --include "*.heic"

# Exclude temporary files
python3 icloud_downloader.py --exclude "*.tmp" --exclude "*/Cache/*"

# Files between 1MB and 100MB
python3 icloud_downloader.py --min-size 1048576 --max-size 104857600
```

## ✨ User-Friendly Features

### Fully Interactive Mode (Default)

**No configuration needed!** When you run the script without arguments, it automatically enters interactive mode:

```bash
python3 icloud_downloader.py
```

You'll be guided through every step with:
- **Clear questions** with sensible defaults in [brackets]
- **Helpful tips** at each stage (💡 markers)
- **Progress indicators** showing what's happening
- **Color-coded output** for easy scanning
- **App-specific password guide** with direct link to Apple's portal
- **Preview option** to check before downloading

Perfect for:
- First-time users who want guidance
- When trying different configurations
- Anyone who prefers not to memorize CLI flags

### Manual Interactive Mode

You can also explicitly request the wizard:

```bash
python3 icloud_downloader.py --wizard
```

Features:
- Step-by-step guided setup
- Plain-English explanations of each option
- Saves configuration for reuse
- Includes helpful tips and links

### Preset Configurations

Skip the complex command-line arguments with presets:

| Preset | Description | Use Case |
|--------|-------------|----------|
| `--preset photos` | Photos and videos only | Backup your photo library |
| `--preset documents` | Document files only | Download work files |
| `--preset quick-test` | First 50 files, 2 levels | Test before full download |
| `--preset large-files` | Files >100MB | Download large media files |

Presets can be combined with other options:
```bash
# Photos preset with custom destination
python3 icloud_downloader.py --preset photos -d /mnt/photos

# Quick test with 10 workers
python3 icloud_downloader.py --preset quick-test -w 10
```

### Colorized Output

Color-coded messages make it easier to understand what's happening:
- 🟢 **Green**: Success messages (✓ Downloaded, ✓ Connected)
- 🟡 **Yellow**: Warnings and tips (⚠️ Low disk space, 💡 Tip: ...)
- 🔴 **Red**: Errors (✗ Failed to download)
- 🔵 **Cyan**: Information (file paths, settings)

Disable colors if needed:
```bash
python3 icloud_downloader.py --no-color
```

### Human-Readable Sizes

All file sizes are now shown in friendly formats:
- "2.3 GB" instead of "2458931200 bytes"
- "543.2 MB downloaded of 1.2 GB (45%)"
- "Average speed: 12.5 MB/s"

### Smart Confirmations

Before large downloads, you'll see a summary and confirmation prompt:

```
============================================================
Download Summary:
  Estimated files: 1,245
  Estimated size:  23.5 GB
============================================================

⚠️  Warning: This is a large download!
   Make sure you have enough disk space and a stable connection.

Continue with download? [Y/n]:
```

Skip confirmations with `--skip-confirm` for automated usage.

### Better Error Messages

When things go wrong, you'll get actionable suggestions:

```
✗ Login failed!

Possible causes:
  1. Wrong password - Double-check your app-specific password
  2. Not an app-specific password - Must generate one at:
     https://appleid.apple.com/account/manage
  3. 2FA required - Set up two-factor authentication first
  4. Network issue - Check your internet connection

💡 Tip: Try creating a new app-specific password
```

### Advanced Options
```bash
# Resume with logging and progress
python3 icloud_downloader.py --log download.log.jsonl -w 10

# Safe trial run (max 100 files, depth 2)
python3 icloud_downloader.py --max-items 100 --max-depth 2 --dry-run

# Use config file
python3 icloud_downloader.py --config my_settings.json
```

## Configuration

### Create Config File
```bash
# Save current options to reusable config
python3 icloud_downloader.py --save-config my_config.json \
  --workers 5 \
  --include "*.pdf" \
  --exclude "*/temp/*" \
  --max-depth 3
```

### Example Config File
```json
{
  "destination": "/mnt/icloud_backup",
  "workers": 5,
  "retries": 5,
  "timeout": 120,
  "include": ["*.jpg", "*.png", "Documents/*"],
  "exclude": ["*.tmp", "*/Cache/*"],
  "max_depth": 4,
  "log_level": "INFO"
}
```

### Use Config
```bash
python3 icloud_downloader.py --config my_config.json
# CLI args override config file values
python3 icloud_downloader.py --config my_config.json --workers 10
```

## Environment Variables

For automated/non-interactive use:

```bash
export ICLOUD_APPLE_ID="your.email@example.com"
export ICLOUD_PASSWORD="your-app-specific-password"
python3 icloud_downloader.py
```

**Security Warning**: Only use environment variables in secure, trusted environments. Never commit credentials to version control.

## CLI Options Reference

### User Experience Options ✨ NEW
- `--wizard`: Run interactive setup wizard
- `--preset`: Use preset configuration (`photos`, `documents`, `quick-test`, `large-files`)
- `--no-color`: Disable colored output
- `--skip-confirm`: Skip confirmation prompt for large downloads

### Core Options
- `--destination, -d`: Download directory (default: `~/iCloud_Drive_Download`)
- `--retries, -r`: Max retries per file (default: 3)
- `--timeout, -t`: Network timeout in seconds (default: 60)
- `--chunk-size, -c`: Download chunk size in bytes (default: 8192)
- `--workers, -w`: Concurrent download workers (default: 3)

### Resume & Mode
- `--no-resume`: Disable resume, start fresh
- `--sequential`: Disable concurrency, download one-by-one
- `--dry-run`: Preview without downloading

### Filters
- `--include`: Include pattern (glob, repeatable)
- `--exclude`: Exclude pattern (glob, repeatable)
- `--min-size`: Minimum file size in bytes
- `--max-size`: Maximum file size in bytes
- `--max-depth`: Maximum directory depth
- `--max-items`: Maximum number of items (safety limit)

### Logging & Output
- `--log`: Structured JSONL log file path
- `--log-level`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `--verbose, -v`: Enable verbose output
- `--no-progress`: Disable progress bars

### Configuration
- `--config`: Load settings from JSON file
- `--save-config`: Save options to JSON file and exit
- `--min-free-space, -f`: Minimum free space in GB (default: 1)

## Usage Examples

### Backup Specific Folders
```bash
# Only Documents and Photos
python3 icloud_downloader.py --include "Documents/*" --include "Photos/*"
```

### Large Media Files Only
```bash
# Files larger than 10MB
python3 icloud_downloader.py --min-size 10485760 --include "*.mp4" --include "*.mov"
```

### Resume Interrupted Download
```bash
# Simply run again - manifest automatically resumes
python3 icloud_downloader.py
```

### Safe Testing
```bash
# Preview first 50 items, max 2 levels deep
python3 icloud_downloader.py --dry-run --max-items 50 --max-depth 2
```

### High-Performance Download
```bash
# 10 workers, structured logging, no progress bars
python3 icloud_downloader.py -w 10 --log fast_download.log.jsonl --no-progress
```

### Graceful Shutdown
```bash
# Press Ctrl+C during download
# Script saves progress and exits cleanly
# Resume by running again
```

## Output & Logs

### Console Output
```
--- iCloud Drive Downloader (Enhanced - Phase 3) ---
Configuration:
  Destination: /home/user/iCloud_Drive_Download
  Max retries: 3
  Timeout: 60s
  Workers: 3
  Mode: Concurrent
  Resume: Enabled

Statistics:
  Total files: 1,245
  Completed: 1,180
  Skipped: 52
  Failed: 13
  Bytes downloaded: 4,582,930,428
  Elapsed time: 342.8s
  Average speed: 12.76 MB/s
```

### Structured Log (JSONL)
```json
{"timestamp": "2025-12-14T10:30:45.123456", "event": "session_start", "config": {...}}
{"timestamp": "2025-12-14T10:30:46.234567", "event": "file_completed", "file": "photo.jpg", "bytes": 2048576, "attempts": 1}
{"timestamp": "2025-12-14T10:30:47.345678", "event": "file_failed", "file": "video.mp4", "error": "Connection timeout", "attempts": 3}
{"timestamp": "2025-12-14T10:35:22.456789", "event": "session_end", "summary": {...}}
```

### Manifest File (`.icloud_download_manifest.json`)
Tracks download state for resume capability:
```json
{
  "files": {
    "/path/to/file.jpg": {
      "status": "complete",
      "bytes_downloaded": 2048576,
      "total_bytes": 2048576,
      "last_updated": "2025-12-14T10:30:46.234567"
    }
  },
  "metadata": {
    "created": "2025-12-14T10:30:45.123456"
  }
}
```

## Security Best Practices

1. **App-Specific Password**: Use Apple app-specific passwords, not your main account password
2. **File Permissions**: All files/dirs created with restrictive permissions (owner-only)
3. **Credentials**: Avoid storing passwords in scripts or config files
4. **Environment Variables**: Only use in secure, non-shared environments
5. **Config Files**: Automatically set to 0o600 (owner read/write only)

## Troubleshooting

### Authentication Issues
- Use app-specific password from appleid.apple.com
- Ensure 2FA is configured on your Apple ID
- Check network connectivity

### Download Failures
- Increase `--retries` and `--timeout` for unstable connections
- Use `--sequential` mode instead of concurrent
- Check `--log` output for detailed error information

### Performance
- Increase `--workers` for faster downloads (don't exceed 10)
- Decrease `--chunk-size` for better resume granularity
- Use `--no-progress` to reduce overhead

### Resume Not Working
- Ensure manifest file exists (`.icloud_download_manifest.json`)
- Don't use `--no-resume` flag
- Check file permissions on manifest

## Requirements

- Python 3.7+
- `pyicloud==1.0.0`
- `requests>=2.31.0`
- `tqdm>=4.66.0` (optional, for progress bars)

### Development Requirements (Optional)
- `pytest>=7.4.0` - Test runner
- `pytest-cov>=4.1.0` - Coverage reporting
- `mypy>=1.7.0` - Static type checking

## Documentation

- **[Quick Start Guide](docs/QUICK_START.md)** - Get up and running in 5 minutes
- **[Configuration Examples](examples/README.md)** - Sample configs for common use cases
- **[Test Suite Documentation](tests/README.md)** - Running tests and coverage
- **[Development Docs](docs/README.md)** - Implementation details and code reviews
- **[Changelog](CHANGELOG.md)** - Full version history

## Code Quality

This project includes:
- ✅ **Comprehensive test suite** (63 tests covering all core functionality)
- ✅ **Type hints** throughout codebase for better IDE support and safety
- ✅ **Thread-safe** operations with proper locking
- ✅ **Security-first** design with path validation and secure permissions
- ✅ **A+ code quality** (see [Code Review Report](docs/development/CODE_REVIEW_REPORT.md))

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing guidelines, and code patterns.

This is a single-file Python utility designed for portability. See [.github/copilot-instructions.md](.github/copilot-instructions.md) for detailed development patterns and conventions.

## License

MIT License - See [LICENSE](LICENSE) for details.

This script is provided for personal use. Use responsibly and in accordance with Apple's Terms of Service.

## Project Structure

```
├── icloud_downloader.py          # Main application (1930 lines)
├── requirements.txt               # Dependencies
├── README.md                      # You are here
├── docs/                          # Documentation
├── examples/                      # Config examples
├── tests/                         # Test suite (63 tests)
├── scripts/                       # Utility scripts
└── archive/                       # Archived/deprecated files
```

See [docs/README.md](docs/README.md) for complete documentation index.

