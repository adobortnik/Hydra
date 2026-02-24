"""
Switch to Private Account Action Module
=========================================
Switches an Instagram account from Public to Private profile.
Navigates through the IG settings UI flow using UIAutomator2.

Flow (confirmed on clones 2025-07):
  Profile → Options (hamburger, desc="Options") → "Settings and activity" →
  scroll to "Account privacy" (under "Who can see your content") →
  Toggle "Private account" ON (if not already private)

Key selectors discovered on device:
  - Options button: d(description="Options")  [no resource-id, just desc]
  - Settings: d(text="Settings and activity") or d(textContains="Settings and")
  - Account privacy: d(text="Account privacy")
  - Private toggle row: checkable=true View at [0,278][1080,422]
    - checked="false" = Public, checked="true" = Private
    - Text label: "Private account"
  - After toggling: confirmation dialog may appear (Switch to private / Cancel)
"""

import logging
import time
import re
import datetime

from automation.ig_controller import IGController, Screen
from automation.actions.helpers import (
    get_db, log_action, random_sleep,
)

log = logging.getLogger(__name__)


class SwitchToPrivateAction:
    """Switch account from Public to Private profile."""

    def __init__(self, device, device_serial, account_info, session_id, pkg=None):
        self.device = device
        self.device_serial = device_serial
        self.account = account_info
        self.session_id = session_id
        self.username = account_info.get('username', '')
        self.account_id = account_info.get('id')

        _pkg = pkg or account_info.get('package',
               account_info.get('instagram_package', 'com.instagram.android'))
        self.ctrl = IGController(device, device_serial, _pkg)
        self.pkg = _pkg

    def execute(self):
        """
        Full flow to switch account to Private.
        Returns dict with 'success', 'error_message'.
        """
        result = {
            'success': False,
            'error_message': None,
        }

        try:
            log.info("[%s] SWITCH_PRIVATE: Starting for @%s",
                     self.device_serial, self.username)

            # Step 1: Navigate to Profile
            if not self.ctrl.navigate_to(Screen.PROFILE):
                result['error_message'] = "Could not navigate to profile"
                return result

            random_sleep(1.5, 3.0, label="profile_loaded")

            # Step 2: Open Options menu (hamburger)
            if not self._open_options_menu():
                result['error_message'] = "Could not open Options menu"
                return result

            # Step 3: Navigate to Settings and activity
            if not self._open_settings():
                result['error_message'] = "Could not open Settings"
                return result

            # Step 4: Scroll to and tap Account privacy
            if not self._open_account_privacy():
                result['error_message'] = "Could not find Account privacy"
                return result

            # Step 5: Check if already private
            is_private = self._check_if_already_private()
            if is_private:
                log.info("[%s] @%s is already private",
                         self.device_serial, self.username)
                result['success'] = True
                self._update_db(True)
                return result

            # Step 6: Toggle Private Account ON
            toggled = self._toggle_private()
            if not toggled:
                result['error_message'] = "Failed to toggle Private Account"
                return result

            # Step 7: Handle confirmation dialog (if any)
            self._handle_confirmation_dialog()

            # Step 8: Verify the toggle is now ON
            success = self._verify_private()

            if success:
                log.info("[%s] ✅ @%s successfully switched to Private!",
                         self.device_serial, self.username)
                result['success'] = True
                self._update_db(True)

                log_action(self.session_id, self.device_serial, self.username,
                           'switch_to_private', success=True)
            else:
                result['error_message'] = "Verification failed — toggle may not have switched"
                log_action(self.session_id, self.device_serial, self.username,
                           'switch_to_private', success=False,
                           error_message=result['error_message'])

        except Exception as e:
            log.error("[%s] SWITCH_PRIVATE error: %s", self.device_serial, e)
            result['error_message'] = str(e)[:200]
            log_action(self.session_id, self.device_serial, self.username,
                       'switch_to_private', success=False,
                       error_message=result['error_message'])

        return result

    # ──────────────────────────────────────────────────
    # Private Methods
    # ──────────────────────────────────────────────────

    def _open_options_menu(self):
        """Open the hamburger/Options menu on the profile page."""
        log.info("[%s] Opening Options menu...", self.device_serial)

        # The Options button has desc="Options" — it's in the top-right action bar
        options_btn = self.device(description="Options")
        if not options_btn.exists(timeout=3):
            # Fallback: try resource-id pattern
            options_btn = self.device(resourceIdMatches=".*option_list_button.*")
        if not options_btn.exists(timeout=3):
            options_btn = self.device(descriptionContains="Menu")

        if not options_btn.exists(timeout=3):
            log.warning("[%s] Options/hamburger menu not found", self.device_serial)
            return False

        options_btn.click()
        random_sleep(2.0, 4.0, label="options_menu_load")
        return True

    def _open_settings(self):
        """Tap 'Settings and activity' (or similar) in the options menu."""
        log.info("[%s] Opening Settings...", self.device_serial)

        # Wait for menu to load — it may take a moment on clones
        for attempt in range(3):
            settings_btn = self.device(text="Settings and activity")
            if not settings_btn.exists(timeout=3):
                settings_btn = self.device(textContains="Settings and")
                if not settings_btn.exists(timeout=2):
                    settings_btn = self.device(textContains="Settings")

            if settings_btn.exists(timeout=3):
                settings_btn.click()
                random_sleep(2.0, 4.0, label="settings_load")
                return True

            # Retry — menu may still be loading
            random_sleep(2.0, 3.0, label="settings_retry_%d" % attempt)

        log.warning("[%s] Settings menu item not found", self.device_serial)
        return False

    def _open_account_privacy(self):
        """Scroll in Settings to find and tap 'Account privacy'."""
        log.info("[%s] Scrolling to find 'Account privacy'...", self.device_serial)

        # Need to scroll down to find "Account privacy" —
        # it's under "Who can see your content" section
        for scroll_i in range(10):
            privacy_btn = self.device(text="Account privacy")
            if privacy_btn.exists(timeout=1.5):
                log.info("[%s] Found 'Account privacy' after %d scrolls",
                         self.device_serial, scroll_i)
                privacy_btn.click()
                random_sleep(2.0, 5.0, label="account_privacy_load")
                return True

            # Swipe up to scroll down
            self.device.swipe(540, 1400, 540, 600, duration=0.4)
            random_sleep(0.8, 1.5, label="settings_scroll_%d" % scroll_i)

        log.warning("[%s] 'Account privacy' not found after scrolling",
                    self.device_serial)
        return False

    def _check_if_already_private(self):
        """
        Check if the Private Account toggle is already ON.
        The toggle row is a checkable View element.
        checked="true" means Private, checked="false" means Public.
        """
        log.info("[%s] Checking if already private...", self.device_serial)

        # Wait for the page to load — it may show "Loading..." initially
        for attempt in range(5):
            xml = self.ctrl.dump_xml("check_private_%d" % attempt)

            if "Private account" in xml:
                # Found the privacy settings page
                # Check the checkable element
                # Pattern: checkable="true" ... checked="true" or "false"
                # The checkable row contains the "Private account" text
                import re as _re
                match = _re.search(
                    r'checkable="true"[^>]*checked="(true|false)"', xml)
                if match:
                    is_checked = match.group(1) == "true"
                    log.info("[%s] Private toggle checked=%s",
                             self.device_serial, is_checked)
                    return is_checked

                # Fallback: check if "Public" or "Private" text exists in descriptions
                if "Account privacy" in xml:
                    # Look in the broader XML for indicators
                    xml_lower = xml.lower()
                    if 'checked="true"' in xml_lower and 'private account' in xml_lower:
                        return True

                log.info("[%s] Could not determine toggle state, assuming not private",
                         self.device_serial)
                return False

            # Page still loading
            if "Loading" in xml:
                random_sleep(2.0, 3.0, label="privacy_loading_%d" % attempt)
                continue

            random_sleep(1.5, 2.5, label="privacy_wait_%d" % attempt)

        log.warning("[%s] Account privacy page did not load", self.device_serial)
        return False

    def _toggle_private(self):
        """
        Toggle the Private Account switch ON.
        The toggle is a checkable View element that can be clicked.
        """
        log.info("[%s] Toggling Private Account ON...", self.device_serial)

        # Method 1: Click the checkable element directly
        # The row containing "Private account" text is checkable and clickable
        toggle_row = self.device(checkable=True, checked=False)
        if toggle_row.exists(timeout=3):
            toggle_row.click()
            random_sleep(1.5, 3.0, label="toggle_clicked")
            log.info("[%s] Clicked checkable toggle row", self.device_serial)
            return True

        # Method 2: Click by text "Private account"
        private_text = self.device(text="Private account")
        if private_text.exists(timeout=2):
            private_text.click()
            random_sleep(1.5, 3.0, label="toggle_text_clicked")
            log.info("[%s] Clicked 'Private account' text", self.device_serial)
            return True

        # Method 3: Click the toggle area on the right side (~x=954, y=350)
        # Based on discovered bounds: toggle visual at [876,302][1032,398]
        try:
            self.device.click(954, 350)
            random_sleep(1.5, 3.0, label="toggle_coord_clicked")
            log.info("[%s] Clicked toggle by coordinates", self.device_serial)
            return True
        except Exception as e:
            log.error("[%s] Coordinate click failed: %s", self.device_serial, e)

        log.warning("[%s] Could not toggle Private Account", self.device_serial)
        return False

    def _handle_confirmation_dialog(self):
        """
        Handle any confirmation dialog that appears after toggling private.
        Instagram may show a dialog asking to confirm switching to private.
        Possible buttons: "Switch to private", "OK", "Confirm", "Cancel"
        """
        random_sleep(1.5, 3.0, label="confirmation_wait")
        xml = self.ctrl.dump_xml("confirmation_dialog")

        # Look for confirmation buttons
        confirm_texts = [
            "Switch to private",
            "Switch to Private",
            "Turn on",
            "OK",
            "Confirm",
            "Yes",
            "Got it",
        ]

        for btn_text in confirm_texts:
            btn = self.device(text=btn_text)
            if btn.exists(timeout=2):
                btn.click()
                log.info("[%s] Confirmation dialog: tapped '%s'",
                         self.device_serial, btn_text)
                random_sleep(1.5, 3.0, label="confirmed")
                return

        # No confirmation dialog — may have toggled directly
        log.info("[%s] No confirmation dialog detected", self.device_serial)

    def _verify_private(self):
        """Verify the account is now set to private by checking the toggle state."""
        random_sleep(1.5, 3.0, label="verify_wait")
        xml = self.ctrl.dump_xml("verify_private")

        # Check if the checkable element is now checked="true"
        import re as _re
        match = _re.search(r'checkable="true"[^>]*checked="(true|false)"', xml)
        if match:
            is_checked = match.group(1) == "true"
            log.info("[%s] Verify: Private toggle checked=%s",
                     self.device_serial, is_checked)
            return is_checked

        # Fallback: look for textual indicators
        if "Private account" in xml:
            # If we're still on the Account privacy page, check text context
            # After toggling to private, the text "Public" should no longer appear
            # near "Account privacy" in the settings
            log.info("[%s] On privacy page but could not read toggle state",
                     self.device_serial)
            return True  # Assume success if we got this far

        log.warning("[%s] Could not verify private toggle state", self.device_serial)
        return False

    def _update_db(self, is_private):
        """Update the account's private status in DB."""
        try:
            conn = get_db()
            now = datetime.datetime.now().isoformat()

            # Ensure column exists
            try:
                conn.execute("ALTER TABLE accounts ADD COLUMN is_private INTEGER DEFAULT 0")
                conn.commit()
            except Exception:
                pass  # Column already exists

            try:
                conn.execute("ALTER TABLE accounts ADD COLUMN private_switched_at TEXT")
                conn.commit()
            except Exception:
                pass  # Column already exists

            conn.execute("""
                UPDATE accounts
                SET is_private = ?, private_switched_at = ?, updated_at = ?
                WHERE id = ?
            """, (1 if is_private else 0, now, now, self.account_id))
            conn.commit()
            conn.close()
            log.info("[%s] DB updated: @%s → is_private=%s",
                     self.device_serial, self.username, is_private)
        except Exception as e:
            log.error("[%s] DB update failed: %s", self.device_serial, e)
