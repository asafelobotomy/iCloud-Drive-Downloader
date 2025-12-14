import os
import re
import sys
import argparse
import time
import random
import shutil
import json
import threading
import fnmatch
import signal
import logging
from pathlib import Path
from datetime import datetime
from getpass import getpass
from queue import Queue
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

try:
    from pyicloud import PyiCloudService
    from pyicloud.exceptions import PyiCloudFailedLoginException
    PYICLOUD_AVAILABLE = True
except ImportError:
    PYICLOUD_AVAILABLE = False

# --- Default Configuration ---
DEFAULT_DOWNLOAD_PATH = os.path.join(os.path.expanduser('~'), 'iCloud_Drive_Download')
DEFAULT_CHUNK_SIZE = 8192
DEFAULT_PROGRESS_EVERY_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT = 60  # seconds
DEFAULT_MIN_FREE_SPACE_GB = 1  # minimum free space in GB
DEFAULT_MAX_WORKERS = 3  # concurrent downloads
MANIFEST_FILENAME = '.icloud_download_manifest.json'
LOG_FILENAME = 'icloud_download.log.jsonl'
CONFIG_FILENAME = '.icloud_downloader.json'

# Retryable HTTP status codes and exceptions
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
RETRYABLE_EXCEPTIONS = (ConnectionError, TimeoutError)


class ShutdownHandler:
    """Handle graceful shutdown on signals."""
    
    def __init__(self):
        self.shutdown_requested = False
        self.lock = threading.Lock()
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
    
    def _handle_signal(self, signum, frame):
        """Signal handler for SIGINT and SIGTERM."""
        with self.lock:
            if not self.shutdown_requested:
                print("\n\n*** Shutdown requested. Finishing current operations and saving state... ***")
                print("*** Press Ctrl+C again to force quit (may lose progress) ***\n")
                self.shutdown_requested = True
            else:
                print("\n*** Force quitting... ***")
                sys.exit(1)
    
    def should_stop(self):
        """Check if shutdown has been requested."""
        with self.lock:
            return self.shutdown_requested


class FileFilter:
    """Filter files based on patterns, size, and date thresholds."""
    
    def __init__(self, include_patterns=None, exclude_patterns=None, 
                 min_size=None, max_size=None, modified_after=None, modified_before=None):
        self.include_patterns = include_patterns or []
        self.exclude_patterns = exclude_patterns or []
        self.min_size = min_size
        self.max_size = max_size
        self.modified_after = modified_after
        self.modified_before = modified_before
    
    def should_include(self, file_path, size=None, modified_date=None):
        """Check if file should be included based on filters."""
        # If include patterns specified, file must match at least one
        if self.include_patterns:
            matched = False
            for pattern in self.include_patterns:
                if fnmatch.fnmatch(file_path, pattern) or fnmatch.fnmatch(os.path.basename(file_path), pattern):
                    matched = True
                    break
            if not matched:
                return False
        
        # If exclude patterns specified, file must not match any
        if self.exclude_patterns:
            for pattern in self.exclude_patterns:
                if fnmatch.fnmatch(file_path, pattern) or fnmatch.fnmatch(os.path.basename(file_path), pattern):
                    return False
        
        # Check size thresholds
        if size is not None:
            if self.min_size is not None and size < self.min_size:
                return False
            if self.max_size is not None and size > self.max_size:
                return False
        
        # Check date thresholds
        if modified_date is not None:
            if self.modified_after is not None and modified_date < self.modified_after:
                return False
            if self.modified_before is not None and modified_date > self.modified_before:
                return False
        
        return True


class DownloadStats:
    """Track download statistics."""
    
    def __init__(self):
        self.lock = threading.Lock()
        self.files_total = 0
        self.files_completed = 0
        self.files_skipped = 0
        self.files_failed = 0
        self.bytes_total = 0
        self.bytes_downloaded = 0
        self.start_time = None
        self.end_time = None
    
    def start(self):
        """Mark start time."""
        with self.lock:
            self.start_time = time.time()
    
    def finish(self):
        """Mark end time."""
        with self.lock:
            self.end_time = time.time()
    
    def add_file(self, size=0):
        """Add a file to total count."""
        with self.lock:
            self.files_total += 1
            self.bytes_total += size
    
    def mark_completed(self, bytes_downloaded=0):
        """Mark a file as completed."""
        with self.lock:
            self.files_completed += 1
            self.bytes_downloaded += bytes_downloaded
    
    def mark_skipped(self):
        """Mark a file as skipped."""
        with self.lock:
            self.files_skipped += 1
    
    def mark_failed(self):
        """Mark a file as failed."""
        with self.lock:
            self.files_failed += 1
    
    def get_summary(self):
        """Get summary statistics."""
        with self.lock:
            elapsed = (self.end_time or time.time()) - (self.start_time or time.time())
            return {
                'files_total': self.files_total,
                'files_completed': self.files_completed,
                'files_skipped': self.files_skipped,
                'files_failed': self.files_failed,
                'bytes_total': self.bytes_total,
                'bytes_downloaded': self.bytes_downloaded,
                'elapsed_seconds': elapsed
            }


class StructuredLogger:
    """JSON Lines structured logger."""
    
    def __init__(self, log_path=None):
        self.log_path = log_path
        self.lock = threading.Lock()
    
    def log(self, event_type, **data):
        """Log an event in JSONL format."""
        if not self.log_path:
            return
        
        entry = {
            'timestamp': datetime.now().isoformat(),
            'event': event_type,
            **data
        }
        
        with self.lock:
            try:
                with open(self.log_path, 'a') as f:
                    f.write(json.dumps(entry) + '\n')
            except IOError as e:
                print(f"Warning: Could not write to log: {e}")


class DownloadManifest:
    """Manages download state persistence and resume capability."""
    
    def __init__(self, manifest_path):
        self.manifest_path = manifest_path
        self.lock = threading.Lock()
        self.data = self._load()
    
    def _load(self):
        """Load manifest from disk or create new one."""
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load manifest ({e}), starting fresh.")
        return {'files': {}, 'metadata': {'created': datetime.now().isoformat()}}
    
    def _save(self):
        """Save manifest to disk."""
        try:
            with open(self.manifest_path, 'w') as f:
                json.dump(self.data, f, indent=2)
            os.chmod(self.manifest_path, 0o600)
        except IOError as e:
            print(f"Warning: Could not save manifest: {e}")
    
    def get_file_status(self, file_path):
        """Get status of a file from manifest."""
        with self.lock:
            return self.data['files'].get(file_path, {})
    
    def update_file(self, file_path, status, bytes_downloaded=0, total_bytes=0, error=None):
        """Update file status in manifest."""
        with self.lock:
            self.data['files'][file_path] = {
                'status': status,
                'bytes_downloaded': bytes_downloaded,
                'total_bytes': total_bytes,
                'last_updated': datetime.now().isoformat(),
                'error': error
            }
            self._save()
    
    def mark_complete(self, file_path, total_bytes):
        """Mark file as completed."""
        self.update_file(file_path, 'complete', total_bytes, total_bytes)
    
    def is_complete(self, file_path):
        """Check if file is already complete."""
        status = self.get_file_status(file_path)
        return status.get('status') == 'complete'


class DirectoryCache:
    """Cache directory listings to reduce API calls."""
    
    def __init__(self):
        self.cache = {}
        self.lock = threading.Lock()
    
    def get(self, node_name):
        """Get cached directory listing."""
        with self.lock:
            return self.cache.get(node_name)
    
    def set(self, node_name, items):
        """Cache directory listing."""
        with self.lock:
            self.cache[node_name] = items
    
    def clear(self):
        """Clear the cache."""
        with self.lock:
            self.cache.clear()


def sanitize_name(name):
    """Sanitize iCloud names for safe local filesystem use."""
    safe = name.replace(os.sep, '_').replace('\x00', '')
    safe = re.sub(r'[\r\n\t]', '_', safe).strip()
    return safe or 'unnamed'


def validate_path_safety(path, root):
    """Ensure path is within root directory and doesn't contain traversal patterns."""
    # Reject absolute paths and parent directory references
    if os.path.isabs(path):
        raise ValueError(f"Absolute paths not allowed: {path}")
    if '..' in path.split(os.sep):
        raise ValueError(f"Path traversal detected: {path}")
    
    # Resolve to absolute and check it's within root
    abs_path = os.path.abspath(path)
    abs_root = os.path.abspath(root)
    
    if not abs_path.startswith(abs_root + os.sep) and abs_path != abs_root:
        raise ValueError(f"Path escapes root: {path}")
    
    return abs_path


def calculate_backoff(attempt, base_delay=1.0, max_delay=60.0):
    """Calculate exponential backoff with jitter."""
    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
    jitter = random.uniform(0, delay * 0.1)  # 10% jitter
    return delay + jitter


def is_retryable_error(exception):
    """Classify if an error is retryable."""
    if isinstance(exception, RETRYABLE_EXCEPTIONS):
        return True
    
    # Check for HTTP status codes in exception message
    error_str = str(exception).lower()
    for code in RETRYABLE_STATUS_CODES:
        if str(code) in error_str:
            return True
    
    return False


def download_file(item, local_path, failures, label, config, manifest=None, 
                  file_filter=None, stats=None, logger=None, dry_run=False, pbar=None):
    """Download a single file with retries and minimal progress feedback."""
    # Apply filters
    if file_filter:
        # Try to get file size (may not be available for all items)
        try:
            size = getattr(item, 'size', None)
        except:
            size = None
        
        if not file_filter.should_include(local_path, size=size):
            if config.get('verbose'):
                print(f"  -> Filtered out: '{label}'")
            if logger:
                logger.log('file_filtered', file=local_path, reason='pattern_or_size')
            return
    
    # Dry run mode
    if dry_run:
        size = getattr(item, 'size', 0) if hasattr(item, 'size') else 0
        print(f"  [DRY RUN] Would download: '{label}' ({size} bytes)")
        if stats:
            stats.add_file(size)
        if logger:
            logger.log('dry_run_file', file=local_path, size=size)
        return
    
    # Check manifest for completion
    if manifest and manifest.is_complete(local_path):
        if os.path.exists(local_path):
            print(f"  -> Skipping '{label}' (already complete in manifest)")
            if stats:
                stats.mark_skipped()
            if logger:
                logger.log('file_skipped', file=local_path, reason='already_complete')
            return
    
    # Check if file exists and is complete
    existing_size = 0
    if os.path.exists(local_path):
        existing_size = os.path.getsize(local_path)
        # If manifest says incomplete, we can try to resume
        if manifest and existing_size > 0:
            status = manifest.get_file_status(local_path)
            if status.get('status') == 'partial':
                print(f"  -> Resuming '{label}' from {existing_size} bytes")
                if logger:
                    logger.log('file_resume', file=local_path, existing_bytes=existing_size)
            else:
                print(f"  -> Skipping '{label}' (already exists)")
                if stats:
                    stats.mark_skipped()
                if logger:
                    logger.log('file_skipped', file=local_path, reason='already_exists')
                return
        else:
            print(f"  -> Skipping '{label}' (already exists)")
            if stats:
                stats.mark_skipped()
            if logger:
                logger.log('file_skipped', file=local_path, reason='already_exists')
            return

    for attempt in range(1, config['max_retries'] + 1):
        try:
            # Determine if we're resuming
            resume_from = existing_size if existing_size > 0 and attempt == 1 else 0
            
            if resume_from > 0:
                print(f"  -> Resuming file: {label} from {resume_from} bytes (attempt {attempt}/{config['max_retries']})")
            else:
                print(f"  -> Downloading file: {label} (attempt {attempt}/{config['max_retries']})")
            
            if manifest:
                manifest.update_file(local_path, 'partial', resume_from, 0)
            
            downloaded = resume_from
            next_progress = ((downloaded // config['progress_every_bytes']) + 1) * config['progress_every_bytes']
            
            # Open file in append mode if resuming, otherwise write mode
            file_mode = 'ab' if resume_from > 0 else 'wb'
            
            with item.open(stream=True) as response:
                with open(local_path, file_mode) as file_out:
                    for chunk in response.iter_content(chunk_size=config['chunk_size']):
                        if not chunk:
                            continue
                        file_out.write(chunk)
                        downloaded += len(chunk)
                        if downloaded >= next_progress:
                            print(f"     ... {downloaded // (1024 * 1024)} MB downloaded for {label}")
                            next_progress += config['progress_every_bytes']
                            if manifest:
                                manifest.update_file(local_path, 'partial', downloaded, 0)
            
            print(f"  -> Saved '{label}' ({downloaded} bytes)")
            if manifest:
                manifest.mark_complete(local_path, downloaded)
            if stats:
                stats.mark_completed(downloaded)
            if logger:
                logger.log('file_completed', file=local_path, bytes=downloaded, attempts=attempt)
            if pbar:
                pbar.update(1)
            return
        except Exception as e:
            is_last_attempt = (attempt == config['max_retries'])
            retryable = is_retryable_error(e)
            
            # On non-retryable or last attempt, keep partial file for potential resume
            if not retryable or is_last_attempt:
                if os.path.exists(local_path):
                    partial_size = os.path.getsize(local_path)
                    if manifest:
                        manifest.update_file(local_path, 'failed', partial_size, 0, str(e))
            
            if is_last_attempt:
                failures.append(f"File '{label}': {e}")
                print(f"    -> FAILED to download '{label}'. Error: {e}")
                if stats:
                    stats.mark_failed()
                if logger:
                    logger.log('file_failed', file=local_path, error=str(e), attempts=attempt)
                if pbar:
                    pbar.update(1)
            elif retryable:
                backoff = calculate_backoff(attempt)
                print(f"    -> Retryable error downloading '{label}', waiting {backoff:.1f}s. Error: {e}")
                time.sleep(backoff)
            else:
                failures.append(f"File '{label}': Non-retryable error: {e}")
                print(f"    -> FAILED (non-retryable) to download '{label}'. Error: {e}")
                if stats:
                    stats.mark_failed()
                if logger:
                    logger.log('file_failed', file=local_path, error=str(e), retryable=False)
                if pbar:
                    pbar.update(1)
                return

def download_node(node, local_path, failures, config, root_path, manifest=None, 
                  dir_cache=None, file_filter=None, stats=None, logger=None, dry_run=False, 
                  pbar=None, shutdown_handler=None, depth=0, max_depth=None):
    """
    This function recursively downloads folders and files.
    """
    # Check for shutdown request
    if shutdown_handler and shutdown_handler.should_stop():
        print(f"Skipping '{node.name}' due to shutdown request")
        return
    
    # Check max depth
    if max_depth is not None and depth >= max_depth:
        if config.get('verbose'):
            print(f"Skipping '{node.name}' (max depth {max_depth} reached)")
        return
    # Validate path safety
    try:
        validate_path_safety(local_path, root_path)
    except ValueError as e:
        msg = f"Path validation failed for '{local_path}': {e}"
        failures.append(msg)
        print(msg)
        return
    
    # Create the local directory, including empty ones for structure.
    if not os.path.exists(local_path):
        print(f"Creating directory: {local_path}")
        os.makedirs(local_path, exist_ok=True)
        os.chmod(local_path, 0o700)  # Secure permissions

    # Try to get cached directory listing first
    cache_key = f"{node.name}_{id(node)}"
    child_item_names = None
    
    if dir_cache:
        child_item_names = dir_cache.get(cache_key)
    
    # If not cached, fetch from API
    if child_item_names is None:
        try:
            child_item_names = node.dir()
            if dir_cache:
                dir_cache.set(cache_key, child_item_names)
        except Exception as e:
            msg = f"Could not list contents for '{node.name}', skipping. Error: {e}"
            failures.append(msg)
            print(msg)
            return

    if child_item_names:
        print(f"Found {len(child_item_names)} items inside '{node.name}'...")
        for item_name in child_item_names:
            try:
                item = node[item_name]
                safe_name = sanitize_name(item_name)
                child_local_path = os.path.join(local_path, safe_name)

                if item.type == 'folder':
                    # Recursive call for the sub-folder
                    download_node(item, child_local_path, failures, config, root_path, manifest, 
                                dir_cache, file_filter, stats, logger, dry_run, pbar, 
                                shutdown_handler, depth + 1, max_depth)
                elif item.type == 'file':
                    # Check shutdown and max items
                    if shutdown_handler and shutdown_handler.should_stop():
                        break
                    if config.get('max_items') and stats and stats.files_total >= config['max_items']:
                        if config.get('verbose'):
                            print(f"Max items limit ({config['max_items']}) reached")
                        break
                    download_file(item, child_local_path, failures, item_name, config, manifest,
                                file_filter, stats, logger, dry_run, pbar)
                    # Set secure permissions on downloaded file
                    if os.path.exists(child_local_path):
                        os.chmod(child_local_path, 0o600)
            except Exception as e:
                failures.append(f"Item '{item_name}' in folder '{node.name}': {e}")
                print(f"    -> FAILED to process '{item_name}'. Error: {e}")
    else:
        print(f"Folder '{node.name}' is empty.")


def download_worker(task):
    """Worker function for concurrent downloads."""
    item, local_path, label, config, manifest, file_filter, stats, logger, dry_run, pbar = task
    failures = []
    download_file(item, local_path, failures, label, config, manifest, 
                 file_filter, stats, logger, dry_run, pbar)
    return failures


def collect_download_tasks(node, local_path, config, root_path, manifest, dir_cache, 
                          tasks_list, failures, file_filter=None, stats=None, 
                          shutdown_handler=None, depth=0, max_depth=None):
    """Recursively collect all download tasks without downloading."""
    # Check for shutdown request
    if shutdown_handler and shutdown_handler.should_stop():
        return
    
    # Check max depth
    if max_depth is not None and depth >= max_depth:
        return
    
    # Check max items
    if config.get('max_items') and stats and stats.files_total >= config['max_items']:
        return
    # Validate path safety
    try:
        validate_path_safety(local_path, root_path)
    except ValueError as e:
        msg = f"Path validation failed for '{local_path}': {e}"
        failures.append(msg)
        print(msg)
        return
    
    # Create the local directory
    if not os.path.exists(local_path):
        os.makedirs(local_path, exist_ok=True)
        os.chmod(local_path, 0o700)
    
    # Get directory listing
    cache_key = f"{node.name}_{id(node)}"
    child_item_names = None
    
    if dir_cache:
        child_item_names = dir_cache.get(cache_key)
    
    if child_item_names is None:
        try:
            child_item_names = node.dir()
            if dir_cache:
                dir_cache.set(cache_key, child_item_names)
        except Exception as e:
            msg = f"Could not list contents for '{node.name}', skipping. Error: {e}"
            failures.append(msg)
            print(msg)
            return
    
    if child_item_names:
        for item_name in child_item_names:
            try:
                item = node[item_name]
                safe_name = sanitize_name(item_name)
                child_local_path = os.path.join(local_path, safe_name)
                
                if item.type == 'folder':
                    collect_download_tasks(item, child_local_path, config, root_path, manifest, dir_cache, 
                                         tasks_list, failures, file_filter, stats, 
                                         shutdown_handler, depth + 1, max_depth)
                elif item.type == 'file':
                    # Check shutdown and max items
                    if shutdown_handler and shutdown_handler.should_stop():
                        break
                    if config.get('max_items') and stats and stats.files_total >= config['max_items']:
                        break
                    
                    # Apply filters
                    should_include = True
                    if file_filter:
                        size = getattr(item, 'size', None) if hasattr(item, 'size') else None
                        should_include = file_filter.should_include(child_local_path, size=size)
                    
                    if should_include:
                        # Skip if already complete
                        if not (manifest and manifest.is_complete(child_local_path) and os.path.exists(child_local_path)):
                            size = getattr(item, 'size', 0) if hasattr(item, 'size') else 0
                            if stats:
                                stats.add_file(size)
                            tasks_list.append((item, child_local_path, item_name, config, manifest))
            except Exception as e:
                failures.append(f"Item '{item_name}' in folder '{node.name}': {e}")
                print(f"    -> FAILED to process '{item_name}'. Error: {e}")


def load_config_file(config_path):
    """Load configuration from JSON file."""
    if not os.path.exists(config_path):
        return {}
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        print(f"Loaded configuration from: {config_path}")
        return config
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Could not load config file ({e}), using defaults.")
        return {}


def save_config_file(config_path, config):
    """Save configuration to JSON file."""
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        os.chmod(config_path, 0o600)
        print(f"Configuration saved to: {config_path}")
    except IOError as e:
        print(f"Warning: Could not save config file: {e}")


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Download your entire iCloud Drive with enhanced reliability and security',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        '--destination', '-d',
        default=DEFAULT_DOWNLOAD_PATH,
        help='Destination directory for downloads'
    )
    parser.add_argument(
        '--retries', '-r',
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help='Maximum number of retries per file'
    )
    parser.add_argument(
        '--timeout', '-t',
        type=int,
        default=DEFAULT_TIMEOUT,
        help='Network timeout in seconds'
    )
    parser.add_argument(
        '--chunk-size', '-c',
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help='Download chunk size in bytes'
    )
    parser.add_argument(
        '--min-free-space', '-f',
        type=float,
        default=DEFAULT_MIN_FREE_SPACE_GB,
        help='Minimum free space required in GB'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--workers', '-w',
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help='Number of concurrent download workers'
    )
    parser.add_argument(
        '--no-resume',
        action='store_true',
        help='Disable resume capability (start fresh)'
    )
    parser.add_argument(
        '--sequential',
        action='store_true',
        help='Download files sequentially instead of concurrently'
    )
    parser.add_argument(
        '--include',
        action='append',
        help='Include files matching pattern (glob syntax, can be used multiple times)'
    )
    parser.add_argument(
        '--exclude',
        action='append',
        help='Exclude files matching pattern (glob syntax, can be used multiple times)'
    )
    parser.add_argument(
        '--min-size',
        type=int,
        help='Minimum file size in bytes'
    )
    parser.add_argument(
        '--max-size',
        type=int,
        help='Maximum file size in bytes'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview what would be downloaded without downloading'
    )
    parser.add_argument(
        '--log',
        help='Path to structured JSONL log file'
    )
    parser.add_argument(
        '--no-progress',
        action='store_true',
        help='Disable progress bars'
    )
    parser.add_argument(
        '--max-depth',
        type=int,
        help='Maximum directory depth to traverse'
    )
    parser.add_argument(
        '--max-items',
        type=int,
        help='Maximum number of items to process (safety limit)'
    )
    parser.add_argument(
        '--config',
        help='Path to configuration file (JSON format)'
    )
    parser.add_argument(
        '--save-config',
        help='Save current options to config file and exit'
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level'
    )
    return parser.parse_args()


def check_free_space(path, min_gb):
    """Check if there's enough free space at the target path."""
    stat = shutil.disk_usage(path if os.path.exists(path) else os.path.dirname(path))
    free_gb = stat.free / (1024 ** 3)
    
    if free_gb < min_gb:
        print(f"WARNING: Only {free_gb:.2f} GB free space available.")
        print(f"Required minimum: {min_gb:.2f} GB")
        response = input("Continue anyway? (yes/no): ").strip().lower()
        if response not in ('yes', 'y'):
            print("Aborted by user.")
            sys.exit(0)
    else:
        print(f"Free space available: {free_gb:.2f} GB")


def main():
    """
    Main function to handle login and start the download.
    """
    args = parse_arguments()
    
    # Set up logging
    log_level = getattr(logging, args.log_level)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Load config file if specified
    file_config = {}
    if args.config:
        file_config = load_config_file(args.config)
    
    # Merge config: CLI args override file config
    def get_value(arg_name, file_key=None, default=None):
        """Get value from CLI args, file config, or default."""
        arg_val = getattr(args, arg_name, None)
        if arg_val is not None:
            return arg_val
        if file_key and file_key in file_config:
            return file_config[file_key]
        return default
    
    # Handle save-config mode
    if args.save_config:
        save_config = {
            'destination': args.destination,
            'retries': args.retries,
            'timeout': args.timeout,
            'chunk_size': args.chunk_size,
            'min_free_space': args.min_free_space,
            'workers': args.workers,
            'include': args.include,
            'exclude': args.exclude,
            'min_size': args.min_size,
            'max_size': args.max_size,
            'max_depth': args.max_depth,
            'max_items': args.max_items,
            'log_level': args.log_level
        }
        # Remove None values
        save_config = {k: v for k, v in save_config.items() if v is not None}
        save_config_file(args.save_config, save_config)
        print("Configuration saved. Exiting.")
        sys.exit(0)
    
    # Check if pyicloud is available
    if not PYICLOUD_AVAILABLE:
        print("ERROR: pyicloud is not installed. Install it with: pip install pyicloud")
        sys.exit(1)
    
    # Build configuration dict with merged values
    config = {
        'max_retries': get_value('retries', 'retries', DEFAULT_MAX_RETRIES),
        'timeout': get_value('timeout', 'timeout', DEFAULT_TIMEOUT),
        'chunk_size': get_value('chunk_size', 'chunk_size', DEFAULT_CHUNK_SIZE),
        'progress_every_bytes': DEFAULT_PROGRESS_EVERY_BYTES,
        'verbose': args.verbose or file_config.get('verbose', False),
        'workers': get_value('workers', 'workers', DEFAULT_MAX_WORKERS),
        'sequential': args.sequential or file_config.get('sequential', False),
        'dry_run': args.dry_run or file_config.get('dry_run', False),
        'no_progress': args.no_progress or file_config.get('no_progress', False),
        'max_depth': get_value('max_depth', 'max_depth'),
        'max_items': get_value('max_items', 'max_items')
    }
    
    # Initialize file filter with merged config
    include_patterns = args.include or file_config.get('include', [])
    exclude_patterns = args.exclude or file_config.get('exclude', [])
    min_size = get_value('min_size', 'min_size')
    max_size = get_value('max_size', 'max_size')
    
    file_filter = FileFilter(
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        min_size=min_size,
        max_size=max_size
    )
    
    # Initialize stats and logger
    stats = DownloadStats()
    logger = StructuredLogger(args.log) if args.log else None
    
    download_path = os.path.abspath(get_value('destination', 'destination', DEFAULT_DOWNLOAD_PATH))
    
    print("--- iCloud Drive Downloader (Enhanced - Phase 3) ---")
    print(f"Configuration:")
    print(f"  Destination: {download_path}")
    print(f"  Max retries: {config['max_retries']}")
    print(f"  Timeout: {config['timeout']}s")
    print(f"  Chunk size: {config['chunk_size']} bytes")
    print(f"  Workers: {config['workers']}")
    print(f"  Mode: {'Sequential' if config['sequential'] else 'Concurrent'}")
    print(f"  Resume: {'Disabled' if args.no_resume else 'Enabled'}")
    print(f"  Dry run: {'Yes' if config['dry_run'] else 'No'}")
    print(f"  Log level: {args.log_level}")
    if config.get('max_depth'):
        print(f"  Max depth: {config['max_depth']}")
    if config.get('max_items'):
        print(f"  Max items: {config['max_items']}")
    if include_patterns:
        print(f"  Include: {', '.join(include_patterns)}")
    if exclude_patterns:
        print(f"  Exclude: {', '.join(exclude_patterns)}")
    if min_size:
        print(f"  Min size: {min_size} bytes")
    if max_size:
        print(f"  Max size: {max_size} bytes")
    if args.log:
        print(f"  Log file: {args.log}")
    if args.config:
        print(f"  Config file: {args.config}")
    print()
    
    # Create download directory with secure permissions
    if not os.path.exists(download_path):
        os.makedirs(download_path, exist_ok=True)
        os.chmod(download_path, 0o700)
    
    # Check free space
    check_free_space(download_path, args.min_free_space)
    
    # Initialize shutdown handler
    shutdown_handler = ShutdownHandler()
    
    # Initialize manifest and directory cache
    manifest = None
    if not args.no_resume and not config['dry_run']:
        manifest_path = os.path.join(download_path, MANIFEST_FILENAME)
        manifest = DownloadManifest(manifest_path)
        print(f"Manifest: {manifest_path}")
    
    dir_cache = DirectoryCache()
    stats.start()
    
    if logger:
        logger.log('session_start', config=config, filters={
            'include': include_patterns,
            'exclude': exclude_patterns,
            'min_size': min_size,
            'max_size': max_size,
            'max_depth': config.get('max_depth'),
            'max_items': config.get('max_items')
        })
    
    print(f"\nAll files will be {'previewed in' if config['dry_run'] else 'saved to'}: {download_path}\n")

    # Get credentials from environment or prompt
    apple_id = os.environ.get('ICLOUD_APPLE_ID')
    if not apple_id:
        apple_id = input("Enter your Apple ID email: ")
    else:
        print(f"Using Apple ID from environment: {apple_id}")
    
    password = os.environ.get('ICLOUD_PASSWORD')
    if not password:
        password = getpass("Enter your app-specific password: ")
    else:
        print("Using password from environment variable")

    try:
        api = PyiCloudService(apple_id, password)
    except PyiCloudFailedLoginException:
        print("Login failed! Check your credentials or app-specific password.")
        sys.exit(1)

    if api.requires_2fa:
        print("Two-factor authentication is required.")
        code = input("Enter the 6-digit code from your device: ")
        if not api.validate_2fa_code(code):
            print("Failed to verify the 2FA code.")
            sys.exit(1)
        try:
            api.trust_session()
        except Exception as e:
            print(f"Warning: could not trust session, you may be prompted for 2FA again. Error: {e}")
        print("Successfully authenticated.")

    print("\nAccessing iCloud Drive...")

    failures = []

    top_level_items = api.drive.dir()
    if not top_level_items:
        print("Could not find any files or folders in your iCloud Drive.")
        sys.exit(1)

    print(f"Found {len(top_level_items)} top-level items to process.")

    if config['sequential']:
        # Sequential mode - original behavior
        for item_name in top_level_items:
            if shutdown_handler.should_stop():
                print("\nStopping due to shutdown request...")
                break
            
            item = api.drive[item_name]
            safe_name = sanitize_name(item_name)
            local_item_path = os.path.join(download_path, safe_name)

            if item.type == 'folder':
                print(f"\n--- Processing folder: '{item_name}' ---")
                download_node(item, local_item_path, failures, config, download_path, manifest, 
                            dir_cache, file_filter, stats, logger, config['dry_run'], None,
                            shutdown_handler, 0, config.get('max_depth'))
            elif item.type == 'file':
                print(f"\n--- Downloading top-level file: '{item_name}' ---")
                download_file(item, local_item_path, failures, item_name, config, manifest,
                            file_filter, stats, logger, config['dry_run'], None)
                # Set secure permissions on downloaded file
                if os.path.exists(local_item_path) and not config['dry_run']:
                    os.chmod(local_item_path, 0o600)
    else:
        # Concurrent mode - collect all tasks first, then download in parallel
        print("\n--- Collecting download tasks ---")
        tasks = []
        
        for item_name in top_level_items:
            if shutdown_handler.should_stop():
                print("\nStopping task collection due to shutdown request...")
                break
            
            item = api.drive[item_name]
            safe_name = sanitize_name(item_name)
            local_item_path = os.path.join(download_path, safe_name)
            
            if item.type == 'folder':
                print(f"Scanning folder: '{item_name}'...")
                collect_download_tasks(item, local_item_path, config, download_path, manifest, 
                                     dir_cache, tasks, failures, file_filter, stats,
                                     shutdown_handler, 0, config.get('max_depth'))
            elif item.type == 'file':
                # Check max items
                if config.get('max_items') and stats.files_total >= config['max_items']:
                    break
                
                # Apply filters
                should_include = True
                if file_filter:
                    size = getattr(item, 'size', None) if hasattr(item, 'size') else None
                    should_include = file_filter.should_include(local_item_path, size=size)
                
                if should_include:
                    if not (manifest and manifest.is_complete(local_item_path) and os.path.exists(local_item_path)):
                        size = getattr(item, 'size', 0) if hasattr(item, 'size') else 0
                        stats.add_file(size)
                        tasks.append((item, local_item_path, item_name, config, manifest))
        
        action = 'Previewing' if config['dry_run'] else 'Downloading'
        print(f"\n--- {action} {len(tasks)} files with {config['workers']} workers ---")
        
        if tasks:
            # Create progress bar if tqdm available and not disabled
            pbar = None
            if TQDM_AVAILABLE and not config['no_progress'] and not config['dry_run']:
                pbar = tqdm(total=len(tasks), desc="Downloading", unit="file")
            
            # Extend tasks with additional parameters
            extended_tasks = [
                (t[0], t[1], t[2], t[3], t[4], file_filter, stats, logger, config['dry_run'], pbar)
                for t in tasks
            ]
            
            with ThreadPoolExecutor(max_workers=config['workers']) as executor:
                future_to_task = {executor.submit(download_worker, task): task for task in extended_tasks}
                completed = 0
                
                for future in as_completed(future_to_task):
                    if shutdown_handler.should_stop():
                        print("\nShutdown requested. Cancelling remaining downloads...")
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    
                    task_failures = future.result()
                    failures.extend(task_failures)
                    completed += 1
                    
                    if not pbar and (completed % 10 == 0 or completed == len(tasks)):
                        print(f"Progress: {completed}/{len(tasks)} files processed")
                    
                    # Set secure permissions on completed files
                    task = future_to_task[future]
                    if os.path.exists(task[1]) and not config['dry_run']:
                        os.chmod(task[1], 0o600)
            
            if pbar:
                pbar.close()
        else:
            print("No files to download (all complete or filtered out).")

    stats.finish()
    summary = stats.get_summary()
    
    if shutdown_handler.should_stop():
        print("\n--- Shutdown requested. Session terminated early. ---")
        print("Manifest and progress have been saved. Resume by running the script again.")
    else:
        print("\n--- All done! Download complete. ---")
    print("\nStatistics:")
    print(f"  Total files: {summary['files_total']}")
    print(f"  Completed: {summary['files_completed']}")
    print(f"  Skipped: {summary['files_skipped']}")
    print(f"  Failed: {summary['files_failed']}")
    print(f"  Bytes downloaded: {summary['bytes_downloaded']:,}")
    print(f"  Elapsed time: {summary['elapsed_seconds']:.1f}s")
    
    if summary['elapsed_seconds'] > 0 and summary['bytes_downloaded'] > 0:
        rate = summary['bytes_downloaded'] / summary['elapsed_seconds'] / (1024 * 1024)
        print(f"  Average speed: {rate:.2f} MB/s")
    
    if logger:
        logger.log('session_end', summary=summary, failures_count=len(failures))

    if failures:
        print("\nSome items failed to download:")
        for failure in failures:
            print(f"  - {failure}")
    else:
        if not args.dry_run:
            print("\nAll items downloaded successfully.")
        else:
            print("\nDry run completed.")

if __name__ == '__main__':
    main()
