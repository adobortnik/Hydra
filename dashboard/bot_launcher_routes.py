"""
Bot Launcher Routes — Dashboard API for run_device.py processes.
================================================================
Blueprint: bot_launcher_bp, prefix: /api/bot

Endpoints:
    GET  /api/bot/status           → status of all running bot processes
    POST /api/bot/launch-all       → launch all devices
    POST /api/bot/launch/<serial>  → launch a single device
    POST /api/bot/stop-all         → stop all bots
    POST /api/bot/stop/<serial>    → stop a single device bot
    GET  /api/bot/logs/<serial>    → get recent log output for a device
"""

import os
import sys
import re
import subprocess
import sqlite3
import datetime
import time
import glob

from flask import Blueprint, jsonify, request
from phone_farm_db import update_device_status

bot_launcher_bp = Blueprint('bot_launcher', __name__, url_prefix='/api/bot')

# Paths
FARM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(FARM_DIR, 'db', 'phone_farm.db')
LOG_DIR = os.path.join(FARM_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
RUN_DEVICE_SCRIPT = os.path.join(FARM_DIR, 'run_device.py')

# Use venv python if available, else sys.executable
PYTHON_EXE = os.path.join(FARM_DIR, 'venv', 'Scripts', 'python.exe')
if not os.path.exists(PYTHON_EXE):
    PYTHON_EXE = sys.executable


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _get_all_devices():
    """Get all devices from the DB that have at least one active account."""
    conn = _get_db()
    rows = conn.execute("""
        SELECT d.device_serial, d.device_name, d.ip_address,
               COUNT(a.id) as account_count
        FROM devices d
        LEFT JOIN accounts a ON a.device_serial = d.device_serial AND a.status = 'active'
        GROUP BY d.device_serial
        ORDER BY d.device_name
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_device_active_account(serial):
    """Get the currently active account for a device (based on time window)."""
    conn = _get_db()
    rows = conn.execute("""
        SELECT username, start_time, end_time
        FROM accounts
        WHERE device_serial = ? AND status = 'active'
        ORDER BY start_time
    """, (serial,)).fetchall()
    conn.close()

    now_hour = datetime.datetime.now().hour
    # First pass: specific windows
    for r in rows:
        start = int(r['start_time'] or 0)
        end = int(r['end_time'] or 0)
        if start == end:
            continue
        if start < end and start <= now_hour < end:
            return r['username']
        if start > end and (now_hour >= start or now_hour < end):
            return r['username']
    # Second pass: always-active
    for r in rows:
        start = int(r['start_time'] or 0)
        end = int(r['end_time'] or 0)
        if start == end:
            return r['username']
    return None


# ---------------------------------------------------------------------------
# Process helpers (Windows)
# ---------------------------------------------------------------------------

def _find_run_device_processes():
    """
    Find all python processes running run_device.py.
    Returns list of dicts: {pid, serial, cmdline}
    """
    processes = []
    try:
        result = subprocess.run(
            ['wmic', 'process', 'where',
             "name like '%python%'",
             'get', 'ProcessId,CommandLine', '/format:csv'],
            capture_output=True, text=True, timeout=15
        )
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('Node,'):
                continue
            parts = line.split(',')
            if len(parts) < 3:
                continue
            pid_str = parts[-1].strip()
            cmdline = ','.join(parts[1:-1]).strip()

            if 'run_device.py' in cmdline and pid_str.isdigit():
                serial_match = re.search(r'run_device\.py["\s]*\s+(\S+)', cmdline)
                serial_raw = serial_match.group(1) if serial_match else '?'
                # Normalize to DB format (underscore)
                serial_db = serial_raw.replace(':', '_')
                processes.append({
                    'pid': int(pid_str),
                    'serial': serial_db,
                    'cmdline': cmdline,
                })
    except Exception as e:
        print(f'[bot_launcher] Error scanning processes: {e}')
    return processes


def _find_process_for_serial(serial):
    """Find PID(s) for a specific device serial."""
    serial_db = serial.replace(':', '_')
    procs = _find_run_device_processes()
    return [p for p in procs if p['serial'] == serial_db]


def _kill_pid(pid, force=True):
    """Kill a process by PID."""
    try:
        flag = '/F' if force else ''
        cmd = ['taskkill', '/PID', str(pid)]
        if force:
            cmd.append('/F')
        subprocess.run(cmd, capture_output=True, timeout=10)
        return True
    except Exception as e:
        print(f'[bot_launcher] Failed to kill PID {pid}: {e}')
        return False


def _launch_device(serial_db):
    """
    Launch run_device.py for a device in a new cmd window.
    serial_db should be DB format (underscore). Converts to ADB format for the script.
    Returns (success: bool, info: dict).
    """
    adb_serial = serial_db.replace('_', ':')

    # Get device name for window title
    conn = _get_db()
    row = conn.execute('SELECT device_name FROM devices WHERE device_serial=?', (serial_db,)).fetchone()
    conn.close()
    device_name = row['device_name'] if row else serial_db

    title = f'Phone Farm - {device_name}'

    # Write a small batch launcher that keeps the window open and shows output
    bat_file = os.path.join(FARM_DIR, 'logs', f'_launch_{serial_db}.bat')
    with open(bat_file, 'w') as f:
        f.write(f'@echo off\n')
        f.write(f'title {title}\n')
        f.write(f'cd /d "{FARM_DIR}"\n')
        f.write(f'echo Starting bot for {device_name} ({adb_serial})...\n')
        f.write(f'echo.\n')
        f.write(f'"{PYTHON_EXE}" -u "{RUN_DEVICE_SCRIPT}" {adb_serial}\n')
        f.write(f'echo.\n')
        f.write(f'echo Bot exited. Press any key to close.\n')
        f.write(f'pause >nul\n')

    try:
        proc = subprocess.Popen(
            ['cmd', '/c', 'start', '', bat_file],
            shell=False, cwd=FARM_DIR
        )
        time.sleep(0.5)
        return True, {'serial': serial_db, 'device_name': device_name}
    except Exception as e:
        return False, {'error': str(e)}


# ---------------------------------------------------------------------------
# Log helpers
# ---------------------------------------------------------------------------

def _get_log_file(serial_db, date_str=None):
    """Get the log file path for a device. Uses today's date if not specified."""
    if date_str is None:
        date_str = datetime.date.today().strftime('%Y-%m-%d')
    return os.path.join(LOG_DIR, f'{serial_db}_{date_str}.log')


def _tail_log(filepath, lines=100):
    """Read the last N lines of a log file."""
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()
            return [l.rstrip('\n\r') for l in all_lines[-lines:]]
    except Exception as e:
        return [f'Error reading log: {e}']


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@bot_launcher_bp.route('/status', methods=['GET'])
def bot_status():
    """
    GET /api/bot/status
    Returns status of all devices and whether their run_device.py process is running.
    """
    devices = _get_all_devices()
    running_procs = _find_run_device_processes()

    # Build a map: serial -> process info
    running_map = {}
    for p in running_procs:
        running_map[p['serial']] = p

    result = []
    for dev in devices:
        serial = dev['device_serial']
        proc = running_map.get(serial)
        is_running = proc is not None

        # Get current active account
        account = _get_device_active_account(serial) if is_running else None

        result.append({
            'serial': serial,
            'device_name': dev['device_name'],
            'ip_address': dev['ip_address'],
            'account_count': dev['account_count'],
            'running': is_running,
            'pid': proc['pid'] if proc else None,
            'account': account,
        })

    running_count = sum(1 for d in result if d['running'])

    return jsonify({
        'success': True,
        'devices': result,
        'total': len(result),
        'running': running_count,
        'stopped': len(result) - running_count,
    })


@bot_launcher_bp.route('/launch-all', methods=['POST'])
def launch_all():
    """
    POST /api/bot/launch-all
    Launch run_device.py for all (or specified) devices.
    Body (optional): {"devices": ["10.1.11.4:5555", ...], "delay": 2}
    """
    data = request.get_json(silent=True) or {}
    requested_serials = data.get('devices', None)
    delay = data.get('delay', 2.0)

    # Get running processes first
    running_procs = _find_run_device_processes()
    running_serials = {p['serial'] for p in running_procs}

    # Determine which devices to launch
    if requested_serials:
        # Normalize requested serials
        serials_to_launch = [s.replace(':', '_') for s in requested_serials]
    else:
        # All devices with active accounts
        devices = _get_all_devices()
        serials_to_launch = [d['device_serial'] for d in devices if d['account_count'] > 0]

    launched = []
    skipped = []
    failed = []

    for serial in serials_to_launch:
        if serial in running_serials:
            skipped.append({'serial': serial, 'reason': 'already running'})
            continue

        success, info = _launch_device(serial)
        if success:
            launched.append(info)
            try:
                update_device_status(serial, 'connected')
            except Exception:
                pass
        else:
            failed.append({'serial': serial, 'error': info.get('error', 'unknown')})

        # Delay between launches to avoid overwhelming the system
        if delay > 0 and serial != serials_to_launch[-1]:
            time.sleep(delay)

    return jsonify({
        'success': True,
        'launched': len(launched),
        'skipped': len(skipped),
        'failed': len(failed),
        'devices': launched,
        'skipped_details': skipped,
        'failed_details': failed,
    })


@bot_launcher_bp.route('/launch/<serial>', methods=['POST'])
def launch_single(serial):
    """
    POST /api/bot/launch/<serial>
    Launch run_device.py for a single device.
    Serial can be in either format (colon or underscore).
    """
    serial_db = serial.replace(':', '_')

    # Check if already running
    existing = _find_process_for_serial(serial_db)
    if existing:
        return jsonify({
            'success': False,
            'error': 'already_running',
            'message': f'Bot already running for {serial_db}',
            'pid': existing[0]['pid'],
        }), 409

    # Verify device exists in DB
    conn = _get_db()
    row = conn.execute('SELECT device_serial, device_name FROM devices WHERE device_serial=?',
                       (serial_db,)).fetchone()
    conn.close()

    if not row:
        return jsonify({
            'success': False,
            'error': 'not_found',
            'message': f'Device {serial_db} not found in database',
        }), 404

    success, info = _launch_device(serial_db)
    if success:
        # Re-check for the actual PID (takes a moment to show up)
        time.sleep(1.5)
        procs = _find_process_for_serial(serial_db)
        pid = procs[0]['pid'] if procs else None

        # Mark device as connected/online
        try:
            update_device_status(serial_db, 'connected')
        except Exception:
            pass

        return jsonify({
            'success': True,
            'serial': serial_db,
            'device_name': info.get('device_name'),
            'pid': pid,
            'status': 'launched',
        })
    else:
        return jsonify({
            'success': False,
            'error': 'launch_failed',
            'message': info.get('error', 'Unknown error'),
        }), 500


@bot_launcher_bp.route('/stop-all', methods=['POST'])
def stop_all():
    """
    POST /api/bot/stop-all
    Stop all running run_device.py processes.
    """
    processes = _find_run_device_processes()

    if not processes:
        return jsonify({
            'success': True,
            'stopped': 0,
            'message': 'No bot processes were running',
        })

    stopped = 0
    failed = 0
    details = []

    for p in processes:
        if _kill_pid(p['pid']):
            stopped += 1
            details.append({'serial': p['serial'], 'pid': p['pid'], 'status': 'stopped'})
            try:
                update_device_status(p['serial'], 'disconnected')
            except Exception:
                pass
        else:
            failed += 1
            details.append({'serial': p['serial'], 'pid': p['pid'], 'status': 'failed'})

    # Also try to clean up parent cmd windows hosting run_device.py
    try:
        result = subprocess.run(
            ['wmic', 'process', 'where',
             "name like '%cmd%'",
             'get', 'ProcessId,CommandLine', '/format:csv'],
            capture_output=True, text=True, timeout=15
        )
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('Node,'):
                continue
            parts = line.split(',')
            if len(parts) < 3:
                continue
            pid_str = parts[-1].strip()
            cmdline = ','.join(parts[1:-1]).strip()
            if 'run_device.py' in cmdline and pid_str.isdigit():
                _kill_pid(int(pid_str))
    except Exception:
        pass

    return jsonify({
        'success': True,
        'stopped': stopped,
        'failed': failed,
        'details': details,
    })


@bot_launcher_bp.route('/stop/<serial>', methods=['POST'])
def stop_single(serial):
    """
    POST /api/bot/stop/<serial>
    Stop the run_device.py process for a specific device.
    """
    serial_db = serial.replace(':', '_')
    procs = _find_process_for_serial(serial_db)

    if not procs:
        return jsonify({
            'success': False,
            'error': 'not_running',
            'message': f'No bot process found for {serial_db}',
        }), 404

    stopped = 0
    for p in procs:
        if _kill_pid(p['pid']):
            stopped += 1

    if stopped > 0:
        try:
            update_device_status(serial_db, 'disconnected')
        except Exception:
            pass

    return jsonify({
        'success': True,
        'serial': serial_db,
        'stopped': stopped,
        'status': 'stopped',
    })


@bot_launcher_bp.route('/logs/<serial>', methods=['GET'])
def get_logs(serial):
    """
    GET /api/bot/logs/<serial>
    Get recent log output for a device.
    Query params: lines (default 100), date (YYYY-MM-DD, default today)
    """
    serial_db = serial.replace(':', '_')
    lines_count = request.args.get('lines', 100, type=int)
    date_str = request.args.get('date', None)

    log_file = _get_log_file(serial_db, date_str)

    if not os.path.exists(log_file):
        # Try to find any log file for this device
        pattern = os.path.join(LOG_DIR, f'{serial_db}_*.log')
        available = sorted(glob.glob(pattern), reverse=True)

        if available:
            log_file = available[0]
        else:
            return jsonify({
                'success': True,
                'serial': serial_db,
                'lines': [],
                'message': 'No log files found for this device',
                'log_file': None,
            })

    lines = _tail_log(log_file, lines_count)

    return jsonify({
        'success': True,
        'serial': serial_db,
        'lines': lines,
        'line_count': len(lines),
        'log_file': os.path.basename(log_file),
    })
