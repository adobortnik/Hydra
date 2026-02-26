"""
Device Synchronization Routes
===============================
Dashboard blueprint for device fingerprinting (Phase 1) and
network discovery + sync (Phase 2).

Routes:
  GET  /sync                           → Sync dashboard page
  GET  /api/sync/status                → Fingerprint status summary
  POST /api/sync/collect-fingerprints  → Phase 1: collect fingerprints from known devices
  POST /api/sync/scan                  → Phase 2: scan IP range for ADB devices
  POST /api/sync/apply                 → Phase 2: apply IP updates to DB
"""

import os
import sys
import json
import sqlite3
import subprocess
import threading
import time
import datetime
import shutil
import ipaddress
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Blueprint, render_template, jsonify, request

# ── Paths ──────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'db', 'phone_farm.db')
BACKUP_DIR = os.path.join(BASE_DIR, 'db', 'backups')

sync_bp = Blueprint('sync', __name__)

# ── In-memory state for async operations ──────────────────────────
_operation_state = {
    'running': False,
    'type': None,          # 'fingerprint' | 'scan'
    'progress': 0,
    'total': 0,
    'phase': '',
    'details': [],
    'result': None,
    'error': None
}
_state_lock = threading.Lock()


def _reset_state(op_type=None):
    with _state_lock:
        _operation_state['running'] = op_type is not None
        _operation_state['type'] = op_type
        _operation_state['progress'] = 0
        _operation_state['total'] = 0
        _operation_state['phase'] = ''
        _operation_state['details'] = []
        _operation_state['result'] = None
        _operation_state['error'] = None


def _update_state(**kwargs):
    with _state_lock:
        _operation_state.update(kwargs)


def _get_state():
    with _state_lock:
        return dict(_operation_state)


# ── Database helpers ──────────────────────────────────────────────
def _get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_columns():
    """Add hardware_serial and hardware_fingerprint columns if missing."""
    conn = _get_conn()
    cols = [c[1] for c in conn.execute("PRAGMA table_info(devices)").fetchall()]
    
    if 'hardware_serial' not in cols:
        conn.execute("ALTER TABLE devices ADD COLUMN hardware_serial TEXT")
    if 'hardware_fingerprint' not in cols:
        conn.execute("ALTER TABLE devices ADD COLUMN hardware_fingerprint TEXT")
    
    conn.commit()
    conn.close()


# Ensure columns on import
try:
    _ensure_columns()
except:
    pass


# ── ADB helpers ───────────────────────────────────────────────────
def _db_to_adb(serial):
    return serial.replace('_', ':')


def _adb_to_db(serial):
    return serial.replace(':', '_')


def _adb_cmd(adb_serial, command, timeout=10):
    """Run ADB shell command. Returns stdout or None."""
    try:
        result = subprocess.run(
            f'adb -s {adb_serial} shell {command}',
            capture_output=True, text=True, timeout=timeout, shell=True
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except:
        return None


def _adb_connect(adb_serial, timeout=3):
    """Try ADB connect. Returns True if connected."""
    try:
        result = subprocess.run(
            f'adb connect {adb_serial}',
            capture_output=True, text=True, timeout=timeout, shell=True
        )
        out = result.stdout.strip().lower()
        return 'connected' in out or 'already' in out
    except:
        return False


# ── Phase 1: Fingerprint collection ──────────────────────────────
def _collect_single_fingerprint(device_serial):
    """Collect fingerprint from one device. Returns result dict."""
    adb_serial = _db_to_adb(device_serial)
    result = {
        'device_serial': device_serial,
        'success': False,
        'hardware_serial': None,
        'fingerprint': {},
        'error': None
    }
    
    if not _adb_connect(adb_serial):
        result['error'] = 'Connection failed'
        return result
    
    time.sleep(0.5)
    
    # Primary serial
    hw = _adb_cmd(adb_serial, 'getprop ro.serialno')
    if not hw or hw in ('', 'unknown'):
        hw = _adb_cmd(adb_serial, 'getprop ro.boot.serialno')
    if not hw or hw in ('', 'unknown'):
        result['error'] = 'Could not read hardware serial'
        return result
    
    result['hardware_serial'] = hw
    
    # Backup identifiers
    fp = {
        'ro_serialno': hw,
        'ro_boot_serialnumber': _adb_cmd(adb_serial, 'getprop ro.boot.serialnumber') or '',
        'ro_product_model': _adb_cmd(adb_serial, 'getprop ro.product.model') or '',
        'ro_product_brand': _adb_cmd(adb_serial, 'getprop ro.product.brand') or '',
        'ro_product_device': _adb_cmd(adb_serial, 'getprop ro.product.device') or '',
        'ro_build_fingerprint': _adb_cmd(adb_serial, 'getprop ro.build.fingerprint') or '',
        'wifi_mac': '',
        'bluetooth_mac': '',
        'android_id': '',
        'ig_packages': []
    }
    
    mac = _adb_cmd(adb_serial, 'cat /sys/class/net/wlan0/address')
    if mac and ':' in mac:
        fp['wifi_mac'] = mac
    
    bt = _adb_cmd(adb_serial, 'settings get secure bluetooth_address')
    if bt and bt != 'null':
        fp['bluetooth_mac'] = bt
    
    aid = _adb_cmd(adb_serial, 'settings get secure android_id')
    if aid and aid != 'null':
        fp['android_id'] = aid
    
    pkgs = _adb_cmd(adb_serial, 'pm list packages | grep instagram')
    if pkgs:
        fp['ig_packages'] = [l.replace('package:', '').strip() for l in pkgs.split('\n') if l.strip()]
    
    result['fingerprint'] = fp
    result['success'] = True
    return result


def _run_fingerprint_collection(device_serials):
    """Background task: collect fingerprints for given devices."""
    _reset_state('fingerprint')
    _update_state(total=len(device_serials), phase='collecting')
    
    results = []
    success = 0
    failed = 0
    
    try:
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(_collect_single_fingerprint, ds): ds for ds in device_serials}
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                    
                    if result['success']:
                        success += 1
                        # Store in DB
                        conn = _get_conn()
                        conn.execute(
                            "UPDATE devices SET hardware_serial=?, hardware_fingerprint=?, updated_at=? WHERE device_serial=?",
                            (result['hardware_serial'],
                             json.dumps(result['fingerprint']),
                             datetime.datetime.now().isoformat(),
                             result['device_serial'])
                        )
                        conn.commit()
                        conn.close()
                    else:
                        failed += 1
                    
                    _update_state(
                        progress=success + failed,
                        details=results[-5:]  # keep last 5 for live display
                    )
                except Exception as e:
                    failed += 1
        
        _update_state(
            running=False,
            phase='done',
            result={
                'success_count': success,
                'fail_count': failed,
                'total': len(device_serials),
                'results': results
            }
        )
    except Exception as e:
        _update_state(running=False, error=str(e))


# ── Phase 2: Network scan ────────────────────────────────────────
def _parse_ip_range(range_str):
    """Parse IP range string into list of IPs."""
    range_str = range_str.strip()
    ips = []
    
    if ',' in range_str and '/' not in range_str:
        for ip_str in range_str.split(','):
            ip_str = ip_str.strip()
            try:
                ipaddress.ip_address(ip_str)
                ips.append(ip_str)
            except ValueError:
                pass
        return ips
    
    if '/' in range_str:
        try:
            network = ipaddress.ip_network(range_str, strict=False)
            return [str(ip) for ip in network.hosts()]
        except ValueError:
            return []
    
    match = re.match(r'^(\d+\.\d+\.\d+\.)(\d+)-(\d+)$', range_str)
    if match:
        prefix, start, end = match.group(1), int(match.group(2)), int(match.group(3))
        return [f"{prefix}{i}" for i in range(start, end + 1) if 1 <= i <= 254]
    
    try:
        ipaddress.ip_address(range_str)
        return [range_str]
    except ValueError:
        return []


def _try_connect(ip, port=5555):
    """Try ADB connect, return (ip, connected, hw_serial)."""
    adb_serial = f"{ip}:{port}"
    try:
        result = subprocess.run(
            f'adb connect {adb_serial}',
            capture_output=True, text=True, timeout=3, shell=True
        )
        out = result.stdout.strip().lower()
        if 'connected' not in out and 'already' not in out:
            return (ip, False, None)
        
        time.sleep(0.3)
        
        # Read hardware serial
        hw_result = subprocess.run(
            f'adb -s {adb_serial} shell getprop ro.serialno',
            capture_output=True, text=True, timeout=5, shell=True
        )
        hw = hw_result.stdout.strip()
        if not hw or hw in ('', 'unknown'):
            hw_result = subprocess.run(
                f'adb -s {adb_serial} shell getprop ro.boot.serialno',
                capture_output=True, text=True, timeout=5, shell=True
            )
            hw = hw_result.stdout.strip()
        
        if hw and hw not in ('', 'unknown'):
            return (ip, True, hw)
        return (ip, True, None)
    except:
        return (ip, False, None)


def _run_network_scan(ip_range_str, port=5555):
    """Background task: scan network for ADB devices."""
    _reset_state('scan')
    
    ips = _parse_ip_range(ip_range_str)
    if not ips:
        _update_state(running=False, error=f'No valid IPs from range: {ip_range_str}')
        return
    
    _update_state(total=len(ips), phase='scanning')
    
    discovered = []
    scanned = 0
    
    try:
        # Limit concurrency to avoid overwhelming ADB server
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(_try_connect, ip, port): ip for ip in ips}
            
            connected_ips = []
            for future in as_completed(futures):
                scanned += 1
                try:
                    ip, connected, hw_serial = future.result()
                    if connected:
                        connected_ips.append(f"{ip}:{port}")
                    if connected and hw_serial:
                        discovered.append({
                            'ip': ip,
                            'port': port,
                            'hardware_serial': hw_serial,
                            'adb_serial': f"{ip}:{port}",
                            'db_serial': f"{ip}_{port}"
                        })
                except:
                    pass
                
                _update_state(progress=scanned)
        
        # Disconnect IPs that aren't in our discovered list to avoid zombie ADB connections
        discovered_adb = {d['adb_serial'] for d in discovered}
        for adb_serial in connected_ips:
            if adb_serial not in discovered_adb:
                try:
                    subprocess.run(f'adb disconnect {adb_serial}',
                                   capture_output=True, timeout=3, shell=True)
                except:
                    pass
        
        # Match against DB
        conn = _get_conn()
        db_devices = [dict(r) for r in conn.execute(
            "SELECT id, device_serial, device_name, hardware_serial, ip_address FROM devices"
        ).fetchall()]
        conn.close()
        
        hw_lookup = {}
        for d in db_devices:
            if d['hardware_serial']:
                hw_lookup[d['hardware_serial']] = d
        
        matched = []
        unmatched = []
        not_found = []
        matched_hw = set()
        
        for disc in discovered:
            hw = disc['hardware_serial']
            if hw in hw_lookup:
                db_dev = hw_lookup[hw]
                matched.append({
                    'hardware_serial': hw,
                    'old_serial': db_dev['device_serial'],
                    'new_serial': disc['db_serial'],
                    'old_ip': db_dev['ip_address'],
                    'new_ip': disc['ip'],
                    'device_name': db_dev['device_name'],
                    'device_id': db_dev['id'],
                    'changed': db_dev['device_serial'] != disc['db_serial']
                })
                matched_hw.add(hw)
            else:
                unmatched.append({
                    'ip': disc['ip'],
                    'db_serial': disc['db_serial'],
                    'hardware_serial': hw
                })
        
        for d in db_devices:
            hw = d.get('hardware_serial')
            if hw and hw not in matched_hw:
                not_found.append({
                    'device_serial': d['device_serial'],
                    'device_name': d['device_name'],
                    'hardware_serial': hw,
                    'reason': 'not_responding'
                })
            elif not hw:
                not_found.append({
                    'device_serial': d['device_serial'],
                    'device_name': d['device_name'],
                    'hardware_serial': None,
                    'reason': 'no_fingerprint'
                })
        
        _update_state(
            running=False,
            phase='done',
            result={
                'discovered_count': len(discovered),
                'matched': matched,
                'unmatched': unmatched,
                'not_found': not_found,
                'total_scanned': len(ips)
            }
        )
    except Exception as e:
        _update_state(running=False, error=str(e))


# ── Apply sync ────────────────────────────────────────────────────
def _get_tables_with_device_serial():
    """Find all tables with device_serial-like columns.
    
    Searches for any column that stores the device serial string (ip_port format).
    Skips integer FK columns like device_id (those reference devices.id, not serial).
    """
    conn = _get_conn()
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    
    # Column names that store the device serial string (ip_port format)
    SERIAL_COLUMNS = {
        'device_serial', 'deviceid', 'assigned_to_device_serial',
        'assigned_device_serial', 'device_assigned',
    }
    
    result = []
    for table in tables:
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        for col in cols:
            if col in SERIAL_COLUMNS:
                result.append((table, col))
    
    conn.close()
    return result


def _apply_sync(changes_to_apply):
    """Apply device serial updates. Returns report."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f'phone_farm_pre_sync_{timestamp}.db')
    shutil.copy2(DB_PATH, backup_path)
    
    tables = _get_tables_with_device_serial()
    conn = _get_conn()
    all_changes = []
    
    try:
        # Pre-check: handle UNIQUE conflicts on device_serial
        merged_devices = []
        for change in changes_to_apply:
            existing = conn.execute(
                "SELECT id, device_serial, hardware_serial, device_name FROM devices "
                "WHERE device_serial = ? AND device_serial != ?",
                (change['new_serial'], change['old_serial'])
            ).fetchone()
            
            if not existing:
                continue  # No conflict, good to go
            
            existing = dict(existing)
            ex_hw = existing.get('hardware_serial') or ''
            
            # If the conflicting device has a DIFFERENT hardware_serial, it's a real
            # physical device at that IP — can't overwrite it
            if ex_hw and ex_hw != change.get('hardware_serial', ''):
                return {
                    'success': False,
                    'backup_path': backup_path,
                    'error': f"IP conflict: '{change['new_serial']}' already belongs to "
                             f"device '{existing['device_name']}' (hw: {ex_hw}). "
                             f"Two different physical devices can't share the same IP.",
                    'changes': []
                }
            
            # Conflicting device has same hw_serial (duplicate) or no hw_serial (stale).
            # Delete the stale/duplicate entry — the real device will take its place.
            conn.execute("DELETE FROM devices WHERE id = ?", (existing['id'],))
            merged_devices.append({
                'deleted_id': existing['id'],
                'deleted_serial': existing['device_serial'],
                'reason': 'duplicate' if ex_hw else 'stale_entry'
            })
        
        for change in changes_to_apply:
            old_serial = change['old_serial']
            new_serial = change['new_serial']
            new_ip = change['new_ip']
            
            for table, column in tables:
                count = conn.execute(
                    f"SELECT COUNT(*) as cnt FROM {table} WHERE {column} = ?",
                    (old_serial,)
                ).fetchone()['cnt']
                
                if count > 0:
                    conn.execute(
                        f"UPDATE {table} SET {column} = ? WHERE {column} = ?",
                        (new_serial, old_serial)
                    )
                    all_changes.append({
                        'table': table,
                        'column': column,
                        'old_value': old_serial,
                        'new_value': new_serial,
                        'rows_affected': count
                    })
            
            # Update IP address
            conn.execute(
                "UPDATE devices SET ip_address = ?, updated_at = ? WHERE device_serial = ?",
                (new_ip, datetime.datetime.now().isoformat(), new_serial)
            )
        
        conn.commit()
        return {
            'success': True,
            'backup_path': backup_path,
            'changes': all_changes,
            'devices_updated': len(changes_to_apply),
            'merged_devices': merged_devices
        }
    except Exception as e:
        conn.rollback()
        return {
            'success': False,
            'backup_path': backup_path,
            'error': str(e),
            'changes': []
        }
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════
#  ROUTES
# ═══════════════════════════════════════════════════════════════════

@sync_bp.route('/sync')
def sync_page():
    """Render the sync dashboard page."""
    return render_template('sync.html')


@sync_bp.route('/api/sync/status')
def sync_status():
    """Get fingerprint status and current operation state."""
    conn = _get_conn()
    
    total_devices = conn.execute("SELECT COUNT(*) as cnt FROM devices").fetchone()['cnt']
    
    # Check if columns exist
    cols = [c[1] for c in conn.execute("PRAGMA table_info(devices)").fetchall()]
    
    if 'hardware_serial' in cols:
        with_fingerprint = conn.execute(
            "SELECT COUNT(*) as cnt FROM devices WHERE hardware_serial IS NOT NULL AND hardware_serial != ''"
        ).fetchone()['cnt']
        
        # Get fingerprint details
        devices = [dict(r) for r in conn.execute(
            "SELECT device_serial, device_name, hardware_serial, hardware_fingerprint, ip_address FROM devices ORDER BY device_name"
        ).fetchall()]
    else:
        with_fingerprint = 0
        devices = [dict(r) for r in conn.execute(
            "SELECT device_serial, device_name, ip_address FROM devices ORDER BY device_name"
        ).fetchall()]
    
    conn.close()
    
    # Parse fingerprint JSON for each device
    for d in devices:
        fp = d.get('hardware_fingerprint')
        if fp:
            try:
                d['hardware_fingerprint'] = json.loads(fp)
            except:
                pass
    
    return jsonify({
        'total_devices': total_devices,
        'with_fingerprint': with_fingerprint,
        'without_fingerprint': total_devices - with_fingerprint,
        'devices': devices,
        'operation': _get_state()
    })


@sync_bp.route('/api/sync/collect-fingerprints', methods=['POST'])
def collect_fingerprints():
    """Phase 1: Collect fingerprints from known devices."""
    state = _get_state()
    if state['running']:
        return jsonify({'error': 'Operation already in progress', 'state': state}), 409
    
    _ensure_columns()
    
    # Get device list
    data = request.get_json(silent=True) or {}
    device_serials = data.get('devices', None)
    
    conn = _get_conn()
    if device_serials:
        devices = [r['device_serial'] for r in conn.execute(
            "SELECT device_serial FROM devices WHERE device_serial IN ({})".format(
                ','.join('?' * len(device_serials))
            ), device_serials
        ).fetchall()]
    else:
        devices = [r['device_serial'] for r in conn.execute(
            "SELECT device_serial FROM devices"
        ).fetchall()]
    conn.close()
    
    if not devices:
        return jsonify({'error': 'No devices found'}), 404
    
    # Run in background
    thread = threading.Thread(
        target=_run_fingerprint_collection,
        args=(devices,),
        daemon=True
    )
    thread.start()
    
    return jsonify({
        'message': f'Started fingerprint collection for {len(devices)} device(s)',
        'device_count': len(devices)
    })


@sync_bp.route('/api/sync/scan', methods=['POST'])
def scan_network():
    """Phase 2: Scan IP range for ADB devices."""
    state = _get_state()
    if state['running']:
        return jsonify({'error': 'Operation already in progress', 'state': state}), 409
    
    data = request.get_json(silent=True) or {}
    ip_range = data.get('ip_range', '')
    port = data.get('port', 5555)
    
    if not ip_range:
        return jsonify({'error': 'ip_range is required'}), 400
    
    # Validate range
    ips = _parse_ip_range(ip_range)
    if not ips:
        return jsonify({'error': f'Invalid IP range: {ip_range}'}), 400
    
    if len(ips) > 1024:
        return jsonify({'error': f'Too many IPs ({len(ips)}). Max 1024.'}), 400
    
    # Run in background
    thread = threading.Thread(
        target=_run_network_scan,
        args=(ip_range, port),
        daemon=True
    )
    thread.start()
    
    return jsonify({
        'message': f'Started scanning {len(ips)} IP(s)',
        'ip_count': len(ips)
    })


@sync_bp.route('/api/sync/apply', methods=['POST'])
def apply_changes():
    """Apply the device serial updates to DB."""
    data = request.get_json(silent=True) or {}
    changes = data.get('changes', [])
    
    if not changes:
        return jsonify({'error': 'No changes provided'}), 400
    
    # Validate changes
    for c in changes:
        if not c.get('old_serial') or not c.get('new_serial') or not c.get('new_ip'):
            return jsonify({'error': 'Each change needs old_serial, new_serial, and new_ip'}), 400
    
    result = _apply_sync(changes)
    
    if result['success']:
        return jsonify({
            'success': True,
            'message': f"Updated {result['devices_updated']} device(s)",
            'backup_path': result['backup_path'],
            'changes': result['changes']
        })
    else:
        return jsonify({
            'success': False,
            'error': result.get('error', 'Unknown error'),
            'backup_path': result.get('backup_path')
        }), 500


@sync_bp.route('/api/sync/operation-status')
def operation_status():
    """Get current operation progress (for polling)."""
    return jsonify(_get_state())
