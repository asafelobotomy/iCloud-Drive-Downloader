---
name: python-testing
description: Write and organize Python tests using pytest — fixtures, parametrize, mocking, and project-appropriate test structure
compatibility: ">=1.4"
---

# Python Testing

> Skill metadata: version "1.0"; license MIT; tags [python, testing, pytest, unittest]; recommended tools [codebase, runCommands, editFiles].

## When to use

- Writing or reviewing Python tests
- Setting up pytest configuration or fixtures
- Debugging test failures in a Python project
- Choosing between pytest and unittest patterns

## Test structure

Organize tests to mirror the source tree:

```text
src/
  mypackage/
    auth.py
    models.py
tests/
  test_auth.py
  test_models.py
  conftest.py
```

- Name test files `test_<module>.py` to match the source module.
- Use `conftest.py` for shared fixtures scoped to a directory.
- Place integration tests in `tests/integration/` and unit tests in `tests/unit/` when both exist.

## pytest conventions

### Fixtures

Use fixtures for setup and teardown. Prefer function scope unless shared state is intentional:

```python
@pytest.fixture
def db_session(tmp_path):
    db = Database(tmp_path / "test.db")
    yield db
    db.close()
```

- Inject fixtures by parameter name — avoid `@pytest.fixture(autouse=True)` unless project-wide.
- Use `tmp_path` (not `tempfile`) for temporary files.
- Use `monkeypatch` for environment variables and attribute patching.

### Parametrize

Use `@pytest.mark.parametrize` for data-driven tests:

```python
@pytest.mark.parametrize("input_val,expected", [
    ("hello", 5),
    ("", 0),
    ("  spaces  ", 10),
])
def test_string_length(input_val, expected):
    assert len(input_val) == expected
```

### Mocking

- Use `unittest.mock.patch` or `monkeypatch` — prefer `monkeypatch` for simple attribute/env patches.
- Mock at the boundary (API calls, file I/O, external services) — not internal functions.
- Use `spec=True` when patching classes to catch interface drift.

### Assertions

- Use plain `assert` statements — pytest rewrites them for detailed failure output.
- For exceptions: `with pytest.raises(ValueError, match="expected message"):`
- For approximate floats: `assert result == pytest.approx(3.14, abs=0.01)`

## Configuration

Prefer `pyproject.toml` for pytest configuration:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers --strict-config"
markers = [
    "slow: marks tests as slow",
    "integration: marks integration tests",
]
```

## Coverage

Run coverage alongside tests:

```bash
pytest --cov=src --cov-report=term-missing
```

- Aim for meaningful coverage of business logic — avoid chasing 100% on boilerplate.
- Use `# pragma: no cover` sparingly and only with justification.

## Verify

- [ ] Test layout mirrors source layout and follows project naming conventions
- [ ] Fixtures and mocks are scoped to external boundaries, not internals
- [ ] Regression test reproduces the bug before the fix
- [ ] Coverage output highlights business-logic gaps, not just line count
