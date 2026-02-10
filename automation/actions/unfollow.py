"""
Unfollow Action Module
=======================
Unfollow users who were followed X days ago, using IGController.

Flow:
1. Navigate to bot account's profile
2. Open Following list
3. Scroll through and unfollow users
4. Respect whitelist and unfollow delay (days since follow)
5. Log each action
"""

import logging
import random
import time
import datetime

from automation.actions.helpers import (
    action_delay, random_sleep, log_action,
    get_account_settings, get_account_sources,
    get_today_action_count, get_db
)
from automation.ig_controller import IGController, Screen

log = logging.getLogger(__name__)


class UnfollowAction:
    """
    Unfollow users from the bot account's following list.
    Uses IGController for reliable screen-state-verified navigation.
    """

    def __init__(self, device, device_serial, account_info, session_id,
                 package='com.instagram.androie'):
        self.device = device
        self.device_serial = device_serial
        self.account = account_info
        self.session_id = session_id
        self.username = account_info['username']
        self.account_id = account_info['id']

        # IGController for reliable UI
        pkg = account_info.get('package', package)
        self.ctrl = IGController(device, device_serial, pkg)

        # Load settings
        self.settings = get_account_settings(self.account_id)
        self._init_limits()
        self._load_whitelist()

    def _init_limits(self):
        """Initialize unfollow limits."""
        raw_limit = self.account.get('unfollow_limit_perday', 'None')
        if raw_limit and raw_limit not in ('None', 'deprecated', ''):
            try:
                self.daily_limit = int(raw_limit)
            except ValueError:
                self.daily_limit = 0
        else:
            self.daily_limit = int(self.settings.get('unfollow_limit_perday', '60'))

        if self.daily_limit <= 0:
            self.daily_limit = 60

        raw_delay = self.account.get('unfollow_delay_day', '2')
        try:
            self.unfollow_delay_days = int(raw_delay) if raw_delay and raw_delay != 'None' else 2
        except ValueError:
            self.unfollow_delay_days = 2

        unfollow_action = self.account.get('unfollow_action', '10,20')
        if ',' in str(unfollow_action):
            parts = str(unfollow_action).split(',')
            try:
                self.session_min = int(parts[0])
                self.session_max = int(parts[1])
            except (ValueError, IndexError):
                self.session_min = 10
                self.session_max = 20
        else:
            self.session_min = 10
            self.session_max = 20

        if self.session_min <= 0:
            self.session_min = 10
        if self.session_max <= 0:
            self.session_max = 20

        self.session_target = random.randint(self.session_min, self.session_max)
        log.info("[%s] Unfollow limits: daily=%d, session_target=%d, delay_days=%d",
                 self.device_serial, self.daily_limit, self.session_target,
                 self.unfollow_delay_days)

    def _load_whitelist(self):
        """Load whitelist of users to never unfollow."""
        self.whitelist = set()
        wl = get_account_sources(self.account_id, 'whitelist')
        self.whitelist.update(u.lower() for u in wl)
        sources = get_account_sources(self.account_id, 'sources')
        self.whitelist.update(u.lower() for u in sources)
        log.info("[%s] Whitelist: %d users", self.device_serial, len(self.whitelist))

    def _get_users_eligible_for_unfollow(self):
        """
        Get users followed long enough ago to be eligible for unfollow.
        Returns set of usernames.
        """
        eligible = set()
        try:
            conn = get_db()
            cutoff = (datetime.datetime.now() -
                     datetime.timedelta(days=self.unfollow_delay_days)).isoformat()
            rows = conn.execute("""
                SELECT DISTINCT target_username FROM action_history
                WHERE device_serial=? AND username=? AND action_type='follow'
                  AND success=1 AND timestamp <= ?
                  AND target_username IS NOT NULL
            """, (self.device_serial, self.username, cutoff)).fetchall()
            conn.close()
            eligible = {r['target_username'] for r in rows}

            eligible -= self.whitelist

            conn = get_db()
            already_unfollowed = conn.execute("""
                SELECT DISTINCT target_username FROM action_history
                WHERE device_serial=? AND username=? AND action_type='unfollow'
                  AND success=1 AND target_username IS NOT NULL
            """, (self.device_serial, self.username)).fetchall()
            conn.close()
            eligible -= {r['target_username'] for r in already_unfollowed}

        except Exception as e:
            log.error("[%s] Error getting eligible unfollow list: %s",
                     self.device_serial, e)

        return eligible

    def execute(self):
        """
        Execute the unfollow action.
        Returns dict: {success, unfollows_done, errors, skipped}
        """
        result = {
            'success': False,
            'unfollows_done': 0,
            'errors': 0,
            'skipped': 0,
        }

        # Ensure Instagram is running
        self.ctrl.ensure_app()
        self.ctrl.dismiss_popups()

        # Check daily limit
        done_today = get_today_action_count(
            self.device_serial, self.username, 'unfollow')
        remaining = self.daily_limit - done_today
        if remaining <= 0:
            log.info("[%s] %s: Daily unfollow limit reached (%d/%d)",
                     self.device_serial, self.username, done_today, self.daily_limit)
            result['success'] = True
            return result

        target = min(self.session_target, remaining)
        log.info("[%s] %s: Will unfollow up to %d users (done today: %d)",
                 self.device_serial, self.username, target, done_today)

        # Get users eligible for unfollow
        eligible = self._get_users_eligible_for_unfollow()
        log.info("[%s] Users eligible for unfollow: %d", self.device_serial, len(eligible))

        # Navigate to own profile using IGController
        if not self.ctrl.navigate_to(Screen.PROFILE):
            log.warning("[%s] Could not navigate to profile", self.device_serial)
            result['errors'] += 1
            return result

        random_sleep(2, 4)

        # Open following list using IGController
        if not self.ctrl.open_following():
            log.warning("[%s] Could not open following list", self.device_serial)
            self.ctrl.press_back()
            result['errors'] += 1
            return result

        random_sleep(2, 4, label="following_list_loaded")

        # Process the following list
        scroll_attempts = 0
        max_scroll_attempts = 20
        seen_usernames = set()

        while result['unfollows_done'] < target and scroll_attempts < max_scroll_attempts:
            # Get visible users using IGController
            users = self.ctrl.get_visible_usernames_in_list()
            new_users = [u for u in users if u not in seen_usernames]

            if not new_users:
                scroll_attempts += 1
                if scroll_attempts >= max_scroll_attempts:
                    break
                self.ctrl.scroll_list("down")
                random_sleep(1, 2)
                continue

            scroll_attempts = 0

            for user in new_users:
                if result['unfollows_done'] >= target:
                    break

                seen_usernames.add(user)

                # Check whitelist
                if user.lower() in self.whitelist:
                    log.debug("[%s] Skip @%s (whitelisted)", self.device_serial, user)
                    result['skipped'] += 1
                    continue

                # Check eligibility
                if eligible and user not in eligible:
                    result['skipped'] += 1
                    continue

                # Dismiss any popups before each unfollow attempt
                self.ctrl.dismiss_popups()

                try:
                    unfollowed = self._unfollow_user_from_list(user)
                    if unfollowed:
                        result['unfollows_done'] += 1
                        log_action(
                            self.session_id, self.device_serial, self.username,
                            'unfollow', target_username=user, success=True)
                        log.info("[%s] Unfollowed @%s (%d/%d)",
                                self.device_serial, user,
                                result['unfollows_done'], target)
                        action_delay("unfollow")
                    else:
                        result['skipped'] += 1
                except Exception as e:
                    log.error("[%s] Error unfollowing @%s: %s",
                             self.device_serial, user, e)
                    result['errors'] += 1
                    log_action(
                        self.session_id, self.device_serial, self.username,
                        'unfollow', target_username=user, success=False,
                        error_message=str(e)[:200])

            self.ctrl.scroll_list("down")
            random_sleep(1.5, 3, label="scroll_following")

        # Navigate back
        self.ctrl.press_back()
        time.sleep(1)

        result['success'] = True
        log.info("[%s] %s: Unfollow complete. Unfollowed: %d, Skipped: %d, Errors: %d",
                 self.device_serial, self.username,
                 result['unfollows_done'], result['skipped'], result['errors'])
        return result

    def _unfollow_user_from_list(self, target_username):
        """
        Unfollow a user from the following list.

        Strategy: Click on username -> visit profile -> Following button -> confirm.
        This is confirmed working from XML testing.

        Returns True if unfollowed, False otherwise.
        """
        try:
            # Find the username element via controller
            user_el = self.ctrl.find_element(text=target_username, timeout=2)
            if user_el is None:
                user_el = self.ctrl.device(
                    resourceIdMatches=self.ctrl._rid_match('follow_list_username'),
                    text=target_username)
                if not user_el.exists(timeout=2):
                    log.debug("[%s] Username @%s not found in list",
                             self.device_serial, target_username)
                    return False

            # Click username to visit profile
            user_el.click()
            time.sleep(3)

            # Verify we're on some kind of profile and dismiss popups
            screen = self.ctrl.detect_screen()
            if screen == Screen.POPUP:
                self.ctrl.dismiss_popups()
                time.sleep(1)

            # Use IGController to unfollow from profile
            unfollowed = self.ctrl.unfollow_user()

            if not unfollowed:
                # Debug: dump XML if unfollow failed
                log.debug("[%s] Unfollow failed for @%s, dumping XML",
                         self.device_serial, target_username)
                self.ctrl.dump_xml(f"unfollow_fail_{target_username}")

            # Go back to the following list
            self.ctrl.press_back()
            time.sleep(1.5)

            # Verify we're back in a list (not stuck on profile)
            screen = self.ctrl.detect_screen()
            if screen == Screen.POPUP:
                self.ctrl.dismiss_popups()
                time.sleep(1)

            return unfollowed

        except Exception as e:
            log.error("[%s] _unfollow_user_from_list error: %s", self.device_serial, e)
            try:
                self.ctrl.press_back()
                time.sleep(1)
            except Exception:
                pass
            return False


def execute_unfollow(device, device_serial, account_info, session_id):
    """Convenience function to run unfollow action."""
    action = UnfollowAction(device, device_serial, account_info, session_id)
    return action.execute()
