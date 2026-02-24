"""
Share to Story Action Module
==============================
Share source accounts' posts/reels to our Instagram story.

Flow:
1. Get source accounts from account_sources
2. Visit each source's profile
3. Open their latest post/reel from profile grid
4. Tap share button → select "Add to your story"
5. In story editor, tap Share/publish
6. Log action, respect daily limits
"""

import logging
import random
import re
import time

from automation.actions.helpers import (
    action_delay, random_sleep, log_action, get_db,
    get_account_settings, get_account_sources,
    get_today_action_count
)
from automation.ig_controller import IGController, Screen
from automation.source_manager import get_sources

log = logging.getLogger(__name__)


def _to_bool(val):
    """Convert various truthy values to bool (settings may be str/int/bool)."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ('true', '1', 'on', 'yes')
    return bool(val)


class ShareToStoryAction:
    """Share source users' content to our story."""

    def __init__(self, device, device_serial, account_info, session_id,
                 package='com.instagram.androie'):
        self.device = device
        self.device_serial = device_serial
        self.account = account_info
        self.session_id = session_id
        self.username = account_info['username']
        self.account_id = account_info['id']

        pkg = account_info.get('package', package)
        self.ctrl = IGController(device, device_serial, pkg)

        self.settings = get_account_settings(self.account_id)

        # Limits from settings
        self.daily_limit = int(self.settings.get('shared_post_limit_perday', 1))
        self.per_source_limit = int(self.settings.get('shared_post_limit_persource_perday', 2))
        self.mention = self.settings.get('sharepost_mention', '').strip()
        self.post_type = self.settings.get('post_type_to_share', 'post_reels')
        self.min_watch = int(self.settings.get('min_sec_share_reel_watch', 5))
        self.max_watch = int(self.settings.get('max_sec_share_reel_watch', 10))

        # Story editor features
        self.enable_mention = _to_bool(self.settings.get('enable_mention_to_story', False))
        self.mention_target = self.settings.get('sharepost_mention', '').strip()
        self.enable_link_sticker = _to_bool(self.settings.get('enable_add_link_to_story', False))
        self.link_sticker_url = self.settings.get('custom_link_text', '')
        self.enable_text_overlay = _to_bool(self.settings.get('story_text_overlay_enabled', False))
        self.text_overlay = self.settings.get('story_text_overlay', '')

    def _handle_permission_dialogs(self):
        """Handle Android permission dialogs that block the story editor.

        Common dialogs when entering story editor (from com.google.android.permissioncontroller):
        - "Allow X to take pictures and record video?" → click "While using the app"
        - "Allow X to access photos and videos?" → click "While using the app" or "Allow"
        - "Allow X to record audio?" → click "While using the app"

        Returns number of permission dialogs handled.
        """
        permission_grant_buttons = [
            "While using the app",
            "WHILE USING THE APP",
            "Only this time",
            "ONLY THIS TIME",
            "Allow",
            "ALLOW",
        ]

        max_dialogs = 3  # Handle up to 3 sequential permission dialogs
        handled = 0

        for _ in range(max_dialogs):
            found = False
            for btn_text in permission_grant_buttons:
                el = self.device(text=btn_text)
                if el.exists(timeout=2):
                    el.click()
                    time.sleep(1.5)
                    log.info("[%s] Granted permission via '%s'",
                             self.device_serial, btn_text)
                    handled += 1
                    found = True
                    break
            if not found:
                break

        if handled:
            log.info("[%s] Handled %d permission dialog(s)", self.device_serial, handled)
        return handled

    def execute(self):
        """
        Execute share-to-story action.
        Returns dict: {success, shares_done, errors, sources_used}
        """
        result = {
            'success': False,
            'shares_done': 0,
            'errors': 0,
            'sources_used': [],
        }

        self.ctrl.ensure_app()
        self.ctrl.dismiss_popups()

        done_today = get_today_action_count(
            self.device_serial, self.username, 'share_to_story')
        remaining = self.daily_limit - done_today
        if remaining <= 0:
            log.info("[%s] %s: Daily share limit reached (%d/%d)",
                     self.device_serial, self.username, done_today, self.daily_limit)
            result['success'] = True
            return result

        log.info("[%s] %s: Will share up to %d posts (done today: %d)",
                 self.device_serial, self.username, remaining, done_today)

        # Get sources: .txt file → DB fallback (Task 3)
        sources = get_sources(
            device_id=self.device_serial,
            account_name=self.username,
            action_type='share_to_story',
            account_id=self.account_id,
            db_source_type='share_sources'
        )
        if not sources:
            log.warning("[%s] %s: No source accounts configured for share_to_story",
                        self.device_serial, self.username)
            return result

        random.shuffle(sources)

        for source_username in sources:
            if result['shares_done'] >= remaining:
                break

            log.info("[%s] Sharing from source: @%s",
                     self.device_serial, source_username)
            result['sources_used'].append(source_username)

            try:
                self.ctrl.dismiss_popups()
                shared = self._share_from_source(source_username)
                if shared:
                    result['shares_done'] += 1
                    log_action(
                        self.session_id, self.device_serial, self.username,
                        'share_to_story', target_username=source_username,
                        success=True)
                    log.info("[%s] Shared from @%s (%d/%d)",
                             self.device_serial, source_username,
                             result['shares_done'], remaining)
                else:
                    result['errors'] += 1
            except Exception as e:
                log.error("[%s] Error sharing from @%s: %s",
                          self.device_serial, source_username, e)
                result['errors'] += 1
                self._recover()

            if result['shares_done'] < remaining:
                random_sleep(10, 25, label="between_shares")

        result['success'] = True
        log.info("[%s] %s: Share complete. Shared: %d, Errors: %d",
                 self.device_serial, self.username,
                 result['shares_done'], result['errors'])
        return result

    def _share_from_source(self, source_username):
        """
        Navigate to source profile, open latest post, share to story.
        Returns True if successfully shared.
        """
        # 1. Navigate to source profile
        if not self.ctrl.search_user(source_username):
            log.warning("[%s] Could not find @%s", self.device_serial, source_username)
            return False

        random_sleep(2, 4, label="on_profile")

        # 2. Open random grid item (post/reel based on post_type setting)
        if not self._open_random_grid_item():
            log.warning("[%s] Could not open grid item for @%s",
                        self.device_serial, source_username)
            self.ctrl.press_back()
            return False

        random_sleep(2, 3, label="post_loaded")

        # 3. Scroll down to reveal action buttons (ONLY for post detail view)
        # Reel full-screen view already shows share button on the right side —
        # swiping on reels scrolls to the next reel which breaks the flow.
        # Detect reel view vs post view by checking for reel-specific UI elements.
        is_reel_view = (
            self.device(description="Reels").exists(timeout=1) or
            self.device(textContains="Original audio").exists(timeout=0.5) or
            self.device(resourceIdMatches=".*reel.*player.*|.*clips_viewer.*").exists(timeout=0.5)
        )
        if is_reel_view:
            log.debug("[%s] Reel full-screen detected — skipping scroll (share button already visible)",
                      self.device_serial)
        else:
            w, h = self.device.window_size()
            self.device.swipe(w // 2, int(h * 0.65), w // 2, int(h * 0.35), duration=0.3)
            time.sleep(2)
            log.debug("[%s] Scrolled post view to reveal action buttons", self.device_serial)

        # 4. Click share button
        if not self._click_share_button():
            log.warning("[%s] Could not click share button", self.device_serial)
            self._go_back(3)
            return False

        random_sleep(1.5, 3, label="share_sheet_loading")

        # 5. Select "Add to story"
        if not self._select_add_to_story():
            log.warning("[%s] Could not find 'Add to story' option", self.device_serial)
            self._go_back(4)
            return False

        random_sleep(2, 4, label="story_editor_loading")

        # 5b. Handle any permission dialogs that may appear
        self._handle_permission_dialogs()

        # Wait a bit more for editor to load after dismissing permissions
        time.sleep(2)

        # 6. Apply story editor features (mention, link, text) and publish
        if not self._publish_story(source_username=source_username):
            log.warning("[%s] Could not publish story", self.device_serial)
            self._go_back(5)
            return False

        random_sleep(3, 5, label="story_publishing")

        # 7. Go back to clean state
        self._go_back(3)
        return True

    def _open_random_grid_item(self):
        """Open a random post/reel from the profile grid based on post_type setting.

        Checks self.post_type to decide which tab (Posts/Reels) to use,
        optionally scrolls the grid for variety, then picks a random item.
        Falls back to _open_first_grid_item_legacy() if no items found.
        """
        post_type = (self.post_type or 'posts').lower().strip()

        # Decide which tab: posts | reels | all
        if post_type == 'reels':
            self._switch_to_reels_tab()
        elif post_type == 'all':
            if random.random() < 0.5:
                log.info("[%s] post_type=all → randomly chose Reels tab",
                         self.device_serial)
                self._switch_to_reels_tab()
            else:
                log.info("[%s] post_type=all → randomly chose Posts tab",
                         self.device_serial)
        else:
            log.debug("[%s] post_type=%s → Posts tab",
                      self.device_serial, post_type)

        time.sleep(2)

        # Random scroll to get variety (0-2 scrolls)
        scroll_count = random.randint(0, 2)
        if scroll_count:
            log.debug("[%s] Scrolling grid %d time(s) for variety",
                      self.device_serial, scroll_count)
            for _ in range(scroll_count):
                self.ctrl.scroll_feed("down", amount=0.3)
                time.sleep(1.5)

        # Dump XML and find all grid items
        xml = self.ctrl.dump_xml("grid_items")
        grid_items = self._find_grid_items(xml)

        if not grid_items:
            log.warning("[%s] No grid items found via XML parsing, falling back to legacy",
                        self.device_serial)
            return self._open_first_grid_item_legacy()

        # Pick a random item
        item = random.choice(grid_items)
        desc_preview = (item.get('desc') or 'no-desc')[:60]
        log.info("[%s] Picked random grid item (%d available): %s",
                 self.device_serial, len(grid_items), desc_preview)

        # Click the item by bounds center
        x, y = item['cx'], item['cy']
        self.device.click(x, y)
        time.sleep(3)

        # Verify we opened something (not still on profile)
        screen = self.ctrl.detect_screen()
        if screen != Screen.PROFILE:
            return True

        # If still on profile, try clicking again with slight offset
        log.debug("[%s] Still on profile after click, retrying with offset", self.device_serial)
        self.device.click(x + 5, y + 5)
        time.sleep(3)
        screen = self.ctrl.detect_screen()
        if screen != Screen.PROFILE:
            return True

        log.warning("[%s] Could not open random grid item, falling back to legacy",
                    self.device_serial)
        return self._open_first_grid_item_legacy()

    def _find_grid_items(self, xml):
        """Parse XML to find all visible grid items (posts or reels).

        Returns list of dicts: [{'desc': str, 'cx': int, 'cy': int, 'bounds': str}, ...]
        """
        items = []

        # Pattern 1: content-desc with "Row X, Column Y" (standard IG grid items)
        # e.g. content-desc="Photo by cristiano. 2 days ago. Row 1, Column 1"
        row_col_pattern = re.compile(
            r'content-desc="([^"]*[Rr]ow\s+\d+[^"]*[Cc]olumn\s+\d+[^"]*)"'
            r'[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
        )
        for match in row_col_pattern.finditer(xml):
            desc = match.group(1)
            x1, y1, x2, y2 = int(match.group(2)), int(match.group(3)), int(match.group(4)), int(match.group(5))
            items.append({
                'desc': desc,
                'cx': (x1 + x2) // 2,
                'cy': (y1 + y2) // 2,
                'bounds': f'[{x1},{y1}][{x2},{y2}]',
            })

        if items:
            log.debug("[%s] Found %d grid items via Row/Column pattern",
                      self.device_serial, len(items))
            return items

        # Pattern 2: Also try bounds-first format (some XML dumps have different attr order)
        row_col_pattern2 = re.compile(
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
            r'[^>]*content-desc="([^"]*[Rr]ow\s+\d+[^"]*[Cc]olumn\s+\d+[^"]*)"'
        )
        for match in row_col_pattern2.finditer(xml):
            x1, y1, x2, y2 = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
            desc = match.group(5)
            items.append({
                'desc': desc,
                'cx': (x1 + x2) // 2,
                'cy': (y1 + y2) // 2,
                'bounds': f'[{x1},{y1}][{x2},{y2}]',
            })

        if items:
            log.debug("[%s] Found %d grid items via Row/Column pattern (alt order)",
                      self.device_serial, len(items))
            return items

        # Pattern 3: Clickable ImageViews in grid area (below ~40% of screen)
        # These are typically the grid thumbnails
        w, h = self.device.window_size()
        grid_top_threshold = int(h * 0.35)  # Grid typically starts below 35% of screen

        imageview_pattern = re.compile(
            r'<node[^>]*class="android\.widget\.ImageView"[^>]*'
            r'clickable="true"[^>]*'
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
        )
        for match in imageview_pattern.finditer(xml):
            x1, y1, x2, y2 = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
            # Filter: must be in grid area (below profile header) and reasonably sized
            item_w = x2 - x1
            item_h = y2 - y1
            if y1 >= grid_top_threshold and item_w > 50 and item_h > 50 and item_w < w * 0.5:
                items.append({
                    'desc': f'ImageView at [{x1},{y1}][{x2},{y2}]',
                    'cx': (x1 + x2) // 2,
                    'cy': (y1 + y2) // 2,
                    'bounds': f'[{x1},{y1}][{x2},{y2}]',
                })

        if items:
            log.debug("[%s] Found %d grid items via ImageView pattern",
                      self.device_serial, len(items))

        return items

    def _switch_to_reels_tab(self):
        """Switch to Reels tab on a user's profile.

        Profile tabs are typically: Posts | Reels | Tagged
        Returns True if successfully switched.
        """
        log.debug("[%s] Switching to Reels tab", self.device_serial)

        # Method 1: content-desc "Reels"
        reels_tab = self.device(description="Reels")
        if reels_tab.exists(timeout=3):
            reels_tab.click()
            time.sleep(2)
            log.debug("[%s] Clicked Reels tab via desc='Reels'", self.device_serial)
            return True

        # Method 2: text "Reels"
        reels_tab = self.device(text="Reels")
        if reels_tab.exists(timeout=2):
            reels_tab.click()
            time.sleep(2)
            log.debug("[%s] Clicked Reels tab via text='Reels'", self.device_serial)
            return True

        # Method 3: XML search for Reels tab in the tab row
        xml = self.ctrl.dump_xml("reels_tab_search")
        reels_match = re.search(
            r'(?:content-desc="Reels"|text="Reels")[^>]*'
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            xml)
        if not reels_match:
            # Try reversed attr order
            reels_match = re.search(
                r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*'
                r'(?:content-desc="Reels"|text="Reels")',
                xml)
        if reels_match:
            x = (int(reels_match.group(1)) + int(reels_match.group(3))) // 2
            y = (int(reels_match.group(2)) + int(reels_match.group(4))) // 2
            self.device.click(x, y)
            time.sleep(2)
            log.debug("[%s] Clicked Reels tab via XML bounds (%d, %d)",
                      self.device_serial, x, y)
            return True

        # Method 4: Try tapping the second tab icon in the tab bar area
        # Profile tabs are typically between y=45%-55% of screen
        w, h = self.device.window_size()
        # Second tab is roughly at x=50% (center), y near the tab row
        self.device.click(int(w * 0.5), int(h * 0.48))
        time.sleep(2)
        log.debug("[%s] Clicked estimated Reels tab position", self.device_serial)
        return True

    def _open_first_grid_item_legacy(self):
        """Legacy fallback: open the first post/reel in the profile grid."""
        xml = self.ctrl.dump_xml()

        # Method 1: Content-desc pattern for grid items
        pattern = r'content-desc="([^"]*[Rr]ow 1[^"]*[Cc]olumn 1[^"]*)"'
        match = re.search(pattern, xml)
        if match:
            desc = match.group(1)
            el = self.device(description=desc)
            if el.exists(timeout=3):
                el.click()
                time.sleep(3)
                log.debug("[%s] Opened grid item via desc: %s",
                          self.device_serial, desc[:60])
                return True

        # Method 2: Look for profile grid RecyclerView and click first media
        grid = self.device(resourceIdMatches=".*profile_grid.*|.*media_grid.*")
        if grid.exists(timeout=3):
            grid.click()
            time.sleep(3)
            return True

        # Method 3: Click center-right area where first grid item typically is
        w, h = self.device.window_size()
        self.device.click(int(w * 0.16), int(h * 0.6))
        time.sleep(3)

        # Verify we opened something (not still on profile)
        screen = self.ctrl.detect_screen()
        if screen != Screen.PROFILE:
            return True

        log.debug("[%s] Failed to open grid item", self.device_serial)
        return False

    def _click_share_button(self):
        """Click the share/send button on the current post.
        
        Live test confirmed: desc='Send post' and rid='row_feed_button_share' 
        are the correct selectors on IG clone apps.
        """
        # Method 1: Content description (confirmed working in live test)
        for desc in ["Send post", "Share", "Send", "Share post"]:
            el = self.device(description=desc)
            if el.exists(timeout=2):
                el.click()
                time.sleep(2)
                log.debug("[%s] Clicked share via desc='%s'",
                          self.device_serial, desc)
                return True

        # Method 2: Resource ID (confirmed: row_feed_button_share)
        el = self.device(resourceIdMatches=".*row_feed_button_share.*|.*direct_share_button.*")
        if el.exists(timeout=2):
            el.click()
            time.sleep(2)
            log.debug("[%s] Clicked share via resource ID", self.device_serial)
            return True

        # Method 3: Find in XML and click by bounds
        xml = self.ctrl.dump_xml()
        share_match = re.search(
            r'<node[^>]*(?:row_feed_button_share|direct_share_button)[^>]*'
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            xml)
        if share_match:
            x = (int(share_match.group(1)) + int(share_match.group(3))) // 2
            y = (int(share_match.group(2)) + int(share_match.group(4))) // 2
            self.device.click(x, y)
            time.sleep(2)
            log.debug("[%s] Clicked share via bounds (%d, %d)",
                      self.device_serial, x, y)
            return True

        log.debug("[%s] Share button not found", self.device_serial)
        return False

    def _select_add_to_story(self):
        """In the share sheet, find and tap 'Add to story'.
        
        Live test confirmed: text='Add to story' is the correct selector.
        The share sheet shows: Add to story, WhatsApp, Copy link, Share, Download
        """
        xml = self.ctrl.dump_xml()

        # Look for story-related text/descriptions in share sheet
        # Order updated based on live testing - "Add to story" is most common
        story_patterns = [
            "Add to story",
            "Add post to your story",
            "Add to your story",
            "Add reel to your story",
            "Your story",
        ]

        # Method 1: Match by text
        for pattern in story_patterns:
            el = self.device(textContains=pattern)
            if el.exists(timeout=2):
                el.click()
                time.sleep(2)
                log.debug("[%s] Clicked story option via text='%s'",
                          self.device_serial, pattern)
                return True

        # Method 2: Match by content-desc
        for pattern in story_patterns:
            el = self.device(descriptionContains=pattern)
            if el.exists(timeout=2):
                el.click()
                time.sleep(2)
                log.debug("[%s] Clicked story option via desc='%s'",
                          self.device_serial, pattern)
                return True

        # Method 3: XML search for anything with "story" that's clickable
        story_nodes = re.findall(
            r'<node[^>]*(?:text|content-desc)="([^"]*[Ss]tory[^"]*)"[^>]*'
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            xml)
        for desc, x1, y1, x2, y2 in story_nodes:
            if 'Add' in desc or 'your' in desc.lower():
                x = (int(x1) + int(x2)) // 2
                y = (int(y1) + int(y2)) // 2
                self.device.click(x, y)
                time.sleep(2)
                log.debug("[%s] Clicked story option via XML match '%s' at (%d,%d)",
                          self.device_serial, desc[:40], x, y)
                return True

        # Method 4: Scroll the share sheet and try again
        w, h = self.device.window_size()
        self.device.swipe(w // 2, int(h * 0.7), w // 2, int(h * 0.4), duration=0.3)
        time.sleep(1.5)

        for pattern in story_patterns[:3]:
            el = self.device(textContains=pattern)
            if el.exists(timeout=2):
                el.click()
                time.sleep(2)
                return True

        # Save debug XML
        self.ctrl.dump_xml("share_sheet_debug")
        log.warning("[%s] Could not find 'Add to story' in share sheet",
                    self.device_serial)
        return False

    def _add_story_mention(self, source_username):
        """Add @mention sticker to story via sticker picker.
        
        Same flow as link sticker (2026-02-22):
        1. Open sticker picker (swipe up OR tap sticker button)
        2. Search "mention" in search bar
        3. Tap first result (MENTION sticker)
        4. Mention form: type username, tap first suggestion, Done
        """
        mention_target = self.mention_target or source_username
        if not mention_target:
            return False

        log.info("[%s] Adding mention @%s via sticker picker", self.device_serial, mention_target)

        # Step 1: Open sticker picker — swipe up first, fallback to button
        sticker_found = False
        w, h = self.device.window_size()
        self.device.swipe(w // 2, int(h * 0.5), w // 2, int(h * 0.15), duration=0.3)
        time.sleep(2)

        if self.device(className="android.widget.EditText").exists(timeout=2):
            sticker_found = True
            log.debug("[%s] Opened sticker picker via swipe up", self.device_serial)

        if not sticker_found:
            for selector in [
                self.device(description="Emojis and stickers"),
                self.device(resourceIdMatches=".*asset_button.*"),
                self.device(descriptionContains="sticker"),
            ]:
                if selector.exists(timeout=2):
                    selector.click()
                    time.sleep(3)
                    sticker_found = True
                    log.debug("[%s] Opened sticker picker via button", self.device_serial)
                    break

        if not sticker_found:
            log.warning("[%s] Could not open sticker picker for mention", self.device_serial)
            return False

        # Step 2+3: Find and click MENTION sticker
        # Try direct click first (sticker grid often shows @MENTION in first row)
        mention_clicked = False

        for text_val in ["@MENTION", "MENTION", "@Mention", "Mention"]:
            el = self.device(textContains=text_val)
            if el.exists(timeout=2):
                el.click()
                time.sleep(2)
                mention_clicked = True
                log.debug("[%s] Clicked MENTION sticker via text='%s' (direct)",
                          self.device_serial, text_val)
                break

        if not mention_clicked:
            for desc_val in ["Mention Sticker", "MENTION", "Mention", "@MENTION",
                             "mention sticker"]:
                el = self.device(descriptionContains=desc_val)
                if not el.exists(timeout=1):
                    el = self.device(description=desc_val)
                if el.exists(timeout=1):
                    el.click()
                    time.sleep(2)
                    mention_clicked = True
                    log.debug("[%s] Clicked MENTION sticker via desc='%s'",
                              self.device_serial, desc_val)
                    break

        # Fallback: search for it
        if not mention_clicked:
            search = self.device(className="android.widget.EditText")
            if not search.exists(timeout=2):
                search = self.device(resourceIdMatches=".*search.*edit.*text.*")
            if search.exists(timeout=2):
                search.click()
                time.sleep(0.5)
                search.set_text("mention")
                time.sleep(3)
                log.debug("[%s] Typed 'mention' in sticker search", self.device_serial)

                for text_val in ["@MENTION", "MENTION", "Mention"]:
                    el = self.device(textContains=text_val)
                    if el.exists(timeout=2):
                        el.click()
                        time.sleep(2)
                        mention_clicked = True
                        log.debug("[%s] Clicked MENTION sticker via search + text='%s'",
                                  self.device_serial, text_val)
                        break

        # XML fallback
        if not mention_clicked:
            xml = self.ctrl.dump_xml("mention_sticker_search")
            for pattern in [r'text="@MENTION"', r'text="MENTION"', r'text="Mention"',
                            r'description="Mention Sticker"']:
                match = re.search(
                    pattern + r'[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
                if not match:
                    match = re.search(
                        r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*' + pattern, xml)
                if match:
                    x = (int(match.group(1)) + int(match.group(3))) // 2
                    y = (int(match.group(2)) + int(match.group(4))) // 2
                    self.device.click(x, y)
                    time.sleep(2)
                    mention_clicked = True
                    log.debug("[%s] Clicked MENTION sticker via XML bounds (%d,%d)",
                              self.device_serial, x, y)
                    break

        if not mention_clicked:
            log.warning("[%s] MENTION sticker not found in search results", self.device_serial)
            self.ctrl.press_back()
            return False

        # Step 4: Enter username in mention form and select from suggestions
        time.sleep(1)
        username_field = self.device(className="android.widget.EditText")
        if username_field.exists(timeout=3):
            username_field.click()
            time.sleep(0.5)
            username_field.set_text(mention_target)
            time.sleep(3)  # Wait for suggestions to load
            log.debug("[%s] Typed username: %s", self.device_serial, mention_target)

            # Click first suggestion (exact match should be first)
            suggestion_clicked = False
            target_lower = mention_target.lower()

            # Try clicking the exact username in suggestions
            for selector in [
                self.device(textContains=mention_target),
                self.device(descriptionContains=mention_target),
            ]:
                if selector.exists(timeout=2):
                    count = min(selector.count, 5)
                    for i in range(count):
                        try:
                            text = (selector[i].get_text() or "").strip().lower()
                            if text == target_lower or target_lower in text:
                                selector[i].click()
                                time.sleep(1.5)
                                suggestion_clicked = True
                                log.info("[%s] Clicked mention suggestion: '%s'",
                                         self.device_serial, mention_target)
                                break
                        except Exception:
                            continue
                    if suggestion_clicked:
                        break

            if not suggestion_clicked:
                # XML fallback for suggestion
                xml = self.ctrl.dump_xml("mention_suggestions")
                match = re.search(
                    r'text="' + re.escape(mention_target) + r'"[^>]*'
                    r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                    xml, re.IGNORECASE)
                if match:
                    x = (int(match.group(1)) + int(match.group(3))) // 2
                    y = (int(match.group(2)) + int(match.group(4))) // 2
                    self.device.click(x, y)
                    time.sleep(1.5)
                    suggestion_clicked = True
                    log.info("[%s] Clicked mention suggestion via XML", self.device_serial)

            if not suggestion_clicked:
                log.warning("[%s] Could not find suggestion for @%s — tapping Done anyway",
                            self.device_serial, mention_target)
        else:
            log.warning("[%s] Username input field not found in mention form", self.device_serial)
            self.ctrl.press_back()
            return False

        # Step 5: After clicking suggestion, IG auto-places the mention sticker
        # and returns to story preview. Only tap Done if we're stuck in editing mode.
        time.sleep(2)
        if self.device(textContains="Your story").exists(timeout=3):
            # Already back in story preview — no Done needed
            log.debug("[%s] Mention placed, already in story preview", self.device_serial)
        elif self.device(text="Done").exists(timeout=2):
            self.device(text="Done").click()
            time.sleep(2)
            log.debug("[%s] Clicked Done after mention placement", self.device_serial)
        elif self.device(description="Done").exists(timeout=2):
            self.device(description="Done").click()
            time.sleep(2)
            log.debug("[%s] Clicked Done (desc) after mention placement", self.device_serial)

        log.info("[%s] Mention @%s added to story via sticker", self.device_serial, mention_target)
        return True

    def _add_link_sticker(self, url):
        """Add link sticker to story in the editor.
        
        Live-tested flow (2026-02-21):
        1. Open sticker picker (swipe up OR tap sticker button)
        2. Type "link" in search bar
        3. Tap first result under "Stickers" heading (the blue LINK button)
        4. Link form: enter URL in first field, tap Done
        """
        if not url:
            return False

        log.info("[%s] Adding link sticker: %s", self.device_serial, url[:50])

        # Step 1: Open sticker picker — try swipe up first (more reliable), fallback to button
        sticker_found = False

        # Method A: Swipe up from center to open sticker picker
        w, h = self.device.window_size()
        self.device.swipe(w // 2, int(h * 0.5), w // 2, int(h * 0.15), duration=0.3)
        time.sleep(2)
        
        # Check if sticker picker opened (search bar should appear)
        if self.device(className="android.widget.EditText").exists(timeout=2):
            sticker_found = True
            log.debug("[%s] Opened sticker picker via swipe up", self.device_serial)
        
        # Method B: Tap sticker button
        if not sticker_found:
            for selector in [
                self.device(description="Emojis and stickers"),
                self.device(resourceIdMatches=".*asset_button.*"),
                self.device(descriptionContains="sticker"),
            ]:
                if selector.exists(timeout=2):
                    selector.click()
                    time.sleep(3)
                    sticker_found = True
                    log.debug("[%s] Opened sticker picker via button", self.device_serial)
                    break

        if not sticker_found:
            log.warning("[%s] Could not open sticker picker", self.device_serial)
            return False

        # Step 2: Type "link" in search bar
        search = self.device(className="android.widget.EditText")
        if not search.exists(timeout=3):
            search = self.device(resourceIdMatches=".*search.*edit.*text.*")
        
        if search.exists(timeout=3):
            search.click()
            time.sleep(0.5)
            search.set_text("link")
            time.sleep(3)  # Wait for search results to load
            log.debug("[%s] Typed 'link' in sticker search", self.device_serial)
        else:
            log.warning("[%s] Sticker search bar not found", self.device_serial)
            self.ctrl.press_back()
            return False

        # Step 3: Tap first result — the LINK sticker
        # From screenshot: appears as blue "LINK" button under "Stickers" heading
        # It's the FIRST clickable result after searching "link"
        link_clicked = False

        # Try description first (worked on .190 after search)
        for desc_val in ["Link Sticker", "LINK"]:
            el = self.device(description=desc_val)
            if el.exists(timeout=2):
                el.click()
                time.sleep(2)
                link_clicked = True
                log.debug("[%s] Clicked LINK sticker via desc='%s'", self.device_serial, desc_val)
                break

        # Try exact text match
        if not link_clicked:
            for text_val in ["LINK", "Link"]:
                el = self.device(text=text_val)
                if el.exists(timeout=2):
                    el.click()
                    time.sleep(2)
                    link_clicked = True
                    log.debug("[%s] Clicked LINK sticker via text='%s'", self.device_serial, text_val)
                    break

        # XML fallback — find first "LINK" or "Link Sticker" in bounds
        if not link_clicked:
            xml = self.ctrl.dump_xml("sticker_search_results")
            for pattern in [r'description="Link Sticker"', r'text="LINK"', r'text="Link"']:
                match = re.search(
                    pattern + r'[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
                if match:
                    x = (int(match.group(1)) + int(match.group(3))) // 2
                    y = (int(match.group(2)) + int(match.group(4))) // 2
                    self.device.click(x, y)
                    time.sleep(2)
                    link_clicked = True
                    log.debug("[%s] Clicked LINK sticker via XML bounds (%d,%d)",
                              self.device_serial, x, y)
                    break

        if not link_clicked:
            log.warning("[%s] LINK sticker not found in search results", self.device_serial)
            self.ctrl.press_back()
            return False

        # Step 4: Enter URL in the link form
        # Form has 2 EditText fields: URL (first) + name/label (second, optional)
        time.sleep(1)
        url_fields = self.device(className="android.widget.EditText")
        if url_fields.exists(timeout=3):
            url_fields[0].click()
            time.sleep(0.5)
            url_fields[0].set_text(url)
            time.sleep(1)
            log.debug("[%s] Entered URL: %s", self.device_serial, url[:50])
        else:
            log.warning("[%s] URL input field not found", self.device_serial)
            self.ctrl.press_back()
            return False

        # Step 5: Tap Done to confirm
        done_clicked = False
        for selector in [
            self.device(text="Done"),
            self.device(description="Done"),
            self.device(resourceIdMatches=".*done_button.*"),
        ]:
            if selector.exists(timeout=2):
                selector.click()
                time.sleep(2)
                done_clicked = True
                log.debug("[%s] Confirmed link sticker with Done", self.device_serial)
                break

        if not done_clicked:
            self.device.press('enter')
            time.sleep(1)

        log.info("[%s] Link sticker added: %s", self.device_serial, url[:50])
        return True

    def _add_text_overlay(self, text_content):
        """Add plain text overlay to story in the editor. (Task 2c)
        
        Flow: tap text tool → type custom text → position center-bottom.
        """
        if not text_content:
            return False

        log.info("[%s] Adding text overlay to story", self.device_serial)

        # Tap text tool — confirmed: rid=add_text_button, desc='Add text'
        text_tool_found = False
        for selector in [
            self.device(resourceIdMatches=".*add_text_button.*"),
            self.device(description="Add text"),
            self.device(descriptionContains="text"),
        ]:
            if selector.exists(timeout=3):
                selector.click()
                time.sleep(2)
                text_tool_found = True
                break

        if not text_tool_found:
            log.warning("[%s] Text tool not found for overlay", self.device_serial)
            return False

        # Type the text via EditText or ADB input
        time.sleep(1)
        edit_field = self.device(className="android.widget.EditText")
        if edit_field.exists(timeout=3):
            try:
                edit_field.set_text(text_content)
                time.sleep(1)
            except Exception:
                import subprocess
                adb_serial = self.device_serial.replace('_', ':')
                escaped = text_content.replace(' ', '%s').replace("'", "\\'")
                subprocess.run(
                    ['adb', '-s', adb_serial, 'shell', 'input', 'text', escaped],
                    capture_output=True, timeout=10
                )
                time.sleep(1)
        else:
            import subprocess
            try:
                adb_serial = self.device_serial.replace('_', ':')
                escaped = text_content.replace(' ', '%s').replace("'", "\\'")
                subprocess.run(
                    ['adb', '-s', adb_serial, 'shell', 'input', 'text', escaped],
                    capture_output=True, timeout=10
                )
                time.sleep(1)
            except Exception as e:
                log.error("[%s] Failed to type text overlay: %s", self.device_serial, e)
                return False

        # Confirm text — tap Done button
        done_btn = self.device(text="Done")
        if not done_btn.exists(timeout=2):
            done_btn = self.device(description="Done")
        if done_btn.exists(timeout=3):
            done_btn.click()
            time.sleep(1)
        else:
            self.device.press('back')
            time.sleep(1)

        log.info("[%s] Text overlay added to story", self.device_serial)
        return True

    def _apply_story_editor_features(self, source_username):
        """Apply all enabled story editor features before publishing. (Task 2)
        
        Called after story editor loads, before tapping Share.
        Features are optional and controlled by account settings.
        """
        features_applied = []

        # Wait for story editor to fully load
        time.sleep(2)

        # a) Mention on story
        if self.enable_mention:
            try:
                if self._add_story_mention(source_username):
                    features_applied.append('mention')
                    random_sleep(1, 2, label="after_mention")
            except Exception as e:
                log.warning("[%s] Mention failed: %s", self.device_serial, e)

        # b) Link sticker
        if self.enable_link_sticker and self.link_sticker_url:
            try:
                if self._add_link_sticker(self.link_sticker_url):
                    features_applied.append('link_sticker')
                    random_sleep(1, 2, label="after_link_sticker")
            except Exception as e:
                log.warning("[%s] Link sticker failed: %s", self.device_serial, e)

        # c) Text overlay
        if self.enable_text_overlay and self.text_overlay:
            try:
                if self._add_text_overlay(self.text_overlay):
                    features_applied.append('text_overlay')
                    random_sleep(1, 2, label="after_text_overlay")
            except Exception as e:
                log.warning("[%s] Text overlay failed: %s", self.device_serial, e)

        if features_applied:
            log.info("[%s] Story features applied: %s",
                     self.device_serial, ', '.join(features_applied))
        return features_applied

    def _publish_story(self, source_username=None):
        """In story editor, apply features then tap Share/publish button.
        
        Live test confirmed: text='Share' appears as the publish button.
        Story editor may show a loading state first.
        """
        # Wait for story editor to load (it shows "Loading..." initially)
        time.sleep(3)

        # Handle any permission dialogs blocking the editor
        self._handle_permission_dialogs()

        # Apply story editor features (mention, link sticker, text overlay)
        if source_username:
            self._apply_story_editor_features(source_username)

        xml = self.ctrl.dump_xml()

        # Look for publish button in story editor
        # CONFIRMED from live XML dump (2026-02-04, JACK 1, com.instagram.androim):
        #   Bottom bar (rid: story_share_controls_action_bar) has 3 buttons:
        #     desc='Your story'    [36,1608][456,1740]  — PUBLISHES the story ✓
        #     desc='Close Friends' [474,1608][894,1740] — shares to close friends
        #     desc='Share to'      [912,1608][1044,1740] — the ">" arrow (share to specific)
        #   "Your story" is the correct publish button.

        # Method 1: "Your story" button (primary — confirmed correct)
        # IMPORTANT: Publish button is on the BOTTOM action bar (y > 75% of screen).
        # After adding link sticker, "story" text may appear in overlay — must verify
        # the element is in the bottom bar, not in the middle of the editor.
        w, h = self.device.window_size()
        bottom_threshold = int(h * 0.70)  # Publish bar is at bottom

        for attempt in range(3):
            # Try by content-desc (most reliable — unique to the button)
            el = self.device(description="Your story")
            if el.exists(timeout=3):
                try:
                    info = el.info
                    bounds = info.get('bounds', {})
                    el_y = bounds.get('top', 0)
                    if el_y >= bottom_threshold:
                        el.click()
                        time.sleep(3)
                        log.info("[%s] Published story via desc='Your story' y=%d (attempt %d)",
                                 self.device_serial, el_y, attempt + 1)
                        return True
                    else:
                        log.debug("[%s] desc='Your story' found but y=%d < %d (not publish bar)",
                                  self.device_serial, el_y, bottom_threshold)
                except Exception:
                    el.click()
                    time.sleep(3)
                    log.info("[%s] Published story via desc='Your story' (attempt %d)",
                             self.device_serial, attempt + 1)
                    return True

            # Try by text — also verify it's in bottom bar
            el = self.device(text="Your story")
            if el.exists(timeout=2):
                try:
                    info = el.info
                    bounds = info.get('bounds', {})
                    el_y = bounds.get('top', 0)
                    if el_y >= bottom_threshold:
                        el.click()
                        time.sleep(3)
                        log.info("[%s] Published story via text='Your story' y=%d (attempt %d)",
                                 self.device_serial, el_y, attempt + 1)
                        return True
                except Exception:
                    pass

            if attempt < 2:
                log.debug("[%s] 'Your story' not found in bottom bar, waiting before retry %d...",
                          self.device_serial, attempt + 2)
                time.sleep(3)

        # Method 2: "Share to" arrow button (the ">" next to Your story / Close Friends)
        share_to = self.device(description="Share to")
        if share_to.exists(timeout=2):
            share_to.click()
            time.sleep(3)
            log.info("[%s] Published story via 'Share to' arrow", self.device_serial)
            return True

        # Method 3: Click the action bar by resource-id (click left side = "Your story")
        action_bar = self.device(resourceIdMatches=".*story_share_controls_action_bar.*")
        if action_bar.exists(timeout=2):
            try:
                info = action_bar.info
                bounds = info.get('bounds', {})
                left_x = bounds.get('left', 0) + 100
                center_y = (bounds.get('top', 0) + bounds.get('bottom', 0)) // 2
                if left_x > 0:
                    self.device.click(left_x, center_y)
                    time.sleep(3)
                    log.info("[%s] Published story via action bar left-side click",
                             self.device_serial)
                    return True
            except Exception as e:
                log.debug("[%s] Action bar click failed: %s", self.device_serial, e)

        # Method 4: Other text patterns
        for attr, pattern in [("text", "Share"), ("text", "Done"), ("text", "Post"),
                              ("description", "Share"), ("description", "Share to your story")]:
            if attr == "text":
                el = self.device(text=pattern)
            else:
                el = self.device(description=pattern)
            if el.exists(timeout=2):
                el.click()
                time.sleep(3)
                log.debug("[%s] Published story via %s='%s'",
                          self.device_serial, attr, pattern)
                return True

        # Method 5: Known resource-id patterns
        for rid_pattern in ["share_story_button", "done_button", "share_button",
                            "action_bar_button_action"]:
            el = self.device(resourceIdMatches=f".*{rid_pattern}.*")
            if el.exists(timeout=2):
                el.click()
                time.sleep(3)
                log.debug("[%s] Published story via rid=%s",
                          self.device_serial, rid_pattern)
                return True

        # Method 6: XML bounds search for share-like buttons
        share_nodes = re.findall(
            r'<node[^>]*(?:text|content-desc)="([^"]*(?:[Ss]hare|[Dd]one|[Pp]ost|[Ss]end|[Ss]tory)[^"]*)"[^>]*'
            r'clickable="true"[^>]*'
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            xml)
        for desc, x1, y1, x2, y2 in share_nodes:
            x = (int(x1) + int(x2)) // 2
            y = (int(y1) + int(y2)) // 2
            self.device.click(x, y)
            time.sleep(3)
            log.debug("[%s] Published story via XML match '%s'",
                      self.device_serial, desc[:40])
            return True

        # Method 5: Check if we're actually on the discard modal already
        # (meaning we accidentally triggered it)
        if self._dismiss_discard_modal():
            log.warning("[%s] Was on discard modal — story not published",
                        self.device_serial)
            return False

        self.ctrl.dump_xml("story_editor_debug")
        log.warning("[%s] Could not find publish button in story editor",
                    self.device_serial)
        return False

    def _dismiss_discard_modal(self):
        """Handle the 'Discard story?' confirmation modal.
        
        Instagram shows this when pressing back in the story editor:
        - "Discard story?" title
        - "If you go back now, your reel won't be shared to your story."
        - "Discard" button (red text)
        - "Keep editing" button
        
        We click "Discard" to escape cleanly.
        Returns True if modal was found and dismissed.
        """
        # Check for "Discard" button (the red action button)
        discard_btn = self.device(text="Discard")
        if discard_btn.exists(timeout=1):
            discard_btn.click()
            time.sleep(1.5)
            log.info("[%s] Dismissed 'Discard story?' modal", self.device_serial)
            return True

        # Also check via content-desc
        discard_btn = self.device(description="Discard")
        if discard_btn.exists(timeout=1):
            discard_btn.click()
            time.sleep(1.5)
            log.info("[%s] Dismissed 'Discard story?' modal (via desc)",
                     self.device_serial)
            return True

        # Check for "Discard story?" title text as fallback
        if self.device(textContains="Discard story").exists(timeout=1):
            # Modal is showing but we couldn't find the button — try tapping
            # "Discard" which is typically the first/top action
            discard_btn = self.device(textContains="Discard", 
                                       className="android.widget.Button")
            if discard_btn.exists(timeout=1):
                discard_btn.click()
                time.sleep(1.5)
                log.info("[%s] Dismissed 'Discard story?' modal (via button class)",
                         self.device_serial)
                return True

        return False

    def _go_back(self, times=3):
        """Press back multiple times to return to clean state.
        
        After each back press, checks for the 'Discard story?' modal
        and dismisses it if present.
        """
        for _ in range(times):
            self.ctrl.press_back()
            time.sleep(1)
            # Check for discard modal after each back press
            if self._dismiss_discard_modal():
                # Modal dismissed — we're out of the story editor now
                # Continue pressing back to get to clean state
                continue
        try:
            self.ctrl.dismiss_popups()
        except Exception:
            pass

    def _recover(self):
        """Try to recover to a known UI state."""
        try:
            # First check if we're stuck on the discard modal
            self._dismiss_discard_modal()
            self._go_back(5)
            self.ctrl.navigate_to(Screen.HOME_FEED)
        except Exception:
            pass


def execute_share_to_story(device, device_serial, account_info, session_id):
    """Convenience function to run share-to-story action."""
    action = ShareToStoryAction(device, device_serial, account_info, session_id)
    return action.execute()
