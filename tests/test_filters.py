"""Tests for FileFilter class."""

from datetime import datetime, timedelta
import unittest
import sys
import os

# Add parent directory to path to import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader import FileFilter


class TestFileFilter(unittest.TestCase):
    """Test FileFilter functionality."""

    def test_no_filters(self):
        """Test with no filters - should include everything."""
        filter = FileFilter()
        self.assertTrue(filter.should_include("test.jpg"))
        self.assertTrue(filter.should_include("document.pdf"))
        self.assertTrue(filter.should_include("folder/file.txt"))

    def test_include_patterns(self):
        """Test include patterns."""
        filter = FileFilter(include_patterns=["*.jpg", "*.png"])
        self.assertTrue(filter.should_include("photo.jpg"))
        self.assertTrue(filter.should_include("image.png"))
        self.assertFalse(filter.should_include("document.pdf"))
        self.assertFalse(filter.should_include("video.mp4"))

    def test_exclude_patterns(self):
        """Test exclude patterns."""
        filter = FileFilter(exclude_patterns=["*.tmp", "*/cache/*"])
        self.assertTrue(filter.should_include("photo.jpg"))
        self.assertFalse(filter.should_include("temp.tmp"))
        self.assertFalse(filter.should_include("folder/cache/file.txt"))
        self.assertTrue(filter.should_include("folder/data/file.txt"))

    def test_include_and_exclude(self):
        """Test combination of include and exclude patterns."""
        filter = FileFilter(
            include_patterns=["*.jpg", "*.png"], exclude_patterns=["*_temp.jpg"]
        )
        self.assertTrue(filter.should_include("photo.jpg"))
        self.assertTrue(filter.should_include("image.png"))
        self.assertFalse(filter.should_include("test_temp.jpg"))
        self.assertFalse(filter.should_include("document.pdf"))

    def test_basename_matching(self):
        """Test that patterns match both full path and basename."""
        filter = FileFilter(include_patterns=["photo.jpg"])
        self.assertTrue(filter.should_include("photo.jpg"))
        self.assertTrue(filter.should_include("folder/photo.jpg"))
        self.assertTrue(filter.should_include("folder/subfolder/photo.jpg"))

    def test_size_filters(self):
        """Test size threshold filters."""
        filter = FileFilter(min_size=1000, max_size=10000)

        # Below minimum
        self.assertFalse(filter.should_include("small.txt", size=500))

        # Within range
        self.assertTrue(filter.should_include("medium.txt", size=5000))

        # Above maximum
        self.assertFalse(filter.should_include("large.txt", size=15000))

        # Exactly at boundaries
        self.assertTrue(filter.should_include("min.txt", size=1000))
        self.assertTrue(filter.should_include("max.txt", size=10000))

    def test_min_size_only(self):
        """Test with only minimum size."""
        filter = FileFilter(min_size=1000)
        self.assertFalse(filter.should_include("small.txt", size=500))
        self.assertTrue(filter.should_include("large.txt", size=5000))

    def test_max_size_only(self):
        """Test with only maximum size."""
        filter = FileFilter(max_size=1000)
        self.assertTrue(filter.should_include("small.txt", size=500))
        self.assertFalse(filter.should_include("large.txt", size=5000))

    def test_size_none_ignored(self):
        """Test that None size bypasses size filters."""
        filter = FileFilter(min_size=1000, max_size=10000)
        # When size is None, size filters should not apply
        self.assertTrue(filter.should_include("unknown.txt", size=None))

    def test_pattern_and_size_combination(self):
        """Test combination of pattern and size filters."""
        filter = FileFilter(include_patterns=["*.jpg"], min_size=1000, max_size=100000)

        # Matches pattern but too small
        self.assertFalse(filter.should_include("tiny.jpg", size=500))

        # Matches pattern and size
        self.assertTrue(filter.should_include("good.jpg", size=50000))

        # Wrong pattern
        self.assertFalse(filter.should_include("document.pdf", size=50000))

    def test_modified_date_filters(self):
        now = datetime.now()
        filter = FileFilter(
            modified_after=now - timedelta(days=1),
            modified_before=now + timedelta(days=1),
        )

        self.assertFalse(filter.should_include("old.txt", modified_date=now - timedelta(days=2)))
        self.assertFalse(filter.should_include("future.txt", modified_date=now + timedelta(days=2)))
        self.assertTrue(filter.should_include("current.txt", modified_date=now))

    def test_selection_scope_includes_selected_files_and_folder_descendants(self):
        filter = FileFilter(
            selected_files=["Docs/report.pdf"],
            selected_folders=["Photos/Trips"],
            selection_root="/downloads",
        )

        self.assertTrue(filter.should_include("/downloads/Docs/report.pdf"))
        self.assertTrue(filter.should_include("/downloads/Photos/Trips/rome.jpg"))
        self.assertFalse(filter.should_include("/downloads/Docs/notes.txt"))
        self.assertFalse(filter.should_include("/downloads/Photos/Family/pic.jpg"))

    def test_selection_scope_limits_directory_traversal_to_relevant_branches(self):
        filter = FileFilter(
            selected_files=["Docs/report.pdf"],
            selected_folders=["Photos/Trips"],
            selection_root="/downloads",
        )

        self.assertTrue(filter.should_traverse_directory("/downloads/Docs"))
        self.assertTrue(filter.should_traverse_directory("/downloads/Photos"))
        self.assertTrue(filter.should_traverse_directory("/downloads/Photos/Trips"))
        self.assertFalse(filter.should_traverse_directory("/downloads/Music"))


if __name__ == "__main__":
    unittest.main()
