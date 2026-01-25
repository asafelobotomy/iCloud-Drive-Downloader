# Copilot / AI Agent Instructions

This repository is a single-file Python utility (`icloud_downloader.py`) with supporting docs. The instructions below capture the key architecture, developer workflows, and project-specific conventions an AI coding agent should follow to be immediately productive.

## Big Picture

**Single-file architecture:** `icloud_downloader.py` implements the complete CLI application (login, traversal, download, resume). The script is intentionally monolithic for portability — avoid splitting into modules unless absolutely necessary.

**Phased implementation:** Phase 0-3 documented in `README.md` (historical notes in `archive/dev-notes/PHASE0_CHANGES.md`):
- Phase 0: Foundation (security, CLI, path validation, retry logic)
- Phase 1: Performance (manifest resume, range requests, caching, concurrency)
- Phase 2: Filtering & UX (patterns, dry-run, logging, progress bars)
- Phase 3: Operational hardening (signals, safety guardrails, config files)
- Phase 4: User Experience (interactive mode, presets, colors, confirmations)

**Core components** (all in `icloud_downloader.py`):
- `DownloadManifest` — JSON-based resume state tracking (`complete`, `partial`, `failed` statuses per file)
- `FileFilter` — pattern-based include/exclude with size thresholds (using `fnmatch` glob patterns)
- `DirectoryCache` — thread-safe cache for `node.dir()` listings to reduce API calls
- `StructuredLogger` — JSONL event logger with thread-safe writes (timestamp + event + payload structure)
- `DownloadStats` — thread-safe counters (files_total, files_completed, files_skipped, files_failed, bytes)
- `ShutdownHandler` — signal-based graceful shutdown (SIGINT once=graceful, twice=force quit)
- `download_file()` — single-file downloader with retry logic and resume capability via HTTP range requests
- `download_node()` — recursive directory traversal (sequential mode)
- `collect_download_tasks()` + `download_worker()` — concurrent mode with `ThreadPoolExecutor`

**Dual execution modes:**
- Sequential mode (`--sequential`): processes folders/files one-by-one using `download_node()` recursively
- Concurrent mode (default): uses `collect_download_tasks()` to build task list first, then downloads files in parallel via `ThreadPoolExecutor` with configurable workers (default: 3)

## Developer Workflows

**Setup and quick run:**
```bash
pip install -r requirements.txt  # pyicloud==1.0.0, requests, tqdm (optional)
python3 icloud_downloader.py      # prompts for Apple ID/password if not in env
```

**Environment variables** (for automated use):
```bash
export ICLOUD_APPLE_ID="user@example.com"
export ICLOUD_PASSWORD="app-specific-password"
python3 icloud_downloader.py --dry-run
```

**Non-destructive testing patterns:**
```bash
# Preview changes without downloading
python3 icloud_downloader.py --dry-run --max-items 5 --max-depth 1

# Test filters without hitting iCloud
python3 icloud_downloader.py --dry-run --include "*.jpg" --exclude "*/Cache/*"

# Validate logging output
python3 icloud_downloader.py --log test.log.jsonl --dry-run --max-items 10
```

**Resume testing workflow:**
1. Start download: `python3 icloud_downloader.py -d /tmp/test_dl`
2. Interrupt with Ctrl+C (graceful shutdown saves manifest)
3. Resume: `python3 icloud_downloader.py -d /tmp/test_dl` (reads `.icloud_download_manifest.json`)

**Config file workflow:**
```bash
# Save reusable config
python3 icloud_downloader.py --save-config my_config.json --workers 5 --include "*.pdf"

# Use config (CLI args override config values)
python3 icloud_downloader.py --config my_config.json --dry-run
```

## Project-Specific Conventions

**Security-first defaults:**
- All directories: `os.chmod(path, 0o700)` — owner-only rwx
- All files: `os.chmod(path, 0o600)` — owner-only rw
- Config files: saved with `0o600` permissions
- These patterns appear in: `download_node()`, `download_file()`, `DownloadManifest._save()`, `save_config_file()`
- **Critical:** Preserve these `chmod` calls when modifying file/directory creation

**Path safety validation:**
- `validate_path_safety(path, root)` called before all file/directory operations
- Rejects absolute paths and `..` traversal patterns
- Resolves to absolute paths and verifies containment within `root`
- **Critical:** Always validate before `os.makedirs()` or file writes

**Name sanitization:**
- `sanitize_name(name)` normalizes iCloud item names for filesystem safety
- Replaces `os.sep`, null bytes, and control chars with `_`
- Called on all `item_name` values before constructing `local_path`

**Retry and backoff logic:**
- Retryable errors: `RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}` and `RETRYABLE_EXCEPTIONS = (ConnectionError, TimeoutError)`
- `is_retryable_error(exception)` classifies by exception type and HTTP status codes in message
- `calculate_backoff(attempt, base_delay=1.0, max_delay=60.0)` — exponential backoff with ±10% jitter
- Non-retryable errors fail immediately (saves time and preserves partial downloads for resume)

**Threading model:**
- All shared state uses `threading.Lock()` for thread-safety (DownloadStats, StructuredLogger, DirectoryCache, DownloadManifest, ShutdownHandler)
- Concurrent mode: `ThreadPoolExecutor` with default `max_workers=3` (configurable via `--workers`)
- Progress bars (`tqdm`) integrated with thread pool via `pbar.update(1)` in worker callbacks
- Worker function: `download_worker(task)` unpacks task tuple and calls `download_file()` with all parameters

## Integration Points

**pyicloud dependency:**
- `PyiCloudService(apple_id, password)` — login and session management
- 2FA flow: `api.requires_2fa`, `api.validate_2fa_code(code)`, `api.trust_session()`
- Drive API: `api.drive` object, `api.drive.dir()` for top-level items, `api.drive[item_name]` for access
- Node types: `item.type` is `'folder'` or `'file'`
- Folder traversal: `node.dir()` returns list of child names, `node[child_name]` accesses child
- File download: `item.open(stream=True)` returns response, `response.iter_content(chunk_size=N)` for streaming
- **Mock points:** `api.drive`, `node.dir()`, `item.open()`, `response.iter_content()` for testing

**tqdm (optional):**
- Guarded with `TQDM_AVAILABLE` boolean flag
- Falls back to manual progress prints if not installed
- Progress bar created with `tqdm(total=len(tasks), desc="Downloading", unit="file")`
- Updated via `pbar.update(1)` in worker thread after each file completes

**Structured logging:**
- JSONL format: one JSON object per line with `timestamp`, `event`, and event-specific fields
- Common events: `session_start`, `session_end`, `file_completed`, `file_failed`, `file_skipped`, `file_filtered`, `dry_run_file`, `file_resume`
- Thread-safe writes with `self.lock` around file append operations
- Human output goes to `stdout` (via `print`), structured logs to file (via `StructuredLogger.log()`)

## Testing & Validation Strategies

**No automated tests exist** — validate changes manually with these patterns:

1. **Syntax check:** `python3 -m py_compile icloud_downloader.py`
2. **Dry-run validation:** `python3 icloud_downloader.py --dry-run --max-items 10 --max-depth 2`
3. **Filter testing:** `--include "*.jpg" --exclude "*/temp/*"` with `--dry-run`
4. **Concurrency:** test with `--workers 1` (sequential-like) vs `--workers 10` (high concurrency)
5. **Resume behavior:** interrupt with Ctrl+C and restart to verify manifest persistence
6. **Retry logic:** simulate with poor network or by adding artificial failures in code
7. **Logging:** inspect `.log.jsonl` output for correct JSONL structure and event types

**When modifying download logic:**
- Test both sequential (`--sequential`) and concurrent (default) modes
- Verify `collect_download_tasks()` and `download_node()` stay semantically consistent
- Check thread-safety if adding new shared state (use `threading.Lock()`)

## Key Files

- `icloud_downloader.py` — entire implementation (~1930 lines)
- `README.md` — comprehensive usage guide, all CLI options, examples
- `CHANGELOG.md` — version history and release notes
- `requirements.txt` — dependencies (pyicloud==1.0.0, requests, tqdm)
- `requirements-test.txt` — testing dependencies (pytest, coverage, mypy)
- `.icloud_download_manifest.json` — generated resume state file (JSON, created in destination dir)
- `docs/` — comprehensive documentation (user guides, dev docs, examples)
- `tests/` — 63-test suite covering all core functionality
- `archive/` — deprecated and historical files (not actively maintained)

## Common Patterns to Follow

When adding new features:
1. Add CLI argument in `parse_arguments()` with default constant at top of file
2. Merge CLI arg with config file value in `main()` using `get_value()` helper
3. Pass new config via `config` dict parameter (avoid global state)
4. Add structured log event if tracking is valuable (use `logger.log('event_name', ...data)`)
5. Validate with `--dry-run` and small scope limits before full testing

When modifying file operations:
1. Call `sanitize_name()` on user-provided names
2. Call `validate_path_safety()` before creating paths
3. Set permissions with `os.chmod()` immediately after creation
4. Update manifest status for resume capability (if applicable)
5. Handle retryable vs non-retryable errors correctly

## Need More Details?

For deeper guidance on specific areas, request:
- Unit test stubs and mocking strategies for `pyicloud` objects
- Contributor checklist for adding new filters or download modes
- Debugging strategies for threading issues or API rate limiting
- Examples of extending `StructuredLogger` event types 
