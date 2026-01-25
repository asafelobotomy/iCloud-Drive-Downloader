# Contributing to iCloud Drive Downloader

Thank you for considering contributing to this project! This guide will help you understand the project structure and development workflow.

## Project Philosophy

This is a **single-file Python utility** (`icloud_downloader.py`) designed for maximum portability. The monolithic architecture is intentional—avoid splitting into modules unless absolutely necessary.

## Development Setup

### Prerequisites
- Python 3.7 or higher
- Git

### Initial Setup

```bash
# Clone the repository
git clone <repository-url>
cd icloud-drive-downloader

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-test.txt
```

## Testing

All changes should include tests. We maintain 100% test pass rate.

```bash
# Run all tests
python3 -m unittest discover tests/ -v

# Run specific test file
python3 -m unittest tests/test_filters.py -v

# Run with coverage
python3 -m pytest tests/ --cov=icloud_downloader --cov-report=html

# Type checking
python3 -m mypy icloud_downloader.py --check-untyped-defs
```

## Code Style

### Security-First Patterns

**Always follow these patterns:**

1. **Path Safety Validation**
   ```python
   # ALWAYS validate paths before file operations
   validate_path_safety(path, root)
   ```

2. **Name Sanitization**
   ```python
   # ALWAYS sanitize user-provided names
   safe_name = sanitize_name(item_name)
   ```

3. **Secure Permissions**
   ```python
   # Files: owner-only read/write
   os.chmod(file_path, 0o600)
   
   # Directories: owner-only rwx
   os.chmod(dir_path, 0o700)
   ```

### Thread Safety

All shared state MUST use `threading.Lock()`:

```python
class SharedResource:
    def __init__(self):
        self.lock = threading.Lock()
        self.data = {}
    
    def update(self, key, value):
        with self.lock:
            self.data[key] = value
```

### Type Hints

Add type hints to all new functions:

```python
from typing import Dict, List, Optional, Tuple

def process_item(item: str, config: Dict[str, Any]) -> Optional[bool]:
    """Process an item with the given configuration."""
    pass
```

## Making Changes

### Before You Start

1. Check existing issues and pull requests
2. For major changes, open an issue first to discuss
3. Read [.github/copilot-instructions.md](.github/copilot-instructions.md) for detailed patterns

### Development Workflow

1. **Create a branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Follow existing code patterns
   - Add tests for new functionality
   - Update documentation as needed

3. **Test thoroughly**
   ```bash
   # Run tests
   python3 -m unittest discover tests/ -v
   
   # Syntax check
   python3 -m py_compile icloud_downloader.py
   
   # Type check
   python3 -m mypy icloud_downloader.py
   
   # Dry-run test
   python3 icloud_downloader.py --dry-run --max-items 10
   ```

4. **Update documentation**
   - Add entry to [CHANGELOG.md](CHANGELOG.md)
   - Update [README.md](README.md) if adding features
   - Add examples to [examples/](examples/) if applicable

5. **Commit your changes**
   ```bash
   git add .
   git commit -m "Add feature: brief description"
   ```

6. **Push and create PR**
   ```bash
   git push origin feature/your-feature-name
   ```

## Common Contribution Types

### Adding a New Feature

1. Add CLI argument in `parse_arguments()`
2. Define constant at top of file
3. Pass config via `config` dict (avoid globals)
4. Add structured log event if tracking is valuable
5. Write tests in `tests/test_*.py`
6. Add example config in `examples/`

### Fixing a Bug

1. Add test that reproduces the bug
2. Fix the bug
3. Verify test passes
4. Document in [CHANGELOG.md](CHANGELOG.md)
5. Add entry to `docs/development/FIXES_APPLIED.md`

### Improving Documentation

- User-facing: Update [README.md](README.md) or [docs/](docs/)
- Developer-facing: Update [.github/copilot-instructions.md](.github/copilot-instructions.md)
- Examples: Add to [examples/](examples/)

## Code Review Process

Pull requests are reviewed for:

1. **Correctness**: Does it work as intended?
2. **Security**: Are paths validated? Permissions secure?
3. **Thread Safety**: Proper locking on shared state?
4. **Testing**: Are there tests? Do they pass?
5. **Documentation**: Is it documented?
6. **Style**: Follows existing patterns?

## Project Structure

```
├── icloud_downloader.py          # Main application (1,378 lines)
├── requirements.txt               # Production dependencies
├── requirements-test.txt          # Testing dependencies
├── README.md                      # Main documentation
├── CHANGELOG.md                   # Version history
├── LICENSE                        # MIT license
├── CONTRIBUTING.md                # This file
│
├── docs/                          # Documentation
│   ├── README.md                  # Documentation index
│   ├── QUICK_START.md             # Quick start guide
│   └── development/               # Development docs
│
├── examples/                      # Configuration examples
│   └── *.json                     # Sample configs
│
└── tests/                         # Test suite (63 tests)
    └── test_*.py                  # Test files
```

## Key Architecture Decisions

### Single-File Design
The entire application fits in one file for portability. Resist the urge to split into modules unless the file exceeds 2000 lines.

### No External State
All state is passed via parameters or contained in classes. No global variables (except constants).

### Defense in Depth
Multiple security layers:
- Input sanitization (`sanitize_name`)
- Path validation (`validate_path_safety`)
- Secure permissions on all I/O

### Resume-First Design
Downloads must be resumable. Use manifest tracking and HTTP range requests.

## Questions?

- Check [docs/README.md](docs/README.md) for documentation index
- Read [.github/copilot-instructions.md](.github/copilot-instructions.md) for patterns
- Open an issue for questions

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
