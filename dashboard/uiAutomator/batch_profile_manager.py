#!/usr/bin/env python3
"""
Batch Profile Manager - Optimized for processing multiple tasks per device
Connects to device ONCE, processes ALL tasks for that device, then disconnects

Key improvements:
1. Groups tasks by device → reduces connection overhead
2. Keeps Instagram open between tasks → faster processing
3. Dismisses common Instagram modals automatically
4. Handles permissions and interruptions gracefully
"""

import uiautomator2 as u2
import time
import sys
import os
import subprocess
from pathlib import Path
from random import uniform
from collections import defaultdict

# Import our database module
from profile_automation_db import (
    init_database, get_pending_tasks, update_task_status,
    update_picture_usage, update_bio_template_usage,
    log_profile_change, update_device_account, get_device_account
)

# Import functions from original script
from instagram_automation import (
    connect_device, navigate_to_profile,
    navigate_to_edit_profile, save_profile_changes
)

# Import smart username changer
from smart_username_changer import SmartUsernameChanger


def human_sleep(min_sec=1.0, max_sec=3.0, log=True):
    """Sleep for random duration to mimic human behavior"""
    delay = uniform(min_sec, max_sec)
    if log:
        print(f"  Waiting {delay:.1f}s...")
    time.sleep(delay)


class BatchProfileManager:
    def __init__(self):
        self.device = None
        self.current_device_serial = None
        self.instagram_package = None
        self.instagram_is_open = False
        self.profile_pictures_dir = Path(__file__).parent / "profile_pictures"

    def dismiss_instagram_modals(self):
        """
        Dismiss common Instagram popup modals that interfere with automation

        Common modals:
        - "Add your avatar" / "Add profile photo" / "Create your avatar"
        - "Turn on notifications"
        - "Add phone number"
        - "Save your login info"
        - Various promotional popups

        Returns:
            int: Number of modals dismissed
        """
        print("Checking for Instagram modals/popups...")
        dismissed_count = 0

        # Common dismiss buttons (ordered by priority - most common first)
        dismiss_buttons = [
            "Not now",
            "Not Now",
            "NOT NOW",
            "Skip",
            "SKIP",
            "Cancel",
            "CANCEL",
            "Maybe Later",
            "Maybe later",
            "Dismiss",
            "Close",
            "No Thanks",
            "No thanks",
            "×",  # Close icon
            "Later",
            "LATER",
        ]

        # Try up to 5 times (some modals appear after dismissing others)
        for attempt in range(5):
            modal_found = False

            # SPECIAL CASE: Check for "Create your avatar" or "Add your avatar" modal specifically
            # This is the most common one that blocks edit profile screen
            try:
                xml_dump = self.device.dump_hierarchy()
                if any(keyword in xml_dump.lower() for keyword in ['avatar', 'profile photo', 'profile picture']):
                    print(f"  Detected avatar/profile photo modal in screen hierarchy")
                    # Try to dismiss it aggressively
                    for dismiss_text in ["Not now", "Skip", "Cancel", "Maybe Later", "Later"]:
                        if self.device(text=dismiss_text).exists(timeout=0.3):
                            print(f"  Clicking '{dismiss_text}' on avatar modal...")
                            self.device(text=dismiss_text).click()
                            dismissed_count += 1
                            modal_found = True
                            human_sleep(0.8, 1.2, log=False)
                            break
                        elif self.device(textContains=dismiss_text).exists(timeout=0.3):
                            print(f"  Clicking button containing '{dismiss_text}'...")
                            self.device(textContains=dismiss_text).click()
                            dismissed_count += 1
                            modal_found = True
                            human_sleep(0.8, 1.2, log=False)
                            break

                    if modal_found:
                        continue  # Check again for more modals
            except Exception as e:
                pass

            # Try exact text-based dismiss buttons
            if not modal_found:
                for button_text in dismiss_buttons:
                    try:
                        button = self.device(text=button_text)
                        if button.exists(timeout=0.3):
                            print(f"  Found modal with '{button_text}' button, dismissing...")
                            button.click()
                            dismissed_count += 1
                            modal_found = True
                            human_sleep(0.5, 1.0, log=False)
                            break
                    except Exception as e:
                        pass

            # Try text contains (for variations like "Not now" vs "Not Now")
            if not modal_found:
                for button_text in ["Not now", "Skip", "Cancel", "Later"]:
                    try:
                        button = self.device(textContains=button_text)
                        if button.exists(timeout=0.3):
                            print(f"  Found modal with button containing '{button_text}', dismissing...")
                            button.click()
                            dismissed_count += 1
                            modal_found = True
                            human_sleep(0.5, 1.0, log=False)
                            break
                    except Exception as e:
                        pass

            # Try description-based (for icon buttons)
            if not modal_found:
                for button_text in dismiss_buttons:
                    try:
                        button = self.device(description=button_text)
                        if button.exists(timeout=0.3):
                            print(f"  Found modal with '{button_text}' icon, dismissing...")
                            button.click()
                            dismissed_count += 1
                            modal_found = True
                            human_sleep(0.5, 1.0, log=False)
                            break
                    except Exception as e:
                        pass

            # LAST RESORT: Try clicking on any clickable element with "Not now" or similar
            # This catches cases where the button has different attributes
            if not modal_found:
                try:
                    for text in ["Not now", "Skip", "Cancel"]:
                        elements = self.device(textMatches=f"(?i).*{text}.*", clickable=True)
                        if elements.exists(timeout=0.3):
                            print(f"  Found clickable element matching '{text}' (regex), clicking...")
                            elements.click()
                            dismissed_count += 1
                            modal_found = True
                            human_sleep(0.5, 1.0, log=False)
                            break
                except Exception as e:
                    pass

            # If no more modals found, we're done
            if not modal_found:
                break

        if dismissed_count > 0:
            print(f"  ✓ Dismissed {dismissed_count} modal(s)")
        else:
            print("  No modals found")

        return dismissed_count

    def check_and_handle_permissions(self):
        """
        Check if Instagram is requesting storage or other permissions

        Returns:
            bool: True if permission was handled, False if no permission dialog
        """
        print("Checking for permission dialogs...")

        # Common permission dialogs
        permission_keywords = [
            "allow",
            "permit",
            "access",
            "photos",
            "media",
            "storage",
        ]

        # Look for Android permission dialog
        for keyword in permission_keywords:
            try:
                # Check for text containing keyword
                if self.device(textContains=keyword).exists(timeout=0.5):
                    # Look for "Allow" button
                    allow_buttons = [
                        self.device(text="Allow"),
                        self.device(text="ALLOW"),
                        self.device(textContains="Allow"),
                    ]

                    for button in allow_buttons:
                        if button.exists(timeout=0.5):
                            print(f"  Permission dialog detected, clicking 'Allow'...")
                            button.click()
                            human_sleep(1.0, 1.5, log=False)
                            return True
            except Exception as e:
                pass

        print("  No permission dialogs found")
        return False

    def ensure_instagram_open(self, instagram_package):
        """
        Ensure Instagram is open and ready
        - If not open, open it
        - If already open, just verify it's running
        - Dismiss any modals

        Args:
            instagram_package: Instagram package name

        Returns:
            bool: Success status
        """
        try:
            # Check if Instagram is already the current app
            current_app = self.device.app_current()

            if current_app.get('package') == instagram_package and self.instagram_is_open:
                print(f"Instagram already open ({instagram_package})")

                # Still check for modals (they can appear anytime)
                self.dismiss_instagram_modals()
                self.check_and_handle_permissions()
                return True

            # Instagram not current app - need to open it
            print(f"Opening Instagram: {instagram_package}")

            # Method 1: Try to bring to foreground if already running
            try:
                self.device.app_start(instagram_package)
                human_sleep(2, 3)
            except:
                # Method 2: Force start if foreground failed
                print("  App not running, starting fresh...")
                self.device.app_start(
                    instagram_package,
                    activity='.activity.MainTabActivity',
                    stop=False  # Don't force stop first
                )
                human_sleep(3, 4)

            # Dismiss any modals that appear on startup
            self.dismiss_instagram_modals()
            self.check_and_handle_permissions()

            self.instagram_is_open = True
            self.instagram_package = instagram_package
            return True

        except Exception as e:
            print(f"Error ensuring Instagram is open: {e}")
            return False

    def navigate_to_edit_profile_safe(self):
        """
        Navigate to edit profile screen with multiple retry strategies

        Returns:
            bool: True if on edit profile screen
        """
        print("Navigating to edit profile screen...")

        # First dismiss any modals
        self.dismiss_instagram_modals()

        # Try to navigate to profile tab first (if not already there)
        try:
            if not self._is_on_profile_tab():
                print("  Not on profile tab, navigating there first...")
                navigate_to_profile(self.device)
                human_sleep(1.5, 2.5)
                self.dismiss_instagram_modals()
        except Exception as e:
            print(f"  Warning during profile navigation: {e}")

        # Now try to click edit profile button
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            print(f"  Attempt {attempt}/{max_attempts} to reach edit profile screen...")

            # Check if already on edit profile screen
            if self._is_on_edit_profile_screen():
                print("  ✓ Already on edit profile screen")
                return True

            # Try to click edit profile button
            if navigate_to_edit_profile(self.device):
                human_sleep(1.5, 2.5)

                # Dismiss any modals that appear
                self.dismiss_instagram_modals()

                # Verify we're on edit profile screen
                if self._is_on_edit_profile_screen():
                    print("  ✓ Successfully navigated to edit profile screen")
                    return True

            # Not there yet, wait and try again
            human_sleep(1, 2)

        print("  ✗ Failed to reach edit profile screen after multiple attempts")
        return False

    def _is_on_profile_tab(self):
        """Check if we're on the profile tab"""
        indicators = [
            self.device(text="Edit profile").exists(timeout=1),
            self.device(description="Profile").exists(timeout=1),
        ]
        return any(indicators)

    def _is_on_edit_profile_screen(self):
        """Check if we're on the edit profile screen"""
        indicators = [
            ("Name", "text"),
            ("Bio", "text"),
            ("Website", "text"),
            ("Username", "text")
        ]

        for indicator_text, selector_type in indicators:
            if self.device(text=indicator_text).exists(timeout=1):
                return True
        return False

    def detect_challenge_screen(self):
        """
        Detect if Instagram is showing a challenge/verification screen
        Uses fast XML dump parsing

        Returns:
            dict: {'is_challenge': bool, 'challenge_type': str or None, 'text': str or None}
        """
        try:
            # Get screen XML dump once (FAST)
            try:
                xml_dump = self.device.dump_hierarchy()
            except:
                return {'is_challenge': False, 'challenge_type': None, 'text': None}

            xml_lower = xml_dump.lower()

            challenge_keywords = [
                ("confirm", "verification"),
                ("verify", "verification"),
                ("security check", "security"),
                ("unusual activity", "suspicious_activity"),
                ("suspicious login", "suspicious_login"),
                ("confirmation code", "code_verification"),
                ("enter the code", "code_verification"),
                ("automated behavior", "automation_detected"),
                ("try again later", "rate_limit"),
            ]

            for keyword, challenge_type in challenge_keywords:
                if keyword in xml_lower:
                    print(f"⚠ CHALLENGE DETECTED: {challenge_type}")
                    print(f"   Keyword found: '{keyword}'")
                    return {'is_challenge': True, 'challenge_type': challenge_type, 'text': keyword}

            return {'is_challenge': False, 'challenge_type': None, 'text': None}

        except Exception as e:
            return {'is_challenge': False, 'challenge_type': None, 'text': None}

    def transfer_image_to_device(self, image_path, device_serial):
        """Transfer image file to device's Camera directory"""
        try:
            adb_serial = device_serial.replace('_', ':')
            timestamp = int(time.time())
            filename = f"profile_pic_{timestamp}.jpg"
            device_path = f"/sdcard/DCIM/Camera/{filename}"

            print(f"Transferring image: {device_path}")

            subprocess.run(
                ['adb', '-s', adb_serial, 'push', str(image_path), device_path],
                capture_output=True,
                text=True,
                check=True
            )

            # Triple media scan
            subprocess.run(
                ['adb', '-s', adb_serial, 'shell', 'am', 'broadcast',
                 '-a', 'android.intent.action.MEDIA_SCANNER_SCAN_FILE',
                 '-d', f'file://{device_path}'],
                capture_output=True
            )

            human_sleep(3, 4, log=False)

            print(f"✓ Image transferred: {device_path}")
            return device_path

        except Exception as e:
            print(f"Failed to transfer image: {e}")
            return None

    def change_profile_picture_automated(self, image_path_on_device):
        """Change profile picture (imports from automated_profile_manager.py)"""
        from automated_profile_manager import AutomatedProfileManager
        temp_manager = AutomatedProfileManager()
        temp_manager.device = self.device
        return temp_manager.change_profile_picture_automated(self.device, image_path_on_device)

    def edit_bio_automated(self, new_bio):
        """Edit bio (imports from automated_profile_manager.py)"""
        from automated_profile_manager import AutomatedProfileManager
        temp_manager = AutomatedProfileManager()
        temp_manager.device = self.device
        return temp_manager.edit_bio_automated(self.device, new_bio)

    def process_single_task(self, task):
        """
        Process a single task
        Assumes device is already connected and Instagram is open

        Args:
            task: Task dictionary from database

        Returns:
            bool: Success status
        """
        task_id = task['id']
        device_serial = task['device_serial']
        instagram_package = task['instagram_package']

        print(f"\n{'='*70}")
        print(f"Processing Task ID: {task_id}")
        print(f"Username: {task.get('username', 'N/A')} → {task.get('new_username', 'N/A')}")
        print(f"{'='*70}\n")

        update_task_status(task_id, 'in_progress')

        try:
            # Ensure Instagram is open (fast if already open)
            if not self.ensure_instagram_open(instagram_package):
                raise Exception("Failed to ensure Instagram is open")

            # Check for challenge screens
            challenge = self.detect_challenge_screen()
            if challenge['is_challenge']:
                error_msg = f"Account requires verification: {challenge['challenge_type']}"
                print(f"\n❌ SKIPPING: {error_msg}")
                update_task_status(task_id, 'failed', error_msg)
                return False

            # Navigate to edit profile screen
            if not self.navigate_to_edit_profile_safe():
                raise Exception("Failed to navigate to edit profile screen")

            human_sleep(1, 2)

            # Track changes
            changes_made = []

            # Change profile picture if specified
            if task['profile_picture_id'] and task['original_path']:
                print(f"\n--- Changing Profile Picture (ID: {task['profile_picture_id']}) ---")

                if os.path.exists(task['original_path']):
                    device_image_path = self.transfer_image_to_device(
                        task['original_path'],
                        device_serial
                    )

                    if device_image_path:
                        # Dismiss modals before changing picture
                        self.dismiss_instagram_modals()
                        self.check_and_handle_permissions()

                        if self.change_profile_picture_automated(device_image_path):
                            print("✓ Profile picture changed")
                            update_picture_usage(task['profile_picture_id'])
                            changes_made.append("profile_picture")

                            log_profile_change(
                                device_serial, instagram_package, task.get('username', 'unknown'),
                                'profile_picture', None, task['filename'], success=True
                            )

                            # IMPORTANT: After changing profile picture, Instagram may be uploading
                            # Wait for upload to complete before continuing
                            print("Waiting for profile picture upload to complete...")
                            human_sleep(3, 5)
                        else:
                            print("⚠ Profile picture change failed")
                else:
                    print(f"⚠ Image file not found: {task['original_path']}")

                # After profile picture change, navigate back to edit profile screen
                print("Navigating back to edit profile screen after picture change...")
                if not self.navigate_to_edit_profile_safe():
                    print("⚠ Warning: Could not navigate back to edit profile screen")

                human_sleep(1, 1.5)

            # Change username if specified
            if task['new_username']:
                print(f"\n--- Changing Username to: {task['new_username']} ---")

                # Ensure we're still on edit profile screen
                if not self._is_on_edit_profile_screen():
                    print("Not on edit profile screen, navigating back...")
                    if not self.navigate_to_edit_profile_safe():
                        raise Exception("Lost edit profile screen during username change")

                smart_changer = SmartUsernameChanger(
                    device=self.device,
                    ai_api_key=task.get('ai_api_key'),
                    ai_provider=task.get('ai_provider', 'openai'),
                    device_serial=device_serial,  # Pass for database sync
                    old_username=task.get('username')  # Pass current username
                )

                result = smart_changer.change_username_with_retry(
                    target_username=task['new_username'],
                    mother_account=task.get('mother_account'),
                    max_attempts=5
                )

                if result['success']:
                    final_username = result['final_username']
                    print(f"✓ Username changed to: {final_username} (took {result['attempts']} attempt(s))")
                    changes_made.append("username")

                    log_profile_change(
                        device_serial, instagram_package, task.get('username', 'unknown'),
                        'username', task.get('username'), final_username, success=True
                    )

                    # Navigate back to edit profile
                    self.device.press("back")
                    human_sleep(1.5, 2.5)
                else:
                    print(f"⚠ Username change failed: {result.get('error', 'Unknown')}")
                    log_profile_change(
                        device_serial, instagram_package, task.get('username', 'unknown'),
                        'username', task.get('username'), task['new_username'], success=False
                    )

            # Change bio if specified
            if task['new_bio']:
                print(f"\n--- Changing Bio ---")

                # Ensure we're on edit profile screen
                if not self._is_on_edit_profile_screen():
                    print("Not on edit profile screen, navigating back...")
                    if not self.navigate_to_edit_profile_safe():
                        raise Exception("Lost edit profile screen during bio change")

                if self.edit_bio_automated(task['new_bio']):
                    print("✓ Bio changed")
                    changes_made.append("bio")

                    log_profile_change(
                        device_serial, instagram_package, task.get('username', 'unknown'),
                        'bio', None, task['new_bio'], success=True
                    )
                else:
                    print("⚠ Bio change failed")

                human_sleep(1, 1.5)

            # Save all changes
            print("\n--- Saving Profile Changes ---")
            save_profile_changes(self.device)
            human_sleep(2, 3)

            # Update device account record
            update_device_account(
                device_serial,
                username=task.get('new_username') or task.get('username'),
                bio=task.get('new_bio'),
                profile_picture_id=task.get('profile_picture_id'),
                instagram_package=instagram_package
            )

            # Mark task as completed
            update_task_status(task_id, 'completed')

            print(f"\n{'='*70}")
            print(f"Task ID {task_id} completed successfully!")
            print(f"Changes made: {', '.join(changes_made) if changes_made else 'None'}")
            print(f"{'='*70}\n")

            # Close Instagram app to return to home screen
            print("Closing Instagram app...")
            try:
                self.device.app_stop(instagram_package)
                self.instagram_is_open = False
                print("✓ Instagram closed - device on home screen")
                human_sleep(1, 2)
            except Exception as e:
                print(f"⚠ Warning: Could not close Instagram: {e}")

            return True

        except Exception as e:
            error_msg = str(e)
            print(f"\n✗ Error processing task {task_id}: {error_msg}")
            update_task_status(task_id, 'failed', error_msg)
            return False

    def process_tasks_for_device(self, device_serial, tasks):
        """
        Process all tasks for a specific device
        Connects once, processes all tasks, then disconnects

        Args:
            device_serial: Device serial number
            tasks: List of tasks for this device

        Returns:
            dict: {'successful': int, 'failed': int}
        """
        print(f"\n{'#'*70}")
        print(f"# DEVICE: {device_serial}")
        print(f"# Tasks to process: {len(tasks)}")
        print(f"{'#'*70}\n")

        successful = 0
        failed = 0

        try:
            # Connect to device ONCE
            print(f"Connecting to device: {device_serial}")
            self.device = connect_device(device_serial=device_serial)

            if not self.device:
                raise Exception(f"Failed to connect to device: {device_serial}")

            self.current_device_serial = device_serial
            print(f"✓ Connected to device: {device_serial}")
            human_sleep(1, 1.5)

            # Process each task for this device
            for i, task in enumerate(tasks, 1):
                print(f"\n\n{'─'*70}")
                print(f"Task {i}/{len(tasks)} for device {device_serial}")
                print(f"{'─'*70}")

                if self.process_single_task(task):
                    successful += 1
                else:
                    failed += 1

                # Wait between tasks (but not after last one)
                if i < len(tasks):
                    wait_time = uniform(3, 6)
                    print(f"\nWaiting {wait_time:.1f}s before next task...")
                    time.sleep(wait_time)

        except Exception as e:
            print(f"\n✗ Error with device {device_serial}: {e}")
            # Mark all remaining tasks as failed
            for task in tasks:
                if task['status'] == 'pending':
                    update_task_status(task['id'], 'failed', f'Device error: {e}')
                    failed += 1

        finally:
            # Clean up
            self.device = None
            self.current_device_serial = None
            self.instagram_is_open = False
            self.instagram_package = None

        return {'successful': successful, 'failed': failed}

    def run_batch_processor(self, max_tasks=None):
        """
        Process all pending tasks, grouped by device

        Key optimization: Processes all tasks for each device before moving to next device

        Args:
            max_tasks: Maximum total tasks to process (None = all)
        """
        print("\n" + "="*70)
        print("BATCH PROFILE MANAGER - OPTIMIZED PROCESSOR")
        print("="*70)

        # Get pending tasks
        pending_tasks = get_pending_tasks()

        if not pending_tasks:
            print("\nNo pending tasks found.")
            return

        print(f"\nFound {len(pending_tasks)} pending task(s)")

        if max_tasks:
            pending_tasks = pending_tasks[:max_tasks]
            print(f"Processing first {max_tasks} task(s)")

        # Group tasks by device
        tasks_by_device = defaultdict(list)
        for task in pending_tasks:
            tasks_by_device[task['device_serial']].append(task)

        print(f"\nTasks grouped across {len(tasks_by_device)} device(s):")
        for device, tasks in tasks_by_device.items():
            print(f"  - {device}: {len(tasks)} task(s)")

        # Process each device's tasks
        total_successful = 0
        total_failed = 0

        for device_index, (device_serial, device_tasks) in enumerate(tasks_by_device.items(), 1):
            print(f"\n\n{'█'*70}")
            print(f"█ DEVICE {device_index}/{len(tasks_by_device)}: {device_serial}")
            print(f"{'█'*70}\n")

            results = self.process_tasks_for_device(device_serial, device_tasks)
            total_successful += results['successful']
            total_failed += results['failed']

            # Wait between devices (but not after last one)
            if device_index < len(tasks_by_device):
                wait_time = uniform(5, 8)
                print(f"\n\nWaiting {wait_time:.1f}s before next device...")
                time.sleep(wait_time)

        # Final summary
        print(f"\n\n{'='*70}")
        print("BATCH PROCESSING COMPLETE")
        print(f"{'='*70}")
        print(f"Devices processed: {len(tasks_by_device)}")
        print(f"Successful tasks: {total_successful}")
        print(f"Failed tasks: {total_failed}")
        print(f"Total tasks: {len(pending_tasks)}")
        print(f"{'='*70}\n")


def main():
    """Main entry point"""
    init_database()

    manager = BatchProfileManager()
    manager.run_batch_processor()


if __name__ == "__main__":
    main()
