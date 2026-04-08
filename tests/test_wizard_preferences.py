"""Tests for wizard_preferences helpers — download-mode inference and application."""

import sys
import os
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader_lib.wizard_preferences import (
    _apply_download_mode_choice,
    _print_download_mode_options,
    current_download_choice,
)
from icloud_downloader_lib.definitions import PRESETS


class TestCurrentDownloadChoicePhotosModes(unittest.TestCase):
    """Verify that photos-library scope values are mapped to the right choice codes."""

    def _photos_config(self, scope: str) -> dict:
        return {"source": "photos-library", "photos_scope": scope}

    def test_photos_all_returns_7(self):
        self.assertEqual(current_download_choice(self._photos_config("all")), "7")

    def test_photos_only_returns_8(self):
        self.assertEqual(current_download_choice(self._photos_config("photos")), "8")

    def test_videos_only_returns_9(self):
        self.assertEqual(current_download_choice(self._photos_config("videos")), "9")

    def test_by_album_returns_10(self):
        self.assertEqual(current_download_choice(self._photos_config("by-album")), "10")

    def test_by_month_hyphen_returns_11(self):
        self.assertEqual(current_download_choice(self._photos_config("by-month")), "11")

    def test_by_month_underscore_returns_11(self):
        # Legacy underscore variant stored in older configs
        self.assertEqual(current_download_choice(self._photos_config("by_month")), "11")

    def test_unknown_photos_scope_defaults_to_7(self):
        self.assertEqual(current_download_choice(self._photos_config("unknown")), "7")

    def test_photos_source_with_no_scope_defaults_to_7(self):
        self.assertEqual(current_download_choice({"source": "photos-library"}), "7")


class TestCurrentDownloadChoiceCacheModes(unittest.TestCase):
    """Verify cache-selector modes return the correct choice codes."""

    def test_cache_select_folders_mode_returns_2(self):
        config = {
            "refresh_inventory_cache": True,
            "select_from_cache": True,
            "selection_mode": "folders",
        }
        self.assertEqual(current_download_choice(config), "2")

    def test_cache_select_mixed_mode_returns_3(self):
        config = {
            "refresh_inventory_cache": True,
            "select_from_cache": True,
            "selection_mode": "mixed",
        }
        self.assertEqual(current_download_choice(config), "3")

    def test_cache_select_no_selection_mode_returns_3(self):
        config = {"refresh_inventory_cache": True, "select_from_cache": True}
        self.assertEqual(current_download_choice(config), "3")


class TestPrintDownloadModeOptions(unittest.TestCase):
    """Verify _print_download_mode_options outputs all expected mode labels."""

    def test_print_options_outputs_all_11_modes(self):
        buf = StringIO()
        with redirect_stdout(buf):
            _print_download_mode_options()
        output = buf.getvalue()
        for label in ("Everything", "By directory", "Explore Drive", "Documents",
                      "Quick test", "Custom filters", "All photos", "photos only",
                      "videos only", "album", "month"):
            self.assertIn(label, output, msg=f"Missing label: {label!r}")


class TestApplyDownloadModeChoice(unittest.TestCase):
    """Verify _apply_download_mode_choice mutates config as expected for each choice."""

    def _call(self, choice: str, config: dict | None = None, input_responses: list | None = None) -> dict:
        cfg = config or {}
        responses = iter(input_responses or ["", ""])
        enable_drive = MagicMock()
        enable_mixed = MagicMock()
        enable_photos = MagicMock()
        _apply_download_mode_choice(
            cfg,
            choice,
            input_func=lambda _: next(responses, ""),
            enable_drive_selector=enable_drive,
            enable_mixed_selector=enable_mixed,
            enable_photos_library=enable_photos,
            existing_include=[],
            existing_exclude=[],
        )
        return cfg

    def test_choice_4_applies_documents_preset(self):
        cfg = self._call("4")
        self.assertEqual(cfg.get("include"), PRESETS["documents"]["include"])

    def test_choice_5_applies_quick_test_preset(self):
        cfg = self._call("5")
        self.assertEqual(cfg.get("max_items"), PRESETS["quick-test"]["max_items"])
        self.assertEqual(cfg.get("max_depth"), PRESETS["quick-test"]["max_depth"])

    def test_choice_7_enables_photos_library_all(self):
        enable_photos = MagicMock()
        cfg: dict = {}
        _apply_download_mode_choice(
            cfg, "7",
            input_func=lambda _: "",
            enable_drive_selector=MagicMock(),
            enable_mixed_selector=MagicMock(),
            enable_photos_library=enable_photos,
            existing_include=[],
            existing_exclude=[],
        )
        enable_photos.assert_called_once_with(cfg, "all")

    def test_choice_8_enables_photos_only(self):
        enable_photos = MagicMock()
        cfg: dict = {}
        _apply_download_mode_choice(
            cfg, "8",
            input_func=lambda _: "",
            enable_drive_selector=MagicMock(),
            enable_mixed_selector=MagicMock(),
            enable_photos_library=enable_photos,
            existing_include=[],
            existing_exclude=[],
        )
        enable_photos.assert_called_once_with(cfg, "photos")

    def test_choice_9_enables_videos_only(self):
        enable_photos = MagicMock()
        cfg: dict = {}
        _apply_download_mode_choice(
            cfg, "9",
            input_func=lambda _: "",
            enable_drive_selector=MagicMock(),
            enable_mixed_selector=MagicMock(),
            enable_photos_library=enable_photos,
            existing_include=[],
            existing_exclude=[],
        )
        enable_photos.assert_called_once_with(cfg, "videos")

    def test_choice_10_enables_by_album(self):
        enable_photos = MagicMock()
        cfg: dict = {}
        _apply_download_mode_choice(
            cfg, "10",
            input_func=lambda _: "",
            enable_drive_selector=MagicMock(),
            enable_mixed_selector=MagicMock(),
            enable_photos_library=enable_photos,
            existing_include=[],
            existing_exclude=[],
        )
        enable_photos.assert_called_once_with(cfg, "by-album")

    def test_choice_11_enables_by_month(self):
        enable_photos = MagicMock()
        cfg: dict = {}
        _apply_download_mode_choice(
            cfg, "11",
            input_func=lambda _: "",
            enable_drive_selector=MagicMock(),
            enable_mixed_selector=MagicMock(),
            enable_photos_library=enable_photos,
            existing_include=[],
            existing_exclude=[],
        )
        enable_photos.assert_called_once_with(cfg, "by-month")

    def test_choice_6_captures_include_and_exclude_patterns(self):
        responses = iter(["*.jpg,*.png", "*.tmp"])
        cfg = {}
        _apply_download_mode_choice(
            cfg, "6",
            input_func=lambda _: next(responses, ""),
            enable_drive_selector=MagicMock(),
            enable_mixed_selector=MagicMock(),
            enable_photos_library=MagicMock(),
            existing_include=[],
            existing_exclude=[],
        )
        self.assertIn("*.jpg", cfg.get("include", []))
        self.assertIn("*.png", cfg.get("include", []))
        self.assertIn("*.tmp", cfg.get("exclude", []))

    def test_choice_6_falls_back_to_existing_include_on_empty_input(self):
        cfg = {}
        _apply_download_mode_choice(
            cfg, "6",
            input_func=lambda _: "",
            enable_drive_selector=MagicMock(),
            enable_mixed_selector=MagicMock(),
            enable_photos_library=MagicMock(),
            existing_include=["*.pdf"],
            existing_exclude=[],
        )
        self.assertIn("*.pdf", cfg.get("include", []))


if __name__ == "__main__":
    unittest.main()
