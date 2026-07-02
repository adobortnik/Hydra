"""
Spoofing service — Flask blueprint.

Endpoints:
  GET  /spoofing                            standalone UI page
  POST /api/spoof/upload                    multipart upload -> {path, kind}
  POST /api/spoof/job                       enqueue async job
  GET  /api/spoof/job/<id>                  poll job status
  POST /api/spoof/quick                     synchronous (count <= 2)
  GET  /api/spoof/variants?source=...       list known variants for a source
  GET  /api/spoof/file?path=...             stream a (source or variant) file

Background worker thread polls `spoof_jobs` for status='queued' and processes.

Storage layout under media_library/:
  spoof_sources/   uploaded source files (kept so the UI can replay)
  spoof_variants/  generated variants — flat dir, random names
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime

from flask import (Blueprint, jsonify, render_template, request,
                   send_file, abort)
from werkzeug.utils import secure_filename

from spoofing_service import (PRESETS, is_image, is_video, spoof_one,
                              IMAGE_EXTS, VIDEO_EXTS, DEFAULT_HASH_THRESHOLD)
from spoof_storage import get_sources_dir, get_variants_dir

log = logging.getLogger(__name__)
spoofing_bp = Blueprint('spoofing', __name__)

# Paths — vault root is configurable via Settings page. Use the helpers from
# spoof_storage at CALL TIME so a settings change applies without restart.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'db', 'phone_farm.db')

_DB_INIT_DONE = False
_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()


# ─────────────────────────────────────────────────────────────────
# DB schema
# ─────────────────────────────────────────────────────────────────

def _init_db():
    """Lazy-create the spoof_jobs + media_variants tables."""
    global _DB_INIT_DONE
    if _DB_INIT_DONE:
        return
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS spoof_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_path   TEXT NOT NULL,
                preset        TEXT DEFAULT 'medium',
                count         INTEGER DEFAULT 1,
                allow_mirror  INTEGER DEFAULT 1,
                status        TEXT DEFAULT 'queued',
                progress      INTEGER DEFAULT 0,
                variants_json TEXT,
                error_message TEXT,
                created_at    TEXT,
                updated_at    TEXT,
                completed_at  TEXT
            );
            CREATE TABLE IF NOT EXISTS media_variants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_path  TEXT,
                variant_path TEXT,
                preset       TEXT,
                seed         INTEGER,
                job_id       INTEGER,
                stats_json   TEXT,
                claimed_by_account_id INTEGER,
                claimed_at   TEXT,
                created_at   TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_variants_source
                ON media_variants(source_path);
            CREATE INDEX IF NOT EXISTS idx_variants_claimed
                ON media_variants(claimed_by_account_id);
        """)
        # Idempotent migration for older DBs that have spoof_jobs without
        # the allow_mirror column.
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(spoof_jobs)")]
            if 'allow_mirror' not in cols:
                conn.execute("ALTER TABLE spoof_jobs ADD COLUMN allow_mirror "
                             "INTEGER DEFAULT 1")
                conn.commit()
        except Exception:
            pass
        conn.commit()
    finally:
        conn.close()
    _DB_INIT_DONE = True


def _conn():
    _init_db()
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    return c


# ─────────────────────────────────────────────────────────────────
# Worker thread
# ─────────────────────────────────────────────────────────────────

def _start_worker_once():
    """Spin up the background worker thread. Idempotent."""
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        _WORKER_STARTED = True
    t = threading.Thread(target=_worker_loop, name='spoof-worker', daemon=True)
    t.start()
    log.info("spoof-worker thread started")


def _worker_loop():
    """Poll spoof_jobs for queued items, run them sequentially."""
    while True:
        try:
            job = _claim_next_job()
            if job is None:
                time.sleep(2)
                continue
            _process_job(job)
        except Exception as e:
            log.error("spoof worker top-level error: %s", e, exc_info=True)
            time.sleep(5)


def _claim_next_job():
    """Atomically pick the oldest queued job and mark it 'running'.
    Returns the row dict, or None if no work."""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM spoof_jobs WHERE status='queued' "
            "ORDER BY id ASC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        now = datetime.utcnow().isoformat()
        r = conn.execute(
            "UPDATE spoof_jobs SET status='running', updated_at=? "
            "WHERE id=? AND status='queued'",
            (now, row['id']))
        conn.commit()
        if r.rowcount == 0:
            return None  # someone else grabbed it
        return dict(row)
    finally:
        conn.close()


def _process_job(job):
    job_id = job['id']
    src = job['source_path']
    preset = job['preset'] or 'medium'
    count = max(1, int(job['count'] or 1))
    allow_mirror = bool(job.get('allow_mirror', 1))
    variants = []
    error = None

    log.info("spoof job #%d start: src=%s preset=%s count=%d mirror=%s",
             job_id, os.path.basename(src), preset, count, allow_mirror)

    if not os.path.exists(src):
        _finish_job(job_id, status='failed',
                    error="source file missing: " + src)
        return

    ext = os.path.splitext(src)[1].lower() or '.bin'

    for i in range(count):
        try:
            v_data = _generate_one_with_retry(src, ext, preset, job_id,
                                              allow_mirror=allow_mirror)
            variants.append(v_data)
            _bump_progress(job_id, i + 1, variants)
        except Exception as e:
            log.error("spoof job #%d variant %d failed: %s",
                      job_id, i, e, exc_info=True)
            error = str(e)
            break

    status = 'done' if not error else ('failed' if not variants else 'partial')
    _finish_job(job_id, status=status, error=error)
    log.info("spoof job #%d %s — %d/%d variants",
             job_id, status, len(variants), count)


# Tunables for the auto-retry gate. If a variant's pHash bypass_count is
# below MIN_BYPASS_COUNT, regenerate with a fresh seed; after RETRY_BUMP_AT
# failures we escalate to the next preset strength.
MIN_BYPASS_COUNT = 2       # require ≥2/4 algos to beat threshold (realistic)
MAX_RETRIES = 2            # per variant (don't burn CPU chasing 4/4)
RETRY_BUMP_AT = 1          # after this many fails, bump preset to stronger
PRESET_ORDER = ['light', 'medium', 'strong']


def _generate_one_with_retry(src, ext, preset, job_id, allow_mirror=True):
    """Generate a single variant, regenerating with new seed if the 4-hash
    check is too weak. Escalates preset strength if the same preset keeps
    failing. Always returns SOMETHING (the best attempt) so the batch
    completes — caller marks it 'partial' if necessary via stats."""
    attempts = []
    cur_preset = preset
    variants_dir = get_variants_dir()
    for attempt in range(MAX_RETRIES + 1):
        seed = int.from_bytes(os.urandom(4), 'little')
        vname = f"spoof_{uuid.uuid4().hex[:10]}__{cur_preset}{ext}"
        vpath = os.path.join(variants_dir, vname)
        stats = spoof_one(src, vpath, preset=cur_preset, seed=seed,
                          allow_mirror=allow_mirror)
        attempts.append({'attempt': attempt + 1, 'preset': cur_preset,
                         'bypass_count': (stats.get('hash_compare') or {}).get('bypass_count', 0),
                         'seed': seed, 'vpath': vpath})

        bypass = (stats.get('hash_compare') or {}).get('bypass_count', 0)
        if bypass >= MIN_BYPASS_COUNT:
            stats['retry_attempts'] = attempts
            _save_variant_row(src, vpath, cur_preset, seed, job_id, stats)
            return {'variant_path': vpath, 'filename': vname,
                    'seed': seed, 'stats': stats}

        # Failed → delete the weak variant before next attempt
        try: os.remove(vpath)
        except Exception: pass

        # Bump preset after RETRY_BUMP_AT failures
        if attempt + 1 == RETRY_BUMP_AT:
            try:
                idx = PRESET_ORDER.index(cur_preset)
                if idx < len(PRESET_ORDER) - 1:
                    cur_preset = PRESET_ORDER[idx + 1]
            except ValueError:
                pass

    # All retries failed — keep the LAST attempt as best-effort.
    last = attempts[-1]
    seed = last['seed']; vpath = last['vpath']
    vname = os.path.basename(vpath)
    stats = spoof_one(src, vpath, preset=last['preset'], seed=seed,
                      allow_mirror=allow_mirror)
    stats['retry_attempts'] = attempts
    stats['retries_exhausted'] = True
    _save_variant_row(src, vpath, last['preset'], seed, job_id, stats)
    return {'variant_path': vpath, 'filename': vname,
            'seed': seed, 'stats': stats}


def _save_variant_row(src, vpath, preset, seed, job_id, stats):
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO media_variants "
            "(source_path, variant_path, preset, seed, job_id, stats_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (src, vpath, preset, seed, job_id,
             json.dumps(stats), datetime.utcnow().isoformat()))
        conn.commit()
    finally:
        conn.close()


def _bump_progress(job_id, n_done, variants):
    conn = _conn()
    try:
        conn.execute(
            "UPDATE spoof_jobs SET progress=?, variants_json=?, updated_at=? "
            "WHERE id=?",
            (n_done, json.dumps(variants), datetime.utcnow().isoformat(), job_id))
        conn.commit()
    finally:
        conn.close()


def _finish_job(job_id, status, error=None):
    conn = _conn()
    try:
        now = datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE spoof_jobs SET status=?, error_message=?, "
            "updated_at=?, completed_at=? WHERE id=?",
            (status, error, now, now, job_id))
        conn.commit()
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────
# UI page
# ─────────────────────────────────────────────────────────────────

@spoofing_bp.route('/spoofing')
def page_spoofing():
    _init_db()
    _start_worker_once()
    return render_template('spoofing.html', presets=list(PRESETS.keys()))


# ─────────────────────────────────────────────────────────────────
# API endpoints
# ─────────────────────────────────────────────────────────────────

@spoofing_bp.route('/api/spoof/upload', methods=['POST'])
def api_upload():
    """Accept a file upload; save under spoof_sources/. Returns path."""
    _init_db()
    if 'file' not in request.files:
        return jsonify({'error': 'no file'}), 400
    f = request.files['file']
    if not f or not f.filename:
        return jsonify({'error': 'empty filename'}), 400

    name = secure_filename(f.filename)
    ext = os.path.splitext(name)[1].lower()
    if ext not in (IMAGE_EXTS | VIDEO_EXTS):
        return jsonify({'error': 'unsupported file type: ' + ext}), 400

    uniq = f"src_{uuid.uuid4().hex[:8]}_{name}"
    dst = os.path.join(get_sources_dir(), uniq)
    f.save(dst)
    size = os.path.getsize(dst)
    kind = 'video' if is_video(dst) else 'image'
    return jsonify({
        'path': dst,
        'filename': uniq,
        'size_bytes': size,
        'kind': kind,
    })


@spoofing_bp.route('/api/spoof/job', methods=['POST'])
def api_create_job():
    """Enqueue an async spoofing job."""
    _init_db()
    _start_worker_once()
    data = request.get_json() or {}
    src = data.get('source_path', '').strip()
    preset = data.get('preset', 'medium')
    count = int(data.get('count', 1))
    allow_mirror = bool(data.get('allow_mirror', True))
    if not src or not os.path.exists(src):
        return jsonify({'error': 'source_path missing or not found'}), 400
    if preset not in PRESETS:
        return jsonify({'error': 'preset must be one of: ' + ', '.join(PRESETS)}), 400
    if count < 1 or count > 50:
        return jsonify({'error': 'count must be 1..50'}), 400

    conn = _conn()
    try:
        now = datetime.utcnow().isoformat()
        cur = conn.execute(
            "INSERT INTO spoof_jobs "
            "(source_path, preset, count, allow_mirror, status, progress, "
            " created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'queued', 0, ?, ?)",
            (src, preset, count, 1 if allow_mirror else 0, now, now))
        conn.commit()
        job_id = cur.lastrowid
    finally:
        conn.close()

    return jsonify({'job_id': job_id, 'status': 'queued',
                    'source_path': src, 'preset': preset, 'count': count,
                    'allow_mirror': allow_mirror}), 201


@spoofing_bp.route('/api/spoof/job/<int:job_id>')
def api_job_status(job_id):
    """Poll job status. Returns row + parsed variants_json."""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM spoof_jobs WHERE id=?", (job_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({'error': 'job not found'}), 404
    d = dict(row)
    try:
        d['variants'] = json.loads(d.pop('variants_json') or '[]')
    except Exception:
        d['variants'] = []
    return jsonify(d)


@spoofing_bp.route('/api/spoof/quick', methods=['POST'])
def api_quick():
    """Synchronous variant generation for small batches (count <= 4).
    Returns the variants directly. Used by UI for the instant preview."""
    _init_db()
    data = request.get_json() or {}
    src = data.get('source_path', '').strip()
    preset = data.get('preset', 'medium')
    count = int(data.get('count', 1))
    allow_mirror = bool(data.get('allow_mirror', True))
    if not src or not os.path.exists(src):
        return jsonify({'error': 'source_path missing or not found'}), 400
    if preset not in PRESETS:
        return jsonify({'error': 'unknown preset'}), 400
    if count < 1 or count > 4:
        return jsonify({'error': 'quick supports 1..4; use /job for more'}), 400

    ext = os.path.splitext(src)[1].lower() or '.bin'
    variants = []
    errors = []
    for _ in range(count):
        try:
            v_data = _generate_one_with_retry(src, ext, preset, None,
                                              allow_mirror=allow_mirror)
            variants.append(v_data)
        except Exception as e:
            log.error("spoof quick error: %s", e, exc_info=True)
            errors.append(str(e))
    return jsonify({'variants': variants, 'errors': errors,
                    'count': len(variants)})


@spoofing_bp.route('/api/spoof/variants')
def api_list_variants():
    """List existing variants for a source path."""
    src = request.args.get('source', '').strip()
    if not src:
        return jsonify({'error': 'source required'}), 400
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT id, variant_path, preset, seed, claimed_by_account_id, "
            "       claimed_at, created_at "
            "FROM media_variants WHERE source_path = ? "
            "ORDER BY id DESC", (src,)
        ).fetchall()
    finally:
        conn.close()
    return jsonify({'source_path': src,
                    'variants': [dict(r) for r in rows]})


@spoofing_bp.route('/api/spoof/file')
def api_serve_file():
    """Stream a file from spoof_sources/ or spoof_variants/. Path-guarded so
    we never serve anything outside those two dirs."""
    p = request.args.get('path', '').strip()
    if not p:
        return jsonify({'error': 'path required'}), 400
    p_abs = os.path.abspath(p)
    if not (p_abs.startswith(os.path.abspath(get_sources_dir())) or
            p_abs.startswith(os.path.abspath(get_variants_dir()))):
        return jsonify({'error': 'forbidden path'}), 403
    if not os.path.exists(p_abs):
        return jsonify({'error': 'file not found'}), 404
    return send_file(p_abs)


@spoofing_bp.route('/api/spoof/presets')
def api_presets():
    """Return the preset config so the UI can show parameter ranges."""
    return jsonify({'presets': PRESETS,
                    'image_exts': sorted(IMAGE_EXTS),
                    'video_exts': sorted(VIDEO_EXTS)})
