# Quick Reference: Three Ways to Use iCloud Drive Downloader

## 🎯 Method 1: Interactive Mode (Easiest)

### Why Use Interactive Mode

First-time users and anyone who wants guidance.

```bash
python3 icloud_downloader.py
```

Just run it! Start asks you 4 things:

1. Your Apple ID
2. Your Apple ID password (then Apple handles 2FA if needed)
3. What to download — pick from iCloud Drive or Photos options
4. Review the current preferences before it starts

Use **Configure** from the main menu to change the download folder, keyring, session, workers, preview mode, and other defaults before starting.

**Time to start**: 1-2 minutes  
**Skill level**: Beginner  
**Best for**: First run, trying different settings

---

## 🚀 Method 2: Presets (Fastest)

### Why Use Presets

Common scenarios and quick downloads.

```bash
# Download only photos and videos
python3 icloud_downloader.py --preset photos

# Download only documents
python3 icloud_downloader.py --preset documents

# Quick test (50 files, 2 levels deep)
python3 icloud_downloader.py --preset quick-test

# Large files only (>100MB)
python3 icloud_downloader.py --preset large-files
```

Combine with other options:

```bash
python3 icloud_downloader.py --preset photos -d /mnt/backup
```

Use direct Photos Library flags when you want Apple Photos content instead of iCloud Drive files:

```bash
python3 icloud_downloader.py --source photos-library --photos-scope photos
```

**Time to start**: 10 seconds  
**Skill level**: Beginner-Intermediate  
**Best for**: Specific file types, quick backups

---

## ⚙️ Method 3: Command-Line (Most Powerful)

### Why Use Command-Line Mode

Custom configurations, automation, and scripts.

### Basic

```bash
# Custom destination
python3 icloud_downloader.py -d /path/to/backup

# More workers (faster)
python3 icloud_downloader.py -w 8

# Preview before downloading
python3 icloud_downloader.py --dry-run

# Download Photos Library videos only
python3 icloud_downloader.py --source photos-library --photos-scope videos
```

### With Filters

```bash
# Only photos
python3 icloud_downloader.py --include "*.jpg" --include "*.png" --include "*.heic"

# Exclude cache and temp files
python3 icloud_downloader.py --exclude "*/Cache/*" --exclude "*.tmp"

# Files between 1MB and 100MB
python3 icloud_downloader.py --min-size 1048576 --max-size 104857600
```

### Advanced

```bash
# Full control
python3 icloud_downloader.py \
  -d /mnt/backup \
  -w 10 \
  --include "*.pdf" \
  --exclude "*/Archive/*" \
  --max-depth 3 \
  --retries 5 \
  --log download.log \
  --dry-run
```

### Photos Library

```bash
# Download one Photos album
python3 icloud_downloader.py \
  --source photos-library \
  --photos-scope by-album \
  --photos-album "Favorites"

# Download one month from Photos Library
python3 icloud_downloader.py \
  --source photos-library \
  --photos-scope by-month \
  --photos-month 2026-03
```

### Using Saved Config

```bash
# Run Configure from the interactive menu to save defaults
python3 icloud_downloader.py
# (Choose "2. Configure" → set preferences → "11. Save & return")

# Or save from the command line
python3 icloud_downloader.py --save-config config-private.json

# Reuse it later
python3 icloud_downloader.py --config config-private.json
```

Saved config files never include your Apple ID or Apple ID password.

**Time to start**: Instant (if you know what you want)  
**Skill level**: Intermediate-Advanced  
**Best for**: Automation, specific requirements, repeated runs

---

## 📋 Environment Variables (Optional)

Skip credential prompts by setting:

```bash
export ICLOUD_APPLE_ID="user@example.com"
export ICLOUD_PASSWORD="your-apple-id-password"

# Now run any way you like
python3 icloud_downloader.py
```

**Best for**: Repeated runs, cron jobs, scripts

---

## 🆘 Common Flags

| Flag | Short | What It Does |
| ---- | ----- | ------------ |
| `--wizard` | - | Start interactive setup |
| `--preset <name>` | - | Use preset config (photos, documents, quick-test, large-files) |
| `--source <drive\|photos-library>` | - | Choose iCloud Drive or Photos Library |
| `--photos-scope <scope>` | - | Choose all, photos, videos, by-album, or by-month |
| `--photos-after <date>` | - | Filter Photos Library items created on or after a date |
| `--photos-before <date>` | - | Filter Photos Library items created on or before a date |
| `--list-presets` | - | Show preset names and descriptions |
| `--show-config` | - | Print the resolved configuration and exit |
| `--auth-status` | - | Print local iCloud session status and exit |
| `--destination <path>` | `-d` | Where to save files |
| `--workers <num>` | `-w` | Concurrent downloads (1-10) |
| `--dry-run` | - | Preview without downloading |
| `--include <pattern>` | - | Include files matching pattern |
| `--exclude <pattern>` | - | Exclude files matching pattern |
| `--max-depth <num>` | - | Maximum folder depth |
| `--max-items <num>` | - | Maximum number of files |
| `--config <file>` | - | Load saved config |
| `--resume` / `--no-resume` | - | Override resume behavior |
| `--progress` / `--no-progress` | - | Override progress bar behavior |
| `--session-dir <path>` | - | Use a custom iCloud session storage directory |
| `--use-keyring` | - | Load the password from the system keyring |
| `--store-in-keyring` | - | Save the password from this run into the system keyring |
| `--china-mainland` | - | Use Apple’s China mainland iCloud endpoints |
| `--no-color` | - | Disable colored output |
| `--skip-confirm` | - | Skip pre-download confirmation |
| `--help` | `-h` | Show all options |
| `--version` | `-V` | Show version number |

---

## 💡 Quick Tips

### First Time?

Use interactive mode: `python3 icloud_downloader.py`

### Reuse An Existing Login?

Inspect the saved session without downloading: `python3 icloud_downloader.py --auth-status --use-keyring`

### Want Photos Only?

Use preset: `python3 icloud_downloader.py --preset photos`

### Want Photos Library Items?

Use direct source flags: `python3 icloud_downloader.py --source photos-library --photos-scope photos`

### Not Sure What You Have?

Preview first: `python3 icloud_downloader.py --dry-run`

### Slow Internet?

Reduce workers: `python3 icloud_downloader.py -w 1`

### Fast Connection?

Increase workers: `python3 icloud_downloader.py -w 10`

### Need to Stop?

Press Ctrl+C once (graceful, saves progress)  
Press Ctrl+C twice (force quit)

### Resume Later?

Just run again with same destination - automatically resumes

### Save for Later?

Run wizard, save config, then use `--config` next time

---

## 🔗 More Help

- **Full documentation**: `docs/README.md`
- **Interactive mode guide**: `docs/INTERACTIVE_MODE.md`
- **All CLI options**: `python3 icloud_downloader.py --help`
- **Configuration examples**: `examples/README.md`
- **Troubleshooting**: `docs/QUICK_START.md`

---

## 🎓 Progressive Learning Path

1. **Start**: Run `python3 icloud_downloader.py` (interactive)
2. **Learn**: Try presets like `--preset photos`
3. **Customize**: Add flags like `-d /backup -w 5`
4. **Save**: Create config file with `--wizard` + save
5. **Automate**: Use `--config` for repeated downloads
6. **Master**: Combine filters, limits, and options

**Remember**: You don't need to learn everything at once. Start simple, add complexity as needed!
