import os
from typing import Dict

__version__ = "4.0.0"
__author__ = "iCloud Drive Downloader Contributors"
__license__ = "MIT"
__description__ = (
    "Download entire folders from iCloud Drive with resume capability, filters, and security"
)

DEFAULT_DOWNLOAD_PATH = os.path.join(os.path.expanduser("~"), "iCloud_Drive_Download")
DEFAULT_CHUNK_SIZE = 8192
DEFAULT_PROGRESS_EVERY_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT = 60
DEFAULT_MIN_FREE_SPACE_GB = 1
DEFAULT_MAX_WORKERS = 3
MANIFEST_FILENAME = ".icloud_download_manifest.json"
LOG_FILENAME = "icloud_download.log.jsonl"
CONFIG_FILENAME = ".icloud_downloader.json"
USER_CONFIG_FILENAME = "config-private.json"
INVENTORY_CACHE_FILENAME = ".icloud_inventory_cache.json"

RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
RETRYABLE_EXCEPTIONS = (ConnectionError, TimeoutError)

PHOTOS_SCOPES: Dict[str, str] = {
    "all": "All Photos & Videos",
    "photos": "All Photos",
    "videos": "All Videos",
    "by-album": "By Album",
    "by-month": "By Month",
}

PRESETS: Dict[str, Dict[str, object]] = {
    "photos": {
        "name": "Photos & Videos In iCloud Drive",
        "description": "Download photo and video files stored in iCloud Drive",
        "include": [
            "*.jpg",
            "*.jpeg",
            "*.png",
            "*.gif",
            "*.heic",
            "*.heif",
            "*.mp4",
            "*.mov",
            "*.avi",
            "*.mkv",
            "*.m4v",
        ],
        "workers": 5,
    },
    "documents": {
        "name": "Documents In iCloud Drive",
        "description": "Download document files stored in iCloud Drive",
        "include": [
            "*.pdf",
            "*.doc",
            "*.docx",
            "*.txt",
            "*.rtf",
            "*.xls",
            "*.xlsx",
            "*.ppt",
            "*.pptx",
            "*.pages",
            "*.numbers",
            "*.key",
        ],
        "workers": 5,
    },
    "quick-test": {
        "name": "Quick Test",
        "description": "Safe test with limits (first 50 items, depth 2)",
        "max_items": 50,
        "max_depth": 2,
        "workers": 3,
    },
    "large-files": {
        "name": "Large Files Only",
        "description": "Download files larger than 100MB",
        "min_size": 104857600,
        "workers": 3,
    },
}