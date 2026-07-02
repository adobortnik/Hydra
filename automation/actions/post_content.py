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
        self.package = pkg
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

            # Push media to device FIRST (before opening IG)
            self._remote_media_path = self._push_media_to_device(self.media_path)
            if not self._remote_media_path:
                raise RuntimeError("Failed to push media to device")

            log.info("[%s] CONTENT: Pushed media to %s",
                     self.device_serial, self._remote_media_path)

            # NOW open IG and start the flow.
            # ensure_app() can FAIL — IG clones sometimes refuse to launch on
            # first try. Bail out early instead of running the rest of the flow
            # on a launcher screen where every selector silently fails.
            self._stop_other_ig_clones()
            if not self.ctrl.ensure_app():
                raise RuntimeError(
                    f"Failed to launch IG clone {self.package} — aborting before "
                    f"the rest of the flow runs on the wrong app. Check that the "
                    f"package is installed and that app_start works.")
            self.ctrl.dismiss_popups()
            self.ctrl.navigate_to(Screen.HOME_FEED)
            time.sleep(2)

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
    # Video Duration Helper
    # ------------------------------------------------------------------

    @staticmethod
    def _get_video_duration_ms(filepath):
        """Read video duration from MP4 moov/mvhd atom. No external deps."""
        import struct
        try:
            with open(filepath, 'rb') as f:
                while True:
                    header = f.read(8)
                    if len(header) < 8:
                        break
                    size = struct.unpack('>I', header[:4])[0]
                    atom_type = header[4:8]
                    if size == 0:
                        break
                    if atom_type == b'moov':
                        # Recurse into moov
                        continue
                    if atom_type == b'mvhd':
                        # mvhd: version(1) + flags(3) + create(4) + modify(4) + timescale(4) + duration(4)
                        data = f.read(min(size - 8, 100))
                        version = data[0]
                        if version == 0:
                            timescale = struct.unpack('>I', data[12:16])[0]
                            duration = struct.unpack('>I', data[16:20])[0]
                        else:
                            timescale = struct.unpack('>I', data[20:24])[0]
                            duration = struct.unpack('>Q', data[24:32])[0]
                        if timescale > 0:
                            return int((duration / timescale) * 1000)
                        return None
                    # Skip to next atom
                    f.seek(size - 8, 1)
        except Exception as e:
            log.debug("Could not read video duration from %s: %s", filepath, e)
        return None

    # ------------------------------------------------------------------
    # Clone Isolation
    # ------------------------------------------------------------------

    # All known IG clone packages
    _IG_CLONE_PACKAGES = [f"com.instagram.androi{c}" for c in "efghijklmnop"]

    def _stop_other_ig_clones(self):
        """Force-stop all IG clone packages except the one we're using."""
        adb_serial = self.device_serial.replace('_', ':')
        stopped = []
        for pkg in self._IG_CLONE_PACKAGES:
            if pkg == self.package:
                continue
            try:
                subprocess.run(
                    ['adb', '-s', adb_serial, 'shell', 'am', 'force-stop', pkg],
                    capture_output=True, timeout=5)
                stopped.append(pkg)
            except Exception:
                pass
        if stopped:
            log.info("[%s] CONTENT: Stopped %d other IG clones before posting",
                     self.device_serial, len(stopped))

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

        # Use MediaProvider's scan_file method — the proper API on Android 10+.
        # This triggers MediaScannerConnection.scanFile() internally and extracts
        # all metadata (duration, resolution, etc.) from the actual file.
        # No manual content insert or deprecated broadcasts needed.
        scan_result = subprocess.run(
            ['adb', '-s', adb_serial, 'shell',
             'content', 'call', '--uri', 'content://media',
             '--method', 'scan_file',
             '--arg', real_remote_path],
            capture_output=True, text=True, timeout=20)

        if scan_result.returncode == 0 and 'content://' in scan_result.stdout:
            log.info("[%s] CONTENT: Scanned %s → %s",
                     self.device_serial, filename,
                     scan_result.stdout.strip()[:100])
        else:
            log.warning("[%s] CONTENT: scan_file returned: %s",
                        self.device_serial,
                        (scan_result.stdout + scan_result.stderr)[:200])
            # Fallback: deprecated broadcast (better than nothing)
            subprocess.run(
                ['adb', '-s', adb_serial, 'shell',
                 'am', 'broadcast', '-a',
                 'android.intent.action.MEDIA_SCANNER_SCAN_FILE',
                 '-d', f'file://{remote_path}'],
                capture_output=True, timeout=10)

        # Brief pause for gallery to refresh
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

    _reel_retry_count = 0

    def _post_reel_retry(self):
        """One-shot retry of _post_reel after Recents recovery."""
        self._reel_retry_count += 1
        if self._reel_retry_count > 1:
            log.warning("[%s] CONTENT: Reel retry limit reached",
                        self.device_serial)
            return False
        log.info("[%s] CONTENT: Retrying reel post (attempt %d)",
                 self.device_serial, self._reel_retry_count + 1)
        self.ctrl.navigate_to(Screen.HOME_FEED)
        time.sleep(2)
        return self._post_reel()

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

        # Safety check: if we accidentally hit the Recents button (nav bar),
        # the app switcher appears. Detect and recover.
        try:
            xml = self.ctrl.dump_xml("check_recents")
            if 'com.android.launcher' in xml or 'RecentTask' in xml or 'recents_view' in xml:
                log.warning("[%s] CONTENT: Detected app switcher / Recents! "
                            "Pressing Home and re-opening IG",
                            self.device_serial)
                self.device.press('home')
                time.sleep(1)
                self.ctrl.ensure_app()
                time.sleep(2)
                # At this point we lost the reel creation flow — retry from the top
                return self._post_reel_retry()
        except Exception as e:
            log.debug("[%s] CONTENT: Recents check error (non-fatal): %s",
                      self.device_serial, e)

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
        # Proactive: clear any forced sub-screen (e.g. cover picker on new accts)
        self._recover_unexpected_reel_screen()
        if not self._tap_next():
            log.debug("[%s] CONTENT: No Next on reel editor — may already be on caption",
                      self.device_serial)

        random_sleep(1.5, 3, label="reel_caption_loading")

        # Step 7: Enter caption
        if self.full_caption:
            self._enter_caption(self.full_caption)
            # Dismiss keyboard so Next/Share button is visible
            self.device.press('back')
            random_sleep(1, 2, label="after_caption_dismiss_keyboard")

        # Step 8: Tap "Next" on caption screen (goes to final confirmation)
        # Some IG versions go directly to Share, others show "Next" first.
        # Recover first so we're really on caption, not a sub-screen.
        self._recover_unexpected_reel_screen()
        next_on_caption = self._tap_next()
        if next_on_caption:
            random_sleep(1.5, 3, label="reel_final_confirmation")

        # Step 9: Handle "About Reels" modal if it appears
        # If modal found, its Share button IS the final share — skip _tap_share
        modal_shared = self._dismiss_about_reels_modal()

        # Step 10: Tap "Share" (only if modal didn't already share). Last
        # recovery before share — for new creators IG sometimes opens
        # "Sharing preferences" right before share, blocking the button.
        if not modal_shared:
            self._recover_unexpected_reel_screen()
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

        random_sleep(2, 4, label="add_to_story_gallery_loading")

        # Step 2: Select media from the "Add to story" gallery grid
        # (we're already on the gallery screen — no need to open camera first)
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

    def _dismiss_album_picker(self):
        """Dismiss album picker bottom sheet if it's showing."""
        # Check for "Select album" title or album filter tabs
        album_title = self.device(resourceIdMatches=".*title_text_view.*",
                                   textContains="Select album")
        if album_title.exists(timeout=2):
            log.debug("[%s] CONTENT: Album picker bottom sheet detected, dismissing",
                      self.device_serial)
            # Press back to dismiss the bottom sheet
            self.device.press('back')
            time.sleep(1)
            return True

        # Also check for album_filter_title which appears in the album picker
        album_filter = self.device(resourceIdMatches=".*album_filter_title.*")
        if album_filter.exists(timeout=1):
            log.debug("[%s] CONTENT: Album filter detected, pressing back",
                      self.device_serial)
            self.device.press('back')
            time.sleep(1)
            return True

        # Also handle context_menu dropdown (older IG versions)
        ctx_menu = self.device(resourceIdMatches=".*context_menu_item_label.*",
                               text="Recents")
        if ctx_menu.exists(timeout=1):
            ctx_menu.click()
            time.sleep(2)
            log.debug("[%s] CONTENT: Selected 'Recents' from album dropdown",
                      self.device_serial)
            return True

        return False

    def _select_media_from_gallery(self):
        """
        Select the pushed media file from the gallery view.

        The gallery typically shows recent items first. Since we just pushed
        the file and triggered a media scan, it should appear as the most
        recent item (top-left in grid).

        Returns True if media was selected.
        """
        # Step 0: Dismiss album picker bottom sheet if it appeared
        # Some IG versions show "Select album" sheet on entering reel gallery
        self._dismiss_album_picker()

        # Step 1: Try clicking the first gallery grid thumbnail (resource-id based)
        # IG clone uses 'gallery_grid_item_thumbnail' (View class, not ImageView)
        for rid in ['gallery_grid_item_thumbnail', 'gallery_grid_item_image',
                     'media_thumbnail', 'gallery_image_view']:
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

        # Step 2: XML-based fallback — find any clickable View/ImageView thumbnails
        xml = self.ctrl.dump_xml("gallery_select")
        screen_w, screen_h = self.device.window_size()
        nav_bar_y = int(screen_h * 0.92)

        # Match both ImageView and View (IG clones use android.view.View)
        thumb_pattern = (
            r'<node[^>]*class="android\.(?:widget\.ImageView|view\.View)"[^>]*'
            r'clickable="true"[^>]*'
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
        )
        thumbs = re.findall(thumb_pattern, xml)

        if thumbs:
            for t in thumbs:
                x1, y1, x2, y2 = [int(v) for v in t]
                w = x2 - x1
                h = y2 - y1
                cy = (y1 + y2) // 2
                # Gallery thumbnails are typically square-ish and >100px
                if w > 100 and h > 100 and cy < nav_bar_y:
                    self.device.click((x1 + x2) // 2, cy)
                    time.sleep(2)
                    log.debug("[%s] CONTENT: Selected media via thumbnail at (%d,%d)",
                              self.device_serial, (x1+x2)//2, cy)
                    return True

        # Step 3: Fallback — tap estimated gallery grid position
        self.device.click(int(screen_w * 0.16), int(screen_h * 0.5))
        time.sleep(2)
        log.debug("[%s] CONTENT: Tapped gallery grid area as fallback",
                  self.device_serial)
        return True

    def _select_media_in_story_mode(self):
        """
        Select media from the "Add to story" gallery grid.

        We're already on the "Add to story" screen which shows a 3-column grid:
          - First cell: Camera tile (camera icon + "Camera" text)
          - Remaining cells: media thumbnails (most recent first)

        Our pushed media will be the first thumbnail (second cell in grid).
        We need to skip the Camera cell and tap the first actual media thumbnail.

        Returns True if media was selected.
        """
        random_sleep(1, 2, label="story_gallery_loaded")

        w, h = self.device.window_size()

        # --- Strategy 1: XML-based — find clickable thumbnails, skip Camera ---
        xml = self.ctrl.dump_xml("story_gallery_grid")

        # Find the "Open camera" button to know where Camera cell is (skip it)
        camera_bounds = None
        # Method A: desc="Open camera" button
        camera_match = re.search(
            r'<node[^>]*content-desc="Open camera"[^>]*'
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            xml
        )
        # Method B: text="Camera" element
        if not camera_match:
            camera_match = re.search(
                r'<node[^>]*text="Camera"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                xml
            )
        # Method C: gallery_grid_camera_item_icon resource-id
        if not camera_match:
            camera_match = re.search(
                r'<node[^>]*resource-id="[^"]*gallery_grid_camera[^"]*"[^>]*'
                r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                xml
            )
        if camera_match:
            camera_bounds = tuple(int(v) for v in camera_match.groups())
            log.debug("[%s] CONTENT: Found Camera cell at bounds %s",
                      self.device_serial, camera_bounds)

        # Find grid top boundary — grid starts BELOW Recents / multi-select row
        # Use camera top y as reference (grid cells are at same level as Camera)
        if camera_bounds:
            grid_top_y = camera_bounds[1]  # Camera top y = grid top
            log.debug("[%s] CONTENT: Grid top y from Camera bounds: %d",
                      self.device_serial, grid_top_y)
        else:
            # Fallback: find Recents text
            grid_top_y = int(h * 0.38)  # conservative default
            recents_match = re.search(
                r'<node[^>]*text="Recents"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                xml
            )
            if recents_match:
                grid_top_y = int(recents_match.group(4))  # bottom of "Recents" text
                log.debug("[%s] CONTENT: Recents text bottom at y=%d",
                          self.device_serial, grid_top_y)

        # Collect all clickable elements in the grid area
        # Grid cells are ViewGroup (clickable), NOT ImageView
        thumb_pattern = (
            r'<node[^>]*class="android\.widget\.ViewGroup"[^>]*'
            r'clickable="true"[^>]*'
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
        )
        thumbs = re.findall(thumb_pattern, xml)

        # Also try Button and other clickable types
        if len(thumbs) < 2:
            thumb_pattern_generic = (
                r'<node[^>]*'
                r'clickable="true"[^>]*'
                r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
            )
            thumbs = re.findall(thumb_pattern_generic, xml)

        # Filter: only items in the grid area (below Recents) and big enough to be thumbnails
        # Grid cells are roughly 350x625px on 1080px screens — require at least 150px
        min_thumb_size = 150
        grid_items = []
        for t in thumbs:
            x1, y1, x2, y2 = [int(v) for v in t]
            item_w = x2 - x1
            item_h = y2 - y1
            if item_w > min_thumb_size and item_h > min_thumb_size and y1 >= grid_top_y:
                # Skip if this overlaps with the Camera cell OR has camera desc
                if camera_bounds:
                    cam_x1, cam_y1, cam_x2, cam_y2 = camera_bounds
                    cx = (x1 + x2) // 2
                    cy = (y1 + y2) // 2
                    if cam_x1 <= cx <= cam_x2 and cam_y1 <= cy <= cam_y2:
                        log.debug("[%s] CONTENT: Skipping Camera cell at [%d,%d][%d,%d]",
                                  self.device_serial, x1, y1, x2, y2)
                        continue
                # Also skip by checking if this node has "camera" in its desc
                # (look at nearby XML context for "Open camera" or "Camera" desc)
                node_context = xml[max(0, xml.find(f'[{x1},{y1}][{x2},{y2}]') - 200):
                                   xml.find(f'[{x1},{y1}][{x2},{y2}]') + 50]
                if 'camera' in node_context.lower() or 'Open camera' in node_context:
                    log.debug("[%s] CONTENT: Skipping camera-related element at [%d,%d][%d,%d]",
                              self.device_serial, x1, y1, x2, y2)
                    continue
                grid_items.append((x1, y1, x2, y2))

        # Sort by position: top-to-bottom, then left-to-right
        grid_items.sort(key=lambda b: (b[1], b[0]))

        if grid_items:
            # Tap the first non-Camera thumbnail
            x1, y1, x2, y2 = grid_items[0]
            tap_x = (x1 + x2) // 2
            tap_y = (y1 + y2) // 2
            self.device.click(tap_x, tap_y)
            log.info("[%s] CONTENT: Tapped first media thumbnail at (%d, %d)",
                     self.device_serial, tap_x, tap_y)
            time.sleep(3)
            return True

        # --- Strategy 2: Coordinate-based fallback ---
        # The grid is 3 columns. Camera is top-left (col 1).
        # First media thumbnail is the SECOND cell (col 2, first row).
        # Column width ≈ w/3, so second cell center is at x ≈ w*0.5
        # Grid starts roughly 35% down the screen
        log.debug("[%s] CONTENT: XML strategy found no thumbnails, using coordinate fallback",
                  self.device_serial)

        # Try to find any clickable element via resource-id first
        for rid in ['gallery_grid_item_image', 'media_thumbnail',
                     'gallery_image_view', 'thumbnail']:
            grid_item = self.device(resourceIdMatches=f".*{rid}.*")
            if grid_item.exists(timeout=2):
                try:
                    # Skip first if it might be Camera
                    count = grid_item.count
                    idx = 1 if count > 1 else 0
                    grid_item[idx].click()
                    time.sleep(3)
                    log.info("[%s] CONTENT: Selected media for story via rid='%s' idx=%d",
                             self.device_serial, rid, idx)
                    return True
                except Exception:
                    continue

        # Pure coordinate fallback: tap second column, first grid row
        tap_x = int(w * 0.5)
        tap_y = int(h * 0.42)
        log.info("[%s] CONTENT: Tapping coordinate fallback (%d, %d) for second grid cell",
                 self.device_serial, tap_x, tap_y)
        self.device.click(tap_x, tap_y)
        time.sleep(3)
        return True

    def _tap_story_create(self):
        """
        Tap the story creation entry point from home screen.
        This is the "Your story" / "+" circle at top-left of the stories tray.

        The clickable Button has content-desc like:
          "robin.rieff_prime's story, 0 of 16, Unseen."
        The text label "Your story" is on a non-clickable TextView below.

        Returns True if tapped.
        """
        # Method 1: Content description — IG clone uses "{username}\u2019s story, 0 of N"
        # "0 of N" = first story slot = user's own story
        # Note: IG uses RIGHT SINGLE QUOTE, so use descriptionContains (not regex)
        el = self.device(descriptionContains="story, 0 of")
        if el.exists(timeout=5):
            el.click()
            time.sleep(4)
            log.debug("[%s] CONTENT: Tapped story create via descContains 'story, 0 of'",
                      self.device_serial)
            return True

        # Method 2: Classic "Your story" / "Add to story" descriptions
        for desc in ["Your story", "Add to story", "Create story",
                      "Your Story"]:
            el = self.device(descriptionContains=desc)
            if el.exists(timeout=3):
                el.click()
                time.sleep(3)
                log.debug("[%s] CONTENT: Tapped story create via desc='%s'",
                          self.device_serial, desc)
                return True

        # Method 3: Resource ID for story ring / create button
        for rid in ['reel_viewer_subtitle', 'story_ring', 'your_story']:
            el = self.device(resourceIdMatches=f".*{rid}.*")
            if el.exists(timeout=2):
                el.click()
                time.sleep(3)
                return True

        # Method 4: "Your story" text label (tap the parent or nearby area)
        el = self.device(text="Your story")
        if el.exists(timeout=3):
            # Get the bounds and tap slightly above (on the story ring, not the text)
            try:
                info = el.info
                bounds = info.get('bounds', {})
                center_x = (bounds.get('left', 0) + bounds.get('right', 0)) // 2
                above_y = bounds.get('top', 0) - 50  # Tap above the text (on the ring)
                if above_y > 0:
                    self.device.click(center_x, above_y)
                    time.sleep(3)
                    log.debug("[%s] CONTENT: Tapped above 'Your story' text at (%d, %d)",
                              self.device_serial, center_x, above_y)
                    return True
            except Exception:
                pass
            el.click()
            time.sleep(3)
            log.debug("[%s] CONTENT: Tapped story create via text='Your story'",
                      self.device_serial)
            return True

        # Method 5: XML search for first story button in the stories tray
        xml = self.ctrl.dump_xml("story_create_xml")
        # Match "story, 0 of N" pattern (user's own story is always index 0)
        story_btn = re.search(
            r'<node[^>]*content-desc="[^"]*story, 0 of \d+[^"]*"[^>]*'
            r'clickable="true"[^>]*'
            r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
            xml
        )
        if story_btn:
            x1, y1, x2, y2 = [int(v) for v in story_btn.groups()]
            self.device.click((x1 + x2) // 2, (y1 + y2) // 2)
            time.sleep(3)
            log.debug("[%s] CONTENT: Tapped story create via XML bounds",
                      self.device_serial)
            return True

        # Method 6: Coordinate fallback — stories tray is below header
        w, h = self.device.window_size()
        self.device.click(int(w * 0.10), int(h * 0.17))
        time.sleep(3)

        xml = self.ctrl.dump_xml("story_create_check")
        if ('add to story' in xml.lower() or 'camera' in xml.lower() or
                'shutter' in xml.lower() or 'gallery' in xml.lower() or
                'recents' in xml.lower()):
            return True

        return False

    def _recover_unexpected_reel_screen(self, max_back=3):
        """
        Detect & escape unexpected sub-screens during reel creation.

        IG opens sub-screens that block our expected flow:
          - "Sharing preferences" (forced onboarding for new accounts —
            shows "How others can interact with your reel" + "Tag products"
            + "Upload at highest quality" toggles)
          - "Tag products" picker
          - "Search audio" / music picker (when not requested by us)
          - "Cover" picker
          - "Add link" sub-screen
          - "Save draft?" / "Discard reel?" dialogs

        For all of them the universal escape = press BACK (or for dialogs:
        find the "Don't save" / "Keep editing" / "Cancel" choice). Returns
        True if we recovered (no longer on a sub-screen), False if stuck
        after `max_back` attempts.

        Safe to call any time — if we're already on an expected screen
        (caption / preview / gallery) it returns True immediately without
        pressing anything.
        """
        # Known sub-screen patterns. Each entry: (xml-needle, label, escape-action)
        #   escape-action:
        #     'back'              → system back is enough
        #     'tap:<button text>' → find element textContains=<button text>, click
        SUBSCREEN_MARKERS = [
            # Sharing prefs / advanced settings — first-time creator onboarding
            ("Sharing preferences",                    "sharing_prefs",   "back"),
            ("How others can interact with your reel", "sharing_prefs",   "back"),
            ("Templates allow anyone on Instagram",    "sharing_prefs",   "back"),
            ("Upload at highest quality",              "sharing_prefs",   "back"),
            # Tag products picker
            ("Add products",                           "tag_products",    "back"),
            # Music / audio picker when we didn't ask for it
            ("Search audio",                           "music_picker",    "back"),
            ("Browse music",                           "music_picker",    "back"),
            # Cover frame picker
            ("Cover frame",                            "cover_picker",    "back"),
            ("Choose cover",                           "cover_picker",    "back"),
            # Interactive sticker pickers
            ("Add a poll",                             "interactive_picker", "back"),
            # IG promo / feature-announcement screens (don't go BACK — they
            # take you OUT of the creation flow; tap the dismiss button)
            ("Create a sticker",                       "sticker_promo",   "tap:Not now"),
            ("Turn part of any photo into a sticker",  "sticker_promo",   "tap:Not now"),
            ("Add music to your reel",                 "music_promo",     "tap:Not now"),
            ("Welcome to reels",                       "reels_intro",     "tap:Not now"),
            ("Try templates",                          "templates_promo", "tap:Not now"),
            ("Boost your reach",                       "boost_promo",     "tap:Not now"),
            ("Try collabs",                            "collab_promo",    "tap:Not now"),
            # Info-only "Introducing X / Create longer X" announcement
            # screens — single OK button, no Save/Discard. Safe to tap OK
            # here because the marker dispatch is per-needle (NOT the generic
            # fallback). Tracked in audits 2026-05-29 14:48 / 16:47 / 20:47
            # and 2026-05-30 16:47 — repeated >5× without merge.
            ("Introducing Remix",                      "remix_promo",     "tap:OK"),
            ("Remix lets anyone create a reel",        "remix_promo",     "tap:OK"),
            ("Create longer reels",                    "longer_reels_promo", "tap:OK"),
            ("Now you can create reels up to 3 minutes long", "longer_reels_promo", "tap:OK"),
            # Acknowledgement / first-time notice screens (Continue = proceed)
            ("others can download your reel",          "download_notice", "tap:Continue"),
            ("Others can download",                    "download_notice", "tap:Continue"),
            ("Anyone can download",                    "download_notice", "tap:Continue"),
            ("anyone can use your audio",              "audio_notice",    "tap:Continue"),
            ("Your reel will appear on",               "reel_audience",   "tap:Continue"),
            ("Who can see your reel",                  "reel_audience",   "tap:Continue"),
            ("Heads up",                               "heads_up_notice", "tap:Continue"),
            # Discard / Save Draft / Generic-confirmation dialogs — these are
            # DANGEROUS. Tapping the wrong button discards our in-progress
            # reel. Always pick the "keep working" option.
            ("Save draft?",                            "draft_dialog",    "tap:Keep editing"),
            ("Discard reel?",                          "discard_dialog",  "tap:Keep editing"),
            ("Discard post?",                          "discard_dialog",  "tap:Keep editing"),
            ("Discard changes",                        "discard_dialog",  "tap:Keep editing"),
            ("Are you sure you want to discard",       "discard_dialog",  "tap:Keep editing"),
            ("Are you sure you want to leave",         "leave_dialog",    "tap:Stay"),
            # Confirmation tooltips that appear during creation flow
            ("Album switcher, Recents",                "album_tooltip",   "tap:Got it"),
        ]
        # Generic dismiss buttons (last resort for unknown screens).
        # CRITICAL: do NOT include 'OK', 'Close', 'Dismiss', 'Confirm' here —
        # on a "Discard reel?" / "Save draft?" dialog they CONFIRM the
        # destructive action and lose the in-progress post. Incident
        # 2026-05-29: tapping 'OK' on an unknown screen bounced JETT 1
        # back to the gallery (reel discarded).
        GENERIC_DISMISS_TEXTS = ['Not now', 'No thanks', 'Maybe later',
                                 'Skip', 'Got it']

        for attempt in range(max_back):
            try:
                xml = self.ctrl.dump_xml(f"subscreen_check_{attempt}")
            except Exception as e:
                log.debug("[%s] CONTENT: subscreen recovery dump failed: %s",
                          self.device_serial, e)
                return True   # can't check — assume OK

            # 1) Explicit marker match
            hit = None
            for needle, label, escape in SUBSCREEN_MARKERS:
                if needle in xml:
                    hit = (needle, label, escape)
                    break

            if hit:
                needle, label, escape = hit
                log.info("[%s] CONTENT: detected sub-screen [%s] (matched %r) — %s",
                         self.device_serial, label, needle, escape)
                if escape == 'back':
                    self.device.press('back')
                elif escape.startswith('tap:'):
                    btn_text = escape.split(':', 1)[1]
                    btn = self.device(textContains=btn_text)
                    if btn.exists(timeout=2):
                        btn.click()
                    else:
                        log.debug("[%s] CONTENT: button %r not found — "
                                  "falling back to system back",
                                  self.device_serial, btn_text)
                        self.device.press('back')
                time.sleep(1.5)
                continue   # re-check after escape

            # 2) Unknown screen — if it has any SAFE generic dismiss button
            # AND doesn't have Next/Share (our flow markers), it's some IG
            # promo we don't know yet. Tap the first safe dismiss we find.
            #
            # IMPORTANT: also check for the presence of destructive-confirmation
            # keywords. If the screen mentions "discard" / "delete" / "leave"
            # we must NOT tap anything generic — even "Not now" might mean
            # "Not now go back" on some IG builds. Bail out instead.
            has_next  = ('text="Next"' in xml or 'text="NEXT"' in xml or
                         'next_button' in xml)
            has_share = ('text="Share"' in xml or 'text="SHARE"' in xml or
                         'text="Post"' in xml or 'text="POST"' in xml or
                         'share_button' in xml)

            xml_lower = xml.lower()
            is_destructive = ('discard' in xml_lower or 'are you sure' in xml_lower
                              or 'delete' in xml_lower or 'leave?' in xml_lower)

            if not has_next and not has_share and not is_destructive:
                # Capture visible texts so we can grow the marker list quickly
                # next time we see this screen.
                visible_texts = re.findall(r'text="([^"]+)"', xml)
                visible_texts = [t for t in visible_texts if t.strip()
                                 and not t.isdigit() and ':' not in t][:10]
                log.info("[%s] CONTENT: unknown screen, texts=%r",
                         self.device_serial, visible_texts)

                tapped = False
                for dismiss_text in GENERIC_DISMISS_TEXTS:
                    if f'text="{dismiss_text}"' in xml:
                        log.info("[%s] CONTENT: tapping safe generic dismiss '%s'",
                                 self.device_serial, dismiss_text)
                        btn = self.device(text=dismiss_text)
                        if btn.exists(timeout=2):
                            btn.click()
                            time.sleep(1.5)
                            tapped = True
                            break
                if not tapped:
                    # No SAFE dismiss button — give up rather than guess
                    log.warning("[%s] CONTENT: no safe dismiss on unknown screen "
                                "— giving up rather than risk destructive tap "
                                "(visible texts: %r)",
                                self.device_serial, visible_texts)
                    return False
                continue   # re-check after safe dismiss
            elif is_destructive:
                # We're on a discard/delete confirmation dialog and no
                # explicit marker matched — try "Keep editing" / "Cancel"
                # as universal "back out of destructive" buttons.
                for keep_text in ('Keep editing', 'Cancel', 'No'):
                    btn = self.device(text=keep_text)
                    if btn.exists(timeout=2):
                        log.info("[%s] CONTENT: destructive dialog detected — "
                                 "tapping '%s'",
                                 self.device_serial, keep_text)
                        btn.click()
                        time.sleep(1.5)
                        break
                else:
                    log.warning("[%s] CONTENT: destructive dialog with no "
                                "Keep-editing/Cancel/No — bailing",
                                self.device_serial)
                    return False
                continue

            # 3) Has Next or Share — we're on a known good screen, done
            if attempt > 0:
                log.info("[%s] CONTENT: sub-screen recovery OK after %d back press(es)",
                         self.device_serial, attempt)
            return True

        log.warning("[%s] CONTENT: sub-screen recovery exhausted (%d attempts) — "
                    "still stuck", self.device_serial, max_back)
        return False

    def _tap_next(self):
        """
        Tap the "Next" button (appears in gallery selection and filter screens).
        Note: On filter/edit screen, button may show "Next →" — use textContains.

        Returns True if tapped. If we don't find Next, we first try to
        recover from any unexpected sub-screen (e.g. forced "Sharing
        preferences" onboarding) and retry once.
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

        # Last-ditch: maybe we're on an unexpected sub-screen blocking the
        # Next button. Recover (press back / dismiss dialog) and retry the
        # selectors ONCE more — without recursing.
        log.debug("[%s] CONTENT: Next button not found — attempting "
                  "sub-screen recovery", self.device_serial)
        if self._recover_unexpected_reel_screen():
            for text in ["Next", "NEXT"]:
                el = self.device(textContains=text)
                if el.exists(timeout=3):
                    el.click()
                    time.sleep(2)
                    log.info("[%s] CONTENT: Tapped Next after sub-screen "
                             "recovery (text='%s')",
                             self.device_serial, text)
                    return True
            for rid in ['next_button', 'next_button_textview',
                        'action_bar_button_action']:
                el = self.device(resourceIdMatches=f".*{rid}.*")
                if el.exists(timeout=2):
                    el.click()
                    time.sleep(2)
                    log.info("[%s] CONTENT: Tapped Next after sub-screen "
                             "recovery (rid='%s')",
                             self.device_serial, rid)
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
                    log.info("[%s] CONTENT: Entered caption via rid='%s'",
                             self.device_serial, rid)
                    return True
                except Exception:
                    pass  # Fall through to ADB input

        # Method 2: Text hint "Write a caption..."
        for hint in ["Write a caption", "Add a caption", "Caption",
                      "Write a caption and add hashtags"]:
            el = self.device(textContains=hint)
            if el.exists(timeout=3):
                log.info("[%s] CONTENT: Found caption field via hint='%s'",
                         self.device_serial, hint)
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
                log.info("[%s] CONTENT: Entered caption via EditText",
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

        Proven flow from share_to_story.py _add_story_mention():
        1. Open sticker picker (swipe up from center, fallback to button)
        2. Try direct click on @MENTION text, then search "mention" as fallback
        3. Type username in mention form, tap suggestion
        4. IG auto-places sticker and returns to preview
        """
        clean_username = mention_username.lstrip('@')
        log.info("[%s] CONTENT: Adding mention @%s to story",
                 self.device_serial, clean_username)

        # Step 1: Open sticker picker — swipe up first (proven more reliable)
        sticker_found = False
        w, h = self.device.window_size()
        self.device.swipe(w // 2, int(h * 0.5), w // 2, int(h * 0.15), duration=0.3)
        time.sleep(2)

        if self.device(className="android.widget.EditText").exists(timeout=2):
            sticker_found = True
            log.debug("[%s] CONTENT: Opened sticker picker via swipe up",
                      self.device_serial)

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
                    log.debug("[%s] CONTENT: Opened sticker picker via button",
                              self.device_serial)
                    break

        if not sticker_found:
            log.warning("[%s] CONTENT: Could not open sticker picker for mention",
                        self.device_serial)
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
                log.debug("[%s] CONTENT: Clicked MENTION sticker via text='%s' (direct)",
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
                    log.debug("[%s] CONTENT: Clicked MENTION sticker via desc='%s'",
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
                log.debug("[%s] CONTENT: Typed 'mention' in sticker search",
                          self.device_serial)

                for text_val in ["@MENTION", "MENTION", "Mention"]:
                    el = self.device(textContains=text_val)
                    if el.exists(timeout=2):
                        el.click()
                        time.sleep(2)
                        mention_clicked = True
                        log.debug("[%s] CONTENT: Clicked MENTION sticker via search + text='%s'",
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
                    log.debug("[%s] CONTENT: Clicked MENTION sticker via XML bounds (%d,%d)",
                              self.device_serial, x, y)
                    break

        if not mention_clicked:
            log.warning("[%s] CONTENT: MENTION sticker not found in search results",
                        self.device_serial)
            self.ctrl.press_back()
            return False

        # Step 4: Enter username in mention form and select from suggestions
        time.sleep(1)
        username_field = self.device(className="android.widget.EditText")
        if username_field.exists(timeout=3):
            username_field.click()
            time.sleep(0.5)
            username_field.set_text(clean_username)
            time.sleep(3)  # Wait for suggestions to load
            log.debug("[%s] CONTENT: Typed username: %s",
                      self.device_serial, clean_username)

            # Click first suggestion (exact match should be first)
            suggestion_clicked = False
            target_lower = clean_username.lower()

            for selector in [
                self.device(textContains=clean_username),
                self.device(descriptionContains=clean_username),
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
                                log.info("[%s] CONTENT: Clicked mention suggestion: '%s'",
                                         self.device_serial, clean_username)
                                break
                        except Exception:
                            continue
                    if suggestion_clicked:
                        break

            if not suggestion_clicked:
                # XML fallback for suggestion
                xml = self.ctrl.dump_xml("mention_suggestions")
                match = re.search(
                    r'text="' + re.escape(clean_username) + r'"[^>]*'
                    r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                    xml, re.IGNORECASE)
                if match:
                    x = (int(match.group(1)) + int(match.group(3))) // 2
                    y = (int(match.group(2)) + int(match.group(4))) // 2
                    self.device.click(x, y)
                    time.sleep(1.5)
                    suggestion_clicked = True
                    log.info("[%s] CONTENT: Clicked mention suggestion via XML",
                             self.device_serial)

            if not suggestion_clicked:
                log.warning("[%s] CONTENT: Could not find suggestion for @%s — tapping Done anyway",
                            self.device_serial, clean_username)
        else:
            log.warning("[%s] CONTENT: Username input field not found in mention form",
                        self.device_serial)
            self.ctrl.press_back()
            return False

        # Step 5: After clicking suggestion, IG auto-places the mention sticker
        # and returns to story preview. Only tap Done if stuck in editing mode.
        time.sleep(2)
        if self.device(textContains="Your story").exists(timeout=3):
            log.debug("[%s] CONTENT: Mention placed, already in story preview",
                      self.device_serial)
        elif self.device(text="Done").exists(timeout=2):
            self.device(text="Done").click()
            time.sleep(2)
            log.debug("[%s] CONTENT: Clicked Done after mention placement",
                      self.device_serial)
        elif self.device(description="Done").exists(timeout=2):
            self.device(description="Done").click()
            time.sleep(2)
            log.debug("[%s] CONTENT: Clicked Done (desc) after mention placement",
                      self.device_serial)

        log.info("[%s] CONTENT: Mention @%s added to story via sticker",
                 self.device_serial, clean_username)
        return True

    def _add_link_sticker(self, url):
        """
        Add a link sticker in the story editor.

        Proven flow from share_to_story.py _add_link_sticker():
        1. Open sticker picker (swipe up from center, fallback to button)
        2. Type "link" in search bar
        3. Tap LINK sticker (desc="Link Sticker" or text="LINK")
        4. Enter URL in first EditText field
        5. Tap Done
        """
        if not url:
            return False

        log.info("[%s] CONTENT: Adding link sticker: %s",
                 self.device_serial, url[:50])

        # Step 1: Open sticker picker — swipe up first (proven more reliable)
        sticker_found = False
        w, h = self.device.window_size()
        self.device.swipe(w // 2, int(h * 0.5), w // 2, int(h * 0.15), duration=0.3)
        time.sleep(2)

        if self.device(className="android.widget.EditText").exists(timeout=2):
            sticker_found = True
            log.debug("[%s] CONTENT: Opened sticker picker via swipe up",
                      self.device_serial)

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
                    log.debug("[%s] CONTENT: Opened sticker picker via button",
                              self.device_serial)
                    break

        if not sticker_found:
            log.warning("[%s] CONTENT: Could not open sticker picker for link",
                        self.device_serial)
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
            log.debug("[%s] CONTENT: Typed 'link' in sticker search",
                      self.device_serial)
        else:
            log.warning("[%s] CONTENT: Sticker search bar not found",
                        self.device_serial)
            self.ctrl.press_back()
            return False

        # Step 3: Tap LINK sticker result
        link_clicked = False

        # Try description first
        for desc_val in ["Link Sticker", "LINK"]:
            el = self.device(description=desc_val)
            if el.exists(timeout=2):
                el.click()
                time.sleep(2)
                link_clicked = True
                log.debug("[%s] CONTENT: Clicked LINK sticker via desc='%s'",
                          self.device_serial, desc_val)
                break

        # Try exact text match
        if not link_clicked:
            for text_val in ["LINK", "Link"]:
                el = self.device(text=text_val)
                if el.exists(timeout=2):
                    el.click()
                    time.sleep(2)
                    link_clicked = True
                    log.debug("[%s] CONTENT: Clicked LINK sticker via text='%s'",
                              self.device_serial, text_val)
                    break

        # XML fallback
        if not link_clicked:
            xml = self.ctrl.dump_xml("sticker_search_results")
            for pattern in [r'description="Link Sticker"', r'text="LINK"',
                            r'text="Link"']:
                match = re.search(
                    pattern + r'[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
                if match:
                    x = (int(match.group(1)) + int(match.group(3))) // 2
                    y = (int(match.group(2)) + int(match.group(4))) // 2
                    self.device.click(x, y)
                    time.sleep(2)
                    link_clicked = True
                    log.debug("[%s] CONTENT: Clicked LINK sticker via XML bounds (%d,%d)",
                              self.device_serial, x, y)
                    break

        if not link_clicked:
            log.warning("[%s] CONTENT: LINK sticker not found in search results",
                        self.device_serial)
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
            log.debug("[%s] CONTENT: Entered URL: %s",
                      self.device_serial, url[:50])
        else:
            log.warning("[%s] CONTENT: URL input field not found",
                        self.device_serial)
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
                log.debug("[%s] CONTENT: Confirmed link sticker with Done",
                          self.device_serial)
                break

        if not done_clicked:
            self.device.press('enter')
            time.sleep(1)

        log.info("[%s] CONTENT: Link sticker added: %s",
                 self.device_serial, url[:50])
        return True

    def _dismiss_about_reels_modal(self):
        """
        Handle the 'About Reels' modal that appears before sharing.

        Modal text: "Your reel will be shared to Reels, where anyone can
        discover it." with Share (blue), Cancel, Learn more buttons.
        We tap Share on this modal to proceed.
        """
        # Check if the modal is present
        modal = self.device(textContains="About Reels")
        if not modal.exists(timeout=3):
            # Also check for the modal body text
            modal = self.device(textContains="will be shared to Reels")
            if not modal.exists(timeout=2):
                log.debug("[%s] CONTENT: No 'About Reels' modal detected",
                          self.device_serial)
                return False

        log.info("[%s] CONTENT: 'About Reels' modal detected, tapping Share",
                 self.device_serial)

        # The modal has its own Share button — tap it
        share_btn = self.device(text="Share")
        if share_btn.exists(timeout=3):
            share_btn.click()
            time.sleep(2)
            log.info("[%s] CONTENT: Dismissed 'About Reels' modal",
                     self.device_serial)
            return True

        # Fallback: try clicking the blue button area
        log.warning("[%s] CONTENT: Could not find Share on 'About Reels' modal",
                    self.device_serial)
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

        # Dump XML so we can see what screen we're stuck on
        try:
            xml = self.ctrl.dump_xml("share_button_missing")
            # Log first 500 chars of text content for debugging
            import re as _re
            texts = _re.findall(r'text="([^"]+)"', xml)
            visible_texts = [t for t in texts if t and t != 'false' and t != 'true']
            log.warning("[%s] CONTENT: Share/Post button not found. Screen texts: %s",
                        self.device_serial, visible_texts[:15])
        except Exception:
            log.warning("[%s] CONTENT: Share/Post button not found (no XML dump)",
                        self.device_serial)
        return False

    def _tap_story_share(self):
        """
        Tap the "Your Story" publish button in the story editor bottom bar.

        Proven flow from share_to_story.py _publish_story():
        - Primary: desc="Your story" in BOTTOM action bar (y > 70% of screen)
        - The bottom bar has: "Your story" | "Close Friends" | "Share to" (arrow)
        - Must verify element is in bottom bar, not a sticker/overlay in the editor

        Returns True if tapped.
        """
        w, h = self.device.window_size()
        bottom_threshold = int(h * 0.70)
        xml = self.ctrl.dump_xml("story_share_screen")

        # Method 1: "Your story" button — verify it's in the bottom bar
        for attempt in range(3):
            # Try by content-desc (most reliable)
            el = self.device(description="Your story")
            if el.exists(timeout=3):
                try:
                    info = el.info
                    bounds = info.get('bounds', {})
                    el_y = bounds.get('top', 0)
                    if el_y >= bottom_threshold:
                        el.click()
                        time.sleep(3)
                        log.info("[%s] CONTENT: Published story via desc='Your story' y=%d (attempt %d)",
                                 self.device_serial, el_y, attempt + 1)
                        return True
                    else:
                        log.debug("[%s] CONTENT: desc='Your story' found but y=%d < %d (not publish bar)",
                                  self.device_serial, el_y, bottom_threshold)
                except Exception:
                    el.click()
                    time.sleep(3)
                    log.info("[%s] CONTENT: Published story via desc='Your story' (attempt %d)",
                             self.device_serial, attempt + 1)
                    return True

            # Try by text — also verify bottom bar
            el = self.device(text="Your story")
            if el.exists(timeout=2):
                try:
                    info = el.info
                    bounds = info.get('bounds', {})
                    el_y = bounds.get('top', 0)
                    if el_y >= bottom_threshold:
                        el.click()
                        time.sleep(3)
                        log.info("[%s] CONTENT: Published story via text='Your story' y=%d (attempt %d)",
                                 self.device_serial, el_y, attempt + 1)
                        return True
                except Exception:
                    pass

            if attempt < 2:
                log.debug("[%s] CONTENT: 'Your story' not in bottom bar, retry %d...",
                          self.device_serial, attempt + 2)
                time.sleep(3)

        # Method 2: "Share to" arrow button (the ">" next to Your story / Close Friends)
        share_to = self.device(description="Share to")
        if share_to.exists(timeout=2):
            share_to.click()
            time.sleep(3)
            log.info("[%s] CONTENT: Published story via 'Share to' arrow",
                     self.device_serial)
            return True

        # Method 3: Click the action bar by resource-id (left side = "Your story")
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
                    log.info("[%s] CONTENT: Published story via action bar left-side click",
                             self.device_serial)
                    return True
            except Exception as e:
                log.debug("[%s] CONTENT: Action bar click failed: %s",
                          self.device_serial, e)

        # Method 4: Other text/desc patterns
        for attr, pattern in [("text", "Share"), ("text", "Done"), ("text", "Post"),
                              ("description", "Share"),
                              ("description", "Share to your story")]:
            if attr == "text":
                el = self.device(text=pattern)
            else:
                el = self.device(description=pattern)
            if el.exists(timeout=2):
                el.click()
                time.sleep(3)
                log.debug("[%s] CONTENT: Published story via %s='%s'",
                          self.device_serial, attr, pattern)
                return True

        # Method 5: Known resource-id patterns
        for rid_pattern in ["share_story_button", "done_button", "share_button",
                            "action_bar_button_action"]:
            el = self.device(resourceIdMatches=f".*{rid_pattern}.*")
            if el.exists(timeout=2):
                el.click()
                time.sleep(3)
                log.debug("[%s] CONTENT: Published story via rid=%s",
                          self.device_serial, rid_pattern)
                return True

        # Method 6: XML bounds search for share-like buttons in bottom area
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
            log.debug("[%s] CONTENT: Published story via XML match '%s'",
                      self.device_serial, desc[:40])
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
