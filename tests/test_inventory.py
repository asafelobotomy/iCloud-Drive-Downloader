"""Tests for privacy-preserving dry-run inventory aggregation."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader_lib.inventory import DryRunInventory, classify_storage_category


class TestInventory(unittest.TestCase):
    """Test dry-run aggregate inventory helpers."""

    def test_classify_storage_category_uses_extension_groups(self):
        self.assertEqual(classify_storage_category("photo.JPG"), "photos")
        self.assertEqual(classify_storage_category("clip.mov"), "videos")
        self.assertEqual(classify_storage_category("doc.pdf"), "documents")
        self.assertEqual(classify_storage_category("song.mp3"), "audio")
        self.assertEqual(classify_storage_category("archive.zip"), "archives")
        self.assertEqual(classify_storage_category("unknown.bin"), "other")

    def test_dry_run_inventory_tracks_root_totals_and_matches(self):
        inventory = DryRunInventory(max_depth=1, max_items=1)

        inventory.record_folder(level=1, preview=True, is_root=True)
        inventory.record_folder(level=2, preview=False)
        inventory.mark_empty_folder()
        inventory.record_file("/tmp/private/photo.jpg", 200, included=True, level=1, preview=True, is_root=True)
        inventory.record_file("/tmp/private/video.mov", 500, included=True, level=2, preview=False)
        inventory.record_file("/tmp/private/report.pdf", 100, included=False, level=2, preview=False)

        summary = inventory.snapshot()

        self.assertEqual(summary["root_items"], 2)
        self.assertEqual(summary["root_folders"], 1)
        self.assertEqual(summary["root_files"], 1)
        self.assertEqual(summary["total_items"], 5)
        self.assertEqual(summary["total_folders"], 2)
        self.assertEqual(summary["total_files"], 3)
        self.assertEqual(summary["total_bytes"], 800)
        self.assertEqual(summary["matched_files"], 2)
        self.assertEqual(summary["matched_bytes"], 700)
        self.assertEqual(summary["preview_items"], 2)
        self.assertEqual(summary["preview_folders"], 1)
        self.assertEqual(summary["preview_files"], 1)
        self.assertEqual(summary["preview_matched_files"], 1)
        self.assertEqual(summary["preview_matched_bytes"], 200)
        self.assertEqual(summary["deepest_level"], 2)
        self.assertEqual(summary["empty_folders"], 1)
        self.assertEqual(summary["category_counts"]["photos"], 1)
        self.assertEqual(summary["category_counts"]["videos"], 1)
        self.assertEqual(summary["category_counts"]["documents"], 1)


if __name__ == "__main__":
    unittest.main()