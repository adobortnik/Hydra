"""
job_orders_v2_routes.py - Job Orders V2 Blueprint

Clean job order management using phone_farm.db as the single source of truth.
Replaces the old file-based Onimator job system.
"""

from flask import Blueprint, render_template, request, jsonify
from phone_farm_db import get_conn, row_to_dict, rows_to_dicts
from datetime import datetime, date

job_orders_v2_bp = Blueprint('job_orders_v2', __name__)


# ─────────────────────────────────────────────
# TABLE INIT — runs on import
# ─────────────────────────────────────────────

def init_job_tables():
    """Create job_orders tables if they don't exist."""
    conn = get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS job_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_name TEXT NOT NULL,
                job_type TEXT NOT NULL,
                target TEXT NOT NULL,
                target_count INTEGER DEFAULT 0,
                completed_count INTEGER DEFAULT 0,
                limit_per_hour INTEGER DEFAULT 50,
                limit_per_day INTEGER DEFAULT 200,
                comment_text TEXT,
                status TEXT DEFAULT 'active',
                priority INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS job_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                device_serial TEXT NOT NULL,
                username TEXT NOT NULL,
                status TEXT DEFAULT 'assigned',
                completed_count INTEGER DEFAULT 0,
                last_action_at TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (job_id) REFERENCES job_orders(id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES accounts(id),
                UNIQUE(job_id, account_id)
            );

            CREATE TABLE IF NOT EXISTS job_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                target TEXT,
                status TEXT DEFAULT 'success',
                error_message TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (job_id) REFERENCES job_orders(id) ON DELETE CASCADE
            );
        """)
        conn.commit()
    finally:
        conn.close()


# Run on import
init_job_tables()

# ── Add report_reason column if missing ──
def _migrate_report_reason():
    conn = get_conn()
    try:
        # Check if column exists
        cursor = conn.execute("PRAGMA table_info(job_orders)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'report_reason' not in columns:
            conn.execute("ALTER TABLE job_orders ADD COLUMN report_reason TEXT DEFAULT 'spam'")
            conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

_migrate_report_reason()


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _sync_job_completed_count(conn, job_id):
    """Recalculate completed_count from assignments and auto-complete if done."""
    row = conn.execute(
        "SELECT COALESCE(SUM(completed_count), 0) AS total FROM job_assignments WHERE job_id = ?",
        (job_id,)
    ).fetchone()
    total = row['total'] if row else 0

    job = conn.execute("SELECT target_count, status FROM job_orders WHERE id = ?", (job_id,)).fetchone()
    if not job:
        return

    new_status = job['status']
    if job['status'] == 'active' and total >= job['target_count'] and job['target_count'] > 0:
        new_status = 'completed'

    now = datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE job_orders SET completed_count = ?, status = ?, updated_at = ? WHERE id = ?",
        (total, new_status, now, job_id)
    )


# ─────────────────────────────────────────────
# PAGE ROUTE
# ─────────────────────────────────────────────

@job_orders_v2_bp.route('/job-orders-v2')
def job_orders_v2_page():
    return render_template('job_orders_v2.html')


# ─────────────────────────────────────────────
# API: LIST ALL JOBS
# ─────────────────────────────────────────────

@job_orders_v2_bp.route('/api/jobs-v2', methods=['GET'])
def api_list_jobs():
    conn = get_conn()
    try:
        jobs = rows_to_dicts(conn.execute("""
            SELECT j.*,
                   COUNT(ja.id) AS assignment_count
            FROM job_orders j
            LEFT JOIN job_assignments ja ON ja.job_id = j.id
            GROUP BY j.id
            ORDER BY j.priority DESC, j.created_at DESC
        """).fetchall())
        return jsonify({'jobs': jobs})
    finally:
        conn.close()


# ─────────────────────────────────────────────
# API: GET SINGLE JOB (with assignments + history)
# ─────────────────────────────────────────────

@job_orders_v2_bp.route('/api/jobs-v2/<int:job_id>', methods=['GET'])
def api_get_job(job_id):
    conn = get_conn()
    try:
        job = row_to_dict(conn.execute("SELECT * FROM job_orders WHERE id = ?", (job_id,)).fetchone())
        if not job:
            return jsonify({'error': 'Job not found'}), 404

        assignments = rows_to_dicts(conn.execute("""
            SELECT ja.*, a.status AS account_status, d.device_name
            FROM job_assignments ja
            LEFT JOIN accounts a ON a.id = ja.account_id
            LEFT JOIN devices d ON d.device_serial = ja.device_serial
            WHERE ja.job_id = ?
            ORDER BY ja.username
        """, (job_id,)).fetchall())

        history = rows_to_dicts(conn.execute("""
            SELECT jh.*, a.username
            FROM job_history jh
            LEFT JOIN accounts a ON a.id = jh.account_id
            WHERE jh.job_id = ?
            ORDER BY jh.created_at DESC
            LIMIT 100
        """, (job_id,)).fetchall())

        job['assignments'] = assignments
        job['history'] = history
        job['assignment_count'] = len(assignments)
        return jsonify(job)
    finally:
        conn.close()


# ─────────────────────────────────────────────
# API: CREATE JOB
# ─────────────────────────────────────────────

@job_orders_v2_bp.route('/api/jobs-v2', methods=['POST'])
def api_create_job():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    required = ['job_name', 'job_type', 'target', 'target_count']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'Missing required field: {field}'}), 400

    conn = get_conn()
    try:
        now = datetime.utcnow().isoformat()
        cursor = conn.execute("""
            INSERT INTO job_orders (job_name, job_type, target, target_count,
                                    limit_per_hour, limit_per_day, comment_text,
                                    report_reason,
                                    comment_list_id, ai_mode, vision_ai,
                                    priority, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
        """, (
            data['job_name'],
            data['job_type'],
            data['target'],
            int(data['target_count']),
            int(data.get('limit_per_hour', 50)),
            int(data.get('limit_per_day', 200)),
            data.get('comment_text', ''),
            data.get('report_reason', 'nudity'),
            data.get('comment_list_id') or None,
            1 if data.get('ai_mode') else 0,
            1 if data.get('vision_ai') else 0,
            int(data.get('priority', 0)),
            now, now
        ))
        job_id = cursor.lastrowid

        # Auto-assign accounts if provided
        account_ids = data.get('accounts', [])
        assigned = 0
        for aid in account_ids:
            acct = conn.execute(
                "SELECT id, device_serial, username FROM accounts WHERE id = ?", (aid,)
            ).fetchone()
            if acct:
                try:
                    conn.execute("""
                        INSERT INTO job_assignments (job_id, account_id, device_serial, username, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (job_id, acct['id'], acct['device_serial'] or '', acct['username'], now))
                    assigned += 1
                except Exception:
                    pass  # skip duplicates

        conn.commit()
        return jsonify({'id': job_id, 'assigned': assigned}), 201
    finally:
        conn.close()


# ─────────────────────────────────────────────
# API: UPDATE JOB
# ─────────────────────────────────────────────

@job_orders_v2_bp.route('/api/jobs-v2/<int:job_id>', methods=['PUT'])
def api_update_job(job_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    conn = get_conn()
    try:
        job = conn.execute("SELECT * FROM job_orders WHERE id = ?", (job_id,)).fetchone()
        if not job:
            return jsonify({'error': 'Job not found'}), 404

        allowed = {
            'job_name', 'target', 'target_count', 'limit_per_hour',
            'limit_per_day', 'comment_text', 'report_reason', 'status', 'priority',
            'comment_list_id', 'ai_mode', 'vision_ai'
        }
        fields = {k: v for k, v in data.items() if k in allowed}
        if not fields:
            return jsonify({'error': 'No valid fields to update'}), 400

        fields['updated_at'] = datetime.utcnow().isoformat()
        set_clause = ', '.join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [job_id]

        conn.execute(f"UPDATE job_orders SET {set_clause} WHERE id = ?", values)

        # Re-sync completed count
        _sync_job_completed_count(conn, job_id)
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()


# ─────────────────────────────────────────────
# API: DELETE JOB
# ─────────────────────────────────────────────

@job_orders_v2_bp.route('/api/jobs-v2/<int:job_id>', methods=['DELETE'])
def api_delete_job(job_id):
    conn = get_conn()
    try:
        job = conn.execute("SELECT id FROM job_orders WHERE id = ?", (job_id,)).fetchone()
        if not job:
            return jsonify({'error': 'Job not found'}), 404

        conn.execute("DELETE FROM job_history WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM job_assignments WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM job_orders WHERE id = ?", (job_id,))
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()


# ─────────────────────────────────────────────
# API: ASSIGN ACCOUNTS TO JOB
# ─────────────────────────────────────────────

@job_orders_v2_bp.route('/api/jobs-v2/<int:job_id>/assign', methods=['POST'])
def api_assign_accounts(job_id):
    data = request.get_json()
    if not data or 'account_ids' not in data:
        return jsonify({'error': 'account_ids[] required'}), 400

    conn = get_conn()
    try:
        job = conn.execute("SELECT id FROM job_orders WHERE id = ?", (job_id,)).fetchone()
        if not job:
            return jsonify({'error': 'Job not found'}), 404

        now = datetime.utcnow().isoformat()
        assigned = 0
        for aid in data['account_ids']:
            acct = conn.execute(
                "SELECT id, device_serial, username FROM accounts WHERE id = ?", (aid,)
            ).fetchone()
            if acct:
                try:
                    conn.execute("""
                        INSERT INTO job_assignments (job_id, account_id, device_serial, username, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (job_id, acct['id'], acct['device_serial'] or '', acct['username'], now))
                    assigned += 1
                except Exception:
                    pass  # duplicate

        conn.commit()
        return jsonify({'assigned': assigned})
    finally:
        conn.close()


# ─────────────────────────────────────────────
# API: REMOVE ACCOUNT FROM JOB
# ─────────────────────────────────────────────

@job_orders_v2_bp.route('/api/jobs-v2/<int:job_id>/assign/<int:account_id>', methods=['DELETE'])
def api_remove_assignment(job_id, account_id):
    conn = get_conn()
    try:
        conn.execute(
            "DELETE FROM job_assignments WHERE job_id = ? AND account_id = ?",
            (job_id, account_id)
        )
        _sync_job_completed_count(conn, job_id)
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()


# ─────────────────────────────────────────────
# API: AVAILABLE ACCOUNTS (for assignment picker)
# ─────────────────────────────────────────────

@job_orders_v2_bp.route('/api/jobs-v2/available-accounts', methods=['GET'])
def api_available_accounts():
    conn = get_conn()
    try:
        accounts = rows_to_dicts(conn.execute("""
            SELECT a.id, a.username, a.device_serial, a.status, a.instagram_package,
                   d.device_name
            FROM accounts a
            LEFT JOIN devices d ON d.id = a.device_id
            ORDER BY d.device_name, a.username
        """).fetchall())

        # Group by device
        devices = {}
        for acct in accounts:
            serial = acct['device_serial'] or 'unassigned'
            name = acct['device_name'] or serial
            if serial not in devices:
                devices[serial] = {
                    'device_serial': serial,
                    'device_name': name,
                    'accounts': []
                }
            devices[serial]['accounts'].append(acct)

        return jsonify({
            'devices': list(devices.values()),
            'total': len(accounts)
        })
    finally:
        conn.close()


# ─────────────────────────────────────────────
# API: RECORD A COMPLETED ACTION (bot engine hook)
# ─────────────────────────────────────────────

@job_orders_v2_bp.route('/api/jobs-v2/<int:job_id>/record', methods=['POST'])
def api_record_action(job_id):
    data = request.get_json()
    if not data or 'account_id' not in data:
        return jsonify({'error': 'account_id required'}), 400

    conn = get_conn()
    try:
        job = conn.execute("SELECT * FROM job_orders WHERE id = ?", (job_id,)).fetchone()
        if not job:
            return jsonify({'error': 'Job not found'}), 404

        now = datetime.utcnow().isoformat()
        account_id = int(data['account_id'])
        action_status = data.get('status', 'success')
        error_msg = data.get('error_message', None)

        # Insert history
        conn.execute("""
            INSERT INTO job_history (job_id, account_id, action_type, target, status, error_message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (job_id, account_id, job['job_type'], data.get('target', ''), action_status, error_msg, now))

        # Increment assignment count on success
        if action_status == 'success':
            conn.execute("""
                UPDATE job_assignments
                SET completed_count = completed_count + 1, last_action_at = ?
                WHERE job_id = ? AND account_id = ?
            """, (now, job_id, account_id))

        # Sync totals
        _sync_job_completed_count(conn, job_id)
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()


# ─────────────────────────────────────────────
# API: JOB HISTORY
# ─────────────────────────────────────────────

@job_orders_v2_bp.route('/api/jobs-v2/<int:job_id>/history', methods=['GET'])
def api_job_history(job_id):
    limit = request.args.get('limit', 100, type=int)
    conn = get_conn()
    try:
        history = rows_to_dicts(conn.execute("""
            SELECT jh.*, a.username
            FROM job_history jh
            LEFT JOIN accounts a ON a.id = jh.account_id
            WHERE jh.job_id = ?
            ORDER BY jh.created_at DESC
            LIMIT ?
        """, (job_id, limit)).fetchall())
        return jsonify({'history': history})
    finally:
        conn.close()


# ─────────────────────────────────────────────
# API: STATS (for dashboard cards)
# ─────────────────────────────────────────────

@job_orders_v2_bp.route('/api/jobs-v2/stats', methods=['GET'])
def api_job_stats():
    conn = get_conn()
    try:
        active = conn.execute(
            "SELECT COUNT(*) AS c FROM job_orders WHERE status = 'active'"
        ).fetchone()['c']

        completed = conn.execute(
            "SELECT COUNT(*) AS c FROM job_orders WHERE status = 'completed'"
        ).fetchone()['c']

        assigned_accounts = conn.execute(
            "SELECT COUNT(DISTINCT account_id) AS c FROM job_assignments"
        ).fetchone()['c']

        today = date.today().isoformat()
        actions_today = conn.execute(
            "SELECT COUNT(*) AS c FROM job_history WHERE created_at >= ?",
            (today,)
        ).fetchone()['c']

        return jsonify({
            'active_jobs': active,
            'completed_jobs': completed,
            'assigned_accounts': assigned_accounts,
            'actions_today': actions_today
        })
    finally:
        conn.close()
