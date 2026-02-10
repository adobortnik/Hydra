"""
Follow Action Module
=====================
Follow users from source accounts' follower lists using IGController.

Flow:
1. Get source accounts for the bot account (from account_sources)
2. Search for source account using IGController
3. Open their followers list
4. Scroll through followers, follow eligible users
5. Respect limits, filters, and delays
6. Log each action to action_history
"""

import logging
import random
import time

from automation.actions.helpers import (
    action_delay, random_sleep, log_action,
    get_account_settings, get_account_sources,
    get_today_action_count, get_recently_interacted,
    get_profile_info, check_filters, parse_number,
    check_dead_source, record_dead_source, clear_dead_source
)
from automation.ig_controller import IGController, Screen
from automation.tag_dedup import is_tag_dedup_enabled, get_same_tag_followed_set

log = logging.getLogger(__name__)


class FollowAction:
    """
    Follow users from source account follower lists.
    Uses IGController for reliable XML-based UI control.
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
        self.filters = self.settings.get('filters', {})
        self.use_filters = self.settings.get('enable_filters', False)

        # Tag-based follow dedup (reads enable_tags + enable_dont_follow_sametag_accounts + tags from settings_json)
        self.tag_dedup_enabled = is_tag_dedup_enabled(self.account_id)
        self.tag_already_followed = set()
        if self.tag_dedup_enabled:
            self.tag_already_followed = get_same_tag_followed_set(self.account_id)
            log.info("[%s] Tag dedup ON — %d targets already followed by same-tag peers",
                     self.device_serial, len(self.tag_already_followed))

        # Limits
        self._init_limits()

    def _init_limits(self):
        """Initialize follow limits from account settings."""
        raw_limit = self.account.get('follow_limit_perday', '0')
        if raw_limit and raw_limit not in ('deprecated', 'None', ''):
            self.daily_limit = int(raw_limit) if str(raw_limit).isdigit() else 0
        else:
            self.daily_limit = 0

        if self.daily_limit <= 0:
            self.daily_limit = int(self.settings.get('default_action_limit_perday', '28'))

        follow_action = self.account.get('follow_action', '10,20')
        if ',' in str(follow_action):
            parts = str(follow_action).split(',')
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
        log.info("[%s] Follow limits: daily=%d, session_target=%d (range %d-%d)",
                 self.device_serial, self.daily_limit, self.session_target,
                 self.session_min, self.session_max)

    def execute(self):
        """
        Execute the follow action.
        Returns dict: {success, follows_done, errors, skipped, sources_used}
        """
        result = {
            'success': False,
            'follows_done': 0,
            'errors': 0,
            'skipped': 0,
            'sources_used': [],
        }

        # Ensure Instagram is running
        self.ctrl.ensure_app()
        self.ctrl.dismiss_popups()

        # Check daily limit
        done_today = get_today_action_count(
            self.device_serial, self.username, 'follow')
        remaining = self.daily_limit - done_today
        if remaining <= 0:
            log.info("[%s] %s: Daily follow limit reached (%d/%d)",
                     self.device_serial, self.username, done_today, self.daily_limit)
            result['success'] = True
            return result

        target = min(self.session_target, remaining)
        log.info("[%s] %s: Will follow up to %d users (done today: %d, daily limit: %d)",
                 self.device_serial, self.username, target, done_today, self.daily_limit)

        # Get recently followed users to skip
        recently_followed = get_recently_interacted(
            self.device_serial, self.username, 'follow', days=14)
        log.info("[%s] Recently followed: %d users (will skip)",
                 self.device_serial, len(recently_followed))

        # Get source accounts
        sources = get_account_sources(self.account_id, 'sources')
        if not sources:
            log.warning("[%s] %s: No source accounts configured",
                       self.device_serial, self.username)
            return result

        random.shuffle(sources)

        for source_username in sources:
            if result['follows_done'] >= target:
                break

            # Check if source is dead before wasting time searching
            dead_info = check_dead_source(self.username, source_username)
            if dead_info:
                log.info("[%s] Skipping dead source @%s (failed %d times, last: %s)",
                         self.device_serial, source_username,
                         dead_info['fail_count'], dead_info['last_failed_at'])
                result['skipped'] += 1
                continue

            log.info("[%s] Processing source: @%s", self.device_serial, source_username)
            result['sources_used'].append(source_username)

            try:
                # Dismiss any lingering popups before searching
                self.ctrl.dismiss_popups()

                follows = self._follow_from_source(
                    source_username, target - result['follows_done'],
                    recently_followed)
                result['follows_done'] += follows.get('followed', 0)
                result['errors'] += follows.get('errors', 0)
                result['skipped'] += follows.get('skipped', 0)
            except Exception as e:
                log.error("[%s] Error processing source @%s: %s",
                         self.device_serial, source_username, e)
                result['errors'] += 1
                self._recover()

            # Pause between sources
            if result['follows_done'] < target:
                random_sleep(5, 15, label="between_sources")

        result['success'] = True
        log.info("[%s] %s: Follow complete. Followed: %d, Skipped: %d, Errors: %d",
                 self.device_serial, self.username,
                 result['follows_done'], result['skipped'], result['errors'])
        return result

    def _follow_from_source(self, source_username, max_follows, already_followed):
        """
        Navigate to source user's followers and follow users.
        Returns dict: {followed, skipped, errors}
        """
        counts = {'followed': 0, 'skipped': 0, 'errors': 0}

        # Navigate to source profile via search
        if not self.ctrl.search_user(source_username):
            log.warning("[%s] Could not find source @%s",
                       self.device_serial, source_username)
            # Record failed source search
            record_dead_source(self.username, source_username)
            counts['errors'] += 1
            return counts

        # Source found — clear from dead sources if it was there
        clear_dead_source(self.username, source_username)

        random_sleep(2, 4, label="on_source_profile")

        # Open followers list
        if not self.ctrl.open_followers():
            log.warning("[%s] Could not open followers list for @%s",
                       self.device_serial, source_username)
            self.ctrl.press_back()
            counts['errors'] += 1
            return counts

        random_sleep(2, 4, label="followers_list_loaded")

        # Process followers in the list
        scroll_attempts = 0
        max_scroll_attempts = 15
        seen_usernames = set()

        while counts['followed'] < max_follows and scroll_attempts < max_scroll_attempts:
            # Parse visible followers using IGController
            users = self.ctrl.get_visible_usernames_in_list()

            new_users = [u for u in users if u not in seen_usernames]
            if not new_users:
                scroll_attempts += 1
                if scroll_attempts >= max_scroll_attempts:
                    log.info("[%s] Reached end of followers list", self.device_serial)
                    break
                self.ctrl.scroll_list("down")
                random_sleep(1, 2)
                continue

            scroll_attempts = 0

            for target_user in new_users:
                if counts['followed'] >= max_follows:
                    break

                seen_usernames.add(target_user)

                # Skip if already followed recently
                if target_user in already_followed:
                    log.debug("[%s] Skip @%s (recently followed)",
                             self.device_serial, target_user)
                    counts['skipped'] += 1
                    continue

                # Tag-based follow dedup: skip if any same-tag account already followed this user
                if self.tag_dedup_enabled and target_user in self.tag_already_followed:
                    log.debug("[%s] Skip @%s (same-tag account already followed)",
                             self.device_serial, target_user)
                    counts['skipped'] += 1
                    continue

                # Skip own username
                if target_user.lower() == self.username.lower():
                    continue

                # Try to follow this user
                try:
                    followed = self._follow_user(target_user)
                    if followed is True:
                        counts['followed'] += 1
                        already_followed.add(target_user)
                        if self.tag_dedup_enabled:
                            self.tag_already_followed.add(target_user)
                        log_action(
                            self.session_id, self.device_serial, self.username,
                            'follow', target_username=target_user, success=True)
                        log.info("[%s] Followed @%s (%d/%d)",
                                self.device_serial, target_user,
                                counts['followed'], max_follows)
                        action_delay("follow")
                    elif followed is False:
                        counts['skipped'] += 1
                    else:
                        counts['errors'] += 1
                except Exception as e:
                    log.error("[%s] Error following @%s: %s",
                             self.device_serial, target_user, e)
                    counts['errors'] += 1
                    log_action(
                        self.session_id, self.device_serial, self.username,
                        'follow', target_username=target_user, success=False,
                        error_message=str(e)[:200])

            # Scroll to see more
            self.ctrl.scroll_list("down")
            random_sleep(1.5, 3, label="scroll_followers")

        # Go back to clean state
        self.ctrl.press_back()
        time.sleep(1)
        self.ctrl.press_back()
        time.sleep(1)

        return counts

    def _follow_user(self, target_username):
        """
        Follow a user from the followers list.

        Strategy 1: Click Follow button in list row (fastest)
        Strategy 2: Visit profile, check filters, follow from there

        Returns: True=followed, False=skipped, None=error
        """
        # Strategy 1: Follow directly from list
        if not self.use_filters:
            result = self.ctrl.follow_user_from_list(target_username)
            if result is not None:
                return result

        # Strategy 2: Visit profile for filters or fallback
        return self._follow_via_profile_visit(target_username)

    def _follow_via_profile_visit(self, target_username):
        """
        Click on username to visit profile, check filters, then follow.
        Returns True/False/None.
        """
        try:
            # Click on username to open profile (use controller's device ref)
            user_el = self.ctrl.find_element(text=target_username, timeout=2)
            if user_el is None:
                user_el = self.ctrl.device(textContains=target_username)
                if not user_el.exists(timeout=2):
                    return None

            user_el.click()
            time.sleep(3)

            # Dismiss any popups that appeared on profile load
            screen = self.ctrl.detect_screen()
            if screen == Screen.POPUP:
                self.ctrl.dismiss_popups()
                time.sleep(1)

            # Check filters if enabled
            if self.use_filters and self.filters:
                profile_info = self.ctrl.get_profile_info()
                passed, reason = check_filters(profile_info, self.filters)
                if not passed:
                    log.debug("[%s] @%s filtered: %s",
                             self.device_serial, target_username, reason)
                    self.ctrl.press_back()
                    time.sleep(1)
                    return False

            # Follow from profile
            result = self.ctrl.follow_user_from_profile()
            self.ctrl.press_back()
            time.sleep(1)

            if result is True:
                return True
            elif result is False:
                return False

            # Could not find follow button — dump XML for debug
            log.debug("[%s] Follow button not found for @%s, dumping XML",
                      self.device_serial, target_username)
            self.ctrl.dump_xml(f"follow_btn_missing_{target_username}")
            return None

        except Exception as e:
            log.error("[%s] _follow_via_profile_visit error: %s",
                     self.device_serial, e)
            try:
                self.ctrl.press_back()
            except Exception:
                pass
            return None

    def _recover(self):
        """Try to recover to a known UI state."""
        try:
            self.ctrl.recover_to_home()
        except Exception:
            pass


def execute_follow(device, device_serial, account_info, session_id):
    """Convenience function to run follow action."""
    action = FollowAction(device, device_serial, account_info, session_id)
    return action.execute()
