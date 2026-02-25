"""
Set Profile Link Action Module
================================
Sets or updates the external link (website URL) on an Instagram profile.

Flow (confirmed on clones 2025-02):
  Profile → Edit Profile → "Add link" (links_text_cell) →
  Links screen → "Add external link" (link_option_text) →
  Add External Link screen → fill URL + optional Title → Done

If a link already exists, it will appear as an editable entry on the Links
screen instead of "Add external link". In that case we click the existing
link entry to edit it.

Key selectors discovered on device (package-agnostic via resourceIdMatches):
  - Edit profile button: d(text="Edit profile")
  - Links cell: d(resourceIdMatches=".*links_text_cell")  content-desc="Add link"
  - Add external link: d(text="Add external link")  rid=link_option_text
  - URL field container: d(resourceIdMatches=".*edit_url_form_field")
  - Title field container: d(resourceIdMatches=".*edit_title_form_field")
  - EditText inside each: child(className="android.widget.EditText")
  - Done button: d(resourceIdMatches=".*action_bar_button_action") desc="Done"
  - Back button: d(resourceIdMatches=".*action_bar_button_back") desc="Back"
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


class SetProfileLinkAction:
    """Set or update the external link on an Instagram profile."""

    def __init__(self, device, device_serial, account_info, session_id,
                 pkg=None, url=None, title=None):
        """
        Args:
            device: uiautomator2 device object
            device_serial: e.g. '10.1.11.4_5555'
            account_info: dict with 'username', 'id', etc.
            session_id: current session ID
            pkg: IG clone package name
            url: URL to set (e.g. 'https://example.com')
            title: optional title for the link
        """
        self.device = device
        self.device_serial = device_serial
        self.account = account_info
        self.session_id = session_id
        self.username = account_info.get('username', '')
        self.account_id = account_info.get('id')
        self.url = url
        self.title = title

        _pkg = pkg or account_info.get('package',
               account_info.get('instagram_package', 'com.instagram.android'))
        self.ctrl = IGController(device, device_serial, _pkg)
        self.pkg = _pkg
        self.adb_serial = device_serial.replace('_', ':')

    def execute(self):
        """
        Full flow to set/update profile link.
        Returns dict with 'success', 'error_message'.
        """
        result = {
            'success': False,
            'error_message': None,
        }

        if not self.url:
            result['error_message'] = "No URL provided"
            return result

        try:
            log.info("[%s] SET_PROFILE_LINK: Starting for @%s — url=%s",
                     self.device_serial, self.username, self.url)

            # Step 1: Navigate to Profile
            if not self._navigate_to_profile():
                result['error_message'] = "Could not navigate to profile"
                return result

            # Step 2: Open Edit Profile
            if not self._open_edit_profile():
                result['error_message'] = "Could not open Edit Profile"
                return result

            # Step 3: Open Links section
            if not self._open_links():
                result['error_message'] = "Could not open Links section"
                return result

            # Step 4: Handle existing link or add new one
            if not self._handle_link_entry():
                result['error_message'] = "Could not open link edit form"
                return result

            # Step 5: Fill in URL (and title if provided)
            if not self._fill_link_fields():
                result['error_message'] = "Could not fill link fields"
                return result

            # Step 6: Save
            if not self._save_link():
                result['error_message'] = "Could not save link"
                return result

            # Step 7: Go back to profile
            self._navigate_back_to_profile()

            # Update DB
            self._update_db()

            log.info("[%s] SET_PROFILE_LINK: Successfully set link for @%s to %s",
                     self.device_serial, self.username, self.url)
            result['success'] = True

            log_action(self.session_id, self.device_serial, self.username,
                       'set_profile_link', success=True)

        except Exception as e:
            log.error("[%s] SET_PROFILE_LINK error: %s",
                      self.device_serial, e, exc_info=True)
            result['error_message'] = str(e)[:200]
            log_action(self.session_id, self.device_serial, self.username,
                       'set_profile_link', success=False,
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

    def _open_links(self):
        """Click 'Add link' / links cell on edit profile page."""
        log.info("[%s] Opening Links section...", self.device_serial)

        # Try the links_text_cell resource ID first
        links_cell = self.device(resourceIdMatches='.*links_text_cell')
        if not links_cell.exists(timeout=3):
            links_cell = self.device(text="Add link")
        if not links_cell.exists(timeout=3):
            links_cell = self.device(textContains="link")
            # Also check if links already shows as a URL (existing link)
            if not links_cell.exists(timeout=2):
                links_cell = self.device(descriptionContains="link")

        if links_cell.exists(timeout=3):
            links_cell.click()
            random_sleep(2.0, 4.0, label="links_load")

            # Verify we're on Links screen
            xml = self.ctrl.dump_xml("links_check")
            if 'links_list' in xml or 'Add external link' in xml:
                log.info("[%s] Links screen loaded", self.device_serial)
                return True
            # Could also be directly on link edit if only one link
            if 'edit_url_form_field' in xml:
                log.info("[%s] Directly on link edit screen", self.device_serial)
                return True

        log.warning("[%s] Could not open Links section", self.device_serial)
        return False

    def _handle_link_entry(self):
        """
        On the Links screen, either click 'Add external link' (no existing link)
        or click the existing link entry to edit it.
        """
        log.info("[%s] Handling link entry...", self.device_serial)

        xml = self.ctrl.dump_xml("link_entry_check")

        # Already on link edit form? (edge case)
        if 'edit_url_form_field' in xml:
            log.info("[%s] Already on link edit form", self.device_serial)
            return True

        # Check for "Add external link" (no existing link)
        add_ext = self.device(text="Add external link")
        if add_ext.exists(timeout=3):
            log.info("[%s] No existing link, clicking 'Add external link'",
                     self.device_serial)
            add_ext.click()
            random_sleep(2.0, 3.0, label="add_ext_link")
            return True

        # If there's an existing link, there will be a link entry in the list
        # with the URL visible. It should be a clickable item in links_list.
        links_list = self.device(resourceIdMatches='.*links_list')
        if links_list.exists(timeout=2):
            # Try clicking the first item in the list (existing link)
            first_item = links_list.child(className="android.view.ViewGroup", index=0)
            if first_item.exists(timeout=2):
                log.info("[%s] Found existing link entry, clicking to edit",
                         self.device_serial)
                first_item.click()
                random_sleep(2.0, 3.0, label="edit_existing_link")

                # Check if we now see a context menu (edit/delete) or the edit form
                xml = self.ctrl.dump_xml("existing_link_action")
                if 'edit_url_form_field' in xml:
                    return True
                # May show options like "Edit", "Remove", etc.
                edit_opt = self.device(text="Edit")
                if edit_opt.exists(timeout=2):
                    edit_opt.click()
                    random_sleep(1.5, 2.5, label="edit_opt_clicked")
                    return True

        # Fallback: try direct text match
        ext_link = self.device(resourceIdMatches='.*link_option_text')
        if ext_link.exists(timeout=2):
            ext_link.click()
            random_sleep(2.0, 3.0, label="link_option_clicked")
            return True

        log.warning("[%s] Could not find link entry to click", self.device_serial)
        return False

    def _fill_link_fields(self):
        """Fill in the URL and Title fields on the link edit form."""
        log.info("[%s] Filling link fields: url=%s, title=%s",
                 self.device_serial, self.url, self.title)

        # Verify we're on the right screen
        xml = self.ctrl.dump_xml("fill_link_check")
        if 'edit_url_form_field' not in xml:
            log.warning("[%s] Not on link edit form!", self.device_serial)
            return False

        # --- Fill URL field ---
        url_container = self.device(resourceIdMatches='.*edit_url_form_field')
        if url_container.exists(timeout=3):
            # Click the container to focus, then find the EditText
            url_edit = url_container.child(className="android.widget.EditText")
            if not url_edit.exists(timeout=2):
                # Try clicking the prism_form_field_container first
                url_form = url_container.child(resourceIdMatches='.*prism_form_field_container')
                if url_form.exists(timeout=2):
                    url_form.click()
                    random_sleep(0.5, 1.0, label="url_focus")
                url_edit = url_container.child(className="android.widget.EditText")

            if url_edit.exists(timeout=3):
                url_edit.click()
                random_sleep(0.5, 1.0, label="url_edit_click")

                # Clear existing text
                url_edit.clear_text()
                random_sleep(0.3, 0.5, label="url_clear")

                # Type URL using ADB for reliability
                self._type_text(self.url)
                random_sleep(0.5, 1.0, label="url_typed")
                log.info("[%s] URL field filled", self.device_serial)
            else:
                log.warning("[%s] URL EditText not found", self.device_serial)
                return False
        else:
            log.warning("[%s] URL container not found", self.device_serial)
            return False

        # --- Fill Title field (optional) ---
        if self.title:
            title_container = self.device(resourceIdMatches='.*edit_title_form_field')
            if title_container.exists(timeout=3):
                title_edit = title_container.child(className="android.widget.EditText")
                if not title_edit.exists(timeout=2):
                    title_form = title_container.child(
                        resourceIdMatches='.*prism_form_field_container')
                    if title_form.exists(timeout=2):
                        title_form.click()
                        random_sleep(0.5, 1.0, label="title_focus")
                    title_edit = title_container.child(className="android.widget.EditText")

                if title_edit.exists(timeout=3):
                    title_edit.click()
                    random_sleep(0.5, 1.0, label="title_edit_click")
                    title_edit.clear_text()
                    random_sleep(0.3, 0.5, label="title_clear")
                    self._type_text(self.title)
                    random_sleep(0.5, 1.0, label="title_typed")
                    log.info("[%s] Title field filled", self.device_serial)
                else:
                    log.warning("[%s] Title EditText not found, continuing without title",
                                self.device_serial)
            else:
                log.warning("[%s] Title container not found, continuing without title",
                            self.device_serial)

        return True

    def _save_link(self):
        """Click the Done button to save the link."""
        log.info("[%s] Saving link...", self.device_serial)

        # Hide keyboard first
        try:
            self.device.press('back')
            random_sleep(0.5, 1.0, label="hide_keyboard")
        except Exception:
            pass

        # Try the action_bar_button_action (Done) button
        done_btn = self.device(resourceIdMatches='.*action_bar_button_action')
        if done_btn.exists(timeout=3):
            done_btn.click()
            random_sleep(2.0, 4.0, label="done_clicked")
            log.info("[%s] Done button clicked", self.device_serial)
            return True

        # Fallback: try by description
        done_btn = self.device(description="Done")
        if done_btn.exists(timeout=2):
            done_btn.click()
            random_sleep(2.0, 4.0, label="done_desc_clicked")
            return True

        # Fallback: try by text
        done_btn = self.device(text="Done")
        if done_btn.exists(timeout=2):
            done_btn.click()
            random_sleep(2.0, 4.0, label="done_text_clicked")
            return True

        log.warning("[%s] Done/Save button not found", self.device_serial)
        return False

    def _navigate_back_to_profile(self):
        """Press back to return to profile from Links or Edit Profile."""
        for _ in range(4):
            xml = self.ctrl.dump_xml("nav_back_check")
            # Check if we're back on profile
            screen = self.ctrl.detect_screen(xml)
            if screen == Screen.PROFILE:
                return
            self.device.press('back')
            random_sleep(1.0, 2.0, label="back_press")

    def _type_text(self, text):
        """Type text using ADB input for reliability across locales."""
        try:
            # Escape special characters for shell
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
            # Fallback to uiautomator2
            focused = self.device(focused=True, className="android.widget.EditText")
            if focused.exists(timeout=2):
                focused.set_text(text)

    def _update_db(self):
        """Update the account's profile link in DB."""
        try:
            conn = get_db()
            now = datetime.datetime.now().isoformat()

            # Ensure columns exist
            for col, col_type in [('profile_link', 'TEXT'),
                                   ('profile_link_title', 'TEXT'),
                                   ('profile_link_set_at', 'TEXT')]:
                try:
                    conn.execute(f"ALTER TABLE accounts ADD COLUMN {col} {col_type}")
                    conn.commit()
                except Exception:
                    pass  # Column already exists

            conn.execute("""
                UPDATE accounts
                SET profile_link = ?, profile_link_title = ?,
                    profile_link_set_at = ?, updated_at = ?
                WHERE id = ?
            """, (self.url, self.title, now, now, self.account_id))
            conn.commit()
            conn.close()
            log.info("[%s] DB updated: @%s profile_link=%s",
                     self.device_serial, self.username, self.url)
        except Exception as e:
            log.error("[%s] DB update failed: %s", self.device_serial, e)
