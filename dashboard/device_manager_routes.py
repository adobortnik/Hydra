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
import sqlite3
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
            ORDER BY d.device_serial
        """).fetchall())

        # Attach bot_status info if available
        for dev in devices:
            bs = conn.execute(
                "SELECT status, pid, started_at, last_check_at FROM bot_status WHERE device_serial = ?",
                (dev['device_serial'],)
            ).fetchone()
            if bs:
                dev['bot_status'] = bs['status']
                dev['bot_pid'] = bs['pid']
                dev['bot_started_at'] = bs['started_at']
                dev['bot_last_check'] = bs['last_check_at']
            else:
                dev['bot_status'] = 'stopped'
                dev['bot_pid'] = None
                dev['bot_started_at'] = None
                dev['bot_last_check'] = None

        return jsonify({'devices': devices, 'total': len(devices)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


# ── API: Single Device Detail ───────────────────────────────────────

@device_manager_bp.route('/api/device-manager/devices/<path:serial>')
def api_dm_device_detail(serial):
    """Single device with all accounts + today's stats."""
    conn = _get_conn()
    try:
        device = _row_to_dict(conn.execute(
            "SELECT * FROM devices WHERE device_serial = ?", (serial,)
        ).fetchone())

        if not device:
            return jsonify({'error': f'Device {serial} not found'}), 404

        # Get accounts with stats
        accounts = _get_accounts_with_stats(conn, serial)

        # Get bot status
        bs = conn.execute(
            "SELECT * FROM bot_status WHERE device_serial = ?", (serial,)
        ).fetchone()
        device['bot_status'] = _row_to_dict(bs) if bs else {'status': 'stopped'}

        return jsonify({
            'device': device,
            'accounts': accounts,
            'total_accounts': len(accounts)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


# ── API: Accounts for Device ────────────────────────────────────────

@device_manager_bp.route('/api/device-manager/accounts/<path:serial>')
def api_dm_accounts(serial):
    """Accounts for a device with today's stats + yesterday comparison."""
    conn = _get_conn()
    try:
        accounts = _get_accounts_with_stats(conn, serial)
        return jsonify({'accounts': accounts, 'total': len(accounts)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


def _get_accounts_with_stats(conn, device_serial):
    """Get accounts with today's stats from action_history (source of truth).
    
    The account_stats table only has followers/following counts from syncs.
    Action counts (follows, unfollows, likes, etc.) come from action_history.
    """
    today = _today()
    yesterday = _yesterday()

    # Get base account info + followers/following from account_stats
    rows = conn.execute("""
        SELECT a.id, a.device_serial, a.username, a.status,
               a.start_time, a.end_time, a.instagram_package,
               a.follow_enabled, a.unfollow_enabled, a.like_enabled,
               a.comment_enabled, a.story_enabled,
               COALESCE(s_today.followers, '0') as followers,
               COALESCE(s_today.following, '0') as following,
               s_yesterday.followers as prev_followers,
               s_yesterday.following as prev_following
        FROM accounts a
        LEFT JOIN account_stats s_today
            ON s_today.account_id = a.id AND s_today.date = ?
        LEFT JOIN account_stats s_yesterday
            ON s_yesterday.account_id = a.id AND s_yesterday.date = ?
        WHERE a.device_serial = ?
        ORDER BY CAST(COALESCE(a.start_time, '0') AS INTEGER), a.username
    """, (today, yesterday, device_serial)).fetchall()

    # Get today's action counts from action_history (the actual source of truth)
    action_counts = conn.execute("""
        SELECT username, action_type, COUNT(*) as cnt
        FROM action_history
        WHERE device_serial = ?
          AND timestamp >= ?
          AND success = 1
        GROUP BY username, action_type
    """, (device_serial, today)).fetchall()
    
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
