# iCloud Drive Downloader (Enhanced)

A robust, feature-rich Python script to download your entire iCloud Drive with enterprise-grade reliability, security, and performance optimizations.

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

## Installation

```bash
# Clone or download this repository
cd "iCloud Downloader"

# Install dependencies
pip install -r requirements.txt
```

## Quick Start

### Basic Usage
```bash
# Download entire iCloud Drive
python3 icloud_downloader.py

# Custom destination with more workers
python3 icloud_downloader.py -d /mnt/backup -w 5

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

## License

This script is provided as-is for personal use. Use responsibly and in accordance with Apple's Terms of Service.

## Changelog

### Phase 3 (Current)
- Signal handling for graceful shutdown
- Max-depth and max-items safety guardrails
- Config file support (JSON)
- Environment variable credentials
- Configurable log levels

### Phase 2
- Include/exclude pattern filtering
- Size threshold filtering
- Dry-run preview mode
- Structured JSONL logging
- Progress bars with tqdm
- Statistics tracking

### Phase 1
- Manifest-based resume capability
- HTTP range request support
- Directory listing cache
- Concurrent downloads
- Smart file skipping

### Phase 0
- CLI argument parsing
- Path security validation
- Network timeout & error classification
- Exponential backoff with jitter
- Free space preflight check
- Secure file permissions
