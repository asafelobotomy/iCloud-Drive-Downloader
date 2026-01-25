# Documentation

Complete documentation for the iCloud Drive Downloader.

## User Documentation

- **[Quick Start Guide](QUICK_START.md)** - Get started in 5 minutes
- **[Interactive Mode Guide](INTERACTIVE_MODE.md)** - **NEW!** Fully guided setup (no CLI knowledge needed)
- **[Rate Limiting & Throttling](RATE_LIMITING_AND_THROTTLING.md)** - Apple's policies, throttling behavior, and mitigation strategies
- **[Configuration Examples](../examples/README.md)** - Sample config files for common scenarios
- **[Changelog](../CHANGELOG.md)** - Version history and release notes
- **[Version Management](VERSION_MANAGEMENT.md)** - How to update version numbers

## Development Documentation

- **[Version Management](VERSION_MANAGEMENT.md)** - Centralized version control system
- **[Phase 0 Implementation](../archive/dev-notes/PHASE0_CHANGES.md)** - Foundation and security features (archived)
- **[Code Review Report](development/CODE_REVIEW_REPORT.md)** - Comprehensive security audit (A+ grade)
- **[Fixes Applied](development/FIXES_APPLIED.md)** - Summary of critical bug fixes
- **[Implementation Summary](development/IMPLEMENTATION_SUMMARY.md)** - Technical implementation details

## Testing

- **[Test Suite Documentation](../tests/README.md)** - Running tests and coverage reports

## Project Structure

```
/app
├── icloud_downloader.py          # Main application (single-file architecture)
├── requirements.txt               # Production dependencies
├── requirements-test.txt          # Development and testing dependencies
├── README.md                      # Main project README
├── CHANGELOG.md                   # Version history
│
├── docs/                          # Documentation
│   ├── README.md                  # This file
│   ├── QUICK_START.md             # Quick start guide
│   ├── INTERACTIVE_MODE.md        # Interactive mode guide
│   ├── QUICK_REFERENCE.md         # Quick reference card
│   └── development/               # Development documentation
│       ├── CODE_REVIEW_REPORT.md
│       ├── FIXES_APPLIED.md
│       ├── IMPLEMENTATION_SUMMARY.md
│       └── INTERACTIVE_MODE_IMPLEMENTATION.md
│
├── archive/                       # Archived/deprecated files
│   ├── README.md                  # Archive documentation
│   ├── dev-notes/                 # Historical dev docs
│   └── deprecated/                # Deprecated configs
│
├── examples/                      # Configuration examples
│   ├── README.md
│   ├── example-config.json
│   ├── photos-only-config.json
│   ├── large-files-config.json
│   └── sample-manifest.json
│
├── tests/                         # Test suite (63 tests)
│   ├── README.md
│   ├── test_filters.py
│   ├── test_manifest.py
│   ├── test_path_security.py
│   ├── test_retry_logic.py
│   ├── test_cache.py
│   ├── test_stats.py
│   └── test_integration.py
│
└── .github/                       # GitHub configuration
    └── copilot-instructions.md    # AI agent instructions
```

## Contributing

This is a single-file architecture project. See [copilot-instructions.md](../.github/copilot-instructions.md) for development guidelines and patterns to follow when contributing.

## Support

For issues, questions, or feature requests, please see the main [README](../README.md).
