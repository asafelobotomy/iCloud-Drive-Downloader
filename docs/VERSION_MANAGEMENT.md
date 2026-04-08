# Version Management

This document explains how version control is implemented and how to update the version number.

## Single Source of Truth

All version information is stored in one location: `icloud_downloader_lib/definitions.py`

```python
__version__ = "4.0.0"
__author__ = "iCloud Drive Downloader Contributors"
__license__ = "MIT"
__description__ = "Download entire folders from iCloud Drive with resume capability, filters, and security"
```

## Where Version Appears

The version number automatically appears in:

1. **CLI --version flag**

   ```bash
   python3 icloud_downloader.py --version
   # Output: icloud_downloader.py 4.0.0
   ```

2. **Startup banner**

   ```text
   ============================================================
      iCloud Drive Downloader v4.0.0
   ============================================================
   ```

3. **README.md badge**

   ```markdown
   [![Version](https://img.shields.io/badge/version-4.0.0-blue.svg)](CHANGELOG.md)
   ```

4. **Python imports**

   ```python
   from icloud_downloader import __version__
   print(__version__)  # 4.0.0
   ```

## How to Update Version

### Step 1: Update the Version Constant

Edit one file only: `icloud_downloader_lib/definitions.py`

```python
__version__ = "4.1.0"  # ← Change this line only
__author__ = "iCloud Drive Downloader Contributors"
__license__ = "MIT"
__description__ = "Download entire folders from iCloud Drive with resume capability, filters, and security"
```

### Step 2: Update README Badge

Edit `README.md` line 5:

```markdown
[![Version](https://img.shields.io/badge/version-4.1.0-blue.svg)](CHANGELOG.md)
```

### Step 3: Update CHANGELOG

Edit `CHANGELOG.md` to add the new version:

```markdown
## [4.1.0] - 2026-02-01

### Added
- New feature description

### Changed
- Changed feature description

### Fixed
- Bug fix description
```

### Step 4: Verify

```bash
# Check version displays correctly
python3 icloud_downloader.py --version

# Check Python import works
python3 -c "from icloud_downloader import __version__; print(__version__)"

# Run tests
python3 -m pytest tests/ -v
```

## Version Numbering Scheme

We follow [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`

### MAJOR version (X.0.0)

Increment when you make incompatible changes:

- Breaking CLI changes
- Removed features
- Major architecture changes

**Example:** 3.0.0 → 4.0.0

### MINOR version (0.X.0)

Increment when you add functionality in a backward-compatible manner:

- New features
- New CLI options
- New presets

**Example:** 4.0.0 → 4.1.0

### PATCH version (0.0.X)

Increment when you make backward-compatible bug fixes:

- Bug fixes
- Performance improvements
- Documentation updates

**Example:** 4.1.0 → 4.1.1

## Version History

### Version 4.0.0 (Current)

**Release Date:** January 25, 2026

**Major Features:**

- Phase 4: User Experience Enhancements
  - Interactive setup wizard (`--wizard`)
  - Preset configurations (`--preset`)
  - Colorized output
  - Human-readable sizes
  - Smart confirmations
  - Enhanced error messages
- Centralized version control
- Pytest suite and type checks
- Full type hints
- Strong local verification

**Breaking Changes:**

- None (additive only)

### Version 3.x (Previous)

- Phase 3: Operational Hardening
- Phase 2: Filtering & UX
- Phase 1: Performance & Resume
- Phase 0: Foundation & Security

## Automation (Future)

For fully automated version management, consider:

1. **Setup script** to update all version references:

   ```bash
   ./scripts/bump_version.sh 4.1.0
   ```

2. **Git tags** matching versions:

   ```bash
   git tag -a v4.0.0 -m "Release version 4.0.0"
   git push origin v4.0.0
   ```

3. **CI/CD integration** to validate version consistency

4. **Automatic changelog generation** from git commits

## Best Practices

1. **Always update CHANGELOG.md** when bumping version
2. **Test thoroughly** before releasing new version
3. **Tag releases in git** for easy rollback
4. **Document breaking changes** prominently
5. **Follow semantic versioning** strictly
6. **Update README examples** if CLI changes

## Quick Reference

| File | What to Update |
| ---- | -------------- |
| `icloud_downloader_lib/definitions.py` | `__version__ = "X.Y.Z"` |
| `README.md` | Line 5: Version badge number |
| `CHANGELOG.md` | Add new version section at top |

**Remember:** Change the version in `icloud_downloader_lib/definitions.py` first, everything else references it.
