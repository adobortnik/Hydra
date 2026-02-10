#!/usr/bin/env python3
"""
Flask routes for Profile Automation Dashboard Integration
Add these routes to your simple_app.py
"""

import sys
import os
from pathlib import Path

# Add uiAutomator to path (now inside dashboard folder)
sys.path.insert(0, str(Path(__file__).parent / "uiAutomator"))

from flask import Blueprint, jsonify, request
from tag_based_automation import TagBasedAutomation
from ai_profile_generator import CampaignAIGenerator
from profile_automation_db import (
    get_profile_pictures, get_bio_templates,
    get_pending_tasks, add_bio_template, add_profile_picture
)

# Import settings helper (in same directory as this file)
import sys
sys.path.insert(0, str(Path(__file__).parent))
from settings_routes import get_ai_config

# Create blueprint
profile_automation_bp = Blueprint('profile_automation', __name__, url_prefix='/api/profile_automation')

# Initialize automation
automation = TagBasedAutomation()

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

        if not all([tag, mother_account]):
            return jsonify({
                'status': 'error',
                'message': 'tag and mother_account are required'
            }), 400

        # Build strategies based on action checkboxes
        strategies = {}

        if actions.get('change_picture', True):
            # Use 'gallery_auto' strategy to automatically pick from phone gallery
            # This skips the library check and just uses first/last photo from gallery
            strategies['profile_picture'] = 'gallery_auto'

        if actions.get('change_bio', True):
            strategies['bio'] = 'ai' if use_ai else 'template'

        if actions.get('change_username', True):
            strategies['username'] = 'creative' if name_shortcuts else ('ai' if use_ai else 'variation')

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
        if selected_accounts:
            result = automation.execute_campaign_for_accounts(campaign_id, selected_accounts)
        else:
            result = automation.execute_campaign(campaign_id)

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

        conn = sqlite3.connect(settings_path)
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
"""
