"""
Browse Profiles Action Module
===============================
Makes the account look like a real user by visiting profiles
and spending time on them organically.

Behavior:
- Picks 1-3 random profiles from a configured source list
- Navigates to each profile via search
- Scrolls through their posts grid slowly
- Maybe opens 1-2 posts/reels and watches briefly
- Maybe views a highlight (optional, not forced)
- Maybe likes 1 post (configurable)
- Spends 30-120 seconds total per profile
- Returns to home feed when done
"""

import logging
import random
import time

from automation.actions.helpers import (
    random_sleep, log_action,
    get_account_settings, get_today_action_count,
)
from automation.ig_controller import IGController, Screen

log = logging.getLogger(__name__)


class BrowseProfilesAction:
    """
    Browse random profiles to appear like a normal user.
    Uses IGController for reliable UI control.
    """

    def __init__(self, device, device_serial, account_info, session_id,
                 package='com.instagram.androie'):
        self.device = device
        self.device_serial = device_serial
        self.account = account_info
        self.session_id = session_id
        self.username = account_info['username']
        self.account_id = account_info['id']
        self.settings = get_account_settings(self.account_id)

        # Use package from account_info if present
        pkg = account_info.get('package', package)
        self.ctrl = IGController(device, device_serial, pkg)

        # Load settings (guard against None values stored in DB)
        self.time_min = int(self.settings.get('browse_profiles_time_min') or 30)
        self.time_max = int(self.settings.get('browse_profiles_time_max') or 120)
        self.can_like = bool(self.settings.get('browse_profiles_can_like', True))
        self.daily_limit = int(self.settings.get('browse_profiles_limit_perday') or 10)

    def execute(self):
        """
        Execute the browse profiles action.
        Returns dict: {success, profiles_browsed, liked, errors}
        """
        result = {
            'success': False,
            'profiles_browsed': 0,
            'liked': 0,
            'errors': 0,
        }

        try:
            # Check daily limit
            done_today = get_today_action_count(
                self.device_serial, self.username, 'browse_profile')
            remaining = self.daily_limit - done_today
            if remaining <= 0:
                log.info("[%s] %s: Daily browse_profiles limit reached (%d/%d)",
                         self.device_serial, self.username, done_today, self.daily_limit)
                result['success'] = True
                return result

            # Get source usernames
            sources = self._get_sources()
            if not sources:
                log.info("[%s] %s: No browse_profiles sources configured",
                         self.device_serial, self.username)
                result['success'] = True
                return result

            # Pick 1-3 random profiles (but don't exceed remaining daily limit)
            pick_count = min(random.randint(1, 3), remaining, len(sources))
            targets = random.sample(sources, pick_count)

            log.info("[%s] %s: Will browse %d profiles: %s (done today: %d/%d)",
                     self.device_serial, self.username, len(targets),
                     ', '.join(targets), done_today, self.daily_limit)

            # Ensure Instagram is running
            self.ctrl.ensure_app()
            self.ctrl.dismiss_popups()

            for target_username in targets:
                try:
                    browsed, liked = self._browse_one_profile(target_username)
                    if browsed:
                        result['profiles_browsed'] += 1
                        result['liked'] += liked
                        log_action(
                            self.session_id, self.device_serial, self.username,
                            'browse_profile', target_username=target_username,
                            success=True)
                    else:
                        result['errors'] += 1
                        log_action(
                            self.session_id, self.device_serial, self.username,
                            'browse_profile', target_username=target_username,
                            success=False, error_message='failed_to_browse')

                    # Random pause between profiles (organic feel)
                    if target_username != targets[-1]:
                        random_sleep(3, 8, label="between_profiles")

                except Exception as e:
                    log.error("[%s] Error browsing @%s: %s",
                              self.device_serial, target_username, e)
                    result['errors'] += 1
                    # Try to recover
                    self.ctrl.press_back()
                    time.sleep(1)
                    self.ctrl.dismiss_popups()

            # Navigate back to home feed
            self.ctrl.navigate_to(Screen.HOME_FEED)
            result['success'] = True

        except Exception as e:
            log.error("[%s] browse_profiles error: %s", self.device_serial, e)

        log.info("[%s] %s: Browse profiles complete. Browsed: %d, Liked: %d, Errors: %d",
                 self.device_serial, self.username,
                 result['profiles_browsed'], result['liked'], result['errors'])
        return result

    def _get_sources(self):
        """
        Get list of source usernames from account_sources table.
        Falls back to settings_json for backwards compatibility.
        """
        from automation.actions.helpers import get_db
        try:
            conn = get_db()
            rows = conn.execute(
                "SELECT value FROM account_sources WHERE account_id = ? AND source_type = 'browse_profiles_sources' ORDER BY value",
                (self.account_id,)
            ).fetchall()
            if rows:
                return [r[0].strip().lstrip('@') for r in rows if r[0] and r[0].strip()]
        except Exception as e:
            log.debug("[%s] Failed reading account_sources: %s", self.device_serial, e)

        # Fallback: settings_json (backwards compat)
        raw = self.settings.get('browse_profiles_sources', '')
        if not raw or not isinstance(raw, str):
            return []
        usernames = [u.strip().lstrip('@') for u in raw.strip().split('\n') if u.strip()]
        return [u for u in usernames if u]

    def _browse_one_profile(self, target_username):
        """
        Browse a single profile organically.
        Returns (success: bool, likes: int).
        """
        log.info("[%s] Browsing profile: @%s", self.device_serial, target_username)
        start_time = time.time()
        likes = 0

        # Calculate how long to spend on this profile
        target_duration = random.uniform(self.time_min, self.time_max)

        # 1. Navigate to profile via search
        if not self.ctrl.search_user(target_username):
            log.warning("[%s] Could not find @%s via search",
                        self.device_serial, target_username)
            return False, 0

        random_sleep(1.5, 3, label="profile_loaded")

        # 2. Main browsing loop — keep doing organic actions until target_duration
        posts_opened = 0
        highlight_viewed = False

        while (time.time() - start_time) < target_duration:
            # Pick a random action: scroll grid, open post, view highlight
            roll = random.random()

            if roll < 0.50:
                # Scroll grid (most common)
                self._slow_scroll_down()
                random_sleep(2, 5, label="grid_scroll")

            elif roll < 0.85 and posts_opened < 3:
                # Try to open a post
                opened = self._try_open_grid_post()
                if opened:
                    posts_opened += 1
                    watch_time = random.uniform(5, 15)
                    log.debug("[%s] Watching post for %.1fs", self.device_serial, watch_time)
                    time.sleep(watch_time)

                    # Maybe like (only if enabled and random chance)
                    if self.can_like and likes == 0 and random.random() < 0.3:
                        try:
                            like_btn = self.device(descriptionContains="Like")
                            if like_btn.exists(timeout=1):
                                like_btn.click()
                                time.sleep(1)
                                likes += 1
                                log.info("[%s] Liked a post on @%s's profile",
                                         self.device_serial, target_username)
                                log_action(
                                    self.session_id, self.device_serial, self.username,
                                    'like', target_username=target_username, success=True)
                        except Exception as e:
                            log.debug("[%s] Like attempt failed: %s", self.device_serial, e)

                    # Go back to profile
                    self.ctrl.press_back()
                    random_sleep(1, 2, label="back_to_profile")
                else:
                    # Tap missed, just scroll instead
                    self._slow_scroll_down()
                    random_sleep(1, 3, label="missed_tap_scroll")

            elif not highlight_viewed and random.random() < 0.3:
                # Try to view a highlight (once per profile)
                self._try_view_highlight()
                highlight_viewed = True

            else:
                # Default: scroll
                self._slow_scroll_down()
                random_sleep(2, 4, label="default_scroll")

        # 6. Navigate back
        self.ctrl.press_back()
        time.sleep(1)

        total_time = time.time() - start_time
        log.info("[%s] Spent %.0fs on @%s's profile (target was %.0fs)",
                 self.device_serial, total_time, target_username, target_duration)

        return True, likes

    def _slow_scroll_down(self):
        """Scroll down slowly like a human browsing."""
        try:
            w, h = self.ctrl.window_size
            # Gentle scroll — not a full page swipe
            start_y = int(h * random.uniform(0.55, 0.70))
            end_y = int(h * random.uniform(0.25, 0.40))
            duration = random.uniform(0.3, 0.6)
            self.device.swipe(w // 2, start_y, w // 2, end_y, duration=duration)
        except Exception:
            self.ctrl.scroll_feed("down")

    def _try_open_grid_post(self):
        """
        Try to tap on a post in the profile grid.
        Returns True if a post was opened.
        """
        try:
            w, h = self.ctrl.window_size

            # Profile grid posts are typically in a 3-column grid
            # Below the profile header (roughly below y=50% of screen on most profiles)
            # Pick a random column (left, center, right)
            col = random.choice([0.17, 0.50, 0.83])
            # Pick a row in the visible grid area
            row_y = random.uniform(0.55, 0.80)

            tap_x = int(w * col)
            tap_y = int(h * row_y)

            log.debug("[%s] Tapping grid post at (%d, %d)", self.device_serial, tap_x, tap_y)
            self.device.click(tap_x, tap_y)
            time.sleep(2)

            # Verify we opened something (check for post/reel indicators)
            # Like button or comment field = we're on a post
            like_btn = self.device(descriptionContains="Like")
            if like_btn.exists(timeout=2):
                return True

            comment_field = self.device(textContains="Add a comment")
            if comment_field.exists(timeout=1):
                return True

            # Comment button (row_feed_button_comment)
            comment_btn = self.device(resourceIdMatches=".*row_feed_button_comment")
            if comment_btn.exists(timeout=1):
                return True

            # Might still be on profile — that's ok, the tap just missed
            log.debug("[%s] Grid tap didn't open a post", self.device_serial)
            return False

        except Exception as e:
            log.debug("[%s] Error opening grid post: %s", self.device_serial, e)
            return False

    def _try_view_highlight(self):
        """
        Try to view a story highlight on the profile.
        Very casual — if we find one, tap it and watch briefly, then exit.
        """
        try:
            # Scroll up to make sure highlights are visible (they're near the top)
            self.ctrl.scroll_feed("up")
            time.sleep(1)

            # Look for highlight circles — they're usually ImageView elements
            # in the highlight row near the top of the profile
            # Try to find elements with "highlight" in description
            highlight = self.device(descriptionContains="highlight")
            if not highlight.exists(timeout=2):
                # Try looking for the highlight tray items
                highlight = self.device(
                    resourceIdMatches=".*profile_header_story_ring.*|.*highlight.*tray.*")
            if not highlight.exists(timeout=1):
                log.debug("[%s] No highlights found", self.device_serial)
                return False

            # Click first (or random) highlight
            count = highlight.count
            if count > 0:
                idx = random.randint(0, min(count - 1, 3))
                highlight[idx].click()
                time.sleep(2)

                # Watch for a few seconds
                watch_time = random.uniform(3, 8)
                log.debug("[%s] Watching highlight for %.1fs", self.device_serial, watch_time)
                time.sleep(watch_time)

                # Exit highlight
                self.ctrl.press_back()
                time.sleep(1)
                return True

        except Exception as e:
            log.debug("[%s] Highlight view error: %s", self.device_serial, e)
            self.ctrl.press_back()
            time.sleep(1)

        return False


def execute_browse_profiles(device, device_serial, account_info, session_id):
    """Convenience function to run browse profiles action."""
    action = BrowseProfilesAction(device, device_serial, account_info, session_id)
    return action.execute()
