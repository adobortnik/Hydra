# Import necessary modules
import os
import sys
import json
import sqlite3
from flask import Flask, render_template, jsonify, request, Blueprint

# Get base directory from simple_app.py
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THELIVEHOUSE_DIR = os.path.dirname(os.path.abspath(__file__))

# Add parent dir so we can import automation.source_manager
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from automation.source_manager import (
        read_sources_txt, write_sources_txt, get_source_info,
        get_source_filename, get_sources, list_all_source_types,
        set_base_dir as sm_set_base_dir, SOURCE_FILE_MAP
    )
    sm_set_base_dir(BASE_DIR)
    _HAS_SOURCE_MANAGER = True
except ImportError:
    _HAS_SOURCE_MANAGER = False

# Create a Blueprint for the sources management routes
sources_bp = Blueprint('sources', __name__)

# Helper function to get a database connection
def get_db_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# Helper function to convert row to dict
def row_to_dict(row):
    return {key: row[key] for key in row.keys()} if row else {}

# ── phone_farm.db path (single source of truth) ──
PHONE_FARM_DB = os.path.join(BASE_DIR, 'db', 'phone_farm.db')

# Get all devices — reads from phone_farm.db
def get_devices():
    try:
        if not os.path.exists(PHONE_FARM_DB):
            # Fallback to old devices.db if phone_farm.db missing
            devices_db = os.path.join(BASE_DIR, 'devices.db')
            if not os.path.exists(devices_db):
                return []
            conn = get_db_connection(devices_db)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM devices')
            devices = [row_to_dict(row) for row in cursor.fetchall()]
            conn.close()
            return devices

        conn = get_db_connection(PHONE_FARM_DB)
        cursor = conn.cursor()
        cursor.execute('SELECT id, device_serial, device_name, ip_address, status FROM devices ORDER BY device_serial')
        devices = []
        for row in cursor.fetchall():
            d = row_to_dict(row)
            # Map to old field names that the template expects
            d['deviceid'] = d.get('device_serial', '')
            d['devicename'] = d.get('device_name', d.get('device_serial', ''))
            devices.append(d)
        conn.close()
        return devices
    except Exception as e:
        print(f"Error getting devices: {e}")
        return []

# Get accounts for a device — reads from phone_farm.db
def get_accounts(device_id):
    try:
        if not os.path.exists(PHONE_FARM_DB):
            # Fallback to old per-device accounts.db
            accounts_db = os.path.join(BASE_DIR, device_id, 'accounts.db')
            if not os.path.exists(accounts_db):
                return []
            conn = get_db_connection(accounts_db)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM accounts')
            accounts = [row_to_dict(row) for row in cursor.fetchall()]
            conn.close()
            return accounts

        conn = get_db_connection(PHONE_FARM_DB)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, device_serial, username, password, instagram_package, status, start_time, end_time FROM accounts WHERE device_serial = ?',
            (device_id,)
        )
        accounts = []
        for row in cursor.fetchall():
            a = row_to_dict(row)
            # Map to old field names that the template expects
            a['account'] = a.get('username', '')
            a['deviceid'] = a.get('device_serial', '')
            accounts.append(a)
        conn.close()
        return accounts
    except Exception as e:
        print(f"Error getting accounts for device {device_id}: {e}")
        return []

# Get tags for an account
def get_account_tags(device_id, account_name):
    try:
        # Try phone_farm.db first (new system)
        if os.path.exists(PHONE_FARM_DB):
            conn = get_db_connection(PHONE_FARM_DB)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT t.name
                FROM account_tags at
                JOIN tags t ON at.tag_id = t.id
                JOIN accounts a ON at.account_id = a.id
                WHERE a.device_serial = ? AND a.username = ?
            ''', (device_id, account_name))
            tags = [row[0] for row in cursor.fetchall()]
            conn.close()
            return tags

        # Fallback to old profile_automation.db
        profile_db_path = os.path.join(BASE_DIR, 'uiAutomator', 'profile_automation.db')
        if not os.path.exists(profile_db_path):
            return []

        conn = get_db_connection(profile_db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.name
            FROM account_tags at
            JOIN tags t ON at.tag_id = t.id
            WHERE at.device_serial = ? AND at.username = ?
        ''', (device_id, account_name))
        tags = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tags
    except Exception as e:
        print(f"Error getting tags for {device_id}/{account_name}: {e}")
        return []

# Map dashboard source_type names → source_manager action_type keys
_DASHBOARD_TYPE_MAP = {
    'follow': 'follow',
    'share': 'share',
    'share_to_story': 'share_to_story',
    'dm': 'dm',
    'follow_likers': 'follow_likers',
    'follow_specific': 'follow_specific',
    'story_viewer_followers': 'story_viewer_followers',
    'story_viewer_likers': 'story_viewer_likers',
    'like_specific': 'like_specific',
    'view_specific': 'view_specific',
}

# Map dashboard source_type → DB source_type in account_sources table
_DB_SOURCE_TYPE_MAP = {
    'follow': 'sources',
    'share': 'share_sources',
    'like': 'like_sources',
    'comment': 'comment_sources',
    'follow_likers': 'follow_likers_sources',
    'follow_specific': 'follow_specific_sources',
    'follow_keywords': 'follow_using_word_search',
    'unfollow_specific': 'unfollow_specific_accounts',
    'like_keywords': 'like_post_likers_using_keyword_search',
    'like_specific': 'like_posts_specific',
    'comment_keywords': 'comment_using_keyword_search',
    'dm': 'directmessagespecificusersources',
    'dm_specific': 'directmessagespecificuser',
    'story_followers': 'storyviewer_user_followers_sources',
    'story_likers': 'storyviewer_user_likers_sources',
    'reels': 'watch_reels_sources',
    'whitelist': 'whitelist',
    'close_friends': 'close_friends',
}


# Get all accounts from all devices with their sources from phone_farm.db
def get_all_accounts_with_sources(source_type='follow'):
    try:
        db_source_type = _DB_SOURCE_TYPE_MAP.get(source_type, source_type)

        conn = get_db_connection(PHONE_FARM_DB)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT a.id, a.device_serial, a.username, d.device_name
            FROM accounts a
            JOIN devices d ON a.device_serial = d.device_serial
            ORDER BY a.device_serial, a.username
        ''')

        all_accounts = []
        for row in cursor.fetchall():
            acct_id = row['id']
            device_id = row['device_serial']
            account_name = row['username']

            # Get sources for this account + source_type
            cursor.execute(
                'SELECT value FROM account_sources WHERE account_id = ? AND source_type = ? ORDER BY value',
                (acct_id, db_source_type)
            )
            source_rows = cursor.fetchall()
            sources_content = '\n'.join(r['value'] for r in source_rows)
            usernames_count = len(source_rows)

            # Get tags
            cursor.execute('''
                SELECT t.name FROM account_tags at
                JOIN tags t ON at.tag_id = t.id
                WHERE at.account_id = ?
            ''', (acct_id,))
            tags = [r['name'] for r in cursor.fetchall()]

            all_accounts.append({
                'device_id': device_id,
                'account_name': account_name,
                'sources_exists': usernames_count > 0,
                'sources_content': sources_content,
                'sources_path': f'{db_source_type}',
                'usernames_count': usernames_count,
                'source_type': source_type,
                'file_name': db_source_type,
                'tags': tags
            })

        conn.close()
        return all_accounts
    except Exception as e:
        print(f"Error getting all accounts with sources: {e}")
        return []

# Update sources in phone_farm.db for multiple accounts
def update_sources_files(account_data, source_type=None):
    """
    Update source lists in phone_farm.db for multiple accounts.

    account_data should be a dictionary with:
    - account_ids: list of account identifiers in format "device_id/account_name"
    - usernames: string with usernames, one per line
    - source_type: string indicating the source type
    """
    try:
        account_ids = account_data.get('account_ids', [])
        usernames = account_data.get('usernames', '')

        if source_type is None:
            source_type = account_data.get('source_type', 'follow')

        db_source_type = _DB_SOURCE_TYPE_MAP.get(source_type, source_type)

        if not account_ids or not usernames:
            return {
                'success': False,
                'message': 'No accounts selected or no usernames provided',
                'updated_count': 0
            }

        username_list = [u.strip() for u in usernames.split('\n') if u.strip()]

        conn = sqlite3.connect(PHONE_FARM_DB)
        cursor = conn.cursor()

        success_count = 0
        failed_accounts = []

        for account_id_str in account_ids:
            try:
                parts = account_id_str.split('/')
                if len(parts) != 2:
                    failed_accounts.append({'account_id': account_id_str, 'error': 'Invalid format'})
                    continue

                device_id, account_name = parts

                cursor.execute(
                    'SELECT id FROM accounts WHERE device_serial = ? AND username = ?',
                    (device_id, account_name)
                )
                row = cursor.fetchone()
                if not row:
                    failed_accounts.append({'account_id': account_id_str, 'error': 'Account not found'})
                    continue

                acct_id = row[0]

                # Delete old sources for this type, then insert new
                cursor.execute(
                    'DELETE FROM account_sources WHERE account_id = ? AND source_type = ?',
                    (acct_id, db_source_type)
                )
                for username in username_list:
                    cursor.execute(
                        'INSERT INTO account_sources (account_id, source_type, value) VALUES (?, ?, ?)',
                        (acct_id, db_source_type, username)
                    )

                success_count += 1

            except Exception as e:
                failed_accounts.append({'account_id': account_id_str, 'error': str(e)})

        conn.commit()
        conn.close()

        return {
            'success': True,
            'message': f'Updated {db_source_type} for {success_count} accounts',
            'updated_count': success_count,
            'failed_accounts': failed_accounts,
            'source_type': source_type,
        }

    except Exception as e:
        print(f"Error updating sources: {e}")
        return {
            'success': False,
            'message': str(e),
            'updated_count': 0
        }

# Route to render the manage sources page
@sources_bp.route('/manage_sources')
def manage_sources():
    return render_template('manage_sources_new.html')

# API route to get all accounts with their sources status
@sources_bp.route('/api/sources/accounts')
def api_sources_accounts():
    source_type = request.args.get('source_type', 'follow')
    accounts = get_all_accounts_with_sources(source_type)
    return jsonify(accounts)

# API route to update sources files for multiple accounts
@sources_bp.route('/api/sources/update', methods=['POST'])
def api_sources_update():
    try:
        data = request.json
        # Let the update_sources_files function handle the source_type from the data
        result = update_sources_files(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API: list all available source types (for dynamic tab generation)
@sources_bp.route('/api/sources/types')
def api_sources_types():
    return jsonify([
        {'key': 'follow', 'label': 'Follow Sources'},
        {'key': 'share', 'label': 'Share Sources'},
        {'key': 'like', 'label': 'Like Sources'},
        {'key': 'comment', 'label': 'Comment Sources'},
        {'key': 'follow_likers', 'label': 'Follow Likers Sources'},
        {'key': 'follow_specific', 'label': 'Follow Specific Sources'},
        {'key': 'dm', 'label': 'DM Sources'},
        {'key': 'reels', 'label': 'Reels Sources'},
        {'key': 'whitelist', 'label': 'Whitelist'},
    ])


# API: get source info for a single account + action type
@sources_bp.route('/api/sources/info')
def api_sources_info():
    device_id = request.args.get('device_id', '')
    account_name = request.args.get('account_name', '')
    action_type = request.args.get('action_type', 'follow')

    if not device_id or not account_name:
        return jsonify({'error': 'device_id and account_name required'}), 400

    action_type = _DASHBOARD_TYPE_MAP.get(action_type, action_type)

    if _HAS_SOURCE_MANAGER:
        info = get_source_info(device_id, account_name, action_type)
        return jsonify(info)

    # Fallback
    if action_type in ('share', 'share_to_story'):
        fn = 'shared_post_username_source.txt'
    else:
        fn = 'sources.txt'
    path = os.path.join(BASE_DIR, device_id, account_name, fn)
    exists = os.path.exists(path)
    content = ''
    if exists:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            pass
    return jsonify({
        'device_id': device_id,
        'account_name': account_name,
        'action_type': action_type,
        'filename': fn,
        'filepath': path,
        'exists': exists,
        'count': len([l for l in content.split('\n') if l.strip()]),
        'content': content,
    })
