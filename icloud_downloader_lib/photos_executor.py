import os
import random
import time
from datetime import date as _date
from typing import Any, Callable, Dict, Iterator, List, Optional

from .filters import ensure_directory, open_secure_file, sanitize_name
from .privacy import sanitize_upstream_error_text
from .presentation import Colors
from .retry import (
    ManualRetryState,
    RetryStateLike,
    TENACITY_AVAILABLE,
    build_retry_decorator,
    is_rate_limit_error,
    is_retryable_error,
)
from .state import DownloadManifest, DownloadStats, StructuredLogger

_VIDEO_EXTENSIONS: frozenset = frozenset({
    ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".wmv", ".3gp", ".3g2", ".webm",
})


def _resolve_photo_path(download_path: str, filename: str, created: Any = None) -> str:
    """Resolve a safe local path for a photo asset, preventing path traversal.

    When `created` is a valid datetime, assets are organised into a YYYY-MM-DD
    sub-directory to prevent filename collisions across different dates.
    """
    safe_name = sanitize_name(os.path.basename(filename))
    if created is not None:
        try:
            subdir = created.strftime("%Y-%m-%d")
            if isinstance(subdir, str):
                return os.path.join(download_path, subdir, safe_name)
        except (AttributeError, OSError, ValueError, TypeError):
            pass
    return os.path.join(download_path, safe_name)


def _iter_photo_download_chunks(download_result: Any, chunk_size: int) -> Iterator[bytes]:
    """Yield photo download data from either raw bytes or a streaming response."""
    if download_result is None:
        raise ValueError("Photo download returned no data")

    if isinstance(download_result, memoryview):
        payload = download_result.tobytes()
        for index in range(0, len(payload), max(chunk_size, 1)):
            yield payload[index:index + max(chunk_size, 1)]
        return

    if isinstance(download_result, (bytes, bytearray)):
        payload = bytes(download_result)
        for index in range(0, len(payload), max(chunk_size, 1)):
            yield payload[index:index + max(chunk_size, 1)]
        return

    if hasattr(download_result, "iter_content"):
        for chunk in download_result.iter_content(chunk_size=chunk_size):
            if chunk:
                yield chunk
        return

    if hasattr(download_result, "read"):
        while True:
            chunk = download_result.read(chunk_size)
            if not chunk:
                break
            yield chunk
        return

    raise TypeError(f"Unsupported photo download response type: {type(download_result).__name__}")


def _asset_in_date_range(asset: Any, after: Optional[str], before: Optional[str]) -> bool:
    """Return True if asset.created falls within [after, before]; both bounds are optional."""
    if not after and not before:
        return True
    created = getattr(asset, "created", None)
    if created is None:
        return True
    try:
        asset_date = created.date() if hasattr(created, "date") else created
        if after and asset_date < _date.fromisoformat(after):
            return False
        if before and asset_date > _date.fromisoformat(before):
            return False
    except (ValueError, AttributeError):
        return True
    return True


def _list_albums(api: Any) -> Dict[str, Any]:
    """Return a sorted dict mapping album name to album object."""
    albums: Dict[str, Any] = {}
    try:
        for name in api.photos.albums:
            try:
                albums[str(name)] = api.photos.albums[name]
            except (KeyError, TypeError):
                pass
    except AttributeError:
        pass
    return dict(sorted(albums.items()))


def _pick_album_interactive(
    albums: Dict[str, Any],
    input_func: Callable[[str], str],
) -> Optional[str]:
    """Print a numbered album list and return the name chosen by the user."""
    if not albums:
        return None
    names = list(albums.keys())
    print("\nAvailable albums:")
    for i, name in enumerate(names, start=1):
        print(f"  {i}. {name}")
    raw = input_func("\nEnter album number or name [1]: ").strip()
    if not raw:
        return names[0]
    if raw.isdigit() and 1 <= int(raw) <= len(names):
        return names[int(raw) - 1]
    return raw if raw in albums else None


def _group_by_month(collection: Any) -> Dict[str, List[Any]]:
    """Bucket photo assets by YYYY-MM using their created date."""
    groups: Dict[str, List[Any]] = {}
    for asset in collection:
        created = getattr(asset, "created", None)
        key = created.strftime("%Y-%m") if created else "unknown"
        groups.setdefault(key, []).append(asset)
    return dict(sorted(groups.items()))


def _pick_month_interactive(
    months: Dict[str, List[Any]],
    input_func: Callable[[str], str],
) -> Optional[str]:
    """Print a numbered month list with counts and return the chosen month."""
    if not months:
        return None
    keys = list(months.keys())
    print("\nAvailable months:")
    for i, key in enumerate(keys, start=1):
        print(f"  {i}. {key} ({len(months[key])} items)")
    raw = input_func("\nEnter month number or key [1]: ").strip()
    if not raw:
        return keys[0]
    if raw.isdigit() and 1 <= int(raw) <= len(keys):
        return keys[int(raw) - 1]
    return raw if raw in months else None


def _run_album_session(
    api: Any,
    config: Dict[str, Any],
    download_path: str,
    failures: List[str],
    manifest: Optional["DownloadManifest"],
    stats: Optional["DownloadStats"],
    logger: Optional["StructuredLogger"],
    input_func: Callable[[str], str],
) -> None:
    """Download all assets from a single Photos Library album."""
    albums = _list_albums(api)
    if not albums:
        print(f"{Colors.YELLOW}No albums found in iCloud Photos Library.{Colors.RESET}")
        return
    album_name = config.get("photos_album") or _pick_album_interactive(albums, input_func)
    if not album_name or album_name not in albums:
        print(f"{Colors.RED}Album not found or not selected.{Colors.RESET}")
        return
    collection = albums[album_name]
    print(f"\n--- iCloud Photos Library: Album '{album_name}' ---")
    after = config.get("photos_after")
    before = config.get("photos_before")
    for asset in collection:
        if _asset_in_date_range(asset, after, before):
            download_photo_asset(asset, download_path, failures, config, manifest, stats, logger)


def _run_month_session(
    api: Any,
    config: Dict[str, Any],
    download_path: str,
    failures: List[str],
    manifest: Optional["DownloadManifest"],
    stats: Optional["DownloadStats"],
    logger: Optional["StructuredLogger"],
    input_func: Callable[[str], str],
) -> None:
    """Download all assets from a single month in the Photos Library."""
    print(f"{Colors.CYAN}Scanning library to list months (may take a moment)...{Colors.RESET}")
    groups = _group_by_month(api.photos.all)
    if not groups:
        print(f"{Colors.YELLOW}No photos found in iCloud Photos Library.{Colors.RESET}")
        return
    month_key = config.get("photos_month") or _pick_month_interactive(groups, input_func)
    if not month_key or month_key not in groups:
        print(f"{Colors.RED}Month not found or not selected.{Colors.RESET}")
        return
    assets = groups[month_key]
    print(f"\n--- iCloud Photos Library: {month_key} ({len(assets)} items) ---")
    after = config.get("photos_after")
    before = config.get("photos_before")
    for asset in assets:
        if _asset_in_date_range(asset, after, before):
            download_photo_asset(asset, download_path, failures, config, manifest, stats, logger)


def download_photo_asset(
    asset: Any,
    download_path: str,
    failures: List[str],
    config: Dict[str, Any],
    manifest: Optional[DownloadManifest] = None,
    stats: Optional[DownloadStats] = None,
    logger: Optional[StructuredLogger] = None,
) -> None:
    """Download a single Photos Library asset with retry and manifest support."""
    filename = getattr(asset, "filename", None) or "unknown"
    created = getattr(asset, "created", None)
    local_path = _resolve_photo_path(download_path, filename, created)
    size = getattr(asset, "size", 0) or 0
    label = filename

    if config.get("dry_run"):
        print(f"  [DRY RUN] Would download: '{label}' ({size} bytes)")
        if stats:
            stats.add_file(size)
        if logger:
            logger.log("dry_run_file", file=local_path, size=size)
        return

    if manifest and manifest.is_complete(local_path) and os.path.exists(local_path):
        print(f"  -> Skipping '{label}' (already complete)")
        if stats:
            stats.mark_skipped()
        if logger:
            logger.log("file_skipped", file=local_path, reason="already_complete")
        return

    if os.path.exists(local_path):
        if not manifest or manifest.get_file_status(local_path).get("status") != "partial":
            print(f"  -> Skipping '{label}' (already exists)")
            if stats:
                stats.mark_skipped()
            if logger:
                logger.log("file_skipped", file=local_path, reason="already_exists")
            return

    def _should_retry(exception: BaseException) -> bool:
        return is_retryable_error(exception)

    def _handle_retry_error(retry_state: RetryStateLike) -> None:
        exception = retry_state.outcome.exception()
        attempt = retry_state.attempt_number
        is_throttled = is_rate_limit_error(exception)
        if is_throttled and stats:
            stats.mark_throttled()
        wait_time = min((2.0 if is_throttled else 1.0) * (2 ** (attempt - 1)), 120.0)
        wait_time += random.uniform(0, wait_time * 0.1)
        if is_throttled:
            print(
                f"{Colors.YELLOW}    -> Rate limited, waiting {wait_time:.1f}s"
                f" before retry {attempt + 1}.{Colors.RESET}"
            )
        else:
            detail = sanitize_upstream_error_text(str(exception))
            print(
                f"    -> Retryable error, waiting {wait_time:.1f}s"
                f" before retry {attempt + 1}. Error: {detail}"
            )
        time.sleep(wait_time)

    def _attempt_download(attempt_tracker: Dict[str, int]) -> int:
        attempt = attempt_tracker.get("count", 0) + 1
        attempt_tracker["count"] = attempt
        print(f"  -> Downloading: '{label}' (attempt {attempt}/{config['max_retries']})")
        if manifest:
            manifest.update_file(local_path, "partial", 0, 0)
        response = asset.download()
        download_root = str(config.get("download_root") or download_path)
        ensure_directory(os.path.dirname(local_path), download_root, 0o700)
        downloaded = 0
        with open_secure_file(local_path, download_root, "wb", permissions=0o600) as out_file:
            for chunk in _iter_photo_download_chunks(response, config["chunk_size"]):
                if chunk:
                    out_file.write(chunk)
                    downloaded += len(chunk)
        return downloaded

    attempt_tracker: Dict[str, int] = {"count": 0}
    try:
        if TENACITY_AVAILABLE:
            download_func = build_retry_decorator(
                _should_retry, config["max_retries"], before_sleep=_handle_retry_error
            )(_attempt_download)
            downloaded = download_func(attempt_tracker)
        else:
            downloaded = None
            for attempt_num in range(1, config["max_retries"] + 1):
                try:
                    downloaded = _attempt_download(attempt_tracker)
                    break
                except Exception as error:
                    if attempt_num < config["max_retries"] and _should_retry(error):
                        _handle_retry_error(ManualRetryState(error, attempt_num))
                    else:
                        raise

        if downloaded is None:
            raise RuntimeError("Download failed after all retries")

        if manifest:
            manifest.mark_complete(local_path, downloaded)
        if stats:
            stats.mark_completed(downloaded)
        if logger:
            logger.log(
                "file_completed",
                file=local_path,
                bytes=downloaded,
                attempts=attempt_tracker["count"],
            )
        print(f"  -> Saved '{label}' ({downloaded} bytes)")

    except Exception as error:
        detail = sanitize_upstream_error_text(str(error))
        err_msg = f"Download failed for '{label}': {detail}"
        print(f"  {Colors.RED}\u2717{Colors.RESET} {err_msg}")
        failures.append(err_msg)
        if stats:
            stats.mark_failed()
        if logger:
            logger.log(
                "file_failed",
                file=local_path,
                error=err_msg,
                attempts=attempt_tracker["count"],
            )


def run_photos_session(
    api: Any,
    config: Dict[str, Any],
    download_path: str,
    failures: List[str],
    manifest: Optional[DownloadManifest] = None,
    stats: Optional[DownloadStats] = None,
    logger: Optional[StructuredLogger] = None,
    input_func: Callable[[str], str] = input,
) -> None:
    """Iterate and download assets from the iCloud Photos Library."""
    scope = config.get("photos_scope", "all")
    config["download_root"] = download_path

    if scope == "by-album":
        _run_album_session(api, config, download_path, failures, manifest, stats, logger, input_func)
    elif scope == "by-month":
        _run_month_session(api, config, download_path, failures, manifest, stats, logger, input_func)
    elif scope == "videos":
        try:
            collection = api.photos.albums["Videos"]
            print("\n--- iCloud Photos Library: All Videos ---")
        except (KeyError, AttributeError):
            print(f"{Colors.YELLOW}Videos album not found in iCloud Photos Library.{Colors.RESET}")
            return
        after = config.get("photos_after")
        before = config.get("photos_before")
        for asset in collection:
            if _asset_in_date_range(asset, after, before):
                download_photo_asset(asset, download_path, failures, config, manifest, stats, logger)
    elif scope == "photos":
        collection = api.photos.all
        print("\n--- iCloud Photos Library: All Photos ---")
        after = config.get("photos_after")
        before = config.get("photos_before")
        for asset in collection:
            filename = getattr(asset, "filename", "") or ""
            if os.path.splitext(filename.lower())[1] in _VIDEO_EXTENSIONS:
                continue
            if _asset_in_date_range(asset, after, before):
                download_photo_asset(asset, download_path, failures, config, manifest, stats, logger)
    else:
        collection = api.photos.all
        print("\n--- iCloud Photos Library: All Photos & Videos ---")
        after = config.get("photos_after")
        before = config.get("photos_before")
        for asset in collection:
            if _asset_in_date_range(asset, after, before):
                download_photo_asset(asset, download_path, failures, config, manifest, stats, logger)
