---
description: Refactor selected code using PDCA cycle and Lean waste elimination
argument-hint: Select code first, or name the file and waste category to target
agent: agent
tools: [editFiles, runCommands, codebase]
---

# Refactor Code

Refactor the selected code following Lean principles from §1 and the PDCA cycle from §5.

1. **Plan**: Identify the specific waste (§6 W1–W16) or baseline violation (§3) being addressed. State the goal and expected LOC delta.
2. **Do**: Perform the refactoring. Preserve all existing behaviour — no feature changes.
3. **Check**: Run `python3 -m py_compile icloud_downloader.py && python3 -m mypy icloud_downloader.py --check-untyped-defs && python3 -m pytest tests/ -v` and confirm no regressions.
4. **Act**: If baselines are exceeded, address them. Summarise what changed and why.

Do not add features, change APIs, or modify tests unless the refactoring requires it.
