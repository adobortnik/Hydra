"""
device_management_routes.py - Device Management Blueprint

Provides /manage-devices page + /api/devices/* REST endpoints.
Uses phone_farm.db as the single source of truth.
"""

from flask import Blueprint, jsonify, request, render_template
from phone_farm_db import (
    get_all_devices, get_device_by_id, get_device_by_serial,
    add_device, update_device, delete_device, update_device_status
)
from adb_helper import (
    discover_devices, check_device_reachable, connect_device,
    serial_adb_to_db, ip_from_serial
)
from datetime import datetime

device_management_bp = Blueprint('device_management', __name__)


# ─────────────────────────────────────────────
# PAGE ROUTE
# ─────────────────────────────────────────────

@device_management_bp.route('/manage-devices')
def manage_devices_page():
    return render_template('manage_devices.html')


# ─────────────────────────────────────────────
# API ROUTES
# ─────────────────────────────────────────────

@device_management_bp.route('/api/devices/list', methods=['GET'])
def api_list_devices():
    """List all devices from phone_farm.db with account counts."""
    try:
        devices = get_all_devices()
        return jsonify({'status': 'success', 'devices': devices})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@device_management_bp.route('/api/devices/discover', methods=['GET'])
def api_discover_devices():
    """
    Run adb devices, compare with DB.
    Returns: new (not in DB), online (in DB + connected), offline (in DB + not connected)
    """
    try:
        # Get ADB-connected devices
        adb_devices = discover_devices()
        adb_serials = {d['db_serial'] for d in adb_devices}
        adb_map = {d['db_serial']: d for d in adb_devices}

        # Get all DB devices
        db_devices = get_all_devices()
        db_serials = {d['device_serial'] for d in db_devices}

        # Categorize
        new_devices = []
        online_devices = []
        offline_devices = []

        # New = in ADB but not in DB
        for serial in adb_serials - db_serials:
            info = adb_map[serial]
            new_devices.append({
                'db_serial': serial,
                'ip_address': info['ip_address'],
                'adb_port': info['adb_port'],
                'adb_status': info['adb_status'],
            })

        # Existing DB devices: online or offline
        now = datetime.utcnow().isoformat()
        for dev in db_devices:
            serial = dev['device_serial']
            if serial in adb_serials:
                online_devices.append(dev)
                # Update status in DB
                update_device_status(serial, 'connected', now)
            else:
                offline_devices.append(dev)
                if dev.get('status') == 'connected':
                    update_device_status(serial, 'disconnected')

        return jsonify({
            'status': 'success',
            'new_devices': new_devices,
            'online_devices': online_devices,
            'offline_devices': offline_devices,
            'adb_count': len(adb_devices),
            'db_count': len(db_devices),
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@device_management_bp.route('/api/devices/add', methods=['POST'])
def api_add_device():
    """
    Add a device to phone_farm.db.
    Body: { "device_serial": "...", "device_name": "...", "ip_address": "...", "notes": "..." }
    Or: { "ip_address": "10.1.10.200", "adb_port": 5555 } for manual add.
    """
    try:
        data = request.get_json()
        serial = data.get('device_serial')
        ip = data.get('ip_address')
        port = data.get('adb_port', 5555)
        name = data.get('device_name')
        notes = data.get('notes', '')

        # If no serial provided, build from IP
        if not serial and ip:
            serial = f"{ip}_{port}"
        if not serial:
            return jsonify({'status': 'error', 'message': 'device_serial or ip_address required'}), 400

        # Check if already exists
        existing = get_device_by_serial(serial)
        if existing:
            return jsonify({'status': 'error', 'message': f'Device {serial} already exists'}), 409

        if not ip:
            ip = ip_from_serial(serial)

        device = add_device(serial, device_name=name, ip_address=ip, adb_port=port, notes=notes)
        return jsonify({'status': 'success', 'device': device})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@device_management_bp.route('/api/devices/<int:device_id>', methods=['PUT'])
def api_update_device(device_id):
    """Update device name/notes."""
    try:
        data = request.get_json()
        name = data.get('device_name')
        notes = data.get('notes')
        kwargs = {}
        if name is not None:
            kwargs['device_name'] = name
        if notes is not None:
            kwargs['notes'] = notes
        if not kwargs:
            return jsonify({'status': 'error', 'message': 'Nothing to update'}), 400

        update_device(device_id, **kwargs)
        device = get_device_by_id(device_id)
        return jsonify({'status': 'success', 'device': device})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@device_management_bp.route('/api/devices/<int:device_id>', methods=['DELETE'])
def api_delete_device(device_id):
    """Delete a device (only if no accounts assigned)."""
    try:
        success, msg = delete_device(device_id)
        if success:
            return jsonify({'status': 'success', 'message': msg})
        return jsonify({'status': 'error', 'message': msg}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@device_management_bp.route('/api/devices/<serial>/status', methods=['GET'])
def api_device_status(serial):
    """Check if a device is reachable via ADB."""
    try:
        reachable = check_device_reachable(serial)
        status = 'connected' if reachable else 'disconnected'
        update_device_status(serial, status)
        return jsonify({
            'status': 'success',
            'device_serial': serial,
            'reachable': reachable,
            'device_status': status
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@device_management_bp.route('/api/devices/connect', methods=['POST'])
def api_connect_device():
    """Connect to a device via ADB (adb connect ip:port)."""
    try:
        data = request.get_json()
        ip = data.get('ip_address')
        port = data.get('adb_port', 5555)
        if not ip:
            return jsonify({'status': 'error', 'message': 'ip_address required'}), 400

        success, output = connect_device(ip, port)
        return jsonify({
            'status': 'success' if success else 'error',
            'connected': success,
            'output': output
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
