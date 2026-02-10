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

        # Determine DM method
        dm_methods = self.settings.get('directmessage_method', {})

        if dm_methods.get('directmessage_specificuser'):
            targets = get_account_sources(self.account_id, 'dm_targets')
            if targets:
                self._dm_specific_users(
                    targets, target, recently_dmed, result)
            else:
                log.warning("[%s] No DM targets configured",
                           self.device_serial)
        elif dm_methods.get('directmessage_new_followers'):
            self._dm_new_followers(target, recently_dmed, result)
        else:
            # Default: try specific users first, then new followers
            targets = get_account_sources(self.account_id, 'dm_targets')
            if targets:
                self._dm_specific_users(
                    targets, target, recently_dmed, result)
            else:
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
            # Navigate to own profile -> followers list
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
                # Some profiles show "Following" with Message as a second button
                msg_btn = self.device(textContains="Message")
                if not msg_btn.exists(timeout=2):
                    log.warning("[%s] Message button not found for @%s",
                               self.device_serial, target_username)
                    self.ctrl.press_back()
                    return False

            msg_btn.click()
            random_sleep(2, 4, label="dm_thread_loaded")

            # Dismiss any popups in the thread
            self.ctrl.dismiss_popups()

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
                for line in lines:
                    self._type_and_send_in_thread(line.strip())
                    random_sleep(1, 3, label="between_lines")
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

    def _type_and_send_in_thread(self, text):
        """
        Type a message in the DM thread composer and send it.
        Returns True on success.
        """
        # Find thread composer input
        msg_input = self.ctrl.find_element(
            resource_id='row_thread_composer_edittext', timeout=3)
        if msg_input is None:
            # Fallback: any EditText in the thread
            msg_input = self.ctrl.find_element(
                class_name='android.widget.EditText', timeout=3)
        if msg_input is None:
            # Try by hint text
            msg_input = self.device(textContains="Message")
            if not msg_input.exists(timeout=2):
                log.warning("[%s] DM input field not found",
                           self.device_serial)
                # Dump XML for debugging
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

        # Type via ADB for reliability (handles special chars better)
        escaped = text.replace(' ', '%s').replace("'", "\\'")
        subprocess.run(
            ['adb', '-s', self.ctrl.adb_serial, 'shell', 'input', 'text',
             escaped],
            capture_output=True, timeout=10
        )
        time.sleep(1)

        # Click send button
        send_btn = self.ctrl.find_element(
            resource_id='row_thread_composer_send_button_icon', timeout=3)
        if send_btn is None:
            send_btn = self.ctrl.find_element(
                resource_id='row_thread_composer_send_button_container', timeout=2)
        if send_btn is None:
            send_btn = self.ctrl.find_element(desc="Send", timeout=2)
        if send_btn is None:
            send_btn = self.ctrl.find_element(text="Send", timeout=2)

        if send_btn is None:
            log.warning("[%s] DM send button not found", self.device_serial)
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
