"""Tests for traversal edge cases and failure handling."""

import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader_lib.state import DownloadStats
from icloud_downloader_lib.traversal import collect_download_tasks, download_node


class FakeNode:
    """Minimal folder node stub."""

    def __init__(self, name, children=None, directory_error=None):
        self.name = name
        self.type = "folder"
        self._children = children or {}
        self._directory_error = directory_error

    def dir(self):
        if self._directory_error is not None:
            raise self._directory_error
        return list(self._children.keys())

    def __getitem__(self, key):
        return self._children[key]


class TestTraversal(unittest.TestCase):
    """Test traversal branch behavior that is not covered by integration tests."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("icloud_downloader_lib.traversal.download_file")
    def test_download_node_records_directory_listing_failures(self, download_file_mock):
        failures = []
        node = FakeNode("root", directory_error=RuntimeError("boom"))

        download_node(
            node,
            os.path.join(self.temp_dir, "root"),
            failures,
            {},
            self.temp_dir,
        )

        self.assertEqual(len(failures), 1)
        self.assertIn("Could not list contents", failures[0])
        download_file_mock.assert_not_called()

    def test_collect_download_tasks_records_path_validation_failures(self):
        failures = []
        tasks = []

        collect_download_tasks(
            FakeNode("root"),
            os.path.join(self.temp_dir, "..", "escape"),
            {},
            self.temp_dir,
            None,
            None,
            tasks,
            failures,
            stats=DownloadStats(),
        )

        self.assertEqual(tasks, [])
        self.assertEqual(len(failures), 1)
        self.assertIn("Path validation failed", failures[0])

    def test_collect_download_tasks_does_not_create_directories_during_discovery(self):
        nested_file = SimpleNamespace(type="file", size=10)
        node = FakeNode("root", children={"nested": FakeNode("nested", children={"one.txt": nested_file})})
        local_path = os.path.join(self.temp_dir, "downloads")
        tasks = []
        failures = []

        collect_download_tasks(
            node,
            local_path,
            {},
            local_path,
            None,
            None,
            tasks,
            failures,
            stats=DownloadStats(),
        )

        self.assertEqual(len(tasks), 1)
        self.assertFalse(os.path.exists(local_path))
        self.assertFalse(os.path.exists(os.path.join(local_path, "nested")))
        self.assertEqual(failures, [])

    @patch("icloud_downloader_lib.traversal.download_file")
    def test_download_node_stops_when_max_items_limit_is_reached(self, download_file_mock):
        file_item = SimpleNamespace(type="file", size=10)
        node = FakeNode("root", children={"one.txt": file_item, "two.txt": file_item})
        stats = DownloadStats()
        stats.files_total = 1

        download_node(
            node,
            os.path.join(self.temp_dir, "root"),
            [],
            {"max_items": 1, "verbose": True},
            self.temp_dir,
            stats=stats,
        )

        download_file_mock.assert_not_called()

    @patch("icloud_downloader_lib.traversal.download_file")
    def test_download_node_tracks_files_total_in_stats(self, download_file_mock):
        file_item = SimpleNamespace(type="file", size=2048)
        node = FakeNode("root", children={"readme.txt": file_item})
        stats = DownloadStats()
        file_filter = Mock()
        file_filter.should_include = Mock(return_value=True)

        download_file_mock.side_effect = lambda *a, **kw: None

        download_node(
            node,
            os.path.join(self.temp_dir, "root"),
            [],
            {},
            self.temp_dir,
            file_filter=file_filter,
            stats=stats,
            dry_run=False,
        )

        self.assertEqual(stats.files_total, 1)
        self.assertEqual(stats.bytes_total, 2048)
        download_file_mock.assert_called_once()