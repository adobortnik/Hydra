"""
Job Executor — runs a single job order assignment for an account
=================================================================
Wraps existing action modules (FollowAction, LikeAction, etc.) with
job-specific parameters, then records results to the job tables.

DB tables used:
  job_orders      — the job definition (job_type, target, limits, etc.)
  job_assignments — per-account assignment (completed_count, status)
  job_history     — per-action log (success/error per execution)

Supported job_types:
  follow          — follow users from target account's follower list
  like            — like posts from target account's profile or feed
  comment         — comment on posts (uses job_orders.comment_text)
  share_to_story  — share target account's posts to story
  save_post       — save/bookmark target account's posts
  report          — report target account's profile
  dm              — send direct message to target user (uses comment_text as message)
"""

import datetime
import json
import logging
import os
import random
import time

from automation.actions.helpers import (
    action_delay, random_sleep, log_action, get_db,
    get_today_action_count, get_recently_interacted,
    get_account_settings,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB helpers for job tracking
# ---------------------------------------------------------------------------

def get_job_today_count(job_id, account_id):
    """Count successful actions done today for a specific job + account."""
    try:
        conn = get_db()
        today = datetime.date.today().isoformat()
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM job_history
            WHERE job_id = ? AND account_id = ? AND status = 'success'
              AND created_at >= ?
        """, (job_id, account_id, today)).fetchone()
        conn.close()
        return row['cnt'] if row else 0
    except Exception as e:
        log.error("Failed to get job today count: %s", e)
        return 0


def claim_job_slot(job_id):
    """
    Atomically claim a slot for this job order.
    Uses UPDATE ... WHERE completed_count < target_count to prevent overshoot.
    
    Returns:
        True if slot was claimed (ok to proceed)
        False if target already reached (stop)
    """
    try:
        conn = get_db()
        cursor = conn.execute("""
            UPDATE job_orders
            SET completed_count = completed_count + 1,
                updated_at = datetime('now')
            WHERE id = ? AND target_count > 0
              AND completed_count < target_count
              AND status != 'completed'
        """, (job_id,))
        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        if rows_affected > 0:
            log.debug("JOB #%d: Claimed slot (atomic)", job_id)
            return True
        else:
            log.info("JOB #%d: No slot available (target reached or job completed)", job_id)
            return False
    except Exception as e:
        log.error("JOB #%d: Failed to claim slot: %s", job_id, e)
        return False


def unclaim_job_slot(job_id):
    """
    Release a claimed slot (e.g., when the action fails).
    Decrements completed_count back down.
    """
    try:
        conn = get_db()
        conn.execute("""
            UPDATE job_orders
            SET completed_count = MAX(0, completed_count - 1),
                updated_at = datetime('now')
            WHERE id = ?
        """, (job_id,))
        conn.commit()
        conn.close()
        log.debug("JOB #%d: Released slot (action failed)", job_id)
    except Exception as e:
        log.error("JOB #%d: Failed to unclaim slot: %s", job_id, e)


def is_post_url(target):
    """Check if the target is an Instagram post/reel URL (not a username)."""
    return ('instagram.com' in target and
            ('/p/' in target or '/reel/' in target or '/reels/' in target or '/tv/' in target))


def open_post_via_deeplink(device, device_serial, package, url):
    """
    Open an Instagram post/reel URL via ADB deep link.
    Returns True if the post loaded successfully.
    """
    import subprocess
    adb_serial = device_serial.replace('_', ':')
    clean_url = url.split('?')[0]  # Strip query params like ?igsh=...

    # Force-stop for clean state
    subprocess.run(
        ['adb', '-s', adb_serial, 'shell', 'am', 'force-stop', package],
        capture_output=True, timeout=5
    )
    random_sleep(1, 2, label="force_stop_wait")

    # Open via deep link
    subprocess.run(
        ['adb', '-s', adb_serial, 'shell', 'am', 'start',
         '-a', 'android.intent.action.VIEW', '-d', clean_url, package],
        capture_output=True, timeout=10
    )
    random_sleep(5, 8, label="deeplink_post_load")

    # Check if post loaded (look for like button or media)
    has_content = (
        device(resourceIdMatches='.*row_feed_button_like').exists(timeout=3) or
        device(descriptionContains='Like').exists(timeout=2) or
        device(resourceIdMatches='.*media_group').exists(timeout=2)
    )

    if not has_content:
        # Scroll down in case header is blocking
        info = device.info
        h = info.get('displayHeight', 1920)
        w = info.get('displayWidth', 1080)
        device.swipe(w // 2, int(h * 0.7), w // 2, int(h * 0.3), steps=20)
        random_sleep(1, 2, label="scroll_after_deeplink")
        has_content = (
            device(resourceIdMatches='.*row_feed_button_like').exists(timeout=2) or
            device(descriptionContains='Like').exists(timeout=2)
        )

    return has_content


def wait_for_global_delay(job_id, delay_seconds):
    """
    Check last action time for this job across ALL devices using a shared
    lockfile (avoids SQLite WAL visibility issues between processes).
    
    Returns True if we waited (or no wait needed), False on error.
    """
    if delay_seconds <= 0:
        return True
    try:
        import filelock
        _has_filelock = True
    except ImportError:
        _has_filelock = False

    lock_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), 'logs')
    os.makedirs(lock_dir, exist_ok=True)
    ts_file = os.path.join(lock_dir, f'job_{job_id}_last_action.txt')
    lock_file = ts_file + '.lock'

    try:
        # Spin-lock using atomic file rename (cross-platform)
        deadline = time.time() + 60
        acquired = False
        while time.time() < deadline:
            try:
                # Atomic: create lock file (fails if exists)
                fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                acquired = True
                break
            except FileExistsError:
                # Check if lock is stale (>60s old)
                try:
                    if time.time() - os.path.getmtime(lock_file) > 60:
                        os.remove(lock_file)
                except OSError:
                    pass
                time.sleep(0.2 + random.random() * 0.3)

        if not acquired:
            log.warning("JOB #%d: Could not acquire delay lock after 60s", job_id)
            return True

        try:
            # Read last action timestamp
            last_ts = 0.0
            if os.path.exists(ts_file):
                try:
                    with open(ts_file, 'r') as f:
                        last_ts = float(f.read().strip())
                except (ValueError, OSError):
                    pass

            now = time.time()
            # last_ts = when the last bot PLANS to comment
            # We need to wait until last_ts + delay_seconds
            next_slot = last_ts + delay_seconds if last_ts > 0 else now
            wait_time = next_slot - now

            if wait_time > 0:
                log.info("JOB #%d: Global delay — next slot in %.0fs, waiting",
                         job_id, wait_time)
                # Claim our slot: we'll act at next_slot
                # Next bot will see this and queue behind us at next_slot + delay
                with open(ts_file, 'w') as f:
                    f.write(str(next_slot))
                try:
                    os.remove(lock_file)
                except OSError:
                    pass
                time.sleep(wait_time)
            else:
                # No wait needed — claim NOW as our slot
                with open(ts_file, 'w') as f:
                    f.write(str(now))
                try:
                    os.remove(lock_file)
                except OSError:
                    pass
        except Exception:
            try:
                os.remove(lock_file)
            except OSError:
                pass
            raise

        return True
    except Exception as e:
        log.error("JOB #%d: Error checking global delay: %s", job_id, e)
        return True  # Don't block on error


def record_job_action(job_id, account_id, action_type, target=None,
                      success=True, error_message=None, used_claim=False,
                      comment_used=None):
    """
    Insert a row into job_history and update counters.
    
    If used_claim=True, the job_orders.completed_count was already bumped
    atomically by claim_job_slot() — don't recalculate from assignments.
    """
    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO job_history (job_id, account_id, action_type, target,
                                     status, error_message, comment_used)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (job_id, account_id, action_type, target,
              'success' if success else 'error', error_message, comment_used))

        if success:
            # Bump assignment completed_count (per-account tracking)
            conn.execute("""
                UPDATE job_assignments
                SET completed_count = completed_count + 1,
                    last_action_at = datetime('now')
                WHERE job_id = ? AND account_id = ?
            """, (job_id, account_id))

            if not used_claim:
                # Legacy path: recalculate job_orders.completed_count from assignments
                conn.execute("""
                    UPDATE job_orders
                    SET completed_count = (
                        SELECT COALESCE(SUM(completed_count), 0)
                        FROM job_assignments WHERE job_id = ?
                    ),
                    updated_at = datetime('now')
                    WHERE id = ?
                """, (job_id, job_id))
            # else: completed_count already bumped by claim_job_slot()

            # Check if job target reached → mark completed
            conn.execute("""
                UPDATE job_orders
                SET status = 'completed', finished_at = datetime('now')
                WHERE id = ? AND target_count > 0
                  AND completed_count >= target_count
            """, (job_id,))

            # Also complete the assignment if the job is now completed
            conn.execute("""
                UPDATE job_assignments
                SET status = 'completed'
                WHERE job_id = ? AND account_id = ?
                  AND (SELECT status FROM job_orders WHERE id = ?) = 'completed'
            """, (job_id, account_id, job_id))

        conn.commit()
        conn.close()
    except Exception as e:
        log.error("Failed to record job action: %s", e)


# ---------------------------------------------------------------------------
# Main executor
# ---------------------------------------------------------------------------

class JobExecutor:
    """
    Execute a job order assignment using existing action modules.

    Parameters come from the job_orders row, not account settings.
    Results are recorded in job_history and counters updated.
    """

    def __init__(self, device, device_serial, account_info, session_id, job, assignment):
        """
        Args:
            device:         uiautomator2 device instance
            device_serial:  e.g. "10.1.11.4_5555"
            account_info:   dict from accounts table (must include 'id', 'username', 'package')
            session_id:     current session id
            job:            dict from job_orders row
            assignment:     dict from job_assignments row
        """
        self.device = device
        self.device_serial = device_serial
        self.account = account_info
        self.session_id = session_id
        self.username = account_info['username']
        self.account_id = account_info['id']
        self.job = job
        self.assignment = assignment

        self.job_id = job['id']
        self.job_type = job['job_type']
        self.target = job['target']
        self.target_count = job['target_count'] or 0
        self.daily_limit = job['limit_per_day'] or 200
        self.hourly_limit = job['limit_per_hour'] or 50
        self.comment_text = job.get('comment_text', '')
        self.priority = job.get('priority', 0)
        self.action_delay = job.get('action_delay_seconds', 0) or 0
        self.unique_comments = bool(job.get('unique_comments', 0))

    def execute(self):
        """
        Run the job action.
        Returns dict: {success, actions_done, errors, skipped, message}
        
        Uses atomic claim system when target_count > 0 to prevent overshoot.
        Respects global action_delay_seconds between actions across all devices.
        """
        result = {
            'success': False,
            'actions_done': 0,
            'errors': 0,
            'skipped': 0,
            'message': '',
        }

        # Check daily limit for this job + account
        done_today = get_job_today_count(self.job_id, self.account_id)
        if done_today >= self.daily_limit:
            msg = "Daily limit reached for job #%d (%d/%d)" % (
                self.job_id, done_today, self.daily_limit)
            log.info("[%s] JOB #%d (%s): %s",
                     self.device_serial, self.job_id, self.job_type, msg)
            result['success'] = True
            result['message'] = 'daily_limit_reached'
            return result

        # Check total target — fresh from DB
        if self.target_count > 0:
            try:
                _conn = get_db()
                _row = _conn.execute(
                    "SELECT completed_count, status FROM job_orders WHERE id = ?",
                    (self.job_id,)).fetchone()
                total_done = _row[0] if _row else 0
                job_status = _row[1] if _row else 'active'
            except Exception:
                total_done = self.job.get('completed_count', 0)
                job_status = 'active'
        else:
            total_done = self.job.get('completed_count', 0)
            job_status = 'active'

        if job_status == 'completed' or (self.target_count > 0 and total_done >= self.target_count):
            msg = "Target reached for job #%d (%d/%d)" % (
                self.job_id, total_done, self.target_count)
            log.info("[%s] JOB #%d (%s): %s",
                     self.device_serial, self.job_id, self.job_type, msg)
            result['success'] = True
            result['message'] = 'target_reached'
            return result

        remaining_daily = self.daily_limit - done_today
        remaining_total = (self.target_count - total_done) if self.target_count > 0 else 999999
        session_budget = min(remaining_daily, remaining_total)

        log.info("[%s] JOB #%d (%s): target=@%s, today=%d/%d, total=%d/%s, budget=%d",
                 self.device_serial, self.job_id, self.job_type, self.target,
                 done_today, self.daily_limit, total_done,
                 str(self.target_count) if self.target_count > 0 else 'unlimited',
                 session_budget)

        # Dispatch to the right handler
        handler = {
            'follow': self._execute_follow,
            'like': self._execute_like,
            'comment': self._execute_comment,
            'share_to_story': self._execute_share_to_story,
            'save_post': self._execute_save_post,
            'report': self._execute_report,
            'dm': self._execute_dm,
        }.get(self.job_type)

        if not handler:
            log.error("[%s] JOB #%d: Unknown job_type '%s'",
                      self.device_serial, self.job_id, self.job_type)
            result['message'] = 'unknown_job_type'
            return result

        try:
            handler_result = handler(session_budget, done_today)
            result.update(handler_result)
            result['success'] = True
        except Exception as e:
            log.error("[%s] JOB #%d (%s): Execution error: %s",
                      self.device_serial, self.job_id, self.job_type, e)
            result['errors'] += 1
            result['message'] = str(e)[:200]
            record_job_action(self.job_id, self.account_id, self.job_type,
                              self.target, success=False, error_message=str(e)[:500])

        return result

    # ------------------------------------------------------------------
    # Follow job
    # ------------------------------------------------------------------
    def _execute_follow(self, budget, done_today):
        """
        Follow the TARGET account directly.
        Each of our accounts follows the target profile (click Follow button).
        
        Flow:
          1. Atomic claim a slot (prevents overshoot with 50 parallel devices)
          2. search_user(target) → navigate to target profile
          3. Check Follow button state
          4. Click Follow if not already following
          5. VERIFY button changed to "Following" or "Requested"
          6. Unclaim if failed
        
        One follow per account per job execution.
        """
        from automation.ig_controller import IGController

        result = {'actions_done': 0, 'errors': 0, 'skipped': 0}
        pkg = self.account.get('package', 'com.instagram.androie')
        ctrl = IGController(self.device, self.device_serial, pkg)

        target = self.target.lstrip('@')

        log.info("[%s] JOB #%d (follow): Following @%s directly "
                 "(%d/%d today, %d/%s total)",
                 self.device_serial, self.job_id, target,
                 done_today, self.daily_limit,
                 self.job.get('completed_count', 0),
                 str(self.target_count) if self.target_count > 0 else '∞')

        # --- Step 0: Check if this account already completed this job (prevent unfollow) ---
        try:
            conn = get_db()
            already = conn.execute(
                "SELECT COUNT(*) FROM job_history "
                "WHERE job_id = ? AND account_id = ? AND status = 'success'",
                (self.job_id, self.account_id)
            ).fetchone()[0]
            conn.close()
            if already > 0:
                log.info("[%s] JOB #%d: Account %s already followed target, skipping "
                         "(prevent unfollow)", self.device_serial, self.job_id, self.username)
                result['skipped'] += 1
                return result
        except Exception as e:
            log.warning("[%s] JOB #%d: Could not check history: %s",
                        self.device_serial, self.job_id, e)

        # --- Step 1: Atomic claim ---
        if not claim_job_slot(self.job_id):
            log.info("[%s] JOB #%d: Target reached, skipping", 
                     self.device_serial, self.job_id)
            return result

        ctrl.ensure_app()
        time.sleep(2)
        ctrl.dismiss_popups()

        # Enable AdbKeyboard for search typing
        try:
            self.device.set_input_ime(True)
        except Exception:
            pass

        # --- Step 2: Search for target user ---
        if not ctrl.search_user(target):
            log.warning("[%s] JOB #%d: Could not find @%s",
                        self.device_serial, self.job_id, target)
            record_job_action(self.job_id, self.account_id, 'follow',
                              target, success=False,
                              error_message="Target user not found")
            unclaim_job_slot(self.job_id)
            result['errors'] += 1
            return result

        random_sleep(2, 4, label="on_target_profile")
        ctrl.dismiss_popups()

        # --- Step 3: Find Follow button ---
        follow_btn = self.device(resourceIdMatches='.*profile_header_follow_button.*')
        if not follow_btn.exists(timeout=5):
            # Fallback: text-based search
            follow_btn = self.device(text='Follow', className='android.widget.Button')
        if not follow_btn.exists(timeout=3):
            follow_btn = self.device(textMatches='(?i)^follow$', clickable=True)

        if not follow_btn.exists:
            log.warning("[%s] JOB #%d: No Follow button found on @%s profile",
                        self.device_serial, self.job_id, target)
            record_job_action(self.job_id, self.account_id, 'follow',
                              target, success=False,
                              error_message="No Follow button on profile")
            unclaim_job_slot(self.job_id)
            result['errors'] += 1
            ctrl.press_back()
            return result

        btn_text = (follow_btn.get_text() or '').strip().lower()

        # --- Already following? ---
        if btn_text in ('following', 'requested'):
            log.info("[%s] JOB #%d: Already following @%s (%s)",
                     self.device_serial, self.job_id, target, btn_text)
            # Count as success (already done)
            record_job_action(self.job_id, self.account_id, 'follow',
                              target, success=True)
            log_action(self.session_id, self.device_serial,
                       self.username, 'follow',
                       target_username=target, success=True)
            result['actions_done'] += 1
            ctrl.press_back()
            time.sleep(0.5)
            ctrl.press_back()
            return result

        # --- Step 4: Click Follow (coordinate click for reliability) ---
        if btn_text not in ('follow', 'follow back'):
            log.warning("[%s] JOB #%d: Unexpected button text '%s' on @%s",
                        self.device_serial, self.job_id, btn_text, target)
            unclaim_job_slot(self.job_id)
            result['errors'] += 1
            ctrl.press_back()
            return result

        try:
            bounds = follow_btn.info.get('bounds', {})
            cx = (bounds.get('left', 0) + bounds.get('right', 0)) // 2
            cy = (bounds.get('top', 0) + bounds.get('bottom', 0)) // 2
            if cx > 0 and cy > 0:
                self.device.click(cx, cy)
            else:
                follow_btn.click()
        except Exception as e:
            log.warning("[%s] JOB #%d: Click error: %s", 
                        self.device_serial, self.job_id, e)
            unclaim_job_slot(self.job_id)
            result['errors'] += 1
            ctrl.press_back()
            return result

        time.sleep(3)

        # --- Step 5: VERIFY follow actually worked ---
        # Re-fetch button (fresh element, not cached)
        verify_btn = self.device(resourceIdMatches='.*profile_header_follow_button.*')
        if not verify_btn.exists(timeout=3):
            verify_btn = self.device(textMatches='(?i)^(following|requested)$', clickable=True)

        verified = False
        if verify_btn.exists:
            new_text = (verify_btn.get_text() or '').strip().lower()
            if new_text in ('following', 'requested'):
                verified = True
                log.info("[%s] JOB #%d (follow): VERIFIED — @%s followed @%s (%s)",
                         self.device_serial, self.job_id, self.username, target, new_text)

        if verified:
            result['actions_done'] += 1
            record_job_action(self.job_id, self.account_id, 'follow',
                              target, success=True)
            log_action(self.session_id, self.device_serial,
                       self.username, 'follow',
                       target_username=target, success=True)
        else:
            # Follow click didn't stick — unclaim
            log.warning("[%s] JOB #%d: Follow NOT verified for @%s (button: %s)",
                        self.device_serial, self.job_id, target,
                        verify_btn.get_text() if verify_btn.exists else 'gone')
            unclaim_job_slot(self.job_id)
            record_job_action(self.job_id, self.account_id, 'follow',
                              target, success=False,
                              error_message="Follow not verified - button did not change")
            result['errors'] += 1

        # Go back to clean state
        ctrl.press_back()
        time.sleep(1)
        ctrl.press_back()
        time.sleep(0.5)

        log.info("[%s] JOB #%d (follow): Done. success=%d, errors=%d",
                 self.device_serial, self.job_id,
                 result['actions_done'], result['errors'])
        return result

    # ------------------------------------------------------------------
    # Like job
    # ------------------------------------------------------------------
    def _execute_like(self, budget, done_today):
        """
        Like posts from target account's profile or a specific post URL.
        URL target: deep link → like single post.
        Username target: search_user → open_first_post → like_post → scroll.
        """
        from automation.ig_controller import IGController
        import subprocess

        result = {'actions_done': 0, 'errors': 0, 'skipped': 0}
        pkg = self.account.get('package', 'com.instagram.androie')
        ctrl = IGController(self.device, self.device_serial, pkg)

        ctrl.ensure_app()
        ctrl.dismiss_popups()

        # Enable AdbKeyboard for search typing
        try:
            self.device.set_input_ime(True)
        except Exception:
            pass

        source = self.target.lstrip('@')
        is_post_url = ('instagram.com' in self.target and
                       ('/p/' in self.target or '/reel/' in self.target or '/reels/' in self.target))

        # For URL targets: 1 like per account. For profiles: multiple likes.
        if is_post_url:
            session_target = min(budget, 1)
        else:
            session_target = min(budget, random.randint(5, 15))

        log.info("[%s] JOB #%d (like): Liking %s "
                 "(%d/%d today, %d/%s total)",
                 self.device_serial, self.job_id,
                 f"post {source}" if is_post_url else f"posts from @{source}",
                 done_today, self.daily_limit,
                 self.job.get('completed_count', 0),
                 str(self.target_count) if self.target_count > 0 else '∞')

        if is_post_url:
            # --- Check if this account already liked this URL (prevent unlike) ---
            try:
                conn = get_db()
                already = conn.execute(
                    "SELECT COUNT(*) FROM job_history "
                    "WHERE job_id = ? AND account_id = ? AND status = 'success'",
                    (self.job_id, self.account_id)
                ).fetchone()[0]
                conn.close()
                if already > 0:
                    log.info("[%s] JOB #%d: Account %s already liked this post, skipping "
                             "(prevent unlike)", self.device_serial, self.job_id, self.username)
                    result['skipped'] += 1
                    return result
            except Exception as e:
                log.warning("[%s] JOB #%d: Could not check history: %s",
                            self.device_serial, self.job_id, e)

            # --- Deep link flow ---
            adb_serial = self.device_serial.replace('_', ':')
            clean_url = self.target.split('?')[0]
            # Force-stop IG for clean state
            subprocess.run([
                'adb', '-s', adb_serial, 'shell', 'am', 'force-stop', pkg
            ], capture_output=True, timeout=5)
            random_sleep(1, 2, label="force_stop_wait")

            deeplink_loaded = False
            d = self.device
            for dl_attempt in range(3):
                subprocess.run([
                    'adb', '-s', adb_serial, 'shell', 'am', 'start',
                    '-a', 'android.intent.action.VIEW',
                    '-d', clean_url, pkg
                ], capture_output=True, timeout=10)
                random_sleep(5, 8, label="deeplink_post_load")
                ctrl.dismiss_popups()

                empty_state = d(resourceIdMatches='.*empty_state_view_root').exists(timeout=1)

                def _find_like_btn(timeout=1):
                    return (
                        d(resourceIdMatches='.*row_feed_button_like').exists(timeout=timeout) or
                        d(resourceIdMatches='.*like_button').exists(timeout=timeout) or
                        d(resourceIdMatches='.*clips_like_button').exists(timeout=timeout) or
                        d(resourceIdMatches='.*reel_viewer_texture_view').exists(timeout=timeout) or
                        d(descriptionContains='Like').exists(timeout=timeout)
                    )

                has_like_btn = _find_like_btn(1)

                # Scroll to find like button if hidden by large image
                if not has_like_btn and not empty_state:
                    for scroll_try in range(3):
                        info = d.info
                        h = info.get('displayHeight', 1920)
                        w = info.get('displayWidth', 1080)
                        d.swipe(w // 2, int(h * 0.7), w // 2, int(h * 0.3), steps=20)
                        random_sleep(1, 2, label="scroll_find_like")
                        if _find_like_btn(1):
                            has_like_btn = True
                            log.info("[%s] JOB #%d: Found like button after scroll %d",
                                     self.device_serial, self.job_id, scroll_try + 1)
                            break

                if has_like_btn:
                    deeplink_loaded = True
                    break
                if empty_state:
                    log.warning("[%s] JOB #%d: Post empty state on attempt %d/3",
                                self.device_serial, self.job_id, dl_attempt + 1)
                    d.press('back')
                    random_sleep(2, 3, label="deeplink_retry_wait")
                else:
                    random_sleep(3, 5, label="deeplink_extra_wait")
                    has_like_btn = _find_like_btn(2)
                    if has_like_btn:
                        deeplink_loaded = True
                        break
                    log.warning("[%s] JOB #%d: No like button on attempt %d/3",
                                self.device_serial, self.job_id, dl_attempt + 1)
                    d.press('back')
                    random_sleep(2, 3, label="deeplink_retry_wait")

            log.info("[%s] JOB #%d: Opened post via deep link: %s (loaded=%s)",
                     self.device_serial, self.job_id, clean_url, deeplink_loaded)

            if not deeplink_loaded:
                log.error("[%s] JOB #%d: Post failed to load after 3 attempts",
                          self.device_serial, self.job_id)
                record_job_action(self.job_id, self.account_id, 'like',
                                  source, success=False,
                                  error_message="Post failed to load via deep link")
                result['errors'] += 1
                return result

            # Atomic claim before liking (prevents overshoot)
            if not claim_job_slot(self.job_id):
                log.info("[%s] JOB #%d: No slot available (target reached), stopping",
                         self.device_serial, self.job_id)
                d.press('back')
                return result

            # Like the post
            liked = ctrl.like_post()
            if liked:
                result['actions_done'] += 1
                record_job_action(self.job_id, self.account_id,
                                  'like', source, success=True)
                log_action(self.session_id, self.device_serial,
                           self.username, 'like',
                           target_username=source, success=True)
                log.info("[%s] JOB #%d (like): Liked post via deep link (%d/%d today)",
                         self.device_serial, self.job_id,
                         done_today + 1, self.daily_limit)
            else:
                # Might already be liked — release the slot
                unclaim_job_slot(self.job_id)
                result['skipped'] += 1
                log.info("[%s] JOB #%d (like): Post already liked or like failed",
                         self.device_serial, self.job_id)

            # Go back
            d.press('back')
            random_sleep(1, 2, label="after_like_back")

        else:
            # --- Profile search flow (original) ---
            if not ctrl.search_user(source):
                log.warning("[%s] JOB #%d: Could not find @%s",
                            self.device_serial, self.job_id, source)
                record_job_action(self.job_id, self.account_id, 'like',
                                  source, success=False,
                                  error_message="User not found")
                result['errors'] += 1
                return result

            random_sleep(2, 4, label="on_target_profile")
            ctrl.dismiss_popups()

            # Open first post in grid
            if not ctrl.open_first_post():
                log.warning("[%s] JOB #%d: Could not open first post for @%s",
                            self.device_serial, self.job_id, source)
                ctrl.press_back()
                result['errors'] += 1
                return result

            random_sleep(1, 3, label="post_opened")
            ctrl.dismiss_popups()

            # Like posts by scrolling through feed
            for i in range(session_target + 5):
                if result['actions_done'] >= session_target:
                    break

                try:
                    ctrl.dismiss_popups()
                    liked = ctrl.like_post()
                    if liked:
                        result['actions_done'] += 1
                        record_job_action(self.job_id, self.account_id,
                                          'like', source, success=True)
                        log_action(self.session_id, self.device_serial,
                                   self.username, 'like',
                                   target_username=source, success=True)
                        log.info("[%s] JOB #%d (like): Liked post %d from @%s (%d/%d today)",
                                 self.device_serial, self.job_id,
                                 result['actions_done'], source,
                                 done_today + result['actions_done'],
                                 self.daily_limit)
                        action_delay('like')
                    else:
                        result['skipped'] += 1

                    # Scroll to next post
                    ctrl.scroll_down()
                    random_sleep(1, 3, label="between_posts")

                except Exception as e:
                    log.warning("[%s] JOB #%d: Error liking post: %s",
                                self.device_serial, self.job_id, e)
                    result['errors'] += 1

            # Go back to clean state
            for _ in range(3):
                ctrl.press_back()
                time.sleep(0.5)

        log.info("[%s] JOB #%d (like): Done. Liked %d, skipped %d, errors %d",
                 self.device_serial, self.job_id,
                 result['actions_done'], result['skipped'], result['errors'])
        return result

    # ------------------------------------------------------------------
    # Comment job
    # ------------------------------------------------------------------
    def _execute_comment(self, budget, done_today):
        """
        Comment on target account's posts.
        Uses CommentAction's proven flow (set_text, _reliable_type, AI comments).
        
        If job has comment_text → uses that (with spintax).
        If comment_text is [AI] → generates via OpenAI.
        Otherwise → uses account's comment templates.
        """
        from automation.actions.comment import CommentAction
        from automation.ig_controller import Screen

        result = {'actions_done': 0, 'errors': 0, 'skipped': 0}

        # Create CommentAction — this sets up AdbKeyboard, loads templates, etc.
        comment_action = CommentAction(
            self.device, self.device_serial, self.account, self.session_id)

        # Override comment templates if job has specific text
        # Each line = separate comment option (random.choice picks one per post)
        all_comment_lines = []
        if self.comment_text and self.comment_text != '[AI]':
            lines = [l.strip() for l in self.comment_text.split('\n') if l.strip()]
            all_comment_lines = lines if lines else [self.comment_text]
            comment_action.comment_templates = list(all_comment_lines)
            # Clear settings comment_text so _get_comment uses templates (random pick per line)
            comment_action.settings['comment_text'] = ''
        elif self.comment_text == '[AI]':
            comment_action.settings['comment_text'] = '[AI]'

        # Unique comments: filter out already-used comments on this job
        chosen_comment = None
        if self.unique_comments and all_comment_lines:
            # Atomic claim: reserve a unique comment via DB lock
            _conn = get_db()
            try:
                _conn.execute("BEGIN IMMEDIATE")
                used = [r[0] for r in _conn.execute(
                    "SELECT comment_used FROM job_history WHERE job_id = ? AND comment_used IS NOT NULL",
                    (self.job_id,)
                ).fetchall()]
                available = [c for c in all_comment_lines if c not in used]
                if not available:
                    _conn.execute("COMMIT")
                    log.info("[%s] JOB #%d: All %d unique comments already used, skipping",
                             self.device_serial, self.job_id, len(all_comment_lines))
                    result['skipped'] += 1
                    return result
                chosen_comment = random.choice(available)
                # Reserve it immediately with a placeholder row
                _conn.execute("""
                    INSERT INTO job_history (job_id, account_id, action_type, target,
                                             status, comment_used)
                    VALUES (?, ?, 'comment', ?, 'reserved', ?)
                """, (self.job_id, self.account_id, self.target, chosen_comment))
                _conn.execute("COMMIT")
            except Exception as e:
                try:
                    _conn.execute("ROLLBACK")
                except Exception:
                    pass
                log.warning("[%s] JOB #%d: Failed to reserve unique comment: %s",
                            self.device_serial, self.job_id, e)
                result['errors'] += 1
                return result
            # Force this specific comment
            comment_action.comment_templates = [chosen_comment]
            log.info("[%s] JOB #%d: Unique comment reserved: '%s' (%d/%d available)",
                     self.device_serial, self.job_id, chosen_comment,
                     len(available), len(all_comment_lines))

        def _unreserve_comment():
            """Remove the reserved comment row if unique_comments active."""
            if chosen_comment:
                try:
                    _uc = get_db()
                    _uc.execute("""
                        DELETE FROM job_history
                        WHERE job_id = ? AND account_id = ? AND status = 'reserved'
                          AND comment_used = ?
                    """, (self.job_id, self.account_id, chosen_comment))
                    _uc.commit()
                    log.debug("[%s] JOB #%d: Unreserved comment '%s'",
                              self.device_serial, self.job_id, chosen_comment)
                except Exception as ue:
                    log.warning("[%s] JOB #%d: Failed to unreserve comment: %s",
                                self.device_serial, self.job_id, ue)

        source = self.target.lstrip('@')
        # Max 1 comment per account per job execution — spread across accounts
        session_target = min(budget, 1)

        log.info("[%s] JOB #%d (comment): Commenting on @%s's posts "
                 "(%d/%d today, %d/%s total)",
                 self.device_serial, self.job_id, source,
                 done_today, self.daily_limit,
                 self.job.get('completed_count', 0),
                 str(self.target_count) if self.target_count > 0 else '∞')

        # Detect if target is a post URL or a username
        # Handles both instagram.com/p/XXX and instagram.com/user/p/XXX formats
        is_post_url = ('instagram.com' in self.target and
                       ('/p/' in self.target or '/reel/' in self.target or '/reels/' in self.target))

        comment_action.ctrl.ensure_app()
        comment_action.ctrl.dismiss_popups()

        if is_post_url:
            # Open post directly via deep link
            import subprocess
            adb_serial = self.device_serial.replace('_', ':')
            pkg = self.account.get('package', self.account.get(
                'instagram_package', 'com.instagram.androie'))
            # Strip query params for clean URL
            clean_url = self.target.split('?')[0]
            # Force-stop IG first for clean state
            subprocess.run([
                'adb', '-s', adb_serial, 'shell', 'am', 'force-stop', pkg
            ], capture_output=True, timeout=5)
            random_sleep(1, 2, label="force_stop_wait")
            # Try deep link with retry on empty state
            deeplink_loaded = False
            for dl_attempt in range(3):
                subprocess.run([
                    'adb', '-s', adb_serial, 'shell', 'am', 'start',
                    '-a', 'android.intent.action.VIEW',
                    '-d', clean_url, pkg
                ], capture_output=True, timeout=10)
                random_sleep(5, 8, label="deeplink_post_load")
                comment_action.ctrl.dismiss_popups()

                # Check if post actually loaded (not empty state)
                d = self.device
                empty_state = d(resourceIdMatches='.*empty_state_view_root').exists(timeout=1)

                def _find_comment_btn(timeout=1):
                    return (
                        d(resourceIdMatches='.*row_feed_button_comment').exists(timeout=timeout) or
                        d(descriptionContains='Comment').exists(timeout=timeout)
                    )

                has_comment_btn = _find_comment_btn(1)

                # If no comment button, try scrolling down (large images push buttons off-screen)
                if not has_comment_btn and not empty_state:
                    for scroll_try in range(3):
                        info = d.info
                        h = info.get('displayHeight', 1920)
                        w = info.get('displayWidth', 1080)
                        d.swipe(w // 2, int(h * 0.7), w // 2, int(h * 0.3), steps=20)
                        random_sleep(1, 2, label="scroll_find_comment")
                        if _find_comment_btn(1):
                            has_comment_btn = True
                            log.info("[%s] JOB #%d: Found comment button after scroll %d",
                                     self.device_serial, self.job_id, scroll_try + 1)
                            break

                if has_comment_btn:
                    deeplink_loaded = True
                    break
                if empty_state:
                    log.warning("[%s] JOB #%d: Post empty state on attempt %d/3, retrying...",
                                self.device_serial, self.job_id, dl_attempt + 1)
                    # Press back and retry
                    d.press('back')
                    random_sleep(2, 3, label="deeplink_retry_wait")
                else:
                    # Post might be loading, wait more
                    random_sleep(3, 5, label="deeplink_extra_wait")
                    has_comment_btn = _find_comment_btn(2)
                    if has_comment_btn:
                        deeplink_loaded = True
                        break
                    log.warning("[%s] JOB #%d: No comment button on attempt %d/3",
                                self.device_serial, self.job_id, dl_attempt + 1)
                    d.press('back')
                    random_sleep(2, 3, label="deeplink_retry_wait")

            log.info("[%s] JOB #%d: Opened post via deep link: %s (loaded=%s)",
                     self.device_serial, self.job_id, clean_url, deeplink_loaded)

            if not deeplink_loaded:
                log.error("[%s] JOB #%d: Post failed to load after 3 attempts",
                          self.device_serial, self.job_id)
                record_job_action(self.job_id, self.account_id, 'comment',
                                  source, success=False,
                                  error_message="Post failed to load via deep link")
                _unreserve_comment()
                result['errors'] += 1
                return result
        else:
            # Navigate to target profile and open grid post
            if not comment_action.ctrl.search_user(source):
                log.warning("[%s] JOB #%d: Could not find @%s",
                            self.device_serial, self.job_id, source)
                record_job_action(self.job_id, self.account_id, 'comment',
                                  source, success=False,
                                  error_message="User not found")
                _unreserve_comment()
                result['errors'] += 1
                return result

            random_sleep(2, 4, label="on_target_profile")
            comment_action.ctrl.dismiss_popups()

            # Open first grid post via content-desc (reliable on clones)
            grid_clicked = False
            xml = comment_action.ctrl.dump_xml("job_grid")
            import xml.etree.ElementTree as _ET
            try:
                _root = _ET.fromstring(xml)
                for _elem in _root.iter():
                    _desc = _elem.get('content-desc', '')
                    _bounds = _elem.get('bounds', '')
                    if _bounds and any(k in _desc for k in
                                      ('Photo by', 'Reel by', 'Video by')):
                        _m = re.match(
                            r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', _bounds)
                        if _m:
                            cx = (int(_m.group(1))+int(_m.group(3)))//2
                            cy = (int(_m.group(2))+int(_m.group(4)))//2
                            self.device.click(cx, cy)
                            grid_clicked = True
                            log.debug("[%s] JOB #%d: Clicked grid: %s",
                                      self.device_serial, self.job_id,
                                      _desc[:60])
                            break
            except Exception:
                pass

            if not grid_clicked:
                # Fallback: clickable images below profile header
                images = self.device(
                    className="android.widget.ImageView", clickable=True)
                if images.exists(timeout=3) and images.count > 0:
                    for idx in range(min(2, images.count - 1), images.count):
                        try:
                            info = images[idx].info
                            if info.get('bounds', {}).get('top', 0) > 400:
                                images[idx].click()
                                grid_clicked = True
                                break
                        except Exception:
                            continue

            if not grid_clicked:
                log.warning("[%s] JOB #%d: No grid posts for @%s",
                            self.device_serial, self.job_id, source)
                comment_action.ctrl.press_back()
                _unreserve_comment()
                result['errors'] += 1
                return result

            random_sleep(2, 3, label="post_opened")
            comment_action.ctrl.dismiss_popups()

        for i in range(session_target + 3):
            if result['actions_done'] >= session_target:
                break

            # Atomic claim: try to reserve a slot before doing the action
            if self.target_count > 0:
                if not claim_job_slot(self.job_id):
                    log.info("[%s] JOB #%d: No slot available (target reached), stopping",
                             self.device_serial, self.job_id)
                    break
                claimed = True
            else:
                claimed = False

            # Global delay: wait if another device posted too recently
            if self.action_delay > 0:
                wait_for_global_delay(self.job_id, self.action_delay)

            try:
                # Use CommentAction's proven comment flow
                xml = comment_action.ctrl.dump_xml("job_comment_post")
                comment_btn = comment_action._find_comment_button(xml)

                # If comment button not visible, try small scroll down (large image)
                if comment_btn is None:
                    log.debug("[%s] JOB #%d: Comment button not visible, scrolling down...",
                              self.device_serial, self.job_id)
                    self.device.swipe(540, 1400, 540, 900, duration=0.3)
                    time.sleep(1.5)
                    xml = comment_action.ctrl.dump_xml("job_comment_post_retry")
                    comment_btn = comment_action._find_comment_button(xml)

                if comment_btn is None:
                    log.debug("[%s] JOB #%d: No comment button on current post (even after scroll)",
                              self.device_serial, self.job_id)
                    result['skipped'] += 1
                    # Release the claimed slot — we didn't actually comment
                    if claimed:
                        unclaim_job_slot(self.job_id)
                    _unreserve_comment()
                else:
                    # _post_comment handles: click btn → find input → 
                    # set_text (reliable) → click Post → verify
                    success = comment_action._post_comment(
                        comment_btn, post_author=source)
                    if success:
                        result['actions_done'] += 1
                        # If unique_comments, update reserved→success; else insert new
                        if chosen_comment:
                            _uc = get_db()
                            _uc.execute("""
                                UPDATE job_history SET status = 'success'
                                WHERE job_id = ? AND account_id = ? AND status = 'reserved'
                                  AND comment_used = ?
                            """, (self.job_id, self.account_id, chosen_comment))
                            # Also update assignment + check job completion
                            _uc.execute("""
                                UPDATE job_assignments
                                SET completed_count = completed_count + 1,
                                    last_action_at = datetime('now')
                                WHERE job_id = ? AND account_id = ?
                            """, (self.job_id, self.account_id))
                            _uc.execute("""
                                UPDATE job_orders
                                SET status = 'completed', finished_at = datetime('now')
                                WHERE id = ? AND target_count > 0
                                  AND completed_count >= target_count
                            """, (self.job_id,))
                            _uc.commit()
                        else:
                            record_job_action(self.job_id, self.account_id,
                                              'comment', source, success=True,
                                              used_claim=claimed,
                                              comment_used=None)
                        log_action(self.session_id, self.device_serial,
                                   self.username, 'comment',
                                   target_username=source, success=True)
                        log.info("[%s] JOB #%d (comment): Commented on @%s's "
                                 "post (%d/%d today)",
                                 self.device_serial, self.job_id, source,
                                 done_today + result['actions_done'],
                                 self.daily_limit)
                        random_sleep(5, 15, label="comment_delay")
                    else:
                        result['errors'] += 1
                        # Release the claimed slot — comment failed
                        if claimed:
                            unclaim_job_slot(self.job_id)
                        _unreserve_comment()

                # Scroll to next post
                comment_action.ctrl.scroll_feed("down", amount=0.5)
                random_sleep(2, 5, label="between_comment_posts")

            except Exception as e:
                log.warning("[%s] JOB #%d: Error commenting: %s",
                            self.device_serial, self.job_id, e)
                result['errors'] += 1
                if claimed:
                    unclaim_job_slot(self.job_id)
                _unreserve_comment()

        # Go back to clean state
        for _ in range(4):
            comment_action.ctrl.press_back()
            time.sleep(0.5)

        # If unique comment was reserved but never posted, release it
        if result['actions_done'] == 0:
            _unreserve_comment()

        log.info("[%s] JOB #%d (comment): Done. Commented %d, skipped %d, "
                 "errors %d",
                 self.device_serial, self.job_id,
                 result['actions_done'], result['skipped'], result['errors'])
        return result

    # ------------------------------------------------------------------
    # Share to story job
    # ------------------------------------------------------------------
    def _execute_share_to_story(self, budget, done_today):
        """
        Share target account's posts to this account's story.
        Supports both:
          - Post/reel URL → deep link → share to story
          - Username → search_user → open grid → share to story
        """
        from automation.actions.share_to_story import ShareToStoryAction
        import subprocess

        result = {'actions_done': 0, 'errors': 0, 'skipped': 0}
        pkg = self.account.get('package', 'com.instagram.androie')

        source = self.target.lstrip('@')
        target_is_url = is_post_url(self.target)
        session_target = min(budget, 1 if target_is_url else random.randint(1, 3))

        # --- Check if this account already shared this (prevent duplicate) ---
        if target_is_url:
            try:
                conn = get_db()
                already = conn.execute(
                    "SELECT COUNT(*) FROM job_history "
                    "WHERE job_id = ? AND account_id = ? AND status = 'success'",
                    (self.job_id, self.account_id)
                ).fetchone()[0]
                conn.close()
                if already > 0:
                    log.info("[%s] JOB #%d: Account %s already shared this post, skipping",
                             self.device_serial, self.job_id, self.username)
                    result['skipped'] += 1
                    return result
            except Exception as e:
                log.warning("[%s] JOB #%d: Could not check history: %s",
                            self.device_serial, self.job_id, e)

        log.info("[%s] JOB #%d (share_to_story): Sharing %s to story "
                 "(%d/%d today, %d/%s total)",
                 self.device_serial, self.job_id,
                 f"post URL" if target_is_url else f"@{source}'s posts",
                 done_today, self.daily_limit,
                 self.job.get('completed_count', 0),
                 str(self.target_count) if self.target_count > 0 else '∞')

        # Create ShareToStoryAction — this sets up IGController, loads settings
        share_action = ShareToStoryAction(
            self.device, self.device_serial,
            self.account, self.session_id, pkg
        )

        share_action.ctrl.ensure_app()
        share_action.ctrl.dismiss_popups()

        if target_is_url:
            # --- URL flow: open post via deep link, then share to story ---
            if not open_post_via_deeplink(self.device, self.device_serial, pkg, self.target):
                log.warning("[%s] JOB #%d: Could not open post URL: %s",
                            self.device_serial, self.job_id, self.target)
                record_job_action(self.job_id, self.account_id,
                                  'share_to_story', source, success=False,
                                  error_message="Could not open post URL")
                result['errors'] += 1
                return result

            share_action.ctrl.dismiss_popups()

            # Find share/send button on the post
            d = self.device
            share_btn = (
                d(resourceIdMatches='.*row_feed_button_share') or
                d(descriptionContains='Share') or
                d(descriptionContains='Send')
            )
            if share_btn.exists(timeout=3):
                share_btn.click()
                random_sleep(2, 3, label="share_menu_open")

                # Look for "Add to your story" option
                story_opt = (
                    d(textContains='Add to your story') or
                    d(textContains='Add reel to your story') or
                    d(textContains='story')
                )
                if story_opt.exists(timeout=3):
                    story_opt.click()
                    random_sleep(3, 5, label="story_editor_load")

                    # Publish — look for share/done button
                    publish_btn = (
                        d(resourceIdMatches='.*share_story_button') or
                        d(descriptionContains='Share') or
                        d(textContains='Share') or
                        d(text='Your story')
                    )
                    if publish_btn.exists(timeout=5):
                        publish_btn.click()
                        random_sleep(3, 5, label="publishing_story")
                        result['actions_done'] += 1
                        record_job_action(self.job_id, self.account_id,
                                          'share_to_story', source, success=True)
                        log_action(self.session_id, self.device_serial,
                                   self.username, 'share_to_story',
                                   target_username=source, success=True)
                        log.info("[%s] JOB #%d (share_to_story): Shared post URL to story",
                                 self.device_serial, self.job_id)
                    else:
                        log.warning("[%s] JOB #%d: Could not find publish button",
                                    self.device_serial, self.job_id)
                        result['errors'] += 1
                else:
                    log.warning("[%s] JOB #%d: Could not find 'Add to story' option",
                                self.device_serial, self.job_id)
                    result['errors'] += 1
            else:
                log.warning("[%s] JOB #%d: Could not find share button on post",
                            self.device_serial, self.job_id)
                result['errors'] += 1

            # Go back to clean state
            share_action.ctrl.press_back()
            time.sleep(1)
            share_action.ctrl.press_back()
        else:
            # --- Username flow: use ShareToStoryAction's proven method ---
            for i in range(session_target + 2):
                if result['actions_done'] >= session_target:
                    break

                try:
                    share_action.ctrl.dismiss_popups()
                    shared = share_action._share_from_source(source)
                    if shared:
                        result['actions_done'] += 1
                        record_job_action(self.job_id, self.account_id,
                                          'share_to_story', source, success=True)
                        log_action(self.session_id, self.device_serial,
                                   self.username, 'share_to_story',
                                   target_username=source, success=True)
                        log.info("[%s] JOB #%d (share_to_story): Shared @%s's post to story "
                                 "(%d/%d today)",
                                 self.device_serial, self.job_id, source,
                                 done_today + result['actions_done'],
                                 self.daily_limit)
                        random_sleep(10, 20, label="after_story_share")
                    else:
                        result['skipped'] += 1
                        result['errors'] += 1

                    if result['actions_done'] < session_target:
                        random_sleep(5, 15, label="between_story_shares")

                except Exception as e:
                    log.warning("[%s] JOB #%d: Error sharing to story: %s",
                                self.device_serial, self.job_id, e)
                    result['errors'] += 1
                    try:
                        share_action._recover()
                    except Exception:
                        pass

        log.info("[%s] JOB #%d (share_to_story): Done. Shared %d, skipped %d, errors %d",
                 self.device_serial, self.job_id,
                 result['actions_done'], result['skipped'], result['errors'])
        return result


    # ------------------------------------------------------------------
    # Save post job
    # ------------------------------------------------------------------
    def _execute_save_post(self, budget, done_today):
        """
        Save/bookmark posts from target account's profile.
        Navigates to target profile, opens posts, saves them.
        """
        from automation.actions.save_post import SavePostAction
        from automation.ig_controller import IGController

        result = {'actions_done': 0, 'errors': 0, 'skipped': 0}
        pkg = self.account.get('package', 'com.instagram.androie')

        target = self.target.lstrip('@')
        session_target = min(budget, random.randint(3, 8))

        log.info("[%s] JOB #%d (save_post): Saving posts from @%s "
                 "(%d/%d today, %d/%s total)",
                 self.device_serial, self.job_id, target,
                 done_today, self.daily_limit,
                 self.job.get('completed_count', 0),
                 str(self.target_count) if self.target_count > 0 else 'unlimited')

        # Create a SavePostAction and use its source-saving logic
        save_action = SavePostAction(
            self.device, self.device_serial,
            self.account, self.session_id, pkg
        )

        save_action.ctrl.ensure_app()
        save_action.ctrl.dismiss_popups()

        # Use _save_from_source for targeted saving
        save_result = save_action._save_from_source(target, session_target)

        for i in range(save_result['saved']):
            record_job_action(self.job_id, self.account_id,
                              'save_post', target, success=True)

        result['actions_done'] = save_result['saved']
        result['errors'] = save_result['errors']

        log.info("[%s] JOB #%d (save_post): Done. Saved %d, errors %d",
                 self.device_serial, self.job_id,
                 result['actions_done'], result['errors'])
        return result

    # ------------------------------------------------------------------
    # Report job
    # ------------------------------------------------------------------
    def _execute_report(self, budget, done_today):
        """
        Execute mass report job.
        Reports the target user profile from this account.
        Budget is typically 1 per account (one report per account per target).
        Uses vision-assisted ReportAction for reliability.
        """
        from automation.actions.report import ReportAction

        result = {'actions_done': 0, 'errors': 0, 'skipped': 0}
        pkg = self.account.get('package', 'com.instagram.androie')

        target = self.target.lstrip('@')
        report_reason = self.job.get('report_reason', 'nudity') or 'nudity'
        session_target = min(budget, 1)  # 1 report per account per target

        log.info("[%s] JOB #%d (report): Reporting @%s (reason: %s) "
                 "(%d/%d today, %d/%s total)",
                 self.device_serial, self.job_id, target, report_reason,
                 done_today, self.daily_limit,
                 self.job.get('completed_count', 0),
                 str(self.target_count) if self.target_count > 0 else '∞')

        report_action = ReportAction(
            self.device, self.device_serial,
            self.account, self.session_id, pkg
        )

        for i in range(session_target):
            try:
                report_result = report_action.execute(
                    target_username=target,
                    report_reason=report_reason
                )

                if report_result['success']:
                    result['actions_done'] += 1
                    record_job_action(self.job_id, self.account_id,
                                      'report', target, success=True)
                    log_action(self.session_id, self.device_serial,
                               self.username, 'report',
                               target_username=target, success=True)
                    log.info("[%s] JOB #%d (report): Successfully reported @%s "
                             "(%d/%d today)",
                             self.device_serial, self.job_id, target,
                             done_today + result['actions_done'],
                             self.daily_limit)
                else:
                    result['errors'] += 1
                    error_msg = report_result.get('message', 'Unknown error')
                    record_job_action(self.job_id, self.account_id,
                                      'report', target, success=False,
                                      error_message=error_msg[:500])
                    log.warning("[%s] JOB #%d (report): Failed to report @%s: %s",
                                self.device_serial, self.job_id, target, error_msg)

            except Exception as e:
                log.error("[%s] JOB #%d (report): Exception reporting @%s: %s",
                          self.device_serial, self.job_id, target, e)
                result['errors'] += 1
                record_job_action(self.job_id, self.account_id,
                                  'report', target, success=False,
                                  error_message=str(e)[:500])

        log.info("[%s] JOB #%d (report): Done. Reported %d, errors %d",
                 self.device_serial, self.job_id,
                 result['actions_done'], result['errors'])
        return result

    # ------------------------------------------------------------------
    # DM job
    # ------------------------------------------------------------------
    def _execute_dm(self, budget, done_today):
        """
        Send a direct message to the target user.
        Delegates to DMAction's proven internal methods:
          - search_user → open profile → click Message → type & send

        Uses job's comment_text as the DM message. If empty, falls back
        to DMAction's loaded templates (from account_text_configs.pm_list).
        """
        from automation.actions.dm import DMAction

        result = {'actions_done': 0, 'errors': 0, 'skipped': 0}
        pkg = self.account.get('package', 'com.instagram.androie')

        target = self.target.lstrip('@')
        session_target = min(budget, random.randint(1, 3))

        log.info("[%s] JOB #%d (dm): DMing @%s "
                 "(%d/%d today, %d/%s total)",
                 self.device_serial, self.job_id, target,
                 done_today, self.daily_limit,
                 self.job.get('completed_count', 0),
                 str(self.target_count) if self.target_count > 0 else '∞')

        # Create DMAction — this sets up IGController, AdbKeyboard, loads templates
        dm_action = DMAction(
            self.device, self.device_serial,
            self.account, self.session_id, pkg
        )

        # Override message templates if job has specific comment_text
        # Each line = separate message option (random.choice picks one per DM)
        if self.comment_text and self.comment_text.strip():
            lines = [l.strip() for l in self.comment_text.split('\n') if l.strip()]
            dm_action.message_templates = lines if lines else [self.comment_text]

        dm_action.ctrl.ensure_app()
        dm_action.ctrl.dismiss_popups()

        for i in range(session_target):
            if result['actions_done'] >= session_target:
                break

            try:
                dm_action.ctrl.dismiss_popups()
                # Use DMAction's proven _send_dm_to_user method
                success = dm_action._send_dm_to_user(target)
                if success:
                    result['actions_done'] += 1
                    record_job_action(self.job_id, self.account_id,
                                      'dm', target, success=True)
                    log_action(self.session_id, self.device_serial,
                               self.username, 'dm',
                               target_username=target, success=True)
                    log.info("[%s] JOB #%d (dm): Sent DM to @%s (%d/%d today)",
                             self.device_serial, self.job_id, target,
                             done_today + result['actions_done'],
                             self.daily_limit)
                    random_sleep(5, 15, label="after_dm_send")
                else:
                    result['errors'] += 1
                    error_msg = "DM send failed"
                    record_job_action(self.job_id, self.account_id,
                                      'dm', target, success=False,
                                      error_message=error_msg)
                    log.warning("[%s] JOB #%d (dm): Failed to DM @%s",
                                self.device_serial, self.job_id, target)

            except Exception as e:
                log.error("[%s] JOB #%d (dm): Exception DMing @%s: %s",
                          self.device_serial, self.job_id, target, e)
                result['errors'] += 1
                record_job_action(self.job_id, self.account_id,
                                  'dm', target, success=False,
                                  error_message=str(e)[:500])
                try:
                    dm_action._recover()
                except Exception:
                    pass

        log.info("[%s] JOB #%d (dm): Done. Sent %d, errors %d",
                 self.device_serial, self.job_id,
                 result['actions_done'], result['errors'])
        return result


# ---------------------------------------------------------------------------
# Spintax helper
# ---------------------------------------------------------------------------
def _process_spintax(text):
    """Process spintax: {option1|option2|option3} → random pick."""
    import re
    def _replace(match):
        options = match.group(1).split('|')
        return random.choice(options).strip()
    return re.sub(r'\{([^}]+)\}', _replace, text)
