"""Tests for traversal-specific recursion and early-return edge paths."""

import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader_lib.state import DownloadStats
from icloud_downloader_lib.traversal import collect_download_tasks, download_node


class FakeNode:
    """Minimal folder node stub used for traversal tests."""

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
        value = self._children[key]
        if isinstance(value, Exception):
            raise value
        return value


class TestTraversalEdges(unittest.TestCase):
    """Test traversal branches not covered by the existing traversal suites."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_download_node_returns_immediately_on_shutdown(self):
        stdout = StringIO()
        shutdown_handler = Mock()
        shutdown_handler.should_stop.return_value = True
        node = FakeNode("root", directory_error=AssertionError("dir should not be called"))

        with redirect_stdout(stdout):
            download_node(node, os.path.join(self.temp_dir, "root"), [], {}, self.temp_dir, shutdown_handler=shutdown_handler)

        self.assertIn("Skipping 'root' due to shutdown request", stdout.getvalue())

    def test_download_node_respects_max_depth_with_verbose_message(self):
        stdout = StringIO()

        with redirect_stdout(stdout):
            download_node(
                FakeNode("nested"),
                os.path.join(self.temp_dir, "nested"),
                [],
                {"verbose": True},
                self.temp_dir,
                depth=1,
                max_depth=1,
            )

        self.assertIn("max depth 1 reached", stdout.getvalue())

    @patch("icloud_downloader_lib.traversal.download_file")
    def test_download_node_creates_directories_uses_cache_and_chmods_downloaded_files(self, download_file_mock):
        local_path = os.path.join(self.temp_dir, "root")
        child_local_path = os.path.join(local_path, "file.txt")
        dir_cache = Mock()
        dir_cache.get.return_value = ["file.txt"]
        file_item = SimpleNamespace(type="file", size=12)
        node = FakeNode("root", children={"file.txt": file_item})

        def fake_exists(path):
            return path == child_local_path

        with patch("icloud_downloader_lib.traversal.os.path.exists", side_effect=fake_exists):
            with patch("icloud_downloader_lib.traversal.ensure_directory") as ensure_directory_mock:
                with patch("icloud_downloader_lib.traversal.set_file_permissions") as set_file_permissions_mock:
                    download_node(node, local_path, [], {}, self.temp_dir, dir_cache=dir_cache)

        dir_cache.set.assert_not_called()
        ensure_directory_mock.assert_called_once_with(local_path, self.temp_dir, 0o700)
        download_file_mock.assert_called_once()
        set_file_permissions_mock.assert_called_once_with(child_local_path, self.temp_dir, 0o600)

    def test_download_node_records_item_processing_failures(self):
        failures = []
        node = FakeNode("root", children={"bad.txt": RuntimeError("broken item")})

        download_node(node, os.path.join(self.temp_dir, "root"), failures, {}, self.temp_dir)

        self.assertEqual(len(failures), 1)
        self.assertIn("bad.txt", failures[0])

    def test_download_node_reports_empty_folder(self):
        stdout = StringIO()

        with redirect_stdout(stdout):
            download_node(FakeNode("empty"), os.path.join(self.temp_dir, "empty"), [], {}, self.temp_dir)

        self.assertIn("Folder 'empty' is empty.", stdout.getvalue())

    def test_download_node_records_path_validation_failures(self):
        failures = []

        download_node(
            FakeNode("root"),
            os.path.join(self.temp_dir, "..", "escape"),
            failures,
            {},
            self.temp_dir,
        )

        self.assertEqual(len(failures), 1)
        self.assertIn("Path validation failed", failures[0])

    @patch("icloud_downloader_lib.traversal.download_file")
    def test_download_node_caches_directory_listing_and_recurses_into_folders(self, download_file_mock):
        dir_cache = Mock()
        dir_cache.get.return_value = None
        node = FakeNode("root", children={"nested": FakeNode("nested")})

        download_node(node, os.path.join(self.temp_dir, "root"), [], {}, self.temp_dir, dir_cache=dir_cache)

        self.assertGreaterEqual(dir_cache.set.call_count, 1)
        download_file_mock.assert_not_called()

    @patch("icloud_downloader_lib.traversal.download_file")
    def test_download_node_breaks_file_loop_when_shutdown_is_requested_mid_iteration(self, download_file_mock):
        shutdown_handler = Mock()
        shutdown_handler.should_stop.side_effect = [False, True]
        node = FakeNode(
            "root",
            children={
                "first.txt": SimpleNamespace(type="file", size=1),
                "second.txt": SimpleNamespace(type="file", size=1),
            },
        )

        download_node(node, os.path.join(self.temp_dir, "root"), [], {}, self.temp_dir, shutdown_handler=shutdown_handler)

        download_file_mock.assert_not_called()

    def test_collect_download_tasks_returns_early_for_shutdown_depth_and_item_limits(self):
        tasks = []
        failures = []
        stats = DownloadStats()
        stats.files_total = 2
        node = FakeNode("root", directory_error=AssertionError("dir should not be called"))
        shutdown_handler = Mock()
        shutdown_handler.should_stop.return_value = True

        collect_download_tasks(node, os.path.join(self.temp_dir, "shutdown"), {}, self.temp_dir, None, None, tasks, failures, shutdown_handler=shutdown_handler)
        collect_download_tasks(node, os.path.join(self.temp_dir, "depth"), {}, self.temp_dir, None, None, tasks, failures, depth=1, max_depth=1)
        collect_download_tasks(node, os.path.join(self.temp_dir, "limit"), {"max_items": 1}, self.temp_dir, None, None, tasks, failures, stats=stats)

        self.assertEqual(tasks, [])
        self.assertEqual(failures, [])

    def test_collect_download_tasks_creates_directory_and_adds_included_files(self):
        local_path = os.path.join(self.temp_dir, "root")
        tasks = []
        failures = []
        stats = DownloadStats()
        dir_cache = Mock()
        dir_cache.get.return_value = ["photo.jpg"]
        file_filter = Mock()
        file_filter.should_include.return_value = True
        file_item = SimpleNamespace(type="file", size=25)
        node = FakeNode("root", children={"photo.jpg": file_item})

        collect_download_tasks(
            node,
            local_path,
            {},
            self.temp_dir,
            None,
            dir_cache,
            tasks,
            failures,
            file_filter=file_filter,
            stats=stats,
        )

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0][1], os.path.join(local_path, "photo.jpg"))
        self.assertEqual(stats.files_total, 1)
        self.assertEqual(failures, [])

    def test_collect_download_tasks_records_directory_listing_failures(self):
        tasks = []
        failures = []

        collect_download_tasks(
            FakeNode("root", directory_error=RuntimeError("boom")),
            os.path.join(self.temp_dir, "root"),
            {},
            self.temp_dir,
            None,
            None,
            tasks,
            failures,
        )

        self.assertEqual(tasks, [])
        self.assertEqual(len(failures), 1)
        self.assertIn("Could not list contents", failures[0])

    def test_collect_download_tasks_recurses_into_folders(self):
        tasks = []
        failures = []
        node = FakeNode("root", children={"nested": FakeNode("nested")})

        collect_download_tasks(
            node,
            os.path.join(self.temp_dir, "root"),
            {},
            self.temp_dir,
            None,
            Mock(get=Mock(return_value=None), set=Mock()),
            tasks,
            failures,
        )

        self.assertEqual(tasks, [])
        self.assertEqual(failures, [])

    def test_collect_download_tasks_breaks_file_loop_for_shutdown_and_item_limits(self):
        local_path = os.path.join(self.temp_dir, "root")
        node = FakeNode("root", children={"first.txt": SimpleNamespace(type="file", size=3)})

        shutdown_tasks = []
        shutdown_handler = Mock()
        shutdown_handler.should_stop.side_effect = [False, True]
        collect_download_tasks(
            node,
            local_path,
            {},
            self.temp_dir,
            None,
            None,
            shutdown_tasks,
            [],
            shutdown_handler=shutdown_handler,
        )

        limited_tasks = []
        stats = DownloadStats()
        stats.files_total = 1
        collect_download_tasks(
            node,
            local_path,
            {"max_items": 1},
            self.temp_dir,
            None,
            None,
            limited_tasks,
            [],
            stats=stats,
        )

        self.assertEqual(shutdown_tasks, [])
        self.assertEqual(limited_tasks, [])

    def test_collect_download_tasks_breaks_after_reaching_max_items_during_iteration(self):
        local_path = os.path.join(self.temp_dir, "root")
        tasks = []
        stats = DownloadStats()
        node = FakeNode(
            "root",
            children={
                "first.txt": SimpleNamespace(type="file", size=3),
                "second.txt": SimpleNamespace(type="file", size=4),
            },
        )

        collect_download_tasks(
            node,
            local_path,
            {"max_items": 1},
            self.temp_dir,
            None,
            None,
            tasks,
            [],
            stats=stats,
        )

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0][2], "first.txt")

    def test_collect_download_tasks_treats_unknown_file_size_as_zero(self):
        local_path = os.path.join(self.temp_dir, "root")
        tasks = []
        stats = DownloadStats()
        node = FakeNode(
            "root",
            children={
                "nested": FakeNode(
                    "nested",
                    children={"Character Bios.odt": SimpleNamespace(type="file", size=None)},
                )
            },
        )

        collect_download_tasks(
            node,
            local_path,
            {},
            self.temp_dir,
            None,
            None,
            tasks,
            [],
            stats=stats,
        )

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0][2], "Character Bios.odt")
        self.assertEqual(stats.files_total, 1)
        self.assertEqual(stats.bytes_total, 0)

    def test_collect_download_tasks_skips_completed_or_filtered_files_and_records_item_errors(self):
        local_path = os.path.join(self.temp_dir, "root")
        os.makedirs(local_path, exist_ok=True)
        existing_path = os.path.join(local_path, "done.txt")
        with open(existing_path, "w", encoding="utf-8"):
            pass

        tasks = []
        failures = []
        manifest = Mock()
        manifest.is_complete.side_effect = lambda path: path == existing_path
        file_filter = Mock()
        file_filter.should_include.side_effect = lambda path, size=None: not path.endswith("skip.txt")
        node = FakeNode(
            "root",
            children={
                "done.txt": SimpleNamespace(type="file", size=5),
                "skip.txt": SimpleNamespace(type="file", size=5),
                "broken.txt": RuntimeError("cannot load item"),
            },
        )

        collect_download_tasks(
            node,
            local_path,
            {},
            self.temp_dir,
            manifest,
            None,
            tasks,
            failures,
            file_filter=file_filter,
            stats=DownloadStats(),
        )

        self.assertEqual(tasks, [])
        self.assertEqual(len(failures), 1)
        self.assertIn("broken.txt", failures[0])


if __name__ == "__main__":
    unittest.main()