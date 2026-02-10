#!/usr/bin/env python3
"""
Automated Instagram Profile Manager
Handles batch profile updates using database-driven task queue
"""

import uiautomator2 as u2
import time
import sys
import os
import subprocess
import shutil
from pathlib import Path
import random
import sqlite3

# Import our database module
from profile_automation_db import (
    init_database, get_pending_tasks, update_task_status,
    update_picture_usage, update_bio_template_usage,
    log_profile_change, update_device_account, get_device_account
)

# Import functions from original script
from instagram_automation import (
    connect_device, open_instagram, navigate_to_profile,
    navigate_to_edit_profile, save_profile_changes, disconnect_device
)

# Import smart username changer
from smart_username_changer import SmartUsernameChanger


def sync_username_with_onimator(device_serial, old_username, new_username):
    """
    Sync Instagram username change with Onimator system

    Updates:
    1. accounts.db - Master account registry (accounts.account field)
    2. stats.db - Account statistics tracking (stats.account field)
    3. Folder name - Rename account folder from old to new username

    Args:
        device_serial: Device serial (e.g., "10.1.10.192_5555")
        old_username: Current Instagram username (before change)
        new_username: New Instagram username (after change)

    Returns:
        dict: {'success': bool, 'updates': list, 'errors': list}
    """
    print(f"\n{'='*70}")
    print(f"SYNCING USERNAME CHANGE WITH ONIMATOR")
    print(f"Device: {device_serial}")
    print(f"Old Username: {old_username}")
    print(f"New Username: {new_username}")
    print(f"{'='*70}\n")

    updates = []
    errors = []

    # Get base path (uiAutomator is now inside dashboard, so 2 levels up)
    base_path = Path(__file__).parent.parent.parent
    device_folder = base_path / device_serial

    if not device_folder.exists():
        error = f"Device folder not found: {device_folder}"
        print(f"❌ {error}")
        errors.append(error)
        return {'success': False, 'updates': updates, 'errors': errors}

    # 1. Update accounts.db (device root)
    accounts_db_path = device_folder / "accounts.db"
    if accounts_db_path.exists():
        try:
            conn = sqlite3.connect(str(accounts_db_path))
            cursor = conn.cursor()

            # Check if account exists
            cursor.execute("SELECT account FROM accounts WHERE account = ?", (old_username,))
            if cursor.fetchone():
                # Update username
                cursor.execute("UPDATE accounts SET account = ? WHERE account = ?",
                             (new_username, old_username))
                conn.commit()
                updates.append(f"✓ Updated accounts.db (account: {old_username} → {new_username})")
                print(updates[-1])
            else:
                msg = f"⚠ Account '{old_username}' not found in accounts.db, skipping"
                print(msg)
                updates.append(msg)

            conn.close()
        except Exception as e:
            error = f"Failed to update accounts.db: {e}"
            print(f"❌ {error}")
            errors.append(error)
    else:
        msg = f"⚠ accounts.db not found at {accounts_db_path}, skipping"
        print(msg)
        updates.append(msg)

    # 2. Update stats.db (account folder)
    old_account_folder = device_folder / old_username
    if old_account_folder.exists():
        stats_db_path = old_account_folder / "stats.db"
        if stats_db_path.exists():
            try:
                conn = sqlite3.connect(str(stats_db_path))
                cursor = conn.cursor()

                # Update all stats entries for this account
                cursor.execute("UPDATE stats SET account = ? WHERE account = ?",
                             (new_username, old_username))
                rows_affected = cursor.rowcount
                conn.commit()
                conn.close()

                updates.append(f"✓ Updated stats.db ({rows_affected} row(s): {old_username} → {new_username})")
                print(updates[-1])
            except Exception as e:
                error = f"Failed to update stats.db: {e}"
                print(f"❌ {error}")
                errors.append(error)
        else:
            msg = f"⚠ stats.db not found in account folder, skipping"
            print(msg)
            updates.append(msg)
    else:
        error = f"Account folder not found: {old_account_folder}"
        print(f"❌ {error}")
        errors.append(error)
        return {'success': False, 'updates': updates, 'errors': errors}

    # 3. Rename account folder
    new_account_folder = device_folder / new_username
    if new_account_folder.exists():
        error = f"Cannot rename folder: {new_username} already exists!"
        print(f"❌ {error}")
        errors.append(error)
        return {'success': False, 'updates': updates, 'errors': errors}

    try:
        old_account_folder.rename(new_account_folder)
        updates.append(f"✓ Renamed folder: {old_username}/ → {new_username}/")
        print(updates[-1])
    except Exception as e:
        error = f"Failed to rename folder: {e}"
        print(f"❌ {error}")
        errors.append(error)
        return {'success': False, 'updates': updates, 'errors': errors}

    # Success
    print(f"\n{'='*70}")
    print(f"✅ ONIMATOR SYNC COMPLETE")
    print(f"Total updates: {len(updates)}")
    if errors:
        print(f"Errors: {len(errors)}")
    print(f"{'='*70}\n")

    return {
        'success': len(errors) == 0,
        'updates': updates,
        'errors': errors
    }


class AutomatedProfileManager:
    def __init__(self):
        self.device = None
        self.current_task = None
        self.profile_pictures_dir = Path(__file__).parent / "profile_pictures"

    def ensure_on_edit_profile_screen(self):
        """
        Verify we're on edit profile screen, if not navigate to it

        Returns:
            bool: True if on edit profile screen, False if failed
        """
        try:
            print("Checking if we're on edit profile screen...")

            # Check for edit profile indicators
            edit_profile_indicators = [
                ("Name", "text"),
                ("Bio", "text"),
                ("Website", "text"),
                ("Username", "text")
            ]

            for indicator_text, selector_type in edit_profile_indicators:
                if self.device(text=indicator_text).exists(timeout=2):
                    print(f"✓ On edit profile screen (found '{indicator_text}')")
                    return True

            # Not on edit profile screen - try to navigate
            print("Not on edit profile screen, attempting to navigate...")

            # Check if we're on profile page (has "Edit profile" button)
            if self.device(text="Edit profile").exists(timeout=3):
                print("Found 'Edit profile' button, clicking it...")
                self.device(text="Edit profile").click()
                time.sleep(2)
                return True

            # Try other variations
            edit_profile_selectors = [
                self.device(textContains="Edit profile"),
                self.device(description="Edit profile"),
            ]

            for selector in edit_profile_selectors:
                if selector.exists(timeout=2):
                    print("Found edit profile button, clicking...")
                    selector.click()
                    time.sleep(2)
                    return True

            print("Could not find edit profile button")
            return False

        except Exception as e:
            print(f"Error ensuring edit profile screen: {e}")
            return False

    def detect_challenge_screen(self):
        """
        Detect if Instagram is showing a challenge/verification screen
        OPTIMIZED: Uses fast XML dump parsing instead of multiple slow selector checks

        Returns:
            dict: {'is_challenge': bool, 'challenge_type': str or None, 'text': str or None}
        """
        try:
            print("Checking for challenge/verification screens...")

            # Get screen XML dump once (FAST - only one call)
            try:
                xml_dump = self.device.dump_hierarchy()
            except:
                # Fallback to slower method if dump fails
                return self._detect_challenge_fallback()

            # Convert to lowercase for faster case-insensitive matching
            xml_lower = xml_dump.lower()

            # Challenge keywords and their types (ordered by likelihood)
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
                ("send code", "code_verification"),
                ("get code", "code_verification"),
            ]

            # Check all keywords in one pass (VERY FAST)
            for keyword, challenge_type in challenge_keywords:
                if keyword in xml_lower:
                    print(f"⚠ CHALLENGE DETECTED: {challenge_type}")
                    print(f"   Keyword found: '{keyword}'")
                    return {'is_challenge': True, 'challenge_type': challenge_type, 'text': keyword}

            # No challenge detected
            print("✓ No challenge screen detected")
            return {'is_challenge': False, 'challenge_type': None, 'text': None}

        except Exception as e:
            print(f"Warning checking for challenges: {e}")
            return {'is_challenge': False, 'challenge_type': None, 'text': None}

    def _detect_challenge_fallback(self):
        """Fallback method using slower selector-based detection"""
        print("  Using fallback detection method...")

        # Quick check for most common indicators only (reduced timeout)
        quick_indicators = [
            "Confirm",
            "Verify",
            "Security",
            "Try Again Later"
        ]

        for text in quick_indicators:
            if self.device(textContains=text).exists(timeout=0.5):
                print(f"⚠ CHALLENGE DETECTED: verification")
                print(f"   Text found: '{text}'")
                return {'is_challenge': True, 'challenge_type': 'verification', 'text': text}

        return {'is_challenge': False, 'challenge_type': None, 'text': None}

    def dismiss_instagram_modals(self):
        """
        Dismiss common Instagram popup modals that interfere with automation
        Especially handles "Create your avatar" modal on edit profile screen

        Returns:
            int: Number of modals dismissed
        """
        try:
            print("Checking for Instagram modals/popups...")
            dismissed_count = 0

            # Try up to 5 times
            for attempt in range(5):
                modal_found = False

                # SPECIAL CASE: Check for avatar/profile photo modal
                try:
                    xml_dump = self.device.dump_hierarchy()
                    if any(keyword in xml_dump.lower() for keyword in ['avatar', 'profile photo', 'profile picture', 'create your']):
                        print(f"  Detected avatar/profile photo modal")
                        # Try to dismiss it
                        for dismiss_text in ["Not now", "Skip", "Cancel", "Maybe Later", "Later"]:
                            if self.device(text=dismiss_text).exists(timeout=0.3):
                                print(f"  Clicking '{dismiss_text}' on modal...")
                                self.device(text=dismiss_text).click()
                                dismissed_count += 1
                                modal_found = True
                                time.sleep(1)
                                break
                            elif self.device(textContains=dismiss_text).exists(timeout=0.3):
                                print(f"  Clicking button containing '{dismiss_text}'...")
                                self.device(textContains=dismiss_text).click()
                                dismissed_count += 1
                                modal_found = True
                                time.sleep(1)
                                break
                        if modal_found:
                            continue
                except Exception as e:
                    pass

                # Try common dismiss buttons
                dismiss_buttons = ["Not now", "Skip", "Cancel", "Maybe Later", "Later", "Dismiss", "Close"]
                for button_text in dismiss_buttons:
                    try:
                        if self.device(text=button_text).exists(timeout=0.3):
                            print(f"  Found modal with '{button_text}' button, dismissing...")
                            self.device(text=button_text).click()
                            dismissed_count += 1
                            modal_found = True
                            time.sleep(1)
                            break
                    except Exception as e:
                        pass

                if not modal_found:
                    break

            if dismissed_count > 0:
                print(f"  ✓ Dismissed {dismissed_count} modal(s)")
            else:
                print("  No modals found")

            return dismissed_count

        except Exception as e:
            print(f"Error dismissing modals: {e}")
            return 0

    def transfer_image_to_device(self, image_path, device_serial):
        """
        Transfer image file to device's Pictures directory

        Args:
            image_path: Local path to image file
            device_serial: Device serial number (with underscore format)

        Returns:
            str: Path to image on device, or None if failed
        """
        try:
            # Convert device serial format for ADB (underscore to colon)
            # Database uses: 10.1.10.183_5555
            # ADB needs: 10.1.10.183:5555
            adb_serial = device_serial.replace('_', ':')

            # Generate unique filename to avoid conflicts
            timestamp = int(time.time())
            filename = f"profile_pic_{timestamp}.jpg"
            device_path = f"/sdcard/DCIM/Camera/{filename}"

            print(f"Transferring image to device: {device_path}")

            # Use ADB to push file to device
            result = subprocess.run(
                ['adb', '-s', adb_serial, 'push', str(image_path), device_path],
                capture_output=True,
                text=True,
                check=True
            )

            print(f"Image transferred successfully: {device_path}")

            # Trigger media scan so gallery apps can see the file
            # Method 1: Broadcast scan for specific file
            print("Triggering media scanner...")
            subprocess.run(
                ['adb', '-s', adb_serial, 'shell', 'am', 'broadcast',
                 '-a', 'android.intent.action.MEDIA_SCANNER_SCAN_FILE',
                 '-d', f'file://{device_path}'],
                capture_output=True
            )

            # Method 2: Also trigger full media rescan (more reliable)
            subprocess.run(
                ['adb', '-s', adb_serial, 'shell', 'am', 'broadcast',
                 '-a', 'android.intent.action.MEDIA_MOUNTED',
                 '-d', 'file:///sdcard'],
                capture_output=True
            )

            # Method 3: Use media scanner service directly
            subprocess.run(
                ['adb', '-s', adb_serial, 'shell',
                 f'am startservice -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{device_path}'],
                capture_output=True
            )

            print("Waiting for media scanner to process...")
            time.sleep(5)  # Increased wait time for media scanner

            # Verify file exists on device
            verify_result = subprocess.run(
                ['adb', '-s', adb_serial, 'shell', f'ls -la {device_path}'],
                capture_output=True,
                text=True
            )
            if device_path in verify_result.stdout:
                print(f"✓ Verified: Image exists on device at {device_path}")
            else:
                print(f"⚠ Warning: Could not verify image on device")

            return device_path

        except subprocess.CalledProcessError as e:
            print(f"Failed to transfer image: {e}")
            print(f"Error output: {e.stderr}")
            return None
        except Exception as e:
            print(f"Unexpected error transferring image: {e}")
            return None

    def change_profile_picture_automated(self, device, image_path_on_device):
        """
        Fully automated profile picture change

        Args:
            device: uiautomator2 device object
            image_path_on_device: Path to image on device storage

        Returns:
            bool: Success status
        """
        try:
            print("Starting automated profile picture change...")

            # Look for "Edit picture or avatar" button or similar
            picture_selectors = [
                device(text="Edit picture or avatar"),
                device(text="Edit picture"),
                device(text="Change profile photo"),
                device(text="Change Profile Photo"),
                device(description="Edit picture or avatar"),
                device(description="Change profile photo"),
                device(textContains="Edit picture"),
                device(textContains="avatar"),
            ]

            picture_clicked = False
            for selector in picture_selectors:
                if selector.exists(timeout=5):
                    selector.click()
                    print(f"Clicked: {selector.info.get('text', 'profile picture element')}")
                    picture_clicked = True
                    break

            if not picture_clicked:
                # Try clicking the top area where profile picture usually is
                print("Trying to find profile picture element by position...")
                screen_width = device.info['displayWidth']
                device.click(screen_width * 0.5, 250)
                print("Clicked profile picture area")

            time.sleep(2)

            # Look for "New profile picture" or gallery option with enhanced selectors
            # Common options in the 3-button modal: "Choose from library", "Import from Facebook", "Take photo"
            gallery_selectors = [
                ("New profile picture", "text"),
                ("Choose from library", "text"),
                ("Choose from Library", "text"),
                ("Select from gallery", "text"),
                ("Select from Gallery", "text"),
                ("library", "textContains"),
                ("gallery", "textContains"),
            ]

            gallery_clicked = False
            for selector_text, selector_type in gallery_selectors:
                if selector_type == "text":
                    selector = device(text=selector_text)
                else:  # textContains
                    selector = device(textContains=selector_text)

                if selector.exists(timeout=3):
                    selector.click()
                    print(f"✓ Selected: {selector_text}")
                    gallery_clicked = True
                    break

            if not gallery_clicked:
                print("⚠ Could not find gallery option with text selectors, trying coordinate fallback...")
                # Fallback: Click on the first option in the modal (usually "Choose from library")
                # The modal typically appears in the center/lower part of screen
                screen_width = device.info['displayWidth']
                screen_height = device.info['displayHeight']
                device.click(screen_width * 0.5, screen_height * 0.45)
                print("✓ Clicked first option in modal (coordinate fallback)")
                gallery_clicked = True

            time.sleep(3)  # Wait for gallery to open

            # Try to find and click the recently added image (should be first in gallery)
            print("Looking for recently uploaded image in gallery...")

            # Strategy: Click on first image in grid (top-left)
            # Most galleries show newest images first
            screen_width = device.info['displayWidth']
            screen_height = device.info['displayHeight']

            # Click on top-left quadrant where first image usually is
            # Adjust these coordinates based on your device's gallery layout
            device.click(screen_width * 0.25, screen_height * 0.3)
            print("Clicked on first image position in gallery")

            time.sleep(2)

            # Look for crop/confirm button
            confirm_selectors = [
                device(text="Done"),
                device(text="OK"),
                device(text="Crop"),
                device(text="Next"),
                device(text="Confirm"),
                device(description="Done"),
                device(resourceId="com.instagram.android:id/next_button"),
            ]

            for selector in confirm_selectors:
                if selector.exists(timeout=3):
                    selector.click()
                    print(f"Clicked confirm button: {selector.info.get('text', 'button')}")
                    time.sleep(1)
                    break

            # Some Instagram versions require a second confirmation
            for selector in confirm_selectors:
                if selector.exists(timeout=2):
                    selector.click()
                    print("Clicked second confirmation if needed")
                    break

            time.sleep(2)
            print("Profile picture change process completed")
            return True

        except Exception as e:
            print(f"Failed to change profile picture automatically: {e}")
            return False

    def change_profile_picture_from_gallery_auto(self, device):
        """
        Automatically change profile picture by selecting first/last photo from phone gallery
        No need to transfer image - just opens gallery and picks first photo

        Args:
            device: uiautomator2 device object

        Returns:
            bool: Success status
        """
        try:
            print("Starting AUTO GALLERY profile picture change...")

            # Look for "Edit picture or avatar" button or similar
            picture_selectors = [
                device(text="Edit picture or avatar"),
                device(text="Edit picture"),
                device(text="Change profile photo"),
                device(text="Change Profile Photo"),
                device(description="Edit picture or avatar"),
                device(description="Change profile photo"),
                device(textContains="Edit picture"),
                device(textContains="avatar"),
            ]

            picture_clicked = False
            for selector in picture_selectors:
                if selector.exists(timeout=5):
                    selector.click()
                    print(f"Clicked: {selector.info.get('text', 'profile picture element')}")
                    picture_clicked = True
                    break

            if not picture_clicked:
                # Try clicking the top area where profile picture usually is
                print("Trying to find profile picture element by position...")
                screen_width = device.info['displayWidth']
                device.click(screen_width * 0.5, 250)
                print("Clicked profile picture area")

            time.sleep(2)

            # Look for "New profile picture" or gallery option
            # The modal has 3 options: Choose from library, Import from Facebook, Take photo
            gallery_selectors = [
                ("New profile picture", "text"),
                ("Choose from library", "text"),
                ("Choose from Library", "text"),
                ("Select from gallery", "text"),
                ("Select from Gallery", "text"),
                ("Choose from gallery", "text"),
                ("Choose from Gallery", "text"),
                ("Gallery", "text"),
                ("Library", "text"),
                ("Photos", "text"),
                ("library", "textContains"),
                ("gallery", "textContains"),
            ]

            gallery_clicked = False
            for selector_text, selector_type in gallery_selectors:
                if selector_type == "text":
                    selector = device(text=selector_text)
                else:  # textContains
                    selector = device(textContains=selector_text)

                if selector.exists(timeout=3):
                    selector.click()
                    print(f"✓ Selected: {selector_text}")
                    gallery_clicked = True
                    break

            if not gallery_clicked:
                print("⚠ Could not find gallery option with text selectors, trying coordinate fallback...")

                # Fallback: Click on the first option in the modal (usually top option)
                # The modal typically shows buttons vertically with "Choose from library" at top
                screen_width = device.info['displayWidth']
                screen_height = device.info['displayHeight']

                # Click at center of screen, about 45% from top (where first option usually is)
                device.click(screen_width * 0.5, screen_height * 0.45)
                print("✓ Clicked first option in modal (coordinate fallback)")
                gallery_clicked = True

            time.sleep(3)  # Wait for gallery to open

            # Pick the FIRST (newest/last) photo in the gallery
            print("Selecting first photo from gallery...")

            # Strategy: Click on first image in grid (top-left)
            # Most galleries show newest images first
            screen_width = device.info['displayWidth']
            screen_height = device.info['displayHeight']

            # Click on top-left quadrant where first image usually is
            # This should be the last/newest photo added to the gallery
            device.click(screen_width * 0.25, screen_height * 0.3)
            print("Clicked on first image (newest photo) in gallery")

            time.sleep(2)

            # Look for crop/confirm button
            confirm_selectors = [
                device(text="Done"),
                device(text="OK"),
                device(text="Crop"),
                device(text="Next"),
                device(text="Confirm"),
                device(description="Done"),
                device(resourceId="com.instagram.android:id/next_button"),
            ]

            for selector in confirm_selectors:
                if selector.exists(timeout=3):
                    selector.click()
                    print(f"Clicked confirm button: {selector.info.get('text', 'button')}")
                    time.sleep(1)
                    break

            # Some Instagram versions require a second confirmation
            for selector in confirm_selectors:
                if selector.exists(timeout=2):
                    selector.click()
                    print("Clicked second confirmation if needed")
                    break

            time.sleep(2)
            print("AUTO GALLERY profile picture change completed successfully!")
            return True

        except Exception as e:
            print(f"Failed to change profile picture from AUTO GALLERY: {e}")
            return False

    def edit_bio_automated(self, device, new_bio):
        """
        Fully automated bio editing - navigates to bio screen and edits
        Works like username editing: click Bio label to navigate to edit screen

        Args:
            device: uiautomator2 device object
            new_bio: New bio text

        Returns:
            bool: Success status
        """
        try:
            print(f"Setting bio to: {new_bio}")

            # Step 1: Navigate to bio field (like username)
            # Bio is typically 2 rows below Username on edit profile screen
            # Layout: Name -> Username -> Pronouns -> Bio
            bio_navigation_found = False

            try:
                # Method 1: Find "Bio" label and click below it
                if device(text="Bio").exists(timeout=3):
                    bio_label_bounds = device(text="Bio").info['bounds']
                    print(f"Found 'Bio' label at bounds: {bio_label_bounds}")

                    # Click below the "Bio" label where the bio text/row is
                    click_x = bio_label_bounds['left'] + 50
                    click_y = bio_label_bounds['bottom'] + 30  # Click 30 pixels below label

                    print(f"Clicking at ({click_x}, {click_y}) to navigate to bio edit screen")
                    device.click(click_x, click_y)
                    bio_navigation_found = True
                    time.sleep(2)  # Wait for bio edit screen to load
                else:
                    print("Could not find 'Bio' label")

            except Exception as e:
                print(f"Label click method failed: {e}")

            # Method 2: Try clicking on bio text directly
            if not bio_navigation_found:
                try:
                    # Look for text that indicates current bio or placeholder
                    bio_text_selectors = [
                        device(textContains="+ Add Bio"),
                        device(textContains="Add Bio"),
                        device(textContains="Tell people"),
                        device(resourceId="com.instagram.android:id/bio"),
                    ]

                    for selector in bio_text_selectors:
                        if selector.exists(timeout=2):
                            selector.click()
                            print("Clicked bio text/row to navigate to edit screen")
                            bio_navigation_found = True
                            time.sleep(2)
                            break

                except Exception as e:
                    print(f"Bio text click method failed: {e}")

            if not bio_navigation_found:
                print("Could not navigate to bio edit screen")
                return False

            # Step 2: Now on bio edit screen - find the EditText field
            print("Looking for bio EditText field...")
            time.sleep(1)

            edit_text_selectors = [
                device(className="android.widget.EditText"),
                device.xpath('//android.widget.EditText'),
                device(resourceId="com.instagram.android:id/bio"),
            ]

            edit_field = None
            for selector in edit_text_selectors:
                if selector.exists(timeout=5):
                    edit_field = selector
                    edit_field.click()
                    print("Found bio EditText field")
                    time.sleep(1)
                    break

            if not edit_field:
                print("Could not find bio edit field")
                return False

            # Step 3: Clear existing bio and input new one (same method as username)
            try:
                print("Clearing existing bio and entering new one...")

                # Select all text using long press
                edit_field.long_click()
                time.sleep(0.5)

                # Try to find and click "Select all" if it appears
                if device(text="Select all").exists(timeout=1):
                    device(text="Select all").click()
                    time.sleep(0.3)

                # Delete selected text
                device.press("delete")
                time.sleep(0.5)

                # Input new bio using shell command
                # Handle special characters properly
                print(f"Attempting to input bio: {new_bio}")

                # Method 1: Try typing character by character for better reliability
                try:
                    for char in new_bio:
                        if char == ' ':
                            # Space needs special handling
                            device.shell('input text %s')
                        elif char in ['|', '&', '<', '>', '(', ')', '{', '}', '[', ']', '$', '`', '"', "'", '\\', ';', '*', '?', '!', '#']:
                            # Special shell characters - use keyevent or direct input
                            device.shell(f'input text "{char}"')
                        else:
                            device.shell(f'input text {char}')
                        time.sleep(0.05)  # Small delay between characters

                    print(f"Bio changed to: {new_bio}")
                    time.sleep(1)

                except Exception as e:
                    print(f"Character-by-character input failed: {e}")
                    # Method 2: Try using uiautomator2's set_text
                    try:
                        edit_field.set_text(new_bio)
                        print(f"Bio changed using set_text: {new_bio}")
                        time.sleep(1)
                    except Exception as e2:
                        print(f"set_text also failed: {e2}")
                        print("Please input bio manually")
                        return False

                # Go back to edit profile screen
                device.press("back")
                time.sleep(2)

                return True

            except Exception as e:
                print(f"Failed to change bio: {e}")
                return False

        except Exception as e:
            print(f"Failed to edit bio: {e}")
            return False

    def edit_username_automated(self, device, new_username):
        """
        Fully automated username editing (from instagram_automation.py)

        Args:
            device: uiautomator2 device object
            new_username: New username

        Returns:
            bool: Success status
        """
        try:
            print(f"Changing username to: {new_username}")

            # Navigate to username field
            username_found = False

            try:
                if device(text="Username").exists(timeout=3):
                    username_label_bounds = device(text="Username").info['bounds']
                    print(f"Found 'Username' label at bounds: {username_label_bounds}")

                    # Click below the label
                    click_x = username_label_bounds['left'] + 50
                    click_y = username_label_bounds['bottom'] + 30

                    print(f"Clicking at ({click_x}, {click_y}) to select username field")
                    device.click(click_x, click_y)
                    username_found = True
                    time.sleep(2)

            except Exception as e:
                print(f"First method failed: {e}")

            if not username_found:
                print("Could not navigate to username edit screen")
                return False

            # Now on username edit screen - find EditText field
            time.sleep(1)

            edit_text_selectors = [
                device(resourceId="com.instagram.android:id/username_text_view"),
                device(className="android.widget.EditText"),
                device.xpath('//android.widget.EditText'),
            ]

            edit_field = None
            for selector in edit_text_selectors:
                if selector.exists(timeout=5):
                    edit_field = selector
                    edit_field.click()
                    print("Found username EditText field")
                    time.sleep(1)
                    break

            if not edit_field:
                print("Could not find username edit field")
                return False

            # Clear and input new username
            try:
                # Select all and delete
                edit_field.long_click()
                time.sleep(0.5)

                if device(text="Select all").exists(timeout=1):
                    device(text="Select all").click()
                    time.sleep(0.3)

                device.press("delete")
                time.sleep(0.5)

                # Input new username
                device.shell(f'input text {new_username}')
                print(f"Username changed to: {new_username}")
                time.sleep(1)

                return True

            except Exception as e:
                print(f"Failed to change username: {e}")
                return False

        except Exception as e:
            print(f"Failed to edit username: {e}")
            return False

    def process_single_task(self, task):
        """
        Process a single profile update task

        Args:
            task: Task dictionary from database

        Returns:
            bool: Success status
        """
        self.current_task = task
        task_id = task['id']
        device_serial = task['device_serial']
        instagram_package = task['instagram_package']

        print(f"\n{'='*70}")
        print(f"Processing Task ID: {task_id}")
        print(f"Device: {device_serial}")
        print(f"Instagram Package: {instagram_package}")
        print(f"{'='*70}\n")

        update_task_status(task_id, 'in_progress')

        try:
            # Connect to device
            print(f"Connecting to device: {device_serial}")
            self.device = connect_device(device_serial=device_serial)

            if not self.device:
                raise Exception(f"Failed to connect to device: {device_serial}")

            # Open Instagram
            print(f"Opening Instagram: {instagram_package}")
            if not open_instagram(self.device, instagram_package):
                raise Exception(f"Failed to open Instagram: {instagram_package}")

            # Wait for Instagram to fully load
            time.sleep(3)

            # Check for challenge/verification screens
            challenge = self.detect_challenge_screen()
            if challenge['is_challenge']:
                error_msg = f"Account requires verification: {challenge['challenge_type']} ('{challenge['text']}')"
                print(f"\n❌ SKIPPING TASK: {error_msg}")
                print("   This account needs manual verification before automation can continue.")
                update_task_status(task_id, 'failed', error_msg)
                return False

            # Navigate to profile
            print("Navigating to profile...")
            if not navigate_to_profile(self.device):
                print("Warning: Could not navigate to profile automatically")
                print("Assuming we're already on profile page...")

            time.sleep(2)

            # Navigate to edit profile
            print("Navigating to edit profile screen...")
            if not navigate_to_edit_profile(self.device):
                raise Exception("Failed to navigate to edit profile screen")

            time.sleep(2)

            # Dismiss any modals that appear (especially "Create your avatar")
            self.dismiss_instagram_modals()

            # Track what changed for logging
            changes_made = []

            # Change profile picture if specified
            if task['profile_picture_id']:
                print(f"\n--- Changing Profile Picture (ID: {task['profile_picture_id']}) ---")

                # Check if using AUTO_GALLERY strategy (pick from phone gallery automatically)
                if task['profile_picture_id'] == 'AUTO_GALLERY':
                    print("Using AUTO_GALLERY strategy - will pick first photo from phone gallery")
                    # Call the auto gallery selection method
                    if self.change_profile_picture_from_gallery_auto(self.device):
                        print("Profile picture changed successfully from gallery!")
                        changes_made.append("profile_picture")

                        # Log change
                        log_profile_change(
                            device_serial, instagram_package, task.get('username', 'unknown'),
                            'profile_picture', None, 'AUTO_GALLERY', success=True
                        )
                    else:
                        print("Warning: Auto gallery profile picture change may have failed")

                elif not task['original_path'] or not os.path.exists(task['original_path']):
                    print(f"Warning: Profile picture file not found: {task['original_path']}")
                else:
                    # Transfer image to device
                    device_image_path = self.transfer_image_to_device(
                        task['original_path'],
                        device_serial
                    )

                    if device_image_path:
                        # Change profile picture
                        if self.change_profile_picture_automated(self.device, device_image_path):
                            print("Profile picture changed successfully!")
                            update_picture_usage(task['profile_picture_id'])
                            changes_made.append("profile_picture")

                            # Log change
                            log_profile_change(
                                device_serial, instagram_package, task.get('username', 'unknown'),
                                'profile_picture', None, task['filename'], success=True
                            )
                        else:
                            print("Warning: Profile picture change may have failed")
                    else:
                        print("Failed to transfer image to device")

                time.sleep(2)

            # Change username if specified (using smart changer with AI and retry)
            if task['new_username']:
                print(f"\n--- Changing Username to: {task['new_username']} ---")

                # Use smart username changer with retry and AI
                smart_changer = SmartUsernameChanger(
                    device=self.device,
                    ai_api_key=task.get('ai_api_key'),  # Get from task if available
                    ai_provider=task.get('ai_provider', 'openai')
                )

                result = smart_changer.change_username_with_retry(
                    target_username=task['new_username'],
                    mother_account=task.get('mother_account'),
                    max_attempts=5
                )

                if result['success']:
                    final_username = result['final_username']
                    print(f"Username changed successfully to: {final_username}")
                    print(f"(Took {result['attempts']} attempt(s))")
                    changes_made.append("username")

                    # Log change with actual username used
                    log_profile_change(
                        device_serial, instagram_package, task.get('username', 'unknown'),
                        'username', task.get('username'), final_username, success=True
                    )

                    # Sync username change with Onimator
                    old_username = task.get('username', 'unknown')
                    if old_username != 'unknown':
                        print(f"\n--- Syncing Username with Onimator ---")
                        sync_result = sync_username_with_onimator(
                            device_serial=device_serial,
                            old_username=old_username,
                            new_username=final_username
                        )
                        if sync_result['success']:
                            print("✅ Onimator sync successful!")
                        else:
                            print(f"⚠ Onimator sync had errors: {sync_result['errors']}")
                    else:
                        print("⚠ Cannot sync with Onimator - old username unknown")

                    # Ensure we're back on edit profile screen
                    print("Navigating back to edit profile screen...")
                    self.device.press("back")
                    time.sleep(2)

                    # Verify we're actually on edit profile screen
                    if not self.ensure_on_edit_profile_screen():
                        print("Warning: May not be on edit profile screen after username change")
                else:
                    error_msg = result.get('error', 'Unknown error')
                    print(f"Failed to change username after {result['attempts']} attempts")
                    print(f"Error: {error_msg}")

                    # Log failed attempt
                    log_profile_change(
                        device_serial, instagram_package, task.get('username', 'unknown'),
                        'username', task.get('username'), task['new_username'], success=False
                    )

            # Change bio if specified
            if task['new_bio']:
                print(f"\n--- Changing Bio ---")
                print(f"New bio: {task['new_bio']}")

                # Ensure we're on edit profile screen before trying to edit bio
                if not self.ensure_on_edit_profile_screen():
                    print("Error: Could not get to edit profile screen for bio editing")
                    print("Warning: Skipping bio change")
                elif self.edit_bio_automated(self.device, task['new_bio']):
                    print("Bio changed successfully!")
                    changes_made.append("bio")

                    # Log change
                    log_profile_change(
                        device_serial, instagram_package, task.get('username', 'unknown'),
                        'bio', None, task['new_bio'], success=True
                    )
                else:
                    print("Warning: Bio change may have failed")

                time.sleep(1)

            # Save all changes
            print("\n--- Saving Profile Changes ---")
            if save_profile_changes(self.device):
                print("Profile changes saved successfully!")
            else:
                print("Warning: Could not find save button, changes may not be saved")

            time.sleep(2)

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

            return True

        except Exception as e:
            error_msg = str(e)
            print(f"\nError processing task {task_id}: {error_msg}")
            update_task_status(task_id, 'failed', error_msg)
            return False

        finally:
            # ALWAYS disconnect device to release UIAutomator for other tools (like Onimator)
            if self.device is not None:
                print(f"\n🔌 Disconnecting device to release UIAutomator...")
                disconnect_device(self.device, device_serial)
                self.device = None

    def run_batch_processor(self, max_tasks=None):
        """
        Process all pending tasks in the queue

        Args:
            max_tasks: Maximum number of tasks to process (None = all)
        """
        print("\n" + "="*70)
        print("AUTOMATED PROFILE MANAGER - BATCH PROCESSOR")
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

        # Process each task
        successful = 0
        failed = 0

        for i, task in enumerate(pending_tasks, 1):
            print(f"\n\n{'#'*70}")
            print(f"# Task {i} of {len(pending_tasks)}")
            print(f"{'#'*70}")

            if self.process_single_task(task):
                successful += 1
            else:
                failed += 1

            # Wait between tasks to avoid issues
            if i < len(pending_tasks):
                print(f"\nWaiting 5 seconds before next task...")
                time.sleep(5)

        # Summary
        print(f"\n\n{'='*70}")
        print("BATCH PROCESSING COMPLETE")
        print(f"{'='*70}")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")
        print(f"Total: {len(pending_tasks)}")
        print(f"{'='*70}\n")

def main():
    """Main entry point"""
    # Initialize database
    init_database()

    # Create manager instance
    manager = AutomatedProfileManager()

    # Run batch processor
    manager.run_batch_processor()

if __name__ == "__main__":
    main()
