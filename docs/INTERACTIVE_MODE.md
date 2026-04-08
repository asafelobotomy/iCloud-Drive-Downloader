# Interactive Mode Guide

## Start Interactive Mode

Interactive mode is the fastest way to configure a download if you do not want to learn the CLI first.

Run the downloader with no arguments:

```bash
python3 icloud_downloader.py
```

The downloader detects the empty command line and opens the main menu automatically.

## Preview the Flow

### Interactive Flow Example

Here's what you'll see when you run the script:

```text
============================================================
   iCloud Drive Downloader
============================================================

Let's download your iCloud Drive files.

💡 Tip: Use Configure from the main menu to change your saved defaults.

  1. 🚀  Start          — use saved preferences and log in
  2. ⚙️   Configure      — change download and auth defaults
  3. 🚪  Exit

Enter choice [1]:

Step 1: Apple ID
Enter your Apple ID (email): user@example.com
✓ Apple ID: user@example.com

Step 2: Apple ID Password
Important: pyicloud signs in with your regular Apple ID password,
then Apple handles any required two-factor authentication.
The password stays in memory for this session unless you choose keyring storage.

Enter your Apple ID password: ****************
✓ Password captured for this session only

Step 3: Choose what to download
  Select an iCloud Drive or Photos option below.

Choose an option below:
  iCloud Drive
  1. ☁️   Everything     — download all iCloud Drive files
  2. 📁  By directory    — pick folders after scanning Drive
  3. 🔍  Explore Drive   — pick folders and files after scanning
  4. 📄  Documents       — download common document files
  5. 🧪  Quick test      — first 50 files, 2 levels deep
  6. ⚙️   Custom filters  — set include and exclude patterns

  iCloud Photo Library
  7. 🖼️   All photos & videos — download the full library
  8. 📸  All photos          — photos only
  9. 🎬  All videos          — videos only
 10. 🗂️   By album            — choose one album
 11. 📅  By month            — choose one month

Enter choice [1]: 2
✓ Download mode for this run: Browse iCloud Drive folders

Step 4: Current preferences
  Download folder: ~/iCloud_Drive_Download
  Download mode: Browse iCloud Drive folders
  Concurrent downloads: 3
  Preview before downloading: No
  Resume downloads: Yes

✓ Setup complete!

Starting...
```

## What Interactive Mode Does

### Smart Defaults

Every question shows a sensible default in `[brackets]`. Just press Enter to accept it.

### Choose After Login

Start always shows the iCloud Drive and Photos chooser after login. Configure no longer stores a separate default download mode.

### Helpful Tips

Look for 💡 markers throughout - they provide context-sensitive guidance at each step.

### Password Guidance

The wizard explains that pyicloud signs in with your regular Apple ID password, then Apple handles 2FA if the account requires it.

### Validation

Invalid inputs are caught immediately with helpful error messages.

### Configuration Saving

Save your choices to a config file and reuse it later:

```bash
python3 icloud_downloader.py --config my_backup.json
```

Saved config files keep download settings only. Interactive mode never writes your Apple ID or Apple ID password to disk.

### Optional Auth and Session Setup

Interactive mode can enable keyring-backed passwords, choose a dedicated session directory, and switch to China mainland routing when needed.

### Preview Mode

Highly recommended for first runs! Preview mode shows you exactly what will be downloaded without using bandwidth or storage.

## When Interactive Mode Starts

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

## Skip Interactive Mode

If you want to use command-line arguments directly:

```bash
# Specify any configuration argument
python3 icloud_downloader.py -d /mnt/backup

# Use a preset
python3 icloud_downloader.py --preset photos

# Load saved config
python3 icloud_downloader.py --config my_backup.json

# Or jump straight into the setup wizard
python3 icloud_downloader.py --wizard
```

## Use Environment Variables

If you set these environment variables, the wizard skips asking for credentials:

```bash
export ICLOUD_APPLE_ID="user@example.com"
export ICLOUD_PASSWORD="your-apple-id-password"

# Now the wizard won't ask for Apple ID or password
python3 icloud_downloader.py
```

This is useful for:

- Repeated runs
- Automation scripts
- Keeping credentials out of shell history

## Common Workflows

### First Run

```bash
# Just run it and follow the prompts
python3 icloud_downloader.py
```

### Preview First

```bash
# Run the wizard and choose preview
python3 icloud_downloader.py
# Review output, then run again without preview
python3 icloud_downloader.py --config config-private.json
```

### Download Photos Quickly

```bash
# Start from the main menu, then choose a Photos Library option
python3 icloud_downloader.py
```

### Run a Small Test

```bash
# Start from the main menu, then choose Quick test
python3 icloud_downloader.py
```

### Use Custom Filters

```bash
# Start from the main menu, then choose Custom filters and enter patterns like: *.pdf,*.docx
python3 icloud_downloader.py
```

## Troubleshoot Interactive Auth and Setup

### Apple ID Is Required

Interactive mode exits if you leave Apple ID blank. Enter your iCloud email address.

### Password Is Required

You must enter your Apple ID password unless you already provided it through `ICLOUD_PASSWORD` or the system keyring.

### Login Still Fails With the Correct Password

Common issues:

1. Use your regular Apple ID password, not an app-specific password
2. Sign in once at `https://www.icloud.com` and accept any pending Apple prompts or terms
3. Use `--china-mainland` if your Apple ID region is China mainland
4. Check your internet connection

If Apple exposes multiple verification routes, the CLI can guide you through trusted-device, SMS, or phone-call code delivery. If pyicloud exposes a broken security-key challenge without the required WebAuthn payload, choose one of the available code-delivery methods instead.

### Skip Preview on a Later Run

If you saved a config with `"dry_run": true`, edit the config file and set it to `false`, or rerun without that saved config and choose not to preview.

There is no `--no-dry-run` flag.

## Compare Wizard and CLI Modes

| Interactive Mode | Command-Line Mode |
| ---------------- | ----------------- |
| Guided questions | Requires knowing flags |
| Validates input immediately | Silent failures possible |
| Shows tips and help | Requires reading docs |
| Great for first-time use | Better for automation |
| Can save config | Can load config |
| User-friendly | Power-user efficient |

Use interactive mode once to create a working configuration, then switch to `--config` for repeated runs.

## See Also

- [Quick Start Guide](../README.md#quick-start) - Getting started
- [Quick Reference](QUICK_REFERENCE.md) - Common commands and flags
- [Configuration Examples](../examples/README.md) - Sample JSON config files
- [README CLI Reference](../README.md#cli-reference) - All available flags
