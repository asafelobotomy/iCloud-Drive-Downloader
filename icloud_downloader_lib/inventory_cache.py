import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from .definitions import INVENTORY_CACHE_FILENAME
from .filters import ensure_directory, open_secure_file
from .inventory import DryRunInventory, classify_storage_category
from .privacy import stable_text_identifier


class InventoryTreeBuilder:
    """Build a secure local inventory tree for later interactive selection."""

    def __init__(self, download_root: str) -> None:
        self.download_root = os.path.realpath(download_root)
        self.nodes: List[Dict[str, Any]] = [
            {
                "id": "root",
                "parent_id": None,
                "type": "root",
                "name": "iCloud Drive",
                "relative_path": "",
                "depth": 0,
                "child_count": 0,
            }
        ]
        self._relative_path_to_id: Dict[str, str] = {"": "root"}

    def _relative_path(self, local_path: str) -> str:
        relative_path = os.path.relpath(os.path.realpath(local_path), self.download_root)
        if relative_path in (".", ""):
            return ""
        return relative_path.replace(os.sep, "/")

    @staticmethod
    def _parent_relative_path(relative_path: str) -> str:
        if not relative_path or "/" not in relative_path:
            return ""
        return relative_path.rsplit("/", 1)[0]

    @staticmethod
    def _node_id(relative_path: str) -> str:
        return stable_text_identifier(relative_path or "icloud-drive-root") or "root"

    def _upsert_node(self, node: Dict[str, Any]) -> None:
        node_id = node["id"]
        for index, existing in enumerate(self.nodes):
            if existing["id"] == node_id:
                self.nodes[index] = {**existing, **node}
                return
        self.nodes.append(node)

    def record_folder(self, local_path: str, folder_name: str, *, depth: int, child_count: int) -> None:
        relative_path = self._relative_path(local_path)
        parent_relative_path = self._parent_relative_path(relative_path)
        parent_id = self._relative_path_to_id.get(parent_relative_path, "root")
        node_id = self._node_id(relative_path)
        self._relative_path_to_id[relative_path] = node_id
        self._upsert_node(
            {
                "id": node_id,
                "parent_id": parent_id,
                "type": "folder",
                "name": folder_name,
                "relative_path": relative_path,
                "depth": depth,
                "child_count": child_count,
            }
        )

    def record_file(
        self,
        local_path: str,
        file_name: str,
        *,
        size: Optional[int],
        depth: int,
        included: bool,
    ) -> None:
        relative_path = self._relative_path(local_path)
        parent_relative_path = self._parent_relative_path(relative_path)
        parent_id = self._relative_path_to_id.get(parent_relative_path, "root")
        node_id = self._node_id(relative_path)
        self._relative_path_to_id[relative_path] = node_id
        self._upsert_node(
            {
                "id": node_id,
                "parent_id": parent_id,
                "type": "file",
                "name": file_name,
                "relative_path": relative_path,
                "depth": depth,
                "size": max(0, int(size or 0)),
                "category": classify_storage_category(local_path),
                "matched_current_filters": included,
            }
        )

    def build_payload(
        self,
        inventory: DryRunInventory,
        config: Dict[str, Any],
        top_level_items: int,
    ) -> Dict[str, Any]:
        summary = inventory.snapshot()
        self.nodes[0]["child_count"] = top_level_items
        return {
            "metadata": {
                "schema_version": 1,
                "created_at": datetime.now().isoformat(),
                "top_level_items": top_level_items,
                "summary": summary,
                "config": {
                    "max_depth": config.get("max_depth"),
                    "max_items": config.get("max_items"),
                },
            },
            "nodes": list(self.nodes),
        }


def resolve_inventory_cache_path(download_path: str, configured_path: Optional[str] = None) -> str:
    """Resolve the secure local inventory cache path."""
    if configured_path:
        return os.path.abspath(configured_path)
    return os.path.join(os.path.abspath(download_path), INVENTORY_CACHE_FILENAME)


def save_inventory_cache(cache_path: str, cache_payload: Dict[str, Any]) -> None:
    """Persist the inventory cache using owner-only permissions."""
    cache_root = os.path.dirname(os.path.abspath(cache_path)) or "."
    ensure_directory(cache_root, cache_root, 0o700)
    with open_secure_file(cache_path, cache_root, "w", permissions=0o600, encoding="utf-8") as cache_file:
        json.dump(cache_payload, cache_file, indent=2)


def load_inventory_cache(cache_path: str) -> Dict[str, Any]:
    """Load a previously persisted inventory cache."""
    cache_root = os.path.dirname(os.path.abspath(cache_path)) or "."
    with open_secure_file(cache_path, cache_root, "r", encoding="utf-8") as cache_file:
        payload = json.load(cache_file)

    if not isinstance(payload, dict) or "nodes" not in payload or "metadata" not in payload:
        raise ValueError("Inventory cache is invalid or incomplete")
    return payload