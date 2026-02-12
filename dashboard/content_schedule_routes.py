"""
Content Schedule Routes - API for scheduling posts, reels, and stories.

Blueprint prefix: /api/content-schedule
All data stored in phone_farm.db (centralized database).
Tables: content_schedule, content_batches
"""

import os
import uuid
import threading
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, render_template
from phone_farm_db import get_conn, row_to_dict, rows_to_dicts, get_account_by_id
from adb_helper import serial_db_to_adb, check_device_reachable

log = logging.getLogger(__name__)

content_schedule_bp = Blueprint('content_schedule', __name__)

# Media library directory (same as simple_app.py)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA_LIBRARY_DIR = os.path.join(BASE_DIR, 'media_library')

# Supported media extensions
MEDIA_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp4', '.mov', '.avi', '.mkv', '.webm'}


# =============================================================================
# DATABASE INIT
# =============================================================================

def init_content_schedule_tables():
    """Create content_schedule and content_batches tables if they don't exist."""
    conn = get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS content_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                device_serial TEXT,
                username TEXT,
                content_type TEXT NOT NULL,
                media_path TEXT,
                caption TEXT,
                hashtags TEXT,
                location TEXT,
                music_name TEXT,
                music_search_query TEXT,
                mention_username TEXT,
                link_url TEXT,
                scheduled_time DATETIME NOT NULL,
                status TEXT DEFAULT 'pending',
                posted_at DATETIME,
                error_message TEXT,
                batch_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS content_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT UNIQUE NOT NULL,
                name TEXT,
                content_type TEXT,
                total_items INTEGER DEFAULT 0,
                completed_items INTEGER DEFAULT 0,
                failed_items INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_cs_status ON content_schedule(status);
            CREATE INDEX IF NOT EXISTS idx_cs_scheduled_time ON content_schedule(scheduled_time);
            CREATE INDEX IF NOT EXISTS idx_cs_batch_id ON content_schedule(batch_id);
            CREATE INDEX IF NOT EXISTS idx_cs_account ON content_schedule(device_serial, username);
            CREATE INDEX IF NOT EXISTS idx_cb_batch_id ON content_batches(batch_id);
        """)
        conn.commit()
    finally:
        conn.close()


# Initialize tables on import
init_content_schedule_tables()


# =============================================================================
# TEST POST NOW - Background thread state
# =============================================================================

_test_post_progress = {}  # test_id -> {status, message, steps, ...}
_test_post_lock = threading.Lock()


# =============================================================================
# PAGE ROUTE
# =============================================================================

@content_schedule_bp.route('/content-schedule')
def content_schedule_page():
    """Render the content schedule page."""
    return render_template('content_schedule.html')


# =============================================================================
# CRUD OPERATIONS
# =============================================================================

@content_schedule_bp.route('/api/content-schedule', methods=['GET'])
def list_scheduled_items():
    """List scheduled items with optional filters."""
    try:
        status = request.args.get('status')
        content_type = request.args.get('content_type')
        device = request.args.get('device')
        account = request.args.get('account')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        batch_id = request.args.get('batch_id')
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)

        query = "SELECT * FROM content_schedule WHERE 1=1"
        params = []

        if status:
            statuses = status.split(',')
            placeholders = ','.join('?' * len(statuses))
            query += f" AND status IN ({placeholders})"
            params.extend(statuses)
        if content_type:
            query += " AND content_type = ?"
            params.append(content_type)
        if device:
            query += " AND device_serial = ?"
            params.append(device)
        if account:
            query += " AND username = ?"
            params.append(account)
        if date_from:
            query += " AND scheduled_time >= ?"
            params.append(date_from)
        if date_to:
            query += " AND scheduled_time <= ?"
            params.append(date_to)
        if batch_id:
            query += " AND batch_id = ?"
            params.append(batch_id)

        # Count total
        count_query = query.replace("SELECT *", "SELECT COUNT(*)", 1)
        
        query += " ORDER BY scheduled_time ASC LIMIT ? OFFSET ?"
        params_with_pagination = params + [limit, offset]

        conn = get_conn()
        try:
            total = conn.execute(count_query, params).fetchone()[0]
            rows = rows_to_dicts(conn.execute(query, params_with_pagination).fetchall())
            return jsonify({'items': rows, 'total': total, 'limit': limit, 'offset': offset})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@content_schedule_bp.route('/api/content-schedule/<int:item_id>', methods=['GET'])
def get_scheduled_item(item_id):
    """Get a single scheduled item by ID."""
    try:
        conn = get_conn()
        try:
            row = conn.execute("SELECT * FROM content_schedule WHERE id = ?", (item_id,)).fetchone()
            if not row:
                return jsonify({'error': 'Item not found'}), 404
            return jsonify(row_to_dict(row))
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@content_schedule_bp.route('/api/content-schedule', methods=['POST'])
def create_scheduled_item():
    """Create a single scheduled item."""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        required = ['content_type', 'scheduled_time']
        for field in required:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400

        if data['content_type'] not in ('post', 'reel', 'story'):
            return jsonify({'error': 'content_type must be post, reel, or story'}), 400

        now = datetime.utcnow().isoformat()
        conn = get_conn()
        try:
            cursor = conn.execute("""
                INSERT INTO content_schedule 
                (account_id, device_serial, username, content_type, media_path,
                 caption, hashtags, location, music_name, music_search_query,
                 mention_username, link_url, scheduled_time, status, batch_id,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            """, (
                data.get('account_id'),
                data.get('device_serial'),
                data.get('username'),
                data['content_type'],
                data.get('media_path'),
                data.get('caption'),
                data.get('hashtags'),
                data.get('location'),
                data.get('music_name'),
                data.get('music_search_query'),
                data.get('mention_username'),
                data.get('link_url'),
                data['scheduled_time'],
                data.get('batch_id'),
                now, now
            ))
            conn.commit()
            item_id = cursor.lastrowid
            row = conn.execute("SELECT * FROM content_schedule WHERE id = ?", (item_id,)).fetchone()
            return jsonify(row_to_dict(row)), 201
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@content_schedule_bp.route('/api/content-schedule/<int:item_id>', methods=['PUT'])
def update_scheduled_item(item_id):
    """Update a scheduled item (caption, reschedule, cancel, etc.)."""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        allowed_fields = {
            'caption', 'hashtags', 'location', 'music_name', 'music_search_query',
            'mention_username', 'link_url', 'scheduled_time', 'status',
            'media_path', 'error_message', 'posted_at', 'device_serial',
            'username', 'account_id'
        }
        updates = {k: v for k, v in data.items() if k in allowed_fields}
        if not updates:
            return jsonify({'error': 'No valid fields to update'}), 400

        updates['updated_at'] = datetime.utcnow().isoformat()
        set_clause = ', '.join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [item_id]

        conn = get_conn()
        try:
            result = conn.execute(f"UPDATE content_schedule SET {set_clause} WHERE id = ?", values)
            if result.rowcount == 0:
                return jsonify({'error': 'Item not found'}), 404
            conn.commit()
            
            # If status changed and has batch_id, update batch counts
            if 'status' in updates:
                row = conn.execute("SELECT batch_id FROM content_schedule WHERE id = ?", (item_id,)).fetchone()
                if row and row['batch_id']:
                    _update_batch_counts(conn, row['batch_id'])
                    conn.commit()

            row = conn.execute("SELECT * FROM content_schedule WHERE id = ?", (item_id,)).fetchone()
            return jsonify(row_to_dict(row))
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@content_schedule_bp.route('/api/content-schedule/<int:item_id>', methods=['DELETE'])
def delete_scheduled_item(item_id):
    """Delete a scheduled item."""
    try:
        conn = get_conn()
        try:
            row = conn.execute("SELECT batch_id FROM content_schedule WHERE id = ?", (item_id,)).fetchone()
            if not row:
                return jsonify({'error': 'Item not found'}), 404
            
            batch_id = row['batch_id']
            conn.execute("DELETE FROM content_schedule WHERE id = ?", (item_id,))
            
            # Update batch counts if part of a batch
            if batch_id:
                _update_batch_counts(conn, batch_id)
            
            conn.commit()
            return jsonify({'message': 'Item deleted', 'id': item_id})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# BULK / BATCH OPERATIONS
# =============================================================================

@content_schedule_bp.route('/api/content-schedule/batch', methods=['POST'])
def create_batch_schedule():
    """
    Bulk schedule: create one content_schedule row per account per media file.
    
    Accepts:
        content_type: post/reel/story
        media_paths: list of media file paths
        device_serial: device serial (or "all" for all devices)
        accounts: list of {device_serial, username, account_id} or "all"
        caption_template: caption text
        hashtags: hashtags text
        start_time: ISO datetime string
        interval_hours: hours between posts (float)
        mention_username: (for stories)
        music_search_query: (for reels)
        link_url: (for stories)
        location: (for posts)
        batch_name: optional name for the batch
    """
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        content_type = data.get('content_type')
        if content_type not in ('post', 'reel', 'story'):
            return jsonify({'error': 'content_type must be post, reel, or story'}), 400

        media_paths = data.get('media_paths', [])
        if not media_paths:
            return jsonify({'error': 'media_paths is required and must not be empty'}), 400

        start_time_str = data.get('start_time')
        if not start_time_str:
            return jsonify({'error': 'start_time is required'}), 400

        interval_hours = float(data.get('interval_hours', 24))
        if interval_hours <= 0:
            return jsonify({'error': 'interval_hours must be positive'}), 400

        # Parse start time
        try:
            start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00').replace('T', ' ').split('+')[0])
        except ValueError:
            return jsonify({'error': 'Invalid start_time format'}), 400

        # Resolve accounts
        accounts = data.get('accounts', [])
        device_serial = data.get('device_serial')
        
        conn = get_conn()
        try:
            if accounts == 'all' or (isinstance(accounts, str) and accounts.lower() == 'all'):
                # Get all accounts (optionally filtered by device)
                if device_serial and device_serial != 'all':
                    acct_rows = conn.execute(
                        "SELECT id, device_serial, username FROM accounts WHERE device_serial = ? AND status = 'active'",
                        (device_serial,)
                    ).fetchall()
                else:
                    acct_rows = conn.execute(
                        "SELECT id, device_serial, username FROM accounts WHERE status = 'active'"
                    ).fetchall()
                accounts = [{'account_id': r['id'], 'device_serial': r['device_serial'], 'username': r['username']} for r in acct_rows]
            elif isinstance(accounts, list):
                # Accounts should be list of {device_serial, username} or {account_id}
                resolved = []
                for acct in accounts:
                    if isinstance(acct, dict):
                        if acct.get('account_id'):
                            resolved.append(acct)
                        elif acct.get('device_serial') and acct.get('username'):
                            row = conn.execute(
                                "SELECT id FROM accounts WHERE device_serial = ? AND username = ?",
                                (acct['device_serial'], acct['username'])
                            ).fetchone()
                            acct['account_id'] = row['id'] if row else None
                            resolved.append(acct)
                    elif isinstance(acct, str):
                        # Could be username - try to find it
                        row = conn.execute(
                            "SELECT id, device_serial, username FROM accounts WHERE username = ?",
                            (acct,)
                        ).fetchone()
                        if row:
                            resolved.append({'account_id': row['id'], 'device_serial': row['device_serial'], 'username': row['username']})
                accounts = resolved

            if not accounts:
                return jsonify({'error': 'No valid accounts found'}), 400

            # Generate batch
            batch_id = str(uuid.uuid4())[:12]
            batch_name = data.get('batch_name', f"{content_type.title()} batch - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}")
            caption_template = data.get('caption_template', '')
            hashtags = data.get('hashtags', '')
            location = data.get('location', '')
            mention_username = data.get('mention_username', '')
            music_search_query = data.get('music_search_query', '')
            link_url = data.get('link_url', '')
            now = datetime.utcnow().isoformat()

            # Create schedule items: one per account per media file
            current_time = start_time
            total_items = 0
            
            for media_path in media_paths:
                for acct in accounts:
                    conn.execute("""
                        INSERT INTO content_schedule
                        (account_id, device_serial, username, content_type, media_path,
                         caption, hashtags, location, music_name, music_search_query,
                         mention_username, link_url, scheduled_time, status, batch_id,
                         created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                    """, (
                        acct.get('account_id'),
                        acct.get('device_serial', device_serial),
                        acct.get('username'),
                        content_type,
                        media_path,
                        caption_template,
                        hashtags,
                        location,
                        None,  # music_name
                        music_search_query,
                        mention_username,
                        link_url,
                        current_time.isoformat(),
                        batch_id,
                        now, now
                    ))
                    total_items += 1
                    current_time += timedelta(hours=interval_hours)

            # Create batch record
            conn.execute("""
                INSERT INTO content_batches (batch_id, name, content_type, total_items, status, created_at)
                VALUES (?, ?, ?, ?, 'active', ?)
            """, (batch_id, batch_name, content_type, total_items, now))

            conn.commit()

            return jsonify({
                'batch_id': batch_id,
                'name': batch_name,
                'total_items': total_items,
                'accounts': len(accounts),
                'media_files': len(media_paths),
                'start_time': start_time.isoformat(),
                'end_time': current_time.isoformat()
            }), 201

        finally:
            conn.close()
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@content_schedule_bp.route('/api/content-schedule/batches', methods=['GET'])
def list_batches():
    """List all batches with progress."""
    try:
        conn = get_conn()
        try:
            rows = rows_to_dicts(conn.execute(
                "SELECT * FROM content_batches ORDER BY created_at DESC"
            ).fetchall())
            return jsonify({'batches': rows})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@content_schedule_bp.route('/api/content-schedule/batches/<batch_id>', methods=['GET'])
def get_batch_detail(batch_id):
    """Get batch detail with all items."""
    try:
        conn = get_conn()
        try:
            batch = conn.execute(
                "SELECT * FROM content_batches WHERE batch_id = ?", (batch_id,)
            ).fetchone()
            if not batch:
                return jsonify({'error': 'Batch not found'}), 404

            items = rows_to_dicts(conn.execute(
                "SELECT * FROM content_schedule WHERE batch_id = ? ORDER BY scheduled_time ASC",
                (batch_id,)
            ).fetchall())

            result = row_to_dict(batch)
            result['items'] = items
            return jsonify(result)
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@content_schedule_bp.route('/api/content-schedule/batches/<batch_id>', methods=['DELETE'])
def cancel_batch(batch_id):
    """Cancel an entire batch (set all pending items to cancelled)."""
    try:
        conn = get_conn()
        try:
            now = datetime.utcnow().isoformat()
            result = conn.execute(
                "UPDATE content_schedule SET status = 'cancelled', updated_at = ? WHERE batch_id = ? AND status = 'pending'",
                (now, batch_id)
            )
            cancelled = result.rowcount

            conn.execute(
                "UPDATE content_batches SET status = 'cancelled' WHERE batch_id = ?",
                (batch_id,)
            )
            _update_batch_counts(conn, batch_id)
            conn.commit()

            return jsonify({'message': f'Batch cancelled, {cancelled} items cancelled', 'cancelled': cancelled})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# STATS & UPCOMING
# =============================================================================

@content_schedule_bp.route('/api/content-schedule/stats', methods=['GET'])
def get_schedule_stats():
    """Get scheduling statistics."""
    try:
        conn = get_conn()
        try:
            today = datetime.utcnow().strftime('%Y-%m-%d')
            tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime('%Y-%m-%d')

            stats = {}
            
            # Pending count
            stats['pending'] = conn.execute(
                "SELECT COUNT(*) FROM content_schedule WHERE status = 'pending'"
            ).fetchone()[0]

            # Currently posting
            stats['posting'] = conn.execute(
                "SELECT COUNT(*) FROM content_schedule WHERE status = 'posting'"
            ).fetchone()[0]

            # Completed today
            stats['completed_today'] = conn.execute(
                "SELECT COUNT(*) FROM content_schedule WHERE status = 'completed' AND posted_at >= ? AND posted_at < ?",
                (today, tomorrow)
            ).fetchone()[0]

            # Failed today
            stats['failed_today'] = conn.execute(
                "SELECT COUNT(*) FROM content_schedule WHERE status = 'failed' AND updated_at >= ? AND updated_at < ?",
                (today, tomorrow)
            ).fetchone()[0]

            # Scheduled today (upcoming)
            stats['scheduled_today'] = conn.execute(
                "SELECT COUNT(*) FROM content_schedule WHERE status = 'pending' AND scheduled_time >= ? AND scheduled_time < ?",
                (today, tomorrow)
            ).fetchone()[0]

            # Total scheduled
            stats['total'] = conn.execute(
                "SELECT COUNT(*) FROM content_schedule"
            ).fetchone()[0]

            # By type
            type_rows = conn.execute(
                "SELECT content_type, COUNT(*) as count FROM content_schedule WHERE status = 'pending' GROUP BY content_type"
            ).fetchall()
            stats['by_type'] = {r['content_type']: r['count'] for r in type_rows}

            return jsonify(stats)
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@content_schedule_bp.route('/api/content-schedule/upcoming', methods=['GET'])
def get_upcoming():
    """Get next N items to be posted."""
    try:
        limit = request.args.get('limit', 20, type=int)
        now = datetime.utcnow().isoformat()
        
        conn = get_conn()
        try:
            rows = rows_to_dicts(conn.execute(
                """SELECT * FROM content_schedule 
                   WHERE status = 'pending' AND scheduled_time >= ?
                   ORDER BY scheduled_time ASC LIMIT ?""",
                (now, limit)
            ).fetchall())
            return jsonify({'items': rows})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# MEDIA FOLDERS
# =============================================================================

@content_schedule_bp.route('/api/content-schedule/media-folders', methods=['GET'])
def list_media_folders():
    """List folders from media_library directory."""
    try:
        folders = []
        
        # Check both 'original' subfolder and root-level folders
        for search_dir in [MEDIA_LIBRARY_DIR, os.path.join(MEDIA_LIBRARY_DIR, 'original')]:
            if not os.path.exists(search_dir):
                continue
            for entry in sorted(os.listdir(search_dir)):
                full_path = os.path.join(search_dir, entry)
                if os.path.isdir(full_path):
                    # Count media files
                    media_count = 0
                    for f in os.listdir(full_path):
                        ext = os.path.splitext(f)[1].lower()
                        if ext in MEDIA_EXTENSIONS:
                            media_count += 1
                    
                    rel_path = os.path.relpath(full_path, MEDIA_LIBRARY_DIR)
                    folders.append({
                        'name': entry,
                        'path': rel_path,
                        'full_path': full_path,
                        'media_count': media_count
                    })

        return jsonify({'folders': folders})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@content_schedule_bp.route('/api/content-schedule/media-folders/<path:folder>', methods=['GET'])
def list_folder_files(folder):
    """List media files in a folder."""
    try:
        folder_path = os.path.join(MEDIA_LIBRARY_DIR, folder)
        if not os.path.exists(folder_path):
            return jsonify({'error': 'Folder not found'}), 404

        files = []
        for f in sorted(os.listdir(folder_path)):
            ext = os.path.splitext(f)[1].lower()
            if ext in MEDIA_EXTENSIONS:
                full_path = os.path.join(folder_path, f)
                rel_path = os.path.relpath(full_path, MEDIA_LIBRARY_DIR)
                is_video = ext in {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
                files.append({
                    'name': f,
                    'path': rel_path,
                    'full_path': full_path,
                    'size': os.path.getsize(full_path),
                    'is_video': is_video,
                    'extension': ext
                })

        return jsonify({'folder': folder, 'files': files, 'total': len(files)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# ACCOUNTS & DEVICES HELPERS (for the frontend)
# =============================================================================

@content_schedule_bp.route('/api/content-schedule/devices', methods=['GET'])
def list_devices_for_schedule():
    """List devices for the schedule UI."""
    try:
        conn = get_conn()
        try:
            rows = rows_to_dicts(conn.execute("""
                SELECT d.id, d.device_serial, d.device_name, d.status,
                       COUNT(a.id) as account_count
                FROM devices d
                LEFT JOIN accounts a ON a.device_serial = d.device_serial AND a.status = 'active'
                GROUP BY d.id
                ORDER BY d.device_serial
            """).fetchall())
            return jsonify({'devices': rows})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@content_schedule_bp.route('/api/content-schedule/accounts', methods=['GET'])
def list_accounts_for_schedule():
    """List accounts for the schedule UI, optionally filtered by device."""
    try:
        device_serial = request.args.get('device_serial')
        
        conn = get_conn()
        try:
            if device_serial and device_serial != 'all':
                rows = rows_to_dicts(conn.execute(
                    "SELECT id, device_serial, username, status FROM accounts WHERE device_serial = ? AND status = 'active' ORDER BY username",
                    (device_serial,)
                ).fetchall())
            else:
                rows = rows_to_dicts(conn.execute(
                    "SELECT id, device_serial, username, status FROM accounts WHERE status = 'active' ORDER BY device_serial, username"
                ).fetchall())
            return jsonify({'accounts': rows})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# SERVE MEDIA FILES (for thumbnails)
# =============================================================================

@content_schedule_bp.route('/api/content-schedule/media-file/<path:filepath>')
def serve_media_file(filepath):
    """Serve a media file for thumbnail preview."""
    try:
        full_path = os.path.join(MEDIA_LIBRARY_DIR, filepath)
        if not os.path.exists(full_path):
            return jsonify({'error': 'File not found'}), 404
        
        directory = os.path.dirname(full_path)
        filename = os.path.basename(full_path)
        from flask import send_from_directory
        return send_from_directory(directory, filename)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# TEST POST NOW - Endpoints
# =============================================================================

@content_schedule_bp.route('/api/content-schedule/test-post', methods=['POST'])
def test_post_now():
    """
    Launch a test post immediately on a real device.
    Runs PostContentAction in a background thread.

    Body: {
        account_id, media_path, content_type (post/reel/story),
        caption, hashtags,
        music_search_query (optional), location (optional)
    }
    Returns: { test_id } for polling via /test-post/status
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'No data provided'}), 400

        account_id = data.get('account_id')
        media_path = data.get('media_path', '')
        content_type = data.get('content_type', '')
        caption = data.get('caption', '')
        hashtags = data.get('hashtags', '')
        music_search_query = data.get('music_search_query', '')
        location = data.get('location', '')

        # --- Validation ---
        if not account_id:
            return jsonify({'status': 'error', 'message': 'account_id is required'}), 400
        if content_type not in ('post', 'reel', 'story'):
            return jsonify({'status': 'error', 'message': 'content_type must be post, reel, or story'}), 400
        if not media_path:
            return jsonify({'status': 'error', 'message': 'media_path is required'}), 400

        # Resolve full media path if relative
        full_media_path = media_path
        if not os.path.isabs(media_path):
            full_media_path = os.path.join(MEDIA_LIBRARY_DIR, media_path)
        if not os.path.exists(full_media_path):
            return jsonify({'status': 'error', 'message': 'Media file not found: %s' % media_path}), 400

        # Get account info
        account = get_account_by_id(int(account_id))
        if not account:
            return jsonify({'status': 'error', 'message': 'Account not found (id=%s)' % account_id}), 404

        device_serial = account.get('device_serial')
        if not device_serial:
            return jsonify({'status': 'error', 'message': 'Account has no device assigned'}), 400

        # Check device reachable
        if not check_device_reachable(device_serial):
            return jsonify({'status': 'error',
                            'message': 'Device %s is not reachable via ADB' % device_serial}), 400

        # Create test ID and initial progress
        test_id = 'test_%s' % uuid.uuid4().hex[:10]

        with _test_post_lock:
            _test_post_progress[test_id] = {
                'status': 'starting',
                'message': 'Initializing...',
                'steps': [],
                'account': account.get('username', ''),
                'device': device_serial,
                'content_type': content_type,
                'started_at': datetime.utcnow().isoformat(),
                'completed_at': None,
                'success': None,
                'error': None,
            }

        # Launch background thread
        t = threading.Thread(
            target=_run_test_post,
            args=(test_id, account, full_media_path, content_type,
                  caption, hashtags, music_search_query, location),
            daemon=True,
        )
        t.start()

        return jsonify({
            'status': 'success',
            'test_id': test_id,
            'message': 'Test post started for @%s on %s' % (account.get('username', '?'), device_serial),
        })

    except Exception as e:
        log.exception("test_post_now error")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@content_schedule_bp.route('/api/content-schedule/test-post/status', methods=['GET'])
def test_post_status():
    """Poll status of a test post by test_id."""
    test_id = request.args.get('test_id', '')
    if not test_id:
        return jsonify({'status': 'error', 'message': 'test_id is required'}), 400

    with _test_post_lock:
        progress = _test_post_progress.get(test_id)

    if not progress:
        return jsonify({'status': 'error', 'message': 'Unknown test_id'}), 404

    return jsonify({'status': 'success', 'progress': progress})


def _run_test_post(test_id, account, media_path, content_type,
                   caption, hashtags, music_search_query, location):
    """Background worker for a test post. Mirrors login_automation pattern."""

    def _update(status, message, **extra):
        with _test_post_lock:
            p = _test_post_progress.get(test_id, {})
            p['status'] = status
            p['message'] = message
            p['steps'].append({'time': datetime.utcnow().isoformat(), 'msg': message})
            p.update(extra)
            _test_post_progress[test_id] = p

    device_serial = account['device_serial']
    adb_serial = serial_db_to_adb(device_serial)

    try:
        # Step 1: Connect to device
        _update('running', 'Connecting to device %s ...' % device_serial)

        import uiautomator2 as u2
        device = u2.connect(adb_serial)
        _update('running', 'Connected to device. Preparing PostContentAction...')

        # Step 2: Build schedule_item dict (matches content_schedule row shape)
        schedule_item = {
            'id': 0,
            'content_type': content_type,
            'media_path': media_path,
            'caption': caption,
            'hashtags': hashtags,
            'location': location,
            'music_search_query': music_search_query,
            'music_name': '',
            'mention_username': '',
            'link_url': '',
        }

        # Step 3: Build account_info dict
        account_info = {
            'id': account['id'],
            'username': account.get('username', ''),
            'package': account.get('instagram_package', 'com.instagram.android'),
        }

        _update('running', 'Launching PostContentAction for %s ...' % content_type)

        # Step 4: Import and run PostContentAction
        from automation.actions.post_content import PostContentAction

        action = PostContentAction(
            device=device,
            device_serial=device_serial,
            account_info=account_info,
            session_id='test_post_%s' % test_id,
            schedule_item=schedule_item,
            package=account_info['package'],
        )

        _update('running', 'Executing %s posting flow on device...' % content_type)

        result = action.execute()

        # Step 5: Record result
        now = datetime.utcnow().isoformat()
        if result.get('success'):
            _update('completed', 'Post completed successfully!',
                    success=True, completed_at=now)
        else:
            err = result.get('error_message', 'Unknown failure')
            _update('failed', 'Post failed: %s' % err,
                    success=False, error=err, completed_at=now)

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        log.error("Test post %s failed: %s\n%s", test_id, e, tb)
        _update('failed', 'Error: %s' % str(e),
                success=False, error=str(e),
                completed_at=datetime.utcnow().isoformat())


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _update_batch_counts(conn, batch_id):
    """Recalculate batch completed/failed counts."""
    completed = conn.execute(
        "SELECT COUNT(*) FROM content_schedule WHERE batch_id = ? AND status = 'completed'",
        (batch_id,)
    ).fetchone()[0]
    failed = conn.execute(
        "SELECT COUNT(*) FROM content_schedule WHERE batch_id = ? AND status IN ('failed', 'cancelled')",
        (batch_id,)
    ).fetchone()[0]
    total = conn.execute(
        "SELECT COUNT(*) FROM content_schedule WHERE batch_id = ?",
        (batch_id,)
    ).fetchone()[0]
    
    # If all done, mark batch complete
    pending = conn.execute(
        "SELECT COUNT(*) FROM content_schedule WHERE batch_id = ? AND status IN ('pending', 'posting')",
        (batch_id,)
    ).fetchone()[0]
    
    batch_status = 'active'
    if pending == 0:
        batch_status = 'completed' if failed == 0 else 'completed_with_errors'
    
    conn.execute(
        "UPDATE content_batches SET completed_items = ?, failed_items = ?, total_items = ?, status = ? WHERE batch_id = ?",
        (completed, failed, total, batch_status, batch_id)
    )
