"""
analytics_routes.py - Instagram Analytics Dashboard
=====================================================
Business account insights from account_insights_v2 table.

Routes:
  GET /analytics                         → Analytics page
  GET /api/analytics/accounts            → List business accounts
  GET /api/analytics?accounts=...&days=  → Aggregated + per-account insights
"""

from flask import Blueprint, render_template, jsonify, request
from phone_farm_db import get_conn
from datetime import datetime, timedelta

analytics_bp = Blueprint('analytics', __name__)


def _row_to_dict(row):
    return dict(row) if row else None


def _rows_to_dicts(rows):
    return [dict(r) for r in rows] if rows else []


# ── Page Route ───────────────────────────────────────────────────────

@analytics_bp.route('/analytics')
@analytics_bp.route('/analytics/')
def analytics_page():
    import os
    err_path = os.path.join(os.path.dirname(__file__), 'logs', 'analytics_debug.log')
    with open(err_path, 'a') as f:
        f.write("analytics_page() called!\n")
    try:
        result = render_template('analytics.html')
        with open(err_path, 'a') as f:
            f.write(f"render OK, size={len(result)}\n")
        return result
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        with open(err_path, 'a') as f:
            f.write(f"RENDER ERROR: {tb}\n")
        return f"<pre>Error: {tb}</pre>", 500


# ── API: List business accounts ──────────────────────────────────────

@analytics_bp.route('/api/analytics/accounts')
def api_analytics_accounts():
    """Return all business accounts with device info."""
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT 
                a.username,
                a.device_serial,
                a.is_business_profile,
                a.business_category,
                a.business_switched_at,
                a.followers,
                d.device_name
            FROM accounts a
            LEFT JOIN devices d ON REPLACE(a.device_serial, '_', ':') = d.device_serial
            WHERE a.is_business_profile = 1
            ORDER BY a.username
        """).fetchall()

        accounts = []
        for r in rows:
            accounts.append({
                'username': r['username'],
                'device_serial': r['device_serial'],
                'device_name': r['device_name'] or r['device_serial'],
                'business_category': r['business_category'],
                'business_switched_at': r['business_switched_at'],
                'followers': r['followers'],
            })

        return jsonify({'accounts': accounts})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


# ── API: Analytics data ──────────────────────────────────────────────

@analytics_bp.route('/api/analytics')
def api_analytics():
    """
    Return aggregated + per-account insights data.
    Query params:
      accounts: comma-separated usernames (default: all business accounts)
      days: number of days to look back (default: 30)
    """
    conn = get_conn()
    try:
        # Get requested accounts
        accounts_param = request.args.get('accounts', '')
        days = int(request.args.get('days', 30))

        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        # Get all business accounts
        biz_rows = conn.execute("""
            SELECT a.username, a.device_serial, a.business_category, a.followers,
                   d.device_name
            FROM accounts a
            LEFT JOIN devices d ON REPLACE(a.device_serial, '_', ':') = d.device_serial
            WHERE a.is_business_profile = 1
        """).fetchall()
        all_biz = [r['username'] for r in biz_rows]
        biz_info = {r['username']: _row_to_dict(r) for r in biz_rows}

        # Filter to requested accounts
        if accounts_param:
            selected = [a.strip() for a in accounts_param.split(',') if a.strip()]
            selected = [a for a in selected if a in all_biz]
        else:
            selected = all_biz

        if not selected:
            return jsonify({
                'aggregated': {},
                'accounts': [],
                'business_accounts': all_biz
            })

        placeholders = ','.join(['?'] * len(selected))

        # Get latest record per account
        latest_records = {}
        for username in selected:
            row = conn.execute("""
                SELECT * FROM account_insights_v2
                WHERE account_id = ?
                ORDER BY scraped_at DESC
                LIMIT 1
            """, (username,)).fetchone()
            if row:
                latest_records[username] = _row_to_dict(row)

        # Get history (all records in date range)
        history_rows = conn.execute(f"""
            SELECT * FROM account_insights_v2
            WHERE account_id IN ({placeholders})
              AND scraped_at >= ?
            ORDER BY scraped_at ASC
        """, (*selected, cutoff)).fetchall()

        # Group history by account
        history_by_account = {}
        for r in _rows_to_dicts(history_rows):
            acct = r['account_id']
            if acct not in history_by_account:
                history_by_account[acct] = []
            history_by_account[acct].append(r)

        # Build per-account response
        accounts_data = []
        for username in selected:
            info = biz_info.get(username, {})
            latest = latest_records.get(username, {})
            history = history_by_account.get(username, [])

            # Get last scraped time
            last_scraped = latest.get('scraped_at', None)

            accounts_data.append({
                'username': username,
                'device_serial': info.get('device_serial', ''),
                'device_name': info.get('device_name', '') or info.get('device_serial', ''),
                'business_category': info.get('business_category', ''),
                'last_scraped': last_scraped,
                'latest': latest,
                'history': history,
            })

        # Aggregate across latest records
        agg = {
            'total_views': 0,
            'total_interactions': 0,
            'total_followers': 0,
            'total_reached': 0,
            'total_profile_visits': 0,
            'total_external_link_taps': 0,
            'total_new_followers': 0,
            'total_likes': 0,
            'avg_followers_pct': 0.0,
            'avg_non_followers_pct': 0.0,
            'avg_reels_views_pct': 0.0,
            'avg_posts_views_pct': 0.0,
        }

        pct_counts = 0
        for username in selected:
            rec = latest_records.get(username, {})
            agg['total_views'] += (rec.get('views') or 0)
            agg['total_interactions'] += (rec.get('interactions') or 0)
            agg['total_followers'] += (rec.get('total_followers') or 0)
            agg['total_reached'] += (rec.get('accounts_reached') or 0)
            agg['total_profile_visits'] += (rec.get('profile_visits') or 0)
            agg['total_external_link_taps'] += (rec.get('external_link_taps') or 0)
            agg['total_new_followers'] += (rec.get('new_followers') or 0)
            agg['total_likes'] += (rec.get('likes_count') or 0)

            if rec.get('views_followers_pct') is not None:
                agg['avg_followers_pct'] += rec['views_followers_pct']
                agg['avg_non_followers_pct'] += (rec.get('views_non_followers_pct') or (100 - rec['views_followers_pct']))
                pct_counts += 1

            if rec.get('reels_views_pct') is not None:
                agg['avg_reels_views_pct'] += rec['reels_views_pct']
            if rec.get('posts_views_pct') is not None:
                agg['avg_posts_views_pct'] += rec['posts_views_pct']

        if pct_counts > 0:
            agg['avg_followers_pct'] = round(agg['avg_followers_pct'] / pct_counts, 1)
            agg['avg_non_followers_pct'] = round(agg['avg_non_followers_pct'] / pct_counts, 1)
        if len(selected) > 0:
            agg['avg_reels_views_pct'] = round(agg['avg_reels_views_pct'] / len(selected), 1)
            agg['avg_posts_views_pct'] = round(agg['avg_posts_views_pct'] / len(selected), 1)

        return jsonify({
            'aggregated': agg,
            'accounts': accounts_data,
            'business_accounts': all_biz,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()
