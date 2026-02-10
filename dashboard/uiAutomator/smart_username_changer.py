#!/usr/bin/env python3
"""
Smart Username Changer with AI and Availability Checking
Intelligently generates usernames and handles "username taken" scenarios
"""

import time
from ai_profile_generator import AIProfileGenerator


class SmartUsernameChanger:
    """
    Intelligently change usernames with automatic retry on conflicts
    Uses AI to generate variations when username is taken
    """

    def __init__(self, device, ai_api_key=None, ai_provider="openai", device_serial=None, old_username=None):
        """
        Initialize smart username changer

        Args:
            device: uiautomator2 device object
            ai_api_key: API key for AI service (optional)
            ai_provider: "openai", "anthropic", or None for algorithmic
            device_serial: Device serial for database updates (optional)
            old_username: Current username before change (optional)
        """
        self.device = device
        self.ai_generator = AIProfileGenerator(
            api_key=ai_api_key,
            provider=ai_provider
        ) if ai_api_key else None

        # For database synchronization
        self.device_serial = device_serial
        self.old_username = old_username

    def change_username_with_retry(self, target_username, mother_account=None, max_attempts=5):
        """
        Try to change username with intelligent retry on failure

        Args:
            target_username: Desired username
            mother_account: Mother account for AI-based variations (optional)
            max_attempts: Maximum retry attempts

        Returns:
            dict: {'success': bool, 'final_username': str, 'attempts': int, 'message': str}
        """
        print(f"\n{'='*70}")
        print(f"SMART USERNAME CHANGE: Attempting to set username to '{target_username}'")
        print(f"{'='*70}")

        attempted_usernames = []
        current_attempt = target_username

        for attempt in range(1, max_attempts + 1):
            print(f"\n--- Attempt {attempt}/{max_attempts}: Trying '{current_attempt}' ---")

            # Try to change username
            result = self._attempt_username_change(current_attempt)

            if result['success']:
                print(f"SUCCESS! Username changed to: {current_attempt}")
                return {
                    'success': True,
                    'final_username': current_attempt,
                    'attempts': attempt,
                    'message': f'Successfully changed to {current_attempt}'
                }

            # Username was taken or error occurred
            attempted_usernames.append(current_attempt)
            print(f"Failed: {result['reason']}")

            if attempt < max_attempts:
                # Generate new variation
                print(f"\nGenerating new username variation...")
                current_attempt = self._generate_next_variation(
                    target_username,
                    mother_account,
                    attempted_usernames,
                    attempt
                )
                print(f"Next attempt will be: {current_attempt}")
                time.sleep(2)

        # All attempts failed
        print(f"\nFAILED after {max_attempts} attempts. Tried:")
        for i, username in enumerate(attempted_usernames, 1):
            print(f"  {i}. {username}")

        return {
            'success': False,
            'final_username': None,
            'attempts': max_attempts,
            'message': f'All {max_attempts} attempts failed',
            'tried_usernames': attempted_usernames
        }

    def _attempt_username_change(self, username):
        """
        Attempt to change username and detect if it's taken

        Returns:
            dict: {'success': bool, 'reason': str}
        """
        try:
            # FIRST: Ensure we're on edit profile screen
            print("  Checking current screen...")
            if not self._is_on_edit_profile_screen():
                print("  Not on edit profile screen! Attempting to navigate...")
                if not self._navigate_to_edit_profile():
                    return {'success': False, 'reason': 'Could not navigate to edit profile screen'}

            # Navigate to username edit screen
            print("  Navigating to username edit...")
            if not self._navigate_to_username_edit():
                return {'success': False, 'reason': 'Could not navigate to username edit screen'}

            # Enter the username
            print(f"  Entering username: {username}")
            if not self._enter_username(username):
                return {'success': False, 'reason': 'Could not enter username'}

            # Save/Submit
            print("  Saving...")
            if not self._save_username():
                return {'success': False, 'reason': 'Could not click save button'}

            time.sleep(3)  # Wait for Instagram to process

            # Check for error messages
            error = self._check_for_username_error()

            if error:
                return {'success': False, 'reason': error}

            # CRITICAL: Verify we're back on edit profile screen, not still on username edit
            if not self._verify_username_accepted():
                return {'success': False, 'reason': 'Still on username edit screen - username was rejected'}

            # Success! Now update bot database and rename folder
            if self.device_serial and self.old_username:
                print("\n  --- Synchronizing Bot Database ---")
                try:
                    from update_username_in_bot import update_username_in_bot

                    db_result = update_username_in_bot(
                        self.device_serial,
                        self.old_username,
                        username
                    )

                    if db_result['success']:
                        print(f"  ✓ Bot database synchronized")
                        print(f"  ✓ Folder renamed: {self.old_username} → {username}")
                        # Update old_username for next retry attempt
                        self.old_username = username
                    else:
                        print(f"  ⚠ Warning: Database sync failed: {db_result['message']}")
                        print(f"  ⚠ Username changed on Instagram but bot folder not renamed!")

                except Exception as e:
                    print(f"  ⚠ Warning: Could not sync database: {e}")
                    print(f"  ⚠ Username changed on Instagram but bot folder not renamed!")

            return {'success': True, 'reason': 'Username changed successfully'}

        except Exception as e:
            return {'success': False, 'reason': f'Exception: {str(e)}'}

    def _navigate_to_username_edit(self):
        """Navigate to username edit screen"""
        try:
            # Look for username field on edit profile screen
            username_selectors = [
                self.device(text="Username"),
                self.device(resourceId="com.instagram.android:id/row_simple_text_textview", text="Username"),
                self.device(className="android.widget.TextView", text="Username")
            ]

            for selector in username_selectors:
                if selector.exists(timeout=3):
                    # Click on the field below the "Username" label
                    bounds = selector.info['bounds']
                    # Click below the label (where the actual username is)
                    click_x = (bounds['left'] + bounds['right']) // 2
                    click_y = bounds['bottom'] + 50  # Click below the label
                    self.device.click(click_x, click_y)
                    time.sleep(2)
                    return True

            print("  Warning: Could not find username field using selectors")
            return False

        except Exception as e:
            print(f"  Error navigating to username edit: {e}")
            return False

    def _enter_username(self, username):
        """Enter username in the text field"""
        try:
            # Find the EditText field
            edit_field = self.device(className="android.widget.EditText")

            if not edit_field.exists(timeout=3):
                print("  Warning: EditText field not found")
                return False

            # Clear existing text
            edit_field.long_click()
            time.sleep(0.5)

            # Try to select all
            if self.device(text="Select all").exists(timeout=1):
                self.device(text="Select all").click()
                time.sleep(0.3)
                self.device.press("delete")
            else:
                # Fallback: clear via set_text
                edit_field.set_text("")

            time.sleep(0.5)

            # Enter new username via ADB (most reliable)
            self.device.shell(f'input text {username}')

            # IMPORTANT: Wait for Instagram to check username availability
            # Instagram shows a loading indicator while checking
            print("  Waiting for Instagram to check username availability...")
            time.sleep(3)  # Give Instagram time to verify username

            return True

        except Exception as e:
            print(f"  Error entering username: {e}")
            return False

    def _save_username(self):
        """
        Click save/done button
        Waits for button to become clickable (Instagram may disable during availability check)
        """
        try:
            # Wait for save button to be ready (not disabled)
            # Instagram disables the checkmark while checking username availability
            max_wait = 10  # Maximum 10 seconds
            start_time = time.time()

            print("  Waiting for save button to be enabled...")

            while (time.time() - start_time) < max_wait:
                # Look for checkmark or done button that is clickable
                save_selectors = [
                    self.device(description="Done", clickable=True),
                    self.device(description="Save", clickable=True),
                    self.device(text="Done", clickable=True),
                    self.device(text="Save", clickable=True),
                    self.device(className="android.widget.ImageView", clickable=True)  # Checkmark
                ]

                for selector in save_selectors:
                    if selector.exists(timeout=0.5):
                        print("  Save button is ready, clicking...")
                        selector.click()
                        time.sleep(0.5)
                        return True

                # Button not ready yet, wait a bit
                time.sleep(0.5)

            print("  Warning: Save button not found or still disabled after 10s, trying anyway...")

            # Fallback: Try to click any save button even if not clickable
            for selector in save_selectors:
                if selector.exists(timeout=1):
                    selector.click()
                    return True

            # Last resort: press enter
            print("  Using keyboard enter as last resort...")
            self.device.press("enter")
            return True

        except Exception as e:
            print(f"  Error saving username: {e}")
            return False

    def _check_for_username_error(self):
        """
        Check if Instagram shows "username taken" or other errors

        Returns:
            str: Error message or None if no error
        """
        try:
            # Common Instagram error messages
            error_indicators = [
                "This username isn't available",
                "isn't available",
                "already taken",
                "try another",
                "unavailable",
                "can't use this username",
                "Username not available"
            ]

            # Check for error text on screen
            for error_text in error_indicators:
                if self.device(textContains=error_text).exists(timeout=2):
                    return f"Username taken: '{error_text}'"

            # Check for generic error dialogs
            if self.device(className="android.widget.TextView", textMatches=".*error.*|.*Error.*").exists(timeout=1):
                error_msg = self.device(className="android.widget.TextView", textMatches=".*error.*|.*Error.*").get_text()
                return f"Error: {error_msg}"

            # No error detected
            return None

        except Exception as e:
            print(f"  Warning checking for errors: {e}")
            return None

    def _verify_username_accepted(self):
        """
        Verify that username was accepted by checking if we returned to edit profile screen
        If we're still on the username edit screen, the username was rejected

        Returns:
            bool: True if on edit profile screen (success), False if still on username edit screen
        """
        try:
            print("  Verifying username was accepted...")
            time.sleep(2)  # Wait for navigation

            # Check if we're back on edit profile screen (has "Edit profile" or profile fields)
            edit_profile_indicators = [
                self.device(text="Name"),  # "Name" field exists on edit profile
                self.device(text="Bio"),   # "Bio" field exists on edit profile
                self.device(text="Website"),  # "Website" field
                self.device(text="Edit profile")  # Header text
            ]

            for indicator in edit_profile_indicators:
                if indicator.exists(timeout=2):
                    print(f"  ✓ Found edit profile indicator: {indicator.info.get('text', 'field')}")
                    return True

            # Check if we're still on username edit screen (has large EditText field)
            if self.device(className="android.widget.EditText").exists(timeout=1):
                # If EditText exists, we might still be on username edit screen
                # Check if "Username" label is at the top (indicates username edit screen)
                if self.device(text="Username").exists() and not self.device(text="Name").exists():
                    print("  ✗ Still on username edit screen - username was rejected!")
                    return False

            # If we can't determine, assume success (but log warning)
            print("  ⚠ Could not determine screen - assuming success")
            return True

        except Exception as e:
            print(f"  Warning verifying username acceptance: {e}")
            return True  # Assume success if we can't verify

    def _generate_next_variation(self, original_username, mother_account, attempted, attempt_num):
        """
        Generate next username variation intelligently

        Args:
            original_username: The original desired username
            mother_account: Mother account for AI generation
            attempted: List of already attempted usernames
            attempt_num: Current attempt number

        Returns:
            str: New username variation
        """
        # If AI is available and mother account provided, use AI
        if self.ai_generator and mother_account:
            print(f"  Using AI to generate variation based on: {mother_account}")
            new_username = self.ai_generator.generate_username(
                mother_account,
                current_username=original_username,
                variations_count=1
            )

            # Ensure it's different from attempted
            if new_username in attempted:
                new_username = self._algorithmic_variation(original_username, attempt_num)

            return new_username

        # Otherwise use algorithmic variations
        return self._algorithmic_variation(original_username, attempt_num)

    def _algorithmic_variation(self, base_username, attempt_num):
        """
        Generate algorithmic username variation

        Args:
            base_username: Base username to vary
            attempt_num: Attempt number (for different patterns)

        Returns:
            str: Variation
        """
        import random

        # Remove existing suffixes
        base = base_username.rstrip('0123456789._')

        # Patterns that avoid words like official, real, private
        patterns = [
            f"{base}{attempt_num}",
            f"{base}.{attempt_num}",
            f"{base}_{attempt_num}",
            f"{base}.ig",
            f"{base}x",
            f"the.{base}",
            f"its.{base}",
            f"{base}.life",
            f"{base}{random.randint(10, 99)}",
            f"x{base}x"
        ]

        # Use attempt_num to select pattern deterministically
        pattern_index = (attempt_num - 1) % len(patterns)
        return patterns[pattern_index]

    def _is_on_edit_profile_screen(self):
        """
        Check if we're currently on the edit profile screen

        Returns:
            bool: True if on edit profile screen
        """
        try:
            # Check for edit profile indicators
            edit_profile_indicators = [
                ("Name", "text"),
                ("Bio", "text"),
                ("Website", "text"),
                ("Username", "text")
            ]

            for indicator_text, selector_type in edit_profile_indicators:
                if self.device(text=indicator_text).exists(timeout=1):
                    print(f"  ✓ On edit profile screen (found '{indicator_text}')")
                    return True

            print("  ✗ Not on edit profile screen")
            return False

        except Exception as e:
            print(f"  Error checking screen: {e}")
            return False

    def _navigate_to_edit_profile(self):
        """
        Navigate to edit profile screen from profile page

        Returns:
            bool: True if successfully navigated
        """
        try:
            print("  Looking for 'Edit profile' button...")

            # Check if we're on profile page (has "Edit profile" button)
            edit_profile_selectors = [
                self.device(text="Edit profile"),
                self.device(textContains="Edit profile"),
                self.device(description="Edit profile"),
            ]

            for selector in edit_profile_selectors:
                if selector.exists(timeout=3):
                    print("  Found 'Edit profile' button, clicking...")
                    selector.click()
                    time.sleep(2)

                    # Verify we're now on edit profile screen
                    if self._is_on_edit_profile_screen():
                        print("  ✓ Successfully navigated to edit profile screen")
                        return True

            print("  ✗ Could not find 'Edit profile' button")
            return False

        except Exception as e:
            print(f"  Error navigating to edit profile: {e}")
            return False


def example_usage():
    """Example usage"""
    import uiautomator2 as u2

    print("="*70)
    print("SMART USERNAME CHANGER - EXAMPLE")
    print("="*70)

    # Connect to device
    device = u2.connect("10.1.10.36:5555")

    # Without AI (algorithmic fallback)
    changer = SmartUsernameChanger(device)

    result = changer.change_username_with_retry(
        target_username="chantall.paris",
        max_attempts=5
    )

    print(f"\n{'='*70}")
    print("RESULT:")
    print(f"  Success: {result['success']}")
    print(f"  Final Username: {result.get('final_username')}")
    print(f"  Attempts: {result['attempts']}")
    print(f"  Message: {result['message']}")
    print(f"{'='*70}")

    # With AI
    # changer_ai = SmartUsernameChanger(device, ai_api_key="your-key", ai_provider="openai")
    # result = changer_ai.change_username_with_retry(
    #     target_username="chantall.paris",
    #     mother_account="chantall.main",
    #     max_attempts=5
    # )


if __name__ == "__main__":
    example_usage()
