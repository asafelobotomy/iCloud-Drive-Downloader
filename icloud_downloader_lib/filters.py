import fnmatch
import os
import re
from contextlib import contextmanager
from datetime import datetime
from typing import Any, IO, Iterator, List, Optional, Set


class FileFilter:
    """Filter files based on patterns, size, and date thresholds."""

    def __init__(
        self,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        min_size: Optional[int] = None,
        max_size: Optional[int] = None,
        modified_after: Optional[datetime] = None,
        modified_before: Optional[datetime] = None,
        selected_files: Optional[List[str]] = None,
        selected_folders: Optional[List[str]] = None,
        selection_root: Optional[str] = None,
    ) -> None:
        self.include_patterns: List[str] = include_patterns or []
        self.exclude_patterns: List[str] = exclude_patterns or []
        self.min_size = min_size
        self.max_size = max_size
        self.modified_after = modified_after
        self.modified_before = modified_before
        self.selected_files: Set[str] = {
            self._normalize_path_value(path) for path in (selected_files or []) if path
        }
        self.selected_folders: Set[str] = {
            self._normalize_path_value(path) for path in (selected_folders or []) if path
        }
        self.selection_root = os.path.realpath(selection_root) if selection_root else None

    @staticmethod
    def _normalize_path_value(path: str) -> str:
        return os.path.normpath(path).replace(os.sep, "/").strip("/")

    def _normalize_relative_path(self, path: str) -> str:
        candidate_path = path
        if self.selection_root and os.path.isabs(path):
            try:
                candidate_path = os.path.relpath(os.path.realpath(path), self.selection_root)
            except ValueError:
                candidate_path = path
        return self._normalize_path_value(candidate_path)

    def has_selection_scope(self) -> bool:
        return bool(self.selected_files or self.selected_folders)

    def should_traverse_directory(self, directory_path: str) -> bool:
        if not self.has_selection_scope():
            return True

        relative_path = self._normalize_relative_path(directory_path)
        if relative_path in ("", "."):
            return True

        selection_paths = self.selected_files | self.selected_folders
        for selected_path in selection_paths:
            if selected_path == relative_path or selected_path.startswith(relative_path + "/"):
                return True
        for selected_folder in self.selected_folders:
            if relative_path.startswith(selected_folder + "/"):
                return True
        return False

    def _matches_selection_scope(self, file_path: str) -> bool:
        if not self.has_selection_scope():
            return True

        relative_path = self._normalize_relative_path(file_path)
        if relative_path in self.selected_files:
            return True
        return any(
            relative_path == folder_path or relative_path.startswith(folder_path + "/")
            for folder_path in self.selected_folders
        )

    def should_include(
        self,
        file_path: str,
        size: Optional[int] = None,
        modified_date: Optional[datetime] = None,
    ) -> bool:
        if not self._matches_selection_scope(file_path):
            return False

        if self.include_patterns:
            matched = False
            for pattern in self.include_patterns:
                if fnmatch.fnmatch(file_path, pattern) or fnmatch.fnmatch(
                    os.path.basename(file_path), pattern
                ):
                    matched = True
                    break
            if not matched:
                return False

        if self.exclude_patterns:
            for pattern in self.exclude_patterns:
                if fnmatch.fnmatch(file_path, pattern) or fnmatch.fnmatch(
                    os.path.basename(file_path), pattern
                ):
                    return False

        if size is not None:
            if self.min_size is not None and size < self.min_size:
                return False
            if self.max_size is not None and size > self.max_size:
                return False

        if modified_date is not None:
            if self.modified_after is not None and modified_date < self.modified_after:
                return False
            if self.modified_before is not None and modified_date > self.modified_before:
                return False

        return True


def sanitize_name(name: str) -> str:
    """Sanitize iCloud names for safe local filesystem use."""
    safe = name.replace(os.sep, "_").replace("\x00", "")
    safe = re.sub(r"[\r\n\t]", "_", safe)
    safe = safe.replace("..", "_")
    safe = safe.strip()
    return safe or "unnamed"


def validate_path_safety(path: str, root: str) -> str:
    """Ensure path is within root directory and doesn't contain traversal patterns."""
    resolved_root = os.path.realpath(root)
    candidate_path = path

    if os.path.isabs(path):
        resolved_path = os.path.realpath(path)
        try:
            within_root = os.path.commonpath([resolved_root, resolved_path]) == resolved_root
        except ValueError:
            within_root = False
        if not within_root:
            raise ValueError(f"Absolute paths not allowed outside root: {path}")
        return resolved_path

    if ".." in path.split(os.sep):
        raise ValueError(f"Path traversal detected: {path}")

    candidate_path = os.path.join(resolved_root, path)
    resolved_path = os.path.realpath(candidate_path)
    try:
        within_root = os.path.commonpath([resolved_root, resolved_path]) == resolved_root
    except ValueError:
        within_root = False
    if not within_root:
        raise ValueError(f"Path escapes root: {path}")
    return resolved_path


def _open_directory_fd(path: str) -> int:
    return os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))


def _open_child_directory_fd(parent_fd: int, name: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return os.open(name, flags, dir_fd=parent_fd)


def _secure_relative_parts(path: str, root: str) -> List[str]:
    resolved_root = os.path.realpath(root)
    if os.path.isabs(path):
        candidate_path = os.path.abspath(path)
        if candidate_path == resolved_root:
            return []
        parent_path = os.path.dirname(candidate_path) or candidate_path
        try:
            within_root = os.path.commonpath([resolved_root, os.path.realpath(parent_path)]) == resolved_root
        except ValueError:
            within_root = False
        if not within_root:
            raise ValueError(f"Absolute paths not allowed outside root: {path}")
    else:
        if ".." in path.split(os.sep):
            raise ValueError(f"Path traversal detected: {path}")
        candidate_path = os.path.abspath(os.path.join(resolved_root, path))
        parent_path = os.path.dirname(candidate_path) or resolved_root
        try:
            within_root = os.path.commonpath([resolved_root, os.path.realpath(parent_path)]) == resolved_root
        except ValueError:
            within_root = False
        if not within_root:
            raise ValueError(f"Path escapes root: {path}")

    relative_path = os.path.relpath(candidate_path, resolved_root)
    if relative_path in (".", ""):
        return []
    parts = relative_path.split(os.sep)
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"Unsafe path segments in {path}")
    return parts


def ensure_directory(path: str, root: str, permissions: int = 0o700) -> None:
    """Create or validate a directory path without following symlinks."""
    resolved_root = os.path.realpath(root)
    if not os.path.exists(resolved_root):
        os.makedirs(resolved_root, mode=permissions, exist_ok=True)
        os.chmod(resolved_root, permissions)

    parts = _secure_relative_parts(path, root)
    current_fd = _open_directory_fd(resolved_root)

    try:
        for part in parts:
            try:
                next_fd = _open_child_directory_fd(current_fd, part)
            except FileNotFoundError:
                os.mkdir(part, permissions, dir_fd=current_fd)
                next_fd = _open_child_directory_fd(current_fd, part)
            if hasattr(os, "fchmod"):
                os.fchmod(next_fd, permissions)
            os.close(current_fd)
            current_fd = next_fd
    finally:
        os.close(current_fd)


def set_file_permissions(path: str, root: str, permissions: int = 0o600) -> None:
    """Apply file permissions without following symlinks."""
    parts = _secure_relative_parts(path, root)
    if not parts:
        raise ValueError(f"File path must not be the root directory: {path}")

    current_fd = _open_directory_fd(os.path.realpath(root))
    file_fd = None

    try:
        for part in parts[:-1]:
            next_fd = _open_child_directory_fd(current_fd, part)
            os.close(current_fd)
            current_fd = next_fd

        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        file_fd = os.open(parts[-1], flags, dir_fd=current_fd)
        if hasattr(os, "fchmod"):
            os.fchmod(file_fd, permissions)
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(current_fd)


@contextmanager
def open_secure_file(
    path: str,
    root: str,
    mode: str,
    *,
    permissions: int = 0o600,
    encoding: Optional[str] = None,
) -> Iterator[IO[Any]]:
    """Open a file relative to a trusted root without following symlinks."""
    parts = _secure_relative_parts(path, root)
    if not parts:
        raise ValueError(f"File path must not be the root directory: {path}")

    current_fd = _open_directory_fd(os.path.realpath(root))
    file_fd = None
    file_obj = None

    try:
        for part in parts[:-1]:
            next_fd = _open_child_directory_fd(current_fd, part)
            os.close(current_fd)
            current_fd = next_fd

        if mode in ("r", "rb"):
            open_flags = os.O_RDONLY
        elif mode == "w":
            open_flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        elif mode == "a":
            open_flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        elif mode == "wb":
            open_flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        elif mode == "ab":
            open_flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        else:
            raise ValueError(f"Unsupported secure file mode: {mode}")

        if hasattr(os, "O_NOFOLLOW"):
            open_flags |= os.O_NOFOLLOW

        file_fd = os.open(parts[-1], open_flags, permissions, dir_fd=current_fd)
        if mode != "r" and hasattr(os, "fchmod"):
            os.fchmod(file_fd, permissions)

        if "b" in mode:
            file_obj = os.fdopen(file_fd, mode)
        else:
            file_obj = os.fdopen(file_fd, mode, encoding=encoding or "utf-8")
        file_fd = None
        yield file_obj
    finally:
        if file_obj is not None:
            file_obj.close()
        elif file_fd is not None:
            os.close(file_fd)
        os.close(current_fd)