---
name: python-typing
description: Apply Python type annotations effectively — mypy/pyright configuration, common patterns, generic types, and stub guidance
compatibility: ">=1.4"
---

# Python Typing

> Skill metadata: version "1.0"; license MIT; tags [python, typing, mypy, pyright, type-checking]; recommended tools [codebase, runCommands, editFiles].

## When to use

- Adding or reviewing type annotations in Python code
- Configuring mypy or pyright for a project
- Resolving type checker errors
- Writing or consuming type stubs

## Core principles

- Annotate function signatures (parameters and return types) at minimum.
- Use `from __future__ import annotations` for forward references (Python 3.7+).
- Prefer built-in generics (`list[str]`, `dict[str, int]`) over `typing.List`, `typing.Dict` (Python 3.9+).
- Use `X | None` instead of `Optional[X]` (Python 3.10+).

## Common patterns

### Function signatures

```python
def process_items(items: list[str], limit: int = 10) -> dict[str, int]:
    ...
```

### Union and optional

```python
# Python 3.10+
def find_user(user_id: int) -> User | None:
    ...

# Python 3.7–3.9
from __future__ import annotations
def find_user(user_id: int) -> User | None:
    ...
```

### TypedDict for structured dictionaries

```python
from typing import TypedDict

class UserProfile(TypedDict):
    name: str
    email: str
    age: int | None
```

### Protocol for structural subtyping

```python
from typing import Protocol

class Serializable(Protocol):
    def to_json(self) -> str: ...
```

### Generics

```python
from typing import TypeVar

T = TypeVar("T")

def first(items: list[T]) -> T | None:
    return items[0] if items else None
```

## Configuration

### mypy in pyproject.toml

```toml
[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
```

### pyright in pyproject.toml

```toml
[tool.pyright]
pythonVersion = "3.12"
typeCheckingMode = "standard"
reportMissingTypeStubs = "warning"
```

## Type stubs

- Install stubs from `types-*` packages on PyPI (e.g., `types-requests`).
- Create `py.typed` marker file to mark a package as typed.
- For internal stubs, place `.pyi` files alongside source files.

## Common pitfalls

- Annotating `self` and `cls` — not needed (mypy and pyright infer them).
- Using `Any` — minimize its use; it defeats the purpose of type checking.
- Mutable default arguments — use `None` as default and assign in the body.
- Circular imports for type checking — use `TYPE_CHECKING` guard:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import User
```

## Verify

- [ ] Public APIs have explicit parameter and return annotations
- [ ] Type checker config exists and runs in CI or local verification flow
- [ ] `Any` usage is intentional and justified
- [ ] Stub strategy (`types-*`, `.pyi`, `py.typed`) matches dependency reality
