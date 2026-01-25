"""Integration tests using dry-run mode."""

import unittest
import sys
import os
import tempfile
import shutil
from unittest.mock import Mock, MagicMock, patch

# Add parent directory to path to import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader import (
    download_file,
    FileFilter,
    DownloadStats,
    StructuredLogger,
    DownloadManifest,
)


class TestIntegrationDryRun(unittest.TestCase):
    """Integration tests using dry-run mode."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file_path = os.path.join(self.temp_dir, "test_file.jpg")

    def tearDown(self):
        """Clean up test files."""
        shutil.rmtree(self.temp_dir)

    def test_download_file_dry_run(self):
        """Test download_file in dry-run mode."""
        # Mock iCloud item
        mock_item = Mock()
        mock_item.size = 2048

        # Create test objects
        failures = []
        config = {
            "max_retries": 3,
            "timeout": 60,
            "chunk_size": 8192,
            "progress_every_bytes": 5242880,
            "verbose": False,
        }
        stats = DownloadStats()

        # Run in dry-run mode
        download_file(
            item=mock_item,
            local_path=self.test_file_path,
            failures=failures,
            label="test_file.jpg",
            config=config,
            manifest=None,
            file_filter=None,
            stats=stats,
            logger=None,
            dry_run=True,
            pbar=None,
        )

        # Verify file was not created
        self.assertFalse(os.path.exists(self.test_file_path))

        # Verify stats were updated
        self.assertEqual(stats.files_total, 1)
        self.assertEqual(len(failures), 0)

    def test_download_file_with_filter_exclude(self):
        """Test download_file with filter that excludes file."""
        mock_item = Mock()
        mock_item.size = 2048

        failures = []
        config = {"verbose": True}

        # Create filter that excludes .tmp files
        file_filter = FileFilter(exclude_patterns=["*.tmp"])

        # Try to download a .tmp file
        tmp_path = os.path.join(self.temp_dir, "temp.tmp")

        download_file(
            item=mock_item,
            local_path=tmp_path,
            failures=failures,
            label="temp.tmp",
            config=config,
            manifest=None,
            file_filter=file_filter,
            stats=None,
            logger=None,
            dry_run=True,
            pbar=None,
        )

        # File should be filtered out (no failures, not created)
        self.assertEqual(len(failures), 0)
        self.assertFalse(os.path.exists(tmp_path))

    def test_download_file_with_filter_include(self):
        """Test download_file with filter that includes file."""
        mock_item = Mock()
        mock_item.size = 2048

        failures = []
        config = {"verbose": False}
        stats = DownloadStats()

        # Create filter that includes only .jpg files
        file_filter = FileFilter(include_patterns=["*.jpg"])

        # Try to download a .jpg file in dry-run
        download_file(
            item=mock_item,
            local_path=self.test_file_path,
            failures=failures,
            label="test_file.jpg",
            config=config,
            manifest=None,
            file_filter=file_filter,
            stats=stats,
            logger=None,
            dry_run=True,
            pbar=None,
        )

        # File should be included (stats updated)
        self.assertEqual(stats.files_total, 1)
        self.assertEqual(len(failures), 0)

    def test_manifest_integration(self):
        """Test manifest integration."""
        manifest_path = os.path.join(self.temp_dir, "test_manifest.json")
        manifest = DownloadManifest(manifest_path)

        # Mark file as complete
        manifest.mark_complete(self.test_file_path, 2048)

        # Create mock item
        mock_item = Mock()
        mock_item.size = 2048

        # Create actual file so skip logic works
        with open(self.test_file_path, "w") as f:
            f.write("test")

        failures = []
        config = {
            "max_retries": 3,
            "timeout": 60,
            "chunk_size": 8192,
            "progress_every_bytes": 5242880,
        }
        stats = DownloadStats()

        # Try to download - should skip
        download_file(
            item=mock_item,
            local_path=self.test_file_path,
            failures=failures,
            label="test_file.jpg",
            config=config,
            manifest=manifest,
            file_filter=None,
            stats=stats,
            logger=None,
            dry_run=False,
            pbar=None,
        )

        # Should be skipped
        self.assertEqual(stats.files_skipped, 1)
        self.assertEqual(len(failures), 0)


if __name__ == "__main__":
    unittest.main()
