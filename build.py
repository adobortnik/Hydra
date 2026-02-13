"""
Hydra Build Script
===================
Creates a protected distribution using PyArmor (encryption) + PyInstaller (packaging).

PyArmor encrypts Python source → unreadable bytecode
PyInstaller bundles everything → single distributable folder
License system → controls who can run it

Usage:
    python build.py                 # Full build (encrypt + package)
    python build.py --encrypt-only  # Just encrypt source files
    python build.py --package-only  # Just package (assumes already encrypted)
    python build.py --test          # Quick test: encrypt + run

Output: dist/hydra/
    hydra.exe              - Main dashboard server
    _internal/             - Encrypted Python modules + dependencies
    templates/             - HTML templates (shipped as-is)
    static/                - CSS/JS/images
    license.key            - User puts their key here
    README.txt             - Quick start guide
"""

import os
import sys
import shutil
import subprocess
import time
from pathlib import Path

FARM_DIR = Path(__file__).parent
DIST_DIR = FARM_DIR / "dist"
BUILD_DIR = FARM_DIR / "build"
ENCRYPTED_DIR = FARM_DIR / "build" / "encrypted"
VENV_PYTHON = FARM_DIR / "venv" / "Scripts" / "python.exe"
VENV_SCRIPTS = FARM_DIR / "venv" / "Scripts"

# ── Core source files to encrypt ──
# These contain business logic that must be protected
ENCRYPT_MODULES = [
    # Dashboard backend
    "dashboard/simple_app.py",
    "dashboard/profile_automation_routes.py",
    "dashboard/content_schedule_routes.py",
    "dashboard/job_orders_v2_routes.py",
    "dashboard/bot_launcher_routes.py",
    "dashboard/bot_settings_routes.py",
    "dashboard/bot_manager_routes.py",
    "dashboard/deploy_routes.py",
    "dashboard/login_automation_routes.py",
    "dashboard/login_automation_v2_routes.py",
    "dashboard/device_management_routes.py",
    "dashboard/device_manager_routes.py",
    "dashboard/farm_stats_routes.py",
    "dashboard/account_health_routes.py",
    "dashboard/comment_routes.py",
    "dashboard/follow_list_routes.py",
    "dashboard/import_v2_routes.py",
    "dashboard/proxy_routes.py",
    "dashboard/settings_routes.py",
    "dashboard/caption_templates_routes.py",
    "dashboard/bulk_import_routes.py",
    "dashboard/phone_farm_db.py",
    "dashboard/adb_helper.py",
    "dashboard/run_dashboard.py",
    "dashboard/media_folder_sync.py",
    # Automation engine
    "automation/bot_engine.py",
    "automation/ig_controller.py",
    "automation/instagram_actions.py",
    "automation/device_connection.py",
    "automation/scheduler.py",
    "automation/source_manager.py",
    "automation/tag_dedup.py",
    "automation/bot_logger.py",
    "automation/login.py",
    "automation/profile.py",
    "automation/api.py",
    "automation/ws_server.py",
    "automation/__init__.py",
    # Actions
    "automation/actions/comment.py",
    "automation/actions/dm.py",
    "automation/actions/engage.py",
    "automation/actions/follow.py",
    "automation/actions/follow_from_list.py",
    "automation/actions/helpers.py",
    "automation/actions/job_executor.py",
    "automation/actions/like.py",
    "automation/actions/post_content.py",
    "automation/actions/reels.py",
    "automation/actions/report.py",
    "automation/actions/save_post.py",
    "automation/actions/scrape.py",
    "automation/actions/share_to_story.py",
    "automation/actions/unfollow.py",
    "automation/actions/__init__.py",
    # DB layer
    "db/models.py",
    "db/proxy_tables.py",
    "db/seed.py",
    "db/__init__.py",
    # Root scripts
    "run_device.py",
    "launch_farm.py",
    "stop_farm.py",
    "watchdog.py",
    "init_db.py",
    "license_manager.py",
    # uiAutomator
    "dashboard/uiAutomator/automated_profile_manager.py",
    "dashboard/uiAutomator/parallel_profile_processor.py",
    "dashboard/uiAutomator/ai_profile_generator.py",
    "dashboard/uiAutomator/profile_automation_db.py",
]

# ── Assets to copy as-is (NOT encrypted) ──
COPY_DIRS = [
    ("dashboard/templates", "templates"),
    ("dashboard/static", "static"),
    ("dashboard/uiAutomator/profile_pictures", "profile_pictures"),
]

COPY_FILES = [
    ("dashboard/auth_config.json", "auth_config.json"),
    ("launch_farm.ps1", "launch_farm.ps1"),
    ("stop_farm.ps1", "stop_farm.ps1"),
]

CREATE_DIRS = ["media_library", "logs", "db"]


def clean():
    """Clean build artifacts."""
    for d in [BUILD_DIR, DIST_DIR / "hydra"]:
        if d.exists():
            print(f"  Cleaning {d}...")
            shutil.rmtree(d)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    ENCRYPTED_DIR.mkdir(parents=True, exist_ok=True)


def encrypt_sources():
    """
    Encrypt Python source files with PyArmor.
    Creates encrypted copies in build/encrypted/ maintaining directory structure.
    """
    print(f"\n{'='*60}")
    print(f"  STEP 1: Encrypting source files with PyArmor")
    print(f"{'='*60}")

    # Copy source tree to build/encrypted
    if ENCRYPTED_DIR.exists():
        shutil.rmtree(ENCRYPTED_DIR)

    # Copy ALL source maintaining structure
    for module_path in ENCRYPT_MODULES:
        src = FARM_DIR / module_path
        if not src.exists():
            print(f"  SKIP: {module_path} (not found)")
            continue

        dest = ENCRYPTED_DIR / module_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    # Run PyArmor on the encrypted directory
    pyarmor = VENV_SCRIPTS / "pyarmor.exe"

    # Encrypt all .py files in the encrypted directory
    cmd = [
        str(pyarmor), "gen",
        "--output", str(ENCRYPTED_DIR),
        "--recursive",
        str(ENCRYPTED_DIR),
    ]

    print(f"  Running: {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=str(FARM_DIR), capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  PyArmor stderr: {result.stderr}")
        print(f"  PyArmor stdout: {result.stdout}")

        # Fallback: try encrypting file by file
        print(f"\n  Trying file-by-file encryption...")
        encrypted_count = 0
        for module_path in ENCRYPT_MODULES:
            src = FARM_DIR / module_path
            if not src.exists():
                continue

            dest_dir = ENCRYPTED_DIR / Path(module_path).parent
            dest_dir.mkdir(parents=True, exist_ok=True)

            cmd = [
                str(pyarmor), "gen",
                "--output", str(dest_dir),
                str(src),
            ]

            r = subprocess.run(cmd, cwd=str(FARM_DIR), capture_output=True, text=True)
            if r.returncode == 0:
                encrypted_count += 1
            else:
                # Just copy unencrypted as fallback
                shutil.copy2(src, ENCRYPTED_DIR / module_path)
                print(f"  WARN: Could not encrypt {module_path}, copied plain")

        print(f"  Encrypted {encrypted_count}/{len(ENCRYPT_MODULES)} files")
    else:
        print(f"  PyArmor encryption complete")

    return True


def package():
    """
    Package with PyInstaller into a distributable folder.
    """
    print(f"\n{'='*60}")
    print(f"  STEP 2: Packaging with PyInstaller")
    print(f"{'='*60}")

    # Create PyInstaller spec dynamically
    entry_point = ENCRYPTED_DIR / "dashboard" / "simple_app.py"
    if not entry_point.exists():
        entry_point = FARM_DIR / "dashboard" / "simple_app.py"
        print(f"  Using original entry point (encryption may have failed)")

    pyinstaller = VENV_SCRIPTS / "pyinstaller.exe"

    cmd = [
        str(pyinstaller),
        str(entry_point),
        "--name", "hydra",
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR / "pyinstaller"),
        "--specpath", str(BUILD_DIR),
        "--noconfirm",
        # Add data directories
        f"--add-data={FARM_DIR / 'dashboard' / 'templates'};templates",
        f"--add-data={FARM_DIR / 'dashboard' / 'static'};static",
        # Include encrypted modules
        f"--paths={str(ENCRYPTED_DIR)}",
        f"--paths={str(ENCRYPTED_DIR / 'dashboard')}",
        f"--paths={str(ENCRYPTED_DIR / 'automation')}",
        f"--paths={str(FARM_DIR)}",
        f"--paths={str(FARM_DIR / 'dashboard')}",
        # Hidden imports (Flask + our modules)
        "--hidden-import=flask",
        "--hidden-import=werkzeug",
        "--hidden-import=jinja2",
        "--hidden-import=sqlite3",
        "--hidden-import=automation",
        "--hidden-import=automation.bot_engine",
        "--hidden-import=automation.ig_controller",
        "--hidden-import=db",
        "--hidden-import=db.models",
        # Console mode (shows output)
        "--console",
    ]

    print(f"  Running PyInstaller...")
    result = subprocess.run(cmd, cwd=str(FARM_DIR))

    if result.returncode != 0:
        print(f"  PyInstaller FAILED")
        return False

    # Copy additional assets
    hydra_dist = DIST_DIR / "hydra"

    for src_rel, dest_name in COPY_DIRS:
        src = FARM_DIR / src_rel
        dest = hydra_dist / dest_name
        if src.exists():
            shutil.copytree(src, dest, dirs_exist_ok=True,
                          ignore=shutil.ignore_patterns("*.pyc", "__pycache__"))
            print(f"  Copied: {src_rel} -> {dest_name}/")

    for src_rel, dest_name in COPY_FILES:
        src = FARM_DIR / src_rel
        dest = hydra_dist / dest_name
        if src.exists():
            shutil.copy2(src, dest)
            print(f"  Copied: {src_rel}")

    for d in CREATE_DIRS:
        (hydra_dist / d).mkdir(parents=True, exist_ok=True)

    # License placeholder
    (hydra_dist / "license.key").write_text(
        "# Paste your Hydra license key here\n"
        "# Contact your administrator for a key\n"
    )

    # README
    (hydra_dist / "README.txt").write_text(
        "HYDRA - Instagram Automation Platform\n"
        "=" * 40 + "\n\n"
        "Quick Start:\n"
        "1. Paste your license key into license.key\n"
        "2. Run hydra.exe to start the dashboard\n"
        "3. Open http://localhost:5055 in your browser\n"
        "4. Default login: admin / hydra2026\n\n"
        "Need help? Contact your administrator.\n"
    )

    print(f"  Package complete: {hydra_dist}")
    return True


def show_summary():
    """Show build summary."""
    hydra_dist = DIST_DIR / "hydra"
    if not hydra_dist.exists():
        print("  No build output found!")
        return

    total_size = sum(f.stat().st_size for f in hydra_dist.rglob("*") if f.is_file())
    file_count = sum(1 for _ in hydra_dist.rglob("*") if _.is_file())
    py_files = sum(1 for f in hydra_dist.rglob("*.py") if f.is_file())

    print(f"\n{'='*60}")
    print(f"  BUILD SUMMARY")
    print(f"{'='*60}")
    print(f"  Output:      {hydra_dist}")
    print(f"  Total size:  {total_size / 1024 / 1024:.1f} MB")
    print(f"  Files:       {file_count}")
    print(f"  .py files:   {py_files} (should be 0 if fully encrypted)")
    print(f"{'='*60}\n")


def build(encrypt=True, package_=True):
    """Run the full build pipeline."""
    print(f"\n{'#'*60}")
    print(f"  HYDRA BUILD PIPELINE")
    print(f"  Mode: {'encrypt' if encrypt else ''} {'+ package' if package_ else ''}")
    print(f"{'#'*60}")

    start = time.time()
    clean()

    if encrypt:
        encrypt_sources()

    if package_:
        package()

    show_summary()

    elapsed = time.time() - start
    print(f"  Total build time: {elapsed:.0f}s ({elapsed/60:.1f}m)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build Hydra distribution")
    parser.add_argument("--encrypt-only", action="store_true", help="Only encrypt sources")
    parser.add_argument("--package-only", action="store_true", help="Only package (skip encryption)")
    parser.add_argument("--test", action="store_true", help="Quick test build")

    args = parser.parse_args()

    if args.encrypt_only:
        clean()
        encrypt_sources()
    elif args.package_only:
        package()
        show_summary()
    else:
        build()
