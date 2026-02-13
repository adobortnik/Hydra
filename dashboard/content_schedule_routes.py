"""
Content Schedule Routes - API for scheduling posts, reels, and stories.

Blueprint prefix: /api/content-schedule
All data stored in phone_farm.db (centralized database).
Tables: content_schedule, content_batches
"""

import os
import re
import json
import uuid
import subprocess
import threading
import logging
import sqlite3
import time as _time
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, render_template
from phone_farm_db import get_conn, row_to_dict, rows_to_dicts, get_account_by_id
from adb_helper import serial_db_to_adb, check_device_reachable
from werkzeug.utils import secure_filename

log = logging.getLogger(__name__)

content_schedule_bp = Blueprint('content_schedule', __name__)

# Media library directory (same as simple_app.py)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA_LIBRARY_DIR = os.path.join(BASE_DIR, 'media_library')

# Supported media extensions
MEDIA_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp4', '.mov', '.avi', '.mkv', '.webm'}


# =============================================================================
# MEDIA VALIDATION
# =============================================================================

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png'}
VIDEO_EXTENSIONS = {'.mp4', '.mov'}
MAX_FILE_SIZE_MB = 100
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Duration limits in seconds
REEL_MAX_DURATION = 90
STORY_MAX_DURATION = 60


def _get_video_duration(filepath):
    """Return video duration in seconds using ffprobe, or None if unavailable."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', filepath],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        # ffprobe not installed or timed out -- skip duration check
        pass
    return None


def validate_media(media_path, content_type):
    """
    Validate a media file for the given content_type (post/reel/story).

    Returns (ok: bool, error_message: str or None).
    """
    if not media_path:
        return True, None  # no media supplied -- let the caller decide if that's ok

    # Resolve full path if relative
    full_path = media_path
    if not os.path.isabs(media_path):
        full_path = os.path.join(MEDIA_LIBRARY_DIR, media_path)

    # 1. File exists?
    if not os.path.exists(full_path):
        return False, "Media file not found: %s" % media_path

    # 2. File size
    file_size = os.path.getsize(full_path)
    if file_size > MAX_FILE_SIZE_BYTES:
        size_mb = round(file_size / (1024 * 1024), 1)
        return False, "File too large: %sMB (max %sMB)" % (size_mb, MAX_FILE_SIZE_MB)

    ext = os.path.splitext(media_path)[1].lower()
    is_image = ext in IMAGE_EXTENSIONS
    is_video = ext in VIDEO_EXTENSIONS

    if not is_image and not is_video:
        return False, "Unsupported media type: %s. Allowed: %s" % (
            ext, ', '.join(sorted(IMAGE_EXTENSIONS | VIDEO_EXTENSIONS)))

    # 3. Type-specific checks
    if content_type == 'reel':
        if not is_video:
            return False, ("Reels require video files (%s). Got: %s"
                           % (', '.join(sorted(VIDEO_EXTENSIONS)), os.path.basename(media_path)))
        duration = _get_video_duration(full_path)
        if duration is not None and duration > REEL_MAX_DURATION:
            return False, ("Reel video too long: %.1fs (max %ds)"
                           % (duration, REEL_MAX_DURATION))

    elif content_type == 'story':
        # stories accept images or videos
        if is_video:
            duration = _get_video_duration(full_path)
            if duration is not None and duration > STORY_MAX_DURATION:
                return False, ("Story video too long: %.1fs (max %ds)"
                               % (duration, STORY_MAX_DURATION))

    elif content_type == 'post':
        # posts accept images or videos -- no extra duration constraint
        pass

    return True, None


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
# BATCH PROGRESS - In-memory tracking for async batch processing
# =============================================================================

_batch_progress = {}       # batch_id -> {status, total, done, current_item, errors, result, created_at}
_batch_progress_lock = threading.Lock()
_BATCH_PROGRESS_TTL = 300  # 5 minutes


def _cleanup_old_batch_progress():
    """Remove batch progress entries older than TTL."""
    now = _time.time()
    with _batch_progress_lock:
        expired = [k for k, v in _batch_progress.items()
                   if now - v.get('created_at_ts', 0) > _BATCH_PROGRESS_TTL
                   and v.get('status') in ('completed', 'failed')]
        for k in expired:
            del _batch_progress[k]


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

        # Validate media if provided
        media_path = data.get('media_path')
        if media_path:
            ok, err = validate_media(media_path, data['content_type'])
            if not ok:
                return jsonify({'error': err}), 400

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
    Async bulk schedule: validates input, returns immediately with batch_id,
    then processes in a background thread.

    Supports two modes:
    1. Smart mode (schedule_items): Pre-computed schedule from frontend strategies.
    2. Legacy mode (media_paths + accounts + start_time + interval_hours).

    Returns: {batch_id, status: 'processing'} immediately.
    Poll GET /api/content-schedule/batch/<batch_id>/progress for status.
    """
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        content_type = data.get('content_type')
        if content_type not in ('post', 'reel', 'story'):
            return jsonify({'error': 'content_type must be post, reel, or story'}), 400

        caption_template = data.get('caption_template', '')
        batch_id = str(uuid.uuid4())[:12]
        batch_name = data.get('batch_name', f"{content_type.title()} batch - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}")

        schedule_items = data.get('schedule_items')

        # ---------- Quick validation (sync, before returning) ----------
        if schedule_items and isinstance(schedule_items, list) and len(schedule_items) > 0:
            # Smart mode - validate media upfront
            validation_errors = []
            for si in schedule_items:
                mp = si.get('media_path', '')
                if mp:
                    ok, err = validate_media(mp, content_type)
                    if not ok:
                        validation_errors.append(err)
            if validation_errors:
                return jsonify({'error': 'Media validation failed', 'details': validation_errors}), 400
            total_estimate = len(schedule_items)
        else:
            # Legacy mode - basic validation
            media_paths = data.get('media_paths', [])
            if not media_paths:
                return jsonify({'error': 'media_paths is required and must not be empty'}), 400
            validation_errors = []
            for mp in media_paths:
                ok, err = validate_media(mp, content_type)
                if not ok:
                    validation_errors.append(err)
            if validation_errors:
                return jsonify({'error': 'Media validation failed', 'details': validation_errors}), 400
            if not data.get('start_time'):
                return jsonify({'error': 'start_time is required'}), 400
            total_estimate = len(media_paths) * max(len(data.get('accounts', [])), 1)

        # ---------- Set up progress tracking ----------
        _cleanup_old_batch_progress()
        with _batch_progress_lock:
            _batch_progress[batch_id] = {
                'status': 'processing',
                'total': total_estimate,
                'done': 0,
                'current_item': 'Starting...',
                'errors': [],
                'result': None,
                'created_at_ts': _time.time(),
            }

        # ---------- Spawn background thread ----------
        t = threading.Thread(
            target=_process_batch_background,
            args=(batch_id, data, content_type, caption_template, batch_name),
            daemon=True,
        )
        t.start()

        return jsonify({
            'batch_id': batch_id,
            'status': 'processing',
            'name': batch_name,
            'total_estimate': total_estimate,
        }), 202

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@content_schedule_bp.route('/api/content-schedule/batch/<batch_id>/progress', methods=['GET'])
def get_batch_progress(batch_id):
    """Poll progress of an async batch operation."""
    with _batch_progress_lock:
        progress = _batch_progress.get(batch_id)
    if not progress:
        return jsonify({'error': 'Unknown batch_id or expired'}), 404
    return jsonify(progress)


def _process_batch_background(batch_id, data, content_type, caption_template, batch_name):
    """
    Background worker for batch processing.
    Handles both smart mode and legacy mode.
    Optimizes AI caption generation into a single batched call.
    """
    def _update_progress(**kwargs):
        with _batch_progress_lock:
            p = _batch_progress.get(batch_id, {})
            p.update(kwargs)
            _batch_progress[batch_id] = p

    try:
        hashtags = data.get('hashtags', '')
        location = data.get('location', '')
        mention_username = data.get('mention_username', '')
        music_search_query = data.get('music_search_query', '')
        link_url = data.get('link_url', '')
        now = datetime.utcnow().isoformat()

        schedule_items = data.get('schedule_items')

        conn = get_conn()
        try:
            total_items = 0
            unique_accounts = set()
            unique_media = set()
            first_time = None
            last_time = None

            if schedule_items and isinstance(schedule_items, list) and len(schedule_items) > 0:
                # ---- SMART MODE ----
                _update_progress(current_item='Preparing schedule items...', total=len(schedule_items))

                # Check for AI tags
                has_ai_tags = bool(AI_TAG_PATTERN.search(caption_template))

                # Phase 1: Generate AI captions in ONE batch call if needed
                captions_list = []
                if has_ai_tags:
                    _update_progress(current_item='Generating AI captions...')
                    ai_api_key = _get_openai_key()
                    if ai_api_key:
                        try:
                            # Extract the prompt from the template
                            matches = list(AI_TAG_PATTERN.finditer(caption_template))
                            base_prompt = None
                            if matches:
                                custom = matches[0].group(1)
                                if custom and custom.strip():
                                    base_prompt = custom.strip()
                            if not base_prompt:
                                base_prompt = (
                                    f"Write a short engaging Instagram caption for a {content_type}. "
                                    "Be creative and use emojis naturally."
                                )

                            count_needed = len(schedule_items)
                            _update_progress(current_item=f'Generating {count_needed} AI captions in one batch...')
                            captions_list = _generate_captions_openai(
                                ai_api_key, base_prompt, 'engaging', content_type, count=count_needed
                            )
                        except Exception as e:
                            log.error("Batch AI caption generation failed: %s", e)
                            _update_progress(current_item='AI caption generation failed, using template...')
                            captions_list = []

                # Phase 2: Build all INSERT rows
                insert_rows = []
                for idx, si in enumerate(schedule_items):
                    mp = si.get('media_path', '')
                    scheduled_time_str = si.get('scheduled_time', '')
                    username = si.get('username', '')

                    _update_progress(
                        done=idx,
                        current_item=f'Preparing item {idx + 1}/{len(schedule_items)} — @{username}...'
                    )

                    # Parse time
                    try:
                        st = datetime.fromisoformat(
                            scheduled_time_str.replace('Z', '+00:00').replace('T', ' ').split('+')[0]
                        )
                    except (ValueError, AttributeError):
                        st = datetime.utcnow()

                    # Resolve caption
                    item_caption = caption_template
                    if has_ai_tags and captions_list:
                        # Use pre-generated caption from batch
                        generated = captions_list[idx % len(captions_list)]
                        # Replace ALL [AI...] tags in the template with this generated caption
                        item_caption = AI_TAG_PATTERN.sub(generated, caption_template)
                    elif has_ai_tags:
                        # Fallback: leave template as-is (AI generation failed)
                        item_caption = caption_template

                    insert_rows.append((
                        si.get('account_id'),
                        si.get('device_serial'),
                        username,
                        content_type,
                        mp,
                        item_caption,
                        hashtags,
                        location,
                        None,
                        music_search_query,
                        mention_username,
                        link_url,
                        st.isoformat(),
                        batch_id,
                        now, now
                    ))
                    total_items += 1
                    unique_accounts.add(username)
                    unique_media.add(mp)
                    if first_time is None or st < first_time:
                        first_time = st
                    if last_time is None or st > last_time:
                        last_time = st

                # Phase 3: Batch insert to DB
                _update_progress(current_item='Saving to database...', done=len(schedule_items))
                conn.executemany("""
                    INSERT INTO content_schedule
                    (account_id, device_serial, username, content_type, media_path,
                     caption, hashtags, location, music_name, music_search_query,
                     mention_username, link_url, scheduled_time, status, batch_id,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                """, insert_rows)

            else:
                # ---- LEGACY MODE ----
                media_paths = data.get('media_paths', [])
                start_time_str = data.get('start_time')
                interval_hours = float(data.get('interval_hours', 24))
                if interval_hours <= 0:
                    interval_hours = 24

                try:
                    start_time = datetime.fromisoformat(
                        start_time_str.replace('Z', '+00:00').replace('T', ' ').split('+')[0]
                    )
                except (ValueError, TypeError):
                    start_time = datetime.utcnow()

                accounts = data.get('accounts', [])
                device_serial = data.get('device_serial')

                # Resolve accounts
                if accounts == 'all' or (isinstance(accounts, str) and accounts.lower() == 'all'):
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
                            row = conn.execute(
                                "SELECT id, device_serial, username FROM accounts WHERE username = ?",
                                (acct,)
                            ).fetchone()
                            if row:
                                resolved.append({'account_id': row['id'], 'device_serial': row['device_serial'], 'username': row['username']})
                    accounts = resolved

                if not accounts:
                    _update_progress(status='failed', current_item='No valid accounts found')
                    _batch_progress[batch_id]['errors'].append('No valid accounts found')
                    return

                total_legacy = len(media_paths) * len(accounts)
                _update_progress(total=total_legacy, current_item='Preparing legacy schedule...')

                # Batch AI captions for legacy mode
                has_ai_tags_legacy = bool(AI_TAG_PATTERN.search(caption_template))
                captions_list = []
                if has_ai_tags_legacy:
                    _update_progress(current_item='Generating AI captions...')
                    ai_api_key_legacy = _get_openai_key()
                    if ai_api_key_legacy:
                        try:
                            matches = list(AI_TAG_PATTERN.finditer(caption_template))
                            base_prompt = None
                            if matches:
                                custom = matches[0].group(1)
                                if custom and custom.strip():
                                    base_prompt = custom.strip()
                            if not base_prompt:
                                base_prompt = (
                                    f"Write a short engaging Instagram caption for a {content_type}. "
                                    "Be creative and use emojis naturally."
                                )
                            captions_list = _generate_captions_openai(
                                ai_api_key_legacy, base_prompt, 'engaging', content_type, count=total_legacy
                            )
                        except Exception as e:
                            log.error("Legacy batch AI caption generation failed: %s", e)

                current_time = start_time
                first_time = start_time
                insert_rows = []
                caption_idx = 0

                for media_path in media_paths:
                    for acct in accounts:
                        username = acct.get('username', '')
                        _update_progress(
                            done=total_items,
                            current_item=f'Preparing {total_items + 1}/{total_legacy} — @{username}...'
                        )

                        item_caption = caption_template
                        if has_ai_tags_legacy and captions_list:
                            generated = captions_list[caption_idx % len(captions_list)]
                            item_caption = AI_TAG_PATTERN.sub(generated, caption_template)
                            caption_idx += 1

                        insert_rows.append((
                            acct.get('account_id'),
                            acct.get('device_serial', device_serial),
                            username,
                            content_type,
                            media_path,
                            item_caption,
                            hashtags,
                            location,
                            None,
                            music_search_query,
                            mention_username,
                            link_url,
                            current_time.isoformat(),
                            batch_id,
                            now, now
                        ))
                        total_items += 1
                        unique_accounts.add(username)
                        current_time += timedelta(hours=interval_hours)

                last_time = current_time
                unique_media = set(media_paths)

                # Batch insert
                _update_progress(current_item='Saving to database...', done=total_items)
                conn.executemany("""
                    INSERT INTO content_schedule
                    (account_id, device_serial, username, content_type, media_path,
                     caption, hashtags, location, music_name, music_search_query,
                     mention_username, link_url, scheduled_time, status, batch_id,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                """, insert_rows)

            # Create batch record
            conn.execute("""
                INSERT INTO content_batches (batch_id, name, content_type, total_items, status, created_at)
                VALUES (?, ?, ?, ?, 'active', ?)
            """, (batch_id, batch_name, content_type, total_items, now))

            conn.commit()

            result = {
                'batch_id': batch_id,
                'name': batch_name,
                'total_items': total_items,
                'accounts': len(unique_accounts),
                'media_files': len(unique_media),
                'start_time': first_time.isoformat() if first_time else now,
                'end_time': last_time.isoformat() if last_time else now,
            }

            _update_progress(
                status='completed',
                done=total_items,
                total=total_items,
                current_item='Done!',
                result=result,
            )

        finally:
            conn.close()

    except Exception as e:
        import traceback
        traceback.print_exc()
        log.error("Batch %s background processing failed: %s", batch_id, e)
        with _batch_progress_lock:
            p = _batch_progress.get(batch_id, {})
            p['status'] = 'failed'
            p['current_item'] = f'Error: {str(e)}'
            p['errors'] = p.get('errors', []) + [str(e)]
            _batch_progress[batch_id] = p


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

def _get_media_library_db():
    """Get connection to the media library database."""
    db_path = os.path.join(MEDIA_LIBRARY_DIR, 'media_library.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@content_schedule_bp.route('/api/content-schedule/media-folders', methods=['GET'])
def list_media_folders():
    """List user-created folders from the media library database."""
    try:
        folders = []
        try:
            mlconn = _get_media_library_db()
            cursor = mlconn.cursor()
            cursor.execute('SELECT * FROM folders ORDER BY name')
            rows = cursor.fetchall()
            for row in rows:
                folder_id = row['id']
                name = row['name']
                cursor.execute(
                    'SELECT COUNT(*) as cnt FROM media_folders WHERE folder_id = ?',
                    (folder_id,)
                )
                cnt_row = cursor.fetchone()
                media_count = cnt_row['cnt'] if cnt_row else 0
                folders.append({
                    'id': folder_id,
                    'name': name,
                    'path': folder_id,  # use id as path key
                    'description': row['description'] or '',
                    'media_count': media_count
                })
            mlconn.close()
        except Exception as db_err:
            log.warning("Could not read media library DB, falling back to filesystem: %s", db_err)
            # Fallback: scan filesystem but skip processed/original
            skip_dirs = {'processed', 'original', '__pycache__'}
            for search_dir in [MEDIA_LIBRARY_DIR]:
                if not os.path.exists(search_dir):
                    continue
                for entry in sorted(os.listdir(search_dir)):
                    if entry in skip_dirs or entry.startswith('.'):
                        continue
                    full_path = os.path.join(search_dir, entry)
                    if os.path.isdir(full_path):
                        media_count = sum(
                            1 for f in os.listdir(full_path)
                            if os.path.splitext(f)[1].lower() in MEDIA_EXTENSIONS
                        )
                        rel_path = os.path.relpath(full_path, MEDIA_LIBRARY_DIR)
                        folders.append({
                            'id': rel_path,
                            'name': entry,
                            'path': rel_path,
                            'description': '',
                            'media_count': media_count
                        })

        # Also add an "All Media" virtual folder
        try:
            mlconn2 = _get_media_library_db()
            c2 = mlconn2.cursor()
            c2.execute('SELECT COUNT(*) as cnt FROM media')
            total = c2.fetchone()['cnt']
            mlconn2.close()
            folders.insert(0, {
                'id': '__all__',
                'name': 'All Media',
                'path': '__all__',
                'description': 'All media files',
                'media_count': total,
                'is_virtual': True
            })
        except Exception:
            pass

        return jsonify({'folders': folders})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@content_schedule_bp.route('/api/content-schedule/media-folders', methods=['POST'])
def create_media_folder_cs():
    """Create a new folder in the media library from the content schedule wizard."""
    try:
        data = request.json
        folder_name = (data or {}).get('name', '').strip()
        if not folder_name:
            return jsonify({'error': 'Folder name is required'}), 400

        description = (data or {}).get('description', '')

        mlconn = _get_media_library_db()
        cursor = mlconn.cursor()
        folder_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        cursor.execute(
            'INSERT INTO folders (id, name, description, created_at, parent_id) VALUES (?, ?, ?, ?, ?)',
            (folder_id, folder_name, description, now, None)
        )
        mlconn.commit()
        mlconn.close()

        return jsonify({'id': folder_id, 'name': folder_name, 'path': folder_id, 'media_count': 0}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@content_schedule_bp.route('/api/content-schedule/media-folders/<path:folder>', methods=['GET'])
def list_folder_files(folder):
    """List media files in a folder. Supports both DB folder IDs and filesystem paths."""
    try:
        files = []

        # Check if this is the virtual "all" folder
        if folder == '__all__':
            try:
                mlconn = _get_media_library_db()
                cursor = mlconn.cursor()
                cursor.execute('SELECT * FROM media ORDER BY upload_date DESC')
                rows = cursor.fetchall()
                for row in rows:
                    original_path = row['original_path'] or ''
                    filename = row['filename']
                    ext = os.path.splitext(filename)[1].lower()
                    is_video = ext in {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
                    media_type = row['media_type'] or ('video' if is_video else 'image')

                    # Build full path for scheduler
                    full_path = os.path.join(MEDIA_LIBRARY_DIR, 'original', original_path) if original_path else ''
                    if not os.path.isabs(original_path or ''):
                        full_path = os.path.join(MEDIA_LIBRARY_DIR, 'original', original_path)
                    else:
                        full_path = original_path

                    # Thumbnail path
                    processed_path = row['processed_path'] or ''
                    if processed_path:
                        thumb_url = '/api/media/processed/' + processed_path.replace('\\', '/').split('/')[-1]
                    else:
                        thumb_url = '/api/media/original/' + (original_path or filename).replace('\\', '/').split('/')[-1]

                    files.append({
                        'name': filename,
                        'path': original_path or filename,
                        'full_path': full_path,
                        'size': row['file_size'] or 0,
                        'is_video': is_video,
                        'media_type': media_type,
                        'extension': ext,
                        'thumb_url': thumb_url,
                        'media_id': row['id']
                    })
                mlconn.close()
                return jsonify({'folder': folder, 'files': files, 'total': len(files)})
            except Exception as e:
                log.warning("Error reading all media from DB: %s", e)
                return jsonify({'folder': folder, 'files': [], 'total': 0})

        # Try DB folder first (folder is a UUID)
        try:
            mlconn = _get_media_library_db()
            cursor = mlconn.cursor()
            cursor.execute('SELECT id FROM folders WHERE id = ?', (folder,))
            if cursor.fetchone():
                # It's a DB folder — get media via media_folders join
                cursor.execute('''
                    SELECT m.* FROM media m
                    JOIN media_folders mf ON m.id = mf.media_id
                    WHERE mf.folder_id = ?
                    ORDER BY m.upload_date DESC
                ''', (folder,))
                rows = cursor.fetchall()
                for row in rows:
                    original_path = row['original_path'] or ''
                    filename = row['filename']
                    ext = os.path.splitext(filename)[1].lower()
                    is_video = ext in {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
                    media_type = row['media_type'] or ('video' if is_video else 'image')

                    full_path = os.path.join(MEDIA_LIBRARY_DIR, 'original', original_path) if original_path else ''
                    if original_path and os.path.isabs(original_path):
                        full_path = original_path

                    processed_path = row['processed_path'] or ''
                    if processed_path:
                        thumb_url = '/api/media/processed/' + processed_path.replace('\\', '/').split('/')[-1]
                    else:
                        thumb_url = '/api/media/original/' + (original_path or filename).replace('\\', '/').split('/')[-1]

                    files.append({
                        'name': filename,
                        'path': original_path or filename,
                        'full_path': full_path,
                        'size': row['file_size'] or 0,
                        'is_video': is_video,
                        'media_type': media_type,
                        'extension': ext,
                        'thumb_url': thumb_url,
                        'media_id': row['id']
                    })
                mlconn.close()
                return jsonify({'folder': folder, 'files': files, 'total': len(files)})
            mlconn.close()
        except Exception as db_err:
            log.warning("DB folder lookup failed: %s", db_err)

        # Fallback: filesystem path
        folder_path = os.path.join(MEDIA_LIBRARY_DIR, folder)
        if not os.path.exists(folder_path):
            return jsonify({'error': 'Folder not found'}), 404

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
                    'media_type': 'video' if is_video else 'image',
                    'extension': ext,
                    'thumb_url': '/api/content-schedule/media-file/' + rel_path.replace('\\', '/'),
                    'media_id': None
                })

        return jsonify({'folder': folder, 'files': files, 'total': len(files)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@content_schedule_bp.route('/api/content-schedule/upload', methods=['POST'])
def upload_media_cs():
    """Upload media files from the content schedule wizard. Saves to media library."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        uploaded_files = request.files.getlist('file')
        folder_id = request.form.get('folder_id', '')
        results = []

        for file in uploaded_files:
            if not file or file.filename == '':
                continue

            filename = secure_filename(file.filename)
            ext = os.path.splitext(filename)[1].lower()
            if ext not in MEDIA_EXTENSIONS:
                results.append({'name': filename, 'error': 'Unsupported file type'})
                continue

            # Generate unique filename
            unique_name = str(uuid.uuid4())[:8] + '_' + filename

            # Save to original directory
            original_dir = os.path.join(MEDIA_LIBRARY_DIR, 'original')
            os.makedirs(original_dir, exist_ok=True)
            save_path = os.path.join(original_dir, unique_name)
            file.save(save_path)

            file_size = os.path.getsize(save_path)
            is_video = ext in {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
            media_type = 'video' if is_video else 'image'

            # Register in media library DB
            media_id = str(uuid.uuid4())
            now = datetime.utcnow().isoformat()

            try:
                mlconn = _get_media_library_db()
                cursor = mlconn.cursor()
                cursor.execute('''
                    INSERT INTO media (id, filename, original_path, media_type, file_size, upload_date, times_used)
                    VALUES (?, ?, ?, ?, ?, ?, 0)
                ''', (media_id, filename, unique_name, media_type, file_size, now))

                # Add to folder if specified
                if folder_id and folder_id != '__all__':
                    cursor.execute(
                        'INSERT OR IGNORE INTO media_folders (media_id, folder_id) VALUES (?, ?)',
                        (media_id, folder_id)
                    )

                mlconn.commit()
                mlconn.close()
            except Exception as db_err:
                log.warning("Failed to register uploaded file in DB: %s", db_err)

            results.append({
                'name': filename,
                'path': unique_name,
                'full_path': save_path,
                'size': file_size,
                'is_video': is_video,
                'media_type': media_type,
                'extension': ext,
                'thumb_url': '/api/media/original/' + unique_name,
                'media_id': media_id,
                'success': True
            })

        return jsonify({'files': results, 'uploaded': len([r for r in results if r.get('success')])}), 201
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
    """List accounts for the schedule UI, optionally filtered by device. Includes work hours."""
    try:
        device_serial = request.args.get('device_serial')
        
        conn = get_conn()
        try:
            if device_serial and device_serial != 'all':
                rows = rows_to_dicts(conn.execute(
                    "SELECT id, device_serial, username, status, start_time, end_time FROM accounts WHERE device_serial = ? AND status = 'active' ORDER BY username",
                    (device_serial,)
                ).fetchall())
            else:
                rows = rows_to_dicts(conn.execute(
                    "SELECT id, device_serial, username, status, start_time, end_time FROM accounts WHERE status = 'active' ORDER BY device_serial, username"
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

        # Validate media for content type
        ok, validation_err = validate_media(media_path, content_type)
        if not ok:
            return jsonify({'status': 'error', 'message': validation_err}), 400

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
# AI CAPTION GENERATION
# =============================================================================

# Regex to find [AI] or [AI:custom prompt] tags
AI_TAG_PATTERN = re.compile(r'\[AI(?::([^\]]*))?\]')

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'global_settings.json')


def _get_openai_key():
    """Read OpenAI API key from global_settings.json. Returns key or empty string."""
    try:
        with open(SETTINGS_PATH, 'r') as f:
            settings = json.load(f)
        return (settings.get('ai', {}).get('openai_api_key', '') or '').strip()
    except Exception as e:
        log.warning("Could not read global_settings.json for AI key: %s", e)
        return ''


def _generate_captions_openai(api_key, prompts, tone='engaging', content_type='post', count=1):
    """
    Generate captions using OpenAI API.

    Args:
        api_key: OpenAI API key
        prompts: list of prompt strings (one per caption needed), or a single string
        tone: tone/style for generation
        content_type: post/reel/story
        count: number of captions to generate (used when prompts is a single string)

    Returns:
        list of generated caption strings
    """
    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    system_prompt = (
        "You are an Instagram caption writer. Generate captions that are creative, "
        "authentic, and engaging. Rules:\n"
        "- Do NOT wrap the caption in quotes\n"
        "- Include emojis naturally (don't overdo it)\n"
        "- Keep it concise (1-3 sentences max)\n"
        "- Match the requested tone/style\n"
        "- Don't include hashtags (those are added separately)\n"
        "- Each caption should be unique and different from others\n"
        f"- Content type: Instagram {content_type}\n"
        f"- Tone/style: {tone}"
    )

    if isinstance(prompts, str):
        # Single prompt, generate `count` captions
        if count == 1:
            user_msg = prompts
        else:
            user_msg = (
                f"Generate {count} UNIQUE and DIFFERENT Instagram captions. "
                f"Base prompt: {prompts}\n\n"
                f"Return exactly {count} captions, one per line. "
                "Number them like 1. 2. 3. etc."
            )

        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_msg}
            ],
            temperature=0.9,
            max_tokens=500 * max(count, 1)
        )

        text = response.choices[0].message.content.strip()

        if count == 1:
            return [text]
        else:
            # Parse numbered list
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            captions = []
            for line in lines:
                # Remove numbering like "1. ", "1) ", "- "
                cleaned = re.sub(r'^[\d]+[.)]\s*', '', line).strip()
                cleaned = re.sub(r'^[-•]\s*', '', cleaned).strip()
                if cleaned:
                    captions.append(cleaned)
            # Ensure we have the right count
            while len(captions) < count:
                captions.append(captions[-1] if captions else text)
            return captions[:count]

    elif isinstance(prompts, list):
        # Multiple individual prompts — generate one caption per prompt
        captions = []
        # Batch into a single request for efficiency
        if len(prompts) <= 10:
            numbered = '\n'.join(f"{i+1}. {p}" for i, p in enumerate(prompts))
            user_msg = (
                f"Generate {len(prompts)} UNIQUE Instagram captions, one for each prompt below.\n\n"
                f"{numbered}\n\n"
                f"Return exactly {len(prompts)} captions, numbered 1. through {len(prompts)}. "
                "Each must be unique and match its corresponding prompt."
            )

            response = client.chat.completions.create(
                model='gpt-4o-mini',
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_msg}
                ],
                temperature=0.9,
                max_tokens=300 * len(prompts)
            )

            text = response.choices[0].message.content.strip()
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            for line in lines:
                cleaned = re.sub(r'^[\d]+[.)]\s*', '', line).strip()
                cleaned = re.sub(r'^[-•]\s*', '', cleaned).strip()
                if cleaned:
                    captions.append(cleaned)

            while len(captions) < len(prompts):
                captions.append(captions[-1] if captions else 'Check out this post! ✨')
            return captions[:len(prompts)]
        else:
            # Too many — batch in groups of 10
            for i in range(0, len(prompts), 10):
                batch = prompts[i:i+10]
                batch_results = _generate_captions_openai(api_key, batch, tone, content_type)
                captions.extend(batch_results)
            return captions

    return ['']


def resolve_ai_tags(caption, content_type='post', tone='engaging', api_key=None):
    """
    Resolve all [AI] and [AI:prompt] tags in a caption for a SINGLE post.
    Returns the caption with tags replaced by AI-generated text.
    If no API key or AI fails, returns the caption unchanged.
    """
    if not caption or '[AI' not in caption:
        return caption

    if not api_key:
        api_key = _get_openai_key()
    if not api_key:
        log.warning("AI tags found in caption but no OpenAI API key configured")
        return caption

    matches = list(AI_TAG_PATTERN.finditer(caption))
    if not matches:
        return caption

    try:
        prompts = []
        for match in matches:
            custom_prompt = match.group(1)
            if custom_prompt and custom_prompt.strip():
                prompts.append(custom_prompt.strip())
            else:
                prompts.append(
                    f"Write a short engaging Instagram caption for a {content_type}. "
                    "Be creative and use emojis naturally."
                )

        generated = _generate_captions_openai(api_key, prompts, tone, content_type)

        # Replace tags from right to left to preserve positions
        result = caption
        for match, replacement in zip(reversed(matches), reversed(generated)):
            result = result[:match.start()] + replacement + result[match.end():]

        return result

    except Exception as e:
        log.error("AI tag resolution failed: %s", e)
        return caption


@content_schedule_bp.route('/api/content-schedule/ai-caption', methods=['POST'])
def generate_ai_caption():
    """
    Generate AI-powered captions.

    Body: {prompt: str, tone: str, content_type: str, count: int}
    Returns: {captions: [str, ...]}
    """
    try:
        data = request.json or {}
        prompt = data.get('prompt', '').strip()
        tone = data.get('tone', 'engaging').strip()
        content_type = data.get('content_type', 'post').strip()
        count = min(int(data.get('count', 1)), 20)  # cap at 20

        if not prompt:
            prompt = f"Write a short engaging Instagram caption for a {content_type}. Be creative and use emojis naturally."

        api_key = _get_openai_key()
        if not api_key:
            return jsonify({
                'error': 'OpenAI API key not configured. Add your key to dashboard/global_settings.json under ai.openai_api_key'
            }), 400

        captions = _generate_captions_openai(api_key, prompt, tone, content_type, count)
        return jsonify({'captions': captions})

    except Exception as e:
        log.error("AI caption generation failed: %s", e)
        return jsonify({'error': 'AI generation failed: %s' % str(e)}), 500


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
