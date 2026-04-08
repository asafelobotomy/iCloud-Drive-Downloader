# Archive

This directory contains files that are no longer actively used but are preserved for historical reference.

## Directory Structure

- **dev-notes/** - Historical development documentation and implementation notes
- **deprecated/** - Deprecated configuration files and examples

## Archived Files

### Documentation
- `README-v4.0.0-full.md` - Complete v4.0.0 README with full development history
  - Reason: Replaced with concise user-focused README
  - Contains: Detailed "Why This Tool Exists" section, phased implementation details
  - Use: Historical reference for development philosophy and detailed feature explanations

### Development Notes
- `PHASE0_CHANGES.md` - Phase 0 implementation notes (foundation features)
  - Reason: Historical record of initial implementation
  - Superseded by: Current documentation in `../docs/` and `../docs/README.md`

### Deprecated Files
- `.env.example` - Example environment file
  - Reason: Not actively used in current implementation
  - Note: Environment variables are documented in README.md instead

- `__pycache__/` - Python bytecode cache
  - Reason: Auto-generated, should not be in version control
  - Note: Added to .gitignore

## Why Archive Instead of Delete?

These files represent the project's history and may contain useful context for:
- Understanding past design decisions
- Reviewing implementation evolution
- Troubleshooting legacy configurations

If you need to reference any archived file, it remains accessible here.

## Maintenance

Files should be archived when they are:
- No longer actively maintained
- Superseded by newer documentation
- Historical/reference-only value
- Not part of the core application

**Do not** archive:
- Active code files
- Current documentation
- Test files
- Configuration templates in use
