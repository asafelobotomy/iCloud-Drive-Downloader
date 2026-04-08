"""Tests for Photos Library album and month navigation helpers."""
import os
import sys
import types
from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icloud_downloader_lib.photos_executor import (
    _asset_in_date_range,
    _group_by_month,
    _list_albums,
    _pick_album_interactive,
    _pick_month_interactive,
    _run_album_session,
    _run_month_session,
    run_photos_session,
)


def _make_asset(filename: str = "photo.jpg", created: Any = None) -> MagicMock:
    asset = MagicMock()
    asset.filename = filename
    asset.size = 100
    asset.created = created
    resp = MagicMock()
    resp.iter_content.return_value = [b"data"]
    asset.download.return_value = resp
    return asset


def _make_api(albums: Dict[str, Any], all_assets: List[Any] | None = None) -> MagicMock:
    api = MagicMock()
    api.photos.albums = albums
    api.photos.all = all_assets or []
    return api


def _base_config() -> Dict[str, Any]:
    return {
        "dry_run": True,
        "max_retries": 1,
        "chunk_size": 8192,
        "download_root": "/tmp/test",
    }


# ---------------------------------------------------------------------------
# _list_albums
# ---------------------------------------------------------------------------


class TestListAlbums:
    def test_returns_sorted_dict(self) -> None:
        api = _make_api({"Zoo": MagicMock(), "Animals": MagicMock()})
        result = _list_albums(api)
        assert list(result.keys()) == ["Animals", "Zoo"]

    def test_returns_empty_when_no_albums(self) -> None:
        api = _make_api({})
        assert _list_albums(api) == {}

    def test_handles_attribute_error(self) -> None:
        api = MagicMock()
        del api.photos  # trigger AttributeError on api.photos
        result = _list_albums(api)
        assert result == {}


# ---------------------------------------------------------------------------
# _pick_album_interactive
# ---------------------------------------------------------------------------


class TestPickAlbumInteractive:
    def _albums(self) -> Dict[str, Any]:
        return {"Alpha": MagicMock(), "Beta": MagicMock(), "Gamma": MagicMock()}

    def test_numeric_choice(self) -> None:
        result = _pick_album_interactive(self._albums(), lambda _: "2")
        assert result == "Beta"

    def test_name_choice(self) -> None:
        result = _pick_album_interactive(self._albums(), lambda _: "Gamma")
        assert result == "Gamma"

    def test_empty_input_picks_first(self) -> None:
        result = _pick_album_interactive(self._albums(), lambda _: "")
        assert result == "Alpha"

    def test_invalid_numeric_returns_none(self) -> None:
        result = _pick_album_interactive(self._albums(), lambda _: "99")
        assert result is None

    def test_empty_albums_returns_none(self) -> None:
        result = _pick_album_interactive({}, lambda _: "1")
        assert result is None


# ---------------------------------------------------------------------------
# _group_by_month
# ---------------------------------------------------------------------------


class TestGroupByMonth:
    def test_groups_by_month(self) -> None:
        a1 = _make_asset("a.jpg", datetime(2025, 1, 15))
        a2 = _make_asset("b.jpg", datetime(2025, 1, 20))
        a3 = _make_asset("c.jpg", datetime(2025, 3, 5))
        groups = _group_by_month([a1, a2, a3])
        assert list(groups.keys()) == ["2025-01", "2025-03"]
        assert len(groups["2025-01"]) == 2
        assert len(groups["2025-03"]) == 1

    def test_unknown_when_no_created(self) -> None:
        asset = _make_asset("x.jpg", None)
        groups = _group_by_month([asset])
        assert "unknown" in groups

    def test_returns_sorted_dict(self) -> None:
        assets = [
            _make_asset("c.jpg", datetime(2025, 3, 1)),
            _make_asset("a.jpg", datetime(2025, 1, 1)),
            _make_asset("b.jpg", datetime(2025, 2, 1)),
        ]
        groups = _group_by_month(assets)
        assert list(groups.keys()) == ["2025-01", "2025-02", "2025-03"]


# ---------------------------------------------------------------------------
# _pick_month_interactive
# ---------------------------------------------------------------------------


class TestPickMonthInteractive:
    def _months(self) -> Dict[str, List[Any]]:
        return {
            "2025-01": [MagicMock()],
            "2025-02": [MagicMock(), MagicMock()],
        }

    def test_numeric_choice(self) -> None:
        result = _pick_month_interactive(self._months(), lambda _: "2")
        assert result == "2025-02"

    def test_key_choice(self) -> None:
        result = _pick_month_interactive(self._months(), lambda _: "2025-01")
        assert result == "2025-01"

    def test_empty_input_picks_first(self) -> None:
        result = _pick_month_interactive(self._months(), lambda _: "")
        assert result == "2025-01"

    def test_invalid_returns_none(self) -> None:
        result = _pick_month_interactive(self._months(), lambda _: "99")
        assert result is None

    def test_empty_months_returns_none(self) -> None:
        result = _pick_month_interactive({}, lambda _: "1")
        assert result is None


# ---------------------------------------------------------------------------
# _run_album_session
# ---------------------------------------------------------------------------


class TestRunAlbumSession:
    def test_uses_config_album_without_prompt(self, capsys: Any) -> None:
        asset = _make_asset("img.jpg")
        album = MagicMock()
        album.__iter__ = MagicMock(return_value=iter([asset]))
        albums = {"Favorites": album, "Other": MagicMock()}
        api = _make_api(albums)
        config = _base_config()
        config["photos_album"] = "Favorites"
        prompt_called = []

        def no_prompt(msg: str) -> str:
            prompt_called.append(msg)
            return ""

        _run_album_session(api, config, "/tmp", [], None, None, None, no_prompt)
        out = capsys.readouterr().out
        assert "Favorites" in out
        assert not prompt_called

    def test_prompts_when_no_album_in_config(self, capsys: Any) -> None:
        asset = _make_asset("shot.heic")
        album = MagicMock()
        album.__iter__ = MagicMock(return_value=iter([asset]))
        albums = {"Summer": album}
        api = _make_api(albums)
        config = _base_config()
        _run_album_session(api, config, "/tmp", [], None, None, None, lambda _: "1")
        out = capsys.readouterr().out
        assert "Summer" in out

    def test_album_not_found_prints_error(self, capsys: Any) -> None:
        api = _make_api({"Real": MagicMock()})
        config = {**_base_config(), "photos_album": "DoesNotExist"}
        _run_album_session(api, config, "/tmp", [], None, None, None, lambda _: "")
        out = capsys.readouterr().out
        assert "not found" in out.lower() or "not selected" in out.lower()

    def test_no_albums_prints_message(self, capsys: Any) -> None:
        api = _make_api({})
        _run_album_session(api, _base_config(), "/tmp", [], None, None, None, lambda _: "")
        out = capsys.readouterr().out
        assert "No albums" in out


# ---------------------------------------------------------------------------
# _run_month_session
# ---------------------------------------------------------------------------


class TestRunMonthSession:
    def test_uses_config_month_without_prompt(self, capsys: Any) -> None:
        asset = _make_asset("jan.jpg", datetime(2025, 1, 10))
        api = _make_api({}, [asset])
        config = {**_base_config(), "photos_month": "2025-01"}
        prompt_called = []
        _run_month_session(api, config, "/tmp", [], None, None, None, lambda _: prompt_called.append("x") or "")
        out = capsys.readouterr().out
        assert "2025-01" in out
        assert not prompt_called

    def test_prompts_when_no_month_in_config(self, capsys: Any) -> None:
        asset = _make_asset("feb.jpg", datetime(2025, 2, 5))
        api = _make_api({}, [asset])
        config = _base_config()
        _run_month_session(api, config, "/tmp", [], None, None, None, lambda _: "1")
        out = capsys.readouterr().out
        assert "2025-02" in out

    def test_month_not_found_prints_error(self, capsys: Any) -> None:
        asset = _make_asset("mar.jpg", datetime(2025, 3, 1))
        api = _make_api({}, [asset])
        config = {**_base_config(), "photos_month": "1900-01"}
        _run_month_session(api, config, "/tmp", [], None, None, None, lambda _: "")
        out = capsys.readouterr().out
        assert "not found" in out.lower() or "not selected" in out.lower()

    def test_empty_library_prints_message(self, capsys: Any) -> None:
        api = _make_api({}, [])
        _run_month_session(api, _base_config(), "/tmp", [], None, None, None, lambda _: "")
        out = capsys.readouterr().out
        assert "No photos" in out


# ---------------------------------------------------------------------------
# run_photos_session routing
# ---------------------------------------------------------------------------


class TestRunPhotosSessionRouting:
    def test_routes_by_album(self, capsys: Any) -> None:
        album = MagicMock()
        album.__iter__ = MagicMock(return_value=iter([]))
        api = _make_api({"Best Of": album})
        config = {**_base_config(), "photos_scope": "by-album", "photos_album": "Best Of"}
        run_photos_session(api, config, "/tmp", [], input_func=lambda _: "")
        out = capsys.readouterr().out
        assert "Best Of" in out

    def test_routes_by_month(self, capsys: Any) -> None:
        api = _make_api({}, [_make_asset("x.jpg", datetime(2024, 6, 1))])
        config = {**_base_config(), "photos_scope": "by-month", "photos_month": "2024-06"}
        run_photos_session(api, config, "/tmp", [], input_func=lambda _: "")
        out = capsys.readouterr().out
        assert "2024-06" in out


# ---------------------------------------------------------------------------
# _asset_in_date_range
# ---------------------------------------------------------------------------


class TestAssetInDateRange:
    def _asset(self, dt: Any) -> MagicMock:
        a = MagicMock()
        a.created = dt
        return a

    def test_no_bounds_always_true(self) -> None:
        assert _asset_in_date_range(self._asset(datetime(2025, 6, 1)), None, None) is True

    def test_after_bound_excludes_earlier(self) -> None:
        assert _asset_in_date_range(self._asset(datetime(2025, 1, 1)), "2025-06-01", None) is False

    def test_after_bound_includes_same_day(self) -> None:
        assert _asset_in_date_range(self._asset(datetime(2025, 6, 1)), "2025-06-01", None) is True

    def test_before_bound_excludes_later(self) -> None:
        assert _asset_in_date_range(self._asset(datetime(2025, 12, 31)), None, "2025-06-01") is False

    def test_before_bound_includes_same_day(self) -> None:
        assert _asset_in_date_range(self._asset(datetime(2025, 6, 1)), None, "2025-06-01") is True

    def test_both_bounds_in_range(self) -> None:
        assert _asset_in_date_range(self._asset(datetime(2025, 3, 15)), "2025-01-01", "2025-12-31") is True

    def test_no_created_attr_returns_true(self) -> None:
        a = MagicMock()
        a.created = None
        assert _asset_in_date_range(a, "2025-01-01", "2025-12-31") is True

    def test_invalid_date_string_returns_true(self) -> None:
        assert _asset_in_date_range(self._asset(datetime(2025, 6, 1)), "not-a-date", None) is True
