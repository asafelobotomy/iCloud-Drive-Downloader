# Interactive Mode Guide

## Overview

iCloud Drive Downloader features a **fully interactive mode** that makes downloading your iCloud files as simple as answering a few questions. No command-line knowledge required!

## Quick Start

Just run the script with no arguments:

```bash
python3 icloud_downloader.py
```

That's it! The script automatically detects that you haven't specified any configuration and enters interactive mode.

## What to Expect

### Interactive Flow Example

Here's what you'll see when you run the script:

```
Running in interactive mode...
(Use --help to see command-line options)

============================================================
   iCloud Drive Downloader - Interactive Setup
============================================================

Welcome! Let's download your iCloud Drive files.

💡 Tip: Press Enter to use default values shown in [brackets]

Step 1: Apple ID
Enter your Apple ID (email): user@example.com
✓ Apple ID: user@example.com

Step 2: App-Specific Password
Important: You need an app-specific password (NOT your regular password)
Get one at: https://appleid.apple.com/account/manage
  → Sign in → Security → App-Specific Passwords → Generate

Enter app-specific password: ****************
✓ Password saved

Step 3: Choose download location
Download folder [/root/iCloud_Drive_Download]: /mnt/backup
✓ Will save to: /mnt/backup

Step 4: What would you like to download?
  1. Everything (full backup)
  2. Photos and videos only
  3. Documents only
  4. Quick test (first 50 files)
  5. Custom filters (advanced)

Enter choice [1]: 2
✓ Will download photos and videos only

Step 5: Performance settings
How many concurrent downloads? (1-10)
💡 Tip: More workers = faster downloads, but uses more bandwidth
Workers [3]: 5
✓ Will use 5 concurrent downloads

Step 6: Preview before downloading (recommended)
Preview what will be downloaded without actually downloading anything?
💡 Tip: This lets you verify before using bandwidth
Preview only? [Y/n]: y
✓ Will run in preview mode (no actual downloads)

Step 7: Save configuration (optional)
Save this configuration for next time? [Y/n]: y
Config filename [icloud_config.json]: my_backup.json
✓ Configuration saved to: my_backup.json

✓ Setup complete!

Starting download...

Press Enter to begin...
```

## Key Features

### 1. Smart Defaults
Every question shows a sensible default in `[brackets]`. Just press Enter to accept it.

### 2. Helpful Tips
Look for 💡 markers throughout - they provide context-sensitive guidance at each step.

### 3. App-Specific Password Help
The wizard provides the exact link and navigation path to create an Apple app-specific password. No searching required!

### 4. Validation
Invalid inputs are caught immediately with helpful error messages.

### 5. Configuration Saving
Save your choices to a config file and reuse it later:

```bash
python3 icloud_downloader.py --config my_backup.json
```

### 6. Preview Mode
Highly recommended for first runs! Preview mode shows you exactly what will be downloaded without using bandwidth or storage.

## When Interactive Mode Triggers

Interactive mode automatically starts when:
- You run the script with **no arguments**
- You haven't specified any of these flags:
  - `--config` (loading saved config)
  - `--preset` (using preset)
  - `--destination` (custom path)
  - `--dry-run` (preview mode)
  - `--include/--exclude` (filters)
  - `--max-items/--max-depth` (limits)
  - `--save-config` (saving config only)

## Bypassing Interactive Mode

If you want to use command-line arguments directly:

```bash
# Specify any configuration argument
python3 icloud_downloader.py -d /mnt/backup

# Use a preset
python3 icloud_downloader.py --preset photos

# Load saved config
python3 icloud_downloader.py --config my_backup.json

# Or explicitly use the wizard flag
python3 icloud_downloader.py --wizard
```

## Using Environment Variables

If you set these environment variables, the wizard skips asking for credentials:

```bash
export ICLOUD_APPLE_ID="user@example.com"
export ICLOUD_PASSWORD="xxxx-xxxx-xxxx-xxxx"

# Now the wizard won't ask for Apple ID or password
python3 icloud_downloader.py
```

This is useful for:
- Repeated runs
- Automation scripts
- Keeping credentials out of shell history

## Common Patterns

### First Time User
```bash
# Just run it - follow the prompts
python3 icloud_downloader.py
```

### Preview First (Recommended)
```bash
# Run interactive mode, choose Preview
python3 icloud_downloader.py
# Review output, then run again without preview
python3 icloud_downloader.py --config icloud_config.json
```

### Quick Photo Backup
```bash
# Interactive mode, select option 2 (Photos)
python3 icloud_downloader.py
```

### Test Run
```bash
# Interactive mode, select option 4 (Quick test)
python3 icloud_downloader.py
```

### Advanced: Custom Filters
```bash
# Interactive mode, select option 5 (Custom)
# Then enter patterns like: *.pdf,*.docx
python3 icloud_downloader.py
```

## Troubleshooting

### "Apple ID is required"
The wizard exits if you leave Apple ID blank. Enter your iCloud email address.

### "Password is required"
You must enter an app-specific password. Follow the link provided in the wizard to generate one.

### App-Specific Password Doesn't Work
Common issues:
1. Make sure it's an **app-specific password**, not your regular Apple password
2. Check that 2FA is enabled on your Apple account
3. Try generating a fresh app-specific password
4. Check your internet connection

### Want to Skip Preview Later
If you saved a config with `"dry_run": true`, edit the config file or use:
```bash
python3 icloud_downloader.py --config my_backup.json --no-dry-run
```
(Note: `--no-dry-run` doesn't exist yet, so just edit the JSON file to set `"dry_run": false`)

## Comparison with Command-Line Mode

| Interactive Mode | Command-Line Mode |
|-----------------|-------------------|
| Guided questions | Requires knowing flags |
| Validates input immediately | Silent failures possible |
| Shows tips and help | Requires reading docs |
| Great for first-time use | Better for automation |
| Can save config | Can load config |
| User-friendly | Power-user efficient |

**Best Practice**: Use interactive mode to configure your setup once, save the config, then use `--config` for repeated runs.

## See Also

- [Quick Start Guide](../README.md#quick-start) - Getting started
- [Preset Configurations](PRESETS.md) - Pre-built configs
- [Configuration Files](CONFIGURATION.md) - JSON config format
- [Command-Line Reference](CLI_REFERENCE.md) - All available flags
