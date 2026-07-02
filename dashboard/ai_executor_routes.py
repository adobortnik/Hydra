"""
AI Executor — Hydra blueprint. Live view + run control for the hybrid AI
automation engine (automation/ai_executor). Phase 0 of Account Factory.

Routes:
  GET  /ai-executor                      -> the live page
  GET  /api/ai-executor/devices          -> device list
  GET  /api/ai-executor/live-shot/<s>    -> one-off screenshot (preview)
  POST /api/ai-executor/run              -> start a run, returns run_id
  GET  /api/ai-executor/status/<run_id>  -> steps + latest screenshot + result
  POST /api/ai-executor/stop/<run_id>    -> request stop
"""

import base64
import json
import os
import sys
import threading
import time
import uuid

from flask import Blueprint, jsonify, render_template, request

ai_executor_bp = Blueprint('ai_executor', __name__)

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)  # so `import automation.ai_executor` resolves

# in-memory run registry: run_id -> state
_runs = {}
_runs_lock = threading.Lock()


def _deepseek_key():
    try:
        with open(os.path.join(_BASE, 'dashboard', 'global_settings.json'), encoding='utf-8') as f:
            d = json.load(f)
        chat = d.get('ai_chat', {})
        if chat.get('provider') == 'deepseek' and chat.get('api_key'):
            return chat['api_key'], chat.get('model') or 'deepseek-chat'
        ai = d.get('ai', {})
        return ai.get('deepseek_api_key', ''), 'deepseek-chat'
    except Exception:
        return '', 'deepseek-chat'


def _clones(db_serial):
    """All clone packages on a device, ordered (same order as the UI list):
    index 0 = clone 1 (androie), ... So 'clone 6' = _clones()[5]."""
    import sqlite3
    c = sqlite3.connect(os.path.join(_BASE, 'db', 'phone_farm.db'))
    rows = c.execute("SELECT instagram_package FROM accounts WHERE device_serial=? "
                     "AND instagram_package IS NOT NULL ORDER BY instagram_package",
                     (db_serial,)).fetchall()
    c.close()
    return [r[0] for r in rows]


def _resolve_clone_from_goal(db_serial, goal):
    """Map an Nth-clone reference in the goal to that clone's package, so the user
    can just write it and we open the right app deterministically (no dropdown,
    no fragile launcher-icon guessing by the AI).

    Catches: 'clone 6', 'klon 6', 'instagram 6', 'insta 6', 'ig 6' (also '#6').
    'instagram clone 6' matches the 'clone 6' branch -> still N=6. Plain
    'open instagram' (no number) returns None -> AI navigates from home."""
    import re
    m = re.search(r'\b(?:clone|klon|instagram|insta|ig)\s*#?\s*(\d+)\b',
                  goal or '', re.I)
    if not m:
        return None
    n = int(m.group(1))
    clones = _clones(db_serial)
    if 1 <= n <= len(clones):
        return clones[n - 1]
    return None


@ai_executor_bp.route('/ai-executor')
def ai_executor_page():
    return render_template('ai_executor.html')


@ai_executor_bp.route('/api/ai-executor/devices')
def ai_devices():
    import sqlite3
    c = sqlite3.connect(os.path.join(_BASE, 'db', 'phone_farm.db'))
    c.row_factory = sqlite3.Row
    rows = c.execute("""SELECT d.device_serial, d.device_name,
                               COUNT(a.id) AS accounts
                        FROM devices d
                        LEFT JOIN accounts a ON a.device_serial=d.device_serial
                        GROUP BY d.device_serial ORDER BY d.device_name""").fetchall()
    c.close()
    return jsonify({'devices': [dict(r) for r in rows]})


@ai_executor_bp.route('/api/ai-executor/accounts/<path:serial>')
def ai_accounts(serial):
    """Accounts (username + clone package) on a device, so the UI can offer an
    unambiguous clone picker instead of guessing 'clone N'."""
    import sqlite3
    db = serial.replace(':', '_')
    c = sqlite3.connect(os.path.join(_BASE, 'db', 'phone_farm.db'))
    c.row_factory = sqlite3.Row
    rows = c.execute("SELECT username, instagram_package, status FROM accounts "
                     "WHERE device_serial=? AND instagram_package IS NOT NULL "
                     "ORDER BY instagram_package", (db,)).fetchall()
    c.close()
    return jsonify({'accounts': [dict(r) for r in rows]})


@ai_executor_bp.route('/api/ai-executor/stream/<path:serial>')
def live_stream(serial):
    """Continuous MJPEG stream of the device screen (~5 fps) so the operator
    sees real motion, not a 1.5s snapshot. <img src> consumes it directly.
    For true scrcpy-smooth (30fps H.264) we'd integrate ws-scrcpy later."""
    import io
    import uiautomator2 as u2
    from flask import Response
    from automation.ai_executor.perception import grab_png
    try:
        from PIL import Image
    except Exception:
        Image = None

    adb = serial.replace('_', ':')

    def gen():
        try:
            d = u2.connect(adb)
        except Exception:
            return
        boundary = b'--frame'
        while True:
            t0 = time.time()
            png = grab_png(d)
            if png:
                frame = png
                ctype = b'image/png'
                if Image is not None:
                    try:
                        im = Image.open(io.BytesIO(png)).convert('RGB')
                        if im.width > 540:
                            im = im.resize((540, int(im.height * 540 / im.width)))
                        buf = io.BytesIO(); im.save(buf, format='JPEG', quality=68)
                        frame = buf.getvalue(); ctype = b'image/jpeg'
                    except Exception:
                        pass
                yield (boundary + b'\r\nContent-Type: ' + ctype + b'\r\n'
                       b'Content-Length: ' + str(len(frame)).encode() + b'\r\n\r\n'
                       + frame + b'\r\n')
            dt = time.time() - t0
            time.sleep(max(0.0, 0.2 - dt))   # ~5 fps cap

    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')


@ai_executor_bp.route('/api/ai-executor/live-shot/<path:serial>')
def live_shot(serial):
    """One-off screenshot for the preview pane (does not stop the engine)."""
    try:
        import uiautomator2 as u2
        from automation.ai_executor.perception import grab_png
        d = u2.connect(serial.replace('_', ':'))
        shot = grab_png(d)
        if not shot:
            return jsonify({'ok': False, 'error': 'screenshot failed'}), 500
        return jsonify({'ok': True, 'png_b64': base64.b64encode(shot).decode()})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


def _run_worker(run_id, serial, package, goal, max_steps, stop_engine,
                recipe_id=None, record=False, model=None, variables=None):
    import uiautomator2 as u2
    from automation.ai_executor import (Executor, LLM, load_recipe,
                                        bump_recipe_stats, update_recipe_steps)

    st = _runs[run_id]
    adb_serial = serial.replace('_', ':')
    db_serial = serial.replace(':', '_')

    def emit(ev):
        png = ev.pop('screenshot', None)
        with _runs_lock:
            if png:
                st['shot'] = base64.b64encode(png).decode()
            st['steps'].append({k: ev.get(k) for k in
                                ('step', 'action', 'index', 'text', 'reason',
                                 'changed', 'note', 'src')})

    # 1) stop the device engine so it doesn't fight us
    killed = False
    if stop_engine:
        try:
            from bot_launcher_routes import _find_process_for_serial, _kill_pid
            procs = _find_process_for_serial(db_serial, use_cache=False)
            killed = len(procs) > 0
            for p in procs:
                _kill_pid(p['pid'])
            if killed:
                time.sleep(4)
        except Exception as e:
            emit({'step': 0, 'action': 'engine', 'reason': f'engine stop failed: {e}', 'changed': False})

    try:
        d = u2.connect(adb_serial)
        key, _cfg_model = _deepseek_key()
        if not key:
            with _runs_lock:
                st['result'] = {'success': False, 'reason': 'no DeepSeek key in global_settings.ai_chat'}
                st['running'] = False
            return
        # Executor model: explicit run choice > 'deepseek-v4-flash' default
        # (flash is fast & fits this many-small-steps agent; pro = optional,
        # slower reasoning for tricky flows / recording).
        use_model = model or 'deepseek-v4-flash'
        with _runs_lock:
            st['model'] = use_model
        llm = LLM(provider='deepseek', api_key=key, model=use_model)
        recipe = load_recipe(recipe_id) if recipe_id else None
        # optional phone verification (TextVerified) — None if not configured
        phone_client, phone_service = None, None
        try:
            from automation.ai_executor.textverified import from_settings
            phone_client = from_settings()
            gl = (goal or '').lower()
            phone_service = 'google' if ('gmail' in gl or 'google' in gl) else 'instagram'
        except Exception:
            phone_client = None
        ex = Executor(d, package=package, llm=llm, max_steps=max_steps,
                      on_step=emit, stop_flag=lambda: st.get('stop'),
                      recipe=recipe, record=(record or recipe is None),
                      phone_client=phone_client, phone_service=phone_service)
        result = ex.run(goal, variables=variables)
        recorded = result.get('recorded_steps') or []
        with _runs_lock:
            st['result'] = {k: v for k, v in result.items()
                            if k not in ('log', 'recorded_steps')}
            st['recorded_steps'] = recorded
        # if this was a successful GMAIL creation, save the account to the
        # Account Factory Gmail pool (with its password) so it's visible + reusable
        try:
            gl2 = (goal or '').lower()
            if (result.get('success') and variables and variables.get('email_local')
                    and ('gmail' in gl2 or 'google' in gl2)):
                import re as _re
                # the registered address may be a Google SUGGESTION, not our
                # email_local — scan the recorded steps for the real @gmail.com
                actual = variables['email_local'] + '@gmail.com'
                for stp in recorded:
                    a = stp.get('action') or {}
                    blob = ((a.get('target') or {}).get('label', '') or '') + ' ' + str(a.get('text', ''))
                    m = _re.search(r'([A-Za-z0-9._%+\-]+@gmail\.com)', blob)
                    if m:
                        actual = m.group(1)
                from account_factory_routes import _persist_gmail
                _persist_gmail(email=actual, password=variables.get('password', ''),
                               device_serial=db_serial, linked_ig='', status='active',
                               full_name=variables.get('full_name', ''))
                print('[ai-executor] saved Gmail to pool:', actual)
        except Exception as e:
            print('[ai-executor] gmail pool save failed:', e)
        # recipe bookkeeping: stats + self-heal (learn screens seen this run)
        if recipe_id:
            try:
                bump_recipe_stats(recipe_id, bool(result.get('success')))
                if recipe and result.get('success'):
                    known = set(recipe.sig_map.keys())
                    new = [s for s in recorded
                           if s.get('sig') and s['sig'] not in known and s.get('llm')]
                    if new:
                        update_recipe_steps(recipe_id, recipe.steps + new)
            except Exception as e:
                print('[ai-executor] recipe bookkeeping failed:', e)
    except Exception as e:
        import traceback
        with _runs_lock:
            st['result'] = {'success': False, 'reason': str(e)}
        print('[ai-executor]', traceback.format_exc())
    finally:
        # 2) restart the engine if we stopped it
        if killed:
            try:
                from bot_launcher_routes import _launch_device
                _launch_device(db_serial)
            except Exception:
                pass
        with _runs_lock:
            st['running'] = False
            st['engine_restarted'] = killed


def _serial_busy(serial):
    with _runs_lock:
        return any(st.get('running') and st.get('serial') == serial
                   for st in _runs.values())


def _spawn_run(serial, goal, package, max_steps=25, stop_engine=True,
               recipe_id=None, record=False, model=None, variables=None):
    """Start an executor run in a background thread. Returns run_id."""
    run_id = uuid.uuid4().hex[:10]
    with _runs_lock:
        _runs[run_id] = {'running': True, 'stop': False, 'steps': [],
                         'shot': None, 'result': None, 'serial': serial,
                         'goal': goal, 'package': package, 'recipe_id': recipe_id,
                         'model': model, 'variables': variables}
    t = threading.Thread(target=_run_worker,
                         args=(run_id, serial, package, goal, max_steps,
                               stop_engine, recipe_id, record, model, variables),
                         daemon=True)
    t.start()
    return run_id


@ai_executor_bp.route('/api/ai-executor/run', methods=['POST'])
def start_run():
    data = request.get_json() or {}
    serial = (data.get('serial') or '').strip()
    goal = (data.get('goal') or '').strip()
    recipe_id = data.get('recipe_id')
    record = bool(data.get('record', False))

    # If replaying a recipe, the goal/package can come from the recipe.
    if recipe_id and (not goal or not (data.get('package') or '').strip()):
        try:
            from automation.ai_executor import load_recipe
            rc = load_recipe(int(recipe_id))
            if rc:
                goal = goal or rc.goal
                if not (data.get('package') or '').strip() and rc.app_package:
                    data = dict(data); data['package'] = rc.app_package
        except Exception:
            pass

    if not serial or not goal:
        return jsonify({'error': 'serial and goal are required'}), 400
    # Package: explicit choice wins; else read "clone N" from the goal (so
    # "open clone 6" -> androij); else None -> executor starts from home.
    package = (data.get('package') or '').strip() or None
    if not package:
        package = _resolve_clone_from_goal(serial.replace(':', '_'), goal)
    max_steps = int(data.get('max_steps') or 25)
    stop_engine = bool(data.get('stop_engine', True))
    model = (data.get('model') or '').strip() or None
    variables = data.get('variables') or None   # {name/username/password/...}

    run_id = _spawn_run(serial, goal, package, max_steps, stop_engine,
                        recipe_id=int(recipe_id) if recipe_id else None,
                        record=record, model=model, variables=variables)
    return jsonify({'run_id': run_id, 'package': package})


@ai_executor_bp.route('/api/ai-executor/status/<run_id>')
def run_status(run_id):
    with _runs_lock:
        st = _runs.get(run_id)
        if not st:
            return jsonify({'error': 'unknown run'}), 404
        return jsonify({
            'running': st['running'], 'result': st['result'],
            'steps': st['steps'], 'shot': st['shot'],
            'serial': st['serial'], 'goal': st['goal'], 'package': st['package'],
            'engine_restarted': st.get('engine_restarted'),
            'recipe_id': st.get('recipe_id'),
            'savable': bool(st.get('recorded_steps')) and not st['running'],
        })


@ai_executor_bp.route('/api/ai-executor/stop/<run_id>', methods=['POST'])
def stop_run(run_id):
    with _runs_lock:
        st = _runs.get(run_id)
        if st:
            st['stop'] = True
    return jsonify({'ok': True})


# ════════════════════════════════════════════════════════════════════════
#  RECIPES — save a learned run, list, run (replay), delete
# ════════════════════════════════════════════════════════════════════════

@ai_executor_bp.route('/api/ai-executor/identity', methods=['POST'])
def gen_identity():
    """Generate account identity data (name/username/password/birthday) used as
    {variables} when recording/replaying a creation recipe. Body (all optional):
    {naming_base, theme, gender, username, count} — count>1 returns a batch
    (for a mother's slaves with a naming scheme)."""
    from automation.ai_executor import generate_identity, generate_batch
    d = request.get_json() or {}
    count = int(d.get('count') or 1)
    base = (d.get('naming_base') or '').strip() or None
    if count > 1 and base:
        return jsonify({'identities': generate_batch(base, min(count, 50),
                                                     themes=d.get('themes'))})
    ident = generate_identity(naming_base=base, theme=d.get('theme'),
                              gender=d.get('gender'),
                              username=(d.get('username') or '').strip() or None)
    return jsonify({'identity': ident})


@ai_executor_bp.route('/api/ai-executor/recipes', methods=['GET'])
def recipes_list():
    from automation.ai_executor import list_recipes
    return jsonify({'recipes': list_recipes()})


@ai_executor_bp.route('/api/ai-executor/recipes', methods=['POST'])
def recipes_save():
    """Save a finished run's learned steps as a reusable recipe."""
    from automation.ai_executor import save_recipe
    data = request.get_json() or {}
    run_id = data.get('run_id')
    name = (data.get('name') or '').strip()
    if not run_id or not name:
        return jsonify({'error': 'run_id and name are required'}), 400
    with _runs_lock:
        st = _runs.get(run_id)
        if not st:
            return jsonify({'error': 'unknown run'}), 404
        steps = st.get('recorded_steps') or []
        goal = st.get('goal')
        package = st.get('package')
    if not steps:
        return jsonify({'error': 'this run captured no steps to save'}), 400
    rid = save_recipe(name, goal, package, steps)
    return jsonify({'ok': True, 'recipe_id': rid,
                    'screens': len({s.get('sig') for s in steps if s.get('sig')})})


@ai_executor_bp.route('/api/ai-executor/recipes/<int:rid>', methods=['GET'])
def recipe_detail(rid):
    """Full recipe contents (ordered steps) for the view modal."""
    from automation.ai_executor import load_recipe
    rc = load_recipe(rid)
    if not rc:
        return jsonify({'error': 'unknown recipe'}), 404
    return jsonify({'id': rc.id, 'name': rc.name, 'goal': rc.goal,
                    'app_package': rc.app_package, 'screens': rc.coverage(),
                    'run_count': rc.run_count, 'success_count': rc.success_count,
                    'steps': rc.steps})


@ai_executor_bp.route('/api/ai-executor/recipes/<int:rid>', methods=['DELETE'])
def recipes_delete(rid):
    from automation.ai_executor import delete_recipe
    delete_recipe(rid)
    return jsonify({'ok': True})


@ai_executor_bp.route('/api/ai-executor/recipes/<int:rid>/run', methods=['POST'])
def recipes_run(rid):
    """Replay a recipe on a device now (AI fills any gaps)."""
    from automation.ai_executor import load_recipe
    data = request.get_json() or {}
    serial = (data.get('serial') or '').strip()
    rc = load_recipe(rid)
    if not rc:
        return jsonify({'error': 'unknown recipe'}), 404
    if not serial:
        return jsonify({'error': 'serial is required'}), 400
    package = (data.get('package') or '').strip() or rc.app_package
    if not package:
        package = _resolve_clone_from_goal(serial.replace(':', '_'), rc.goal or '')
    max_steps = int(data.get('max_steps') or 40)
    model = (data.get('model') or '').strip() or None
    variables = data.get('variables') or None
    run_id = _spawn_run(serial, rc.goal or '', package, max_steps,
                        stop_engine=bool(data.get('stop_engine', True)),
                        recipe_id=rid, record=False, model=model,
                        variables=variables)
    return jsonify({'run_id': run_id, 'package': package})


# ════════════════════════════════════════════════════════════════════════
#  SCHEDULES — cron-like recurring recipe runs
# ════════════════════════════════════════════════════════════════════════

def _compute_next_run(mode, interval_minutes, daily_time, jitter_minutes, now):
    """Return epoch seconds of the next run. Jitter avoids identical timing
    (anti-detection). Caller seeds randomness per-call."""
    import random as _r
    jitter = _r.randint(0, max(0, int(jitter_minutes or 0))) * 60
    if mode == 'interval':
        return int(now + max(1, int(interval_minutes or 10)) * 60 + jitter)
    if mode == 'daily':
        # next occurrence of HH:MM (local), today if still ahead else tomorrow
        import datetime as _dt
        try:
            hh, mm = [int(x) for x in (daily_time or '09:00').split(':')]
        except Exception:
            hh, mm = 9, 0
        base = _dt.datetime.fromtimestamp(now)
        cand = base.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if cand.timestamp() <= now:
            cand = cand + _dt.timedelta(days=1)
        return int(cand.timestamp() + jitter)
    return None  # 'once' -> no next run


@ai_executor_bp.route('/api/ai-executor/schedules', methods=['GET'])
def schedules_list():
    import sqlite3
    from automation.ai_executor import ensure_tables
    ensure_tables()
    c = sqlite3.connect(os.path.join(_BASE, 'db', 'phone_farm.db'))
    c.row_factory = sqlite3.Row
    rows = c.execute("""SELECT s.*, r.name AS recipe_name
                        FROM ai_schedules s LEFT JOIN ai_recipes r ON r.id=s.recipe_id
                        ORDER BY s.enabled DESC, s.next_run_at ASC""").fetchall()
    c.close()
    return jsonify({'schedules': [dict(r) for r in rows]})


@ai_executor_bp.route('/api/ai-executor/schedules', methods=['POST'])
def schedules_create():
    import sqlite3
    import time as _t
    from automation.ai_executor import ensure_tables
    data = request.get_json() or {}
    recipe_id = data.get('recipe_id')
    serial = (data.get('device_serial') or '').strip()
    mode = (data.get('mode') or 'interval').strip()
    if not recipe_id or not serial:
        return jsonify({'error': 'recipe_id and device_serial are required'}), 400
    if mode not in ('interval', 'daily', 'once'):
        return jsonify({'error': 'mode must be interval|daily|once'}), 400
    interval_minutes = int(data.get('interval_minutes') or 0) or None
    daily_time = (data.get('daily_time') or '').strip() or None
    jitter = int(data.get('jitter_minutes', 5))
    package = (data.get('package') or '').strip() or None
    name = (data.get('name') or '').strip() or None
    now = _t.time()
    if mode == 'once':
        next_run = int(data.get('run_at') or (now + 60))
    else:
        next_run = _compute_next_run(mode, interval_minutes, daily_time, jitter, now)
    ensure_tables()
    c = sqlite3.connect(os.path.join(_BASE, 'db', 'phone_farm.db'))
    cur = c.execute("""INSERT INTO ai_schedules
        (recipe_id, name, device_serial, package, mode, interval_minutes,
         daily_time, jitter_minutes, next_run_at, enabled, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,1,?)""",
        (recipe_id, name, serial, package, mode, interval_minutes, daily_time,
         jitter, next_run, int(now)))
    sid = cur.lastrowid
    c.commit()
    c.close()
    return jsonify({'ok': True, 'schedule_id': sid, 'next_run_at': next_run})


@ai_executor_bp.route('/api/ai-executor/schedules/<int:sid>', methods=['DELETE'])
def schedules_delete(sid):
    import sqlite3
    c = sqlite3.connect(os.path.join(_BASE, 'db', 'phone_farm.db'))
    c.execute("DELETE FROM ai_schedules WHERE id=?", (sid,))
    c.commit()
    c.close()
    return jsonify({'ok': True})


@ai_executor_bp.route('/api/ai-executor/schedules/<int:sid>/toggle', methods=['POST'])
def schedules_toggle(sid):
    import sqlite3
    c = sqlite3.connect(os.path.join(_BASE, 'db', 'phone_farm.db'))
    c.execute("UPDATE ai_schedules SET enabled = 1 - enabled WHERE id=?", (sid,))
    c.commit()
    row = c.execute("SELECT enabled FROM ai_schedules WHERE id=?", (sid,)).fetchone()
    c.close()
    return jsonify({'ok': True, 'enabled': bool(row[0]) if row else None})


# ── background scheduler: fire due schedules ──
_scheduler_started = False


def _scheduler_loop():
    import sqlite3
    import time as _t
    db = os.path.join(_BASE, 'db', 'phone_farm.db')
    while True:
        try:
            now = _t.time()
            c = sqlite3.connect(db)
            c.row_factory = sqlite3.Row
            due = c.execute("SELECT * FROM ai_schedules WHERE enabled=1 AND "
                            "next_run_at IS NOT NULL AND next_run_at <= ?",
                            (now,)).fetchall()
            c.close()
            for s in due:
                serial = s['device_serial']
                if _serial_busy(serial):
                    continue   # don't pile runs on a busy device; catch it next tick
                try:
                    _spawn_run(serial, '', s['package'], max_steps=40,
                               stop_engine=True, recipe_id=s['recipe_id'],
                               record=False)
                    status = 'started'
                except Exception as e:
                    status = f'error: {e}'
                # schedule the next occurrence (or disable a 'once')
                nxt = _compute_next_run(s['mode'], s['interval_minutes'],
                                        s['daily_time'], s['jitter_minutes'], now)
                c2 = sqlite3.connect(db)
                if s['mode'] == 'once':
                    c2.execute("UPDATE ai_schedules SET enabled=0, last_run_at=?, "
                               "last_status=?, next_run_at=NULL WHERE id=?",
                               (int(now), status, s['id']))
                else:
                    c2.execute("UPDATE ai_schedules SET last_run_at=?, "
                               "last_status=?, next_run_at=? WHERE id=?",
                               (int(now), status, nxt, s['id']))
                c2.commit()
                c2.close()
        except Exception as e:
            print('[ai-executor] scheduler tick error:', e)
        _t.sleep(30)


def _start_scheduler():
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    try:
        from automation.ai_executor import ensure_tables
        ensure_tables()
    except Exception:
        pass
    threading.Thread(target=_scheduler_loop, daemon=True).start()


_start_scheduler()
