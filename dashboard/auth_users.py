"""auth_users.py — multi-user accounts + permission matrix for the dashboard.

Replaces the old single-user Basic Auth (auth_config.json = {username,
password_hash}) with a list of users, each carrying a set of PERMISSIONS. A
superadmin (permissions == ["*"]) sees everything and manages other users; a
restricted user (e.g. a colleague who only schedules content) sees only the nav
sections their permissions allow.

Back-compat: an old-format auth_config.json is migrated in place on first load —
the existing admin becomes a superadmin, so nobody gets locked out.

Enforcement is PAGE-LEVEL: each navigable page route maps to a permission; a user
without it can't open that page. APIs/static/shared endpoints stay open (the
threat model is a trusted colleague we want to keep out of irrelevant sections,
not a hostile actor — this avoids brittle per-API gating that breaks pages).
"""

import os
import json
import threading

from werkzeug.security import generate_password_hash, check_password_hash

AUTH_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'auth_config.json')

_lock = threading.Lock()

# ── Permission catalog (the matrix columns) ──────────────────────────────────
# (key, human label). "*" is the implicit superadmin wildcard (not listed here).
PERMISSIONS = [
    ('dashboard',  'Dashboard (home)'),
    ('devices',    'Devices'),
    ('accounts',   'Accounts & Health'),
    ('content',    'Content & Scheduling'),
    ('automation', 'Automation'),
    ('operations', 'Operations'),
    ('phone_farm', 'Phone Farm'),
    ('analytics',  'Analytics'),
    ('ai_factory', 'AI Factory'),
    ('settings',   'Settings'),
    ('users',      'User Management'),
]
PERMISSION_KEYS = [k for k, _ in PERMISSIONS]

# Role presets offered in the UI (superadmin = full wildcard).
PRESETS = {
    'superadmin': ['*'],
    'scheduler':  ['dashboard', 'content'],
    'operator':   ['dashboard', 'devices', 'accounts', 'operations',
                   'phone_farm', 'analytics'],
    'custom':     [],
}

# Permissions that only make sense when a build FEATURE is enabled. perm_key ->
# feature flags; the permission is offered only if ANY of them is on. So a client
# build with AI Factory excluded won't show 'ai_factory' as a grantable permission.
_PERM_FEATURES = {'ai_factory': ('ai_executor', 'account_factory')}


def visible_permissions():
    """PERMISSIONS filtered to features enabled in THIS build."""
    try:
        from feature_flags import is_enabled
    except Exception:
        def is_enabled(_name):
            return True
    out = []
    for key, label in PERMISSIONS:
        feats = _PERM_FEATURES.get(key)
        if feats and not any(is_enabled(f) for f in feats):
            continue
        out.append((key, label))
    return out

# ── Page route -> required permission ────────────────────────────────────────
# Longest-prefix match wins. '/' is matched EXACTLY (see path_required_permission).
PAGE_PERMISSIONS = [
    ('/device-manager',        'devices'),
    ('/device-management',     'devices'),
    ('/account-health',        'accounts'),
    ('/account-inventory',     'accounts'),
    ('/accounts',              'accounts'),
    ('/inventory',             'accounts'),
    ('/media-library',         'content'),
    ('/scheduled-posts',       'content'),
    ('/content-schedule',      'content'),
    ('/caption-templates',     'content'),
    ('/comments',              'content'),
    ('/profile-automation',    'automation'),
    ('/login-automation',      'automation'),
    ('/automation-flows',      'automation'),
    ('/job-orders',            'operations'),
    ('/manage_sources',        'operations'),
    ('/bulk_operations',       'operations'),
    ('/deploy',                'phone_farm'),
    ('/login-automation-v2',   'phone_farm'),
    ('/proxy-management',      'phone_farm'),
    ('/sync',                  'phone_farm'),
    ('/farm-stats',            'phone_farm'),
    ('/source-quality',        'phone_farm'),
    ('/account-factory',       'ai_factory'),
    ('/ai-executor',           'ai_factory'),
    ('/analytics',             'analytics'),
    ('/settings',              'settings'),
    ('/users',                 'users'),
]


# ── Load / save / migrate ────────────────────────────────────────────────────
def _default_users():
    pw = os.environ.get('HYDRA_ADMIN_PASSWORD', 'changeme')
    return [{
        'username': os.environ.get('HYDRA_ADMIN_USER', 'admin'),
        'password_hash': generate_password_hash(pw),
        'role': 'superadmin',
        'permissions': ['*'],
    }]


def _migrate(raw):
    """Return a normalized {'users':[...]} dict from any historical shape."""
    if isinstance(raw, dict) and isinstance(raw.get('users'), list) and raw['users']:
        users = []
        for u in raw['users']:
            if not u.get('username'):
                continue
            perms = u.get('permissions')
            if not isinstance(perms, list):
                perms = ['*'] if u.get('role') == 'superadmin' else []
            users.append({
                'username': u['username'],
                'password_hash': u.get('password_hash', ''),
                'role': u.get('role') or ('superadmin' if perms == ['*'] else 'custom'),
                'permissions': perms,
            })
        if users:
            return {'users': users}
    # old single-user format -> one superadmin
    if isinstance(raw, dict) and raw.get('username') and raw.get('password_hash'):
        return {'users': [{
            'username': raw['username'],
            'password_hash': raw['password_hash'],
            'role': 'superadmin',
            'permissions': ['*'],
        }]}
    return {'users': _default_users()}


def load_config():
    with _lock:
        if not os.path.exists(AUTH_CONFIG_PATH):
            cfg = {'users': _default_users()}
            with open(AUTH_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=2)
            return cfg
        with open(AUTH_CONFIG_PATH, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        cfg = _migrate(raw)
        # persist the migration so the file is upgraded once
        if cfg != raw:
            with open(AUTH_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=2)
        return cfg


def save_config(cfg):
    with _lock:
        with open(AUTH_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2)


def list_users():
    return load_config()['users']


def find_user(username):
    if not username:
        return None
    for u in load_config()['users']:
        if u['username'] == username:
            return u
    return None


# ── Auth + permission checks ─────────────────────────────────────────────────
def check_credentials(username, password):
    """Return the user dict on valid login, else None."""
    u = find_user(username)
    if u and u.get('password_hash') and check_password_hash(u['password_hash'], password):
        return u
    return None


def is_superadmin(user):
    return bool(user) and '*' in (user.get('permissions') or [])


def user_can(user, perm):
    if not user:
        return False
    perms = user.get('permissions') or []
    return '*' in perms or perm in perms


def path_required_permission(path):
    """The permission a given request path needs, or None if it's open
    (APIs, static, auth, and unmapped paths are open). '/' (home) -> dashboard."""
    path = path or '/'
    if path == '/':
        return 'dashboard'
    # only gate top-level HTML pages; leave APIs/static open
    if path.startswith('/api/') or path.startswith('/static/'):
        return None
    best = None
    for prefix, perm in PAGE_PERMISSIONS:
        if (path == prefix or path.startswith(prefix + '/') or path.startswith(prefix)) \
                and (best is None or len(prefix) > len(best[0])):
            best = (prefix, perm)
    return best[1] if best else None


# ── User management operations (used by the superadmin UI) ───────────────────
def add_user(username, password, permissions, role='custom'):
    username = (username or '').strip()
    if not username:
        return False, 'username required'
    cfg = load_config()
    if any(u['username'] == username for u in cfg['users']):
        return False, 'username already exists'
    perms = ['*'] if role == 'superadmin' else [p for p in (permissions or [])
                                                if p in PERMISSION_KEYS]
    cfg['users'].append({
        'username': username,
        'password_hash': generate_password_hash(password or 'changeme'),
        'role': role,
        'permissions': perms,
    })
    save_config(cfg)
    return True, 'created'


def update_user(username, permissions=None, role=None, password=None):
    cfg = load_config()
    u = next((x for x in cfg['users'] if x['username'] == username), None)
    if not u:
        return False, 'user not found'
    if role is not None:
        u['role'] = role
        if role == 'superadmin':
            u['permissions'] = ['*']
    if permissions is not None and u.get('role') != 'superadmin':
        u['permissions'] = [p for p in permissions if p in PERMISSION_KEYS]
    if password:
        u['password_hash'] = generate_password_hash(password)
    save_config(cfg)
    return True, 'updated'


def delete_user(username):
    cfg = load_config()
    supers = [u for u in cfg['users'] if is_superadmin(u)]
    target = next((u for u in cfg['users'] if u['username'] == username), None)
    if not target:
        return False, 'user not found'
    # never delete the last superadmin (avoid lockout)
    if is_superadmin(target) and len(supers) <= 1:
        return False, 'cannot delete the last superadmin'
    cfg['users'] = [u for u in cfg['users'] if u['username'] != username]
    save_config(cfg)
    return True, 'deleted'
