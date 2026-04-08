---
name: Python Conventions
applyTo: "**/*.py"
description: "PEP 8 style, import ordering, docstrings, virtual environment, and packaging conventions for Python projects"
---

# Python Conventions

- Follow PEP 8 for style. Use a formatter (ruff format, black) rather than manual formatting.
- Import order: stdlib, blank line, third-party, blank line, local. Use `isort` or `ruff` to enforce.
- Use type annotations on all public function signatures.
- Write docstrings for public modules, classes, and functions. Use Google or NumPy style consistently within the project.
- Prefer `pathlib.Path` over `os.path` for file system operations.
- Use context managers (`with`) for resource management (files, connections, locks).
- Use `dataclasses` or `pydantic` for structured data — avoid raw dictionaries for domain objects.
- Prefer list comprehensions over `map()`/`filter()` for simple transformations.
- Use `logging` module instead of `print()` for application output.
- Virtual environments: use `venv`, `poetry`, or `uv` — never install into the system Python.
- Pin dependencies with exact versions in lock files (`poetry.lock`, `uv.lock`, `requirements.txt` with hashes).
