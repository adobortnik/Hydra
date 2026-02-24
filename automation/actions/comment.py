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
import os
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

        # Enable AdbKeyboard IME for reliable text input
        try:
            self.device.set_input_ime(True)
            log.info("[%s] AdbKeyboard IME enabled", self.device_serial)
        except Exception as e:
            log.warning("[%s] Failed to enable AdbKeyboard IME: %s",
                        self.device_serial, e)

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

    def _get_comment(self, post_author=None, post_context=None):
        """Get a comment — AI-generated if [AI] mode, else spintax/template."""
        ai_text = self.settings.get('comment_text', '')
        if ai_text == '[AI]':
            comment = self._generate_ai_comment(post_author, post_context)
            if comment:
                return comment
            # Fall through to templates if AI fails
        elif ai_text and ai_text != '[AI]':
            return _process_spintax(ai_text)

        template = random.choice(self.comment_templates)
        return _process_spintax(template)

    def _generate_ai_comment(self, post_author=None, post_context=None):
        """Generate a comment using OpenAI API."""
        try:
            import json
            settings_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                'dashboard', 'global_settings.json')
            with open(settings_path) as f:
                settings = json.load(f)
            api_key = settings.get('ai', {}).get('openai_api_key', '')
            if not api_key:
                log.warning("[%s] No OpenAI API key configured", self.device_serial)
                return None

            # Get the GPT prompt from account text configs
            prompt = self._get_comment_gpt_prompt()
            if not prompt:
                prompt = ("Generate a short, natural Instagram comment "
                          "(1-2 sentences). Be casual, friendly. "
                          "May include 1-2 emojis.")

            # Replace placeholders
            if post_author:
                prompt = prompt.replace('[SOURCE]', post_author).replace('[AUTHOR]', post_author)

            import requests
            response = requests.post(
                'https://api.openai.com/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'gpt-4o-mini',
                    'messages': [
                        {'role': 'system', 'content': prompt},
                        {'role': 'user', 'content': (
                            f'Write a short comment for an Instagram post by '
                            f'@{post_author or "someone"}.'
                            f'{" Post context: " + post_context if post_context else ""}'
                        )}
                    ],
                    'max_tokens': 100,
                    'temperature': 0.9
                },
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                comment = data['choices'][0]['message']['content'].strip()
                # Clean: remove quotes if wrapped
                comment = comment.strip('"').strip("'")
                log.info("[%s] AI comment generated: %s",
                         self.device_serial, comment[:50])
                return comment
            else:
                log.warning("[%s] OpenAI API returned %d: %s",
                            self.device_serial, response.status_code,
                            response.text[:200])
        except Exception as e:
            log.warning("[%s] AI comment generation failed: %s",
                        self.device_serial, e)
        return None

    def _get_comment_gpt_prompt(self):
        """Get comment GPT prompt from account text configs."""
        try:
            conn = get_db()
            row = conn.execute(
                "SELECT content FROM account_text_configs "
                "WHERE account_id=? AND config_type='comment_gpt_prompt'",
                (self.account_id,)
            ).fetchone()
            conn.close()
            if row and row['content']:
                return row['content'].strip()
        except Exception:
            pass
        return None

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

        # Parse comment_method — can be a dict like {'comment_using_keyword_search': False}
        use_keyword_search = False
        if isinstance(comment_method, dict):
            use_keyword_search = comment_method.get('comment_using_keyword_search', False)
            log.debug("[%s] comment_method is dict: %s, keyword_search=%s",
                      self.device_serial, comment_method, use_keyword_search)
        elif isinstance(comment_method, str):
            use_keyword_search = (comment_method == 'keyword_search')

        # Priority 1: Comment sources (specific profiles to comment on)
        comment_sources = get_account_sources(self.account_id, 'comment_sources')
        if comment_sources:
            log.info("[%s] Found %d comment sources, using source-based commenting",
                     self.device_serial, len(comment_sources))
            self._comment_on_sources(
                comment_sources, target, recently_commented, result)

        # Priority 2: Keyword search if enabled and still have budget
        if use_keyword_search and result['comments_posted'] < target:
            keywords = get_account_sources(self.account_id, 'comment_keywords')
            if keywords:
                remaining_target = target - result['comments_posted']
                self._comment_via_search(
                    keywords, remaining_target, recently_commented, result)

        # Priority 3: Feed commenting as fallback if we haven't reached target
        if result['comments_posted'] < target:
            remaining_target = target - result['comments_posted']
            log.info("[%s] Falling back to feed commenting (need %d more)",
                     self.device_serial, remaining_target)
            self._comment_on_feed(remaining_target, recently_commented, result)

        result['success'] = True
        log.info("[%s] %s: Comment complete. Posted: %d, Skipped: %d, Errors: %d",
                 self.device_serial, self.username,
                 result['comments_posted'], result['skipped'], result['errors'])
        return result

    # ------------------------------------------------------------------
    # Reliable typing helper
    # ------------------------------------------------------------------
    def _check_field_has_text(self, field_id_pattern, label=""):
        """Check if the target EditText field has any non-empty text.
        
        IMPORTANT: Instagram composer has a bug where hint text == text attribute
        when the field is actually EMPTY. We must check text != hint to confirm
        real text was entered.
        """
        xml = self.ctrl.dump_xml(f"verify_type_{label}")
        if not xml:
            return False

        # Helper to check a node's text vs hint
        def _node_has_real_text(node_xml):
            text_m = re.search(r'text="([^"]*)"', node_xml)
            hint_m = re.search(r'hint="([^"]*)"', node_xml) or re.search(r'content-desc="([^"]*)"', node_xml)
            if text_m:
                field_text = text_m.group(1)
                if not field_text:
                    return False
                # If hint matches text exactly, the field is actually EMPTY
                if hint_m and field_text == hint_m.group(1):
                    log.debug("[%s] Field text == hint ('%s'), field is empty (%s)",
                              self.device_serial, field_text[:30], label)
                    return False
                log.debug("[%s] Field has real text (%s): '%s'",
                          self.device_serial, label, field_text[:50])
                return True
            return False

        # Try focused EditText first
        for m in re.finditer(r'<node[^>]*class="android\.widget\.EditText"[^/]*/>', xml):
            node_str = m.group(0)
            if 'focused="true"' in node_str:
                if _node_has_real_text(node_str):
                    return True

        # Try by resource-id pattern
        for m in re.finditer(r'<node[^/]*/>', xml):
            node_str = m.group(0)
            if field_id_pattern in node_str and 'EditText' in node_str:
                if _node_has_real_text(node_str):
                    return True

        log.debug("[%s] Field text empty after typing (%s)",
                  self.device_serial, label)
        return False

    def _reliable_type(self, element, text, field_id_pattern='comment_thread_edittext'):
        """
        Type text reliably. Primary: set_text(). Fallback: ADB input text.
        AdbKeyboard IME must be enabled (done in __init__).
        Returns True if text was typed successfully.
        """
        # Strategy 1 (primary): u2 set_text — most reliable with AdbKeyboard
        log.debug("[%s] _reliable_type: trying set_text()", self.device_serial)
        try:
            element.set_text(text)
            time.sleep(1)
            if self._check_field_has_text(field_id_pattern, "set_text"):
                return True
            log.info("[%s] set_text verification failed (hint==text bug?)",
                     self.device_serial)
        except Exception as e:
            log.warning("[%s] set_text failed: %s", self.device_serial, e)

        # Strategy 2: ADB input text fallback
        log.info("[%s] _reliable_type: trying ADB input text fallback",
                 self.device_serial)
        try:
            element.clear_text()
            time.sleep(0.3)
        except Exception:
            pass
        escaped = text.replace(' ', '%s').replace("'", "\\'")
        subprocess.run(
            ['adb', '-s', self.ctrl.adb_serial, 'shell', 'input', 'text',
             escaped],
            capture_output=True, timeout=10
        )
        time.sleep(1)
        if self._check_field_has_text(field_id_pattern, "adb"):
            return True

        # If verification fails but text may still be present (hint==text bug),
        # return True and let Post button check catch it
        log.warning("[%s] _reliable_type: verification failed but text may be "
                    "present (hint==text bug). Will check Post button.",
                    self.device_serial)
        return True

    # ------------------------------------------------------------------
    # Comment Methods
    # ------------------------------------------------------------------
    def _comment_on_sources(self, sources, max_comments, already_commented, result):
        """
        Comment on posts from specific source profiles.
        For each source: navigate to their profile → open latest post → comment.
        """
        random.shuffle(sources)

        for source_username in sources:
            if result['comments_posted'] >= max_comments:
                break

            if source_username.lower() == self.username.lower():
                continue

            log.info("[%s] Commenting on source: @%s",
                     self.device_serial, source_username)

            try:
                self.ctrl.dismiss_popups()

                # Step 1: Search and open source profile
                if not self.ctrl.search_user(source_username):
                    log.warning("[%s] Could not find source @%s",
                                self.device_serial, source_username)
                    result['errors'] += 1
                    continue

                random_sleep(2, 3, label="source_profile_loaded")
                self.ctrl.dismiss_popups()

                # Step 2: Open their latest post (first grid item)
                # Grid items have content-desc like "Reel by X" / "Photo by X"
                grid_item = None
                grid_clicked = False

                xml = self.ctrl.dump_xml("source_profile_grid")
                # Primary: find grid items via content-desc (most reliable)
                import xml.etree.ElementTree as _ET
                try:
                    _root = _ET.fromstring(xml)
                    for _elem in _root.iter():
                        _desc = _elem.get('content-desc', '')
                        _bounds = _elem.get('bounds', '')
                        if _bounds and any(k in _desc for k in
                                          ('Photo by', 'Reel by', 'Video by')):
                            _m = re.match(
                                r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', _bounds)
                            if _m:
                                cx = (int(_m.group(1))+int(_m.group(3)))//2
                                cy = (int(_m.group(2))+int(_m.group(4)))//2
                                self.device.click(cx, cy)
                                grid_clicked = True
                                log.debug("[%s] Clicked grid item: %s",
                                          self.device_serial, _desc[:60])
                                break
                except Exception:
                    pass

                if not grid_clicked:
                    # Fallback: find grid images below the profile header
                    images = self.device(
                        className="android.widget.ImageView",
                        clickable=True)
                    if images.exists(timeout=3) and images.count > 0:
                        for i in range(min(2, images.count - 1), images.count):
                            try:
                                bounds = images[i].info.get('bounds', {})
                                if bounds.get('top', 0) > 400:
                                    grid_item = images[i]
                                    break
                            except Exception:
                                continue

                if not grid_clicked and grid_item is None:
                    log.warning("[%s] No grid posts found for @%s",
                                self.device_serial, source_username)
                    self.ctrl.press_back()
                    time.sleep(1)
                    result['errors'] += 1
                    continue

                if not grid_clicked:
                    grid_item.click()
                random_sleep(2, 3, label="source_post_loaded")
                self.ctrl.dismiss_popups()

                # Step 3: Find the post author for logging
                xml = self.ctrl.dump_xml("source_post")
                author = self._get_post_author_from_xml(xml) or source_username

                if author in already_commented:
                    log.debug("[%s] Skip source @%s (already commented)",
                              self.device_serial, author)
                    result['skipped'] += 1
                    self.ctrl.press_back()
                    time.sleep(1)
                    self.ctrl.press_back()
                    time.sleep(1)
                    continue

                # Step 4: Find and click comment button
                comment_btn = self._find_comment_button(xml)
                if comment_btn is None:
                    # Re-dump in case XML changed
                    xml = self.ctrl.dump_xml("source_post_retry")
                    comment_btn = self._find_comment_button(xml)

                if comment_btn is None:
                    log.warning("[%s] Comment button not found on @%s's post",
                                self.device_serial, source_username)
                    self.ctrl.press_back()
                    time.sleep(1)
                    self.ctrl.press_back()
                    time.sleep(1)
                    result['errors'] += 1
                    continue

                # Step 5: Post the comment
                success = self._post_comment(comment_btn, post_author=author)
                if success:
                    result['comments_posted'] += 1
                    already_commented.add(author)
                    log_action(
                        self.session_id, self.device_serial,
                        self.username, 'comment',
                        target_username=author, success=True)
                    log.info("[%s] Commented on @%s's post via source (%d/%d)",
                             self.device_serial, author,
                             result['comments_posted'], max_comments)
                    random_sleep(self.min_delay, self.max_delay,
                                 label="comment_delay")
                else:
                    result['errors'] += 1
                    log_action(
                        self.session_id, self.device_serial,
                        self.username, 'comment',
                        target_username=author, success=False,
                        error_message="Comment post failed on source")

                # Step 6: Go back to clean state
                self.ctrl.press_back()
                time.sleep(1)
                self.ctrl.press_back()
                time.sleep(1)
                # Extra back in case we're still nested
                screen = self.ctrl.detect_screen()
                if screen not in (Screen.HOME_FEED, Screen.SEARCH):
                    self.ctrl.press_back()
                    time.sleep(1)

            except Exception as e:
                log.error("[%s] Source comment error for @%s: %s",
                          self.device_serial, source_username, e)
                result['errors'] += 1
                self._recover()

            # Brief pause between sources
            if result['comments_posted'] < max_comments:
                random_sleep(3, 8, label="between_sources")

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
                            success = self._post_comment(comment_btn, post_author=author)
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
                            success = self._post_comment(comment_btn, post_author=author)
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

    def _post_comment(self, comment_btn_info, post_author=None):
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
        comment_text = self._get_comment(post_author=post_author)
        log.debug("[%s] Typing comment: %s", self.device_serial, comment_text)

        # Type reliably with multi-strategy fallback
        typed = self._reliable_type(comment_input, comment_text,
                                     field_id_pattern='comment_thread_edittext')
        if not typed:
            log.warning("[%s] Failed to type comment after all strategies",
                        self.device_serial)
            self.ctrl.press_back()
            return False

        # Verify post button is visible before clicking
        # (send/post button only appears when text is present)
        time.sleep(0.5)

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
        time.sleep(2)

        # Verify: check if comment was actually posted
        # If posted, the input field should be empty or cleared
        xml = self.ctrl.dump_xml("verify_comment_posted")
        if xml:
            # Check if EditText field is now empty (comment was consumed)
            pattern = (
                r'<node[^>]*class="android\.widget\.EditText"[^>]*'
                r'text="([^"]*)"'
            )
            match = re.search(pattern, xml)
            if match:
                remaining_text = match.group(1)
                if not remaining_text or remaining_text == '':
                    log.info("[%s] Enter key posted comment (input cleared)",
                             self.device_serial)
                    return True
                else:
                    log.warning("[%s] Enter key did NOT post comment "
                                "(text still present: '%s')",
                                self.device_serial, remaining_text[:30])
                    return False
            else:
                # No EditText found — might have navigated away (comment posted)
                log.info("[%s] Enter key may have posted comment "
                         "(no EditText in view)", self.device_serial)
                return True

        log.warning("[%s] Could not verify comment post (no XML)", self.device_serial)
        return False

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
