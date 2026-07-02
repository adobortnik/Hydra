"""
Scrape Account Status — IG Settings → Account Status section.

The Account Status page shows 4 categories with ✓ (OK) or ⚠ (issue) markers:
  1. Removed content
  2. What can't be recommended
  3. Monetization
  4. Features you can't use

Navigation: Profile → Hamburger menu → Settings and activity → scroll to "Account status"
Or sometimes: Profile → Hamburger → Account Status (direct link in some IG versions)

Stores result as JSON in accounts.account_status_json + accounts.account_status_checked_at
"""
import datetime
import json
import logging
import re
import time

from automation.ig_controller import IGController, Screen
from automation.actions.helpers import get_db, log_action, random_sleep

log = logging.getLogger(__name__)

# Category labels we look for in the XML hierarchy.
# IG sometimes localizes — we keep matchers loose.
CATEGORIES = [
    {'key': 'removed_content',  'label_patterns': ['removed content', 'odstránený obsah']},
    {'key': 'recommendable',    'label_patterns': ["what can't be recommended", "what can not be recommended", 'čo nie je možné odporučiť']},
    {'key': 'monetization',     'label_patterns': ['monetization', 'monetizácia']},
    {'key': 'features_usable',  'label_patterns': ["features you can't use", 'features you can not use', 'funkcie ktoré nemôžete použiť']},
]


class ScrapeAccountStatusAction:
    """Navigate to Settings → Account Status and capture per-category OK/issue state."""

    def __init__(self, device, device_serial, account_info, session_id, pkg=None):
        self.device = device
        self.device_serial = device_serial
        self.account = account_info
        self.session_id = session_id
        self.username = account_info.get('username', '')
        self.account_id = account_info.get('id')
        _pkg = pkg or account_info.get('instagram_package', 'com.instagram.android')
        self.ctrl = IGController(device, device_serial, _pkg)

    def execute(self):
        """
        Navigate to Account Status page, parse the 4 items, save to DB.
        Returns dict with parsed status or None on failure.
        """
        try:
            log.info("[%s] ACCOUNT_STATUS: capture for @%s",
                     self.device_serial, self.username)

            # Navigate to profile first
            if not self.ctrl.navigate_to(Screen.PROFILE):
                log.warning("[%s] ACCOUNT_STATUS: cannot reach profile", self.device_serial)
                return None
            random_sleep(1.0, 1.8)

            # Open hamburger menu (top-right)
            if not self._open_menu():
                return None

            # Find and click "Account Status" (or "Account status")
            if not self._click_account_status():
                self._press_back_safely(2)
                return None

            # Wait for status page to load
            random_sleep(2.0, 3.0, label="account_status_load")

            # Parse the 4 categories
            xml = self.ctrl.dump_xml("account_status")
            result = self._parse_status(xml)

            # Persist
            if result:
                self._save(result)
                log_action(
                    self.session_id, self.device_serial, self.username,
                    'account_status_check', success=True,
                )
                summary = ', '.join(f"{k}={v}" for k, v in result.items() if k != 'captured_at')
                log.info("[%s] ACCOUNT_STATUS: @%s → %s",
                         self.device_serial, self.username, summary)

            # Navigate back to a clean state
            self._press_back_safely(3)
            return result

        except Exception as e:
            log.error("[%s] ACCOUNT_STATUS error for @%s: %s",
                      self.device_serial, self.username, e, exc_info=True)
            try:
                self._press_back_safely(3)
            except Exception:
                pass
            return None

    # ── Navigation helpers ─────────────────────────────────────────────

    def _open_menu(self):
        """
        Click hamburger menu (Options) at top-right of profile screen.
        Modern IG profile uses Compose UI which delays rendering icons —
        we wait + nudge with a tiny scroll so the hamburger appears in
        the hierarchy.
        """
        # Wait for Compose icons to render
        random_sleep(3.0, 4.5, label="profile_compose_render")
        # Tiny scroll to force render if not yet visible
        try:
            self.device.swipe(540, 800, 540, 750, 0.3)
        except Exception:
            pass
        random_sleep(1.0, 2.0)

        candidates = [
            {'description': 'Options'},
            {'descriptionContains': 'Options'},
            {'descriptionContains': 'Menu'},
            {'resourceIdMatches': r'.*action_bar_overflow_button'},
            {'resourceIdMatches': r'.*action_bar_options'},
        ]
        for sel in candidates:
            try:
                el = self.device(**sel)
                if el.exists(timeout=3):
                    el.click()
                    random_sleep(1.5, 2.5, label="menu_opened")
                    return True
            except Exception:
                continue

        log.warning("[%s] ACCOUNT_STATUS: Options/hamburger button not found",
                    self.device_serial)
        return False

    def _click_account_status(self):
        """
        Path: hamburger menu → Settings and activity → scroll down → Account Status

        Account Status is in the lower part of the Settings list (under "More info
        and support" section per IG layout). Need ~5-8 scrolls to reach it.
        """
        # Step 1: Click "Settings and activity" from the hamburger menu
        settings_clicked = False
        for label in ['Settings and activity', 'Settings and privacy', 'Settings', 'Nastavenia']:
            try:
                el = self.device(text=label)
                if el.exists(timeout=3):
                    el.click()
                    random_sleep(2.0, 3.0, label="settings_page_load")
                    settings_clicked = True
                    break
            except Exception:
                continue
        if not settings_clicked:
            log.warning("[%s] ACCOUNT_STATUS: 'Settings and activity' not in menu",
                        self.device_serial)
            return False

        # Step 2: Scroll down to find Account Status (it's near the bottom)
        for attempt in range(10):
            for label in ['Account Status', 'Account status', 'Stav účtu']:
                try:
                    el = self.device(text=label)
                    if el.exists(timeout=1):
                        el.click()
                        random_sleep(2.0, 3.0, label="account_status_load")
                        return True
                except Exception:
                    pass
            # Scroll down in the Settings list
            try:
                self.device(scrollable=True).scroll.forward(steps=30)
            except Exception:
                # Fallback: blind swipe
                try:
                    self.device.swipe(540, 1500, 540, 500, 0.5)
                except Exception:
                    pass
            random_sleep(0.6, 1.0)

        log.warning("[%s] ACCOUNT_STATUS: Account Status link not reached after scrolling",
                    self.device_serial)
        return False

    def _press_back_safely(self, n):
        for _ in range(n):
            try:
                self.ctrl.press_back()
                time.sleep(0.5)
            except Exception:
                break

    # ── Parser ─────────────────────────────────────────────────────────

    def _parse_status(self, xml):
        """
        Parse the 4 category rows from XML.
        For each row, look at the trailing icon's content-desc to determine OK vs issue.
        Returns: {removed_content, recommendable, monetization, features_usable, captured_at}
        """
        result = {'captured_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        xml_lower = (xml or '').lower()

        for cat in CATEGORIES:
            key = cat['key']
            status = 'unknown'
            for label in cat['label_patterns']:
                if label in xml_lower:
                    # Look for the row's status icon nearby. The check icon
                    # usually has content-desc containing 'check', 'no issue',
                    # 'ok', or success/green keywords. Issue icons have
                    # 'warning', 'attention', 'issue', 'restricted'.
                    # We extract a window of text around the label and inspect.
                    idx = xml_lower.find(label)
                    window = xml_lower[idx:idx + 800]
                    is_ok = any(k in window for k in [
                        'no issue', 'check_circle', 'check-circle',
                        'no_issues', "doesn't appear",
                    ])
                    is_warn = any(k in window for k in [
                        'warning', 'attention', 'issue', 'restricted',
                        'violation', 'cannot', 'can\'t use',
                    ])
                    # Default: if we matched a label and saw any "issue" word → warn
                    # If we saw a "check" without issue word → ok
                    if is_warn and not is_ok:
                        status = 'warning'
                    elif is_ok:
                        status = 'ok'
                    else:
                        status = 'ok'  # default to OK if no warning indicators
                    break
            result[key] = status

        return result

    def _save(self, parsed):
        """Persist to accounts.account_status_json + account_status_checked_at."""
        try:
            conn = get_db()
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn.execute(
                "UPDATE accounts SET account_status_json = ?, account_status_checked_at = ? WHERE id = ?",
                (json.dumps(parsed), now, self.account_id)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            log.error("[%s] ACCOUNT_STATUS: failed to save: %s", self.device_serial, e)


def execute_scrape_account_status(device, device_serial, account_info, session_id, pkg=None):
    return ScrapeAccountStatusAction(device, device_serial, account_info, session_id, pkg).execute()
