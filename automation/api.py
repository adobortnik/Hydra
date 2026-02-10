"""
Automation API Blueprint
=========================
REST endpoints for the dashboard to control device automation.

Endpoints:
    POST /api/automation/connect/<device_serial>       - Connect to a device
    POST /api/automation/disconnect/<device_serial>     - Disconnect from a device
    POST /api/automation/open-instagram/<account_id>    - Open IG for an account
    GET  /api/automation/screenshot/<device_serial>     - Get device screenshot
    GET  /api/automation/status                         - All device statuses
    GET  /api/automation/status/<device_serial>         - Single device status
    POST /api/automation/login/<account_id>             - Trigger login
    POST /api/automation/scheduler/start                - Start task scheduler
    POST /api/automation/scheduler/stop                 - Stop task scheduler
    GET  /api/automation/scheduler/status               - Scheduler status

  Profile Automation:
    POST /api/automation/profile/task                   - Create a profile update task
    GET  /api/automation/profile/tasks                  - List profile tasks
    POST /api/automation/profile/execute/<task_id>      - Execute a profile task
    GET  /api/automation/profile/pictures               - List profile pictures
    POST /api/automation/profile/pictures               - Upload a profile picture
    GET  /api/automation/profile/bio-templates           - List bio templates
    POST /api/automation/profile/bio-templates           - Create a bio template
    GET  /api/automation/profile/history                - Profile change history
"""

import threading
import logging
import time
import datetime
import json
from flask import Blueprint, jsonify, request, Response

log = logging.getLogger(__name__)

automation_bp = Blueprint('automation', __name__)


# ------------------------------------------------------------------
#  Device Connection
# ------------------------------------------------------------------

@automation_bp.route('/api/automation/connect/<device_serial>', methods=['POST'])
def api_connect_device(device_serial):
    """Connect to a device. Runs in background thread."""
    from automation.device_connection import get_connection

    conn = get_connection(device_serial)

    if conn.status == 'connected':
        return jsonify({
            'success': True,
            'message': 'Already connected',
            'status': conn.get_status_dict(),
        })

    # Connect in background to avoid blocking the request
    timeout = request.json.get('timeout', 45) if request.is_json else 45

    def _do_connect():
        conn.connect(timeout=timeout)

    thread = threading.Thread(target=_do_connect, daemon=True)
    thread.start()

    return jsonify({
        'success': True,
        'message': 'Connection initiated',
        'status': conn.get_status_dict(),
    })


@automation_bp.route('/api/automation/disconnect/<device_serial>', methods=['POST'])
def api_disconnect_device(device_serial):
    """Disconnect from a device."""
    from automation.device_connection import disconnect_device

    disconnect_device(device_serial)
    return jsonify({'success': True, 'message': 'Disconnected'})


# ------------------------------------------------------------------
#  Device Status
# ------------------------------------------------------------------

@automation_bp.route('/api/automation/status')
def api_automation_status():
    """Get status of all devices (from DB + live connection state)."""
    from automation.device_connection import get_all_statuses, get_device_status
    from automation.actions.helpers import get_db

    # Get all devices from DB
    try:
        conn = get_db()
        db_devices = conn.execute(
            "SELECT device_serial, device_name, ip_address FROM devices ORDER BY device_serial"
        ).fetchall()
        conn.close()
    except Exception:
        db_devices = []

    # Get live connection statuses (only devices that have been connected)
    live = {s['device_serial']: s for s in get_all_statuses()}

    # Merge: show ALL DB devices, overlay live status if available
    devices = []
    for row in db_devices:
        serial = row['device_serial']
        if serial in live:
            dev = live[serial]
        else:
            dev = {
                'device_serial': serial,
                'status': 'disconnected',
                'connected': False,
            }
        dev['device_name'] = row['device_name'] or ''
        dev['ip_address'] = row['ip_address'] or ''
        devices.append(dev)

    return jsonify({
        'success': True,
        'devices': devices,
    })


@automation_bp.route('/api/automation/status/<device_serial>')
def api_device_status(device_serial):
    """Get status of a single device."""
    from automation.device_connection import get_device_status
    return jsonify({
        'success': True,
        'status': get_device_status(device_serial),
    })


# ------------------------------------------------------------------
#  Screenshot
# ------------------------------------------------------------------

@automation_bp.route('/api/automation/screenshot/<device_serial>')
def api_screenshot(device_serial):
    """
    Get a device screenshot.
    Query params:
        format=base64  -> JSON with base64 data (default)
        format=png     -> Raw PNG image
    """
    fmt = request.args.get('format', 'base64')

    if fmt == 'png':
        from automation.device_connection import take_screenshot_bytes
        png_bytes = take_screenshot_bytes(device_serial)
        if png_bytes:
            return Response(png_bytes, mimetype='image/png')
        return jsonify({'success': False, 'error': 'Screenshot failed'}), 500

    else:
        from automation.device_connection import take_screenshot
        b64 = take_screenshot(device_serial)
        if b64:
            return jsonify({
                'success': True,
                'screenshot': b64,
                'format': 'base64',
                'content_type': 'image/png',
            })
        return jsonify({'success': False, 'error': 'Screenshot failed'}), 500


# ------------------------------------------------------------------
#  Open Instagram
# ------------------------------------------------------------------

@automation_bp.route('/api/automation/open-instagram/<int:account_id>', methods=['POST'])
def api_open_instagram(account_id):
    """Open Instagram for a specific account (using its package + activity)."""
    from db.models import get_connection as db_conn, row_to_dict
    from automation.device_connection import get_connection
    from automation.instagram_actions import InstagramActions
    from automation.actions.helpers import get_account_settings

    conn = db_conn()
    row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    conn.close()

    if not row:
        return jsonify({'success': False, 'error': 'Account not found'}), 404

    acct = row_to_dict(row)
    serial = acct['device_serial']
    package = acct.get('instagram_package', 'com.instagram.android')

    # Get activity from account settings app_cloner field
    activity = None
    try:
        settings = get_account_settings(account_id)
        app_cloner = settings.get('app_cloner', '')
        if app_cloner and '/' in str(app_cloner) and str(app_cloner) != 'None':
            parts = str(app_cloner).split('/', 1)
            if parts[0] == package and len(parts) > 1:
                activity = parts[1]
    except Exception:
        pass

    dev_conn = get_connection(serial)
    device = dev_conn.ensure_connected()

    if not device:
        return jsonify({
            'success': False,
            'error': 'Device not connected',
            'device_serial': serial,
        }), 503

    ig = InstagramActions(device, serial)
    opened = ig.open_instagram(package, activity=activity)
    screen = ig.detect_screen_state() if opened else 'unknown'

    return jsonify({
        'success': opened,
        'account': acct['username'],
        'device_serial': serial,
        'instagram_package': package,
        'activity': activity,
        'screen_state': screen,
    })


# ------------------------------------------------------------------
#  Login
# ------------------------------------------------------------------

@automation_bp.route('/api/automation/login/<int:account_id>', methods=['POST'])
def api_login(account_id):
    """
    Trigger login for an account.
    Runs in background thread, returns immediately with task status.
    """
    from db.models import get_connection as db_conn, row_to_dict

    conn = db_conn()
    row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    conn.close()

    if not row:
        return jsonify({'success': False, 'error': 'Account not found'}), 404

    acct = row_to_dict(row)
    serial = acct['device_serial']

    if not acct.get('password'):
        return jsonify({'success': False, 'error': 'No password stored'}), 400

    # Run login in background
    def _do_login():
        from automation.login import login_from_db
        result = login_from_db(serial, account_id)
        log.info("Login result for %s: %s", acct['username'], result)

        # Update login_history in DB
        import datetime, json
        conn = db_conn()
        conn.execute("""
            INSERT INTO login_history
                (device_serial, instagram_package, username, login_type,
                 success, two_fa_used, challenge_encountered, error_details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            serial,
            acct.get('instagram_package', 'com.instagram.android'),
            acct['username'],
            result.get('login_type', 'unknown'),
            1 if result.get('success') else 0,
            1 if result.get('two_fa_used') else 0,
            1 if result.get('challenge_encountered') else 0,
            result.get('error'),
        ))
        conn.commit()
        conn.close()

    thread = threading.Thread(target=_do_login, daemon=True)
    thread.start()

    return jsonify({
        'success': True,
        'message': 'Login initiated',
        'account': acct['username'],
        'device_serial': serial,
        'instagram_package': acct.get('instagram_package'),
    })


# ------------------------------------------------------------------
#  Batch Connect (DISABLED — production safety)
# ------------------------------------------------------------------

@automation_bp.route('/api/automation/connect-all', methods=['POST'])
def api_connect_all():
    """DISABLED: Only JACK 1 (10.1.11.4_5555) is safe for dev use."""
    return jsonify({
        'success': False,
        'error': 'Batch connect disabled. Only JACK 1 (10.1.11.4_5555) is available for development.',
    }), 403


# ------------------------------------------------------------------
#  Scheduler Control
# ------------------------------------------------------------------

@automation_bp.route('/api/automation/scheduler/start', methods=['POST'])
def api_scheduler_start():
    """Start the task scheduler."""
    from automation.scheduler import get_scheduler
    sched = get_scheduler()
    sched.start()
    return jsonify({'success': True, 'running': sched.is_running})


@automation_bp.route('/api/automation/scheduler/stop', methods=['POST'])
def api_scheduler_stop():
    """Stop the task scheduler."""
    from automation.scheduler import get_scheduler
    sched = get_scheduler()
    sched.stop()
    return jsonify({'success': True, 'running': sched.is_running})


@automation_bp.route('/api/automation/scheduler/status')
def api_scheduler_status():
    """Get scheduler status."""
    from automation.scheduler import get_scheduler
    sched = get_scheduler()
    return jsonify({
        'success': True,
        'running': sched.is_running,
    })


# ------------------------------------------------------------------
#  Profile Automation
# ------------------------------------------------------------------

@automation_bp.route('/api/automation/profile/task', methods=['POST'])
def api_profile_create_task():
    """Create a profile update task."""
    from db.models import get_connection as db_conn
    import datetime, json

    data = request.json or {}
    device_serial = data.get('device_serial')
    account_id = data.get('account_id')
    instagram_package = data.get('instagram_package', 'com.instagram.android')
    username = data.get('username')
    new_username = data.get('new_username')
    new_bio = data.get('new_bio')
    profile_picture_id = data.get('profile_picture_id')

    if not device_serial:
        # Try to resolve from account_id
        if account_id:
            conn = db_conn()
            row = conn.execute("SELECT device_serial, username, instagram_package FROM accounts WHERE id=?",
                               (account_id,)).fetchone()
            conn.close()
            if row:
                device_serial = row['device_serial']
                username = username or row['username']
                instagram_package = data.get('instagram_package') or row['instagram_package']
            else:
                return jsonify({'success': False, 'error': 'Account not found'}), 404
        else:
            return jsonify({'success': False, 'error': 'device_serial or account_id required'}), 400

    if not any([new_username, new_bio, profile_picture_id]):
        return jsonify({'success': False, 'error': 'At least one change required (new_username, new_bio, or profile_picture_id)'}), 400

    now = datetime.datetime.now().isoformat()
    conn = db_conn()
    conn.execute("""
        INSERT INTO profile_updates
            (device_serial, instagram_package, username, new_username, new_bio,
             profile_picture_id, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
    """, (device_serial, instagram_package, username, new_username, new_bio,
          profile_picture_id, now, now))
    task_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'task_id': task_id,
        'device_serial': device_serial,
        'username': username,
    })


@automation_bp.route('/api/automation/profile/tasks')
def api_profile_list_tasks():
    """List profile update tasks."""
    from db.models import get_connection as db_conn, row_to_dict

    status_filter = request.args.get('status')
    device_filter = request.args.get('device_serial')
    limit = int(request.args.get('limit', 50))

    conn = db_conn()
    q = "SELECT * FROM profile_updates WHERE 1=1"
    params = []
    if status_filter:
        q += " AND status=?"
        params.append(status_filter)
    if device_filter:
        q += " AND device_serial=?"
        params.append(device_filter)
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(q, params).fetchall()
    conn.close()

    return jsonify({
        'success': True,
        'tasks': [row_to_dict(r) for r in rows],
        'count': len(rows),
    })


@automation_bp.route('/api/automation/profile/execute/<int:task_id>', methods=['POST'])
def api_profile_execute(task_id):
    """Execute a profile update task. Runs in background."""
    from db.models import get_connection as db_conn, row_to_dict

    conn = db_conn()
    row = conn.execute("SELECT * FROM profile_updates WHERE id=?", (task_id,)).fetchone()
    conn.close()

    if not row:
        return jsonify({'success': False, 'error': 'Task not found'}), 404

    task = row_to_dict(row)
    if task['status'] not in ('pending', 'failed'):
        return jsonify({'success': False, 'error': 'Task status is %s, expected pending/failed' % task['status']}), 400

    serial = task['device_serial']

    def _run():
        from automation.profile import run_profile_task
        result = run_profile_task(serial, task_id)
        log.info("Profile task %d result: %s", task_id, result)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return jsonify({
        'success': True,
        'message': 'Profile task %d started' % task_id,
        'device_serial': serial,
    })


@automation_bp.route('/api/automation/profile/pictures', methods=['GET'])
def api_profile_pictures_list():
    """List profile pictures from the library."""
    from db.models import get_connection as db_conn, row_to_dict

    gender = request.args.get('gender')
    category = request.args.get('category')

    conn = db_conn()
    q = "SELECT * FROM profile_pictures WHERE 1=1"
    params = []
    if gender:
        q += " AND gender=?"
        params.append(gender)
    if category:
        q += " AND category=?"
        params.append(category)
    q += " ORDER BY times_used ASC, uploaded_at DESC"

    rows = conn.execute(q, params).fetchall()
    conn.close()

    return jsonify({
        'success': True,
        'pictures': [row_to_dict(r) for r in rows],
        'count': len(rows),
    })


@automation_bp.route('/api/automation/profile/pictures', methods=['POST'])
def api_profile_pictures_add():
    """Add a profile picture record to the library."""
    from db.models import get_connection as db_conn
    import datetime

    data = request.json or {}
    filename = data.get('filename')
    original_path = data.get('original_path')
    category = data.get('category')
    gender = data.get('gender')
    description = data.get('description')

    if not filename or not original_path:
        return jsonify({'success': False, 'error': 'filename and original_path required'}), 400

    now = datetime.datetime.now().isoformat()
    conn = db_conn()
    conn.execute("""
        INSERT INTO profile_pictures (filename, original_path, category, gender, description, uploaded_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (filename, original_path, category, gender, description, now))
    pic_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'id': pic_id})


@automation_bp.route('/api/automation/profile/bio-templates', methods=['GET'])
def api_bio_templates_list():
    """List bio templates."""
    from db.models import get_connection as db_conn, row_to_dict

    category = request.args.get('category')
    conn = db_conn()
    if category:
        rows = conn.execute("SELECT * FROM bio_templates WHERE category=? ORDER BY times_used ASC",
                            (category,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM bio_templates ORDER BY times_used ASC").fetchall()
    conn.close()

    return jsonify({
        'success': True,
        'templates': [row_to_dict(r) for r in rows],
        'count': len(rows),
    })


@automation_bp.route('/api/automation/profile/bio-templates', methods=['POST'])
def api_bio_templates_add():
    """Create a bio template."""
    from db.models import get_connection as db_conn
    import datetime

    data = request.json or {}
    name = data.get('name')
    bio_text = data.get('bio_text')
    category = data.get('category')

    if not name or not bio_text:
        return jsonify({'success': False, 'error': 'name and bio_text required'}), 400

    now = datetime.datetime.now().isoformat()
    conn = db_conn()
    try:
        conn.execute(
            "INSERT INTO bio_templates (name, bio_text, category, created_at) VALUES (?, ?, ?, ?)",
            (name, bio_text, category, now))
        bio_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400
    conn.close()

    return jsonify({'success': True, 'id': bio_id})


@automation_bp.route('/api/automation/profile/history')
def api_profile_history():
    """Get profile change history from task_history."""
    from db.models import get_connection as db_conn, row_to_dict

    limit = int(request.args.get('limit', 50))
    conn = db_conn()
    rows = conn.execute("""
        SELECT * FROM task_history
        WHERE task_type LIKE 'profile_%'
        ORDER BY completed_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    return jsonify({
        'success': True,
        'history': [row_to_dict(r) for r in rows],
        'count': len(rows),
    })


# ------------------------------------------------------------------
#  Bot Engine Control
# ------------------------------------------------------------------

@automation_bp.route('/api/automation/bot/run/<int:account_id>', methods=['POST'])
def api_bot_run(account_id):
    """
    Run the bot engine for a specific account.
    Runs in a background thread, returns immediately.
    """
    from db.models import get_connection as db_conn, row_to_dict

    conn = db_conn()
    row = conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    conn.close()

    if not row:
        return jsonify({'success': False, 'error': 'Account not found'}), 404

    acct = row_to_dict(row)
    serial = acct['device_serial']

    def _run():
        from automation.bot_engine import BotEngine
        engine = BotEngine(serial, account_id)
        result = engine.run()
        log.info("Bot engine result for %s: success=%s, actions=%d, errors=%d",
                 acct['username'], result.get('success'),
                 len(result.get('actions_completed', [])),
                 len(result.get('errors', [])))

    thread = threading.Thread(target=_run, daemon=True,
                              name="Bot-%s-%s" % (serial, acct['username']))
    thread.start()

    return jsonify({
        'success': True,
        'message': 'Bot engine started',
        'account': acct['username'],
        'device_serial': serial,
    })


@automation_bp.route('/api/automation/bot/action/<int:account_id>/<action_name>', methods=['POST'])
def api_bot_single_action(account_id, action_name):
    """
    Run a single action (follow/unfollow/like/engage/scrape) for an account.
    Runs in background thread.
    """
    from db.models import get_connection as db_conn, row_to_dict

    if action_name not in ('follow', 'unfollow', 'like', 'engage', 'scrape', 'reels', 'dm', 'comment'):
        return jsonify({'success': False,
                       'error': 'Invalid action. Choose: follow, unfollow, like, engage, scrape, reels, dm, comment'}), 400

    conn = db_conn()
    row = conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    conn.close()

    if not row:
        return jsonify({'success': False, 'error': 'Account not found'}), 404

    acct = row_to_dict(row)
    serial = acct['device_serial']

    def _run():
        from automation.device_connection import get_connection
        from automation.actions.helpers import create_session, end_session, get_account_settings

        dev_conn = get_connection(serial)
        device = dev_conn.ensure_connected()
        if not device:
            log.error("[%s] Device not connected for action %s", serial, action_name)
            return

        # Open Instagram with correct package AND activity for this account
        from automation.instagram_actions import InstagramActions
        ig = InstagramActions(device, serial)
        package = acct.get('instagram_package', 'com.instagram.android')

        # Get activity from account settings app_cloner field
        activity = None
        try:
            settings = get_account_settings(account_id)
            app_cloner = settings.get('app_cloner', '')
            if app_cloner and '/' in str(app_cloner) and str(app_cloner) != 'None':
                parts = str(app_cloner).split('/', 1)
                if parts[0] == package and len(parts) > 1:
                    activity = parts[1]
        except Exception:
            pass

        ig.open_instagram(package, activity=activity)

        session_id = create_session(serial, acct['username'])

        try:
            if action_name == 'follow':
                from automation.actions.follow import FollowAction
                action = FollowAction(device, serial, acct, session_id)
            elif action_name == 'unfollow':
                from automation.actions.unfollow import UnfollowAction
                action = UnfollowAction(device, serial, acct, session_id)
            elif action_name == 'like':
                from automation.actions.like import LikeAction
                action = LikeAction(device, serial, acct, session_id)
            elif action_name == 'engage':
                from automation.actions.engage import EngageAction
                action = EngageAction(device, serial, acct, session_id)
            elif action_name == 'scrape':
                from automation.actions.scrape import ScrapeAction
                action = ScrapeAction(device, serial, acct, session_id)
            elif action_name == 'reels':
                from automation.actions.reels import ReelsAction
                action = ReelsAction(device, serial, acct, session_id)
            elif action_name == 'dm':
                from automation.actions.dm import DMAction
                action = DMAction(device, serial, acct, session_id)
            elif action_name == 'comment':
                from automation.actions.comment import CommentAction
                action = CommentAction(device, serial, acct, session_id)

            result = action.execute()
            log.info("[%s] Action %s result: %s", serial, action_name, result)
            end_session(session_id, 'completed')

        except Exception as e:
            log.error("[%s] Action %s error: %s", serial, action_name, e)
            end_session(session_id, 'error', error_details=str(e)[:500])

    thread = threading.Thread(target=_run, daemon=True,
                              name="Action-%s-%s-%s" % (serial, acct['username'], action_name))
    thread.start()

    return jsonify({
        'success': True,
        'message': '%s action started for %s' % (action_name, acct['username']),
        'account': acct['username'],
        'device_serial': serial,
        'action': action_name,
    })


# Orchestrator endpoints moved to bottom of file (expanded versions)


@automation_bp.route('/api/automation/action-history')
def api_action_history():
    """Get recent action history."""
    from db.models import get_connection as db_conn, row_to_dict

    device_serial = request.args.get('device_serial')
    username = request.args.get('username')
    action_type = request.args.get('action_type')
    limit = int(request.args.get('limit', 100))

    conn = db_conn()
    q = "SELECT * FROM action_history WHERE 1=1"
    params = []

    if device_serial:
        q += " AND device_serial=?"
        params.append(device_serial)
    if username:
        q += " AND username=?"
        params.append(username)
    if action_type:
        q += " AND action_type=?"
        params.append(action_type)

    q += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(q, params).fetchall()
    conn.close()

    return jsonify({
        'success': True,
        'history': [row_to_dict(r) for r in rows],
        'count': len(rows),
    })


@automation_bp.route('/api/automation/sessions')
def api_sessions():
    """Get recent bot sessions."""
    from db.models import get_connection as db_conn, row_to_dict

    device_serial = request.args.get('device_serial')
    limit = int(request.args.get('limit', 50))

    conn = db_conn()
    q = "SELECT * FROM account_sessions WHERE 1=1"
    params = []
    if device_serial:
        q += " AND device_serial=?"
        params.append(device_serial)
    q += " ORDER BY session_start DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(q, params).fetchall()
    conn.close()

    return jsonify({
        'success': True,
        'sessions': [row_to_dict(r) for r in rows],
        'count': len(rows),
    })


# ------------------------------------------------------------------
#  WebSocket Server Control
# ------------------------------------------------------------------

@automation_bp.route('/api/automation/ws/status')
def api_ws_status():
    """Get WebSocket server status."""
    try:
        from automation.ws_server import get_ws_status
        return jsonify({'success': True, **get_ws_status()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@automation_bp.route('/api/automation/ws/start', methods=['POST'])
def api_ws_start():
    """Start the WebSocket server."""
    try:
        from automation.ws_server import start_ws_server
        start_ws_server()
        return jsonify({'success': True, 'message': 'WebSocket server started on port 5056'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@automation_bp.route('/api/automation/ws/stop', methods=['POST'])
def api_ws_stop():
    """Stop the WebSocket server."""
    try:
        from automation.ws_server import stop_ws_server
        stop_ws_server()
        return jsonify({'success': True, 'message': 'WebSocket server stopped'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ------------------------------------------------------------------
#  ADB Devices (live scan)
# ------------------------------------------------------------------

@automation_bp.route('/api/automation/adb-devices')
def api_adb_devices():
    """List currently connected ADB devices."""
    import subprocess
    try:
        result = subprocess.run(
            ['adb', 'devices', '-l'],
            capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.strip().split('\n')[1:]
        devices = []
        for line in lines:
            if line.strip() and 'device' in line:
                parts = line.split()
                serial = parts[0]
                model = "Unknown"
                for part in parts:
                    if part.startswith('model:'):
                        model = part.split(':')[1]
                devices.append({'serial': serial, 'model': model})
        return jsonify({'success': True, 'devices': devices, 'count': len(devices)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ===================================================================
#  BOT ORCHESTRATOR — Start/Stop/Status per device
# ===================================================================

@automation_bp.route('/api/automation/orchestrator/start', methods=['POST'])
def api_orchestrator_start():
    """
    Start the device orchestrator.
    Optional JSON body: { "devices": ["10.1.11.4_5555", ...] }
    If devices is provided, only those devices are managed.
    If omitted, ALL devices are managed.
    """
    from automation.device_orchestrator import get_orchestrator
    orch = get_orchestrator()
    if orch.is_running:
        return jsonify({'success': True, 'message': 'Already running'})

    device_serials = None
    if request.is_json and request.json:
        device_serials = request.json.get('devices')

    orch.start(device_serials=device_serials)

    msg = 'Orchestrator started'
    if device_serials:
        msg += f' (restricted to {len(device_serials)} device(s))'
    return jsonify({'success': True, 'message': msg})


@automation_bp.route('/api/automation/orchestrator/stop', methods=['POST'])
def api_orchestrator_stop():
    """Stop the device orchestrator."""
    from automation.device_orchestrator import get_orchestrator
    orch = get_orchestrator()
    if not orch.is_running:
        return jsonify({'success': True, 'message': 'Already stopped'})
    orch.stop()
    return jsonify({'success': True, 'message': 'Orchestrator stopped'})


@automation_bp.route('/api/automation/orchestrator/status')
def api_orchestrator_status():
    """Get orchestrator status + all managed devices."""
    from automation.device_orchestrator import get_orchestrator
    orch = get_orchestrator()
    return jsonify({
        'success': True,
        'running': orch.is_running,
        'devices': orch.get_status() if orch.is_running else {},
    })


@automation_bp.route('/api/automation/bot/start/<device_serial>', methods=['POST'])
def api_bot_start_device(device_serial):
    """Start bot on a specific device. Orchestrator picks the right account."""
    from automation.device_orchestrator import get_orchestrator
    orch = get_orchestrator()
    if not orch.is_running:
        orch.start()
    result = orch.start_device(device_serial)
    return jsonify({
        'success': bool(result),
        'message': 'Bot started' if result else 'No active account for this device',
        'device_serial': device_serial,
    })


@automation_bp.route('/api/automation/bot/stop/<device_serial>', methods=['POST'])
def api_bot_stop_device(device_serial):
    """Stop bot on a specific device."""
    from automation.device_orchestrator import get_orchestrator
    orch = get_orchestrator()
    result = orch.stop_device(device_serial)
    return jsonify({
        'success': bool(result),
        'message': 'Bot stopped' if result else 'No bot running on this device',
        'device_serial': device_serial,
    })


@automation_bp.route('/api/automation/bot/start-all', methods=['POST'])
def api_bot_start_all():
    """Start bots on all devices that have active accounts."""
    from automation.device_orchestrator import get_orchestrator
    orch = get_orchestrator()
    if not orch.is_running:
        orch.start()
    return jsonify({
        'success': True,
        'message': 'Orchestrator started — will auto-start all devices',
    })


@automation_bp.route('/api/automation/bot/stop-all', methods=['POST'])
def api_bot_stop_all():
    """Stop all bots."""
    from automation.device_orchestrator import get_orchestrator
    orch = get_orchestrator()
    orch.stop()
    return jsonify({'success': True, 'message': 'All bots stopped'})


@automation_bp.route('/api/automation/bot/status')
def api_bot_status_all():
    """Get bot status for all devices from DB."""
    from db.models import get_connection as db_conn, row_to_dict
    conn = db_conn()
    rows = conn.execute("""
        SELECT bs.*, d.device_name
        FROM bot_status bs
        LEFT JOIN devices d ON d.device_serial = bs.device_serial
        ORDER BY bs.device_serial
    """).fetchall()
    conn.close()
    return jsonify({
        'success': True,
        'devices': [row_to_dict(r) for r in rows],
    })


# ===================================================================
#  DEAD SOURCES — Track sources that can't be found
# ===================================================================

@automation_bp.route('/api/dead-sources')
def api_dead_sources_list():
    """List all dead sources, optionally filtered by account."""
    from db.models import get_connection as db_conn, row_to_dict

    account = request.args.get('account')
    status_filter = request.args.get('status')

    conn = db_conn()
    q = "SELECT * FROM dead_sources WHERE 1=1"
    params = []

    if account:
        q += " AND account_username=?"
        params.append(account)
    if status_filter:
        q += " AND status=?"
        params.append(status_filter)

    q += " ORDER BY last_failed_at DESC"
    rows = conn.execute(q, params).fetchall()
    conn.close()

    return jsonify({
        'success': True,
        'dead_sources': [row_to_dict(r) for r in rows],
        'count': len(rows),
    })


@automation_bp.route('/api/dead-sources/count')
def api_dead_sources_count():
    """Return dead source counts per account (for badge)."""
    from db.models import get_connection as db_conn

    conn = db_conn()
    rows = conn.execute("""
        SELECT account_username, COUNT(*) as cnt
        FROM dead_sources
        WHERE status='dead'
        GROUP BY account_username
    """).fetchall()

    total_row = conn.execute(
        "SELECT COUNT(*) as cnt FROM dead_sources WHERE status='dead'"
    ).fetchone()
    conn.close()

    counts = {r['account_username']: r['cnt'] for r in rows}
    total = total_row['cnt'] if total_row else 0

    return jsonify({
        'success': True,
        'counts': counts,
        'total': total,
    })


@automation_bp.route('/api/dead-sources', methods=['DELETE'])
def api_dead_sources_delete():
    """
    Bulk delete dead sources.
    Body: {"ids": [1,2,3]}
      or: {"source_usernames": ["user1","user2"]}
      or: {"account_username": "xxx"} to delete all for an account.
    """
    from db.models import get_connection as db_conn

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'JSON body required'}), 400

    conn = db_conn()
    deleted = 0

    if 'ids' in data:
        for id_val in data['ids']:
            deleted += conn.execute(
                "DELETE FROM dead_sources WHERE id=?", (id_val,)
            ).rowcount
    elif 'source_usernames' in data:
        for src in data['source_usernames']:
            deleted += conn.execute(
                "DELETE FROM dead_sources WHERE source_username=?", (src,)
            ).rowcount
    elif 'account_username' in data:
        deleted = conn.execute(
            "DELETE FROM dead_sources WHERE account_username=?",
            (data['account_username'],)
        ).rowcount
    else:
        conn.close()
        return jsonify({'success': False, 'error': 'Provide ids, source_usernames, or account_username'}), 400

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'deleted': deleted})


@automation_bp.route('/api/dead-sources/<int:source_id>/retry', methods=['POST'])
def api_dead_sources_retry(source_id):
    """Reset a specific dead source so it gets tried again next cycle."""
    from db.models import get_connection as db_conn

    conn = db_conn()
    updated = conn.execute("""
        UPDATE dead_sources
        SET fail_count=0, status='suspect'
        WHERE id=?
    """, (source_id,)).rowcount
    conn.commit()
    conn.close()

    if updated:
        return jsonify({'success': True, 'message': 'Source reset for retry'})
    return jsonify({'success': False, 'error': 'Source not found'}), 404


@automation_bp.route('/api/dead-sources/cleanup', methods=['POST'])
def api_dead_sources_cleanup():
    """
    Remove dead sources from actual source lists AND delete from dead_sources table.
    Body: {"account_username": "xxx"} or {"account_id": 123}
    Removes all dead sources for that account from account_sources table.
    """
    from db.models import get_connection as db_conn

    data = request.get_json() or {}
    account_username = data.get('account_username')
    account_id = data.get('account_id')

    conn = db_conn()

    # Resolve account_id if username provided
    if account_username and not account_id:
        row = conn.execute(
            "SELECT id FROM accounts WHERE username=?", (account_username,)
        ).fetchone()
        if row:
            account_id = row['id']

    if not account_username:
        if account_id:
            row = conn.execute(
                "SELECT username FROM accounts WHERE id=?", (account_id,)
            ).fetchone()
            if row:
                account_username = row['username']

    if not account_username:
        conn.close()
        return jsonify({'success': False, 'error': 'Could not resolve account'}), 400

    # Get dead sources for this account
    dead_rows = conn.execute(
        "SELECT source_username FROM dead_sources WHERE account_username=? AND status='dead'",
        (account_username,)
    ).fetchall()
    dead_usernames = [r['source_username'] for r in dead_rows]

    sources_removed = 0
    if account_id and dead_usernames:
        # Remove from account_sources (all source_type variants)
        for src in dead_usernames:
            sources_removed += conn.execute(
                "DELETE FROM account_sources WHERE account_id=? AND value=?",
                (account_id, src)
            ).rowcount

    # Delete from dead_sources table
    dead_deleted = conn.execute(
        "DELETE FROM dead_sources WHERE account_username=? AND status='dead'",
        (account_username,)
    ).rowcount

    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'sources_removed_from_lists': sources_removed,
        'dead_records_deleted': dead_deleted,
        'dead_usernames': dead_usernames,
    })


# ===================================================================
#  SOURCE MANAGEMENT — CRUD for account_sources
# ===================================================================

@automation_bp.route('/api/automation/sources/<int:account_id>')
def api_get_sources(account_id):
    """Get all sources for an account, grouped by type."""
    from db.models import get_connection as db_conn, row_to_dict
    conn = db_conn()
    rows = conn.execute(
        "SELECT * FROM account_sources WHERE account_id=? ORDER BY source_type, value",
        (account_id,)
    ).fetchall()
    conn.close()

    # Group by type
    grouped = {}
    for r in rows:
        d = row_to_dict(r)
        stype = d['source_type']
        if stype not in grouped:
            grouped[stype] = []
        grouped[stype].append(d)

    return jsonify({
        'success': True,
        'account_id': account_id,
        'sources': grouped,
        'total': len(rows),
    })


@automation_bp.route('/api/automation/sources/<int:account_id>', methods=['POST'])
def api_add_source(account_id):
    """Add a source for an account. Body: {source_type, value} or {source_type, values: [...]}"""
    from db.models import get_connection as db_conn
    import datetime

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'JSON body required'}), 400

    source_type = data.get('source_type', 'sources')
    values = data.get('values', [])
    if not values and data.get('value'):
        values = [data['value']]

    if not values:
        return jsonify({'success': False, 'error': 'No values provided'}), 400

    conn = db_conn()
    now = datetime.datetime.now().isoformat()
    added = 0

    for val in values:
        val = val.strip().lstrip('@')  # Remove leading @
        if not val:
            continue
        try:
            conn.execute(
                "INSERT OR IGNORE INTO account_sources (account_id, source_type, value, created_at) VALUES (?,?,?,?)",
                (account_id, source_type, val, now)
            )
            added += 1
        except Exception as e:
            log.error("Failed to add source %s: %s", val, e)

    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'added': added,
        'source_type': source_type,
    })


@automation_bp.route('/api/automation/sources/<int:account_id>/<int:source_id>', methods=['DELETE'])
def api_delete_source(account_id, source_id):
    """Delete a specific source entry."""
    from db.models import get_connection as db_conn
    conn = db_conn()
    conn.execute(
        "DELETE FROM account_sources WHERE id=? AND account_id=?",
        (source_id, account_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@automation_bp.route('/api/automation/sources/<int:account_id>/clear', methods=['POST'])
def api_clear_sources(account_id):
    """Clear all sources of a given type for an account. Body: {source_type}"""
    from db.models import get_connection as db_conn
    data = request.get_json() or {}
    source_type = data.get('source_type')

    conn = db_conn()
    if source_type:
        conn.execute(
            "DELETE FROM account_sources WHERE account_id=? AND source_type=?",
            (account_id, source_type)
        )
    else:
        conn.execute("DELETE FROM account_sources WHERE account_id=?", (account_id,))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'source_type': source_type})


@automation_bp.route('/api/automation/sources/bulk', methods=['POST'])
def api_bulk_set_sources():
    """
    Set sources for multiple accounts at once.
    Body: {account_ids: [1,2,3], source_type: "sources", values: ["user1","user2"]}
    """
    from db.models import get_connection as db_conn
    import datetime

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'JSON body required'}), 400

    account_ids = data.get('account_ids', [])
    source_type = data.get('source_type', 'sources')
    values = data.get('values', [])
    replace = data.get('replace', False)

    if not account_ids or not values:
        return jsonify({'success': False, 'error': 'account_ids and values required'}), 400

    conn = db_conn()
    now = datetime.datetime.now().isoformat()
    total_added = 0

    for acct_id in account_ids:
        if replace:
            conn.execute(
                "DELETE FROM account_sources WHERE account_id=? AND source_type=?",
                (acct_id, source_type)
            )
        for val in values:
            val = val.strip().lstrip('@')
            if val:
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO account_sources (account_id, source_type, value, created_at) VALUES (?,?,?,?)",
                        (acct_id, source_type, val, now)
                    )
                    total_added += 1
                except Exception:
                    pass

    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'accounts_updated': len(account_ids),
        'total_added': total_added,
    })


# ===================================================================
#  REAL-TIME LOGS
# ===================================================================

@automation_bp.route('/api/automation/logs')
def api_automation_logs():
    """
    Get recent bot engine logs.
    Query params:
        limit=100       - Max entries to return
        since_id=0      - Return only entries after this ID (for polling)
        device_serial=  - Filter by device
        level=          - Filter by level (INFO, WARNING, ERROR)
        username=       - Filter by username
    """
    from automation.bot_logger import get_recent_logs

    limit = int(request.args.get('limit', 100))
    since_id = request.args.get('since_id')
    if since_id is not None:
        since_id = int(since_id)
    device_serial = request.args.get('device_serial')
    level = request.args.get('level')
    username = request.args.get('username')

    logs = get_recent_logs(
        limit=limit,
        since_id=since_id,
        device_serial=device_serial,
        level=level,
        username=username,
    )

    return jsonify({
        'success': True,
        'logs': logs,
        'count': len(logs),
        'max_id': logs[0]['id'] if logs and since_id is None else (logs[-1]['id'] if logs else 0),
    })


@automation_bp.route('/api/automation/logs/poll')
def api_automation_logs_poll():
    """
    Long-poll endpoint for log updates. Returns new entries since `since_id`.
    Designed for dashboard polling (every 1-2s).

    Query params:
        since_id=0      - Return entries after this ID
        limit=50        - Max entries per poll
        device_serial=  - Filter by device
        level=          - Filter by level
        username=       - Filter by username
    """
    from automation.bot_logger import get_recent_logs

    since_id = int(request.args.get('since_id', 0))
    limit = int(request.args.get('limit', 50))
    device_serial = request.args.get('device_serial')
    level = request.args.get('level')
    username = request.args.get('username')

    logs = get_recent_logs(
        limit=limit,
        since_id=since_id,
        device_serial=device_serial,
        level=level,
        username=username,
    )

    max_id = since_id
    if logs:
        max_id = max(entry['id'] for entry in logs)

    return jsonify({
        'success': True,
        'logs': logs,
        'count': len(logs),
        'max_id': max_id,
    })


@automation_bp.route('/api/automation/logs/stats')
def api_automation_log_stats():
    """Get log statistics for dashboard."""
    from automation.bot_logger import get_log_stats
    stats = get_log_stats()
    return jsonify({'success': True, **stats})


@automation_bp.route('/api/automation/logs/history')
def api_automation_logs_history():
    """
    Get historical logs from DB (supports pagination).
    Query params:
        limit=200, offset=0, device_serial=, level=, username=, since=
    """
    from automation.bot_logger import get_logs_from_db

    logs = get_logs_from_db(
        limit=int(request.args.get('limit', 200)),
        offset=int(request.args.get('offset', 0)),
        device_serial=request.args.get('device_serial'),
        level=request.args.get('level'),
        username=request.args.get('username'),
        since=request.args.get('since'),
    )
    return jsonify({'success': True, 'logs': logs, 'count': len(logs)})


# ===================================================================
#  ACCOUNT ROTATION / ACTIVE ACCOUNTS
# ===================================================================

@automation_bp.route('/api/automation/active-accounts')
def api_active_accounts():
    """
    Get which account is currently active on each connected device,
    and when the next rotation happens.
    """
    from automation.actions.helpers import get_db

    conn = get_db()
    current_hour = datetime.datetime.now().hour

    # Get all devices that have accounts
    devices = conn.execute("""
        SELECT DISTINCT d.device_serial, d.device_name
        FROM devices d
        JOIN accounts a ON a.device_serial = d.device_serial
        WHERE a.status = 'active'
        ORDER BY d.device_serial
    """).fetchall()

    result = []
    for dev in devices:
        serial = dev['device_serial']

        # Get all accounts for this device
        accounts = conn.execute("""
            SELECT id, username, instagram_package, start_time, end_time
            FROM accounts
            WHERE device_serial=? AND status='active'
            ORDER BY start_time ASC
        """, (serial,)).fetchall()

        active_account = None
        next_rotation = None
        next_account = None

        acct_list = [dict(a) for a in accounts]

        for acct in acct_list:
            st = int(acct['start_time']) if str(acct.get('start_time', '0')).isdigit() else 0
            et = int(acct['end_time']) if str(acct.get('end_time', '0')).isdigit() else 0

            if st == 0 and et == 0:
                continue  # Skip always-active in first pass

            in_window = False
            if st < et:
                in_window = st <= current_hour < et
            elif st > et:
                in_window = current_hour >= st or current_hour < et

            if in_window:
                active_account = acct
                # Next rotation is at end_time
                next_rotation = et
                break

        # If no time-windowed match, use always-active
        if not active_account:
            for acct in acct_list:
                st = int(acct['start_time']) if str(acct.get('start_time', '0')).isdigit() else 0
                et = int(acct['end_time']) if str(acct.get('end_time', '0')).isdigit() else 0
                if st == 0 and et == 0:
                    active_account = acct
                    next_rotation = None  # Always active, no rotation
                    break

        # Find next account after current window ends
        if next_rotation is not None:
            for acct in acct_list:
                st = int(acct['start_time']) if str(acct.get('start_time', '0')).isdigit() else 0
                et = int(acct['end_time']) if str(acct.get('end_time', '0')).isdigit() else 0
                if st == 0 and et == 0:
                    continue
                if st == next_rotation:
                    next_account = acct['username']
                    break

        result.append({
            'device_serial': serial,
            'device_name': dev['device_name'],
            'active_account': {
                'id': active_account['id'],
                'username': active_account['username'],
                'package': active_account['instagram_package'],
                'start_time': active_account.get('start_time'),
                'end_time': active_account.get('end_time'),
            } if active_account else None,
            'next_rotation_hour': next_rotation,
            'next_account': next_account,
            'total_accounts': len(acct_list),
        })

    conn.close()

    return jsonify({
        'success': True,
        'current_hour': current_hour,
        'devices': result,
    })


# ===================================================================
#  DAILY STATS & ACTION HISTORY
# ===================================================================

@automation_bp.route('/api/automation/stats/<int:account_id>')
def api_account_stats(account_id):
    """Get daily stats for an account. Query param: days=7"""
    from db.models import get_connection as db_conn, row_to_dict
    import datetime

    days = int(request.args.get('days', 7))
    since = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime('%Y-%m-%d')

    conn = db_conn()
    rows = conn.execute("""
        SELECT * FROM account_stats
        WHERE account_id=? AND date >= ?
        ORDER BY date DESC
    """, (account_id, since)).fetchall()

    # Also get today's action counts
    today = datetime.date.today().isoformat()
    acct = conn.execute("SELECT username, device_serial FROM accounts WHERE id=?", (account_id,)).fetchone()
    action_counts = {}
    if acct:
        for action_type in ('follow', 'unfollow', 'like', 'comment', 'dm', 'story_view'):
            row = conn.execute("""
                SELECT COUNT(*) as cnt FROM action_history
                WHERE device_serial=? AND username=? AND action_type=?
                  AND timestamp >= ? AND success=1
            """, (acct['device_serial'], acct['username'], action_type, today)).fetchone()
            action_counts[action_type] = row['cnt'] if row else 0

    conn.close()

    return jsonify({
        'success': True,
        'account_id': account_id,
        'stats': [row_to_dict(r) for r in rows],
        'today_actions': action_counts,
    })


@automation_bp.route('/api/automation/stats/summary')
def api_stats_summary():
    """Get summary stats across all accounts for today."""
    from db.models import get_connection as db_conn
    import datetime

    today = datetime.date.today().isoformat()
    conn = db_conn()

    # Total actions today by type
    rows = conn.execute("""
        SELECT action_type, COUNT(*) as cnt
        FROM action_history
        WHERE timestamp >= ? AND success=1
        GROUP BY action_type
    """, (today,)).fetchall()

    actions_today = {r['action_type']: r['cnt'] for r in rows}

    # Active sessions today
    sessions = conn.execute("""
        SELECT COUNT(*) as cnt FROM account_sessions
        WHERE session_start >= ?
    """, (today,)).fetchone()

    # Total accounts with actions today
    active_accounts = conn.execute("""
        SELECT COUNT(DISTINCT username) as cnt FROM action_history
        WHERE timestamp >= ? AND success=1
    """, (today,)).fetchone()

    conn.close()

    return jsonify({
        'success': True,
        'date': today,
        'actions_today': actions_today,
        'total_actions': sum(actions_today.values()),
        'sessions_today': sessions['cnt'] if sessions else 0,
        'active_accounts_today': active_accounts['cnt'] if active_accounts else 0,
    })
