# Changelog

All notable changes to the iCloud Drive Downloader project.

## [Unreleased]

### Changed - Dependency Baseline

- Raised the supported Python runtime to 3.10+ to align with `pyicloud 2.5.0`.
- Bumped the verified runtime dependency baseline to `pyicloud 2.5.0`, `requests 2.33.1+`, `tenacity 9.1.4+`, and `tqdm 4.67.3+`.
- Bumped the verified development dependency baseline to `pytest 9.0.2+`, `pytest-cov 7.1.0+`, `pytest-timeout 2.4.0+`, and `mypy 1.20.0+`.
- Expanded CI to run the verification gate on Python 3.10 and 3.14.

### Changed - Documentation

- Refreshed the quick-start and quick-reference guides for the Python 3.10+ baseline, Photos Library CLI flags, and the current interactive main-menu flow.
- Updated contributor and workspace metadata docs to reflect the modular package coverage command and current runtime guidance.

## [4.0.0] - 2026-01-25

### Added - Phase 4: User Experience Enhancements ✨

- **Fully Interactive Mode (Default)**:
  - Script automatically enters interactive mode when run without arguments
  - No command-line knowledge required - just run and follow prompts
  - Smart auto-detection based on whether significant args are provided
  - Integrated Apple ID and password prompts with validation
  - Helpful tips (💡) and progress indicators throughout
  - Preview mode (dry-run) now recommended by default
- **Interactive Setup Wizard** (`--wizard`):
  - Step-by-step configuration for first-time users
  - Guided prompts for destination, filters, workers, dry-run
  - Optional configuration saving
  - Helpful tips and app-specific password instructions
- **Preset Configurations** (`--preset`):
  - `photos`: Only photo and video files
  - `documents`: Only document files
  - `quick-test`: Safe test with limits (50 items, depth 2)
  - `large-files`: Files larger than 100MB only
- **Colorized Output**:
  - Green for success messages (✓)
  - Yellow for warnings and tips (⚠️ 💡)
  - Red for errors (✗)
  - Cyan for information (paths, settings)
  - `--no-color` option to disable
- **Human-Readable Formats**:
  - File sizes: "2.3 GB" instead of "2458931200 bytes"
  - Download speeds: "12.5 MB/s"
  - Time estimates: "2h 15m 30s"
- **Smart Confirmations**:
  - Pre-download summary with file count and total size estimates
  - Warning for downloads >10GB
  - `--skip-confirm` to bypass for automation
- **Enhanced Error Messages**:
  - Actionable suggestions for common problems
  - Direct links to Apple ID management
  - Context-sensitive troubleshooting tips
- **Progress Enhancements**:
  - Real-time ETA calculations
  - Current speed tracking
  - Progress percentage display
- Documentation improvements:
  - Expanded README with wizard and preset examples
  - New "User-Friendly Features" section
  - Updated CLI options reference
  - Better quick-start guide

### Added - Testing & Code Quality

- **Comprehensive test suite** (433+ tests) covering:
  - FileFilter pattern matching and size filters
  - DownloadManifest state persistence and recovery
  - Path security validation (sanitization, traversal prevention)
  - Retry logic with exponential backoff
  - DirectoryCache thread-safety
  - DownloadStats accuracy and concurrency
  - Integration tests with dry-run mode
- **Type hints** throughout the codebase for better IDE support and type safety
- **Test documentation** in `tests/README.md`
- **Test requirements** file (`requirements-test.txt`) for development dependencies
- Support for pytest and coverage reporting

### Added - Version Control

- **Centralized version management**:
  - Single source of truth (`__version__` in `icloud_downloader.py`)
  - `--version` CLI flag to display version
  - Version displayed in startup banner
  - Version badge in README
  - Comprehensive version management documentation
- **Version metadata**:
  - `__version__`: Version number (4.0.0)
  - `__author__`: Project contributors
  - `__license__`: MIT License
  - `__description__`: Project description
- **Documentation**:
  - `docs/VERSION_MANAGEMENT.md` - Complete version update guide
  - Semantic versioning guidelines
  - Version history tracking

### Changed - Phase 4

- Enhanced code quality with full type annotations on all classes and functions
- Improved maintainability with comprehensive test coverage
- Modernized output with colors and better formatting
- More intuitive error messages with actionable guidance

### Removed

- Unrelated Docker configuration files (Dockerfile, compose files)
- Unrelated Node.js artifacts (package.json, node_modules)
- `.dockerignore` file (no longer needed)

### Fixed

- All existing functionality preserved and validated through tests

---

## Phase 3 - Operational Hardening

### Added - Phase 3

- Signal handling for graceful shutdown (SIGINT/SIGTERM)
- `--max-depth` safety guardrail for controlled traversal
- `--max-items` safety limit for total file count
- JSON config file support (`--config`, `--save-config`)
- Environment variable support for credentials
- Configurable log levels (DEBUG, INFO, WARNING, ERROR)

---

## Phase 2 - Filtering & UX

### Added - Phase 2

- Include/exclude pattern filtering with glob support
- Size threshold filtering (--min-size, --max-size)
- Dry-run preview mode (--dry-run)
- Structured JSONL logging
- Progress bars with tqdm (optional dependency)
- Comprehensive statistics tracking and reporting

---

## Phase 1 - Performance & Resume

### Added - Phase 1

- Manifest-based resume capability
- HTTP range request support for partial downloads
- Directory listing cache to reduce API calls
- Concurrent downloads with ThreadPoolExecutor
- Smart file skipping based on completion status

---

## Phase 0 - Foundation & Security

### Added - Phase 0

- Comprehensive CLI argument parsing
- Path security validation (traversal prevention)
- Network timeout configuration
- Retryable error classification
- Exponential backoff with jitter for retries
- Free space preflight check
- Secure file permissions (0o600 for files, 0o700 for directories)
- Name sanitization for filesystem safety

---

## Initial Release

### Added - Initial Release

- Basic iCloud Drive download functionality
- 2FA authentication support
- Folder traversal and file downloading
