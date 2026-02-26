#!/usr/bin/env python3
"""
Hydra Phone Farm — PyArmor Obfuscation Build Script
=====================================================
Creates an obfuscated copy of the entire phone-farm codebase in dist/.

How it works:
  1. Discovers all .py files in the project (excluding junk/temp files)
  2. Uses PyArmor 'gen' to obfuscate them in bulk
  3. Copies non-Python assets (templates, static, data, db, etc.) as-is
  4. Result: dist/ folder that mirrors the original structure, ready to run

Usage:
    python build_obfuscated.py              # Full obfuscated build
    python build_obfuscated.py --dry-run    # Show what would be done
    python build_obfuscated.py --clean      # Remove dist/ and rebuild
    python build_obfuscated.py --verify     # Build + verify obfuscation

PyArmor Version Notes:
    Free/Trial: Basic obfuscation, no RFT/BCC/mix-str. Big scripts may fail.
    Pro License: Unlocks RFT mode (rename functions/classes), BCC mode (C compilation),
                 mix-str (string obfuscation), and removes size limits.

To register Pro license:
    pyarmor reg /path/to/pyarmor-regfile-xxxx.zip
"""

import os
import sys
import shutil
import subprocess
import argparse
import time
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════

FARM_DIR = Path(__file__).parent.resolve()
DIST_DIR = FARM_DIR / "dist"

# Find pyarmor executable - check multiple locations
def find_pyarmor():
    """Locate the pyarmor executable."""
    # Try PATH first
    for cmd in ["pyarmor", "pyarmor.exe"]:
        path = shutil.which(cmd)
        if path:
            return path
    
    # Try known Windows Store Python location
    local_app = os.environ.get("LOCALAPPDATA", "")
    if local_app:
        for ver in ["Python313", "Python312", "Python311"]:
            candidate = Path(local_app) / "Packages" / f"PythonSoftwareFoundation.Python.3.{ver[-2:]}_qbz5n2kfra8p0" / "LocalCache" / "local-packages" / ver / "Scripts" / "pyarmor.exe"
            if candidate.exists():
                return str(candidate)
    
    # Try venv
    venv_pyarmor = FARM_DIR / "venv" / "Scripts" / "pyarmor.exe"
    if venv_pyarmor.exists():
        return str(venv_pyarmor)
    
    return None

PYARMOR = find_pyarmor()

# ── Entry point scripts (these are the main runnable files) ──
ENTRY_POINTS = [
    "dashboard/simple_app.py",
    "dashboard/run_dashboard.py",
    "automation/bot_engine.py",
    "run_device.py",
    "launch_farm.py",
    "watchdog.py",
]

# ── Directories to SKIP entirely (not obfuscated, not copied unless in COPY_DIRS) ──
SKIP_DIRS = {
    "dist", "build", "venv", ".venv", "env", "__pycache__", ".git",
    "node_modules", ".idea", ".vscode", "test_obf",
    # Large asset dirs we handle separately
    "screenshots", "xml_dumps", "test_results", "references",
    "logs",  # logs are runtime-generated, don't ship old ones
}

# ── Directories to copy AS-IS (non-Python assets) ──
# Format: (source_relative_path, dest_relative_path)
# dest is relative to DIST_DIR
COPY_DIRS = [
    ("dashboard/templates", "dashboard/templates"),
    ("dashboard/static", "dashboard/static"),
    ("dashboard/data", "dashboard/data"),
    ("dashboard/uiAutomator/profile_pictures", "dashboard/uiAutomator/profile_pictures"),
    ("dashboard/uiAutomator/bot_data", "dashboard/uiAutomator/bot_data"),
    ("dashboard/uiAutomator/bot/config-examples", "dashboard/uiAutomator/bot/config-examples"),
    ("dashboard/uiAutomator/bot/res", "dashboard/uiAutomator/bot/res"),
    ("dashboard/uiAutomator/bot/test", "dashboard/uiAutomator/bot/test"),
    ("data", "data"),
    ("db/migrations", "db/migrations"),
    ("docs", "docs"),
    # ("media_library", "media_library"),  # EXCLUDED — videos are 1.3GB+, added via dashboard
    ("scheduled_posts", "scheduled_posts"),
]

# ── Individual files to copy AS-IS ──
COPY_FILES_PATTERNS = [
    "*.json", "*.txt", "*.md", "*.bat", "*.ps1", "*.sh",
    "*.html", "*.css", "*.js", "*.jpg", "*.jpeg", "*.png",
    "*.gif", "*.webp", "*.ico", "*.svg",
    "*.db", "*.sqlite", "*.sqlite3",
    "*.yaml", "*.yml", "*.toml", "*.cfg", "*.ini",
    "*.csv", "*.vbs",
    "requirements.txt",
]

# ── Files/patterns to EXCLUDE from obfuscation ──
# These are temp/debug scripts that shouldn't be in the distribution
EXCLUDE_PREFIXES = [
    "debug_", "tmp_", "temp_", "check_", "fix_", "verify_",
    "inspect_", "examine_", "collect_", "dump_", "investigate",
    "tap_", "reset_and_", "report_final", "setup_test",
    "quick_", "find_", "extract_", "parse_", "grant_",
    "do_dashboard_", "screen_capture",
    "_add_", "_age_", "_apply_", "_bump_", "_check_", "_cleanup",
    "_connect_", "_create_test", "_disable_", "_dump_", "_extend_",
    "_extract_", "_find_", "_fix_", "_follow_", "_inspect_",
    "_log_", "_migrate_", "_reschedule", "_restart", "_restore_",
    "_revert_", "_run_post", "_schedule_", "_setup_", "_set_active",
    "_show_", "_start4", "_tap_", "_test_", "_tmp_", "_update_",
    "_verify_", "_watch_",
]

# ── Specific files to always EXCLUDE ──
EXCLUDE_FILES = {
    "build.py", "build_package.py", "build_obfuscated.py",
    "app.py",  # old/duplicate entry point
    "run.py", "start.py", "run_server.py",  # old scripts
    "jarvis.py", "map_editor.py",  # utility scripts
    "sync_devices.py", "sync_fingerprints.py",  # one-off sync scripts
}

# ── Specific files to always INCLUDE (override exclude patterns) ──
FORCE_INCLUDE = {
    "dashboard/check_accounts_columns.py",  # needed at runtime? keep if unsure
    "automation/actions/check_profile.py",   # bot action — must not be excluded
    "grant_permissions.py",                  # imported by device_manager_routes
}


# ═══════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════

def should_obfuscate(rel_path: str, filename: str) -> bool:
    """Determine if a Python file should be obfuscated."""
    if not filename.endswith(".py"):
        return False
    
    # Force include overrides everything
    if rel_path.replace("\\", "/") in FORCE_INCLUDE:
        return True
    
    # Check explicit excludes
    if filename in EXCLUDE_FILES:
        return False
    
    # Check prefix patterns
    for prefix in EXCLUDE_PREFIXES:
        if filename.startswith(prefix):
            return False
    
    return True


def discover_python_files() -> list:
    """
    Walk the project tree and collect all Python files to obfuscate.
    Returns list of Path objects relative to FARM_DIR.
    """
    py_files = []
    
    for root, dirs, files in os.walk(FARM_DIR):
        # Skip excluded directories (modify in-place to prevent descent)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        
        rel_root = Path(root).relative_to(FARM_DIR)
        
        for f in files:
            if not f.endswith(".py"):
                continue
            
            rel_path = str(rel_root / f).replace("\\", "/")
            
            if should_obfuscate(rel_path, f):
                py_files.append(rel_root / f)
    
    return sorted(py_files)


def discover_asset_files() -> list:
    """
    Discover non-Python files that should be copied as-is.
    Returns list of (src_path, dest_path) tuples.
    """
    assets = []
    
    for root, dirs, files in os.walk(FARM_DIR):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        
        rel_root = Path(root).relative_to(FARM_DIR)
        
        for f in files:
            if f.endswith(".py") or f.endswith(".pyc") or f.endswith(".pyo"):
                continue
            
            rel_path = rel_root / f
            src = FARM_DIR / rel_path
            dest = DIST_DIR / rel_path
            
            # Check if it matches any copy pattern
            for pattern in COPY_FILES_PATTERNS:
                if f == pattern or (pattern.startswith("*.") and f.endswith(pattern[1:])):
                    assets.append((src, dest))
                    break
    
    return assets


def run_pyarmor(py_files: list, dry_run: bool = False) -> dict:
    """
    Run PyArmor to obfuscate Python files.
    
    Strategy: Use 'pyarmor gen' with --output to generate obfuscated files.
    PyArmor 8+ uses 'gen' command (not 'obfuscate' from v7).
    
    Returns dict with counts: {'success': N, 'failed': N, 'skipped': N}
    """
    if not PYARMOR:
        print("ERROR: pyarmor executable not found!")
        print("Install it: pip install pyarmor")
        sys.exit(1)
    
    print(f"\n  PyArmor path: {PYARMOR}")
    
    # Show PyArmor version/license info
    result = subprocess.run([PYARMOR, "--version"], capture_output=True, text=True)
    for line in result.stdout.strip().split("\n")[:3]:
        print(f"  {line}")
    
    stats = {"success": 0, "failed": 0, "failed_files": []}
    
    if dry_run:
        print(f"\n  [DRY RUN] Would obfuscate {len(py_files)} files")
        return stats
    
    # ──────────────────────────────────────────────────────────────
    # PyArmor gen configuration
    # ──────────────────────────────────────────────────────────────
    # 
    # FREE version flags (current):
    #   --output DIR     : where to write obfuscated files
    #   --platform       : target platform (auto-detected)
    #
    # PRO version flags (enable after registering license):
    #   --enable-rft     : Rename Function/class names (strong obfuscation)
    #   --enable-bcc     : Compile to C extensions (strongest protection)
    #   --mix-str        : Obfuscate string constants
    #   --private        : Private mode (restrict module access)
    #   --restrict       : Restrict mode (prevent import from non-obfuscated code)
    #   --period N       : Check license every N seconds
    #   --bind-device    : Bind to specific machine
    #
    # ──────────────────────────────────────────────────────────────

    # Group files by directory for efficient batch processing
    # PyArmor works best when processing files per-package
    dir_groups = {}
    for pf in py_files:
        parent = str(pf.parent) if str(pf.parent) != "." else ""
        if parent not in dir_groups:
            dir_groups[parent] = []
        dir_groups[parent].append(pf)
    
    total_groups = len(dir_groups)
    
    for i, (rel_dir, files) in enumerate(sorted(dir_groups.items()), 1):
        display_dir = rel_dir if rel_dir else "(root)"
        print(f"\n  [{i}/{total_groups}] Obfuscating: {display_dir}/ ({len(files)} files)")
        
        if rel_dir:
            output_dir = DIST_DIR / rel_dir
        else:
            output_dir = DIST_DIR
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Build the pyarmor gen command
        file_paths = [str(FARM_DIR / f) for f in files]
        
        cmd = [
            PYARMOR, "gen",
            "--output", str(output_dir),
            # ── PRO LICENSE FEATURES ──
            # NOTE: --enable-rft REMOVED — it renames exported symbols which
            # breaks cross-module imports when files are obfuscated in separate
            # batches (each directory = separate batch). This causes ImportError
            # for named imports and access violations on Python 3.13.
            # "--enable-rft",    # DISABLED — breaks cross-module imports
            "--mix-str",         # Obfuscate string constants (safe)
            "--enable-bcc",      # Compile to C extensions (strongest protection, needs clang)
        ] + file_paths
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(FARM_DIR),
        )
        
        if result.returncode == 0:
            stats["success"] += len(files)
            print(f"    ✓ {len(files)} files obfuscated")
        else:
            # Batch failed — try one-by-one to identify problematic files
            stderr = result.stderr.strip()
            if "big script" in stderr.lower() or "too large" in stderr.lower():
                print(f"    ⚠ Batch failed (likely big script limit), trying individually...")
            else:
                print(f"    ⚠ Batch failed: {stderr[:200]}")
                print(f"    Trying individually...")
            
            for f in files:
                single_cmd = [
                    PYARMOR, "gen",
                    "--output", str(output_dir),
                    # "--enable-rft",  # DISABLED — breaks cross-module imports
                    "--mix-str",
                    "--enable-bcc",
                    str(FARM_DIR / f),
                ]
                
                r = subprocess.run(single_cmd, capture_output=True, text=True, cwd=str(FARM_DIR))
                
                if r.returncode == 0:
                    stats["success"] += 1
                    print(f"    ✓ {f.name}")
                else:
                    # File failed — copy as-is (plain) and note it
                    stats["failed"] += 1
                    stats["failed_files"].append(str(f))
                    
                    # Copy plain file as fallback
                    dest = output_dir / f.name
                    shutil.copy2(FARM_DIR / f, dest)
                    
                    err_short = r.stderr.strip().split("\n")[-1][:100] if r.stderr else "unknown error"
                    print(f"    ✗ {f.name} — copied plain ({err_short})")
    
    return stats


def copy_assets(dry_run: bool = False):
    """Copy non-Python assets to dist/ preserving structure."""
    print(f"\n{'─'*60}")
    print(f"  Copying non-Python assets")
    print(f"{'─'*60}")
    
    copied = 0
    
    # Copy entire directories
    for src_rel, dest_rel in COPY_DIRS:
        src = FARM_DIR / src_rel
        dest = DIST_DIR / dest_rel
        
        if not src.exists():
            print(f"  SKIP (not found): {src_rel}/")
            continue
        
        if dry_run:
            file_count = sum(1 for _ in src.rglob("*") if _.is_file())
            print(f"  [DRY RUN] Would copy: {src_rel}/ ({file_count} files)")
            continue
        
        # Copy, ignoring Python bytecode
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(
            src, dest,
            ignore=shutil.ignore_patterns("*.pyc", "__pycache__"),
            dirs_exist_ok=True,
        )
        file_count = sum(1 for _ in dest.rglob("*") if _.is_file())
        copied += file_count
        print(f"  ✓ {src_rel}/ → {dest_rel}/ ({file_count} files)")
    
    # Copy individual asset files discovered in the tree
    # (handles .json, .txt, .md, etc. that are alongside .py files)
    assets = discover_asset_files()
    for src, dest in assets:
        # Skip if already covered by directory copy above
        rel = src.relative_to(FARM_DIR)
        already_covered = False
        for src_dir_rel, _ in COPY_DIRS:
            if str(rel).replace("\\", "/").startswith(src_dir_rel):
                already_covered = True
                break
        if already_covered:
            continue
        
        if dry_run:
            print(f"  [DRY RUN] Would copy: {rel}")
            continue
        
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied += 1
    
    # Create empty directories that are needed at runtime
    for d in ["logs", "db", "screenshots"]:
        (DIST_DIR / d).mkdir(parents=True, exist_ok=True)
    
    # Copy DB files specifically (SQLite databases)
    for db_file in (FARM_DIR / "db").glob("*.db"):
        dest = DIST_DIR / "db" / db_file.name
        if not dry_run:
            shutil.copy2(db_file, dest)
            print(f"  ✓ db/{db_file.name} (SQLite database)")
            copied += 1
    
    # Also check for phone_farm.db in dashboard/ or root
    for search_dir in [FARM_DIR / "dashboard", FARM_DIR]:
        for db_file in search_dir.glob("*.db"):
            rel = db_file.relative_to(FARM_DIR)
            dest = DIST_DIR / rel
            if not dry_run and not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(db_file, dest)
                print(f"  ✓ {rel} (SQLite database)")
                copied += 1
    
    print(f"\n  Total assets copied: {copied}")
    return copied


def copy_pyarmor_runtime():
    """
    Ensure the pyarmor_runtime package is in dist/.
    PyArmor gen creates a pyarmor_runtime_XXXXXX/ folder that MUST be
    alongside the obfuscated files for them to import correctly.
    """
    # Find pyarmor_runtime dirs that were created during obfuscation
    runtime_dirs = list(DIST_DIR.glob("**/pyarmor_runtime_*"))
    
    if not runtime_dirs:
        print("  ⚠ No pyarmor_runtime found — obfuscated files may not work!")
        return
    
    # The runtime should be at the root level of dist/ for all imports to find it
    root_runtime = None
    for rd in runtime_dirs:
        if rd.parent == DIST_DIR:
            root_runtime = rd
            break
    
    if root_runtime:
        print(f"  ✓ PyArmor runtime at: {root_runtime.name}/")
    else:
        # Copy the first found runtime to root
        src_runtime = runtime_dirs[0]
        dest_runtime = DIST_DIR / src_runtime.name
        if not dest_runtime.exists():
            shutil.copytree(src_runtime, dest_runtime)
        root_runtime = dest_runtime
        print(f"  ✓ Copied runtime to root: {root_runtime.name}/")
    
    # Ensure every subdirectory that has .py files also has access to runtime
    # PyArmor 8+ handles this via the runtime package being importable
    # We may need to copy it to subdirectories too
    for subdir in DIST_DIR.rglob("*"):
        if subdir.is_dir() and any(subdir.glob("*.py")):
            # Check if any .py file here imports pyarmor_runtime
            sub_runtime = list(subdir.glob("pyarmor_runtime_*"))
            if not sub_runtime and subdir != DIST_DIR:
                # Check if it was already created by pyarmor in this subdir
                pass  # PyArmor usually handles runtime placement correctly


def verify_obfuscation():
    """Verify that obfuscated files are actually obfuscated."""
    print(f"\n{'─'*60}")
    print(f"  Verifying obfuscation")
    print(f"{'─'*60}")
    
    obfuscated = 0
    plain = 0
    
    for py_file in DIST_DIR.rglob("*.py"):
        if "pyarmor_runtime" in str(py_file):
            continue
        
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        
        # Obfuscated files contain pyarmor markers
        if "pyarmor" in content.lower() or "__pyarmor__" in content:
            obfuscated += 1
        else:
            plain += 1
            rel = py_file.relative_to(DIST_DIR)
            # Only warn about files that were supposed to be obfuscated
            print(f"  ⚠ PLAIN: {rel}")
    
    print(f"\n  Obfuscated: {obfuscated} files")
    print(f"  Plain:      {plain} files")
    
    if obfuscated > 0:
        print(f"  ✓ Obfuscation verified!")
    else:
        print(f"  ✗ No obfuscated files found — something went wrong")
    
    return obfuscated, plain


def test_import():
    """Try to import a simple obfuscated module to verify it works."""
    print(f"\n{'─'*60}")
    print(f"  Testing obfuscated module import")
    print(f"{'─'*60}")
    
    # Try to import db/__init__.py or automation/__init__.py from dist
    test_script = f'''
import sys
sys.path.insert(0, r"{DIST_DIR}")

try:
    # Try importing the db package
    import db
    print("OK: db package imported successfully")
except Exception as e:
    print(f"WARN: db import failed: {{e}}")

try:
    # Try importing automation package  
    import automation
    print("OK: automation package imported successfully")
except Exception as e:
    print(f"WARN: automation import failed: {{e}}")

# Check that pyarmor_runtime exists
import importlib
runtime_found = False
for p in sys.path:
    import os
    for item in os.listdir(p) if os.path.isdir(p) else []:
        if item.startswith("pyarmor_runtime"):
            runtime_found = True
            break
    if runtime_found:
        break

if runtime_found:
    print("OK: pyarmor_runtime package found")
else:
    print("WARN: pyarmor_runtime not found in path")

print("DONE")
'''
    
    result = subprocess.run(
        ["python", "-c", test_script],
        capture_output=True, text=True,
        cwd=str(DIST_DIR),
    )
    
    output = result.stdout.strip()
    if output:
        for line in output.split("\n"):
            print(f"  {line}")
    
    if result.stderr:
        for line in result.stderr.strip().split("\n")[:5]:
            print(f"  ERR: {line}")
    
    return "DONE" in output


# ═══════════════════════════════════════════════════════════════════════
# Main Build Pipeline
# ═══════════════════════════════════════════════════════════════════════

def build(dry_run=False, clean=False, verify=False):
    """Run the full obfuscation build."""
    
    print(f"\n{'═'*60}")
    print(f"  HYDRA PHONE FARM — OBFUSCATION BUILD")
    print(f"  Source:  {FARM_DIR}")
    print(f"  Output:  {DIST_DIR}")
    print(f"  PyArmor: {PYARMOR or 'NOT FOUND'}")
    print(f"{'═'*60}")
    
    start_time = time.time()
    
    # ── Step 0: Clean ──
    if clean or not dry_run:
        if DIST_DIR.exists():
            print(f"\n  Cleaning {DIST_DIR}...")
            if not dry_run:
                shutil.rmtree(DIST_DIR)
        if not dry_run:
            DIST_DIR.mkdir(parents=True, exist_ok=True)
    
    # ── Step 1: Discover files ──
    print(f"\n{'─'*60}")
    print(f"  Step 1: Discovering Python files")
    print(f"{'─'*60}")
    
    py_files = discover_python_files()
    print(f"  Found {len(py_files)} Python files to obfuscate")
    
    # Show by directory
    dir_counts = {}
    for f in py_files:
        d = str(f.parent) if str(f.parent) != "." else "(root)"
        dir_counts[d] = dir_counts.get(d, 0) + 1
    for d, count in sorted(dir_counts.items()):
        print(f"    {d}: {count} files")
    
    if dry_run:
        print(f"\n  [DRY RUN] Would obfuscate these files:")
        for f in py_files:
            print(f"    {f}")
    
    # ── Step 2: Obfuscate ──
    print(f"\n{'─'*60}")
    print(f"  Step 2: Running PyArmor obfuscation")
    print(f"{'─'*60}")
    
    stats = run_pyarmor(py_files, dry_run=dry_run)
    
    # ── Step 3: Copy runtime ──
    if not dry_run:
        print(f"\n{'─'*60}")
        print(f"  Step 3: Checking PyArmor runtime")
        print(f"{'─'*60}")
        copy_pyarmor_runtime()
    
    # ── Step 4: Copy assets ──
    print(f"\n{'─'*60}")
    print(f"  Step 4: Copying non-Python assets")
    print(f"{'─'*60}")
    copy_assets(dry_run=dry_run)
    
    # ── Step 5: Verify ──
    if verify and not dry_run:
        obf_count, plain_count = verify_obfuscation()
        test_import()
    
    # ── Summary ──
    elapsed = time.time() - start_time
    
    print(f"\n{'═'*60}")
    print(f"  BUILD COMPLETE")
    print(f"{'═'*60}")
    print(f"  Time:        {elapsed:.1f}s")
    print(f"  Obfuscated:  {stats['success']} files")
    print(f"  Failed:      {stats['failed']} files (copied plain)")
    
    if stats.get("failed_files"):
        print(f"\n  Files that couldn't be obfuscated (free version limits):")
        for f in stats["failed_files"]:
            print(f"    - {f}")
    
    if not dry_run:
        # Count output
        total_files = sum(1 for _ in DIST_DIR.rglob("*") if _.is_file())
        total_size = sum(f.stat().st_size for f in DIST_DIR.rglob("*") if f.is_file())
        print(f"\n  Output: {DIST_DIR}")
        print(f"  Total files: {total_files}")
        print(f"  Total size:  {total_size / 1024 / 1024:.1f} MB")
    
    print(f"{'═'*60}\n")
    
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build obfuscated Hydra Phone Farm distribution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python build_obfuscated.py                # Full build
    python build_obfuscated.py --dry-run      # Preview what will happen
    python build_obfuscated.py --verify       # Build + verify
    python build_obfuscated.py --clean        # Clean rebuild
        """,
    )
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be done without doing it")
    parser.add_argument("--clean", action="store_true",
                       help="Clean dist/ before building")
    parser.add_argument("--verify", action="store_true",
                       help="Verify obfuscation after build")
    
    args = parser.parse_args()
    
    stats = build(
        dry_run=args.dry_run,
        clean=args.clean,
        verify=args.verify,
    )
    
    # Exit with error if everything failed
    if stats["success"] == 0 and stats["failed"] > 0:
        sys.exit(1)
