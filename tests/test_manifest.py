"""Tests for DownloadManifest class."""

import unittest
import tempfile
import os
import json
import sys

# Add parent directory to path to import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader import DownloadManifest


class TestDownloadManifest(unittest.TestCase):
    """Test DownloadManifest functionality."""

    def setUp(self):
        """Create a temporary manifest file for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.manifest_path = os.path.join(self.temp_dir, "test_manifest.json")

    def tearDown(self):
        """Clean up temporary files."""
        if os.path.exists(self.manifest_path):
            os.remove(self.manifest_path)
        os.rmdir(self.temp_dir)

    def test_new_manifest(self):
        """Test creating a new manifest."""
        manifest = DownloadManifest(self.manifest_path)
        self.assertIsNotNone(manifest.data)
        self.assertIn("files", manifest.data)
        self.assertIn("metadata", manifest.data)
        self.assertEqual(len(manifest.data["files"]), 0)

    def test_update_file(self):
        """Test updating file status."""
        manifest = DownloadManifest(self.manifest_path)

        manifest.update_file("/path/to/file.jpg", "partial", 1024, 2048)

        status = manifest.get_file_status("/path/to/file.jpg")
        self.assertEqual(status["status"], "partial")
        self.assertEqual(status["bytes_downloaded"], 1024)
        self.assertEqual(status["total_bytes"], 2048)
        self.assertIn("last_updated", status)

    def test_mark_complete(self):
        """Test marking file as complete."""
        manifest = DownloadManifest(self.manifest_path)

        manifest.mark_complete("/path/to/file.jpg", 2048)

        status = manifest.get_file_status("/path/to/file.jpg")
        self.assertEqual(status["status"], "complete")
        self.assertEqual(status["bytes_downloaded"], 2048)
        self.assertEqual(status["total_bytes"], 2048)

    def test_is_complete(self):
        """Test checking if file is complete."""
        manifest = DownloadManifest(self.manifest_path)

        # Not complete initially
        self.assertFalse(manifest.is_complete("/path/to/file.jpg"))

        # Mark as partial
        manifest.update_file("/path/to/file.jpg", "partial", 1024, 2048)
        self.assertFalse(manifest.is_complete("/path/to/file.jpg"))

        # Mark as complete
        manifest.mark_complete("/path/to/file.jpg", 2048)
        self.assertTrue(manifest.is_complete("/path/to/file.jpg"))

    def test_persistence(self):
        """Test that manifest persists to disk."""
        # Create and update manifest
        manifest1 = DownloadManifest(self.manifest_path)
        manifest1.update_file("/path/to/file1.jpg", "complete", 1024, 1024)
        manifest1.update_file("/path/to/file2.jpg", "partial", 512, 2048)

        # Verify file was created
        self.assertTrue(os.path.exists(self.manifest_path))

        # Load in new instance
        manifest2 = DownloadManifest(self.manifest_path)

        # Verify data persisted
        status1 = manifest2.get_file_status("/path/to/file1.jpg")
        self.assertEqual(status1["status"], "complete")
        self.assertEqual(status1["bytes_downloaded"], 1024)

        status2 = manifest2.get_file_status("/path/to/file2.jpg")
        self.assertEqual(status2["status"], "partial")
        self.assertEqual(status2["bytes_downloaded"], 512)

    def test_file_permissions(self):
        """Test that manifest file has secure permissions."""
        manifest = DownloadManifest(self.manifest_path)
        manifest.update_file("/path/to/file.jpg", "complete", 1024, 1024)

        # Check permissions (0o600 = owner read/write only)
        stat_info = os.stat(self.manifest_path)
        permissions = stat_info.st_mode & 0o777
        self.assertEqual(permissions, 0o600)

    def test_error_field(self):
        """Test storing error information."""
        manifest = DownloadManifest(self.manifest_path)

        error_msg = "Connection timeout"
        manifest.update_file("/path/to/file.jpg", "failed", 512, 2048, error=error_msg)

        status = manifest.get_file_status("/path/to/file.jpg")
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["error"], error_msg)

    def test_corrupted_manifest_recovery(self):
        """Test recovery from corrupted manifest file."""
        # Create corrupted manifest
        with open(self.manifest_path, "w") as f:
            f.write("{ invalid json }")

        # Should create new manifest instead of crashing
        manifest = DownloadManifest(self.manifest_path)
        self.assertIsNotNone(manifest.data)
        self.assertEqual(len(manifest.data["files"]), 0)


if __name__ == "__main__":
    unittest.main()
