"""
Post Content Action Module
============================
Posts scheduled content (feed post, reel, story) to Instagram via uiautomator2.

Handles three content types:
  - post: Feed post with image + caption + hashtags + optional location
  - reel: Short video with caption + optional music
  - story: Image/video story with optional mention/link stickers

Media is pushed to the device via ADB, then selected from the gallery inside IG.
"""

import logging
import os
import re
import subprocess
import time

from automation.actions.helpers import (
    random_sleep, log_action, get_db
)
from automation.ig_controller import IGController, Screen

log = logging.getLogger(__name__)


class PostContentAction:
    """Post scheduled content (post/reel/story) to Instagram."""

    def __init__(self, device, device_serial, account_info, session_id,
                 schedule_item, package='com.instagram.androie'):
        """
        Args:
            device: uiautomator2 device object
            device_serial: e.g. '10.1.11.4_5555'
            account_info: dict with account data (id, username, package, etc.)
            session_id: current bot session id
            schedule_item: dict from content_schedule row
        """
        self.device = device
        self.device_serial = device_serial
        self.account = account_info
        self.session_id = session_id
        self.schedule = schedule_item
        self.username = account_info['username']
        self.account_id = account_info['id']

        pkg = account_info.get('package', package)
        self.ctrl = IGController(device, device_serial, pkg)

        # Parse schedule item fields
        self.content_type = schedule_item.get('content_type', 'post')  # post/reel/story
        self.media_path = schedule_item.get('media_path', '')
        self.caption = schedule_item.get('caption', '') or ''
        self.hashtags = schedule_item.get('hashtags', '') or ''
        self.location = schedule_item.get('location', '') or ''
        self.music_name = schedule_item.get('music_name', '') or ''
        self.music_search_query = schedule_item.get('music_search_query', '') or ''
        self.mention_username = schedule_item.get('mention_username', '') or ''
        self.link_url = schedule_item.get('link_url', '') or ''

        # Build full caption with hashtags
        self.full_caption = self.caption
        if self.hashtags:
            # Add hashtags on new line if caption exists
            if self.full_caption:
                self.full_caption += '\n\n' + self.hashtags
            else:
                self.full_caption = self.hashtags

        # Remote path for pushed media
        self._remote_media_path = None

    def execute(self):
        """
        Execute the content posting action.

        Returns dict: {success, content_type, error_message}
        """
        result = {
            'success': False,
            'content_type': self.content_type,
            'error_message': None,
        }

        schedule_id = self.schedule.get('id')
        caption_preview = (self.caption[:50] + '...') if len(self.caption) > 50 else self.caption

        log.info("[%s] CONTENT: Posting %s for @%s (schedule #%s, caption: \"%s\")",
                 self.device_serial, self.content_type, self.username,
                 schedule_id, caption_preview)

        try:
            # Validate media path
            if not self.media_path or not os.path.exists(self.media_path):
                raise FileNotFoundError(
                    f"Media file not found: {self.media_path}")

            # Ensure IG is open and on home screen
            self.ctrl.ensure_app()
            self.ctrl.dismiss_popups()
            self.ctrl.navigate_to(Screen.HOME_FEED)
            time.sleep(2)

            # Push media to device
            self._remote_media_path = self._push_media_to_device(self.media_path)
            if not self._remote_media_path:
                raise RuntimeError("Failed to push media to device")

            log.info("[%s] CONTENT: Pushed media to %s",
                     self.device_serial, self._remote_media_path)

            # Dispatch to content-type handler
            if self.content_type == 'post':
                success = self._post_feed_post()
            elif self.content_type == 'reel':
                success = self._post_reel()
            elif self.content_type == 'story':
                success = self._post_story()
            else:
                raise ValueError(f"Unknown content type: {self.content_type}")

            if success:
                result['success'] = True
                log.info("[%s] CONTENT: ✓ %s posted successfully",
                         self.device_serial, self.content_type.capitalize())
                log_action(
                    self.session_id, self.device_serial, self.username,
                    f'post_content_{self.content_type}',
                    success=True)
            else:
                result['error_message'] = f'{self.content_type} posting flow failed'
                log.warning("[%s] CONTENT: ✗ %s posting failed",
                            self.device_serial, self.content_type.capitalize())
                log_action(
                    self.session_id, self.device_serial, self.username,
                    f'post_content_{self.content_type}',
                    success=False,
                    error_message=result['error_message'])

        except Exception as e:
            result['error_message'] = str(e)[:500]
            log.error("[%s] CONTENT: ✗ Error posting %s: %s",
                      self.device_serial, self.content_type, e)
            log_action(
                self.session_id, self.device_serial, self.username,
                f'post_content_{self.content_type}',
                success=False,
                error_message=result['error_message'])

        finally:
            # Clean up pushed media from device
            self._cleanup_device_media()
            # Try to recover to home
            self._recover()

        return result

    # ------------------------------------------------------------------
    # ADB Media Push / Cleanup
    # ------------------------------------------------------------------

    def _push_media_to_device(self, local_path, remote_dir="/sdcard/Pictures"):
        """Push media file to device via ADB and register in MediaStore."""
        adb_serial = self.device_serial.replace('_', ':')
        filename = os.path.basename(local_path)
        remote_path = f"{remote_dir}/{filename}"
        # MediaStore needs the real /storage/emulated/0 path, not /sdcard
        real_remote_path = remote_path.replace('/sdcard/', '/storage/emulated/0/')

        # Determine mime type
        ext = os.path.splitext(filename)[1].lower()
        mime_map = {
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
            '.gif': 'image/gif', '.webp': 'image/webp', '.bmp': 'image/bmp',
            '.mp4': 'video/mp4', '.mov': 'video/quicktime', '.avi': 'video/x-msvideo',
        }
        mime_type = mime_map.get(ext, 'image/jpeg')
        is_video = mime_type.startswith('video/')
        media_uri = 'content://media/external/video/media' if is_video else 'content://media/external/images/media'

        # Create remote directory
        subprocess.run(
            ['adb', '-s', adb_serial, 'shell', 'mkdir', '-p', remote_dir],
            capture_output=True, timeout=10)

        # Push the file
        result = subprocess.run(
            ['adb', '-s', adb_serial, 'push', local_path, remote_path],
            capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            log.error("[%s] CONTENT: ADB push failed: %s",
                      self.device_serial, result.stderr[:200])
            return None

        # Register in MediaStore via content insert (works on Android 10+)
        # This is the reliable replacement for the deprecated MEDIA_SCANNER_SCAN_FILE broadcast
        insert_result = subprocess.run(
            ['adb', '-s', adb_serial, 'shell', 'content', 'insert',
             '--uri', media_uri,
             '--bind', f'_data:s:{real_remote_path}',
             '--bind', f'_display_name:s:{filename}',
             '--bind', f'mime_type:s:{mime_type}'],
            capture_output=True, text=True, timeout=15)

        if insert_result.returncode != 0:
            log.warning("[%s] CONTENT: MediaStore insert failed (%s), trying legacy broadcast",
                        self.device_serial, insert_result.stderr[:100])
            # Fallback: legacy broadcast (works on Android <10)
            subprocess.run(
                ['adb', '-s', adb_serial, 'shell',
                 'am', 'broadcast', '-a',
                 'android.intent.action.MEDIA_SCANNER_SCAN_FILE',
                 '-d', f'file://{remote_path}'],
                capture_output=True, timeout=10)
        else:
            log.info("[%s] CONTENT: Registered %s in MediaStore",
                     self.device_serial, filename)

        # Give media system a moment to index
        time.sleep(2)

        return remote_path

    def _cleanup_device_media(self):
        """Remove pushed media file from device."""
        if not self._remote_media_path:
            return
        try:
            adb_serial = self.device_serial.replace('_', ':')
            subprocess.run(
                ['adb', '-s', adb_serial, 'shell', 'rm', '-f',
                 self._remote_media_path],
                capture_output=True, timeout=10)
            log.debug("[%s] CONTENT: Cleaned up %s from device",
                      self.device_serial, self._remote_media_path)
        except Exception as e:
            log.debug("[%s] CONTENT: Cleanup failed (non-critical): %s",
                      self.device_serial, e)

    # ------------------------------------------------------------------
    # Feed Post Flow
    # ------------------------------------------------------------------

    def _post_feed_post(self):
        """
        Post a feed post (image + caption).

        Flow:
        1. Tap "+" (new content) button on home screen
        2. Select "Post" option
        3. Select media from gallery (the file we pushed)
        4. Tap "Next" → skip filters → "Next"
        5. Enter caption + hashtags
        6. Optionally add location
        7. Tap "Share"
        8. Wait for upload confirmation

        Returns True on success.
        """
        # Step 1: Tap the "+" / create content button
        if not self._tap_create_button():
            log.warning("[%s] CONTENT: Could not find create/+ button",
                        self.device_serial)
            return False

        random_sleep(1.5, 3, label="create_menu_loading")

        # Step 2: Select "Post" from content type picker
        if not self._select_content_type('POST'):
            log.warning("[%s] CONTENT: Could not select Post option",
                        self.device_serial)
            self.ctrl.press_back()
            return False

        random_sleep(2, 4, label="gallery_loading")

        # Step 3: Select media from gallery
        if not self._select_media_from_gallery():
            log.warning("[%s] CONTENT: Could not select media from gallery",
                        self.device_serial)
            self._go_back(2)
            return False

        random_sleep(1, 2, label="media_selected")

        # Step 4: Tap "Next" (past gallery selection)
        if not self._tap_next():
            log.warning("[%s] CONTENT: Could not tap Next after gallery",
                        self.device_serial)
            self._go_back(3)
            return False

        random_sleep(2, 3, label="filter_screen_loading")

        # Step 5: Tap "Next" again (past filters screen — skip filters)
        if not self._tap_next():
            # Some flows go directly to caption screen
            log.debug("[%s] CONTENT: No second Next — may be on caption screen already",
                      self.device_serial)

        random_sleep(1.5, 3, label="caption_screen_loading")

        # Step 6: Enter caption
        if self.full_caption:
            self._enter_caption(self.full_caption)
            # Dismiss keyboard so Share button is visible
            self.device.press('back')
            random_sleep(1, 2, label="after_caption_dismiss_keyboard")

        # Step 7: Optionally add location
        if self.location:
            self._add_location(self.location)
            random_sleep(1, 2, label="after_location")

        # Step 8: Tap "Share" / "Post"
        if not self._tap_share():
            log.warning("[%s] CONTENT: Could not tap Share/Post button",
                        self.device_serial)
            self._go_back(4)
            return False

        # Step 9: Wait for upload
        return self._wait_for_upload_complete()

    # ------------------------------------------------------------------
    # Reel Flow
    # ------------------------------------------------------------------

    def _post_reel(self):
        """
        Post a reel (video + caption + optional music).

        Flow:
        1. Tap "+" → select "Reel"
        2. Select video from gallery
        3. Optionally add music
        4. Tap "Next" → enter caption
        5. Tap "Share"

        Returns True on success.
        """
        # Step 1: Tap create button
        if not self._tap_create_button():
            log.warning("[%s] CONTENT: Could not find create/+ button",
                        self.device_serial)
            return False

        random_sleep(1.5, 3, label="create_menu_loading")

        # Step 2: Select "Reel" option
        if not self._select_content_type('REEL'):
            log.warning("[%s] CONTENT: Could not select Reel option",
                        self.device_serial)
            self.ctrl.press_back()
            return False

        random_sleep(2, 4, label="reel_gallery_loading")

        # Step 3: Select video from gallery
        if not self._select_media_from_gallery():
            log.warning("[%s] CONTENT: Could not select video from gallery",
                        self.device_serial)
            self._go_back(2)
            return False

        random_sleep(1, 2, label="video_selected")

        # Step 4: Tap "Next" to proceed past video trimming/preview
        if not self._tap_next():
            log.debug("[%s] CONTENT: No Next button on reel preview — trying Add",
                      self.device_serial)
            # Some IG versions use "Add" instead of "Next"
            add_btn = self.device(text="Add")
            if add_btn.exists(timeout=3):
                add_btn.click()
                time.sleep(2)

        random_sleep(2, 3, label="reel_editor_loading")

        # Step 5: Add music if specified
        if self.music_search_query:
            self._add_reel_music(self.music_search_query)
            random_sleep(1, 2, label="after_music")

        # Step 6: Tap "Next" to go to caption screen
        if not self._tap_next():
            log.debug("[%s] CONTENT: No Next on reel editor — may already be on caption",
                      self.device_serial)

        random_sleep(1.5, 3, label="reel_caption_loading")

        # Step 7: Enter caption
        if self.full_caption:
            self._enter_caption(self.full_caption)
            # Dismiss keyboard so Share button is visible
            self.device.press('back')
            random_sleep(1, 2, label="after_caption_dismiss_keyboard")

        # Step 8: Tap "Share"
        if not self._tap_share():
            log.warning("[%s] CONTENT: Could not tap Share for reel",
                        self.device_serial)
            self._go_back(4)
            return False

        # Step 9: Wait for upload
        return self._wait_for_upload_complete()

    # ------------------------------------------------------------------
    # Story Flow
    # ------------------------------------------------------------------

    def _post_story(self):
        """
        Post a story (image/video + optional stickers).

        Flow:
        1. Tap story creation (Your story / + icon at top-left)
        2. Select media from gallery
        3. Add mention sticker if specified
        4. Add link sticker if specified
        5. Tap "Share to Story" / "Your Story"

        Returns True on success.
        """
        # Step 1: Tap story creation entry point
        if not self._tap_story_create():
            # Fallback: use the general create button → Story option
            if not self._tap_create_button():
                log.warning("[%s] CONTENT: Could not find story creation entry",
                            self.device_serial)
                return False

            random_sleep(1, 2, label="create_menu_loading")

            if not self._select_content_type('STORY'):
                log.warning("[%s] CONTENT: Could not select Story option",
                            self.device_serial)
                self.ctrl.press_back()
                return False

        random_sleep(2, 4, label="story_camera_loading")

        # Step 2: Open gallery in story camera and select media
        if not self._select_media_in_story_mode():
            log.warning("[%s] CONTENT: Could not select media for story",
                        self.device_serial)
            self._go_back(2)
            return False

        random_sleep(2, 3, label="story_editor_loading")

        # Step 3: Add mention sticker if specified
        if self.mention_username:
            self._add_mention_sticker(self.mention_username)
            random_sleep(1, 2, label="after_mention_sticker")

        # Step 4: Add link sticker if specified
        if self.link_url:
            self._add_link_sticker(self.link_url)
            random_sleep(1, 2, label="after_link_sticker")

        # Step 5: Publish story
        if not self._tap_story_share():
            log.warning("[%s] CONTENT: Could not publish story",
                        self.device_serial)
            self._go_back(3)
            return False

        random_sleep(3, 5, label="story_publishing")
        return True

    # ==================================================================
    # UI Interaction Helpers (shared across content types)
    # ==================================================================

    def _tap_create_button(self):
        """
        Tap the "+" / create new content button on the home screen.

        Known selectors (IG clone apps):
        - content-desc="Create" or "New post"
        - resource-id contains "creation_tab" or "tab_bar" with "+"
        - The "+" tab in bottom nav bar

        Returns True if tapped.
        """
        # Method 1: Content description based
        for desc in ["Create", "New post", "New Post", "Add"]:
            el = self.device(description=desc)
            if el.exists(timeout=2):
                el.click()
                time.sleep(2)
                log.debug("[%s] CONTENT: Tapped create via desc='%s'",
                          self.device_serial, desc)
                return True

        # Method 2: Resource ID patterns
        for rid_pattern in ['creation_tab', 'tab_create', 'compose_tab',
                            'action_bar_new_post']:
            el = self.device(resourceIdMatches=f".*{rid_pattern}.*")
            if el.exists(timeout=2):
                el.click()
                time.sleep(2)
                log.debug("[%s] CONTENT: Tapped create via rid pattern '%s'",
                          self.device_serial, rid_pattern)
                return True

        # Method 3: "+" text button (some IG versions show literal +)
        el = self.device(text="+")
        if el.exists(timeout=2):
            el.click()
            time.sleep(2)
            return True

        # Method 4: Look in bottom navigation for a creation/compose icon
        # Typically the center button in the bottom nav
        xml = self.ctrl.dump_xml("find_create_btn")
        # Look for any clickable node with "create" or "new" in desc/rid
        create_nodes = re.findall(
            r'<node[^>]*(?:content-desc="[^"]*(?:[Cc]reate|[Nn]ew post)[^"]*"|'
            r'resource-id="[^"]*(?:creation|compose|create)[^"]*")[^>]*'
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            xml)
        if create_nodes:
            x1, y1, x2, y2 = [int(v) for v in create_nodes[0]]
            self.device.click((x1 + x2) // 2, (y1 + y2) // 2)
            time.sleep(2)
            log.debug("[%s] CONTENT: Tapped create via XML bounds",
                      self.device_serial)
            return True

        # Method 5: Tap center of bottom nav bar (common position for +)
        w, h = self.device.window_size()
        self.device.click(w // 2, int(h * 0.95))
        time.sleep(2)
        log.debug("[%s] CONTENT: Tapped center bottom nav as fallback",
                  self.device_serial)
        return True

    def _select_content_type(self, content_type):
        """
        In the content type picker (POST / REEL / STORY), select the right one.

        Args:
            content_type: 'POST', 'REEL', or 'STORY'

        Returns True if selected.
        """
        type_map = {
            'POST': ['Post', 'POST', 'New post'],
            'REEL': ['Reel', 'REEL', 'Reels', 'Short video'],
            'STORY': ['Story', 'STORY', 'Your story'],
        }

        labels = type_map.get(content_type, [content_type])

        # Method 1: Text-based match
        for label in labels:
            el = self.device(text=label)
            if el.exists(timeout=3):
                el.click()
                time.sleep(2)
                log.debug("[%s] CONTENT: Selected content type '%s' via text",
                          self.device_serial, label)
                return True

        # Method 2: Content description match
        for label in labels:
            el = self.device(descriptionContains=label)
            if el.exists(timeout=2):
                el.click()
                time.sleep(2)
                log.debug("[%s] CONTENT: Selected content type '%s' via desc",
                          self.device_serial, label)
                return True

        # Method 3: XML search for tab/button with the text
        xml = self.ctrl.dump_xml("content_type_picker")
        for label in labels:
            pattern = (
                r'<node[^>]*(?:text="' + re.escape(label) + r'"|'
                r'content-desc="[^"]*' + re.escape(label) + r'[^"]*")[^>]*'
                r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
            )
            match = re.search(pattern, xml, re.IGNORECASE)
            if match:
                x1, y1, x2, y2 = [int(v) for v in match.groups()]
                self.device.click((x1 + x2) // 2, (y1 + y2) // 2)
                time.sleep(2)
                log.debug("[%s] CONTENT: Selected content type via XML '%s'",
                          self.device_serial, label)
                return True

        # If no picker appeared, we might already be in the right mode
        # (some IG versions go directly to gallery for posts)
        log.debug("[%s] CONTENT: Content type picker not found — may already be in correct mode",
                  self.device_serial)
        return True

    def _select_media_from_gallery(self):
        """
        Select the pushed media file from the gallery view.

        The gallery typically shows recent items first. Since we just pushed
        the file and triggered a media scan, it should appear as the most
        recent item (top-left in grid).

        Returns True if media was selected.
        """
        # Method 1: Look for gallery tab/button and ensure we're in gallery mode
        for label in ["Gallery", "GALLERY", "Recents", "All Photos"]:
            el = self.device(textContains=label)
            if el.exists(timeout=2):
                el.click()
                time.sleep(2)
                log.debug("[%s] CONTENT: Tapped gallery tab '%s'",
                          self.device_serial, label)
                break

        # Also try resource-id based gallery tab
        for rid in ['gallery_tab', 'gallery_folder_menu', 'gallery_picker_tab']:
            el = self.device(resourceIdMatches=f".*{rid}.*")
            if el.exists(timeout=2):
                el.click()
                time.sleep(1)
                break

        random_sleep(1, 2, label="gallery_grid_loading")

        # Method 2: Select the first (most recent) image in the gallery grid
        # IG gallery grid uses ImageView elements — the first one is our pushed media
        # Try specific gallery grid resource IDs
        for rid in ['gallery_grid_item_image', 'media_thumbnail',
                    'gallery_image_view', 'gallery_grid']:
            grid_item = self.device(resourceIdMatches=f".*{rid}.*")
            if grid_item.exists(timeout=3):
                try:
                    grid_item[0].click()
                    time.sleep(2)
                    log.debug("[%s] CONTENT: Selected media via rid='%s'",
                              self.device_serial, rid)
                    return True
                except Exception:
                    continue

        # Method 3: Look for a large preview image (some IG versions show a
        # preview of the selected image at top, with grid below)
        # The preview is typically already showing the latest image.
        # Just look for the grid and tap the first item
        xml = self.ctrl.dump_xml("gallery_select")

        # Find ImageView elements that look like gallery thumbnails
        # They're usually in a RecyclerView/GridView with square-ish bounds
        thumb_pattern = (
            r'<node[^>]*class="android\.widget\.ImageView"[^>]*'
            r'clickable="true"[^>]*'
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
        )
        thumbs = re.findall(thumb_pattern, xml)
        if thumbs:
            # Pick the first thumbnail (most recent media)
            x1, y1, x2, y2 = [int(v) for v in thumbs[0]]
            # Sanity check: thumbnail should be reasonably sized (not a tiny icon)
            w = x2 - x1
            h = y2 - y1
            if w > 50 and h > 50:
                self.device.click((x1 + x2) // 2, (y1 + y2) // 2)
                time.sleep(2)
                log.debug("[%s] CONTENT: Selected media via first ImageView thumbnail",
                          self.device_serial)
                return True

        # Method 4: Tap the typical gallery grid area (center of screen)
        # The gallery grid usually occupies the bottom 2/3 of the screen
        w, h = self.device.window_size()
        self.device.click(int(w * 0.16), int(h * 0.6))
        time.sleep(2)
        log.debug("[%s] CONTENT: Tapped gallery grid area as fallback",
                  self.device_serial)
        return True

    def _select_media_in_story_mode(self):
        """
        In story camera mode, open the gallery picker and select pushed media.

        Story camera typically has a small gallery thumbnail at bottom-left
        that opens the full gallery picker.

        Returns True if media was selected.
        """
        # Method 1: Look for gallery/recent media thumbnail in story camera
        for desc in ["Gallery", "Recent", "Photos", "Choose from gallery"]:
            el = self.device(descriptionContains=desc)
            if el.exists(timeout=3):
                el.click()
                time.sleep(3)
                log.debug("[%s] CONTENT: Opened gallery in story mode via desc='%s'",
                          self.device_serial, desc)
                break
        else:
            # Method 2: Resource ID for the gallery preview thumbnail
            for rid in ['gallery_preview', 'camera_roll_preview',
                        'recent_image_thumbnail', 'media_preview']:
                el = self.device(resourceIdMatches=f".*{rid}.*")
                if el.exists(timeout=2):
                    el.click()
                    time.sleep(3)
                    log.debug("[%s] CONTENT: Opened gallery in story mode via rid='%s'",
                              self.device_serial, rid)
                    break
            else:
                # Method 3: Swipe up from bottom to open gallery picker
                # (common gesture in story camera)
                w, h = self.device.window_size()
                self.device.swipe(w // 2, int(h * 0.85), w // 2, int(h * 0.3),
                                  duration=0.4)
                time.sleep(3)
                log.debug("[%s] CONTENT: Swiped up to open gallery in story mode",
                          self.device_serial)

        # Now select the most recent item (our pushed media)
        random_sleep(1, 2, label="story_gallery_loaded")

        # Look for gallery grid items
        for rid in ['gallery_grid_item_image', 'media_thumbnail',
                    'gallery_image_view']:
            grid_item = self.device(resourceIdMatches=f".*{rid}.*")
            if grid_item.exists(timeout=3):
                try:
                    grid_item[0].click()
                    time.sleep(3)
                    log.debug("[%s] CONTENT: Selected media for story via rid='%s'",
                              self.device_serial, rid)
                    return True
                except Exception:
                    continue

        # Fallback: tap first clickable ImageView
        xml = self.ctrl.dump_xml("story_gallery")
        thumb_pattern = (
            r'<node[^>]*class="android\.widget\.ImageView"[^>]*'
            r'clickable="true"[^>]*'
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
        )
        thumbs = re.findall(thumb_pattern, xml)
        if thumbs:
            x1, y1, x2, y2 = [int(v) for v in thumbs[0]]
            if (x2 - x1) > 50 and (y2 - y1) > 50:
                self.device.click((x1 + x2) // 2, (y1 + y2) // 2)
                time.sleep(3)
                return True

        # Last resort: tap the bottom-left of screen (gallery thumbnail location)
        w, h = self.device.window_size()
        self.device.click(int(w * 0.08), int(h * 0.9))
        time.sleep(3)
        return True

    def _tap_story_create(self):
        """
        Tap the story creation entry point from home screen.
        This is the "Your story" / "+" circle at top-left of the stories tray.

        Returns True if tapped.
        """
        # Method 1: Content description
        for desc in ["Your story", "Add to story", "Create story",
                      "Your Story"]:
            el = self.device(descriptionContains=desc)
            if el.exists(timeout=3):
                el.click()
                time.sleep(3)
                log.debug("[%s] CONTENT: Tapped story create via desc='%s'",
                          self.device_serial, desc)
                return True

        # Method 2: Resource ID for story ring / create button
        for rid in ['reel_viewer_subtitle', 'story_ring', 'your_story']:
            el = self.device(resourceIdMatches=f".*{rid}.*")
            if el.exists(timeout=2):
                el.click()
                time.sleep(3)
                return True

        # Method 3: Tap top-left area where "Your story" typically appears
        w, h = self.device.window_size()
        self.device.click(int(w * 0.08), int(h * 0.12))
        time.sleep(3)

        # Check if we entered story camera
        xml = self.ctrl.dump_xml("story_create_check")
        if ('camera' in xml.lower() or 'shutter' in xml.lower() or
                'gallery' in xml.lower()):
            return True

        return False

    def _tap_next(self):
        """
        Tap the "Next" button (appears in gallery selection and filter screens).
        Note: On filter/edit screen, button may show "Next →" — use textContains.

        Returns True if tapped.
        """
        # Method 1: Text-based (textContains to catch "Next", "Next →", etc.)
        for text in ["Next", "NEXT"]:
            el = self.device(textContains=text)
            if el.exists(timeout=5):
                el.click()
                time.sleep(2)
                log.debug("[%s] CONTENT: Tapped Next (textContains='%s')",
                          self.device_serial, text)
                return True

        # Method 2: Content description
        el = self.device(descriptionContains="Next")
        if el.exists(timeout=3):
            el.click()
            time.sleep(2)
            return True

        # Method 3: Resource ID
        for rid in ['next_button', 'next_button_textview',
                     'action_bar_button_action']:
            el = self.device(resourceIdMatches=f".*{rid}.*")
            if el.exists(timeout=2):
                el.click()
                time.sleep(2)
                log.debug("[%s] CONTENT: Tapped Next via rid='%s'",
                          self.device_serial, rid)
                return True

        # Method 4: Top-right corner (Next is typically there)
        xml = self.ctrl.dump_xml("find_next_btn")
        next_match = re.search(
            r'<node[^>]*(?:text="Next"|content-desc="[^"]*[Nn]ext[^"]*")[^>]*'
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            xml)
        if next_match:
            x1, y1, x2, y2 = [int(v) for v in next_match.groups()]
            self.device.click((x1 + x2) // 2, (y1 + y2) // 2)
            time.sleep(2)
            return True

        # Method 5: Right arrow / chevron icon in the action bar area
        w, h = self.device.window_size()
        right_arrow = self.device(descriptionContains="arrow")
        if right_arrow.exists(timeout=2):
            right_arrow.click()
            time.sleep(2)
            return True

        log.debug("[%s] CONTENT: Next button not found", self.device_serial)
        return False

    def _enter_caption(self, caption_text):
        """
        Enter caption text in the caption field.

        The caption field typically has resource-id containing "caption"
        and is an EditText element.
        """
        adb_serial = self.device_serial.replace('_', ':')

        # Method 1: Resource ID based
        for rid in ['caption_text_view', 'caption_edit_text', 'caption_input',
                     'caption_text', 'write_a_caption']:
            el = self.device(resourceIdMatches=f".*{rid}.*")
            if el.exists(timeout=3):
                el.click()
                time.sleep(1)
                try:
                    el.set_text(caption_text)
                    time.sleep(1)
                    log.debug("[%s] CONTENT: Entered caption via rid='%s'",
                              self.device_serial, rid)
                    return True
                except Exception:
                    pass  # Fall through to ADB input

        # Method 2: Text hint "Write a caption..."
        for hint in ["Write a caption", "Add a caption", "Caption"]:
            el = self.device(textContains=hint)
            if el.exists(timeout=3):
                el.click()
                time.sleep(1)
                break

        # Method 3: Find any EditText on the caption screen
        edit = self.device(className="android.widget.EditText")
        if edit.exists(timeout=3):
            edit.click()
            time.sleep(0.5)
            try:
                edit.set_text(caption_text)
                time.sleep(1)
                log.debug("[%s] CONTENT: Entered caption via EditText",
                          self.device_serial)
                return True
            except Exception:
                pass

        # Method 4: ADB input (most reliable for complex text)
        # First ensure a text field is focused
        time.sleep(0.5)
        try:
            # ADB shell input doesn't handle newlines well;
            # replace newlines with spaces for ADB
            safe_text = caption_text.replace('\n', ' ').replace("'", "\\'")
            # Escape special shell characters
            safe_text = safe_text.replace(' ', '%s').replace('&', '\\&')
            subprocess.run(
                ['adb', '-s', adb_serial, 'shell', 'input', 'text', safe_text],
                capture_output=True, timeout=30)
            time.sleep(1)
            log.debug("[%s] CONTENT: Entered caption via ADB input",
                      self.device_serial)
            return True
        except Exception as e:
            log.warning("[%s] CONTENT: Failed to enter caption: %s",
                        self.device_serial, e)
            return False

    def _add_location(self, location_name):
        """
        Add a location tag to the post.

        Flow: Tap "Add location" → search for location → select first result.
        """
        # Find "Add location" option
        for text in ["Add location", "Add Location", "Location"]:
            el = self.device(textContains=text)
            if el.exists(timeout=3):
                el.click()
                time.sleep(2)
                break
        else:
            # Try resource ID
            el = self.device(resourceIdMatches=".*add_location.*|.*location_button.*")
            if el.exists(timeout=2):
                el.click()
                time.sleep(2)
            else:
                log.debug("[%s] CONTENT: Add location button not found",
                          self.device_serial)
                return False

        # Search for location
        search_bar = self.device(className="android.widget.EditText")
        if search_bar.exists(timeout=3):
            search_bar.click()
            time.sleep(0.5)
            adb_serial = self.device_serial.replace('_', ':')
            subprocess.run(
                ['adb', '-s', adb_serial, 'shell', 'input', 'text',
                 location_name.replace(' ', '%s')],
                capture_output=True, timeout=10)
            time.sleep(3)

            # Select first search result
            # Location results appear as list items — tap the first one
            xml = self.ctrl.dump_xml("location_results")
            # Look for location result rows
            for rid in ['place_result', 'search_result_row', 'location_item']:
                result_el = self.device(resourceIdMatches=f".*{rid}.*")
                if result_el.exists(timeout=3):
                    result_el[0].click()
                    time.sleep(2)
                    log.debug("[%s] CONTENT: Selected location '%s'",
                              self.device_serial, location_name)
                    return True

            # Fallback: tap first item below search bar
            w, h = self.device.window_size()
            self.device.click(w // 2, int(h * 0.3))
            time.sleep(2)
            return True

        return False

    def _add_reel_music(self, search_query):
        """
        Add music to a reel.

        Flow: Tap "Music" / audio button → search → select first result.
        """
        # Find music/audio button in reel editor
        for desc in ["Music", "Audio", "Add music", "Add audio"]:
            el = self.device(descriptionContains=desc)
            if el.exists(timeout=3):
                el.click()
                time.sleep(3)
                log.debug("[%s] CONTENT: Tapped music button via desc='%s'",
                          self.device_serial, desc)
                break
        else:
            for text in ["Music", "Audio", "♪"]:
                el = self.device(textContains=text)
                if el.exists(timeout=2):
                    el.click()
                    time.sleep(3)
                    break
            else:
                log.debug("[%s] CONTENT: Music button not found in reel editor",
                          self.device_serial)
                return False

        # Search for the track
        search_bar = self.device(className="android.widget.EditText")
        if search_bar.exists(timeout=3):
            search_bar.click()
            time.sleep(0.5)
            adb_serial = self.device_serial.replace('_', ':')
            subprocess.run(
                ['adb', '-s', adb_serial, 'shell', 'input', 'text',
                 search_query.replace(' ', '%s')],
                capture_output=True, timeout=10)
            time.sleep(3)

            # Select first music result
            # Music results are typically in a scrollable list
            xml = self.ctrl.dump_xml("music_results")

            # Look for music result items
            for rid in ['music_row', 'audio_row', 'track_row', 'music_result']:
                result_el = self.device(resourceIdMatches=f".*{rid}.*")
                if result_el.exists(timeout=3):
                    result_el[0].click()
                    time.sleep(2)
                    log.debug("[%s] CONTENT: Selected music '%s'",
                              self.device_serial, search_query)
                    # Confirm / Done
                    done = self.device(text="Done")
                    if done.exists(timeout=3):
                        done.click()
                        time.sleep(2)
                    return True

            # Fallback: tap the first list item below search
            w, h = self.device.window_size()
            self.device.click(w // 2, int(h * 0.35))
            time.sleep(2)
            # Confirm
            done = self.device(text="Done")
            if done.exists(timeout=3):
                done.click()
                time.sleep(2)
            return True

        return False

    def _add_mention_sticker(self, mention_username):
        """
        Add a @mention sticker in the story editor.

        Reuses patterns from share_to_story.py's _add_story_mention().
        Flow: Tap sticker button → tap Mention sticker → type username → confirm.
        """
        log.info("[%s] CONTENT: Adding mention @%s to story",
                 self.device_serial, mention_username)

        # Tap sticker icon
        sticker_found = False
        for selector in [
            self.device(resourceIdMatches=".*asset_button.*"),
            self.device(description="Emojis and stickers"),
            self.device(descriptionContains="sticker"),
        ]:
            if selector.exists(timeout=3):
                selector.click()
                time.sleep(3)
                sticker_found = True
                log.debug("[%s] CONTENT: Tapped sticker button", self.device_serial)
                break

        if not sticker_found:
            log.warning("[%s] CONTENT: Sticker button not found", self.device_serial)
            return False

        # Find and tap "Mention Sticker"
        mention_sticker = self.device(description="Mention Sticker")
        if not mention_sticker.exists(timeout=3):
            mention_sticker = self.device(descriptionContains="Mention")
        if not mention_sticker.exists(timeout=3):
            # Search for it
            search = self.device(className="android.widget.EditText")
            if search.exists(timeout=2):
                search.click()
                time.sleep(0.5)
                search.set_text("Mention")
                time.sleep(2)
                mention_sticker = self.device(descriptionContains="Mention")

        if mention_sticker.exists(timeout=3):
            mention_sticker.click()
            time.sleep(2)
        else:
            log.warning("[%s] CONTENT: Mention sticker not found", self.device_serial)
            self.ctrl.press_back()
            return False

        # Type the username in the mention search
        edit = self.device(className="android.widget.EditText")
        if edit.exists(timeout=3):
            edit.click()
            time.sleep(0.5)
            adb_serial = self.device_serial.replace('_', ':')
            # Remove @ prefix if present
            clean_username = mention_username.lstrip('@')
            subprocess.run(
                ['adb', '-s', adb_serial, 'shell', 'input', 'text', clean_username],
                capture_output=True, timeout=10)
            time.sleep(3)

            # Select the first result
            result = self.device(textContains=clean_username)
            if result.exists(timeout=3):
                result.click()
                time.sleep(2)
                log.info("[%s] CONTENT: Mention @%s added to story",
                         self.device_serial, clean_username)
                return True

            # Fallback: tap first result area
            w, h = self.device.window_size()
            self.device.click(w // 2, int(h * 0.35))
            time.sleep(2)
            return True

        self.ctrl.press_back()
        return False

    def _add_link_sticker(self, url):
        """
        Add a link sticker in the story editor.

        Reuses patterns from share_to_story.py's _add_link_sticker().
        Flow: Tap sticker button → tap Link sticker → enter URL → Done.
        """
        log.info("[%s] CONTENT: Adding link sticker: %s",
                 self.device_serial, url[:50])

        # Tap sticker icon
        sticker_found = False
        for selector in [
            self.device(resourceIdMatches=".*asset_button.*"),
            self.device(description="Emojis and stickers"),
            self.device(descriptionContains="sticker"),
        ]:
            if selector.exists(timeout=3):
                selector.click()
                time.sleep(3)
                sticker_found = True
                break

        if not sticker_found:
            log.warning("[%s] CONTENT: Sticker button not found for link",
                        self.device_serial)
            return False

        # Find and tap "Link Sticker"
        link_sticker = self.device(description="Link Sticker")
        if not link_sticker.exists(timeout=3):
            link_sticker = self.device(descriptionContains="Link")

        if not link_sticker.exists(timeout=3):
            # Search for it
            search = self.device(className="android.widget.EditText")
            if search.exists(timeout=2):
                search.click()
                time.sleep(0.5)
                search.set_text("Link")
                time.sleep(2)
                link_sticker = self.device(descriptionContains="Link")

        if link_sticker.exists(timeout=3):
            link_sticker.click()
            time.sleep(2)
        else:
            log.warning("[%s] CONTENT: Link sticker not found", self.device_serial)
            self.ctrl.press_back()
            return False

        # Enter URL
        url_field = self.device(className="android.widget.EditText")
        if url_field.exists(timeout=3):
            url_field.click()
            time.sleep(0.5)
            url_field.set_text(url)
            time.sleep(1)

            # Confirm
            for text in ["Done", "OK", "Add"]:
                done = self.device(text=text)
                if done.exists(timeout=2):
                    done.click()
                    time.sleep(2)
                    log.info("[%s] CONTENT: Link sticker added: %s",
                             self.device_serial, url[:50])
                    return True

        self.ctrl.press_back()
        return False

    def _tap_share(self):
        """
        Tap the "Share" / "Post" button to publish content.

        Returns True if tapped.
        """
        # Method 1: Text-based
        for text in ["Share", "Post", "SHARE", "POST", "Publish"]:
            el = self.device(text=text)
            if el.exists(timeout=5):
                el.click()
                time.sleep(3)
                log.debug("[%s] CONTENT: Tapped share via text='%s'",
                          self.device_serial, text)
                return True

        # Method 2: Content description
        for desc in ["Share", "Post", "Publish"]:
            el = self.device(description=desc)
            if el.exists(timeout=3):
                el.click()
                time.sleep(3)
                return True

        # Method 3: Resource ID
        for rid in ['share_button', 'post_button', 'action_bar_button_action',
                     'next_button_textview']:
            el = self.device(resourceIdMatches=f".*{rid}.*")
            if el.exists(timeout=2):
                el.click()
                time.sleep(3)
                log.debug("[%s] CONTENT: Tapped share via rid='%s'",
                          self.device_serial, rid)
                return True

        # Method 4: XML bounds search
        xml = self.ctrl.dump_xml("find_share_btn")
        share_match = re.search(
            r'<node[^>]*(?:text="(?:Share|Post)"|'
            r'content-desc="(?:Share|Post)")[^>]*'
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            xml)
        if share_match:
            x1, y1, x2, y2 = [int(v) for v in share_match.groups()]
            self.device.click((x1 + x2) // 2, (y1 + y2) // 2)
            time.sleep(3)
            return True

        log.warning("[%s] CONTENT: Share/Post button not found", self.device_serial)
        return False

    def _tap_story_share(self):
        """
        Tap the "Share to Story" / "Your Story" button to publish a story.

        Returns True if tapped.
        """
        # Patterns from share_to_story.py _publish_story()
        publish_patterns = [
            ("description", "Your story"),
            ("text", "Your story"),
            ("description", "Share to"),
            ("text", "Share"),
            ("text", "Done"),
            ("text", "Post"),
            ("description", "Share"),
            ("description", "Share to your story"),
        ]

        for attr, pattern in publish_patterns:
            if attr == "text":
                el = self.device(text=pattern)
            else:
                el = self.device(description=pattern)
            if el.exists(timeout=3):
                el.click()
                time.sleep(3)
                log.debug("[%s] CONTENT: Published story via %s='%s'",
                          self.device_serial, attr, pattern)
                return True

        # Resource ID fallback
        for rid in ['share_story_button', 'done_button', 'share_button']:
            el = self.device(resourceIdMatches=f".*{rid}.*")
            if el.exists(timeout=2):
                el.click()
                time.sleep(3)
                return True

        log.warning("[%s] CONTENT: Story share button not found",
                    self.device_serial)
        return False

    def _wait_for_upload_complete(self, timeout=60):
        """
        Wait for the post/reel upload to complete.

        After tapping Share, IG typically:
        - Shows a progress bar / "Sharing..." toast
        - Returns to the feed when done
        - May show "Your post has been shared" notification

        Returns True if upload appears successful.
        """
        log.debug("[%s] CONTENT: Waiting for upload (timeout=%ds)...",
                  self.device_serial, timeout)

        start = time.time()
        while time.time() - start < timeout:
            time.sleep(3)

            xml = self.ctrl.dump_xml("upload_check")
            screen = self.ctrl.detect_screen(xml)

            # If we're back on home feed → upload complete
            if screen == Screen.HOME_FEED:
                log.debug("[%s] CONTENT: Back on home feed — upload complete",
                          self.device_serial)
                return True

            # If we're back on profile → upload complete (some IG versions)
            if screen == Screen.PROFILE:
                log.debug("[%s] CONTENT: Back on profile — upload complete",
                          self.device_serial)
                return True

            # Check for "shared" confirmation text
            for confirm_text in ["has been shared", "shared", "posted",
                                 "Your reel", "Uploading"]:
                if confirm_text.lower() in xml.lower():
                    if 'uploading' in confirm_text.lower():
                        log.debug("[%s] CONTENT: Upload in progress...",
                                  self.device_serial)
                        continue
                    log.debug("[%s] CONTENT: Found confirmation text '%s'",
                              self.device_serial, confirm_text)
                    return True

            # Check for error states (use specific phrases to avoid false positives)
            for error_text in ["couldn't share", "couldn't post", "failed to upload",
                               "try again", "something went wrong", "unable to share"]:
                if error_text.lower() in xml.lower():
                    log.warning("[%s] CONTENT: Upload error detected: '%s'",
                                self.device_serial, error_text)
                    return False

        log.warning("[%s] CONTENT: Upload timeout after %ds",
                    self.device_serial, timeout)
        # If we timed out but are on a normal screen, assume success
        screen = self.ctrl.detect_screen()
        return screen in (Screen.HOME_FEED, Screen.PROFILE)

    # ------------------------------------------------------------------
    # Navigation / Recovery Helpers
    # ------------------------------------------------------------------

    def _go_back(self, times=3):
        """Press back multiple times to return to a clean state."""
        for _ in range(times):
            self.ctrl.press_back()
            time.sleep(1)
        try:
            self.ctrl.dismiss_popups()
        except Exception:
            pass

    def _recover(self):
        """Try to recover to home feed."""
        try:
            self._go_back(3)
            self.ctrl.navigate_to(Screen.HOME_FEED)
        except Exception:
            pass


def execute_post_content(device, device_serial, account_info, session_id,
                         schedule_item):
    """Convenience function to post scheduled content."""
    action = PostContentAction(device, device_serial, account_info,
                               session_id, schedule_item)
    return action.execute()
