"""
Bulk Import Routes - Import accounts directly to Onimator folder structure

This module handles bulk importing accounts by:
1. Creating account folders from template
2. Adding entries to accounts.db
3. Setting up default settings
"""

from flask import Blueprint, request, jsonify
from pathlib import Path
import sqlite3
import shutil
import json

bulk_import_bp = Blueprint('bulk_import', __name__, url_prefix='/api/bulk-import')

# Base path for Onimator data (parent of dashboard folder)
BASE_PATH = Path(__file__).parent.parent

# Template folder path
TEMPLATE_PATH = BASE_PATH / 'template' / 'accountemplate'


def get_device_folder(device_serial):
    """Get the device folder path"""
    return BASE_PATH / device_serial


def get_accounts_db_path(device_serial):
    """Get path to device's accounts.db"""
    return get_device_folder(device_serial) / 'accounts.db'


def get_account_folder(device_serial, account):
    """Get the account folder path"""
    return get_device_folder(device_serial) / account


def create_account_folder(device_serial, username):
    """
    Create account folder by copying template files

    Returns:
        tuple: (success: bool, message: str)
    """
    account_folder = get_account_folder(device_serial, username)

    # Check if folder already exists
    if account_folder.exists():
        return False, f"Account folder already exists: {username}"

    # Check if template exists
    if not TEMPLATE_PATH.exists():
        return False, f"Template folder not found: {TEMPLATE_PATH}"

    try:
        # Copy entire template folder to new account folder
        shutil.copytree(TEMPLATE_PATH, account_folder)
        return True, f"Created account folder: {username}"
    except Exception as e:
        return False, f"Failed to create folder: {str(e)}"


def add_account_to_db(device_serial, account_data):
    """
    Add account entry to accounts.db

    Args:
        device_serial: Device serial number
        account_data: Dict with username, password, starttime, endtime, appid, 2fa_code

    Returns:
        tuple: (success: bool, message: str)
    """
    accounts_db = get_accounts_db_path(device_serial)

    if not accounts_db.exists():
        return False, f"accounts.db not found for device: {device_serial}"

    try:
        conn = sqlite3.connect(str(accounts_db))
        cursor = conn.cursor()

        # Check if account already exists
        cursor.execute("SELECT account FROM accounts WHERE account = ?", (account_data['username'],))
        if cursor.fetchone():
            conn.close()
            return False, f"Account already exists in database: {account_data['username']}"

        # Get existing columns to know what we can insert
        cursor.execute("PRAGMA table_info(accounts)")
        existing_columns = {col[1] for col in cursor.fetchall()}

        # Build INSERT statement based on available columns
        columns = []
        values = []
        placeholders = []

        # Required fields
        if 'account' in existing_columns:
            columns.append('account')
            values.append(account_data['username'])
            placeholders.append('?')

        if 'password' in existing_columns:
            columns.append('password')
            values.append(account_data.get('password', ''))
            placeholders.append('?')

        # Scheduling fields
        if 'starttime' in existing_columns:
            columns.append('starttime')
            values.append(str(account_data.get('starttime', '0')))
            placeholders.append('?')

        if 'endtime' in existing_columns:
            columns.append('endtime')
            values.append(str(account_data.get('endtime', '24')))
            placeholders.append('?')

        # Email (optional)
        if 'email' in existing_columns and account_data.get('email'):
            columns.append('email')
            values.append(account_data.get('email', ''))
            placeholders.append('?')

        # Default toggle values (all OFF initially)
        toggle_defaults = {
            'follow': 'False',
            'unfollow': 'False',
            'mute': 'False',
            'like': 'False',
            'comment': 'False',
            'story': 'False',
            'switchmode': 'False',
            'randomaction': 'False',
        }

        for toggle, default_value in toggle_defaults.items():
            if toggle in existing_columns:
                # Use backticks for reserved words
                columns.append(f'`{toggle}`' if toggle == 'like' else toggle)
                values.append(default_value)
                placeholders.append('?')

        # Default action values
        action_defaults = {
            'followaction': '10,20',
            'unfollowaction': '10,20',
            'followdelay': '30,60',
            'unfollowdelay': '30,60',
            'randomdelay': '30,60',
            'unfollowdelayday': '3',
            'mutemethod': 'random',
        }

        for field, default_value in action_defaults.items():
            if field in existing_columns:
                columns.append(field)
                values.append(default_value)
                placeholders.append('?')

        # Build and execute INSERT query
        # Fix column names for the query (remove backticks for building string)
        columns_str = ', '.join(columns)
        placeholders_str = ', '.join(placeholders)

        query = f"INSERT INTO accounts ({columns_str}) VALUES ({placeholders_str})"
        cursor.execute(query, values)
        conn.commit()
        conn.close()

        return True, f"Added account to database: {account_data['username']}"

    except Exception as e:
        return False, f"Database error: {str(e)}"


def update_account_settings_db(device_serial, username, app_cloner=None):
    """
    Update settings.db in account folder with app_cloner value

    Args:
        device_serial: Device serial
        username: Account username
        app_cloner: App ID string (e.g., "com.instagram.android/...")
    """
    settings_db_path = get_account_folder(device_serial, username) / 'settings.db'

    if not settings_db_path.exists():
        return False, "settings.db not found in account folder"

    try:
        conn = sqlite3.connect(str(settings_db_path))
        cursor = conn.cursor()

        # Read existing settings
        cursor.execute("SELECT settings FROM accountsettings WHERE id = 1")
        row = cursor.fetchone()

        if row and row[0]:
            settings = json.loads(row[0])
        else:
            settings = {}

        # Update app_cloner if provided
        if app_cloner:
            settings['app_cloner'] = app_cloner

        # Write back
        cursor.execute(
            "UPDATE accountsettings SET settings = ? WHERE id = 1",
            (json.dumps(settings),)
        )
        conn.commit()
        conn.close()

        return True, "Settings updated"

    except Exception as e:
        return False, f"Settings error: {str(e)}"


def store_2fa_code(device_serial, username, twofa_code):
    """
    Store 2FA code in 2factorauthcodes.db
    """
    if not twofa_code:
        return True, "No 2FA code to store"

    twofa_db_path = get_account_folder(device_serial, username) / '2factorauthcodes.db'

    if not twofa_db_path.exists():
        return False, "2factorauthcodes.db not found"

    try:
        conn = sqlite3.connect(str(twofa_db_path))
        cursor = conn.cursor()

        # Check if table exists, create if not
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS codes (
                id INTEGER PRIMARY KEY,
                code TEXT
            )
        """)

        # Insert or update the 2FA code
        cursor.execute("DELETE FROM codes")  # Clear existing
        cursor.execute("INSERT INTO codes (code) VALUES (?)", (twofa_code,))

        conn.commit()
        conn.close()

        return True, "2FA code stored"

    except Exception as e:
        return False, f"2FA storage error: {str(e)}"


@bulk_import_bp.route('/accounts', methods=['POST'])
def bulk_import_accounts():
    """
    Bulk import accounts to Onimator

    Request body:
    {
        "device_serial": "10.1.10.244_5555",
        "accounts": [
            {
                "username": "user1",
                "password": "pass1",
                "appid": "com.instagram.android/...",
                "starttime": 0,
                "endtime": 2,
                "twofa_code": "ABCD1234..."
            },
            ...
        ]
    }

    Or from CSV-like format:
    {
        "device_serial": "10.1.10.244_5555",
        "accounts_text": "user1:pass1:2fa\nuser2:pass2:2fa"
    }
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        device_serial = data.get('device_serial')
        if not device_serial:
            return jsonify({'success': False, 'error': 'device_serial is required'}), 400

        # Check device folder exists
        device_folder = get_device_folder(device_serial)
        if not device_folder.exists():
            return jsonify({
                'success': False,
                'error': f'Device folder not found: {device_serial}'
            }), 404

        # Check accounts.db exists
        accounts_db = get_accounts_db_path(device_serial)
        if not accounts_db.exists():
            return jsonify({
                'success': False,
                'error': f'accounts.db not found for device: {device_serial}'
            }), 404

        # Parse accounts from either format
        accounts = data.get('accounts', [])

        # If accounts_text provided, parse it
        if not accounts and data.get('accounts_text'):
            accounts = parse_accounts_text(data['accounts_text'])

        if not accounts:
            return jsonify({'success': False, 'error': 'No accounts provided'}), 400

        # Process each account
        results = []
        success_count = 0
        skip_count = 0
        error_count = 0

        for i, account in enumerate(accounts):
            username = account.get('username', '').strip()

            if not username:
                results.append({
                    'username': f'(row {i+1})',
                    'success': False,
                    'error': 'Empty username'
                })
                error_count += 1
                continue

            # Step 1: Create account folder from template
            folder_success, folder_msg = create_account_folder(device_serial, username)

            if not folder_success:
                if 'already exists' in folder_msg:
                    results.append({
                        'username': username,
                        'success': False,
                        'skipped': True,
                        'error': folder_msg
                    })
                    skip_count += 1
                else:
                    results.append({
                        'username': username,
                        'success': False,
                        'error': folder_msg
                    })
                    error_count += 1
                continue

            # Step 2: Add to accounts.db
            db_success, db_msg = add_account_to_db(device_serial, {
                'username': username,
                'password': account.get('password', ''),
                'starttime': account.get('starttime', i * 2),  # Default: stagger by 2 hours
                'endtime': account.get('endtime', (i * 2) + 2),
                'email': account.get('email', ''),
            })

            if not db_success:
                # Rollback: remove created folder
                try:
                    shutil.rmtree(get_account_folder(device_serial, username))
                except:
                    pass

                results.append({
                    'username': username,
                    'success': False,
                    'error': db_msg
                })
                error_count += 1
                continue

            # Step 3: Update settings.db with app_cloner
            if account.get('appid'):
                update_account_settings_db(device_serial, username, account.get('appid'))

            # Step 4: Store 2FA code if provided
            if account.get('twofa_code'):
                store_2fa_code(device_serial, username, account.get('twofa_code'))

            results.append({
                'username': username,
                'success': True
            })
            success_count += 1

        return jsonify({
            'success': True,
            'message': f'Imported {success_count} accounts, skipped {skip_count}, errors {error_count}',
            'summary': {
                'total': len(accounts),
                'success': success_count,
                'skipped': skip_count,
                'errors': error_count
            },
            'results': results
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def parse_accounts_text(text):
    """
    Parse accounts from text format: username:password:2fa_code
    """
    accounts = []
    lines = text.strip().split('\n')

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        parts = line.split(':')
        if len(parts) >= 2:
            account = {
                'username': parts[0].strip(),
                'password': parts[1].strip() if len(parts) > 1 else '',
                'twofa_code': parts[2].strip().replace(' ', '') if len(parts) > 2 else '',
                'starttime': i * 2,
                'endtime': (i * 2) + 2,
            }

            # Generate app ID (increment letter for each account)
            letter = chr(101 + i)  # 'e', 'f', 'g', ...
            account['appid'] = f"com.instagram.androi{letter}/com.instagram.mainactivity.MainActivity"

            accounts.append(account)

    return accounts


@bulk_import_bp.route('/check-template', methods=['GET'])
def check_template():
    """Check if template folder exists and list its contents"""
    if not TEMPLATE_PATH.exists():
        return jsonify({
            'success': False,
            'error': 'Template folder not found',
            'expected_path': str(TEMPLATE_PATH)
        }), 404

    files = list(TEMPLATE_PATH.iterdir())

    return jsonify({
        'success': True,
        'template_path': str(TEMPLATE_PATH),
        'files_count': len(files),
        'files': [f.name for f in files]
    })


@bulk_import_bp.route('/preview', methods=['POST'])
def preview_import():
    """
    Preview what would be imported without actually doing it
    """
    try:
        data = request.get_json()

        device_serial = data.get('device_serial')
        accounts_text = data.get('accounts_text', '')

        if not device_serial:
            return jsonify({'success': False, 'error': 'device_serial required'}), 400

        # Parse accounts
        accounts = parse_accounts_text(accounts_text)

        # Check which already exist
        preview = []
        for account in accounts:
            username = account['username']
            folder_exists = get_account_folder(device_serial, username).exists()

            preview.append({
                'username': username,
                'password': '***' + account['password'][-3:] if len(account['password']) > 3 else '***',
                'has_2fa': bool(account.get('twofa_code')),
                'appid': account.get('appid', ''),
                'starttime': account.get('starttime'),
                'endtime': account.get('endtime'),
                'already_exists': folder_exists,
                'will_import': not folder_exists
            })

        new_count = sum(1 for p in preview if p['will_import'])
        skip_count = sum(1 for p in preview if p['already_exists'])

        return jsonify({
            'success': True,
            'total': len(preview),
            'new_accounts': new_count,
            'existing_accounts': skip_count,
            'preview': preview
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
