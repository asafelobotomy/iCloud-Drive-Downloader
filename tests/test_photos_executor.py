"""Tests for the iCloud Photos Library executor."""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader_lib.photos_executor import download_photo_asset, run_photos_session
from icloud_downloader_lib.state import DownloadManifest, DownloadStats, StructuredLogger


def make_config(**overrides):
    config = {
        "max_retries": 2,
        "timeout": 60,
        "chunk_size": 4,
        "dry_run": False,
        "verbose": False,
        "progress_every_bytes": 1024 * 1024,
    }
    config.update(overrides)
    return config


def make_asset(filename="photo.jpg", size=100, content=b"imgdata"):
    asset = Mock()
    asset.filename = filename
    asset.size = size
    asset.created = None
    response = Mock()
    response.iter_content = lambda chunk_size: iter([content])
    asset.download = Mock(return_value=response)
    return asset


class TestDownloadPhotoAssetDryRun(unittest.TestCase):
    """Dry-run mode prints a preview and updates stats without writing files."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_dry_run_prints_preview_and_updates_stats(self):
        asset = make_asset()
        stats = DownloadStats()
        failures = []

        download_photo_asset(asset, self.temp_dir, failures, make_config(dry_run=True), stats=stats)

        self.assertEqual(failures, [], "dry-run should produce no failures")
        self.assertFalse(
            os.path.exists(os.path.join(self.temp_dir, "photo.jpg")),
            "dry-run must not write any file",
        )
        asset.download.assert_not_called()
        summary = stats.get_summary()
        self.assertEqual(summary["files_total"], 1)
        self.assertEqual(summary["files_completed"], 0)


class TestDownloadPhotoAssetSkip(unittest.TestCase):
    """Assets already downloaded or present are skipped without re-downloading."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.file_path = os.path.join(self.temp_dir, "photo.jpg")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_skips_asset_when_manifest_marks_complete(self):
        # Arrange: file exists and manifest says complete
        with open(self.file_path, "wb") as f:
            f.write(b"existing")
        manifest = DownloadManifest(os.path.join(self.temp_dir, "manifest.json"))
        manifest.mark_complete(self.file_path, 8)
        asset = make_asset()
        stats = DownloadStats()
        failures = []

        # Act
        download_photo_asset(asset, self.temp_dir, failures, make_config(), manifest=manifest, stats=stats)

        # Assert
        asset.download.assert_not_called()
        self.assertEqual(stats.get_summary()["files_skipped"], 1)

    def test_skips_asset_when_file_exists_and_no_manifest(self):
        with open(self.file_path, "wb") as f:
            f.write(b"existing")
        asset = make_asset()
        stats = DownloadStats()
        failures = []

        download_photo_asset(asset, self.temp_dir, failures, make_config(), stats=stats)

        asset.download.assert_not_called()
        self.assertEqual(stats.get_summary()["files_skipped"], 1)


class TestDownloadPhotoAssetSuccess(unittest.TestCase):
    """Successful downloads write file content, update manifest, and update stats."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.file_path = os.path.join(self.temp_dir, "photo.jpg")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("icloud_downloader_lib.photos_executor.TENACITY_AVAILABLE", False)
    def test_download_writes_content_and_marks_manifest_complete(self):
        asset = make_asset(content=b"bytes123")
        manifest = DownloadManifest(os.path.join(self.temp_dir, "manifest.json"))
        stats = DownloadStats()
        failures = []

        download_photo_asset(asset, self.temp_dir, failures, make_config(), manifest=manifest, stats=stats)

        self.assertEqual(failures, [])
        self.assertTrue(os.path.exists(self.file_path), "file should have been written")
        with open(self.file_path, "rb") as f:
            self.assertEqual(f.read(), b"bytes123")
        self.assertTrue(manifest.is_complete(self.file_path))
        summary = stats.get_summary()
        self.assertEqual(summary["files_completed"], 1)
        self.assertEqual(summary["files_failed"], 0)

    @patch("icloud_downloader_lib.photos_executor.TENACITY_AVAILABLE", False)
    def test_download_accepts_raw_bytes_from_pyicloud_asset_download(self):
        asset = Mock()
        asset.filename = "photo.jpg"
        asset.size = 8
        asset.created = None
        asset.download = Mock(return_value=b"bytes123")
        failures = []

        download_photo_asset(asset, self.temp_dir, failures, make_config())

        self.assertEqual(failures, [])
        with open(self.file_path, "rb") as downloaded_file:
            self.assertEqual(downloaded_file.read(), b"bytes123")

    @patch("icloud_downloader_lib.photos_executor.TENACITY_AVAILABLE", False)
    def test_path_traversal_in_filename_is_blocked(self):
        # filename with path components must not escape download_path
        asset = make_asset(filename="../escape.jpg")
        failures = []

        download_photo_asset(asset, self.temp_dir, failures, make_config())

        escaped = os.path.join(os.path.dirname(self.temp_dir), "escape.jpg")
        self.assertFalse(
            os.path.exists(escaped),
            "path traversal in asset filename must be neutralised",
        )


class TestDownloadPhotoAssetFailure(unittest.TestCase):
    """Download errors are recorded in failures and reflected in stats."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("icloud_downloader_lib.photos_executor.TENACITY_AVAILABLE", False)
    @patch("icloud_downloader_lib.photos_executor.time.sleep")
    def test_non_retryable_failure_appends_to_failures_and_marks_failed(self, _sleep):
        asset = Mock()
        asset.filename = "bad.jpg"
        asset.size = 0
        asset.download = Mock(side_effect=ValueError("invalid response"))
        stats = DownloadStats()
        failures = []

        download_photo_asset(asset, self.temp_dir, failures, make_config(), stats=stats)

        self.assertEqual(len(failures), 1)
        self.assertEqual(stats.get_summary()["files_failed"], 1)

    @patch("icloud_downloader_lib.photos_executor.TENACITY_AVAILABLE", False)
    @patch("icloud_downloader_lib.photos_executor.random.uniform", return_value=0.0)
    @patch("icloud_downloader_lib.photos_executor.time.sleep")
    def test_retryable_failure_retries_up_to_max_retries(self, _sleep, _rand):
        asset = Mock()
        asset.filename = "retry.jpg"
        asset.size = 0
        asset.download = Mock(side_effect=ConnectionError("network error"))
        failures = []

        download_photo_asset(asset, self.temp_dir, failures, make_config(max_retries=2))

        self.assertEqual(asset.download.call_count, 2)
        self.assertEqual(len(failures), 1)


class TestRunPhotosSession(unittest.TestCase):
    """run_photos_session routes to the correct collection based on photos_scope."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("icloud_downloader_lib.photos_executor.TENACITY_AVAILABLE", False)
    def test_all_scope_iterates_photos_all(self):
        asset = make_asset()
        api = MagicMock()
        api.photos.all = [asset]
        failures = []

        run_photos_session(api, make_config(photos_scope="all"), self.temp_dir, failures)

        asset.download.assert_called_once()

    @patch("icloud_downloader_lib.photos_executor.TENACITY_AVAILABLE", False)
    def test_videos_scope_iterates_videos_album(self):
        asset = make_asset(filename="clip.mov")
        api = MagicMock()
        api.photos.albums = {"Videos": [asset]}
        failures = []

        run_photos_session(api, make_config(photos_scope="videos"), self.temp_dir, failures)

        asset.download.assert_called_once()

    def test_missing_videos_album_exits_gracefully(self):
        api = MagicMock()
        api.photos.albums = {}  # "Videos" key absent
        failures = []

        # Should not raise
        run_photos_session(api, make_config(photos_scope="videos"), self.temp_dir, failures)

        self.assertEqual(failures, [])

    @patch("icloud_downloader_lib.photos_executor.TENACITY_AVAILABLE", False)
    def test_default_scope_falls_back_to_all(self):
        asset = make_asset()
        api = MagicMock()
        api.photos.all = [asset]
        config = make_config()
        config.pop("photos_scope", None)
        failures = []

        run_photos_session(api, config, self.temp_dir, failures)

        asset.download.assert_called_once()


class TestPhotosLoggerIntegration(unittest.TestCase):
    """Verify StructuredLogger receives events from the photos download path."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _read_log_events(self, log_path):
        import json
        with open(log_path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def test_dry_run_logs_dry_run_file_event(self):
        asset = make_asset()
        log_path = os.path.join(self.temp_dir, "photos.jsonl")
        logger = StructuredLogger(log_path, base_path=self.temp_dir)
        stats = DownloadStats()

        download_photo_asset(
            asset, self.temp_dir, [], make_config(dry_run=True), stats=stats, logger=logger,
        )

        event_types = [e["event"] for e in self._read_log_events(log_path)]
        self.assertIn("dry_run_file", event_types)

    @patch("icloud_downloader_lib.photos_executor.TENACITY_AVAILABLE", False)
    def test_completed_download_logs_file_completed_event(self):
        asset = make_asset()
        log_path = os.path.join(self.temp_dir, "photos.jsonl")
        logger = StructuredLogger(log_path, base_path=self.temp_dir)
        stats = DownloadStats()

        download_photo_asset(
            asset, self.temp_dir, [], make_config(), stats=stats, logger=logger,
        )

        event_types = [e["event"] for e in self._read_log_events(log_path)]
        self.assertIn("file_completed", event_types)

    def test_skipped_download_logs_file_skipped_event(self):
        asset = make_asset()
        local_path = os.path.join(self.temp_dir, "photo.jpg")
        with open(local_path, "wb") as f:
            f.write(b"existing")
        log_path = os.path.join(self.temp_dir, "photos.jsonl")
        logger = StructuredLogger(log_path, base_path=self.temp_dir)
        stats = DownloadStats()

        download_photo_asset(
            asset, self.temp_dir, [], make_config(), stats=stats, logger=logger,
        )

        event_types = [e["event"] for e in self._read_log_events(log_path)]
        self.assertIn("file_skipped", event_types)


if __name__ == "__main__":
    unittest.main()
