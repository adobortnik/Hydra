"""
Device Manager Routes
======================
Two-level device management UI:
  Level 1: /device-manager           → All devices overview
  Level 2: /device-manager/<serial>  → Device detail with accounts + stats

API endpoints:
  GET /api/device-manager/devices           → all devices with account counts
  GET /api/device-manager/devices/<serial>  → single device + accounts + stats
  GET /api/device-manager/accounts/<serial> → accounts with today/yesterday stats
  GET /api/watchdog/status                  → watchdog process status
"""

import os
import sys
import json
import sqlite3
import subprocess
import threading
import time
import concurrent.futures
from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify, request

# DB path
DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'db', 'phone_farm.db'
)

device_manager_bp = Blueprint('device_manager', __name__)


def _get_conn():
    """Thread-safe connection with Row factory."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# Auto-create missing tables on import
try:
    import sys as _sys
    _migrations_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _migrations_dir not in _sys.path:
        _sys.path.insert(0, _migrations_dir)
    from db.migrations import ensure_schema
    ensure_schema()
except Exception as _e:
    # Fallback: create the most critical missing table inline
    try:
        _conn = sqlite3.connect(DB_PATH)
        _conn.executescript("""
            CREATE TABLE IF NOT EXISTS follower_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                username TEXT,
                followers INTEGER DEFAULT 0,
                following INTEGER DEFAULT 0,
                posts INTEGER DEFAULT 0,
                captured_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            );
            CREATE TABLE IF NOT EXISTS job_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_name TEXT, job_type TEXT NOT NULL, target TEXT,
                target_count INTEGER DEFAULT 0, completed_count INTEGER DEFAULT 0,
                limit_per_hour INTEGER DEFAULT 50, limit_per_day INTEGER DEFAULT 200,
                comment_text TEXT, status TEXT DEFAULT 'active', priority INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')), updated_at TEXT,
                report_reason TEXT, comment_list_id INTEGER, ai_mode TEXT,
                vision_ai INTEGER DEFAULT 0, finished_at TEXT
            );
            CREATE TABLE IF NOT EXISTS job_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL, account_id INTEGER NOT NULL,
                device_serial TEXT, username TEXT, status TEXT DEFAULT 'assigned',
                completed_count INTEGER DEFAULT 0, last_action_at TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS job_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL, account_id INTEGER NOT NULL,
                action_type TEXT, target TEXT, status TEXT, error_message TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        _conn.commit()
        _conn.close()
    except Exception:
        pass


def _row_to_dict(row):
    return dict(row) if row else None


def _rows_to_dicts(rows):
    return [dict(r) for r in rows] if rows else []


def _today():
    return datetime.utcnow().strftime('%Y-%m-%d')


def _yesterday():
    return (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')


# ── Page Routes ──────────────────────────────────────────────────────

@device_manager_bp.route('/device-manager')
def device_manager_page():
    """Level 1: Device list overview."""
    return render_template('device_manager.html')


@device_manager_bp.route('/device-manager/<path:device_serial>')
def device_manager_detail_page(device_serial):
    """Level 2: Device accounts detail."""
    return render_template('device_manager_detail.html', device_serial=device_serial)


# ── API: All Devices ────────────────────────────────────────────────

@device_manager_bp.route('/api/device-manager/devices')
def api_dm_devices():
    """List all devices with account counts and bot status."""
    conn = _get_conn()
    try:
        devices = _rows_to_dicts(conn.execute("""
            SELECT d.*,
                   COUNT(a.id) as account_count
            FROM devices d
            LEFT JOIN accounts a ON a.device_serial = d.device_serial
            GROUP BY d.id
            ORDER BY d.created_at ASC, d.device_serial
        """).fetchall())

        # Attach bot_status — detect from log files (most reliable)
        import os as _os
        from datetime import datetime as _dt, timedelta as _td
        logs_dir = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), 'logs')
        today_str = _dt.utcnow().strftime('%Y-%m-%d')
        hung_threshold = _td(minutes=10)  # no log activity for 10min = hung

        for dev in devices:
            serial = dev['device_serial']
            dev['bot_status'] = 'stopped'
            dev['bot_pid'] = None
            dev['bot_started_at'] = None
            dev['bot_last_check'] = None

            # Check today's log file modification time
            log_file = _os.path.join(logs_dir, f"{serial}_{today_str}.log")
            if _os.path.exists(log_file):
                mtime = _dt.utcfromtimestamp(_os.path.getmtime(log_file))
                age = _dt.utcnow() - mtime
                if age < hung_threshold:
                    dev['bot_status'] = 'active'
                elif age < _td(hours=2):
                    dev['bot_status'] = 'hung'
                # else stays 'stopped'
                dev['bot_last_check'] = mtime.isoformat()

            # Also check bot_status table for PID info
            bs = conn.execute(
                "SELECT pid, started_at FROM bot_status WHERE device_serial = ?",
                (serial,)
            ).fetchone()
            if bs:
                dev['bot_pid'] = bs['pid']
                dev['bot_started_at'] = bs['started_at']

        return jsonify({'devices': devices, 'total': len(devices)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


# ── API: Single Device Detail ───────────────────────────────────────

@device_manager_bp.route('/api/device-manager/devices/<path:serial>')
def api_dm_device_detail(serial):
    """Single device with all accounts + stats for a given date (default: today)."""
    target_date = request.args.get('date', None)  # YYYY-MM-DD or None
    conn = _get_conn()
    try:
        device = _row_to_dict(conn.execute(
            "SELECT * FROM devices WHERE device_serial = ?", (serial,)
        ).fetchone())

        if not device:
            return jsonify({'error': f'Device {serial} not found'}), 404

        # Get accounts with stats
        accounts = _get_accounts_with_stats(conn, serial, target_date=target_date)

        # Get bot status — detect from log files
        import os as _os2
        from datetime import datetime as _dt2, timedelta as _td2
        logs_dir2 = _os2.path.join(_os2.path.dirname(_os2.path.dirname(__file__)), 'logs')
        today_log = _os2.path.join(logs_dir2, f"{serial}_{_dt2.utcnow().strftime('%Y-%m-%d')}.log")
        bot_stat = 'stopped'
        if _os2.path.exists(today_log):
            age2 = _dt2.utcnow() - _dt2.utcfromtimestamp(_os2.path.getmtime(today_log))
            if age2 < _td2(minutes=10):
                bot_stat = 'active'
            elif age2 < _td2(hours=2):
                bot_stat = 'hung'
        bs = conn.execute(
            "SELECT * FROM bot_status WHERE device_serial = ?", (serial,)
        ).fetchone()
        bot_info = _row_to_dict(bs) if bs else {}
        bot_info['status'] = bot_stat
        device['bot_status'] = bot_info

        return jsonify({
            'device': device,
            'accounts': accounts,
            'total_accounts': len(accounts),
            'date': target_date or _today()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


# ── API: Accounts for Device ────────────────────────────────────────

@device_manager_bp.route('/api/device-manager/accounts/<path:serial>')
def api_dm_accounts(serial):
    """Accounts for a device with stats + yesterday comparison for a given date."""
    target_date = request.args.get('date', None)  # YYYY-MM-DD or None
    conn = _get_conn()
    try:
        accounts = _get_accounts_with_stats(conn, serial, target_date=target_date)
        return jsonify({
            'accounts': accounts,
            'total': len(accounts),
            'date': target_date or _today()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


def _get_accounts_with_stats(conn, device_serial, target_date=None):
    """Get accounts with stats from action_history (source of truth).
    
    The account_stats table only has followers/following counts from syncs.
    Action counts (follows, unfollows, likes, etc.) come from action_history.
    
    Args:
        target_date: YYYY-MM-DD string to query. Defaults to today (UTC).
                     "Yesterday" comparison is always target_date - 1 day.
    """
    if target_date:
        # Validate format
        try:
            parsed = datetime.strptime(target_date, '%Y-%m-%d')
            today = target_date
            yesterday = (parsed - timedelta(days=1)).strftime('%Y-%m-%d')
        except ValueError:
            # Bad format -- fall back to actual today
            today = _today()
            yesterday = _yesterday()
    else:
        today = _today()
        yesterday = _yesterday()

    # Get base account info + followers/following from follower_snapshots (latest per account)
    rows = conn.execute("""
        SELECT a.id, a.device_serial, a.username, a.status,
               a.start_time, a.end_time, a.instagram_package,
               a.follow_enabled, a.unfollow_enabled, a.like_enabled,
               a.comment_enabled, a.story_enabled,
               a.is_business_profile, a.business_category,
               COALESCE(snap_today.followers, a.followers, 0) as followers,
               COALESCE(snap_today.following, a.following, 0) as following,
               snap_yesterday.followers as prev_followers,
               snap_yesterday.following as prev_following
        FROM accounts a
        LEFT JOIN (
            SELECT account_id, followers, following,
                   ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY captured_at DESC) as rn
            FROM follower_snapshots
            WHERE captured_at >= ?
        ) snap_today ON snap_today.account_id = a.id AND snap_today.rn = 1
        LEFT JOIN (
            SELECT account_id, followers, following,
                   ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY captured_at DESC) as rn
            FROM follower_snapshots
            WHERE captured_at >= ? AND captured_at < ?
        ) snap_yesterday ON snap_yesterday.account_id = a.id AND snap_yesterday.rn = 1
        WHERE a.device_serial = ?
        ORDER BY CAST(COALESCE(a.start_time, '0') AS INTEGER), a.username
    """, (today, yesterday, today, device_serial)).fetchall()

    # Get action counts for the target date from action_history
    next_day = (datetime.strptime(today, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    action_counts = conn.execute("""
        SELECT username, action_type, COUNT(*) as cnt
        FROM action_history
        WHERE device_serial = ?
          AND timestamp >= ?
          AND timestamp < ?
          AND success = 1
        GROUP BY username, action_type
    """, (device_serial, today, next_day)).fetchall()
    
    # Build lookup: username -> {action_type: count}
    counts_by_user = {}
    for row in action_counts:
        user = row['username']
        if user not in counts_by_user:
            counts_by_user[user] = {}
        counts_by_user[user][row['action_type']] = row['cnt']

    accounts = []
    for row in rows:
        acct = dict(row)
        username = acct['username']
        user_counts = counts_by_user.get(username, {})
        
        # Map action_history types to display columns
        acct['follows_done'] = user_counts.get('follow', 0)
        acct['unfollows_done'] = user_counts.get('unfollow', 0)
        acct['likes_done'] = user_counts.get('like', 0) + user_counts.get('reel_like', 0)
        acct['comments_done'] = user_counts.get('comment', 0)
        acct['stories_viewed'] = user_counts.get('story_view', 0)
        acct['dms_sent'] = user_counts.get('dm', 0)
        
        # Compute deltas for followers/following
        try:
            f_today = int(acct['followers']) if acct['followers'] else 0
            f_prev = int(acct['prev_followers']) if acct['prev_followers'] else None
            if f_prev is not None:
                acct['followers_delta'] = f_today - f_prev
            else:
                acct['followers_delta'] = None
        except (ValueError, TypeError):
            acct['followers_delta'] = None

        try:
            fw_today = int(acct['following']) if acct['following'] else 0
            fw_prev = int(acct['prev_following']) if acct['prev_following'] else None
            if fw_prev is not None:
                acct['following_delta'] = fw_today - fw_prev
            else:
                acct['following_delta'] = None
        except (ValueError, TypeError):
            acct['following_delta'] = None

        accounts.append(acct)

    return accounts


# ── API: Screen Mirror (scrcpy) ─────────────────────────────────────

@device_manager_bp.route('/api/device-manager/<path:serial>/mirror')
def api_mirror_device(serial):
    """Launch scrcpy to mirror a device screen."""
    import subprocess, os
    adb_serial = serial.replace('_', ':')

    scrcpy_path = r'C:\tools\scrcpy\scrcpy-win64-v3.1\scrcpy.exe'
    if not os.path.exists(scrcpy_path):
        return jsonify(success=False, error='scrcpy not found. Install it to C:\\tools\\scrcpy\\')

    try:
        # Launch scrcpy detached (non-blocking)
        subprocess.Popen(
            [scrcpy_path, '-s', adb_serial, '--window-title', f'Mirror: {serial}',
             '--max-size', '800', '--stay-awake', '--no-audio'],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
        return jsonify(success=True, message=f'Mirroring started for {serial}')
    except Exception as e:
        return jsonify(success=False, error=str(e))


# ── API: Detect Foreground App ──────────────────────────────────────

@device_manager_bp.route('/api/device-manager/<path:serial>/detect-foreground-app')
def api_detect_foreground_app(serial):
    """Detect the currently running foreground app on a device via ADB."""
    import subprocess
    adb_serial = serial.replace('_', ':')
    try:
        result = subprocess.run(
            ['adb', '-s', adb_serial, 'shell', 'dumpsys', 'window', 'windows'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return jsonify(success=False, error=f'ADB error: {result.stderr[:200]}')

        # Parse mCurrentFocus or mFocusedApp to get package/activity
        package = None
        activity = None
        for line in result.stdout.splitlines():
            if 'mCurrentFocus' in line or 'mFocusedApp' in line:
                # Format: mCurrentFocus=Window{... com.package.name/com.activity.name}
                parts = line.split()
                for part in parts:
                    if '/' in part and '.' in part:
                        clean = part.lstrip('{').rstrip('}').strip()
                        slash_parts = clean.split('/', 1)
                        pkg = slash_parts[0]
                        act = slash_parts[1] if len(slash_parts) > 1 else None
                        if pkg.startswith('com.') or pkg.startswith('org.') or pkg.startswith('net.'):
                            package = pkg
                            activity = act
                            break
                if package:
                    break

        if not package:
            return jsonify(success=False, error='No foreground app detected. Open the app on the phone first.')

        # Return full package/activity string
        full_app_id = f"{package}/{activity}" if activity else package
        return jsonify(success=True, package=full_app_id)
    except subprocess.TimeoutExpired:
        return jsonify(success=False, error='ADB command timed out')
    except Exception as e:
        return jsonify(success=False, error=str(e))


# ── API: Update Device Group ────────────────────────────────────────

@device_manager_bp.route('/api/device-manager/update-group', methods=['POST'])
def api_update_device_group():
    """Update device_group tag for a device."""
    data = request.get_json() or {}
    device_id = data.get('device_id')
    group = data.get('device_group', '')

    if not device_id:
        return jsonify({'success': False, 'error': 'No device_id'}), 400

    try:
        from phone_farm_db import get_conn
        conn = get_conn()
        conn.execute("UPDATE devices SET device_group = ? WHERE id = ?", (group, device_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@device_manager_bp.route('/api/device-manager/bulk-group', methods=['POST'])
def api_bulk_update_group():
    """Set device_group for multiple devices at once."""
    data = request.get_json() or {}
    device_ids = data.get('device_ids', [])
    group = data.get('device_group', '')

    if not device_ids:
        return jsonify({'success': False, 'error': 'No devices selected'}), 400

    try:
        from phone_farm_db import get_conn
        conn = get_conn()
        placeholders = ','.join('?' * len(device_ids))
        conn.execute(f"UPDATE devices SET device_group = ? WHERE id IN ({placeholders})",
                     [group] + device_ids)
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'updated': len(device_ids)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── API: Update Account App ID ─────────────────────────────────────

@device_manager_bp.route('/api/device-manager/<path:serial>/update-app-id', methods=['POST'])
def api_update_app_id(serial):
    """Update instagram_package and app_cloner for an account."""
    data = request.get_json() or {}
    username = data.get('username')
    package = data.get('package')  # May be "com.instagram.androif/com.instagram.mainactivity.MainActivity"
    if not username or not package:
        return jsonify(success=False, error='username and package required')

    # Split into package-only and full app_id
    if '/' in package:
        pkg_only = package.split('/')[0]
        full_app_id = package
    else:
        pkg_only = package
        full_app_id = f"{package}/com.instagram.mainactivity.MainActivity"

    conn = _get_conn()
    try:
        # Update instagram_package column (package only — used as resource ID prefix)
        conn.execute(
            "UPDATE accounts SET instagram_package=? WHERE device_serial=? AND username=?",
            (pkg_only, serial, username)
        )

        # Update app_cloner in account_settings (full package/activity)
        row = conn.execute(
            "SELECT id FROM accounts WHERE device_serial=? AND username=?",
            (serial, username)
        ).fetchone()
        if row:
            account_id = row[0] if isinstance(row, tuple) else row['id']
            settings_row = conn.execute(
                "SELECT settings_json FROM account_settings WHERE account_id=?",
                (account_id,)
            ).fetchone()
            if settings_row:
                import json
                settings = json.loads(settings_row[0] if isinstance(settings_row, tuple) else settings_row['settings_json'] or '{}')
                settings['app_cloner'] = full_app_id
                conn.execute(
                    "UPDATE account_settings SET settings_json=? WHERE account_id=?",
                    (json.dumps(settings), account_id)
                )
            else:
                import json
                conn.execute(
                    "INSERT INTO account_settings (account_id, settings_json) VALUES (?, ?)",
                    (account_id, json.dumps({'app_cloner': full_app_id}))
                )

        conn.commit()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e))
    finally:
        conn.close()


# ── API: Watchdog Status ────────────────────────────────────────────

@device_manager_bp.route('/api/watchdog/status')
def api_watchdog_status():
    """
    Show watchdog-monitored bots: last log activity, status (active/hung/stopped).
    Checks log file modification times.
    """
    import glob

    conn = _get_conn()
    try:
        devices = _rows_to_dicts(conn.execute(
            "SELECT device_serial, device_name, status FROM devices ORDER BY device_serial"
        ).fetchall())

        logs_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'logs'
        )
        today = _today()
        now = datetime.utcnow()
        hung_threshold_minutes = 10

        results = []
        for dev in devices:
            serial = dev['device_serial']
            info = {
                'device_serial': serial,
                'device_name': dev['device_name'],
                'device_status': dev['status'],
                'bot_status': 'stopped',
                'last_activity': None,
                'log_file': None,
                'pid': None
            }

            # Check bot_status table
            bs = conn.execute(
                "SELECT status, pid, last_check_at FROM bot_status WHERE device_serial = ?",
                (serial,)
            ).fetchone()
            if bs:
                info['pid'] = bs['pid']

            # Check log file
            log_pattern = os.path.join(logs_dir, f"{serial}_{today}.log")
            if os.path.exists(log_pattern):
                mtime = os.path.getmtime(log_pattern)
                last_mod = datetime.utcfromtimestamp(mtime)
                info['last_activity'] = last_mod.isoformat()
                info['log_file'] = os.path.basename(log_pattern)

                age_minutes = (now - last_mod).total_seconds() / 60

                if age_minutes < hung_threshold_minutes:
                    info['bot_status'] = 'active'
                else:
                    info['bot_status'] = 'hung'
            else:
                # No log today — check if process is registered as running
                if bs and bs['status'] in ('running', 'active'):
                    info['bot_status'] = 'hung'
                else:
                    info['bot_status'] = 'stopped'

            results.append(info)

        return jsonify({
            'bots': results,
            'total': len(results),
            'timestamp': now.isoformat(),
            'hung_threshold_minutes': hung_threshold_minutes
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


# ── Fix Orientation ──────────────────────────────────────────────────

@device_manager_bp.route('/api/devices/fix-orientation', methods=['POST'])
def api_fix_orientation():
    """Force portrait orientation on one or all devices."""
    data = request.get_json(silent=True) or {}
    target = data.get('device')  # single serial or None for all

    if target:
        serials = [target]
    else:
        # All connected devices
        try:
            result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=10)
            serials = []
            for line in result.stdout.strip().split('\n')[1:]:
                if '\tdevice' in line:
                    serials.append(line.split('\t')[0])
        except:
            return jsonify({'ok': False, 'error': 'Could not list devices'}), 500

    if not serials:
        return jsonify({'ok': False, 'error': 'No devices found'}), 404

    fixed = 0
    errors = []
    for serial in serials:
        adb_serial = serial.replace('_', ':') if '_' in serial else serial
        try:
            cmds = [
                "settings put system accelerometer_rotation 0",
                "settings put system user_rotation 0",
                "content update --uri content://settings/system --bind value:i:0 --where \"name='accelerometer_rotation'\"",
            ]
            for cmd in cmds:
                subprocess.run(['adb', '-s', adb_serial, 'shell', cmd],
                               capture_output=True, timeout=10)

            # Also try wm rotation lock
            subprocess.run(['adb', '-s', adb_serial, 'shell', 'wm', 'set-user-rotation', 'lock'],
                           capture_output=True, timeout=10)
            subprocess.run(['adb', '-s', adb_serial, 'shell', 'wm', 'set-user-rotation', 'lock', '0'],
                           capture_output=True, timeout=10)

            fixed += 1
        except Exception as e:
            errors.append(f"{adb_serial}: {e}")

    return jsonify({
        'ok': True,
        'fixed': fixed,
        'total': len(serials),
        'errors': errors,
        'message': f'Fixed orientation on {fixed}/{len(serials)} device(s)',
    })


# ── Grant Permissions ────────────────────────────────────────────────
# Inline logic from grant_permissions.py — runs in background thread

_GRANT_PACKAGES = [f"com.instagram.androi{c}" for c in "efghijklmnop"]

_GRANT_PERMISSIONS = [
    "android.permission.CAMERA",
    "android.permission.RECORD_AUDIO",
    "android.permission.READ_EXTERNAL_STORAGE",
    "android.permission.WRITE_EXTERNAL_STORAGE",
    "android.permission.READ_MEDIA_IMAGES",
    "android.permission.READ_MEDIA_VIDEO",
    "android.permission.READ_MEDIA_AUDIO",
    "android.permission.ACCESS_MEDIA_LOCATION",
    "android.permission.ACCESS_FINE_LOCATION",
    "android.permission.ACCESS_COARSE_LOCATION",
]

# Shared state for background grant job
_grant_state = {
    'running': False,
    'progress': '',
    'devices_total': 0,
    'devices_done': 0,
    'clones_total': 0,
    'permissions_count': len(_GRANT_PERMISSIONS),
    'results': None,
    'error': None,
    'started_at': None,
    'finished_at': None,
}
_grant_lock = threading.Lock()


def _get_adb_devices():
    """Get list of connected ADB device serials."""
    try:
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=10)
        devices = []
        for line in result.stdout.strip().split("\n")[1:]:
            line = line.strip()
            if line and "\tdevice" in line:
                devices.append(line.split("\t")[0])
        return devices
    except Exception:
        return []


def _get_installed_ig_clones(serial):
    """Get list of installed IG clone packages on a device."""
    adb_serial = serial.replace('_', ':') if '_' in serial else serial
    try:
        result = subprocess.run(
            ["adb", "-s", adb_serial, "shell", "pm", "list", "packages", "com.instagram.androi"],
            capture_output=True, text=True, timeout=15
        )
        installed = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line.startswith("package:"):
                pkg = line.replace("package:", "")
                if pkg in _GRANT_PACKAGES:
                    installed.append(pkg)
        return installed
    except Exception:
        return []


def _grant_permissions_one_device(serial, packages_filter=None):
    """Grant all permissions to all IG clones on a single device. Returns clone count."""
    installed = _get_installed_ig_clones(serial)
    if packages_filter:
        installed = [p for p in installed if p in packages_filter]
    if not installed:
        return 0

    adb_serial = serial.replace('_', ':') if '_' in serial else serial
    granted = 0
    for pkg in installed:
        cmds = " ; ".join([f"pm grant {pkg} {p} 2>/dev/null" for p in _GRANT_PERMISSIONS])
        try:
            subprocess.run(
                ["adb", "-s", adb_serial, "shell", cmds],
                capture_output=True, text=True, timeout=30
            )
            granted += 1
        except Exception:
            pass
    return granted


def _run_grant_job(target_device=None):
    """Background job: grant permissions to all (or one) device."""
    global _grant_state
    try:
        with _grant_lock:
            _grant_state['running'] = True
            _grant_state['error'] = None
            _grant_state['results'] = None
            _grant_state['started_at'] = datetime.utcnow().isoformat()
            _grant_state['finished_at'] = None
            _grant_state['devices_done'] = 0
            _grant_state['clones_total'] = 0

        if target_device:
            devices = [target_device]
        else:
            devices = _get_adb_devices()

        with _grant_lock:
            _grant_state['devices_total'] = len(devices)
            _grant_state['progress'] = f'Found {len(devices)} device(s), granting permissions...'

        if not devices:
            with _grant_lock:
                _grant_state['running'] = False
                _grant_state['error'] = 'No connected devices found'
                _grant_state['finished_at'] = datetime.utcnow().isoformat()
            return

        total_clones = 0

        def _process_one(serial):
            nonlocal total_clones
            count = _grant_permissions_one_device(serial)
            with _grant_lock:
                _grant_state['devices_done'] += 1
                _grant_state['clones_total'] += count
                _grant_state['progress'] = (
                    f"{_grant_state['devices_done']}/{_grant_state['devices_total']} devices done "
                    f"({_grant_state['clones_total']} clones)"
                )
            return count

        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            futures = {executor.submit(_process_one, dev): dev for dev in devices}
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception:
                    pass

        with _grant_lock:
            _grant_state['running'] = False
            _grant_state['finished_at'] = datetime.utcnow().isoformat()
            _grant_state['results'] = {
                'ok': True,
                'devices': _grant_state['devices_total'],
                'clones': _grant_state['clones_total'],
                'permissions': len(_GRANT_PERMISSIONS),
            }
            _grant_state['progress'] = (
                f"Done! {_grant_state['devices_total']} devices, "
                f"{_grant_state['clones_total']} clones × {len(_GRANT_PERMISSIONS)} permissions"
            )

    except Exception as e:
        with _grant_lock:
            _grant_state['running'] = False
            _grant_state['error'] = str(e)
            _grant_state['finished_at'] = datetime.utcnow().isoformat()


@device_manager_bp.route('/api/devices/grant-permissions', methods=['POST'])
def api_grant_permissions():
    """Start a background grant-permissions job."""
    with _grant_lock:
        if _grant_state['running']:
            return jsonify({
                'ok': False,
                'error': 'Grant job already running',
                'progress': _grant_state['progress']
            }), 409

    data = request.get_json(silent=True) or {}
    target_device = data.get('device', None)

    thread = threading.Thread(target=_run_grant_job, args=(target_device,), daemon=True)
    thread.start()

    return jsonify({
        'ok': True,
        'message': f'Grant job started' + (f' for {target_device}' if target_device else ' for all devices'),
    })


@device_manager_bp.route('/api/devices/grant-permissions/status')
def api_grant_permissions_status():
    """Poll the grant-permissions job status."""
    with _grant_lock:
        return jsonify({
            'running': _grant_state['running'],
            'progress': _grant_state['progress'],
            'devices_total': _grant_state['devices_total'],
            'devices_done': _grant_state['devices_done'],
            'clones_total': _grant_state['clones_total'],
            'permissions_count': _grant_state['permissions_count'],
            'results': _grant_state['results'],
            'error': _grant_state['error'],
            'started_at': _grant_state['started_at'],
            'finished_at': _grant_state['finished_at'],
        })


# ── Follower Growth Tracking ─────────────────────────────────────────

@device_manager_bp.route('/api/device-manager/<serial>/follower-history')
def api_follower_history(serial):
    """
    Get follower history for an account on a device.
    Query params:
      username (required) - Instagram username
      days (optional, default 30) - Number of days of history
    Returns daily snapshots and growth metrics.
    """
    username = request.args.get('username', '').strip()
    if not username:
        return jsonify({'error': 'username is required'}), 400

    days = int(request.args.get('days', '30'))
    if days < 1:
        days = 1
    elif days > 365:
        days = 365

    try:
        conn = _get_conn()
        since = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')

        # Get daily snapshots (latest per day)
        rows = conn.execute("""
            SELECT
                DATE(captured_at) AS date,
                MAX(followers) AS followers,
                MAX(following) AS following,
                MAX(posts_count) AS posts
            FROM follower_snapshots
            WHERE username = ? AND device_serial = ?
              AND captured_at >= ?
            GROUP BY DATE(captured_at)
            ORDER BY date ASC
        """, (username, serial, since)).fetchall()

        history = [
            {
                'date': r['date'],
                'followers': r['followers'] or 0,
                'following': r['following'] or 0,
                'posts': r['posts'] or 0,
            }
            for r in rows
        ]

        # Calculate growth metrics
        growth = {'today': 0, 'week': 0, 'month': 0}

        if len(history) >= 2:
            latest = history[-1]['followers']

            # Today's growth (latest vs yesterday)
            if len(history) >= 2:
                growth['today'] = latest - history[-2]['followers']

            # Week growth
            week_ago = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')
            week_rows = [h for h in history if h['date'] <= week_ago]
            if week_rows:
                growth['week'] = latest - week_rows[-1]['followers']
            elif len(history) >= 2:
                growth['week'] = latest - history[0]['followers']

            # Month growth
            if len(history) >= 2:
                growth['month'] = latest - history[0]['followers']

        conn.close()

        return jsonify({
            'success': True,
            'history': history,
            'growth': growth,
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════════
# Business Profile & Insights API
# ══════════════════════════════════════════════════════════════════════

@device_manager_bp.route('/api/device-manager/<path:serial>/<username>/switch-business', methods=['POST'])
def api_switch_to_business(serial, username):
    """Create a task to switch an account to Business profile."""
    data = request.get_json(silent=True) or {}
    category = data.get('category', 'Digital creator')

    conn = _get_conn()
    try:
        account = conn.execute(
            "SELECT id FROM accounts WHERE device_serial=? AND username=?",
            (serial, username)
        ).fetchone()

        if not account:
            return jsonify({'success': False, 'error': 'Account not found'}), 404

        account_id = account['id']
        now = datetime.utcnow().isoformat()

        conn.execute("""
            INSERT INTO tasks (account_id, device_serial, task_type, status, priority, params_json, created_at, updated_at)
            VALUES (?, ?, 'switch_business', 'pending', 5, ?, ?, ?)
        """, (account_id, serial, json.dumps({'category': category}), now, now))
        conn.commit()

        return jsonify({
            'success': True,
            'message': f'Business switch task created for @{username} (category: {category})'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@device_manager_bp.route('/api/insights/<path:serial>/<username>')
def api_get_insights(serial, username):
    """Get latest insights data for an account."""
    conn = _get_conn()
    try:
        row = conn.execute("""
            SELECT * FROM account_insights
            WHERE device_serial = ? AND username = ?
            ORDER BY captured_at DESC
            LIMIT 1
        """, (serial, username)).fetchone()

        if not row:
            return jsonify({
                'success': True,
                'insights': None,
                'message': 'No insights data yet'
            })

        insights = dict(row)
        # Parse JSON fields
        try:
            insights['follower_demographics'] = json.loads(insights.get('follower_demographics', '{}'))
        except (json.JSONDecodeError, TypeError):
            insights['follower_demographics'] = {}
        try:
            insights['engagement_breakdown'] = json.loads(insights.get('engagement_breakdown', '{}'))
        except (json.JSONDecodeError, TypeError):
            insights['engagement_breakdown'] = {}

        return jsonify({
            'success': True,
            'insights': insights
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@device_manager_bp.route('/api/insights/<path:serial>/<username>/scrape', methods=['POST'])
def api_scrape_insights(serial, username):
    """Create a task to scrape insights for an account."""
    data = request.get_json(silent=True) or {}
    period = data.get('period', '7d')

    conn = _get_conn()
    try:
        account = conn.execute(
            "SELECT id, is_business_profile FROM accounts WHERE device_serial=? AND username=?",
            (serial, username)
        ).fetchone()

        if not account:
            return jsonify({'success': False, 'error': 'Account not found'}), 404

        if not account['is_business_profile']:
            return jsonify({
                'success': False,
                'error': 'Account is not a Business profile. Switch to Business first.'
            }), 400

        account_id = account['id']
        now = datetime.utcnow().isoformat()

        conn.execute("""
            INSERT INTO tasks (account_id, device_serial, task_type, status, priority, params_json, created_at, updated_at)
            VALUES (?, ?, 'scrape_insights', 'pending', 3, ?, ?, ?)
        """, (account_id, serial, json.dumps({'period': period}), now, now))
        conn.commit()

        return jsonify({
            'success': True,
            'message': f'Insights scrape task created for @{username}'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@device_manager_bp.route('/api/insights/<path:serial>/<username>/history')
def api_insights_history(serial, username):
    """Get historical insights data for an account."""
    days = int(request.args.get('days', '30'))
    if days < 1:
        days = 1
    elif days > 365:
        days = 365

    conn = _get_conn()
    try:
        since = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')

        rows = conn.execute("""
            SELECT id, accounts_reached, accounts_reached_delta,
                   accounts_engaged, accounts_engaged_delta,
                   profile_visits, website_clicks, email_clicks,
                   period_type, captured_at
            FROM account_insights
            WHERE device_serial = ? AND username = ?
              AND captured_at >= ?
            ORDER BY captured_at ASC
        """, (serial, username, since)).fetchall()

        history = [dict(r) for r in rows]

        return jsonify({
            'success': True,
            'history': history,
            'total': len(history)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════
# Insights V2 API (account_insights_v2 table)
# ══════════════════════════════════════════════════════════════════════

@device_manager_bp.route('/api/account/<username>/insights')
def api_account_insights_v2(username):
    """Get latest insights_v2 record for an account + business profile info."""
    conn = _get_conn()
    try:
        # Check if account is business
        acct = conn.execute(
            "SELECT is_business_profile, business_category, business_switched_at FROM accounts WHERE username = ?",
            (username,)
        ).fetchone()

        is_biz = bool(acct['is_business_profile']) if acct else False

        if not is_biz:
            return jsonify({
                'success': True,
                'is_business': False,
                'insights': None,
                'message': 'Switch to Business Profile to unlock insights'
            })

        # Get latest insights_v2 record
        row = conn.execute("""
            SELECT * FROM account_insights_v2
            WHERE account_id = ?
            ORDER BY scraped_at DESC
            LIMIT 1
        """, (username,)).fetchone()

        if not row:
            return jsonify({
                'success': True,
                'is_business': True,
                'business_category': acct['business_category'],
                'insights': None,
                'message': 'No insights data scraped yet'
            })

        insights = dict(row)
        # Parse JSON fields safely
        for jfield in ('top_cities', 'top_countries', 'age_range', 'gender', 'most_active_times'):
            try:
                insights[jfield] = json.loads(insights.get(jfield) or '{}')
            except (json.JSONDecodeError, TypeError):
                insights[jfield] = {}

        return jsonify({
            'success': True,
            'is_business': True,
            'business_category': acct['business_category'],
            'insights': insights
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@device_manager_bp.route('/api/account/<username>/insights/history')
def api_account_insights_v2_history(username):
    """Get insights_v2 history for charting."""
    days = int(request.args.get('days', '30'))
    days = max(1, min(days, 365))

    conn = _get_conn()
    try:
        since = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')

        rows = conn.execute("""
            SELECT id, scraped_at, date_range, views, interactions, new_followers,
                   content_shared, accounts_reached, accounts_reached_change_pct,
                   views_followers_pct, views_non_followers_pct,
                   profile_visits, profile_visits_change_pct,
                   external_link_taps, total_followers, comparison_period
            FROM account_insights_v2
            WHERE account_id = ?
              AND scraped_at >= ?
            ORDER BY scraped_at ASC
        """, (username, since)).fetchall()

        history = [dict(r) for r in rows]

        return jsonify({
            'success': True,
            'history': history,
            'total': len(history)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()