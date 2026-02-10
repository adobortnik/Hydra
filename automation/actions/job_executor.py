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
                SET status = 'completed'
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
            'report': self._execute_report,
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
        Delegates to FollowAction with the job's target as the source.
        """
        from automation.actions.follow import FollowAction
        from automation.ig_controller import IGController

        result = {'actions_done': 0, 'errors': 0, 'skipped': 0}
        pkg = self.account.get('package', 'com.instagram.androie')
        ctrl = IGController(self.device, self.device_serial, pkg)

        ctrl.ensure_app()
        ctrl.dismiss_popups()

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

        # Scroll through followers and follow
        max_scrolls = 15
        for scroll_i in range(max_scrolls):
            if result['actions_done'] >= session_target:
                break

            usernames = ctrl.get_follower_usernames()
            if not usernames:
                log.info("[%s] JOB #%d: No usernames found on scroll %d",
                         self.device_serial, self.job_id, scroll_i)
                ctrl.scroll_down()
                random_sleep(1, 3)
                continue

            for uname in usernames:
                if result['actions_done'] >= session_target:
                    break

                clean = uname.strip().lstrip('@').lower()
                if not clean or clean == self.username.lower():
                    continue
                if clean in recently_followed:
                    result['skipped'] += 1
                    continue

                # Try to follow via button next to username
                try:
                    followed = ctrl.follow_user_in_list(uname)
                    if followed:
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
                    else:
                        result['skipped'] += 1
                except Exception as e:
                    log.warning("[%s] JOB #%d: Error following @%s: %s",
                                self.device_serial, self.job_id, clean, e)
                    result['errors'] += 1

            # Scroll down for more
            ctrl.scroll_down()
            random_sleep(1, 3, label="scroll_followers")

        # Go back to clean state
        for _ in range(3):
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
        Navigates to target profile, opens posts, likes them.
        """
        from automation.ig_controller import IGController

        result = {'actions_done': 0, 'errors': 0, 'skipped': 0}
        pkg = self.account.get('package', 'com.instagram.androie')
        ctrl = IGController(self.device, self.device_serial, pkg)

        ctrl.ensure_app()
        ctrl.dismiss_popups()

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

        # Open first post in grid
        if not ctrl.open_first_post():
            log.warning("[%s] JOB #%d: Could not open first post for @%s",
                        self.device_serial, self.job_id, source)
            ctrl.press_back()
            result['errors'] += 1
            return result

        random_sleep(1, 3, label="post_opened")

        # Like posts by scrolling through feed
        for i in range(session_target + 5):  # extra to account for already-liked
            if result['actions_done'] >= session_target:
                break

            try:
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

        # Go back
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
        Uses the job's comment_text (supports spintax).
        """
        import re
        from automation.ig_controller import IGController

        result = {'actions_done': 0, 'errors': 0, 'skipped': 0}
        pkg = self.account.get('package', 'com.instagram.androie')
        ctrl = IGController(self.device, self.device_serial, pkg)

        ctrl.ensure_app()
        ctrl.dismiss_popups()

        source = self.target.lstrip('@')
        session_target = min(budget, random.randint(3, 8))
        comment_template = self.comment_text or '{Great|Amazing|Nice} post! 🔥'

        log.info("[%s] JOB #%d (comment): Commenting on @%s's posts "
                 "(%d/%d today, %d/%s total)",
                 self.device_serial, self.job_id, source,
                 done_today, self.daily_limit,
                 self.job.get('completed_count', 0),
                 str(self.target_count) if self.target_count > 0 else '∞')

        # Navigate to target's profile
        if not ctrl.search_user(source):
            log.warning("[%s] JOB #%d: Could not find @%s",
                        self.device_serial, self.job_id, source)
            record_job_action(self.job_id, self.account_id, 'comment',
                              source, success=False,
                              error_message="User not found")
            result['errors'] += 1
            return result

        random_sleep(2, 4, label="on_target_profile")

        # Open first post
        if not ctrl.open_first_post():
            log.warning("[%s] JOB #%d: Could not open first post for @%s",
                        self.device_serial, self.job_id, source)
            ctrl.press_back()
            result['errors'] += 1
            return result

        random_sleep(1, 3, label="post_opened")

        for i in range(session_target + 3):
            if result['actions_done'] >= session_target:
                break

            try:
                # Process spintax
                comment = _process_spintax(comment_template)

                commented = ctrl.comment_on_post(comment)
                if commented:
                    result['actions_done'] += 1
                    record_job_action(self.job_id, self.account_id,
                                      'comment', source, success=True)
                    log_action(self.session_id, self.device_serial,
                               self.username, 'comment',
                               target_username=source, success=True)
                    log.info("[%s] JOB #%d (comment): Commented on @%s's post "
                             "(%d/%d today): %s",
                             self.device_serial, self.job_id, source,
                             done_today + result['actions_done'],
                             self.daily_limit, comment[:50])
                    action_delay('follow')  # comments need longer delays
                else:
                    result['skipped'] += 1

                # Scroll to next post
                ctrl.scroll_down()
                random_sleep(2, 5, label="between_comment_posts")

            except Exception as e:
                log.warning("[%s] JOB #%d: Error commenting: %s",
                            self.device_serial, self.job_id, e)
                result['errors'] += 1

        # Go back
        for _ in range(4):
            ctrl.press_back()
            time.sleep(0.5)

        log.info("[%s] JOB #%d (comment): Done. Commented %d, skipped %d, errors %d",
                 self.device_serial, self.job_id,
                 result['actions_done'], result['skipped'], result['errors'])
        return result

    # ------------------------------------------------------------------
    # Share to story job
    # ------------------------------------------------------------------
    def _execute_share_to_story(self, budget, done_today):
        """
        Share target account's posts to this account's story.
        Delegates to ShareToStoryAction but targets the job's target account.
        """
        from automation.ig_controller import IGController

        result = {'actions_done': 0, 'errors': 0, 'skipped': 0}
        pkg = self.account.get('package', 'com.instagram.androie')
        ctrl = IGController(self.device, self.device_serial, pkg)

        ctrl.ensure_app()
        ctrl.dismiss_popups()

        source = self.target.lstrip('@')
        session_target = min(budget, random.randint(1, 3))  # Stories are less frequent

        log.info("[%s] JOB #%d (share_to_story): Sharing @%s's posts to story "
                 "(%d/%d today, %d/%s total)",
                 self.device_serial, self.job_id, source,
                 done_today, self.daily_limit,
                 self.job.get('completed_count', 0),
                 str(self.target_count) if self.target_count > 0 else '∞')

        # Navigate to target's profile
        if not ctrl.search_user(source):
            log.warning("[%s] JOB #%d: Could not find @%s",
                        self.device_serial, self.job_id, source)
            record_job_action(self.job_id, self.account_id, 'share_to_story',
                              source, success=False,
                              error_message="User not found")
            result['errors'] += 1
            return result

        random_sleep(2, 4, label="on_target_profile")

        # Open first post
        if not ctrl.open_first_post():
            log.warning("[%s] JOB #%d: Could not open post for @%s",
                        self.device_serial, self.job_id, source)
            ctrl.press_back()
            result['errors'] += 1
            return result

        random_sleep(1, 3, label="post_opened")

        for i in range(session_target + 2):
            if result['actions_done'] >= session_target:
                break

            try:
                shared = ctrl.share_post_to_story()
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

                # Scroll to next post
                ctrl.scroll_down()
                random_sleep(2, 5, label="between_story_shares")

            except Exception as e:
                log.warning("[%s] JOB #%d: Error sharing to story: %s",
                            self.device_serial, self.job_id, e)
                result['errors'] += 1

        # Go back
        for _ in range(4):
            ctrl.press_back()
            time.sleep(0.5)

        log.info("[%s] JOB #%d (share_to_story): Done. Shared %d, skipped %d, errors %d",
                 self.device_serial, self.job_id,
                 result['actions_done'], result['skipped'], result['errors'])
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
