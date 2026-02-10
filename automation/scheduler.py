"""
Task Scheduler
===============
Reads tasks from phone_farm.db and executes them.

Supports:
    - Task queue (pending -> running -> completed/failed)
    - Priority ordering
    - Retry logic
    - Scheduled execution times
    - Concurrent device execution (one task per device at a time)
"""

import threading
import time
import datetime
import logging
import json

log = logging.getLogger(__name__)


class TaskScheduler:
    """
    Scheduler that polls phone_farm.db for pending tasks and executes them.

    Each device runs at most one task at a time.
    Tasks are ordered by priority (higher first), then by creation time.
    """

    def __init__(self, poll_interval=10):
        """
        Args:
            poll_interval: Seconds between DB polls for new tasks
        """
        self.poll_interval = poll_interval
        self._running = False
        self._thread = None
        self._device_locks = {}  # serial -> Lock
        self._active_tasks = {}  # serial -> task_id

    def start(self):
        """Start the scheduler in a background thread."""
        if self._running:
            log.warning("Scheduler already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="TaskScheduler")
        self._thread.start()
        log.info("Task scheduler started (poll every %ds)", self.poll_interval)

    def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=30)
        log.info("Task scheduler stopped")

    @property
    def is_running(self):
        return self._running

    def _run_loop(self):
        """Main scheduler loop."""
        while self._running:
            try:
                self._poll_and_execute()
            except Exception as e:
                log.error("Scheduler error: %s", e)
            time.sleep(self.poll_interval)

    def _poll_and_execute(self):
        """Check for pending tasks and launch them."""
        from db.models import get_connection, row_to_dict

        conn = get_connection()
        now = datetime.datetime.now().isoformat()

        # Get pending tasks that are ready (no scheduled_time or scheduled_time <= now)
        rows = conn.execute("""
            SELECT * FROM tasks
            WHERE status = 'pending'
              AND (scheduled_time IS NULL OR scheduled_time <= ?)
              AND retry_count < max_retries
            ORDER BY priority DESC, created_at ASC
            LIMIT 20
        """, (now,)).fetchall()
        conn.close()

        for row in rows:
            task = row_to_dict(row)
            serial = task.get('device_serial')

            if not serial:
                continue

            # Skip if device already has an active task
            if serial in self._active_tasks:
                continue

            # Get or create device lock
            if serial not in self._device_locks:
                self._device_locks[serial] = threading.Lock()

            if self._device_locks[serial].acquire(blocking=False):
                self._active_tasks[serial] = task['id']
                thread = threading.Thread(
                    target=self._execute_task,
                    args=(task,),
                    daemon=True,
                    name=f"Task-{task['id']}-{serial}"
                )
                thread.start()
            # else: device busy, skip

    def _execute_task(self, task):
        """Execute a single task."""
        task_id = task['id']
        serial = task['device_serial']

        try:
            from db.models import get_connection as db_conn
            now = datetime.datetime.now().isoformat()

            # Mark as running
            conn = db_conn()
            conn.execute(
                "UPDATE tasks SET status='running', started_at=?, updated_at=? WHERE id=?",
                (now, now, task_id)
            )
            conn.commit()
            conn.close()

            log.info("[Task %d] Starting %s on %s", task_id, task['task_type'], serial)

            # Dispatch based on task type
            result = self._dispatch_task(task)

            # Mark result
            now = datetime.datetime.now().isoformat()
            conn = db_conn()

            if result.get('success'):
                conn.execute(
                    "UPDATE tasks SET status='completed', completed_at=?, result_json=?, updated_at=? WHERE id=?",
                    (now, json.dumps(result), now, task_id)
                )
                log.info("[Task %d] Completed successfully", task_id)
            else:
                retry = task.get('retry_count', 0) + 1
                max_retries = task.get('max_retries', 3)

                if retry >= max_retries:
                    new_status = 'failed'
                else:
                    new_status = 'pending'

                conn.execute(
                    """UPDATE tasks SET status=?, retry_count=?, result_json=?,
                       updated_at=? WHERE id=?""",
                    (new_status, retry, json.dumps(result), now, task_id)
                )
                log.warning("[Task %d] %s (retry %d/%d): %s",
                            task_id, new_status, retry, max_retries,
                            result.get('error', 'unknown'))

            # Archive to history
            started = task.get('started_at', now)
            conn.execute("""
                INSERT INTO task_history
                    (task_id, account_id, device_serial, task_type, status,
                     started_at, completed_at, params_json, result_json, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id, task.get('account_id'), serial, task['task_type'],
                'completed' if result.get('success') else 'failed',
                started, now,
                task.get('params_json', '{}'), json.dumps(result),
                result.get('error')
            ))
            conn.commit()
            conn.close()

        except Exception as e:
            log.error("[Task %d] Execution error: %s", task_id, e)
            try:
                conn = db_conn()
                now = datetime.datetime.now().isoformat()
                conn.execute(
                    "UPDATE tasks SET status='failed', result_json=?, updated_at=? WHERE id=?",
                    (json.dumps({'error': str(e)}), now, task_id)
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

        finally:
            # Release device
            self._active_tasks.pop(serial, None)
            lock = self._device_locks.get(serial)
            if lock and lock.locked():
                lock.release()

    def _dispatch_task(self, task):
        """Route task to the appropriate handler."""
        task_type = task['task_type']
        params = json.loads(task.get('params_json', '{}'))

        if task_type == 'login':
            return self._task_login(task, params)
        elif task_type == 'open_instagram':
            return self._task_open_instagram(task, params)
        elif task_type == 'screenshot':
            return self._task_screenshot(task, params)
        elif task_type == 'profile_update':
            return self._task_profile_update(task, params)
        elif task_type == 'bot_run':
            return self._task_bot_run(task, params)
        elif task_type in ('follow', 'unfollow', 'like', 'comment', 'dm', 'engage', 'story_view'):
            return self._task_bot_run(task, params)
        else:
            return {'success': False, 'error': f'Unknown task type: {task_type}'}

    def _task_login(self, task, params):
        """Execute a login task."""
        from automation.login import login_from_db
        account_id = task.get('account_id')
        serial = task['device_serial']

        if not account_id:
            return {'success': False, 'error': 'No account_id for login task'}

        return login_from_db(serial, account_id)

    def _task_open_instagram(self, task, params):
        """Open Instagram for an account."""
        from automation.device_connection import get_connection
        from automation.instagram_actions import InstagramActions

        serial = task['device_serial']
        package = params.get('instagram_package', 'com.instagram.android')

        dev_conn = get_connection(serial)
        device = dev_conn.ensure_connected()
        if not device:
            return {'success': False, 'error': 'Device not connected'}

        ig = InstagramActions(device, serial)
        if ig.open_instagram(package):
            return {'success': True, 'screen_state': ig.detect_screen_state()}
        return {'success': False, 'error': 'Failed to open Instagram'}

    def _task_screenshot(self, task, params):
        """Take a screenshot."""
        from automation.device_connection import take_screenshot
        serial = task['device_serial']
        b64 = take_screenshot(serial)
        if b64:
            return {'success': True, 'screenshot_size': len(b64)}
        return {'success': False, 'error': 'Screenshot failed'}

    def _task_profile_update(self, task, params):
        """Placeholder for profile update tasks."""
        return {'success': False, 'error': 'Profile update not yet implemented'}

    def _task_bot_run(self, task, params):
        """Run the full bot engine for a device + account."""
        from automation.bot_engine import BotEngine

        account_id = task.get('account_id')
        serial = task['device_serial']

        if not account_id:
            return {'success': False, 'error': 'No account_id for bot_run task'}

        engine = BotEngine(serial, account_id)
        return engine.run()


# Module-level singleton
_scheduler = None


def get_scheduler():
    """Get the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = TaskScheduler()
    return _scheduler
