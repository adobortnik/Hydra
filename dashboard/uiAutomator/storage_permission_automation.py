"""
storage_permission_automation.py

Instagram Storage Permission Automation
Handles granting storage permissions to Instagram for uploading photos/videos

This is required before profile automation (changing profile pictures, posting content)

Author: Claude Code
Created: 2025-11-22
"""

import uiautomator2 as u2
import subprocess
import time
from pathlib import Path


class StoragePermissionAutomation:
    """
    Instagram Storage Permission Automation

    Grants storage permissions by:
    1. Opening Instagram
    2. Clicking the "+" (add content) button
    3. Handling native permission dialogs:
       - "Allow Instagram to access photos, media, and files?" → Allow
       - "Allow Instagram to take pictures and record video?" → While using the app

    Usage:
        automation = StoragePermissionAutomation(device_serial="10.1.10.183_5555")
        result = automation.grant_storage_permission(
            instagram_package="com.instagram.androim"
        )
    """

    def __init__(self, device_serial=None):
        """
        Initialize storage permission automation

        Args:
            device_serial: Device serial in format "10.1.10.183_5555" (optional)
        """
        self.device = None
        self.device_serial = device_serial

    def connect_device(self, device_serial=None):
        """
        Connect to device using the UIAutomator connection pattern

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

        # Kill existing UIAutomator processes
        print("Cleaning up existing UIAutomator processes...")
        try:
            subprocess.run(
                ['adb', '-s', connection_serial, 'shell', 'pkill', '-9', 'uiautomator'],
                capture_output=True, timeout=5
            )
            subprocess.run(
                ['adb', '-s', connection_serial, 'shell', 'am', 'force-stop', 'com.github.uiautomator'],
                capture_output=True, timeout=5
            )
            subprocess.run(
                ['adb', '-s', connection_serial, 'shell', 'pkill', '-9', '-f', 'androidx.test.runner'],
                capture_output=True, timeout=5
            )
            print("✓ Killed all UIAutomator-related processes")
            time.sleep(5)
        except Exception as e:
            print(f"⚠ Warning during cleanup: {e}")

        # Connect to device
        print("Connecting to device...")
        self.device = u2.connect(connection_serial)
        print(f"Connected (serial: {self.device.serial})")

        # Wait for UIAutomator to be responsive
        print("Waiting for UIAutomator to be responsive...")
        max_wait = 45
        start_time = time.time()

        while (time.time() - start_time) < max_wait:
            try:
                _ = self.device.info
                _ = self.device.window_size()
                elapsed = int(time.time() - start_time)
                print(f"✓ UIAutomator is responsive (took {elapsed}s)")
                break
            except Exception as e:
                elapsed = int(time.time() - start_time)
                if elapsed % 5 == 0:
                    print(f"Waiting... {elapsed}s / {max_wait}s")
                time.sleep(1)

        return self.device

    def open_instagram(self, instagram_package):
        """
        Open Instagram app

        Args:
            instagram_package: Package name (e.g., "com.instagram.androim")

        Returns:
            bool: True if opened successfully
        """
        print(f"\nOpening Instagram ({instagram_package})...")

        try:
            # Launch Instagram
            self.device.app_start(instagram_package)
            time.sleep(5)

            print("✓ Instagram opened")
            return True

        except Exception as e:
            print(f"✗ Error opening Instagram: {e}")
            return False

    def click_add_content_button(self):
        """
        Click the "+" (add content) button to trigger permission prompts

        Returns:
            bool: True if clicked successfully
        """
        print("\n" + "-"*70)
        print("CLICKING ADD CONTENT BUTTON (+)")
        print("-"*70)

        try:
            # Selectors for the "+" button
            add_button_selectors = [
                self.device(description="New post"),
                self.device(description="Create"),
                self.device(descriptionContains="New"),
                self.device(descriptionContains="Create"),
                self.device(descriptionContains="Add"),
                self.device(resourceId="com.instagram.android:id/tab_create"),
                # Icon-based selector (plus icon)
                self.device(className="android.widget.ImageView", descriptionContains="Create"),
            ]

            for i, selector in enumerate(add_button_selectors, 1):
                if selector.exists(timeout=3):
                    print(f"✓ Found add button (selector #{i})")
                    selector.click()
                    print("✓ Clicked add button")
                    time.sleep(3)
                    return True

            print("⚠ Could not find add button, trying coordinate-based click")

            # Fallback: Click center-bottom of screen (where + button usually is)
            w, h = self.device.window_size()
            # Bottom navigation bar is usually at the bottom, + is in the center
            x = w // 2
            y = int(h * 0.95)  # 95% down the screen

            print(f"Clicking at ({x}, {y})")
            self.device.click(x, y)
            time.sleep(3)

            return True

        except Exception as e:
            print(f"✗ Error clicking add button: {e}")
            return False

    def handle_storage_permission_dialogs(self):
        """
        Handle the two native permission dialogs:
        1. "Allow Instagram to access photos, media, and files?" → Allow
        2. "Allow Instagram to take pictures and record video?" → While using the app

        Returns:
            bool: True if handled successfully
        """
        print("\n" + "-"*70)
        print("HANDLING STORAGE PERMISSION DIALOGS")
        print("-"*70)

        try:
            # Dialog 1: Access photos, media, and files
            print("\nLooking for 'Access photos and media' dialog...")
            time.sleep(2)

            # Selectors for "Allow" button
            allow_selectors = [
                self.device(text="Allow"),
                self.device(textContains="Allow"),
                self.device(text="ALLOW"),
                self.device(resourceId="com.android.permissioncontroller:id/permission_allow_button"),
                self.device(resourceId="com.android.packageinstaller:id/permission_allow_button"),
            ]

            for i, selector in enumerate(allow_selectors, 1):
                if selector.exists(timeout=3):
                    print(f"✓ Found 'Allow' button (selector #{i})")
                    selector.click()
                    print("✓ Clicked 'Allow' for photos/media access")
                    time.sleep(2)
                    break

            # Dialog 2: Take pictures and record video
            print("\nLooking for 'Take pictures and record video' dialog...")
            time.sleep(2)

            # Selectors for "While using the app" button
            while_using_selectors = [
                self.device(text="While using the app"),
                self.device(textContains="While using"),
                self.device(text="WHILE USING THE APP"),
                self.device(resourceId="com.android.permissioncontroller:id/permission_allow_foreground_only_button"),
                self.device(resourceId="com.android.packageinstaller:id/permission_allow_foreground_only_button"),
            ]

            for i, selector in enumerate(while_using_selectors, 1):
                if selector.exists(timeout=3):
                    print(f"✓ Found 'While using the app' button (selector #{i})")
                    selector.click()
                    print("✓ Clicked 'While using the app' for camera access")
                    time.sleep(2)
                    break
            else:
                # If "While using the app" not found, try "Allow" again
                print("⚠ 'While using the app' not found, trying 'Allow'...")
                for selector in allow_selectors:
                    if selector.exists(timeout=2):
                        print("✓ Found 'Allow' button")
                        selector.click()
                        print("✓ Clicked 'Allow'")
                        time.sleep(2)
                        break

            print("✓ Storage permission dialogs handled")
            return True

        except Exception as e:
            print(f"⚠ Error handling permission dialogs: {e}")
            return True  # Continue anyway

    def dismiss_any_remaining_prompts(self):
        """
        Dismiss any remaining prompts or go back to main screen

        Returns:
            bool: True
        """
        print("\n" + "-"*70)
        print("DISMISSING REMAINING PROMPTS")
        print("-"*70)

        try:
            # Press back a few times to return to main screen
            for i in range(3):
                print(f"Pressing back ({i+1}/3)...")
                self.device.press("back")
                time.sleep(1)

            print("✓ Returned to main screen")
            return True

        except Exception as e:
            print(f"⚠ Error dismissing prompts: {e}")
            return True

    def grant_storage_permission(self, instagram_package):
        """
        Complete storage permission granting flow

        Args:
            instagram_package: Package name (e.g., "com.instagram.androim")

        Returns:
            dict: {
                'success': bool,
                'error': str or None
            }
        """
        print("\n" + "="*70)
        print("INSTAGRAM STORAGE PERMISSION AUTOMATION")
        print("="*70)
        print(f"Package: {instagram_package}")
        print("="*70)

        result = {
            'success': False,
            'error': None
        }

        try:
            # Open Instagram
            if not self.open_instagram(instagram_package):
                result['error'] = "Failed to open Instagram"
                return result

            # Click add content button
            if not self.click_add_content_button():
                result['error'] = "Failed to click add content button"
                return result

            # Handle permission dialogs
            self.handle_storage_permission_dialogs()

            # Dismiss remaining prompts
            self.dismiss_any_remaining_prompts()

            print("\n" + "="*70)
            print("✓ STORAGE PERMISSION GRANTED!")
            print("="*70)

            result['success'] = True
            return result

        except Exception as e:
            print(f"\n✗ Storage permission failed with exception: {e}")
            result['error'] = str(e)
            return result


if __name__ == '__main__':
    import sys

    print("="*70)
    print("INSTAGRAM STORAGE PERMISSION AUTOMATION - STANDALONE TEST")
    print("="*70)

    if len(sys.argv) < 2:
        print("\nUsage: python storage_permission_automation.py <DEVICE_SERIAL> [PACKAGE]")
        print("\nExample:")
        print("  python storage_permission_automation.py 10.1.10.183_5555")
        print("  python storage_permission_automation.py 10.1.10.183_5555 com.instagram.androim")
        sys.exit(1)

    device_serial = sys.argv[1]
    instagram_package = sys.argv[2] if len(sys.argv) > 2 else "com.instagram.android"

    # Create automation instance
    automation = StoragePermissionAutomation(device_serial)

    # Connect to device
    if not automation.connect_device():
        print("\n✗ Failed to connect to device")
        sys.exit(1)

    # Grant storage permission
    result = automation.grant_storage_permission(instagram_package)

    # Print result
    print("\n" + "="*70)
    print("RESULT")
    print("="*70)
    for key, value in result.items():
        print(f"{key}: {value}")

    sys.exit(0 if result['success'] else 1)
