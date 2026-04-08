#!/usr/bin/env python3
"""Heartbeat MCP server — session reflection tool for autonomous retrospective.

Provides a single `session_reflect` tool that reads heartbeat state, computes
session metrics, and returns structured reflection prompts.  The model calls
this tool autonomously when the periodic health digest indicates significant
work.  Output is compact (~200 tokens) so the model can process it silently
and surface only actionable findings to the user.

Transport: stdio  |  Run: uvx --from "mcp[cli]" mcp run <this-file>
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Heartbeat")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_workspace_root() -> Path:
    """Detect the git repository root (works regardless of cwd)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception:
        pass
    return Path.cwd()


ROOT = _find_workspace_root()
WORKSPACE = ROOT / ".copilot" / "workspace"
STATE_PATH = WORKSPACE / "state.json"
EVENTS_PATH = WORKSPACE / ".heartbeat-events.jsonl"
SENTINEL_PATH = WORKSPACE / ".heartbeat-session"


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _git_modified_count() -> int:
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(ROOT),
        )
        if proc.returncode == 0:
            return len([l for l in proc.stdout.splitlines() if l.strip()])
    except Exception:
        pass
    return 0


def _recent_events(limit: int = 20) -> list[dict]:
    if not EVENTS_PATH.exists():
        return []
    events: list[dict] = []
    try:
        for line in EVENTS_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        pass
    return events[-limit:]


def _append_event(trigger: str, detail: str = "", session_id: str = "", duration_s: int | None = None) -> None:
    if not WORKSPACE.exists():
        return
    event = {
        "ts": int(time.time()),
        "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "trigger": trigger,
    }
    if detail:
        event["detail"] = detail
    if session_id:
        event["session_id"] = session_id
    if duration_s is not None:
        event["duration_s"] = int(duration_s)
    with EVENTS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def _session_events(state: dict, limit: int = 50) -> list[dict]:
    session_id = str(state.get("session_id") or "")
    session_start = int(state.get("session_start_epoch") or 0)
    scoped: list[dict] = []
    for event in _recent_events(limit):
        if not isinstance(event, dict):
            continue
        event_session_id = str(event.get("session_id") or "")
        if session_id and event_session_id:
            if event_session_id != session_id:
                continue
        else:
            event_ts = event.get("ts")
            if session_start > 0 and isinstance(event_ts, (int, float)) and int(event_ts) < session_start:
                continue
        scoped.append(event)
    return scoped


def _set_sentinel_complete(session_id: str) -> None:
    """Mark the session sentinel as complete so the Stop hook passes through."""
    if not WORKSPACE.exists():
        return
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    tmp = SENTINEL_PATH.with_suffix(".tmp")
    tmp.write_text(f"{session_id}|{ts}|complete\n", encoding="utf-8")
    os.replace(tmp, SENTINEL_PATH)


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


@mcp.tool()
def session_reflect() -> dict:
    """Reflect on the current coding session.

    Returns structured session metrics (files changed, active work time, edit
    count, key events) and lean reflection prompts.

    Call before ending any session where the health digest indicates significant
    work (one strong signal: 8+ modified files or 30+ minutes active; or two
    supporting signals: 5+ modified files, 15+ minutes active, or context
    compaction). Process the output
    silently — update SOUL.md, MEMORY.md, USER.md only if insights warrant it.
    Surface findings to the user only for actionable items (security concerns,
    tech debt, coverage gaps, broken assumptions).
    """
    state = _load_state()
    now = int(time.time())

    # --- Metrics -----------------------------------------------------------
    session_start = int(state.get("session_start_epoch") or 0)
    session_duration_s = max(0, now - session_start) if session_start else 0

    # Close any still-open work window for accurate active seconds.
    active_s = int(state.get("active_work_seconds") or 0)
    tw_start = int(state.get("task_window_start_epoch") or 0)
    last_tool = int(state.get("last_raw_tool_epoch") or 0)
    if tw_start > 0 and last_tool >= tw_start:
        active_s += max(0, last_tool - tw_start)

    delta_files = max(
        0,
        _git_modified_count() - int(state.get("session_start_git_count") or 0),
    )
    edit_count = int(state.get("copilot_edit_count") or 0)
    effective_files = delta_files if delta_files > 0 else edit_count
    compactions = sum(
        1 for ev in _session_events(state, 50) if ev.get("trigger") == "compaction"
    )

    # --- Magnitude ---------------------------------------------------------
    active_min = active_s // 60
    if effective_files >= 8 or active_min >= 30:
        magnitude = "large"
    elif effective_files >= 5 or active_min >= 15:
        magnitude = "medium"
    else:
        magnitude = "small"

    # --- Reflection prompts ------------------------------------------------
    prompts: list[str] = []
    if effective_files > 0:
        label = "files changed" if delta_files > 0 else "files edited (committed)"
        prompts.append(
            f"{effective_files} {label} across {active_min}min active"
            " — review execution accuracy and scope completeness"
        )
    if compactions > 0:
        prompts.append(
            "Context compaction occurred"
            " — verify no key decisions were lost"
        )
    if effective_files >= 5:
        prompts.append(
            "Consider whether test coverage and documentation kept pace"
        )

    # --- Workspace state ---------------------------------------------------
    ws = {
        "soul_exists": (WORKSPACE / "SOUL.md").exists(),
        "memory_exists": (WORKSPACE / "MEMORY.md").exists(),
        "user_exists": (WORKSPACE / "USER.md").exists(),
    }

    # --- Set sentinel complete ---------------------------------------------
    session_id = state.get("session_id") or "unknown"
    _append_event("session_reflect", "complete", session_id=str(session_id))
    _set_sentinel_complete(session_id)

    return {
        "magnitude": magnitude,
        "metrics": {
            "active_work_minutes": active_min,
            "files_changed": effective_files,
            "edits_tracked": edit_count,
            "compactions": compactions,
            "session_duration_minutes": session_duration_s // 60,
        },
        "reflection_prompts": prompts,
        "workspace_state": ws,
    }


if __name__ == "__main__":
    mcp.run()
