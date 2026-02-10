"""
import_v2_routes.py - Import Accounts V2 Blueprint

New flow: paste accounts → assign to devices → save directly to phone_farm.db.
Replaces the old CSV-export-for-Onimator workflow.
"""

from flask import Blueprint, jsonify, request, render_template
import json
from phone_farm_db import (
    get_all_devices, get_device_by_serial, get_accounts_for_device,
    get_available_clone_letters, get_used_clone_letters,
    make_package_name, make_app_id, add_account,
    upsert_account_settings, CLONE_LETTERS
)

import_v2_bp = Blueprint('import_v2', __name__)

MAX_ACCOUNTS_PER_DEVICE = 12  # one per clone slot


# ─────────────────────────────────────────────
# PAGE ROUTE
# ─────────────────────────────────────────────

@import_v2_bp.route('/import-accounts-v2')
def import_accounts_v2_page():
    return render_template('import_accounts_v2.html')


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def parse_accounts_text(text):
    """Parse username:password:2fa_token lines."""
    accounts = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(':')
        if len(parts) < 2:
            continue
        accounts.append({
            'username': parts[0].strip(),
            'password': parts[1].strip(),
            'two_fa_token': parts[2].strip() if len(parts) > 2 and parts[2].strip() else '',
        })
    return accounts


def auto_stagger_times(count, start_hour=0, slot_hours=2):
    """
    Generate staggered start/end times for `count` accounts.
    Returns list of (start_hour, end_hour) tuples.
    """
    slots = []
    for i in range(count):
        s = (start_hour + (i * slot_hours)) % 24
        e = (s + slot_hours) % 24
        slots.append((str(s), str(e)))
    return slots


def distribute_accounts(accounts, device_serials, used_map):
    """
    Distribute accounts round-robin across devices, respecting clone limits.

    Args:
        accounts: list of parsed account dicts
        device_serials: list of device serial strings
        used_map: dict { device_serial: set_of_used_letters }

    Returns:
        list of dicts with device + clone assignment added
    """
    # Track available letters per device
    avail = {}
    for ds in device_serials:
        used = used_map.get(ds, set())
        avail[ds] = [l for l in CLONE_LETTERS if l not in used]

    assigned = []
    device_idx = 0

    for acc in accounts:
        # Find a device with available slots
        attempts = 0
        while attempts < len(device_serials):
            ds = device_serials[device_idx % len(device_serials)]
            if avail[ds]:
                letter = avail[ds].pop(0)
                acc_copy = dict(acc)
                acc_copy['device_serial'] = ds
                acc_copy['clone_letter'] = letter
                acc_copy['instagram_package'] = make_package_name(letter)
                acc_copy['app_id'] = make_app_id(letter)
                assigned.append(acc_copy)
                device_idx += 1
                break
            device_idx += 1
            attempts += 1
        else:
            # No device had space
            acc_copy = dict(acc)
            acc_copy['device_serial'] = None
            acc_copy['clone_letter'] = None
            acc_copy['instagram_package'] = None
            acc_copy['app_id'] = None
            acc_copy['error'] = 'No available clone slots on selected devices'
            assigned.append(acc_copy)

    return assigned


# ─────────────────────────────────────────────
# API ROUTES
# ─────────────────────────────────────────────

@import_v2_bp.route('/api/import/clone-apps/<device_serial>', methods=['GET'])
def api_clone_apps(device_serial):
    """Return which clone app letters are available/used on a device."""
    try:
        used = list(get_used_clone_letters(device_serial))
        available = get_available_clone_letters(device_serial)
        return jsonify({
            'status': 'success',
            'device_serial': device_serial,
            'used_letters': used,
            'available_letters': available,
            'total_slots': len(CLONE_LETTERS),
            'free_slots': len(available),
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@import_v2_bp.route('/api/import/preview', methods=['POST'])
def api_import_preview():
    """
    Parse accounts text + settings, return preview with calculated assignments.

    Body:
    {
        "accounts_text": "user1:pass1:2fa\nuser2:pass2",
        "device_serials": ["10.1.10.177_5555"],   // list for auto-distribute
        "auto_distribute": true,
        "auto_stagger": true,
        "start_hour": 0,
        "slot_hours": 2,
        "settings": { "follow_enabled": "True", ... }
    }
    """
    try:
        data = request.get_json()
        text = data.get('accounts_text', '')
        device_serials = data.get('device_serials', [])
        auto_distribute = data.get('auto_distribute', True)
        auto_stagger = data.get('auto_stagger', True)
        start_hour = int(data.get('start_hour', 0))
        slot_hours = int(data.get('slot_hours', 2))

        # Parse
        accounts = parse_accounts_text(text)
        if not accounts:
            return jsonify({'status': 'error', 'message': 'No valid accounts found in text'}), 400

        if not device_serials:
            return jsonify({'status': 'error', 'message': 'No devices selected'}), 400

        # Build used-letters map
        used_map = {}
        for ds in device_serials:
            used_map[ds] = get_used_clone_letters(ds)

        # Distribute
        if auto_distribute:
            assigned = distribute_accounts(accounts, device_serials, used_map)
        else:
            # Single device mode: all go to first device
            ds = device_serials[0]
            assigned = distribute_accounts(accounts, [ds], used_map)

        # Auto-stagger time slots
        if auto_stagger:
            time_slots = auto_stagger_times(len(assigned), start_hour, slot_hours)
            for i, acc in enumerate(assigned):
                if i < len(time_slots):
                    acc['start_time'] = time_slots[i][0]
                    acc['end_time'] = time_slots[i][1]
        else:
            for acc in assigned:
                acc['start_time'] = str(start_hour)
                acc['end_time'] = str((start_hour + slot_hours) % 24)

        # Add 2FA indicator
        for acc in assigned:
            acc['has_2fa'] = bool(acc.get('two_fa_token'))

        # Count per device
        device_counts = {}
        errors = []
        for acc in assigned:
            ds = acc.get('device_serial')
            if ds:
                device_counts[ds] = device_counts.get(ds, 0) + 1
            if acc.get('error'):
                errors.append(acc['error'])

        return jsonify({
            'status': 'success',
            'preview': assigned,
            'total': len(assigned),
            'device_counts': device_counts,
            'errors': errors,
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@import_v2_bp.route('/api/import/execute', methods=['POST'])
def api_import_execute():
    """
    Execute the import: save accounts to phone_farm.db.

    Body:
    {
        "accounts": [  // the preview array (possibly edited by user)
            {
                "username": "...",
                "password": "...",
                "two_fa_token": "...",
                "device_serial": "...",
                "instagram_package": "com.instagram.androie",
                "start_time": "0",
                "end_time": "2",
                ...
            }
        ],
        "settings": {
            "follow_enabled": "True",
            "like_enabled": "True",
            ...
        }
    }
    """
    try:
        data = request.get_json()
        accounts_list = data.get('accounts', [])
        global_settings = data.get('settings', {})

        if not accounts_list:
            return jsonify({'status': 'error', 'message': 'No accounts to import'}), 400

        imported = 0
        skipped = 0
        errors = []

        for acc in accounts_list:
            if not acc.get('device_serial') or not acc.get('username'):
                skipped += 1
                errors.append(f"Skipped {acc.get('username', '?')}: no device assigned")
                continue

            try:
                new_acc = add_account(
                    device_serial=acc['device_serial'],
                    username=acc['username'],
                    password=acc.get('password', ''),
                    two_fa_token=acc.get('two_fa_token', ''),
                    instagram_package=acc.get('instagram_package', 'com.instagram.android'),
                    status='pending_login',
                    start_time=acc.get('start_time', '0'),
                    end_time=acc.get('end_time', '0'),
                    follow_enabled=global_settings.get('follow_enabled', 'False'),
                    unfollow_enabled=global_settings.get('unfollow_enabled', 'False'),
                    like_enabled=global_settings.get('like_enabled', 'False'),
                    story_enabled=global_settings.get('story_enabled', 'False'),
                    comment_enabled=global_settings.get('comment_enabled', 'False'),
                    mute_enabled=global_settings.get('mute_enabled', 'False'),
                )

                # Save extended settings if provided
                if global_settings and new_acc:
                    upsert_account_settings(new_acc['id'], global_settings)

                imported += 1

            except Exception as e:
                err_msg = str(e)
                if 'UNIQUE constraint' in err_msg:
                    skipped += 1
                    errors.append(f"Skipped {acc['username']}: already exists on {acc['device_serial']}")
                else:
                    errors.append(f"Error importing {acc['username']}: {err_msg}")

        return jsonify({
            'status': 'success',
            'imported': imported,
            'skipped': skipped,
            'errors': errors,
            'total': len(accounts_list),
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
