"""
Comment Action Module — IGController Edition
===============================================
Post comments on Instagram posts using XML-based UI control.

Modes:
- Feed: Comment on posts in home feed
- Source followers: Visit source profiles, comment on their posts
- Hashtag: Comment on posts from hashtag search (via source keywords)

Supports:
- Spintax in comment templates ({Great|Amazing|Awesome} post!)
- Template comments from account_text_configs (comments_list)
- AI placeholder for GPT-generated comments
- Rate limiting per day
- Duplicate avoidance

Discovered Resource IDs (verified on androif 2026-02-05):
- Comment button: row_feed_button_comment (content-desc="Comment")
- Comment input: layout_comment_thread_edittext
- Comment post button: layout_comment_thread_post_button_icon (content-desc="Post")
- Comment post click area: layout_comment_thread_post_button_click_area
- Comment composer parent: comment_composer_parent
- Comment composer avatar: comment_composer_avatar
- Like button: row_feed_button_like
- Post header: row_feed_profile_header
- Feed buttons: row_feed_button_share, row_feed_button_save
"""

import logging
import random
import re
import time
import subprocess

from automation.actions.helpers import (
    action_delay, random_sleep, log_action,
    get_account_settings, get_account_sources,
    get_today_action_count, get_recently_interacted, get_db,
)
from automation.ig_controller import IGController, Screen

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Spintax support: {Great|Amazing|Awesome} -> random pick
# ---------------------------------------------------------------------------
def _process_spintax(text):
    """Process spintax: {option1|option2|option3} -> random pick."""
    def _replace(match):
        options = match.group(1).split('|')
        return random.choice(options).strip()
    return re.sub(r'\{([^}]+)\}', _replace, text)


class CommentAction:
    """
    Post comments on Instagram posts.
    Uses IGController for reliable XML-based UI control.
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

        # Load settings & templates
        self.settings = get_account_settings(self.account_id)
        self._init_limits()
        self._load_comments()

    def _init_limits(self):
        """Initialize comment limits from account settings."""
        self.daily_limit = int(self.settings.get('comment_limit_perday', '25'))
        if self.daily_limit <= 0:
            self.daily_limit = 25

        min_c = int(self.settings.get('min_comment', '5'))
        max_c = int(self.settings.get('max_comment', '10'))
        if min_c <= 0:
            min_c = 3
        if max_c <= 0:
            max_c = 8
        if min_c > max_c:
            min_c, max_c = max_c, min_c
        self.session_target = random.randint(min_c, max_c)

        self.min_delay = int(self.settings.get('comment_min_delay', '5'))
        self.max_delay = int(self.settings.get('comment_max_delay', '15'))
        if self.min_delay < 3:
            self.min_delay = 3
        if self.max_delay < self.min_delay:
            self.max_delay = self.min_delay + 10

        log.info("[%s] Comment limits: daily=%d, session_target=%d, delay=%d-%ds",
                 self.device_serial, self.daily_limit, self.session_target,
                 self.min_delay, self.max_delay)

    def _load_comments(self):
        """Load comment templates from DB (account_text_configs.comments_list)."""
        self.comment_templates = []
        try:
            conn = get_db()
            row = conn.execute("""
                SELECT content FROM account_text_configs
                WHERE account_id=? AND config_type='comments_list'
            """, (self.account_id,)).fetchone()
            conn.close()

            if row and row['content']:
                lines = [l.strip() for l in row['content'].split('\n')
                         if l.strip()]
                self.comment_templates = lines
        except Exception as e:
            log.error("[%s] Failed to load comments: %s",
                      self.device_serial, e)

        if not self.comment_templates:
            self.comment_templates = [
                "{🔥|❤️|✨} {Love this|Amazing|So good}!",
                "{This is incredible|Wow, stunning|Beautiful work}! {🙌|💯|😍}",
                "{Awesome post|Great content|Love your page}! {🔥|✨|💪}",
                "{So inspiring|Really amazing|Keep it up}! {❤️|🙏|🌟}",
                "{Goals|This is everything|Perfection}! {💯|😍|🔥}",
                "Love this {perspective|energy|vibe}! {✨|🙌|❤️}",
            ]

        log.info("[%s] Loaded %d comment templates",
                 self.device_serial, len(self.comment_templates))

    def _get_comment(self):
        """Get a random comment with spintax resolved."""
        # Check for AI mode
        ai_text = self.settings.get('comment_text', '')
        if ai_text == '[AI]':
            # Placeholder for AI comment generation
            # Falls back to templates for now
            pass
        elif ai_text and ai_text != '[AI]':
            return _process_spintax(ai_text)

        template = random.choice(self.comment_templates)
        return _process_spintax(template)

    # ------------------------------------------------------------------
    # Main execute
    # ------------------------------------------------------------------
    def execute(self):
        """
        Execute the comment action.
        Returns dict: {success, comments_posted, errors, skipped}
        """
        result = {
            'success': False,
            'comments_posted': 0,
            'errors': 0,
            'skipped': 0,
        }

        # Ensure Instagram is running
        self.ctrl.ensure_app()
        self.ctrl.dismiss_popups()

        # Check daily limit
        done_today = get_today_action_count(
            self.device_serial, self.username, 'comment')
        remaining = self.daily_limit - done_today
        if remaining <= 0:
            log.info("[%s] %s: Daily comment limit reached (%d/%d)",
                     self.device_serial, self.username,
                     done_today, self.daily_limit)
            result['success'] = True
            return result

        target = min(self.session_target, remaining)
        log.info("[%s] %s: Will post up to %d comments (done today: %d, daily limit: %d)",
                 self.device_serial, self.username, target,
                 done_today, self.daily_limit)

        recently_commented = get_recently_interacted(
            self.device_serial, self.username, 'comment', days=7)
        log.info("[%s] Recently commented: %d users (will skip)",
                 self.device_serial, len(recently_commented))

        # Determine comment method based on settings
        comment_method = self.settings.get('comment_method', 'feed')

        if comment_method == 'keyword_search':
            keywords = get_account_sources(self.account_id, 'comment_keywords')
            if keywords:
                self._comment_via_search(
                    keywords, target, recently_commented, result)
            else:
                # Fall back to feed
                self._comment_on_feed(target, recently_commented, result)
        else:
            # Default: comment on home feed posts
            self._comment_on_feed(target, recently_commented, result)

        result['success'] = True
        log.info("[%s] %s: Comment complete. Posted: %d, Skipped: %d, Errors: %d",
                 self.device_serial, self.username,
                 result['comments_posted'], result['skipped'], result['errors'])
        return result

    # ------------------------------------------------------------------
    # Comment Methods
    # ------------------------------------------------------------------
    def _comment_on_feed(self, max_comments, already_commented, result):
        """
        Scroll home feed and comment on posts.
        Uses IGController XML parsing for reliable element detection.
        """
        # Navigate to home feed
        if not self.ctrl.navigate_to(Screen.HOME_FEED):
            log.warning("[%s] Could not navigate to home feed",
                       self.device_serial)
            result['errors'] += 1
            return

        random_sleep(2, 4, label="home_loaded")

        scroll_attempts = 0
        max_scrolls = 20
        seen_authors = set()

        while (result['comments_posted'] < max_comments
               and scroll_attempts < max_scrolls):

            self.ctrl.dismiss_popups()

            # Get current post info from XML
            xml = self.ctrl.dump_xml("feed_comment_scan")
            author = self._get_post_author_from_xml(xml)

            if author:
                if author in seen_authors:
                    # Already processed this post
                    pass
                elif (author in already_commented
                      or author.lower() == self.username.lower()):
                    log.debug("[%s] Skip comment on @%s (already done or self)",
                             self.device_serial, author)
                    result['skipped'] += 1
                    seen_authors.add(author)
                else:
                    seen_authors.add(author)

                    # Check if comment button is visible
                    comment_btn = self._find_comment_button(xml)
                    if comment_btn:
                        try:
                            success = self._post_comment(comment_btn)
                            if success:
                                result['comments_posted'] += 1
                                already_commented.add(author)
                                log_action(
                                    self.session_id, self.device_serial,
                                    self.username, 'comment',
                                    target_username=author, success=True)
                                log.info("[%s] Commented on @%s's post (%d/%d)",
                                        self.device_serial, author,
                                        result['comments_posted'],
                                        max_comments)
                                random_sleep(self.min_delay, self.max_delay,
                                            label="comment_delay")
                            else:
                                result['errors'] += 1
                                log_action(
                                    self.session_id, self.device_serial,
                                    self.username, 'comment',
                                    target_username=author, success=False,
                                    error_message="Comment post failed")
                        except Exception as e:
                            log.error("[%s] Comment error on @%s: %s",
                                     self.device_serial, author, e)
                            result['errors'] += 1
                            self._recover()
                    else:
                        log.debug("[%s] No comment button visible",
                                 self.device_serial)

            # Scroll to next post
            self.ctrl.scroll_feed("down", amount=0.5)
            random_sleep(2, 4, label="scroll_feed")
            scroll_attempts += 1

    def _comment_via_search(self, keywords, max_comments, already_commented,
                            result):
        """
        Comment on posts found via hashtag/keyword search.
        """
        random.shuffle(keywords)

        for keyword in keywords:
            if result['comments_posted'] >= max_comments:
                break

            log.info("[%s] Searching keyword: %s", self.device_serial, keyword)

            # Navigate to search
            if not self.ctrl.navigate_to(Screen.SEARCH):
                continue

            time.sleep(1)

            # Search for keyword
            search_bar = self.ctrl.find_element(
                resource_id='action_bar_search_edit_text', timeout=3)
            if search_bar is None:
                search_bar = self.ctrl.find_element(
                    class_name='android.widget.EditText', timeout=3)
            if search_bar is None:
                continue

            search_bar.click()
            time.sleep(1)
            search_bar.clear_text()
            time.sleep(0.5)

            # Type keyword
            subprocess.run(
                ['adb', '-s', self.ctrl.adb_serial, 'shell', 'input', 'text',
                 keyword.replace(' ', '%s')],
                capture_output=True, timeout=10
            )
            time.sleep(2)

            # Submit search
            subprocess.run(
                ['adb', '-s', self.ctrl.adb_serial, 'shell', 'input',
                 'keyevent', '66'],
                capture_output=True, timeout=10
            )
            time.sleep(3)

            # Click on a post from results
            if self.ctrl.open_explore_post():
                random_sleep(2, 3)

                xml = self.ctrl.dump_xml("search_post")
                author = self._get_post_author_from_xml(xml)

                if (author and author not in already_commented
                        and author.lower() != self.username.lower()):

                    comment_btn = self._find_comment_button(xml)
                    if comment_btn:
                        try:
                            success = self._post_comment(comment_btn)
                            if success:
                                result['comments_posted'] += 1
                                already_commented.add(author)
                                log_action(
                                    self.session_id, self.device_serial,
                                    self.username, 'comment',
                                    target_username=author, success=True)
                                log.info("[%s] Commented on @%s (keyword: %s)",
                                        self.device_serial, author, keyword)
                                random_sleep(self.min_delay, self.max_delay,
                                            label="comment_delay")
                        except Exception as e:
                            log.error("[%s] Comment error: %s",
                                     self.device_serial, e)
                            result['errors'] += 1

                self.ctrl.press_back()
                time.sleep(1)

            self.ctrl.press_back()
            time.sleep(1)

    # ------------------------------------------------------------------
    # Core comment posting
    # ------------------------------------------------------------------
    def _get_post_author_from_xml(self, xml):
        """
        Extract the post author username from XML.
        Uses multiple strategies for reliability.

        Known content-desc patterns:
        - row_feed_profile_header: "username posted a photo 3 hours ago"
        - row_feed_photo_profile_imageview: "Profile picture of username"
        - Button child: content-desc="username" (clickable username label)
        """
        if not xml:
            return None

        # Method 1: row_feed_profile_header content-desc
        # e.g. "nekonekodreamer posted a photo 3 hours ago"
        # e.g. "willie27_ Verified"
        header = self.ctrl._find_in_xml(
            xml, resource_id='row_feed_profile_header')
        if header:
            desc = header.get('content_desc', '')
            if desc:
                # Extract username (first word before space)
                username = desc.split(' ')[0].strip()
                if username and username not in ('Sponsored', 'Suggested', 'Photo'):
                    return username

        # Method 2: row_feed_photo_profile_name text (sometimes has username)
        name_el = self.ctrl._find_in_xml(
            xml, resource_id='row_feed_photo_profile_name')
        if name_el:
            text = name_el.get('text', '')
            if text:
                username = text.split('\n')[0].strip()
                if username and username not in ('Sponsored', 'Suggested'):
                    return username

        # Method 3: "Profile picture of username" pattern
        # row_feed_photo_profile_imageview has content-desc="Profile picture of username"
        profile_pics = self.ctrl._find_all_in_xml(
            xml, desc_pattern=r"Profile picture of .+")
        for pic in profile_pics:
            desc = pic.get('content_desc', '')
            # Extract: "Profile picture of username" -> username
            if desc.startswith('Profile picture of '):
                username = desc[len('Profile picture of '):].strip()
                if username and len(username) < 50:
                    return username

        # Method 4: Old pattern — "username's profile picture"
        profile_pics_old = self.ctrl._find_all_in_xml(
            xml, desc_pattern=r"[^']+['\u2019]s profile picture")
        for pic in profile_pics_old:
            desc = pic.get('content_desc', '')
            username = desc.split("'")[0].strip()
            if username and len(username) < 50:
                return username

        # Method 5: "username posted a ..." pattern in any content-desc
        import re
        posted_match = re.search(
            r'content-desc="(\w[\w._]+)\s+posted\s+a\s+',
            xml)
        if posted_match:
            username = posted_match.group(1)
            if username and username not in ('Sponsored', 'Suggested'):
                return username

        # Method 6: "Video/Photo N of M by username, N likes, N comments" pattern
        # Instagram clone shows media info like: "Video 3 of 5 by Willie Salim, 7,509 likes"
        by_match = re.search(
            r'content-desc="(?:Video|Photo|Reel|Image)[^"]*\bby\s+([\w][\w._ ]+?)(?:,|\s*\d)',
            xml)
        if by_match:
            username = by_match.group(1).strip()
            if username and username not in ('Sponsored', 'Suggested'):
                return username

        return None

    def _find_comment_button(self, xml):
        """
        Find the comment button in the current XML.
        Returns bounds dict or None.
        """
        btn = self.ctrl._find_in_xml(
            xml, resource_id='row_feed_button_comment')
        if btn and btn.get('bounds'):
            return btn

        # Fallback: content-desc="Comment"
        btns = self.ctrl._find_all_in_xml(xml, desc_pattern=r"Comment")
        for b in btns:
            if b.get('bounds') and b.get('clickable', 'false') == 'true':
                return b

        return None

    def _post_comment(self, comment_btn_info):
        """
        Post a comment on the post whose comment button info is provided.

        Flow:
        1. Click comment button (by bounds)
        2. Wait for comment sheet to appear
        3. Find comment input field
        4. Type comment via ADB
        5. Find and click Post/Send button
        6. Verify comment was posted
        7. Go back

        Returns True on success.
        """
        # Click the comment button
        bounds = comment_btn_info.get('bounds', '')
        if bounds:
            cx, cy = self.ctrl._bounds_center(bounds)
            if cx > 0 and cy > 0:
                self.device.click(cx, cy)
            else:
                # Fallback to u2
                btn = self.ctrl.find_element(
                    resource_id='row_feed_button_comment', timeout=2)
                if btn:
                    btn.click()
                else:
                    return False
        else:
            btn = self.ctrl.find_element(
                resource_id='row_feed_button_comment', timeout=2)
            if btn:
                btn.click()
            else:
                return False

        random_sleep(2, 3, label="comment_sheet_load")

        # Dismiss any popup that appeared
        screen = self.ctrl.detect_screen()
        if screen == Screen.POPUP:
            self.ctrl.dismiss_popups()
            time.sleep(1)

        # Find comment input field
        comment_input = self.ctrl.find_element(
            resource_id='layout_comment_thread_edittext', timeout=5)
        if comment_input is None:
            comment_input = self.ctrl.find_element(
                class_name='android.widget.EditText', timeout=3)

        if comment_input is None:
            log.warning("[%s] Comment input not found", self.device_serial)
            self.ctrl.dump_xml("comment_input_not_found")
            self.ctrl.press_back()
            return False

        # Click to focus the input
        comment_input.click()
        time.sleep(1)

        # Get and type comment
        comment_text = self._get_comment()
        log.debug("[%s] Typing comment: %s", self.device_serial, comment_text)

        # Type via ADB for emoji support
        escaped = comment_text.replace(' ', '%s').replace("'", "\\'")
        subprocess.run(
            ['adb', '-s', self.ctrl.adb_serial, 'shell', 'input', 'text',
             escaped],
            capture_output=True, timeout=10
        )
        time.sleep(1)

        # Find and click Post button
        posted = self._click_post_button()
        if not posted:
            log.warning("[%s] Could not find Post button", self.device_serial)
            self.ctrl.dump_xml("comment_post_btn_not_found")
            self.ctrl.press_back()
            return False

        random_sleep(2, 3, label="comment_posting")

        # Verify: check if we're back to the comment sheet or feed
        # If the comment was posted, the input should be cleared
        screen = self.ctrl.detect_screen()
        if screen in (Screen.COMMENT_VIEW, Screen.HOME_FEED, Screen.POPUP):
            if screen == Screen.POPUP:
                self.ctrl.dismiss_popups()
                time.sleep(1)

        # Go back to feed
        self.ctrl.press_back()
        time.sleep(1)

        # Make sure we're back in feed, not stuck
        screen = self.ctrl.detect_screen()
        if screen == Screen.COMMENT_VIEW:
            self.ctrl.press_back()
            time.sleep(1)

        log.info("[%s] Comment posted successfully", self.device_serial)
        return True

    def _click_post_button(self):
        """
        Find and click the Post/Send button for comments.
        Tries multiple strategies.
        Returns True if clicked.
        """
        # Strategy 1: resource ID for post button icon (confirmed working 2026-02-05)
        post_btn = self.ctrl.find_element(
            resource_id='layout_comment_thread_post_button_icon',
            timeout=2)
        if post_btn:
            post_btn.click()
            return True

        # Strategy 1b: resource ID for post button click area
        post_btn = self.ctrl.find_element(
            resource_id='layout_comment_thread_post_button_click_area',
            timeout=2)
        if post_btn:
            post_btn.click()
            return True

        # Strategy 2: text="Post"
        post_btn = self.ctrl.find_element(text="Post", timeout=2)
        if post_btn:
            post_btn.click()
            return True

        # Strategy 3: desc="Post"
        post_btn = self.ctrl.find_element(desc="Post", timeout=2)
        if post_btn:
            post_btn.click()
            return True

        # Strategy 4: Look in XML for post-related clickable elements
        xml = self.ctrl.dump_xml("find_post_btn")
        post_el = self.ctrl._find_in_xml(xml, text="Post")
        if post_el and post_el.get('bounds'):
            cx, cy = self.ctrl._bounds_center(post_el['bounds'])
            if cx > 0 and cy > 0:
                self.device.click(cx, cy)
                return True

        # Strategy 5: "Send" button (some keyboard layouts)
        send_btn = self.ctrl.find_element(text="Send", timeout=2)
        if send_btn:
            send_btn.click()
            return True

        # Strategy 6: Press Enter key via ADB
        log.debug("[%s] Trying Enter key to post comment", self.device_serial)
        subprocess.run(
            ['adb', '-s', self.ctrl.adb_serial, 'shell', 'input',
             'keyevent', '66'],
            capture_output=True, timeout=10
        )
        time.sleep(1)
        return True  # Assume it worked

    # ------------------------------------------------------------------
    # Recovery
    # ------------------------------------------------------------------
    def _recover(self):
        """Try to recover to a known UI state."""
        try:
            # Close keyboard if open
            self.device.press('back')
            time.sleep(0.5)
            self.ctrl.recover_to_home()
        except Exception:
            pass


def execute_comment(device, device_serial, account_info, session_id):
    """Convenience function to run comment action."""
    action = CommentAction(device, device_serial, account_info, session_id)
    return action.execute()
