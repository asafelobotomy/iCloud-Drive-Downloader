"""Tests for the active Python file line-count budget."""

from pathlib import Path
import unittest


MAX_FILE_LINES = 400
REPO_ROOT = Path(__file__).resolve().parents[1]
ACTIVE_ROOTS = {"icloud_downloader.py", "icloud_downloader_lib", "tests"}
EXCLUDED_DIRS = {".venv", "archive", "__pycache__"}


def iter_active_python_files():
    """Yield active Python files covered by the LOC budget."""
    for file_path in REPO_ROOT.rglob("*.py"):
        relative_path = file_path.relative_to(REPO_ROOT)
        if any(part in EXCLUDED_DIRS for part in relative_path.parts):
            continue
        if relative_path.parts[0] not in ACTIVE_ROOTS:
            continue
        yield relative_path, file_path


class TestLineCountBudget(unittest.TestCase):
    """Ensure active Python files stay within the hard line-count cap."""

    def test_active_python_files_stay_within_budget(self):
        """Reject active Python files that exceed 400 lines."""
        offenders = []

        for relative_path, file_path in iter_active_python_files():
            with self.subTest(path=str(relative_path)):
                with file_path.open("r", encoding="utf-8") as source_file:
                    line_count = sum(1 for _ in source_file)
                if line_count > MAX_FILE_LINES:
                    offenders.append(f"{relative_path}: {line_count} lines")

        self.assertEqual(
            offenders,
            [],
            msg=(
                f"Active Python files must stay at or below {MAX_FILE_LINES} lines. "
                f"Offenders: {', '.join(offenders)}"
            ),
        )