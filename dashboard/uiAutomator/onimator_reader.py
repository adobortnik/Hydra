#!/usr/bin/env python3
"""
Onimator Data Reader
Reads Onimator's data structures (accounts.db, settings.db, sources.txt)
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime


class OnimatorReader:
    """Reads Onimator data for a specific device"""

    def __init__(self, device_serial):
        """
        Initialize reader for a device

        Args:
            device_serial: Device serial (e.g., "10.1.10.183_5555")
        """
        self.device_serial = device_serial
        # uiAutomator is now inside the-livehouse-dashboard, device folders are 2 levels up
        self.device_folder = Path(__file__).parent.parent.parent / device_serial

        if not self.device_folder.exists():
            raise Exception(f"Device folder not found: {self.device_folder}")

    def get_accounts(self):
        """
        Read all accounts from {device_serial}/accounts.db

        Returns:
            List[dict]: List of account dicts with all fields from accounts table
        """
        accounts_db = self.device_folder / "accounts.db"

        if not accounts_db.exists():
            print(f"Warning: accounts.db not found at {accounts_db}")
            return []

        try:
            conn = sqlite3.connect(str(accounts_db))
            conn.row_factory = sqlite3.Row  # Return dict-like rows
            cursor = conn.cursor()

            accounts = []
            for row in cursor.execute("SELECT * FROM accounts"):
                accounts.append(dict(row))

            conn.close()
            return accounts

        except Exception as e:
            print(f"Error reading accounts.db: {e}")
            return []

    def get_accounts_for_current_hour(self):
        """
        Filter accounts where current hour is within their time window

        Returns:
            List[dict]: Accounts that should run now
        """
        current_hour = datetime.now().hour
        all_accounts = self.get_accounts()

        scheduled = []
        for account in all_accounts:
            try:
                start = int(account['starttime'])
                end = int(account['endtime'])

                # Handle time window that wraps midnight
                if start < end:
                    # Normal case: 14-16 (2 PM to 4 PM)
                    if start <= current_hour < end:
                        scheduled.append(account)
                else:
                    # Wrap case: 22-2 (10 PM to 2 AM)
                    if current_hour >= start or current_hour < end:
                        scheduled.append(account)

            except (KeyError, ValueError, TypeError) as e:
                print(f"Warning: Invalid time window for account {account.get('account', 'unknown')}: {e}")
                continue

        return scheduled

    def get_account_settings(self, username):
        """
        Read account settings from {device_serial}/{username}/settings.db

        Returns:
            dict: Parsed JSON settings or empty dict if not found
        """
        settings_db = self.device_folder / username / "settings.db"

        if not settings_db.exists():
            print(f"Warning: settings.db not found for {username}")
            return {}

        try:
            conn = sqlite3.connect(str(settings_db))
            cursor = conn.cursor()

            row = cursor.execute("SELECT settings FROM accountsettings WHERE id = 1").fetchone()
            conn.close()

            if row and row[0]:
                settings_json = row[0]
                return json.loads(settings_json)
            else:
                return {}

        except Exception as e:
            print(f"Error reading settings for {username}: {e}")
            return {}

    def get_account_sources(self, username):
        """
        Read target accounts from {device_serial}/{username}/sources.txt

        Returns:
            List[str]: List of target usernames
        """
        sources_file = self.device_folder / username / "sources.txt"

        if not sources_file.exists():
            print(f"Warning: sources.txt not found for {username}")
            return []

        try:
            sources = sources_file.read_text(encoding='utf-8').strip().split('\n')
            # Filter out empty lines and whitespace
            return [s.strip() for s in sources if s.strip()]

        except Exception as e:
            print(f"Error reading sources for {username}: {e}")
            return []

    def get_instagram_package(self, username):
        """
        Get Instagram package ID from account settings

        Returns:
            str: Package ID (e.g., "com.instagram.android")
        """
        settings = self.get_account_settings(username)
        # Default to original Instagram if not specified
        return settings.get('app_cloner', 'com.instagram.android')

    def account_folder_exists(self, username):
        """Check if account folder exists"""
        account_folder = self.device_folder / username
        return account_folder.exists()


def list_all_devices():
    """
    List all device folders in the project

    Returns:
        List[str]: List of device serials
    """
    # uiAutomator is now inside the-livehouse-dashboard, device folders are 2 levels up
    base_path = Path(__file__).parent.parent.parent

    devices = []
    for folder in base_path.iterdir():
        if folder.is_dir():
            # Check if it matches device serial pattern (IP_port format)
            name = folder.name
            if '_' in name and name.replace('_', '').replace('.', '').isdigit():
                devices.append(name)

    return devices


if __name__ == "__main__":
    # Test Onimator reader
    print("Testing Onimator reader...")

    # List all devices
    devices = list_all_devices()
    print(f"\nFound {len(devices)} device(s): {devices}")

    if devices:
        # Test with first device
        test_device = devices[0]
        print(f"\nTesting with device: {test_device}")

        reader = OnimatorReader(test_device)

        # Get all accounts
        accounts = reader.get_accounts()
        print(f"\nFound {len(accounts)} account(s) in accounts.db")

        if accounts:
            print("\nSample account:")
            sample = accounts[0]
            print(f"  Username: {sample.get('account')}")
            print(f"  Time window: {sample.get('starttime')}-{sample.get('endtime')}")
            print(f"  Follow enabled: {sample.get('follow')}")
            print(f"  Unfollow enabled: {sample.get('unfollow')}")

            # Test getting scheduled accounts
            scheduled = reader.get_accounts_for_current_hour()
            print(f"\nAccounts scheduled for current hour ({datetime.now().hour}): {len(scheduled)}")

            # Test getting account settings
            if reader.account_folder_exists(sample['account']):
                settings = reader.get_account_settings(sample['account'])
                print(f"\nAccount settings loaded: {len(settings)} settings")

                # Test getting sources
                sources = reader.get_account_sources(sample['account'])
                print(f"Sources loaded: {len(sources)} sources")

                if sources:
                    print(f"  Sample sources: {sources[:5]}")

                # Test getting Instagram package
                package = reader.get_instagram_package(sample['account'])
                print(f"Instagram package: {package}")
            else:
                print(f"\nAccount folder not found for {sample['account']}")

    print("\nOnimator reader test complete!")
