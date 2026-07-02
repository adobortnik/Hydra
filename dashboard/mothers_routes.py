"""
Mothers routes — Mother account dashboard backend.
==================================================
Endpoints:
  GET  /api/mothers              — list all mother accounts with stats + slave counts
  GET  /api/mothers/<id>/slaves  — slave accounts (same tag, is_mother=0)
  POST /api/accounts/<id>/mother — set/unset is_mother flag (body: {is_mother: 0|1})
"""

import os
import sqlite3
import subprocess
import time
from flask import Blueprint, jsonify, request, render_template, abort, Response

mothers_bp = Blueprint('mothers', __name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'db', 'phone_farm.db')


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _normalize_tag(tag):
    """Lowercase + strip + return None if empty. Tags can be comma-separated."""
    if not tag:
        return None
    return tag.strip().lower() or None


def _split_tags(tag_str):
    """Settings store tags as comma-separated string. Return set of normalized tags."""
    if not tag_str:
        return set()
    return {t.strip().lower() for t in tag_str.split(',') if t.strip()}


def _parse_account_status_for_response(row):
    """Parse account_status_json from DB row + return enriched dict for UI."""
    raw = row['account_status_json'] if 'account_status_json' in row.keys() else None
    if not raw:
        return None
    try:
        import json as _json
        d = _json.loads(raw)
        d['checked_at'] = row['account_status_checked_at'] if 'account_status_checked_at' in row.keys() else None
        d['issues'] = sum(1 for k, v in d.items()
                          if k not in ('captured_at', 'checked_at') and v == 'warning')
        return d
    except Exception:
        return None


def _account_status(row, unresolved_event_count):
    """
    Determine status badge for the mothers table.
    Returns one of: 'ok', 'warning', 'error'.
    - ok      = status='active' AND no unresolved events
    - warning = status='active' AND has unresolved events
    - error   = status NOT in ('active') (logged_out, suspended, banned, etc.)
    """
    status = (row['status'] or '').lower()
    if status not in ('active', '', 'ok'):
        return 'error'
    if unresolved_event_count > 0:
        return 'warning'
    return 'ok'


def _last_post_map(conn, account_ids=None):
    """Map account_id -> ISO timestamp of the most recent snapshot where the IG
    posts_count INCREASED vs the previous snapshot (≈ when the account last
    posted). Returns None for accounts with no observed increase in snapshot
    history. Source: follower_snapshots posts_count over time (works for both
    mothers — which post organically, not via Hydra — and slaves)."""
    where = "WHERE posts_count IS NOT NULL"
    params = []
    if account_ids:
        ph = ','.join('?' * len(account_ids))
        where += f" AND account_id IN ({ph})"
        params = list(account_ids)
    q = f"""
        WITH snaps AS (
            SELECT account_id, captured_at, posts_count,
                   LAG(posts_count) OVER (
                       PARTITION BY account_id ORDER BY captured_at
                   ) AS prev_pc
            FROM follower_snapshots
            {where}
        )
        SELECT account_id, MAX(captured_at) AS last_post_at
        FROM snaps
        WHERE prev_pc IS NOT NULL AND posts_count > prev_pc
        GROUP BY account_id
    """
    try:
        return {r['account_id']: r['last_post_at']
                for r in conn.execute(q, params).fetchall()}
    except Exception:
        return {}


@mothers_bp.route('/api/mothers', methods=['GET'])
def list_mothers():
    """
    Return all mother accounts with denormalized stats + slave counts.
    Slave count = accounts sharing any tag with the mother where is_mother=0.
    """
    conn = _conn()
    try:
        # Pull all mothers with their device info
        rows = conn.execute("""
            SELECT a.id, a.username, a.tag, a.followers, a.following, a.posts,
                   a.status, a.is_business_profile, a.is_mother, a.device_serial,
                   a.profile_link, a.display_name, a.updated_at,
                   d.device_name, d.device_group, d.status AS device_status
            FROM accounts a
            LEFT JOIN devices d ON d.device_serial = a.device_serial
            WHERE a.is_mother = 1
            ORDER BY a.tag, a.username
        """).fetchall()

        # Pull unresolved health event counts per account in one query
        event_rows = conn.execute("""
            SELECT account_id, COUNT(*) AS cnt
            FROM account_health_events
            WHERE resolved_at IS NULL
            GROUP BY account_id
        """).fetchall()
        unresolved_map = {r['account_id']: r['cnt'] for r in event_rows}

        # Last-post time per mother (from posts_count snapshot increases)
        last_post_map = _last_post_map(conn)

        # Pull slave counts per tag in one query
        # A slave is is_mother=0 with a tag. We count distinct accounts per tag.
        slave_counts = {}
        for r in conn.execute("""
            SELECT tag, COUNT(*) AS cnt
            FROM accounts
            WHERE is_mother = 0 AND tag IS NOT NULL AND tag != ''
            GROUP BY tag
        """).fetchall():
            tag_set = _split_tags(r['tag'])
            for t in tag_set:
                slave_counts[t] = slave_counts.get(t, 0) + r['cnt']

        # But the above multi-counts when slave has multi-tag. Use a different approach:
        # Build a per-account tag set, then sum 1 per matching tag.
        slave_counts = {}
        for r in conn.execute(
            "SELECT tag FROM accounts WHERE is_mother = 0 AND tag IS NOT NULL AND tag != ''"
        ).fetchall():
            for t in _split_tags(r['tag']):
                slave_counts[t] = slave_counts.get(t, 0) + 1

        result = []
        for row in rows:
            mother_tags = _split_tags(row['tag'])
            # Slave count = sum across all this mother's tags (deduped)
            # If mother has tags "jagger,vip", we want unique slaves with tag in either.
            # Simpler approximation: max across tags. For now: just first tag's count.
            # Better: query directly per mother for accuracy.
            slave_count = 0
            if mother_tags:
                placeholders = ','.join('?' * len(mother_tags))
                params = list(mother_tags) + [row['id']]
                # Count distinct slaves where any of their tags overlap with mother's tags
                slave_rows = conn.execute(f"""
                    SELECT id, tag FROM accounts
                    WHERE is_mother = 0 AND tag IS NOT NULL AND tag != '' AND id != ?
                """, (row['id'],)).fetchall()
                for sr in slave_rows:
                    slave_tags = _split_tags(sr['tag'])
                    if mother_tags & slave_tags:
                        slave_count += 1

            unresolved = unresolved_map.get(row['id'], 0)
            status_kind = _account_status(row, unresolved)

            result.append({
                'id': row['id'],
                'username': row['username'],
                'display_name': row['display_name'],
                'tag': row['tag'] or '',
                'tags': sorted(mother_tags),
                'posts': row['posts'] or 0,
                'followers': row['followers'] or 0,
                'following': row['following'] or 0,
                'status': row['status'],
                'status_kind': status_kind,
                'is_business_profile': bool(row['is_business_profile']),
                'profile_link': row['profile_link'],
                'device_serial': row['device_serial'],
                'device_name': row['device_name'],
                'device_group': row['device_group'],
                'device_status': row['device_status'],
                'unresolved_events': unresolved,
                'slave_count': slave_count,
                'updated_at': row['updated_at'],
                'last_post_at': last_post_map.get(row['id']),
            })

        return jsonify({'success': True, 'mothers': result, 'total': len(result)})
    finally:
        conn.close()


@mothers_bp.route('/api/mothers/<int:account_id>/slaves', methods=['GET'])
def list_slaves(account_id):
    """Return slave accounts that share any tag with the given mother."""
    conn = _conn()
    try:
        mother = conn.execute(
            "SELECT id, username, tag FROM accounts WHERE id=? AND is_mother=1",
            (account_id,)
        ).fetchone()
        if not mother:
            return jsonify({'success': False, 'error': 'Mother account not found'}), 404

        mother_tags = _split_tags(mother['tag'])
        if not mother_tags:
            return jsonify({'success': True, 'slaves': [], 'mother': dict(mother)})

        # Pull all candidate slaves (is_mother=0, has any tag), filter in Python
        rows = conn.execute("""
            SELECT a.id, a.username, a.tag, a.followers, a.following, a.posts,
                   a.status, a.device_serial, a.account_status_json, a.account_status_checked_at,
                   a.start_time, a.end_time,
                   d.device_name, d.device_group
            FROM accounts a
            LEFT JOIN devices d ON d.device_serial = a.device_serial
            WHERE a.is_mother = 0 AND a.tag IS NOT NULL AND a.tag != '' AND a.id != ?
            ORDER BY a.username
        """, (account_id,)).fetchall()

        # Filter slaves by mother tag overlap
        matching_slaves = [
            r for r in rows if mother_tags & _split_tags(r['tag'])
        ]
        if not matching_slaves:
            return jsonify({
                'success': True,
                'mother': {'id': mother['id'], 'username': mother['username'], 'tag': mother['tag']},
                'slaves': [],
                'total': 0,
            })

        # ── Bulk-fetch action stats for all slaves in 2 queries ─────────
        slave_usernames = [r['username'] for r in matching_slaves]
        ph = ','.join('?' * len(slave_usernames))
        # today + 7d action counts grouped by user
        today_rows = conn.execute(f"""
            SELECT username, action_type, COUNT(*) AS cnt
            FROM action_history
            WHERE username IN ({ph}) AND DATE(timestamp)=DATE('now') AND success=1
            GROUP BY username, action_type
        """, slave_usernames).fetchall()
        week_rows = conn.execute(f"""
            SELECT username, action_type, COUNT(*) AS cnt
            FROM action_history
            WHERE username IN ({ph})
              AND timestamp >= datetime('now', '-7 days')
              AND success=1
            GROUP BY username, action_type
        """, slave_usernames).fetchall()
        err_rows = conn.execute(f"""
            SELECT username, COUNT(*) AS cnt
            FROM action_history
            WHERE username IN ({ph}) AND DATE(timestamp)=DATE('now') AND success=0
            GROUP BY username
        """, slave_usernames).fetchall()
        last_rows = conn.execute(f"""
            SELECT username, MAX(timestamp) AS last_at
            FROM action_history
            WHERE username IN ({ph})
            GROUP BY username
        """, slave_usernames).fetchall()
        # unresolved health events
        health_rows = conn.execute(f"""
            SELECT username, COUNT(*) AS cnt
            FROM account_health_events
            WHERE username IN ({ph}) AND resolved_at IS NULL
            GROUP BY username
        """, slave_usernames).fetchall()

        today_actions, week_actions = {}, {}
        for r in today_rows:
            today_actions.setdefault(r['username'], {})[r['action_type']] = r['cnt']
        for r in week_rows:
            week_actions.setdefault(r['username'], {})[r['action_type']] = r['cnt']
        errors_today = {r['username']: r['cnt'] for r in err_rows}
        last_action = {r['username']: r['last_at'] for r in last_rows}
        unresolved_events = {r['username']: r['cnt'] for r in health_rows}
        # Last-post time per slave (posts_count snapshot increases)
        last_post_map = _last_post_map(conn, [r['id'] for r in matching_slaves])

        slaves = []
        for r in matching_slaves:
            uname = r['username']
            tact = today_actions.get(uname, {})
            wact = week_actions.get(uname, {})
            # Parse account_status_json
            acc_status = None
            if r['account_status_json']:
                try:
                    import json as _json
                    acc_status = _json.loads(r['account_status_json'])
                    acc_status['checked_at'] = r['account_status_checked_at']
                    issues = sum(1 for k, v in acc_status.items()
                                 if k not in ('captured_at', 'checked_at') and v == 'warning')
                    acc_status['issues'] = issues
                except Exception:
                    acc_status = None
            slaves.append({
                'id': r['id'],
                'username': uname,
                'tag': r['tag'],
                'posts': r['posts'] or 0,
                'followers': r['followers'] or 0,
                'following': r['following'] or 0,
                'status': r['status'],
                'account_status': acc_status,
                'device_serial': r['device_serial'],
                'device_name': r['device_name'],
                'device_group': r['device_group'],
                'start_time': r['start_time'],
                'end_time': r['end_time'],
                'last_post_at': last_post_map.get(r['id']),
                # New stats
                'today': {
                    'follows': tact.get('follow', 0),
                    'likes': tact.get('like', 0) + tact.get('reel_like', 0),
                    'shares': tact.get('share_to_story', 0),
                    'dms': tact.get('dm', 0),
                    'comments': tact.get('comment', 0),
                    'reels': tact.get('reel_watch', 0),
                    'stories': tact.get('story_view', 0),
                    'total': sum(tact.values()),
                },
                'week_total': sum(wact.values()),
                'errors_today': errors_today.get(uname, 0),
                'last_action_at': last_action.get(uname),
                'unresolved_events': unresolved_events.get(uname, 0),
            })

        return jsonify({
            'success': True,
            'mother': {'id': mother['id'], 'username': mother['username'], 'tag': mother['tag']},
            'slaves': slaves,
            'total': len(slaves),
        })
    finally:
        conn.close()


@mothers_bp.route('/mothers/<int:account_id>', methods=['GET'])
def mother_detail_page(account_id):
    """Render the mother account detail page with phone mockup + slaves overview."""
    conn = _conn()
    try:
        row = conn.execute("""
            SELECT a.id, a.username, a.tag, a.followers, a.following, a.posts,
                   a.status, a.is_business_profile, a.is_mother, a.device_serial,
                   a.profile_link, a.display_name, a.updated_at,
                   a.start_time, a.end_time,
                   d.device_name, d.device_group
            FROM accounts a
            LEFT JOIN devices d ON d.device_serial = a.device_serial
            WHERE a.id = ? AND a.is_mother = 1
        """, (account_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        abort(404)
    mother = dict(row)
    # Last-post time (posts_count snapshot increase) for the header
    lp_conn = _conn()
    try:
        mother['last_post_at'] = _last_post_map(lp_conn, [account_id]).get(account_id)
    finally:
        lp_conn.close()
    return render_template('mother_detail.html', mother=mother)


@mothers_bp.route('/api/mothers/<int:account_id>', methods=['GET'])
def get_mother(account_id):
    """Return single mother dict with full stats + slave summary."""
    conn = _conn()
    try:
        row = conn.execute("""
            SELECT a.id, a.username, a.tag, a.followers, a.following, a.posts,
                   a.status, a.is_business_profile, a.is_mother, a.device_serial,
                   a.profile_link, a.display_name, a.updated_at,
                   a.instagram_package, a.business_category, a.is_private,
                   a.account_status_json, a.account_status_checked_at,
                   d.device_name, d.device_group, d.status AS device_status
            FROM accounts a
            LEFT JOIN devices d ON d.device_serial = a.device_serial
            WHERE a.id = ? AND a.is_mother = 1
        """, (account_id,)).fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Mother not found'}), 404

        # Read app_cloner from settings_json (source of truth, matches bot_engine logic)
        app_cloner = None
        sett = conn.execute(
            "SELECT settings_json FROM account_settings WHERE account_id=?",
            (account_id,)
        ).fetchone()
        if sett and sett['settings_json']:
            try:
                import json as _json
                sd = _json.loads(sett['settings_json'])
                ac = sd.get('app_cloner') or sd.get('appcloner')
                if ac and str(ac).strip() and str(ac).strip() != 'None':
                    app_cloner = str(ac).strip()
            except Exception:
                pass

        mother_tags = _split_tags(row['tag'])

        # Health events for this mother
        unresolved = conn.execute(
            "SELECT COUNT(*) FROM account_health_events WHERE account_id=? AND resolved_at IS NULL",
            (account_id,)
        ).fetchone()[0]

        # Slaves summary (counts + status breakdown)
        slaves_summary = {'total': 0, 'active': 0, 'logged_out': 0, 'suspended': 0, 'banned': 0, 'other': 0}
        if mother_tags:
            slave_rows = conn.execute(
                "SELECT id, status, tag FROM accounts WHERE is_mother=0 AND tag IS NOT NULL AND tag != '' AND id != ?",
                (account_id,)
            ).fetchall()
            for sr in slave_rows:
                if mother_tags & _split_tags(sr['tag']):
                    slaves_summary['total'] += 1
                    s = (sr['status'] or '').lower()
                    if s == 'active':
                        slaves_summary['active'] += 1
                    elif 'logged_out' in s or s == 'logged out':
                        slaves_summary['logged_out'] += 1
                    elif 'suspend' in s:
                        slaves_summary['suspended'] += 1
                    elif 'ban' in s:
                        slaves_summary['banned'] += 1
                    else:
                        slaves_summary['other'] += 1

        # Latest follower snapshot for growth (compare to 7d ago)
        prev = conn.execute("""
            SELECT followers, following, posts_count, captured_at FROM follower_snapshots
            WHERE account_id=? AND captured_at <= datetime('now', '-7 days')
            ORDER BY captured_at DESC LIMIT 1
        """, (account_id,)).fetchone()
        growth = {}
        if prev:
            growth = {
                'followers_delta': (row['followers'] or 0) - (prev['followers'] or 0),
                'following_delta': (row['following'] or 0) - (prev['following'] or 0),
                'posts_delta': (row['posts'] or 0) - (prev['posts_count'] or 0),
                'baseline_at': prev['captured_at'],
            }

        # ── Slaves activity & ROI (last 7 days) ────────────────────────
        roi = None
        if mother_tags:
            # Find slave usernames
            slave_usernames = []
            for sr in conn.execute(
                "SELECT username, tag FROM accounts WHERE is_mother=0 AND tag IS NOT NULL AND tag != '' AND id != ?",
                (account_id,)
            ).fetchall():
                if mother_tags & _split_tags(sr['tag']):
                    slave_usernames.append(sr['username'])

            if slave_usernames:
                placeholders = ','.join('?' * len(slave_usernames))
                # Total successful actions in last 7d, grouped by type
                rows = conn.execute(f"""
                    SELECT action_type, COUNT(*) AS cnt
                    FROM action_history
                    WHERE username IN ({placeholders})
                      AND success=1
                      AND timestamp >= datetime('now', '-7 days')
                    GROUP BY action_type
                """, slave_usernames).fetchall()
                actions_by_type = {r['action_type']: r['cnt'] for r in rows}
                total_actions = sum(actions_by_type.values())
                follower_delta = growth.get('followers_delta') if growth else None
                ratio = None
                if total_actions > 0 and follower_delta is not None and follower_delta > 0:
                    ratio = round(total_actions / follower_delta, 1)
                roi = {
                    'window_days': 7,
                    'total_actions': total_actions,
                    'actions_by_type': actions_by_type,
                    'follower_delta': follower_delta,
                    'actions_per_follower': ratio,  # lower = better ROI
                }

        # ── Latest Insights (Professional Dashboard scrape) ─────────────
        insights = None
        try:
            ins_row = conn.execute("""
                SELECT * FROM account_insights_v2
                WHERE account_id = ?
                ORDER BY scraped_at DESC LIMIT 1
            """, (row['username'],)).fetchone()
            if ins_row:
                insights = {k: ins_row[k] for k in ins_row.keys()}
        except Exception:
            pass

        return jsonify({
            'success': True,
            'mother': {
                'id': row['id'],
                'username': row['username'],
                'display_name': row['display_name'],
                'tag': row['tag'] or '',
                'tags': sorted(mother_tags),
                'posts': row['posts'] or 0,
                'followers': row['followers'] or 0,
                'following': row['following'] or 0,
                'status': row['status'],
                'status_kind': _account_status(row, unresolved),
                'is_business_profile': bool(row['is_business_profile']),
                'business_category': row['business_category'],
                'is_private': bool(row['is_private']),
                'profile_link': row['profile_link'],
                'device_serial': row['device_serial'],
                'device_name': row['device_name'],
                'device_group': row['device_group'],
                'device_status': row['device_status'],
                'instagram_package': row['instagram_package'],
                'app_cloner': app_cloner,
                'unresolved_events': unresolved,
                'updated_at': row['updated_at'],
                'account_status': _parse_account_status_for_response(row),
            },
            'slaves_summary': slaves_summary,
            'growth_7d': growth,
            'roi_7d': roi,
            'insights': insights,
        })
    finally:
        conn.close()


@mothers_bp.route('/api/mothers/<int:account_id>/growth', methods=['GET'])
def get_mother_growth(account_id):
    """
    Daily follower count history from follower_snapshots.
    Returns last N days (default 30). Days are ordered ascending.
    Query: ?days=30|90|all
    """
    days_param = request.args.get('days', '30')
    conn = _conn()
    try:
        if days_param == 'all':
            since_clause = ''
            params = (account_id,)
        else:
            try:
                n = int(days_param)
            except ValueError:
                n = 30
            since_clause = f"AND captured_at >= datetime('now', '-{n} days')"
            params = (account_id,)

        # One row per day — pick the latest snapshot of each day
        rows = conn.execute(f"""
            SELECT DATE(captured_at) AS day,
                   MAX(followers) AS followers,
                   MAX(following) AS following,
                   MAX(posts_count) AS posts
            FROM follower_snapshots
            WHERE account_id = ?
              {since_clause}
            GROUP BY DATE(captured_at)
            ORDER BY day ASC
        """, params).fetchall()

        return jsonify({
            'success': True,
            'days_param': days_param,
            'series': [
                {
                    'day': r['day'],
                    'followers': r['followers'] or 0,
                    'following': r['following'] or 0,
                    'posts': r['posts'] or 0,
                }
                for r in rows
            ],
        })
    finally:
        conn.close()


@mothers_bp.route('/api/devices/<path:device_serial>/open-ig', methods=['POST'])
def device_open_ig(device_serial):
    """
    Open a specific Instagram clone package on the device, optionally with deep-link
    to a username profile. Used to ensure screenshots are taken from the mother's
    IG context (not whichever slave clone happens to be in foreground).

    Body: {package: "com.instagram.androif", username: "jaggerprime" (optional)}
    """
    data = request.get_json(silent=True) or {}
    raw_pkg = (data.get('package') or '').strip()
    username = (data.get('username') or '').strip()
    force_stop = data.get('force_stop', True)
    if not raw_pkg:
        return jsonify({'success': False, 'error': 'Missing package'}), 400

    # Accept both short ("com.instagram.androip") and full
    # ("com.instagram.androip/com.instagram.mainactivity.MainActivity") formats
    pkg = raw_pkg.split('/', 1)[0] if '/' in raw_pkg else raw_pkg

    adb_serial = device_serial.replace('_', ':')

    try:
        # Step 1: force-stop the target package for a clean state (matches bot engine behavior)
        if force_stop:
            subprocess.run(
                ['adb', '-s', adb_serial, 'shell', 'am', 'force-stop', pkg],
                capture_output=True, timeout=5, check=False
            )
            time.sleep(1)  # matches bot_engine._open_instagram (line 609)

        # Step 2: launch via deep link to user profile if provided, else LAUNCHER intent.
        # The trailing pkg arg restricts intent target to this clone (no chooser dialog).
        if username:
            uri = f'instagram://user?username={username}'
            cmd = [
                'adb', '-s', adb_serial, 'shell',
                'am', 'start', '-W',
                '-a', 'android.intent.action.VIEW',
                '-d', uri,
                pkg,
            ]
        else:
            cmd = [
                'adb', '-s', adb_serial, 'shell',
                'monkey', '-p', pkg, '-c', 'android.intent.category.LAUNCHER', '1',
            ]

        result = subprocess.run(cmd, capture_output=True, timeout=15, check=False)
        out = (result.stdout.decode('utf-8', 'ignore') or '') + (result.stderr.decode('utf-8', 'ignore') or '')
        ok = result.returncode == 0 and 'Error' not in out and 'No activities found' not in out
        return jsonify({
            'success': bool(ok),
            'output': out[:500],
            'package': pkg,
            'username': username or None,
            'mode': 'deep_link' if username else 'launcher',
            'force_stopped': bool(force_stop),
        }), (200 if ok else 502)
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Open timed out'}), 504
    except FileNotFoundError:
        return jsonify({'success': False, 'error': 'adb command not found in PATH'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@mothers_bp.route('/api/devices/<path:device_serial>/stream', methods=['GET'])
def device_stream(device_serial):
    """
    MJPEG stream of the device screen via multipart/x-mixed-replace.
    Browser <img src=this> auto-refreshes as frames arrive (no flicker).
    Re-encodes PNG → JPEG for ~3x smaller frames (smoother on LAN).

    Query params:
      quality (int 1-100, default 75)  — JPEG quality
      scale (float 0.1-1.0, default 0.6) — resize factor (0.6 → ~640x1152)
    """
    adb_serial = device_serial.replace('_', ':')
    quality = max(10, min(95, int(request.args.get('quality', 75))))
    scale = max(0.1, min(1.0, float(request.args.get('scale', 0.6))))
    boundary = b'frame'

    def gen():
        from io import BytesIO
        from PIL import Image
        last_err_log = 0.0
        while True:
            try:
                proc = subprocess.run(
                    ['adb', '-s', adb_serial, 'exec-out', 'screencap', '-p'],
                    capture_output=True, timeout=5, check=False
                )
                png = proc.stdout
                if proc.returncode != 0 or not png or len(png) < 100:
                    # Throttle on errors so we don't spam ADB
                    time.sleep(0.5)
                    continue
                # Decode PNG → resize → encode JPEG
                try:
                    img = Image.open(BytesIO(png))
                    if img.mode == 'RGBA':
                        img = img.convert('RGB')
                    if scale < 1.0:
                        new_w = max(64, int(img.width * scale))
                        new_h = max(64, int(img.height * scale))
                        img = img.resize((new_w, new_h), Image.BILINEAR)
                    buf = BytesIO()
                    img.save(buf, format='JPEG', quality=quality, optimize=False)
                    body = buf.getvalue()
                except Exception:
                    # Fall back to raw PNG
                    body = png
                    mime = b'image/png'
                else:
                    mime = b'image/jpeg'

                yield (b'--' + boundary + b'\r\n'
                       b'Content-Type: ' + mime + b'\r\n'
                       b'Content-Length: ' + str(len(body)).encode() + b'\r\n\r\n'
                       + body + b'\r\n')
                time.sleep(0.05)  # tiny breath between frames
            except GeneratorExit:
                return
            except Exception:
                # Don't spam logs — slow down on persistent errors
                if time.time() - last_err_log > 5:
                    last_err_log = time.time()
                time.sleep(1)

    return Response(
        gen(),
        mimetype='multipart/x-mixed-replace; boundary=' + boundary.decode(),
        headers={'Cache-Control': 'no-store, no-cache', 'Pragma': 'no-cache',
                 'X-Accel-Buffering': 'no'}
    )


@mothers_bp.route('/api/devices/<path:device_serial>/tap', methods=['POST'])
def device_tap(device_serial):
    """Forward a tap event to the device. Body: {x: int, y: int} (device pixels)."""
    data = request.get_json(silent=True) or {}
    try:
        x = int(data.get('x', 0))
        y = int(data.get('y', 0))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Bad x/y'}), 400
    if x < 0 or y < 0 or x > 5000 or y > 5000:
        return jsonify({'success': False, 'error': 'Out of range'}), 400
    adb_serial = device_serial.replace('_', ':')
    try:
        subprocess.run(
            ['adb', '-s', adb_serial, 'shell', 'input', 'tap', str(x), str(y)],
            capture_output=True, timeout=5, check=False
        )
        return jsonify({'success': True, 'x': x, 'y': y})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'tap timed out'}), 504
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@mothers_bp.route('/api/devices/<path:device_serial>/swipe', methods=['POST'])
def device_swipe(device_serial):
    """Forward a swipe gesture. Body: {x1, y1, x2, y2, duration_ms?}."""
    data = request.get_json(silent=True) or {}
    try:
        x1 = int(data.get('x1', 0)); y1 = int(data.get('y1', 0))
        x2 = int(data.get('x2', 0)); y2 = int(data.get('y2', 0))
        dur = int(data.get('duration_ms', 300))
        dur = max(50, min(3000, dur))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Bad coords'}), 400
    adb_serial = device_serial.replace('_', ':')
    try:
        subprocess.run(
            ['adb', '-s', adb_serial, 'shell', 'input', 'swipe',
             str(x1), str(y1), str(x2), str(y2), str(dur)],
            capture_output=True, timeout=10, check=False
        )
        return jsonify({'success': True})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'swipe timed out'}), 504
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@mothers_bp.route('/api/devices/<path:device_serial>/key', methods=['POST'])
def device_key(device_serial):
    """Forward a keyevent (Home, Back, etc.). Body: {keycode: 'KEYCODE_HOME'} or {keycode: 4}."""
    data = request.get_json(silent=True) or {}
    kc = str(data.get('keycode', '')).strip()
    if not kc:
        return jsonify({'success': False, 'error': 'Missing keycode'}), 400
    adb_serial = device_serial.replace('_', ':')
    try:
        subprocess.run(
            ['adb', '-s', adb_serial, 'shell', 'input', 'keyevent', kc],
            capture_output=True, timeout=5, check=False
        )
        return jsonify({'success': True, 'keycode': kc})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@mothers_bp.route('/api/devices/<path:device_serial>/screenshot', methods=['GET'])
def device_screenshot(device_serial):
    """
    Return a PNG screenshot from the given device via ADB.
    Lightweight (no u2 dependency); ~300-500ms per call.
    Accepts either underscore (DB) or colon (ADB) formatted serials.
    """
    adb_serial = device_serial.replace('_', ':')
    # Bot engines on the same device hit ADB heavily — screencap can take 5-25s.
    # Use a generous timeout so transient ADB pressure doesn't fail every call.
    try:
        result = subprocess.run(
            ['adb', '-s', adb_serial, 'exec-out', 'screencap', '-p'],
            capture_output=True, timeout=30, check=False
        )
        if result.returncode != 0 or not result.stdout or len(result.stdout) < 100:
            err = result.stderr.decode('utf-8', errors='ignore')[:200] if result.stderr else 'empty output'
            return jsonify({'success': False, 'error': f'ADB screencap failed: {err}'}), 502
        return Response(
            result.stdout,
            mimetype='image/png',
            headers={'Cache-Control': 'no-store, no-cache', 'Pragma': 'no-cache'}
        )
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'ADB screencap timed out (device under heavy bot load — try again)'}), 504
    except FileNotFoundError:
        return jsonify({'success': False, 'error': 'adb command not found in PATH'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@mothers_bp.route('/api/accounts/<int:account_id>/scrape-insights', methods=['POST'])
def scrape_account_insights(account_id):
    """
    Run scrape_insights_overview live for the given account.
    Connects to device, navigates Profile → Professional dashboard, parses + saves.
    Account must be a Business profile.
    """
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT id, username, device_serial, instagram_package, is_business_profile FROM accounts WHERE id=?",
            (account_id,)
        ).fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Account not found'}), 404
        if not row['is_business_profile']:
            return jsonify({'success': False, 'error': 'Not a business profile — cannot scrape insights'}), 400
        username = row['username']
        adb_serial = (row['device_serial'] or '').replace('_', ':')
        pkg = row['instagram_package'] or 'com.instagram.android'
    finally:
        conn.close()

    try:
        # Force-stop + LAUNCHER intent + click profile tab
        subprocess.run(['adb', '-s', adb_serial, 'shell', 'am', 'force-stop', pkg],
                       capture_output=True, timeout=5, check=False)
        time.sleep(1)
        subprocess.run(['adb', '-s', adb_serial, 'shell', 'monkey',
                        '-p', pkg, '-c', 'android.intent.category.LAUNCHER', '1'],
                       capture_output=True, timeout=10, check=False)
        time.sleep(7)

        import sys as _sys
        _parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _parent not in _sys.path:
            _sys.path.insert(0, _parent)
        import uiautomator2 as u2
        d = u2.connect(adb_serial)
        # Click profile tab
        try:
            d(resourceIdMatches=r'.*:id/profile_tab').click()
        except Exception:
            pass
        time.sleep(4)

        # Full scrape — drills into Views / Interactions / Followers / Content sections.
        # Slower (3-5 min) but populates ALL chart fields in /analytics.
        # Pass mode=overview via query param to use the quick path instead.
        from automation.actions.scrape_insights import (
            scrape_insights, scrape_insights_overview, save_insights_to_db
        )
        mode = (request.args.get('mode') or '').lower()
        scraper = scrape_insights_overview if mode == 'overview' else scrape_insights
        data = scraper(d, pkg)
        if not data:
            return jsonify({'success': False, 'error': 'scrape returned no data — Professional dashboard may not be visible yet'}), 502

        row_id = save_insights_to_db(data, account_id=username,
                                     device_serial=row['device_serial'])
        return jsonify({
            'success': True,
            'username': username,
            'row_id': row_id,
            'data': data,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@mothers_bp.route('/api/accounts/<int:account_id>/business', methods=['POST'])
def set_business_flag(account_id):
    """
    Manually set accounts.is_business_profile flag. Used when the account is
    already a business profile on Instagram but Hydra didn't track it (e.g.,
    switched manually outside of our automation).

    Body: {is_business_profile: 0|1}
    """
    data = request.get_json(silent=True) or {}
    raw = data.get('is_business_profile', None)
    if raw is None:
        return jsonify({'success': False, 'error': 'Missing is_business_profile field'}), 400
    flag = 1 if raw in (1, True, '1', 'true', 'True') else 0

    conn = _conn()
    try:
        row = conn.execute(
            "SELECT id, username FROM accounts WHERE id=?", (account_id,)
        ).fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Account not found'}), 404
        conn.execute(
            "UPDATE accounts SET is_business_profile=?, business_switched_at=COALESCE(business_switched_at, datetime('now')), updated_at=datetime('now') WHERE id=?",
            (flag, account_id)
        )
        conn.commit()
        return jsonify({
            'success': True,
            'account_id': account_id,
            'username': row['username'],
            'is_business_profile': bool(flag),
        })
    finally:
        conn.close()


@mothers_bp.route('/api/accounts/<int:account_id>/detect-business', methods=['POST'])
def detect_business_from_device(account_id):
    """
    Force-open the account's IG clone, wait, dump XML, run business detection.
    Updates accounts.is_business_profile based on XML indicators.
    """
    import json as _stdlib_json
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT a.id, a.username, a.device_serial, a.instagram_package, s.settings_json "
            "FROM accounts a LEFT JOIN account_settings s ON s.account_id = a.id "
            "WHERE a.id=?",
            (account_id,)
        ).fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Account not found'}), 404
        adb_serial = (row['device_serial'] or '').replace('_', ':')
        if not adb_serial:
            return jsonify({'success': False, 'error': 'No device assigned'}), 400
        username = row['username']
        # Resolve package: app_cloner first (full or short), then instagram_package
        pkg_full = None
        if row['settings_json']:
            try:
                sd = _stdlib_json.loads(row['settings_json'])
                pkg_full = (sd.get('app_cloner') or sd.get('appcloner') or '').strip() or None
            except Exception:
                pass
        if not pkg_full:
            pkg_full = row['instagram_package']
        pkg = pkg_full.split('/', 1)[0] if pkg_full and '/' in pkg_full else pkg_full
        if not pkg:
            return jsonify({'success': False, 'error': 'No package configured for account'}), 400
    finally:
        conn.close()

    # Step 0: force-stop + deep link to mother profile (matches Open Mother IG flow)
    try:
        subprocess.run(
            ['adb', '-s', adb_serial, 'shell', 'am', 'force-stop', pkg],
            capture_output=True, timeout=5, check=False
        )
        time.sleep(1)
        subprocess.run(
            ['adb', '-s', adb_serial, 'shell', 'am', 'start', '-W',
             '-a', 'android.intent.action.VIEW',
             '-d', f'instagram://user?username={username}', pkg],
            capture_output=True, timeout=15, check=False
        )
        time.sleep(6)  # let IG settle + location banner disappear
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'open-ig step timed out'}), 504

    # Dump UI hierarchy via uiautomator2 JSONRPC server (port 9008 on device).
    # Standalone `uiautomator dump` conflicts with running u2 server, so we use
    # the u2 jsonrpc endpoint via adb port-forward (matches what bot uses).
    import socket, json as _json, urllib.request
    # Pick a free local port for forwarding
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    local_port = s.getsockname()[1]
    s.close()
    xml = ''
    fwd_added = False
    try:
        fwd = subprocess.run(
            ['adb', '-s', adb_serial, 'forward', f'tcp:{local_port}', 'tcp:9008'],
            capture_output=True, timeout=5, check=False
        )
        if fwd.returncode != 0:
            return jsonify({'success': False, 'error': f'adb forward failed: {fwd.stderr.decode("utf-8", "ignore")[:200]}'}), 502
        fwd_added = True
        body = _json.dumps({'jsonrpc': '2.0', 'method': 'dumpWindowHierarchy',
                            'params': [True, 1000], 'id': 1}).encode()
        req = urllib.request.Request(
            f'http://127.0.0.1:{local_port}/jsonrpc/0',
            data=body, headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = _json.loads(resp.read().decode('utf-8', errors='ignore'))
        xml = payload.get('result', '') or ''
        if not xml or len(xml) < 100:
            return jsonify({'success': False, 'error': 'Empty XML from u2 server'}), 502
    except urllib.error.URLError as e:
        return jsonify({'success': False, 'error': f'u2 server unreachable: {e}'}), 502
    except Exception as e:
        return jsonify({'success': False, 'error': f'XML dump error: {e}'}), 500
    finally:
        if fwd_added:
            subprocess.run(
                ['adb', '-s', adb_serial, 'forward', '--remove', f'tcp:{local_port}'],
                capture_output=True, timeout=5, check=False
            )

    # Sanity check: are we on the right profile? username should appear in XML.
    xml_lower = xml.lower()
    if username and username.lower() not in xml_lower:
        return jsonify({
            'success': False,
            'error': f'Device not on @{username} profile — XML does not contain username. Try again or click Open Mother IG first.',
            'xml_size': len(xml),
        }), 409  # Conflict

    # Detection: same logic as check_profile.py / switch_to_business.py
    indicators_found = []
    indicators = [
        'professional dashboard',
        'professional_dashboard',
        'switch to personal account',
        'switch account type',
    ]
    count = 0
    for ind in indicators:
        if ind in xml_lower:
            count += 1
            indicators_found.append(ind)
    if 'insights' in xml_lower and 'professional' in xml_lower:
        count += 1
        indicators_found.append('insights+professional')
    if 'views in the last' in xml_lower:
        count += 1
        indicators_found.append('views in the last')

    is_business = count >= 2

    # Update DB
    conn = _conn()
    try:
        conn.execute(
            "UPDATE accounts SET is_business_profile=?, updated_at=datetime('now') WHERE id=?",
            (1 if is_business else 0, account_id)
        )
        conn.commit()
    finally:
        conn.close()

    return jsonify({
        'success': True,
        'account_id': account_id,
        'is_business_profile': is_business,
        'indicators_count': count,
        'indicators_found': indicators_found,
    })


@mothers_bp.route('/api/accounts/<int:account_id>/mother', methods=['POST'])
def set_mother_flag(account_id):
    """Set is_mother flag on an account. Body: {is_mother: 0|1}."""
    data = request.get_json(silent=True) or {}
    raw = data.get('is_mother', None)
    if raw is None:
        return jsonify({'success': False, 'error': 'Missing is_mother field'}), 400
    flag = 1 if raw in (1, True, '1', 'true', 'True') else 0

    conn = _conn()
    try:
        row = conn.execute(
            "SELECT id, username, is_business_profile, tag FROM accounts WHERE id=?",
            (account_id,)
        ).fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Account not found'}), 404

        # Warning if marking as mother but not business profile
        warning = None
        if flag and not row['is_business_profile']:
            warning = ('Account is not a business profile. Insights/analytics will be unavailable. '
                       'Switch to business in IG settings to enable Professional Dashboard scraping.')
        if flag and not (row['tag'] or '').strip():
            warning = (warning + ' ' if warning else '') + 'Account has no tag — slaves cannot be linked. Add a tag first.'

        conn.execute(
            "UPDATE accounts SET is_mother=?, updated_at=datetime('now') WHERE id=?",
            (flag, account_id)
        )
        conn.commit()

        return jsonify({
            'success': True,
            'account_id': account_id,
            'username': row['username'],
            'is_mother': bool(flag),
            'warning': warning,
        })
    finally:
        conn.close()
