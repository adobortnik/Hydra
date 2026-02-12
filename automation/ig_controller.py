"""
IGController — Screenshot-Driven Instagram Automation Core
============================================================
Reliable UI control that ALWAYS verifies screen state before/after actions.
Uses XML hierarchy parsing (NOT blind coordinate clicks).
"""

import logging
import os
import re
import subprocess
import time
import datetime
from enum import Enum
from typing import Optional, Dict, List, Tuple

log = logging.getLogger(__name__)

# Screen states
class Screen(str, Enum):
    HOME_FEED = "HOME_FEED"
    SEARCH = "SEARCH"
    PROFILE = "PROFILE"
    REELS = "REELS"
    STORY_VIEW = "STORY_VIEW"
    FOLLOWERS_LIST = "FOLLOWERS_LIST"
    FOLLOWING_LIST = "FOLLOWING_LIST"
    DM_INBOX = "DM_INBOX"
    DM_THREAD = "DM_THREAD"
    COMMENT_VIEW = "COMMENT_VIEW"
    LOGIN = "LOGIN"
    POPUP = "POPUP"
    ADD_CONTENT = "ADD_CONTENT"     # "Add to story" / new post screen
    EDIT_PROFILE = "EDIT_PROFILE"
    UNKNOWN = "UNKNOWN"


class IGController:
    """
    Core Instagram UI controller using XML hierarchy analysis.
    Every action is verified via screenshot + XML dump.
    """

    def __init__(self, device, device_serial: str, package: str):
        """
        Args:
            device: uiautomator2 device object
            device_serial: e.g. '10.1.11.4_5555' (DB format)
            package: IG clone package e.g. 'com.instagram.androie'
        """
        self.device = device
        self.device_serial = device_serial
        self.adb_serial = device_serial.replace('_', ':')
        self.package = package

        # Ensure test_results dir
        self.results_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'test_results'
        )
        os.makedirs(self.results_dir, exist_ok=True)

        # Cache window size
        self._window_size = None

        # Last known state
        self._last_xml = None
        self._last_screen = Screen.UNKNOWN
        self._action_counter = 0

    # -----------------------------------------------------------------------
    # Window size (cached)
    # -----------------------------------------------------------------------
    @property
    def window_size(self) -> Tuple[int, int]:
        if self._window_size is None:
            self._window_size = self.device.window_size()
        return self._window_size

    # -----------------------------------------------------------------------
    # Screenshot + XML Dump
    # -----------------------------------------------------------------------
    def screenshot(self, name: str = "screen") -> 'PIL.Image':
        """Take screenshot, save to test_results/{name}.png, return PIL image."""
        self._action_counter += 1
        fname = f"{self._action_counter:03d}_{name}.png"
        fpath = os.path.join(self.results_dir, fname)
        try:
            img = self.device.screenshot()
            img.save(fpath)
            log.debug("[%s] Screenshot saved: %s", self.device_serial, fname)
            return img
        except Exception as e:
            log.error("[%s] Screenshot failed: %s", self.device_serial, e)
            return None

    def dump_xml(self, name: str = "hierarchy") -> str:
        """Dump UI hierarchy XML, save to test_results/{name}.xml, return string."""
        fname = f"{self._action_counter:03d}_{name}.xml"
        fpath = os.path.join(self.results_dir, fname)
        try:
            xml = self.device.dump_hierarchy()
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(xml)
            self._last_xml = xml
            log.debug("[%s] XML dumped: %s (%d bytes)", self.device_serial, fname, len(xml))
            return xml
        except Exception as e:
            log.error("[%s] XML dump failed: %s", self.device_serial, e)
            return ""

    # -----------------------------------------------------------------------
    # Resource ID helper (auto-adds package prefix)
    # -----------------------------------------------------------------------
    def _rid(self, short_id: str) -> str:
        """Build full resource ID from short name. e.g. 'feed_tab' -> 'com.instagram.androie:id/feed_tab'"""
        if ':id/' in short_id:
            return short_id
        return f"{self.package}:id/{short_id}"

    def _rid_match(self, short_id: str) -> str:
        """Build regex pattern for resourceIdMatches. Matches any package prefix."""
        return f".*{short_id}$"

    # -----------------------------------------------------------------------
    # Screen Detection
    # -----------------------------------------------------------------------
    def detect_screen(self, xml: str = None) -> Screen:
        """
        Detect current screen state from XML hierarchy.
        Returns Screen enum value.
        """
        if xml is None:
            xml = self.dump_xml("detect_screen")
        if not xml:
            return Screen.UNKNOWN

        xml_lower = xml.lower()

        # Check if our app is even in foreground
        try:
            current_pkg = self.device.app_current().get('package', '')
            if current_pkg != self.package:
                log.warning("[%s] Wrong app in foreground: %s (expected %s)",
                           self.device_serial, current_pkg, self.package)
                return Screen.UNKNOWN
        except Exception:
            pass

        # --- Popup/Dialog detection (highest priority) ---
        # NOTE: modal_container and overlay_layout_container are ALWAYS present
        # in IG's XML, even on clean home screen. Do NOT use them as indicators.
        # Only match elements that appear when an actual dialog/sheet is visible.
        popup_indicators = [
            f'{self.package}:id/action_sheet_container',
            f'{self.package}:id/dialog_container',
            f'{self.package}:id/igds_prompt',
            f'{self.package}:id/prompt_container',
            f'{self.package}:id/comment_composer_parent',
        ]
        # Check for text-based popup indicators
        popup_texts = ['Not Now', 'Not now', 'Turn on Notifications',
                       'Save Your Login Info', 'Add Your Phone Number',
                       'Save your login info']
        has_popup = False
        for indicator in popup_indicators:
            if indicator in xml:
                has_popup = True
                break
        if not has_popup:
            for text in popup_texts:
                if f'text="{text}"' in xml:
                    has_popup = True
                    break
        if has_popup:
            self._last_screen = Screen.POPUP
            return Screen.POPUP

        # --- Login detection ---
        login_indicators = [
            'login_username', 'login_password', 'log_in_button',
            'Sign up', 'Log in', 'Create new account'
        ]
        login_count = sum(1 for ind in login_indicators if ind in xml)
        if login_count >= 2:
            self._last_screen = Screen.LOGIN
            return Screen.LOGIN

        # --- DM Thread (inside a conversation) --- [BEFORE story detection]
        dm_thread_indicators = [
            f'{self.package}:id/row_thread_composer_edittext',
            f'{self.package}:id/row_thread_composer_button_send',
            f'{self.package}:id/thread_message_list',
        ]
        if any(ind in xml for ind in dm_thread_indicators):
            self._last_screen = Screen.DM_THREAD
            return Screen.DM_THREAD

        # --- DM Inbox --- [BEFORE story detection]
        # DM inbox has a "Notes" area with reel_viewer_front_avatar elements,
        # which causes false STORY_VIEW detection. Check DM indicators first.
        dm_inbox_indicators = [
            f'{self.package}:id/inbox_refreshable_thread_list_recyclerview',
            f'{self.package}:id/inbox_tab',
            f'{self.package}:id/direct_thread',
        ]
        # Primary check: the thread list recyclerview is definitive
        if f'{self.package}:id/inbox_refreshable_thread_list_recyclerview' in xml:
            self._last_screen = Screen.DM_INBOX
            return Screen.DM_INBOX
        # Secondary: other DM indicators + notes area (reel_viewer_front_avatar)
        if any(ind in xml for ind in dm_inbox_indicators[1:]):
            self._last_screen = Screen.DM_INBOX
            return Screen.DM_INBOX
        # Tertiary: action bar title + reel_viewer_front_avatar (Notes in DM inbox)
        if (f'{self.package}:id/reel_viewer_front_avatar' in xml
                and f'{self.package}:id/igds_action_bar_title' in xml):
            self._last_screen = Screen.DM_INBOX
            return Screen.DM_INBOX

        # --- Comment View (bottom sheet) ---
        comment_view_indicators = [
            f'{self.package}:id/layout_comment_thread_edittext',
            f'{self.package}:id/comment_composer_parent',
        ]
        if any(ind in xml for ind in comment_view_indicators):
            self._last_screen = Screen.COMMENT_VIEW
            return Screen.COMMENT_VIEW

        # --- Story View detection ---
        story_indicators = [
            f'{self.package}:id/reel_viewer_root',
            f'{self.package}:id/story_viewer',
            f'{self.package}:id/reel_viewer_texture_view',
        ]
        if any(ind in xml for ind in story_indicators):
            self._last_screen = Screen.STORY_VIEW
            return Screen.STORY_VIEW
        # Fallback: check for reel_viewer in any form
        # Exclude reel_viewer_front_avatar (DM Notes area element)
        if 'reel_viewer' in xml_lower and 'reels_tray' not in xml_lower:
            # Make sure it's not just the Notes avatar in DM inbox
            has_real_reel_viewer = False
            for reel_rid in ['reel_viewer_root', 'reel_viewer_texture_view',
                             'story_viewer', 'reel_viewer_title']:
                if reel_rid in xml:
                    has_real_reel_viewer = True
                    break
            # If only reel_viewer_front_avatar, it's NOT a story view
            if has_real_reel_viewer:
                self._last_screen = Screen.STORY_VIEW
                return Screen.STORY_VIEW
            # Check if reel_viewer appears in contexts other than front_avatar
            reel_matches = re.findall(r'reel_viewer(?!_front_avatar)', xml)
            if reel_matches:
                self._last_screen = Screen.STORY_VIEW
                return Screen.STORY_VIEW

        # --- Add content / camera screen ---
        if 'Add to story' in xml or 'add_to_story' in xml_lower:
            self._last_screen = Screen.ADD_CONTENT
            return Screen.ADD_CONTENT

        # --- Edit Profile (actual edit screen, not just the button on profile) ---
        # The profile page has a button with desc="Edit profile", but the actual
        # edit screen has specific input fields like name_field, username_field, bio_field
        edit_profile_indicators = [
            f'{self.package}:id/name_field',
            f'{self.package}:id/username_field',
            f'{self.package}:id/bio_field',
            f'{self.package}:id/change_avatar',
        ]
        if any(ind in xml for ind in edit_profile_indicators):
            self._last_screen = Screen.EDIT_PROFILE
            return Screen.EDIT_PROFILE

        # --- Followers/Following List ---
        if f'{self.package}:id/unified_follow_list_tab_layout' in xml:
            # Determine which tab is active by checking tab text
            if re.search(r'text="\d+\s*following"', xml_lower):
                # Check if "following" tab is selected
                pass
            if re.search(r'text=".*followers?"', xml, re.IGNORECASE):
                # If followers tab visible, could be either
                self._last_screen = Screen.FOLLOWERS_LIST
                return Screen.FOLLOWERS_LIST

        if 'follow_list_username' in xml:
            # We're in some follow list
            self._last_screen = Screen.FOLLOWERS_LIST
            return Screen.FOLLOWERS_LIST

        # --- Tab-based screen detection ---
        # Check which tab is selected
        feed_tab = self._find_in_xml(xml, resource_id='feed_tab')
        search_tab = self._find_in_xml(xml, resource_id='search_tab')
        profile_tab = self._find_in_xml(xml, resource_id='profile_tab')
        clips_tab = self._find_in_xml(xml, resource_id='clips_tab')

        if feed_tab and feed_tab.get('selected') == 'true':
            self._last_screen = Screen.HOME_FEED
            return Screen.HOME_FEED
        if search_tab and search_tab.get('selected') == 'true':
            self._last_screen = Screen.SEARCH
            return Screen.SEARCH
        if profile_tab and profile_tab.get('selected') == 'true':
            self._last_screen = Screen.PROFILE
            return Screen.PROFILE
        if clips_tab and clips_tab.get('selected') == 'true':
            self._last_screen = Screen.REELS
            return Screen.REELS

        # --- Fallback: check for key elements ---
        if 'reels_tray_container' in xml and ('row_feed' in xml or 'feed_tab' in xml):
            self._last_screen = Screen.HOME_FEED
            return Screen.HOME_FEED
        if 'clips_viewer' in xml_lower or 'clips_tab' in xml:
            self._last_screen = Screen.REELS
            return Screen.REELS

        self._last_screen = Screen.UNKNOWN
        return Screen.UNKNOWN

    def _find_in_xml(self, xml: str, resource_id: str = None,
                     text: str = None, desc: str = None) -> Optional[Dict]:
        """
        Find a single element in raw XML by attribute.
        Returns dict of attributes or None.
        """
        # Build pattern based on what we're searching for
        if resource_id:
            # Match with or without package prefix
            pattern = r'<node[^>]*resource-id="[^"]*' + re.escape(resource_id) + r'"[^>]*'
        elif text:
            pattern = r'<node[^>]*text="' + re.escape(text) + r'"[^>]*'
        elif desc:
            pattern = r'<node[^>]*content-desc="[^"]*' + re.escape(desc) + r'[^"]*"[^>]*'
        else:
            return None

        match = re.search(pattern, xml)
        if not match:
            return None

        node_str = match.group(0)
        attrs = {}
        for attr_name in ['resource-id', 'class', 'text', 'content-desc',
                          'clickable', 'selected', 'bounds', 'checked',
                          'enabled', 'focusable', 'scrollable']:
            m = re.search(rf'{attr_name}="([^"]*)"', node_str)
            if m:
                attrs[attr_name.replace('-', '_')] = m.group(1)
        return attrs

    def _find_all_in_xml(self, xml: str, resource_id: str = None,
                         text: str = None, desc_pattern: str = None,
                         class_name: str = None) -> List[Dict]:
        """Find all matching elements in raw XML. Returns list of attribute dicts."""
        if resource_id:
            pattern = r'<node[^>]*resource-id="[^"]*' + re.escape(resource_id) + r'"[^>]*'
        elif text:
            pattern = r'<node[^>]*text="' + re.escape(text) + r'"[^>]*'
        elif desc_pattern:
            pattern = r'<node[^>]*content-desc="' + desc_pattern + r'"[^>]*'
        elif class_name:
            pattern = r'<node[^>]*class="[^"]*' + re.escape(class_name) + r'"[^>]*'
        else:
            return []

        results = []
        for match in re.finditer(pattern, xml):
            node_str = match.group(0)
            attrs = {}
            for attr_name in ['resource-id', 'class', 'text', 'content-desc',
                              'clickable', 'selected', 'bounds', 'checked',
                              'enabled', 'focusable', 'scrollable', 'index']:
                m = re.search(rf'{attr_name}="([^"]*)"', node_str)
                if m:
                    attrs[attr_name.replace('-', '_')] = m.group(1)
            results.append(attrs)
        return results

    def _parse_bounds(self, bounds_str: str) -> Tuple[int, int, int, int]:
        """Parse bounds string '[x1,y1][x2,y2]' into (x1, y1, x2, y2)."""
        m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str)
        if m:
            return int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return 0, 0, 0, 0

    def _bounds_center(self, bounds_str: str) -> Tuple[int, int]:
        """Get center coordinates from bounds string."""
        x1, y1, x2, y2 = self._parse_bounds(bounds_str)
        return (x1 + x2) // 2, (y1 + y2) // 2

    # -----------------------------------------------------------------------
    # Navigation
    # -----------------------------------------------------------------------
    def navigate_to(self, target: Screen, max_attempts: int = 3) -> bool:
        """
        Navigate to target screen. Verifies arrival.
        Returns True if we're on the target screen.
        """
        for attempt in range(max_attempts):
            current = self.detect_screen()
            if current == target:
                log.info("[%s] Already on %s", self.device_serial, target.value)
                return True

            log.info("[%s] Navigating to %s (attempt %d, currently on %s)",
                    self.device_serial, target.value, attempt + 1, current.value)

            # Handle special cases first
            if current == Screen.POPUP:
                self.dismiss_popups()
                time.sleep(1)
                continue

            if current == Screen.STORY_VIEW:
                # Press back to exit story
                self.device.press('back')
                time.sleep(2)
                continue

            if current == Screen.ADD_CONTENT:
                self.device.press('back')
                time.sleep(2)
                continue

            if current == Screen.EDIT_PROFILE:
                self.device.press('back')
                time.sleep(2)
                continue

            if current == Screen.UNKNOWN:
                # Try to ensure we're in our app
                if not self.is_correct_app():
                    self.launch_app()
                    time.sleep(4)
                    continue

            # Navigate using tab bar
            success = False
            if target == Screen.HOME_FEED:
                success = self._click_tab('feed_tab', 'Home')
            elif target == Screen.SEARCH:
                success = self._click_tab('search_tab', 'Search and explore')
            elif target == Screen.PROFILE:
                success = self._click_tab('profile_tab', 'Profile')
            elif target == Screen.REELS:
                success = self._click_tab('clips_tab', 'Reels')

            if success:
                time.sleep(2)
                # Verify we arrived
                current = self.detect_screen()
                if current == target:
                    log.info("[%s] Successfully navigated to %s", self.device_serial, target.value)
                    return True
                else:
                    log.warning("[%s] Navigation to %s failed, landed on %s",
                               self.device_serial, target.value, current.value)
            else:
                # Tab click failed, try pressing back first
                self.device.press('back')
                time.sleep(1)

        log.error("[%s] Failed to navigate to %s after %d attempts",
                 self.device_serial, target.value, max_attempts)
        return False

    def _click_tab(self, tab_id: str, fallback_desc: str) -> bool:
        """Click a bottom navigation tab by resource ID or content-desc."""
        # Try resource ID first
        tab = self.device(resourceIdMatches=self._rid_match(tab_id))
        if tab.exists(timeout=3):
            tab.click()
            return True

        # Try content-desc fallback
        tab = self.device(description=fallback_desc)
        if tab.exists(timeout=2):
            tab.click()
            return True

        log.warning("[%s] Tab not found: %s / %s", self.device_serial, tab_id, fallback_desc)
        return False

    # -----------------------------------------------------------------------
    # Popup Dismissal
    # -----------------------------------------------------------------------
    def dismiss_popups(self, max_attempts: int = 5) -> int:
        """
        Dismiss any modals/popups/notifications.
        Returns number of popups dismissed.
        """
        dismissed = 0

        for attempt in range(max_attempts):
            xml = self.dump_xml(f"dismiss_popup_{attempt}")
            if not xml:
                break

            # Look for dismissal buttons in priority order
            # Includes Android permission dialog buttons (com.google.android.permissioncontroller)
            dismiss_patterns = [
                ('text', 'While using the app'),
                ('text', 'WHILE USING THE APP'),
                ('text', 'Allow'),
                ('text', 'ALLOW'),
                ('text', 'Not Now'),
                ('text', 'Not now'),
                ('text', 'Cancel'),
                ('text', 'Skip'),
                ('text', 'Dismiss'),
                ('text', 'Close'),
                ('text', 'No Thanks'),
                ('text', 'Maybe Later'),
                ('text', 'OK'),
                ('text', 'Got it'),
                ('desc', 'Close'),
                ('desc', 'Dismiss'),
            ]

            found = False
            for match_type, match_val in dismiss_patterns:
                if match_type == 'text':
                    btn = self.device(text=match_val)
                else:
                    btn = self.device(description=match_val)

                if btn.exists(timeout=1):
                    try:
                        btn.click()
                        dismissed += 1
                        found = True
                        log.info("[%s] Dismissed popup with '%s'", self.device_serial, match_val)
                        time.sleep(1.5)
                        break
                    except Exception as e:
                        log.debug("[%s] Failed to click '%s': %s", self.device_serial, match_val, e)

            if not found:
                # No more popups found
                break

        if dismissed > 0:
            log.info("[%s] Dismissed %d popups total", self.device_serial, dismissed)
        return dismissed

    # -----------------------------------------------------------------------
    # Element Finding (XML-based)
    # -----------------------------------------------------------------------
    def find_element(self, resource_id: str = None, text: str = None,
                     desc: str = None, class_name: str = None,
                     timeout: float = 5) -> Optional[object]:
        """
        Find element using uiautomator2 selectors.
        Tries resource ID match first, then text, then desc.
        Returns u2 element or None.
        """
        if resource_id:
            el = self.device(resourceIdMatches=self._rid_match(resource_id))
            if el.exists(timeout=timeout):
                return el

        if text:
            el = self.device(text=text)
            if el.exists(timeout=timeout):
                return el

        if desc:
            el = self.device(description=desc)
            if el.exists(timeout=timeout):
                return el
            # Try contains
            el = self.device(descriptionContains=desc)
            if el.exists(timeout=timeout):
                return el

        if class_name:
            el = self.device(className=class_name)
            if el.exists(timeout=timeout):
                return el

        return None

    def find_elements(self, resource_id: str = None, text: str = None,
                      desc_contains: str = None, desc_matches: str = None,
                      timeout: float = 3) -> list:
        """
        Find multiple elements matching criteria.
        Returns list of u2 elements (may be empty).
        """
        if resource_id:
            els = self.device(resourceIdMatches=self._rid_match(resource_id))
            if els.exists(timeout=timeout):
                return els
        if text:
            els = self.device(text=text)
            if els.exists(timeout=timeout):
                return els
        if desc_contains:
            els = self.device(descriptionContains=desc_contains)
            if els.exists(timeout=timeout):
                return els
        if desc_matches:
            els = self.device(descriptionMatches=desc_matches)
            if els.exists(timeout=timeout):
                return els
        return []

    # -----------------------------------------------------------------------
    # Scrolling
    # -----------------------------------------------------------------------
    def scroll_feed(self, direction: str = "down", amount: float = 0.4) -> bool:
        """
        Scroll the current feed. Verify we're still on the right screen after.

        Args:
            direction: 'down' or 'up'
            amount: fraction of screen to scroll (0.0-1.0)

        Returns True if scroll succeeded and we're still on expected screen.
        """
        screen_before = self.detect_screen()
        w, h = self.window_size

        # Calculate swipe coordinates
        cx = w // 2
        if direction == "down":
            sy = int(h * 0.70)
            ey = int(h * (0.70 - amount))
        else:
            sy = int(h * 0.30)
            ey = int(h * (0.30 + amount))

        # Clamp
        ey = max(50, min(ey, h - 50))
        sy = max(50, min(sy, h - 50))

        try:
            duration = 0.3 + (0.3 * amount)  # Longer swipe for bigger scrolls
            self.device.swipe(cx, sy, cx, ey, duration=duration)
            time.sleep(1)

            # Verify we're still on the same screen
            screen_after = self.detect_screen()
            if screen_after != screen_before:
                log.warning("[%s] Screen changed during scroll: %s -> %s",
                           self.device_serial, screen_before.value, screen_after.value)
                # If we accidentally entered a story or something, go back
                if screen_after == Screen.STORY_VIEW:
                    self.device.press('back')
                    time.sleep(1)
                return False

            return True

        except Exception as e:
            log.error("[%s] Scroll failed: %s", self.device_serial, e)
            return False

    # -----------------------------------------------------------------------
    # Wait for Element
    # -----------------------------------------------------------------------
    def wait_for_element(self, resource_id: str = None, text: str = None,
                         desc: str = None, timeout: int = 10) -> bool:
        """Wait for element to appear in hierarchy. Returns True if found."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            el = self.find_element(resource_id=resource_id, text=text,
                                   desc=desc, timeout=1)
            if el is not None:
                return True
            time.sleep(0.5)
        return False

    # -----------------------------------------------------------------------
    # App Management
    # -----------------------------------------------------------------------
    def is_correct_app(self) -> bool:
        """Verify our IG clone is in foreground."""
        try:
            current = self.device.app_current()
            return current.get('package', '') == self.package
        except Exception:
            return False

    def launch_app(self) -> bool:
        """Launch our IG clone package."""
        try:
            self.device.app_start(self.package)
            time.sleep(4)
            return self.is_correct_app()
        except Exception as e:
            log.error("[%s] Failed to launch %s: %s", self.device_serial, self.package, e)
            return False

    def ensure_app(self) -> bool:
        """Ensure IG is running and in foreground."""
        if self.is_correct_app():
            return True
        return self.launch_app()

    # -----------------------------------------------------------------------
    # Story Operations
    # -----------------------------------------------------------------------
    def get_story_items(self, xml: str = None) -> List[Dict]:
        """
        Get all story items from the story bar.
        Returns list of dicts with: username, index, total, seen, bounds
        """
        if xml is None:
            xml = self.dump_xml("story_items")
        if not xml:
            return []

        # Pattern: "username's story, N of M, Unseen/Seen."
        story_pattern = r'content-desc="([^"]+?)\'s story, (\d+) of (\d+), (Unseen|Seen)\."'
        items = []

        for match in re.finditer(story_pattern, xml):
            # Find the node this desc belongs to
            # Get the surrounding node's bounds
            desc_str = match.group(0)
            pos = match.start()
            # Look backwards for the node start
            node_start = xml.rfind('<node', 0, pos)
            node_end = xml.find('>', pos)
            if node_start >= 0 and node_end >= 0:
                node_str = xml[node_start:node_end + 1]
                bounds_m = re.search(r'bounds="([^"]*)"', node_str)
                bounds = bounds_m.group(1) if bounds_m else ''
            else:
                bounds = ''

            items.append({
                'username': match.group(1),
                'index': int(match.group(2)),
                'total': int(match.group(3)),
                'seen': match.group(4) == 'Seen',
                'bounds': bounds,
            })

        # Deduplicate (avatar_image_view and container both have the desc)
        seen_usernames = set()
        unique_items = []
        for item in items:
            if item['username'] not in seen_usernames:
                seen_usernames.add(item['username'])
                unique_items.append(item)

        return unique_items

    def click_story(self, story_item: Dict) -> bool:
        """Click a story item from get_story_items() result."""
        if not story_item.get('bounds'):
            log.warning("[%s] Story item has no bounds", self.device_serial)
            return False

        cx, cy = self._bounds_center(story_item['bounds'])
        if cx == 0 and cy == 0:
            return False

        log.info("[%s] Clicking story: %s (index %d, %s)",
                self.device_serial, story_item['username'],
                story_item['index'], 'Seen' if story_item['seen'] else 'Unseen')

        self.device.click(cx, cy)
        time.sleep(3)

        # Verify we entered story view
        screen = self.detect_screen()
        if screen == Screen.STORY_VIEW:
            return True

        log.warning("[%s] Expected STORY_VIEW after click, got %s",
                   self.device_serial, screen.value)
        return False

    def tap_next_story(self) -> bool:
        """Tap right side of screen to advance to next story."""
        w, h = self.window_size
        self.device.click(int(w * 0.85), int(h * 0.5))
        time.sleep(1)
        return True

    def is_in_story_view(self, xml: str = None) -> bool:
        """Check if we're currently viewing a story."""
        if xml is None:
            xml = self.dump_xml("story_check")
        return self.detect_screen(xml) == Screen.STORY_VIEW

    # -----------------------------------------------------------------------
    # Feed Operations
    # -----------------------------------------------------------------------
    def get_visible_posts(self, xml: str = None) -> List[Dict]:
        """
        Get info about visible feed posts.
        Returns list of dicts with: author, desc, has_like_btn, liked
        """
        if xml is None:
            xml = self.dump_xml("visible_posts")
        if not xml:
            return []

        posts = []

        # Find post headers
        headers = self._find_all_in_xml(xml, resource_id='row_feed_profile_header')
        for header in headers:
            post = {
                'header_desc': header.get('content_desc', ''),
                'bounds': header.get('bounds', ''),
            }
            posts.append(post)

        # Find like buttons
        like_btns = self._find_all_in_xml(xml, resource_id='row_feed_button_like')
        for i, btn in enumerate(like_btns):
            desc = btn.get('content_desc', '')
            if i < len(posts):
                posts[i]['like_btn_bounds'] = btn.get('bounds', '')
                posts[i]['liked'] = 'liked' in desc.lower() and 'like' != desc.lower()

        return posts

    def like_visible_post(self) -> bool:
        """
        Find and click the like button on the currently visible post.
        Returns True if successfully liked.
        """
        xml = self.dump_xml("like_post")

        # Find like button
        like_btns = self._find_all_in_xml(xml, resource_id='row_feed_button_like')
        for btn in like_btns:
            desc = btn.get('content_desc', '').lower()
            bounds = btn.get('bounds', '')

            # Skip if already liked
            if desc == 'liked':
                log.debug("[%s] Post already liked", self.device_serial)
                return False

            if desc == 'like' and bounds:
                cx, cy = self._bounds_center(bounds)
                if cx > 0 and cy > 0:
                    self.device.click(cx, cy)
                    time.sleep(1)

                    # Verify
                    xml2 = self.dump_xml("like_verify")
                    like_btns2 = self._find_all_in_xml(xml2, resource_id='row_feed_button_like')
                    for btn2 in like_btns2:
                        if btn2.get('content_desc', '').lower() == 'liked':
                            log.info("[%s] Successfully liked post", self.device_serial)
                            return True

                    log.warning("[%s] Like click didn't change state", self.device_serial)
                    return False

        log.debug("[%s] No likeable post visible", self.device_serial)
        return False

    # -----------------------------------------------------------------------
    # Search Operations
    # -----------------------------------------------------------------------
    def search_user(self, username: str) -> bool:
        """
        Search for a user and open their profile.
        Handles slow-loading clone apps: types query, submits search,
        switches to Accounts tab, then finds the user.
        Returns True if profile page is confirmed open.
        """
        if not self.navigate_to(Screen.SEARCH):
            return False

        time.sleep(1)

        # Click on search bar
        search_bar = self.find_element(resource_id='action_bar_search_edit_text', timeout=3)
        if search_bar is None:
            search_bar = self.find_element(class_name='android.widget.EditText', timeout=3)
        if search_bar is None:
            log.warning("[%s] Search bar not found", self.device_serial)
            return False

        search_bar.click()
        time.sleep(1)
        search_bar.clear_text()
        time.sleep(0.5)

        # Type via ADB for reliability
        subprocess.run(
            ['adb', '-s', self.adb_serial, 'shell', 'input', 'text', username],
            capture_output=True, timeout=10
        )

        target_lower = username.lower()

        # --- Inline-only approach (no Enter/submit) ---
        # Instagram shows results as you type - more human-like to click directly
        for attempt in range(3):
            time.sleep(1.5 if attempt == 0 else 1)  # Wait for results to populate
            
            inline_match = self._try_click_inline_result(target_lower)
            if inline_match:
                return True
            
            if attempt < 2:
                log.debug("[%s] Inline attempt %d failed for '%s', retrying...",
                         self.device_serial, attempt + 1, username)
                # Small scroll in case user is just off-screen in dropdown
                self.device.swipe(540, 600, 540, 400, duration=0.1)
                time.sleep(0.5)

        log.warning("[%s] User '%s' not found in inline search results",
                   self.device_serial, username)
        self.screenshot("search_user_not_found")
        return False

    def _try_click_inline_result(self, target_lower: str) -> bool:
        """
        Click inline search suggestion matching username.
        This is the primary search method (no Enter/submit fallback).
        """
        # Check if any inline results appeared
        user_rows = self.device(resourceIdMatches=self._rid_match('row_search_user_username'))
        if user_rows.exists(timeout=2):
            count = min(user_rows.count, 10)
            for i in range(count):
                try:
                    row_text = (user_rows[i].get_text() or "").strip()
                    if row_text.lower() == target_lower:
                        log.info("[%s] Inline match: '%s' (row %d), clicking",
                                self.device_serial, row_text, i)
                        # Re-fetch to ensure element is still there and click it
                        fresh = self.device(resourceIdMatches=self._rid_match('row_search_user_username'), text=row_text)
                        if fresh.exists(timeout=1):
                            fresh.click()
                        else:
                            # Element moved - try clicking parent container at same row
                            try:
                                info = user_rows[i].info
                                bounds = info.get('bounds', {})
                                cy = (bounds.get('top', 0) + bounds.get('bottom', 0)) // 2
                                if cy > 0:
                                    self.device.click(540, cy)  # Center of screen at row y
                                else:
                                    user_rows[i].click()
                            except:
                                user_rows[i].click()
                        time.sleep(2.5)
                        if self._verify_on_profile(target_lower):
                            return True
                        log.debug("[%s] Inline click didn't land on profile, will retry",
                                 self.device_serial)
                        self.device.press('back')
                        time.sleep(1)
                        return False  # Return to retry loop
                except Exception:
                    continue

        # Quick TextView scan for inline suggestions (different resource IDs)
        all_tvs = self.device(className='android.widget.TextView')
        if all_tvs.exists(timeout=1):
            for i in range(min(all_tvs.count, 20)):
                try:
                    text = (all_tvs[i].get_text() or "").strip()
                    if text.lower() == target_lower:
                        info = all_tvs[i].info
                        rid = info.get('resourceName', '') or ''
                        if any(skip in rid.lower() for skip in
                               ['edit_text', 'search_bar', 'keyword']):
                            continue
                        bounds = info.get('bounds', {})
                        cy = (bounds.get('top', 0) + bounds.get('bottom', 0)) // 2
                        log.info("[%s] Inline match via TextView: '%s' at y=%d",
                                self.device_serial, text, cy)
                        # Click the element directly (more reliable than coordinates)
                        # Re-fetch element to ensure it's still there
                        fresh_el = self.device(className='android.widget.TextView', text=text)
                        if fresh_el.exists(timeout=1):
                            fresh_el.click()
                            log.debug("[%s] Clicked inline result directly", self.device_serial)
                        elif cy > 0:
                            self.device.click(200, cy)
                            log.debug("[%s] Clicked inline result by coord (200,%d)", self.device_serial, cy)
                        else:
                            all_tvs[i].click()
                        time.sleep(2.5)
                        if self._verify_on_profile(target_lower):
                            return True
                        log.debug("[%s] Inline TextView click didn't navigate, will retry",
                                 self.device_serial)
                        self.device.press('back')
                        time.sleep(1)
                        return False  # Return to retry loop
                except Exception:
                    continue

        log.debug("[%s] No inline match for '%s'", self.device_serial, target_lower)
        return False

    def _find_and_click_user_in_results(self, target_lower: str) -> bool:
        """
        Thorough search through submitted search results for a username match.
        Tries resource ID match first, then TextView scan with multiple click strategies.
        Returns True if profile opened successfully.
        """
        # Strategy 1: Match by row_search_user_username resource ID (most reliable)
        user_rows = self.device(resourceIdMatches=self._rid_match('row_search_user_username'))
        if user_rows.exists(timeout=2):
            count = min(user_rows.count, 15)
            for i in range(count):
                try:
                    row_text = (user_rows[i].get_text() or "").strip()
                    if row_text.lower() == target_lower:
                        log.info("[%s] Found '%s' in search results (row %d)",
                                self.device_serial, row_text, i)
                        user_rows[i].click()
                        time.sleep(4)
                        if self._verify_on_profile(target_lower):
                            return True
                        # Try coordinate click on same row
                        log.debug("[%s] Direct click on row didn't navigate, trying coords",
                                 self.device_serial)
                        self.device.press('back')
                        time.sleep(2)
                        # Re-find and click via coordinates
                        user_rows2 = self.device(resourceIdMatches=self._rid_match('row_search_user_username'))
                        if user_rows2.exists(timeout=2):
                            for j in range(min(user_rows2.count, 15)):
                                rt = (user_rows2[j].get_text() or "").strip()
                                if rt.lower() == target_lower:
                                    b = user_rows2[j].info.get('bounds', {})
                                    cy = (b.get('top', 0) + b.get('bottom', 0)) // 2
                                    if cy > 0:
                                        self.device.click(200, cy)
                                        time.sleep(4)
                                        if self._verify_on_profile(target_lower):
                                            return True
                                    break
                        self.device.press('back')
                        time.sleep(2)
                except Exception as e:
                    log.debug("[%s] Error checking search result %d: %s",
                             self.device_serial, i, e)
                    continue

        # Strategy 2: Match username in any visible TextView
        all_tvs = self.device(className='android.widget.TextView')
        if all_tvs.exists(timeout=1):
            tv_count = min(all_tvs.count, 25)
            for i in range(tv_count):
                try:
                    text = (all_tvs[i].get_text() or "").strip()
                    if text.lower() == target_lower:
                        info = all_tvs[i].info
                        rid = info.get('resourceName', '') or ''
                        if any(skip in rid.lower() for skip in
                               ['edit_text', 'search_bar', 'keyword']):
                            continue
                        bounds = info.get('bounds', {})
                        cy = (bounds.get('top', 0) + bounds.get('bottom', 0)) // 2
                        log.info("[%s] Found '%s' via TextView (rid=%s, y=%d)",
                                self.device_serial, text, rid, cy)

                        # Try coordinate-based row click first (more reliable)
                        if cy > 0:
                            self.device.click(200, cy)
                            time.sleep(4)
                            if self._verify_on_profile(target_lower):
                                return True
                            self.device.press('back')
                            time.sleep(2)

                        # Try direct element click as fallback
                        fresh = self.device(className='android.widget.TextView', text=text)
                        if fresh.exists(timeout=2):
                            fresh.click()
                            time.sleep(4)
                            if self._verify_on_profile(target_lower):
                                return True
                            self.device.press('back')
                            time.sleep(2)

                        return False  # Found the right text but couldn't navigate
                except Exception:
                    continue

        return False

    def _verify_on_profile(self, expected_username: str = None) -> bool:
        """
        Verify we actually landed on a user profile page.
        Checks for profile-specific elements (not just tab state).
        """
        xml = self.dump_xml("verify_profile")
        if not xml:
            return False
        xml_lower = xml.lower()

        # Profile indicators: resource IDs found on profile pages
        profile_indicators = [
            'profile_header_follow_button',
            'profile_header_followers_stacked_familiar',
            'profile_header_following_stacked_familiar',
            'row_profile_header',
            'profile_header_container',
            'profile_tab_layout',
            'profile_tab_icon_view',
            'action_bar_title',
            'profile_header_bio_text',
            'profile_header_full_name',
            'profile_header_website',
            'coordinator_root_layout',
        ]
        found = sum(1 for ind in profile_indicators if ind in xml)
        if found >= 1:
            log.debug("[%s] Verified on profile page (%d resource indicators)",
                     self.device_serial, found)
            return True

        # Text-based indicators (case-insensitive)
        text_indicators = ['followers', 'following', 'posts']
        text_found = sum(1 for t in text_indicators if t in xml_lower)
        if text_found >= 2:
            log.debug("[%s] Verified on profile page (%d text indicators: followers/following/posts)",
                     self.device_serial, text_found)
            return True

        # Check for expected username on the page (outside search context)
        if expected_username:
            # If we see the username AND "Follow"/"Following"/"Message" button, it's a profile
            has_username = expected_username in xml_lower
            has_action = any(btn in xml for btn in ['Follow', 'Following', 'Message', 'Requested'])
            if has_username and has_action:
                log.debug("[%s] Verified on profile via username + action button",
                         self.device_serial)
                return True

        # Check if we're on our own profile (Edit profile button)
        if 'Edit profile' in xml or 'edit_profile' in xml_lower:
            return True

        # Use screen detection as final fallback
        screen = self.detect_screen()
        if screen == Screen.PROFILE:
            log.debug("[%s] Verified on profile via screen detection", self.device_serial)
            return True

        log.debug("[%s] Profile verification FAILED — not on profile page",
                 self.device_serial)
        return False

    # -----------------------------------------------------------------------
    # Utility
    # -----------------------------------------------------------------------
    def press_back(self) -> bool:
        """Press back button."""
        try:
            self.device.press('back')
            time.sleep(1)
            return True
        except Exception:
            return False

    def type_text(self, text: str) -> bool:
        """Type text via ADB shell (more reliable than u2)."""
        try:
            subprocess.run(
                ['adb', '-s', self.adb_serial, 'shell', 'input', 'text',
                 text.replace(' ', '%s')],
                capture_output=True, timeout=10
            )
            return True
        except Exception as e:
            log.error("[%s] Type text failed: %s", self.device_serial, e)
            return False

    def get_screen_summary(self) -> str:
        """Get a human-readable summary of current screen state."""
        xml = self.dump_xml("summary")
        screen = self.detect_screen(xml)

        summary = f"Screen: {screen.value}"
        if screen == Screen.HOME_FEED:
            stories = self.get_story_items(xml)
            unseen = sum(1 for s in stories if not s['seen'])
            posts = self.get_visible_posts(xml)
            summary += f" | Stories: {len(stories)} ({unseen} unseen) | Posts visible: {len(posts)}"
        elif screen == Screen.STORY_VIEW:
            summary += " | In story viewer"

        return summary

    # -----------------------------------------------------------------------
    # Like Operations
    # -----------------------------------------------------------------------
    def like_post(self) -> bool:
        """
        Find and click the like button on the currently visible post.
        Verifies the liked state changed.
        Returns True if successfully liked, False if already liked or not found.
        """
        xml = self.dump_xml("like_post")

        # Find like button by resource ID
        like_btns = self._find_all_in_xml(xml, resource_id='row_feed_button_like')
        for btn in like_btns:
            desc = btn.get('content_desc', '').lower()
            bounds = btn.get('bounds', '')

            # Skip if already liked
            if desc == 'liked' or 'unlike' in desc:
                log.debug("[%s] Post already liked", self.device_serial)
                return False

            if desc == 'like' and bounds:
                cx, cy = self._bounds_center(bounds)
                if cx > 0 and cy > 0:
                    self.device.click(cx, cy)
                    time.sleep(1.5)

                    # Verify liked state
                    xml2 = self.dump_xml("like_verify")
                    btns2 = self._find_all_in_xml(xml2, resource_id='row_feed_button_like')
                    for b2 in btns2:
                        if b2.get('content_desc', '').lower() == 'liked':
                            log.info("[%s] Successfully liked post", self.device_serial)
                            return True

                    log.warning("[%s] Like click didn't change state", self.device_serial)
                    return False

        # Fallback: double-tap on the media
        for rid in ['media_group', 'row_feed_photo_imageview']:
            media = self._find_in_xml(xml, resource_id=rid)
            if media and media.get('bounds'):
                cx, cy = self._bounds_center(media['bounds'])
                if cx > 0 and cy > 0:
                    self.device.double_click(cx, cy, 0.15)
                    time.sleep(1.5)
                    log.info("[%s] Double-tapped to like post", self.device_serial)
                    return True

        log.debug("[%s] No likeable post visible", self.device_serial)
        return False

    def is_post_liked(self) -> Optional[bool]:
        """Check if the currently visible post is liked. Returns True/False/None."""
        xml = self.dump_xml("check_liked")
        btns = self._find_all_in_xml(xml, resource_id='row_feed_button_like')
        for btn in btns:
            desc = btn.get('content_desc', '').lower()
            if desc == 'liked':
                return True
            if desc == 'like':
                return False
        return None

    def like_story(self) -> bool:
        """Like the current story being viewed."""
        try:
            like_btn = self.device(resourceIdMatches=self._rid_match('toolbar_like_button'))
            if like_btn.exists(timeout=2):
                info = like_btn.info
                if not info.get('selected', False):
                    like_btn.click()
                    time.sleep(1)
                    log.info("[%s] Liked a story", self.device_serial)
                    return True
                log.debug("[%s] Story already liked", self.device_serial)
                return False

            # Fallback: double-tap center of screen
            w, h = self.window_size
            self.device.double_click(w // 2, h // 2, 0.15)
            time.sleep(1)
            log.info("[%s] Double-tapped to like story", self.device_serial)
            return True
        except Exception as e:
            log.error("[%s] Like story failed: %s", self.device_serial, e)
            return False

    # -----------------------------------------------------------------------
    # Reels Operations
    # -----------------------------------------------------------------------
    def like_reel(self) -> bool:
        """
        Like the currently playing reel.
        Tries dedicated like button first, falls back to double-tap center.
        Returns True if like action was performed.
        """
        try:
            xml = self.dump_xml("like_reel")

            # Method 1: Reel-specific like button (clips_like_button)
            for rid in ['clips_like_button', 'like_button']:
                btn = self._find_in_xml(xml, resource_id=rid)
                if btn and btn.get('bounds'):
                    desc = (btn.get('content_desc', '') or '').lower()
                    selected = btn.get('selected', 'false') == 'true'

                    # Already liked?
                    if 'unlike' in desc or 'liked' in desc or selected:
                        log.debug("[%s] Reel already liked", self.device_serial)
                        return False

                    cx, cy = self._bounds_center(btn['bounds'])
                    if cx > 0 and cy > 0:
                        self.device.click(cx, cy)
                        time.sleep(1)
                        log.info("[%s] Liked reel via button", self.device_serial)
                        return True

            # Method 2: Find like button via row_feed_button_like (some reel UIs)
            like_btns = self._find_all_in_xml(xml, resource_id='row_feed_button_like')
            for btn in like_btns:
                desc = (btn.get('content_desc', '') or '').lower()
                bounds = btn.get('bounds', '')
                if desc == 'like' and bounds:
                    cx, cy = self._bounds_center(bounds)
                    if cx > 0 and cy > 0:
                        self.device.click(cx, cy)
                        time.sleep(1)
                        log.info("[%s] Liked reel via feed like button", self.device_serial)
                        return True

            # Method 3: Double-tap center of screen
            w, h = self.window_size
            self.device.double_click(w // 2, h // 2, 0.15)
            time.sleep(1)
            log.info("[%s] Double-tapped to like reel", self.device_serial)
            return True

        except Exception as e:
            log.error("[%s] Like reel failed: %s", self.device_serial, e)
            return False

    def swipe_to_next_reel(self, is_ad: bool = False) -> bool:
        """
        Swipe up to advance to the next reel.
        If is_ad=True, uses a more aggressive swipe in a guaranteed-safe zone.
        Returns True if swipe succeeded and we're still in reels.
        """
        try:
            w, h = self.window_size
            import random as _rand

            if is_ad:
                # AD REEL: use ADB shell input swipe for reliable gesture
                # that can't be intercepted by overlay buttons.
                # Swipe in the far-left edge (x=5-10% width) from 40% to 10% height
                # This area has NO clickable ad elements — just the video.
                sx = int(w * 0.08)
                sy = int(h * 0.40)
                ey = int(h * 0.08)
                dur_ms = _rand.randint(150, 250)
                log.debug("[%s] Ad-safe ADB swipe: (%d,%d)->(%d,%d) %dms",
                          self.device_serial, sx, sy, sx, ey, dur_ms)
                try:
                    adb_serial = self.device_serial.replace('_', ':')
                    subprocess.run(
                        ['adb', '-s', adb_serial, 'shell', 'input', 'swipe',
                         str(sx), str(sy), str(sx), str(ey), str(dur_ms)],
                        timeout=10, capture_output=True
                    )
                except Exception as e:
                    log.warning("[%s] ADB swipe failed, falling back to u2: %s",
                                self.device_serial, e)
                    self.device.swipe(sx, sy, sx, ey, duration=dur_ms / 1000.0)
            else:
                # Normal reel: swipe in the upper-center area
                # Start at 45% height, end at 15% — well above ad CTA zone
                start_x = int(w * 0.35) + _rand.randint(-15, 15)
                start_y = int(h * 0.45) + _rand.randint(-10, 10)
                end_y = int(h * 0.15) + _rand.randint(-10, 10)
                duration = _rand.uniform(0.20, 0.35)
                self.device.swipe(start_x, start_y, start_x, end_y, duration=duration)

            time.sleep(1.5)

            # Verify we didn't accidentally tap into an ad profile/webview
            if not self._recover_from_ad_tap():
                return False
            return True
        except Exception as e:
            log.error("[%s] Swipe to next reel failed: %s", self.device_serial, e)
            return False

    def is_reel_ad(self, xml: str = None) -> bool:
        """
        Detect if the current reel is a sponsored/ad reel.
        Checks for 'Sponsored' label and ad-specific UI elements.
        """
        if xml is None:
            xml = self.dump_xml("reel_ad_check")
        if not xml:
            return False
        # Instagram shows "Sponsored" text on ad reels + CTA buttons
        ad_indicators = [
            'text="Sponsored"',
            'content-desc="Sponsored"',
            'text="Visit Instagram profile"',
            'text="Shop Now"',
            'text="Shop now"',
            'text="Learn More"',
            'text="Learn more"',
            'text="Install Now"',
            'text="Install now"',
            'text="Sign Up"',
            'text="Download"',
            'text="Book Now"',
            'text="Book now"',
            'text="Get Offer"',
            'text="Apply Now"',
            'text="Apply now"',
            'text="Contact Us"',
            'text="Watch More"',
            'text="Subscribe"',
            'text="Send Message"',
        ]
        return any(ind in xml for ind in ad_indicators)

    def _recover_from_ad_tap(self, max_back=3) -> bool:
        """
        Check if we accidentally left reels (e.g. tapped an ad).
        If so, press back repeatedly until we're back in reels.
        Returns True if we recovered (or never left), False if stuck.
        """
        for attempt in range(max_back):
            try:
                screen = self.detect_screen()
                if screen == Screen.REELS:
                    return True
                if screen == Screen.POPUP:
                    self.dismiss_popups()
                    time.sleep(0.5)
                    continue
                # We're on a profile, webview, or unknown — press back
                log.warning("[%s] Reel ad recovery: landed on %s, pressing back (attempt %d/%d)",
                            self.device_serial, screen.value, attempt + 1, max_back)
                self.press_back()
                time.sleep(1.5)
            except Exception as e:
                log.error("[%s] Ad recovery error: %s", self.device_serial, e)
                self.press_back()
                time.sleep(1)
        # Final check
        screen = self.detect_screen()
        if screen == Screen.REELS:
            return True
        log.error("[%s] Could not recover to reels after ad tap (screen=%s)",
                  self.device_serial, screen.value)
        return False

    # -----------------------------------------------------------------------
    # Follow/Unfollow Operations
    # -----------------------------------------------------------------------
    def follow_user_from_list(self, target_username: str) -> Optional[bool]:
        """
        Follow a user visible in a followers/following list.
        Finds the Follow button in the same row via vertical proximity.

        Returns:
            True = followed successfully
            False = skipped (already following)
            None = error (element not found)
        """
        try:
            user_el = self.device(text=target_username)
            if not user_el.exists(timeout=2):
                user_el = self.device(textContains=target_username)
            if not user_el.exists(timeout=2):
                return None

            user_bounds = user_el.info.get('bounds', {})
            user_cy = (user_bounds.get('top', 0) + user_bounds.get('bottom', 0)) // 2

            # Find Follow buttons by resource ID
            follow_btns = self.device(resourceIdMatches=self._rid_match(
                'follow_list_row_large_follow_button'))
            if not follow_btns.exists(timeout=2):
                follow_btns = self.device(textMatches="^Follow$")

            if follow_btns.exists(timeout=2):
                best_btn = None
                best_dist = 999999
                for i in range(min(follow_btns.count, 20)):
                    try:
                        btn = follow_btns[i]
                        bb = btn.info.get('bounds', {})
                        btn_cy = (bb.get('top', 0) + bb.get('bottom', 0)) // 2
                        dist = abs(btn_cy - user_cy)
                        if dist < best_dist:
                            best_dist = dist
                            best_btn = btn
                    except Exception:
                        continue

                if best_btn and best_dist < 100:
                    btn_text = (best_btn.get_text() or "").strip()
                    if btn_text in ("Follow", "Follow Back", ""):
                        best_btn.click()
                        time.sleep(2)
                        # Verify
                        try:
                            new_text = (best_btn.get_text() or "").strip()
                            if new_text in ("Following", "Requested", "Message"):
                                log.info("[%s] Followed @%s from list",
                                        self.device_serial, target_username)
                                return True
                        except Exception:
                            pass
                        return True  # Assume success if click worked
                    elif btn_text in ("Following", "Requested", "Message"):
                        log.debug("[%s] Already following @%s", self.device_serial, target_username)
                        return False

            return None

        except Exception as e:
            log.error("[%s] follow_user_from_list error for @%s: %s",
                     self.device_serial, target_username, e)
            return None

    def follow_user_from_profile(self) -> Optional[bool]:
        """
        Click the Follow button on a profile page.

        Returns:
            True = followed
            False = already following
            None = button not found
        """
        try:
            # Try the profile header follow button
            btn = self.device(resourceIdMatches=self._rid_match('profile_header_follow_button'))
            if not btn.exists(timeout=3):
                btn = self.device(text="Follow", className="android.widget.Button")
            if not btn.exists(timeout=3):
                btn = self.device(textMatches="^Follow$", clickable=True)

            if btn.exists(timeout=2):
                text = (btn.get_text() or "").strip()
                if text in ("Follow", "Follow Back"):
                    btn.click()
                    time.sleep(2)
                    # Verify
                    verify_btn = self.device(resourceIdMatches=self._rid_match(
                        'profile_header_follow_button'))
                    if verify_btn.exists(timeout=2):
                        new_text = (verify_btn.get_text() or "").strip()
                        if new_text in ("Following", "Requested"):
                            log.info("[%s] Followed user from profile", self.device_serial)
                            return True
                    return True
                elif text in ("Following", "Requested"):
                    log.debug("[%s] Already following this user", self.device_serial)
                    return False
                elif text == "Edit profile":
                    log.debug("[%s] This is our own profile", self.device_serial)
                    return False

            return None

        except Exception as e:
            log.error("[%s] follow_user_from_profile error: %s", self.device_serial, e)
            return None

    def unfollow_user(self) -> bool:
        """
        Unfollow a user from their profile page.
        Clicks Following button -> confirms Unfollow in dialog.
        Must be on a user's profile page first.

        Returns True if unfollowed.
        """
        try:
            # Find the Following button on profile
            btn = self.device(resourceIdMatches=self._rid_match('profile_header_follow_button'))
            if not btn.exists(timeout=3):
                btn = self.device(text="Following", className="android.widget.Button")

            if btn.exists(timeout=3):
                text = (btn.get_text() or "").strip()
                if text != "Following":
                    log.debug("[%s] Button text is '%s', not Following", self.device_serial, text)
                    return False

                btn.click()
                time.sleep(2)

                # Look for Unfollow confirmation in the bottom sheet
                for confirm_text in ["Unfollow", "Remove"]:
                    confirm = self.device(text=confirm_text)
                    if confirm.exists(timeout=3):
                        confirm.click()
                        time.sleep(2)
                        log.info("[%s] Unfollowed user", self.device_serial)
                        return True

                # Dialog didn't appear, press back
                self.device.press('back')
                time.sleep(1)

            return False

        except Exception as e:
            log.error("[%s] unfollow_user error: %s", self.device_serial, e)
            return False

    # -----------------------------------------------------------------------
    # Profile Operations (open followers, following)
    # -----------------------------------------------------------------------
    def _ensure_profile_header_visible(self):
        """Scroll up on profile page to ensure header (followers/following counts) is visible."""
        w, h = self.window_size
        for _ in range(3):
            self.device.swipe(w // 2, int(h * 0.3), w // 2, int(h * 0.8), duration=0.3)
            time.sleep(0.3)
        time.sleep(0.5)

    def open_followers(self) -> bool:
        """
        From a profile page, click on the followers count to open followers list.
        Returns True if followers list opened.
        """
        # Ensure profile header is visible (may be scrolled off)
        self._ensure_profile_header_visible()

        selectors = [
            ('resource_id', 'profile_header_followers_stacked_familiar'),
            ('resource_id', 'profile_header_familiar_followers_value'),
            ('desc_pattern', r'.*\d+.*follower.*'),
        ]
        for sel_type, sel_val in selectors:
            if sel_type == 'resource_id':
                el = self.device(resourceIdMatches=self._rid_match(sel_val))
            elif sel_type == 'desc_pattern':
                el = self.device(descriptionMatches=sel_val)
            else:
                continue

            if el.exists(timeout=3):
                el.click()
                time.sleep(3)

                # Verify we're in followers list
                xml = self.dump_xml("verify_followers")
                if ('unified_follow_list_tab_layout' in xml or
                    'follow_list_username' in xml):
                    log.info("[%s] Opened followers list", self.device_serial)
                    return True

        log.warning("[%s] Could not open followers list", self.device_serial)
        return False

    def open_following(self) -> bool:
        """
        From a profile page, click on the following count to open following list.
        Ensures "following" tab is selected in the unified tab.
        Returns True if following list opened.
        """
        # Ensure profile header is visible (may be scrolled off)
        self._ensure_profile_header_visible()

        selectors = [
            ('resource_id', 'profile_header_following_stacked_familiar'),
            ('resource_id', 'profile_header_familiar_following_value'),
            ('desc_pattern', r'.*\d+.*following.*'),
        ]
        for sel_type, sel_val in selectors:
            if sel_type == 'resource_id':
                el = self.device(resourceIdMatches=self._rid_match(sel_val))
            elif sel_type == 'desc_pattern':
                el = self.device(descriptionMatches=sel_val)
            else:
                continue

            if el.exists(timeout=3):
                el.click()
                time.sleep(3)

                # Click the "following" tab in the unified tab layout
                title_btns = self.device(resourceIdMatches=self._rid_match('title'))
                if title_btns.exists(timeout=2):
                    for i in range(min(title_btns.count, 6)):
                        try:
                            text = title_btns[i].get_text() or ""
                            if "following" in text.lower():
                                title_btns[i].click()
                                time.sleep(2)
                                break
                        except Exception:
                            continue

                log.info("[%s] Opened following list", self.device_serial)
                return True

        log.warning("[%s] Could not open following list", self.device_serial)
        return False

    # -----------------------------------------------------------------------
    # User List Operations (for follow/unfollow lists)
    # -----------------------------------------------------------------------
    def get_visible_usernames_in_list(self) -> List[str]:
        """
        Extract usernames from a currently visible followers/following list.
        Returns list of username strings.
        """
        usernames = []
        try:
            # Primary: follow_list_username resource ID
            views = self.device(resourceIdMatches=self._rid_match('follow_list_username'))
            if views.exists(timeout=2):
                for i in range(min(views.count, 20)):
                    try:
                        text = views[i].get_text()
                        if text and text.strip():
                            usernames.append(text.strip())
                    except Exception:
                        continue
                if usernames:
                    return usernames

            # Fallback patterns
            for rid_suffix in ['row_user_primary_name', 'row_user_textview', 'username']:
                views = self.device(resourceIdMatches=f".*{rid_suffix}$")
                if views.exists(timeout=2):
                    for i in range(min(views.count, 20)):
                        try:
                            text = views[i].get_text()
                            if text and text.strip() and not text.startswith('#'):
                                usernames.append(text.strip())
                        except Exception:
                            continue
                    if usernames:
                        return usernames

        except Exception as e:
            log.debug("[%s] Error getting visible users: %s", self.device_serial, e)

        return usernames

    def scroll_list(self, direction: str = "down") -> bool:
        """Scroll the current list (followers/following/explore). Returns True on success."""
        try:
            w, h = self.window_size
            cx = w // 2
            if direction == "down":
                sy = int(h * 0.7)
                ey = int(h * 0.3)
            else:
                sy = int(h * 0.3)
                ey = int(h * 0.7)
            self.device.swipe(cx, sy, cx, ey, duration=0.5)
            time.sleep(1)
            return True
        except Exception as e:
            log.error("[%s] scroll_list failed: %s", self.device_serial, e)
            return False

    # -----------------------------------------------------------------------
    # Profile Info
    # -----------------------------------------------------------------------
    def get_profile_info(self) -> Dict:
        """
        Extract profile info from current profile screen using XML.
        Returns dict with: followers, following, posts, is_private, username
        """
        info = {
            'posts': 0, 'followers': 0, 'following': 0,
            'is_private': False, 'username': '', 'has_story': False,
        }

        # Ensure profile header is visible (may be scrolled off after prior actions)
        self._ensure_profile_header_visible()

        xml = self.dump_xml("profile_info")
        if not xml:
            return info

        # Detect private account
        xml_lower = xml.lower()
        info['is_private'] = ('this account is private' in xml_lower or
                              'private account' in xml_lower)

        # Story ring
        info['has_story'] = 'story_ring' in xml_lower or 'reel_ring' in xml_lower

        # Username from action bar title or title_chevron area
        title = self._find_in_xml(xml, resource_id='action_bar_title')
        if title and title.get('text'):
            info['username'] = title['text']
        else:
            # Fallback: look for action_bar_textview_title or large_title
            for rid in ['action_bar_textview_title', 'action_bar_large_title',
                        'action_bar_title_chevron']:
                el = self._find_in_xml(xml, resource_id=rid)
                if el:
                    # chevron is an ImageView — check content_desc for username
                    username = el.get('text') or el.get('content_desc', '')
                    if username and username not in ('', 'Discover people'):
                        info['username'] = username
                        break

        # Followers count from content-desc
        followers_el = self._find_in_xml(xml, resource_id='profile_header_followers_stacked_familiar')
        if followers_el:
            desc = followers_el.get('content_desc', '')
            # Pattern: "698Mfollowers" or "1,234followers"
            m = re.match(r'([\d,.]+[KMBkmb]?)\s*followers?', desc)
            if m:
                info['followers'] = self._parse_number(m.group(1))

        # Following count
        following_el = self._find_in_xml(xml, resource_id='profile_header_following_stacked_familiar')
        if following_el:
            desc = following_el.get('content_desc', '')
            m = re.match(r'([\d,.]+[KMBkmb]?)\s*following', desc)
            if m:
                info['following'] = self._parse_number(m.group(1))

        return info

    @staticmethod
    def _parse_number(text: str) -> int:
        """Parse Instagram-style numbers like '1.2K', '3.4M', '500'."""
        if not text:
            return 0
        text = text.strip().replace(',', '').replace(' ', '')
        try:
            upper = text.upper()
            if upper.endswith('K'):
                return int(float(text[:-1]) * 1000)
            elif upper.endswith('M'):
                return int(float(text[:-1]) * 1000000)
            elif upper.endswith('B'):
                return int(float(text[:-1]) * 1000000000)
            return int(text)
        except (ValueError, TypeError):
            return 0

    # -----------------------------------------------------------------------
    # Explore Page Operations
    # -----------------------------------------------------------------------
    def open_explore_post(self) -> bool:
        """
        On the explore/search page, click a random post thumbnail.
        Returns True if a post was opened.
        """
        try:
            images = self.device(resourceIdMatches=self._rid_match('image_button'))
            if not images.exists(timeout=2):
                images = self.device(className="android.widget.ImageView", clickable=True)
            if images.exists(timeout=2) and images.count > 0:
                import random
                idx = random.randint(0, min(images.count - 1, 5))
                images[idx].click()
                time.sleep(3)
                return True
        except Exception as e:
            log.debug("[%s] open_explore_post error: %s", self.device_serial, e)
        return False

    # -----------------------------------------------------------------------
    # Recovery
    # -----------------------------------------------------------------------
    def recover_to_home(self, max_backs: int = 5) -> bool:
        """
        Try to recover from any state back to home feed.
        Presses back repeatedly and dismisses popups.
        """
        for _ in range(max_backs):
            screen = self.detect_screen()
            if screen == Screen.HOME_FEED:
                return True
            if screen == Screen.POPUP:
                self.dismiss_popups()
                time.sleep(1)
            else:
                self.device.press('back')
                time.sleep(1.5)

        # Last resort: try tab click
        return self.navigate_to(Screen.HOME_FEED)
