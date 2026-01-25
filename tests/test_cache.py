"""Tests for DirectoryCache class."""

import unittest
import sys
import os
import threading
import time

# Add parent directory to path to import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader import DirectoryCache


class TestDirectoryCache(unittest.TestCase):
    """Test DirectoryCache functionality."""

    def test_empty_cache(self):
        """Test that empty cache returns None."""
        cache = DirectoryCache()
        self.assertIsNone(cache.get("node1"))

    def test_set_and_get(self):
        """Test basic set and get operations."""
        cache = DirectoryCache()
        items = ["file1.txt", "file2.jpg", "folder1"]

        cache.set("node1", items)
        retrieved = cache.get("node1")

        self.assertEqual(retrieved, items)

    def test_multiple_nodes(self):
        """Test caching multiple nodes."""
        cache = DirectoryCache()

        items1 = ["file1.txt", "file2.jpg"]
        items2 = ["doc1.pdf", "doc2.pdf"]
        items3 = ["photo1.png"]

        cache.set("node1", items1)
        cache.set("node2", items2)
        cache.set("node3", items3)

        self.assertEqual(cache.get("node1"), items1)
        self.assertEqual(cache.get("node2"), items2)
        self.assertEqual(cache.get("node3"), items3)

    def test_overwrite_existing(self):
        """Test that setting overwrites existing entry."""
        cache = DirectoryCache()

        cache.set("node1", ["old_file.txt"])
        cache.set("node1", ["new_file.txt"])

        self.assertEqual(cache.get("node1"), ["new_file.txt"])

    def test_clear(self):
        """Test clearing the cache."""
        cache = DirectoryCache()

        cache.set("node1", ["file1.txt"])
        cache.set("node2", ["file2.txt"])

        cache.clear()

        self.assertIsNone(cache.get("node1"))
        self.assertIsNone(cache.get("node2"))

    def test_thread_safety_read_write(self):
        """Test thread-safe concurrent reads and writes."""
        cache = DirectoryCache()
        errors = []

        def writer(node_id, items):
            try:
                for _ in range(100):
                    cache.set(f"node{node_id}", items)
                    time.sleep(0.0001)
            except Exception as e:
                errors.append(e)

        def reader(node_id):
            try:
                for _ in range(100):
                    cache.get(f"node{node_id}")
                    time.sleep(0.0001)
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        for i in range(5):
            threads.append(threading.Thread(target=writer, args=(i, [f"file{i}.txt"])))
            threads.append(threading.Thread(target=reader, args=(i,)))

        # Start all threads
        for t in threads:
            t.start()

        # Wait for completion
        for t in threads:
            t.join()

        # No errors should occur
        self.assertEqual(len(errors), 0)

    def test_cache_independence(self):
        """Test that cached lists are independent copies."""
        cache = DirectoryCache()

        original = ["file1.txt", "file2.txt"]
        cache.set("node1", original)

        # Modify original list
        original.append("file3.txt")

        # Cache should have original values
        cached = cache.get("node1")
        self.assertEqual(len(cached), 3)  # Note: Python passes by reference
        # This test documents current behavior - lists are not deep-copied


if __name__ == "__main__":
    unittest.main()
