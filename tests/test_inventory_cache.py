"""Tests for secure inventory cache persistence and selector helpers."""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader_lib.inventory import DryRunInventory
from icloud_downloader_lib.inventory_cache import InventoryTreeBuilder, load_inventory_cache, save_inventory_cache
from icloud_downloader_lib.selector import normalize_selection, summarize_selection


class TestInventoryCache(unittest.TestCase):
    """Test secure inventory cache persistence and selection helpers."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_inventory_cache_persists_owner_only_json_payload(self):
        cache_path = os.path.join(self.temp_dir, "inventory-cache.json")
        payload = {"metadata": {"schema_version": 1}, "nodes": [{"id": "root", "parent_id": None}]}

        save_inventory_cache(cache_path, payload)
        loaded_payload = load_inventory_cache(cache_path)

        self.assertEqual(loaded_payload, payload)
        self.assertEqual(os.stat(cache_path).st_mode & 0o777, 0o600)

    def test_tree_builder_and_selector_helpers_deduplicate_selected_paths(self):
        inventory = DryRunInventory()
        inventory.record_folder(level=1, is_root=True)
        inventory.record_folder(level=2)
        inventory.record_file(
            os.path.join(self.temp_dir, "Photos", "Trips", "rome.jpg"),
            200,
            included=True,
            level=3,
        )
        inventory.record_file(
            os.path.join(self.temp_dir, "Docs", "report.pdf"),
            100,
            included=True,
            level=2,
        )
        builder = InventoryTreeBuilder(self.temp_dir)
        builder.record_folder(os.path.join(self.temp_dir, "Photos"), "Photos", depth=1, child_count=1)
        builder.record_folder(
            os.path.join(self.temp_dir, "Photos", "Trips"),
            "Trips",
            depth=2,
            child_count=1,
        )
        builder.record_file(
            os.path.join(self.temp_dir, "Photos", "Trips", "rome.jpg"),
            "rome.jpg",
            size=200,
            depth=3,
            included=True,
        )
        builder.record_folder(os.path.join(self.temp_dir, "Docs"), "Docs", depth=1, child_count=1)
        builder.record_file(
            os.path.join(self.temp_dir, "Docs", "report.pdf"),
            "report.pdf",
            size=100,
            depth=2,
            included=True,
        )
        payload = builder.build_payload(inventory, {"max_depth": None, "max_items": None}, 2)
        node_ids = {node["relative_path"]: node["id"] for node in payload["nodes"] if "relative_path" in node}

        selection = normalize_selection(
            payload,
            [node_ids["Photos/Trips"], node_ids["Photos/Trips/rome.jpg"], node_ids["Docs/report.pdf"]],
        )
        summary = summarize_selection(payload, selection)

        self.assertEqual(selection["selected_folders"], {"Photos/Trips"})
        self.assertEqual(selection["selected_files"], {"Docs/report.pdf"})
        self.assertEqual(summary, {"files": 2, "bytes": 300})