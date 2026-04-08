"""Tests for _migrate_config_file — legacy config-key upgrade helper in app.py."""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader_lib.app import _migrate_config_file


class TestMigrateConfigFile(unittest.TestCase):
    """Verify _migrate_config_file upgrades legacy save_login_info keys correctly."""

    def test_no_legacy_key_leaves_config_unchanged(self):
        # Arrange
        config = {"destination": "/tmp/dl", "workers": 4}
        # Act
        _migrate_config_file(config)
        # Assert
        self.assertEqual(config, {"destination": "/tmp/dl", "workers": 4})

    def test_save_login_info_true_sets_both_new_keys(self):
        # Arrange
        config = {"save_login_info": True, "destination": "/tmp/dl"}
        # Act
        _migrate_config_file(config)
        # Assert — old key removed, both new keys added
        self.assertNotIn("save_login_info", config)
        self.assertTrue(config["save_apple_id"])
        self.assertTrue(config["save_2fa_session"])

    def test_save_login_info_false_removes_key_without_setting_new_keys(self):
        # Arrange
        config = {"save_login_info": False, "destination": "/tmp/dl"}
        # Act
        _migrate_config_file(config)
        # Assert — old key removed, new keys NOT added
        self.assertNotIn("save_login_info", config)
        self.assertNotIn("save_apple_id", config)
        self.assertNotIn("save_2fa_session", config)

    def test_save_login_info_true_does_not_overwrite_explicit_new_keys(self):
        # Arrange — user explicitly opted out of both in new-schema config that
        # also carries the old key (edge case: config written by an older version
        # and then manually edited).
        config = {
            "save_login_info": True,
            "save_apple_id": False,
            "save_2fa_session": False,
        }
        # Act
        _migrate_config_file(config)
        # Assert — setdefault must NOT overwrite the explicit False values
        self.assertNotIn("save_login_info", config)
        self.assertFalse(config["save_apple_id"])
        self.assertFalse(config["save_2fa_session"])

    def test_migration_is_idempotent_when_called_twice(self):
        # Arrange
        config = {"save_login_info": True}
        # Act
        _migrate_config_file(config)
        _migrate_config_file(config)  # second call — no save_login_info present
        # Assert — stable result, no KeyError
        self.assertNotIn("save_login_info", config)
        self.assertTrue(config["save_apple_id"])
        self.assertTrue(config["save_2fa_session"])

    def test_other_keys_are_preserved_during_migration(self):
        # Arrange
        config = {"save_login_info": True, "workers": 4, "retries": 3}
        # Act
        _migrate_config_file(config)
        # Assert — unrelated keys untouched
        self.assertEqual(config["workers"], 4)
        self.assertEqual(config["retries"], 3)


if __name__ == "__main__":
    unittest.main()
