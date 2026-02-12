"""
account_health_routes.py - Account Health & Inventory API + Dashboard
=====================================================================
Provides:
  - Account health monitoring (flagged accounts, events, resolution)
  - Account inventory management (import, assign, list, delete)
  - Dashboard pages for both systems
"""

from flask import Blueprint, render_template, jsonify, request
from phone_farm_db import get_conn, row_to_dict, rows_to_dicts
from datetime import datetime, timedelta
import json
import subprocess
import logging

log = logging.getLogger(__name__)

account_health_bp = Blueprint('account_health', __name__)


# =====================================================================
#  ACCOUNT HEALTH - Page Routes
# =====================================================================

@account_health_bp.route('/account-health')
def account_health_page():
    """Account health monitoring dashboard."""
    return render_template('account_health.html')


@account_health_bp.route('/inventory')
def inventory_page():
    """Account inventory management page."""
    return render_template('account_inventory_v2.html')


# =====================================================================
#  ACCOUNT HEALTH - API Endpoints
# =====================================================================

@account_health_bp.route('/api/account-health')
def api_health_list():
    """
    GET /api/account-health
    List all flagged accounts (unresolved health events).
    Optional query params: ?event_type=suspended&limit=50
    """
    conn = get_conn()
    try:
        event_type = request.args.get('event_type')
        limit = request.args.get('limit', 100, type=int)

        query = """
            SELECT he.*,
                   a.status AS account_status,
                   a.instagram_package,
                   d.device_name
            FROM account_health_events he
            LEFT JOIN accounts a ON a.id = he.account_id
            LEFT JOIN devices d ON d.device_serial = he.device_serial
            WHERE he.resolved_at IS NULL
        """
        params = []

        if event_type:
            query += " AND he.event_type = ?"
            params.append(event_type)

        query += " ORDER BY he.detected_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return jsonify(rows_to_dicts(rows))
    finally:
        conn.close()


@account_health_bp.route('/api/account-health/summary')
def api_health_summary():
    """
    GET /api/account-health/summary
    Counts by event_type (unresolved) + overall account status counts.
    """
    conn = get_conn()
    try:
        # Unresolved events by type
        event_rows = conn.execute("""
            SELECT event_type, COUNT(*) as count
            FROM account_health_events
            WHERE resolved_at IS NULL
            GROUP BY event_type
        """).fetchall()
        events_by_type = {r['event_type']: r['count'] for r in event_rows}

        # Overall account status counts
        status_rows = conn.execute("""
            SELECT status, COUNT(*) as count
            FROM accounts
            GROUP BY status
        """).fetchall()
        accounts_by_status = {r['status']: r['count'] for r in status_rows}

        # Total unresolved
        total_unresolved = sum(events_by_type.values())

        return jsonify({
            'events_by_type': events_by_type,
            'accounts_by_status': accounts_by_status,
            'total_unresolved': total_unresolved,
        })
    finally:
        conn.close()


@account_health_bp.route('/api/account-health/events')
def api_health_events():
    """
    GET /api/account-health/events?account_id=X
    Events for a specific account (all, including resolved).
    """
    account_id = request.args.get('account_id', type=int)
    if not account_id:
        return jsonify({'error': 'account_id required'}), 400

    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT * FROM account_health_events
            WHERE account_id = ?
            ORDER BY detected_at DESC
            LIMIT 50
        """, (account_id,)).fetchall()
        return jsonify(rows_to_dicts(rows))
    finally:
        conn.close()


@account_health_bp.route('/api/account-health/resolve', methods=['POST'])
def api_health_resolve():
    """
    POST /api/account-health/resolve
    Body: { "event_id": 123, "resolved_by": "manual" }
    Marks a health event as resolved.
    """
    data = request.get_json() or {}
    event_id = data.get('event_id')
    resolved_by = data.get('resolved_by', 'manual')

    if not event_id:
        return jsonify({'error': 'event_id required'}), 400

    conn = get_conn()
    try:
        now = datetime.utcnow().isoformat()
        conn.execute("""
            UPDATE account_health_events
            SET resolved_at = ?, resolved_by = ?
            WHERE id = ? AND resolved_at IS NULL
        """, (now, resolved_by, event_id))

        # Also reset the account status to 'active' if resolving manually
        if resolved_by == 'manual':
            event = conn.execute(
                "SELECT account_id FROM account_health_events WHERE id = ?",
                (event_id,)
            ).fetchone()
            if event:
                conn.execute(
                    "UPDATE accounts SET status = 'active', updated_at = ? WHERE id = ?",
                    (now, event['account_id'])
                )

        conn.commit()
        return jsonify({'success': True, 'resolved_at': now})
    finally:
        conn.close()


@account_health_bp.route('/api/account-health/notifications')
def api_health_notifications():
    """
    GET /api/account-health/notifications
    Recent unresolved events for the notification bell (last 24h, max 20).
    """
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT he.id, he.username, he.device_serial, he.event_type,
                   he.detected_at, he.details
            FROM account_health_events he
            WHERE he.resolved_at IS NULL
            ORDER BY he.detected_at DESC
            LIMIT 20
        """).fetchall()

        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM account_health_events WHERE resolved_at IS NULL"
        ).fetchone()['cnt']

        return jsonify({
            'events': rows_to_dicts(rows),
            'total_unresolved': total,
        })
    finally:
        conn.close()


@account_health_bp.route('/api/account-health/resolve-all', methods=['POST'])
def api_health_resolve_all():
    """
    POST /api/account-health/resolve-all
    Body: { "event_type": "logged_out" } (optional — resolves all if omitted)
    Bulk resolve unresolved events.
    """
    data = request.get_json() or {}
    event_type = data.get('event_type')

    conn = get_conn()
    try:
        now = datetime.utcnow().isoformat()
        if event_type:
            result = conn.execute("""
                UPDATE account_health_events
                SET resolved_at = ?, resolved_by = 'manual_bulk'
                WHERE resolved_at IS NULL AND event_type = ?
            """, (now, event_type))
        else:
            result = conn.execute("""
                UPDATE account_health_events
                SET resolved_at = ?, resolved_by = 'manual_bulk'
                WHERE resolved_at IS NULL
            """, (now,))
        conn.commit()
        return jsonify({'success': True, 'resolved_count': result.rowcount})
    finally:
        conn.close()


# =====================================================================
#  ACCOUNT AUTO-FIX - Direct account replacement (no health event needed)
# =====================================================================

# Statuses considered "broken" and eligible for auto-fix
BROKEN_STATUSES = ('banned', 'suspended', 'challenge', 'login_failed', 'verification_required')


@account_health_bp.route('/api/account-health/replaceable')
def api_replaceable_accounts():
    """
    GET /api/account-health/replaceable
    Returns accounts with broken statuses that can be replaced from inventory.
    """
    conn = get_conn()
    try:
        placeholders = ','.join('?' * len(BROKEN_STATUSES))
        rows = conn.execute("""
            SELECT a.id, a.username, a.password, a.device_id, a.device_serial,
                   a.instagram_package, a.status, a.updated_at,
                   d.device_name
            FROM accounts a
            LEFT JOIN devices d ON d.id = a.device_id
            WHERE a.status IN ({})
            ORDER BY a.updated_at ASC
        """.format(placeholders), BROKEN_STATUSES).fetchall()

        accounts = rows_to_dicts(rows)

        # Check inventory availability
        avail_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM account_inventory WHERE status = 'available'"
        ).fetchone()['cnt']

        # Calculate how long each has been in bad state
        now = datetime.utcnow()
        for acct in accounts:
            updated = acct.get('updated_at')
            if updated:
                try:
                    dt = datetime.fromisoformat(updated)
                    delta = now - dt
                    acct['bad_since_hours'] = round(delta.total_seconds() / 3600, 1)
                    acct['bad_since_text'] = _format_duration(delta)
                except Exception:
                    acct['bad_since_hours'] = None
                    acct['bad_since_text'] = 'unknown'
            else:
                acct['bad_since_hours'] = None
                acct['bad_since_text'] = 'unknown'
            acct['replacement_available'] = avail_count > 0

        return jsonify({
            'accounts': accounts,
            'total': len(accounts),
            'replacements_available': avail_count,
        })
    finally:
        conn.close()


@account_health_bp.route('/api/account-health/inventory-available')
def api_inventory_available_count():
    """
    GET /api/account-health/inventory-available
    Returns count of available accounts in inventory ready for replacement.
    """
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM account_inventory WHERE status = 'available'"
        ).fetchone()
        return jsonify({'available': row['cnt']})
    finally:
        conn.close()


@account_health_bp.route('/api/account-health/auto-fix', methods=['POST'])
def api_auto_fix():
    """
    POST /api/account-health/auto-fix
    Body: { "account_id": int }

    Replaces a broken account with a fresh one from inventory.
    Preserves device_id, device_serial, instagram_package, position, schedule.
    """
    data = request.get_json() or {}
    account_id = data.get('account_id')

    if not account_id:
        return jsonify({'error': 'account_id required'}), 400

    conn = get_conn()
    try:
        now = datetime.utcnow().isoformat()

        # a) Load the broken account
        old_account = conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if not old_account:
            return jsonify({'error': 'Account not found'}), 404
        old_account = dict(old_account)

        # Verify it is actually in a broken state
        if old_account['status'] not in BROKEN_STATUSES:
            return jsonify({
                'error': 'Account status is "%s" - not eligible for auto-fix. Must be one of: %s'
                         % (old_account['status'], ', '.join(BROKEN_STATUSES))
            }), 400

        # b) Load old account settings (for app_cloner etc.)
        old_settings_row = conn.execute(
            "SELECT settings_json FROM account_settings WHERE account_id = ?",
            (old_account['id'],)
        ).fetchone()
        old_settings_json = json.loads(old_settings_row['settings_json']) if old_settings_row else {}
        app_cloner = old_settings_json.get('app_cloner', 'None')

        # c) Pick next available inventory account
        inv = conn.execute(
            "SELECT * FROM account_inventory WHERE status = 'available' ORDER BY id ASC LIMIT 1"
        ).fetchone()
        if not inv:
            return jsonify({'error': 'No available accounts in inventory'}), 404
        inv = dict(inv)

        # d) Preserve device assignment from old account
        device_id = old_account.get('device_id')
        device_serial = old_account['device_serial']
        instagram_package = old_account['instagram_package']
        start_time = old_account.get('start_time', '0')
        end_time = old_account.get('end_time', '0')

        # e) Clear IG clone app data via ADB
        adb_clear_ok = False
        adb_error = None
        try:
            adb_serial = device_serial.replace('_', ':')
            clear_result = subprocess.run(
                ['adb', '-s', adb_serial, 'shell', 'pm', 'clear', instagram_package],
                capture_output=True, timeout=15, text=True
            )
            adb_clear_ok = clear_result.returncode == 0
            if not adb_clear_ok:
                adb_error = clear_result.stderr or clear_result.stdout
                log.warning("ADB clear failed for %s on %s: %s",
                            instagram_package, adb_serial, adb_error)
        except Exception as e:
            adb_error = str(e)
            log.warning("ADB clear exception for %s on %s: %s",
                        instagram_package, device_serial, e)

        # f) Create new account record (inherits device + package + schedule)
        cursor = conn.execute("""
            INSERT INTO accounts (
                device_id, device_serial, username, password, email,
                instagram_package, two_fa_token, status,
                follow_enabled, unfollow_enabled, mute_enabled, like_enabled,
                comment_enabled, story_enabled, switchmode,
                start_time, end_time,
                follow_action, unfollow_action, random_action, random_delay,
                follow_delay, unfollow_delay, like_delay,
                follow_limit_perday, unfollow_limit_perday, like_limit_perday,
                created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, 'pending_login',
                'False', 'False', 'False', 'False',
                'False', 'False', 'False',
                ?, ?,
                '0', '0', '30,60', '30,60',
                '30', '30', '0',
                '0', '0', '0',
                ?, ?
            )
        """, (
            device_id, device_serial, inv['username'], inv['password'], inv.get('email'),
            instagram_package, inv.get('two_factor_auth'),
            start_time, end_time,
            now, now
        ))
        new_account_id = cursor.lastrowid

        # g) Create account_settings with warmup config (reels only for 7 days)
        warmup_end = (datetime.utcnow() + timedelta(days=7)).isoformat()
        warmup_settings = {
            "enable_likepost": False,
            "enable_comment": False,
            "enable_directmessage": False,
            "enable_story_viewer": False,
            "enable_human_behaviour_emulation": False,
            "enable_viewhomefeedstory": False,
            "enable_scrollhomefeed": False,
            "enable_share_post_to_story": False,
            "enable_follow_from_list": False,
            "enable_watch_reels": True,
            "min_reels_to_watch": "10",
            "max_reels_to_watch": "20",
            "watch_reels_duration_min": "5",
            "watch_reels_duration_max": "15",
            "watch_reels_daily_limit": "100",
            "enable_save_reels_while_watching": False,
            "enable_like_reels_while_watching": False,
            "enable_comment_reels_while_watching": False,
            "app_cloner": app_cloner,
            "_warmup_mode": True,
            "_warmup_start": now,
            "_warmup_end": warmup_end,
            "_replaced_account_id": old_account['id'],
            "_replaced_username": old_account['username'],
        }

        conn.execute(
            "INSERT INTO account_settings (account_id, settings_json, updated_at) VALUES (?, ?, ?)",
            (new_account_id, json.dumps(warmup_settings), now)
        )

        # h) Queue login task
        conn.execute("""
            INSERT INTO login_tasks (
                device_serial, instagram_package, username, password,
                two_fa_token, status, priority, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'pending', 10, ?, ?)
        """, (
            device_serial, instagram_package, inv['username'], inv['password'],
            inv.get('two_factor_auth'), now, now
        ))

        # i) Mark old account as replaced
        conn.execute(
            "UPDATE accounts SET status = 'replaced', updated_at = ? WHERE id = ?",
            (now, old_account['id'])
        )

        # j) Resolve any open health events for this account
        conn.execute("""
            UPDATE account_health_events
            SET resolved_at = ?, resolved_by = 'auto_fix', replacement_account_id = ?
            WHERE account_id = ? AND resolved_at IS NULL
        """, (now, new_account_id, old_account['id']))

        # k) Update inventory account status
        conn.execute("""
            UPDATE account_inventory
            SET status = 'used',
                device_assigned = ?,
                assigned_to_device_serial = ?,
                assigned_to_account_id = ?,
                assigned_at = ?,
                date_used = ?
            WHERE id = ?
        """, (device_serial, device_serial, new_account_id, now, now, inv['id']))

        conn.commit()

        log.info("Auto-fix: @%s -> @%s on %s (%s)",
                 old_account['username'], inv['username'], device_serial, instagram_package)

        return jsonify({
            'success': True,
            'old_account': {
                'id': old_account['id'],
                'username': old_account['username'],
                'status': old_account['status'],
            },
            'new_account': {
                'id': new_account_id,
                'username': inv['username'],
            },
            'device_serial': device_serial,
            'instagram_package': instagram_package,
            'login_task_queued': True,
            'warmup_days': 7,
            'adb_clear_ok': adb_clear_ok,
            'adb_error': adb_error,
        })

    except Exception as e:
        log.error("Auto-fix error: %s", e, exc_info=True)
        return jsonify({'error': 'Auto-fix failed: %s' % str(e)}), 500
    finally:
        conn.close()


@account_health_bp.route('/api/account-health/auto-fix-all', methods=['POST'])
def api_auto_fix_all():
    """
    POST /api/account-health/auto-fix-all
    Bulk replace all broken accounts from inventory (up to available count).
    Returns summary of replacements made.
    """
    conn = get_conn()
    results = []
    errors = []
    try:
        placeholders = ','.join('?' * len(BROKEN_STATUSES))
        broken_rows = conn.execute("""
            SELECT id, username, status FROM accounts
            WHERE status IN ({})
            ORDER BY updated_at ASC
        """.format(placeholders), BROKEN_STATUSES).fetchall()
        conn.close()  # Close - each fix will get its own conn via the endpoint

        for row in broken_rows:
            acct = dict(row)
            # Call auto-fix for each account by simulating the request internally
            try:
                inner_conn = get_conn()
                now = datetime.utcnow().isoformat()

                old_account = inner_conn.execute(
                    "SELECT * FROM accounts WHERE id = ?", (acct['id'],)
                ).fetchone()
                if not old_account:
                    errors.append({'account_id': acct['id'], 'error': 'Not found'})
                    inner_conn.close()
                    continue
                old_account = dict(old_account)

                if old_account['status'] not in BROKEN_STATUSES:
                    # Status changed since query - skip
                    inner_conn.close()
                    continue

                # Pick next available inventory account
                inv = inner_conn.execute(
                    "SELECT * FROM account_inventory WHERE status = 'available' ORDER BY id ASC LIMIT 1"
                ).fetchone()
                if not inv:
                    errors.append({
                        'account_id': acct['id'],
                        'username': acct['username'],
                        'error': 'No more inventory accounts available'
                    })
                    inner_conn.close()
                    break  # No point continuing

                inv = dict(inv)

                # Load old settings
                old_settings_row = inner_conn.execute(
                    "SELECT settings_json FROM account_settings WHERE account_id = ?",
                    (old_account['id'],)
                ).fetchone()
                old_settings_json = json.loads(old_settings_row['settings_json']) if old_settings_row else {}
                app_cloner = old_settings_json.get('app_cloner', 'None')

                device_id = old_account.get('device_id')
                device_serial = old_account['device_serial']
                instagram_package = old_account['instagram_package']
                start_time = old_account.get('start_time', '0')
                end_time = old_account.get('end_time', '0')

                # ADB clear
                adb_clear_ok = False
                try:
                    adb_serial = device_serial.replace('_', ':')
                    clear_result = subprocess.run(
                        ['adb', '-s', adb_serial, 'shell', 'pm', 'clear', instagram_package],
                        capture_output=True, timeout=15, text=True
                    )
                    adb_clear_ok = clear_result.returncode == 0
                except Exception:
                    pass

                # Create new account
                cursor = inner_conn.execute("""
                    INSERT INTO accounts (
                        device_id, device_serial, username, password, email,
                        instagram_package, two_fa_token, status,
                        follow_enabled, unfollow_enabled, mute_enabled, like_enabled,
                        comment_enabled, story_enabled, switchmode,
                        start_time, end_time,
                        follow_action, unfollow_action, random_action, random_delay,
                        follow_delay, unfollow_delay, like_delay,
                        follow_limit_perday, unfollow_limit_perday, like_limit_perday,
                        created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?, ?,
                        ?, ?, 'pending_login',
                        'False', 'False', 'False', 'False',
                        'False', 'False', 'False',
                        ?, ?,
                        '0', '0', '30,60', '30,60',
                        '30', '30', '0',
                        '0', '0', '0',
                        ?, ?
                    )
                """, (
                    device_id, device_serial, inv['username'], inv['password'], inv.get('email'),
                    instagram_package, inv.get('two_factor_auth'),
                    start_time, end_time, now, now
                ))
                new_account_id = cursor.lastrowid

                # Warmup settings
                warmup_end = (datetime.utcnow() + timedelta(days=7)).isoformat()
                warmup_settings = {
                    "enable_watch_reels": True,
                    "min_reels_to_watch": "10",
                    "max_reels_to_watch": "20",
                    "watch_reels_duration_min": "5",
                    "watch_reels_duration_max": "15",
                    "watch_reels_daily_limit": "100",
                    "app_cloner": app_cloner,
                    "_warmup_mode": True,
                    "_warmup_start": now,
                    "_warmup_end": warmup_end,
                    "_replaced_account_id": old_account['id'],
                    "_replaced_username": old_account['username'],
                }
                inner_conn.execute(
                    "INSERT INTO account_settings (account_id, settings_json, updated_at) VALUES (?, ?, ?)",
                    (new_account_id, json.dumps(warmup_settings), now)
                )

                # Login task
                inner_conn.execute("""
                    INSERT INTO login_tasks (
                        device_serial, instagram_package, username, password,
                        two_fa_token, status, priority, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'pending', 10, ?, ?)
                """, (
                    device_serial, instagram_package, inv['username'], inv['password'],
                    inv.get('two_factor_auth'), now, now
                ))

                # Mark old as replaced
                inner_conn.execute(
                    "UPDATE accounts SET status = 'replaced', updated_at = ? WHERE id = ?",
                    (now, old_account['id'])
                )

                # Resolve health events
                inner_conn.execute("""
                    UPDATE account_health_events
                    SET resolved_at = ?, resolved_by = 'auto_fix_bulk', replacement_account_id = ?
                    WHERE account_id = ? AND resolved_at IS NULL
                """, (now, new_account_id, old_account['id']))

                # Update inventory
                inner_conn.execute("""
                    UPDATE account_inventory
                    SET status = 'used',
                        device_assigned = ?,
                        assigned_to_device_serial = ?,
                        assigned_to_account_id = ?,
                        assigned_at = ?,
                        date_used = ?
                    WHERE id = ?
                """, (device_serial, device_serial, new_account_id, now, now, inv['id']))

                inner_conn.commit()
                inner_conn.close()

                results.append({
                    'old_username': old_account['username'],
                    'old_status': old_account['status'],
                    'new_username': inv['username'],
                    'new_account_id': new_account_id,
                    'device_serial': device_serial,
                    'adb_clear_ok': adb_clear_ok,
                })

                log.info("Auto-fix bulk: @%s -> @%s on %s",
                         old_account['username'], inv['username'], device_serial)

            except Exception as e:
                errors.append({
                    'account_id': acct['id'],
                    'username': acct['username'],
                    'error': str(e),
                })
                log.error("Auto-fix bulk error for #%d: %s", acct['id'], e)

        return jsonify({
            'success': True,
            'replaced': len(results),
            'errors_count': len(errors),
            'results': results,
            'errors': errors[:20],
        })

    except Exception as e:
        log.error("Auto-fix-all error: %s", e, exc_info=True)
        return jsonify({'error': 'Bulk auto-fix failed: %s' % str(e)}), 500


def _format_duration(delta):
    """Format a timedelta into a human-readable string (ASCII only)."""
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return '%ds' % total_seconds
    if total_seconds < 3600:
        return '%dm' % (total_seconds // 60)
    if total_seconds < 86400:
        return '%dh %dm' % (total_seconds // 3600, (total_seconds % 3600) // 60)
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    return '%dd %dh' % (days, hours)


# =====================================================================
#  ACCOUNT REPLACEMENT - API Endpoints (Health Event based)
# =====================================================================

@account_health_bp.route('/api/account-health/replace-preview/<int:event_id>')
def api_replace_preview(event_id):
    """
    GET /api/account-health/replace-preview/<event_id>
    Preview what a replacement would look like before confirming.
    Returns the flagged account details and the next available inventory account.
    """
    conn = get_conn()
    try:
        # Load the health event
        event = conn.execute(
            "SELECT * FROM account_health_events WHERE id = ? AND resolved_at IS NULL",
            (event_id,)
        ).fetchone()
        if not event:
            return jsonify({'error': 'Health event not found or already resolved'}), 404

        event = dict(event)

        # Load the flagged (old) account
        old_account = conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (event['account_id'],)
        ).fetchone()
        if not old_account:
            return jsonify({'error': 'Flagged account not found'}), 404

        old_account = dict(old_account)

        # Load old account's settings for app_cloner
        old_settings_row = conn.execute(
            "SELECT settings_json FROM account_settings WHERE account_id = ?",
            (old_account['id'],)
        ).fetchone()
        old_settings_json = json.loads(old_settings_row['settings_json']) if old_settings_row else {}
        app_cloner = old_settings_json.get('app_cloner', 'None')

        # Pick next available inventory account
        inv = conn.execute(
            "SELECT * FROM account_inventory WHERE status = 'available' ORDER BY id ASC LIMIT 1"
        ).fetchone()

        # Count total available
        available_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM account_inventory WHERE status = 'available'"
        ).fetchone()['cnt']

        return jsonify({
            'event': row_to_dict(conn.execute(
                "SELECT * FROM account_health_events WHERE id = ?", (event_id,)
            ).fetchone()),
            'old_account': {
                'id': old_account['id'],
                'username': old_account['username'],
                'device_serial': old_account['device_serial'],
                'instagram_package': old_account['instagram_package'],
                'start_time': old_account.get('start_time', '0'),
                'end_time': old_account.get('end_time', '0'),
                'app_cloner': app_cloner,
            },
            'new_account': row_to_dict(inv) if inv else None,
            'available_inventory_count': available_count,
        })
    finally:
        conn.close()


@account_health_bp.route('/api/account-health/replace', methods=['POST'])
def api_replace_account():
    """
    POST /api/account-health/replace
    Body: { "health_event_id": int, "inventory_account_id": int (optional) }

    Full replacement pipeline:
    1. Load health event and flagged account
    2. Pick inventory account
    3. Clear IG clone app data via ADB
    4. Create new account record (inherits device + package + schedule)
    5. Set warmup settings (reels only for 7 days)
    6. Queue login task
    7. Mark old account as replaced, resolve health event, update inventory
    """
    data = request.get_json() or {}
    health_event_id = data.get('health_event_id')
    inventory_account_id = data.get('inventory_account_id')

    if not health_event_id:
        return jsonify({'error': 'health_event_id required'}), 400

    conn = get_conn()
    try:
        now = datetime.utcnow().isoformat()

        # a) Load the health event
        event = conn.execute(
            "SELECT * FROM account_health_events WHERE id = ? AND resolved_at IS NULL",
            (health_event_id,)
        ).fetchone()
        if not event:
            return jsonify({'error': 'Health event not found or already resolved'}), 404
        event = dict(event)

        # b) Load the flagged (old) account
        old_account = conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (event['account_id'],)
        ).fetchone()
        if not old_account:
            return jsonify({'error': 'Flagged account not found'}), 404
        old_account = dict(old_account)

        # c) Load old account's settings
        old_settings_row = conn.execute(
            "SELECT settings_json FROM account_settings WHERE account_id = ?",
            (old_account['id'],)
        ).fetchone()
        old_settings_json = json.loads(old_settings_row['settings_json']) if old_settings_row else {}
        app_cloner = old_settings_json.get('app_cloner', 'None')

        # d) Pick inventory account (or use specified one)
        if inventory_account_id:
            inv = conn.execute(
                "SELECT * FROM account_inventory WHERE id = ? AND status = 'available'",
                (inventory_account_id,)
            ).fetchone()
        else:
            inv = conn.execute(
                "SELECT * FROM account_inventory WHERE status = 'available' ORDER BY id ASC LIMIT 1"
            ).fetchone()

        if not inv:
            return jsonify({'error': 'No available accounts in inventory'}), 404
        inv = dict(inv)

        # e) Get the IG package info from old account
        instagram_package = old_account['instagram_package']
        device_serial = old_account['device_serial']
        device_id = old_account.get('device_id')
        start_time = old_account.get('start_time', '0')
        end_time = old_account.get('end_time', '0')

        # f) Clear the IG clone app data via ADB
        adb_clear_ok = False
        adb_error = None
        try:
            adb_serial = device_serial.replace('_', ':')
            clear_result = subprocess.run(
                ['adb', '-s', adb_serial, 'shell', 'pm', 'clear', instagram_package],
                capture_output=True, timeout=15, text=True
            )
            adb_clear_ok = clear_result.returncode == 0
            if not adb_clear_ok:
                adb_error = clear_result.stderr or clear_result.stdout
                log.warning("ADB clear failed for %s on %s: %s",
                            instagram_package, adb_serial, adb_error)
        except Exception as e:
            adb_error = str(e)
            log.warning("ADB clear exception for %s on %s: %s",
                        instagram_package, device_serial, e)

        # g) Create new account in accounts table
        cursor = conn.execute("""
            INSERT INTO accounts (
                device_id, device_serial, username, password, email,
                instagram_package, two_fa_token, status,
                follow_enabled, unfollow_enabled, mute_enabled, like_enabled,
                comment_enabled, story_enabled, switchmode,
                start_time, end_time,
                follow_action, unfollow_action, random_action, random_delay,
                follow_delay, unfollow_delay, like_delay,
                follow_limit_perday, unfollow_limit_perday, like_limit_perday,
                created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, 'pending_login',
                'False', 'False', 'False', 'False',
                'False', 'False', 'False',
                ?, ?,
                '0', '0', '30,60', '30,60',
                '30', '30', '0',
                '0', '0', '0',
                ?, ?
            )
        """, (
            device_id, device_serial, inv['username'], inv['password'], inv.get('email'),
            instagram_package, inv.get('two_factor_auth'),
            start_time, end_time,
            now, now
        ))
        new_account_id = cursor.lastrowid

        # h) Create account_settings with warmup config (reels only)
        warmup_settings = {
            # Everything OFF except reels
            "enable_likepost": False,
            "enable_comment": False,
            "enable_directmessage": False,
            "enable_story_viewer": False,
            "enable_human_behaviour_emulation": False,
            "enable_viewhomefeedstory": False,
            "enable_scrollhomefeed": False,
            "enable_share_post_to_story": False,
            "enable_follow_from_list": False,

            # Reels ONLY — warmup mode
            "enable_watch_reels": True,
            "min_reels_to_watch": "10",
            "max_reels_to_watch": "20",
            "watch_reels_duration_min": "5",
            "watch_reels_duration_max": "15",
            "watch_reels_daily_limit": "100",
            "enable_save_reels_while_watching": False,
            "enable_like_reels_while_watching": False,
            "enable_comment_reels_while_watching": False,

            # Copy app_cloner from old account (critical)
            "app_cloner": app_cloner,

            # Mark as warmup with end date
            "_warmup_mode": True,
            "_warmup_start": now,
            "_warmup_end": (datetime.utcnow() + timedelta(days=7)).isoformat(),
            "_replaced_account_id": old_account['id'],
            "_replaced_username": old_account['username'],
        }

        conn.execute(
            "INSERT INTO account_settings (account_id, settings_json, updated_at) VALUES (?, ?, ?)",
            (new_account_id, json.dumps(warmup_settings), now)
        )

        # i) Queue login task
        conn.execute("""
            INSERT INTO login_tasks (
                device_serial, instagram_package, username, password,
                two_fa_token, status, priority, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'pending', 10, ?, ?)
        """, (
            device_serial, instagram_package, inv['username'], inv['password'],
            inv.get('two_factor_auth'), now, now
        ))

        # j) Mark old account as replaced
        conn.execute(
            "UPDATE accounts SET status = 'replaced', updated_at = ? WHERE id = ?",
            (now, old_account['id'])
        )

        # k) Resolve health event
        conn.execute("""
            UPDATE account_health_events
            SET resolved_at = ?, resolved_by = 'manual_replace', replacement_account_id = ?
            WHERE id = ?
        """, (now, new_account_id, health_event_id))

        # l) Update inventory account
        conn.execute("""
            UPDATE account_inventory
            SET status = 'assigned',
                assigned_to_device_serial = ?,
                assigned_to_account_id = ?,
                assigned_at = ?,
                date_used = ?
            WHERE id = ?
        """, (device_serial, new_account_id, now, now, inv['id']))

        conn.commit()

        log.info("Account replaced: @%s → @%s on %s (%s)",
                 old_account['username'], inv['username'], device_serial, instagram_package)

        return jsonify({
            'success': True,
            'old_account': old_account['username'],
            'new_account': inv['username'],
            'new_account_id': new_account_id,
            'device': device_serial,
            'package': instagram_package,
            'login_task_queued': True,
            'warmup_days': 7,
            'adb_clear_ok': adb_clear_ok,
            'adb_error': adb_error,
        })

    except Exception as e:
        log.error("Replace account error: %s", e, exc_info=True)
        return jsonify({'error': 'Replace failed: %s' % str(e)}), 500
    finally:
        conn.close()


# =====================================================================
#  ACCOUNT INVENTORY - API Endpoints
# =====================================================================

@account_health_bp.route('/api/inventory/v2')
def api_inventory_list():
    """
    GET /api/inventory/v2
    List all inventory accounts. Optional: ?status=available
    """
    conn = get_conn()
    try:
        status = request.args.get('status')
        query = "SELECT * FROM account_inventory"
        params = []

        if status:
            query += " WHERE status = ?"
            params.append(status)

        query += " ORDER BY id DESC"
        rows = conn.execute(query, params).fetchall()

        # Also get counts
        counts = {}
        for row in conn.execute(
            "SELECT status, COUNT(*) as count FROM account_inventory GROUP BY status"
        ).fetchall():
            counts[row['status']] = row['count']

        return jsonify({
            'accounts': rows_to_dicts(rows),
            'counts': counts,
            'total': sum(counts.values()),
        })
    finally:
        conn.close()


@account_health_bp.route('/api/inventory/v2/import', methods=['POST'])
def api_inventory_import():
    """
    POST /api/inventory/v2/import
    Body: { "text": "user1:pass1:email1\\nuser2:pass2:email2\\n..." }
    Format per line: username:password[:email[:phone[:2fa_token]]]
    """
    data = request.get_json() or {}
    text = data.get('text', '')

    if not text.strip():
        return jsonify({'error': 'No text provided'}), 400

    conn = get_conn()
    try:
        now = datetime.utcnow().isoformat()
        added = 0
        skipped = 0
        errors = []

        for line_num, line in enumerate(text.strip().split('\n'), 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            parts = line.split(':')
            if len(parts) < 2:
                errors.append("Line %d: need at least username:password" % line_num)
                continue

            username = parts[0].strip()
            password = parts[1].strip()
            email = parts[2].strip() if len(parts) > 2 else None
            phone = parts[3].strip() if len(parts) > 3 else None
            two_fa = parts[4].strip() if len(parts) > 4 else None

            if not username or not password:
                errors.append("Line %d: empty username or password" % line_num)
                continue

            # Check for duplicate
            existing = conn.execute(
                "SELECT id FROM account_inventory WHERE username = ?",
                (username,)
            ).fetchone()
            if existing:
                skipped += 1
                continue

            conn.execute("""
                INSERT INTO account_inventory
                    (username, password, email, phone, two_factor_auth, status, date_added)
                VALUES (?, ?, ?, ?, ?, 'available', ?)
            """, (username, password, email, phone, two_fa, now))
            added += 1

        conn.commit()
        return jsonify({
            'success': True,
            'added': added,
            'skipped': skipped,
            'errors': errors[:10],  # Cap error messages
        })
    finally:
        conn.close()


@account_health_bp.route('/api/inventory/v2/assign', methods=['POST'])
def api_inventory_assign():
    """
    POST /api/inventory/v2/assign
    Body: { "inventory_id": 5, "device_serial": "10.1.11.4_5555", "replace_account_id": 123 }
    Assigns an inventory account to a device, optionally replacing a flagged account.
    """
    data = request.get_json() or {}
    inventory_id = data.get('inventory_id')
    device_serial = data.get('device_serial')
    replace_account_id = data.get('replace_account_id')

    if not inventory_id or not device_serial:
        return jsonify({'error': 'inventory_id and device_serial required'}), 400

    conn = get_conn()
    try:
        now = datetime.utcnow().isoformat()

        # Check inventory account
        inv = conn.execute(
            "SELECT * FROM account_inventory WHERE id = ? AND status = 'available'",
            (inventory_id,)
        ).fetchone()
        if not inv:
            return jsonify({'error': 'Inventory account not found or not available'}), 404

        inv = dict(inv)

        # Mark inventory account as assigned
        conn.execute("""
            UPDATE account_inventory
            SET status = 'assigned',
                assigned_to_device_serial = ?,
                assigned_to_account_id = ?,
                assigned_at = ?
            WHERE id = ?
        """, (device_serial, replace_account_id, now, inventory_id))

        # If replacing a flagged account, resolve its health events
        if replace_account_id:
            conn.execute("""
                UPDATE account_health_events
                SET resolved_at = ?, resolved_by = 'auto_replace',
                    replacement_account_id = ?
                WHERE account_id = ? AND resolved_at IS NULL
            """, (now, inventory_id, replace_account_id))

            # Mark old account as disabled
            conn.execute(
                "UPDATE accounts SET status = 'replaced', updated_at = ? WHERE id = ?",
                (now, replace_account_id)
            )

        conn.commit()
        return jsonify({
            'success': True,
            'inventory_id': inventory_id,
            'username': inv['username'],
            'device_serial': device_serial,
        })
    finally:
        conn.close()


@account_health_bp.route('/api/inventory/v2/<int:inventory_id>', methods=['DELETE'])
def api_inventory_delete(inventory_id):
    """
    DELETE /api/inventory/v2/<id>
    Remove an account from inventory.
    """
    conn = get_conn()
    try:
        result = conn.execute(
            "DELETE FROM account_inventory WHERE id = ?",
            (inventory_id,)
        )
        conn.commit()
        if result.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True})
    finally:
        conn.close()


@account_health_bp.route('/api/inventory/v2/<int:inventory_id>/burn', methods=['POST'])
def api_inventory_burn(inventory_id):
    """
    POST /api/inventory/v2/<id>/burn
    Mark an inventory account as burned (permanently unusable).
    """
    conn = get_conn()
    try:
        now = datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE account_inventory SET status = 'burned', date_used = ? WHERE id = ?",
            (now, inventory_id)
        )
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()


# =====================================================================
#  Helper: Account status badge data (for other templates)
# =====================================================================

@account_health_bp.route('/api/account-status-badges')
def api_account_status_badges():
    """
    GET /api/account-status-badges
    Returns status for all accounts — used to render health badges
    on the devices page and accounts listing.
    """
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT a.id, a.username, a.device_serial, a.status,
                   (SELECT COUNT(*) FROM account_health_events he
                    WHERE he.account_id = a.id AND he.resolved_at IS NULL) as unresolved_events
            FROM accounts a
            ORDER BY a.device_serial, a.username
        """).fetchall()
        return jsonify(rows_to_dicts(rows))
    finally:
        conn.close()
