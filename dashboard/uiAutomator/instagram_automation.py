#!/usr/bin/env python3
"""
Instagram Profile Automation Script using uiAutomator2
This script connects to an Android device via ADB and automates opening Instagram app
and navigating to the user's profile.
"""

import uiautomator2 as u2
import time
import sys
import os
import subprocess

def list_adb_devices():
    """List all connected ADB devices with details"""
    try:
        result = subprocess.run(['adb', 'devices', '-l'],
                              capture_output=True,
                              text=True,
                              check=True)

        lines = result.stdout.strip().split('\n')[1:]  # Skip header
        devices = []

        for line in lines:
            if line.strip() and 'device' in line:
                parts = line.split()
                serial = parts[0]

                # Get device model and product info
                model = "Unknown"
                product = "Unknown"

                for part in parts:
                    if part.startswith('model:'):
                        model = part.split(':')[1]
                    elif part.startswith('product:'):
                        product = part.split(':')[1]

                devices.append({
                    'serial': serial,
                    'model': model,
                    'product': product
                })

        return devices
    except subprocess.CalledProcessError as e:
        print(f"Error running adb: {e}")
        return []
    except FileNotFoundError:
        print("ADB not found. Please ensure ADB is installed and in your PATH.")
        return []

def select_device():
    """Interactive device selection menu"""
    devices = list_adb_devices()

    if not devices:
        print("No devices found. Please connect your Android device and enable USB debugging.")
        return None

    print("\n" + "="*70)
    print("CONNECTED DEVICES")
    print("="*70)

    for idx, device in enumerate(devices, 1):
        print(f"{idx}. Serial: {device['serial']:<20} Model: {device['model']:<15} Product: {device['product']}")

    print("="*70)

    while True:
        try:
            choice = input(f"\nSelect device (1-{len(devices)}) or 'q' to quit: ").strip()

            if choice.lower() == 'q':
                return None

            choice_num = int(choice)
            if 1 <= choice_num <= len(devices):
                selected = devices[choice_num - 1]
                print(f"\nSelected device: {selected['model']} ({selected['serial']})")
                return selected['serial']
            else:
                print(f"Invalid choice. Please enter a number between 1 and {len(devices)}")
        except ValueError:
            print("Invalid input. Please enter a number or 'q' to quit.")
        except KeyboardInterrupt:
            print("\nCancelled.")
            return None

def select_instagram_package():
    """Interactive Instagram package selection menu"""
    # Instagram clones - note: some devices use 'androi' (single letter) instead of 'android'
    packages = []

    # Add both variations to support different clone naming schemes
    for letter in 'efghijklmnop':
        packages.append(f"com.instagram.androi{letter}")  # Single letter version (e.g., androie, androif)

    print("\n" + "="*70)
    print("INSTAGRAM PACKAGE SELECTION")
    print("="*70)
    print("0. com.instagram.android (Original Instagram)")

    for idx, package in enumerate(packages, 1):
        suffix = package.split('.')[-1].replace('androi', '')
        print(f"{idx}. {package} (Clone {suffix.upper()})")

    print("="*70)

    while True:
        try:
            choice = input(f"\nSelect Instagram package (0-{len(packages)}) or 'q' to quit: ").strip()

            if choice.lower() == 'q':
                return None

            choice_num = int(choice)
            if choice_num == 0:
                selected = "com.instagram.android"
                print(f"\nSelected: {selected} (Original)")
                return selected
            elif 1 <= choice_num <= len(packages):
                selected = packages[choice_num - 1]
                print(f"\nSelected: {selected}")
                return selected
            else:
                print(f"Invalid choice. Please enter a number between 0 and {len(packages)}")
        except ValueError:
            print("Invalid input. Please enter a number or 'q' to quit.")
        except KeyboardInterrupt:
            print("\nCancelled.")
            return None

def connect_device(device_ip=None, device_serial=None):
    """
    Connect to Android device via ADB
    First tries simple connection (assumes UIAutomator is running)
    If that fails, does ATX recovery and retries
    """
    try:
        device = None
        connection_serial = None

        if device_ip:
            connection_serial = device_ip
        elif device_serial:
            # Convert underscore to colon for network ADB
            connection_serial = device_serial.replace('_', ':')

        if connection_serial:
            print(f"Preparing to connect to: {connection_serial}")

            # STEP 1: Kill ALL existing UIAutomator processes to start fresh
            print("\nStep 1: Cleaning up existing UIAutomator processes...")
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
                print("  Killed all UIAutomator-related processes")
                print("  Waiting for complete shutdown...")
                time.sleep(5)  # Wait longer for complete shutdown
            except Exception as e:
                print(f"  Warning during cleanup: {e}")

            # STEP 2: Connect to device (u2.connect will auto-start UIAutomator)
            print("\nStep 2: Connecting to device...")
            print("  (uiautomator2 will automatically start UIAutomator service)")
            device = u2.connect(connection_serial)
            print(f"  Connected (serial: {device.serial})")

            # STEP 3: Wait for UIAutomator to be responsive
            print("\nStep 3: Waiting for UIAutomator to be responsive...")
            max_wait = 45
            start_time = time.time()

            while (time.time() - start_time) < max_wait:
                try:
                    _ = device.info
                    _ = device.window_size()
                    elapsed = int(time.time() - start_time)
                    print(f"  SUCCESS! UIAutomator is responsive (took {elapsed}s)")
                    return device
                except Exception as e:
                    elapsed = int(time.time() - start_time)
                    if elapsed % 5 == 0:  # Print every 5 seconds
                        print(f"  Waiting... {elapsed}s / {max_wait}s")
                    time.sleep(1)

            print(f"\nWarning: UIAutomator didn't respond after {max_wait}s")
            print("You may need to manually start UIAutomator in ATX Agent app")
            return device
        else:
            # No serial specified, connect to first available device
            device = u2.connect()

        if device:
            return device
        else:
            print("Connection failed")
            return None

    except Exception as e:
        print(f"Failed to connect: {e}")
        return None


def disconnect_device(device, device_serial=None):
    """
    Properly disconnect from device and stop UIAutomator service.
    This releases the device so Onimator/igbot.exe can use it.

    CRITICAL: The main issue is that uiautomator2 maintains HTTP session connections
    to the atx-agent. We must close these Python-side connections, not just try to
    kill device processes (which require root anyway).

    Args:
        device: The uiautomator2 device object
        device_serial: Optional device serial for ADB cleanup
    """
    import gc

    if device is None:
        return

    try:
        print(f"\nDisconnecting from device...")

        # Get the serial from device if not provided
        if device_serial is None:
            try:
                device_serial = device.serial
            except:
                pass

        # CRITICAL: Close the internal HTTP session that uiautomator2 maintains
        # This is what actually holds the connection open from Python side
        try:
            # uiautomator2 uses a requests Session internally
            if hasattr(device, '_reqsess') and device._reqsess is not None:
                device._reqsess.close()
                print("  Closed HTTP session (_reqsess)")

            # Also try the session attribute (different u2 versions)
            if hasattr(device, 'session') and device.session is not None:
                if hasattr(device.session, 'close'):
                    device.session.close()
                print("  Closed session")

            # Try closing any http client
            if hasattr(device, 'http') and device.http is not None:
                if hasattr(device.http, 'close'):
                    device.http.close()
                print("  Closed http client")

        except Exception as e:
            print(f"  Note: HTTP session cleanup: {e}")

        # Try to stop via uiautomator2's built-in method
        try:
            if hasattr(device, 'stop_uiautomator'):
                device.stop_uiautomator()
                print("  Stopped via device.stop_uiautomator()")
        except Exception as e:
            print(f"  stop_uiautomator: {e}")

        # Remove ADB port forwards - this is key for releasing the connection
        if device_serial:
            connection_serial = device_serial.replace('_', ':')
            print(f"  Cleaning up ADB forwards for {connection_serial}...")
            try:
                # Remove the forward rules that uiautomator2 sets up
                # This breaks the tunnel between PC and device's atx-agent
                subprocess.run(
                    ['adb', '-s', connection_serial, 'forward', '--remove-all'],
                    capture_output=True, timeout=5
                )
                subprocess.run(
                    ['adb', '-s', connection_serial, 'reverse', '--remove-all'],
                    capture_output=True, timeout=5
                )
                print(f"  ADB forwards removed")

                # Force-stop the uiautomator app (this we CAN do without root)
                subprocess.run(
                    ['adb', '-s', connection_serial, 'shell', 'am', 'force-stop', 'com.github.uiautomator'],
                    capture_output=True, timeout=5
                )
                subprocess.run(
                    ['adb', '-s', connection_serial, 'shell', 'am', 'force-stop', 'com.github.uiautomator.test'],
                    capture_output=True, timeout=5
                )
                print(f"  UIAutomator apps force-stopped")

            except Exception as e:
                print(f"  Warning during ADB cleanup: {e}")

        # Clear all references to allow garbage collection
        # This is important - Python's reference counting needs objects to be dereferenced
        try:
            # Clear any internal state
            if hasattr(device, '_reqsess'):
                device._reqsess = None
            if hasattr(device, 'session'):
                device.session = None
            if hasattr(device, 'http'):
                device.http = None
        except:
            pass

        print("  Device disconnected successfully")

        # Force garbage collection to clean up any remaining socket connections
        gc.collect()
        print("  Garbage collection completed")

    except Exception as e:
        print(f"  Warning during disconnect: {e}")


def open_instagram(device, package_name="com.instagram.android"):
    """
    Open Instagram app using uiautomator2's app_start with monkey (GramAddict proven method)
    """
    try:
        print(f"Opening Instagram package: {package_name}")

        # Use uiautomator2's app_start with use_monkey=True (GramAddict proven method)
        # This is more reliable than direct ADB commands
        try:
            device.app_start(package_name, use_monkey=True)
            print(f"Instagram launched with monkey")
            time.sleep(5)  # Give Instagram time to fully launch

            # Verify Instagram is running
            try:
                current_app = device.app_current().get('package')
                if current_app == package_name:
                    print(f"Instagram is running: {package_name}")
                    return True
                else:
                    print(f"Note: Current app is {current_app}, but Instagram should be starting...")
                    return True
            except Exception as e:
                print(f"Note: Could not verify app state: {e}")
                return True

        except Exception as e:
            print(f"app_start failed: {e}, falling back to ADB monkey command")
            # Fallback to direct ADB monkey command
            result = subprocess.run(
                ['adb', '-s', device.serial, 'shell', 'monkey', '-p', package_name, '1'],
                capture_output=True,
                text=True,
                timeout=10
            )
            print(f"Started Instagram via ADB monkey")
            time.sleep(5)
            return True

    except Exception as e:
        print(f"Failed to open Instagram: {e}")
        return False

def navigate_to_profile(device):
    """Navigate to user profile"""
    try:
        # Look for profile tab (usually at bottom right)
        # Instagram profile tab typically has content description or resource ID

        # Try multiple selectors for profile tab
        profile_selectors = [
            # By content description
            device(description="Profile"),
            device(description="profile"),
            # By resource ID (may vary by Instagram version)
            device(resourceId="com.instagram.android:id/profile_tab"),
            # By text
            device(text="Profile"),
            # By XPath for bottom navigation
            device.xpath('//android.widget.FrameLayout[contains(@content-desc, "Profile")]'),
        ]

        profile_clicked = False
        for selector in profile_selectors:
            if selector.exists(timeout=5):
                selector.click()
                print("Clicked on profile tab")
                profile_clicked = True
                break

        if not profile_clicked:
            # Fallback: try clicking bottom-right area where profile usually is
            print("Profile tab not found with selectors, trying bottom-right corner")
            # Use window_size() instead of device.info to avoid UiAutomation issues
            screen_width, screen_height = device.window_size()
            # Click bottom-right area (approximate profile tab location)
            device.click(screen_width * 0.8, screen_height * 0.95)

        time.sleep(2)  # Wait for profile to load
        print("Navigated to profile")
        return True

    except Exception as e:
        print(f"Failed to navigate to profile: {e}")
        return False

def navigate_to_edit_profile(device):
    """Navigate to edit profile screen"""
    try:
        # Look for "Edit profile" button - common selectors
        edit_profile_selectors = [
            device(text="Edit profile"),
            device(text="Edit Profile"),
            device(description="Edit profile"),
            device(resourceId="com.instagram.android:id/action_bar_button_text"),
            device.xpath('//android.widget.Button[contains(@text, "Edit")]'),
        ]

        edit_clicked = False
        for selector in edit_profile_selectors:
            if selector.exists(timeout=5):
                selector.click()
                print("Clicked 'Edit profile' button")
                edit_clicked = True
                break

        if not edit_clicked:
            print("Edit profile button not found, searching more broadly...")
            # Try to find any button with "Edit" in it
            if device(textContains="Edit").exists(timeout=3):
                device(textContains="Edit").click()
                edit_clicked = True

        if edit_clicked:
            time.sleep(2)  # Wait for edit profile screen to load
            print("Navigated to edit profile screen")
            return True
        else:
            print("Could not find Edit profile button")
            return False

    except Exception as e:
        print(f"Failed to navigate to edit profile: {e}")
        return False

def change_profile_picture(device):
    """Change profile picture - should be called when already on edit profile screen"""
    try:
        # Look for "Edit picture or avatar" button or similar on edit profile screen
        picture_selectors = [
            device(text="Edit picture or avatar"),
            device(text="Edit picture"),
            device(text="Change profile photo"),
            device(text="Change Profile Photo"),
            device(description="Edit picture or avatar"),
            device(description="Change profile photo"),
            device(description="Profile photo"),
            device(textContains="Edit picture"),
            device(textContains="avatar"),
            device(resourceId="com.instagram.android:id/avatar_image_view"),
            device.xpath('//android.widget.Button[contains(@text, "picture")]'),
            device.xpath('//android.widget.Button[contains(@text, "avatar")]'),
        ]

        picture_clicked = False
        for selector in picture_selectors:
            if selector.exists(timeout=5):
                selector.click()
                print(f"Clicked: {selector.info.get('text', 'profile picture element')}")
                picture_clicked = True
                break

        if not picture_clicked:
            # Try clicking the top area where profile picture usually is on edit screen
            print("Trying to find profile picture element...")
            screen_width, screen_height = device.window_size()
            device.click(screen_width * 0.5, 250)  # Click top center area
            print("Clicked profile picture area")

        time.sleep(2)

        # Look for photo selection options
        if device(text="New profile picture").exists(timeout=3):
            device(text="New profile picture").click()
            print("Selected 'New profile picture'")
        elif device(text="Select from gallery").exists(timeout=3):
            device(text="Select from gallery").click()
            print("Selected 'Select from gallery'")
        elif device(text="Select from Gallery").exists(timeout=3):
            device(text="Select from Gallery").click()
            print("Selected 'Select from Gallery'")
        elif device(text="Choose from Library").exists(timeout=3):
            device(text="Choose from Library").click()
            print("Selected 'Choose from Library'")
        elif device(textContains="Gallery").exists(timeout=3):
            device(textContains="Gallery").click()
            print("Selected gallery option")
        else:
            print("No gallery option found - you may need to select manually")

        time.sleep(2)
        print("Profile picture change initiated - manual selection may be required")
        return True

    except Exception as e:
        print(f"Failed to change profile picture: {e}")
        return False

def edit_username(device, new_username=None):
    """Edit username - should be called when already on edit profile screen"""
    try:
        # On edit profile screen, look for Username field/row that navigates to new screen
        # Need to avoid clicking "Name" field which appears first

        # Strategy: Click on the actual username value (like "anna.trmnl"), not the label
        # First, try to find all text elements and identify which one looks like a username
        username_found = False

        # Strategy: Use dump hierarchy and find the username field by looking at the structure
        try:
            # Get the screen bounds for the "Username" label
            if device(text="Username").exists(timeout=3):
                username_label_bounds = device(text="Username").info['bounds']
                print(f"Found 'Username' label at bounds: {username_label_bounds}")

                # Click below the "Username" label where the actual username value should be
                # The username value is typically displayed below the label in the same row
                click_x = username_label_bounds['left'] + 50
                click_y = username_label_bounds['bottom'] + 30  # Click 30 pixels below the label

                print(f"Clicking at ({click_x}, {click_y}) to select username field")
                device.click(click_x, click_y)
                username_found = True
                time.sleep(2)  # Wait for new screen to load
            else:
                print("Could not find 'Username' label")

        except Exception as e:
            print(f"First method failed: {e}")

        # Fallback methods if the above didn't work
        if not username_found:
            username_selectors = [
                device.xpath('//android.widget.LinearLayout[.//android.widget.TextView[@text="Username"]]'),
                device(textMatches=".*[a-z0-9._]+.*"),  # Try to match username pattern
            ]

            for selector in username_selectors:
                if selector.exists(timeout=3):
                    selector.click()
                    print("Clicked Username field using fallback - navigating to username edit screen")
                    username_found = True
                    time.sleep(2)  # Wait for new screen to load
                    break

        if not username_found:
            print("Could not find Username field on edit profile screen")
            return False

        # Now we're on the username edit screen - find the actual EditText field
        time.sleep(1)

        edit_text_selectors = [
            device(resourceId="com.instagram.android:id/username_text_view"),
            device(className="android.widget.EditText"),
            device.xpath('//android.widget.EditText'),
        ]

        edit_text_found = False
        for selector in edit_text_selectors:
            if selector.exists(timeout=5):
                selector.click()
                print("Found username EditText field")
                edit_text_found = True
                time.sleep(1)
                break

        if edit_text_found:
            # Clear existing username and input new one
            time.sleep(0.5)

            if new_username:
                try:
                    # First, get the EditText element to work with
                    edit_field = None
                    for selector in edit_text_selectors:
                        if selector.exists(timeout=2):
                            edit_field = selector
                            break

                    if edit_field:
                        # Select all text using long press and then clear
                        edit_field.long_click()
                        time.sleep(0.5)

                        # Try to find and click "Select all" if it appears
                        if device(text="Select all").exists(timeout=1):
                            device(text="Select all").click()
                            time.sleep(0.3)

                        # Delete selected text using keycode
                        device.press("delete")
                        time.sleep(0.5)

                        # Now input the new username using shell command
                        device.shell(f'input text {new_username}')
                        print(f"Username changed to: {new_username}")
                    else:
                        print("Could not find edit field to clear")
                        return False

                except Exception as e:
                    print(f"Failed to change username: {e}")
                    print("Please clear and enter username manually")
            else:
                print("Username field ready - enter username manually")

            return True
        else:
            print("Could not find username EditText on username edit screen")
            return False

    except Exception as e:
        print(f"Failed to edit username: {e}")
        return False

def edit_bio(device, new_bio=None):
    """
    Edit bio - navigates to bio screen and edits
    Works like username editing: click Bio label to navigate to edit screen
    """
    try:
        # Step 1: Navigate to bio field by clicking on it
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
        if new_bio:
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
        else:
            print("Bio field selected - manual input required")
            return True

    except Exception as e:
        print(f"Failed to edit bio: {e}")
        return False

def save_profile_changes(device):
    """Save profile changes"""
    try:
        # Look for save/done button
        save_selectors = [
            device(text="Done"),
            device(text="Save"),
            device(description="Done"),
            device(resourceId="com.instagram.android:id/action_bar_button_text"),
        ]

        for selector in save_selectors:
            if selector.exists(timeout=5):
                selector.click()
                print("Profile changes saved")
                time.sleep(2)
                return True

        print("Could not find save button")
        return False

    except Exception as e:
        print(f"Failed to save profile changes: {e}")
        return False

def show_menu():
    """Display action menu"""
    print("\n" + "="*50)
    print("INSTAGRAM PROFILE AUTOMATION")
    print("="*50)
    print("1. Navigate to profile only")
    print("2. Navigate to edit profile")
    print("3. Change profile picture")
    print("4. Edit username")
    print("5. Edit bio")
    print("6. Full profile edit (picture + username + bio)")
    print("0. Exit")
    print("="*50)

def main():
    """Main function"""
    print("\n" + "="*70)
    print("INSTAGRAM PROFILE AUTOMATION - SETUP")
    print("="*70)

    # Step 1: Select device
    device_serial = select_device()
    if not device_serial:
        print("Exiting: No device selected")
        return

    # Step 2: Select Instagram package
    package_name = select_instagram_package()
    if not package_name:
        print("Exiting: No Instagram package selected")
        return

    # Step 3: Connect to device
    device = connect_device(device_serial=device_serial)
    if not device:
        print("Exiting: Could not connect to device")
        return

    # Step 4: Open Instagram
    if not open_instagram(device, package_name):
        print("Exiting: Could not open Instagram")
        return

    # Navigate to profile first
    if not navigate_to_profile(device):
        print("Warning: Could not navigate to profile automatically")
        print("Please manually navigate to your profile, then continue...")
        input("Press Enter when you're on your profile page...")

    # Track current screen state
    on_edit_profile_screen = False

    # Show interactive menu
    while True:
        show_menu()
        if on_edit_profile_screen:
            print("\n[Currently on Edit Profile screen]")

        try:
            choice = input("\nEnter your choice (0-6): ").strip()

            if choice == "0":
                print("Exiting...")
                break

            elif choice == "1":
                # Go back to profile page
                device.press("back")
                time.sleep(1)
                on_edit_profile_screen = False
                print("Navigated back to profile page")

            elif choice == "2":
                # Navigate to edit profile (only if not already there)
                if not on_edit_profile_screen:
                    if navigate_to_edit_profile(device):
                        print("Successfully navigated to edit profile screen")
                        on_edit_profile_screen = True
                    else:
                        print("Failed to navigate to edit profile")
                else:
                    print("Already on edit profile screen!")

            elif choice == "3":
                # Change profile picture
                if not on_edit_profile_screen:
                    if navigate_to_edit_profile(device):
                        on_edit_profile_screen = True
                    else:
                        print("Failed to navigate to edit profile first")
                        continue

                change_profile_picture(device)

            elif choice == "4":
                # Edit username
                if not on_edit_profile_screen:
                    if navigate_to_edit_profile(device):
                        on_edit_profile_screen = True
                    else:
                        print("Failed to navigate to edit profile first")
                        continue

                new_username = input("Enter new username (or press Enter to just select field): ").strip()
                username_value = new_username if new_username else None
                if edit_username(device, username_value):
                    if input("Save changes? (y/n): ").lower() == 'y':
                        save_profile_changes(device)
                        device.press("back")
                        time.sleep(1)
                    else:
                        device.press("back")
                        time.sleep(1)

            elif choice == "5":
                # Edit bio
                if not on_edit_profile_screen:
                    if navigate_to_edit_profile(device):
                        on_edit_profile_screen = True
                    else:
                        print("Failed to navigate to edit profile first")
                        continue

                new_bio = input("Enter new bio (or press Enter to just select field): ").strip()
                bio_value = new_bio if new_bio else None
                if edit_bio(device, bio_value):
                    if input("Save changes? (y/n): ").lower() == 'y':
                        save_profile_changes(device)

            elif choice == "6":
                # Full profile edit
                if not on_edit_profile_screen:
                    if navigate_to_edit_profile(device):
                        on_edit_profile_screen = True
                    else:
                        print("Failed to navigate to edit profile first")
                        continue

                print("\n--- FULL PROFILE EDIT ---")

                # Profile picture
                if input("Change profile picture? (y/n): ").lower() == 'y':
                    change_profile_picture(device)
                    input("Press Enter after selecting picture...")

                # Username
                if input("Change username? (y/n): ").lower() == 'y':
                    new_username = input("Enter new username: ").strip()
                    edit_username(device, new_username)
                    device.press("back")
                    time.sleep(1)

                # Bio
                if input("Change bio? (y/n): ").lower() == 'y':
                    new_bio = input("Enter new bio: ").strip()
                    edit_bio(device, new_bio)

                # Save all changes
                if input("Save all changes? (y/n): ").lower() == 'y':
                    save_profile_changes(device)

            else:
                print("Invalid choice. Please try again.")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"An error occurred: {e}")

    print("Script completed!")

if __name__ == "__main__":
    main()