#!/usr/bin/env python3
"""
Flask routes for Profile Automation Dashboard Integration
Add these routes to your simple_app.py
"""

import sys
import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime

# Add uiAutomator to path (now inside dashboard folder)
sys.path.insert(0, str(Path(__file__).parent / "uiAutomator"))

from flask import Blueprint, jsonify, request
from tag_based_automation import TagBasedAutomation
from ai_profile_generator import CampaignAIGenerator
from profile_automation_db import (
    init_database as _init_pa_db,
    get_db_connection as _get_pa_db,
    PROFILE_AUTOMATION_DB,
    get_profile_pictures, get_bio_templates,
    get_pending_tasks, add_bio_template, add_profile_picture
)
# Ensure profile_automation tables exist on startup
try:
    _init_pa_db()
except Exception:
    pass

# Import settings helper (in same directory as this file)
import sys
sys.path.insert(0, str(Path(__file__).parent))
from settings_routes import get_ai_config

# Create blueprint
profile_automation_bp = Blueprint('profile_automation', __name__, url_prefix='/api/profile_automation')

# Initialize automation
automation = TagBasedAutomation()

@profile_automation_bp.route('/ai-config', methods=['GET'])
def get_ai_config_endpoint():
    """Get AI configuration for frontend use"""
    try:
        ai_config = get_ai_config()
        # Mask the key for display but return enough to know it's set
        api_key = ai_config.get('api_key', '')
        return jsonify({
            'status': 'success',
            'api_key': api_key,
            'provider': ai_config.get('provider', 'openai'),
            'enabled': ai_config.get('enabled', False),
            'has_key': bool(api_key)
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@profile_automation_bp.route('/upload-picture-url', methods=['POST'])
def upload_picture_from_url():
    """Download an image from a URL and save it as a profile picture"""
    try:
        import requests as req
        import time as _time
        from profile_automation_db import add_profile_picture, PROFILE_PICTURES_DIR

        data = request.get_json()
        url = data.get('url', '').strip()
        gender = data.get('gender', 'neutral')

        if not url:
            return jsonify({'status': 'error', 'message': 'URL is required'}), 400

        # Download the image
        resp = req.get(url, timeout=15, stream=True, headers={
            'User-Agent': 'Mozilla/5.0'
        })
        resp.raise_for_status()

        # Determine extension from content type
        content_type = resp.headers.get('Content-Type', '')
        ext_map = {
            'image/jpeg': '.jpg', 'image/jpg': '.jpg',
            'image/png': '.png', 'image/gif': '.gif',
            'image/webp': '.webp'
        }
        ext = ext_map.get(content_type.split(';')[0].strip(), '.jpg')

        # Save to uploaded folder
        upload_dir = PROFILE_PICTURES_DIR / "uploaded"
        upload_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{_time.time()}{ext}"
        save_path = upload_dir / filename

        with open(str(save_path), 'wb') as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)

        # Register in DB
        pic_id = add_profile_picture(
            filename=filename,
            original_path=str(save_path),
            category='uploaded',
            gender=gender,
            notes=f'Fetched from URL: {url[:100]}'
        )

        return jsonify({
            'status': 'success',
            'picture_id': pic_id,
            'filename': filename,
            'message': 'Picture fetched and uploaded successfully'
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@profile_automation_bp.route('/tags', methods=['GET'])
def get_tags():
    """Get all tags with account counts"""
    try:
        tags = automation.get_tags()
        return jsonify({
            'status': 'success',
            'tags': tags
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@profile_automation_bp.route('/tags', methods=['POST'])
def create_tag():
    """Create a new tag"""
    try:
        data = request.get_json()
        name = data.get('name')
        description = data.get('description', '')

        if not name:
            return jsonify({
                'status': 'error',
                'message': 'Tag name is required'
            }), 400

        tag_id = automation.create_tag(name, description)

        return jsonify({
            'status': 'success',
            'tag_id': tag_id
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@profile_automation_bp.route('/accounts/<tag_name>', methods=['GET'])
def get_tagged_accounts(tag_name):
    """Get all accounts with a specific tag"""
    try:
        accounts = automation.get_accounts_by_tag(tag_name)
        return jsonify({
            'status': 'success',
            'tag': tag_name,
            'accounts': accounts
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@profile_automation_bp.route('/accounts/tag', methods=['POST'])
def tag_account():
    """Tag an account"""
    try:
        data = request.get_json()
        device_serial = data.get('device_serial')
        username = data.get('username')
        tag_name = data.get('tag')

        if not all([device_serial, username, tag_name]):
            return jsonify({
                'status': 'error',
                'message': 'device_serial, username, and tag are required'
            }), 400

        success = automation.tag_account(device_serial, username, tag_name)

        return jsonify({
            'status': 'success' if success else 'exists',
            'message': 'Account tagged' if success else 'Account already has this tag'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@profile_automation_bp.route('/accounts/tag/bulk', methods=['POST'])
def bulk_tag_accounts():
    """Bulk tag multiple accounts"""
    try:
        data = request.get_json()
        tag_name = data.get('tag')
        device_serials = data.get('device_serials', [])
        usernames = data.get('usernames', [])

        if not tag_name:
            return jsonify({
                'status': 'error',
                'message': 'Tag name is required'
            }), 400

        count = automation.bulk_tag_accounts(tag_name, device_serials, usernames)

        return jsonify({
            'status': 'success',
            'tagged_count': count
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@profile_automation_bp.route('/accounts/untag', methods=['POST'])
def untag_account():
    """Remove tag from account"""
    try:
        data = request.get_json()
        device_serial = data.get('device_serial')
        username = data.get('username')
        tag_name = data.get('tag')

        if not all([device_serial, username, tag_name]):
            return jsonify({
                'status': 'error',
                'message': 'device_serial, username, and tag are required'
            }), 400

        automation.untag_account(device_serial, username, tag_name)

        return jsonify({
            'status': 'success',
            'message': 'Tag removed'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@profile_automation_bp.route('/campaigns', methods=['POST'])
def create_campaign():
    """
    Create a profile automation campaign

    POST body:
    {
        "tag": "chantall",
        "name": "Chantall Q1 Update",
        "mother_account": "chantall.main",
        "use_ai": true,
        "ai_config": {
            "provider": "openai",
            "api_key": "sk-..."
        },
        "strategies": {
            "profile_picture": "rotate",
            "bio": "ai",
            "username": "ai"
        }
    }
    """
    try:
        data = request.get_json()
        tag_name = data.get('tag')
        campaign_name = data.get('name')
        mother_account = data.get('mother_account')
        use_ai = data.get('use_ai', False)
        ai_config = data.get('ai_config', {})
        strategies = data.get('strategies', {})

        if not all([tag_name, campaign_name]):
            return jsonify({
                'status': 'error',
                'message': 'tag and name are required'
            }), 400

        campaign_id = automation.create_campaign(
            tag_name=tag_name,
            campaign_name=campaign_name,
            mother_account=mother_account,
            use_ai=use_ai,
            ai_config=ai_config,
            strategies=strategies
        )

        return jsonify({
            'status': 'success',
            'campaign_id': campaign_id
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@profile_automation_bp.route('/campaigns/<int:campaign_id>/execute', methods=['POST'])
def execute_campaign(campaign_id):
    """
    Execute a campaign (creates profile update tasks for all tagged accounts)
    """
    try:
        result = automation.execute_campaign(campaign_id)

        return jsonify({
            'status': 'success',
            'result': result
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@profile_automation_bp.route('/ai/generate/username', methods=['POST'])
def generate_ai_username():
    """
    Generate username using AI

    POST body:
    {
        "mother_account": "chantall.main",
        "api_key": "sk-...",
        "provider": "openai"
    }
    """
    try:
        data = request.get_json()
        mother_account = data.get('mother_account')
        api_key = data.get('api_key')
        provider = data.get('provider', 'openai')

        if not mother_account:
            return jsonify({
                'status': 'error',
                'message': 'mother_account is required'
            }), 400

        generator = CampaignAIGenerator(api_key=api_key, provider=provider)
        username = generator.generator.generate_username(mother_account)

        return jsonify({
            'status': 'success',
            'username': username
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@profile_automation_bp.route('/ai/generate/bio', methods=['POST'])
def generate_ai_bio():
    """
    Generate bio using AI

    POST body:
    {
        "mother_account": "chantall.main",
        "mother_bio": "✨ Fashion | Paris",
        "api_key": "sk-...",
        "provider": "openai"
    }
    """
    try:
        data = request.get_json()
        mother_account = data.get('mother_account')
        mother_bio = data.get('mother_bio')
        api_key = data.get('api_key')
        provider = data.get('provider', 'openai')

        if not mother_account:
            return jsonify({
                'status': 'error',
                'message': 'mother_account is required'
            }), 400

        generator = CampaignAIGenerator(api_key=api_key, provider=provider)
        bio = generator.generator.generate_bio(mother_account, mother_bio)

        return jsonify({
            'status': 'success',
            'bio': bio
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@profile_automation_bp.route('/ai/generate/campaign', methods=['POST'])
def generate_campaign_profiles():
    """
    Generate complete profiles for a campaign

    POST body:
    {
        "mother_account": "chantall.main",
        "mother_bio": "✨ Fashion | Paris",
        "account_count": 10,
        "api_key": "sk-...",
        "provider": "openai"
    }
    """
    try:
        data = request.get_json()
        mother_account = data.get('mother_account')
        mother_bio = data.get('mother_bio', '')
        account_count = data.get('account_count', 5)
        api_key = data.get('api_key')
        provider = data.get('provider', 'openai')

        if not mother_account:
            return jsonify({
                'status': 'error',
                'message': 'mother_account is required'
            }), 400

        generator = CampaignAIGenerator(api_key=api_key, provider=provider)
        profiles = generator.generate_campaign_profiles(
            mother_account, mother_bio, account_count
        )

        return jsonify({
            'status': 'success',
            'profiles': profiles
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@profile_automation_bp.route('/profile_pictures', methods=['GET'])
def get_pictures():
    """Get all profile pictures"""
    try:
        gender = request.args.get('gender')
        category = request.args.get('category')
        unused_only = request.args.get('unused_only') == 'true'

        pictures = get_profile_pictures(
            gender=gender,
            category=category,
            unused_only=unused_only
        )

        return jsonify({
            'status': 'success',
            'pictures': pictures
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@profile_automation_bp.route('/bio_templates', methods=['GET'])
def get_templates():
    """Get all bio templates"""
    try:
        category = request.args.get('category')
        templates = get_bio_templates(category=category)

        return jsonify({
            'status': 'success',
            'templates': templates
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@profile_automation_bp.route('/tasks', methods=['GET'])
def get_tasks():
    """Get all pending profile update tasks"""
    try:
        tasks = get_pending_tasks()

        return jsonify({
            'status': 'success',
            'tasks': tasks
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@profile_automation_bp.route('/quick_campaign', methods=['POST'])
def quick_campaign():
    """
    Quick campaign - one-click automation for tagged accounts

    POST body:
    {
        "tag": "chantall",
        "mother_account": "chantall.main",
        "mother_bio": "✨ Fashion & Lifestyle | 📍 Paris",
        "use_ai": false,
        "selected_accounts": [{"device_serial": "...", "username": "..."}],  (optional)
        "actions": {
            "change_picture": true,
            "change_bio": true,
            "change_username": false
        }
    }
    """
    try:
        data = request.get_json()
        tag = data.get('tag')
        mother_account = data.get('mother_account')
        mother_bio = data.get('mother_bio', '')
        name_shortcuts = data.get('name_shortcuts', [])  # List of name variations
        use_ai = data.get('use_ai', False)

        # Try to get AI key from request, otherwise use global settings
        ai_key = data.get('ai_api_key')
        if not ai_key and use_ai:
            # Load from global settings
            ai_config = get_ai_config()
            ai_key = ai_config.get('api_key', '')
            if not ai_key:
                return jsonify({
                    'status': 'error',
                    'message': 'AI is enabled but no API key is configured. Please set API key in Settings.'
                }), 400

        selected_accounts = data.get('selected_accounts')  # Optional: specific accounts only

        # Action checkboxes - control what changes to make
        actions = data.get('actions', {
            'change_picture': True,
            'change_bio': True,
            'change_username': True
        })

        # `mother_account` is OPTIONAL. It's only a *source* to derive
        # bio/username FROM when using AI/variation. Editing a (new) mother
        # account directly — uploading a picture + writing a custom bio — needs
        # no source mother. create_campaign(mother_account=None) + the nullable
        # DB column handle empty fine. Only `tag` is required (the frontend
        # always sends at least 'manual'). Previously mother_account was
        # mandatory, which blocked exactly this case (400).
        if not tag:
            return jsonify({'status': 'error', 'message': 'tag is required'}), 400

        # Get uploaded picture ID for simplified picture handling
        uploaded_picture_id = data.get('uploaded_picture_id')

        # Build strategies based on action checkboxes.
        # IMPORTANT: disabled actions MUST get an explicit skip value. If we
        # just omit the key, create_campaign defaults profile_picture→'rotate'
        # and bio→'template' (both ACTIVE) — so change_picture:false /
        # change_bio:false were silently ignored (a "bio-only" task still
        # rotated a picture). 'none' picture → no picture_id assigned → step
        # skipped; 'none' bio → new_bio left unset → step skipped; 'manual'
        # username = skip (existing convention).
        strategies = {
            'profile_picture': 'uploaded' if actions.get('change_picture', True) else 'none',
            'bio': ('ai' if use_ai else 'template') if actions.get('change_bio', True) else 'none',
            'username': ('creative' if name_shortcuts else ('ai' if use_ai else 'variation'))
                        if actions.get('change_username', True) else 'manual',
        }

        # Create campaign
        campaign_id = automation.create_campaign(
            tag_name=tag,
            campaign_name=f"{tag} Quick Campaign",
            mother_account=mother_account,
            name_shortcuts=name_shortcuts,
            mother_bio=mother_bio,
            use_ai=use_ai,
            ai_config={'api_key': ai_key, 'provider': 'openai'} if ai_key else {},
            strategies=strategies
        )

        # Execute campaign with selected accounts if provided
        extra_kwargs = {}
        if uploaded_picture_id:
            extra_kwargs['uploaded_picture_id'] = uploaded_picture_id

        if selected_accounts:
            result = automation.execute_campaign_for_accounts(campaign_id, selected_accounts, **extra_kwargs)
        else:
            result = automation.execute_campaign(campaign_id, **extra_kwargs)

        return jsonify({
            'status': 'success',
            'campaign_id': campaign_id,
            'tasks_created': result['tasks_created'],
            'actions': actions,
            'message': f"Created {result['tasks_created']} profile update tasks. Run: python parallel_profile_processor.py"
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@profile_automation_bp.route('/mother_account/<device_serial>/<username>', methods=['GET'])
def get_mother_account_info(device_serial, username):
    """
    Get mother account info from settings.db
    Returns current username, bio, and any other relevant info
    """
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent / "uiAutomator"))

        settings_path = Path(__file__).parent.parent / device_serial / username / "settings.db"

        if not settings_path.exists():
            return jsonify({
                'status': 'error',
                'message': f'Account not found: {device_serial}/{username}'
            }), 404

        import sqlite3
        import json

        conn = sqlite3.connect(settings_path, timeout=30)
        conn.execute("PRAGMA busy_timeout=30000")
        cursor = conn.cursor()
        cursor.execute('SELECT settings FROM accountsettings WHERE id = 1')
        row = cursor.fetchone()
        conn.close()

        if row and row[0]:
            settings = json.loads(row[0])

            return jsonify({
                'status': 'success',
                'device_serial': device_serial,
                'username': username,
                'tags': settings.get('tags', ''),
                'mention': settings.get('sharepost_mention', ''),  # Current bio/mention info
                'settings': {
                    'enable_tags': settings.get('enable_tags', False)
                }
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'No settings found for account'
            }), 404

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@profile_automation_bp.route('/run_processor', methods=['POST'])
def run_batch_processor():
    """
    Run the batch profile manager to process all pending tasks
    Uses optimized batch processing (groups tasks by device)
    """
    try:
        import subprocess
        from pathlib import Path

        # Path to batch manager script
        uiautomator_path = Path(__file__).parent.parent / "uiAutomator"
        batch_manager_path = uiautomator_path / "batch_profile_manager.py"

        if not batch_manager_path.exists():
            return jsonify({
                'status': 'error',
                'message': 'Batch manager script not found'
            }), 404

        # Get optional max_tasks parameter
        data = request.get_json() or {}
        max_tasks = data.get('max_tasks')

        # Run the batch processor in background
        cmd = ['python', str(batch_manager_path)]
        if max_tasks:
            cmd.extend(['--max-tasks', str(max_tasks)])

        subprocess.Popen(
            cmd,
            cwd=str(uiautomator_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        return jsonify({
            'status': 'success',
            'message': 'Batch processor started. Processing tasks by device (optimized mode).'
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@profile_automation_bp.route('/grant_permissions', methods=['POST'])
def grant_storage_permissions():
    """
    Grant storage permissions to all Instagram apps on all connected devices
    Prevents permission dialogs during profile picture changes
    """
    try:
        import subprocess
        from pathlib import Path

        # Get list of connected devices
        result = subprocess.run(
            ['adb', 'devices'],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return jsonify({
                'status': 'error',
                'message': 'Failed to get ADB devices. Is ADB installed?'
            }), 500

        # Parse devices
        devices = []
        for line in result.stdout.split('\n')[1:]:  # Skip header
            if line.strip() and '\t' in line:
                serial = line.split('\t')[0]
                devices.append(serial)

        if not devices:
            return jsonify({
                'status': 'error',
                'message': 'No devices connected'
            }), 400

        # Instagram packages to grant permissions to
        instagram_packages = ['com.instagram.android']
        # Add clones (e through p)
        for letter in 'efghijklmnop':
            instagram_packages.append(f'com.instagram.android{letter}')

        granted_count = 0
        failed_count = 0
        results = []

        for device_serial in devices:
            device_results = {'device': device_serial, 'packages': []}

            for package in instagram_packages:
                try:
                    # Grant READ_EXTERNAL_STORAGE
                    subprocess.run(
                        ['adb', '-s', device_serial, 'shell', 'pm', 'grant',
                         package, 'android.permission.READ_EXTERNAL_STORAGE'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )

                    # Grant WRITE_EXTERNAL_STORAGE
                    subprocess.run(
                        ['adb', '-s', device_serial, 'shell', 'pm', 'grant',
                         package, 'android.permission.WRITE_EXTERNAL_STORAGE'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )

                    granted_count += 1
                    device_results['packages'].append({'package': package, 'status': 'granted'})

                except Exception as e:
                    failed_count += 1
                    device_results['packages'].append({'package': package, 'status': 'failed', 'error': str(e)})

            results.append(device_results)

        return jsonify({
            'status': 'success',
            'message': f'Granted permissions to {granted_count} Instagram app(s) across {len(devices)} device(s)',
            'devices': len(devices),
            'granted': granted_count,
            'failed': failed_count,
            'details': results
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@profile_automation_bp.route('/processor_status', methods=['GET'])
def get_processor_status():
    """
    Get status of batch processor and pending tasks
    """
    try:
        from profile_automation_db import get_pending_tasks
        from collections import defaultdict

        pending = get_pending_tasks()

        # Group by device
        tasks_by_device = defaultdict(int)
        for task in pending:
            tasks_by_device[task['device_serial']] += 1

        return jsonify({
            'status': 'success',
            'total_pending': len(pending),
            'devices': len(tasks_by_device),
            'tasks_by_device': dict(tasks_by_device),
            'is_running': False  # TODO: Check if process is actually running
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@profile_automation_bp.route('/statistics', methods=['GET'])
def get_statistics():
    """
    Get statistics for profile automation dashboard
    Similar to login automation statistics
    """
    try:
        from profile_automation_db import get_all_tasks, get_profile_history

        all_tasks = get_all_tasks()

        # Count by status
        stats = {
            'total': len(all_tasks),
            'pending': len([t for t in all_tasks if t['status'] == 'pending']),
            'processing': len([t for t in all_tasks if t['status'] == 'processing']),
            'completed': len([t for t in all_tasks if t['status'] == 'completed']),
            'failed': len([t for t in all_tasks if t['status'] == 'failed'])
        }

        # Get recent history count
        history = get_profile_history(limit=100)
        stats['history_count'] = len(history)
        stats['recent_successful'] = len([h for h in history if h.get('success', False)])

        return jsonify({
            'status': 'success',
            'statistics': stats
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@profile_automation_bp.route('/tasks/<int:task_id>/log', methods=['GET'])
def get_task_log(task_id):
    """
    Return the worker log lines for one profile-automation task. Reads
    dashboard_stdout.log (where ParallelProfileProcessor + AutomatedProfileManager
    print) and isolates the block(s) between `Processing Task ID: <id>` and
    the next `Processing Task ID:` line. Multiple attempts (restart) get
    concatenated with separators.
    """
    from pathlib import Path
    log_path = Path(__file__).parent / 'logs' / 'dashboard_stdout.log'
    if not log_path.exists():
        return jsonify({'status': 'error',
                        'message': f'log file not found: {log_path}'}), 404

    # Tail last 80 MB to keep memory bounded — most recent attempt(s) are at the
    # end. A typical task block is ~50–200 lines so this gives lots of headroom.
    MAX_TAIL = 80 * 1024 * 1024
    try:
        size = log_path.stat().st_size
        with open(log_path, 'rb') as f:
            if size > MAX_TAIL:
                f.seek(size - MAX_TAIL)
                f.readline()  # skip partial first line
            data = f.read()
        text = data.decode('utf-8', errors='replace')
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

    marker = f"Processing Task ID: {task_id}"
    blocks = []
    cur = None
    for line in text.splitlines():
        if 'Processing Task ID:' in line:
            # boundary
            if marker in line:
                if cur is not None:
                    blocks.append(cur)
                cur = [line]
            else:
                if cur is not None:
                    blocks.append(cur)
                    cur = None
        elif cur is not None:
            cur.append(line)
    if cur is not None:
        blocks.append(cur)

    if not blocks:
        return jsonify({'status': 'success', 'task_id': task_id,
                        'attempts': 0,
                        'log': f'No log lines found for task {task_id}. '
                               f'Either the task has not started yet, '
                               f'or its log is older than the {MAX_TAIL//(1024*1024)} MB tail '
                               f'window we read.',
                        'lines': 0})

    sep = '\n\n──── new attempt ────\n\n'
    rendered = sep.join('\n'.join(b) for b in blocks)
    return jsonify({'status': 'success', 'task_id': task_id,
                    'attempts': len(blocks),
                    'lines': sum(len(b) for b in blocks),
                    'log': rendered})


@profile_automation_bp.route('/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    """
    Delete a profile automation task
    """
    try:
        from profile_automation_db import delete_task as db_delete_task

        db_delete_task(task_id)

        return jsonify({
            'status': 'success',
            'message': f'Task {task_id} deleted'
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@profile_automation_bp.route('/tasks/<int:task_id>/restart', methods=['POST'])
def restart_task(task_id):
    """
    Restart a profile automation task by resetting status to pending
    """
    try:
        from profile_automation_db import update_task_status

        update_task_status(task_id, 'pending', error_message=None)

        return jsonify({
            'status': 'success',
            'message': f'Task {task_id} restarted'
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@profile_automation_bp.route('/single-action', methods=['POST'])
def single_account_action():
    """Change bio and/or profile picture on ONE account immediately.

    Stops the device's bot engine first (so it doesn't fight us on the same
    u2 session), runs the profile action on just that account, then restarts
    the engine if it was running. Used by the per-account "Quick Profile Edit"
    in the shared account panel (account detail + mother detail).

    Body: { device_serial, username, bio? , uploaded_picture_id? }
    """
    import sys, time as _t, sqlite3 as _sq
    from pathlib import Path as _P
    data = request.get_json() or {}
    device_serial = (data.get('device_serial') or '').strip()
    username = (data.get('username') or '').strip()
    bio = (data.get('bio') or '').strip() or None
    pic_id = data.get('uploaded_picture_id') or None

    if not device_serial or not username:
        return jsonify({'status': 'error', 'message': 'device_serial and username are required'}), 400
    if not bio and not pic_id:
        return jsonify({'status': 'error', 'message': 'Provide a bio and/or a picture to change'}), 400

    sys.path.insert(0, str(_P(__file__).parent / 'uiAutomator'))
    from profile_automation_db import add_profile_update_task, get_pending_tasks
    from parallel_profile_processor import ParallelProfileProcessor

    # Resolve the account's instagram package from phone_farm.db
    pkg = 'com.instagram.android'
    try:
        _pf = str(_P(__file__).parent.parent / 'db' / 'phone_farm.db')
        _con = _sq.connect(_pf)
        _r = _con.execute("SELECT instagram_package FROM accounts WHERE device_serial=? AND username=?",
                          (device_serial, username)).fetchone()
        _con.close()
        if _r and _r[0]:
            pkg = _r[0]
    except Exception as e:
        print(f"[single-action] package lookup failed: {e}")

    # 1) Create the single profile-update task
    task_id = add_profile_update_task(
        device_serial=device_serial, instagram_package=pkg, username=username,
        new_bio=bio, profile_picture_id=pic_id)

    # 2) Stop the device's bot engine (so it releases the u2 session)
    was_running = False
    try:
        from bot_launcher_routes import _find_process_for_serial, _kill_pid, _launch_device
        procs = _find_process_for_serial(device_serial, use_cache=False)
        was_running = len(procs) > 0
        for p in procs:
            _kill_pid(p['pid'])
        if was_running:
            _t.sleep(4)  # let atx-agent / u2 fully release the device
    except Exception as e:
        print(f"[single-action] engine stop failed: {e}")

    # 3) Run ONLY this task
    result = {'successful': 0, 'failed': 0, 'total': 0}
    err = None
    try:
        pending = [t for t in get_pending_tasks()
                   if t.get('device_serial') == device_serial and t.get('id') == task_id]
        if pending:
            proc = ParallelProfileProcessor()
            proc.run_parallel(pending, max_parallel_devices=1)
            result = proc.results
    except Exception as e:
        import traceback
        err = str(e)
        print(f"[single-action] processing failed: {e}\n{traceback.format_exc()}")
    finally:
        # 4) Restart the engine if we stopped it
        if was_running:
            try:
                from bot_launcher_routes import _launch_device
                _launch_device(device_serial)
            except Exception as e:
                print(f"[single-action] engine restart failed: {e}")

    ok = (result.get('successful', 0) > 0) and not err
    return jsonify({
        'status': 'success' if ok else 'error',
        'task_id': task_id,
        'engine_restarted': was_running,
        'stats': result,
        'message': (err or ('Done — engine restarted' if was_running else 'Done')),
    }), (200 if ok else 500)


@profile_automation_bp.route('/tasks/process-parallel', methods=['POST'])
def process_tasks_parallel():
    """
    Process all pending profile tasks using parallel processor (FASTER)

    Different devices will process simultaneously in parallel threads.
    Same device tasks will still run sequentially.

    POST body (optional):
    {
        "device_serial": "10.1.10.183_5555",  // Optional filter
        "max_tasks": 10,  // Optional limit
        "max_devices": 3  // Optional: limit parallel devices
    }

    Returns:
        {
            "status": "success",
            "stats": {
                "successful": 13,
                "failed": 1,
                "total": 14
            },
            "duration": 78
        }
    """
    try:
        import sys
        from pathlib import Path
        import time

        # Import parallel processor
        sys.path.insert(0, str(Path(__file__).parent / 'uiAutomator'))
        from parallel_profile_processor import ParallelProfileProcessor
        from profile_automation_db import get_pending_tasks
        from instagram_automation import disconnect_device

        data = request.get_json() or {}

        # Get pending tasks
        pending_tasks = get_pending_tasks()

        # Filter by device if specified
        if data.get('device_serial'):
            pending_tasks = [t for t in pending_tasks if t['device_serial'] == data['device_serial']]

        # Limit tasks if specified
        if data.get('max_tasks'):
            pending_tasks = pending_tasks[:data['max_tasks']]

        if not pending_tasks:
            return jsonify({
                'status': 'success',
                'message': 'No pending tasks',
                'stats': {
                    'successful': 0,
                    'failed': 0,
                    'total': 0
                },
                'duration': 0
            })

        # Create processor and run in parallel mode
        processor = ParallelProfileProcessor()

        start_time = time.time()
        processor.run_parallel(
            pending_tasks,
            max_parallel_devices=data.get('max_devices')
        )
        end_time = time.time()

        duration = int(end_time - start_time)

        return jsonify({
            'status': 'success',
            'stats': processor.results,
            'duration': duration,
            'message': f'Processed {processor.results["total"]} tasks in {duration} seconds'
        })

    except Exception as e:
        import traceback
        return jsonify({
            'status': 'error',
            'message': str(e),
            'traceback': traceback.format_exc()
        }), 500


@profile_automation_bp.route('/tasks/clear', methods=['POST'])
def clear_completed_tasks():
    """
    Clear completed profile tasks

    POST body:
    {
        "days_old": 7  // Optional, default 7
    }
    """
    try:
        from profile_automation_db import clear_old_tasks

        data = request.get_json() or {}
        days_old = data.get('days_old', 7)

        deleted_count = clear_old_tasks(days_old)

        return jsonify({
            'status': 'success',
            'message': f'Cleared {deleted_count} completed tasks',
            'deleted_count': deleted_count
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@profile_automation_bp.route('/history', methods=['GET'])
def get_history():
    """
    Get profile automation history
    """
    try:
        from profile_automation_db import get_profile_history

        limit = request.args.get('limit', 50, type=int)
        history = get_profile_history(limit=limit)

        return jsonify({
            'status': 'success',
            'history': history
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


# ═══════════════════════════════════════════════════════════════════════
# V2 ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════

@profile_automation_bp.route('/accounts-with-details', methods=['GET'])
def get_accounts_with_details():
    """
    Get all accounts with details: current bio, pfp info, device name, tags, work hours.
    Merges data from phone_farm.db accounts + account_settings.
    """
    try:
        from pathlib import Path
        import json

        phone_farm_db = Path(__file__).parent.parent / "db" / "phone_farm.db"
        conn = sqlite3.connect(str(phone_farm_db), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get all accounts with settings and device info
        cursor.execute("""
            SELECT
                a.id, a.device_serial, a.username, a.password, a.email,
                a.status, a.instagram_package, a.tag as account_tag,
                d.device_name, d.device_serial as d_serial, d.device_group,
                s.settings_json
            FROM accounts a
            LEFT JOIN devices d ON a.device_serial = d.device_serial
            LEFT JOIN account_settings s ON a.id = s.account_id
            ORDER BY a.device_serial, a.username
        """)

        accounts = []
        for row in cursor.fetchall():
            account = dict(row)
            tags = ''
            enable_tags = False
            work_hours = None
            mother_mention = ''

            if account.get('settings_json'):
                try:
                    settings = json.loads(account['settings_json'])
                    tags = settings.get('tags', '')
                    enable_tags = settings.get('enable_tags', False)
                    mother_mention = settings.get('sharepost_mention', '')
                    work_hours = {
                        'start': settings.get('work_hours_start'),
                        'end': settings.get('work_hours_end')
                    }
                except (json.JSONDecodeError, Exception):
                    pass

            # Clean up - don't send settings_json blob to frontend
            account.pop('settings_json', None)
            account.pop('d_serial', None)
            account['app_package'] = account.pop('instagram_package', 'com.instagram.android')
            account['tags'] = tags
            account['account_tag'] = account.get('account_tag', '')
            account['device_group'] = account.get('device_group', '')
            account['enable_tags'] = enable_tags
            account['mother_mention'] = mother_mention
            account['work_hours'] = work_hours

            accounts.append(account)

        conn.close()

        return jsonify({
            'status': 'success',
            'accounts': accounts,
            'total': len(accounts)
        })

    except Exception as e:
        import traceback
        return jsonify({
            'status': 'error',
            'message': str(e),
            'traceback': traceback.format_exc()
        }), 500


@profile_automation_bp.route('/preview-ai', methods=['POST'])
def preview_ai_generation():
    """
    Preview AI-generated usernames/bios without creating tasks.
    Returns samples for review before committing.
    """
    try:
        data = request.get_json()
        preview_type = data.get('type', 'username')  # 'username' or 'bio'
        count = min(data.get('count', 5), 10)
        mother_account = data.get('mother_account', '')
        mother_bio = data.get('mother_bio', '')
        name_shortcuts = data.get('name_shortcuts', [])
        tone = data.get('tone', 'default')

        # Get AI config
        ai_config = get_ai_config()
        api_key = data.get('ai_api_key') or ai_config.get('api_key', '')

        username_source = data.get('username_source', 'creative')
        exclude_private = data.get('exclude_private', True)

        samples = []

        if preview_type == 'username':
            if username_source == 'creative' and name_shortcuts:
                # Use creative generation
                tba = TagBasedAutomation()
                for i in range(count):
                    username = tba._generate_creative_username(name_shortcuts, i, exclude_private=exclude_private)
                    samples.append(username)
            elif api_key and mother_account:
                # Use AI - single batch call instead of N separate calls
                generator = CampaignAIGenerator(api_key=api_key, provider='openai')
                try:
                    samples = generator.generator.generate_usernames_batch(
                        mother_account, count=count, name_shortcuts=name_shortcuts
                    )
                except Exception as e:
                    print(f"AI batch generation failed: {e}")
                    # Fallback
                    from ai_profile_generator import AIProfileGenerator
                    gen = AIProfileGenerator()
                    samples = [gen._generate_username_fallback(mother_account or 'user', index=i) for i in range(count)]
            else:
                # Fallback
                from ai_profile_generator import AIProfileGenerator
                gen = AIProfileGenerator()
                for i in range(count):
                    samples.append(gen._generate_username_fallback(mother_account or 'user', index=i))
        elif preview_type == 'bio':
            if api_key and mother_account:
                generator = CampaignAIGenerator(api_key=api_key, provider='openai')
                for i in range(count):
                    bio = generator.generator.generate_bio(mother_account, mother_bio, account_number=i+1)
                    samples.append(bio)
            else:
                from ai_profile_generator import AIProfileGenerator
                gen = AIProfileGenerator()
                for i in range(count):
                    samples.append(gen._generate_bio_fallback(mother_bio))

        return jsonify({
            'status': 'success',
            'preview_type': preview_type,
            'samples': samples
        })

    except Exception as e:
        import traceback
        return jsonify({
            'status': 'error',
            'message': str(e),
            'traceback': traceback.format_exc()
        }), 500


@profile_automation_bp.route('/execution-status', methods=['GET'])
def get_execution_status():
    """
    Get enriched task status for live execution dashboard.
    Returns all tasks (not just pending) with rich status info.
    """
    try:
        from profile_automation_db import get_all_tasks
        from collections import defaultdict

        all_tasks = get_all_tasks()

        stats = {
            'pending': 0,
            'processing': 0,
            'completed': 0,
            'failed': 0,
            'total': len(all_tasks)
        }

        tasks_enriched = []
        for task in all_tasks:
            status = task.get('status', 'pending')
            # Normalize status: 'in_progress' → 'processing'
            if status == 'in_progress':
                status = 'processing'
            stats[status] = stats.get(status, 0) + 1

            # Build actions list
            actions = []
            if task.get('new_username'):
                actions.append('username')
            if task.get('new_bio'):
                actions.append('bio')
            if task.get('profile_picture_id'):
                actions.append('picture')

            tasks_enriched.append({
                'id': task['id'],
                'device_serial': task['device_serial'],
                'username': task.get('username', ''),
                'instagram_package': task.get('instagram_package', ''),
                'new_username': task.get('new_username'),
                'new_bio': task.get('new_bio'),
                'profile_picture_id': task.get('profile_picture_id'),
                'picture_filename': task.get('filename'),
                'status': status,
                'error_message': task.get('error_message'),
                'created_at': task.get('created_at'),
                'updated_at': task.get('updated_at'),
                'completed_at': task.get('completed_at'),
                'mother_account': task.get('mother_account'),
                'actions': actions
            })

        return jsonify({
            'status': 'success',
            'stats': stats,
            'tasks': tasks_enriched
        })

    except Exception as e:
        import traceback
        return jsonify({
            'status': 'error',
            'message': str(e),
            'traceback': traceback.format_exc()
        }), 500


@profile_automation_bp.route('/upload-picture', methods=['POST'])
def upload_picture():
    """
    Upload profile picture via drag&drop.
    Saves to uiAutomator/profile_pictures/uploaded/ and registers in DB.
    """
    try:
        from profile_automation_db import add_profile_picture, PROFILE_PICTURES_DIR

        if 'file' not in request.files:
            return jsonify({'status': 'error', 'message': 'No file uploaded'}), 400

        file = request.files['file']
        if not file.filename:
            return jsonify({'status': 'error', 'message': 'Empty filename'}), 400

        # Validate extension
        allowed_ext = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed_ext:
            return jsonify({'status': 'error', 'message': f'Invalid file type: {ext}'}), 400

        # Save to uploaded folder
        upload_dir = PROFILE_PICTURES_DIR / "uploaded"
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        import time as _time
        filename = f"{_time.time()}{ext}"
        save_path = upload_dir / filename
        file.save(str(save_path))

        # Get gender from form data
        gender = request.form.get('gender', 'neutral')

        # Register in DB
        pic_id = add_profile_picture(
            filename=filename,
            original_path=str(save_path),
            category='uploaded',
            gender=gender,
            notes='Uploaded via V2 dashboard'
        )

        return jsonify({
            'status': 'success',
            'picture_id': pic_id,
            'filename': filename,
            'message': 'Picture uploaded successfully'
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@profile_automation_bp.route('/picture/<path:filename>', methods=['GET'])
def serve_picture(filename):
    """Serve profile pictures as thumbnails"""
    from flask import send_from_directory
    from profile_automation_db import PROFILE_PICTURES_DIR

    # Check in subdirectories
    for subdir in ['uploaded', 'female', 'male', 'neutral', '']:
        pic_path = PROFILE_PICTURES_DIR / subdir / filename if subdir else PROFILE_PICTURES_DIR / filename
        if pic_path.exists():
            return send_from_directory(str(pic_path.parent), filename)

    return jsonify({'status': 'error', 'message': 'Picture not found'}), 404


@profile_automation_bp.route('/pictures-with-files', methods=['GET'])
def get_pictures_with_files():
    """
    Get profile pictures from both DB and filesystem scan.
    Returns pictures with their serve URLs.
    """
    try:
        from profile_automation_db import get_profile_pictures, PROFILE_PICTURES_DIR

        gender = request.args.get('gender')
        pictures = get_profile_pictures(gender=gender)

        # Also scan filesystem for any not-yet-imported pictures
        all_files = []
        for subdir in ['uploaded', 'female', 'male', 'neutral']:
            dir_path = PROFILE_PICTURES_DIR / subdir
            if dir_path.exists():
                for f in dir_path.iterdir():
                    if f.is_file() and f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.gif', '.webp'}:
                        all_files.append({
                            'filename': f.name,
                            'subfolder': subdir,
                            'url': f'/api/profile_automation/picture/{f.name}',
                            'size': f.stat().st_size
                        })

        # Enrich DB pictures with URLs
        for pic in pictures:
            pic['url'] = f'/api/profile_automation/picture/{pic["filename"]}'

        return jsonify({
            'status': 'success',
            'pictures': pictures,
            'filesystem_files': all_files
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@profile_automation_bp.route('/tasks/process-parallel-async', methods=['POST'])
def process_tasks_parallel_async():
    """
    Start parallel processing in background thread.
    Returns immediately, poll /execution-status for progress.
    """
    try:
        import threading
        from pathlib import Path

        data = request.get_json() or {}

        # Import required modules
        sys.path.insert(0, str(Path(__file__).parent / 'uiAutomator'))
        from parallel_profile_processor import ParallelProfileProcessor
        from profile_automation_db import get_pending_tasks

        # Get pending tasks
        pending_tasks = get_pending_tasks()

        # Filter by device if specified
        if data.get('device_serial'):
            pending_tasks = [t for t in pending_tasks if t['device_serial'] == data['device_serial']]

        if data.get('max_tasks'):
            pending_tasks = pending_tasks[:data['max_tasks']]

        if not pending_tasks:
            return jsonify({
                'status': 'success',
                'message': 'No pending tasks',
                'task_count': 0
            })

        def run_processor():
            try:
                processor = ParallelProfileProcessor()
                processor.run_parallel(
                    pending_tasks,
                    max_parallel_devices=data.get('max_devices')
                )
            except Exception as e:
                print(f"[ProfileAutomation] Async processor error: {e}")

        thread = threading.Thread(target=run_processor, daemon=True)
        thread.start()

        return jsonify({
            'status': 'success',
            'message': f'Started processing {len(pending_tasks)} tasks in background',
            'task_count': len(pending_tasks)
        })

    except Exception as e:
        import traceback
        return jsonify({
            'status': 'error',
            'message': str(e),
            'traceback': traceback.format_exc()
        }), 500


@profile_automation_bp.route('/tasks/stop-execution', methods=['POST'])
def stop_execution():
    """
    Hard stop: signal all processing threads to stop after current task finishes.
    Remaining pending tasks stay pending for re-run.
    """
    try:
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent / 'uiAutomator'))
        from parallel_profile_processor import ParallelProfileProcessor

        ParallelProfileProcessor.request_stop()

        return jsonify({
            'status': 'success',
            'message': 'Stop signal sent. Processing will halt after current task completes.'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@profile_automation_bp.route('/tasks/retry-failed', methods=['POST'])
def retry_failed_tasks():
    """Reset all failed tasks back to pending"""
    try:
        from profile_automation_db import get_all_tasks, update_task_status

        all_tasks = get_all_tasks()
        retried = 0

        for task in all_tasks:
            if task['status'] == 'failed':
                update_task_status(task['id'], 'pending', error_message=None)
                retried += 1

        return jsonify({
            'status': 'success',
            'retried': retried,
            'message': f'{retried} tasks reset to pending'
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@profile_automation_bp.route('/tasks/clear-completed', methods=['POST'])
def clear_completed_tasks_v2():
    """Delete all completed tasks"""
    try:
        from profile_automation_db import PROFILE_AUTOMATION_DB

        conn = _get_pa_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM profile_updates WHERE status = 'completed'")
        deleted = cursor.rowcount
        conn.commit()
        conn.close()

        return jsonify({
            'status': 'success',
            'deleted': deleted,
            'message': f'{deleted} completed tasks cleared'
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@profile_automation_bp.route('/bio_templates', methods=['POST'])
def add_template():
    """Add a new bio template"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        bio_text = data.get('bio_text', '').strip()
        category = data.get('category', 'general')

        if not name or not bio_text:
            return jsonify({'status': 'error', 'message': 'Name and bio_text are required'}), 400

        template_id = add_bio_template(name, bio_text, category)
        if template_id:
            return jsonify({'status': 'success', 'template_id': template_id})
        else:
            return jsonify({'status': 'error', 'message': 'Template with this name already exists'}), 409

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# Instructions for integration into simple_app.py
"""
To add these routes to your simple_app.py:

1. Add import at the top of simple_app.py:
   from profile_automation_routes import profile_automation_bp

2. Register blueprint after app creation:
   app.register_blueprint(profile_automation_bp)

3. Now you can call these endpoints:
   - GET  /api/profile_automation/tags
   - POST /api/profile_automation/tags
   - GET  /api/profile_automation/accounts/<tag_name>
   - POST /api/profile_automation/accounts/tag
   - POST /api/profile_automation/accounts/tag/bulk
   - POST /api/profile_automation/campaigns
   - POST /api/profile_automation/campaigns/<id>/execute
   - POST /api/profile_automation/quick_campaign (RECOMMENDED - One-click automation!)
   - GET  /api/profile_automation/tasks
   - And more...

   Unique Personas Mode endpoints:
   - POST /api/profile_automation/generate-personas
   - POST /api/profile_automation/regenerate-single-persona
   - POST /api/profile_automation/save-manifest
   - POST /api/profile_automation/execute-personas
   - GET  /api/profile_automation/persona-status
   - POST /api/profile_automation/download-stock-photos
   - GET  /api/profile_automation/pic-category-files
"""


# ═══════════════════════════════════════════════════════════════════════
# UNIQUE PERSONAS MODE ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════

@profile_automation_bp.route('/generate-personas', methods=['POST'])
def generate_personas_endpoint():
    """
    Generate unique persona assignments for selected accounts.

    POST body:
    {
        "account_ids": [1, 2, 3, ...],
        "gender_split": 0.7,
        "age_range": [18, 28]
    }

    Returns preview data (username, bio, pic_category per account).
    Ensures NO duplicate usernames across all assignments.
    """
    try:
        from persona_generator import generate_personas, get_pic_category_stats, get_gender_stats

        data = request.get_json()
        account_ids = data.get('account_ids', [])
        gender_split = data.get('gender_split', 0.7)
        age_range = data.get('age_range', [18, 28])

        if not account_ids:
            return jsonify({'status': 'error', 'message': 'No account IDs provided'}), 400

        # Generate persona assignments
        assignments = generate_personas(
            account_ids=account_ids,
            gender_split=gender_split,
            age_range=age_range
        )

        # Get account details from DB to enrich assignments
        phone_farm_db = Path(__file__).parent.parent / "db" / "phone_farm.db"
        conn = sqlite3.connect(str(phone_farm_db), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Build lookup
        if account_ids:
            placeholders = ','.join('?' * len(account_ids))
            cursor.execute(f"""
                SELECT a.id, a.username, a.device_serial, d.device_name
                FROM accounts a
                LEFT JOIN devices d ON a.device_serial = d.device_serial
                WHERE a.id IN ({placeholders})
            """, account_ids)

            account_lookup = {}
            for row in cursor.fetchall():
                account_lookup[row['id']] = {
                    'current_username': row['username'],
                    'device_serial': row['device_serial'],
                    'device_name': row['device_name'] or row['device_serial']
                }
            conn.close()

            # Enrich assignments
            for a in assignments:
                info = account_lookup.get(a['account_id'], {})
                a['current_username'] = info.get('current_username', '')
                a['device_serial'] = info.get('device_serial', '')
                a['device_name'] = info.get('device_name', '')

        return jsonify({
            'status': 'success',
            'assignments': assignments,
            'stats': {
                'total': len(assignments),
                'gender': get_gender_stats(assignments),
                'pic_categories': get_pic_category_stats(assignments),
            }
        })

    except Exception as e:
        import traceback
        return jsonify({
            'status': 'error',
            'message': str(e),
            'traceback': traceback.format_exc()
        }), 500


@profile_automation_bp.route('/regenerate-single-persona', methods=['POST'])
def regenerate_single_persona_endpoint():
    """
    Regenerate a single persona assignment (for the "regenerate" button per row).

    POST body:
    {
        "gender": "female",
        "existing_usernames": ["username1", "username2", ...]
    }
    """
    try:
        from persona_generator import regenerate_single

        data = request.get_json()
        gender = data.get('gender', 'female')
        existing_usernames = set(data.get('existing_usernames', []))

        result = regenerate_single(gender=gender, existing_usernames=existing_usernames)

        return jsonify({
            'status': 'success',
            **result
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@profile_automation_bp.route('/save-manifest', methods=['POST'])
def save_manifest_endpoint():
    """
    Save the reviewed/edited persona assignments to a manifest file.

    POST body:
    {
        "assignments": [
            {
                "account_id": 1,
                "device_serial": "...",
                "current_username": "...",
                "new_username": "...",
                "new_bio": "...",
                "pic_category": "...",
                "gender": "female",
                "persona_name": "..."
            },
            ...
        ]
    }
    """
    try:
        data = request.get_json()
        assignments = data.get('assignments', [])

        if not assignments:
            return jsonify({'status': 'error', 'message': 'No assignments provided'}), 400

        manifest = {
            'campaign': 'unique_personas',
            'created': datetime.now().isoformat(),
            'version': '2.0',
            'total_accounts': len(assignments),
            'assignments': assignments
        }

        # Save to data directory
        manifest_path = Path(__file__).parent.parent / "data" / "persona_manifest_active.json"
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        return jsonify({
            'status': 'success',
            'message': f'Manifest saved with {len(assignments)} assignments',
            'path': str(manifest_path)
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@profile_automation_bp.route('/execute-personas', methods=['POST'])
def execute_personas_endpoint():
    """
    Create profile_update tasks for all persona assignments.

    POST body:
    {
        "assignments": [...],
        "options": {
            "change_username": true,
            "change_bio": true,
            "change_picture": true,
            "delay_between_changes": 10,
            "batch_size": 15,
            "delay_between_batches": 10
        }
    }
    """
    try:
        from profile_automation_db import PROFILE_AUTOMATION_DB
        import random as _random

        data = request.get_json()
        assignments = data.get('assignments', [])
        options = data.get('options', {})

        if not assignments:
            return jsonify({'status': 'error', 'message': 'No assignments provided'}), 400

        change_username = options.get('change_username', True)
        change_bio = options.get('change_bio', True)
        change_picture = options.get('change_picture', True)

        # ── PHASE 1: Read-only — gather all data with NO write locks ──
        phone_farm_db = Path(__file__).parent.parent / "db" / "phone_farm.db"
        farm_conn = sqlite3.connect(str(phone_farm_db), timeout=30)
        farm_conn.execute("PRAGMA journal_mode=WAL")
        farm_conn.execute("PRAGMA busy_timeout=30000")
        farm_conn.row_factory = sqlite3.Row

        # Pre-fetch all account packages in one query
        account_ids = [a.get('account_id') for a in assignments if a.get('account_id')]
        pkg_map = {}
        if account_ids:
            placeholders = ','.join('?' * len(account_ids))
            for row in farm_conn.execute(
                f"SELECT id, instagram_package FROM accounts WHERE id IN ({placeholders})",
                account_ids
            ):
                pkg_map[row['id']] = row['instagram_package']
        farm_conn.close()

        # Base path for stock profile pictures
        stock_pics_base = Path(__file__).parent.parent / "data" / "profile_pics"

        # Build all rows in memory first (no DB connection held)
        pic_rows = []    # (filename, path, category, gender, notes) — for profile_pictures table
        task_rows = []   # (device_serial, username, pkg, new_user, new_bio, pic_placeholder, mother)

        for assignment in assignments:
            account_id = assignment.get('account_id')
            device_serial = assignment.get('device_serial', '')
            current_username = assignment.get('current_username', '')
            instagram_package = pkg_map.get(account_id, 'com.instagram.android')

            new_username = assignment.get('new_username') if change_username else None
            new_bio = assignment.get('new_bio') if change_bio else None

            # Pick a profile picture file (no DB access yet)
            needs_picture = False
            if change_picture:
                pic_category = assignment.get('pic_category', 'face_selfie')
                gender = assignment.get('gender', 'neutral')

                candidates = []
                for g in [gender, 'neutral'] if gender != 'neutral' else ['neutral']:
                    d = stock_pics_base / pic_category / g
                    if d.is_dir():
                        candidates = list(d.glob('*.jpg')) + list(d.glob('*.jpeg')) + list(d.glob('*.png'))
                        if candidates:
                            break

                if not candidates:
                    pic_dir_any = stock_pics_base / pic_category
                    if pic_dir_any.is_dir():
                        for sub in pic_dir_any.iterdir():
                            if sub.is_dir():
                                candidates = list(sub.glob('*.jpg')) + list(sub.glob('*.jpeg')) + list(sub.glob('*.png'))
                                if candidates:
                                    break

                if candidates:
                    chosen = _random.choice(candidates)
                    pic_rows.append((
                        chosen.name, str(chosen.resolve()), pic_category, gender,
                        f'Auto-assigned for persona: {current_username}'
                    ))
                    needs_picture = True

            if new_username or new_bio or needs_picture:
                task_rows.append((
                    device_serial, current_username, instagram_package,
                    new_username, new_bio, needs_picture
                ))

        # ── PHASE 2: Single fast write transaction with retry ──
        tasks_created = 0
        max_retries = 5

        for attempt in range(1, max_retries + 1):
            try:
                conn = sqlite3.connect(str(PROFILE_AUTOMATION_DB), timeout=60)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=60000")
                cursor = conn.cursor()

                # Insert all picture rows and collect their IDs
                pic_ids = []
                for pr in pic_rows:
                    cursor.execute(
                        "INSERT INTO profile_pictures (filename, original_path, category, gender, style, notes) VALUES (?,?,?,?,NULL,?)",
                        pr
                    )
                    pic_ids.append(cursor.lastrowid)

                # Insert task rows, linking picture IDs
                pic_idx = 0
                for tr in task_rows:
                    device_serial, username, pkg, new_user, new_bio, needs_pic = tr
                    pic_id = None
                    if needs_pic and pic_idx < len(pic_ids):
                        pic_id = pic_ids[pic_idx]
                        pic_idx += 1

                    cursor.execute("""
                        INSERT INTO profile_updates
                        (device_serial, username, instagram_package, new_username, new_bio,
                         profile_picture_id, mother_account, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, 'unique_personas', 'pending', datetime('now'))
                    """, (device_serial, username, pkg, new_user, new_bio, pic_id))
                    tasks_created += 1

                conn.commit()
                conn.close()
                break  # Success!

            except sqlite3.OperationalError as e:
                if 'locked' in str(e) and attempt < max_retries:
                    import time as _time
                    wait = attempt * 2
                    print(f"[execute-personas] DB locked, retry {attempt}/{max_retries} in {wait}s...")
                    try:
                        conn.close()
                    except Exception:
                        pass
                    _time.sleep(wait)
                else:
                    raise

        return jsonify({
            'status': 'success',
            'tasks_created': tasks_created,
            'message': f'Created {tasks_created} profile update tasks'
        })

    except Exception as e:
        import traceback
        return jsonify({
            'status': 'error',
            'message': str(e),
            'traceback': traceback.format_exc()
        }), 500


@profile_automation_bp.route('/persona-status', methods=['GET'])
def persona_status_endpoint():
    """
    Get progress of persona execution: how many done, pending, failed.
    """
    try:
        from profile_automation_db import get_all_tasks

        all_tasks = get_all_tasks()

        # Filter to persona tasks only (mother_account = 'unique_personas')
        persona_tasks = [t for t in all_tasks if t.get('mother_account') == 'unique_personas']

        stats = {
            'total': len(persona_tasks),
            'pending': len([t for t in persona_tasks if t['status'] == 'pending']),
            'processing': len([t for t in persona_tasks if t['status'] in ('processing', 'in_progress')]),
            'completed': len([t for t in persona_tasks if t['status'] == 'completed']),
            'failed': len([t for t in persona_tasks if t['status'] == 'failed']),
        }

        return jsonify({
            'status': 'success',
            'stats': stats
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@profile_automation_bp.route('/save-api-key', methods=['POST'])
def save_api_key():
    """Save an API key to data/api_keys.json."""
    try:
        import json as _json
        data = request.get_json()
        provider = data.get('provider', '')
        key = data.get('key', '').strip()

        if not provider or not key:
            return jsonify({'status': 'error', 'message': 'provider and key required'}), 400

        keys_path = Path(__file__).parent.parent / "data" / "api_keys.json"
        existing = {}
        if keys_path.exists():
            existing = _json.loads(keys_path.read_text(encoding='utf-8'))

        existing[provider] = key
        keys_path.write_text(_json.dumps(existing, indent=2), encoding='utf-8')

        return jsonify({'status': 'success', 'message': f'{provider} key saved'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@profile_automation_bp.route('/get-api-keys', methods=['GET'])
def get_api_keys():
    """Get saved API keys (masked for display, full for form pre-fill)."""
    try:
        import json as _json
        keys_path = Path(__file__).parent.parent / "data" / "api_keys.json"
        if not keys_path.exists():
            return jsonify({})

        keys = _json.loads(keys_path.read_text(encoding='utf-8'))
        # Return full keys (they go into password fields anyway)
        return jsonify({
            'unsplash': keys.get('unsplash', ''),
            'pexels': keys.get('pexels', ''),
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@profile_automation_bp.route('/download-stock-photos', methods=['POST'])
def download_stock_photos_endpoint():
    """
    Trigger stock photo download script.

    POST body:
    {
        "api_keys": {
            "unsplash": "...",
            "pexels": "..."
        },
        "count_per_category": 50
    }
    """
    try:
        import subprocess
        import threading

        data = request.get_json()
        api_keys = data.get('api_keys', {})
        count_per_category = data.get('count_per_category', 50)

        script_path = Path(__file__).parent.parent / "data" / "download_profile_pics.py"

        if not script_path.exists():
            return jsonify({
                'status': 'error',
                'message': 'download_profile_pics.py not found in data directory'
            }), 404

        # Build environment with API keys — fall back to saved keys
        import json as _json
        saved_keys = {}
        keys_path = Path(__file__).parent.parent / "data" / "api_keys.json"
        if keys_path.exists():
            try:
                saved_keys = _json.loads(keys_path.read_text(encoding='utf-8'))
            except:
                pass

        env = os.environ.copy()
        unsplash = api_keys.get('unsplash') or saved_keys.get('unsplash', '')
        pexels = api_keys.get('pexels') or saved_keys.get('pexels', '')
        if unsplash:
            env['UNSPLASH_API_KEY'] = unsplash
        if pexels:
            env['PEXELS_API_KEY'] = pexels

        # Calculate female/male counts (70/30 split)
        total = count_per_category * 7  # ~7 stock categories
        female_count = int(total * 0.7)
        male_count = total - female_count

        # Run in background thread
        def run_download():
            try:
                log_path = script_path.parent / "download_log.txt"
                with open(log_path, "w", encoding="utf-8") as log_file:
                    subprocess.run(
                        ['python', '-u', str(script_path),
                         '--female', str(female_count),
                         '--male', str(male_count)],
                        cwd=str(script_path.parent),
                        env=env,
                        timeout=1200,
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                    )
            except Exception as e:
                print(f"[PersonaGenerator] Stock photo download error: {e}")

        thread = threading.Thread(target=run_download, daemon=True)
        thread.start()

        return jsonify({
            'status': 'success',
            'message': f'Started downloading stock photos ({count_per_category} per category)'
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@profile_automation_bp.route('/download-stock-photos/status', methods=['GET'])
def download_stock_photos_status():
    """Check stock photo download progress."""
    try:
        pics_dir = Path(__file__).parent.parent / "data" / "profile_pics"
        log_path = Path(__file__).parent.parent / "data" / "download_log.txt"
        manifest_path = pics_dir / "download_manifest.json"

        result = {'running': False, 'total_files': 0, 'by_folder': {}, 'log_tail': ''}

        # Count files — check category/gender structure
        if pics_dir.exists():
            for item in pics_dir.iterdir():
                if item.is_dir():
                    cat_count = 0
                    for sub in item.rglob('*'):
                        if sub.is_file() and sub.suffix.lower() in ('.jpg', '.png', '.jpeg'):
                            cat_count += 1
                    if cat_count > 0:
                        result['by_folder'][item.name] = cat_count
                        result['total_files'] += cat_count

        # Read last lines of log
        if log_path.exists():
            try:
                lines = log_path.read_text(encoding='utf-8', errors='replace').strip().split('\n')
                result['log_tail'] = '\n'.join(lines[-10:])
                result['running'] = not any(x in result['log_tail'] for x in ['DOWNLOAD COMPLETE', 'No API keys', 'error'])
            except:
                pass

        # Check manifest
        if manifest_path.exists():
            try:
                import json as _json
                m = _json.loads(manifest_path.read_text(encoding='utf-8'))
                result['downloaded'] = len(m.get('downloaded', []))
                result['failed'] = len(m.get('failed', []))
            except:
                pass

        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@profile_automation_bp.route('/pic-category-files', methods=['GET'])
def get_pic_category_files():
    """
    Get available profile picture files per category.
    Scans the profile_pics directory structure.
    """
    try:
        from profile_automation_db import PROFILE_PICTURES_DIR

        categories = {
            'face_selfie': {'target_pct': 30, 'count': 0, 'files': []},
            'full_body_lifestyle': {'target_pct': 20, 'count': 0, 'files': []},
            'aesthetic_artistic': {'target_pct': 15, 'count': 0, 'files': []},
            'mirror_selfie_gym': {'target_pct': 15, 'count': 0, 'files': []},
            'back_view_silhouette': {'target_pct': 10, 'count': 0, 'files': []},
            'other_diverse': {'target_pct': 10, 'count': 0, 'files': []},
        }

        # Check profile_pics directory for categorized photos
        pic_base = Path(__file__).parent.parent / "data" / "profile_pics"

        for cat_name in categories:
            cat_dir = pic_base / cat_name
            if cat_dir.exists():
                files = []
                # Check direct files in category folder
                for f in cat_dir.iterdir():
                    if f.is_file() and f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}:
                        files.append(f.name)
                # Check gender subfolders (female/male/neutral)
                for gender_sub in ['female', 'male', 'neutral']:
                    gender_dir = cat_dir / gender_sub
                    if gender_dir.exists():
                        for f in gender_dir.iterdir():
                            if f.is_file() and f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}:
                                files.append(f'{gender_sub}/{f.name}')
                categories[cat_name]['count'] = len(files)
                categories[cat_name]['files'] = files[:20]  # First 20 for preview

        # Also check the uploaded directory in uiAutomator
        uploaded_dir = PROFILE_PICTURES_DIR / "uploaded" if PROFILE_PICTURES_DIR.exists() else None
        uploaded_count = 0
        if uploaded_dir and uploaded_dir.exists():
            uploaded_count = len([f for f in uploaded_dir.iterdir()
                                  if f.is_file() and f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}])

        return jsonify({
            'status': 'success',
            'categories': categories,
            'uploaded_count': uploaded_count,
            'total_available': sum(c['count'] for c in categories.values()) + uploaded_count
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
