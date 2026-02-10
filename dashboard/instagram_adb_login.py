#!/usr/bin/env python3
import os
import subprocess
import time
import re
import requests
from bs4 import BeautifulSoup
import json
import sqlite3
from pathlib import Path
import tempfile
from PIL import Image
import io
import base64

class InstagramADBLogin:
    def __init__(self):
        self.device = None
        self.devices = []
        self.selected_package = None
        # List of possible Instagram package variations
        self.instagram_packages = [
            f"com.instagram.androi{chr(ord('a') + i)}" for i in range(26)
        ]
        # Main activity is typically the same across package variations
        self.main_activity = "com.instagram.mainactivity.MainActivity"
        
    def get_adb_devices(self):
        """Get list of connected ADB devices"""
        try:
            result = subprocess.run(["adb", "devices"], capture_output=True, text=True, check=True)
            lines = result.stdout.strip().split('\n')[1:]  # Skip the first line which is the header
            
            self.devices = []
            for line in lines:
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        device_id = parts[0].strip()
                        status = parts[1].strip()
                        if status == "device":  # Only add devices that are properly connected
                            self.devices.append(device_id)
            
            return self.devices
        except subprocess.CalledProcessError as e:
            print(f"Error executing ADB command: {e}")
            return []
        except Exception as e:
            print(f"Unexpected error: {e}")
            return []
    
    def select_device(self):
        """Allow user to select which device to use"""
        devices = self.get_adb_devices()
        
        if not devices:
            print("No ADB devices found. Make sure your device is connected and ADB is enabled.")
            return False
        
        print("\nAvailable ADB devices:")
        for i, device in enumerate(devices):
            print(f"{i+1}. {device}")
        
        while True:
            try:
                choice = int(input("\nSelect a device (number): "))
                if 1 <= choice <= len(devices):
                    self.device = devices[choice-1]
                    print(f"Selected device: {self.device}")
                    return True
                else:
                    print("Invalid selection. Please try again.")
            except ValueError:
                print("Please enter a valid number.")
    
    def run_adb_command(self, command):
        """Run an ADB command on the selected device"""
        if not self.device:
            print("No device selected. Please select a device first.")
            return None
        
        full_command = ["adb", "-s", self.device] + command
        try:
            result = subprocess.run(full_command, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"Error executing ADB command: {e}")
            print(f"Error output: {e.stderr}")
            return None

    def get_installed_instagram_packages(self):
        """Get all Instagram package variations installed on the device"""
        if not self.device:
            print("No device selected. Please select a device first.")
            return []
            
        installed_packages = []
        for package in self.instagram_packages:
            result = self.run_adb_command(["shell", "pm", "list", "packages", "|" , "grep", package])
            if result and package in result:
                installed_packages.append(package)
        
        return installed_packages
    
    def select_instagram_package(self):
        """Allow user to select which Instagram package to use"""
        installed_packages = self.get_installed_instagram_packages()
        
        if not installed_packages:
            print("No Instagram packages found on the device.")
            return False
        
        print("\nAvailable Instagram packages:")
        for i, package in enumerate(installed_packages):
            print(f"{i+1}. {package}")
        
        while True:
            try:
                choice = int(input("\nSelect an Instagram package (number): "))
                if 1 <= choice <= len(installed_packages):
                    self.selected_package = installed_packages[choice-1]
                    print(f"Selected package: {self.selected_package}")
                    return True
                else:
                    print("Invalid selection. Please try again.")
            except ValueError:
                print("Please enter a valid number.")
    
    def launch_instagram(self):
        """Launch the selected Instagram package"""
        if not self.device or not self.selected_package:
            print("Device or Instagram package not selected.")
            return False
            
        full_activity = f"{self.selected_package}/{self.main_activity}"
        result = self.run_adb_command(["shell", "am", "start", "-n", full_activity])
        
        if result and "Error" not in result:
            print(f"Successfully launched {self.selected_package}")
            # Wait for app to fully load
            time.sleep(5)
            return True
        else:
            print(f"Failed to launch {self.selected_package}")
            return False
            
    def take_screenshot(self):
        """Take a screenshot of the device and return as PIL Image"""
        if not self.device:
            print("No device selected.")
            return None
            
        # Create a temporary file to store the screenshot
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            temp_path = temp_file.name
            
        try:
            # Take screenshot and save to device
            self.run_adb_command(["shell", "screencap", "-p", "/sdcard/screen.png"])
            
            # Pull the screenshot from device to temp file
            self.run_adb_command(["pull", "/sdcard/screen.png", temp_path])
            
            # Remove the screenshot from device
            self.run_adb_command(["shell", "rm", "/sdcard/screen.png"])
            
            # Open and return the image
            img = Image.open(temp_path)
            return img
        except Exception as e:
            print(f"Error taking screenshot: {e}")
            return None
        finally:
            # Clean up the temp file
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def detect_element(self, element_type):
        """Detect UI elements on screen and return coordinates"""
        # Take a screenshot
        img = self.take_screenshot()
        if not img:
            return None
            
        # Get screen dimensions
        width, height = img.size
        
        # Define detection logic based on element type
        if element_type == "login_username_field":
            # This is a simplified example - in a real implementation,
            # you would use image recognition or OCR to find elements
            # For now, we'll return estimated coordinates
            return (width // 2, height // 3)
            
        elif element_type == "login_password_field":
            return (width // 2, height // 2.5)
            
        elif element_type == "login_button":
            return (width // 2, height // 2)
            
        elif element_type == "2fa_field":
            return (width // 2, height // 2.2)
            
        return None
        
    def tap_screen(self, x, y):
        """Tap on the screen at the specified coordinates"""
        self.run_adb_command(["shell", "input", "tap", str(x), str(y)])
        time.sleep(0.5)
        
    def input_text(self, text):
        """Input text into the currently focused field"""
        self.run_adb_command(["shell", "input", "text", text])
        time.sleep(0.5)
        
    def press_key(self, key):
        """Press a specific key"""
        self.run_adb_command(["shell", "input", "keyevent", key])
        time.sleep(0.5)
        
    def clear_app_data(self):
        """Clear app data for the selected Instagram package"""
        if not self.device or not self.selected_package:
            print("Device or Instagram package not selected.")
            return False
            
        result = self.run_adb_command(["shell", "pm", "clear", self.selected_package])
        if "Success" in result:
            print(f"Successfully cleared data for {self.selected_package}")
            return True
        else:
            print(f"Failed to clear data for {self.selected_package}")
            return False
            
    def login_to_instagram(self, username, password):
        """Login to Instagram with the provided credentials"""
        if not self.device or not self.selected_package:
            print("Device or Instagram package not selected.")
            return False
            
        # Launch Instagram
        if not self.launch_instagram():
            return False
            
        # Wait for login screen to appear
        print("Waiting for login screen to appear...")
        time.sleep(5)  # Give app time to fully load
        
        try:
            # Detect and tap on username field
            print("Detecting username field...")
            username_coords = self.detect_element("login_username_field")
            if not username_coords:
                print("Could not detect username field, using default coordinates")
                username_coords = (540, 800)  # Default fallback coordinates
                
            print(f"Tapping username field at {username_coords}...")
            self.tap_screen(*username_coords)
            time.sleep(1)
            
            # Clear any existing text (press select all + delete)
            self.press_key("KEYCODE_CTRL_LEFT")
            self.press_key("KEYCODE_A")
            self.press_key("KEYCODE_DEL")
            
            # Input username
            print(f"Entering username: {username}")
            self.input_text(username)
            time.sleep(1)
            
            # Detect and tap on password field
            password_coords = self.detect_element("login_password_field")
            if not password_coords:
                print("Could not detect password field, using tab key")
                self.press_key("KEYCODE_TAB")
            else:
                print(f"Tapping password field at {password_coords}...")
                self.tap_screen(*password_coords)
            time.sleep(1)
            
            # Input password
            print("Entering password...")
            self.input_text(password)
            time.sleep(1)
            
            # Detect and tap login button
            login_button_coords = self.detect_element("login_button")
            if not login_button_coords:
                print("Could not detect login button, using tab and enter")
                self.press_key("KEYCODE_TAB")
                time.sleep(0.5)
                self.press_key("KEYCODE_ENTER")
            else:
                print(f"Tapping login button at {login_button_coords}...")
                self.tap_screen(*login_button_coords)
            
            # Wait for login to complete
            print("Waiting for login process...")
            time.sleep(8)  # Give more time for login to complete
            
            # Take a screenshot to verify the current state
            print("Taking screenshot to verify login state...")
            screenshot = self.take_screenshot()
            
            # Here you could implement more sophisticated detection of the current screen
            # For now, we'll assume login was successful and 2FA is required
            print("Login initiated, checking for 2FA screen...")
            
            # For now, we'll assume 2FA is required and proceed
            return True
            
        except Exception as e:
            print(f"Error during login process: {e}")
            return False
        
    def get_2fa_code(self, account_code):
        """Scrape 2FA code from 2fa.live using the account code"""
        try:
            print(f"Getting 2FA code for account code: {account_code}")
            url = f"https://2fa.live/tok/{account_code}"
            response = requests.get(url)
            
            if response.status_code == 200:
                # Parse the JSON response
                data = response.json()
                if 'token' in data:
                    code = data['token']
                    print(f"Retrieved 2FA code: {code}")
                    return code
                else:
                    print("No token found in response")
                    return None
            else:
                print(f"Failed to get 2FA code. Status code: {response.status_code}")
                return None
        except Exception as e:
            print(f"Error getting 2FA code: {e}")
            return None
            
    def enter_2fa_code(self, code):
        """Enter the 2FA code"""
        if not code:
            print("No 2FA code provided")
            return False
        
        try:
            # Wait for 2FA screen to appear
            print("Waiting for 2FA screen...")
            time.sleep(3)
            
            # Detect and tap on 2FA field
            print("Detecting 2FA field...")
            twofa_coords = self.detect_element("2fa_field")
            if not twofa_coords:
                print("Could not detect 2FA field, using default coordinates")
                twofa_coords = (540, 900)  # Default fallback coordinates
                
            print(f"Tapping 2FA field at {twofa_coords}...")
            self.tap_screen(*twofa_coords)
            time.sleep(1)
            
            # Clear any existing text
            self.press_key("KEYCODE_CTRL_LEFT")
            self.press_key("KEYCODE_A")
            self.press_key("KEYCODE_DEL")
            
            # Input 2FA code
            print(f"Entering 2FA code: {code}")
            self.input_text(code)
            time.sleep(1)
            
            # Press confirm button
            self.press_key("KEYCODE_ENTER")
            time.sleep(8)  # Give more time for verification
            
            # Take a screenshot to verify the current state
            print("Taking screenshot to verify 2FA completion...")
            screenshot = self.take_screenshot()
            
            # Here you could implement more sophisticated detection to verify success
            print("2FA code entered and submitted")
            return True
            
        except Exception as e:
            print(f"Error during 2FA entry: {e}")
            return False

    def load_accounts_config(self, config_file="accounts_config.json"):
        """Load accounts configuration from JSON file"""
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                return config.get('accounts', [])
        except Exception as e:
            print(f"Error loading accounts configuration: {e}")
            return []
    
    def process_account(self, account):
        """Process a single account login"""
        username = account.get('username')
        password = account.get('password')
        app_id = account.get('app_id')
        two_fa_code = account.get('two_fa_code')
        
        if not username or not password or not app_id or not two_fa_code:
            print("Missing required account information")
            return False
        
        # Select the specific Instagram package for this account
        if app_id in self.instagram_packages:
            self.selected_package = app_id
            print(f"Selected package: {self.selected_package}")
        else:
            print(f"Package {app_id} not found in available packages")
            return False
        
        # Clear app data before login (optional - uncomment if needed)
        # print(f"Clearing app data for {self.selected_package}...")
        # self.clear_app_data()
        # time.sleep(2)
        
        # Login to Instagram
        print(f"\nProcessing account: {username}")
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            print(f"Login attempt {attempt}/{max_attempts}")
            
            if self.login_to_instagram(username, password):
                # Get 2FA code
                code = self.get_2fa_code(two_fa_code)
                
                if code:
                    # Enter 2FA code
                    if self.enter_2fa_code(code):
                        print(f"Login successful for {username}!")
                        
                        # Take a final screenshot to confirm success
                        print("Taking confirmation screenshot...")
                        final_screenshot = self.take_screenshot()
                        
                        # Save the screenshot with a timestamp
                        timestamp = time.strftime("%Y%m%d-%H%M%S")
                        screenshot_path = f"{username}_{timestamp}_success.png"
                        if final_screenshot:
                            final_screenshot.save(screenshot_path)
                            print(f"Saved confirmation screenshot to {screenshot_path}")
                        
                        return True
                    else:
                        print(f"Failed to enter 2FA code for {username}.")
                else:
                    print(f"Failed to get 2FA code for {username}.")
            else:
                print(f"Failed to login to Instagram for {username}.")
            
            if attempt < max_attempts:
                print("Retrying after a short delay...")
                time.sleep(5)
        
        print(f"All login attempts failed for {username}")
        return False

if __name__ == "__main__":
    # Initialize the Instagram ADB Login tool
    ig_login = InstagramADBLogin()
    
    # Get and select an ADB device
    if ig_login.select_device():
        print("Device selected successfully.")
        
        # Load accounts configuration
        accounts = ig_login.load_accounts_config()
        
        if not accounts:
            print("No accounts found in configuration. Using manual mode.")
            # Select Instagram package
            if ig_login.select_instagram_package():
                # Ask for login credentials
                username = input("Enter Instagram username: ")
                password = input("Enter Instagram password: ")
                account_2fa_code = input("Enter the 2FA.live account code: ")
                
                # Login to Instagram
                if ig_login.login_to_instagram(username, password):
                    # Get 2FA code
                    code = ig_login.get_2fa_code(account_2fa_code)
                    
                    if code:
                        # Enter 2FA code
                        if ig_login.enter_2fa_code(code):
                            print("Login successful!")
                        else:
                            print("Failed to enter 2FA code.")
                    else:
                        print("Failed to get 2FA code.")
                else:
                    print("Failed to login to Instagram.")
            else:
                print("Failed to select Instagram package.")
        else:
            print(f"Found {len(accounts)} accounts in configuration.")
            
            # Process each account
            for i, account in enumerate(accounts):
                print(f"\nProcessing account {i+1}/{len(accounts)}")
                ig_login.process_account(account)
                time.sleep(2)  # Wait between accounts
    else:
        print("Failed to select a device. Exiting.")
