"""Tests for the top-level wrapper module entrypoint."""

import os
import runpy
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestWrapperEntrypoint(unittest.TestCase):
    """Test the compatibility wrapper's __main__ entrypoint."""

    @patch("icloud_downloader_lib.app.main", side_effect=SystemExit(0))
    def test_running_wrapper_as_main_invokes_main(self, package_main_mock):
        with self.assertRaises(SystemExit) as exc_info:
            runpy.run_module("icloud_downloader", run_name="__main__")

        self.assertEqual(exc_info.exception.code, 0)
        package_main_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()