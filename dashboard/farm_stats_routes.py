"""
farm_stats_routes.py - Farm Stats & Analytics Dashboard
READ-ONLY analytics over phone_farm.db tables:
  action_history, account_stats, account_sessions, bot_status, bot_logs
"""

from flask import Blueprint, render_template, jsonify, request
from phone_farm_db import get_conn, row_to_dict
from datetime import datetime, timedelta

farm_stats_bp = Blueprint('farm_stats', __name__)


# ── Helper ───────────────────────────────────────────────────────────

def _date_n_days_ago(n):
    return (datetime.utcnow() - timedelta(days=n)).strftime('%Y-%m-%d')


def _today():
    return datetime.utcnow().strftime('%Y-%m-%d')


# ── Page route ───────────────────────────────────────────────────────

@farm_stats_bp.route('/farm-stats')
def farm_stats_page():
    return render_template('farm_stats.html')


# ── API: Summary cards ──────────────────────────────────────────────

@farm_stats_bp.route('/api/farm-stats/summary')
def api_summary():
    conn = get_conn()
    try:
        today = _today()
        week_ago = _date_n_days_ago(7)

        # Total actions today
        r = conn.execute(
            "SELECT COUNT(*) as cnt FROM action_history WHERE date(timestamp) = ?", (today,)
        ).fetchone()
        actions_today = r['cnt'] if r else 0

        # Total actions this week
        r = conn.execute(
            "SELECT COUNT(*) as cnt FROM action_history WHERE date(timestamp) >= ?", (week_ago,)
        ).fetchone()
        actions_week = r['cnt'] if r else 0

        # Total actions all time
        r = conn.execute("SELECT COUNT(*) as cnt FROM action_history").fetchone()
        actions_all = r['cnt'] if r else 0

        # Active devices
        r = conn.execute(
            "SELECT COUNT(*) as cnt FROM bot_status WHERE status NOT IN ('idle','stopped')"
        ).fetchone()
        active_devices = r['cnt'] if r else 0

        # Total devices
        r = conn.execute("SELECT COUNT(*) as cnt FROM bot_status").fetchone()
        total_devices = r['cnt'] if r else 0

        # Sessions today
        r = conn.execute(
            "SELECT COUNT(*) as cnt FROM account_sessions WHERE date(session_start) = ?", (today,)
        ).fetchone()
        sessions_today = r['cnt'] if r else 0

        # Error rate
        r = conn.execute("SELECT COUNT(*) as total, SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as failed FROM action_history").fetchone()
        total_acts = r['total'] if r else 0
        failed_acts = r['failed'] if r else 0
        error_rate = round((failed_acts / total_acts * 100), 1) if total_acts > 0 else 0

        return jsonify({
            'actions_today': actions_today,
            'actions_week': actions_week,
            'actions_all': actions_all,
            'active_devices': active_devices,
            'total_devices': total_devices,
            'sessions_today': sessions_today,
            'error_rate': error_rate,
            'failed_actions': failed_acts,
            'total_actions': total_acts
        })
    finally:
        conn.close()


# ── API: Actions over time ──────────────────────────────────────────

@farm_stats_bp.route('/api/farm-stats/actions-over-time')
def api_actions_over_time():
    conn = get_conn()
    try:
        days = request.args.get('days', '30')
        if days == 'all':
            where = ''
            params = []
        else:
            n = int(days)
            since = _date_n_days_ago(n)
            where = 'WHERE date(timestamp) >= ?'
            params = [since]

        rows = conn.execute(f"""
            SELECT date(timestamp) as day, action_type, COUNT(*) as cnt
            FROM action_history
            {where}
            GROUP BY day, action_type
            ORDER BY day
        """, params).fetchall()

        # Build {date: {type: count}}
        data = {}
        action_types = set()
        for r in rows:
            d = r['day']
            at = r['action_type']
            action_types.add(at)
            if d not in data:
                data[d] = {}
            data[d][at] = r['cnt']

        dates = sorted(data.keys())
        action_types = sorted(action_types)

        series = {}
        for at in action_types:
            series[at] = [data.get(d, {}).get(at, 0) for d in dates]

        return jsonify({'dates': dates, 'series': series, 'action_types': action_types})
    finally:
        conn.close()


# ── API: Action breakdown (doughnut) ────────────────────────────────

@farm_stats_bp.route('/api/farm-stats/action-breakdown')
def api_action_breakdown():
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT action_type, COUNT(*) as cnt
            FROM action_history
            GROUP BY action_type
            ORDER BY cnt DESC
        """).fetchall()
        labels = [r['action_type'] for r in rows]
        values = [r['cnt'] for r in rows]
        return jsonify({'labels': labels, 'values': values})
    finally:
        conn.close()


# ── API: Follower growth ────────────────────────────────────────────

@farm_stats_bp.route('/api/farm-stats/follower-growth')
def api_follower_growth():
    conn = get_conn()
    try:
        mode = request.args.get('mode', 'top10')  # top10 | all | <account_id>
        days = request.args.get('days', '90')

        if days == 'all':
            date_filter = ''
            params = []
        else:
            n = int(days)
            since = _date_n_days_ago(n)
            date_filter = 'AND s.date >= ?'
            params = [since]

        if mode == 'all':
            # Average followers across all accounts per day
            rows = conn.execute(f"""
                SELECT s.date, CAST(AVG(CAST(s.followers AS REAL)) AS INTEGER) as avg_followers
                FROM account_stats s
                WHERE 1=1 {date_filter}
                GROUP BY s.date
                ORDER BY s.date
            """, params).fetchall()
            return jsonify({
                'mode': 'all',
                'dates': [r['date'] for r in rows],
                'series': {'Average': [r['avg_followers'] for r in rows]}
            })

        elif mode == 'top10':
            # Find top 10 accounts by latest follower count
            top_ids = conn.execute("""
                SELECT account_id, MAX(CAST(followers AS INTEGER)) as max_f
                FROM account_stats
                GROUP BY account_id
                ORDER BY max_f DESC
                LIMIT 10
            """).fetchall()
            account_ids = [r['account_id'] for r in top_ids]

            if not account_ids:
                return jsonify({'mode': 'top10', 'dates': [], 'series': {}})

            placeholders = ','.join('?' * len(account_ids))

            # Get usernames
            names = {}
            name_rows = conn.execute(
                f"SELECT id, username FROM accounts WHERE id IN ({placeholders})", account_ids
            ).fetchall()
            for nr in name_rows:
                names[nr['id']] = nr['username']

            rows = conn.execute(f"""
                SELECT s.account_id, s.date, CAST(s.followers AS INTEGER) as followers
                FROM account_stats s
                WHERE s.account_id IN ({placeholders}) {date_filter}
                ORDER BY s.date
            """, account_ids + params).fetchall()

            # Build series
            all_dates = sorted(set(r['date'] for r in rows))
            series = {}
            for aid in account_ids:
                label = names.get(aid, f'Account #{aid}')
                acct_data = {r['date']: r['followers'] for r in rows if r['account_id'] == aid}
                series[label] = [acct_data.get(d, None) for d in all_dates]

            return jsonify({'mode': 'top10', 'dates': all_dates, 'series': series})

        else:
            # Specific account
            try:
                aid = int(mode)
            except ValueError:
                return jsonify({'error': 'Invalid account id'}), 400

            name_row = conn.execute("SELECT username FROM accounts WHERE id = ?", (aid,)).fetchone()
            label = name_row['username'] if name_row else f'Account #{aid}'

            rows = conn.execute(f"""
                SELECT date, CAST(followers AS INTEGER) as followers
                FROM account_stats
                WHERE account_id = ? {date_filter}
                ORDER BY date
            """, [aid] + params).fetchall()

            return jsonify({
                'mode': 'account',
                'account_id': aid,
                'dates': [r['date'] for r in rows],
                'series': {label: [r['followers'] for r in rows]}
            })
    finally:
        conn.close()


# ── API: Account list for dropdown ──────────────────────────────────

@farm_stats_bp.route('/api/farm-stats/accounts')
def api_accounts_list():
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT a.id, a.username, MAX(CAST(s.followers AS INTEGER)) as max_followers
            FROM accounts a
            LEFT JOIN account_stats s ON s.account_id = a.id
            GROUP BY a.id
            ORDER BY max_followers DESC
        """).fetchall()
        return jsonify([{'id': r['id'], 'username': r['username'], 'followers': r['max_followers'] or 0} for r in rows])
    finally:
        conn.close()


# ── API: Recent activity ────────────────────────────────────────────

@farm_stats_bp.route('/api/farm-stats/recent-activity')
def api_recent_activity():
    conn = get_conn()
    try:
        limit = request.args.get('limit', 50, type=int)
        rows = conn.execute("""
            SELECT id, device_serial, username, action_type, target_username,
                   target_post_id, success, timestamp, error_message
            FROM action_history
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


# ── API: Per-device stats ───────────────────────────────────────────

@farm_stats_bp.route('/api/farm-stats/device-stats')
def api_device_stats():
    conn = get_conn()
    try:
        today = _today()

        rows = conn.execute("""
            SELECT
                bs.device_serial,
                bs.status,
                bs.started_at,
                bs.last_check_at,
                bs.actions_today,
                bs.accounts_run_today,
                (SELECT COUNT(DISTINCT ah.username) FROM action_history ah WHERE ah.device_serial = bs.device_serial) as total_accounts,
                (SELECT COUNT(*) FROM action_history ah WHERE ah.device_serial = bs.device_serial AND date(ah.timestamp) = ?) as actions_today_actual,
                (SELECT COUNT(*) FROM account_sessions s WHERE s.device_serial = bs.device_serial AND date(s.session_start) = ?) as sessions_today
            FROM bot_status bs
            ORDER BY bs.device_serial
        """, (today, today)).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


# ── API: Error log ──────────────────────────────────────────────────

@farm_stats_bp.route('/api/farm-stats/errors')
def api_errors():
    conn = get_conn()
    try:
        limit = request.args.get('limit', 100, type=int)
        rows = conn.execute("""
            SELECT id, device_serial, username, action_type, target_username,
                   timestamp, error_message
            FROM action_history
            WHERE success = 0
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()
