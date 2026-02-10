#!/usr/bin/env python3
"""
Proxy Management Routes
========================
Flask blueprint for SuperProxy management on the phone farm dashboard.

Endpoints:
  Page:
    GET  /proxy-management              Dashboard page

  Proxy Pool CRUD:
    GET    /api/proxies                 List all proxies
    POST   /api/proxies                 Add a proxy
    PUT    /api/proxies/<id>            Update proxy
    DELETE /api/proxies/<id>            Delete proxy
    POST   /api/proxies/import          Bulk import proxies
    POST   /api/proxies/check-all       Health-check all proxies

  Device Proxy Actions:
    POST   /api/devices/<serial>/proxy/open     Open SuperProxy on device
    GET    /api/devices/<serial>/proxy/status    Check proxy status on device
    POST   /api/devices/<serial>/proxy/toggle    Toggle proxy on/off
    POST   /api/devices/<serial>/proxy/set       Set a specific proxy on device
    GET    /api/devices/<serial>/proxy/inspect   Dump SuperProxy UI for debugging
    GET    /api/devices/<serial>/proxy/screenshot Screenshot of device
"""

import os
import sys
import json
import sqlite3
import threading
import traceback
from datetime import datetime
from flask import Blueprint, jsonify, request, render_template

# Add parent dirs to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'automation'))

from db.proxy_tables import init_proxy_tables

proxy_bp = Blueprint('proxy_management', __name__)

# ─────────────────────────────────────────────
# DB HELPERS
# ─────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'db', 'phone_farm.db')


def get_conn():
    """Get a SQLite connection with Row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def row_to_dict(row):
    return dict(row) if row else None


def rows_to_dicts(rows):
    return [dict(r) for r in rows] if rows else []


def _ensure_tables():
    """Ensure proxy tables exist (safe to call every time)."""
    init_proxy_tables(DB_PATH)


def _get_superproxy_controller(device_serial):
    """
    Get a SuperProxyController for the given device.
    Connects via the device_connection module.
    
    Returns: (controller, error_message)
    """
    try:
        from automation.device_connection import get_connection
        from automation.superproxy import SuperProxyController
    except ImportError:
        # Try alternate import path
        try:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            sys.path.insert(0, base)
            from automation.device_connection import get_connection
            from automation.superproxy import SuperProxyController
        except ImportError as e:
            return None, f"Import error: {e}"

    # Normalize serial: DB uses underscore, ADB uses colon
    adb_serial = device_serial.replace('_', ':')
    db_serial = device_serial.replace(':', '_')

    conn = get_connection(db_serial)
    device = conn.ensure_connected()

    if not device:
        return None, f"Could not connect to device {adb_serial}"

    controller = SuperProxyController(device, adb_serial)
    return controller, None


def _log_proxy_action(device_serial, proxy_id, proxy_host, proxy_port, action, details=None):
    """Log a proxy action to device_proxy_history."""
    try:
        conn = get_conn()
        conn.execute(
            """INSERT INTO device_proxy_history 
               (device_serial, proxy_id, proxy_host, proxy_port, action, details)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (device_serial, proxy_id, proxy_host, proxy_port, action, details)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[proxy_routes] Failed to log action: {e}")


# ─────────────────────────────────────────────
# PAGE ROUTE
# ─────────────────────────────────────────────

@proxy_bp.route('/proxy-management')
def proxy_management_page():
    """Render the proxy management dashboard page."""
    _ensure_tables()
    return render_template('proxy_management.html')


# ─────────────────────────────────────────────
# PROXY POOL CRUD
# ─────────────────────────────────────────────

@proxy_bp.route('/api/proxies', methods=['GET'])
def api_list_proxies():
    """List all proxies with optional filtering."""
    _ensure_tables()
    try:
        status_filter = request.args.get('status')
        conn = get_conn()

        if status_filter:
            rows = conn.execute(
                "SELECT * FROM proxies WHERE status = ? ORDER BY id", (status_filter,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM proxies ORDER BY id").fetchall()

        conn.close()

        proxies = rows_to_dicts(rows)
        # Mask passwords in response
        for p in proxies:
            if p.get('password'):
                p['password'] = '••••••'

        return jsonify({'status': 'success', 'proxies': proxies, 'count': len(proxies)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@proxy_bp.route('/api/proxies', methods=['POST'])
def api_add_proxy():
    """Add a single proxy to the pool."""
    _ensure_tables()
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'No JSON body'}), 400

        host = data.get('host', '').strip()
        port = data.get('port')
        if not host or not port:
            return jsonify({'status': 'error', 'message': 'host and port are required'}), 400

        conn = get_conn()
        now = datetime.now().isoformat()
        conn.execute(
            """INSERT INTO proxies (host, port, proxy_type, username, password, label, country, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                host, int(port),
                data.get('proxy_type', 'HTTP'),
                data.get('username'),
                data.get('password'),
                data.get('label'),
                data.get('country'),
                data.get('notes'),
                now, now,
            )
        )
        conn.commit()
        proxy_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()

        return jsonify({'status': 'success', 'message': 'Proxy added', 'proxy_id': proxy_id})

    except sqlite3.IntegrityError:
        return jsonify({'status': 'error', 'message': f'Proxy {host}:{port} already exists'}), 409
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@proxy_bp.route('/api/proxies/<int:proxy_id>', methods=['PUT'])
def api_update_proxy(proxy_id):
    """Update a proxy entry."""
    _ensure_tables()
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'No JSON body'}), 400

        allowed_fields = ['host', 'port', 'proxy_type', 'username', 'password',
                          'label', 'status', 'country', 'notes', 'assigned_device_serial']
        
        updates = []
        values = []
        for field in allowed_fields:
            if field in data:
                updates.append(f"{field} = ?")
                values.append(data[field])

        if not updates:
            return jsonify({'status': 'error', 'message': 'No fields to update'}), 400

        updates.append("updated_at = ?")
        values.append(datetime.now().isoformat())
        values.append(proxy_id)

        conn = get_conn()
        conn.execute(f"UPDATE proxies SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': 'Proxy updated'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@proxy_bp.route('/api/proxies/<int:proxy_id>', methods=['DELETE'])
def api_delete_proxy(proxy_id):
    """Delete a proxy entry."""
    _ensure_tables()
    try:
        conn = get_conn()

        # Check if it's assigned to a device
        row = conn.execute("SELECT * FROM proxies WHERE id = ?", (proxy_id,)).fetchone()
        if not row:
            conn.close()
            return jsonify({'status': 'error', 'message': 'Proxy not found'}), 404

        conn.execute("DELETE FROM proxies WHERE id = ?", (proxy_id,))
        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': 'Proxy deleted'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@proxy_bp.route('/api/proxies/import', methods=['POST'])
def api_import_proxies():
    """
    Bulk import proxies from text.
    
    Accepts JSON: { "proxies_text": "host:port\\nhost:port:user:pass\\n..." }
    Or:           { "proxies_text": "host:port:type:user:pass\\n..." }
    """
    _ensure_tables()
    try:
        data = request.get_json()
        text = data.get('proxies_text', '').strip()
        default_type = data.get('default_type', 'HTTP')

        if not text:
            return jsonify({'status': 'error', 'message': 'No proxy text provided'}), 400

        lines = [l.strip() for l in text.split('\n') if l.strip() and not l.strip().startswith('#')]
        added = 0
        skipped = 0
        errors = []

        conn = get_conn()
        now = datetime.now().isoformat()

        for line in lines:
            parts = line.split(':')
            if len(parts) < 2:
                errors.append(f'Invalid format: {line}')
                continue

            host = parts[0].strip()
            try:
                port = int(parts[1].strip())
            except ValueError:
                errors.append(f'Invalid port: {line}')
                continue

            # Determine format: host:port | host:port:user:pass | host:port:type:user:pass
            username = None
            password = None
            proxy_type = default_type

            if len(parts) == 4:
                # host:port:user:pass
                username = parts[2].strip() or None
                password = parts[3].strip() or None
            elif len(parts) == 5:
                # host:port:type:user:pass
                proxy_type = parts[2].strip().upper() or default_type
                username = parts[3].strip() or None
                password = parts[4].strip() or None
            elif len(parts) == 3:
                # Could be host:port:type OR host:port:user (ambiguous)
                third = parts[2].strip().upper()
                if third in ('HTTP', 'HTTPS', 'SOCKS4', 'SOCKS5'):
                    proxy_type = third
                else:
                    username = parts[2].strip() or None

            try:
                conn.execute(
                    """INSERT INTO proxies (host, port, proxy_type, username, password, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (host, port, proxy_type, username, password, now, now)
                )
                added += 1
            except sqlite3.IntegrityError:
                skipped += 1

        conn.commit()
        conn.close()

        return jsonify({
            'status': 'success',
            'added': added,
            'skipped': skipped,
            'errors': errors,
            'message': f'Imported {added} proxies ({skipped} duplicates skipped)'
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@proxy_bp.route('/api/proxies/check-all', methods=['POST'])
def api_check_all_proxies():
    """
    Start a background health check of all proxies.
    Uses simple TCP connect test.
    """
    _ensure_tables()
    try:
        conn = get_conn()
        proxies = rows_to_dicts(conn.execute(
            "SELECT id, host, port FROM proxies WHERE status != 'dead' ORDER BY id"
        ).fetchall())
        conn.close()

        if not proxies:
            return jsonify({'status': 'success', 'message': 'No proxies to check'})

        # Run checks in background thread
        def check_all():
            import socket
            c = get_conn()
            now = datetime.now().isoformat()
            alive = 0
            dead = 0
            for proxy in proxies:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5)
                    start = datetime.now()
                    sock.connect((proxy['host'], proxy['port']))
                    latency = int((datetime.now() - start).total_seconds() * 1000)
                    sock.close()
                    c.execute(
                        """UPDATE proxies SET status = CASE WHEN status = 'in_use' THEN 'in_use' ELSE 'available' END,
                           last_checked = ?, last_working = ?, check_latency_ms = ?, updated_at = ?
                           WHERE id = ?""",
                        (now, now, latency, now, proxy['id'])
                    )
                    alive += 1
                except Exception:
                    c.execute(
                        """UPDATE proxies SET status = CASE WHEN status = 'in_use' THEN 'in_use' ELSE 'dead' END,
                           last_checked = ?, updated_at = ?
                           WHERE id = ?""",
                        (now, now, proxy['id'])
                    )
                    dead += 1
            c.commit()
            c.close()
            print(f"[proxy_check] Done: {alive} alive, {dead} dead out of {len(proxies)}")

        thread = threading.Thread(target=check_all, daemon=True)
        thread.start()

        return jsonify({
            'status': 'success',
            'message': f'Health check started for {len(proxies)} proxies (background)',
            'count': len(proxies)
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ─────────────────────────────────────────────
# DEVICE PROXY ACTIONS
# ─────────────────────────────────────────────

@proxy_bp.route('/api/devices/<serial>/proxy/open', methods=['POST'])
def api_open_superproxy(serial):
    """Open SuperProxy app on a device."""
    try:
        controller, err = _get_superproxy_controller(serial)
        if err:
            return jsonify({'status': 'error', 'message': err}), 500

        result = controller.open_app()
        
        _log_proxy_action(serial, None, None, None, 'app_opened',
                          result.get('message', ''))

        return jsonify({
            'status': 'success' if result['success'] else 'error',
            'data': result
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@proxy_bp.route('/api/devices/<serial>/proxy/status', methods=['GET'])
def api_proxy_status(serial):
    """Check if proxy is active on a device."""
    try:
        controller, err = _get_superproxy_controller(serial)
        if err:
            return jsonify({'status': 'error', 'message': err}), 500

        result = controller.is_proxy_active()
        current = controller.get_current_proxy()

        return jsonify({
            'status': 'success',
            'data': {
                'active': result['active'],
                'confidence': result['confidence'],
                'indicators': result['indicators'],
                'current_proxy': current,
            }
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@proxy_bp.route('/api/devices/<serial>/proxy/toggle', methods=['POST'])
def api_toggle_proxy(serial):
    """Toggle proxy on/off on a device."""
    try:
        data = request.get_json() or {}
        enable = data.get('enable', True)

        controller, err = _get_superproxy_controller(serial)
        if err:
            return jsonify({'status': 'error', 'message': err}), 500

        result = controller.toggle_proxy(enable=enable)

        action = 'toggled_on' if enable else 'toggled_off'
        _log_proxy_action(serial, None, None, None, action, result.get('message', ''))

        return jsonify({
            'status': 'success' if result['success'] else 'error',
            'data': result
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@proxy_bp.route('/api/devices/<serial>/proxy/set', methods=['POST'])
def api_set_proxy(serial):
    """
    Set a specific proxy on a device.
    
    Body: { proxy_id: int } or { host, port, proxy_type, username, password }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'No JSON body'}), 400

        # If proxy_id is provided, look up the proxy
        proxy_id = data.get('proxy_id')
        if proxy_id:
            conn = get_conn()
            row = conn.execute("SELECT * FROM proxies WHERE id = ?", (proxy_id,)).fetchone()
            conn.close()
            if not row:
                return jsonify({'status': 'error', 'message': f'Proxy {proxy_id} not found'}), 404
            proxy = row_to_dict(row)
            host = proxy['host']
            port = proxy['port']
            proxy_type = proxy['proxy_type']
            username = proxy.get('username')
            password = proxy.get('password')
        else:
            host = data.get('host')
            port = data.get('port')
            proxy_type = data.get('proxy_type', 'HTTP')
            username = data.get('username')
            password = data.get('password')

        if not host or not port:
            return jsonify({'status': 'error', 'message': 'host and port are required'}), 400

        controller, err = _get_superproxy_controller(serial)
        if err:
            return jsonify({'status': 'error', 'message': err}), 500

        result = controller.set_proxy(
            host=host,
            port=int(port),
            proxy_type=proxy_type,
            username=username,
            password=password,
        )

        # Update proxy assignment in DB
        if result['success'] and proxy_id:
            conn = get_conn()
            now = datetime.now().isoformat()
            # Release any previous assignment for this device
            conn.execute(
                "UPDATE proxies SET status = 'available', assigned_device_serial = NULL, updated_at = ? WHERE assigned_device_serial = ?",
                (now, serial)
            )
            # Assign new proxy
            conn.execute(
                "UPDATE proxies SET status = 'in_use', assigned_device_serial = ?, updated_at = ? WHERE id = ?",
                (serial, now, proxy_id)
            )
            conn.commit()
            conn.close()

        _log_proxy_action(serial, proxy_id, host, port, 'assigned',
                          result.get('message', ''))

        return jsonify({
            'status': 'success' if result['success'] else 'error',
            'data': result
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@proxy_bp.route('/api/devices/<serial>/proxy/inspect', methods=['GET'])
def api_inspect_device_proxy(serial):
    """Dump SuperProxy UI hierarchy for debugging."""
    try:
        controller, err = _get_superproxy_controller(serial)
        if err:
            return jsonify({'status': 'error', 'message': err}), 500

        result = controller.inspect_ui()
        return jsonify({'status': 'success', 'data': result})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@proxy_bp.route('/api/devices/<serial>/proxy/screenshot', methods=['GET'])
def api_proxy_screenshot(serial):
    """Take a screenshot of the device (for proxy debugging)."""
    try:
        controller, err = _get_superproxy_controller(serial)
        if err:
            return jsonify({'status': 'error', 'message': err}), 500

        b64 = controller.take_screenshot()
        if b64:
            return jsonify({'status': 'success', 'screenshot': b64})
        else:
            return jsonify({'status': 'error', 'message': 'Screenshot failed'}), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ─────────────────────────────────────────────
# PROXY HISTORY
# ─────────────────────────────────────────────

@proxy_bp.route('/api/proxies/history', methods=['GET'])
def api_proxy_history():
    """Get recent proxy action history."""
    _ensure_tables()
    try:
        limit = request.args.get('limit', 50, type=int)
        device = request.args.get('device')

        conn = get_conn()
        if device:
            rows = conn.execute(
                "SELECT * FROM device_proxy_history WHERE device_serial = ? ORDER BY timestamp DESC LIMIT ?",
                (device, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM device_proxy_history ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
        conn.close()

        return jsonify({'status': 'success', 'history': rows_to_dicts(rows)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ─────────────────────────────────────────────
# STATS
# ─────────────────────────────────────────────

@proxy_bp.route('/api/proxies/stats', methods=['GET'])
def api_proxy_stats():
    """Get proxy pool statistics."""
    _ensure_tables()
    try:
        conn = get_conn()
        total = conn.execute("SELECT COUNT(*) FROM proxies").fetchone()[0]
        available = conn.execute("SELECT COUNT(*) FROM proxies WHERE status='available'").fetchone()[0]
        in_use = conn.execute("SELECT COUNT(*) FROM proxies WHERE status='in_use'").fetchone()[0]
        dead = conn.execute("SELECT COUNT(*) FROM proxies WHERE status='dead'").fetchone()[0]
        conn.close()

        return jsonify({
            'status': 'success',
            'stats': {
                'total': total,
                'available': available,
                'in_use': in_use,
                'dead': dead,
            }
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
