"""user_management_routes.py — superadmin API for managing dashboard users and
their permission matrix. All endpoints require the caller to be a superadmin
(checked against flask.g.user set by the main app's auth hook)."""

from flask import Blueprint, jsonify, request, g

import auth_users

user_management_bp = Blueprint('user_management', __name__)


def _require_super():
    """Return None if caller is superadmin, else an error response tuple."""
    if not auth_users.is_superadmin(getattr(g, 'user', None)):
        return jsonify({'error': 'superadmin only'}), 403
    return None


def _public_user(u):
    """User dict without the password hash, for the UI."""
    return {
        'username': u['username'],
        'role': u.get('role', 'custom'),
        'permissions': u.get('permissions', []),
        'is_superadmin': auth_users.is_superadmin(u),
    }


@user_management_bp.route('/api/users', methods=['GET'])
def list_users():
    err = _require_super()
    if err:
        return err
    return jsonify({
        'users': [_public_user(u) for u in auth_users.list_users()],
        'permissions': auth_users.visible_permissions(),
        'presets': auth_users.PRESETS,
        'current': (getattr(g, 'user', {}) or {}).get('username'),
    })


@user_management_bp.route('/api/users', methods=['POST'])
def create_user():
    err = _require_super()
    if err:
        return err
    d = request.get_json() or {}
    ok, msg = auth_users.add_user(
        d.get('username'), d.get('password'),
        d.get('permissions') or [], role=d.get('role') or 'custom')
    return (jsonify({'ok': True}) if ok else (jsonify({'error': msg}), 400))


@user_management_bp.route('/api/users/<username>', methods=['PUT'])
def update_user(username):
    err = _require_super()
    if err:
        return err
    d = request.get_json() or {}
    # Guard: don't let the last superadmin demote themselves out of access.
    if d.get('role') and d.get('role') != 'superadmin':
        target = auth_users.find_user(username)
        if target and auth_users.is_superadmin(target):
            supers = [u for u in auth_users.list_users() if auth_users.is_superadmin(u)]
            if len(supers) <= 1:
                return jsonify({'error': 'cannot demote the last superadmin'}), 400
    ok, msg = auth_users.update_user(
        username,
        permissions=d.get('permissions'),
        role=d.get('role'),
        password=(d.get('password') or None))
    return (jsonify({'ok': True}) if ok else (jsonify({'error': msg}), 400))


@user_management_bp.route('/api/users/<username>', methods=['DELETE'])
def delete_user(username):
    err = _require_super()
    if err:
        return err
    if username == (getattr(g, 'user', {}) or {}).get('username'):
        return jsonify({'error': 'cannot delete yourself'}), 400
    ok, msg = auth_users.delete_user(username)
    return (jsonify({'ok': True}) if ok else (jsonify({'error': msg}), 400))
