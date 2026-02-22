"""
Switch to Business Profile Action Module
==========================================
Switches a personal Instagram account to a Business/Professional profile.
Navigates through the IG settings UI flow using UIAutomator2.

Primary flow (confirmed working on clones 2026-02-22):
  Profile → Options (hamburger) → "Settings and activity" →
  scroll to "Account type and tools" → "Switch to professional account" →
  Intro (Next) → Category picker → Contact info → Skip Facebook → Close setup

Fallback: Profile → Edit Profile → scroll to "Switch to professional account"

Key clone-specific details:
  - Menu item is "Settings and activity" (NOT "Settings and privacy")
  - Need 6+ swipe-scrolls in Settings to reach "Account type and tools"
  - Primary action button rid: bb_primary_action (clone-specific)
  - Category picker uses RadioButtons
  - Final setup screen dismissed via Close (X) button, not Done
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

# Default category to select (use one visible in the default list)
DEFAULT_CATEGORY = "Artist"

# Categories that appear in the default picker without searching
# (RadioButtons on the category screen — confirmed 2026-02-22)
SAFE_CATEGORIES = [
    "Artist",
    "Blogger",
    "Musician/band",
    "Digital creator",
    "Entrepreneur",
    "Personal blog",
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
        self.pkg = _pkg

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

            # Step 3: Try Settings path first (most reliable on clones),
            #         fallback to Edit Profile path
            switch_found = self._try_settings_path()
            if not switch_found:
                switch_found = self._try_edit_profile_path()

            if not switch_found:
                result['error_message'] = "Could not find 'Switch to professional account' option"
                return result

            # Step 4: Handle intro screen (Next button)
            self._handle_intro_screen()

            # Step 5: Select category
            category_ok = self._select_category()
            if not category_ok:
                result['error_message'] = "Failed to select category"
                return result

            # Step 6: Handle contact info screen
            self._handle_contact_info()

            # Step 7: Skip Facebook connection
            self._skip_facebook_connect()

            # Step 8: Dismiss setup complete screen (Close button)
            self._dismiss_setup_complete()

            # Step 9: Verify switch was successful
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
        xml_lower = xml.lower()
        count = sum(1 for ind in indicators if ind.lower() in xml_lower)

        # Also check for Insights on profile (strong indicator)
        if 'insights' in xml_lower and 'professional' in xml_lower:
            count += 1

        # Check for views indicator (e.g., "153 views in the last 30 days.")
        if 'views in the last' in xml_lower:
            count += 1

        return count >= 2  # At least 2 indicators

    def _try_settings_path(self):
        """
        Primary path (confirmed 2026-02-22 on clones):
        Profile → Options (hamburger) → "Settings and activity" →
        scroll to "Account type and tools" → "Switch to professional account"
        """
        log.info("[%s] Trying Settings path...", self.device_serial)

        # Navigate to profile first
        self.ctrl.navigate_to(Screen.PROFILE)
        random_sleep(1.0, 2.0)

        # Tap hamburger menu — d(description="Options")
        options_btn = self.device(description="Options")
        if not options_btn.exists(timeout=3):
            options_btn = self.device(resourceIdMatches=".*option_list_button.*")
        if not options_btn.exists(timeout=3):
            options_btn = self.device(descriptionContains="Menu")

        if not options_btn.exists(timeout=3):
            log.warning("[%s] Options/hamburger menu not found", self.device_serial)
            return False

        options_btn.click()
        random_sleep(1.5, 3.0, label="options_menu_load")

        # Tap "Settings and activity" (clone text — NOT "Settings and privacy"!)
        settings_btn = self.device(text="Settings and activity")
        if not settings_btn.exists(timeout=3):
            # Fallback: try partial match for other clone variants
            settings_btn = self.device(textContains="Settings and")
            if not settings_btn.exists(timeout=2):
                settings_btn = self.device(textContains="Settings")

        if not settings_btn.exists(timeout=3):
            log.warning("[%s] Settings menu item not found", self.device_serial)
            return False

        settings_btn.click()
        random_sleep(1.5, 3.0, label="settings_load")

        # Scroll DOWN to find "Account type and tools" — needs 6+ scrolls
        # It's under "For professionals" section, near bottom of Settings
        acct_type_btn = self.device(text="Account type and tools")
        if not acct_type_btn.exists(timeout=2):
            log.info("[%s] Scrolling to find 'Account type and tools'...",
                     self.device_serial)
            for scroll_i in range(10):
                # Swipe up to scroll down
                self.device.swipe(540, 1500, 540, 600, duration=0.4)
                random_sleep(0.8, 1.5, label="settings_scroll_%d" % scroll_i)

                acct_type_btn = self.device(text="Account type and tools")
                if acct_type_btn.exists(timeout=1):
                    log.info("[%s] Found 'Account type and tools' after %d scrolls",
                             self.device_serial, scroll_i + 1)
                    break

                # Also check partial match
                acct_type_btn = self.device(textContains="Account type")
                if acct_type_btn.exists(timeout=1):
                    log.info("[%s] Found 'Account type...' after %d scrolls",
                             self.device_serial, scroll_i + 1)
                    break

        if not acct_type_btn.exists(timeout=2):
            log.warning("[%s] 'Account type and tools' not found after scrolling",
                        self.device_serial)
            return False

        acct_type_btn.click()
        random_sleep(1.5, 3.0, label="acct_type_load")

        # Now tap "Switch to professional account"
        return self._find_and_tap_switch_link()

    def _try_edit_profile_path(self):
        """
        Fallback path: Edit Profile → scroll to "Switch to professional account".
        Less reliable on clones but kept as fallback.
        """
        log.info("[%s] Trying Edit Profile path (fallback)...", self.device_serial)

        # Navigate to profile
        self.ctrl.navigate_to(Screen.PROFILE)
        random_sleep(1.0, 2.0)

        # Tap Edit Profile button
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

        # Scroll to find "Switch to professional account"
        return self._find_and_tap_switch_link()

    def _find_and_tap_switch_link(self):
        """Find and tap 'Switch to professional account' on current screen."""
        for scroll_attempt in range(6):
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

        log.warning("[%s] 'Switch to professional' not found after scrolling",
                    self.device_serial)
        return False

    def _handle_intro_screen(self):
        """
        Handle the intro screen: "Get more tools and switch for free"
        Button: text="Next" with rid=bb_primary_action
        """
        random_sleep(1.5, 3.0, label="intro_screen")
        xml = self.ctrl.dump_xml("intro_screen")

        # Check if we're on the intro screen
        if "switch for free" in xml.lower() or "more tools" in xml.lower():
            log.info("[%s] On intro screen — tapping Next", self.device_serial)

        # Try the primary action button (clone-specific rid)
        rid_pattern = ".*bb_primary_action.*"
        next_btn = self.device(text="Next", resourceIdMatches=rid_pattern)
        if next_btn.exists(timeout=3):
            next_btn.click()
            random_sleep(1.5, 3.0, label="intro_next")
            log.info("[%s] Intro: tapped Next (bb_primary_action)", self.device_serial)
            return

        # Fallback: plain text buttons
        for btn_text in ["Next", "Continue", "Get started", "Got it"]:
            btn = self.device(text=btn_text)
            if btn.exists(timeout=2):
                btn.click()
                random_sleep(1.5, 3.0, label="intro_dismiss")
                log.info("[%s] Intro: tapped '%s'", self.device_serial, btn_text)
                return

        log.info("[%s] No intro screen detected — may have been skipped",
                 self.device_serial)

    def _is_category_screen(self, xml):
        """Check if we're on the category selection screen."""
        indicators = [
            "What best describes you",
            "Choose a category",
            "Select a category",
            "Search categories",
        ]
        xml_lower = xml.lower()
        return any(ind.lower() in xml_lower for ind in indicators)

    def _select_category(self):
        """
        Select a business category from the picker.
        Categories are RadioButtons (Artist, Blogger, Musician/band, etc.)
        Bottom button: "Switch to professional account" with rid=bb_primary_action

        Strategy: Pick first visible suggested category (don't search —
        search doesn't reliably find exact matches on clones).
        """
        random_sleep(1.5, 3.0, label="category_wait")
        xml = self.ctrl.dump_xml("category_screen")

        if not self._is_category_screen(xml):
            log.warning("[%s] Not on category screen — may have been skipped",
                        self.device_serial)
            return True

        log.info("[%s] On category picker screen", self.device_serial)

        # Try to find the desired category as a RadioButton or text
        cat_found = False

        # First, try the desired category directly
        cat_btn = self.device(text=self.category)
        if cat_btn.exists(timeout=2):
            cat_btn.click()
            cat_found = True
            log.info("[%s] Selected desired category: %s",
                     self.device_serial, self.category)
        else:
            # Pick first available safe category from the visible list
            for fallback in SAFE_CATEGORIES:
                fb_btn = self.device(text=fallback)
                if fb_btn.exists(timeout=1):
                    fb_btn.click()
                    self.category = fallback
                    cat_found = True
                    log.info("[%s] Selected fallback category: %s",
                             self.device_serial, fallback)
                    break

        if not cat_found:
            # Last resort: tap any RadioButton
            radio = self.device(className="android.widget.RadioButton")
            if radio.exists(timeout=2):
                radio.click()
                self.category = "unknown"
                cat_found = True
                log.info("[%s] Selected first available RadioButton category",
                         self.device_serial)

        if not cat_found:
            log.warning("[%s] Could not select any category", self.device_serial)
            return False

        random_sleep(1.0, 2.0)

        # Tap "Switch to professional account" button (bb_primary_action)
        # NOTE: Same button text as Step 3 — but this is the category confirmation
        rid_pattern = ".*bb_primary_action.*"
        switch_btn = self.device(text="Switch to professional account",
                                 resourceIdMatches=rid_pattern)
        if switch_btn.exists(timeout=3):
            switch_btn.click()
            random_sleep(2.0, 4.0, label="category_confirmed")
            log.info("[%s] Category confirmed via 'Switch to professional account' button",
                     self.device_serial)
            return True

        # Fallback: try other confirmation buttons
        for btn_text in ["Switch to professional account", "Done", "Next"]:
            btn = self.device(text=btn_text)
            if btn.exists(timeout=2):
                btn.click()
                random_sleep(1.5, 3.0)
                log.info("[%s] Category confirmed via '%s'",
                         self.device_serial, btn_text)
                return True

        log.warning("[%s] Could not confirm category selection", self.device_serial)
        return False

    def _handle_contact_info(self):
        """
        Handle the "Review your contact info" screen.
        Button: "Next" or "Don't use my contact info"
        """
        random_sleep(1.5, 3.0, label="contact_info_wait")
        xml = self.ctrl.dump_xml("contact_info")

        for btn_text in ["Next", "Don't use my contact info", "Skip", "Not now"]:
            btn = self.device(text=btn_text)
            if btn.exists(timeout=2):
                btn.click()
                log.info("[%s] Contact info: tapped '%s'",
                         self.device_serial, btn_text)
                random_sleep(1.5, 3.0)
                return

        # May have auto-advanced
        log.info("[%s] Contact info screen not detected — may have been skipped",
                 self.device_serial)

    def _skip_facebook_connect(self):
        """
        Skip the "Connect a Facebook Page" screen.
        Always tap Skip (not "Connect to Facebook" or "Login to Facebook").
        """
        random_sleep(1.5, 3.0, label="facebook_wait")
        xml = self.ctrl.dump_xml("facebook_connect")

        # Prefer "Skip" — the safe option
        for btn_text in ["Skip", "Not now", "Don't connect", "Later"]:
            btn = self.device(text=btn_text)
            if btn.exists(timeout=2):
                btn.click()
                log.info("[%s] Facebook connect: tapped '%s'",
                         self.device_serial, btn_text)
                random_sleep(1.5, 3.0)
                return

        # If Facebook-related text visible but no skip button, press back
        if "Facebook" in xml or "Connect" in xml:
            self.device.press('back')
            log.info("[%s] Facebook connect: pressed back", self.device_serial)
            random_sleep(1.0, 2.0)

    def _dismiss_setup_complete(self):
        """
        Dismiss the "Set Up Your Professional Account" screen.
        Shows "0 of 8 steps complete".
        Close button: d(description="Close") — X icon top-left.
        """
        random_sleep(1.5, 3.0, label="setup_complete_wait")

        for i in range(5):
            xml = self.ctrl.dump_xml("post_switch_%d" % i)

            # Check if we're back on the profile already
            current = self.ctrl.detect_screen(xml)
            if current == Screen.PROFILE:
                log.info("[%s] Already back on profile", self.device_serial)
                return

            # Try Close button (X icon) — primary dismiss on clones
            close_btn = self.device(description="Close")
            if close_btn.exists(timeout=2):
                close_btn.click()
                log.info("[%s] Setup complete: tapped Close (X)",
                         self.device_serial)
                random_sleep(1.5, 3.0)
                continue

            # Try other dismiss buttons
            found = False
            for btn_text in ["Done", "Got it", "Not now", "Skip",
                             "Close", "Maybe later", "Not Now",
                             "Explore professional tools"]:
                btn = self.device(text=btn_text)
                if btn.exists(timeout=1):
                    btn.click()
                    log.info("[%s] Post-switch dismiss: '%s'",
                             self.device_serial, btn_text)
                    found = True
                    random_sleep(1.0, 2.0)
                    break

            if not found:
                # No button found, try back
                self.device.press('back')
                random_sleep(1.0, 2.0)

    def _verify_business_profile(self):
        """Navigate to profile and verify business switch succeeded."""
        self.ctrl.navigate_to(Screen.PROFILE)
        random_sleep(2.0, 4.0, label="verify_profile_load")
        xml = self.ctrl.dump_xml("verify_business")

        indicators = [
            'Professional dashboard',
            'professional_dashboard',
            'views in the last',       # e.g., "153 views in the last 30 days."
            'Insights',
            'Ad tools',
            'Promotions',
        ]
        xml_lower = xml.lower()
        found_list = [ind for ind in indicators if ind.lower() in xml_lower]
        found = len(found_list)
        log.info("[%s] Business verification: %d/%d indicators found: %s",
                 self.device_serial, found, len(indicators), found_list)
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
