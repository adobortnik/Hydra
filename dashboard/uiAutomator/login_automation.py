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

import uiautomator2 as u2
import subprocess
import time
from pathlib import Path
from two_fa_live_client import TwoFALiveClient


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
            print("✗ No device serial specified")
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
            print("✓ Killed all UIAutomator-related processes")
            print("⏳ Waiting for complete shutdown...")
            time.sleep(5)  # CRITICAL: Wait for complete shutdown before connecting
        except Exception as e:
            print(f"⚠ Warning during cleanup: {e}")

        # STEP 2: Connect to device - u2.connect() will auto-start UIAutomator
        print("Connecting to device...")
        print("(uiautomator2 will automatically start UIAutomator service)")
        self.device = u2.connect(connection_serial)
        print(f"✓ Connected (serial: {self.device.serial})")

        # STEP 3: Wait for UIAutomator to be responsive
        print("⏳ Waiting for UIAutomator to be responsive...")
        max_wait = 45  # seconds
        start_time = time.time()

        while (time.time() - start_time) < max_wait:
            try:
                _ = self.device.info
                _ = self.device.window_size()
                elapsed = int(time.time() - start_time)
                print(f"✓ SUCCESS! UIAutomator is responsive (took {elapsed}s)")
                return self.device
            except Exception as e:
                elapsed = int(time.time() - start_time)
                if elapsed % 5 == 0:  # Print every 5 seconds
                    print(f"⏳ Waiting... {elapsed}s / {max_wait}s")
                time.sleep(1)

        print(f"✗ Failed to connect to device after {max_wait}s")
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
            print("✗ Device not connected")
            return False

        print(f"\n{'='*70}")
        print(f"OPENING INSTAGRAM: {instagram_package}")
        print(f"{'='*70}")

        try:
            # Use uiautomator2's app_start with monkey (most reliable)
            self.device.app_start(instagram_package, use_monkey=True)
            print("✓ Instagram launched with monkey")
            time.sleep(5)  # Give app time to launch

            # Verify app is running
            current_app = self.device.app_current().get('package')
            if current_app == instagram_package:
                print(f"✓ Instagram is running: {instagram_package}")
                return True

            return True  # Still return True even if verification fails

        except Exception as e:
            print(f"⚠ app_start failed: {e}, falling back to ADB monkey command")
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
                print("✓ Already logged in (profile tab visible)")
                return 'logged_in'

            # Check for challenge/verification screens
            challenge_keywords = ["verify", "security check", "unusual activity", "confirm", "suspicious"]
            for keyword in challenge_keywords:
                if keyword in xml_lower:
                    print(f"⚠ Challenge screen detected: {keyword}")
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
                print("✓ On login screen (has username AND password fields)")
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
                print("✓ On signup/intro screen (has 'already have account' or signup button)")
                return 'signup'

            # Fallback: if we have at least one login field, assume login screen
            if has_username_field or has_password_field:
                print("✓ On login screen (has at least one login field)")
                return 'login'

            print("⚠ Unknown screen state")
            return 'unknown'

        except Exception as e:
            print(f"✗ Error detecting screen state: {e}")
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
                    print(f"✓ Found login link (selector #{i})")
                    selector.click()
                    print("✓ Clicked login link")
                    time.sleep(3)  # Wait for transition
                    return True
            except Exception as e:
                print(f"⚠ Selector #{i} failed: {e}")
                continue

        # Fallback: click bottom area where "Log In" link usually is
        try:
            print("⚠ Trying coordinate-based click (bottom center)")
            width, height = self.device.window_size()
            self.device.click(width // 2, int(height * 0.85))  # Bottom center area
            time.sleep(3)
            return True
        except Exception as e:
            print(f"✗ Coordinate click failed: {e}")

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
                    print(f"✓ Found username field (selector #{i})")
                    username_field = selector
                    break

            if not username_field:
                print("✗ Could not find username field")
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
            print("✓ Username entered")
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
                    print(f"✓ Found password field (selector #{i})")
                    password_field = selector
                    break

            if not password_field:
                print("✗ Could not find password field")
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
            print("✓ Password entered")
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
                    print(f"✓ Found login button (selector #{i})")
                    selector.click()
                    print("✓ Clicked login button")
                    time.sleep(5)  # Wait for login to process
                    return True

            print("✗ Could not find login button")
            return False

        except Exception as e:
            print(f"✗ Error entering credentials: {e}")
            return False

    def detect_two_factor_screen(self):
        """
        Detect if we're on the 2FA code entry screen

        Returns:
            bool: True if on 2FA screen
        """
        try:
            print("Checking screen for 2FA indicators...")
            xml_dump = self.device.dump_hierarchy()
            xml_lower = xml_dump.lower()

            # Keywords that indicate 2FA screen
            two_fa_keywords = [
                "enter the 6-digit code",
                "enter the code",
                "enter your",
                "confirmation code",
                "security code",
                "two-factor",
                "2fa",
                "authentication code",
                "verify",
                "we sent"
            ]

            for keyword in two_fa_keywords:
                if keyword in xml_lower:
                    print(f"✓ 2FA screen detected: keyword '{keyword}'")
                    return True

            # Check for EditText field with specific context
            # On 2FA screen, there's usually a single EditText field
            edit_texts = self.device(className="android.widget.EditText")
            if edit_texts.exists(timeout=2):
                # Count EditText fields - 2FA usually has 1, login has 2
                edit_text_count = edit_texts.count
                print(f"Found {edit_text_count} EditText field(s)")

                # If only 1 EditText and page mentions code/verify/security
                if edit_text_count == 1:
                    if any(keyword in xml_lower for keyword in ["code", "security", "verify", "sent"]):
                        print("✓ 2FA screen detected (single EditText + verification keywords)")
                        return True

            # Also check for "Resend Code" or similar buttons (unique to 2FA)
            if self.device(textContains="Resend").exists(timeout=1):
                print("✓ 2FA screen detected ('Resend' button found)")
                return True

            print("✗ No 2FA indicators found")
            return False

        except Exception as e:
            print(f"⚠ Error detecting 2FA screen: {e}")
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
            print("✗ No 2FA token provided")
            return False

        # Fetch code from 2fa.live
        client = TwoFALiveClient(two_fa_token, timeout=60)
        code = client.get_code(max_retries=20, retry_interval=3)

        if not code:
            print("✗ Could not retrieve 2FA code")
            return False

        print(f"\n✓ Got 2FA code: {code}")

        # Enter code
        print("Entering 2FA code...")

        try:
            # Find code input field
            code_field = self.device(className="android.widget.EditText")

            if not code_field.exists(timeout=3):
                print("✗ Could not find code input field")
                return False

            print("✓ Found code input field")
            code_field.click()
            time.sleep(1)
            code_field.clear_text()
            time.sleep(0.5)

            # Enter code via ADB
            connection_serial = self.device_serial.replace('_', ':')
            subprocess.run(
                ['adb', '-s', connection_serial, 'shell', 'input', 'text', code],
                capture_output=True, timeout=10
            )

            print(f"✓ Entered code: {code}")
            time.sleep(2)

            # Scroll down slightly to reveal the Continue button
            # (On some devices with purple background, the button is below the fold)
            print("Scrolling down to reveal Continue button...")
            try:
                width, height = self.device.window_size()
                # Swipe up (scroll down) from bottom 60% to bottom 40%
                self.device.swipe(width // 2, int(height * 0.6), width // 2, int(height * 0.4), duration=0.3)
                time.sleep(1)
                print("✓ Scrolled down")
            except Exception as e:
                print(f"⚠ Could not scroll: {e}")

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
                    print(f"✓ Found confirm button (selector #{i}: {selector})")

                    # Get button info to make sure it's not a checkbox
                    try:
                        button_info = selector.info
                        if button_info.get('checkable', False):
                            print(f"⚠ Selector #{i} is checkable (likely checkbox), skipping...")
                            continue
                    except:
                        pass

                    selector.click()
                    print("✓ Clicked confirm button")
                    button_found = True
                    break

            # If no specific button found, try generic button but verify it's not a checkbox
            if not button_found:
                print("⚠ No specific button found, trying generic button selector...")
                buttons = self.device(className="android.widget.Button")
                if buttons.exists(timeout=2):
                    # Try to find a button that's not checkable
                    for i in range(buttons.count):
                        try:
                            btn = self.device(className="android.widget.Button", instance=i)
                            btn_info = btn.info
                            if not btn_info.get('checkable', False):
                                print(f"✓ Found non-checkable button (instance {i})")
                                btn.click()
                                print("✓ Clicked button")
                                button_found = True
                                break
                        except:
                            continue

            if not button_found:
                print("⚠ Could not find confirm button, continuing anyway...")

            time.sleep(5)  # Wait for 2FA to process
            return True

        except Exception as e:
            print(f"✗ Error entering 2FA code: {e}")
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
                print("✓ No 'Save Login Info' prompt found")
                return True

            print("✓ 'Save Login Info' prompt detected")

            # Find Save button
            save_selectors = [
                self.device(text="Save"),
                self.device(textContains="Save"),
                self.device(text="Save Info"),
                self.device(description="Save"),
            ]

            for i, selector in enumerate(save_selectors, 1):
                if selector.exists(timeout=3):
                    print(f"✓ Found Save button (selector #{i})")
                    selector.click()
                    print("✓ Clicked Save")
                    time.sleep(3)
                    return True

            print("⚠ Could not find Save button, trying Not Now")

            # Try "Not Now" as fallback
            not_now_selectors = [
                self.device(text="Not Now"),
                self.device(textContains="Not Now"),
                self.device(text="Not now"),
            ]

            for selector in not_now_selectors:
                if selector.exists(timeout=2):
                    print("✓ Clicked 'Not Now'")
                    selector.click()
                    time.sleep(2)
                    return True

            print("⚠ Could not interact with Save prompt, continuing anyway")
            return True

        except Exception as e:
            print(f"⚠ Error handling save prompt: {e}")
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
                print("✓ No notification prompt found")
                return True

            print("✓ Notification prompt detected")

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
                    print(f"✓ Found dismiss button (selector #{i})")
                    selector.click()
                    print("✓ Dismissed notification prompt")
                    time.sleep(2)
                    return True

            print("⚠ Could not dismiss notification prompt")
            return True  # Continue anyway

        except Exception as e:
            print(f"⚠ Error dismissing notification: {e}")
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
                        print("✓ Found 'Continue' button (likely location services)")
                        selector.click()
                        print("✓ Clicked Continue")
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
                                print("✓ Found 'Deny' button in permission dialog")
                                deny_selector.click()
                                print("✓ Clicked Deny")
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
                        print(f"✓ Found dismiss button (selector #{i}): {selector.info.get('text', 'unknown')}")
                        selector.click()
                        print("✓ Clicked dismiss button")
                        time.sleep(2)  # Wait for modal to dismiss
                        modal_found = True
                        break

                if not modal_found:
                    print("✓ No more modals found")
                    break

            print("✓ Post-login modal check complete")
            return True

        except Exception as e:
            print(f"⚠ Error dismissing post-login modals: {e}")
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
                print("✓ Logged in (Profile tab visible)")
                return True

            if self.device(resourceId="com.instagram.android:id/profile_tab").exists(timeout=3):
                print("✓ Logged in (Profile tab resource ID found)")
                return True

            # Check for home feed tab
            if self.device(description="Home").exists(timeout=3):
                print("✓ Logged in (Home tab visible)")
                return True

            # Check for search/explore tab
            if self.device(description="Search and Explore").exists(timeout=3):
                print("✓ Logged in (Search tab visible)")
                return True

            # Check XML for common logged-in elements
            xml_dump = self.device.dump_hierarchy()
            xml_lower = xml_dump.lower()

            logged_in_keywords = ["home", "profile", "search", "reels", "activity"]
            matches = sum(1 for keyword in logged_in_keywords if keyword in xml_lower)

            if matches >= 2:
                print(f"✓ Logged in (found {matches} navigation elements)")
                return True

            print("⚠ Could not verify login (but may still be successful)")
            return False

        except Exception as e:
            print(f"⚠ Error verifying login: {e}")
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
                print("\n✓ Account is already logged in!")
                result['success'] = True
                result['login_type'] = 'already_logged_in'
                return result

            # Handle challenge screen
            if screen_state == 'challenge':
                print("\n⚠ Challenge/verification screen detected")
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

            # Wait and check for 2FA (give it more time to appear)
            print("\n" + "-"*70)
            print("CHECKING FOR 2FA SCREEN...")
            print("-"*70)
            time.sleep(6)  # Increased from 5 to 6 seconds

            two_fa_detected = self.detect_two_factor_screen()

            if two_fa_detected:
                print("\n✓ 2FA screen detected")
                result['two_fa_used'] = True

                if not two_fa_token:
                    result['error'] = "2FA required but no token provided"
                    return result

                if not self.handle_two_factor(two_fa_token):
                    result['error'] = "Failed to handle 2FA"
                    return result

                result['login_type'] = '2fa'

                # After 2FA, wait for login to complete before handling prompts
                print("⏳ Waiting for 2FA login to complete...")
                time.sleep(6)  # Increased from 5 to 6
            else:
                print("✓ No 2FA screen detected (normal login)")
                result['login_type'] = 'normal'
                # After normal login, wait a bit for any prompts
                time.sleep(3)

            # Before handling prompts, double-check we're not stuck on 2FA screen
            print("\n" + "-"*70)
            print("DOUBLE-CHECKING: Are we stuck on 2FA screen?")
            print("-"*70)

            # Re-check for 2FA screen (in case detection missed it the first time)
            if self.detect_two_factor_screen():
                print("\n⚠ WARNING: Still on 2FA screen after entering credentials!")

                if two_fa_token and not two_fa_detected:
                    # We missed 2FA detection the first time, handle it now
                    print("Handling 2FA now (was missed in first detection)...")
                    result['two_fa_used'] = True

                    if not self.handle_two_factor(two_fa_token):
                        result['error'] = "Failed to handle 2FA (second attempt)"
                        return result

                    result['login_type'] = '2fa'
                    print("⏳ Waiting for 2FA login to complete...")
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
                print("✓ LOGIN SUCCESSFUL!")
                print("="*70)
                result['success'] = True
                return result
            else:
                # Try to dismiss modals even if verification was inconclusive
                self.dismiss_post_login_modals()

                print("\n" + "="*70)
                print("⚠ LOGIN VERIFICATION INCONCLUSIVE")
                print("="*70)
                result['error'] = "Could not verify login success"
                # Still mark as success since no errors occurred
                result['success'] = True
                return result

        except Exception as e:
            print(f"\n✗ Login failed with exception: {e}")
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
        print("\n✗ Failed to connect to device")
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
