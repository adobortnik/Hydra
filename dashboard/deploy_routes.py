"""
deploy_routes.py - One-Click Deploy Wizard Blueprint

Provides the /deploy page and API endpoints for the deploy wizard:
  Step 1: Select devices
  Step 2: Import accounts (username:password:2fa)
  Step 3: Configure warmup + settings
  Step 4: Review distribution preview
  Step 5: Execute deploy (save to phone_farm.db)
"""

from flask import Blueprint, jsonify, request, render_template
import json
from datetime import datetime, timedelta

from phone_farm_db import (
    get_all_devices, get_device_by_serial, get_accounts_for_device,
    get_available_clone_letters, get_used_clone_letters,
    make_package_name, make_app_id, add_account,
    upsert_account_settings, CLONE_LETTERS,
    set_warmup, clear_warmup, bulk_set_warmup, expire_warmups,
    get_warmup_accounts, update_account,
)

deploy_bp = Blueprint('deploy', __name__)

MAX_ACCOUNTS_PER_DEVICE = 12  # one per clone slot (e through p)


# ─────────────────────────────────────────────
# PAGE ROUTE
# ─────────────────────────────────────────────

@deploy_bp.route('/deploy')
def deploy_page():
    return render_template('deploy.html')


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def parse_accounts_text(text):
    """Parse username:password:2fa_token lines."""
    accounts = []
    seen = set()
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(':')
        if len(parts) < 2:
            continue
        username = parts[0].strip()
        if username.lower() in seen:
            continue  # skip duplicates in input
        seen.add(username.lower())
        accounts.append({
            'username': username,
            'password': parts[1].strip(),
            'two_fa_token': parts[2].strip() if len(parts) > 2 and parts[2].strip() else '',
        })
    return accounts


def auto_stagger_times(count, start_hour=0, slot_hours=2):
    """
    Generate staggered start/end times for `count` accounts.
    Wraps around 24h. Returns list of (start_str, end_str).
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
    Each device gets accounts assigned to sequential clone letters (e, f, g, ...).
    """
    # Track available letters per device
    avail = {}
    for ds in device_serials:
        used = used_map.get(ds, set())
        avail[ds] = [l for l in CLONE_LETTERS if l not in used]

    assigned = []
    device_idx = 0

    for acc in accounts:
        placed = False
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
                placed = True
                break
            device_idx += 1
            attempts += 1

        if not placed:
            acc_copy = dict(acc)
            acc_copy['device_serial'] = None
            acc_copy['clone_letter'] = None
            acc_copy['instagram_package'] = None
            acc_copy['app_id'] = None
            acc_copy['error'] = 'No available clone slots on selected devices'
            assigned.append(acc_copy)

    return assigned


def stagger_per_device(assigned, slot_hours=2, start_hour=0):
    """
    Assign time slots PER DEVICE (so each device has its own 0-24h schedule).
    Account 1 on device X: start_hour → start_hour+slot_hours
    Account 2 on device X: next slot, etc.
    """
    # Group by device
    device_index = {}
    for acc in assigned:
        ds = acc.get('device_serial')
        if ds:
            if ds not in device_index:
                device_index[ds] = 0
            idx = device_index[ds]
            s = (start_hour + (idx * slot_hours)) % 24
            e = (s + slot_hours) % 24
            acc['start_time'] = str(s)
            acc['end_time'] = str(e)
            device_index[ds] += 1
        else:
            acc['start_time'] = '0'
            acc['end_time'] = '0'
    return assigned


# ─────────────────────────────────────────────
# API: Preview deployment
# ─────────────────────────────────────────────

@deploy_bp.route('/api/deploy/preview', methods=['POST'])
def api_deploy_preview():
    """
    Compute a full deployment preview.

    Body:
    {
        "accounts_text": "user1:pass1:2fa\nuser2:pass2",
        "device_serials": ["10.1.10.177_5555", ...],
        "slot_hours": 2,
        "start_hour": 0,
        "warmup_days": 7,
        "settings": { ... }
    }
    """
    try:
        data = request.get_json()
        text = data.get('accounts_text', '')
        device_serials = data.get('device_serials', [])
        slot_hours = int(data.get('slot_hours', 2))
        start_hour = int(data.get('start_hour', 0))
        warmup_days = int(data.get('warmup_days', 0))

        # Parse
        accounts = parse_accounts_text(text)
        if not accounts:
            return jsonify({'status': 'error', 'message': 'No valid accounts found'}), 400
        if not device_serials:
            return jsonify({'status': 'error', 'message': 'No devices selected'}), 400

        # Build used-letters map
        used_map = {}
        for ds in device_serials:
            used_map[ds] = get_used_clone_letters(ds)

        # Distribute across devices round-robin
        assigned = distribute_accounts(accounts, device_serials, used_map)

        # Stagger time slots per device
        assigned = stagger_per_device(assigned, slot_hours, start_hour)

        # Add metadata
        warmup_until = None
        if warmup_days > 0:
            warmup_until = (datetime.utcnow() + timedelta(days=warmup_days)).strftime('%Y-%m-%d')

        for acc in assigned:
            acc['has_2fa'] = bool(acc.get('two_fa_token'))
            acc['warmup'] = 1 if warmup_days > 0 else 0
            acc['warmup_until'] = warmup_until
            acc['status'] = 'pending_login'

        # Stats
        device_counts = {}
        errors = []
        for acc in assigned:
            ds = acc.get('device_serial')
            if ds:
                device_counts[ds] = device_counts.get(ds, 0) + 1
            if acc.get('error'):
                errors.append(acc['error'])

        total_capacity = sum(len(avail) for ds in device_serials
                            for avail in [[l for l in CLONE_LETTERS if l not in used_map.get(ds, set())]])
        # Recalc properly
        total_capacity = sum(
            len([l for l in CLONE_LETTERS if l not in used_map.get(ds, set())])
            for ds in device_serials
        )

        return jsonify({
            'status': 'success',
            'preview': assigned,
            'total': len(assigned),
            'device_counts': device_counts,
            'total_capacity': total_capacity,
            'errors': errors,
            'warmup_until': warmup_until,
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ─────────────────────────────────────────────
# API: Execute deployment
# ─────────────────────────────────────────────

@deploy_bp.route('/api/deploy/execute', methods=['POST'])
def api_deploy_execute():
    """
    Execute the full deployment — create accounts in DB.

    Body:
    {
        "accounts": [ ... ],          // the preview array
        "warmup_days": 7,
        "settings": {
            "follow_enabled": "False",
            ...
        }
    }
    """
    try:
        data = request.get_json()
        accounts_list = data.get('accounts', [])
        warmup_days = int(data.get('warmup_days', 0))
        global_settings = data.get('settings', {})

        if not accounts_list:
            return jsonify({'status': 'error', 'message': 'No accounts to deploy'}), 400

        warmup_until = None
        if warmup_days > 0:
            warmup_until = (datetime.utcnow() + timedelta(days=warmup_days)).strftime('%Y-%m-%d')

        imported = 0
        skipped = 0
        errors = []

        for acc in accounts_list:
            if not acc.get('device_serial') or not acc.get('username'):
                skipped += 1
                errors.append(f"Skipped {acc.get('username', '?')}: no device assigned")
                continue

            try:
                # During warmup: disable all aggressive actions
                if warmup_days > 0:
                    settings_override = {
                        'follow_enabled': 'False',
                        'unfollow_enabled': 'False',
                        'like_enabled': 'False',
                        'story_enabled': 'False',
                        'comment_enabled': 'False',
                        'mute_enabled': 'False',
                    }
                else:
                    settings_override = global_settings

                new_acc = add_account(
                    device_serial=acc['device_serial'],
                    username=acc['username'],
                    password=acc.get('password', ''),
                    two_fa_token=acc.get('two_fa_token', ''),
                    instagram_package=acc.get('instagram_package', 'com.instagram.android'),
                    status='pending_login',
                    start_time=acc.get('start_time', '0'),
                    end_time=acc.get('end_time', '0'),
                    follow_enabled=settings_override.get('follow_enabled', 'False'),
                    unfollow_enabled=settings_override.get('unfollow_enabled', 'False'),
                    like_enabled=settings_override.get('like_enabled', 'False'),
                    story_enabled=settings_override.get('story_enabled', 'False'),
                    comment_enabled=settings_override.get('comment_enabled', 'False'),
                    mute_enabled=settings_override.get('mute_enabled', 'False'),
                    warmup=1 if warmup_days > 0 else 0,
                    warmup_until=warmup_until,
                )

                # Save extended settings (app_cloner, etc.)
                if new_acc:
                    # Build settings JSON
                    ext_settings = dict(global_settings)
                    ext_settings['app_cloner'] = acc.get('app_id', '')
                    # Enable warmup-related settings in the JSON blob
                    if warmup_days > 0:
                        ext_settings['enable_watch_reels'] = True
                        ext_settings['enable_scrollhomefeed'] = True
                        ext_settings['enable_human_behaviour_emulation'] = True
                        ext_settings['storyviewer_limit_perday'] = '0'
                        ext_settings['follow_limit_perday'] = '0'
                        ext_settings['directmessage_daily_limit'] = '0'
                    upsert_account_settings(new_acc['id'], ext_settings)

                imported += 1

            except Exception as e:
                err_msg = str(e)
                if 'UNIQUE constraint' in err_msg:
                    skipped += 1
                    errors.append(f"Skipped {acc['username']}: already exists on {acc['device_serial']}")
                else:
                    errors.append(f"Error deploying {acc['username']}: {err_msg}")

        return jsonify({
            'status': 'success',
            'imported': imported,
            'skipped': skipped,
            'errors': errors,
            'total': len(accounts_list),
            'warmup_until': warmup_until,
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ─────────────────────────────────────────────
# API: Warmup management
# ─────────────────────────────────────────────

@deploy_bp.route('/api/deploy/warmup/status', methods=['GET'])
def api_warmup_status():
    """Get all accounts currently in warmup mode."""
    try:
        # Auto-expire first
        expired = expire_warmups()
        accounts = get_warmup_accounts()
        return jsonify({
            'status': 'success',
            'accounts': accounts,
            'total_warmup': len(accounts),
            'just_expired': expired,
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@deploy_bp.route('/api/deploy/warmup/toggle', methods=['POST'])
def api_warmup_toggle():
    """Toggle warmup for a single account."""
    try:
        data = request.get_json()
        account_id = data.get('account_id')
        enable = data.get('enable', True)
        warmup_days = int(data.get('warmup_days', 7))

        if not account_id:
            return jsonify({'status': 'error', 'message': 'account_id required'}), 400

        if enable:
            warmup_until = (datetime.utcnow() + timedelta(days=warmup_days)).strftime('%Y-%m-%d')
            set_warmup(account_id, warmup_until)
            return jsonify({'status': 'success', 'warmup': True, 'warmup_until': warmup_until})
        else:
            clear_warmup(account_id)
            return jsonify({'status': 'success', 'warmup': False})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@deploy_bp.route('/api/deploy/devices', methods=['GET'])
def api_deploy_devices():
    """Get devices with slot availability for the deploy wizard."""
    try:
        devices = get_all_devices()
        result = []
        for d in devices:
            ds = d['device_serial']
            used = get_used_clone_letters(ds)
            avail = [l for l in CLONE_LETTERS if l not in used]
            result.append({
                'device_serial': ds,
                'device_name': d.get('device_name', ds),
                'status': d.get('status', 'unknown'),
                'account_count': d.get('account_count', 0),
                'total_slots': len(CLONE_LETTERS),
                'free_slots': len(avail),
                'used_letters': list(used),
                'available_letters': avail,
            })
        return jsonify({'status': 'success', 'devices': result})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
