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


def record_job_action(job_id, account_id, action_type, target=None,
                      success=True, error_message=None):
    """Insert a row into job_history and update counters."""
    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO job_history (job_id, account_id, action_type, target,
                                     status, error_message)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (job_id, account_id, action_type, target,
              'success' if success else 'error', error_message))

        if success:
            # Bump assignment completed_count
            conn.execute("""
                UPDATE job_assignments
                SET completed_count = completed_count + 1,
                    last_action_at = datetime('now')
                WHERE job_id = ? AND account_id = ?
            """, (job_id, account_id))

            # Recalculate job_orders.completed_count as SUM of all assignments
            conn.execute("""
                UPDATE job_orders
                SET completed_count = (
                    SELECT COALESCE(SUM(completed_count), 0)
                    FROM job_assignments WHERE job_id = ?
                ),
                updated_at = datetime('now')
                WHERE id = ?
            """, (job_id, job_id))

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

    def execute(self):
        """
        Run the job action.
        Returns dict: {success, actions_done, errors, skipped, message}
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

        # Check total target
        total_done = self.job.get('completed_count', 0)
        if self.target_count > 0 and total_done >= self.target_count:
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
        Follow users from target account's follower list.
        Uses the same IGController methods as FollowAction:
          - search_user() → navigate to source profile
          - open_followers() → open followers list
          - get_visible_usernames_in_list() → parse usernames from list
          - follow_user_from_list() → click Follow button next to username
          - scroll_list() → scroll for more users
        """
        from automation.ig_controller import IGController

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

        # Get recently followed to avoid duplicates
        recently_followed = get_recently_interacted(
            self.device_serial, self.username, 'follow', days=14)

        source = self.target.lstrip('@')
        session_target = min(budget, random.randint(8, 18))

        log.info("[%s] JOB #%d (follow): Following from @%s's followers "
                 "(%d/%d today, %d/%s total)",
                 self.device_serial, self.job_id, source,
                 done_today, self.daily_limit,
                 self.job.get('completed_count', 0),
                 str(self.target_count) if self.target_count > 0 else '∞')

        # Search for source user
        if not ctrl.search_user(source):
            log.warning("[%s] JOB #%d: Could not find source @%s",
                        self.device_serial, self.job_id, source)
            record_job_action(self.job_id, self.account_id, 'follow',
                              source, success=False,
                              error_message="Source user not found")
            result['errors'] += 1
            return result

        random_sleep(2, 4, label="on_source_profile")
        ctrl.dismiss_popups()

        # Open followers list
        if not ctrl.open_followers():
            log.warning("[%s] JOB #%d: Could not open followers for @%s",
                        self.device_serial, self.job_id, source)
            ctrl.press_back()
            record_job_action(self.job_id, self.account_id, 'follow',
                              source, success=False,
                              error_message="Could not open followers list")
            result['errors'] += 1
            return result

        random_sleep(2, 4, label="followers_list_loaded")

        # Scroll through followers and follow (same logic as FollowAction._follow_from_source)
        max_scroll_attempts = 15
        scroll_attempts = 0
        seen_usernames = set()

        while result['actions_done'] < session_target and scroll_attempts < max_scroll_attempts:
            # Use get_visible_usernames_in_list (same as FollowAction)
            usernames = ctrl.get_visible_usernames_in_list()
            new_users = [u for u in usernames if u not in seen_usernames]

            if not new_users:
                scroll_attempts += 1
                if scroll_attempts >= max_scroll_attempts:
                    log.info("[%s] JOB #%d: Reached end of followers list",
                             self.device_serial, self.job_id)
                    break
                ctrl.scroll_list("down")
                random_sleep(1, 2)
                continue

            scroll_attempts = 0  # Reset on finding new users

            for uname in new_users:
                if result['actions_done'] >= session_target:
                    break

                seen_usernames.add(uname)
                clean = uname.strip().lstrip('@').lower()

                if not clean or clean == self.username.lower():
                    continue
                if clean in recently_followed:
                    result['skipped'] += 1
                    continue

                # Use follow_user_from_list (same as FollowAction)
                try:
                    followed = ctrl.follow_user_from_list(uname)
                    if followed is True:
                        result['actions_done'] += 1
                        recently_followed.add(clean)

                        # Record to job_history + update counters
                        record_job_action(self.job_id, self.account_id,
                                          'follow', clean, success=True)

                        # Also log to action_history for global tracking
                        log_action(self.session_id, self.device_serial,
                                   self.username, 'follow',
                                   target_username=clean, success=True)

                        log.info("[%s] JOB #%d (follow): Followed @%s (%d/%d today)",
                                 self.device_serial, self.job_id, clean,
                                 done_today + result['actions_done'],
                                 self.daily_limit)

                        action_delay('follow')
                    elif followed is False:
                        result['skipped'] += 1
                    else:
                        # None = error
                        result['errors'] += 1
                except Exception as e:
                    log.warning("[%s] JOB #%d: Error following @%s: %s",
                                self.device_serial, self.job_id, clean, e)
                    result['errors'] += 1

            # Scroll down for more
            ctrl.scroll_list("down")
            random_sleep(1.5, 3, label="scroll_followers")

        # Go back to clean state
        ctrl.press_back()
        time.sleep(1)
        ctrl.press_back()
        time.sleep(1)
        ctrl.press_back()
        time.sleep(0.5)

        log.info("[%s] JOB #%d (follow): Done. Followed %d, skipped %d, errors %d",
                 self.device_serial, self.job_id,
                 result['actions_done'], result['skipped'], result['errors'])
        return result

    # ------------------------------------------------------------------
    # Like job
    # ------------------------------------------------------------------
    def _execute_like(self, budget, done_today):
        """
        Like posts from target account's profile.
        Uses IGController: search_user → open_first_post → like_post → scroll_down.
        """
        from automation.ig_controller import IGController

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
        session_target = min(budget, random.randint(5, 15))

        log.info("[%s] JOB #%d (like): Liking posts from @%s "
                 "(%d/%d today, %d/%s total)",
                 self.device_serial, self.job_id, source,
                 done_today, self.daily_limit,
                 self.job.get('completed_count', 0),
                 str(self.target_count) if self.target_count > 0 else '∞')

        # Navigate to target's profile
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
        for i in range(session_target + 5):  # extra to account for already-liked
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
        if self.comment_text and self.comment_text != '[AI]':
            lines = [l.strip() for l in self.comment_text.split('\n') if l.strip()]
            comment_action.comment_templates = lines if lines else [self.comment_text]
            # Clear settings comment_text so _get_comment uses templates (random pick per line)
            comment_action.settings['comment_text'] = ''
        elif self.comment_text == '[AI]':
            comment_action.settings['comment_text'] = '[AI]'

        source = self.target.lstrip('@')
        session_target = min(budget, random.randint(1, 3))

        log.info("[%s] JOB #%d (comment): Commenting on @%s's posts "
                 "(%d/%d today, %d/%s total)",
                 self.device_serial, self.job_id, source,
                 done_today, self.daily_limit,
                 self.job.get('completed_count', 0),
                 str(self.target_count) if self.target_count > 0 else '∞')

        # Detect if target is a post URL or a username
        is_post_url = ('instagram.com/p/' in self.target or
                       'instagram.com/reel/' in self.target)

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
                has_comment_btn = (
                    d(resourceIdMatches='.*row_feed_button_comment').exists(timeout=1) or
                    d(descriptionContains='Comment').exists(timeout=1)
                )
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
                    has_comment_btn = (
                        d(resourceIdMatches='.*row_feed_button_comment').exists(timeout=2) or
                        d(descriptionContains='Comment').exists(timeout=2)
                    )
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
                result['errors'] += 1
                return result

            random_sleep(2, 3, label="post_opened")
            comment_action.ctrl.dismiss_popups()

        for i in range(session_target + 3):
            if result['actions_done'] >= session_target:
                break

            # Re-check global target count from DB (other devices may have completed)
            if self.target_count > 0:
                try:
                    from automation.actions.helpers import get_db as _get_db
                    _conn = _get_db()
                    _row = _conn.execute(
                        "SELECT completed_count FROM job_orders WHERE id = ?",
                        (self.job_id,)).fetchone()
                    if _row and _row[0] >= self.target_count:
                        log.info("[%s] JOB #%d: Global target reached (%d/%d), stopping",
                                 self.device_serial, self.job_id, _row[0], self.target_count)
                        break
                except Exception:
                    pass

            try:
                # Use CommentAction's proven comment flow
                xml = comment_action.ctrl.dump_xml("job_comment_post")
                comment_btn = comment_action._find_comment_button(xml)

                if comment_btn is None:
                    log.debug("[%s] JOB #%d: No comment button on current post",
                              self.device_serial, self.job_id)
                    result['skipped'] += 1
                else:
                    # _post_comment handles: click btn → find input → 
                    # set_text (reliable) → click Post → verify
                    success = comment_action._post_comment(
                        comment_btn, post_author=source)
                    if success:
                        result['actions_done'] += 1
                        record_job_action(self.job_id, self.account_id,
                                          'comment', source, success=True)
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

                # Scroll to next post
                comment_action.ctrl.scroll_feed("down", amount=0.5)
                random_sleep(2, 5, label="between_comment_posts")

            except Exception as e:
                log.warning("[%s] JOB #%d: Error commenting: %s",
                            self.device_serial, self.job_id, e)
                result['errors'] += 1

        # Go back to clean state
        for _ in range(4):
            comment_action.ctrl.press_back()
            time.sleep(0.5)

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
        Delegates to ShareToStoryAction's proven internal methods:
          - _share_from_source() handles the full flow:
            search_user → open grid → click share → add to story → publish
        """
        from automation.actions.share_to_story import ShareToStoryAction

        result = {'actions_done': 0, 'errors': 0, 'skipped': 0}
        pkg = self.account.get('package', 'com.instagram.androie')

        source = self.target.lstrip('@')
        session_target = min(budget, random.randint(1, 3))  # Stories are less frequent

        log.info("[%s] JOB #%d (share_to_story): Sharing @%s's posts to story "
                 "(%d/%d today, %d/%s total)",
                 self.device_serial, self.job_id, source,
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

        for i in range(session_target + 2):
            if result['actions_done'] >= session_target:
                break

            try:
                share_action.ctrl.dismiss_popups()
                # Use ShareToStoryAction's proven _share_from_source method
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

                # Pause between shares
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
