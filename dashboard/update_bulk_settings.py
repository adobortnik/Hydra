#!/usr/bin/env python
# Script to update specific settings in all account settings.db files
# Updates: enable_mention_to_story, post_type_to_share, and sharepost_mention

import os
import sqlite3
import sys

def get_db_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def update_account_setting(db_path, key, value):
    """
    Update a specific setting in an account's settings.db file
    """
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Check if the setting already exists
        cursor.execute("SELECT * FROM accountsettings WHERE key = ?", (key,))
        row = cursor.fetchone()
        
        if row:
            # Update existing setting
            cursor.execute(
                "UPDATE accountsettings SET value = ? WHERE key = ?",
                (value, key)
            )
            print(f"Updated existing setting '{key}' to '{value}'")
        else:
            # Insert new setting
            cursor.execute(
                "INSERT INTO accountsettings (key, value) VALUES (?, ?)",
                (key, value)
            )
            print(f"Inserted new setting '{key}' with value '{value}'")
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error updating setting in {db_path}: {e}")
        return False

def find_account_settings_dbs(base_dir):
    """Find all account-specific settings.db files"""
    settings_dbs = []
    
    # Look for device directories (these are typically IP addresses with port numbers)
    device_dirs = [d for d in os.listdir(base_dir) 
                  if os.path.isdir(os.path.join(base_dir, d)) and
                  not d.startswith('.') and
                  not d == 'the-livehouse-dashboard']
    
    for device_dir in device_dirs:
        device_path = os.path.join(base_dir, device_dir)
        
        # Look for account directories within each device directory
        try:
            account_dirs = [d for d in os.listdir(device_path) 
                           if os.path.isdir(os.path.join(device_path, d))]
            
            for account_dir in account_dirs:
                account_path = os.path.join(device_path, account_dir)
                settings_db_path = os.path.join(account_path, 'settings.db')
                
                if os.path.exists(settings_db_path):
                    settings_dbs.append((device_dir, account_dir, settings_db_path))
        except Exception as e:
            # Skip directories that can't be accessed
            print(f"Skipping directory {device_path}: {e}")
    
    return settings_dbs

def main():
    # Get the absolute path to the current script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Get the parent directory (which should be the main tool directory)
    base_dir = os.path.dirname(current_dir)
    
    print(f"Looking for settings databases in: {base_dir}")
    
    # Find all account-specific settings.db files
    settings_dbs = find_account_settings_dbs(base_dir)
    
    if not settings_dbs:
        print("No account-specific settings databases found.")
        return 1
    
    print(f"Found {len(settings_dbs)} account-specific settings databases:")
    for device_id, account_name, db_path in settings_dbs:
        print(f"  Device: {device_id}, Account: {account_name}, DB: {db_path}")
    
    # Settings to update
    settings_to_update = {
        "enable_mention_to_story": "true",  # Can be "true" or "false"
        "post_type_to_share": "post_reels",  # Can be "post_reels", "post_photos", or a value for both
        "sharepost_mention": "@Christian.jagg"  # Username to mention
    }
    
    # Ask for confirmation
    print("\nThe following settings will be updated for ALL accounts:")
    for key, value in settings_to_update.items():
        print(f"  {key}: {value}")
    
    confirm = input("\nDo you want to proceed? (yes/no): ")
    if confirm.lower() not in ['yes', 'y']:
        print("Operation cancelled.")
        return 0
    
    # Update settings for each account
    total_updated = 0
    for device_id, account_name, db_path in settings_dbs:
        print(f"\nUpdating settings for Device: {device_id}, Account: {account_name}")
        
        success = True
        for key, value in settings_to_update.items():
            if update_account_setting(db_path, key, value):
                total_updated += 1
            else:
                success = False
        
        if success:
            print(f"Successfully updated all settings for {account_name}")
        else:
            print(f"Some settings failed to update for {account_name}")
    
    print(f"\nUpdated {total_updated} settings across {len(settings_dbs)} accounts")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
