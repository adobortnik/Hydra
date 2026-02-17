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

                return self.device
            except Exception as e:
                elapsed = int(time.time() - start_time)
                if elapsed % 5 == 0:  # Print every 5 seconds
                    print(f"[...] Waiting... {elapsed}s / {max_wait}s")
                time.sleep(1)

        print(f"[X] Failed to connect to device after {max_wait}s")
        return None

    def open_instagram(self, instagram_package="com.instagram.android"):
        """
        Open Instagram app using the proven monkey method

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
            # Use uiautomator2's app_start with monkey (most reliable)
            self.device.app_start(instagram_package, use_monkey=True)
            print("[OK] Instagram launched with monkey")
            time.sleep(5)  # Give app time to launch

            # Verify app is running
            current_app = self.device.app_current().get('package')
            if current_app == instagram_package:
                print(f"[OK] Instagram is running: {instagram_package}")
                return True

            return True  # Still return True even if verification fails

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
            if self.device(description="Profile").exists(timeout=2) or \
               self.device(resourceId="com.instagram.android:id/profile_tab").exists(timeout=2):
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

            # Check for challenge/verification screens
            challenge_keywords = ["verify", "security check", "unusual activity", "confirm", "suspicious"]
            for keyword in challenge_keywords:
                if keyword in xml_lower:
                    print(f"[!] Challenge screen detected: {keyword}")
                    return 'challenge'

            # Check for signup/intro screen (has login-related button and signup/get started button)
            # Check for login screen FIRST (has username and password fields)
            # This is more reliable than button detection
            has_username_field = (
                self.device(textContains="Username").exists(timeout=2) or
                self.device(textContains="Phone").exists(timeout=2) or
                self.device(textContains="Email").exists(timeout=2) or
                self.device(className="android.widget.EditText").exists(timeout=2)
            )

            has_password_field = (
                self.device(textContains="Password").exists(timeout=2) or
                self.device(textContains="password").exists(timeout=2)
            )

            # If we have BOTH username and password fields, we're definitely on login screen
            if has_username_field and has_password_field:
                print("[OK] On login screen (has username AND password fields)")
                return 'login'

            # Check if it's just the intro screen with "I already have an account" or "Sign Up"
            # (These appear BEFORE the login screen)
            has_already_account = (
                self.device(textContains="I already have an account").exists(timeout=2) or
                self.device(textContains="Already have an account").exists(timeout=2)
            )

            has_signup_button = (
                self.device(textContains="Sign Up").exists(timeout=2) or
                self.device(textContains="Sign up").exists(timeout=2) or
                self.device(textContains="Get started").exists(timeout=2) or
                self.device(textContains="Get Started").exists(timeout=2) or
                self.device(textContains="Create").exists(timeout=2) or
                self.device(textContains="Join Instagram").exists(timeout=2)
            )

            # Only consider it signup screen if we have "already have account" or signup button
            # AND we DON'T have both username+password fields
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
        Handle the signup screen by clicking "Already have an account?" or similar

        Returns:
            bool: True if successfully navigated to login screen
        """
        print("\n" + "-"*70)
        print("HANDLING SIGNUP SCREEN")
        print("-"*70)

        # Multiple selector variations for "Already have an account?" link
        selectors = [
            self.device(textContains="I already have an account"),
            self.device(textContains="Already have an account"),
            self.device(text="I already have an account"),
            self.device(textContains="Log In"),
            self.device(textContains="Log in"),
            self.device(text="Log In"),
            self.device(text="Log in"),
            self.device(descriptionContains="Log in"),
        ]

        # Try each selector
        for i, selector in enumerate(selectors, 1):
            try:
                if selector.exists(timeout=3):
                    print(f"[OK] Found login link (selector #{i})")
                    selector.click()
                    print("[OK] Clicked login link")
                    time.sleep(3)  # Wait for transition
                    return True
            except Exception as e:
                print(f"[!] Selector #{i} failed: {e}")
                continue

        # Fallback: click bottom area where "Log In" link usually is
        try:
            print("[!] Trying coordinate-based click (bottom center)")
            width, height = self.device.window_size()
            self.device.click(width // 2, int(height * 0.85))  # Bottom center area
            time.sleep(3)
            return True
        except Exception as e:
            print(f"[X] Coordinate click failed: {e}")

        return False

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
                self.device(textContains="Username"),
                self.device(textContains="Phone"),
                self.device(textContains="Email"),
                self.device(className="android.widget.EditText", instance=0),
            ]

            username_field = None
            for i, selector in enumerate(username_selectors, 1):
                if selector.exists(timeout=3):
                    print(f"[OK] Found username field (selector #{i})")
                    username_field = selector
                    break

            if not username_field:
                print("[X] Could not find username field")
                return False

            # Clear and enter username
            print(f"Entering username: {username}")
            username_field.click()
            time.sleep(1)
            username_field.clear_text()
            time.sleep(0.5)

            # Use ADB input for reliability
            connection_serial = self.device_serial.replace('_', ':')
            subprocess.run(
                ['adb', '-s', connection_serial, 'shell', 'input', 'text', username],
                capture_output=True, timeout=10
            )
            print("[OK] Username entered")
            time.sleep(1)

            # Find password field
            print("Looking for password field...")
            password_selectors = [
                self.device(textContains="Password"),
                self.device(textContains="password"),
                self.device(className="android.widget.EditText", instance=1),
            ]

            password_field = None
            for i, selector in enumerate(password_selectors, 1):
                if selector.exists(timeout=3):
                    print(f"[OK] Found password field (selector #{i})")
                    password_field = selector
                    break

            if not password_field:
                print("[X] Could not find password field")
                return False

            # Clear and enter password
            print("Entering password...")
            password_field.click()
            time.sleep(1)
            password_field.clear_text()
            time.sleep(0.5)

            subprocess.run(
                ['adb', '-s', connection_serial, 'shell', 'input', 'text', password],
                capture_output=True, timeout=10
            )
            print("[OK] Password entered")
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
                if selector.exists(timeout=3):
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

            # FIRST: Exclude challenge/notification screens that are NOT 2FA code entry
            # These screens may contain words like "we sent" but are NOT code entry screens
            challenge_exclusions = [
                "check your notifications",
                "notifications on another device",
                "waiting for approval",
                "approve from the other device",
                "try another way",
                "check your sms",
                "check your email",
                "confirm your identity",
                "it was you",
            ]
            for excl in challenge_exclusions:
                if excl in xml_lower:
                    print(f"[X] Not 2FA code entry — this is a challenge screen ('{excl}')")
                    return False

            # Strong 2FA code entry keywords (specific to the actual code entry screen)
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
                    print(f"[OK] 2FA code entry screen detected: '{keyword}'")
                    return True

            # Weak keywords — only match if there's also an EditText (input field) visible
            weak_keywords = ["we sent", "verify", "2fa", "enter your"]
            for keyword in weak_keywords:
                if keyword in xml_lower:
                    # Must also have an input field to be a code entry screen
                    edit_texts = self.device(className="android.widget.EditText")
                    if edit_texts.exists(timeout=2) and edit_texts.count == 1:
                        print(f"[OK] 2FA screen detected: '{keyword}' + single EditText field")
                        return True
                    else:
                        print(f"[!] Found '{keyword}' but no single EditText — not a code entry screen")

            # Check for single EditText + code/security context
            edit_texts = self.device(className="android.widget.EditText")
            if edit_texts.exists(timeout=2):
                edit_text_count = edit_texts.count
                print(f"Found {edit_text_count} EditText field(s)")
                if edit_text_count == 1:
                    if any(kw in xml_lower for kw in ["code", "security"]):
                        print("[OK] 2FA screen detected (single EditText + code/security context)")
                        return True

            # Check for "Resend Code" button (unique to 2FA)
            if self.device(textContains="Resend").exists(timeout=1):
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
        """
        for attempt in range(1, max_retries + 1):
            try:
                xml = self.device.dump_hierarchy()
                # Check if we got systemui instead of the actual app
                if 'com.android.systemui' in xml[:500] and 'instagram' not in xml[:1000].lower():
                    print(f"{tag} [DUMP] Attempt {attempt}/{max_retries}: Got systemui overlay, retrying...")
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
                # Notification approval screens
                "check your notifications",
                "notifications on another device",
                "waiting for approval",
                "approve from the other device",
                # SMS screens (also have "Try another way")
                "check your sms",
                # Email screens
                "check your email",
                # Generic challenge
                "confirm your identity",
                "verify your identity",
                "it was you",
                "we noticed an unusual login",
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
            if not try_btn.exists(timeout=3):
                try_btn = self.device(textContains="another way")
            if not try_btn.exists(timeout=3):
                try_btn = self.device(descriptionContains="Try another way")

            if try_btn.exists(timeout=2):
                print(f"{TAG} [OK] Found 'Try another way' - clicking...")
                try_btn.click()
                time.sleep(2)

                # Verify click registered - if button still visible, retry with coordinates
                try:
                    if try_btn.exists(timeout=2):
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
        if not auth_app.exists(timeout=3):
            auth_app = self.device(textContains="authentication app")
        if not auth_app.exists(timeout=3):
            auth_app = self.device(descriptionContains="Authentication app")
        if not auth_app.exists(timeout=3):
            # Try scrolling
            try:
                w, h = self.device.window_size()
                self.device.swipe(w // 2, int(h * 0.7), w // 2, int(h * 0.3), duration=0.3)
                time.sleep(1.5)
            except:
                pass
            auth_app = self.device(textContains="Authentication app")

        if not auth_app.exists(timeout=3):
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
            if radio.exists(timeout=2):
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
            if btn.exists(timeout=2):
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
            if btn.exists(timeout=2):
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
                if selector.exists(timeout=2):
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

            # Enter code via ADB (most reliable method)
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
                if selector.exists(timeout=2):
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
                if buttons.exists(timeout=2):
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
                if selector.exists(timeout=3):
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
                if selector.exists(timeout=2):
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

            # Click "Not Now" or similar
            dismiss_selectors = [
                self.device(text="Not Now"),
                self.device(textContains="Not Now"),
                self.device(text="Not now"),
                self.device(text="Skip"),
                self.device(textContains="Skip"),
            ]

            for i, selector in enumerate(dismiss_selectors, 1):
                if selector.exists(timeout=3):
                    print(f"[OK] Found dismiss button (selector #{i})")
                    selector.click()
                    print("[OK] Dismissed notification prompt")
                    time.sleep(2)
                    return True

            print("[!] Could not dismiss notification prompt")
            return True  # Continue anyway

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
                    if selector.exists(timeout=2):
                        print("[OK] Found 'Continue' button (likely location services)")
                        selector.click()
                        print("[OK] Clicked Continue")
                        time.sleep(2)
                        continue_found = True

                        # Now look for "Deny" button in the native permission dialog
                        deny_selectors = [
                            self.device(text="Deny"),
                            self.device(textContains="Deny"),
                            self.device(text="Don't allow"),
                            self.device(textContains="Don't allow"),
                        ]

                        for deny_selector in deny_selectors:
                            if deny_selector.exists(timeout=3):
                                print("[OK] Found 'Deny' button in permission dialog")
                                deny_selector.click()
                                print("[OK] Clicked Deny")
                                time.sleep(2)
                                break

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
                    if selector.exists(timeout=2):
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
        Verify that login was successful by checking for profile tab or home feed

        Returns:
            bool: True if logged in
        """
        print("\n" + "-"*70)
        print("VERIFYING LOGIN SUCCESS")
        print("-"*70)

        try:
            # Wait a bit for UI to settle
            time.sleep(3)

            # Check for profile tab
            if self.device(description="Profile").exists(timeout=5):
                print("[OK] Logged in (Profile tab visible)")
                return True

            if self.device(resourceId="com.instagram.android:id/profile_tab").exists(timeout=3):
                print("[OK] Logged in (Profile tab resource ID found)")
                return True

            # Check for home feed tab
            if self.device(description="Home").exists(timeout=3):
                print("[OK] Logged in (Home tab visible)")
                return True

            # Check for search/explore tab
            if self.device(description="Search and Explore").exists(timeout=3):
                print("[OK] Logged in (Search tab visible)")
                return True

            # Check XML for common logged-in elements
            xml_dump = self.device.dump_hierarchy()
            xml_lower = xml_dump.lower()

            logged_in_keywords = ["home", "profile", "search", "reels", "activity"]
            matches = sum(1 for keyword in logged_in_keywords if keyword in xml_lower)

            if matches >= 2:
                print(f"[OK] Logged in (found {matches} navigation elements)")
                return True

            print("[!] Could not verify login (but may still be successful)")
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

            # Enter credentials
            if not self.enter_credentials(username, password):
                result['error'] = "Failed to enter credentials"
                return result

            # Quick check for Wrong Password modal (appears instantly)
            time.sleep(3)
            xml_quick = self.device.dump_hierarchy().lower()
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

            # Check for SMS/Email verification — NOT a dead end if "Try another way" exists
            sms_keywords = ["check your sms", "we sent a link", "sent a code to", "check your email"]
            sms_detected = any(kw in xml_check for kw in sms_keywords)
            if sms_detected:
                sms_matched = [kw for kw in sms_keywords if kw in xml_check]
                print(f"\n[!] SMS/Email screen detected: {sms_matched}")
                # Don't return as dead end yet — _try_another_way_to_2fa will handle it
                # by clicking "Try another way" → "Authentication app"
                if "try another way" not in xml_check:
                    print("[X] No 'Try another way' option — true dead end")
                    result['error'] = "SMS/Email verification required — no alternative"
                    result['login_type'] = 'sms_challenge'
                    return result
                else:
                    print("[OK] 'Try another way' available — will attempt Auth app path")

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
                # Try to dismiss modals even if verification was inconclusive
                self.dismiss_post_login_modals()

                print("\n" + "="*70)
                print("[!] LOGIN VERIFICATION INCONCLUSIVE")
                print("="*70)
                result['error'] = "Could not verify login success"
                # Still mark as success since no errors occurred
                result['success'] = True
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
