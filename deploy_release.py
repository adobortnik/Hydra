#!/usr/bin/env python3
"""
Hydra — Deploy to Release Branch
==================================
Pushes the obfuscated dist/ to a 'release' branch on GitHub.
Uses a temporary clone so the main working directory is never touched.

Usage:
    python deploy_release.py              # Full build + deploy
    python deploy_release.py --skip-build # Deploy existing dist/ without rebuilding
    python deploy_release.py --dry-run    # Show what would happen

Henry's PC setup (one-time):
    git clone -b release https://github.com/adobortnik/Hydra.git

Henry's PC update:
    cd Hydra && git pull
"""

import os
import sys
import subprocess
import shutil
import argparse
import time
import tempfile
from pathlib import Path

# Force UTF-8 output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

FARM_DIR = Path(__file__).parent.resolve()
DIST_DIR = FARM_DIR / "dist"
RELEASE_BRANCH = "release"


def run(cmd, cwd=None, check=True):
    """Run a command and return output."""
    print(f"  $ {cmd}")
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        cwd=str(cwd or FARM_DIR), encoding='utf-8', errors='replace'
    )
    if result.stdout.strip():
        for line in result.stdout.strip().split('\n')[:15]:
            print(f"    {line}")
    if result.returncode != 0 and check:
        if result.stderr.strip():
            for line in result.stderr.strip().split('\n')[:5]:
                print(f"    ERR: {line}")
    return result


def get_remote_url():
    """Get the git remote URL."""
    r = run("git remote get-url origin", check=False)
    return r.stdout.strip()


def get_master_info():
    """Get current master commit hash + message."""
    r = run("git log -1 --format=%H%n%s", check=False)
    lines = r.stdout.strip().split('\n')
    if len(lines) >= 2:
        return lines[0][:8], lines[1]
    return "unknown", "unknown"


def build_dist():
    """Run the obfuscation build."""
    print(f"\n{'='*60}")
    print(f"  STEP 1: Building obfuscated distribution")
    print(f"{'='*60}\n")

    build_script = FARM_DIR / "build_obfuscated.py"
    if not build_script.exists():
        print("  ERROR: build_obfuscated.py not found!")
        return False

    result = subprocess.run(
        [sys.executable, str(build_script), "--clean", "--verify"],
        cwd=str(FARM_DIR),
    )

    if not DIST_DIR.exists() or not any(DIST_DIR.rglob("*.py")):
        print("  ERROR: dist/ is empty after build!")
        return False

    file_count = sum(1 for _ in DIST_DIR.rglob("*") if _.is_file())
    total_size = sum(f.stat().st_size for f in DIST_DIR.rglob("*") if f.is_file())
    print(f"\n  Build OK: {file_count} files, {total_size / 1024 / 1024:.1f} MB")
    return True


def deploy_to_release(dry_run=False):
    """Deploy dist/ to release branch using a temp clone."""
    print(f"\n{'='*60}")
    print(f"  STEP 2: Deploying to '{RELEASE_BRANCH}' branch")
    print(f"{'='*60}\n")

    remote_url = get_remote_url()
    if not remote_url:
        print("  ERROR: Could not get remote URL")
        return False
    print(f"  Remote: {remote_url}")

    commit_hash, commit_msg = get_master_info()
    release_msg = f"Release from master@{commit_hash}: {commit_msg}"
    print(f"  Message: {release_msg}")

    if dry_run:
        print(f"\n  [DRY RUN] Would deploy dist/ to '{RELEASE_BRANCH}' branch")
        return True

    # Use a temp directory for clean operations
    tmp_base = FARM_DIR / ".deploy_tmp"
    if tmp_base.exists():
        shutil.rmtree(tmp_base, ignore_errors=True)
        time.sleep(1)  # Windows needs a moment after rmtree
    tmp_base.mkdir(exist_ok=True)

    try:
        # Check if release branch exists on remote
        r = run(f"git ls-remote --heads origin {RELEASE_BRANCH}", check=False)
        release_exists = RELEASE_BRANCH in r.stdout

        if release_exists:
            # Clone only the release branch (shallow for speed)
            print(f"\n  Cloning existing '{RELEASE_BRANCH}' branch...")
            run(f'git clone -b {RELEASE_BRANCH} --depth 1 "{remote_url}" deploy_repo',
                cwd=tmp_base)
        else:
            # Clone master shallow, then create orphan release
            print(f"\n  Creating new '{RELEASE_BRANCH}' branch...")
            run(f'git clone --depth 1 "{remote_url}" deploy_repo', cwd=tmp_base)
            run(f"git checkout --orphan {RELEASE_BRANCH}", cwd=tmp_base / "deploy_repo")
            run("git rm -rf .", cwd=tmp_base / "deploy_repo", check=False)

        repo_dir = tmp_base / "deploy_repo"

        # Clean everything except .git
        print(f"  Cleaning repo directory...")
        for item in repo_dir.iterdir():
            if item.name == '.git':
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        # Copy dist/ contents into the repo root
        print(f"  Copying dist/ contents...")
        copied = 0
        for item in DIST_DIR.iterdir():
            dest = repo_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
            copied += 1

        # Copy launcher exe and icon if they exist
        for extra in ["hydra.ico", "Hydra Dashboard.exe"]:
            src = DIST_DIR / extra
            if not src.exists():
                src = FARM_DIR / extra
            if src.exists():
                dest = repo_dir / extra
                if not dest.exists():
                    shutil.copy2(src, dest)

        # Create README
        readme = repo_dir / "README.md"
        readme.write_text(
            "# Hydra Dashboard\n\n"
            "## Quick Start\n\n"
            "1. Install Python 3.12+ from https://www.python.org/downloads/\n"
            "2. Double-click `Hydra Dashboard.exe` (or run `python launcher.py`)\n"
            "3. Dashboard opens in your browser at http://localhost:5055\n\n"
            "## Update\n\n"
            "```\ngit pull\n```\n\n"
            f"Built from: master@{commit_hash}\n",
            encoding='utf-8'
        )

        # Create .gitignore for release
        gitignore = repo_dir / ".gitignore"
        gitignore.write_text(
            "__pycache__/\n*.pyc\nlogs/\n*.log\nscreenshots/\nxml_dumps/\n",
            encoding='utf-8'
        )

        # Stage + commit + push
        print(f"\n  Staging files...")
        run("git add -A", cwd=repo_dir)

        r = run("git diff --cached --stat", cwd=repo_dir, check=False)
        if not r.stdout.strip():
            print(f"\n  No changes to deploy.")
            return True

        print(f"  Committing...")
        run(f'git commit -m "{release_msg}"', cwd=repo_dir)

        print(f"  Pushing to origin/{RELEASE_BRANCH}...")
        r = run(f"git push origin {RELEASE_BRANCH}", cwd=repo_dir, check=False)
        if r.returncode != 0:
            run(f"git push --set-upstream origin {RELEASE_BRANCH}", cwd=repo_dir)

        print(f"\n  Done! Pushed to origin/{RELEASE_BRANCH}")
        return True

    finally:
        # Clean up temp directory
        print(f"  Cleaning up temp files...")
        try:
            shutil.rmtree(tmp_base, ignore_errors=True)
        except:
            pass


def main():
    print(f"\n{'='*60}")
    print(f"  HYDRA -- DEPLOY TO RELEASE BRANCH")
    print(f"{'='*60}")

    parser = argparse.ArgumentParser(description="Build and deploy obfuscated Hydra to release branch")
    parser.add_argument("--skip-build", action="store_true", help="Skip build, deploy existing dist/")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen")
    args = parser.parse_args()

    start = time.time()

    if not args.skip_build:
        if not build_dist():
            print("\n  Build failed, aborting deploy")
            sys.exit(1)
    else:
        if not DIST_DIR.exists():
            print(f"\n  ERROR: dist/ not found! Run without --skip-build first.")
            sys.exit(1)
        print(f"\n  Skipping build, using existing dist/")

    if not deploy_to_release(dry_run=args.dry_run):
        print("\n  Deploy failed")
        sys.exit(1)

    elapsed = time.time() - start
    print(f"\n{'='*60}")
    print(f"  ALL DONE ({elapsed:.0f}s)")
    print(f"{'='*60}")
    print(f"\n  Henry's first-time setup:")
    print(f"    git clone -b release https://github.com/adobortnik/Hydra.git")
    print(f"\n  Henry's update:")
    print(f"    cd Hydra && git pull")
    print()


if __name__ == "__main__":
    main()
