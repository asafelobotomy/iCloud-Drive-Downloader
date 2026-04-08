import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple

from .filters import FileFilter, ensure_directory, open_secure_file
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

DownloadWorkerTask = Tuple[
    Any,
    str,
    str,
    Dict[str, Any],
    Optional[DownloadManifest],
    Optional[FileFilter],
    Optional[DownloadStats],
    Optional[StructuredLogger],
    bool,
    Any,
]


def describe_transfer_error(error: Optional[BaseException]) -> str:
    """Return a privacy-safe description for transfer failures."""
    if error is None:
        return "Unknown transfer error"
    detail = sanitize_upstream_error_text(str(error))
    if detail and detail != type(error).__name__:
        return f"{type(error).__name__}: {detail}"
    return detail or type(error).__name__


def download_file(
    item: Any,
    local_path: str,
    failures: List[str],
    label: str,
    config: Dict[str, Any],
    manifest: Optional[DownloadManifest] = None,
    file_filter: Optional[FileFilter] = None,
    stats: Optional[DownloadStats] = None,
    logger: Optional[StructuredLogger] = None,
    dry_run: bool = False,
    pbar: Any = None,
) -> None:
    """Download a single file with retries and minimal progress feedback."""
    if file_filter:
        try:
            size = getattr(item, "size", None)
        except Exception:
            size = None

        if not file_filter.should_include(local_path, size=size):
            if config.get("verbose"):
                print(f"  -> Filtered out: '{label}'")
            if logger:
                logger.log("file_filtered", file=local_path, reason="pattern_or_size")
            return

    if dry_run:
        size = getattr(item, "size", 0) if hasattr(item, "size") else 0
        print(f"  [DRY RUN] Would download: '{label}' ({size} bytes)")
        if stats:
            stats.add_file(size)
        if logger:
            logger.log("dry_run_file", file=local_path, size=size)
        return

    if manifest and manifest.is_complete(local_path):
        if os.path.exists(local_path):
            print(f"  -> Skipping '{label}' (already complete in manifest)")
            if stats:
                stats.mark_skipped()
            if logger:
                logger.log("file_skipped", file=local_path, reason="already_complete")
            return

    if os.path.exists(local_path):
        existing_size = os.path.getsize(local_path)
        if manifest and existing_size > 0:
            status = manifest.get_file_status(local_path)
            if status.get("status") == "partial":
                print(f"  -> Resuming '{label}' from {existing_size} bytes")
                if logger:
                    logger.log("file_resume", file=local_path, existing_bytes=existing_size)
            else:
                print(f"  -> Skipping '{label}' (already exists)")
                if stats:
                    stats.mark_skipped()
                if logger:
                    logger.log("file_skipped", file=local_path, reason="already_exists")
                return
        else:
            print(f"  -> Skipping '{label}' (already exists)")
            if stats:
                stats.mark_skipped()
            if logger:
                logger.log("file_skipped", file=local_path, reason="already_exists")
            return

    def should_retry(exception: BaseException) -> bool:
        return is_retryable_error(exception)

    def handle_retry_error(retry_state: RetryStateLike) -> None:
        exception = retry_state.outcome.exception()
        attempt = retry_state.attempt_number
        is_throttled = is_rate_limit_error(exception)

        if is_throttled and stats:
            stats.mark_throttled()

        if is_throttled:
            wait_time = min(2.0 * (2 ** (attempt - 1)), 120.0)
            jitter = random.uniform(0, wait_time * 0.1)
            wait_time += jitter

            if stats and stats.should_warn_throttle():
                print(f"{Colors.YELLOW}⚠️  Rate limiting detected! Slowing down...{Colors.RESET}")
                print(
                    f"{Colors.YELLOW}    Consider reducing workers (current: {config.get('workers', 'N/A')}){Colors.RESET}"
                )
            print(
                f"{Colors.YELLOW}    -> Rate limited, waiting {wait_time:.1f}s before retry {attempt + 1}. Error: {describe_transfer_error(exception)}{Colors.RESET}"
            )
        else:
            wait_time = min(1.0 * (2 ** (attempt - 1)), 60.0)
            jitter = random.uniform(0, wait_time * 0.1)
            wait_time += jitter
            print(
                f"    -> Retryable transfer error, waiting {wait_time:.1f}s before retry {attempt + 1}. Error: {describe_transfer_error(exception)}"
            )

        time.sleep(wait_time)

    def _download_with_retry(attempt_tracker: Dict[str, int]) -> int:
        attempt = attempt_tracker.get("count", 0) + 1
        attempt_tracker["count"] = attempt

        print(
            f"  -> Downloading file: {label} (attempt {attempt}/{config['max_retries']})"
        )

        if manifest:
            manifest.update_file(local_path, "partial", 0, 0)

        downloaded = 0
        next_progress = config["progress_every_bytes"]

        download_root = str(config.get("download_root") or os.path.dirname(local_path) or ".")
        ensure_directory(os.path.dirname(local_path), download_root, 0o700)

        with item.open(stream=True) as response:
            with open_secure_file(local_path, download_root, "wb", permissions=0o600) as file_out:
                for chunk in response.iter_content(chunk_size=config["chunk_size"]):
                    if not chunk:
                        continue
                    file_out.write(chunk)
                    downloaded += len(chunk)
                    if downloaded >= next_progress:
                        print(f"     ... {downloaded // (1024 * 1024)} MB downloaded for {label}")
                        next_progress += config["progress_every_bytes"]
                        if manifest:
                            manifest.update_file(local_path, "partial", downloaded, 0)

        return downloaded

    attempt_tracker = {"count": 0}
    try:
        if TENACITY_AVAILABLE:
            download_func = build_retry_decorator(
                should_retry, config["max_retries"], before_sleep=handle_retry_error
            )(_download_with_retry)
            downloaded = download_func(attempt_tracker)
        else:
            downloaded = None
            for attempt in range(1, config["max_retries"] + 1):
                try:
                    downloaded = _download_with_retry(attempt_tracker)
                    break
                except Exception as error:
                    if attempt < config["max_retries"] and should_retry(error):
                        handle_retry_error(ManualRetryState(error, attempt))
                    else:
                        raise

        if downloaded is None:
            raise RuntimeError("Download failed after all retries")

        print(f"  -> Saved '{label}' ({downloaded} bytes)")
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
        if pbar:
            pbar.update(1)

    except Exception as error:
        is_throttled = is_rate_limit_error(error)
        error_detail = describe_transfer_error(error)

        if os.path.exists(local_path):
            partial_size = os.path.getsize(local_path)
            if manifest:
                manifest.update_file(local_path, "failed", partial_size, 0, error_detail)

        failures.append(f"Download failed: {error_detail}")
        if is_throttled:
            print(
                f"{Colors.YELLOW}    -> RATE LIMITED: Download failed after {attempt_tracker['count']} attempts. Error: {error_detail}{Colors.RESET}"
            )
            print(
                f"{Colors.YELLOW}    💡 Tip: Try reducing workers with --workers 1 or --sequential{Colors.RESET}"
            )
        else:
            print(f"    -> FAILED to download after {attempt_tracker['count']} attempts. Error: {error_detail}")

        if stats:
            stats.mark_failed()
        if logger:
            logger.log(
                "file_failed",
                file=local_path,
                error_type=type(error).__name__,
                attempts=attempt_tracker["count"],
                throttled=is_throttled,
            )
        if pbar:
            pbar.update(1)


def download_worker(task: DownloadWorkerTask) -> List[str]:
    """Worker function for concurrent downloads."""
    (
        item,
        local_path,
        label,
        config,
        manifest,
        file_filter,
        stats,
        logger,
        dry_run,
        pbar,
    ) = task
    failures: List[str] = []
    download_file(
        item,
        local_path,
        failures,
        label,
        config,
        manifest,
        file_filter,
        stats,
        logger,
        dry_run,
        pbar,
    )
    return failures