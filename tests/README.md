# iCloud Downloader Test Suite

Current automated coverage for the iCloud Downloader utility.

## Running Tests

### Run all tests

```bash
python3 -m pytest tests/ -v
```

### Run specific test file

```bash
python3 -m pytest tests/test_filters.py -v
python3 tests/test_filters.py  # Direct execution
```

### Run with coverage

```bash
python3 -m pytest tests/ --cov=icloud_downloader_lib --cov=icloud_downloader --cov-report=html
```

## Test Structure

The suite is split by behavior area instead of one monolithic test module.

- Wrapper and CLI flow: `test_wrapper_main.py`, `test_cli_config.py`, `test_cli_support.py`, `test_app_cli_edges.py`, `test_app_migrate.py`
- Filtering, path safety, and presentation: `test_filters.py`, `test_path_security.py`, `test_presentation.py`, `test_reporting.py`
- Auth and 2FA: `test_session_auth.py`, `test_session_edges.py`, `test_session_cleanup.py`, `test_two_factor.py`, `test_two_factor_refresh.py`, `test_app_privacy.py`, `test_privacy.py`
- Download runtime and traversal: `test_execution_helpers.py`, `test_execution_runtime.py`, `test_execution_edges.py`, `test_transfer.py`, `test_transfer_edges.py`, `test_traversal.py`, `test_traversal_edges.py`
- Photos Library: `test_photos_executor.py`, `test_photos_navigator.py`
- Wizard and preferences: `test_wizard.py`, `test_wizard_preferences.py`
- Crypto and session encryption: `test_crypto.py`
- Inventory, cache, state, and retry: `test_inventory.py`, `test_inventory_cache.py`, `test_cache_selector_workflow.py`, `test_retry_logic.py`, `test_retry_edges.py`, `test_state_runtime.py`, `test_cache.py`, `test_manifest.py`, `test_stats.py`
- Integration and repo health: `test_integration.py`, `test_loc_budget.py`

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
- Streamed write and resume behavior
- Wizard config persistence and main flow interaction

⚠️ **Live-only paths not covered in CI**

- Real pyicloud API calls against a live iCloud account
- End-to-end network behavior beyond the mocked retry and resume flows

✅ **Covered with mocks or isolated filesystem tests**

- 2FA code flows and security-key challenges
- Local session status inspection
- Transfer retry exhaustion and rate-limit handling
- Manifest persistence, secure permissions, and path validation

## Adding New Tests

1. Create new test file in `tests/` directory
2. Follow naming convention: `test_<module>.py`
3. Import necessary modules from parent directory
4. Use unittest.TestCase for test classes
5. Add descriptive docstrings to test methods

## Dependencies

Tests are written with `unittest` and run through `pytest`.

- `pytest` - Test runner
- `pytest-cov` - Coverage reporting
- `pytest-timeout` - Timeout guardrails
- `unittest.mock` - Mocking and isolation

Optional:

- `mypy` - Type checking during local verification
