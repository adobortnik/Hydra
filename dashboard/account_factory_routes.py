"""
Account Factory — Hydra blueprint. The PRODUCTION orchestration UI on top of the
AI Executor recipes. Generate a batch of identities (mother + naming scheme),
pick a pipeline (chain of recipes: gmail-create -> ig-signup -> ...), and run it
per account on a device.

This layer ORCHESTRATES; the atomic steps are recorded/tested in /ai-executor.

Routes:
  GET  /account-factory                         -> the page
  GET  /api/account-factory/devices             -> device list
  GET  /api/account-factory/recipes             -> available recipes (pipeline steps)
  POST /api/account-factory/identities          -> generate a batch preview
  POST /api/account-factory/run                 -> start a pipeline job
  GET  /api/account-factory/status/<job_id>     -> job progress
  POST /api/account-factory/stop/<job_id>       -> request stop
  GET  /api/account-factory/accounts            -> created-accounts table
"""

import base64
import os
import sqlite3
import sys
import threading
import time
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request

account_factory_bp = Blueprint('account_factory', __name__)

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

_DB = os.path.join(_BASE, 'db', 'phone_farm.db')

_jobs = {}
_jobs_lock = threading.Lock()


def _ensure_accounts_table():
    c = sqlite3.connect(_DB)
    c.execute("""CREATE TABLE IF NOT EXISTS af_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id TEXT,
        device_serial TEXT,
        username TEXT,
        full_name TEXT,
        password TEXT,
        email TEXT,
        gender TEXT,
        birthday TEXT,
        status TEXT,
        recipe_chain TEXT,
        error TEXT,
        created_at INTEGER
    )""")
    c.commit()
    c.close()


def _ensure_gmail_table():
    c = sqlite3.connect(_DB)
    c.execute("""CREATE TABLE IF NOT EXISTS gmail_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password TEXT,
        full_name TEXT,
        recovery_email TEXT,
        recovery_phone TEXT,
        device_serial TEXT,
        ip TEXT,
        linked_ig TEXT,
        status TEXT,
        notes TEXT,
        created_at INTEGER,
        last_used INTEGER
    )""")
    # add columns if upgrading an older table
    for col in ('full_name TEXT', 'ip TEXT'):
        try:
            c.execute('ALTER TABLE gmail_accounts ADD COLUMN ' + col)
        except Exception:
            pass
    c.commit()
    c.close()


def _persist_gmail(email, password, device_serial, linked_ig='', status='active',
                   recovery_phone='', full_name='', ip='', now=None):
    """Save a created Gmail to the pool (one row per email, unique). Records WHERE
    it lives: device + ip + the account holder's name."""
    try:
        _ensure_gmail_table()
        ts = int(now if now is not None else time.time())
        if not ip and device_serial:   # derive LAN ip from the serial
            ip = device_serial.replace('_5555', '').replace('_', ':').split(':')[0]
        c = sqlite3.connect(_DB)
        c.execute("""INSERT OR IGNORE INTO gmail_accounts
            (email, password, full_name, recovery_phone, device_serial, ip,
             linked_ig, status, created_at, last_used)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (email, password, full_name, recovery_phone, device_serial, ip,
             linked_ig, status, ts, ts))
        c.commit()
        c.close()
    except Exception as e:
        print('[account-factory] gmail persist failed:', e)


def _persist_account(job_id, device_serial, ident, status, recipe_ids, error='', now=None):
    try:
        _ensure_accounts_table()
        ts = int(now if now is not None else time.time())
        c = sqlite3.connect(_DB)
        c.execute("""INSERT INTO af_accounts
            (job_id, device_serial, username, full_name, password, email, gender,
             birthday, status, recipe_chain, error, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (job_id, device_serial, ident.get('username'), ident.get('full_name'),
             ident.get('password'), (ident.get('email_local', '') + '@gmail.com'),
             ident.get('gender'),
             f"{ident.get('birth_day')} {ident.get('birth_month_name')} {ident.get('birth_year')}",
             status, ','.join(str(r) for r in recipe_ids), error, ts))
        c.commit()
        c.close()
    except Exception as e:
        print('[account-factory] persist failed:', e)


def _sync_account_to_accounts(device_serial, package, username, password, tag='',
                              is_mother=0, now=None):
    """Reconcile a factory-created account into the MAIN `accounts` table (the bot
    engine + capacity source of truth): mark any ACTIVE account currently on this
    clone slot as 'replaced', then upsert the new account as active. Returns the new
    account id. Used by both the reconcile fix and the batch-create worker."""
    ts = int(now if now is not None else time.time())
    c = sqlite3.connect(_DB)
    try:
        # device_id: inherit from any row on this device, else the devices table
        row = c.execute("SELECT device_id FROM accounts WHERE device_serial=? "
                        "AND device_id IS NOT NULL LIMIT 1", (device_serial,)).fetchone()
        device_id = row[0] if row else None
        if device_id is None:
            dr = c.execute("SELECT id FROM devices WHERE device_serial=?",
                           (device_serial,)).fetchone()
            device_id = dr[0] if dr else None
        # retire whatever ACTIVE account sat on this clone slot
        c.execute("UPDATE accounts SET status='replaced', updated_at=? "
                  "WHERE device_serial=? AND instagram_package=? AND status='active'",
                  (ts, device_serial, package))
        # upsert the new account (UNIQUE is on device_serial+username)
        existing = c.execute("SELECT id FROM accounts WHERE device_serial=? AND username=?",
                             (device_serial, username)).fetchone()
        if existing:
            c.execute("UPDATE accounts SET instagram_package=?, password=?, status='active', "
                      "tag=?, is_mother=?, updated_at=? WHERE id=?",
                      (package, password, tag, is_mother, ts, existing[0]))
            aid = existing[0]
        else:
            cur = c.execute(
                "INSERT INTO accounts (device_id, device_serial, username, password, "
                "instagram_package, status, tag, is_mother, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (device_id, device_serial, username, password, package, 'active',
                 tag, is_mother, ts, ts))
            aid = cur.lastrowid
        c.commit()
        return aid
    finally:
        c.close()


def _retire_and_resolve(account_id, new_username='', resolved_by='reregister', now=None):
    """When a re-registration succeeds on a banned/dead account's slot: mark that
    specific old account 'replaced' (clearing its time window) and resolve any open
    health events for it. Uses ISO timestamps to match the health-event convention."""
    iso = now or datetime.utcnow().isoformat()
    c = sqlite3.connect(_DB)
    try:
        c.execute("UPDATE accounts SET status='replaced', start_time='0', end_time='0', "
                  "updated_at=? WHERE id=?", (iso, account_id))
        c.execute("UPDATE account_health_events SET resolved_at=?, resolved_by=? "
                  "WHERE account_id=? AND resolved_at IS NULL",
                  (iso, resolved_by, account_id))
        c.commit()
    except Exception as e:
        print('[account-factory] retire/resolve failed:', e)
    finally:
        c.close()


@account_factory_bp.route('/account-factory')
def page():
    return render_template('account_factory.html')


@account_factory_bp.route('/api/account-factory/devices')
def devices():
    c = sqlite3.connect(_DB)
    c.row_factory = sqlite3.Row
    rows = c.execute("""SELECT d.device_serial, d.device_name,
                               COUNT(a.id) AS accounts
                        FROM devices d
                        LEFT JOIN accounts a ON a.device_serial=d.device_serial
                        GROUP BY d.device_serial ORDER BY d.device_name""").fetchall()
    c.close()
    return jsonify({'devices': [dict(r) for r in rows]})


@account_factory_bp.route('/api/account-factory/capacity')
def capacity():
    """Per-device clone SLOTS for the factory. Each IG clone = 1 slot. State:
      used  = has an ACTIVE account (don't touch)
      dead  = has a banned/disabled/logged_out account (re-registrable after NEW_IDENTITY)
      empty = clone installed but no account
    free = dead + empty (where batch-create can place new accounts). Installed clones
    are detected per device via adb `pm list packages com.instagram` (parallel, with a
    DB fallback if a device is offline)."""
    import subprocess
    from concurrent.futures import ThreadPoolExecutor

    c = sqlite3.connect(_DB)
    c.row_factory = sqlite3.Row
    devs = c.execute("SELECT device_serial, device_name FROM devices "
                     "ORDER BY device_name").fetchall()
    accts = c.execute("SELECT device_serial, instagram_package, username, status "
                      "FROM accounts WHERE instagram_package IS NOT NULL").fetchall()
    c.close()

    by_dev = {}
    for a in accts:
        by_dev.setdefault(a['device_serial'], {})[a['instagram_package']] = dict(a)

    def detect(serial_db):
        adb = serial_db.replace('_', ':')
        try:
            r = subprocess.run(['adb', '-s', adb, 'shell', 'pm', 'list', 'packages',
                                'com.instagram'], capture_output=True, timeout=12, text=True)
            pkgs = [ln.split(':', 1)[1].strip() for ln in (r.stdout or '').splitlines()
                    if ln.startswith('package:')]
            # exclude the BASE Instagram app — only AppCloner clones are factory slots
            pkgs = [p for p in pkgs if p != 'com.instagram.android']
            return serial_db, sorted(set(pkgs))
        except Exception:
            return serial_db, None

    detected = {}
    serials = [d['device_serial'] for d in devs]
    if serials:
        with ThreadPoolExecutor(max_workers=8) as ex:
            for sd, pkgs in ex.map(detect, serials):
                detected[sd] = pkgs

    out_devs, t_used, t_free = [], 0, 0
    for d in devs:
        sd = d['device_serial']
        amap = by_dev.get(sd, {})
        clones = detected.get(sd) or sorted(amap.keys())   # adb result, else DB fallback
        slots = []
        for i, pkg in enumerate(clones, 1):
            a = amap.get(pkg)
            st = (a['status'] or '').lower() if a else None
            state = 'used' if st == 'active' else ('dead' if a else 'empty')
            slots.append({'clone': i, 'package': pkg,
                          'username': a['username'] if a else None,
                          'status': a['status'] if a else None, 'state': state})
        used = sum(1 for s in slots if s['state'] == 'used')
        free = sum(1 for s in slots if s['state'] in ('empty', 'dead'))
        t_used += used
        t_free += free
        out_devs.append({'device_serial': sd, 'device_name': d['device_name'],
                         'total': len(slots), 'used': used, 'free': free,
                         'adb_ok': detected.get(sd) is not None, 'slots': slots})
    return jsonify({'devices': out_devs,
                    'totals': {'used': t_used, 'free': t_free,
                               'slots': t_used + t_free}})


def _free_slots_for_device(device_serial):
    """Free clone packages on one device = installed IG clones (adb) MINUS those with
    an ACTIVE account. Covers empty + dead/banned clones (re-registrable)."""
    import subprocess
    adb = device_serial.replace('_', ':')
    try:
        r = subprocess.run(['adb', '-s', adb, 'shell', 'pm', 'list', 'packages',
                            'com.instagram'], capture_output=True, timeout=12, text=True)
        clones = sorted(set(ln.split(':', 1)[1].strip() for ln in (r.stdout or '').splitlines()
                            if ln.startswith('package:')))
        clones = [p for p in clones if p != 'com.instagram.android']
    except Exception:
        clones = []
    if not clones:
        return []
    c = sqlite3.connect(_DB)
    active = {row[0] for row in c.execute(
        "SELECT instagram_package FROM accounts WHERE device_serial=? AND status='active' "
        "AND instagram_package IS NOT NULL", (device_serial,))}
    c.close()
    return [p for p in clones if p not in active]


def _allocate_free_slots(count, devices=None):
    """Pick `count` free slots, spread round-robin across devices for balance."""
    c = sqlite3.connect(_DB)
    devs = [r[0] for r in c.execute("SELECT device_serial FROM devices ORDER BY device_name")]
    c.close()
    if devices:
        devs = [d for d in devs if d in devices]
    pool = {d: _free_slots_for_device(d) for d in devs}
    out = []
    while len(out) < count and any(pool.values()):
        for d in devs:
            if pool[d]:
                out.append({'device_serial': d, 'package': pool[d].pop(0)})
                if len(out) >= count:
                    break
    return out


def _batch_worker(job_id):
    """Create accounts slot-by-slot: NEW_IDENTITY (AppCloner) -> run ig-signup recipe
    -> reconcile into the main accounts table (mother tag) + log to af_accounts."""
    import subprocess
    import uiautomator2 as u2
    from ai_executor_routes import _deepseek_key
    from automation.ai_executor import Executor, LLM, load_recipe
    job = _jobs[job_id]
    key, _ = _deepseek_key()
    if not key:
        with _jobs_lock:
            job['error'] = 'no DeepSeek key'; job['running'] = False
        return
    llm = LLM(provider='deepseek', api_key=key, model=job.get('model') or 'deepseek-v4-flash')
    phone = None
    try:
        from automation.ai_executor.textverified import from_settings as _tv
        phone = _tv()
    except Exception:
        phone = None
    rc = load_recipe(job['recipe_id'])
    if not rc:
        with _jobs_lock:
            job['error'] = 'recipe not found'; job['running'] = False
        return
    try:
        from bot_launcher_routes import _find_process_for_serial, _kill_pid, _launch_device
    except Exception:
        _find_process_for_serial = _kill_pid = _launch_device = None
    stopped = set()
    for acct in job['accounts']:
        if job.get('stop'):
            break
        ident = acct['identity']; dev = acct['device_serial']; pkg = acct['package']
        adb = dev.replace('_', ':')
        with _jobs_lock:
            acct['status'] = 'running'; acct['step'] = 'new identity'
        if _find_process_for_serial and dev not in stopped:
            try:
                for p in _find_process_for_serial(dev, use_cache=False):
                    _kill_pid(p['pid'])
                stopped.add(dev); time.sleep(3)
            except Exception:
                pass
        try:
            subprocess.run(['adb', '-s', adb, 'shell', 'am', 'broadcast', '-p',
                            'com.applisto.appcloner', '-a',
                            'com.applisto.appcloner.api.action.NEW_IDENTITY',
                            '--es', 'package_name', pkg, '--ez', 'clear_cache', 'true',
                            '--ez', 'delete_app_data', 'true'],
                           capture_output=True, timeout=15, text=True)
            time.sleep(3)
        except Exception as e:
            with _jobs_lock:
                acct['status'] = 'fail'; acct['error'] = f'new_identity failed: {e}'
            continue

        def emit(ev, _a=acct):
            png = ev.pop('screenshot', None)
            with _jobs_lock:
                if png:
                    job['shot'] = base64.b64encode(png).decode()
                _a['last'] = f"{ev.get('action')} {ev.get('reason') or ev.get('note') or ''}"[:80]

        with _jobs_lock:
            acct['step'] = 'signing up'
        try:
            d = u2.connect(adb)
            ex = Executor(d, package=pkg, llm=llm, max_steps=job.get('max_steps', 130),
                          recipe=rc, record=False, variables=ident, on_step=emit,
                          stop_flag=lambda: job.get('stop'), phone_client=phone,
                          phone_service='instagram', phone_mode='verification')
            res = ex.run(rc.goal or '', variables=ident)
        except Exception as e:
            res = {'success': False, 'reason': str(e)}
        if res.get('success'):
            try:
                _sync_account_to_accounts(dev, pkg, ident['username'],
                                          ident.get('password', ''), tag=job.get('tag', ''))
                _persist_account(job_id, dev, ident, 'active', [job['recipe_id']])
                # re-registration: retire the specific banned account + resolve its events
                rid = acct.get('replace_account_id')
                if rid:
                    _retire_and_resolve(rid, ident['username'])
            except Exception as e:
                print('[account-factory] sync failed:', e)
            with _jobs_lock:
                acct['status'] = 'done'; acct['username'] = ident['username']
        else:
            reason = (res.get('reason') or '').lower()
            attn = 'captcha' in reason or 'human' in reason
            with _jobs_lock:
                acct['status'] = 'needs_attention' if attn else 'fail'
                acct['error'] = res.get('reason', '')
    if _launch_device:
        for dev in stopped:
            try:
                _launch_device(dev)
            except Exception:
                pass
    with _jobs_lock:
        job['running'] = False


@account_factory_bp.route('/api/account-factory/batch', methods=['POST'])
def batch_start():
    """Start a batch: mother + tag + count -> allocate free slots (auto, or manual
    'slots' override) -> per slot NEW_IDENTITY + ig-signup recipe + accounts sync."""
    from automation.ai_executor import generate_batch
    d = request.get_json() or {}
    mother = (d.get('mother') or '').strip()
    naming_base = (d.get('naming_base') or mother or '').strip()
    tag = (d.get('tag') or mother or '').strip()
    count = int(d.get('count') or 0)
    recipe_id = d.get('recipe_id')
    if not naming_base or count < 1 or not recipe_id:
        return jsonify({'error': 'naming_base/count/recipe_id required'}), 400
    slots = d.get('slots') or _allocate_free_slots(count, devices=d.get('devices'))
    slots = slots[:count]
    if not slots:
        return jsonify({'error': 'no free slots available'}), 400
    idents = generate_batch(naming_base, len(slots))
    accounts = [{'identity': idents[i], 'device_serial': s['device_serial'],
                 'package': s['package'], 'status': 'queued'} for i, s in enumerate(slots)]
    job_id = uuid.uuid4().hex[:10]
    with _jobs_lock:
        _jobs[job_id] = {'running': True, 'stop': False, 'mother': mother, 'tag': tag,
                         'recipe_id': int(recipe_id), 'model': d.get('model'),
                         'max_steps': int(d.get('max_steps') or 130),
                         'accounts': accounts, 'shot': None}
    threading.Thread(target=_batch_worker, args=(job_id,), daemon=True).start()
    return jsonify({'job_id': job_id, 'allocated': len(slots), 'requested': count})


@account_factory_bp.route('/api/account-factory/batch/status/<job_id>')
def batch_status(job_id):
    with _jobs_lock:
        j = _jobs.get(job_id)
        if not j:
            return jsonify({'error': 'unknown job'}), 404
        return jsonify({
            'running': j['running'], 'mother': j.get('mother'), 'tag': j.get('tag'),
            'shot': j.get('shot'), 'error': j.get('error'),
            'accounts': [{
                'username': a.get('username') or a['identity'].get('username'),
                'device_serial': a['device_serial'], 'package': a['package'],
                'status': a['status'], 'step': a.get('step'),
                'replacing': a.get('replacing'),
                'last': a.get('last'), 'error': a.get('error')} for a in j['accounts']]})


@account_factory_bp.route('/api/account-factory/batch/stop/<job_id>', methods=['POST'])
def batch_stop(job_id):
    with _jobs_lock:
        j = _jobs.get(job_id)
        if j:
            j['stop'] = True
    return jsonify({'ok': True})


@account_factory_bp.route('/api/account-factory/reregister', methods=['POST'])
def reregister():
    """Replace ONE banned/dead account via a fresh signup (Account Health → Re-register).
    Reuses the batch worker on the old account's exact slot: NEW_IDENTITY + recipe ->
    new account synced in, the banned account retired + its health events resolved.
    Body: { account_id, recipe_id, mother?, naming_base?, tag?, model?, max_steps? }
    Inherits device/package/tag from the old account; uses OUR naming scheme."""
    from automation.ai_executor import generate_batch
    d = request.get_json() or {}
    account_id = d.get('account_id')
    recipe_id = d.get('recipe_id')
    if not account_id or not recipe_id:
        return jsonify({'error': 'account_id and recipe_id required'}), 400

    c = sqlite3.connect(_DB)
    c.row_factory = sqlite3.Row
    old = c.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    c.close()
    if not old:
        return jsonify({'error': 'account not found'}), 404
    old = dict(old)
    dev = old.get('device_serial')
    pkg = old.get('instagram_package')
    if not dev or not pkg:
        return jsonify({'error': 'account has no device/clone slot to re-register on'}), 400

    mother = (d.get('mother') or old.get('tag') or '').strip()
    naming_base = (d.get('naming_base') or mother or '').strip()
    tag = (d.get('tag') or old.get('tag') or mother or '').strip()
    if not naming_base:
        return jsonify({'error': 'naming_base/mother required'}), 400

    idents = generate_batch(naming_base, 1)
    accounts = [{'identity': idents[0], 'device_serial': dev, 'package': pkg,
                 'status': 'queued', 'replace_account_id': account_id,
                 'replacing': old.get('username')}]
    job_id = uuid.uuid4().hex[:10]
    with _jobs_lock:
        _jobs[job_id] = {'running': True, 'stop': False, 'mother': mother, 'tag': tag,
                         'recipe_id': int(recipe_id), 'model': d.get('model'),
                         'max_steps': int(d.get('max_steps') or 130),
                         'accounts': accounts, 'shot': None, 'kind': 'reregister'}
    threading.Thread(target=_batch_worker, args=(job_id,), daemon=True).start()
    return jsonify({'job_id': job_id, 'replacing': old.get('username'),
                    'new_username': idents[0].get('username'),
                    'device_serial': dev, 'package': pkg})


@account_factory_bp.route('/api/account-factory/recipes')
def recipes():
    from automation.ai_executor import list_recipes
    return jsonify({'recipes': list_recipes()})


@account_factory_bp.route('/api/account-factory/identities', methods=['POST'])
def identities():
    from automation.ai_executor import generate_batch, generate_identity
    d = request.get_json() or {}
    count = max(1, int(d.get('count') or 1))
    base = (d.get('naming_base') or '').strip() or None
    gender = d.get('gender') or None
    if count > 1:
        if not base:
            return jsonify({'error': 'naming_base required for a batch'}), 400
        out = generate_batch(base, min(count, 50), themes=d.get('themes'))
    else:
        out = [generate_identity(naming_base=base, gender=gender)]
    for i in out:
        i['email'] = i.get('email_local', i.get('username', '')) + '@gmail.com'
    return jsonify({'identities': out})


def _af_worker(job_id):
    import uiautomator2 as u2
    from ai_executor_routes import _deepseek_key
    from automation.ai_executor import Executor, LLM, load_recipe

    job = _jobs[job_id]
    db_serial = job['device_serial'].replace(':', '_')
    adb_serial = job['device_serial'].replace('_', ':')

    # stop the device engine ONCE for the whole batch
    killed = False
    try:
        from bot_launcher_routes import _find_process_for_serial, _kill_pid
        procs = _find_process_for_serial(db_serial, use_cache=False)
        killed = len(procs) > 0
        for p in procs:
            _kill_pid(p['pid'])
        if killed:
            time.sleep(4)
    except Exception as e:
        print('[account-factory] engine stop failed:', e)

    try:
        d = u2.connect(adb_serial)
        key, _ = _deepseek_key()
        if not key:
            with _jobs_lock:
                job['error'] = 'no DeepSeek key in global_settings.ai_chat'
                job['running'] = False
            return
        llm = LLM(provider='deepseek', api_key=key,
                  model=job.get('model') or 'deepseek-v4-flash')
        # optional phone verification provider (TextVerified)
        phone_client = None
        try:
            from automation.ai_executor.textverified import from_settings
            phone_client = from_settings()
        except Exception:
            phone_client = None
        recipes_chain = [r for r in (load_recipe(rid) for rid in job['recipe_ids']) if r]
        if not recipes_chain:
            with _jobs_lock:
                job['error'] = 'no valid recipes in the pipeline'
                job['running'] = False
            return

        for acct in job['accounts']:
            if job.get('stop'):
                break
            ident = acct['identity']
            with _jobs_lock:
                acct['status'] = 'running'
            ok_all = True
            for rc in recipes_chain:
                if job.get('stop'):
                    ok_all = False
                    break
                step = {'recipe': rc.name, 'status': 'running', 'reason': ''}
                with _jobs_lock:
                    acct['steps'].append(step)

                def emit(ev):
                    png = ev.pop('screenshot', None)
                    with _jobs_lock:
                        if png:
                            job['shot'] = base64.b64encode(png).decode()
                        step['last'] = f"{ev.get('action')} {ev.get('reason') or ''}"[:80]

                pkg = rc.app_package or job.get('package')
                rn = (rc.name or '').lower()
                psvc = 'google' if ('gmail' in rn or 'google' in rn) else 'instagram'
                try:
                    ex = Executor(d, package=pkg, llm=llm,
                                  max_steps=job.get('max_steps', 60),
                                  recipe=rc, record=False, variables=ident,
                                  on_step=emit, stop_flag=lambda: job.get('stop'),
                                  phone_client=phone_client, phone_service=psvc,
                                  phone_mode=job.get('phone_mode', 'verification'))
                    res = ex.run(rc.goal or '', variables=ident)
                except Exception as e:
                    res = {'success': False, 'reason': str(e)}
                with _jobs_lock:
                    step['status'] = 'ok' if res.get('success') else 'fail'
                    step['reason'] = res.get('reason', '')
                # a successful gmail-* recipe means a real Gmail now exists -> pool it
                if res.get('success') and 'gmail' in (rc.name or '').lower():
                    _persist_gmail(
                        email=(ident.get('email_local', '') + '@gmail.com'),
                        password=ident.get('password', ''),
                        device_serial=job['device_serial'],
                        linked_ig=ident.get('username', ''))
                if not res.get('success'):
                    ok_all = False
                    break

            status = 'created' if ok_all else 'failed'
            with _jobs_lock:
                acct['status'] = status
            err = '' if ok_all else (acct['steps'][-1].get('reason', '') if acct['steps'] else '')
            _persist_account(job_id, job['device_serial'], ident, status,
                             job['recipe_ids'], error=err)
    except Exception as e:
        import traceback
        with _jobs_lock:
            job['error'] = str(e)
        print('[account-factory]', traceback.format_exc())
    finally:
        if killed:
            try:
                from bot_launcher_routes import _launch_device
                _launch_device(db_serial)
            except Exception:
                pass
        with _jobs_lock:
            job['running'] = False
            job['engine_restarted'] = killed


@account_factory_bp.route('/api/account-factory/run', methods=['POST'])
def run_pipeline():
    data = request.get_json() or {}
    serial = (data.get('device_serial') or '').strip()
    recipe_ids = data.get('recipe_ids') or []
    idents = data.get('identities') or []
    if not serial or not recipe_ids or not idents:
        return jsonify({'error': 'device_serial, recipe_ids and identities are required'}), 400

    job_id = uuid.uuid4().hex[:10]
    with _jobs_lock:
        _jobs[job_id] = {
            'running': True, 'stop': False, 'device_serial': serial,
            'recipe_ids': [int(r) for r in recipe_ids],
            'package': (data.get('package') or '').strip() or None,
            'model': (data.get('model') or '').strip() or None,
            'max_steps': int(data.get('max_steps') or 60),
            # 'rental' = long-term number (mother), 'verification' = cheap one-time (slaves)
            'phone_mode': (data.get('phone_mode') or 'verification'),
            'shot': None, 'error': None,
            'accounts': [{'identity': i, 'status': 'queued', 'steps': []} for i in idents],
        }
    threading.Thread(target=_af_worker, args=(job_id,), daemon=True).start()
    return jsonify({'job_id': job_id, 'accounts': len(idents)})


@account_factory_bp.route('/api/account-factory/status/<job_id>')
def status(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return jsonify({'error': 'unknown job'}), 404
        return jsonify({
            'running': job['running'], 'error': job.get('error'),
            'shot': job.get('shot'), 'engine_restarted': job.get('engine_restarted'),
            'accounts': [{
                'username': a['identity'].get('username'),
                'full_name': a['identity'].get('full_name'),
                'status': a['status'],
                'steps': a['steps'],
            } for a in job['accounts']],
        })


@account_factory_bp.route('/api/account-factory/stop/<job_id>', methods=['POST'])
def stop(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job:
            job['stop'] = True
    return jsonify({'ok': True})


@account_factory_bp.route('/api/account-factory/accounts')
def accounts():
    _ensure_accounts_table()
    c = sqlite3.connect(_DB)
    c.row_factory = sqlite3.Row
    rows = c.execute("SELECT * FROM af_accounts ORDER BY created_at DESC LIMIT 200").fetchall()
    c.close()
    return jsonify({'accounts': [dict(r) for r in rows]})


_GS = os.path.join(_BASE, 'dashboard', 'global_settings.json')


@account_factory_bp.route('/api/account-factory/phone/status')
def phone_status():
    """Is TextVerified configured? If so, show username + live balance."""
    import json
    try:
        cfg = json.load(open(_GS, encoding='utf-8')).get('textverified', {})
    except Exception:
        cfg = {}
    out = {'configured': bool(cfg.get('api_key') and cfg.get('username')),
           'has_key': bool(cfg.get('api_key')), 'username': cfg.get('username', '')}
    if out['configured']:
        try:
            from automation.ai_executor import TextVerified
            tv = TextVerified(cfg['api_key'], cfg['username'],
                              base_url=cfg.get('base_url') or 'https://www.textverified.com/api/pub/v2')
            out['balance'] = tv.balance()
        except Exception as e:
            out['error'] = str(e)[:200]
    return jsonify(out)


@account_factory_bp.route('/api/account-factory/phone/config', methods=['POST'])
def phone_config():
    """Save TextVerified account username (and optionally api_key) to settings."""
    import json
    d = request.get_json() or {}
    try:
        cfg_all = json.load(open(_GS, encoding='utf-8'))
    except Exception:
        cfg_all = {}
    tv = cfg_all.get('textverified', {})
    if d.get('username') is not None:
        tv['username'] = (d.get('username') or '').strip()
    if d.get('api_key'):
        tv['api_key'] = d['api_key'].strip()
    tv.setdefault('base_url', 'https://www.textverified.com/api/pub/v2')
    cfg_all['textverified'] = tv
    json.dump(cfg_all, open(_GS, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
    return jsonify({'ok': True})


@account_factory_bp.route('/api/account-factory/email/status')
def email_status():
    """Is the catch-all email pool configured? Test the IMAP connection."""
    import json
    try:
        cfg = json.load(open(_GS, encoding='utf-8')).get('email_pool', {})
    except Exception:
        cfg = {}
    configured = bool(cfg.get('imap_host') and cfg.get('imap_user')
                      and cfg.get('imap_pass'))
    out = {'configured': configured, 'domain': cfg.get('domain', ''),
           'imap_host': cfg.get('imap_host', ''),
           'imap_user': cfg.get('imap_user', '')}
    if configured:
        try:
            from automation.ai_executor import mailbox_from_settings
            mb = mailbox_from_settings(_GS)
            ok, msg = mb.check() if mb else (False, 'not configured')
            out['reachable'] = ok
            if not ok:
                out['error'] = msg[:200]
        except Exception as e:
            out['reachable'] = False
            out['error'] = str(e)[:200]
    return jsonify(out)


@account_factory_bp.route('/api/account-factory/email/config', methods=['POST'])
def email_config():
    """Save catch-all email pool IMAP settings (domain, host, port, user, pass)."""
    import json
    d = request.get_json() or {}
    try:
        cfg_all = json.load(open(_GS, encoding='utf-8'))
    except Exception:
        cfg_all = {}
    ep = cfg_all.get('email_pool', {})
    for k in ('domain', 'imap_host', 'imap_user'):
        if d.get(k) is not None:
            ep[k] = (d.get(k) or '').strip()
    if d.get('imap_pass'):                       # only overwrite when provided
        ep['imap_pass'] = d['imap_pass'].strip()
    if d.get('imap_port'):
        try:
            ep['imap_port'] = int(d['imap_port'])
        except Exception:
            pass
    ep.setdefault('imap_port', 993)
    ep.setdefault('ssl', True)
    if 'ssl' in d:
        ep['ssl'] = bool(d['ssl'])
    cfg_all['email_pool'] = ep
    json.dump(cfg_all, open(_GS, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
    return jsonify({'ok': True})


@account_factory_bp.route('/api/account-factory/gmails')
def gmails():
    _ensure_gmail_table()
    c = sqlite3.connect(_DB)
    c.row_factory = sqlite3.Row
    rows = c.execute("SELECT * FROM gmail_accounts ORDER BY created_at DESC LIMIT 500").fetchall()
    c.close()
    return jsonify({'gmails': [dict(r) for r in rows]})


@account_factory_bp.route('/api/account-factory/gmails.csv')
def gmails_csv():
    import csv
    import io
    from flask import Response
    _ensure_gmail_table()
    c = sqlite3.connect(_DB)
    c.row_factory = sqlite3.Row
    rows = c.execute("SELECT email, password, full_name, device_serial, ip, "
                     "recovery_phone, linked_ig, status, created_at FROM gmail_accounts "
                     "ORDER BY created_at DESC").fetchall()
    c.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['email', 'password', 'full_name', 'device', 'ip', 'recovery_phone',
                'linked_ig', 'status', 'created_at'])
    for r in rows:
        w.writerow([r['email'], r['password'], r['full_name'], r['device_serial'],
                    r['ip'], r['recovery_phone'], r['linked_ig'], r['status'],
                    r['created_at']])
    return Response(buf.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=gmails.csv'})
