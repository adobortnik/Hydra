from flask import Blueprint, render_template, request, jsonify, redirect
import sqlite3
import os
import json
from datetime import datetime
from pathlib import Path

job_orders_bp = Blueprint('job_orders', __name__)

def get_root_dir():
    """Get the root directory where Onimator data is stored"""
    current_dir = Path(__file__).parent
    return current_dir.parent  # full_igbot_14.2.4/

BASE_DIR = get_root_dir()
JOBS_DIR = BASE_DIR / 'jobs'
JOBS_DB = JOBS_DIR / 'jobs.db'

def get_db_connection(db_path):
    """Create a database connection"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn

def get_all_job_orders():
    """Get all job orders from the central jobs system"""
    jobs = []

    # Check if jobs.db exists
    if not JOBS_DB.exists():
        return jobs

    try:
        # Get enabled jobs from central database
        conn = get_db_connection(JOBS_DB)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM job_orders WHERE is_enable = 1')
        job_rows = cursor.fetchall()
        conn.close()

        # For each enabled job, get its configuration
        for job_row in job_rows:
            job_id = str(job_row['id'])
            job_path = JOBS_DIR / job_id

            if not job_path.exists():
                continue

            # Read settings.db
            settings_db = job_path / 'settings.db'
            if not settings_db.exists():
                continue

            try:
                conn = get_db_connection(settings_db)
                cursor = conn.cursor()
                cursor.execute('SELECT settings FROM job_settings LIMIT 1')
                settings_row = cursor.fetchone()
                conn.close()

                if not settings_row:
                    continue

                settings = json.loads(settings_row['settings'])

                # Count selected accounts
                selected_db = job_path / 'selected_accounts.db'
                account_count = 0
                if selected_db.exists():
                    conn = get_db_connection(selected_db)
                    cursor = conn.cursor()
                    cursor.execute('SELECT COUNT(*) as count FROM job_selected_accounts')
                    account_count = cursor.fetchone()['count']
                    conn.close()

                # Count successful completions
                success_db = job_path / 'success_accounts.db'
                success_count = 0
                if success_db.exists():
                    conn = get_db_connection(success_db)
                    cursor = conn.cursor()
                    cursor.execute('SELECT COUNT(*) as count FROM accounts')
                    success_count = cursor.fetchone()['count']
                    conn.close()

                # Build job object
                jobs.append({
                    'id': job_id,
                    'job_name': settings.get('job_name', 'Unnamed'),
                    'job_type': settings.get('job_type', 'follow'),
                    'target': settings.get('target', ''),
                    'to_deliver': int(settings.get('to_deliver', 0)),
                    'limit_per_hour': int(settings.get('limit_number_action_per_hour', 0)),
                    'limit_per_day': int(settings.get('limit_number_action_per_day', 0)),
                    'comment_text': settings.get('comment', ''),
                    'account_count': account_count,
                    'total_completed': success_count
                })

            except Exception as e:
                print(f"Error reading job {job_id}: {e}")
                continue

    except Exception as e:
        print(f"Error getting job orders: {e}")
        import traceback
        traceback.print_exc()

    return jobs

@job_orders_bp.route('/')
def index():
    """Redirect to Job Orders V2 (now the main Job Orders page)"""
    return redirect('/job-orders-v2')

@job_orders_bp.route('/api/jobs', methods=['GET'])
def get_jobs():
    """Get all job orders"""
    try:
        jobs = get_all_job_orders()
        return jsonify({'success': True, 'jobs': jobs})
    except Exception as e:
        print(f"Error in get_jobs: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@job_orders_bp.route('/api/jobs/<job_id>', methods=['GET'])
def get_job(job_id):
    """Get a specific job order with its accounts"""
    try:
        job_path = os.path.join(JOBS_DIR, job_id)

        if not os.path.exists(job_path):
            return jsonify({'success': False, 'error': 'Job not found'}), 404

        # Read settings
        settings_db = os.path.join(job_path, 'settings.db')
        conn = get_db_connection(settings_db)
        cursor = conn.cursor()
        cursor.execute('SELECT settings FROM job_settings LIMIT 1')
        settings_row = cursor.fetchone()
        conn.close()

        settings = json.loads(settings_row['settings'])

        # Get selected accounts
        selected_db = os.path.join(job_path, 'selected_accounts.db')
        conn = get_db_connection(selected_db)
        cursor = conn.cursor()
        cursor.execute('SELECT deviceid, username FROM job_selected_accounts')
        accounts = [{'device': row['deviceid'], 'username': row['username']} for row in cursor.fetchall()]
        conn.close()

        # Count successful
        success_db = os.path.join(job_path, 'success_accounts.db')
        conn = get_db_connection(success_db)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as count FROM accounts')
        success_count = cursor.fetchone()['count']
        conn.close()

        job = {
            'id': job_id,
            'job_name': settings.get('job_name', 'Unnamed'),
            'job_type': settings.get('job_type', 'follow'),
            'target': settings.get('target', ''),
            'to_deliver': int(settings.get('to_deliver', 0)),
            'limit_per_hour': int(settings.get('limit_number_action_per_hour', 0)),
            'limit_per_day': int(settings.get('limit_number_action_per_day', 0)),
            'comment_text': settings.get('comment', ''),
            'accounts': accounts,
            'total_completed': success_count
        }

        return jsonify({'success': True, 'job': job})

    except Exception as e:
        print(f"Error in get_job: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@job_orders_bp.route('/api/jobs', methods=['POST'])
def create_job():
    """Create a new job order"""
    try:
        data = request.json

        # Generate job ID (timestamp in milliseconds)
        job_id = str(int(datetime.now().timestamp() * 1000))
        job_path = os.path.join(JOBS_DIR, job_id)
        os.makedirs(job_path, exist_ok=True)

        # Create settings.db
        settings_db = os.path.join(job_path, 'settings.db')
        conn = get_db_connection(settings_db)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS job_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                settings TEXT NOT NULL
            )
        ''')

        settings = {
            'job_name': data.get('job_name', 'Unnamed'),
            'target': data.get('target', ''),
            'to_deliver': str(data.get('total_to_deliver', 1000)),
            'job_type': data.get('job_type', 'follow'),
            'limit_number_action_per_hour': str(data.get('limit_per_hour', 100)),
            'limit_number_action_per_day': str(data.get('limit_per_day', 500)),
            'comment': data.get('comment_text', '')
        }

        cursor.execute('INSERT INTO job_settings (settings) VALUES (?)', (json.dumps(settings),))
        conn.commit()
        conn.close()

        # Create selected_accounts.db
        selected_db = os.path.join(job_path, 'selected_accounts.db')
        conn = get_db_connection(selected_db)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS job_selected_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deviceid TEXT NOT NULL,
                username TEXT NOT NULL
            )
        ''')

        for account in data.get('accounts', []):
            cursor.execute('INSERT INTO job_selected_accounts (deviceid, username) VALUES (?, ?)',
                         (account['device'], account['username']))

        conn.commit()
        conn.close()

        # Create success_accounts.db
        success_db = os.path.join(job_path, 'success_accounts.db')
        conn = get_db_connection(success_db)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deviceid TEXT NOT NULL,
                username TEXT NOT NULL,
                date TEXT,
                hour TEXT
            )
        ''')

        conn.commit()
        conn.close()

        # Add to central jobs.db
        if os.path.exists(JOBS_DB):
            conn = get_db_connection(JOBS_DB)
            cursor = conn.cursor()

            cursor.execute('INSERT INTO job_orders (id, job, is_enable) VALUES (?, ?, 1)',
                         (int(job_id), data.get('job_type', 'follow')))

            conn.commit()
            conn.close()

        # Also create job entries in each account's jobs folder
        job_type = data.get('job_type', 'follow')
        for account in data.get('accounts', []):
            device = account['device']
            username = account['username']

            account_jobs_path = BASE_DIR / device / username / 'jobs'
            account_jobs_path.mkdir(parents=True, exist_ok=True)

            job_db_path = account_jobs_path / f'{job_type}_jobs.db'

            try:
                conn = get_db_connection(job_db_path)
                cursor = conn.cursor()

                if job_type == 'follow':
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS job_orders (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            job VARCHAR,
                            target_username VARCHAR,
                            is_done INTEGER DEFAULT 0
                        )
                    ''')
                    cursor.execute('INSERT INTO job_orders (job, target_username, is_done) VALUES (?, ?, 0)',
                                 (job_id, data.get('target', '')))
                else:
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS job_orders (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            job VARCHAR,
                            target VARCHAR,
                            is_done INTEGER DEFAULT 0
                        )
                    ''')
                    cursor.execute('INSERT INTO job_orders (job, target, is_done) VALUES (?, ?, 0)',
                                 (job_id, data.get('target', '')))

                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Error creating job in account {username}: {e}")

        return jsonify({'success': True, 'job_id': job_id})

    except Exception as e:
        print(f"Error in create_job: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@job_orders_bp.route('/api/jobs/<job_id>', methods=['DELETE'])
def delete_job(job_id):
    """Delete a job order"""
    try:
        job_path = os.path.join(JOBS_DIR, job_id)

        if not os.path.exists(job_path):
            return jsonify({'success': False, 'error': 'Job not found'}), 404

        # Get selected accounts first
        selected_db = os.path.join(job_path, 'selected_accounts.db')
        accounts = []
        if os.path.exists(selected_db):
            conn = get_db_connection(selected_db)
            cursor = conn.cursor()
            cursor.execute('SELECT deviceid, username FROM job_selected_accounts')
            accounts = [dict(row) for row in cursor.fetchall()]
            conn.close()

        # Get job type from settings
        settings_db = os.path.join(job_path, 'settings.db')
        job_type = 'follow'
        if os.path.exists(settings_db):
            conn = get_db_connection(settings_db)
            cursor = conn.cursor()
            cursor.execute('SELECT settings FROM job_settings LIMIT 1')
            settings_row = cursor.fetchone()
            if settings_row:
                settings = json.loads(settings_row['settings'])
                job_type = settings.get('job_type', 'follow')
            conn.close()

        # Delete from central jobs.db
        if os.path.exists(JOBS_DB):
            conn = get_db_connection(JOBS_DB)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM job_orders WHERE id = ?', (int(job_id),))
            conn.commit()
            conn.close()

        # Delete from each account's jobs folder
        for account in accounts:
            device = account['deviceid']
            username = account['username']

            job_db_path = BASE_DIR / device / username / 'jobs' / f'{job_type}_jobs.db'

            if job_db_path.exists():
                try:
                    conn = get_db_connection(job_db_path)
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM job_orders WHERE job = ?', (job_id,))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    print(f"Error deleting from {job_db_path}: {e}")

        # Delete job folder
        import shutil
        if os.path.exists(job_path):
            shutil.rmtree(job_path)

        return jsonify({'success': True})

    except Exception as e:
        print(f"Error in delete_job: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@job_orders_bp.route('/api/available-accounts', methods=['GET'])
def get_available_accounts():
    """Get all available devices and accounts for job assignment"""
    try:
        root_dir = get_root_dir()
        devices_db = root_dir / 'devices.db'

        all_accounts = []

        # Get devices from devices.db
        conn = sqlite3.connect(str(devices_db))
        cursor = conn.cursor()
        cursor.execute("SELECT deviceid FROM devices")
        devices = [row[0] for row in cursor.fetchall()]
        conn.close()

        for device_serial in devices:
            device_folder = root_dir / device_serial

            if not device_folder.exists():
                continue

            # Get accounts from accounts.db in device folder
            accounts_db = device_folder / 'accounts.db'

            if not accounts_db.exists():
                continue

            try:
                conn = sqlite3.connect(str(accounts_db))
                cursor = conn.cursor()
                cursor.execute("SELECT account FROM accounts")
                accounts = cursor.fetchall()
                conn.close()

                for account in accounts:
                    all_accounts.append({
                        'device': device_serial,
                        'username': account[0],
                        'enabled': 1  # All accounts in the table are considered enabled
                    })

            except Exception as e:
                print(f"Error reading accounts from {device_serial}: {e}")
                continue

        return jsonify({'success': True, 'accounts': all_accounts})

    except Exception as e:
        print(f"Error in get_available_accounts: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
