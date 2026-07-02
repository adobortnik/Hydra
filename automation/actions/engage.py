"""
Engagement Action Module
=========================
Warmup and engagement actions using IGController:
- Story viewing (home feed stories)
- Feed scrolling (home feed warmup)
- Explore page browsing
"""

import logging
import random
import time

from automation.actions.helpers import (
    action_delay, random_sleep, log_action,
    get_account_settings, get_today_action_count,
)
from automation.ig_controller import IGController, Screen

log = logging.getLogger(__name__)


class EngageAction:
    """
    Run engagement/warmup activities on Instagram.
    Uses IGController for reliable UI control with screen state verification.
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

        # Use package from account_info if present, otherwise default
        pkg = account_info.get('package', package)
        self.ctrl = IGController(device, device_serial, pkg)

    def execute(self):
        """
        Execute engagement actions based on account settings.
        Returns dict: {success, stories_viewed, feed_scrolls, explore_scrolls}
        """
        result = {
            'success': False,
            'stories_viewed': 0,
            'feed_scrolls': 0,
            'explore_scrolls': 0,
        }

        try:
            # Ensure Instagram is running
            self.ctrl.ensure_app()

            # Dismiss any initial popups
            self.ctrl.dismiss_popups()

            # 1. View home feed stories
            if self.settings.get('enable_viewhomefeedstory', False):
                stories = self._view_home_stories()
                result['stories_viewed'] = stories

            # 2. Scroll home feed
            if self.settings.get('enable_scrollhomefeed', False):
                scrolls = self._scroll_home_feed()
                result['feed_scrolls'] = scrolls

            # 3. Scroll explore page
            if self.settings.get('enable_scrollexplorepage', False):
                explores = self._scroll_explore_page()
                result['explore_scrolls'] = explores

            result['success'] = True

        except Exception as e:
            log.error("[%s] Engagement error: %s", self.device_serial, e)

        log.info("[%s] %s: Engagement complete. Stories: %d, Feed: %d, Explore: %d",
                 self.device_serial, self.username,
                 result['stories_viewed'], result['feed_scrolls'],
                 result['explore_scrolls'])
        return result

    def _view_home_stories(self):
        """
        View stories from the home feed story bar using IGController.
        Returns number of stories viewed.
        """
        viewed = 0

        # ── Daily session cap (safe: fails open if anything errors) ──
        # `storyview_session_limit_perday` = max sessions of home-story viewing
        # per day. Default 999 = effectively unlimited (preserves legacy
        # behavior if operator never sets this field).
        try:
            _v = self.settings.get('storyview_session_limit_perday')
            cap = int(_v) if _v is not None else 999
            done = get_today_action_count(
                self.device_serial, self.username, 'story_view')
            if done >= cap:
                log.info(
                    "[%s] %s: storyview daily cap reached (%d/%d) — skipping",
                    self.device_serial, self.username, done, cap)
                return 0
        except Exception as _e:
            log.debug("[%s] storyview cap check failed: %s (proceeding)",
                      self.device_serial, _e)

        min_stories = int(self.settings.get('min_viewhomefeedstory') or 5)
        max_stories = int(self.settings.get('max_viewhomefeedstory') or 10)
        target = random.randint(min_stories, max_stories)

        log.info("[%s] Viewing up to %d home stories", self.device_serial, target)

        try:
            # Navigate to home feed
            if not self.ctrl.navigate_to(Screen.HOME_FEED):
                return 0

            time.sleep(2)

            # Scroll up to make story bar visible
            self.ctrl.scroll_feed("up")
            time.sleep(1)

            # Get story items using XML parsing
            stories = self.ctrl.get_story_items()
            unseen = [s for s in stories if not s['seen']]
            log.info("[%s] Found %d stories (%d unseen)",
                    self.device_serial, len(stories), len(unseen))

            if not unseen and stories:
                unseen = stories  # Use any story if none unseen

            if not unseen:
                log.info("[%s] No stories available", self.device_serial)
                return 0

            # Find first story that is NOT the account's own "Your story"
            # bubble. "Your story" is index 0 with username == self.username;
            # clicking it opens the ADD_CONTENT (story-creation) screen, not
            # a story viewer. Warmup accounts follow nobody, so the tray
            # often contains ONLY "Your story" — in that case we must NOT
            # click anything (the old `unseen[0]` fallback opened the story
            # camera every cycle and got stuck on "Add story").
            target_story = None
            for s in unseen:
                is_own = (s['index'] == 0 and s['username'] == self.username)
                if is_own:
                    continue
                target_story = s
                break

            if not target_story:
                log.info("[%s] No other-user stories to view "
                         "(only own 'Your story' present) — skipping",
                         self.device_serial)
                return 0

            # Click the story
            if not self.ctrl.click_story(target_story):
                log.warning("[%s] Failed to open story", self.device_serial)
                return 0

            # Watch stories
            for i in range(target):
                # Watch for a bit
                min_delay = int(self.settings.get('min_viewhomefeedstory_delay') or 3)
                max_delay = int(self.settings.get('max_viewhomefeedstory_delay') or 5)
                watch_time = random.uniform(min_delay, max_delay)
                time.sleep(watch_time)

                viewed += 1

                # Maybe like the story
                # IMPORTANT: use explicit None check — `or 50` would treat 0 as falsy
                # and overwrite with default 50, making "disable likes" impossible.
                _v = self.settings.get('percent_to_like_homefeedstory')
                like_pct = int(_v) if _v is not None else 50
                if like_pct > 0 and random.randint(1, 100) <= like_pct:
                    self.ctrl.like_story()

                # Tap to next story
                self.ctrl.tap_next_story()
                time.sleep(1)

                # Check if we're still in story view
                if not self.ctrl.is_in_story_view():
                    log.info("[%s] Story view ended after %d stories",
                            self.device_serial, viewed)
                    break

            log_action(self.session_id, self.device_serial, self.username,
                      'story_view', success=True)

            # Navigate back to feed
            if self.ctrl.is_in_story_view():
                self.ctrl.press_back()
                time.sleep(1)

        except Exception as e:
            log.error("[%s] Story viewing error: %s", self.device_serial, e)
            self.ctrl.press_back()

        return viewed

    def _scroll_home_feed(self):
        """
        Scroll through the home feed for warmup using IGController.
        Returns number of scroll actions.
        """
        # ── Daily session cap (safe: fails open if anything errors) ──
        try:
            _v = self.settings.get('homefeed_session_limit_perday')
            cap = int(_v) if _v is not None else 999
            done = get_today_action_count(
                self.device_serial, self.username, 'engage_homefeed')
            if done >= cap:
                log.info(
                    "[%s] %s: homefeed daily cap reached (%d/%d) — skipping",
                    self.device_serial, self.username, done, cap)
                return 0
        except Exception as _e:
            log.debug("[%s] homefeed cap check failed: %s (proceeding)",
                      self.device_serial, _e)

        min_scrolls = int(self.settings.get('min_scrollhomefeed') or 5)
        max_scrolls = int(self.settings.get('max_scrollhomefeed') or 10)
        target = random.randint(min_scrolls, max_scrolls)

        log.info("[%s] Scrolling home feed %d times", self.device_serial, target)

        scrolls = 0
        try:
            if not self.ctrl.navigate_to(Screen.HOME_FEED):
                return 0

            time.sleep(2)

            for _ in range(target):
                # Scroll and verify we're still on home feed
                self.ctrl.scroll_feed("down")

                min_delay = int(self.settings.get('min_scrollhomefeed_delay') or 3)
                max_delay = int(self.settings.get('max_scrollhomefeed_delay') or 5)
                random_sleep(min_delay, max_delay, label="feed_scroll")

                scrolls += 1

                # Maybe like a post while scrolling.
                # Explicit None check so 0 disables likes (0 or 50 == 50 was a bug).
                _v = self.settings.get('percent_to_like_homefeed')
                like_pct = int(_v) if _v is not None else 50
                if like_pct > 0 and random.randint(1, 100) <= like_pct:
                    if self.ctrl.like_post():
                        log_action(self.session_id, self.device_serial,
                                  self.username, 'like', success=True)

                # Dismiss any popups
                screen = self.ctrl.detect_screen()
                if screen == Screen.POPUP:
                    self.ctrl.dismiss_popups()
                elif screen != Screen.HOME_FEED:
                    # We drifted off, go back
                    log.warning("[%s] Drifted from HOME_FEED to %s during scroll",
                               self.device_serial, screen.value)
                    self.ctrl.navigate_to(Screen.HOME_FEED)

        except Exception as e:
            log.error("[%s] Feed scroll error: %s", self.device_serial, e)

        # Log the session so the daily cap counter works
        if scrolls > 0:
            try:
                log_action(self.session_id, self.device_serial, self.username,
                           'engage_homefeed', success=True)
            except Exception:
                pass
        return scrolls

    def _scroll_explore_page(self):
        """
        Browse the explore page for engagement using IGController.
        Returns number of scroll actions.
        """
        # ── Daily session cap (safe: fails open if anything errors) ──
        try:
            _v = self.settings.get('explore_session_limit_perday')
            cap = int(_v) if _v is not None else 999
            done = get_today_action_count(
                self.device_serial, self.username, 'engage_explore')
            if done >= cap:
                log.info(
                    "[%s] %s: explore daily cap reached (%d/%d) — skipping",
                    self.device_serial, self.username, done, cap)
                return 0
        except Exception as _e:
            log.debug("[%s] explore cap check failed: %s (proceeding)",
                      self.device_serial, _e)

        min_scrolls = int(self.settings.get('min_scrollexplorepage') or 5)
        max_scrolls = int(self.settings.get('max_scrollexplorepage') or 10)
        target = random.randint(min_scrolls, max_scrolls)

        log.info("[%s] Scrolling explore page %d times", self.device_serial, target)

        scrolls = 0
        try:
            if not self.ctrl.navigate_to(Screen.SEARCH):
                return 0

            time.sleep(2)

            for _ in range(target):
                self.ctrl.scroll_feed("down")

                min_delay = int(self.settings.get('min_scrollexplorepage_delay') or 5)
                max_delay = int(self.settings.get('max_scrollexplorepage_delay') or 7)
                random_sleep(min_delay, max_delay, label="explore_scroll")

                scrolls += 1

                # Maybe open and like a post.
                # Explicit None check so 0 disables likes (0 or 50 == 50 was a bug).
                _v = self.settings.get('percent_to_like_explorepagepost')
                like_pct = int(_v) if _v is not None else 50
                if like_pct > 0 and random.randint(1, 100) <= like_pct:
                    if self.ctrl.open_explore_post():
                        self.ctrl.like_post()
                        log_action(self.session_id, self.device_serial,
                                  self.username, 'like', success=True)
                        time.sleep(1)
                        self.ctrl.press_back()
                        time.sleep(1)

                # Check we're still on explore
                screen = self.ctrl.detect_screen()
                if screen == Screen.POPUP:
                    self.ctrl.dismiss_popups()
                elif screen != Screen.SEARCH:
                    self.ctrl.navigate_to(Screen.SEARCH)

        except Exception as e:
            log.error("[%s] Explore page error: %s", self.device_serial, e)

        # Navigate back to feed when done
        self.ctrl.press_back()
        time.sleep(1)

        # Log the session so the daily cap counter works
        if scrolls > 0:
            try:
                log_action(self.session_id, self.device_serial, self.username,
                           'engage_explore', success=True)
            except Exception:
                pass
        return scrolls


def execute_engage(device, device_serial, account_info, session_id):
    """Convenience function to run engagement action."""
    action = EngageAction(device, device_serial, account_info, session_id)
    return action.execute()
