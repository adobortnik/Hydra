"""
DM (Direct Message) Action Module — IGController Edition
==========================================================
Send direct messages on Instagram using XML-based UI control.

Modes:
- Specific users: DM a list of usernames
- New followers: DM users who recently followed

Supports:
- Spintax in message templates ({Hi|Hey|Hello} there!)
- Per-line sending (each line as separate message bubble)
- Rate limiting per day
- Template messages from account_text_configs (pm_list)

Discovered Resource IDs (com.instagram.androie):
- DM inbox button: action_bar_inbox_button
- DM thread list: inbox_refreshable_thread_list_recyclerview
- New message: desc="New Message" (pencil icon)
- Thread composer input: row_thread_composer_edittext
- Thread send button: row_thread_composer_send_button_icon (or content-desc="Send")
- Message button on profile: text="Message"
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
# Spintax support: {Hi|Hey|Hello} -> random pick
# ---------------------------------------------------------------------------
def _process_spintax(text):
    """Process spintax: {option1|option2|option3} -> random pick."""
    def _replace(match):
        options = match.group(1).split('|')
        return random.choice(options).strip()
    return re.sub(r'\{([^}]+)\}', _replace, text)


class DMAction:
    """
    Send direct messages on Instagram.
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
        self._load_messages()

    def _init_limits(self):
        """Initialize DM limits from account settings."""
        self.daily_limit = int(self.settings.get('directmessage_daily_limit', '20'))
        if self.daily_limit <= 0:
            self.daily_limit = 20

        min_dm = int(self.settings.get('directmessage_min', '3'))
        max_dm = int(self.settings.get('directmessage_max', '5'))
        if min_dm <= 0:
            min_dm = 2
        if max_dm <= 0:
            max_dm = 5
        if min_dm > max_dm:
            min_dm, max_dm = max_dm, min_dm
        self.session_target = random.randint(min_dm, max_dm)

        self.min_delay = int(self.settings.get('directmessage_min_delay', '10'))
        self.max_delay = int(self.settings.get('directmessage_max_delay', '30'))
        if self.min_delay < 5:
            self.min_delay = 5
        if self.max_delay < self.min_delay:
            self.max_delay = self.min_delay + 10

        self.send_per_line = self.settings.get(
            'enable_send_message_every_new_line', False)

        log.info("[%s] DM limits: daily=%d, session_target=%d, delay=%d-%ds",
                 self.device_serial, self.daily_limit, self.session_target,
                 self.min_delay, self.max_delay)

    def _load_messages(self):
        """Load message templates from DB (account_text_configs.pm_list)."""
        self.message_templates = []
        try:
            conn = get_db()
            row = conn.execute("""
                SELECT content FROM account_text_configs
                WHERE account_id=? AND config_type='pm_list'
            """, (self.account_id,)).fetchone()
            conn.close()

            if row and row['content']:
                lines = [l.strip() for l in row['content'].split('\n')
                         if l.strip()]
                self.message_templates = lines
        except Exception as e:
            log.error("[%s] Failed to load DM templates: %s",
                      self.device_serial, e)

        if not self.message_templates:
            self.message_templates = [
                "Hey! {Love|Really like} your content! {🔥|✨|🙌}",
                "{Hi|Hey} there! Just discovered your page, {great stuff|amazing content}! 🙌",
                "{Hey|Hello}! Your posts are {amazing|awesome|incredible}! Keep it up! ✨",
            ]

        log.info("[%s] Loaded %d DM templates",
                 self.device_serial, len(self.message_templates))

    def _get_message(self):
        """Get a random message with spintax resolved."""
        template = random.choice(self.message_templates)
        return _process_spintax(template)

    # ------------------------------------------------------------------
    # Main execute
    # ------------------------------------------------------------------
    def execute(self):
        """
        Execute the DM action.
        Returns dict: {success, dms_sent, errors, skipped}
        """
        result = {
            'success': False,
            'dms_sent': 0,
            'errors': 0,
            'skipped': 0,
        }

        # Ensure Instagram is running
        self.ctrl.ensure_app()
        self.ctrl.dismiss_popups()

        # Check daily limit
        done_today = get_today_action_count(
            self.device_serial, self.username, 'dm')
        remaining = self.daily_limit - done_today
        if remaining <= 0:
            log.info("[%s] %s: Daily DM limit reached (%d/%d)",
                     self.device_serial, self.username,
                     done_today, self.daily_limit)
            result['success'] = True
            return result

        target = min(self.session_target, remaining)
        log.info("[%s] %s: Will send up to %d DMs (done today: %d, daily limit: %d)",
                 self.device_serial, self.username, target,
                 done_today, self.daily_limit)

        recently_dmed = get_recently_interacted(
            self.device_serial, self.username, 'dm', days=30)
        log.info("[%s] Recently DMed: %d users (will skip)",
                 self.device_serial, len(recently_dmed))

        # Determine DM method — can be a string ("directmessage_specificuser")
        # or a dict ({"directmessage_specificuser": true}) depending on dashboard version
        dm_methods_raw = self.settings.get('directmessage_method', '')
        if isinstance(dm_methods_raw, str):
            # Convert string value to dict for uniform handling
            dm_methods = {dm_methods_raw: True} if dm_methods_raw else {}
        else:
            dm_methods = dm_methods_raw or {}

        # Dashboard sends: "dm-specific-users" or "dm-new-followers"
        # Legacy values: "directmessage_specificuser" / "directmessage_new_followers"
        method_str = dm_methods_raw if isinstance(dm_methods_raw, str) else ''
        is_specific = (method_str in ('dm-specific-users', 'directmessage_specificuser')
                       or dm_methods.get('directmessage_specificuser')
                       or dm_methods.get('dm-specific-users'))

        if is_specific:
            targets = get_account_sources(self.account_id, 'dm_targets')
            if targets:
                self._dm_specific_users(
                    targets, target, recently_dmed, result)
            else:
                log.warning("[%s] Specific users selected but no DM targets "
                            "configured — falling back to new followers",
                            self.device_serial)
                self._dm_new_followers(target, recently_dmed, result)
        else:
            # Default: new followers
            self._dm_new_followers(target, recently_dmed, result)

        result['success'] = True
        log.info("[%s] %s: DM complete. Sent: %d, Skipped: %d, Errors: %d",
                 self.device_serial, self.username,
                 result['dms_sent'], result['skipped'], result['errors'])
        return result

    # ------------------------------------------------------------------
    # DM Methods
    # ------------------------------------------------------------------
    def _dm_specific_users(self, targets, max_dms, already_dmed, result):
        """Send DMs to a list of specific usernames."""
        random.shuffle(targets)

        for target_user in targets:
            if result['dms_sent'] >= max_dms:
                break

            if target_user in already_dmed:
                log.debug("[%s] Skip DM @%s (recently messaged)",
                         self.device_serial, target_user)
                result['skipped'] += 1
                continue

            # Skip own username
            if target_user.lower() == self.username.lower():
                continue

            try:
                self.ctrl.dismiss_popups()
                success = self._send_dm_to_user(target_user)
                if success:
                    result['dms_sent'] += 1
                    already_dmed.add(target_user)
                    log_action(
                        self.session_id, self.device_serial, self.username,
                        'dm', target_username=target_user, success=True)
                    log.info("[%s] DM sent to @%s (%d/%d)",
                            self.device_serial, target_user,
                            result['dms_sent'], max_dms)
                    random_sleep(self.min_delay, self.max_delay,
                                label="dm_delay")
                else:
                    result['errors'] += 1
                    log_action(
                        self.session_id, self.device_serial, self.username,
                        'dm', target_username=target_user, success=False,
                        error_message="DM send failed")
            except Exception as e:
                log.error("[%s] DM error for @%s: %s",
                         self.device_serial, target_user, e)
                result['errors'] += 1
                self._recover()

            # Pause between DMs
            if result['dms_sent'] < max_dms:
                random_sleep(3, 8, label="between_dms")

    def _dm_new_followers(self, max_dms, already_dmed, result):
        """
        DM new followers by:
        1. Navigate to own profile
        2. Open followers list
        3. Pick users not yet DMed
        """
        try:
            # Navigate to own profile -> followers list (with retry)
            if not self.ctrl.navigate_to(Screen.PROFILE):
                # Retry: dismiss popups, try again
                self.ctrl.dismiss_popups()
                time.sleep(1)
                self.ctrl.ensure_app()
                time.sleep(2)
                if not self.ctrl.navigate_to(Screen.PROFILE):
                    log.warning("[%s] Could not navigate to profile for DM",
                               self.device_serial)
                    result['errors'] += 1
                    return

            random_sleep(1, 2)

            if not self.ctrl.open_followers():
                log.warning("[%s] Could not open followers list for DM",
                           self.device_serial)
                self.ctrl.press_back()
                result['errors'] += 1
                return

            random_sleep(2, 4, label="followers_loaded")

            # Get visible usernames
            scroll_attempts = 0
            max_scrolls = 5
            followers = []
            seen = set()

            while scroll_attempts < max_scrolls and len(followers) < max_dms * 3:
                users = self.ctrl.get_visible_usernames_in_list()
                new_users = [u for u in users if u not in seen
                            and u not in already_dmed
                            and u.lower() != self.username.lower()]
                followers.extend(new_users)
                seen.update(users)

                if not new_users:
                    scroll_attempts += 1

                self.ctrl.scroll_list("down")
                random_sleep(1, 2)

            # Go back from followers list
            self.ctrl.press_back()
            time.sleep(1)
            self.ctrl.press_back()
            time.sleep(1)

            log.info("[%s] Found %d new followers to DM",
                     self.device_serial, len(followers))

            random.shuffle(followers)

            for target_user in followers[:max_dms]:
                if result['dms_sent'] >= max_dms:
                    break

                try:
                    self.ctrl.dismiss_popups()
                    success = self._send_dm_to_user(target_user)
                    if success:
                        result['dms_sent'] += 1
                        already_dmed.add(target_user)
                        log_action(
                            self.session_id, self.device_serial, self.username,
                            'dm', target_username=target_user, success=True)
                        log.info("[%s] DM sent to follower @%s (%d/%d)",
                                self.device_serial, target_user,
                                result['dms_sent'], max_dms)
                        random_sleep(self.min_delay, self.max_delay,
                                    label="dm_delay")
                    else:
                        result['errors'] += 1
                except Exception as e:
                    log.error("[%s] DM error for @%s: %s",
                             self.device_serial, target_user, e)
                    result['errors'] += 1
                    self._recover()

        except Exception as e:
            log.error("[%s] DM new followers error: %s",
                     self.device_serial, e)
            result['errors'] += 1

    # ------------------------------------------------------------------
    # Core DM sending
    # ------------------------------------------------------------------
    def _send_dm_to_user(self, target_username):
        """
        Navigate to a user's profile and send them a DM.

        Flow:
        1. Search and open user profile
        2. Click "Message" button
        3. Type message in thread composer
        4. Click send

        Returns True on success.
        """
        try:
            # Search and open the user's profile
            if not self.ctrl.search_user(target_username):
                log.warning("[%s] Could not find @%s for DM",
                           self.device_serial, target_username)
                return False

            random_sleep(2, 3, label="profile_loaded")
            self.ctrl.dismiss_popups()

            # Click the "Message" button on their profile
            msg_btn = self.ctrl.find_element(text="Message", timeout=3)
            if msg_btn is None:
                msg_btn = self.ctrl.find_element(desc="Message", timeout=2)
            if msg_btn is None:
                # Try scrolling profile down slightly (button may be off-screen)
                try:
                    w, h = self.device.window_size()
                    self.device.swipe(w // 2, int(h * 0.5), w // 2,
                                      int(h * 0.35), duration=0.3)
                    time.sleep(1)
                except Exception:
                    pass
                msg_btn = self.ctrl.find_element(text="Message", timeout=2)
            if msg_btn is None:
                msg_btn = self.device(textContains="Message")
                if not msg_btn.exists(timeout=2):
                    log.warning("[%s] Message button not found for @%s",
                               self.device_serial, target_username)
                    self.ctrl.dump_xml("dm_no_message_btn")
                    self.ctrl.press_back()
                    return False

            msg_btn.click()
            random_sleep(2, 4, label="dm_thread_loaded")

            # Dismiss any popups in the DM thread
            for _ in range(3):
                popup = self.ctrl.detect_screen()
                if popup == Screen.POPUP:
                    self.ctrl.dismiss_popups()
                    time.sleep(1)
                else:
                    break

            # Handle "Can't message this account" or restricted screens
            xml = self.ctrl.dump_xml("dm_thread_check")
            if xml and ("can't send" in xml.lower() or "restrict" in xml.lower()
                        or "unavailable" in xml.lower()):
                log.warning("[%s] Can't DM @%s (restricted/unavailable)",
                            self.device_serial, target_username)
                self.ctrl.press_back()
                time.sleep(1)
                return False

            # Verify we're in a DM thread
            screen = self.ctrl.detect_screen()
            if screen == Screen.POPUP:
                self.ctrl.dismiss_popups()
                time.sleep(1)

            # Get message text
            message = self._get_message()

            # Send message(s)
            if self.send_per_line:
                lines = [l for l in message.split('\n') if l.strip()]
                all_lines_ok = True
                for line in lines:
                    line_ok = self._type_and_send_in_thread(line.strip())
                    if not line_ok:
                        log.warning("[%s] send_per_line: failed on line: %s",
                                    self.device_serial, line[:40])
                        all_lines_ok = False
                        break
                    random_sleep(1, 3, label="between_lines")
                if not all_lines_ok:
                    self.ctrl.press_back()
                    time.sleep(1)
                    return False
            else:
                success = self._type_and_send_in_thread(message)
                if not success:
                    self.ctrl.press_back()
                    time.sleep(1)
                    return False

            # Go back to clean state
            self.ctrl.press_back()
            time.sleep(1)
            self.ctrl.press_back()
            time.sleep(1)

            return True

        except Exception as e:
            log.error("[%s] Send DM error for @%s: %s",
                     self.device_serial, target_username, e)
            try:
                self.ctrl.press_back()
                time.sleep(0.5)
                self.ctrl.press_back()
            except Exception:
                pass
            return False

    def _check_field_has_text(self, field_id_pattern, label=""):
        """Check if the target EditText field has any non-empty text.
        
        IMPORTANT: Instagram DM composer has a bug where hint text == text attribute
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
        focused_pattern = (
            r'<node[^>]*class="android\.widget\.EditText"[^>]*focused="true"[^/]*/>'
            r'|<node[^>]*focused="true"[^>]*class="android\.widget\.EditText"[^/]*/>'
        )
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

    def _reliable_type(self, element, text, field_id_pattern='composer_edittext'):
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
            log.info("[%s] set_text verification failed (hint==text bug?), "
                     "skipping verification — text likely entered OK",
                     self.device_serial)
            # Even if verification fails due to hint==text bug,
            # we'll check for send button appearance as final verification
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

        # If both strategies failed verification but text may still be there
        # (hint==text bug), return True and let send button check catch it
        log.warning("[%s] _reliable_type: verification failed but text may be "
                    "present (hint==text bug). Will check send button.",
                    self.device_serial)
        return True

    def _find_send_button(self):
        """Find the DM send button. Returns element or None."""
        send_btn = self.ctrl.find_element(
            resource_id='row_thread_composer_send_button_icon', timeout=2)
        if send_btn is None:
            send_btn = self.ctrl.find_element(
                resource_id='row_thread_composer_send_button_container', timeout=1)
        if send_btn is None:
            send_btn = self.ctrl.find_element(desc="Send", timeout=1)
        if send_btn is None:
            send_btn = self.ctrl.find_element(text="Send", timeout=1)
        return send_btn

    def _type_and_send_in_thread(self, text):
        """
        Type a message in the DM thread composer and send it.
        Returns True on success.
        """
        # Find thread composer input
        msg_input = self.ctrl.find_element(
            resource_id='row_thread_composer_edittext', timeout=3)
        if msg_input is None:
            msg_input = self.ctrl.find_element(
                class_name='android.widget.EditText', timeout=3)
        if msg_input is None:
            msg_input = self.device(textContains="Message")
            if not msg_input.exists(timeout=2):
                log.warning("[%s] DM input field not found",
                           self.device_serial)
                self.ctrl.dump_xml("dm_input_not_found")
                return False

        msg_input.click()
        time.sleep(0.5)

        # Clear any existing text
        try:
            msg_input.clear_text()
            time.sleep(0.3)
        except Exception:
            pass

        # Type with primary method: set_text
        log.debug("[%s] Typing DM: %s", self.device_serial, text[:50])
        try:
            msg_input.set_text(text)
            time.sleep(1)
        except Exception as e:
            log.warning("[%s] set_text failed: %s", self.device_serial, e)

        # Verify: send button should appear if text was entered
        send_btn = self._find_send_button()
        if send_btn is None:
            # Text likely didn't enter — retry with ADB input text
            log.info("[%s] Send button not found after set_text, retrying with ADB input",
                     self.device_serial)
            try:
                msg_input.click()
                time.sleep(0.3)
                msg_input.clear_text()
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
            send_btn = self._find_send_button()

        if send_btn is None:
            log.warning("[%s] DM send button not found after both typing methods",
                        self.device_serial)
            self.ctrl.dump_xml("dm_send_btn_not_found")
            return False

        send_btn.click()
        time.sleep(2)
        log.info("[%s] DM message sent", self.device_serial)
        return True

    # ------------------------------------------------------------------
    # DM Inbox approach (alternative)
    # ------------------------------------------------------------------
    def navigate_to_dm_inbox(self):
        """
        Navigate to the DM inbox from any screen.
        Returns True if on DM inbox.
        """
        # First go to home feed
        if not self.ctrl.navigate_to(Screen.HOME_FEED):
            return False

        time.sleep(1)

        # Click DM inbox button
        dm_btn = self.ctrl.find_element(
            resource_id='action_bar_inbox_button', timeout=3)
        if dm_btn is None:
            dm_btn = self.ctrl.find_element(desc="Direct", timeout=2)
        if dm_btn is None:
            dm_btn = self.ctrl.find_element(
                desc="Messenger", timeout=2)

        if dm_btn is None:
            log.warning("[%s] DM inbox button not found",
                       self.device_serial)
            return False

        dm_btn.click()
        time.sleep(3)

        # Verify
        screen = self.ctrl.detect_screen()
        if screen == Screen.DM_INBOX:
            log.info("[%s] Navigated to DM inbox", self.device_serial)
            return True

        # Might have a popup
        if screen == Screen.POPUP:
            self.ctrl.dismiss_popups()
            time.sleep(1)
            screen = self.ctrl.detect_screen()
            if screen == Screen.DM_INBOX:
                return True

        log.warning("[%s] Expected DM_INBOX, got %s",
                   self.device_serial, screen.value)
        return False

    # ------------------------------------------------------------------
    # Recovery
    # ------------------------------------------------------------------
    def _recover(self):
        """Try to recover to a known UI state."""
        try:
            self.ctrl.recover_to_home()
        except Exception:
            pass


def execute_dm(device, device_serial, account_info, session_id):
    """Convenience function to run DM action."""
    action = DMAction(device, device_serial, account_info, session_id)
    return action.execute()
