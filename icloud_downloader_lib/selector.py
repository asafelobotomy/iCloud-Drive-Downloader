import sys
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Set

from .presentation import Colors, format_size

try:
    import prompt_toolkit  # noqa: F401

    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False


def build_inventory_indexes(cache_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build lookup indexes used by the selector and selection summary helpers."""
    nodes = cache_payload.get("nodes", [])
    node_by_id = {node["id"]: node for node in nodes}
    children_by_parent: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        parent_id = node.get("parent_id")
        if parent_id is not None:
            children_by_parent[parent_id].append(node)

    for entries in children_by_parent.values():
        entries.sort(key=lambda node: (node.get("type") != "folder", node.get("name", "").lower()))

    return {
        "node_by_id": node_by_id,
        "children_by_parent": dict(children_by_parent),
    }


def normalize_selection(
    cache_payload: Dict[str, Any],
    selected_node_ids: Iterable[str],
) -> Dict[str, Set[str]]:
    """Reduce selected node IDs to distinct folder and file path scopes."""
    indexes = build_inventory_indexes(cache_payload)
    node_by_id = indexes["node_by_id"]
    selected_folder_paths = sorted(
        {
            node_by_id[node_id]["relative_path"]
            for node_id in selected_node_ids
            if node_id in node_by_id and node_by_id[node_id].get("type") == "folder"
        },
        key=lambda path: (path.count("/"), path),
    )
    selected_folders: Set[str] = set()
    for folder_path in selected_folder_paths:
        if any(folder_path == parent or folder_path.startswith(parent + "/") for parent in selected_folders):
            continue
        selected_folders.add(folder_path)

    selected_files: Set[str] = set()
    for node_id in selected_node_ids:
        node = node_by_id.get(node_id)
        if not node or node.get("type") != "file":
            continue
        relative_path = node["relative_path"]
        if any(relative_path.startswith(folder_path + "/") for folder_path in selected_folders):
            continue
        selected_files.add(relative_path)

    return {"selected_files": selected_files, "selected_folders": selected_folders}


def summarize_selection(cache_payload: Dict[str, Any], selection: Dict[str, Set[str]]) -> Dict[str, int]:
    """Summarize the distinct files and bytes covered by the current selection."""
    indexes = build_inventory_indexes(cache_payload)
    node_by_id = indexes["node_by_id"]
    selected_files = set(selection.get("selected_files", set()))
    selected_folders = set(selection.get("selected_folders", set()))

    total_files = 0
    total_bytes = 0
    for node in node_by_id.values():
        if node.get("type") != "file":
            continue
        relative_path = node.get("relative_path", "")
        if relative_path in selected_files or any(
            relative_path.startswith(folder_path + "/") for folder_path in selected_folders
        ):
            total_files += 1
            total_bytes += int(node.get("size", 0))

    return {"files": total_files, "bytes": total_bytes}


def run_inventory_selector(
    cache_payload: Dict[str, Any],
    selection_mode: str = "mixed",
) -> Optional[Dict[str, Any]]:
    """Launch a full-screen selector for cached folders and files."""
    if not PROMPT_TOOLKIT_AVAILABLE:
        print(f"{Colors.RED}\u2717 The interactive selector requires prompt_toolkit, which is not installed.{Colors.RESET}")
        print("Install it with:  pip install 'prompt_toolkit>=3.0'")
        sys.exit(1)

    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style
    from prompt_toolkit.widgets import Frame

    indexes = build_inventory_indexes(cache_payload)
    node_by_id = indexes["node_by_id"]
    children_by_parent = indexes["children_by_parent"]

    # Precompute per-folder stats once so build_browser_text renders fast
    folder_stats: Dict[str, Dict[str, int]] = {}

    def _fill_folder_stats(node_id: str) -> int:
        if node_id in folder_stats:
            return folder_stats[node_id]["total_bytes"]
        children = children_by_parent.get(node_id, [])
        direct_sub = [c for c in children if c.get("type") == "folder"]
        direct_files = [c for c in children if c.get("type") == "file"]
        file_bytes = sum(int(c.get("size", 0)) for c in direct_files)
        sub_bytes = sum(_fill_folder_stats(c["id"]) for c in direct_sub)
        folder_stats[node_id] = {
            "folders": len(direct_sub),
            "files": len(direct_files),
            "total_bytes": file_bytes + sub_bytes,
        }
        return folder_stats[node_id]["total_bytes"]

    _fill_folder_stats("root")

    current_parent_id = "root"
    cursor_index = 0
    selected_node_ids: Set[str] = set()

    def current_entries() -> List[Dict[str, Any]]:
        return children_by_parent.get(current_parent_id, [])

    def current_path() -> str:
        node = node_by_id.get(current_parent_id)
        if not node or not node.get("relative_path"):
            return "/"
        return "/" + str(node["relative_path"])

    def is_selectable(node: Dict[str, Any]) -> bool:
        node_type = node.get("type")
        if selection_mode == "files":
            return node_type == "file"
        if selection_mode == "folders":
            return node_type == "folder"
        return node_type in {"file", "folder"}

    def move_cursor(step: int) -> None:
        nonlocal cursor_index
        entries = current_entries()
        if not entries:
            cursor_index = 0
            return
        cursor_index = max(0, min(len(entries) - 1, cursor_index + step))

    def open_current_entry() -> None:
        nonlocal current_parent_id, cursor_index
        entries = current_entries()
        if not entries:
            return
        entry = entries[cursor_index]
        if entry.get("type") == "folder":
            current_parent_id = entry["id"]
            cursor_index = 0
        elif is_selectable(entry):
            toggle_current_entry()

    def go_to_parent() -> None:
        nonlocal current_parent_id, cursor_index
        node = node_by_id.get(current_parent_id)
        parent_id = node.get("parent_id") if node else None
        if parent_id is None:
            return
        current_parent_id = parent_id
        cursor_index = 0

    def toggle_current_entry() -> None:
        entries = current_entries()
        if not entries:
            return
        entry = entries[cursor_index]
        if not is_selectable(entry):
            return
        node_id = entry["id"]
        if node_id in selected_node_ids:
            selected_node_ids.remove(node_id)
        else:
            selected_node_ids.add(node_id)

    def build_browser_text() -> List[Any]:
        fragments: List[Any] = [
            ("class:title", f"Current folder: {current_path()}\n\n"),
        ]
        entries = current_entries()
        if not entries:
            fragments.append(("class:muted", "  (empty folder)\n"))
            return fragments

        for index, entry in enumerate(entries):
            is_current = index == cursor_index
            prefix = ">" if is_current else " "
            selectable = is_selectable(entry)
            selected = entry["id"] in selected_node_ids
            marker = "[x]" if selected else "[ ]" if selectable else " - "
            entry_type = "DIR" if entry.get("type") == "folder" else "FILE"
            if entry.get("type") == "folder":
                st = folder_stats.get(entry["id"], {"folders": 0, "files": 0, "total_bytes": 0})
                parts = []
                if st["folders"]:
                    n = st["folders"]
                    parts.append(f"{n} folder{'s' if n != 1 else ''}")
                if st["files"]:
                    n = st["files"]
                    parts.append(f"{n} file{'s' if n != 1 else ''}")
                if parts:
                    parts.append(format_size(st["total_bytes"]))
                suffix = f" ({', '.join(parts)})" if parts else " (empty)"
            else:
                suffix = f" ({format_size(entry.get('size', 0))})"
            style = "class:cursor" if is_current else ""
            fragments.append((style, f"{prefix} {marker} [{entry_type}] {entry.get('name', '')}{suffix}\n"))
        return fragments

    def build_summary_text() -> List[Any]:
        selection = normalize_selection(cache_payload, selected_node_ids)
        summary = summarize_selection(cache_payload, selection)
        return [
            ("class:title", "Selection Summary\n"),
            ("", f"Mode: {selection_mode}\n"),
            ("", f"Folders: {len(selection['selected_folders'])}\n"),
            ("", f"Files: {len(selection['selected_files'])}\n"),
            ("", f"Covered files: {summary['files']}\n"),
            ("", f"Covered size:  {format_size(summary['bytes'])}\n\n"),
            ("class:title", "Keys\n"),
            ("", "Up/Down   navigate\n"),
            ("", "Enter     open folder / toggle file\n"),
            ("", "Space     toggle item\n"),
            ("", "Left/Back go up\n"),
            ("", "Ctrl-S    accept selection\n"),
            ("", "Esc       cancel\n"),
        ]

    browser_control = FormattedTextControl(build_browser_text)
    summary_control = FormattedTextControl(build_summary_text)
    bindings = KeyBindings()

    @bindings.add("up")
    def _move_up(_event: Any) -> None:
        move_cursor(-1)

    @bindings.add("down")
    def _move_down(_event: Any) -> None:
        move_cursor(1)

    @bindings.add("right")
    @bindings.add("enter")
    def _open(_event: Any) -> None:
        open_current_entry()

    @bindings.add("left")
    @bindings.add("backspace")
    def _back(_event: Any) -> None:
        go_to_parent()

    @bindings.add(" ")
    def _toggle(_event: Any) -> None:
        toggle_current_entry()

    @bindings.add("c-s")
    def _accept(event: Any) -> None:
        selection: Dict[str, Any] = normalize_selection(cache_payload, selected_node_ids)
        selection["summary"] = summarize_selection(cache_payload, selection)
        event.app.exit(result=selection)

    @bindings.add("escape")
    @bindings.add("c-c")
    def _cancel(event: Any) -> None:
        event.app.exit(result=None)

    root_container = HSplit(
        [
            Window(height=1, content=FormattedTextControl(lambda: [("class:header", "Inventory Selector")])),
            VSplit(
                [
                    Frame(Window(content=browser_control, wrap_lines=False), title="Browse"),
                    Frame(Window(content=summary_control, wrap_lines=False), title="Selection"),
                ]
            ),
        ]
    )
    application: Any = Application(
        layout=Layout(root_container),
        key_bindings=bindings,
        full_screen=True,
        mouse_support=False,
        style=Style.from_dict(
            {
                "header": "reverse",
                "title": "bold",
                "cursor": "reverse",
                "muted": "italic",
            }
        ),
    )
    return application.run()