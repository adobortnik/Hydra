"""
Switch to Business Profile Action Module
==========================================
Switches a personal Instagram account to a Business/Professional profile.
Navigates through the IG settings UI flow using UIAutomator2.

Flow: Profile → Edit Profile → Switch to Professional → Category → Business → Done
Fallback: Profile → Settings → Account type and tools → Switch to Professional → ...
"""

import logging
import time
import re
import datetime

from automation.ig_controller import IGController, Screen
from automation.actions.helpers import (
    get_db, log_action, random_sleep,
    get_account_settings,
)

log = logging.getLogger(__name__)

# Default category to select
DEFAULT_CATEGORY = "Digital creator"

# Categories that work well for automation accounts
SAFE_CATEGORIES = [
    "Digital creator",
    "Entrepreneur",
    "Personal blog",
    "Artist",
    "Musician/band",
    "Product/service",
    "Gaming video creator",
    "Video creator",
]


class SwitchToBusinessAction:
    """Switch account from Personal to Business/Professional profile."""

    def __init__(self, device, device_serial, account_info, session_id,
                 pkg=None, category=None, account_type='business'):
        self.device = device
        self.device_serial = device_serial
        self.account = account_info
        self.session_id = session_id
        self.username = account_info.get('username', '')
        self.account_id = account_info.get('id')
        self.category = category or DEFAULT_CATEGORY
        self.account_type = account_type  # 'business' or 'creator'

        _pkg = pkg or account_info.get('package',
               account_info.get('instagram_package', 'com.instagram.android'))
        self.ctrl = IGController(device, device_serial, _pkg)

    def execute(self):
        """
        Full flow to switch account to Business profile.
        Returns dict with 'success', 'category', 'error_message'.
        """
        result = {
            'success': False,
            'category': None,
            'error_message': None,
        }

        try:
            log.info("[%s] SWITCH_BUSINESS: Starting for @%s (target: %s, category: %s)",
                     self.device_serial, self.username, self.account_type, self.category)

            # Step 1: Navigate to Profile
            if not self.ctrl.navigate_to(Screen.PROFILE):
                result['error_message'] = "Could not navigate to profile"
                return result

            random_sleep(1.5, 3.0, label="profile_loaded")

            # Step 2: Check if already a business profile
            xml = self.ctrl.dump_xml("check_business")
            if self._is_already_business(xml):
                log.info("[%s] @%s is already a Business/Professional profile",
                         self.device_serial, self.username)
                result['success'] = True
                result['category'] = 'already_business'
                self._update_db(True, 'already_business')
                return result

            # Step 3: Try Edit Profile path first, fallback to Settings path
            switch_found = self._try_edit_profile_path()
            if not switch_found:
                switch_found = self._try_settings_path()

            if not switch_found:
                result['error_message'] = "Could not find 'Switch to professional' option"
                return result

            # Step 4: Handle intro/continue screens
            self._dismiss_intro_screens()

            # Step 5: Select category
            category_ok = self._select_category()
            if not category_ok:
                result['error_message'] = "Failed to select category"
                return result

            # Step 6: Select Business (not Creator)
            type_ok = self._select_account_type()
            if not type_ok:
                result['error_message'] = "Failed to select Business account type"
                return result

            # Step 7: Handle contact info screen
            self._handle_contact_info()

            # Step 8: Skip Facebook connection
            self._skip_facebook_connect()

            # Step 9: Dismiss welcome/setup screens
            self._dismiss_post_switch_screens()

            # Step 10: Verify switch was successful
            success = self._verify_business_profile()

            if success:
                log.info("[%s] ✅ @%s successfully switched to Business Profile!",
                         self.device_serial, self.username)
                result['success'] = True
                result['category'] = self.category
                self._update_db(True, self.category)

                log_action(self.session_id, self.device_serial, self.username,
                           'switch_to_business', success=True)
            else:
                result['error_message'] = "Verification failed — profile may not have switched"
                log_action(self.session_id, self.device_serial, self.username,
                           'switch_to_business', success=False,
                           error_message=result['error_message'])

        except Exception as e:
            log.error("[%s] SWITCH_BUSINESS error: %s", self.device_serial, e)
            result['error_message'] = str(e)[:200]
            log_action(self.session_id, self.device_serial, self.username,
                       'switch_to_business', success=False,
                       error_message=result['error_message'])

        return result

    # ──────────────────────────────────────────────────
    # Private Methods
    # ──────────────────────────────────────────────────

    def _is_already_business(self, xml):
        """Check if account is already a Professional/Business profile."""
        indicators = [
            'Professional dashboard',
            'professional_dashboard',
            'Switch to personal account',
            'Switch account type',
        ]
        # Check for Insights on profile (strong indicator)
        # Use case-insensitive check for mixed UI versions
        xml_lower = xml.lower()
        count = sum(1 for ind in indicators if ind.lower() in xml_lower)

        # Also check for Insights button specifically
        if 'insights' in xml_lower and 'professional' in xml_lower:
            count += 1

        return count >= 2  # At least 2 indicators

    def _try_edit_profile_path(self):
        """Try: Edit Profile → Switch to professional account."""
        log.info("[%s] Trying Edit Profile path...", self.device_serial)

        # Tap Edit Profile button — use resourceIdMatches for clone compat
        edit_btn = self.device(textContains="Edit profile")
        if not edit_btn.exists(timeout=3):
            edit_btn = self.device(descriptionContains="Edit profile")
        if not edit_btn.exists(timeout=3):
            edit_btn = self.device(textContains="Edit your profile")

        if not edit_btn.exists(timeout=3):
            log.warning("[%s] Edit profile button not found", self.device_serial)
            return False

        edit_btn.click()
        random_sleep(2.0, 4.0, label="edit_profile_load")

        # Scroll down to find "Switch to professional account"
        return self._find_and_tap_switch_link()

    def _try_settings_path(self):
        """Try: Settings → Account type and tools → Switch to professional."""
        log.info("[%s] Trying Settings path...", self.device_serial)

        # Navigate to profile first
        self.ctrl.navigate_to(Screen.PROFILE)
        random_sleep(1.0, 2.0)

        # Tap hamburger menu (Options)
        options_btn = self.device(description="Options")
        if not options_btn.exists(timeout=3):
            options_btn = self.device(resourceIdMatches=".*option_list_button.*")
        if not options_btn.exists(timeout=3):
            # Try the three-line menu icon
            options_btn = self.device(descriptionContains="Menu")

        if not options_btn.exists(timeout=3):
            log.warning("[%s] Options/hamburger menu not found", self.device_serial)
            return False

        options_btn.click()
        random_sleep(1.5, 3.0, label="options_menu_load")

        # Tap "Settings and privacy"
        settings_btn = self.device(textContains="Settings")
        if settings_btn.exists(timeout=3):
            settings_btn.click()
            random_sleep(1.5, 3.0, label="settings_load")

        # Look for "Account type and tools" or similar
        acct_type_btn = self.device(textContains="Account type")
        if not acct_type_btn.exists(timeout=3):
            # Scroll to find it under "For professionals" section
            try:
                self.device(scrollable=True).scroll.to(textContains="Account type")
            except Exception:
                pass
            acct_type_btn = self.device(textContains="Account type")

        if acct_type_btn.exists(timeout=3):
            acct_type_btn.click()
            random_sleep(1.5, 3.0, label="acct_type_load")
            return self._find_and_tap_switch_link()

        log.warning("[%s] Account type and tools not found in settings", self.device_serial)
        return False

    def _find_and_tap_switch_link(self):
        """Find and tap 'Switch to professional account' on current screen."""
        for scroll_attempt in range(5):
            xml = self.ctrl.dump_xml("find_switch_%d" % scroll_attempt)

            # Look for the switch text
            switch_texts = [
                "Switch to professional account",
                "Switch to Professional Account",
                "Switch to professional",
                "Get professional tools",
            ]

            for text in switch_texts:
                if text.lower() in xml.lower():
                    switch_btn = self.device(textContains=text)
                    if switch_btn.exists(timeout=2):
                        switch_btn.click()
                        random_sleep(2.0, 4.0, label="switch_clicked")
                        log.info("[%s] Tapped: '%s'", self.device_serial, text)
                        return True

            # Scroll down to find it
            try:
                self.device.swipe(540, 1500, 540, 800, duration=0.5)
                random_sleep(1.0, 2.0, label="scroll_for_switch")
            except Exception:
                break

        log.warning("[%s] 'Switch to professional' not found after scrolling", self.device_serial)
        return False

    def _dismiss_intro_screens(self):
        """Dismiss 1-4 intro/benefit screens by tapping Continue."""
        for i in range(6):
            random_sleep(1.5, 3.0, label="intro_screen_%d" % i)
            xml = self.ctrl.dump_xml("intro_%d" % i)

            # Check if we've reached the category picker
            if self._is_category_screen(xml):
                log.info("[%s] Reached category picker after %d intro screens",
                         self.device_serial, i)
                return

            # Check if we've reached account type screen already
            if "Business" in xml and "Creator" in xml:
                log.info("[%s] Reached account type screen after %d intros",
                         self.device_serial, i)
                return

            # Look for Continue button
            continue_btn = self.device(text="Continue")
            if continue_btn.exists(timeout=2):
                continue_btn.click()
                log.info("[%s] Dismissed intro screen %d (Continue)", self.device_serial, i + 1)
                continue

            # Look for "Get started" or "Next"
            found = False
            for btn_text in ["Get started", "Next", "Got it"]:
                btn = self.device(text=btn_text)
                if btn.exists(timeout=1):
                    btn.click()
                    log.info("[%s] Dismissed intro screen %d (%s)",
                             self.device_serial, i + 1, btn_text)
                    found = True
                    break

            if not found:
                # No dismiss button found — might already be past intros
                break

    def _is_category_screen(self, xml):
        """Check if we're on the category selection screen."""
        indicators = [
            "What best describes you",
            "Choose a category",
            "Select a category",
            "Digital creator",
            "Entrepreneur",
            "Personal blog",
        ]
        return sum(1 for ind in indicators if ind in xml) >= 2

    def _select_category(self):
        """Select a business category."""
        random_sleep(1.0, 2.0)
        xml = self.ctrl.dump_xml("category_screen")

        if not self._is_category_screen(xml):
            log.warning("[%s] Not on category screen — may have been skipped",
                        self.device_serial)
            # Could already be past this step
            return True

        # Try to find and tap the desired category
        cat_btn = self.device(text=self.category)
        if cat_btn.exists(timeout=3):
            cat_btn.click()
            log.info("[%s] Selected category: %s", self.device_serial, self.category)
        else:
            # Try search if available
            search = self.device(textContains="Search")
            if search.exists(timeout=2):
                search.click()
                random_sleep(0.5, 1.0)
                search.set_text(self.category)
                random_sleep(1.0, 2.0)
                cat_btn = self.device(text=self.category)
                if cat_btn.exists(timeout=3):
                    cat_btn.click()
                else:
                    # Fall back to first available safe category
                    for fallback in SAFE_CATEGORIES:
                        fb_btn = self.device(text=fallback)
                        if fb_btn.exists(timeout=1):
                            fb_btn.click()
                            self.category = fallback
                            log.info("[%s] Used fallback category: %s",
                                     self.device_serial, fallback)
                            break
            else:
                # No search, try scrolling for fallback categories
                for fallback in SAFE_CATEGORIES:
                    fb_btn = self.device(text=fallback)
                    if fb_btn.exists(timeout=1):
                        fb_btn.click()
                        self.category = fallback
                        log.info("[%s] Used fallback category: %s",
                                 self.device_serial, fallback)
                        break

        random_sleep(1.0, 2.0)

        # Tap Done
        done_btn = self.device(text="Done")
        if done_btn.exists(timeout=3):
            done_btn.click()
            random_sleep(1.5, 3.0, label="category_done")
            return True

        # Try Next instead
        next_btn = self.device(text="Next")
        if next_btn.exists(timeout=2):
            next_btn.click()
            random_sleep(1.5, 3.0)
            return True

        log.warning("[%s] Could not confirm category selection", self.device_serial)
        return False

    def _select_account_type(self):
        """Select Business (not Creator) account type."""
        random_sleep(1.0, 2.0)
        xml = self.ctrl.dump_xml("account_type_screen")

        # Check if we're on the account type screen
        if "Business" not in xml and "Creator" not in xml:
            # Might have been skipped (some flows don't show this)
            log.info("[%s] Account type screen not detected — may have been skipped",
                     self.device_serial)
            return True

        if self.account_type == 'business':
            type_btn = self.device(text="Business")
        else:
            type_btn = self.device(text="Creator")

        if type_btn.exists(timeout=3):
            type_btn.click()
            log.info("[%s] Selected account type: %s",
                     self.device_serial, self.account_type)
            random_sleep(1.0, 2.0)

        # Tap Next
        next_btn = self.device(text="Next")
        if next_btn.exists(timeout=3):
            next_btn.click()
            random_sleep(1.5, 3.0, label="type_next")
            return True

        log.warning("[%s] Could not confirm account type", self.device_serial)
        return True  # May have auto-advanced

    def _handle_contact_info(self):
        """Handle the contact info review screen."""
        random_sleep(1.5, 3.0)

        # If contact info screen is showing, just tap Next/Skip
        for btn_text in ["Next", "Skip", "Don't use my contact info", "Not now"]:
            btn = self.device(text=btn_text)
            if btn.exists(timeout=2):
                btn.click()
                log.info("[%s] Contact info: tapped '%s'",
                         self.device_serial, btn_text)
                random_sleep(1.5, 3.0)
                return

    def _skip_facebook_connect(self):
        """Skip the Facebook page connection screen."""
        random_sleep(1.5, 3.0)
        xml = self.ctrl.dump_xml("facebook_connect")

        for btn_text in ["Skip", "Not now", "Don't connect", "Later"]:
            btn = self.device(text=btn_text)
            if btn.exists(timeout=2):
                btn.click()
                log.info("[%s] Facebook connect: tapped '%s'",
                         self.device_serial, btn_text)
                random_sleep(1.5, 3.0)
                return

        # Also try pressing back if nothing found
        if "Facebook" in xml or "Connect" in xml:
            self.device.press('back')
            random_sleep(1.0, 2.0)

    def _dismiss_post_switch_screens(self):
        """Dismiss any post-switch promotional screens."""
        for i in range(5):
            random_sleep(1.5, 3.0)
            xml = self.ctrl.dump_xml("post_switch_%d" % i)

            # Check if we're back on the profile
            current = self.ctrl.detect_screen(xml)
            if current == Screen.PROFILE:
                return

            # Dismiss buttons
            found = False
            for btn_text in ["Done", "Got it", "Not now", "Skip",
                             "Explore professional tools", "Close",
                             "Maybe later", "Not Now"]:
                btn = self.device(text=btn_text)
                if btn.exists(timeout=1):
                    btn.click()
                    log.info("[%s] Post-switch dismiss: '%s'",
                             self.device_serial, btn_text)
                    found = True
                    break

            if not found:
                # No button found, try back
                self.device.press('back')

    def _verify_business_profile(self):
        """Navigate to profile and verify business switch succeeded."""
        self.ctrl.navigate_to(Screen.PROFILE)
        random_sleep(2.0, 4.0, label="verify_profile_load")
        xml = self.ctrl.dump_xml("verify_business")

        indicators = [
            'Professional dashboard',
            'professional_dashboard',
            'Insights',
            'insights',
            'Ad tools',
            'Promotions',
        ]
        xml_lower = xml.lower()
        found = sum(1 for ind in indicators if ind.lower() in xml_lower)
        log.info("[%s] Business verification: %d/6 indicators found",
                 self.device_serial, found)
        return found >= 1

    def _update_db(self, is_business, category):
        """Update the account's business profile status in DB."""
        try:
            conn = get_db()
            now = datetime.datetime.now().isoformat()
            conn.execute("""
                UPDATE accounts
                SET is_business_profile = ?, business_category = ?,
                    business_switched_at = ?, updated_at = ?
                WHERE id = ?
            """, (1 if is_business else 0, category, now, now, self.account_id))
            conn.commit()
            conn.close()
            log.info("[%s] DB updated: @%s → business=%s, category=%s",
                     self.device_serial, self.username, is_business, category)
        except Exception as e:
            log.error("[%s] DB update failed: %s", self.device_serial, e)
