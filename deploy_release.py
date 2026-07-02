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
import json
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


# ─── Build-time feature gating ────────────────────────────────
BUILD_CONFIG_PATH = FARM_DIR / "build_config.json"

# What gets dropped from dist/ when a feature flag is FALSE.
# Paths are relative to dist/.
FEATURE_FILES = {
    "assistant_chat": [
        "dashboard/chat_routes.py",
        "dashboard/llm_provider.py",
        "dashboard/templates/partials/hydra_chat.html",
        # hydra_tools is shared with mcp_server — only dropped if BOTH off
    ],
    "mcp_server": [
        "hydra_mcp",
    ],
    "ai_executor": [
        "dashboard/ai_executor_routes.py",
        "dashboard/templates/ai_executor.html",
        # automation/ai_executor is shared with account_factory — only dropped
        # if BOTH off (handled below, like hydra_tools)
    ],
    "account_factory": [
        "dashboard/account_factory_routes.py",
        "dashboard/templates/account_factory.html",
    ],
    "cloudphone": [
        "dashboard/cloudphone_routes.py",
        "dashboard/templates/cloudphone.html",
        "dashboard/templates/cloudphone_mirror.html",
        "dashboard/scrcpy-server.jar",
    ],
    # NOTE: mother_dashboard is flag-disabled only (route unregistered + hidden from
    # the home page) — its files are NOT removed (not secret IP). Add here if a future
    # client should have them physically stripped too.
    # Add more here as features are wired up
}


def load_build_config(profile: str = None) -> dict:
    """Resolve the feature set for a named build PROFILE. New format = named
    {profiles:{name:{features}}} + active_profile; legacy = flat {features}.
    Returns {'features':{...}, '_profile': name, '_label': label}."""
    if not BUILD_CONFIG_PATH.exists():
        return {"features": {}, "_profile": None, "_label": "default"}
    try:
        raw = json.loads(BUILD_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  WARN: failed to read build_config.json: {e}")
        return {"features": {}, "_profile": None, "_label": "default"}
    profiles = raw.get("profiles")
    if profiles:
        name = profile or raw.get("active_profile") or next(iter(profiles))
        prof = profiles.get(name)
        if prof is None:
            raise SystemExit(f"  ERROR: build profile '{name}' not found in "
                             f"build_config.json (have: {', '.join(profiles)})")
        return {"features": prof.get("features", {}), "_profile": name,
                "_label": prof.get("_label", name)}
    # legacy flat format
    return {"features": raw.get("features", {}), "_profile": None, "_label": "default"}


def regenerate_feature_flags(cfg: dict):
    """Write dashboard/feature_flags.py with the configured flags BEFORE build,
    so the obfuscator picks up the right values. Emits VALID PYTHON booleans
    (json.dumps would write lowercase true/false → NameError on import → the flag
    gate silently fails open). build_dist() restores the dev copy afterwards."""
    features = (cfg.get("features") or {})
    src = FARM_DIR / "dashboard" / "feature_flags.py"
    entries = "".join(
        f"    {json.dumps(k)}: {bool(features[k])},\n" for k in sorted(features)
    )
    body = (
        '"""feature_flags.py — auto-generated by deploy_release.py for the CLIENT\n'
        'build. Source-of-truth: build_config.json.\n'
        '"""\n\n'
        'FEATURES = {\n' + entries + '}\n\n'
        'def is_enabled(name: str) -> bool:\n'
        '    return bool(FEATURES.get(name, True))\n'
    )
    src.write_text(body, encoding="utf-8")
    print(f"  feature_flags.py written ({len(features)} flags)")


def apply_feature_excludes(cfg: dict):
    """Delete files from dist/ for features turned OFF."""
    features = cfg.get("features") or {}
    dropped = []
    for feat_name, paths in FEATURE_FILES.items():
        if features.get(feat_name, True):
            continue  # feature on — keep files
        for rel in paths:
            target = DIST_DIR / rel
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
                dropped.append(f"{rel}/ (dir)")
            elif target.exists():
                target.unlink()
                dropped.append(rel)
    # hydra_tools is shared — drop it only if BOTH chat AND mcp are off
    if not features.get("assistant_chat", True) and not features.get("mcp_server", True):
        ht = DIST_DIR / "hydra_tools"
        if ht.exists():
            shutil.rmtree(ht, ignore_errors=True)
            dropped.append("hydra_tools/ (dir, shared)")
    # automation/ai_executor is shared by ai_executor + account_factory — drop it
    # only if BOTH are off (account_factory imports from the package).
    if not features.get("ai_executor", True) and not features.get("account_factory", True):
        ae = DIST_DIR / "automation" / "ai_executor"
        if ae.exists():
            shutil.rmtree(ae, ignore_errors=True)
            dropped.append("automation/ai_executor/ (dir, shared)")
    if dropped:
        print(f"  Feature gate dropped {len(dropped)} item(s):")
        for d in dropped:
            print(f"    - {d}")
    else:
        print("  All features enabled — no files dropped.")


def build_dist(profile: str = None):
    print(f"\n{'='*60}")
    print(f"  STEP 1: Building obfuscated distribution")
    print(f"{'='*60}\n")

    # Apply build-time feature config BEFORE obfuscation so flags get baked in.
    cfg = load_build_config(profile)
    print(f"  Build profile: {cfg.get('_profile') or 'default'} "
          f"({cfg.get('_label')})")
    print(f"  features: {json.dumps(cfg.get('features', {}), sort_keys=True)}")

    # Back up the dev source feature_flags.py (all-ON) so the developer keeps the
    # full toolset after a client build; we restore it in `finally`.
    ff_src = FARM_DIR / "dashboard" / "feature_flags.py"
    ff_backup = ff_src.read_text(encoding="utf-8") if ff_src.exists() else None

    try:
        regenerate_feature_flags(cfg)

        result = subprocess.run(
            [sys.executable, str(FARM_DIR / "build_obfuscated.py"), "--clean", "--verify"],
            cwd=str(FARM_DIR),
        )
        if not DIST_DIR.exists() or not any(DIST_DIR.rglob("*.py")):
            print("  ERROR: dist/ is empty after build!")
            return False

        # Drop files for features turned OFF (after obfuscation runs).
        apply_feature_excludes(cfg)
    finally:
        # Restore dev source so master keeps every feature enabled.
        if ff_backup is not None:
            ff_src.write_text(ff_backup, encoding="utf-8")
            print("  restored dev dashboard/feature_flags.py (source stays all-ON)")

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

    # Single source of truth: the VERSION file (also shown in the dashboard footer
    # + login page). Bump it manually when cutting a release — no auto-increment, so
    # the in-app version and the client release version never drift apart again.
    import json
    version_file = DIST_DIR / "version.json"
    vf = FARM_DIR / "VERSION"
    new_version = (vf.read_text(encoding='utf-8').strip() if vf.exists() else '1.2.0')

    import datetime as dt
    ver_data = {
        'version': new_version,
        'build_date': dt.datetime.now().strftime('%Y-%m-%d'),
        'source_commit': commit_hash,
        'changelog': commit_msg
    }
    version_file.write_text(json.dumps(ver_data, indent=2), encoding='utf-8')
    print(f"  Version: {new_version} (from VERSION file)")

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

        # Files/dirs to NEVER ship to client repo
        DEPLOY_SKIP_FILES = {
            'deploy_token.txt', 'deploy_release.py',
            'phone_farm.db', 'phone_farm.db-wal', 'phone_farm.db-shm',
            'login_automation.db', 'profile_automation.db',
            'account_inventory.db', 'media_library.db',
            'scheduled_posts.db', 'devices.db',
            'global_settings.json', 'api_keys.json',
            'jap_api_key.txt', 'auth_config.json',
            # build-time only — must NOT leak to clients
            'build_config.json',          # reveals profiles / feature gating
            'pyarmor-regcode-11432.txt',  # PyArmor LICENSE regcode (also caught by prefix below)
            '.flask_secret',              # dev session secret (client makes its own)
        }
        DEPLOY_SKIP_DIRS = {'backups', '__pycache__',
                            'screenshots', 'logs', 'test_results',
                            'xml_dumps', 'api_keys', '.github', '.claude',
                            # Runtime artifacts added during the session — wake
                            # signals, ig-preview thumbnail cache, reel audit
                            # reports, spoof variant cache. Auto-created at
                            # client side on first use; never ship snapshots.
                            'runtime',
                            # operator media + temp + debug dumps — never ship
                            'media_library',      # operator's own media (~195MB)
                            'tmp',                # scratch / generated temp files
                            'superproxy_dumps',   # debug screenshot dumps
                            'docs'}               # internal dev docs (the /docs PAGE is a template, not this dir)
        # Extensions to skip everywhere (runtime data + internal docs)
        DEPLOY_SKIP_EXTENSIONS = {'.db', '.db-wal', '.db-shm', '.md', '.log'}

        def _should_skip(path):
            """Check if a file/dir should be skipped from deploy."""
            name = path.name
            if name in DEPLOY_SKIP_FILES:
                return True
            if name.startswith('pyarmor-regcode'):   # license regcode, any version
                return True
            if name in DEPLOY_SKIP_DIRS:
                return True
            if path.is_file() and path.suffix.lower() in DEPLOY_SKIP_EXTENSIONS:
                return True
            return False

        def _ignore_func(directory, contents):
            """shutil.copytree ignore function — skip deploy files."""
            skip = set()
            for name in contents:
                full = Path(directory) / name
                if name in DEPLOY_SKIP_FILES or name in DEPLOY_SKIP_DIRS:
                    skip.add(name)
                elif full.is_file() and full.suffix in DEPLOY_SKIP_EXTENSIONS:
                    skip.add(name)
            return skip

        def _is_root_oneoff_script(item):
            """True iff item is a top-level _xyz.py debug/audit/one-off
            script. Matches names starting with single underscore + .py,
            but explicitly EXCLUDES __init__.py and __main__.py (double
            underscore, kept everywhere) and only fires at the project
            root — never recurses. Filtering happens in _copy_filtered
            which iterates only the top-level, so nested `_*.py` files
            (none today) would be unaffected even if they appeared."""
            name = item.name
            if not item.is_file() or not name.endswith('.py'):
                return False
            if name.startswith('__'):       # __init__.py, __main__.py
                return False
            return name.startswith('_')

        def _is_root_junk_media(item):
            """Top-level loose images = debug screenshots (camillo*.jpg,
            follow_test_*.jpg, robin*.png …). Legit images always live in subdirs
            (static/, data/, profile_pictures/), never at the project root, so any
            root-level image is test debris that must not ship."""
            return (item.is_file()
                    and item.suffix.lower() in {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'})

        def _copy_filtered(src_dir, dst_dir):
            for item in src_dir.iterdir():
                if _should_skip(item):
                    continue
                # Top-level only: drop ad-hoc debug/audit/one-off scripts
                # (_check*.py, _test_*.py, _migrate_*.py, _delete_*.py …).
                # These are operator-side helpers; clients don't need them.
                if _is_root_oneoff_script(item):
                    continue
                # Top-level only: drop loose debug screenshots.
                if _is_root_junk_media(item):
                    continue
                dest = dst_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, ignore=_ignore_func)
                else:
                    shutil.copy2(item, dest)

        # Copy dist/ contents (filtered)
        print(f"  Copying dist/ contents...")
        _copy_filtered(DIST_DIR, repo_dir)

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

        # .gitignore — protect ALL user data from being overwritten on git pull
        (repo_dir / ".gitignore").write_text(
            "# ===== User data (NEVER overwrite on git pull) =====\n"
            "\n# Databases\n"
            "*.db\n*.db-wal\n*.db-shm\n"
            "\n# Settings & API keys\n"
            "dashboard/data/global_settings.json\n"
            "dashboard/data/api_keys.json\n"
            "data/api_keys/\n"
            "dashboard/auth_config.json\n"
            "\n# Runtime data\n"
            "media_library/\nscreenshots/\nlogs/\n"
            "db/backups/\ntest_results/\n"
            "automation/xml_dumps/\n"
            "scheduled_posts/\n"
            "runtime/\n"
            "\n# Spoof / IG preview caches (recreated per session)\n"
            "media_library/spoof_sources/\n"
            "media_library/spoof_variants/\n"
            "\n# Bot data\n"
            "dashboard/uiAutomator/bot_data/\n"
            "dashboard/uiAutomator/profile_pictures/\n"
            "\n# Python cache\n"
            "__pycache__/\n*.pyc\n*.pyo\n",
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
    parser.add_argument("--profile", default=None,
                        help="build profile from build_config.json (default: active_profile)")
    args = parser.parse_args()

    start = time.time()

    if not args.skip_build:
        if not build_dist(args.profile):
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
