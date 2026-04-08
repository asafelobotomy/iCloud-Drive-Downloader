# Documentation

Complete documentation for the iCloud Drive Downloader.

## User Documentation

- **[Quick Start Guide](QUICK_START.md)** - Get started in 5 minutes
- **[Interactive Mode Guide](INTERACTIVE_MODE.md)** - Fully guided setup (no CLI knowledge needed)
- **[Rate Limiting & Throttling](RATE_LIMITING_AND_THROTTLING.md)** - Apple's policies, throttling behavior, and mitigation strategies
- **[Configuration Examples](../examples/README.md)** - Sample config files for common scenarios
- **[Changelog](../CHANGELOG.md)** - Version history and release notes
- **[Version Management](VERSION_MANAGEMENT.md)** - How to update version numbers

## Development Documentation

- **[Version Management](VERSION_MANAGEMENT.md)** - Centralized version control system
- **[Phase 0 Implementation](../archive/dev-notes/PHASE0_CHANGES.md)** - Foundation and security features (archived)
- **[Code Review Report](../archive/dev-notes/CODE_REVIEW_REPORT.md)** - January 2026 security audit (archived)
- **[Fixes Applied](../archive/dev-notes/FIXES_APPLIED.md)** - January 2026 critical bug fixes (archived)
- **[Implementation Summary](../archive/dev-notes/IMPLEMENTATION_SUMMARY.md)** - January 2026 technical implementation details (archived)

## Testing

- **[Test Suite Documentation](../tests/README.md)** - Running tests and coverage reports

## Project Structure

Use the top-level [README](../README.md#project-structure) for the current project layout. Keep this docs index focused on navigation so it does not drift from the codebase.

## Contributing

This project uses a thin wrapper in `icloud_downloader.py` and the main implementation in `icloud_downloader_lib/`. See [copilot-instructions.md](../.github/copilot-instructions.md) for development guidelines and patterns to follow when contributing.

## Support

For issues, questions, or feature requests, please see the main [README](../README.md).
