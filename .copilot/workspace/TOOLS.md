# Tool Usage Patterns — iCloud Drive Downloader

*(Populated by Copilot from observed effective workflows. See §11 of `.github/copilot-instructions.md` for the full Tool Protocol.)*

## Core commands

| Tool / command | Effective usage pattern |
| -------------- | ----------------------- |
| `python3 -m pytest tests/ -v` | Canonical underlying full-suite entrypoint when you need the direct command. |
| `python3 -m mypy icloud_downloader.py --check-untyped-defs` | Run after every type definition change |
| `python3 -m pytest tests/ --cov=icloud_downloader_lib --cov=icloud_downloader --cov-report=term-missing` | Use when validating the coverage gate or checking coverage drift. |
| `find . -path './archive' -prune -o -name '*.py' -exec wc -l {} +` | Run after adding new files to check LOC bands |
| `python3 -m py_compile icloud_downloader.py && python3 -m mypy icloud_downloader.py --check-untyped-defs && python3 -m pytest tests/ -v` | Preferred final verification command or ritual before marking any task done. |

If the repo documents a targeted-test selector or phase-test command, use it during intermediate phases instead of defaulting to the full suite.

## Toolbox

Custom-built and adapted tools are saved to `.copilot/tools/`. The catalogue is maintained in `.copilot/tools/INDEX.md`.

**Before writing any automation script**, always:

1. Check `.copilot/tools/INDEX.md` for an existing tool.
2. Follow §11 (Tool Protocol) in `.github/copilot-instructions.md` if no match is found.

The toolbox directory is created lazily — it does not exist until the first tool is saved.

## Discovered workflow patterns

Copilot appends effective multi-step tool workflows here as they become repeatable.

## Extension registry

Copilot appends new stack → extension mappings here when discovered during extension audits.

| Stack signal | Recommended extension(s) | Discovered | Quality (installs · rating) |
| ------------ | ------------------------ | ---------- | -------------------------- |
