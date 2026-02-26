#!/usr/bin/env python3
"""
Hydra — Deploy to Release Branch
==================================
Pushes the obfuscated dist/ to a 'release' branch on GitHub.
Uses a temporary clone so the main working directory is never touched.

Usage:
    python deploy_release.py              # Full build + deploy
    python deploy_release.py --skip-build # Deploy existing dist/ without rebuilding

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
    out = result.stdout.strip()
    err = result.stderr.strip()
    if out:
        for line in out.split('\n')[:15]:
            print(f"    {line}")
    if result.returncode != 0 and check and err:
        for line in err.split('\n')[:5]:
            print(f"    ERR: {line}")
    return result


def get_remote_url():
    r = run("git remote get-url origin", check=False)
    return r.stdout.strip()


def get_master_info():
    r = run("git log -1 --format=%H%n%s", check=False)
    lines = r.stdout.strip().split('\n')
    return (lines[0][:8], lines[1]) if len(lines) >= 2 else ("unknown", "unknown")


def build_dist():
    print(f"\n{'='*60}")
    print(f"  STEP 1: Building obfuscated distribution")
    print(f"{'='*60}\n")
    result = subprocess.run(
        [sys.executable, str(FARM_DIR / "build_obfuscated.py"), "--clean", "--verify"],
        cwd=str(FARM_DIR),
    )
    if not DIST_DIR.exists() or not any(DIST_DIR.rglob("*.py")):
        print("  ERROR: dist/ is empty after build!")
        return False
    fc = sum(1 for _ in DIST_DIR.rglob("*") if _.is_file())
    sz = sum(f.stat().st_size for f in DIST_DIR.rglob("*") if f.is_file())
    print(f"\n  Build OK: {fc} files, {sz / 1024 / 1024:.1f} MB")
    return True


def deploy_to_release():
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

    # Use temp directory outside the repo to avoid any contamination
    tmp_base = Path(os.environ.get('TEMP', FARM_DIR.parent)) / "hydra_deploy_tmp"
    if tmp_base.exists():
        shutil.rmtree(tmp_base, ignore_errors=True)
        time.sleep(1)
    tmp_base.mkdir(exist_ok=True)
    repo_dir = tmp_base / "repo"

    try:
        # Check if release branch exists on remote
        r = run(f"git ls-remote --heads origin {RELEASE_BRANCH}", check=False)
        release_exists = RELEASE_BRANCH in r.stdout

        if release_exists:
            print(f"\n  Cloning existing '{RELEASE_BRANCH}' branch (shallow)...")
            r = run(f'git clone -b {RELEASE_BRANCH} --depth 1 "{remote_url}" repo', cwd=tmp_base)
            if r.returncode != 0:
                print("  ERROR: Clone failed")
                return False
        else:
            print(f"\n  No release branch yet. Initializing fresh repo...")
            repo_dir.mkdir()
            run("git init", cwd=repo_dir)
            run(f'git remote add origin "{remote_url}"', cwd=repo_dir)
            # Create orphan branch
            run(f"git checkout --orphan {RELEASE_BRANCH}", cwd=repo_dir)

        # Verify we're on the right branch
        r = run("git branch --show-current", cwd=repo_dir, check=False)
        current = r.stdout.strip()
        print(f"  Current branch in temp repo: {current}")
        if current != RELEASE_BRANCH:
            print(f"  WARNING: Expected {RELEASE_BRANCH}, got {current}. Switching...")
            run(f"git checkout -b {RELEASE_BRANCH}", cwd=repo_dir, check=False)

        # Clean everything except .git
        print(f"  Cleaning temp repo...")
        for item in repo_dir.iterdir():
            if item.name == '.git':
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        # Copy dist/ contents to repo root
        print(f"  Copying dist/ contents...")
        for item in DIST_DIR.iterdir():
            dest = repo_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        # Copy launcher exe if exists
        for extra in ["hydra.ico", "Hydra Dashboard.exe"]:
            src = FARM_DIR / extra
            if src.exists() and not (repo_dir / extra).exists():
                shutil.copy2(src, repo_dir / extra)

        # README
        (repo_dir / "README.md").write_text(
            f"# Hydra Dashboard\n\n"
            f"## Quick Start\n"
            f"1. Install Python 3.12+\n"
            f"2. Run `python launcher.py` or double-click `Hydra Dashboard.exe`\n"
            f"3. Dashboard opens at http://localhost:5055\n\n"
            f"## Update\n```\ngit pull\n```\n\n"
            f"Built from: master@{commit_hash}\n",
            encoding='utf-8'
        )

        # .gitignore
        (repo_dir / ".gitignore").write_text(
            "__pycache__/\n*.pyc\nlogs/\n*.log\nscreenshots/\nxml_dumps/\n",
            encoding='utf-8'
        )

        # Stage all
        run("git add -A", cwd=repo_dir)

        # Check for changes
        r = run("git diff --cached --stat", cwd=repo_dir, check=False)
        if not r.stdout.strip():
            print(f"\n  No changes to deploy.")
            return True

        # Commit
        print(f"\n  Committing...")
        run(f'git commit -m "{release_msg}"', cwd=repo_dir)

        # Push
        print(f"  Pushing to origin/{RELEASE_BRANCH}...")
        r = run(f"git push origin {RELEASE_BRANCH}", cwd=repo_dir, check=False)
        if r.returncode != 0:
            r = run(f"git push --set-upstream origin {RELEASE_BRANCH}", cwd=repo_dir, check=False)
            if r.returncode != 0:
                # Force push for orphan branch first push
                run(f"git push -f origin {RELEASE_BRANCH}", cwd=repo_dir)

        print(f"\n  Done! Pushed to origin/{RELEASE_BRANCH}")
        return True

    finally:
        print(f"  Cleaning up temp files...")
        try:
            shutil.rmtree(tmp_base, ignore_errors=True)
        except Exception:
            pass


def main():
    print(f"\n{'='*60}")
    print(f"  HYDRA -- DEPLOY TO RELEASE BRANCH")
    print(f"{'='*60}")

    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()

    start = time.time()

    if not args.skip_build:
        if not build_dist():
            sys.exit(1)
    else:
        if not DIST_DIR.exists():
            print("  ERROR: dist/ not found!")
            sys.exit(1)
        print(f"\n  Skipping build, using existing dist/")

    if not deploy_to_release():
        print("\n  Deploy failed")
        sys.exit(1)

    elapsed = time.time() - start
    print(f"\n{'='*60}")
    print(f"  ALL DONE ({elapsed:.0f}s)")
    print(f"{'='*60}")
    print(f"\n  Henry: git clone -b release https://github.com/adobortnik/Hydra.git")
    print(f"  Update: cd Hydra && git pull\n")


if __name__ == "__main__":
    main()
