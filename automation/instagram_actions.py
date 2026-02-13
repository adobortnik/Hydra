"""
Instagram Actions Module
=========================
Core Instagram UI interactions via uiautomator2.

Provides:
    - Open Instagram (any clone package)
    - Detect screen state (logged_in, login, signup, challenge, 2fa, unknown)
    - Navigate to profile, edit profile
    - Dismiss common popups and modals
    - Get current app info

All actions use the multiple-selector-with-fallback pattern from the original scripts.
"""

import subprocess
import time
import logging

log = logging.getLogger(__name__)


class InstagramActions:
    """
    Instagram UI automation controller.

    Requires an active DeviceConnection or raw u2 device object.
    """

    def __init__(self, device, device_serial):
        """
        Args:
            device: uiautomator2 device object (already connected)
            device_serial: DB format serial "10.1.10.183_5555"
        """
        self.device = device
        self.device_serial = device_serial
        self.adb_serial = device_serial.replace('_', ':')

    # ------------------------------------------------------------------
    #  App Lifecycle
    # ------------------------------------------------------------------

    def open_instagram(self, package="com.instagram.android", activity=None):
        """
        Open an Instagram clone package and VERIFY it's in foreground.

        Uses the proven GramAddict method: app_start with use_monkey=True.
        Falls back to bring-to-foreground and ADB monkey if needed.

        Args:
            package: The Instagram clone package name (e.g. com.instagram.androio)
            activity: Optional activity class (ignored for launch, kept for compat)
        Returns True only if the correct package is confirmed in foreground.
        """
        log.info("[%s] Opening Instagram: %s", self.device_serial, package)

        # Check if already in foreground
        try:
            current = self.device.app_current().get('package', '')
            if current == package:
                log.info("[%s] Instagram already in foreground: %s", self.device_serial, package)
                return True

            # If a DIFFERENT Instagram clone is in foreground, force-stop it first
            if current and current.startswith('com.instagram.'):
                log.info("[%s] Stopping wrong IG clone in foreground: %s", self.device_serial, current)
                try:
                    subprocess.run(
                        ['adb', '-s', self.adb_serial, 'shell', 'am', 'force-stop', current],
                        capture_output=True, timeout=5
                    )
                    time.sleep(2)
                except Exception:
                    pass
        except Exception:
            pass

        # Launch with retry (up to 2 attempts)
        for attempt in range(1, 3):
            # Method 1: app_start with monkey (proven GramAddict method)
            try:
                self.device.app_start(package, use_monkey=True)
                log.info("[%s] Launched %s via monkey (attempt %d)", self.device_serial, package, attempt)
            except Exception as e:
                log.warning("[%s] app_start monkey failed: %s", self.device_serial, e)
                # Fallback: ADB monkey
                try:
                    subprocess.run(
                        ['adb', '-s', self.adb_serial, 'shell',
                         'monkey', '-p', package, '1'],
                        capture_output=True, text=True, timeout=10
                    )
                    log.info("[%s] Launched %s via ADB monkey (attempt %d)", self.device_serial, package, attempt)
                except Exception as e2:
                    log.error("[%s] All launch methods failed: %s", self.device_serial, e2)
                    if attempt == 2:
                        return False
                    continue

            # Wait for app to load
            time.sleep(5)

            # VERIFY: Check up to 10s for the correct package
            for wait in range(10):
                try:
                    current = self.device.app_current().get('package', '')
                    if current == package:
                        log.info("[%s] ✓ Instagram confirmed: %s (took %ds)",
                                 self.device_serial, package, wait + 5)
                        return True
                except Exception:
                    pass
                time.sleep(1)

            # Wrong app still — force-stop it before retry
            try:
                current = self.device.app_current().get('package', '')
                if current and current.startswith('com.instagram.') and current != package:
                    log.warning("[%s] Wrong clone still running: %s. Force-stopping before retry.",
                                self.device_serial, current)
                    subprocess.run(
                        ['adb', '-s', self.adb_serial, 'shell', 'am', 'force-stop', current],
                        capture_output=True, timeout=5
                    )
                    time.sleep(2)
            except Exception:
                pass

        # Failed after retries
        try:
            current = self.device.app_current().get('package', '')
        except Exception:
            current = 'unknown'

        log.error("[%s] ✗ Failed to open %s after 2 attempts. Foreground: %s",
                  self.device_serial, package, current)
        return False

    def close_instagram(self, package="com.instagram.android"):
        """Force-stop Instagram."""
        try:
            self.device.app_stop(package)
            return True
        except Exception:
            try:
                subprocess.run(
                    ['adb', '-s', self.adb_serial, 'shell', 'am', 'force-stop', package],
                    capture_output=True, timeout=5
                )
                return True
            except Exception:
                return False

    # ------------------------------------------------------------------
    #  Screen Detection
    # ------------------------------------------------------------------

    def detect_screen_state(self):
        """
        Detect which screen we're currently on.

        Returns one of:
            'logged_in'           - Profile/home tab visible
            'login'               - Username + password fields visible
            'signup'              - Intro screen with "Already have account"
            'challenge'           - Verification/security screen
            '2fa'                 - Two-factor auth code entry
            'suspended'           - Account disabled/suspended/compromised
            'verification_required' - Human verification required
            'unknown'             - Could not determine
        """
        try:
            xml_dump = self.device.dump_hierarchy()
            xml_lower = xml_dump.lower()

            # Check for suspended / disabled / compromised FIRST (highest priority)
            suspended_kw = [
                "your account has been disabled",
                "we suspended your account",
                "account suspended",
                "your account was compromised",
                "we've disabled your account",
                "your account has been temporarily locked",
                "this account has been suspended",
                "we removed your account",
            ]
            for kw in suspended_kw:
                if kw in xml_lower:
                    log.warning("[%s] SUSPENDED screen detected: matched '%s'",
                                self.device_serial, kw)
                    return 'suspended'

            # Check for human verification / captcha
            verification_kw = [
                "human verification required",
                "verify you're a real person",
                "complete the captcha",
                "prove you're not a robot",
                "automated behavior",
            ]
            for kw in verification_kw:
                if kw in xml_lower:
                    log.warning("[%s] VERIFICATION_REQUIRED screen detected: matched '%s'",
                                self.device_serial, kw)
                    return 'verification_required'

            # Check challenge/verification (generic Instagram challenges)
            challenge_kw = ["verify", "security check", "unusual activity", "confirm", "suspicious"]
            for kw in challenge_kw:
                if kw in xml_lower:
                    return 'challenge'

            # Check 2FA
            twofa_kw = ["enter the 6-digit code", "enter the code", "confirmation code",
                        "security code", "two-factor", "2fa", "authentication code"]
            for kw in twofa_kw:
                if kw in xml_lower:
                    return '2fa'

            # Check for login/signup BEFORE checking logged_in
            # (prevents false 'logged_in' when app is on login screen or launcher)

            # Check signup/intro — "I already have an account" / "Sign In" / "Log In"
            signup_kw = [
                "i already have an account", "already have an account",
                "sign in", "log in", "log into",
                "sign up", "get started", "create new account",
            ]
            for kw in signup_kw:
                if kw in xml_lower:
                    log.info("[%s] Login/signup screen detected: matched '%s'",
                             self.device_serial, kw)
                    return 'signup' if 'sign up' in kw or 'create' in kw or 'get started' in kw or 'already' in kw else 'login'

            # Check for login fields
            has_username = (
                self.device(textContains="Username").exists(timeout=2) or
                self.device(textContains="Phone").exists(timeout=2) or
                self.device(textContains="Email").exists(timeout=2) or
                self.device(className="android.widget.EditText").exists(timeout=2)
            )
            has_password = (
                self.device(textContains="Password").exists(timeout=2) or
                self.device(textContains="password").exists(timeout=2)
            )

            if has_username and has_password:
                return 'login'

            if has_username or has_password:
                return 'login'

            # Check logged in — ONLY if correct IG app is in foreground
            # Verify the expected package is running (not launcher or wrong clone)
            try:
                import subprocess
                adb_serial = self.device_serial.replace('_', ':')
                focus_result = subprocess.run(
                    ['adb', '-s', adb_serial, 'shell', 'dumpsys', 'window', '|', 'grep', 'mCurrentFocus'],
                    capture_output=True, text=True, timeout=5, shell=True
                )
                focus_text = focus_result.stdout.strip()
                # Check if any IG package is in foreground
                is_ig_foreground = 'com.instagram' in focus_text
            except Exception:
                is_ig_foreground = True  # assume yes if check fails

            if is_ig_foreground and (
                self.device(description="Profile").exists(timeout=2) or
                self.device(description="Home").exists(timeout=2) or
                self.device(descriptionContains="Search").exists(timeout=2)):
                return 'logged_in'

            return 'unknown'

        except Exception as e:
            log.error("[%s] detect_screen_state error: %s", self.device_serial, e)
            return 'unknown'

    # ------------------------------------------------------------------
    #  Navigation
    # ------------------------------------------------------------------

    def navigate_to_profile(self):
        """Navigate to the user's profile tab. Returns True on success."""
        try:
            selectors = [
                self.device(description="Profile"),
                self.device(description="profile"),
                self.device(text="Profile"),
            ]
            for sel in selectors:
                if sel.exists(timeout=3):
                    sel.click()
                    time.sleep(2)
                    return True

            # Fallback: bottom-right corner
            w, h = self.device.window_size()
            self.device.click(int(w * 0.9), int(h * 0.95))
            time.sleep(2)
            return True
        except Exception as e:
            log.error("[%s] navigate_to_profile failed: %s", self.device_serial, e)
            return False

    def navigate_to_edit_profile(self):
        """Navigate to Edit Profile screen. Returns True on success."""
        try:
            selectors = [
                self.device(text="Edit profile"),
                self.device(text="Edit Profile"),
                self.device(description="Edit profile"),
                self.device(textContains="Edit"),
            ]
            for sel in selectors:
                if sel.exists(timeout=3):
                    sel.click()
                    time.sleep(2)
                    return True
            return False
        except Exception as e:
            log.error("[%s] navigate_to_edit_profile failed: %s", self.device_serial, e)
            return False

    def navigate_to_home(self):
        """Navigate to home feed."""
        try:
            selectors = [
                self.device(description="Home"),
                self.device(description="home"),
            ]
            for sel in selectors:
                if sel.exists(timeout=3):
                    sel.click()
                    time.sleep(2)
                    return True
            return False
        except Exception as e:
            log.error("[%s] navigate_to_home failed: %s", self.device_serial, e)
            return False

    # ------------------------------------------------------------------
    #  Signup / Login Screen Handling
    # ------------------------------------------------------------------

    def handle_signup_screen(self):
        """
        From the signup/intro screen, navigate to login.
        Returns True on success.
        """
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
        for sel in selectors:
            try:
                if sel.exists(timeout=3):
                    sel.click()
                    time.sleep(3)
                    return True
            except Exception:
                continue

        # Fallback: bottom center tap
        try:
            w, h = self.device.window_size()
            self.device.click(w // 2, int(h * 0.85))
            time.sleep(3)
            return True
        except Exception:
            return False

    def enter_credentials(self, username, password):
        """
        Enter username and password on login screen.
        Returns True on success.
        """
        try:
            # Find username field
            username_sels = [
                self.device(textContains="Username"),
                self.device(textContains="Phone"),
                self.device(textContains="Email"),
                self.device(className="android.widget.EditText", instance=0),
            ]
            username_field = None
            for sel in username_sels:
                if sel.exists(timeout=3):
                    username_field = sel
                    break
            if not username_field:
                log.error("[%s] Username field not found", self.device_serial)
                return False

            username_field.click()
            time.sleep(1)
            username_field.clear_text()
            time.sleep(0.5)

            # Use ADB input for reliability
            subprocess.run(
                ['adb', '-s', self.adb_serial, 'shell', 'input', 'text', username],
                capture_output=True, timeout=10
            )
            time.sleep(1)

            # Find password field
            password_sels = [
                self.device(textContains="Password"),
                self.device(textContains="password"),
                self.device(className="android.widget.EditText", instance=1),
            ]
            password_field = None
            for sel in password_sels:
                if sel.exists(timeout=3):
                    password_field = sel
                    break
            if not password_field:
                log.error("[%s] Password field not found", self.device_serial)
                return False

            password_field.click()
            time.sleep(1)
            password_field.clear_text()
            time.sleep(0.5)

            subprocess.run(
                ['adb', '-s', self.adb_serial, 'shell', 'input', 'text', password],
                capture_output=True, timeout=10
            )
            time.sleep(1)

            # Click login button
            login_sels = [
                self.device(text="Log In"),
                self.device(text="Log in"),
                self.device(textContains="Log in"),
                self.device(textContains="Log In"),
                self.device(description="Log in"),
                self.device(className="android.widget.Button", textContains="Log"),
            ]
            for sel in login_sels:
                if sel.exists(timeout=3):
                    sel.click()
                    time.sleep(5)
                    return True

            log.error("[%s] Login button not found", self.device_serial)
            return False

        except Exception as e:
            log.error("[%s] enter_credentials failed: %s", self.device_serial, e)
            return False

    # ------------------------------------------------------------------
    #  Post-Login Popup Handling
    # ------------------------------------------------------------------

    def handle_save_login_info(self):
        """Handle 'Save Your Login Info?' prompt."""
        try:
            xml_lower = self.device.dump_hierarchy().lower()
            if "save" not in xml_lower and "login info" not in xml_lower:
                return True

            for sel in [self.device(text="Save"), self.device(textContains="Save"),
                        self.device(text="Save Info")]:
                if sel.exists(timeout=3):
                    sel.click()
                    time.sleep(3)
                    return True

            # Fallback: Not Now
            for sel in [self.device(text="Not Now"), self.device(textContains="Not Now"),
                        self.device(text="Not now")]:
                if sel.exists(timeout=2):
                    sel.click()
                    time.sleep(2)
                    return True
            return True
        except Exception:
            return True

    def dismiss_notification_prompt(self):
        """Dismiss 'Turn On Notifications?' prompt."""
        try:
            xml_lower = self.device.dump_hierarchy().lower()
            if "notification" not in xml_lower:
                return True

            for sel in [self.device(text="Not Now"), self.device(textContains="Not Now"),
                        self.device(text="Not now"), self.device(text="Skip"),
                        self.device(textContains="Skip")]:
                if sel.exists(timeout=3):
                    sel.click()
                    time.sleep(2)
                    return True
            return True
        except Exception:
            return True

    def dismiss_post_login_modals(self, max_attempts=5):
        """Dismiss any post-login modals (location, contacts, etc.)."""
        try:
            time.sleep(2)
            for attempt in range(max_attempts):
                # Check for Continue -> Deny flow (location services)
                for sel in [self.device(text="Continue"), self.device(textContains="Continue")]:
                    if sel.exists(timeout=2):
                        sel.click()
                        time.sleep(2)
                        for deny in [self.device(text="Deny"), self.device(textContains="Deny"),
                                     self.device(text="Don't allow")]:
                            if deny.exists(timeout=3):
                                deny.click()
                                time.sleep(2)
                                break
                        break

                # Generic dismiss buttons
                dismiss_sels = [
                    self.device(text="Not Now"), self.device(text="Not now"),
                    self.device(text="Skip"), self.device(text="Deny"),
                    self.device(textContains="Not Now"), self.device(textContains="Skip"),
                ]
                found = False
                for sel in dismiss_sels:
                    if sel.exists(timeout=2):
                        sel.click()
                        time.sleep(2)
                        found = True
                        break
                if not found:
                    break
            return True
        except Exception:
            return True

    def verify_logged_in(self):
        """
        Check if we're currently logged in.
        Returns True/False.
        """
        try:
            time.sleep(3)

            if self.device(description="Profile").exists(timeout=5):
                return True
            if self.device(description="Home").exists(timeout=3):
                return True
            if self.device(description="Search and Explore").exists(timeout=3):
                return True

            # XML keyword check
            xml_lower = self.device.dump_hierarchy().lower()
            nav_kw = ["home", "profile", "search", "reels", "activity"]
            if sum(1 for kw in nav_kw if kw in xml_lower) >= 2:
                return True

            return False
        except Exception:
            return False

    # ------------------------------------------------------------------
    #  2FA Detection
    # ------------------------------------------------------------------

    def detect_two_factor_screen(self):
        """Check if we're on the 2FA code entry screen."""
        try:
            xml_lower = self.device.dump_hierarchy().lower()
            twofa_kw = [
                "enter the 6-digit code", "enter the code", "confirmation code",
                "security code", "two-factor", "2fa", "authentication code",
                "verify", "we sent"
            ]
            for kw in twofa_kw:
                if kw in xml_lower:
                    return True

            # Single EditText + verification context
            edit_texts = self.device(className="android.widget.EditText")
            if edit_texts.exists(timeout=2) and edit_texts.count == 1:
                if any(kw in xml_lower for kw in ["code", "security", "verify", "sent"]):
                    return True

            if self.device(textContains="Resend").exists(timeout=1):
                return True

            return False
        except Exception:
            return False

    def enter_2fa_code(self, code):
        """Enter a 2FA code into the input field. Returns True on success."""
        try:
            code_field = self.device(className="android.widget.EditText")
            if not code_field.exists(timeout=3):
                return False

            code_field.click()
            time.sleep(1)
            code_field.clear_text()
            time.sleep(0.5)

            subprocess.run(
                ['adb', '-s', self.adb_serial, 'shell', 'input', 'text', code],
                capture_output=True, timeout=10
            )
            time.sleep(2)

            # Scroll down to reveal Continue button
            try:
                w, h = self.device.window_size()
                self.device.swipe(w // 2, int(h * 0.6), w // 2, int(h * 0.4), duration=0.3)
                time.sleep(1)
            except Exception:
                pass

            # Click confirm button
            confirm_sels = [
                self.device(text="Continue"), self.device(text="Next"),
                self.device(text="Confirm"), self.device(textContains="Continue"),
                self.device(textContains="Next"),
            ]
            for sel in confirm_sels:
                if sel.exists(timeout=2):
                    try:
                        info = sel.info
                        if info.get('checkable', False):
                            continue
                    except Exception:
                        pass
                    sel.click()
                    time.sleep(5)
                    return True

            # Generic non-checkable button
            buttons = self.device(className="android.widget.Button")
            if buttons.exists(timeout=2):
                for i in range(min(buttons.count, 3)):
                    try:
                        btn = self.device(className="android.widget.Button", instance=i)
                        if not btn.info.get('checkable', False):
                            btn.click()
                            time.sleep(5)
                            return True
                    except Exception:
                        continue

            return True  # Code entered even if no button found

        except Exception as e:
            log.error("[%s] enter_2fa_code failed: %s", self.device_serial, e)
            return False
