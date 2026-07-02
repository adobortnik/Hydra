"""
Single source of truth for where spoofing artifacts live on disk.

Both `spoofing_routes.py` (UI uploads + variant cache) and
`content_schedule_routes.py` (batch worker) import from here so the operator
can point the vault at any drive via Settings → "Spoofing Vault" and both
sides honor it without restart.

Layout under the configured vault root:
    <root>/
        spoof_sources/     uploaded source files from the /spoofing UI
        spoof_variants/    generated variants (image + video)

Default root: <phone-farm>/media_library — keeps everything bundled with the
project. Override via global_settings.json key `spoof_vault_root` (set from
the Settings page).
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_VAULT = os.path.join(BASE_DIR, 'media_library')
SETTINGS_FILE = Path(__file__).parent / 'global_settings.json'


def _load_raw_settings():
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def get_vault_root() -> str:
    """Return the configured vault root (or default). Always an absolute path."""
    cfg = _load_raw_settings()
    p = (cfg.get('spoof_vault_root') or '').strip()
    if not p:
        return DEFAULT_VAULT
    return os.path.abspath(p)


def set_vault_root(new_path: str) -> dict:
    """Validate + persist a new vault root. Auto-creates the subdirs.
    Returns {'ok': bool, 'error': str|None, 'root': str}."""
    new_path = (new_path or '').strip()
    if not new_path:
        # blank = revert to default
        cfg = _load_raw_settings()
        cfg.pop('spoof_vault_root', None)
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=4)
        except Exception as e:
            return {'ok': False, 'error': 'failed to save: %s' % e,
                    'root': get_vault_root()}
        return {'ok': True, 'error': None, 'root': get_vault_root()}

    new_path = os.path.abspath(new_path)
    # Try to create the root + subdirs; bail out gracefully on permissions
    try:
        os.makedirs(os.path.join(new_path, 'spoof_sources'), exist_ok=True)
        os.makedirs(os.path.join(new_path, 'spoof_variants'), exist_ok=True)
    except Exception as e:
        return {'ok': False, 'error': 'cannot create dirs: %s' % e,
                'root': get_vault_root()}

    # Write-test: touch + remove a file
    probe = os.path.join(new_path, '.hydra_vault_probe')
    try:
        with open(probe, 'w') as f:
            f.write('ok')
        os.remove(probe)
    except Exception as e:
        return {'ok': False, 'error': 'not writable: %s' % e,
                'root': get_vault_root()}

    cfg = _load_raw_settings()
    cfg['spoof_vault_root'] = new_path
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=4)
    except Exception as e:
        return {'ok': False, 'error': 'failed to save: %s' % e,
                'root': get_vault_root()}
    return {'ok': True, 'error': None, 'root': new_path}


def get_sources_dir() -> str:
    p = os.path.join(get_vault_root(), 'spoof_sources')
    os.makedirs(p, exist_ok=True)
    return p


def get_variants_dir() -> str:
    p = os.path.join(get_vault_root(), 'spoof_variants')
    os.makedirs(p, exist_ok=True)
    return p


def _dir_stats(path: str) -> dict:
    """Walk a dir, return file count + total bytes."""
    count = 0
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    s = os.path.getsize(os.path.join(root, f))
                    count += 1
                    total += s
                except OSError:
                    pass
    except OSError:
        pass
    return {'count': count, 'bytes': total}


def get_vault_stats() -> dict:
    """Used by Settings UI for the 'how full is the vault?' panel."""
    root = get_vault_root()
    sources = _dir_stats(os.path.join(root, 'spoof_sources'))
    variants = _dir_stats(os.path.join(root, 'spoof_variants'))
    drive_free = None
    drive_total = None
    try:
        usage = shutil.disk_usage(root if os.path.isdir(root)
                                  else os.path.splitdrive(root)[0] + os.sep)
        drive_free = usage.free
        drive_total = usage.total
    except OSError:
        pass
    return {
        'root': root,
        'is_default': root == os.path.abspath(DEFAULT_VAULT),
        'default_root': os.path.abspath(DEFAULT_VAULT),
        'sources': sources,
        'variants': variants,
        'total_bytes': sources['bytes'] + variants['bytes'],
        'drive_free_bytes': drive_free,
        'drive_total_bytes': drive_total,
        'exists': os.path.isdir(root),
    }
