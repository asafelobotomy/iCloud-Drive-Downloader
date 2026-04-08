import os
from typing import Any, Dict, Optional


PHOTO_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".heic",
    ".heif",
    ".tif",
    ".tiff",
    ".webp",
    ".bmp",
    ".raw",
    ".dng",
}
VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".m4v",
    ".wmv",
    ".flv",
    ".webm",
    ".hevc",
    ".mpg",
    ".mpeg",
}
DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".rtf",
    ".md",
    ".pages",
    ".numbers",
    ".key",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".csv",
    ".json",
}
AUDIO_EXTENSIONS = {
    ".mp3",
    ".m4a",
    ".wav",
    ".aiff",
    ".flac",
    ".aac",
    ".ogg",
}
ARCHIVE_EXTENSIONS = {
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
}

CATEGORY_ORDER = ("photos", "videos", "documents", "audio", "archives", "other")


def build_log_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return a reduced logging view that omits local paths and secrets."""
    return {
        "workers": config.get("workers"),
        "sequential": config.get("sequential"),
        "resume": config.get("resume"),
        "dry_run": config.get("dry_run"),
        "progress": config.get("progress"),
        "max_retries": config.get("max_retries"),
        "timeout": config.get("timeout"),
        "chunk_size": config.get("chunk_size"),
        "min_free_space": config.get("min_free_space"),
        "max_depth": config.get("max_depth"),
        "max_items": config.get("max_items"),
        "log_level": config.get("log_level"),
        "use_keyring": config.get("use_keyring"),
        "china_mainland": config.get("china_mainland"),
    }


def estimate_download_size(api: Any, top_level_items: list[str]) -> Dict[str, int]:
    """Estimate the number of files and bytes to download from a sample."""
    estimated_files = 0
    estimated_size = 0

    for item_name in top_level_items[:50]:
        try:
            item = api.drive[item_name]
            if hasattr(item, "size") and item.size:
                estimated_files += 1
                estimated_size += item.size
            elif item.type == "folder":
                estimated_files += 10
                estimated_size += 50 * 1024 * 1024
        except Exception:
            pass

    if len(top_level_items) > 50:
        ratio = len(top_level_items) / 50
        estimated_files = int(estimated_files * ratio)
        estimated_size = int(estimated_size * ratio)

    return {"estimated_files": estimated_files, "estimated_size": estimated_size}


def classify_storage_category(file_path: str) -> str:
    """Classify a file path into a coarse storage category."""
    extension = os.path.splitext(file_path)[1].lower()
    if extension in PHOTO_EXTENSIONS:
        return "photos"
    if extension in VIDEO_EXTENSIONS:
        return "videos"
    if extension in DOCUMENT_EXTENSIONS:
        return "documents"
    if extension in AUDIO_EXTENSIONS:
        return "audio"
    if extension in ARCHIVE_EXTENSIONS:
        return "archives"
    return "other"


class DryRunInventory:
    """Aggregate privacy-preserving inventory metrics for preview mode."""

    def __init__(self, *, max_depth: Optional[int] = None, max_items: Optional[int] = None) -> None:
        self.max_depth = max_depth
        self.max_items = max_items
        self.root_files = 0
        self.root_folders = 0
        self.total_files = 0
        self.total_folders = 0
        self.total_bytes = 0
        self.preview_files = 0
        self.preview_folders = 0
        self.preview_bytes = 0
        self.matched_files = 0
        self.matched_bytes = 0
        self.preview_matched_files = 0
        self.preview_matched_bytes = 0
        self.empty_folders = 0
        self.deepest_level = 0
        self.category_counts = {category: 0 for category in CATEGORY_ORDER}
        self.category_bytes = {category: 0 for category in CATEGORY_ORDER}

    def record_root_folder(self) -> None:
        """Record a folder present directly in the iCloud Drive root."""
        self.root_folders += 1

    def record_root_file(self) -> None:
        """Record a file present directly in the iCloud Drive root."""
        self.root_files += 1

    def preview_limit_reached(self) -> bool:
        """Return whether the preview-scope item limit has been satisfied."""
        return self.max_items is not None and self.preview_matched_files >= self.max_items

    def preview_allows_folder(self, level: int) -> bool:
        """Return whether a folder level is inside the preview depth limit."""
        return self.max_depth is None or level <= self.max_depth

    def preview_allows_file(self, level: int) -> bool:
        """Return whether a file level is inside the preview depth limit."""
        return self.max_depth is None or level <= (self.max_depth + 1)

    def record_folder(self, *, level: int, preview: bool = False, is_root: bool = False) -> None:
        self.total_folders += 1
        self.deepest_level = max(self.deepest_level, level)
        if is_root:
            self.record_root_folder()
        if preview:
            self.preview_folders += 1

    def mark_empty_folder(self) -> None:
        """Record that a folder has no children."""
        self.empty_folders += 1

    def record_file(
        self,
        file_path: str,
        size: Optional[int],
        *,
        included: bool,
        level: int,
        preview: bool = False,
        is_root: bool = False,
    ) -> None:
        normalized_size = max(0, int(size or 0))
        category = classify_storage_category(file_path)

        self.total_files += 1
        self.total_bytes += normalized_size
        self.deepest_level = max(self.deepest_level, level)
        self.category_counts[category] += 1
        self.category_bytes[category] += normalized_size
        if is_root:
            self.record_root_file()
        if included:
            self.matched_files += 1
            self.matched_bytes += normalized_size
        if preview:
            self.preview_files += 1
            self.preview_bytes += normalized_size
            if included:
                self.preview_matched_files += 1
                self.preview_matched_bytes += normalized_size

    def snapshot(self) -> Dict[str, Any]:
        return {
            "root_files": self.root_files,
            "root_folders": self.root_folders,
            "root_items": self.root_files + self.root_folders,
            "total_files": self.total_files,
            "total_folders": self.total_folders,
            "total_items": self.total_files + self.total_folders,
            "total_bytes": self.total_bytes,
            "preview_files": self.preview_files,
            "preview_folders": self.preview_folders,
            "preview_items": self.preview_files + self.preview_folders,
            "preview_bytes": self.preview_bytes,
            "matched_files": self.matched_files,
            "matched_bytes": self.matched_bytes,
            "preview_matched_files": self.preview_matched_files,
            "preview_matched_bytes": self.preview_matched_bytes,
            "empty_folders": self.empty_folders,
            "deepest_level": self.deepest_level,
            "has_preview_limits": self.max_depth is not None or self.max_items is not None,
            "preview_limit_reached": self.preview_limit_reached(),
            "category_counts": dict(self.category_counts),
            "category_bytes": dict(self.category_bytes),
        }