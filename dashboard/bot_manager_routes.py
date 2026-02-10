#!/usr/bin/env python3
"""
Bot Manager Routes
Dashboard API for starting/stopping Onimator bots (igbot.exe)
"""

import subprocess
import os
import sys
import time
from pathlib import Path
from flask import Blueprint, jsonify, request

# Add uiAutomator to path (now inside dashboard folder)
sys.path.insert(0, str(Path(__file__).parent / "uiAutomator"))

from bot_db import (
    get_bot_status, update_bot_status,
    query_account_sessions, calculate_device_metrics,
    init_bot_database
)

bot_manager_bp = Blueprint('bot_manager', __name__, url_prefix='/api/bots')

# Track running bot processes (in-memory cache)
running_bots = {}  # device_serial -> process


def get_root_dir():
    """Get root directory (parent of the-livehouse-dashboard)"""
    return Path(__file__).parent.parent


def get_igbot_exe_path():
    """Get path to igbot.exe"""
    return get_root_dir() / "igbot.exe"


def get_device_folder(device_serial):
    """Get device folder path"""
    return get_root_dir() / device_serial


def read_device_pid(device_serial):
    """
    Read PID from device's pid file

    Returns:
        list: List of PIDs (as integers) or empty list
    """
    pid_file = get_device_folder(device_serial) / "pid"

    if not pid_file.exists():
        return []

    try:
        content = pid_file.read_text().strip()
        if content:
            # PIDs are stored one per line, convert to integers
            pids = []
            for pid in content.split('\n'):
                pid = pid.strip()
                if pid:
                    try:
                        pids.append(int(pid))
                    except ValueError:
                        pass  # Skip invalid PIDs
            return pids
        return []
    except Exception as e:
        print(f"Error reading pid file: {e}")
        return []


def write_device_pid(device_serial, pid):
    """Write PID to device's pid file"""
    pid_file = get_device_folder(device_serial) / "pid"

    try:
        # Append PID (Onimator can have multiple PIDs per device)
        existing_pids = read_device_pid(device_serial)  # Returns list of ints
        existing_pids.append(int(pid))  # Ensure it's an int

        # Convert to strings for writing
        pid_strings = [str(p) for p in existing_pids]
        pid_file.write_text('\n'.join(pid_strings) + '\n')

        print(f"Wrote PID {pid} to {pid_file}")
        return True
    except Exception as e:
        print(f"Error writing pid file: {e}")
        return False


def is_process_running(pid):
    """Check if process with given PID is running (Windows)"""
    try:
        result = subprocess.run(
            ['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'],
            capture_output=True,
            text=True,
            timeout=5
        )
        # If PID exists, tasklist will return a line with the process
        return str(pid) in result.stdout
    except Exception as e:
        print(f"Error checking process {pid}: {e}")
        return False


def kill_process(pid):
    """Kill process with given PID (Windows)"""
    try:
        subprocess.run(['taskkill', '/F', '/PID', str(pid)], check=False, timeout=5)
        print(f"Killed process {pid}")
        return True
    except Exception as e:
        print(f"Error killing process {pid}: {e}")
        return False


def get_all_running_pids():
    """Get all running PIDs at once (much faster than checking individually)"""
    try:
        result = subprocess.run(
            ['tasklist', '/FO', 'CSV', '/NH'],
            capture_output=True,
            text=True,
            timeout=5
        )
        # Parse CSV output to extract PIDs
        running_pids = set()
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split(',')
                if len(parts) >= 2:
                    pid_str = parts[1].strip('"')
                    try:
                        running_pids.add(int(pid_str))
                    except ValueError:
                        pass
        return running_pids
    except Exception as e:
        print(f"Error getting all PIDs: {e}")
        return set()


def get_all_igbot_processes():
    """
    Get all running igbot.exe processes with their PIDs and device serials

    Returns:
        dict: {device_serial: [pid1, pid2, ...]}
    """
    try:
        # Use WMIC to get process command lines
        result = subprocess.run(
            ['wmic', 'process', 'where', 'name="igbot.exe"', 'get', 'ProcessId,CommandLine', '/FORMAT:CSV'],
            capture_output=True,
            text=True,
            timeout=10
        )

        device_pids = {}
        lines = result.stdout.strip().split('\n')

        for line in lines[1:]:  # Skip header
            if not line.strip():
                continue

            parts = line.split(',')
            if len(parts) >= 3:
                # Format: Node,CommandLine,ProcessId
                command_line = parts[1]
                try:
                    pid = int(parts[2])
                except (ValueError, IndexError):
                    continue

                # Extract device serial from command line
                # Command line format: "path\to\igbot.exe" 10.1.10.192_5555
                # or: igbot.exe 10.1.10.192_5555
                if command_line:
                    # Split and get the last argument (device serial)
                    cmd_parts = command_line.strip().split()
                    if len(cmd_parts) >= 2:
                        device_serial = cmd_parts[-1]
                        # Validate it looks like a device serial (IP_PORT format)
                        if '_' in device_serial and '.' in device_serial:
                            if device_serial not in device_pids:
                                device_pids[device_serial] = []
                            device_pids[device_serial].append(pid)

        return device_pids

    except Exception as e:
        print(f"Error getting igbot processes: {e}")
        return {}


@bot_manager_bp.route('/status', methods=['GET'])
def get_all_bots_status():
    """Get status of all bots across all devices"""

    # Import here to avoid circular dependency
    try:
        from simple_app import get_devices
        devices = get_devices()
    except:
        # Fallback: read from devices.db directly
        devices_db = get_root_dir() / "devices.db"
        if devices_db.exists():
            import sqlite3
            conn = sqlite3.connect(str(devices_db))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            devices = [dict(row) for row in cursor.execute("SELECT * FROM devices")]
            conn.close()
        else:
            devices = []

    # Get all running igbot.exe processes mapped by device serial
    igbot_processes = get_all_igbot_processes()
    print(f"Found {len(igbot_processes)} devices with running igbot.exe")

    # Also get all running PIDs for fallback
    all_running_pids = get_all_running_pids()

    statuses = []

    for device in devices:
        device_serial = device['deviceid']

        # Method 1: Check from WMIC command line scan (most accurate)
        running_pids = igbot_processes.get(device_serial, [])

        # Method 2: Fallback to PID file if WMIC didn't find it
        if not running_pids:
            try:
                pids = read_device_pid(device_serial)
                running_pids = [pid for pid in pids if pid in all_running_pids]
            except Exception as e:
                print(f"Error reading PIDs for {device_serial}: {e}")
                running_pids = []

        # Get bot database status (if using our new bot system)
        try:
            bot_db_status = get_bot_status(device_serial)
        except:
            bot_db_status = {}

        # Determine overall status
        if running_pids:
            status = 'running'
        elif bot_db_status.get('status') == 'running':
            status = 'running'
        else:
            status = 'stopped'

        statuses.append({
            'device_serial': device_serial,
            'device_name': device.get('devicename'),
            'bot_status': status,  # Changed to bot_status to match frontend
            'pid': running_pids[0] if running_pids else None,  # First PID
            'pids': running_pids,
            'pid_count': len(running_pids),
            'accounts_running': bot_db_status.get('accounts_run_today', 0),
            'actions_today': bot_db_status.get('actions_today', 0),
            'started_at': bot_db_status.get('started_at'),
        })

    return jsonify({'status': 'success', 'bots': statuses})


@bot_manager_bp.route('/start', methods=['POST'])
def start_bot():
    """
    Start igbot.exe for specific device

    Request body:
        {
            "device_serial": "10.1.10.192_5555",
            "bot_type": "igbot" (optional, default) or "device_bot"
        }
    """
    print("\n" + "="*70)
    print("START BOT REQUEST RECEIVED")
    print("="*70)

    data = request.get_json()
    print(f"Request data: {data}")

    device_serial = data.get('device_serial')
    bot_type = data.get('bot_type', 'igbot')  # Default to igbot.exe

    print(f"Device serial: {device_serial}")
    print(f"Bot type: {bot_type}")

    if not device_serial:
        print("ERROR: No device_serial provided")
        return jsonify({'status': 'error', 'message': 'device_serial required'}), 400

    # Check if device folder exists
    device_folder = get_device_folder(device_serial)
    if not device_folder.exists():
        return jsonify({'status': 'error', 'message': f'Device folder not found: {device_serial}'}), 404

    # Check if already running
    existing_pids = read_device_pid(device_serial)
    running_pids = [pid for pid in existing_pids if is_process_running(pid)]

    if running_pids:
        return jsonify({
            'status': 'error',
            'message': f'Bot already running for {device_serial}',
            'pids': running_pids
        }), 400

    try:
        if bot_type == 'igbot':
            # Launch igbot.exe (Onimator's bot)
            igbot_exe = get_igbot_exe_path()

            if not igbot_exe.exists():
                return jsonify({
                    'status': 'error',
                    'message': f'igbot.exe not found at {igbot_exe}'
                }), 404

            # Start igbot.exe with device serial as argument
            # IMPORTANT: igbot.exe must run from root directory (where igbot.exe is located)
            # because it needs to access database files in that directory
            root_dir = get_root_dir()

            print(f"Starting igbot.exe for {device_serial}...")
            print(f"Command: {igbot_exe} {device_serial}")
            print(f"Working directory: {root_dir}")
            print(f"igbot.exe exists: {igbot_exe.exists()}")
            print(f"Device folder exists: {device_folder.exists()}")

            process = subprocess.Popen(
                [str(igbot_exe), device_serial],
                cwd=str(root_dir),  # Run from root directory, not device folder
                creationflags=subprocess.CREATE_NEW_CONSOLE  # Create separate console window
            )

            print(f"Process started with PID: {process.pid}")
            print("Waiting 2 seconds to check if process stays alive...")
            time.sleep(2)

            # Check if process is still running
            poll_result = process.poll()
            if poll_result is not None:
                # Process already exited
                print(f"ERROR: Process exited immediately with code {poll_result}")
                return jsonify({
                    'status': 'error',
                    'message': f'Process exited immediately with code {poll_result}'
                }), 500

            print(f"SUCCESS: Process still running after 2 seconds")

            # Write PID to device folder
            write_device_pid(device_serial, process.pid)

            # Track process in memory
            running_bots[device_serial] = process

            return jsonify({
                'status': 'success',
                'message': f'Started igbot.exe for {device_serial}',
                'pid': process.pid,
                'bot_type': 'igbot'
            })

        elif bot_type == 'device_bot':
            # Launch our new device_bot.py
            uiautomator_dir = get_root_dir() / "uiAutomator"

            print(f"Starting device_bot.py for {device_serial}...")

            process = subprocess.Popen(
                [sys.executable, 'device_bot.py', '--device', device_serial],
                cwd=str(uiautomator_dir),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            )

            # Update bot database
            update_bot_status(device_serial, 'running', pid=process.pid)

            # Track process in memory
            running_bots[device_serial] = process

            return jsonify({
                'status': 'success',
                'message': f'Started device_bot.py for {device_serial}',
                'pid': process.pid,
                'bot_type': 'device_bot'
            })

        else:
            return jsonify({'status': 'error', 'message': f'Unknown bot_type: {bot_type}'}), 400

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to start bot: {str(e)}'
        }), 500


@bot_manager_bp.route('/stop', methods=['POST'])
def stop_bot():
    """
    Stop bot for specific device

    Request body:
        {"device_serial": "10.1.10.192_5555"}
    """
    data = request.get_json()
    device_serial = data.get('device_serial')

    if not device_serial:
        return jsonify({'status': 'error', 'message': 'device_serial required'}), 400

    # Read PIDs from device folder
    pids = read_device_pid(device_serial)

    if not pids:
        return jsonify({'status': 'error', 'message': 'No PIDs found for device'}), 404

    # Kill all processes
    killed_pids = []
    failed_pids = []

    for pid in pids:
        if is_process_running(pid):
            if kill_process(pid):
                killed_pids.append(pid)
            else:
                failed_pids.append(pid)

    # Clear pid file
    pid_file = get_device_folder(device_serial) / "pid"
    if pid_file.exists():
        pid_file.write_text('')

    # Update bot database
    update_bot_status(device_serial, 'stopped')

    # Remove from memory cache
    if device_serial in running_bots:
        del running_bots[device_serial]

    return jsonify({
        'status': 'success',
        'message': f'Stopped bot for {device_serial}',
        'killed_pids': killed_pids,
        'failed_pids': failed_pids
    })


@bot_manager_bp.route('/<device_serial>/sessions', methods=['GET'])
def get_device_sessions(device_serial):
    """Get recent sessions for device"""
    limit = request.args.get('limit', 50, type=int)

    try:
        sessions = query_account_sessions(device_serial, limit=limit)
        return jsonify({'status': 'success', 'sessions': sessions})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bot_manager_bp.route('/<device_serial>/metrics', methods=['GET'])
def get_device_metrics(device_serial):
    """Get today's metrics for device"""
    try:
        metrics = calculate_device_metrics(device_serial)
        return jsonify({'status': 'success', 'metrics': metrics})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bot_manager_bp.route('/<device_serial>/status', methods=['GET'])
def get_device_status(device_serial):
    """Get detailed status for specific device"""

    # Check PIDs
    pids = read_device_pid(device_serial)
    running_pids = [pid for pid in pids if is_process_running(pid)]

    # Get bot database status
    bot_db_status = get_bot_status(device_serial)

    # Get recent sessions
    recent_sessions = query_account_sessions(device_serial, limit=5)

    # Get today's metrics
    metrics = calculate_device_metrics(device_serial)

    return jsonify({
        'status': 'success',
        'device_serial': device_serial,
        'bot_status': {
            'pids': running_pids,
            'is_running': len(running_pids) > 0,
            'db_status': bot_db_status.get('status'),
            'started_at': bot_db_status.get('started_at'),
        },
        'recent_sessions': recent_sessions,
        'metrics': metrics
    })


@bot_manager_bp.route('/init/<device_serial>', methods=['POST'])
def init_device_bot(device_serial):
    """Initialize bot database for device"""
    try:
        init_bot_database(device_serial)
        return jsonify({
            'status': 'success',
            'message': f'Initialized bot database for {device_serial}'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bot_manager_bp.route('/<device_serial>/accounts', methods=['GET'])
def get_device_accounts(device_serial):
    """
    Get all accounts for a specific device with their stats.
    Reads from phone_farm.db (single source of truth),
    falls back to old per-device accounts.db if phone_farm.db has no results.
    """
    import sqlite3

    # ── Try phone_farm.db first (new system) ──
    phone_farm_db = get_root_dir() / 'db' / 'phone_farm.db'
    if phone_farm_db.exists():
        try:
            conn = sqlite3.connect(str(phone_farm_db))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT username, password, instagram_package, status,
                       follow_enabled, unfollow_enabled, like_enabled,
                       comment_enabled, story_enabled,
                       start_time, end_time,
                       follow_limit_perday, unfollow_limit_perday, like_limit_perday,
                       follow_action, unfollow_action, random_action, random_delay,
                       follow_delay, unfollow_delay, like_delay
                FROM accounts
                WHERE device_serial = ?
                ORDER BY username
            """, (device_serial,))
            rows = cursor.fetchall()

            if rows:
                accounts = []
                for row in rows:
                    a = dict(row)
                    # Map to field names the modal JS expects
                    a['account'] = a.pop('username', '')
                    a.setdefault('followers', 0)
                    a.setdefault('following', 0)
                    a.setdefault('followed_today', 0)
                    a.setdefault('unfollowed_today', 0)
                    # Map toggle names for the settings view
                    a['follow'] = a.get('follow_enabled', 'False')
                    a['unfollow'] = a.get('unfollow_enabled', 'False')
                    a['like'] = a.get('like_enabled', 'False')
                    a['comment'] = a.get('comment_enabled', 'False')
                    a['story'] = a.get('story_enabled', 'False')
                    accounts.append(a)

                conn.close()
                return jsonify({
                    'status': 'success',
                    'device_serial': device_serial,
                    'accounts': accounts,
                    'count': len(accounts)
                })
            conn.close()
        except Exception as e:
            print(f"[bot_manager] phone_farm.db error for {device_serial}: {e}")

    # ── Fallback: old per-device accounts.db ──
    device_folder = get_device_folder(device_serial)
    accounts_db = device_folder / 'accounts.db'

    if not accounts_db.exists():
        return jsonify({
            'status': 'error',
            'message': f'No accounts found for device {device_serial}'
        }), 404

    try:
        conn = sqlite3.connect(str(accounts_db))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(accounts)")
        columns = {col[1] for col in cursor.fetchall()}

        select_cols = ['account']
        optional_cols = [
            'password', 'followers', 'following', 'followed', 'unfollowed',
            'liked', 'commented', 'story_viewed', 'dm_sent',
            'follow', 'unfollow', 'like', 'comment', 'story'
        ]
        for col in optional_cols:
            if col in columns:
                select_cols.append('`like`' if col == 'like' else col)

        cursor.execute(f"SELECT {', '.join(select_cols)} FROM accounts")
        rows = cursor.fetchall()

        accounts = []
        for row in rows:
            account_data = dict(row)
            if 'like' in account_data:
                account_data['like_enabled'] = account_data.pop('like')
            account_data.setdefault('followers', 0)
            account_data.setdefault('following', 0)
            account_data.setdefault('followed_today', account_data.get('followed', 0))
            account_data.setdefault('unfollowed_today', account_data.get('unfollowed', 0))
            accounts.append(account_data)

        conn.close()
        return jsonify({
            'status': 'success',
            'device_serial': device_serial,
            'accounts': accounts,
            'count': len(accounts)
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
