"""
login_automation_v2_routes.py - Login Automation V2 Blueprint

Reads account credentials from phone_farm.db (single source of truth)
instead of per-device accounts.db files.

Reuses the existing ADB-based login scripts where possible.
"""

import sys
import os
import json
import time
import threading
import traceback
from pathlib import Path
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, render_template, Response

from phone_farm_db import (
    get_all_devices, get_all_accounts, get_account_by_id,
    update_account_status, update_account, get_accounts_for_device,
    create_task, update_task, get_tasks_by_type_and_status
)
from adb_helper import serial_db_to_adb, check_device_reachable

# Try to import existing login utilities
UI_AUTOMATOR_PATH = Path(__file__).parent / 'uiAutomator'
sys.path.insert(0, str(UI_AUTOMATOR_PATH))

try:
    from automated_login_manager import AutomatedLoginManager
    HAS_LOGIN_MANAGER = True
except ImportError:
    HAS_LOGIN_MANAGER = False

try:
    from two_fa_live_client import TwoFALiveClient
    HAS_2FA_CLIENT = True
except ImportError:
    HAS_2FA_CLIENT = False

login_v2_bp = Blueprint('login_v2', __name__)

# In-memory task tracker for live progress
_login_progress = {}  # batch_id -> { status, message, ... }
_login_lock = threading.Lock()
_stop_requested = set()  # batch_ids that should stop


# ─────────────────────────────────────────────
# THREAD-AWARE STDOUT TEE (for live log window)
# ─────────────────────────────────────────────
# Each login worker thread can attach its own log file. All print() calls
# from that thread (including those from imported modules like login_automation)
# get teed to the file in addition to the normal stdout. Other threads
# (HTTP request handlers, bot launchers) are unaffected.

class _ThreadAwareTee:
    def __init__(self, original_stdout):
        self._orig = original_stdout
        self._files = {}  # thread_id -> file_handle
        self._lock = threading.Lock()

    def attach(self, file_handle):
        tid = threading.get_ident()
        with self._lock:
            self._files[tid] = file_handle

    def detach(self):
        tid = threading.get_ident()
        with self._lock:
            self._files.pop(tid, None)

    def write(self, data):
        try:
            self._orig.write(data)
        except Exception:
            pass
        tid = threading.get_ident()
        with self._lock:
            f = self._files.get(tid)
        if f:
            try:
                f.write(data)
                f.flush()
            except Exception:
                pass

    def flush(self):
        try:
            self._orig.flush()
        except Exception:
            pass

    def isatty(self):
        try:
            return self._orig.isatty()
        except Exception:
            return False

    def __getattr__(self, name):
        return getattr(self._orig, name)


_tee_stdout = None
_tee_lock = threading.Lock()
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')


def _ensure_tee_installed():
    global _tee_stdout
    with _tee_lock:
        if _tee_stdout is None:
            _tee_stdout = _ThreadAwareTee(sys.stdout)
            sys.stdout = _tee_stdout


def _login_log_path():
    """Single shared log file for live login automation window."""
    os.makedirs(LOG_DIR, exist_ok=True)
    return os.path.join(LOG_DIR, 'login_automation_live.log')


def _attach_worker_log():
    """Open the shared log file in append mode and attach to this thread."""
    _ensure_tee_installed()
    try:
        f = open(_login_log_path(), 'a', encoding='utf-8', buffering=1)
        _tee_stdout.attach(f)
        return f
    except Exception:
        return None


def _detach_worker_log(file_handle):
    if _tee_stdout is not None:
        try:
            _tee_stdout.detach()
        except Exception:
            pass
    if file_handle:
        try:
            file_handle.close()
        except Exception:
            pass


# ─────────────────────────────────────────────
# PAGE ROUTE
# ─────────────────────────────────────────────

@login_v2_bp.route('/login-automation-v2')
def login_automation_v2_page():
    # Clean up stale tasks stuck in 'running' for > 10 minutes
    try:
        stale_cutoff = (datetime.utcnow() - timedelta(minutes=10)).isoformat()
        stale_tasks = get_tasks_by_type_and_status('login', ['running'])
        for t in stale_tasks:
            started = t.get('started_at', '')
            if started and started < stale_cutoff:
                update_task(t['id'], status='failed', completed_at=datetime.utcnow().isoformat(),
                            result_json=json.dumps({'error': 'Task timed out (stale)'}))
                account_id = t.get('account_id')
                if account_id:
                    update_account_status(account_id, 'login_failed')
    except Exception:
        pass  # Don't block page load
    return render_template('login_automation_v2.html')


# ─────────────────────────────────────────────
# API ROUTES
# ─────────────────────────────────────────────

@login_v2_bp.route('/api/login-v2/pending', methods=['GET'])
def api_pending_accounts():
    """
    Get accounts with status pending_login or login_failed.
    Optional query param: ?device_serial=...
    """
    try:
        device_serial = request.args.get('device_serial')
        statuses = ['pending_login', 'login_failed', 'logging_in']

        accounts = get_all_accounts(status_filter=statuses, device_serial=device_serial)

        # Group by device for the UI
        by_device = {}
        for acc in accounts:
            ds = acc.get('device_serial', 'unassigned')
            if ds not in by_device:
                by_device[ds] = []
            by_device[ds].append(acc)

        return jsonify({
            'status': 'success',
            'accounts': accounts,
            'by_device': by_device,
            'total': len(accounts),
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@login_v2_bp.route('/api/login-v2/devices', methods=['GET'])
def api_login_devices():
    """Get all devices for the filter dropdown."""
    try:
        devices = get_all_devices()
        return jsonify({'status': 'success', 'devices': devices})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@login_v2_bp.route('/api/login-v2/create-tasks', methods=['POST'])
def api_create_login_tasks():
    """
    Create login tasks for selected account IDs.

    Body: { "account_ids": [1, 2, 3, ...] }
    """
    try:
        data = request.get_json()
        account_ids = data.get('account_ids', [])

        if not account_ids:
            return jsonify({'status': 'error', 'message': 'No accounts selected'}), 400

        task_ids = []
        errors = []

        for aid in account_ids:
            acc = get_account_by_id(aid)
            if not acc:
                errors.append(f"Account ID {aid} not found")
                continue

            if not acc.get('device_serial'):
                errors.append(f"{acc['username']}: no device assigned")
                continue

            # Get 2FA token — try accounts.two_fa_token first, fallback to account_settings.code_2fa
            tfa = acc.get('two_fa_token', '')
            if not tfa:
                try:
                    from phone_farm_db import get_conn as _gc
                    _c = _gc()
                    _row = _c.execute(
                        "SELECT settings_json FROM account_settings WHERE account_id = ?",
                        (acc['id'],)
                    ).fetchone()
                    _c.close()
                    if _row:
                        import json as _j
                        _s = _j.loads(_row['settings_json'] or '{}')
                        tfa = _s.get('code_2fa', '')
                except Exception:
                    pass

            # Build params for the login task
            params = {
                'username': acc['username'],
                'password': acc.get('password', ''),
                'two_fa_token': tfa,
                'instagram_package': acc.get('instagram_package', 'com.instagram.android'),
                'device_serial': acc['device_serial'],
            }

            task_id = create_task(
                account_id=acc['id'],
                device_serial=acc['device_serial'],
                task_type='login',
                params_json=json.dumps(params),
            )
            task_ids.append(task_id)

            # Set account status to logging_in
            update_account_status(acc['id'], 'logging_in')

        return jsonify({
            'status': 'success',
            'created': len(task_ids),
            'task_ids': task_ids,
            'errors': errors,
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@login_v2_bp.route('/api/login-v2/execute', methods=['POST'])
def api_execute_login():
    """
    Execute login tasks. Runs in background threads.
    
    Body: { "task_ids": [1, 2, 3] } or { "all_pending": true }
    """
    try:
        data = request.get_json()
        task_ids = data.get('task_ids', [])
        all_pending = data.get('all_pending', False)

        # Get tasks to execute
        if all_pending:
            tasks = get_tasks_by_type_and_status('login', ['pending'])
        else:
            tasks = get_tasks_by_type_and_status('login', ['pending'])
            if task_ids:
                tasks = [t for t in tasks if t['id'] in task_ids]

        if not tasks:
            return jsonify({'status': 'error', 'message': 'No pending login tasks found'}), 400

        # Group by device (max 1 concurrent login per device)
        by_device = {}
        for task in tasks:
            ds = task.get('device_serial', '')
            if ds not in by_device:
                by_device[ds] = []
            by_device[ds].append(task)

        # Launch one thread per device
        batch_id = f"batch_{int(datetime.utcnow().timestamp())}"

        with _login_lock:
            _login_progress[batch_id] = {
                'total': len(tasks),
                'completed': 0,
                'failed': 0,
                'in_progress': 0,
                'results': {},
                'started_at': datetime.utcnow().isoformat(),
            }

        for ds, device_tasks in by_device.items():
            t = threading.Thread(
                target=_run_device_logins,
                args=(batch_id, ds, device_tasks),
                daemon=True
            )
            t.start()

        return jsonify({
            'status': 'success',
            'batch_id': batch_id,
            'total_tasks': len(tasks),
            'devices': len(by_device),
            'message': f'Started {len(tasks)} login tasks across {len(by_device)} devices',
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@login_v2_bp.route('/api/login-v2/status', methods=['GET'])
def api_login_status():
    """Get live status of login tasks."""
    try:
        batch_id = request.args.get('batch_id')

        if batch_id:
            with _login_lock:
                progress = _login_progress.get(batch_id, {})
            return jsonify({'status': 'success', 'progress': progress})

        # Return all active tasks
        tasks = get_tasks_by_type_and_status('login', ['pending', 'running', 'completed', 'failed'])

        return jsonify({
            'status': 'success',
            'tasks': tasks,
            'active_batches': list(_login_progress.keys()),
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@login_v2_bp.route('/api/login-v2/reset-failed', methods=['POST'])
def api_reset_failed():
    """Reset login_failed or logging_in accounts back to pending_login."""
    try:
        data = request.get_json()
        account_ids = data.get('account_ids', [])

        if not account_ids:
            return jsonify({'status': 'error', 'message': 'No accounts selected'}), 400

        count = 0
        for aid in account_ids:
            update_account_status(aid, 'pending_login')
            count += 1

        return jsonify({'status': 'success', 'reset': count})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@login_v2_bp.route('/api/login-v2/open-log-window', methods=['POST'])
def api_open_log_window():
    """
    Open a separate console window that live-tails the login automation log.
    Spawned as a detached cmd window using PowerShell's Get-Content -Wait
    (equivalent of `tail -f`).

    Body: { batch_id: "batch_xxx" }  (optional — used only for window title)
    """
    try:
        import subprocess
        data = request.get_json(silent=True) or {}
        batch_id = data.get('batch_id') or 'live'
        log_path = _login_log_path()

        # Make sure the file exists so PS doesn't error out
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            if not os.path.exists(log_path):
                with open(log_path, 'a', encoding='utf-8') as f:
                    f.write(f"[{datetime.utcnow().isoformat()}] login automation live log created\n")
        except Exception:
            pass

        title = f"Login Automation Live - {batch_id}"
        # PowerShell Get-Content -Wait acts like tail -f.
        # We start it via `cmd /c start` so the window is detached from Flask.
        ps_cmd = (
            f"$Host.UI.RawUI.WindowTitle='{title}'; "
            f"Write-Host 'Live login automation log:'; "
            f"Write-Host '{log_path}'; "
            f"Write-Host '----------------------------------------'; "
            f"Get-Content -Path '{log_path}' -Wait -Tail 50"
        )
        subprocess.Popen(
            ['cmd', '/c', 'start', title, 'powershell', '-NoExit', '-Command', ps_cmd],
            shell=False,
            creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0)
        )
        return jsonify({'status': 'success', 'log_path': log_path, 'title': title})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@login_v2_bp.route('/api/login-v2/stop', methods=['POST'])
def api_stop_login():
    """Stop a running login batch. Remaining tasks revert to pending."""
    try:
        data = request.get_json() or {}
        batch_id = data.get('batch_id')

        if not batch_id:
            # Stop ALL active batches
            with _login_lock:
                for bid in list(_login_progress.keys()):
                    _stop_requested.add(bid)
                    _login_progress[bid]['stopped'] = True
                stopped = len(_stop_requested)
            return jsonify({'status': 'success', 'message': f'Stop requested for {stopped} batch(es)'})

        _stop_requested.add(batch_id)
        with _login_lock:
            if batch_id in _login_progress:
                _login_progress[batch_id]['stopped'] = True

        return jsonify({'status': 'success', 'message': f'Stop requested for {batch_id}'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@login_v2_bp.route('/api/login-v2/export-failed', methods=['GET'])
def api_export_failed():
    """Export failed accounts as CSV for sending to supplier."""
    try:
        import csv
        import io

        # Get all failed accounts
        failed = get_all_accounts(status_filter=['login_failed'])

        if not failed:
            return jsonify({'status': 'error', 'message': 'No failed accounts to export'}), 404

        # Get 2FA tokens from account_settings
        from phone_farm_db import get_conn
        conn = get_conn()
        tfa_map = {}
        for acc in failed:
            try:
                row = conn.execute(
                    "SELECT settings_json FROM account_settings WHERE account_id = ?",
                    (acc['id'],)
                ).fetchone()
                if row:
                    s = json.loads(row['settings_json'] or '{}')
                    tfa_map[acc['id']] = s.get('code_2fa', '')
            except:
                pass
        conn.close()

        # Build CSV — simple format: username:password:2fa
        output = io.StringIO()

        for acc in failed:
            tfa = acc.get('two_fa_token', '') or tfa_map.get(acc['id'], '')
            line = f"{acc.get('username', '')}:{acc.get('password', '')}:{tfa}"
            output.write(line + '\n')

        csv_data = output.getvalue()
        output.close()

        # Return as downloadable CSV file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'failed_accounts_{timestamp}.csv'

        return Response(
            csv_data,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@login_v2_bp.route('/api/login-v2/failed-accounts', methods=['GET'])
def api_get_failed_accounts():
    """Get all login_failed accounts grouped by device with slot info."""
    try:
        failed = get_all_accounts(status_filter=['login_failed'])
        by_device = {}
        for acc in failed:
            ds = acc.get('device_serial', 'unassigned')
            if ds not in by_device:
                by_device[ds] = []
            by_device[ds].append({
                'id': acc['id'],
                'username': acc['username'],
                'device_serial': ds,
                'device_name': acc.get('device_name', ''),
                'instagram_package': acc.get('instagram_package', ''),
                'status': acc['status'],
            })
        return jsonify({
            'status': 'success',
            'failed': failed,
            'by_device': by_device,
            'total': len(failed),
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@login_v2_bp.route('/api/login-v2/replace-failed', methods=['POST'])
def api_replace_failed():
    """
    Replace failed accounts with new credentials.
    
    Body: {
        "new_accounts": "user1:pass1:2fa1\\nuser2:pass2:2fa2\\n...",
        "failed_account_ids": [1, 2, 3, ...]  // optional — if omitted, replaces ALL failed
    }
    
    Maps new accounts 1:1 onto failed slots (same device, same clone package).
    If fewer new accounts than failed slots, only the first N are replaced.
    If more new accounts than failed slots, extras are ignored.
    """
    try:
        data = request.get_json()
        raw_text = data.get('new_accounts', '')
        target_ids = data.get('failed_account_ids', [])

        # Parse new accounts
        new_accounts = []
        for line in raw_text.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(':')
            if len(parts) < 2:
                continue
            new_accounts.append({
                'username': parts[0].strip(),
                'password': parts[1].strip(),
                'two_fa_token': parts[2].strip() if len(parts) > 2 and parts[2].strip() else '',
            })

        if not new_accounts:
            return jsonify({'status': 'error', 'message': 'No valid accounts parsed. Use format: username:password:2fa (one per line)'}), 400

        # Get failed accounts to replace
        if target_ids:
            failed = [get_account_by_id(aid) for aid in target_ids]
            failed = [a for a in failed if a and a.get('status') == 'login_failed']
        else:
            failed = get_all_accounts(status_filter=['login_failed'])

        if not failed:
            return jsonify({'status': 'error', 'message': 'No failed accounts to replace'}), 400

        # Map 1:1 — new account credentials onto failed slots
        replaced = []
        skipped = []
        for i, new_acc in enumerate(new_accounts):
            if i >= len(failed):
                skipped.append(new_acc['username'])
                continue

            old = failed[i]
            # Update the existing row: swap credentials, reset status
            update_account(old['id'],
                username=new_acc['username'],
                password=new_acc['password'],
                two_fa_token=new_acc['two_fa_token'],
                status='pending_login',
            )
            replaced.append({
                'old_username': old['username'],
                'new_username': new_acc['username'],
                'device_serial': old.get('device_serial', ''),
                'instagram_package': old.get('instagram_package', ''),
            })

        unfilled = len(failed) - len(replaced)

        return jsonify({
            'status': 'success',
            'replaced': len(replaced),
            'details': replaced,
            'skipped_new': skipped,
            'unfilled_slots': unfilled,
            'message': f'Replaced {len(replaced)} accounts. {unfilled} failed slots still unfilled.' if unfilled > 0
                       else f'Replaced {len(replaced)} accounts. All failed slots filled!',
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ─────────────────────────────────────────────
# RE-VERIFY ACCOUNTS
# ─────────────────────────────────────────────

_verify_state = {
    'running': False,
    'progress': '',
    'total': 0,
    'checked': 0,
    'verified': 0,
    'failed': 0,
    'unreachable': 0,
    'results': [],
    'error': None,
}
_verify_lock = threading.Lock()


@login_v2_bp.route('/api/login-v2/active-accounts', methods=['GET'])
def api_active_accounts():
    """
    Get all CHECKABLE accounts (any status except dead ones) for the verify
    modal. Verifier opens every clone and corrects status both ways —
    upgrade if actually logged in, downgrade if actually out — so we
    want to surface ALL non-dead accounts in the modal, not just 'active'.
    """
    try:
        CHECKABLE = ['active', 'logged_in', 'login_failed', 'logged_out',
                     'verification_required', 'pending_login', 'logging_in']
        accounts = get_all_accounts(status_filter=CHECKABLE)
        return jsonify({
            'status': 'success',
            'accounts': accounts,
            'total': len(accounts),
            'note': 'All non-dead accounts surfaced. Suspended/banned/replaced excluded.',
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@login_v2_bp.route('/api/login-v2/verify-accounts', methods=['POST'])
def api_verify_accounts():
    """
    Start a background job to re-verify which accounts are actually logged in.
    Opens each account's IG clone, checks if logged in, marks failed ones.
    
    Body: { "device_serials": [...] }  — optional, defaults to all connected devices
    """
    with _verify_lock:
        if _verify_state['running']:
            return jsonify({'status': 'error', 'message': 'Verification already running'}), 409

    data = request.get_json() or {}
    device_serials = data.get('device_serials', [])

    # By default check ALL "checkable" accounts — even login_failed, logged_out
    # etc. The verifier will UPGRADE actually-logged-in accounts to active and
    # DOWNGRADE actually-out accounts to login_failed. This corrects DB drift
    # caused by post-login modal verification failures.
    #
    # We still SKIP terminally-dead statuses (no point opening IG on a banned
    # account — IG will only confirm the death).
    CHECKABLE = (
        'active', 'logged_in',
        'login_failed', 'logged_out',
        'verification_required',  # might have resolved on its own after a few days
        'pending_login', 'logging_in',
    )
    SKIP_STATUSES = ('suspended', 'banned', 'replaced', 'disabled')

    # `only_active=true` body flag preserves the OLD behavior (check only
    # currently-active accounts) for callers that explicitly want it.
    only_active = bool(data.get('only_active', False))
    allowed = ('active',) if only_active else CHECKABLE

    if device_serials:
        accounts = []
        for ds in device_serials:
            accounts.extend(get_accounts_for_device(ds))
        accounts = [a for a in accounts
                    if (a.get('status') or '').lower() in allowed]
    else:
        accounts = get_all_accounts(status_filter=list(allowed))

    if not accounts:
        return jsonify({'status': 'error',
                        'message': f'No checkable accounts to verify '
                                   f'(allowed statuses: {", ".join(allowed)})'}), 400

    # Group by device
    by_device = {}
    for acc in accounts:
        ds = acc.get('device_serial', '')
        if ds not in by_device:
            by_device[ds] = []
        by_device[ds].append(acc)

    with _verify_lock:
        _verify_state.update({
            'running': True,
            'progress': 'Starting verification...',
            'total': len(accounts),
            'checked': 0,
            'verified': 0,
            'failed': 0,
            'unreachable': 0,
            'results': [],
            'error': None,
        })

    # Start background thread
    t = threading.Thread(target=_run_verify, args=(by_device,), daemon=True)
    t.start()

    return jsonify({
        'status': 'success',
        'message': f'Verification started for {len(accounts)} accounts on {len(by_device)} devices',
        'total': len(accounts),
    })


@login_v2_bp.route('/api/login-v2/verify-status', methods=['GET'])
def api_verify_status():
    """Get verification progress."""
    with _verify_lock:
        return jsonify(_verify_state.copy())


def _run_verify(by_device):
    """Coordinator: spawn one thread per device for parallel verification."""
    import builtins
    _orig_print = builtins.print
    def _fp(*a, **kw):
        kw.setdefault('flush', True)
        _orig_print(*a, **kw)
    builtins.print = _fp

    threads = []
    for device_serial, accounts in by_device.items():
        t = threading.Thread(target=_verify_one_device, args=(device_serial, accounts), daemon=True)
        threads.append(t)
        t.start()
        print(f"[VERIFY] Started thread for {device_serial} ({len(accounts)} accounts)")

    # Wait for all threads to finish
    for t in threads:
        t.join()

    with _verify_lock:
        v = _verify_state
        v['progress'] = f"Done! {v['verified']} verified, {v['failed']} failed, {v['unreachable']} unreachable"
        v['running'] = False

    print(f"[VERIFY] === COMPLETE === Verified: {_verify_state['verified']}, "
          f"Failed: {_verify_state['failed']}, Unreachable: {_verify_state['unreachable']}")


def _verify_one_device(device_serial, accounts):
    """Verify all accounts on a single device. Runs in its own thread."""
    try:
        import uiautomator2 as u2
        adb_serial = serial_db_to_adb(device_serial)

        # Check device reachable
        if not check_device_reachable(device_serial):
            print(f"[VERIFY] Device {device_serial} not reachable — skipping {len(accounts)} accounts")
            with _verify_lock:
                _verify_state['unreachable'] += len(accounts)
                _verify_state['checked'] += len(accounts)
                for acc in accounts:
                    _verify_state['results'].append({
                        'username': acc['username'],
                        'device': device_serial,
                        'status': 'device_unreachable',
                    })
            return

        # Connect to device
        try:
            print(f"[VERIFY] Connecting to {device_serial}...")
            device = u2.connect(adb_serial)
            device.info  # test connection
        except Exception as ce:
            print(f"[VERIFY] Failed to connect to {device_serial}: {ce}")
            with _verify_lock:
                _verify_state['unreachable'] += len(accounts)
                _verify_state['checked'] += len(accounts)
            return

        for acc in accounts:
            username = acc.get('username', '?')
            package = acc.get('instagram_package', 'com.instagram.android')
            acc_id = acc['id']

            with _verify_lock:
                _verify_state['progress'] = f'Checking {username} on {device_serial}...'

            try:
                print(f"[VERIFY] Checking {username} ({package}) on {device_serial}...")

                # Open the specific IG clone
                device.app_start(package)
                time.sleep(5)

                # Dump screen
                xml = device.dump_hierarchy()
                xl = xml.lower()

                # === Check NOT logged in first (aggressive) ===
                not_logged = False
                reason = ''
                if 'join instagram' in xl or 'get started' in xl:
                    not_logged, reason = True, 'join/signup page'
                elif 'already have an account' in xl:
                    not_logged, reason = True, 'signup page'
                elif 'create new account' in xl:
                    not_logged, reason = True, 'create account page'
                elif 'log in' in xl and 'sign up' in xl:
                    not_logged, reason = True, 'login/signup page'
                elif 'log in' in xl and ('password' in xl or 'phone' in xl or 'email' in xl):
                    not_logged, reason = True, 'login page'
                elif 'we suspended' in xl or 'suspended your account' in xl:
                    not_logged, reason = True, 'suspended'
                elif 'account has been disabled' in xl:
                    not_logged, reason = True, 'disabled'
                elif 'check your sms' in xl or 'we sent a link' in xl:
                    not_logged, reason = True, 'SMS verification'
                elif 'wrong password' in xl or 'incorrect password' in xl:
                    not_logged, reason = True, 'wrong password'

                if not_logged:
                    print(f"[VERIFY] {device_serial} | {username} -- NOT LOGGED IN ({reason})")
                    update_account_status(acc_id, 'login_failed')
                    with _verify_lock:
                        _verify_state['failed'] += 1
                        _verify_state['results'].append({
                            'username': username, 'device': device_serial,
                            'package': package, 'status': 'not_logged_in',
                            'reason': reason,
                        })
                else:
                    # === Check positive logged-in indicators ===
                    logged_in = False

                    # First, check for post-login modals. These ONLY appear
                    # AFTER a successful login (Android permission dialogs,
                    # IG's "Set up new device" / location / save login info /
                    # welcome screens). If any of these are on screen, the
                    # account is logged in but a modal is blocking the home
                    # feed — exactly the case John was hitting manually.
                    post_login_modals = [
                        # Android 13+ system permission dialogs
                        'com.android.permissioncontroller',
                        'send you notifications',
                        'allow notifications',
                        'turn on notifications',
                        # IG location flow
                        'set up on new device',
                        'to use location services',
                        'allow instagram to access your location',
                        "access this device's location",
                        'access this device’s location',
                        'while using the app',
                        'only this time',
                        'how you can use location services',
                        # Save login info / device-trust
                        'save your login info',
                        "we'll remember this device",
                        'we’ll remember this device',
                        # Other typical post-login prompts
                        'add a profile photo',
                        'add profile photo',
                        'discover people to follow',
                        'find people to follow',
                        'sync contacts',
                        "see when you're online",
                        'see when you’re online',
                    ]
                    matched_modal = None
                    for marker in post_login_modals:
                        if marker in xl:
                            matched_modal = marker
                            logged_in = True
                            break

                    if not logged_in:
                        p_rid = package + ':id/profile_tab'
                        if device(resourceId=p_rid).exists(timeout=3):
                            logged_in = True
                        elif device(description="Profile").exists(timeout=2) and 'sign up' not in xl:
                            logged_in = True
                        elif device(description="Home").exists(timeout=2) and 'sign up' not in xl and 'join instagram' not in xl:
                            logged_in = True
                        elif device(description="Search and explore").exists(timeout=2):
                            logged_in = True
                    elif matched_modal:
                        print(f"[VERIFY] {device_serial} | {username} — post-login modal detected: '{matched_modal}'")

                if not not_logged and logged_in:
                    print(f"[VERIFY] {device_serial} | {username} — LOGGED IN")
                    # UPGRADE status to active (corrects accounts that were
                    # mis-flagged as login_failed when verify_logged_in() got
                    # confused by a post-login modal).
                    try:
                        prev = (acc.get('status') or '').lower()
                        if prev != 'active':
                            update_account_status(acc_id, 'active')
                            print(f"[VERIFY] {device_serial} | {username} status: {prev} -> active")
                    except Exception as _e:
                        print(f"[VERIFY] {username} status upgrade failed: {_e}")
                    with _verify_lock:
                        _verify_state['verified'] += 1
                        _verify_state['results'].append({
                            'username': username, 'device': device_serial,
                            'package': package, 'status': 'verified',
                            'previous_status': acc.get('status'),
                        })
                elif not not_logged and not logged_in:
                    # Uncertain = conservative, mark as failed
                    print(f"[VERIFY] {device_serial} | {username} -- UNCERTAIN, marking NOT logged in")
                    print(f"[VERIFY] {device_serial} | XML: {xl[:300]}")
                    update_account_status(acc_id, 'login_failed')
                    with _verify_lock:
                        _verify_state['failed'] += 1
                        _verify_state['results'].append({
                            'username': username, 'device': device_serial,
                            'package': package, 'status': 'uncertain',
                        })

            except Exception as e:
                print(f"[VERIFY] {device_serial} | Error checking {username}: {e}")
                with _verify_lock:
                    _verify_state['results'].append({
                        'username': username, 'device': device_serial,
                        'status': 'error', 'error': str(e),
                    })

            with _verify_lock:
                _verify_state['checked'] += 1

            # Brief pause between accounts on same device
            time.sleep(2)

        # Press home after done
        try:
            device.press('home')
        except:
            pass

    except Exception as e:
        print(f"[VERIFY] {device_serial} | Thread error: {e}")
        traceback.print_exc()
        with _verify_lock:
            _verify_state['error'] = str(e)


# ─────────────────────────────────────────────
# BACKGROUND LOGIN WORKER
# ─────────────────────────────────────────────

def _stop_bot_engine_on_device(device_serial):
    """
    Check if bot engine (run_device.py) is running on this device.
    If so, kill it before login starts. Returns the PID that was killed, or None.
    """
    try:
        from bot_launcher_routes import _find_process_for_serial, _kill_pid, _invalidate_proc_cache
        procs = _find_process_for_serial(device_serial, use_cache=False)
        if procs:
            for p in procs:
                print(f'[login_v2] Stopping bot engine on {device_serial} (PID {p["pid"]}) before login...')
                _kill_pid(p['pid'], force=True)
            _invalidate_proc_cache()
            import time as _time
            _time.sleep(2)  # Give process time to die
            return procs[0]['pid']
    except Exception as e:
        print(f'[login_v2] Warning: could not check/stop bot engine on {device_serial}: {e}')
    return None


def _run_device_logins(batch_id, device_serial, tasks):
    """
    Execute login tasks sequentially on a single device.
    Runs in a background thread.
    Auto-stops bot engine on the device before starting logins.
    """
    # Tee this thread's stdout to the shared live-log file (used by the
    # optional "Live log window" toggle in the v2 UI).
    log_handle = _attach_worker_log()
    print(f"\n{'='*70}\n[BATCH {batch_id}] device={device_serial} starting {len(tasks)} task(s) at {datetime.utcnow().isoformat()}\n{'='*70}")
    try:
        _run_device_logins_inner(batch_id, device_serial, tasks)
    finally:
        print(f"[BATCH {batch_id}] device={device_serial} thread done\n")
        _detach_worker_log(log_handle)


def _run_device_logins_inner(batch_id, device_serial, tasks):
    # Stop bot engine if running on this device
    stopped_pid = _stop_bot_engine_on_device(device_serial)
    if stopped_pid:
        print(f'[login_v2] Bot engine was running on {device_serial} — stopped (PID {stopped_pid})')

    for task in tasks:
        # Check if stop was requested before starting next account
        if batch_id in _stop_requested:
            # Mark remaining tasks back to pending
            remaining = [t for t in tasks if t['id'] >= task['id']]
            for rt in remaining:
                rt_id = rt['id']
                rt_params = json.loads(rt.get('params_json', '{}'))
                rt_username = rt_params.get('username', '?')
                update_task(rt_id, status='pending')
                rt_account_id = rt.get('account_id')
                if rt_account_id:
                    update_account_status(rt_account_id, 'pending_login')
                with _login_lock:
                    if batch_id in _login_progress:
                        _login_progress[batch_id]['results'][str(rt_id)] = {
                            'status': 'skipped',
                            'username': rt_username,
                            'device': device_serial,
                            'message': 'Stopped by user',
                        }
            with _login_lock:
                if batch_id in _login_progress:
                    _login_progress[batch_id]['stopped'] = True
            return  # Exit the thread

        task_id = task['id']
        account_id = task.get('account_id')
        params = json.loads(task.get('params_json', '{}'))
        username = params.get('username', '?')

        # Update progress
        with _login_lock:
            if batch_id in _login_progress:
                _login_progress[batch_id]['in_progress'] += 1
                _login_progress[batch_id]['results'][str(task_id)] = {
                    'status': 'running',
                    'username': username,
                    'device': device_serial,
                }

        # Update task status
        update_task(task_id, status='running', started_at=datetime.utcnow().isoformat())

        pkg = params.get('instagram_package', 'com.instagram.android')
        adb_ser = serial_db_to_adb(device_serial)

        try:
            # Try using the existing login manager
            success, message = _perform_login(
                device_serial=device_serial,
                username=params.get('username', ''),
                password=params.get('password', ''),
                two_fa_token=params.get('two_fa_token', ''),
                instagram_package=params.get('instagram_package', 'com.instagram.android'),
            )

            now = datetime.utcnow().isoformat()

            if success:
                update_task(task_id, status='completed', completed_at=now,
                            result_json=json.dumps({'message': message}))
                if account_id:
                    update_account_status(account_id, 'active')

                with _login_lock:
                    if batch_id in _login_progress:
                        _login_progress[batch_id]['completed'] += 1
                        _login_progress[batch_id]['in_progress'] -= 1
                        _login_progress[batch_id]['results'][str(task_id)] = {
                            'status': 'completed', 'username': username,
                            'device': device_serial, 'message': message,
                        }
            else:
                update_task(task_id, status='failed', completed_at=now,
                            result_json=json.dumps({'error': message}))
                if account_id:
                    update_account_status(account_id, 'login_failed')

                # Force-stop the IG clone so screen doesn't stay stuck
                try:
                    import subprocess
                    subprocess.run(['adb', '-s', adb_ser, 'shell', 'am', 'force-stop', pkg],
                                   timeout=10, capture_output=True)
                    print(f"[CLEANUP] Force-stopped {pkg} on {device_serial}")
                except Exception as fe:
                    print(f"[CLEANUP] Could not force-stop {pkg}: {fe}")

                with _login_lock:
                    if batch_id in _login_progress:
                        _login_progress[batch_id]['failed'] += 1
                        _login_progress[batch_id]['in_progress'] -= 1
                        _login_progress[batch_id]['results'][str(task_id)] = {
                            'status': 'failed', 'username': username,
                            'device': device_serial, 'error': message,
                        }

        except Exception as e:
            now = datetime.utcnow().isoformat()
            error_msg = f"{type(e).__name__}: {str(e)}"
            update_task(task_id, status='failed', completed_at=now,
                        result_json=json.dumps({'error': error_msg}))
            if account_id:
                update_account_status(account_id, 'login_failed')

            with _login_lock:
                if batch_id in _login_progress:
                    _login_progress[batch_id]['failed'] += 1
                    _login_progress[batch_id]['in_progress'] -= 1
                    _login_progress[batch_id]['results'][str(task_id)] = {
                        'status': 'failed', 'username': username,
                        'device': device_serial, 'error': error_msg,
                    }


def _perform_login(device_serial, username, password, two_fa_token, instagram_package):
    """
    Perform the actual Instagram login via ADB.
    Uses AutomatedLoginManager if available, otherwise returns a stub.
    """
    adb_serial = serial_db_to_adb(device_serial)

    # Check device reachability first
    if not check_device_reachable(device_serial):
        return False, f"Device {device_serial} not reachable via ADB"

    if HAS_LOGIN_MANAGER:
        try:
            manager = AutomatedLoginManager()

            # The existing manager expects certain params — adapt
            result = manager.login_account(
                device_serial=adb_serial,
                instagram_package=instagram_package,
                username=username,
                password=password,
                two_fa_token=two_fa_token if two_fa_token else None,
            )

            if isinstance(result, dict):
                success = result.get('success', False)
                message = result.get('message', str(result))
                return success, message
            elif isinstance(result, bool):
                return result, 'Login completed' if result else 'Login failed'
            else:
                return bool(result), str(result)

        except Exception as e:
            return False, f"Login manager error: {str(e)}"
    else:
        # Fallback: just verify device is reachable (stub for testing)
        return False, "AutomatedLoginManager not available. Install uiAutomator dependencies."
