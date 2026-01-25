# Quick Reference: Three Ways to Use iCloud Drive Downloader

## 🎯 Method 1: Interactive Mode (Easiest)

**Perfect for: First-time users, anyone who wants guidance**

```bash
python3 icloud_downloader.py
```

Just run it! The script will ask you 7 simple questions:
1. Your Apple ID
2. Your app-specific password (with help link)
3. Where to save files
4. What to download (everything, photos, documents, etc.)
5. How many concurrent downloads
6. Preview first? (recommended)
7. Save configuration?

**Time to start**: 1-2 minutes  
**Skill level**: Beginner  
**Best for**: First run, trying different settings

---

## 🚀 Method 2: Presets (Fastest)

**Perfect for: Common scenarios, quick downloads**

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

**Time to start**: 10 seconds  
**Skill level**: Beginner-Intermediate  
**Best for**: Specific file types, quick backups

---

## ⚙️ Method 3: Command-Line (Most Powerful)

**Perfect for: Custom configurations, automation, scripts**

### Basic
```bash
# Custom destination
python3 icloud_downloader.py -d /path/to/backup

# More workers (faster)
python3 icloud_downloader.py -w 8

# Preview before downloading
python3 icloud_downloader.py --dry-run
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

### Using Saved Config
```bash
# Save your configuration
python3 icloud_downloader.py --wizard
# (Choose "Save configuration" at step 7)

# Reuse it later
python3 icloud_downloader.py --config icloud_config.json
```

**Time to start**: Instant (if you know what you want)  
**Skill level**: Intermediate-Advanced  
**Best for**: Automation, specific requirements, repeated runs

---

## 📋 Environment Variables (Optional)

Skip credential prompts by setting:

```bash
export ICLOUD_APPLE_ID="user@example.com"
export ICLOUD_PASSWORD="xxxx-xxxx-xxxx-xxxx"

# Now run any way you like
python3 icloud_downloader.py
```

**Best for**: Repeated runs, cron jobs, scripts

---

## 🆘 Common Flags

| Flag | Short | What It Does |
|------|-------|--------------|
| `--wizard` | - | Start interactive setup |
| `--preset <name>` | - | Use preset config (photos, documents, quick-test, large-files) |
| `--destination <path>` | `-d` | Where to save files |
| `--workers <num>` | `-w` | Concurrent downloads (1-10) |
| `--dry-run` | - | Preview without downloading |
| `--include <pattern>` | - | Include files matching pattern |
| `--exclude <pattern>` | - | Exclude files matching pattern |
| `--max-depth <num>` | - | Maximum folder depth |
| `--max-items <num>` | - | Maximum number of files |
| `--config <file>` | - | Load saved config |
| `--no-color` | - | Disable colored output |
| `--skip-confirm` | - | Skip pre-download confirmation |
| `--help` | `-h` | Show all options |
| `--version` | `-V` | Show version number |

---

## 💡 Quick Tips

### First Time?
Use interactive mode: `python3 icloud_downloader.py`

### Want Photos Only?
Use preset: `python3 icloud_downloader.py --preset photos`

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
