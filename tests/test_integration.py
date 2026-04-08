"""Integration tests covering dry-run and download flows."""

import unittest
import sys
import os
import tempfile
import shutil
from unittest.mock import Mock

# Add parent directory to path to import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader import (
    collect_download_tasks,
    download_file,
    StructuredLogger,
    DownloadManifest,
    DownloadStats,
    FileFilter,
)


class FakeResponse:
    """Minimal streaming response for download tests."""

    def __init__(self, chunks):
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_content(self, chunk_size):
        del chunk_size
        for chunk in self._chunks:
            yield chunk


class FakeItem:
    """Minimal iCloud item stub for file downloads."""

    def __init__(self, chunks, size=None, item_type="file"):
        self._chunks = chunks
        self.size = size if size is not None else sum(len(chunk) for chunk in chunks)
        self.type = item_type

    def open(self, stream=True):
        del stream
        return FakeResponse(self._chunks)


class FakeNode:
    """Minimal directory tree node for task collection tests."""

    def __init__(self, name, node_type="folder", children=None, size=0):
        self.name = name
        self.type = node_type
        self.size = size
        self._children = children or {}

    def dir(self):
        return list(self._children.keys())

    def __getitem__(self, key):
        return self._children[key]


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


class TestDownloadExecution(unittest.TestCase):
    """Integration tests for streamed downloads and task collection."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_file_path = os.path.join(self.temp_dir, "test_file.bin")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_download_file_writes_streamed_content(self):
        manifest_path = os.path.join(self.temp_dir, "manifest.json")
        manifest = DownloadManifest(manifest_path)
        item = FakeItem([b"hello ", b"world"])
        failures = []
        config = {
            "max_retries": 3,
            "timeout": 60,
            "chunk_size": 4,
            "progress_every_bytes": 1024,
            "workers": 1,
        }
        stats = DownloadStats()

        download_file(
            item=item,
            local_path=self.test_file_path,
            failures=failures,
            label="stream.bin",
            config=config,
            manifest=manifest,
            file_filter=None,
            stats=stats,
            logger=None,
            dry_run=False,
            pbar=None,
        )

        with open(self.test_file_path, "rb") as saved_file:
            self.assertEqual(saved_file.read(), b"hello world")

        self.assertTrue(manifest.is_complete(self.test_file_path))
        self.assertEqual(stats.files_completed, 1)
        self.assertEqual(stats.bytes_downloaded, 11)
        self.assertEqual(failures, [])

    def test_download_file_resume_skips_existing_bytes(self):
        manifest_path = os.path.join(self.temp_dir, "manifest.json")
        manifest = DownloadManifest(manifest_path)

        with open(self.test_file_path, "wb") as existing_file:
            existing_file.write(b"hello ")

        manifest.update_file(self.test_file_path, "partial", 6, 11)

        item = FakeItem([b"hello ", b"world"])
        failures = []
        config = {
            "max_retries": 3,
            "timeout": 60,
            "chunk_size": 4,
            "progress_every_bytes": 1024,
            "workers": 1,
        }
        stats = DownloadStats()

        download_file(
            item=item,
            local_path=self.test_file_path,
            failures=failures,
            label="resume.bin",
            config=config,
            manifest=manifest,
            file_filter=None,
            stats=stats,
            logger=None,
            dry_run=False,
            pbar=None,
        )

        with open(self.test_file_path, "rb") as saved_file:
            self.assertEqual(saved_file.read(), b"hello world")

        self.assertEqual(stats.files_completed, 1)
        self.assertEqual(stats.bytes_downloaded, 11)
        self.assertEqual(failures, [])

    def test_collect_download_tasks_recurses_and_filters_files(self):
        nested_folder = FakeNode(
            "nested",
            children={
                "keep.jpg": FakeItem([b"img"], size=3),
                "skip.txt": FakeItem([b"txt"], size=3),
            },
        )
        root = FakeNode(
            "root",
            children={
                "top.jpg": FakeItem([b"top"], size=3),
                "nested": nested_folder,
            },
        )
        tasks = []
        failures = []
        stats = DownloadStats()
        file_filter = FileFilter(include_patterns=["*.jpg"])
        target_root = os.path.join(self.temp_dir, "downloads")

        collect_download_tasks(
            node=root,
            local_path=target_root,
            config={},
            root_path=target_root,
            manifest=None,
            dir_cache=None,
            tasks_list=tasks,
            failures=failures,
            file_filter=file_filter,
            stats=stats,
            shutdown_handler=None,
            depth=0,
            max_depth=None,
        )

        self.assertEqual([task[2] for task in tasks], ["top.jpg", "keep.jpg"])
        self.assertEqual(stats.files_total, 2)
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
