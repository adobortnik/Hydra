"""
Save Post Action Module
========================
Save/bookmark posts from feed or source account profiles using IGController.

Modes:
- Feed: Scroll home feed and save posts by tapping the bookmark icon
- Source accounts: Navigate to source profiles, open posts, save them
"""

import logging
import random
import re
import time

from automation.actions.helpers import (
    action_delay, random_sleep, log_action,
    get_account_settings, get_account_sources,
    get_today_action_count, get_recently_interacted,
)
from automation.ig_controller import IGController, Screen

log = logging.getLogger(__name__)


class SavePostAction:
    """
    Save/bookmark posts on Instagram using IGController.
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
        """Initialize save limits."""
        self.daily_limit = int(self.settings.get('save_limit_perday', '15'))
        if self.daily_limit <= 0:
            self.daily_limit = 15

        min_save = int(self.settings.get('min_save_action', '3'))
        max_save = int(self.settings.get('max_save_action', '8'))
        if min_save <= 0:
            min_save = 3
        if max_save <= 0:
            max_save = 8
        if min_save > max_save:
            min_save, max_save = max_save, min_save
        self.session_target = random.randint(min_save, max_save)

        log.info("[%s] Save limits: daily=%d, session_target=%d",
                 self.device_serial, self.daily_limit, self.session_target)

    def execute(self):
        """
        Execute the save post action.
        Returns dict: {success, saves_done, errors}
        """
        result = {
            'success': False,
            'saves_done': 0,
            'errors': 0,
        }

        # Ensure Instagram is running
        self.ctrl.ensure_app()
        self.ctrl.dismiss_popups()

        done_today = get_today_action_count(
            self.device_serial, self.username, 'save_post')
        remaining = self.daily_limit - done_today
        if remaining <= 0:
            log.info("[%s] %s: Daily save limit reached (%d/%d)",
                     self.device_serial, self.username, done_today, self.daily_limit)
            result['success'] = True
            return result

        target = min(self.session_target, remaining)
        log.info("[%s] %s: Will save up to %d posts (done today: %d)",
                 self.device_serial, self.username, target, done_today)

        # Strategy: try source accounts first, then fall back to feed
        sources = get_account_sources(self.account_id)
        saves_from_sources = {'saved': 0, 'errors': 0}

        if sources and random.random() < 0.4:
            # 40% chance to save from source accounts
            source_target = min(target, random.randint(1, 3))
            source = random.choice(sources)
            saves_from_sources = self._save_from_source(source, source_target)
            result['saves_done'] += saves_from_sources['saved']
            result['errors'] += saves_from_sources['errors']

        # Remaining from feed
        feed_target = target - result['saves_done']
        if feed_target > 0:
            saves_from_feed = self._save_from_feed(feed_target)
            result['saves_done'] += saves_from_feed['saved']
            result['errors'] += saves_from_feed['errors']

        result['success'] = True

        log.info("[%s] %s: Save complete. Saved: %d, Errors: %d",
                 self.device_serial, self.username,
                 result['saves_done'], result['errors'])
        return result

    def _find_bookmark_button(self, xml):
        """
        Find the bookmark/save button in the current XML hierarchy.
        Returns (element_dict, already_saved) or (None, False).
        """
        # Try resource-id based selectors first
        for rid_keyword in ['bookmark', 'save']:
            elements = self.ctrl._find_all_in_xml(
                xml, resource_id=rid_keyword)
            for el in elements:
                desc = el.get('content_desc', '').lower()
                # Skip if already saved
                if 'remove' in desc or 'unsave' in desc:
                    return el, True
                if el.get('bounds'):
                    return el, False

        # Try content-desc based selectors
        for desc_keyword in ['Save', 'Bookmark', 'save']:
            el = self.ctrl._find_in_xml(xml, desc=desc_keyword)
            if el:
                desc = el.get('content_desc', '').lower()
                if 'remove' in desc or 'unsave' in desc:
                    return el, True
                if el.get('bounds'):
                    return el, False

        return None, False

    def _tap_bookmark(self, xml):
        """
        Find and tap the bookmark/save button on the currently visible post.
        Returns True if successfully saved, False otherwise.
        """
        el, already_saved = self._find_bookmark_button(xml)

        if already_saved:
            log.debug("[%s] Post already saved, skipping", self.device_serial)
            return False

        if el and el.get('bounds'):
            cx, cy = self.ctrl._bounds_center(el['bounds'])
            if cx > 0 and cy > 0:
                self.device.click(cx, cy)
                time.sleep(1.5)

                # Verify save state changed
                xml2 = self.ctrl.dump_xml("save_verify")
                el2, is_saved = self._find_bookmark_button(xml2)
                if is_saved:
                    log.info("[%s] Successfully saved post", self.device_serial)
                    return True

                # If we can't verify but we clicked, assume success
                log.info("[%s] Tapped bookmark button (unverified)",
                         self.device_serial)
                return True

        # Fallback: try uiautomator2 selectors directly
        try:
            for selector_fn in [
                lambda: self.device(resourceIdMatches=".*bookmark.*"),
                lambda: self.device(resourceIdMatches=".*save.*"),
                lambda: self.device(descriptionContains="Save"),
                lambda: self.device(descriptionContains="Bookmark"),
            ]:
                btn = selector_fn()
                if btn.exists(timeout=1):
                    info = btn.info
                    desc = info.get('contentDescription', '').lower()
                    if 'remove' in desc or 'unsave' in desc:
                        log.debug("[%s] Post already saved (u2 fallback)",
                                  self.device_serial)
                        return False
                    btn.click()
                    time.sleep(1.5)
                    log.info("[%s] Saved post via u2 fallback",
                             self.device_serial)
                    return True
        except Exception as e:
            log.debug("[%s] u2 fallback save failed: %s",
                      self.device_serial, e)

        log.debug("[%s] No save/bookmark button found", self.device_serial)
        return False

    def _save_from_feed(self, target):
        """
        Scroll through home feed and save posts.
        Returns: {saved, errors}
        """
        counts = {'saved': 0, 'errors': 0}

        if not self.ctrl.navigate_to(Screen.HOME_FEED):
            log.warning("[%s] Could not navigate to home feed",
                        self.device_serial)
            counts['errors'] += 1
            return counts

        random_sleep(2, 4, label="feed_loaded")

        # Scroll past story bar first
        self.ctrl.scroll_feed("down")
        time.sleep(1)

        scroll_attempts = 0
        max_scrolls = 30

        while counts['saved'] < target and scroll_attempts < max_scrolls:
            try:
                # Check screen state
                screen = self.ctrl.detect_screen()
                if screen == Screen.POPUP:
                    self.ctrl.dismiss_popups()
                    continue
                if screen != Screen.HOME_FEED:
                    if not self.ctrl.navigate_to(Screen.HOME_FEED):
                        break

                # Random chance to save (human-like, not every post)
                save_chance = int(self.settings.get(
                    'percent_to_save_homefeed', '30'))
                if random.randint(1, 100) <= save_chance:
                    xml = self.ctrl.dump_xml("save_from_feed")
                    if self._tap_bookmark(xml):
                        counts['saved'] += 1
                        log.info("[%s] Saved a feed post (%d/%d)",
                                 self.device_serial, counts['saved'], target)
                        log_action(
                            self.session_id, self.device_serial,
                            self.username, 'save_post', success=True)
                        action_delay("like")  # similar delay profile

                # Scroll to next post
                self._scroll_to_next_post()
                random_sleep(1.5, 4, label="between_posts")
                scroll_attempts += 1

            except Exception as e:
                log.error("[%s] Feed save error: %s", self.device_serial, e)
                counts['errors'] += 1
                scroll_attempts += 1
                self.ctrl.dismiss_popups()
                self.ctrl.scroll_feed("down")

        return counts

    def _save_from_source(self, source_username, target):
        """
        Navigate to a source account profile, open posts, and save them.
        Returns: {saved, errors}
        """
        counts = {'saved': 0, 'errors': 0}
        source = source_username.strip().lstrip('@')

        log.info("[%s] Saving posts from source @%s (target: %d)",
                 self.device_serial, source, target)

        # Navigate to source profile
        if not self.ctrl.search_user(source):
            log.warning("[%s] Could not find source @%s",
                        self.device_serial, source)
            counts['errors'] += 1
            return counts

        random_sleep(2, 4, label="on_source_profile")

        # Try to open the first post in the grid
        if not self._open_first_grid_post():
            log.warning("[%s] Could not open first post for @%s",
                        self.device_serial, source)
            self.ctrl.press_back()
            counts['errors'] += 1
            return counts

        random_sleep(1, 3, label="post_opened")

        # Save posts by scrolling through
        for i in range(target + 5):  # extra to account for already-saved
            if counts['saved'] >= target:
                break

            try:
                xml = self.ctrl.dump_xml("save_from_source")
                saved = self._tap_bookmark(xml)
                if saved:
                    counts['saved'] += 1
                    log_action(
                        self.session_id, self.device_serial,
                        self.username, 'save_post',
                        target_username=source, success=True)
                    log.info("[%s] Saved post %d from @%s (%d/%d)",
                             self.device_serial, counts['saved'],
                             source, counts['saved'], target)
                    action_delay("like")

                # Scroll to next post
                self._scroll_to_next_post()
                random_sleep(1.5, 4, label="between_source_posts")

            except Exception as e:
                log.warning("[%s] Error saving post from @%s: %s",
                            self.device_serial, source, e)
                counts['errors'] += 1

        # Navigate back
        for _ in range(3):
            self.ctrl.press_back()
            time.sleep(0.5)

        log.info("[%s] Source @%s save done. Saved %d, errors %d",
                 self.device_serial, source,
                 counts['saved'], counts['errors'])
        return counts

    def _open_first_grid_post(self):
        """
        Open the first post in a profile's grid.
        Returns True if a post was opened.
        """
        try:
            xml = self.ctrl.dump_xml("open_grid_post")

            # Look for image grid items
            for rid in ['media_set_row_content_identifier',
                        'image_button', 'media_group']:
                elements = self.ctrl._find_all_in_xml(xml, resource_id=rid)
                if elements:
                    el = elements[0]
                    if el.get('bounds'):
                        cx, cy = self.ctrl._bounds_center(el['bounds'])
                        if cx > 0 and cy > 0:
                            self.device.click(cx, cy)
                            time.sleep(2)
                            return True

            # Fallback: tap center of upper grid area
            w, h = self.ctrl.window_size
            grid_y = int(h * 0.55)
            grid_x = int(w * 0.2)
            self.device.click(grid_x, grid_y)
            time.sleep(2)

            # Verify we opened a post (should see like/comment buttons)
            xml2 = self.ctrl.dump_xml("verify_post_opened")
            for rid in ['row_feed_button_like', 'bookmark', 'save']:
                if self.ctrl._find_in_xml(xml2, resource_id=rid):
                    return True

            log.debug("[%s] Could not verify post opened after grid tap",
                      self.device_serial)
            return False

        except Exception as e:
            log.error("[%s] Error opening grid post: %s",
                      self.device_serial, e)
            return False

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


def execute_save_post(device, device_serial, account_info, session_id):
    """Convenience function to run save post action."""
    action = SavePostAction(device, device_serial, account_info, session_id)
    return action.execute()
