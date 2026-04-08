"""Tests for path security functions."""

import unittest
import tempfile
import os
import shutil
import sys

# Add parent directory to path to import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader import sanitize_name, validate_path_safety


class TestSanitizeName(unittest.TestCase):
    """Test sanitize_name function."""

    def test_clean_name(self):
        """Test that clean names pass through unchanged."""
        self.assertEqual(sanitize_name("file.txt"), "file.txt")
        self.assertEqual(sanitize_name("my_document.pdf"), "my_document.pdf")
        self.assertEqual(sanitize_name("photo-2024.jpg"), "photo-2024.jpg")

    def test_path_separator(self):
        """Test that path separators are replaced."""
        self.assertEqual(sanitize_name("folder/file.txt"), "folder_file.txt")
        if os.sep == "\\":  # Windows
            self.assertEqual(sanitize_name("folder\\file.txt"), "folder_file.txt")

    def test_null_bytes(self):
        """Test that null bytes are removed."""
        self.assertEqual(sanitize_name("file\x00name.txt"), "filename.txt")

    def test_control_characters(self):
        """Test that control characters are replaced."""
        self.assertEqual(sanitize_name("file\rname.txt"), "file_name.txt")
        self.assertEqual(sanitize_name("file\nname.txt"), "file_name.txt")
        self.assertEqual(sanitize_name("file\tname.txt"), "file_name.txt")

    def test_whitespace_stripped(self):
        """Test that leading/trailing whitespace is stripped."""
        self.assertEqual(sanitize_name("  file.txt  "), "file.txt")
        # Note: \t and \n are replaced with _ before stripping
        self.assertEqual(sanitize_name("\tfile.txt\n"), "_file.txt_")

    def test_path_traversal_patterns(self):
        """Test that .. patterns are removed for security."""
        self.assertEqual(sanitize_name("file/../etc/passwd"), "file___etc_passwd")
        self.assertEqual(sanitize_name("....txt"), "__txt")
        # Note: .. is replaced with _ (single underscore, not double)
        self.assertEqual(sanitize_name("file..name"), "file_name")

    def test_empty_name_fallback(self):
        """Test that empty names get a fallback."""
        self.assertEqual(sanitize_name(""), "unnamed")
        self.assertEqual(sanitize_name("   "), "unnamed")


class TestValidatePathSafety(unittest.TestCase):
    """Test validate_path_safety function."""

    def setUp(self):
        """Create a temporary root directory."""
        self.temp_root = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_safe_relative_path(self):
        """Test that safe relative paths are accepted."""
        # Change to the temp directory first so relative paths work
        old_cwd = os.getcwd()
        try:
            os.chdir(self.temp_root)
            result = validate_path_safety("folder/file.txt", self.temp_root)
            expected = os.path.join(self.temp_root, "folder", "file.txt")
            self.assertEqual(result, expected)
        finally:
            os.chdir(old_cwd)

    def test_absolute_path_rejected(self):
        """Test that absolute paths are rejected."""
        with self.assertRaises(ValueError) as ctx:
            validate_path_safety("/absolute/path/file.txt", self.temp_root)
        self.assertIn("Absolute paths not allowed", str(ctx.exception))

    def test_absolute_path_within_root_accepted(self):
        """Test that internal absolute paths under the root are accepted."""
        safe_path = os.path.join(self.temp_root, "folder", "file.txt")
        result = validate_path_safety(safe_path, self.temp_root)
        self.assertEqual(result, safe_path)

    def test_parent_traversal_rejected(self):
        """Test that parent directory traversal is rejected."""
        with self.assertRaises(ValueError) as ctx:
            validate_path_safety("folder/../../../etc/passwd", self.temp_root)
        self.assertIn("Path traversal detected", str(ctx.exception))

    def test_single_parent_traversal(self):
        """Test that even single .. is rejected."""
        with self.assertRaises(ValueError) as ctx:
            validate_path_safety("folder/../file.txt", self.temp_root)
        self.assertIn("Path traversal detected", str(ctx.exception))

    def test_path_escaping_root_rejected(self):
        """Test that paths escaping root are rejected."""
        outside_root = tempfile.mkdtemp()
        link_dir = os.path.join(self.temp_root, "safe")
        os.makedirs(link_dir)
        os.symlink(outside_root, os.path.join(link_dir, "escape"))

        try:
            escaped_path = os.path.join(self.temp_root, "safe", "escape", "file.txt")
            with self.assertRaises(ValueError) as ctx:
                validate_path_safety(escaped_path, self.temp_root)
            self.assertIn("Absolute paths not allowed outside root", str(ctx.exception))
        finally:
            shutil.rmtree(outside_root, ignore_errors=True)

    def test_root_itself_accepted(self):
        """Test that the root directory itself is accepted."""
        old_cwd = os.getcwd()
        try:
            os.chdir(self.temp_root)
            result = validate_path_safety(".", self.temp_root)
            self.assertEqual(result, os.path.abspath(self.temp_root))
        finally:
            os.chdir(old_cwd)

    def test_nested_safe_paths(self):
        """Test deeply nested but safe paths."""
        old_cwd = os.getcwd()
        try:
            os.chdir(self.temp_root)
            nested = "a/b/c/d/e/f/g/file.txt"
            result = validate_path_safety(nested, self.temp_root)
            expected = os.path.join(
                self.temp_root, "a", "b", "c", "d", "e", "f", "g", "file.txt"
            )
            self.assertEqual(result, expected)
        finally:
            os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
