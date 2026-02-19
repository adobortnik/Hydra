"""
source_quality_routes.py - Source Quality Scoring & Warm-up Status Dashboard
=============================================================================
Tracks which tag groups and source accounts generate the best follower growth.
Also provides warm-up status per account.

API endpoints:
  GET /api/source-quality?days=7      → Tag performance + source scoring
  GET /api/warmup-status              → Warm-up status per account
  POST /api/warmup-toggle             → Toggle warmup on/off for an account
"""

import os
import json
import sqlite3
from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify, request

# DB path
DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'db', 'phone_farm.db'
)

source_quality_bp = Blueprint('source_quality', __name__)


def _get_conn():
    """Thread-safe connection with Row factory."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _date_n_days_ago(n):
    return (datetime.utcnow() - timedelta(days=n)).strftime('%Y-%m-%d')


def _today():
    return datetime.utcnow().strftime('%Y-%m-%d')


# ── Page Route ───────────────────────────────────────────────────────

@source_quality_bp.route('/source-quality')
def source_quality_page():
    return render_template('source_quality.html')


# ── API: Source Quality Scoring ──────────────────────────────────────

@source_quality_bp.route('/api/source-quality')
def api_source_quality():
    conn = _get_conn()
    try:
        days_param = request.args.get('days', '7')
        if days_param == 'all':
            since = '1970-01-01'
            period_days = None
        else:
            period_days = int(days_param)
            since = _date_n_days_ago(period_days)

        # ── By Tag ──────────────────────────────────────────────
        # Get all accounts grouped by tag
        tag_rows = conn.execute("""
            SELECT a.tag, COUNT(a.id) as account_count,
                   GROUP_CONCAT(a.id) as account_ids
            FROM accounts a
            WHERE a.tag IS NOT NULL AND a.tag != ''
            GROUP BY a.tag
            ORDER BY account_count DESC
        """).fetchall()

        by_tag = []
        for tr in tag_rows:
            tag = tr['tag']
            account_ids = [int(x) for x in tr['account_ids'].split(',')]
            account_count = tr['account_count']
            placeholders = ','.join('?' * len(account_ids))

            # Get usernames for these account_ids
            username_rows = conn.execute(
                f"SELECT username FROM accounts WHERE id IN ({placeholders})",
                account_ids
            ).fetchall()
            usernames = [r['username'] for r in username_rows]
            u_placeholders = ','.join('?' * len(usernames))

            # Sum successful follows in period
            follows_row = conn.execute(f"""
                SELECT COUNT(*) as cnt FROM action_history
                WHERE username IN ({u_placeholders})
                  AND action_type = 'follow'
                  AND success = 1
                  AND date(timestamp) >= ?
            """, usernames + [since]).fetchone()
            total_follows = follows_row['cnt'] if follows_row else 0

            # Calculate follower growth from follower_snapshots
            # Growth = latest snapshot - earliest snapshot for each account in period
            growth = 0
            has_snapshots = False
            for uname in usernames:
                earliest = conn.execute("""
                    SELECT followers FROM follower_snapshots
                    WHERE username = ? AND date(captured_at) >= ?
                    ORDER BY captured_at ASC LIMIT 1
                """, (uname, since)).fetchone()
                latest = conn.execute("""
                    SELECT followers FROM follower_snapshots
                    WHERE username = ? AND date(captured_at) >= ?
                    ORDER BY captured_at DESC LIMIT 1
                """, (uname, since)).fetchone()
                if earliest and latest:
                    has_snapshots = True
                    growth += (latest['followers'] or 0) - (earliest['followers'] or 0)

            conversion = round((growth / total_follows * 100), 1) if total_follows > 0 else 0

            by_tag.append({
                'tag': tag,
                'accounts': account_count,
                'total_follows': total_follows,
                'follower_growth': growth if has_snapshots else None,
                'conversion_rate': conversion if has_snapshots else None,
                'has_snapshots': has_snapshots,
                'period_days': period_days,
            })

        # ── By Source ───────────────────────────────────────────
        source_rows = conn.execute("""
            SELECT ah.source_username,
                   COUNT(*) as follows_count,
                   COUNT(DISTINCT ah.username) as used_by_accounts
            FROM action_history ah
            WHERE ah.source_username IS NOT NULL
              AND ah.action_type = 'follow'
              AND ah.success = 1
              AND date(ah.timestamp) >= ?
            GROUP BY ah.source_username
            ORDER BY follows_count DESC
            LIMIT 50
        """, (since,)).fetchall()

        by_source = []
        for sr in source_rows:
            src = sr['source_username']
            # Try to find which tag uses this source
            tag_row = conn.execute("""
                SELECT a.tag FROM accounts a
                JOIN account_sources asrc ON asrc.account_id = a.id
                WHERE asrc.value = ? AND asrc.source_type = 'sources'
                  AND a.tag IS NOT NULL AND a.tag != ''
                LIMIT 1
            """, (src,)).fetchone()
            used_by_tag = tag_row['tag'] if tag_row else None

            by_source.append({
                'source_username': src,
                'follows_from_source': sr['follows_count'],
                'used_by_accounts': sr['used_by_accounts'],
                'used_by_tag': used_by_tag,
            })

        # ── Overall ─────────────────────────────────────────────
        overall_row = conn.execute("""
            SELECT COUNT(*) as total_follows FROM action_history
            WHERE action_type = 'follow' AND success = 1
              AND date(timestamp) >= ?
        """, (since,)).fetchone()
        total_follows_all = overall_row['total_follows'] if overall_row else 0

        # Total growth from snapshots
        total_growth = 0
        has_any_snapshots = False
        snap_check = conn.execute("SELECT COUNT(*) as cnt FROM follower_snapshots").fetchone()
        if snap_check and snap_check['cnt'] > 0:
            has_any_snapshots = True
            growth_row = conn.execute("""
                SELECT username,
                       MAX(CASE WHEN rn_desc = 1 THEN followers END) -
                       MAX(CASE WHEN rn_asc = 1 THEN followers END) as growth
                FROM (
                    SELECT username, followers,
                           ROW_NUMBER() OVER(PARTITION BY username ORDER BY captured_at DESC) as rn_desc,
                           ROW_NUMBER() OVER(PARTITION BY username ORDER BY captured_at ASC) as rn_asc
                    FROM follower_snapshots
                    WHERE date(captured_at) >= ?
                ) sub
                WHERE rn_desc = 1 OR rn_asc = 1
                GROUP BY username
            """, (since,)).fetchall()
            for gr in growth_row:
                if gr['growth']:
                    total_growth += gr['growth']

        avg_conversion = round((total_growth / total_follows_all * 100), 1) if total_follows_all > 0 and has_any_snapshots else 0

        # ── Untagged accounts summary ───────────────────────────
        untagged_row = conn.execute("""
            SELECT COUNT(*) as cnt FROM accounts
            WHERE tag IS NULL OR tag = ''
        """).fetchone()
        untagged_count = untagged_row['cnt'] if untagged_row else 0

        return jsonify({
            'by_tag': by_tag,
            'by_source': by_source,
            'overall': {
                'total_follows': total_follows_all,
                'total_growth': total_growth if has_any_snapshots else None,
                'avg_conversion': avg_conversion if has_any_snapshots else None,
                'has_snapshots': has_any_snapshots,
            },
            'untagged_accounts': untagged_count,
            'period': days_param,
        })
    finally:
        conn.close()


# ── API: Warm-up Status ─────────────────────────────────────────────

@source_quality_bp.route('/api/warmup-status')
def api_warmup_status():
    conn = _get_conn()
    try:
        today = _today()

        rows = conn.execute("""
            SELECT a.id, a.username, a.device_serial, a.tag, a.status,
                   a.warmup, a.warmup_until,
                   d.device_name
            FROM accounts a
            LEFT JOIN devices d ON d.id = a.device_id
            ORDER BY a.warmup DESC, a.tag, a.username
        """).fetchall()

        accounts = []
        for r in rows:
            acc_id = r['id']
            username = r['username']

            # Days active: days since first action
            first_action = conn.execute("""
                SELECT MIN(timestamp) as first_ts FROM action_history
                WHERE username = ?
            """, (username,)).fetchone()
            if first_action and first_action['first_ts']:
                try:
                    first_dt = datetime.fromisoformat(first_action['first_ts'])
                    days_active = (datetime.utcnow() - first_dt).days
                except (ValueError, TypeError):
                    days_active = 0
            else:
                days_active = 0

            # Actions today
            actions_today_row = conn.execute("""
                SELECT COUNT(*) as cnt FROM action_history
                WHERE username = ? AND date(timestamp) = ? AND success = 1
            """, (username, today)).fetchone()
            actions_today = actions_today_row['cnt'] if actions_today_row else 0

            # Check warmup from account_settings JSON too
            settings_warmup = False
            settings_row = conn.execute("""
                SELECT settings_json FROM account_settings WHERE account_id = ?
            """, (acc_id,)).fetchone()
            if settings_row:
                try:
                    sj = json.loads(settings_row['settings_json'])
                    settings_warmup = sj.get('warmup_mode', False)
                except (json.JSONDecodeError, TypeError):
                    pass

            is_warmup = bool(r['warmup']) or settings_warmup

            accounts.append({
                'id': acc_id,
                'username': username,
                'device_serial': r['device_serial'],
                'device_name': r['device_name'],
                'tag': r['tag'] or '',
                'status': r['status'],
                'days_active': days_active,
                'actions_today': actions_today,
                'warmup': is_warmup,
                'warmup_until': r['warmup_until'],
            })

        return jsonify(accounts)
    finally:
        conn.close()


# ── API: Toggle Warm-up ─────────────────────────────────────────────

@source_quality_bp.route('/api/warmup-toggle', methods=['POST'])
def api_warmup_toggle():
    conn = _get_conn()
    try:
        data = request.get_json()
        account_id = data.get('account_id')
        enable = data.get('enable', False)
        warmup_until = data.get('warmup_until')  # optional YYYY-MM-DD

        if not account_id:
            return jsonify({'error': 'account_id required'}), 400

        now = datetime.utcnow().isoformat()
        if enable:
            # Default warmup_until: 3 days from now
            if not warmup_until:
                warmup_until = (datetime.utcnow() + timedelta(days=3)).strftime('%Y-%m-%d')
            conn.execute(
                "UPDATE accounts SET warmup = 1, warmup_until = ?, updated_at = ? WHERE id = ?",
                (warmup_until, now, account_id)
            )
            # Also set in account_settings JSON
            settings_row = conn.execute(
                "SELECT settings_json FROM account_settings WHERE account_id = ?",
                (account_id,)
            ).fetchone()
            if settings_row:
                try:
                    sj = json.loads(settings_row['settings_json'])
                    sj['warmup_mode'] = True
                    conn.execute(
                        "UPDATE account_settings SET settings_json = ?, updated_at = ? WHERE account_id = ?",
                        (json.dumps(sj), now, account_id)
                    )
                except (json.JSONDecodeError, TypeError):
                    pass
        else:
            conn.execute(
                "UPDATE accounts SET warmup = 0, warmup_until = NULL, updated_at = ? WHERE id = ?",
                (now, account_id)
            )
            settings_row = conn.execute(
                "SELECT settings_json FROM account_settings WHERE account_id = ?",
                (account_id,)
            ).fetchone()
            if settings_row:
                try:
                    sj = json.loads(settings_row['settings_json'])
                    sj['warmup_mode'] = False
                    conn.execute(
                        "UPDATE account_settings SET settings_json = ?, updated_at = ? WHERE account_id = ?",
                        (json.dumps(sj), now, account_id)
                    )
                except (json.JSONDecodeError, TypeError):
                    pass

        conn.commit()
        return jsonify({'success': True, 'warmup': enable})
    finally:
        conn.close()
