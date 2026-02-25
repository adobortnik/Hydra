"""
Set Profile Name Action Module
================================
Sets or updates the display name on an Instagram profile.

Flow (confirmed on clones 2025-02):
  Profile → Edit Profile → Name field (full_name) → clear + type → Back (auto-saves)

Key selectors discovered on device (package-agnostic via resourceIdMatches):
  - Edit profile button: d(text="Edit profile")
  - Name field container: d(resourceIdMatches=".*:id/full_name")
  - Inside: prism_form_field_container → EditText (NAF=true)
  - Back button: d(resourceIdMatches=".*action_bar_button_back") desc="Back"
  - Edit profile saves automatically when navigating back
"""

import logging
import time
import subprocess
import datetime

from automation.ig_controller import IGController, Screen
from automation.actions.helpers import (
    get_db, log_action, random_sleep,
)

log = logging.getLogger(__name__)


class SetProfileNameAction:
    """Set or update the display name on an Instagram profile."""

    def __init__(self, device, device_serial, account_info, session_id,
                 pkg=None, name=None):
        """
        Args:
            device: uiautomator2 device object
            device_serial: e.g. '10.1.11.4_5555'
            account_info: dict with 'username', 'id', etc.
            session_id: current session ID
            pkg: IG clone package name
            name: display name to set (e.g. 'John Smith')
        """
        self.device = device
        self.device_serial = device_serial
        self.account = account_info
        self.session_id = session_id
        self.username = account_info.get('username', '')
        self.account_id = account_info.get('id')
        self.name = name

        _pkg = pkg or account_info.get('package',
               account_info.get('instagram_package', 'com.instagram.android'))
        self.ctrl = IGController(device, device_serial, _pkg)
        self.pkg = _pkg
        self.adb_serial = device_serial.replace('_', ':')

    def execute(self):
        """
        Full flow to set/update profile display name.
        Returns dict with 'success', 'error_message'.
        """
        result = {
            'success': False,
            'error_message': None,
        }

        if not self.name:
            result['error_message'] = "No name provided"
            return result

        try:
            log.info("[%s] SET_PROFILE_NAME: Starting for @%s — name='%s'",
                     self.device_serial, self.username, self.name)

            # Step 1: Navigate to Profile
            if not self._navigate_to_profile():
                result['error_message'] = "Could not navigate to profile"
                return result

            # Step 2: Open Edit Profile
            if not self._open_edit_profile():
                result['error_message'] = "Could not open Edit Profile"
                return result

            # Step 3: Click on Name field and edit it
            if not self._set_name_field():
                result['error_message'] = "Could not set name field"
                return result

            # Step 4: Go back (auto-saves on Instagram)
            self._navigate_back_to_profile()

            # Update DB
            self._update_db()

            log.info("[%s] SET_PROFILE_NAME: Successfully set name for @%s to '%s'",
                     self.device_serial, self.username, self.name)
            result['success'] = True

            log_action(self.session_id, self.device_serial, self.username,
                       'set_profile_name', success=True)

        except Exception as e:
            log.error("[%s] SET_PROFILE_NAME error: %s",
                      self.device_serial, e, exc_info=True)
            result['error_message'] = str(e)[:200]
            log_action(self.session_id, self.device_serial, self.username,
                       'set_profile_name', success=False,
                       error_message=result['error_message'])

        return result

    # ──────────────────────────────────────────────────
    # Private Methods
    # ──────────────────────────────────────────────────

    def _navigate_to_profile(self):
        """Navigate to the profile tab."""
        nav_ok = self.ctrl.navigate_to(Screen.PROFILE)
        if not nav_ok:
            log.warning("[%s] navigate_to PROFILE failed, trying direct tab click",
                        self.device_serial)
            profile_tab = self.device(description="Profile")
            if profile_tab.exists(timeout=5):
                profile_tab.click()
                random_sleep(2.0, 3.0, label="profile_tab_click")
                return True
            return False
        random_sleep(1.5, 3.0, label="profile_loaded")
        return True

    def _open_edit_profile(self):
        """Click 'Edit profile' button on the profile page."""
        log.info("[%s] Opening Edit Profile...", self.device_serial)

        for attempt in range(3):
            edit_btn = self.device(text="Edit profile")
            if not edit_btn.exists(timeout=3):
                edit_btn = self.device(description="Edit profile")
            if not edit_btn.exists(timeout=3):
                edit_btn = self.device(textContains="Edit")

            if edit_btn.exists(timeout=3):
                edit_btn.click()
                random_sleep(2.0, 4.0, label="edit_profile_load")

                # Verify we're on edit profile screen
                xml = self.ctrl.dump_xml("edit_profile_check")
                if 'edit_profile_fields' in xml:
                    log.info("[%s] Edit profile screen loaded", self.device_serial)
                    return True

            random_sleep(1.5, 2.5, label="edit_retry_%d" % attempt)

        return False

    def _set_name_field(self):
        """Click on name field which opens a separate Name screen,
        clear it, type new name, then click the checkmark (save) button.
        
        Instagram opens a dedicated 'Name' sub-screen with:
        - X (cancel) on top-left
        - Checkmark (save) on top-right (action_bar_button_action)
        - Single EditText for the name
        """
        log.info("[%s] Setting name field to '%s'...", self.device_serial, self.name)

        # Find and click the name field container to open the Name sub-screen
        name_container = self.device(resourceIdMatches='.*:id/full_name')
        if not name_container.exists(timeout=5):
            # Fallback: try finding by label "Name"
            name_label = self.device(text="Name")
            if name_label.exists(timeout=3):
                name_label.click()
                random_sleep(2.0, 3.0, label="name_label_click")
            else:
                log.warning("[%s] Name field container not found", self.device_serial)
                return False
        else:
            # Click the field container to open Name sub-screen
            form_field = name_container.child(resourceIdMatches='.*prism_form_field_container')
            if form_field.exists(timeout=2):
                form_field.click()
            else:
                name_container.click()
            random_sleep(2.0, 3.0, label="name_screen_open")

        # Verify we're on the Name sub-screen (title should be "Name")
        name_title = self.device(resourceIdMatches='.*action_bar_title', text='Name')
        if not name_title.exists(timeout=3):
            # Also check by screen content
            xml = self.ctrl.dump_xml("name_screen_check")
            if 'known by' not in xml and 'change your name' not in xml:
                log.warning("[%s] Not on Name sub-screen", self.device_serial)
                return False
        
        log.info("[%s] Name sub-screen opened", self.device_serial)

        # Find the EditText on this screen
        edit_text = self.device(className="android.widget.EditText")
        if not edit_text.exists(timeout=5):
            log.warning("[%s] Name EditText not found on Name screen", self.device_serial)
            return False

        # Click, clear, and type
        edit_text.click()
        random_sleep(0.5, 1.0, label="edit_text_click")

        edit_text.clear_text()
        random_sleep(0.3, 0.5, label="name_clear")

        self._type_text(self.name)
        random_sleep(0.5, 1.0, label="name_typed")

        log.info("[%s] Name typed: '%s'", self.device_serial, self.name)

        # Click the checkmark/save button (action_bar_button_action)
        save_btn = self.device(resourceIdMatches='.*action_bar_button_action')
        if not save_btn.exists(timeout=3):
            save_btn = self.device(description="Done")
        if not save_btn.exists(timeout=3):
            save_btn = self.device(description="Save")

        if save_btn.exists(timeout=3):
            save_btn.click()
            random_sleep(2.0, 3.0, label="name_checkmark")
            
            # Instagram shows a confirmation dialog:
            # "Are you sure you want to change your name to X?"
            # with "Change name" and "Cancel" buttons
            change_btn = self.device(text="Change name")
            if not change_btn.exists(timeout=3):
                change_btn = self.device(textContains="Change")
            
            if change_btn.exists(timeout=3):
                log.info("[%s] Confirmation dialog found, clicking 'Change name'", 
                         self.device_serial)
                change_btn.click()
                random_sleep(2.0, 4.0, label="name_confirmed")
            
            log.info("[%s] Name saved", self.device_serial)
            return True
        else:
            log.warning("[%s] Save/checkmark button not found, trying back", 
                        self.device_serial)
            self.device.press('back')
            random_sleep(1.0, 2.0, label="name_back_fallback")
            return True

    def _navigate_back_to_profile(self):
        """Press back to return to profile. Instagram auto-saves edit profile changes."""
        log.info("[%s] Navigating back (auto-save)...", self.device_serial)
        for _ in range(4):
            xml = self.ctrl.dump_xml("nav_back_check")
            screen = self.ctrl.detect_screen(xml)
            if screen == Screen.PROFILE:
                return
            # Try the back button first
            back_btn = self.device(resourceIdMatches='.*action_bar_button_back')
            if back_btn.exists(timeout=1):
                back_btn.click()
            else:
                self.device.press('back')
            random_sleep(1.0, 2.0, label="back_press")

    def _type_text(self, text):
        """Type text using ADB input for reliability across locales."""
        try:
            escaped = text.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")
            escaped = escaped.replace(' ', '%s')
            escaped = escaped.replace('&', '\\&')
            escaped = escaped.replace('|', '\\|')
            escaped = escaped.replace(';', '\\;')
            escaped = escaped.replace('(', '\\(').replace(')', '\\)')
            subprocess.run(
                ['adb', '-s', self.adb_serial, 'shell', 'input', 'text', escaped],
                capture_output=True, timeout=10
            )
        except Exception as e:
            log.warning("[%s] ADB text input failed: %s, trying u2 set_text",
                        self.device_serial, e)
            focused = self.device(focused=True, className="android.widget.EditText")
            if focused.exists(timeout=2):
                focused.set_text(text)

    def _update_db(self):
        """Update the account's display name in DB."""
        try:
            conn = get_db()
            now = datetime.datetime.now().isoformat()

            # Ensure column exists
            for col, col_type in [('display_name', 'TEXT'),
                                   ('display_name_set_at', 'TEXT')]:
                try:
                    conn.execute(f"ALTER TABLE accounts ADD COLUMN {col} {col_type}")
                    conn.commit()
                except Exception:
                    pass  # Column already exists

            conn.execute("""
                UPDATE accounts
                SET display_name = ?, display_name_set_at = ?, updated_at = ?
                WHERE id = ?
            """, (self.name, now, now, self.account_id))
            conn.commit()
            conn.close()
            log.info("[%s] DB updated: @%s display_name='%s'",
                     self.device_serial, self.username, self.name)
        except Exception as e:
            log.error("[%s] DB update failed: %s", self.device_serial, e)
