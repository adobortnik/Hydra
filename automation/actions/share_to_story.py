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

        # Story editor features (Task 2)
        self.enable_mention = self.settings.get('story_mention_enabled', False)
        self.mention_target = self.settings.get('story_mention_target', '')  # @username per source
        self.enable_link_sticker = self.settings.get('story_link_sticker_enabled', False)
        self.link_sticker_url = self.settings.get('story_link_sticker_url', '')
        self.enable_text_overlay = self.settings.get('story_text_overlay_enabled', False)
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

        # 2. Open first grid item (latest post/reel)
        if not self._open_first_grid_item():
            log.warning("[%s] Could not open grid item for @%s",
                        self.device_serial, source_username)
            self.ctrl.press_back()
            return False

        random_sleep(2, 3, label="post_loaded")

        # 3. Scroll down to reveal action buttons
        w, h = self.device.window_size()
        self.device.swipe(w // 2, int(h * 0.65), w // 2, int(h * 0.35), duration=0.3)
        time.sleep(2)

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

    def _open_first_grid_item(self):
        """Open the first post/reel in the profile grid."""
        xml = self.ctrl.dump_xml()

        # Method 1: Content-desc pattern for grid items
        # e.g. "Photo by cristiano. 2 days ago. Row 1, Column 1"
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
        # Grid usually starts around y=60% of screen, first item at x=16%
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
        """Add @mention to story in the editor. (Task 2a)
        
        DISCOVERED SELECTORS (live-tested 2025-01-24):
        - Text tool button: rid=add_text_button, desc='Add text'
        - Text input field: rid=text_overlay_edit_text, class=EditText
        - Mention picker:   rid=text_mention_picker, desc='Mention'
        - Done button:      rid=done_button, desc='Done'
        
        Flow: tap Add text → type @username → tap Done.
        Alternative: tap Add text → tap Mention picker → search user.
        """
        mention_target = self.mention_target or source_username
        if not mention_target:
            return False

        log.info("[%s] Adding mention @%s to story", self.device_serial, mention_target)

        # Find and tap text tool — confirmed selectors from live discovery
        text_tool_found = False
        for selector in [
            self.device(resourceId="com.instagram.androie:id/add_text_button"),
            self.device(description="Add text"),
            self.device(descriptionContains="Aa"),
        ]:
            if selector.exists(timeout=2):
                selector.click()
                time.sleep(2)
                text_tool_found = True
                log.debug("[%s] Tapped text tool (Add text)", self.device_serial)
                break

        if not text_tool_found:
            log.warning("[%s] Text tool not found in story editor", self.device_serial)
            return False

        # Type the mention into the text input field
        mention_text = f"@{mention_target}"
        time.sleep(1)

        # Method 1: Use the discovered EditText (rid=text_overlay_edit_text)
        edit_field = self.device(resourceId="com.instagram.androie:id/text_overlay_edit_text")
        if not edit_field.exists(timeout=2):
            edit_field = self.device(className="android.widget.EditText")
        
        if edit_field.exists(timeout=3):
            try:
                edit_field.set_text(mention_text)
                time.sleep(1)
                log.debug("[%s] Typed mention via EditText", self.device_serial)
            except Exception:
                # Fallback: ADB input
                import subprocess
                subprocess.run(
                    ['adb', '-s', self.ctrl.adb_serial, 'shell', 'input', 'text',
                     mention_text.replace(' ', '%s')],
                    capture_output=True, timeout=10
                )
                time.sleep(1)
        else:
            # Fallback: ADB input if no EditText found
            import subprocess
            try:
                subprocess.run(
                    ['adb', '-s', self.ctrl.adb_serial, 'shell', 'input', 'text',
                     mention_text.replace(' ', '%s')],
                    capture_output=True, timeout=10
                )
                time.sleep(1)
            except Exception as e:
                log.error("[%s] Failed to type mention: %s", self.device_serial, e)
                return False

        # Tap Done button — confirmed: rid=done_button, desc='Done'
        done_btn = self.device(resourceId="com.instagram.androie:id/done_button")
        if not done_btn.exists(timeout=2):
            done_btn = self.device(description="Done")
        if not done_btn.exists(timeout=2):
            done_btn = self.device(text="Done")

        if done_btn.exists(timeout=3):
            done_btn.click()
            time.sleep(1)
            log.debug("[%s] Confirmed text with Done button", self.device_serial)
        else:
            # Tap outside the text area to deselect
            w, h = self.device.window_size()
            self.device.click(int(w * 0.5), int(h * 0.3))
            time.sleep(1)

        log.info("[%s] Mention @%s added to story", self.device_serial, mention_target)
        return True

    def _add_link_sticker(self, url):
        """Add link sticker to story in the editor. (Task 2b)
        
        DISCOVERED SELECTORS (live-tested 2025-01-24):
        - Sticker button: rid=asset_button, desc='Emojis and stickers'
        - Search bar:     rid=row_search_edit_text, class=EditText
        - Link Sticker:   desc='Link Sticker'
        - Mention Sticker: desc='Mention Sticker'
        
        Sticker picker shows: LOCATION, MENTION, MUSIC, PHOTO, GIF,
        ADD YOURS, FRAMES, QUESTIONS, CUTOUTS, AVATAR, ADD YOURS TEMPLATES,
        POLL, LINK, HASHTAG, DONATION, COUNTDOWN
        
        Flow: tap sticker button → tap Link Sticker (or search) → enter URL.
        """
        if not url:
            return False

        log.info("[%s] Adding link sticker: %s", self.device_serial, url[:50])

        # Tap sticker icon — confirmed: rid=asset_button, desc='Emojis and stickers'
        sticker_found = False
        for selector in [
            self.device(resourceId="com.instagram.androie:id/asset_button"),
            self.device(description="Emojis and stickers"),
            self.device(descriptionContains="sticker"),
        ]:
            if selector.exists(timeout=2):
                selector.click()
                time.sleep(3)
                sticker_found = True
                log.debug("[%s] Tapped sticker button", self.device_serial)
                break

        if not sticker_found:
            log.warning("[%s] Sticker button not found", self.device_serial)
            return False

        # Method 1: Directly tap "Link Sticker" (visible in picker grid)
        link_sticker = self.device(description="Link Sticker")
        if link_sticker.exists(timeout=3):
            log.debug("[%s] Found Link Sticker directly, clicking...", self.device_serial)
            link_sticker.click()
            time.sleep(2)
        else:
            # Method 2: Search for it
            search = self.device(resourceId="com.instagram.androie:id/row_search_edit_text")
            if not search.exists(timeout=2):
                search = self.device(className="android.widget.EditText")
            
            if search.exists(timeout=3):
                search.click()
                time.sleep(0.5)
                search.set_text("Link")
                time.sleep(2)
                
                # Tap the Link sticker from search results
                link_result = self.device(description="Link Sticker")
                if not link_result.exists(timeout=3):
                    link_result = self.device(descriptionContains="Link")
                if link_result.exists(timeout=2):
                    link_result.click()
                    time.sleep(2)
                else:
                    log.warning("[%s] Link sticker not found in search", self.device_serial)
                    self.ctrl.press_back()
                    return False
            else:
                log.warning("[%s] Sticker search bar not found", self.device_serial)
                self.ctrl.press_back()
                return False

        # Enter the URL in the link sticker dialog
        url_field = self.device(className="android.widget.EditText")
        if url_field.exists(timeout=3):
            url_field.click()
            time.sleep(0.5)
            url_field.set_text(url)
            time.sleep(1)

            # Confirm
            done = self.device(text="Done")
            if not done.exists(timeout=2):
                done = self.device(description="Done")
            if done.exists(timeout=2):
                done.click()
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
        # Try multiple times with increasing wait — editor may still be loading
        for attempt in range(3):
            # Try by content-desc (most reliable)
            el = self.device(description="Your story")
            if el.exists(timeout=3):
                el.click()
                time.sleep(3)
                log.info("[%s] Published story via desc='Your story' (attempt %d)",
                         self.device_serial, attempt + 1)
                return True

            # Try by text
            el = self.device(text="Your story")
            if el.exists(timeout=2):
                el.click()
                time.sleep(3)
                log.info("[%s] Published story via text='Your story' (attempt %d)",
                         self.device_serial, attempt + 1)
                return True

            # Try by textContains (handles variations like "Your Story")
            el = self.device(textContains="Your story")
            if not el.exists(timeout=1):
                el = self.device(textContains="our story")
            if el.exists(timeout=1):
                el.click()
                time.sleep(3)
                log.info("[%s] Published story via textContains (attempt %d)",
                         self.device_serial, attempt + 1)
                return True

            if attempt < 2:
                log.debug("[%s] 'Your story' not found, waiting before retry %d...",
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
