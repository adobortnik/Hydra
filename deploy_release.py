#!/usr/bin/env python3
"""
Hydra — Deploy Release
========================
Builds obfuscated dist/ and pushes to the distribution repo on GitHub.
Source (adobortnik/Hydra) stays private; clients get obfuscated code only.

Distribution repo: happymuffinlabel/hydra (private)

Usage:
    python deploy_release.py              # Full build + deploy
    python deploy_release.py --skip-build # Deploy existing dist/ without rebuilding

Client setup (one-time):
    git clone https://<TOKEN>@github.com/happymuffinlabel/hydra.git

Client update:
    cd hydra && git pull
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

# Distribution repo (separate from source)
DIST_REPO = "https://github.com/happymuffinlabel/hydra.git"
DIST_BRANCH = "main"

# Token file (gitignored) — contains GitHub PAT for happymuffinlabel
TOKEN_FILE = FARM_DIR / "data" / "deploy_token.txt"


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


def get_deploy_token():
    """Read GitHub PAT for the distribution repo."""
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding='utf-8').strip()
    # Check environment variable as fallback
    token = os.environ.get('HYDRA_DEPLOY_TOKEN', '')
    if token:
        return token
    return None


def get_auth_url(token=None):
    """Get authenticated URL for the distribution repo."""
    if token:
        # Insert token into URL: https://TOKEN@github.com/...
        return DIST_REPO.replace('https://github.com/', f'https://{token}@github.com/')
    return DIST_REPO


def deploy_to_release():
    print(f"\n{'='*60}")
    print(f"  STEP 2: Deploying to distribution repo")
    print(f"{'='*60}\n")

    token = get_deploy_token()
    if not token:
        print(f"  ERROR: No deploy token found!")
        print(f"  Create {TOKEN_FILE} with your GitHub PAT,")
        print(f"  or set HYDRA_DEPLOY_TOKEN environment variable.")
        return False

    auth_url = get_auth_url(token)
    print(f"  Repo:  {DIST_REPO}")
    print(f"  Token: {'*' * 8}...{token[-4:]}")

    commit_hash, commit_msg = get_master_info()
    release_msg = f"Release from master@{commit_hash}: {commit_msg}"
    print(f"  Message: {release_msg}")

    # Read current version or auto-increment
    version_file = DIST_DIR / "version.json"
    import json
    if version_file.exists():
        ver_data = json.loads(version_file.read_text(encoding='utf-8'))
        version = ver_data.get('version', '1.0.0')
    else:
        version = '1.0.0'

    # Auto-increment patch version
    parts = version.split('.')
    parts[-1] = str(int(parts[-1]) + 1)
    new_version = '.'.join(parts)

    # Write updated version.json into dist/
    import datetime as dt
    ver_data = {
        'version': new_version,
        'build_date': dt.datetime.now().strftime('%Y-%m-%d'),
        'source_commit': commit_hash,
        'changelog': commit_msg
    }
    version_file.write_text(json.dumps(ver_data, indent=2), encoding='utf-8')
    print(f"  Version: {version} → {new_version}")

    # Use temp directory outside the repo
    tmp_base = Path(os.environ.get('TEMP', FARM_DIR.parent)) / "hydra_deploy_tmp"
    if tmp_base.exists():
        shutil.rmtree(tmp_base, ignore_errors=True)
        time.sleep(1)
    tmp_base.mkdir(exist_ok=True)
    repo_dir = tmp_base / "repo"

    try:
        # Clone distribution repo (shallow)
        print(f"\n  Cloning distribution repo (shallow)...")
        r = run(f'git clone --depth 1 "{auth_url}" repo', cwd=tmp_base)
        if r.returncode != 0:
            print("  ERROR: Clone failed — check token and repo URL")
            return False

        # Configure git identity
        run('git config user.email "happymuffinlabel@users.noreply.github.com"', cwd=repo_dir)
        run('git config user.name "happymuffinlabel"', cwd=repo_dir)

        # Clean everything except .git
        print(f"  Cleaning repo...")
        for item in repo_dir.iterdir():
            if item.name == '.git':
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        # Copy dist/ contents
        print(f"  Copying dist/ contents...")
        for item in DIST_DIR.iterdir():
            dest = repo_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        # README
        (repo_dir / "README.md").write_text(
            f"# Hydra Dashboard\n\n"
            f"## Quick Start\n"
            f"1. Install Python 3.12+\n"
            f"2. Double-click **Start Hydra.bat**\n"
            f"3. Dashboard opens at http://localhost:5055\n\n"
            f"## Update\n```\ncd hydra\ngit pull\n```\n"
            f"Then restart the dashboard.\n",
            encoding='utf-8'
        )

        # .gitignore — protect user data from being overwritten
        (repo_dir / ".gitignore").write_text(
            "# User data (preserved across updates)\n"
            "db/phone_farm.db\ndb/phone_farm.db-wal\ndb/phone_farm.db-shm\n"
            "db/backups/\nmedia_library/\nscreenshots/\nlogs/\n"
            "__pycache__/\n*.pyc\n"
            "dashboard/data/global_settings.json\n"
            "dashboard/data/api_keys.json\n",
            encoding='utf-8'
        )

        # Stage
        run("git add -A", cwd=repo_dir)

        # Check for changes
        r = run("git diff --cached --stat", cwd=repo_dir, check=False)
        if not r.stdout.strip():
            print(f"\n  No changes to deploy (dist/ is identical).")
            return True

        # Commit + push
        print(f"\n  Committing v{new_version}...")
        run(f'git commit -m "v{new_version}: {commit_msg}"', cwd=repo_dir)

        print(f"  Pushing...")
        r = run(f"git push origin {DIST_BRANCH}", cwd=repo_dir, check=False)
        if r.returncode != 0:
            run(f"git push -f origin {DIST_BRANCH}", cwd=repo_dir)

        print(f"\n  ✓ Deployed v{new_version} to {DIST_REPO}")
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
    print(f"\n  Client setup: git clone https://<TOKEN>@github.com/happymuffinlabel/hydra.git")
    print(f"  Client update: cd hydra && git pull\n")


if __name__ == "__main__":
    main()
