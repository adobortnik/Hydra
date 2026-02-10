"""
Reels Watching Action Module
=============================
Watch Instagram Reels with human-like behavior.
Uses IGController for reliable, XML-verified navigation and interaction.

Features:
- Navigate to Reels tab via IGController.navigate_to(Screen.REELS)
- Verify screen state with detect_screen() before/after actions
- Configurable watch duration per reel (min/max seconds)
- Like reels with configurable percentage (via ctrl.like_reel())
- Save reels optionally
- Daily limit tracking
- Human-like random delays between reels

Settings keys (from account_settings JSON):
  enable_watch_reels          : bool  - Master toggle
  min_reels_to_watch          : str   - Min reels per session
  max_reels_to_watch          : str   - Max reels per session
  min_sec_reel_watch          : str   - Min seconds to watch each reel
  max_sec_reel_watch          : str   - Max seconds to watch each reel
  enable_like_reel            : bool  - Whether to like reels
  like_reel_percent           : str   - Percentage chance to like (0-100)
  enable_save_reels_after_watching : bool - Whether to save reels
  watch_reel_limit_perday     : str   - Daily limit
"""

import logging
import random
import time

from automation.ig_controller import IGController, Screen
from automation.actions.helpers import (
    action_delay, random_sleep, log_action,
    get_account_settings, get_today_action_count,
)

log = logging.getLogger(__name__)


class ReelsAction:
    """Watch Instagram Reels with human-like behavior using IGController."""

    def __init__(self, device, device_serial, account_info, session_id,
                 ctrl: IGController = None, pkg: str = None):
        """
        Args:
            device: uiautomator2 device object
            device_serial: e.g. '10.1.11.4_5555'
            account_info: dict with 'username', 'id', etc.
            session_id: current session ID
            ctrl: optional pre-existing IGController instance
            pkg: IG clone package (used if ctrl not provided)
        """
        self.device = device
        self.device_serial = device_serial
        self.account = account_info
        self.session_id = session_id
        self.username = account_info['username']
        self.account_id = account_info['id']

        # Use provided controller or create new one
        if ctrl is not None:
            self.ctrl = ctrl
        else:
            _pkg = pkg or account_info.get('package', 'com.instagram.android')
            self.ctrl = IGController(device, device_serial, _pkg)

        self.settings = get_account_settings(self.account_id)
        self._init_limits()

    def _init_limits(self):
        """Initialize reel watching limits from settings."""
        self.daily_limit = int(self.settings.get('watch_reel_limit_perday', '50'))

        min_reels = int(self.settings.get('min_reels_to_watch', '10'))
        max_reels = int(self.settings.get('max_reels_to_watch', '20'))
        if min_reels <= 0:
            min_reels = 5
        if max_reels <= 0:
            max_reels = 15
        if max_reels < min_reels:
            max_reels = min_reels + 5
        self.session_target = random.randint(min_reels, max_reels)

        self.min_watch_sec = int(self.settings.get('min_sec_reel_watch', '10'))
        self.max_watch_sec = int(self.settings.get('max_sec_reel_watch', '20'))
        if self.min_watch_sec <= 0:
            self.min_watch_sec = 5
        if self.max_watch_sec <= 0:
            self.max_watch_sec = 15

        self.like_enabled = bool(self.settings.get('enable_like_reel', False))
        self.like_percent = int(self.settings.get('like_reel_percent', '40'))
        self.save_enabled = bool(self.settings.get('enable_save_reels_after_watching', False))

        log.info("[%s] Reels limits: daily=%d, session_target=%d, "
                 "watch=%d-%ds, like=%s(%d%%), save=%s",
                 self.device_serial, self.daily_limit, self.session_target,
                 self.min_watch_sec, self.max_watch_sec,
                 self.like_enabled, self.like_percent, self.save_enabled)

    def execute(self):
        """
        Execute the reels watching action.
        Returns dict with results.
        """
        result = {
            'success': False,
            'reels_watched': 0,
            'reels_liked': 0,
            'reels_saved': 0,
            'errors': 0,
        }

        # Check daily limit
        done_today = get_today_action_count(
            self.device_serial, self.username, 'reel_watch')
        remaining = self.daily_limit - done_today
        if remaining <= 0:
            log.info("[%s] Daily reel watch limit reached (%d/%d)",
                     self.device_serial, done_today, self.daily_limit)
            result['success'] = True
            return result

        target = min(self.session_target, remaining)
        log.info("[%s] Will watch up to %d reels (done today: %d)",
                 self.device_serial, target, done_today)

        try:
            # Navigate to Reels tab using IGController
            if not self.ctrl.navigate_to(Screen.REELS):
                log.error("[%s] Could not navigate to Reels tab", self.device_serial)
                result['errors'] += 1
                return result

            # Verify we're actually in reels view
            screen = self.ctrl.detect_screen()
            if screen != Screen.REELS:
                log.error("[%s] Expected REELS screen, got %s",
                          self.device_serial, screen.value)
                result['errors'] += 1
                return result

            time.sleep(3)

            # Watch reels in a loop
            for i in range(target):
                try:
                    watched = self._watch_current_reel(i + 1, target)
                    if not watched:
                        log.warning("[%s] Reel watch failed at #%d",
                                    self.device_serial, i + 1)
                        result['errors'] += 1
                        if result['errors'] >= 3:
                            log.warning("[%s] Too many reel errors, stopping",
                                        self.device_serial)
                            break
                        continue

                    result['reels_watched'] += 1

                    # Log the watch action
                    log_action(
                        self.session_id, self.device_serial, self.username,
                        'reel_watch', success=True)

                    # Maybe like the reel
                    if self.like_enabled and random.randint(1, 100) <= self.like_percent:
                        if self.ctrl.like_reel():
                            result['reels_liked'] += 1
                            log_action(
                                self.session_id, self.device_serial, self.username,
                                'reel_like', success=True)

                    # Maybe save the reel
                    if self.save_enabled and random.randint(1, 100) <= 20:
                        if self._save_current_reel():
                            result['reels_saved'] += 1

                    # Swipe to next reel using IGController
                    if i < target - 1:
                        self.ctrl.swipe_to_next_reel()
                        random_sleep(1, 3, label="reel_transition")

                        # Verify we're still in reels view
                        screen = self.ctrl.detect_screen()
                        if screen == Screen.POPUP:
                            self.ctrl.dismiss_popups()
                            time.sleep(1)
                        elif screen != Screen.REELS:
                            log.warning("[%s] Left reels view after swipe (screen=%s), recovering",
                                        self.device_serial, screen.value)
                            if not self.ctrl.navigate_to(Screen.REELS):
                                log.error("[%s] Could not recover to reels", self.device_serial)
                                break

                except Exception as e:
                    log.error("[%s] Reel #%d error: %s",
                              self.device_serial, i + 1, e)
                    result['errors'] += 1
                    if result['errors'] >= 3:
                        break

            result['success'] = True

        except Exception as e:
            log.error("[%s] Reels action error: %s", self.device_serial, e)
            result['errors'] += 1

        finally:
            # Navigate back from Reels to home
            try:
                self.ctrl.navigate_to(Screen.HOME_FEED)
            except Exception:
                try:
                    self.ctrl.press_back()
                except Exception:
                    pass

        log.info("[%s] Reels complete. Watched: %d, Liked: %d, Saved: %d, Errors: %d",
                 self.device_serial, result['reels_watched'],
                 result['reels_liked'], result['reels_saved'],
                 result['errors'])
        return result

    def _watch_current_reel(self, reel_num, total):
        """
        Watch the current reel for a random duration.
        Returns True if successfully watched.
        """
        watch_time = random.uniform(self.min_watch_sec, self.max_watch_sec)

        # Occasionally watch longer (simulates being hooked)
        if random.random() < 0.15:
            watch_time *= random.uniform(1.3, 2.0)

        # Occasionally watch shorter (simulates quick scroll-past)
        if random.random() < 0.1:
            watch_time = random.uniform(2, 5)

        log.info("[%s] Watching reel %d/%d for %.1fs",
                 self.device_serial, reel_num, total, watch_time)

        time.sleep(watch_time)

        # Small random touch during viewing (simulates natural behavior)
        if random.random() < 0.2:
            self._random_screen_touch()

        return True

    def _random_screen_touch(self):
        """Simulate a random natural touch (e.g., tapping to pause/unpause)."""
        try:
            w, h = self.ctrl.window_size
            self.device.click(w // 2, h // 2)
            time.sleep(random.uniform(0.5, 2.0))
            self.device.click(w // 2, h // 2)
        except Exception:
            pass

    def _save_current_reel(self):
        """
        Save the currently playing reel.
        Returns True on success.
        """
        try:
            xml = self.ctrl.dump_xml("reel_save")
            for rid in ['save_button', 'clips_save']:
                btn = self.ctrl._find_in_xml(xml, resource_id=rid)
                if btn and btn.get('bounds'):
                    desc = (btn.get('content_desc', '') or '').lower()
                    if 'unsave' in desc or 'saved' in desc:
                        return False  # Already saved
                    cx, cy = self.ctrl._bounds_center(btn['bounds'])
                    if cx > 0 and cy > 0:
                        self.device.click(cx, cy)
                        time.sleep(1)
                        log.debug("[%s] Saved reel", self.device_serial)
                        return True

            # Fallback: uiautomator2 selector
            save_btn = self.device(descriptionContains="Save")
            if save_btn.exists(timeout=2):
                desc = (save_btn.info.get('contentDescription', '') or '').lower()
                if 'unsave' not in desc and 'saved' not in desc:
                    save_btn.click()
                    time.sleep(1)
                    log.debug("[%s] Saved reel via desc", self.device_serial)
                    return True

        except Exception as e:
            log.debug("[%s] Reel save error: %s", self.device_serial, e)
        return False


def execute_reels(device, device_serial, account_info, session_id,
                  ctrl=None, pkg=None):
    """Convenience function to run reels watching action."""
    action = ReelsAction(device, device_serial, account_info, session_id,
                         ctrl=ctrl, pkg=pkg)
    return action.execute()
