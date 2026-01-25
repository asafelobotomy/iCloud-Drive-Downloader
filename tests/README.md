# iCloud Downloader Test Suite

Comprehensive test coverage for the iCloud Downloader utility.

## Running Tests

### Run all tests
```bash
python3 -m pytest tests/ -v
```

Or using unittest:
```bash
python3 -m unittest discover tests/
```

### Run specific test file
```bash
python3 -m pytest tests/test_filters.py -v
python3 tests/test_filters.py  # Direct execution
```

### Run with coverage
```bash
pip install pytest pytest-cov
python3 -m pytest tests/ --cov=icloud_downloader --cov-report=html
```

## Test Structure

- **test_filters.py** - FileFilter class tests (pattern matching, size filters)
- **test_manifest.py** - DownloadManifest tests (state persistence, resume capability)
- **test_path_security.py** - Security validation tests (path traversal, sanitization)
- **test_retry_logic.py** - Retry and backoff mechanism tests
- **test_cache.py** - DirectoryCache thread-safety tests
- **test_stats.py** - DownloadStats counter and thread-safety tests
- **test_integration.py** - Integration tests with dry-run mode

## Test Coverage Areas

✅ **Unit Tests**
- FileFilter: pattern matching, size thresholds
- DownloadManifest: state persistence, recovery
- Path security: sanitization, traversal prevention
- Retry logic: exponential backoff, error classification
- DirectoryCache: thread-safe caching
- DownloadStats: counter accuracy, thread-safety

✅ **Integration Tests**
- Dry-run mode functionality
- Filter integration with download logic
- Manifest skip behavior
- Component interaction

⚠️ **Not Covered** (requires mocking or live API)
- Actual pyicloud API calls
- Real file downloads
- Network failures and retries
- 2FA authentication flow
- Signal handling (SIGINT/SIGTERM)

## Adding New Tests

1. Create new test file in `tests/` directory
2. Follow naming convention: `test_<module>.py`
3. Import necessary modules from parent directory
4. Use unittest.TestCase for test classes
5. Add descriptive docstrings to test methods

## Dependencies

Tests use only Python standard library:
- `unittest` - Test framework
- `tempfile` - Temporary file/directory creation
- `threading` - Concurrency testing
- `unittest.mock` - Mocking for integration tests

Optional:
- `pytest` - Alternative test runner with better output
- `pytest-cov` - Coverage reporting
