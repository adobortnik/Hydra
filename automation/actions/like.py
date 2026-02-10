"""
Like Action Module
===================
Like posts from feed, hashtags, or specific users using IGController.

Modes:
- Feed: Scroll home feed and like posts
- Hashtag: Navigate to hashtag and like top/recent posts
"""

import logging
import random
import subprocess
import time

from automation.actions.helpers import (
    action_delay, random_sleep, log_action,
    get_account_settings, get_account_sources,
    get_today_action_count, get_recently_interacted,
)
from automation.ig_controller import IGController, Screen

log = logging.getLogger(__name__)


class LikeAction:
    """
    Like posts on Instagram using IGController.
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

        self.settings = get_account_settings(self.account_id)
        self._init_limits()

    def _init_limits(self):
        """Initialize like limits."""
        raw = self.account.get('like_limit_perday', 'None')
        if raw and raw not in ('None', 'deprecated', ''):
            try:
                self.daily_limit = int(raw)
            except ValueError:
                self.daily_limit = 0
        else:
            self.daily_limit = int(self.settings.get('like_limit_perday', '20'))

        if self.daily_limit <= 0:
            self.daily_limit = 20

        min_like = int(self.settings.get('min_likepost_action', '10'))
        max_like = int(self.settings.get('max_likepost_action', '20'))
        if min_like <= 0:
            min_like = 5
        if max_like <= 0:
            max_like = 15
        self.session_target = random.randint(min_like, max_like)

        log.info("[%s] Like limits: daily=%d, session_target=%d",
                 self.device_serial, self.daily_limit, self.session_target)

    def execute(self):
        """
        Execute the like action.
        Returns dict: {success, likes_done, errors}
        """
        result = {
            'success': False,
            'likes_done': 0,
            'errors': 0,
        }

        # Ensure Instagram is running
        self.ctrl.ensure_app()
        self.ctrl.dismiss_popups()

        done_today = get_today_action_count(
            self.device_serial, self.username, 'like')
        remaining = self.daily_limit - done_today
        if remaining <= 0:
            log.info("[%s] %s: Daily like limit reached (%d/%d)",
                     self.device_serial, self.username, done_today, self.daily_limit)
            result['success'] = True
            return result

        target = min(self.session_target, remaining)
        log.info("[%s] %s: Will like up to %d posts (done today: %d)",
                 self.device_serial, self.username, target, done_today)

        # Strategy: like from home feed
        likes = self._like_from_feed(target)
        result['likes_done'] = likes['liked']
        result['errors'] = likes['errors']
        result['success'] = True

        log.info("[%s] %s: Like complete. Liked: %d, Errors: %d",
                 self.device_serial, self.username,
                 result['likes_done'], result['errors'])
        return result

    def _like_from_feed(self, target):
        """
        Scroll through home feed and like posts using IGController.
        Returns: {liked, errors}
        """
        counts = {'liked': 0, 'errors': 0}

        if not self.ctrl.navigate_to(Screen.HOME_FEED):
            log.warning("[%s] Could not navigate to home feed", self.device_serial)
            counts['errors'] += 1
            return counts

        random_sleep(2, 4, label="feed_loaded")

        # Scroll past story bar first
        self.ctrl.scroll_feed("down")
        time.sleep(1)

        scroll_attempts = 0
        max_scrolls = 30

        while counts['liked'] < target and scroll_attempts < max_scrolls:
            try:
                # Check screen state
                screen = self.ctrl.detect_screen()
                if screen == Screen.POPUP:
                    self.ctrl.dismiss_popups()
                    continue
                if screen != Screen.HOME_FEED:
                    if not self.ctrl.navigate_to(Screen.HOME_FEED):
                        break

                # Random chance to skip (human-like)
                like_chance = int(self.settings.get('percent_to_like_homefeed', '50'))
                if random.randint(1, 100) <= like_chance:
                    # Try to like the visible post
                    if self.ctrl.like_post():
                        counts['liked'] += 1
                        log.info("[%s] Liked a feed post (%d/%d)",
                                self.device_serial, counts['liked'], target)
                        log_action(
                            self.session_id, self.device_serial, self.username,
                            'like', success=True)
                        action_delay("like")

                # Scroll to next post
                self._scroll_to_next_post()
                random_sleep(1.5, 4, label="between_posts")
                scroll_attempts += 1

            except Exception as e:
                log.error("[%s] Feed like error: %s", self.device_serial, e)
                counts['errors'] += 1
                scroll_attempts += 1
                self.ctrl.dismiss_popups()
                self.ctrl.scroll_feed("down")

        return counts

    def _scroll_to_next_post(self):
        """Scroll feed to approximately the next post."""
        try:
            w, h = self.ctrl.window_size
            start_y = int(h * 0.75)
            end_y = int(h * 0.25)
            self.device.swipe(w // 2, start_y, w // 2, end_y, duration=0.4)
            time.sleep(1)
        except Exception:
            self.ctrl.scroll_feed("down")

    def like_from_hashtag(self, hashtag, target=5):
        """
        Navigate to a hashtag and like posts there using IGController.
        Returns: {liked, errors}
        """
        counts = {'liked': 0, 'errors': 0}

        if not self.ctrl.navigate_to(Screen.SEARCH):
            counts['errors'] += 1
            return counts

        time.sleep(2)

        # Click search bar
        search_bar = self.ctrl.find_element(resource_id='action_bar_search_edit_text')
        if not search_bar:
            search_bar = self.ctrl.find_element(class_name='android.widget.EditText')
        if not search_bar:
            counts['errors'] += 1
            return counts

        search_bar.click()
        time.sleep(1)
        search_bar.clear_text()

        # Type hashtag via ADB
        self.ctrl.type_text('#' + hashtag)
        time.sleep(3)

        # Click hashtag result
        hashtag_result = self.device(textContains='#' + hashtag)
        if hashtag_result.exists(timeout=5):
            hashtag_result.click()
            time.sleep(3)

            # Click first post
            first_post = self.device(resourceIdMatches=self.ctrl._rid_match('image_button'))
            if first_post.exists(timeout=3):
                first_post.click()
                time.sleep(2)

                for _ in range(target):
                    if self.ctrl.like_post():
                        counts['liked'] += 1
                        log_action(
                            self.session_id, self.device_serial, self.username,
                            'like', success=True)
                        action_delay("like")
                    self._scroll_to_next_post()
                    random_sleep(2, 5)

        # Navigate back
        for _ in range(3):
            self.ctrl.press_back()
            time.sleep(1)

        return counts


def execute_like(device, device_serial, account_info, session_id):
    """Convenience function to run like action."""
    action = LikeAction(device, device_serial, account_info, session_id)
    return action.execute()
