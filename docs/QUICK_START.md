# Quick Start Guide

## Installation

```bash
# Install core dependencies
pip install -r requirements.txt

# Optional: Install test dependencies
pip install -r requirements-test.txt
```

## Basic Usage

```bash
# Download entire iCloud Drive
python3 icloud_downloader.py

# Custom destination
python3 icloud_downloader.py -d /mnt/backup

# Preview before downloading
python3 icloud_downloader.py --dry-run
```

## Testing

```bash
# Run all tests
python3 -m unittest discover tests/ -v

# Run specific test
python3 tests/test_filters.py
```

## Using Configuration Files

```bash
# Use example config
python3 icloud_downloader.py --config examples/photos-only-config.json

# Save your settings
python3 icloud_downloader.py --workers 5 --include "*.pdf" --save-config my-config.json
```

## Common Workflows

### Backup Photos Only
```bash
python3 icloud_downloader.py \
  --include "*.jpg" --include "*.png" --include "*.heic" \
  --exclude "*/thumbnails/*" \
  --workers 10 \
  -d /mnt/photos-backup
```

### Large Files Only
```bash
python3 icloud_downloader.py \
  --min-size 104857600 \
  --sequential \
  --retries 10 \
  -d /mnt/large-files
```

### Safe Trial Run
```bash
python3 icloud_downloader.py \
  --dry-run \
  --max-items 100 \
  --max-depth 2
```

## Environment Variables

```bash
export ICLOUD_APPLE_ID="user@example.com"
export ICLOUD_PASSWORD="app-specific-password"
python3 icloud_downloader.py
```

## Getting Help

```bash
# Show all options
python3 icloud_downloader.py --help

# Check version/syntax
python3 -m py_compile icloud_downloader.py
```

## Documentation

- [README.md](README.md) - Complete documentation
- [tests/README.md](tests/README.md) - Testing guide
- [examples/README.md](examples/README.md) - Configuration examples
- [CHANGELOG.md](CHANGELOG.md) - Version history
- [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) - Recent improvements
