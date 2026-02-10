"""
Report Action Module — Instagram Profile Reporting via UI Automation
=====================================================================
Reports a target user profile through the Instagram UI.

Verified flow (2026-02-10, tested on androil clone on JACK 1):
1. Navigate to target user's profile (search → open profile)
2. Tap the three-dot menu (⋯) — found via content-desc="Options"
3. Tap "Report" in the bottom sheet menu
4. Tap "Something about this account"
5. Tap "Something else"
6. Select report reason from full list:
   - "Nudity or sexual activity"  (preferred)
   - "Violence, hate or exploitation"  (preferred)
   - "It's spam"
   - "Bullying or unwanted contact"
   - "Scam or fraud"
   - etc.
7. Select sub-reason if prompted (e.g. "Nudity or sexual activity" again)
8. Wait for "Thanks for your feedback" confirmation
9. Tap "Done" → back to profile

Report reason categories for the API:
  'nudity'      → "Nudity or sexual activity" (default/preferred)
  'violence'    → "Violence, hate or exploitation" (preferred)
  'spam'        → "It's spam"
  'fake'        → "They're pretending to be someone else"  (shortcut at step 4)
  'bullying'    → "Bullying or unwanted contact"
  'scam'        → "Scam or fraud"
  'underage'    → "It may be under the age of 13"  (shortcut at step 4)
"""

import logging
import os
import re
import subprocess
import time
from datetime import datetime
from typing import Optional, Tuple

from automation.ig_controller import IGController, Screen
from automation.actions.helpers import (
    random_sleep, log_action,
)

log = logging.getLogger(__name__)

# ── Report flow constants (verified 2026-02-10) ─────────────────────

# Step 4 options: "Why are you reporting this profile?"
# 'fake' and 'underage' are shortcuts here (no need for "Something else")
STEP4_SHORTCUTS = {
    'fake': "They are pretending to be someone else",
    'underage': "It may be under the age of 13",
}

# Step 6 options: after "Something else" → "What do you want to report?"
REPORT_REASON_TEXTS = {
    'nudity': [
        "Nudity or sexual activity",
    ],
    'violence': [
        "Violence, hate or exploitation",
        "Violence or dangerous",
    ],
    'spam': [
        "It's spam",
    ],
    'bullying': [
        "Bullying or unwanted contact",
        "Bullying or harassment",
    ],
    'scam': [
        "Scam or fraud",
        "Scam",
    ],
    'suicide': [
        "Suicide, self-injury or eating disorders",
    ],
    'selling': [
        "Selling or promoting restricted items",
    ],
    'dislike': [
        "I just don't like it",
    ],
    # Legacy aliases
    'inappropriate': ["Nudity or sexual activity"],
    'harassment': ["Bullying or unwanted contact"],
}

# Sub-reason texts (step 7) — for reasons that have sub-menus
REPORT_SUB_REASONS = {
    'nudity': [
        "Nudity or sexual activity",  # generic catch-all sub-option
        "Seems like sexual exploitation",
        "Threatening to share or sharing nude images",
        "Seems like prostitution",
    ],
    'violence': [
        "Violence, hate or exploitation",
        "Violent threat",
        "Hate speech or symbols",
        "Dangerous organizations or individuals",
    ],
}

# Success screen detection
REPORT_SUCCESS_TEXTS = [
    "Thanks for your feedback",
    "Thank you",
    "Thanks for letting us know",
    "We'll look into this",
    "Report submitted",
    "You've reported this",
]


class ReportAction:
    """
    Report a target user's Instagram profile.
    Uses IGController for reliable UI automation with vision-assisted fallbacks.
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

        # Screenshots dir
        self.screenshots_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))),
            "screenshots", "report_flow"
        )
        os.makedirs(self.screenshots_dir, exist_ok=True)

        # Step counter for ordered screenshots
        self._step_counter = 0

    # ──────────────────────────────────────────────────────────────────
    # Screenshot / Vision Helpers
    # ──────────────────────────────────────────────────────────────────

    def _capture_step(self, step_name: str) -> Optional[str]:
        """
        Capture screenshot for debugging/development.
        Saves to screenshots/report_flow/{serial}_{step}_{timestamp}.png
        Returns filepath or None on failure.
        """
        self._step_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        serial_safe = self.device_serial.replace(':', '_').replace('.', '_')
        filename = f"{serial_safe}_{self._step_counter:02d}_{step_name}_{timestamp}.png"
        filepath = os.path.join(self.screenshots_dir, filename)

        try:
            adb_serial = self.device_serial.replace('_', ':')
            result = subprocess.run(
                ["adb", "-s", adb_serial, "exec-out", "screencap", "-p"],
                capture_output=True, timeout=15
            )
            if result.returncode == 0 and len(result.stdout) > 1000:
                with open(filepath, "wb") as f:
                    f.write(result.stdout)
                log.debug("[%s] Screenshot saved: %s", self.device_serial, filename)
                return filepath
            else:
                log.warning("[%s] Screenshot capture returned %d bytes (rc=%d)",
                           self.device_serial, len(result.stdout), result.returncode)
        except subprocess.TimeoutExpired:
            log.warning("[%s] Screenshot capture timed out", self.device_serial)
        except Exception as e:
            log.error("[%s] Screenshot capture error: %s", self.device_serial, e)

        return None

    def _dump_and_capture(self, step_name: str) -> str:
        """Dump XML hierarchy and capture screenshot. Returns XML string."""
        xml = self.ctrl.dump_xml(step_name)
        self._capture_step(step_name)
        return xml or ""

    def _find_and_tap_text(self, texts: list, timeout: float = 3,
                           partial: bool = True) -> bool:
        """
        Try to find and tap an element matching any of the given texts.
        Tries exact match first, then partial (contains) match.
        Returns True if tapped successfully.
        """
        for text in texts:
            # Exact match
            el = self.device(text=text)
            if el.exists(timeout=min(timeout, 1.5)):
                try:
                    el.click()
                    log.info("[%s] Tapped text: '%s'", self.device_serial, text)
                    return True
                except Exception as e:
                    log.debug("[%s] Failed to tap '%s': %s", self.device_serial, text, e)

        if partial:
            for text in texts:
                # Partial / contains match
                el = self.device(textContains=text)
                if el.exists(timeout=min(timeout, 1.5)):
                    try:
                        el.click()
                        matched_text = ""
                        try:
                            matched_text = el.get_text()
                        except Exception:
                            pass
                        log.info("[%s] Tapped textContains: '%s' (matched: '%s')",
                                self.device_serial, text, matched_text)
                        return True
                    except Exception as e:
                        log.debug("[%s] Failed to tap contains '%s': %s",
                                 self.device_serial, text, e)

        return False

    def _find_and_tap_desc(self, descs: list, timeout: float = 3) -> bool:
        """Try to find and tap an element matching content-description."""
        for desc in descs:
            el = self.device(description=desc)
            if el.exists(timeout=min(timeout, 1.5)):
                try:
                    el.click()
                    log.info("[%s] Tapped desc: '%s'", self.device_serial, desc)
                    return True
                except Exception as e:
                    log.debug("[%s] Failed to tap desc '%s': %s",
                             self.device_serial, desc, e)

            # Try descriptionContains
            el = self.device(descriptionContains=desc)
            if el.exists(timeout=min(timeout, 1)):
                try:
                    el.click()
                    log.info("[%s] Tapped descContains: '%s'", self.device_serial, desc)
                    return True
                except Exception as e:
                    log.debug("[%s] Failed to tap descContains '%s': %s",
                             self.device_serial, desc, e)

        return False

    def _scroll_and_find_text(self, texts: list, max_scrolls: int = 3) -> bool:
        """Scroll down looking for text, tap it when found."""
        for scroll_i in range(max_scrolls):
            if self._find_and_tap_text(texts, timeout=1.5):
                return True
            # Scroll down a bit
            w, h = self.ctrl.window_size
            self.device.swipe(w // 2, int(h * 0.65), w // 2, int(h * 0.35), duration=0.3)
            time.sleep(1)
        return False

    # ──────────────────────────────────────────────────────────────────
    # Main Execute
    # ──────────────────────────────────────────────────────────────────

    def execute(self, target_username: str, report_reason: str = 'spam') -> dict:
        """
        Report a user profile.

        Args:
            target_username: Instagram username to report (without @)
            report_reason: One of 'spam', 'inappropriate', 'fake', 'harassment'

        Returns:
            dict with keys: success (bool), message (str), step_failed (str or None)
        """
        result = {
            'success': False,
            'message': '',
            'step_failed': None,
            'screenshots': [],
        }

        target = target_username.lstrip('@').strip().lower()
        reason = report_reason.lower() if report_reason else 'nudity'
        if reason not in REPORT_REASON_TEXTS:
            # Try to map old reason names
            reason_map = {
                'inappropriate': 'nudity',
                'sexual': 'nudity',
                'hate': 'violence',
                'harassment': 'bullying',
                'fraud': 'scam',
            }
            reason = reason_map.get(reason, 'nudity')

        log.info("[%s] ═══ REPORT JOB: @%s reporting @%s (reason: %s) ═══",
                 self.device_serial, self.username, target, reason)

        try:
            # ── Step 0: Ensure app is running ────────────────────────
            self.ctrl.ensure_app()
            self.ctrl.dismiss_popups()
            self._dump_and_capture("00_initial_state")

            # ── Step 1: Navigate to target profile ───────────────────
            log.info("[%s] Step 1: Searching for @%s", self.device_serial, target)
            if not self.ctrl.search_user(target):
                result['message'] = f"Could not find user @{target}"
                result['step_failed'] = 'search_user'
                self._dump_and_capture("01_search_failed")
                log.warning("[%s] Report failed: %s", self.device_serial, result['message'])
                return result

            self._dump_and_capture("01_on_profile")
            random_sleep(1, 3, label="on_target_profile")

            # ── Step 2: Tap three-dot menu ───────────────────────────
            log.info("[%s] Step 2: Opening three-dot menu", self.device_serial)
            if not self._tap_three_dot_menu():
                result['message'] = "Could not find three-dot menu on profile"
                result['step_failed'] = 'three_dot_menu'
                self._dump_and_capture("02_menu_not_found")
                log.warning("[%s] Report failed: %s", self.device_serial, result['message'])
                self._cleanup()
                return result

            self._dump_and_capture("02_menu_opened")
            random_sleep(0.5, 1.5, label="menu_opened")

            # ── Step 3: Tap "Report" in menu ─────────────────────────
            log.info("[%s] Step 3: Tapping Report option", self.device_serial)
            if not self._tap_report_option():
                result['message'] = "Could not find 'Report' in menu"
                result['step_failed'] = 'tap_report'
                self._dump_and_capture("03_report_not_found")
                log.warning("[%s] Report failed: %s", self.device_serial, result['message'])
                self._cleanup()
                return result

            self._dump_and_capture("03_report_tapped")
            random_sleep(0.5, 1.5, label="report_dialog")

            # ── Step 4: "Something about this account" ─────────────
            log.info("[%s] Step 4: Report type selection", self.device_serial)
            if not self._step4_report_type(reason):
                result['message'] = "Could not navigate report type screen"
                result['step_failed'] = 'report_type'
                self._dump_and_capture("04_type_failed")
                log.warning("[%s] Report failed: %s", self.device_serial, result['message'])
                self._cleanup()
                return result
            self._dump_and_capture("04_type_done")
            random_sleep(0.5, 1.5, label="report_type")

            # ── Step 5: "Something else" (unless shortcut) ───────────
            if reason not in STEP4_SHORTCUTS:
                log.info("[%s] Step 5: 'Something else'", self.device_serial)
                if not self._step5_something_else():
                    result['message'] = "Could not tap 'Something else'"
                    result['step_failed'] = 'something_else'
                    self._dump_and_capture("05_else_failed")
                    log.warning("[%s] Report failed: %s", self.device_serial, result['message'])
                    self._cleanup()
                    return result
                self._dump_and_capture("05_else_done")
                random_sleep(0.5, 1.5, label="something_else")

                # ── Step 6: Select specific reason ───────────────────
                log.info("[%s] Step 6: Selecting reason: %s", self.device_serial, reason)
                if not self._step6_select_reason(reason):
                    result['message'] = f"Could not select reason: {reason}"
                    result['step_failed'] = 'select_reason'
                    self._dump_and_capture("06_reason_failed")
                    log.warning("[%s] Report failed: %s", self.device_serial, result['message'])
                    self._cleanup()
                    return result
                self._dump_and_capture("06_reason_done")
                random_sleep(0.5, 1.5, label="reason_selected")

            # ── Step 7: Sub-reason if needed ─────────────────────────
            log.info("[%s] Step 7: Sub-reason / confirmation", self.device_serial)
            self._step7_sub_reason_and_confirm(reason)
            self._dump_and_capture("07_confirmed")
            random_sleep(1, 2, label="report_confirmed")

            # ── Step 8: Navigate back to clean state ─────────────────
            log.info("[%s] Step 8: Navigating back", self.device_serial)
            self._cleanup()
            self._dump_and_capture("08_cleanup_done")

            result['success'] = True
            result['message'] = f"Successfully reported @{target} for {reason}"
            log.info("[%s] ✓ Report completed: @%s reported @%s for %s",
                     self.device_serial, self.username, target, reason)

        except Exception as e:
            result['message'] = f"Exception during report: {str(e)[:200]}"
            result['step_failed'] = 'exception'
            log.error("[%s] Report exception: %s", self.device_serial, e, exc_info=True)
            self._capture_step("error_exception")
            self._cleanup()

        return result

    # ──────────────────────────────────────────────────────────────────
    # Step Implementations
    # ──────────────────────────────────────────────────────────────────

    def _tap_three_dot_menu(self) -> bool:
        """
        Tap the three-dot (⋯) overflow menu on a profile page.
        Tries multiple selectors: resource ID, content-desc, coordinate fallback.
        """
        # Method 1: Resource ID (profile_header_overflow_icon / overflow_icon)
        for rid in ['profile_header_overflow_icon', 'overflow_icon',
                    'action_bar_overflow_icon', 'action_bar_button_action']:
            el = self.device(resourceIdMatches=self.ctrl._rid_match(rid))
            if el.exists(timeout=2):
                el.click()
                time.sleep(1.5)
                log.info("[%s] Three-dot menu opened via resourceId: %s",
                        self.device_serial, rid)
                return True

        # Method 2: Content description
        for desc in ['Options', 'More options', 'Menu', '⋯']:
            el = self.device(description=desc)
            if el.exists(timeout=1.5):
                el.click()
                time.sleep(1.5)
                log.info("[%s] Three-dot menu opened via desc: %s",
                        self.device_serial, desc)
                return True

        # Method 3: Find ImageView/ImageButton with "option" or "more" in desc
        el = self.device(descriptionMatches="(?i).*(option|more|menu).*",
                         className="android.widget.ImageView")
        if el.exists(timeout=1.5):
            el.click()
            time.sleep(1.5)
            log.info("[%s] Three-dot menu opened via ImageView desc match",
                    self.device_serial)
            return True

        # Method 4: Coordinate-based fallback — top-right area of screen
        # The three-dot menu is usually in the top-right corner
        w, h = self.ctrl.window_size
        # Try clicking at approximate position (near top-right, below status bar)
        for x_pct, y_px in [(0.92, 80), (0.95, 80), (0.90, 100)]:
            x = int(w * x_pct)
            self.device.click(x, y_px)
            time.sleep(1.5)

            # Check if a menu/sheet appeared
            xml = self.ctrl.dump_xml("menu_check")
            if xml and any(indicator in xml for indicator in [
                'action_sheet_container', 'Report', 'Block', 'Restrict',
                'Share this profile', 'About this account',
                'Copy profile URL', 'Share Profile'
            ]):
                log.info("[%s] Three-dot menu opened via coordinate tap (%d, %d)",
                        self.device_serial, x, y_px)
                return True

        log.warning("[%s] Could not find three-dot menu", self.device_serial)
        return False

    def _tap_report_option(self) -> bool:
        """
        From the opened menu/bottom sheet, tap the "Report" option.
        """
        # Try text match first
        report_texts = ["Report", "Report…", "Report...", "Report this account"]
        if self._find_and_tap_text(report_texts, timeout=3):
            time.sleep(1.5)
            return True

        # Try content-desc
        if self._find_and_tap_desc(["Report"], timeout=2):
            time.sleep(1.5)
            return True

        # Scroll within the menu to find Report (might be below fold)
        if self._scroll_and_find_text(report_texts, max_scrolls=3):
            time.sleep(1.5)
            return True

        # XML-based fallback: find "Report" in dump
        xml = self.ctrl.dump_xml("find_report_option")
        if xml:
            # Find all TextViews with "Report" text
            nodes = self.ctrl._find_all_in_xml(xml, text="Report")
            for node in nodes:
                bounds = node.get('bounds', '')
                if bounds:
                    cx, cy = self.ctrl._bounds_center(bounds)
                    if cx > 0 and cy > 0:
                        self.device.click(cx, cy)
                        time.sleep(1.5)
                        log.info("[%s] Tapped 'Report' via XML bounds at (%d,%d)",
                                self.device_serial, cx, cy)
                        return True

        log.warning("[%s] 'Report' option not found in menu", self.device_serial)
        return False

    # ──────────────────────────────────────────────────────────────────
    # NEW Step Implementations (verified 2026-02-10)
    # ──────────────────────────────────────────────────────────────────

    def _step4_report_type(self, reason: str) -> bool:
        """
        Step 4: Handle "What do you want to report?" screen.
        
        Screen shows:
          - "A specific post"
          - "Something about this account"
        
        For 'fake' and 'underage', there's a shortcut at the
        "Why are you reporting?" screen (step before "Something else").
        For everything else, tap "Something about this account".
        """
        # Wait for the report type screen to appear
        for _ in range(5):
            el = self.device(textContains="Something about this account")
            if el.exists(timeout=1.5):
                el.click()
                log.info("[%s] Tapped 'Something about this account'",
                        self.device_serial)
                time.sleep(2)
                return True
            # Maybe it shows a different initial screen
            el2 = self.device(textContains="A specific post")
            if el2.exists(timeout=0.5):
                # We're on the right screen, just need to find our option
                break
            time.sleep(1)

        # Fallback: text-based search in XML
        return self._find_and_tap_text(
            ["Something about this account"], timeout=3
        )

    def _step5_something_else(self) -> bool:
        """
        Step 5: Handle "Why are you reporting this profile?" screen.
        
        Screen shows:
          - "They are pretending to be someone else"
          - "It may be under the age of 13"
          - "Something else"
        
        Always tap "Something else" to get to the full reasons list.
        """
        for _ in range(5):
            el = self.device(text="Something else")
            if el.exists(timeout=1.5):
                el.click()
                log.info("[%s] Tapped 'Something else'", self.device_serial)
                time.sleep(2)
                return True
            # Also try partial match
            el = self.device(textContains="Something else")
            if el.exists(timeout=0.5):
                el.click()
                time.sleep(2)
                return True
            time.sleep(1)
        return False

    def _step6_select_reason(self, reason: str) -> bool:
        """
        Step 6: Select specific reason from full list.
        
        Screen "What do you want to report?" shows:
          - It's spam
          - I just don't like it
          - Bullying or unwanted contact
          - Suicide, self-injury or eating disorders
          - Violence, hate or exploitation
          - Selling or promoting restricted items
          - Nudity or sexual activity
          - Scam or fraud
        
        Some options are below the fold — scroll if needed.
        """
        reason_texts = REPORT_REASON_TEXTS.get(reason, REPORT_REASON_TEXTS['nudity'])

        # Try direct tap first
        if self._find_and_tap_text(reason_texts, timeout=3):
            time.sleep(2)
            return True

        # Scroll down and retry (nudity is near bottom of list)
        if self._scroll_and_find_text(reason_texts, max_scrolls=3):
            time.sleep(2)
            return True

        # Fallback: try nudity if original reason not found
        if reason != 'nudity':
            log.info("[%s] Reason '%s' not found, falling back to 'nudity'",
                    self.device_serial, reason)
            if self._scroll_and_find_text(["Nudity or sexual activity"], max_scrolls=2):
                time.sleep(2)
                return True

        # Last fallback: spam (always visible without scrolling)
        if reason != 'spam':
            log.info("[%s] Falling back to 'spam'", self.device_serial)
            if self._find_and_tap_text(["It's spam", "spam"], timeout=2):
                time.sleep(2)
                return True

        return False

    def _step7_sub_reason_and_confirm(self, reason: str):
        """
        Step 7: Handle sub-reason screen and confirmation.
        
        After selecting a reason like "Nudity or sexual activity", IG shows:
          "How is this nudity or sexual activity?"
          - Threatening to share or sharing nude images
          - Seems like prostitution
          - Seems like sexual exploitation
          - Nudity or sexual activity  (generic catch-all)
        
        After tapping a sub-reason, IG shows:
          "Thanks for your feedback"
          [Done] button
        
        For 'spam' there's no sub-reason — it goes straight to confirmation.
        """
        max_steps = 6

        for step_i in range(max_steps):
            time.sleep(1)
            xml = self._dump_and_capture(f"07_sub_{step_i}")

            # ── Check for success screen ──
            if self._is_success_screen(xml):
                log.info("[%s] Report success! (sub-step %d)", self.device_serial, step_i)
                self._find_and_tap_text(["Done", "Close", "OK", "Got it"], timeout=3)
                time.sleep(1)
                return

            # ── Try sub-reasons for this reason type ──
            sub_texts = REPORT_SUB_REASONS.get(reason, [])
            if sub_texts:
                # For "Nudity or sexual activity" sub-reason, we want the one
                # that appears as a list item (lower on screen), not the header.
                # Use scroll_and_find to handle off-screen items.
                if self._scroll_and_find_text(sub_texts, max_scrolls=2):
                    log.info("[%s] Tapped sub-reason for '%s'",
                            self.device_serial, reason)
                    time.sleep(2)
                    # Clear sub_texts so next loop iteration doesn't re-tap
                    sub_texts = []
                    continue

            # ── Try generic submit/done/close buttons ──
            for btn_text in ["Submit report", "Submit", "Done", "Close",
                            "Next", "Continue", "Got it"]:
                el = self.device(text=btn_text)
                if el.exists(timeout=1):
                    el.click()
                    log.info("[%s] Tapped '%s' (sub-step %d)",
                            self.device_serial, btn_text, step_i)
                    time.sleep(1.5)
                    break
            else:
                # Nothing found — might already be done
                if step_i >= 2:
                    log.info("[%s] Sub-reason loop exhausted after %d steps",
                            self.device_serial, step_i + 1)
                    self._find_and_tap_text(["Done", "Close"], timeout=1)
                    return

    def _is_success_screen(self, xml: str) -> bool:
        """Check if the current screen is the report success/thank-you screen."""
        if not xml:
            return False
        xml_lower = xml.lower()
        return any(txt.lower() in xml_lower for txt in REPORT_SUCCESS_TEXTS)

    def _cleanup(self):
        """Navigate back to a clean state (home feed)."""
        # Press back multiple times to close any dialogs/sheets
        for _ in range(5):
            self.ctrl.press_back()
            time.sleep(0.5)
            # Check if we're on home or search
            try:
                screen = self.ctrl.detect_screen()
                if screen in (Screen.HOME_FEED, Screen.SEARCH):
                    break
            except Exception:
                pass

        # Try to navigate to home
        try:
            self.ctrl.navigate_to(Screen.HOME_FEED, max_attempts=2)
        except Exception:
            pass
