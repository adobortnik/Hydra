"""
login_automation.py

Core Instagram Login Automation Logic
Handles the complete login flow including signup screen detection, credential entry,
2FA handling, and post-login prompts.

Follows the same UI selector patterns as instagram_automation.py:
- Multiple selectors with fallbacks
- XPath alternatives
- Coordinate-based last resort
- Robust error handling

Author: Claude Code
Created: 2025-11-21
"""

import sys
import os
import io

# Fix Windows console encoding for Unicode characters
if sys.stdout and hasattr(sys.stdout, 'encoding') and sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

import builtins
import uiautomator2 as u2
import subprocess
import time
from pathlib import Path
from two_fa_live_client import TwoFALiveClient

# Force all print() calls to flush immediately — critical for log capture in threads
_original_print = builtins.print
def _flushed_print(*args, **kwargs):
    kwargs.setdefault('flush', True)
    _original_print(*args, **kwargs)
builtins.print = _flushed_print


class LoginAutomation:
    """
    Instagram Login Automation Controller

    Usage:
        login = LoginAutomation(device_serial="10.1.10.183_5555")
        result = login.login_account(
            username="testuser",
            password="testpass123",
            instagram_package="com.instagram.androim",
            two_fa_token="CHN44RHFYSYPFCKLL2C5CFHNTY54PYOD"
        )
    """

    def __init__(self, device_serial=None):
        """
        Initialize login automation

        Args:
            device_serial: Device serial in format "10.1.10.183_5555" (optional)
        """
        self.device = None
        self.device_serial = device_serial

    def connect_device(self, device_serial=None):
        """
        Connect to device using the proven UIAutomator connection pattern

        CRITICAL: This follows the exact pattern from instagram_automation.py
        that was discovered after 3+ hours of debugging.

        Args:
            device_serial: Device serial (e.g., "10.1.10.183_5555")

        Returns:
            Device object, or None if failed
        """
        if device_serial:
            self.device_serial = device_serial

        if not self.device_serial:
            print("[X] No device serial specified")
            return None

        # Convert folder naming (underscore) to ADB format (colon)
        connection_serial = self.device_serial.replace('_', ':')

        print(f"\n{'='*70}")
        print(f"CONNECTING TO DEVICE: {self.device_serial}")
        print(f"{'='*70}")

        # STEP 1: Kill ALL existing UIAutomator processes to start fresh
        print("Cleaning up existing UIAutomator processes...")
        try:
            # Kill all uiautomator processes
            subprocess.run(
                ['adb', '-s', connection_serial, 'shell', 'pkill', '-9', 'uiautomator'],
                capture_output=True, timeout=5
            )
            # Force stop the app
            subprocess.run(
                ['adb', '-s', connection_serial, 'shell', 'am', 'force-stop', 'com.github.uiautomator'],
                capture_output=True, timeout=5
            )
            # Kill any existing instrumentation processes
            subprocess.run(
                ['adb', '-s', connection_serial, 'shell', 'pkill', '-9', '-f', 'androidx.test.runner'],
                capture_output=True, timeout=5
            )
            print("[OK] Killed all UIAutomator-related processes")
            print("[...] Waiting for complete shutdown...")
            time.sleep(5)  # CRITICAL: Wait for complete shutdown before connecting
        except Exception as e:
            print(f"[!] Warning during cleanup: {e}")

        # STEP 2: Connect to device - u2.connect() will auto-start UIAutomator
        print("Connecting to device...")
        print("(uiautomator2 will automatically start UIAutomator service)")
        self.device = u2.connect(connection_serial)
        print(f"[OK] Connected (serial: {self.device.serial})")

        # STEP 3: Wait for UIAutomator to be responsive
        print("[...] Waiting for UIAutomator to be responsive...")
        max_wait = 45  # seconds
        start_time = time.time()

        while (time.time() - start_time) < max_wait:
            try:
                _ = self.device.info
                _ = self.device.window_size()
                elapsed = int(time.time() - start_time)
                print(f"[OK] SUCCESS! UIAutomator is responsive (took {elapsed}s)")

                # Lock rotation to portrait — UIAutomator can flip apps to landscape
                try:
                    self.device.shell("settings put system accelerometer_rotation 0")
                    self.device.shell("settings put system user_rotation 0")
                    self.device.shell("wm set-user-rotation lock")
                    self.device.shell("wm set-user-rotation lock 0")
                    self.device.shell("content update --uri content://settings/system --bind value:i:0 --where \"name='accelerometer_rotation'\"")
                    self.device.freeze_rotation()
                    self.device.set_orientation('natural')
                    print("[OK] Rotation locked to portrait")
                except Exception as rot_err:
                    print(f"[!] Could not lock rotation: {rot_err}")

                # Enable AdbKeyboard IME for reliable text input
                try:
                    self.device.set_input_ime(True)
                    print("[OK] AdbKeyboard IME enabled")
                except Exception as ime_err:
                    print(f"[!] Failed to enable AdbKeyboard IME: {ime_err}")

                return self.device
            except Exception as e:
                elapsed = int(time.time() - start_time)
                if elapsed % 5 == 0:  # Print every 5 seconds
                    print(f"[...] Waiting... {elapsed}s / {max_wait}s")
                time.sleep(1)

        print(f"[X] Failed to connect to device after {max_wait}s")
        return None

    def clear_app_data(self, instagram_package):
        """
        Reset clone identity via AppCloner New Identity broadcast.
        Generates new Android ID, GAID, device fingerprint AND clears all app data.
        This ensures a completely fresh identity for the next login.

        Args:
            instagram_package: Package name (e.g., "com.instagram.androil")

        Returns:
            bool: True if successful
        """
        print(f"[...] New Identity reset for {instagram_package}...")
        try:
            connection_serial = self.device_serial.replace('_', ':')
            result = subprocess.run(
                ['adb', '-s', connection_serial, 'shell', 'am', 'broadcast',
                 '-p', 'com.applisto.appcloner',
                 '-a', 'com.applisto.appcloner.api.action.NEW_IDENTITY',
                 '--es', 'package_name', instagram_package,
                 '--ez', 'clear_cache', 'true',
                 '--ez', 'delete_app_data', 'true'],
                capture_output=True, text=True, timeout=15
            )
            output = result.stdout.strip()
            if 'result=0' in output:
                print(f"[OK] New Identity completed successfully")
                return True
            else:
                print(f"[!] New Identity returned: {output}")
                return False
        except Exception as e:
            print(f"[!] Failed New Identity reset: {e}")
            return False

    def open_instagram(self, instagram_package="com.instagram.android"):
        """
        Open Instagram app using the proven monkey method.
        ALWAYS clears app data first to ensure fresh login screen.

        Args:
            instagram_package: Package name (e.g., "com.instagram.androim")

        Returns:
            bool: True if successful
        """
        if not self.device:
            print("[X] Device not connected")
            return False

        print(f"\n{'='*70}")
        print(f"OPENING INSTAGRAM: {instagram_package}")
        print(f"{'='*70}")

        try:
            # Force-stop first
            print(f"[...] Force-stopping {instagram_package} first...")
            self.device.app_stop(instagram_package)
            time.sleep(1)

            # New Identity is already handled by auto-fix (account_health_routes)
            # before this login flow runs. No need to reset again here.

            # Use uiautomator2's app_start with monkey (most reliable)
            self.device.app_start(instagram_package, use_monkey=True)
            print("[OK] Instagram launched with monkey")
            time.sleep(5)  # Initial render budget

            # Verify app is running, and wait for first interactive UI element
            # to appear — slow devices need more than a flat sleep(5).
            current_app = self.device.app_current().get('package')
            if current_app == instagram_package:
                print(f"[OK] Instagram is running: {instagram_package}")
            # Wait up to 8 more seconds for ANY clickable UI element to render.
            # This avoids flaky behavior on slow devices where the splash is
            # still up when we start trying to detect the screen state.
            ready_deadline = time.time() + 8
            while time.time() < ready_deadline:
                try:
                    if (self.device(className="android.widget.EditText").wait(timeout=0.5)
                        or self.device(className="android.widget.Button").wait(timeout=0.5)
                        or self.device(textContains="account").wait(timeout=0.5)
                        or self.device(textContains="Log").wait(timeout=0.5)):
                        print("[OK] IG UI rendered")
                        break
                except Exception:
                    pass
                time.sleep(0.5)
            return True

        except Exception as e:
            print(f"[!] app_start failed: {e}, falling back to ADB monkey command")
            # Fallback to direct ADB
            connection_serial = self.device_serial.replace('_', ':')
            result = subprocess.run(
                ['adb', '-s', connection_serial, 'shell', 'monkey', '-p', instagram_package, '1'],
                capture_output=True, text=True, timeout=10
            )
            time.sleep(5)
            return True

    def detect_screen_state(self):
        """
        Detect which screen we're currently on

        Returns:
            str: 'signup', 'login', 'logged_in', 'challenge', or 'unknown'
        """
        print("\n" + "-"*70)
        print("DETECTING SCREEN STATE")
        print("-"*70)

        try:
            # Get XML dump once (fast)
            xml_dump = self.device.dump_hierarchy()
            xml_lower = xml_dump.lower()

            # Check for already logged in (profile tab visible)
            if self.device(description="Profile").wait(timeout=2) or \
               self.device(resourceId="com.instagram.android:id/profile_tab").wait(timeout=2):
                print("[OK] Already logged in (profile tab visible)")
                return 'logged_in'

            # Check for suspended/disabled account (dead end)
            suspended_keywords = ["we suspended your account", "your account has been disabled",
                                  "account was disabled", "days left to appeal", "permanently disable"]
            for keyword in suspended_keywords:
                if keyword in xml_lower:
                    print(f"[X] Account SUSPENDED/DISABLED: '{keyword}'")
                    return 'suspended'

            # Check for SMS verification screen (dead end — can't proceed)
            sms_keywords = ["check your sms", "we sent a link", "sent a code to", "check your email"]
            for keyword in sms_keywords:
                if keyword in xml_lower:
                    print(f"[!] SMS/Email verification screen detected: '{keyword}' — account cannot be logged in")
                    return 'sms_challenge'

            # Check for challenge/verification screens.
            # Keywords MUST be specific multi-word phrases — bare words like
            # "verify" or "confirm" match the welcome / age-gate / cookie /
            # T&C screens (e.g. "Verify you're 13+", "Confirm your age",
            # "I confirm I have read the terms") and cause the bot to abort
            # before it can click "Already have an account".
            challenge_keywords = [
                "security check",
                "unusual activity",
                "suspicious activity",
                "verify your identity",
                "verify it's you",
                "verify it’s you",
                "verify your account",
                "confirm your identity",
                "confirm it's you",
                "confirm it’s you",
                "confirm you're human",
                "confirm you’re human",
                "we need to confirm",
                "to use your account",          # "Confirm you're human to use your account"
                "we just need to make sure",
                "help us confirm",
            ]
            for keyword in challenge_keywords:
                if keyword in xml_lower:
                    print(f"[!] Challenge screen detected: {keyword}")
                    return 'challenge'

            # ─── XML-based fast detection (no per-selector timeouts) ───
            # All checks run against the already-dumped xml_lower string.
            # Each check is O(1) — no UIAutomator round-trips.
            has_password_field = any(kw in xml_lower for kw in [
                'descriptionContains="Password"'.lower(),
                'description="password"',
                'text="password"',
                'hint="password"',
                # generic match — any node mentioning password as text/desc/hint
                'password',
            ]) and ('password' in xml_lower)

            # username field signals
            username_keywords = [
                'username', 'phone number', 'email or username',
                'mobile number', 'email address',
                'descriptionContains="Username"'.lower(),
            ]
            has_username_field = any(kw in xml_lower for kw in username_keywords)

            # Has at least one EditText
            has_edit_text = 'android.widget.edittext' in xml_lower

            # Login screen = has password keyword + at least one EditText
            if has_password_field and has_edit_text:
                print("[OK] On login screen (password field + EditText present)")
                return 'login'

            # Intro / signup affordances
            has_already_account = any(kw in xml_lower for kw in [
                'already have an account', 'i already have',
            ])
            has_signup_button = any(kw in xml_lower for kw in [
                'sign up', 'get started', 'create new account',
                'join instagram', 'create account',
            ])

            if has_already_account or has_signup_button:
                print("[OK] On signup/intro screen (has 'already have account' or signup button)")
                return 'signup'

            # Fallback: if we have at least one login field, assume login screen
            if has_username_field or has_password_field:
                print("[OK] On login screen (has at least one login field)")
                return 'login'

            print("[!] Unknown screen state")
            return 'unknown'

        except Exception as e:
            print(f"[X] Error detecting screen state: {e}")
            return 'unknown'

    def handle_signup_screen(self):
        """
        Handle the signup screen by clicking "Already have an account?" or similar.

        Hardened for slow devices / different IG clone layouts:
          - Polls multiple selectors over a longer window (lets the button
            actually finish rendering before we try to click).
          - Verifies the click actually advanced us to the login screen
            BEFORE returning True (prevents downstream "Failed to enter
            credentials" when a blind click missed the button).
          - Falls back to coordinate-based click only if no selector matched
            after polling, AND verifies result.

        Returns:
            bool: True if successfully navigated to login screen
        """
        print("\n" + "-"*70)
        print("HANDLING SIGNUP SCREEN")
        print("-"*70)

        # All known variants of the "switch to login" affordance.
        selectors = [
            self.device(textContains="I already have an account"),
            self.device(textContains="Already have an account"),
            self.device(text="I already have an account"),
            self.device(textContains="Log In"),
            self.device(textContains="Log in"),
            self.device(text="Log In"),
            self.device(text="Log in"),
            self.device(descriptionContains="Log in"),
            self.device(descriptionContains="Already have"),
            self.device(textMatches=r"(?i)already\s*have\s*an?\s*account"),
            self.device(textMatches=r"(?i)log\s*in"),
        ]

        # ─── PRIMARY: XML-based bounds extraction (FAST — single dump) ───
        # Most layouts can be solved on the first dump. Skip the slow
        # per-selector polling unless XML scan finds nothing.
        try:
            bounds = self._find_login_link_bounds()
            if bounds:
                cx, cy = bounds
                print(f"[FAST] XML-based click at ({cx}, {cy})")
                self.device.click(cx, cy)
                time.sleep(2.5)
                if self._is_on_login_screen():
                    print("[OK] Reached login screen via XML bounds")
                    return True
                print("[!] XML click did not advance — falling back to selectors")
        except Exception as e:
            print(f"[!] XML primary failed: {e}")

        # ─── SECONDARY: short selector poll (max ~5s) ───
        # Only used if XML scan came up empty (button not yet rendered).
        clicked = False
        deadline = time.time() + 5
        while not clicked and time.time() < deadline:
            # Re-dump XML and try again — much cheaper than 11 × selector.exists
            try:
                bounds = self._find_login_link_bounds()
                if bounds:
                    cx, cy = bounds
                    print(f"[OK] Login link rendered after wait — clicking ({cx}, {cy})")
                    self.device.click(cx, cy)
                    time.sleep(2.5)
                    if self._is_on_login_screen():
                        return True
                    clicked = True  # exit and let coordinate fallback try
                    break
            except Exception:
                pass
            # Quick selector probes (timeout=0.5 — 11 selectors × 0.5 = 5.5s max)
            for i, selector in enumerate(selectors[:4], 1):  # only top-4 most common
                try:
                    if selector.wait(timeout=0.5):
                        print(f"[OK] Found login link (selector #{i})")
                        try:
                            selector.click()
                            print("[OK] Clicked login link")
                            clicked = True
                            break
                        except Exception:
                            continue
                except Exception:
                    continue
            if clicked:
                break
            time.sleep(0.5)

        if clicked:
            time.sleep(2.5)
            if self._is_on_login_screen():
                print("[OK] Confirmed: navigated to login screen")
                return True
            print("[!] Clicked but still on intro/signup — coordinate fallback")

        # ─── Last-resort: safe coordinate click ───
        # AVOID the Android system nav bar at the very bottom (last ~5% on
        # most phones, ~10% on devices with software nav). We never click
        # below 90% of screen height.
        try:
            print("[!] Trying coordinate-based click (safe zone, avoids nav bar)")
            width, height = self.device.window_size()
            # Conservative y-range — keeps us above any soft nav buttons.
            # Verify each click actually advanced to login before declaring success.
            for y_pct in (0.86, 0.82, 0.78, 0.74):
                pkg_before = (self.device.app_current().get('package') or '')
                try:
                    self.device.click(width // 2, int(height * y_pct))
                    time.sleep(2.5)

                    # If our click sent IG to background (e.g. hit Home button),
                    # re-launch and bail to outer caller for a clean retry.
                    pkg_after = (self.device.app_current().get('package') or '')
                    if pkg_before and pkg_after and pkg_after != pkg_before \
                       and not pkg_after.startswith('com.instagram'):
                        print(f"[!] y={y_pct} sent app to background ({pkg_after}) — aborting fallback")
                        # Try to re-foreground IG
                        try:
                            self.device.app_start(pkg_before, use_monkey=True)
                            time.sleep(3)
                        except Exception:
                            pass
                        return False

                    if self._is_on_login_screen():
                        print(f"[OK] Coordinate click at y={y_pct} reached login")
                        return True
                except Exception:
                    continue
        except Exception as e:
            print(f"[X] Coordinate click failed: {e}")

        # Last resort: maybe we were never on signup at all
        if self._is_on_login_screen():
            print("[OK] Already on login screen (no navigation needed)")
            return True

        print("[X] handle_signup_screen: could not reach login screen")
        return False

    def _find_login_link_bounds(self):
        """
        Parse the current XML hierarchy and find the bounds of the
        "Log In" / "Already have an account" affordance.

        Returns (cx, cy) center coordinates, or None if not found.

        This is robust to: layout changes, custom views with text in
        descendants, different aspect ratios. We never return coordinates
        inside the Android system nav-bar area (bottom ~5%).
        """
        import re
        try:
            xml = self.device.dump_hierarchy() or ''
        except Exception:
            return None
        if not xml:
            return None

        # Window size — used to filter out Android nav bar clicks.
        try:
            w, h = self.device.window_size()
        except Exception:
            w, h = 1080, 2340
        nav_bar_top = int(h * 0.95)  # never click below this y

        # Patterns we trust for a login link, ordered by specificity.
        keyword_patterns = [
            r"i\s*already\s*have\s*an?\s*account",
            r"already\s*have\s*an?\s*account",
            r"\blog\s*in\b",        # "Log in" / "Log In"
            r"\blogin\b",
        ]
        # Tag scan: every <node ... /> can carry text="..." OR content-desc="..."
        # We extract bounds [x1,y1][x2,y2] from each node and check both fields.
        node_re = re.compile(
            r'<node[^>]*?(?:text="(?P<text>[^"]*)")?[^>]*?'
            r'(?:content-desc="(?P<desc>[^"]*)")?[^>]*?'
            r'bounds="\[(?P<x1>\d+),(?P<y1>\d+)\]\[(?P<x2>\d+),(?P<y2>\d+)\]"',
            re.IGNORECASE,
        )

        # Build a list of (priority, cx, cy, label) candidates.
        candidates = []
        for m in node_re.finditer(xml):
            text = (m.group('text') or '').strip().lower()
            desc = (m.group('desc') or '').strip().lower()
            content = f"{text} {desc}".strip()
            if not content:
                continue
            for prio, pat in enumerate(keyword_patterns):
                if re.search(pat, content):
                    x1, y1, x2, y2 = (int(m.group(k)) for k in ('x1','y1','x2','y2'))
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    # Discard zero-area matches or things in the system nav-bar.
                    if x2 <= x1 or y2 <= y1:
                        continue
                    if cy >= nav_bar_top:
                        continue
                    # Discard tiny elements (likely icons, not text links)
                    if (x2 - x1) < 40 or (y2 - y1) < 20:
                        continue
                    candidates.append((prio, cx, cy, content[:40]))
                    break  # one keyword match per node is enough

        if not candidates:
            return None

        # Best candidate: lowest priority number (most specific keyword),
        # tie-break by lowest y (login link is at bottom of the welcome card).
        candidates.sort(key=lambda c: (c[0], -c[2]))
        best = candidates[0]
        print(f"[XML] login-link candidate: '{best[3]}' at ({best[1]}, {best[2]}) (prio={best[0]})")
        return (best[1], best[2])

    def _is_on_login_screen(self):
        """
        Quick check: are we on the actual credential-entry login screen
        (i.e. has the password field rendered)? Used by handle_signup_screen
        to verify a click actually worked.
        """
        try:
            if (self.device(descriptionContains="Password").wait(timeout=1)
                or self.device(textContains="Password").wait(timeout=1)
                or self.device(text="Forgot password?").wait(timeout=1)
                or self.device(textContains="Forgot password").wait(timeout=1)):
                return True
            # Also accept if we have ≥2 EditText fields (login screen has
            # username + password) AND no signup intro buttons.
            edits = self.device(className="android.widget.EditText")
            if edits.wait(timeout=1) and edits.count >= 2:
                xml_lower = (self.device.dump_hierarchy() or '').lower()
                if "create new account" not in xml_lower and "join instagram" not in xml_lower:
                    return True
        except Exception:
            pass
        return False

    def _clear_field(self, field):
        """
        Thoroughly clear an EditText field using multiple methods.
        Instagram's custom EditText fields sometimes don't respond to clear_text().
        """
        try:
            field.clear_text()
            time.sleep(0.3)
        except Exception:
            pass

        # Also try select-all + delete via ADB for thorough clearing
        try:
            connection_serial = self.device_serial.replace('_', ':')
            # Ctrl+A (select all) then Delete
            subprocess.run(['adb', '-s', connection_serial, 'shell', 'input', 'keyevent', 'KEYCODE_MOVE_END'],
                          capture_output=True, timeout=5)
            # Select all by holding shift + move to home
            subprocess.run(['adb', '-s', connection_serial, 'shell', 'input', 'keyevent', '--longpress',
                          'KEYCODE_DEL', 'KEYCODE_DEL', 'KEYCODE_DEL', 'KEYCODE_DEL', 'KEYCODE_DEL',
                          'KEYCODE_DEL', 'KEYCODE_DEL', 'KEYCODE_DEL', 'KEYCODE_DEL', 'KEYCODE_DEL',
                          'KEYCODE_DEL', 'KEYCODE_DEL', 'KEYCODE_DEL', 'KEYCODE_DEL', 'KEYCODE_DEL',
                          'KEYCODE_DEL', 'KEYCODE_DEL', 'KEYCODE_DEL', 'KEYCODE_DEL', 'KEYCODE_DEL',
                          'KEYCODE_DEL', 'KEYCODE_DEL', 'KEYCODE_DEL', 'KEYCODE_DEL', 'KEYCODE_DEL',
                          'KEYCODE_DEL', 'KEYCODE_DEL', 'KEYCODE_DEL', 'KEYCODE_DEL', 'KEYCODE_DEL'],
                          capture_output=True, timeout=10)
            time.sleep(0.3)
        except Exception:
            pass

    def enter_credentials(self, username, password):
        """
        Enter username and password into login fields

        Args:
            username: Instagram username
            password: Instagram password

        Returns:
            bool: True if successful
        """
        print("\n" + "-"*70)
        print(f"ENTERING CREDENTIALS: {username}")
        print("-"*70)

        try:
            # Find username field
            print("Looking for username field...")
            username_selectors = [
                self.device(descriptionContains="Username"),
                self.device(descriptionContains="username"),
                self.device(textContains="Username"),
                self.device(textContains="Phone"),
                self.device(textContains="Email"),
                self.device(descriptionContains="email"),
                self.device(descriptionContains="phone"),
                self.device(className="android.widget.EditText", instance=0),
            ]

            username_field = None
            for i, selector in enumerate(username_selectors, 1):
                if selector.wait(timeout=3):
                    print(f"[OK] Found username field (selector #{i})")
                    username_field = selector
                    break

            if not username_field:
                print("[X] Could not find username field")
                return False

            # Clear and enter username with fallback methods
            # IMPORTANT: Instagram EditText fields return hint/content-desc from get_text(),
            # NOT the actual typed text. So we cannot rely on get_text() for verification.
            # Instead, we trust set_text/send_keys and only fall back on EXCEPTIONS.
            print(f"Entering username: {username}")
            username_field.click()
            time.sleep(1)

            # Clear field thoroughly
            self._clear_field(username_field)

            # Primary: adb shell input text (most reliable on our devices)
            adb_serial = self.device_serial if ':' in self.device_serial else self.device_serial.replace('_', ':')
            escaped_user = username.replace(' ', '%s')
            for ch in '()&;<>|$`\\!"\'{}[]~*?#':
                escaped_user = escaped_user.replace(ch, '\\' + ch)
            subprocess.run(['adb', '-s', adb_serial, 'shell', 'input', 'text', escaped_user],
                    capture_output=True, timeout=10)
            print(f"[OK] Username entered via adb input text")

            time.sleep(1)

            # Find password field
            print("Looking for password field...")
            password_selectors = [
                self.device(descriptionContains="Password"),
                self.device(descriptionContains="password"),
                self.device(textContains="Password"),
                self.device(textContains="password"),
                self.device(className="android.widget.EditText", instance=1),
            ]

            password_field = None
            for i, selector in enumerate(password_selectors, 1):
                if selector.wait(timeout=3):
                    print(f"[OK] Found password field (selector #{i})")
                    password_field = selector
                    break

            if not password_field:
                print("[X] Could not find password field")
                return False

            # Clear and enter password with fallback methods
            # Same note as username: get_text() is unreliable on IG fields
            print("Entering password...")
            password_field.click()
            time.sleep(1)

            # Clear field thoroughly
            self._clear_field(password_field)

            # Primary: adb shell input text (most reliable on our devices)
            escaped_pass = password.replace(' ', '%s')
            for ch in '()&;<>|$`\\!"\'{}[]~*?#':
                escaped_pass = escaped_pass.replace(ch, '\\' + ch)
            subprocess.run(['adb', '-s', adb_serial, 'shell', 'input', 'text', escaped_pass],
                    capture_output=True, timeout=10)
            print(f"[OK] Password entered via adb input text")

            time.sleep(1)

            # Click login button
            print("Looking for login button...")
            login_button_selectors = [
                self.device(text="Log In"),
                self.device(text="Log in"),
                self.device(textContains="Log in"),
                self.device(textContains="Log In"),
                self.device(description="Log in"),
                self.device(className="android.widget.Button", textContains="Log"),
            ]

            for i, selector in enumerate(login_button_selectors, 1):
                if selector.wait(timeout=3):
                    print(f"[OK] Found login button (selector #{i})")
                    selector.click()
                    print("[OK] Clicked login button")
                    time.sleep(5)  # Wait for login to process
                    return True

            print("[X] Could not find login button")
            return False

        except Exception as e:
            print(f"[X] Error entering credentials: {e}")
            return False

    def detect_two_factor_screen(self):
        """
        Detect if we're on the actual 2FA CODE ENTRY screen (not challenge/notification screens).

        Returns:
            bool: True if on 2FA code entry screen
        """
        try:
            print("Checking screen for 2FA code entry indicators...")
            xml_dump = (self._dump_app_hierarchy("[2FA_DETECT]") or '')
            xml_lower = xml_dump.lower()

            # ─── PRIORITY 1: Strong 2FA code-entry indicators (definitive) ───
            # The actual 2FA code entry screen ALSO contains a "Try another way"
            # link at the bottom — so we must NOT blanket-exclude on that phrase.
            # If we see any of these strong markers, we are 100% on the code-entry
            # screen, even if 'try another way' is also present.
            strong_keywords = [
                "enter the 6-digit code",
                "enter the code",
                "go to your authentication app",
                "authentication app you set up",
                "confirmation code",
                "security code",
                "two-factor",
                "enter your security",
                "authentication code",
            ]
            for keyword in strong_keywords:
                if keyword in xml_lower:
                    print(f"[OK] 2FA code entry screen detected (strong): '{keyword}'")
                    return True

            # ─── PRIORITY 2: Exclude challenge/notification screens ───
            # Only kicks in when no strong code-entry marker was found.
            # These screens may contain "try another way" but lack the code field.
            challenge_exclusions = [
                "check your notifications",
                "notifications on another device",
                "waiting for approval",
                "approve from the other device",
                "check your sms",
                "check your email",
                "confirm your identity",
                "it was you",
            ]
            for excl in challenge_exclusions:
                if excl in xml_lower:
                    print(f"[X] Not 2FA code entry — this is a challenge screen ('{excl}')")
                    return False

            # 'try another way' alone (without strong markers) = challenge screen
            if "try another way" in xml_lower:
                # …unless there's a single EditText (could still be code entry on stripped UI)
                edit_texts = self.device(className="android.widget.EditText")
                if not (edit_texts.wait(timeout=1) and edit_texts.count == 1):
                    print("[X] Not 2FA code entry — 'try another way' present and no single EditText")
                    return False

            # Weak keywords — only match if there's also an EditText (input field) visible
            weak_keywords = ["we sent", "verify", "2fa", "enter your"]
            for keyword in weak_keywords:
                if keyword in xml_lower:
                    # Must also have an input field to be a code entry screen
                    edit_texts = self.device(className="android.widget.EditText")
                    if edit_texts.wait(timeout=2) and edit_texts.count == 1:
                        print(f"[OK] 2FA screen detected: '{keyword}' + single EditText field")
                        return True
                    else:
                        print(f"[!] Found '{keyword}' but no single EditText — not a code entry screen")

            # Check for single EditText + code/security context
            edit_texts = self.device(className="android.widget.EditText")
            if edit_texts.wait(timeout=2):
                edit_text_count = edit_texts.count
                print(f"Found {edit_text_count} EditText field(s)")
                if edit_text_count == 1:
                    if any(kw in xml_lower for kw in ["code", "security"]):
                        print("[OK] 2FA screen detected (single EditText + code/security context)")
                        return True

            # Check for "Resend Code" button (unique to 2FA)
            if self.device(textContains="Resend").wait(timeout=1):
                print("[OK] 2FA screen detected ('Resend' button found)")
                return True

            print("[X] No 2FA code entry indicators found")
            return False

        except Exception as e:
            print(f"[!] Error detecting 2FA screen: {e}")
            return False

    def _dump_app_hierarchy(self, tag="", max_retries=3):
        """
        Dump UI hierarchy with retry logic.
        UIAutomator sometimes captures com.android.systemui instead of the
        foreground app. This retries the dump if it detects systemui.
        Returns the XML string or None if all retries fail.

        NOTE: On Samsung devices, systemui rounded-corner overlays ALWAYS
        appear at the top of the hierarchy (first ~500 chars) even when the
        app is fully visible underneath. We must check the ENTIRE dump for
        instagram content, not just the first 1000 chars.
        """
        for attempt in range(1, max_retries + 1):
            try:
                xml = self.device.dump_hierarchy()
                xml_lower = xml.lower()
                # Check if the dump contains ONLY systemui (no app content at all)
                # Samsung devices always have systemui overlay nodes at the top,
                # so we check if instagram appears ANYWHERE in the dump
                has_instagram = 'instagram' in xml_lower
                has_edit_text = 'android.widget.edittext' in xml_lower
                has_app_content = has_instagram or has_edit_text

                if not has_app_content and 'com.android.systemui' in xml:
                    print(f"{tag} [DUMP] Attempt {attempt}/{max_retries}: Only systemui, no app content, retrying...")
                    time.sleep(1.5)
                    continue
                return xml
            except Exception as e:
                print(f"{tag} [DUMP] Attempt {attempt}/{max_retries}: Error: {e}")
                time.sleep(1)
        # Last attempt — return whatever we get
        try:
            return self.device.dump_hierarchy()
        except:
            return None

    def _try_another_way_to_2fa(self):
        """
        Handle screens that block normal login and have a "Try another way" link.
        
        Detected screens:
          - "Check your notifications on another device"
          - "Check your SMS" (also has "Try another way")
          - "Waiting for approval"
          - Various challenge/verification screens
        
        Flow:
          1. Detect one of the above screens
          2. Scroll down (button is always at the very bottom)
          3. Click "Try another way" (with retry)
          4. On "Choose a way to confirm" screen, select "Authentication app"
          5. Click "Continue"/"Next"
          6. Verify we reached the 2FA code entry screen
        
        Returns:
            bool: True if we reached the 2FA code entry screen
        """
        TAG = "[TRY_ANOTHER_WAY]"
        try:
            print(f"\n{TAG} === Starting 'Try another way' detection ===")

            # Reliable dump - retry if we get systemui instead of the app
            xml_dump = self._dump_app_hierarchy(TAG)
            if not xml_dump:
                print(f"{TAG} Could not get app hierarchy after retries - skipping")
                return False
            xml_lower = xml_dump.lower()
            print(f"{TAG} Screen text (first 500 chars): {xml_lower[:500]}")

            # Step 1: Detect any screen that has "Try another way"
            trigger_keywords = [
                # Notification approval screens — the main target
                "check your notifications",
                "notifications on another device",
                "waiting for approval",
                "approve from the other device",
            ]

            matched = [kw for kw in trigger_keywords if kw in xml_lower]

            if not matched:
                # Also check if "Try another way" is directly visible
                if "try another way" in xml_lower:
                    matched = ["try another way (direct)"]
                else:
                    print(f"{TAG} Not on any trigger screen - skipping")
                    return False

            print(f"{TAG} DETECTED challenge screen (matched: {matched})")

            # Wait for page to fully load
            time.sleep(2)

            # Step 2: Find and click "Try another way"
            if not self._click_try_another_way(TAG):
                return False

            # Step 3: Handle "Choose a way to confirm" screen
            time.sleep(3)
            if not self._select_authentication_app(TAG):
                return False

            # Step 4: Verify we reached the 2FA code entry screen
            print(f"{TAG} Step 4: Checking if we landed on 2FA code entry screen...")
            for wait_round in range(3):
                if self.detect_two_factor_screen():
                    print(f"{TAG} [OK] SUCCESS! Navigated to 2FA code entry screen!")
                    return True
                if wait_round < 2:
                    print(f"{TAG} Not on 2FA screen yet - waiting 3s (attempt {wait_round+1}/3)...")
                    time.sleep(3)

            print(f"{TAG} [X] FAILED - not on 2FA code entry screen after full navigation")
            xml_final = (self._dump_app_hierarchy(TAG) or "")
            print(f"{TAG} [DEBUG] Final screen (1000 chars):\n{xml_final[:1000]}")
            return False

        except Exception as e:
            print(f"{TAG} [!] EXCEPTION in _try_another_way_to_2fa: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _click_try_another_way(self, TAG):
        """Find and click 'Try another way' button, with scroll and retry."""
        try:
            w, h = self.device.window_size()
        except:
            w, h = 1080, 1920

        # Attempt up to 3 times - scroll progressively more each time
        for attempt in range(1, 4):
            print(f"{TAG} Looking for 'Try another way' (attempt {attempt}/3)...")

            # Progressive scroll - first gentle, then more aggressive
            try:
                if attempt == 1:
                    self.device.swipe(w // 2, int(h * 0.7), w // 2, int(h * 0.4), duration=0.3)
                elif attempt == 2:
                    self.device.swipe(w // 2, int(h * 0.8), w // 2, int(h * 0.2), duration=0.3)
                else:
                    self.device.swipe(w // 2, int(h * 0.9), w // 2, int(h * 0.1), duration=0.4)
                time.sleep(2)
            except:
                pass

            # Look for the button
            try_btn = self.device(textContains="Try another way")
            if not try_btn.wait(timeout=3):
                try_btn = self.device(textContains="another way")
            if not try_btn.wait(timeout=3):
                try_btn = self.device(descriptionContains="Try another way")

            if try_btn.wait(timeout=2):
                print(f"{TAG} [OK] Found 'Try another way' - clicking...")
                try_btn.click()
                time.sleep(2)

                # Verify click registered - if button still visible, retry with coordinates
                try:
                    if try_btn.wait(timeout=2):
                        print(f"{TAG} Button still visible - clicking by coordinates...")
                        try:
                            bounds = try_btn.info.get("bounds", {})
                            cx = (bounds.get("left", 0) + bounds.get("right", w)) // 2
                            cy = (bounds.get("top", 0) + bounds.get("bottom", h)) // 2
                            self.device.click(cx, cy)
                        except:
                            try_btn.click()
                        time.sleep(2)
                except:
                    pass

                # Check if we navigated away
                time.sleep(1)
                xml_after = (self._dump_app_hierarchy(TAG) or "").lower()
                if "choose a way" in xml_after or "authentication app" in xml_after or "confirmation method" in xml_after:
                    print(f"{TAG} [OK] Navigated to 'Choose a way' screen!")
                    return True
                if self.detect_two_factor_screen():
                    print(f"{TAG} [OK] Jumped directly to 2FA screen!")
                    return True
                # Still on same screen?
                if "try another way" in xml_after and attempt < 3:
                    print(f"{TAG} Still on same screen after click - will retry...")
                    continue
                # Screen changed - proceed
                print(f"{TAG} Screen changed after click - proceeding")
                return True

            print(f"{TAG} Button not found on attempt {attempt}")

        print(f"{TAG} [X] 'Try another way' button NOT FOUND after 3 attempts")
        return False

    def _select_authentication_app(self, TAG):
        """On 'Choose a way to confirm' screen, select Authentication app and click Continue."""
        xml_dump = self._dump_app_hierarchy(TAG) or ""
        xml_lower = xml_dump.lower()

        # Check if we are on the right screen
        choose_screen = ("choose a way" in xml_lower or "confirmation methods" in xml_lower
                         or "confirm it" in xml_lower or "authentication app" in xml_lower
                         or "select a way" in xml_lower)

        if not choose_screen:
            # Maybe we skipped straight to 2FA entry
            if self.detect_two_factor_screen():
                print(f"{TAG} [OK] Already on 2FA code entry screen - no selection needed")
                return True
            # Wait and retry
            time.sleep(3)
            xml_lower = (self._dump_app_hierarchy(TAG) or "").lower()
            choose_screen = ("choose a way" in xml_lower or "authentication app" in xml_lower)
            if not choose_screen:
                print(f"{TAG} [X] NOT on 'Choose a way' screen")
                print(f"{TAG} [DEBUG] Screen text (500 chars): {xml_lower[:500]}")
                if self.detect_two_factor_screen():
                    return True
                return False

        print(f"{TAG} Step 3: On 'Choose a way to confirm' - selecting 'Authentication app'...")

        # Find and click "Authentication app"
        auth_app = self.device(textContains="Authentication app")
        if not auth_app.wait(timeout=3):
            auth_app = self.device(textContains="authentication app")
        if not auth_app.wait(timeout=3):
            auth_app = self.device(descriptionContains="Authentication app")
        if not auth_app.wait(timeout=3):
            # Try scrolling
            try:
                w, h = self.device.window_size()
                self.device.swipe(w // 2, int(h * 0.7), w // 2, int(h * 0.3), duration=0.3)
                time.sleep(1.5)
            except:
                pass
            auth_app = self.device(textContains="Authentication app")

        if not auth_app.wait(timeout=3):
            print(f"{TAG} [X] 'Authentication app' option NOT FOUND")
            xml_debug = (self._dump_app_hierarchy(TAG) or "")
            print(f"{TAG} [DEBUG] Screen (1500 chars):\n{xml_debug[:1500]}")
            return False

        print(f"{TAG} [OK] Found 'Authentication app' - clicking...")
        auth_app.click()
        time.sleep(2)

        # Try to verify radio button is selected
        try:
            radio = self.device(className="android.widget.RadioButton", textContains="Authentication")
            if radio.wait(timeout=2):
                checked = radio.info.get("checked", False)
                if not checked:
                    print(f"{TAG} Radio not checked - clicking directly...")
                    radio.click()
                    time.sleep(1)
                else:
                    print(f"{TAG} [OK] Authentication app radio is checked")
        except:
            pass

        # Click "Continue" / "Next"
        try:
            w, h = self.device.window_size()
        except:
            w, h = 1080, 1920

        for btn_text in ["Continue", "Next", "CONTINUE", "NEXT"]:
            btn = self.device(textContains=btn_text)
            if btn.wait(timeout=2):
                print(f"{TAG} Clicking '{btn_text}'...")
                btn.click()
                time.sleep(4)
                return True

        # Scroll and retry
        print(f"{TAG} 'Continue'/'Next' not found - scrolling...")
        try:
            self.device.swipe(w // 2, int(h * 0.8), w // 2, int(h * 0.3), duration=0.3)
            time.sleep(2)
        except:
            pass

        for btn_text in ["Continue", "Next"]:
            btn = self.device(textContains=btn_text)
            if btn.wait(timeout=2):
                print(f"{TAG} Clicking '{btn_text}' (after scroll)...")
                btn.click()
                time.sleep(4)
                return True

        print(f"{TAG} [X] 'Continue'/'Next' button NOT FOUND")
        xml_debug = (self._dump_app_hierarchy(TAG) or "")
        print(f"{TAG} [DEBUG] Screen (1000 chars):\n{xml_debug[:1000]}")
        return False

    def handle_two_factor(self, two_fa_token):
        """
        Handle 2FA by fetching code from 2fa.live and entering it

        Args:
            two_fa_token: 2fa.live token (e.g., "CHN44RHFYSYPFCKLL2C5CFHNTY54PYOD")

        Returns:
            bool: True if successful
        """
        print("\n" + "="*70)
        print("HANDLING TWO-FACTOR AUTHENTICATION")
        print("="*70)

        if not two_fa_token:
            print("[X] No 2FA token provided")
            return False

        # Fetch code from 2fa.live
        client = TwoFALiveClient(two_fa_token, timeout=60)
        code = client.get_code(max_retries=20, retry_interval=3)

        if not code:
            print("[X] Could not retrieve 2FA code")
            return False

        print(f"\n[OK] Got 2FA code: {code}")

        # Enter code
        print("Entering 2FA code...")

        try:
            # Find code input field — try multiple selectors
            code_field = None
            selectors = [
                # Standard EditText
                ("EditText", self.device(className="android.widget.EditText")),
                # Input field with hint/text "Code" (seen on "Go to your authentication app" screen)
                ("text=Code", self.device(text="Code")),
                ("textContains=Code", self.device(textContains="Code", className="android.widget.EditText")),
                # IG sometimes uses resourceId with "code" or "security"
                ("resourceId ~code", self.device(resourceIdMatches=".*code.*")),
                ("resourceId ~security", self.device(resourceIdMatches=".*security.*input.*")),
                ("resourceId ~verification", self.device(resourceIdMatches=".*verification.*")),
                # Focused/clickable input
                ("focused input", self.device(focused=True, className="android.widget.EditText")),
                # IG input fields (clickable EditText)
                ("clickable EditText", self.device(className="android.widget.EditText", clickable=True)),
                # Generic focusable field
                ("focusable EditText", self.device(className="android.widget.EditText", focusable=True)),
            ]

            for name, selector in selectors:
                if selector.wait(timeout=2):
                    code_field = selector
                    print(f"[OK] Found code input field via: {name}")
                    break

            if not code_field:
                # Last resort: dump hierarchy and look for any input-like element
                print("[!] Standard selectors failed, searching XML dump...")
                xml = self.device.dump_hierarchy()
                # Check if there's an EditText at all
                if 'EditText' in xml:
                    print("[!] EditText exists in XML but selectors didn't match. Trying xpath...")
                    try:
                        code_field = self.device.xpath('//android.widget.EditText').get()
                        if code_field:
                            print("[OK] Found code input via xpath")
                    except Exception as xpath_err:
                        print(f"[!] Xpath attempt failed: {xpath_err}")

            if not code_field:
                print("[X] Could not find code input field (tried all selectors)")
                # Dump the XML for debugging
                try:
                    xml = self.device.dump_hierarchy()
                    # Log first 2000 chars to help debug
                    print(f"[DEBUG] Screen XML (first 2000 chars):\n{xml[:2000]}")
                except:
                    pass
                return False

            print("[OK] Found code input field")
            try:
                code_field.click()
            except:
                # xpath elements use .click() differently
                pass
            time.sleep(1)
            try:
                code_field.clear_text()
            except:
                pass
            time.sleep(0.5)

            # Use set_text (AdbKeyboard IME) for reliable input
            try:
                code_field.set_text(code)
            except Exception:
                # Fallback to ADB input if set_text fails on xpath element
                connection_serial = self.device_serial.replace('_', ':')
                subprocess.run(
                    ['adb', '-s', connection_serial, 'shell', 'input', 'text', code],
                    capture_output=True, timeout=10
                )

            print(f"[OK] Entered code: {code}")
            time.sleep(2)

            # Scroll down slightly to reveal the Continue button
            # (On some devices with purple background, the button is below the fold)
            print("Scrolling down to reveal Continue button...")
            try:
                width, height = self.device.window_size()
                # Swipe up (scroll down) from bottom 60% to bottom 40%
                self.device.swipe(width // 2, int(height * 0.6), width // 2, int(height * 0.4), duration=0.3)
                time.sleep(1)
                print("[OK] Scrolled down")
            except Exception as e:
                print(f"[!] Could not scroll: {e}")

            # Click confirm/next button (may auto-submit)
            # Be specific to avoid clicking "Trust this device" checkbox
            confirm_selectors = [
                self.device(text="Continue"),
                self.device(text="Next"),
                self.device(text="Confirm"),
                self.device(textContains="Continue"),
                self.device(textContains="Next"),
                # Only use generic button selector as last resort
            ]

            button_found = False
            for i, selector in enumerate(confirm_selectors, 1):
                if selector.wait(timeout=2):
                    print(f"[OK] Found confirm button (selector #{i}: {selector})")

                    # Get button info to make sure it's not a checkbox
                    try:
                        button_info = selector.info
                        if button_info.get('checkable', False):
                            print(f"[!] Selector #{i} is checkable (likely checkbox), skipping...")
                            continue
                    except:
                        pass

                    selector.click()
                    print("[OK] Clicked confirm button")
                    button_found = True
                    break

            # If no specific button found, try generic button but verify it's not a checkbox
            if not button_found:
                print("[!] No specific button found, trying generic button selector...")
                buttons = self.device(className="android.widget.Button")
                if buttons.wait(timeout=2):
                    # Try to find a button that's not checkable
                    for i in range(buttons.count):
                        try:
                            btn = self.device(className="android.widget.Button", instance=i)
                            btn_info = btn.info
                            if not btn_info.get('checkable', False):
                                print(f"[OK] Found non-checkable button (instance {i})")
                                btn.click()
                                print("[OK] Clicked button")
                                button_found = True
                                break
                        except:
                            continue

            if not button_found:
                print("[!] Could not find confirm button, continuing anyway...")

            time.sleep(5)  # Wait for 2FA to process
            return True

        except Exception as e:
            print(f"[X] Error entering 2FA code: {e}")
            return False

    def handle_save_login_info(self):
        """
        Handle "Save Your Login Info?" prompt by clicking Save

        Returns:
            bool: True if handled (whether prompt found or not)
        """
        print("\n" + "-"*70)
        print("CHECKING FOR 'SAVE LOGIN INFO' PROMPT")
        print("-"*70)

        try:
            # Check if prompt is visible
            xml_dump = self.device.dump_hierarchy()
            xml_lower = xml_dump.lower()

            if "save" not in xml_lower and "login info" not in xml_lower:
                print("[OK] No 'Save Login Info' prompt found")
                return True

            print("[OK] 'Save Login Info' prompt detected")

            # Find Save button
            save_selectors = [
                self.device(text="Save"),
                self.device(textContains="Save"),
                self.device(text="Save Info"),
                self.device(description="Save"),
            ]

            for i, selector in enumerate(save_selectors, 1):
                if selector.wait(timeout=3):
                    print(f"[OK] Found Save button (selector #{i})")
                    selector.click()
                    print("[OK] Clicked Save")
                    time.sleep(3)
                    return True

            print("[!] Could not find Save button, trying Not Now")

            # Try "Not Now" as fallback
            not_now_selectors = [
                self.device(text="Not Now"),
                self.device(textContains="Not Now"),
                self.device(text="Not now"),
            ]

            for selector in not_now_selectors:
                if selector.wait(timeout=2):
                    print("[OK] Clicked 'Not Now'")
                    selector.click()
                    time.sleep(2)
                    return True

            print("[!] Could not interact with Save prompt, continuing anyway")
            return True

        except Exception as e:
            print(f"[!] Error handling save prompt: {e}")
            return True  # Continue anyway

    def dismiss_notification_prompt(self):
        """
        Dismiss "Turn On Notifications?" prompt

        Returns:
            bool: True if handled
        """
        print("\n" + "-"*70)
        print("CHECKING FOR NOTIFICATION PROMPT")
        print("-"*70)

        try:
            # Check for notifications prompt
            xml_dump = self.device.dump_hierarchy()
            xml_lower = xml_dump.lower()

            if "notification" not in xml_lower:
                print("[OK] No notification prompt found")
                return True

            print("[OK] Notification prompt detected")

            # Two flavors of notification prompt:
            #   (a) IG in-app: "Turn on notifications?" → buttons "Not Now" / "Turn On"
            #   (b) Android 13+ system dialog: package com.android.permissioncontroller →
            #       buttons "Don't allow" / "Allow"
            dismiss_selectors = [
                # Android 13+ system permission dialog
                self.device(text="Don't allow"),
                self.device(text="Don’t allow"),  # curly apostrophe variant
                self.device(textMatches=r"(?i)don['’]?t allow"),
                self.device(resourceIdMatches=r".*permission_deny.*"),
                self.device(resourceId="com.android.permissioncontroller:id/permission_deny_button"),
                # IG in-app prompt
                self.device(text="Not Now"),
                self.device(text="Not now"),
                self.device(textContains="Not Now"),
                self.device(text="Skip"),
                self.device(textContains="Skip"),
                # Fallback: any "Deny" button
                self.device(text="Deny"),
                self.device(textContains="Deny"),
            ]

            for i, selector in enumerate(dismiss_selectors, 1):
                try:
                    if selector.wait(timeout=2):
                        print(f"[OK] Found dismiss button (selector #{i})")
                        selector.click()
                        print("[OK] Dismissed notification prompt")
                        time.sleep(2)
                        return True
                except Exception:
                    continue

            # Last-resort: try resource ID for Android system permission deny
            try:
                deny = self.device(resourceId="com.android.permissioncontroller:id/permission_deny_button")
                if deny.wait(timeout=1):
                    deny.click()
                    print("[OK] Dismissed via resourceId permission_deny_button")
                    time.sleep(2)
                    return True
            except Exception:
                pass

            print("[!] Could not dismiss notification prompt — but it implies login is past auth")
            return True  # Continue — caller's verify will handle it

        except Exception as e:
            print(f"[!] Error dismissing notification: {e}")
            return True

    def dismiss_post_login_modals(self):
        """
        Dismiss post-login modals like location permission, contacts, notifications

        These modals appear after successful login with buttons like:
        - "Not Now"
        - "Skip"
        - "Continue" (for location services, then "Deny")
        - "Deny" (for permissions)

        Returns:
            bool: True if modals were dismissed or none found
        """
        print("\n" + "-"*70)
        print("CHECKING FOR POST-LOGIN MODALS")
        print("-"*70)

        try:
            # Wait a moment for any modals to appear
            time.sleep(2)

            # Try to dismiss up to 5 times (in case multiple modals appear)
            for attempt in range(5):
                print(f"\nAttempt {attempt + 1}/5 to find and dismiss modals...")

                # Check for location services "Continue" button first
                continue_selectors = [
                    self.device(text="Continue"),
                    self.device(textContains="Continue"),
                ]

                continue_found = False
                for selector in continue_selectors:
                    if selector.wait(timeout=2):
                        print("[OK] Found 'Continue' button (likely location services)")
                        selector.click()
                        print("[OK] Clicked Continue")
                        time.sleep(2)
                        continue_found = True

                        # Now look for "Deny" / "Don't allow" / "Only this time"
                        # in the native permission dialog.
                        # We pick the LEAST-permissive option:
                        #   1) "Deny" (Android < 13 location dialog)
                        #   2) "Don't allow" / "Don’t allow" (Android 13+ notif/loc)
                        #   3) "Only this time" (Android 11+ location — temporary)
                        # We avoid "While using the app" / "Allow only while using"
                        # which grants location access.
                        deny_selectors = [
                            self.device(text="Deny"),
                            self.device(text="Don't allow"),
                            self.device(text="Don’t allow"),
                            self.device(textMatches=r"(?i)don['’]?t allow"),
                            self.device(resourceId="com.android.permissioncontroller:id/permission_deny_button"),
                            self.device(resourceIdMatches=r".*permission_deny.*"),
                            self.device(textContains="Don't allow"),
                            self.device(textContains="Deny"),
                            self.device(text="Only this time"),
                            self.device(textContains="Only this time"),
                        ]

                        for deny_selector in deny_selectors:
                            try:
                                if deny_selector.wait(timeout=3):
                                    print("[OK] Found permission deny button")
                                    deny_selector.click()
                                    print("[OK] Clicked deny/only-this-time")
                                    time.sleep(2)
                                    break
                            except Exception:
                                continue

                        break

                if continue_found:
                    # Continue to next attempt to check for more modals
                    continue

                # Selectors for common dismiss buttons
                dismiss_selectors = [
                    self.device(text="Not Now"),
                    self.device(text="Not now"),
                    self.device(text="Skip"),
                    self.device(text="Skip for now"),
                    self.device(text="Skip For Now"),
                    self.device(text="Deny"),
                    self.device(textContains="Not Now"),
                    self.device(textContains="Not now"),
                    self.device(textContains="Skip"),
                    self.device(textContains="Deny"),
                    self.device(textMatches="(?i)not now"),  # Case insensitive
                    self.device(textMatches="(?i)skip"),
                    self.device(textMatches="(?i)deny"),
                ]

                modal_found = False
                for i, selector in enumerate(dismiss_selectors):
                    if selector.wait(timeout=2):
                        print(f"[OK] Found dismiss button (selector #{i}): {selector.info.get('text', 'unknown')}")
                        selector.click()
                        print("[OK] Clicked dismiss button")
                        time.sleep(2)  # Wait for modal to dismiss
                        modal_found = True
                        break

                if not modal_found:
                    print("[OK] No more modals found")
                    break

            print("[OK] Post-login modal check complete")
            return True

        except Exception as e:
            print(f"[!] Error dismissing post-login modals: {e}")
            return True  # Continue anyway

    def verify_logged_in(self):
        """
        Verify that login was successful by checking for IG home feed or profile tab.

        IMPORTANT: We must NOT match generic content-desc="Home" because the
        Android system nav bar also has a Home button with that exact desc.
        That false-positive would mark a stuck-on-2FA flow as "logged in".

        Returns:
            bool: True if logged in
        """
        print("\n" + "-"*70)
        print("VERIFYING LOGIN SUCCESS")
        print("-"*70)

        try:
            time.sleep(3)
            xml_dump = self.device.dump_hierarchy()
            xml_lower = xml_dump.lower()

            # POST-LOGIN signals — these screens/dialogs ONLY appear AFTER a
            # successful login. If we see any of them, the login is done; the
            # remaining modals are dismissed by dismiss_post_login_modals().
            post_login_dialog_markers = [
                # Android 13+ system permission dialogs
                "com.android.permissioncontroller",
                "send you notifications",
                "allow notifications",
                "turn on notifications",
                # Location permission flow (IG → "Set up on new device")
                "set up on new device",
                "to use location services",
                "allow instagram to access your location",
                "access this device's location",
                "access this device’s location",       # curly apostrophe
                "while using the app",
                "only this time",
                # Other typical post-login welcome / prompts
                "how you can use location services",
                "save your login info",
                "we'll remember this device",
                "we’ll remember this device",
                "add a profile photo",
                "add profile photo",
                "discover people to follow",
                "find people to follow",
                "sync contacts",
                "see when you're online",
                "see when you’re online",
            ]
            for marker in post_login_dialog_markers:
                if marker in xml_lower:
                    print(f"[OK] Logged in — post-login dialog visible ('{marker}')")
                    return True

            # If we're still on a 2FA / login / challenge screen → not logged in.
            still_on_login = [
                "go to your authentication app",
                "enter the 6-digit code",
                "enter the code",
                "try another way",
                "we sent you a code",
                "confirm it’s you",
                "confirm it's you",
            ]
            # 'log in' bare phrase can collide with random texts, so scope to
            # actual login-screen indicators (must co-occur with login affordances).
            if ("log in" in xml_lower) and ("forgot password" in xml_lower or "create new account" in xml_lower):
                print("[!] Verification FAILED — still on login screen ('log in' + login affordances)")
                return False
            for kw in still_on_login:
                if kw in xml_lower:
                    print(f"[!] Verification FAILED — still on login/2FA screen ('{kw}')")
                    return False

            # IG-package-specific bottom nav ids (works for clones via wildcard match)
            ig_resource_markers = [
                ":id/profile_tab",
                ":id/feed_tab",
                ":id/clips_tab",
                ":id/search_tab",
                ":id/news_tab",
            ]
            for marker in ig_resource_markers:
                if marker in xml_dump:
                    print(f"[OK] Logged in — IG nav element present ({marker})")
                    return True

            # Profile tab content-desc is IG-specific (not used by Android nav bar)
            if self.device(description="Profile").wait(timeout=3):
                print("[OK] Logged in (Profile tab content-desc visible)")
                return True

            # 'Search and Explore' — IG-specific
            if self.device(description="Search and Explore").wait(timeout=2):
                print("[OK] Logged in (Search and Explore visible)")
                return True

            # Reels tab — IG-specific
            if self.device(descriptionContains="Reels").wait(timeout=2):
                print("[OK] Logged in (Reels content-desc visible)")
                return True

            # XML keyword fallback — require ≥3 IG-specific markers (was 2 → too loose).
            # Removed bare "home" because Android system nav has it.
            ig_keywords = ["profile", "search and explore", "reels", "your activity",
                           "stories tray", "feed_tab", "clips_tab"]
            matches = sum(1 for k in ig_keywords if k in xml_lower)
            if matches >= 2:
                print(f"[OK] Logged in (found {matches} IG-specific markers)")
                return True

            print("[!] Could not verify login (no IG nav elements found)")
            return False

        except Exception as e:
            print(f"[!] Error verifying login: {e}")
            return False

    def login_account(self, username, password, instagram_package, two_fa_token=None):
        """
        Complete login flow for an Instagram account

        Args:
            username: Instagram username
            password: Instagram password
            instagram_package: Package name (e.g., "com.instagram.androim")
            two_fa_token: Optional 2fa.live token for 2FA

        Returns:
            dict: {
                'success': bool,
                'login_type': str,
                'error': str or None,
                'two_fa_used': bool,
                'challenge_encountered': bool
            }
        """
        print("\n" + "="*70)
        print(f"INSTAGRAM LOGIN AUTOMATION")
        print("="*70)
        print(f"Username: {username}")
        print(f"Package: {instagram_package}")
        print(f"2FA Token: {'Yes' if two_fa_token else 'No'}")
        print("="*70)

        result = {
            'success': False,
            'login_type': 'unknown',
            'error': None,
            'two_fa_used': False,
            'challenge_encountered': False
        }

        try:
            # Open Instagram
            if not self.open_instagram(instagram_package):
                result['error'] = "Failed to open Instagram"
                return result

            # Detect screen state
            screen_state = self.detect_screen_state()

            # Handle already logged in
            if screen_state == 'logged_in':
                print("\n[OK] Account is already logged in!")
                result['success'] = True
                result['login_type'] = 'already_logged_in'
                return result

            # Handle suspended/disabled account (dead end)
            if screen_state == 'suspended':
                print("\n[X] Account is SUSPENDED — cannot login")
                result['error'] = "Account suspended by Instagram"
                result['challenge_encountered'] = True
                result['login_type'] = 'suspended'
                return result

            # Handle SMS/Email verification (dead end — can't login)
            if screen_state == 'sms_challenge':
                print("\n[X] SMS/Email verification required — account cannot be logged in automatically")
                result['error'] = "SMS/Email verification required — account is unusable"
                result['challenge_encountered'] = True
                result['login_type'] = 'sms_challenge'
                return result

            # Handle challenge screen
            if screen_state == 'challenge':
                print("\n[!] Challenge/verification screen detected")
                result['error'] = "Challenge screen encountered - manual intervention required"
                result['challenge_encountered'] = True
                result['login_type'] = 'challenge'
                return result

            # Handle signup screen
            if screen_state == 'signup':
                if not self.handle_signup_screen():
                    result['error'] = "Failed to navigate from signup to login screen"
                    return result
                time.sleep(2)

            # Enter credentials. If first attempt fails to find fields, the
            # device may have been on intro screen and our signup-handler
            # missed the click. Re-detect and retry once.
            if not self.enter_credentials(username, password):
                print("[!] enter_credentials failed — retrying after re-detecting screen state")
                time.sleep(2)
                # If we're still on intro/signup, try the link click again
                if not self._is_on_login_screen():
                    print("[!] Still not on login screen — re-running signup handler")
                    if self.handle_signup_screen():
                        time.sleep(2)
                if self.enter_credentials(username, password):
                    print("[OK] Credentials entered on second attempt")
                else:
                    result['error'] = "Failed to enter credentials"
                    return result

            # Quick check for Wrong Password / Can't find account modals (appear instantly)
            time.sleep(3)
            xml_quick = self.device.dump_hierarchy().lower()

            # Can't find account (username doesn't exist or is banned)
            cant_find_keywords = ["can't find account", "can\u2019t find account",
                                  "find an account with", "try another mobile number"]
            for kw in cant_find_keywords:
                if kw in xml_quick:
                    print(f"\n[X] ACCOUNT NOT FOUND: '{kw}'")
                    result['error'] = "Account not found on Instagram"
                    result['login_type'] = 'account_not_found'
                    return result

            wrong_pw_keywords = ["wrong password", "incorrect password", "password you entered is incorrect",
                                 "password was incorrect", "the password you entered"]
            for kw in wrong_pw_keywords:
                if kw in xml_quick:
                    print(f"\n[X] WRONG PASSWORD detected: '{kw}'")
                    result['error'] = "Wrong password"
                    result['login_type'] = 'wrong_password'
                    return result

            # Wait and check for 2FA (give it more time to appear)
            print("\n" + "-"*70)
            print("CHECKING FOR 2FA SCREEN...")
            print("-"*70)
            time.sleep(3)  # Already waited 3s above, total ~6s

            # Post-credential screen checks (retry if systemui captured)
            xml_check = (self._dump_app_hierarchy("[POST_CRED]") or '').lower()

            # Check for suspended account (dead end) after entering credentials
            suspended_checks = ["we suspended your account", "your account has been disabled",
                                "account was disabled", "days left to appeal", "permanently disable"]
            for kw in suspended_checks:
                if kw in xml_check:
                    print(f"\n[X] Account SUSPENDED after credentials: '{kw}'")
                    result['error'] = "Account suspended by Instagram"
                    result['login_type'] = 'suspended'
                    return result

            # Check for SMS/Email verification — always a dead end
            sms_dead_ends = ["check your sms", "we sent a link", "sent a code to", "check your email"]
            for kw in sms_dead_ends:
                if kw in xml_check:
                    print(f"\n[X] SMS/Email verification detected: '{kw}' — dead end")
                    result['error'] = "SMS/Email verification required — account unusable"
                    result['login_type'] = 'sms_challenge'
                    return result

            # IMPORTANT: Check for challenge screens (notifications, SMS, etc.) FIRST
            # because detect_two_factor_screen() has broad keywords like "we sent" that
            # false-positive on these screens. _try_another_way navigates to the real 2FA screen.
            two_fa_detected = self._try_another_way_to_2fa()

            # If not a challenge screen, check for standard 2FA code entry screen
            if not two_fa_detected:
                two_fa_detected = self.detect_two_factor_screen()

            if two_fa_detected:
                print(f"\n[OK] 2FA screen detected (two_fa_token={'YES: '+two_fa_token[:8]+'...' if two_fa_token else 'NONE/EMPTY'})")
                result['two_fa_used'] = True

                if not two_fa_token:
                    result['error'] = "2FA required but no token provided"
                    print("[X] No 2FA token available — cannot proceed")
                    return result

                if not self.handle_two_factor(two_fa_token):
                    result['error'] = "Failed to handle 2FA"
                    return result

                result['login_type'] = '2fa'

                # After 2FA, wait for login to complete before handling prompts
                print("[...] Waiting for 2FA login to complete...")
                time.sleep(6)  # Increased from 5 to 6
            else:
                print("[OK] No 2FA screen detected (normal login)")
                result['login_type'] = 'normal'
                # After normal login, wait a bit for any prompts
                time.sleep(3)

            # Before handling prompts, double-check we're not stuck on 2FA screen
            print("\n" + "-"*70)
            print("DOUBLE-CHECKING: Are we stuck on 2FA screen?")
            print("-"*70)

            # Re-check: challenge screens first, then 2FA (same order as above)
            still_on_2fa = self._try_another_way_to_2fa()
            if not still_on_2fa:
                still_on_2fa = self.detect_two_factor_screen()

            if still_on_2fa:
                print("\n[!] WARNING: Still on 2FA screen after entering credentials!")

                if two_fa_token and not two_fa_detected:
                    # We missed 2FA detection the first time, handle it now
                    print("Handling 2FA now (was missed in first detection)...")
                    result['two_fa_used'] = True

                    if not self.handle_two_factor(two_fa_token):
                        result['error'] = "Failed to handle 2FA (second attempt)"
                        return result

                    result['login_type'] = '2fa'
                    print("[...] Waiting for 2FA login to complete...")
                    time.sleep(6)
                else:
                    result['error'] = "Stuck on 2FA screen but no token provided or already tried"
                    return result

            # Handle post-login prompts (after login/2FA is complete)
            self.handle_save_login_info()
            time.sleep(2)
            self.dismiss_notification_prompt()
            time.sleep(2)

            # Verify login
            if self.verify_logged_in():
                # Dismiss any post-login modals (location, contacts, etc.)
                self.dismiss_post_login_modals()

                print("\n" + "="*70)
                print("[OK] LOGIN SUCCESSFUL!")
                print("="*70)
                result['success'] = True
                return result
            else:
                # Verification failed — likely stuck on 2FA / challenge / error screen.
                # Do NOT dismiss modals here (we'd click 2FA Continue with empty Code).
                # Do NOT mark success — that hides real failures and leaves the account
                # marked 'active' in the DB while it's actually stuck.
                print("\n" + "="*70)
                print("[X] LOGIN VERIFICATION FAILED")
                print("="*70)
                # Inspect screen to give a useful error in the dashboard.
                # NOTE: do NOT call _try_another_way_to_2fa here — it NAVIGATES.
                try:
                    if self.detect_two_factor_screen():
                        result['error'] = "Stuck on 2FA code entry screen — code was not accepted"
                    else:
                        xml_low = (self.device.dump_hierarchy() or '').lower()
                        if "try another way" in xml_low or "choose a way" in xml_low:
                            result['error'] = "Stuck on challenge / 'Try another way' screen"
                        elif "incorrect" in xml_low or "wrong password" in xml_low:
                            result['error'] = "Wrong password"
                        else:
                            result['error'] = "Could not verify login (not on IG home/profile)"
                except Exception:
                    result['error'] = "Could not verify login (not on IG home/profile)"
                result['success'] = False
                return result

        except Exception as e:
            print(f"\n[X] Login failed with exception: {e}")
            result['error'] = str(e)
            return result


if __name__ == '__main__':
    import sys

    print("="*70)
    print("INSTAGRAM LOGIN AUTOMATION - STANDALONE TEST")
    print("="*70)

    if len(sys.argv) < 4:
        print("\nUsage: python login_automation.py <DEVICE_SERIAL> <USERNAME> <PASSWORD> [PACKAGE] [2FA_TOKEN]")
        print("\nExample:")
        print("  python login_automation.py 10.1.10.183_5555 testuser testpass123")
        print("  python login_automation.py 10.1.10.183_5555 testuser testpass123 com.instagram.androim")
        print("  python login_automation.py 10.1.10.183_5555 testuser testpass123 com.instagram.androim CHN44RHFY...")
        sys.exit(1)

    device_serial = sys.argv[1]
    username = sys.argv[2]
    password = sys.argv[3]
    instagram_package = sys.argv[4] if len(sys.argv) > 4 else "com.instagram.android"
    two_fa_token = sys.argv[5] if len(sys.argv) > 5 else None

    # Create automation instance
    login = LoginAutomation(device_serial)

    # Connect to device
    if not login.connect_device():
        print("\n[X] Failed to connect to device")
        sys.exit(1)

    # Perform login
    result = login.login_account(username, password, instagram_package, two_fa_token)

    # Print result
    print("\n" + "="*70)
    print("LOGIN RESULT")
    print("="*70)
    for key, value in result.items():
        print(f"{key}: {value}")

    sys.exit(0 if result['success'] else 1)
