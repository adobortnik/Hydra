# Hydra Phone Farm — Obfuscation Guide

## Overview

The codebase is obfuscated using **PyArmor 9.x** before deployment. This converts Python source code into protected bytecode that can't be easily reverse-engineered.

**Current setup:** PyArmor 9.2.3 (trial/free version)
**Target:** PyArmor Pro license (unlocks full protection)

---

## Quick Start

### Build Obfuscated Distribution

```bash
# Full build with verification
python build_obfuscated.py --clean --verify

# Preview what will be done (no changes)
python build_obfuscated.py --dry-run

# Just build (no verify step)
python build_obfuscated.py --clean
```

Output goes to `phone-farm/dist/` — a complete copy of the project with obfuscated Python files.

### What Gets Obfuscated
- All Python files in `automation/`, `dashboard/`, `db/`, and root scripts
- Entry points: `simple_app.py`, `bot_engine.py`, `run_device.py`, `launch_farm.py`, `run_dashboard.py`, `watchdog.py`
- Total: ~183 Python files

### What Gets Copied As-Is (NOT obfuscated)
- `dashboard/templates/` — Jinja2 HTML templates
- `dashboard/static/` — CSS, JS, images
- `dashboard/data/` — config files, API keys
- `data/` — names, bios, profile pics
- `db/*.db` — SQLite databases (phone_farm.db etc.)
- `media_library/` — media files
- All `.json`, `.txt`, `.md`, `.bat`, `.ps1`, `.vbs` files
- `logs/`, `screenshots/` — empty dirs created for runtime

---

## Deploying the Obfuscated Build

1. **Build it:**
   ```bash
   python build_obfuscated.py --clean --verify
   ```

2. **Copy `dist/` folder** to the target machine

3. **Install dependencies** on target:
   ```bash
   pip install -r dist/dashboard/requirements.txt
   ```

4. **Run from dist/:**
   ```bash
   cd dist
   python dashboard/run_dashboard.py     # Dashboard (port 5055)
   python run_device.py <device_id>       # Single device
   python launch_farm.py                  # Full farm
   ```

5. **Important:** The `pyarmor_runtime_000000/` folder in `dist/` MUST be present — obfuscated files import from it at runtime.

---

## Free Version Limitations (Current)

The trial/free PyArmor license has these restrictions:

### "Big Script" Limit
Files over a certain complexity/size can't be obfuscated. Currently **11 files** are affected and are copied as plain Python:

| File | Why it matters |
|------|---------------|
| `dashboard/simple_app.py` | **Main dashboard entry point** — most critical file |
| `automation/bot_engine.py` | **Core bot logic** — very important |
| `automation/ig_controller.py` | Instagram controller |
| `automation/api.py` | API layer |
| `dashboard/content_schedule_routes.py` | Content scheduling |
| `dashboard/device_manager_routes.py` | Device management |
| `dashboard/profile_automation_routes.py` | Profile automation |
| `dashboard/uiAutomator/login_automation.py` | Login automation |
| `automation/actions/post_content.py` | Post creation |
| `automation/actions/share_to_story.py` | Story sharing |
| `dashboard/uiAutomator/bot/GramAddict/core/views.py` | UI views |

### Missing Protection Modes
- **No RFT mode** — function/class names remain readable
- **No BCC mode** — no C compilation (strongest protection)
- **No mix-str** — string constants (URLs, API endpoints) visible in obfuscated code

---

## Pro License — What It Unlocks

### RFT Mode (Rename Functions/Types)
Renames all function names, class names, and variables to meaningless identifiers. Makes decompiled code unreadable.

### BCC Mode (Bytecode to C)
Compiles critical Python functions to C extensions. Nearly impossible to reverse-engineer.

### Mix-String
Obfuscates string constants so API URLs, secret keys, and identifiers aren't visible in the binary.

### No Size Limits
All 183 files (including the 11 "big scripts") will be fully obfuscated.

### How to Register Pro License

1. **Purchase** from https://pyarmor.dashingsoft.com/

2. **Register:**
   ```bash
   pyarmor reg /path/to/pyarmor-regfile-xxxx.zip
   ```

3. **Enable Pro features** in `build_obfuscated.py` — uncomment these lines in the `run_pyarmor()` function:
   ```python
   cmd = [
       PYARMOR, "gen",
       "--output", str(output_dir),
       "--enable-rft",      # ← Uncomment: Rename functions/classes
       "--enable-bcc",      # ← Uncomment: Compile to C
       "--mix-str",         # ← Uncomment: Obfuscate strings
       "--private",         # ← Uncomment: Private mode
   ] + file_paths
   ```

4. **Rebuild:**
   ```bash
   python build_obfuscated.py --clean --verify
   ```

---

## Build Script Details

### `build_obfuscated.py`

The build script does:
1. **Discovers** all Python files (excludes temp/debug scripts automatically)
2. **Groups by directory** and runs PyArmor `gen` per directory
3. **Falls back to per-file** if batch fails (handles free version limits gracefully)
4. **Copies failed files as plain** Python (so the build always produces a working output)
5. **Copies assets** (templates, static, data, databases)
6. **Verifies** obfuscation (checks for pyarmor markers in output files)
7. **Tests imports** from the dist/ folder

### Configuration
All configuration is at the top of `build_obfuscated.py`:
- `ENTRY_POINTS` — main runnable scripts
- `SKIP_DIRS` — directories to ignore completely
- `COPY_DIRS` — directories copied as-is
- `EXCLUDE_PREFIXES` — filename patterns for temp/debug scripts
- `EXCLUDE_FILES` — specific files to skip

### Build Stats (Free Version)
- **Time:** ~37 seconds
- **Files obfuscated:** 172/183 (94%)
- **Files plain (too big):** 11 (6%)
- **Output size:** ~1.4 GB (includes media_library)
- **Import test:** ✅ Passes

---

## Troubleshooting

### "out of license" error
Free version can't handle large/complex scripts. These are copied plain. Get Pro license to fix.

### "No module named pyarmor_runtime_000000"
The `pyarmor_runtime_000000/` folder must be in the Python path. It should be at the root of `dist/`.

### Obfuscated file crashes at import
Check Python version matches — PyArmor obfuscates for a specific Python version. Build and run on the same version (currently Python 3.13).

### Templates/static not found
Check that `dist/dashboard/templates/` and `dist/dashboard/static/` exist. The build copies them automatically.

---

## File Structure After Build

```
dist/
├── pyarmor_runtime_000000/     # PyArmor runtime (REQUIRED)
├── automation/                  # Obfuscated automation code
│   ├── actions/                 # Obfuscated action modules
│   └── *.py                     # Protected bytecode
├── dashboard/
│   ├── templates/               # HTML templates (plain)
│   ├── static/                  # CSS/JS/images (plain)
│   ├── data/                    # Config files (plain)
│   ├── uiAutomator/            # Obfuscated + profile pics
│   └── *.py                     # Protected bytecode
├── data/                        # Data files (plain)
├── db/
│   ├── phone_farm.db           # SQLite database (plain)
│   └── *.py                     # Obfuscated DB models
├── logs/                        # Empty (runtime)
├── screenshots/                 # Empty (runtime)
├── launch_farm.py              # Obfuscated
├── run_device.py               # Obfuscated
├── watchdog.py                 # Obfuscated
└── ...
```
